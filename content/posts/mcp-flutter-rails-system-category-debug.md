---
title: "MCP 도구 연동부터 Flutter 설정 토글까지 — 삽질 기록"
date: 2026-03-04
draft: false
tags: ["Rails", "Flutter", "BLoC", "MCP", "RSpec", "HydratedBloc"]
description: "MCP로 서버에 카테고리를 만들었는데 앱에서 안 보인다? API 응답 필드 누락부터 Flutter Freezed 엔티티 수정, 설정 토글 구현까지의 과정 정리"
---

MCP 도구로 서버 사이드에 카테고리를 생성했다.
그런데 모바일 앱에서 새 카테고리가 보이지 않았다.

간단해 보이는 문제였는데, 파고들수록 여러 레이어가 얽혀 있었다.

---

## 문제의 시작: MCP로 만든 카테고리가 앱에 안 보인다

MCP 도구를 통해 `dev/`, `memory` 같은 시스템 카테고리를 서버에 생성했다.
API를 직접 호출하면 데이터가 있다. 앱을 리프레시해도 나타나지 않는다.

첫 번째 가설: 앱이 캐시를 사용하는 건가?
→ 아니다. `PapersLoadRequested` + `PaperCategoriesLoadRequested` 이벤트를 순서대로 디스패치하고 있었고, 서버에서 정상 응답이 오고 있었다.

두 번째 가설: API가 필터링하고 있나?
→ Rails 컨트롤러를 봤다. 필터 없음. 전체 반환 중.

세 번째 가설: Flutter 앱에서 필터링하나?
→ 있었다. 의도한 건지 아닌지도 모르게 남아있던 필터 코드.

---

## 1단계: API 응답에 `is_system` 필드가 없었다

Rails `paper_categories_controller.rb`의 응답 직렬화 부분:

```ruby
# 기존
{
  id: paper_category.id.to_s,
  name: paper_category.name,
  color: paper_category.color,
  order: paper_category.order,
  updated_at: paper_category.updated_at.to_i,
  _count: { papers: paper_category.papers.count }
}
```

`is_system` 필드가 DB에는 있는데 응답에 포함되지 않고 있었다.
index, show, create, update, reorder — 다섯 곳 모두 추가했다.

```ruby
is_system: paper_category.is_system,
```

---

## 2단계: Flutter Freezed 엔티티에 필드 추가

`PaperCategory` 도메인 엔티티 (Freezed 사용):

```dart
// 수정 전
@freezed
class PaperCategory with _$PaperCategory {
  const factory PaperCategory({
    required String id,
    required String name,
    required String color,
    required DateTime createdAt,
    required DateTime updatedAt,
  }) = _PaperCategory;
}
```

`isSystem` 필드 추가:

```dart
@freezed
class PaperCategory with _$PaperCategory {
  const factory PaperCategory({
    required String id,
    required String name,
    required String color,
    required DateTime createdAt,
    required DateTime updatedAt,
    @Default(false) bool isSystem,  // 추가
  }) = _PaperCategory;
}
```

Freezed 사용 시 필드를 추가하면 반드시 코드 생성이 필요하다:

```bash
dart run build_runner build --delete-conflicting-outputs
```

이걸 빠뜨리면 런타임 에러 대신 컴파일 에러가 나서 금방 발견하긴 하지만, 습관적으로 실행해야 한다.

DTO에도 추가:

```dart
@JsonKey(name: 'is_system')
final bool isSystem;

// fromJson 커스텀 파서에도
isSystem: json['is_system'] as bool? ?? false,
```

`?? false` 기본값은 중요하다. 기존 데이터에 필드가 없는 경우 null이 올 수 있기 때문.

---

## 3단계: 단순 숨기기 말고, 설정으로 제어하자

처음 생각은 "시스템 카테고리는 그냥 숨기자"였다.
하지만 MCP로 생성한 카테고리를 앱에서도 탐색하고 싶은 케이스가 있다.

그래서 설정 탭에 토글로 제어하기로 했다.

### HydratedBloc 설정 상태 추가

`SettingsState`에 `showSystemCategories` 필드 추가:

```dart
@freezed
class SettingsState with _$SettingsState {
  const factory SettingsState({
    // ... 기존 필드들
    @Default(false) bool showSystemCategories,  // 기본: 숨김
  }) = _SettingsState;
}
```

`fromJson`/`toJson`도 함께 추가해야 HydratedBloc이 영속성을 보장한다.
빠뜨리면 앱 재시작 시 기본값으로 초기화되는 버그가 생긴다.

이벤트:

```dart
class SettingsShowSystemCategoriesChanged extends SettingsEvent {
  final bool enabled;
  const SettingsShowSystemCategoriesChanged(this.enabled);
}
```

핸들러:

```dart
on<SettingsShowSystemCategoriesChanged>((event, emit) {
  emit(state.copyWith(showSystemCategories: event.enabled));
});
```

### 설정 화면에 토글 추가

```dart
BlocSelector<SettingsBloc, SettingsState, bool>(
  selector: (state) => state.showSystemCategories,
  builder: (context, showSystemCategories) => SwitchListTile(
    secondary: const Icon(Icons.folder_special_outlined),
    title: const Text('시스템 카테고리 표시'),
    subtitle: const Text('MCP로 동기화된 카테고리를 메모 탭에 표시'),
    value: showSystemCategories,
    onChanged: (value) {
      context.read<SettingsBloc>().add(
        SettingsShowSystemCategoriesChanged(value),
      );
    },
  ),
),
```

`BlocSelector`를 쓰면 `showSystemCategories`가 바뀔 때만 이 위젯이 리빌드된다.
`BlocBuilder`로 전체 상태를 감시하면 다른 설정 변경 시에도 불필요한 리빌드가 발생한다.

### 카테고리 목록 화면에서 필터링

```dart
BlocSelector<SettingsBloc, SettingsState, bool>(
  selector: (s) => s.showSystemCategories,
  builder: (context, showSystemCategories) => PaperCategoryFilter(
    categories: showSystemCategories
        ? state.categories
        : state.categories.where((c) => !c.isSystem).toList(),
    selectedCategoryId: state.selectedCategoryId,
    onCategorySelected: ...,
    onAddCategory: ...,
  ),
),
```

여기서 한 가지 실수를 했다. `BlocSelector`로 `PaperCategoryFilter`를 감싼 후 괄호 닫기를 하나 빠뜨려서 컴파일 에러가 났다. Flutter 위젯 트리에서 중첩이 깊어질수록 괄호 관리가 까다롭다.

---

## 4단계: 테스트

기능을 구현했으면 테스트도 함께 간다.

### Rails RSpec

API 응답 구조가 중첩되어 있어서 헬퍼 메서드를 먼저 만들었다:

```ruby
def categories_list
  JSON.parse(response.body).dig('data', 'data')
end

def category_data
  JSON.parse(response.body)['data']
end
```

응답 구조: `{ success: true, data: { data: [...], meta: {...} } }`

`json['data']`만 하면 Array가 아닌 Hash가 나온다. `dig`으로 중첩 접근이 필요하다.

주요 테스트 케이스:

```ruby
it 'returns is_system true for dev root category' do
  PaperCategory.find_or_create_dev_root!(user)
  get '/api/paper-categories', headers: auth_headers
  dev = categories_list.find { |c| c['name'] == 'dev' }
  expect(dev['is_system']).to eq(true)
end

it 'returns is_system false for dev subcategories' do
  PaperCategory.find_or_create_dev_subcategory!(user, 'memory')
  get '/api/paper-categories', headers: auth_headers
  memory = categories_list.find { |c| c['name'] == 'memory' }
  expect(memory['is_system']).to eq(false)
end
```

시스템 카테고리 중에서도 루트(`dev`)만 `is_system: true`고, 하위 카테고리는 `false`다.
이 규칙을 명시적으로 테스트에 담아두는 게 나중에 혼란을 줄여준다.

### Flutter bloc_test

```dart
blocTest<SettingsBloc, SettingsState>(
  'toggles show system categories on',
  build: () => SettingsBloc(
    notificationService: mockNotificationService,
    liveActivityManager: mockLiveActivityManager,
  ),
  act: (bloc) => bloc.add(const SettingsShowSystemCategoriesChanged(true)),
  expect: () => [const SettingsState(showSystemCategories: true)],
);

test('showSystemCategories serializes and deserializes correctly', () {
  const state = SettingsState(showSystemCategories: true);
  final json = state.toJson();
  final restored = SettingsState.fromJson(json);
  expect(restored.showSystemCategories, true);
});
```

영속성 테스트가 중요하다. `HydratedBloc`을 쓰면 `toJson`/`fromJson`이 실제로 동작하는지 단위 테스트로 검증해둬야 한다. 새 필드를 추가하고 직렬화 코드를 빠뜨리면 앱 재시작 후 설정이 리셋되는데, 이런 버그는 수동으로 발견하기 어렵다.

---

## 마이그레이션 멱등성 (이번 주 다른 삽질)

이번 주에 배포 서버에서 `PG::DuplicateColumn` 에러가 났다.
로컬에서는 문제없이 돌아가던 마이그레이션이 프로덕션에서 터진 것이다.

원인: 이미 컬럼이 존재하는데 `add_column`을 다시 실행하려 했기 때문.

Rails 마이그레이션에서 멱등성을 보장하는 방법:

```ruby
# 컬럼
unless column_exists?(:paper_categories, :is_system)
  add_column :paper_categories, :is_system, :boolean, default: false, null: false
end

# 인덱스
unless index_exists?(:paper_categories, [:user_id, :is_system])
  add_index :paper_categories, [:user_id, :is_system]
end
```

또는 Rails 6.1+에서는:

```ruby
add_column :paper_categories, :is_system, :boolean, default: false, null: false,
           if_not_exists: true
```

로컬과 프로덕션의 DB 상태가 달라지는 건 언제든 발생할 수 있다.
마이그레이션을 처음부터 멱등하게 작성하는 습관이 중요하다.

---

## 정리

이번 작업에서 건진 것들:

1. **API 응답 설계**: DB에 있다고 해서 자동으로 응답에 포함되는 게 아니다. 필드를 명시적으로 직렬화해야 한다.

2. **Freezed 엔티티 수정 후 build_runner**: 빠뜨리면 안 된다. CI에 넣어두는 게 맞다.

3. **HydratedBloc + toJson/fromJson**: 새 필드 추가 시 직렬화 코드도 함께 수정. 영속성 단위 테스트로 검증.

4. **BlocSelector vs BlocBuilder**: 특정 필드만 감시할 때는 `BlocSelector`. 불필요한 리빌드를 방지한다.

5. **마이그레이션 멱등성**: `column_exists?`, `index_exists?` 또는 `if_not_exists: true`로 방어.

기능 하나 추가하는 데 레이어가 많다. API → DTO → Entity → Repository → BLoC Event/State → UI → Test. 각 레이어를 순서대로 따라가면 빠뜨리는 게 없다.
