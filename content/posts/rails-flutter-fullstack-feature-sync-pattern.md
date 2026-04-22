---
title: "Rails + Flutter 풀스택에서 기능 하나를 웹-API-앱까지 관통시키는 패턴"
date: 2025-03-25
draft: false
tags: ["Rails", "Flutter", "Freezed", "Web Share API", "Stimulus"]
categories: ["Flutter", "Rails"]
description: "Rails 백엔드에 성별 토글, 코트 선수 교체 모달, 초대 링크 공유를 구현하고 API serializer를 거쳐 Flutter Freezed 모델까지 동기화한 실전 기록. before_action 누락, private method 에러, precompiled assets 캐시 등 삽질 포함."
---

## 하나의 기능이 세 개의 레이어를 관통할 때

웹 서비스에 새 기능을 추가하면 끝이 아니다. 모바일 앱이 있으면 API serializer를 거쳐 Flutter 모델까지 맞춰야 한다. 이 과정에서 빠뜨리기 쉬운 게 한두 가지가 아니다.

테니스 대회 운영 서비스를 만들고 있는데, 선수 성별 토글 하나를 추가하는 작업이 결국 Rails enum 정의 → ERB 뷰 토글 버튼 → Controller 액션 → API v2 serializer → Flutter Freezed 모델 → Flutter UI 위젯까지 6단계를 거쳤다. 그 과정에서 만난 에러들과 해결 패턴을 정리했다.

---

## 전체 아키텍처: 기능이 흐르는 경로

```
[Rails Model]  →  [Controller Action]  →  [ERB View / Stimulus JS]
                         ↓
              [API v2 Serializer]  →  camelCase JSON
                         ↓
           [Flutter Model (Freezed)]  →  [Entity]  →  [UI Widget]
```

Rails 8 + Hotwire(Stimulus + Turbo) 웹과 Flutter 앱이 같은 PostgreSQL 백엔드를 공유하는 구조다. 웹은 Turbo Stream으로 부분 갱신하고, 앱은 REST API v2를 호출한다.

핵심은 **하나의 DB 컬럼 추가가 6개 파일에 영향을 준다**는 것이다.

| 레이어 | 파일 | 역할 |
|--------|------|------|
| DB | migration | 컬럼 추가 |
| Model | `player.rb` | enum 정의 |
| Controller | `players_controller.rb` | `toggle_gender` 액션 |
| View | `index.html.erb` | 토글 버튼 렌더링 |
| API Serializer | `player_serializer.rb` | JSON에 gender 포함 |
| Flutter Model | `app_models.dart` | Freezed 필드 추가 |
| Flutter Entity | `app_entities.dart` | 도메인 모델 반영 |
| Flutter UI | `player_list_screen.dart` | 뱃지 표시 |

---

## 1. Rails enum + 토글 액션 구현

### DB migration은 이미 있는데 UI가 없는 상황

migration으로 `players` 테이블에 `gender` integer 컬럼을 추가하고, 모델에 enum을 선언한 상태였다.

```ruby
# app/models/player.rb
enum :gender, { male: 0, female: 1 }, prefix: true
```

문제는 선수 목록 페이지에서 성별을 설정할 수 있는 UI가 없었다는 것이다. 선수 편집 폼(`_form.html.erb`)에는 select 드롭다운이 있었지만, 운영 중에 폼을 열어서 하나씩 수정하는 건 비현실적이다.

### 토글 방식 결정: 별도 액션 vs 기존 update

처음에는 기존 `update` 액션에 gender 파라미터를 넘기려 했다. 그런데 `normalized_player_params` 메서드가 seed 값이 빈 문자열이면 자동으로 다음 시드를 배정하는 로직이 있었다.

```ruby
def normalized_player_params(existing_player: nil)
  permitted = player_params.to_h
  seed_value = permitted["seed"].presence
  permitted["seed"] = seed_value.blank? ? next_available_seed(existing_player:) : normalized_seed_value(seed_value)
  permitted
end
```

성별만 바꾸려고 PATCH를 보내면 seed가 빈 값으로 들어가서 **의도치 않게 시드가 재배정**된다. 이런 사이드 이펙트를 피하려면 별도의 `toggle_gender` 액션을 만드는 게 안전하다.

```ruby
def toggle_gender
  authorize @player, :update?
  next_gender = case @player.gender
                when "male"   then "female"
                when "female" then nil
                else               "male"
                end
  @player.update!(gender: next_gender)
  redirect_back fallback_location: tournament_players_path(@tournament),
    notice: "#{@player.display_name}: #{next_gender == 'male' ? '남' : next_gender == 'female' ? '여' : '미지정'}"
end
```

### 삽질: before_action 누락

`toggle_gender`를 만들고 바로 테스트했더니 에러가 났다.

```
NoMethodError: undefined method 'dom_id' for an instance of PlayersController
```

원인은 두 가지였다:

1. `before_action :set_player` 목록에 `toggle_gender`가 빠져 있었다
2. Turbo Stream 응답에서 `dom_id(@player)`를 호출했는데, 컨트롤러에서는 `ActionView::RecordIdentifier`를 include하지 않으면 `dom_id`를 쓸 수 없다

카드 레이아웃이라 Turbo Stream 부분 교체가 복잡해서, 결국 `redirect_back`으로 단순화했다.

```ruby
before_action :set_player, only: %i[show update destroy update_status toggle_gender withdraw stats notify unlink]
```

**교훈**: 새 액션을 추가하면 `before_action` 목록을 반드시 확인하자. Rails가 에러를 던지는 시점이 뷰 렌더링 중이라 원인을 찾기 어렵다.

---

## 2. Stimulus DnD에 교체 모달 추가

### 기존 구조: 빈 코트에만 드롭 가능

친선 모드 대시보드에서 선수를 코트에 드래그 앤 드롭으로 배치하는 기능이 있었다. `player_drag_controller.js`가 Stimulus로 구현되어 있고, 코트 요소에 `data-court-empty="true/false"` 속성으로 드롭 가능 여부를 판단했다.

```javascript
dragOver(e) {
  const court = e.currentTarget
  if (court.dataset.courtEmpty !== "true") return  // 이미 선수가 있으면 무시
  e.preventDefault()
}
```

문제는 **이미 선수가 배치된 코트에 다른 선수를 드롭하면 아무 반응이 없다**는 것이었다. 운영자 입장에서는 "A 선수를 B 선수 자리에 교체"하고 싶은 경우가 많다.

### 해결: swappable 상태 추가 + 모달

코트 요소에 새로운 data attribute를 추가했다.

```erb
data-court-swappable="<%= (team_a_players.any? || team_b_players.any?) && !is_live && can_manage %>"
data-court-players="<%= (team_a_players + team_b_players).map { |mp|
  { id: mp.participant_id, name: mp.participant.display_name }
}.to_json.html_safe %>"
data-court-swap-url="<%= tournament_friendly_swap_player_on_court_path(tournament, court) %>"
```

드래그 시 빈 코트는 초록 링으로, 교체 가능한 코트는 주황 링으로 강조한다.

```javascript
_highlightDropTargets() {
  this.courtTargets.forEach(c => {
    if (c.dataset.courtEmpty === "true") {
      c.classList.add("ring-2", "ring-[color:var(--color-primary-400)]", "ring-offset-2")
    } else if (c.dataset.courtSwappable === "true") {
      c.classList.add("ring-2", "ring-amber-400", "ring-offset-2")
    }
  })
}
```

드롭하면 순수 JavaScript로 모달을 생성한다. Turbo Frame이 아닌 DOM 직접 조작 방식을 썼다. 선수 목록을 `data-court-players` JSON에서 파싱해서 버튼으로 표시하고, 클릭하면 swap API를 호출한다.

```javascript
_showSwapModal(courtEl, newPlayerId) {
  const players = JSON.parse(courtEl.dataset.courtPlayers || "[]")
  // 모달 HTML 생성 → 각 선수를 버튼으로 표시
  // 버튼 클릭 시 _swapPlayer(courtEl, newPlayerId, removePlayerId, swapUrl) 호출
}
```

백엔드 swap 액션은 기존 선수의 team_side와 position을 보존하면서 교체한다.

```ruby
def swap_player_on_court
  mp = match.match_players.find_by(participant_id: old_player_id)
  old_team_side = mp.team_side
  old_position  = mp.position
  mp.destroy!
  match.match_players.create!(participant: new_player, team_side: old_team_side, position: old_position)
end
```

---

## 3. Web Share API로 선수 초대 링크

### navigator.share() + 클립보드 폴백

계정이 연결되지 않은 선수에게 가입을 유도하는 기능이 필요했다. 대회 공유 URL과 참가 코드를 포함한 메시지를 카카오톡이나 문자로 보내는 게 목표다.

Web Share API는 모바일에서 네이티브 공유 시트를 띄워준다. iOS Safari, Android Chrome 모두 지원하고, 카카오톡/문자/에어드롭 등 설치된 앱 목록이 나온다.

```javascript
async share() {
  const url = this.urlValue || window.location.href
  const title = this.hasTitleValue ? this.titleValue : document.title
  const text = this.hasTextValue ? this.textValue : ""

  if (navigator.share) {
    try {
      await navigator.share({ title, text, url })
      return
    } catch { /* 사용자가 취소하거나 미지원 */ }
  }

  // 폴백: 클립보드에 복사 + 토스트 알림
  await this.copyToClipboard(`${text}\n${url}`)
}
```

주의할 점이 있다. `navigator.share()`는 **사용자 제스처(클릭 이벤트) 안에서만 호출 가능**하다. 페이지 로드 시 자동으로 호출하면 `NotAllowedError`가 발생한다. MDN 문서에서는 이를 "transient activation" 요건이라고 설명한다.

데스크톱 브라우저에서는 `navigator.share`가 없는 경우가 많으므로, 클립보드 복사 + 토스트 알림으로 폴백한다. 실제로 이 패턴이 가장 범용적이다.

### 삽질: private method 에러

초대 URL을 생성할 때 `@tournament.share_url(base_url: request.base_url)`을 호출했더니 에러가 났다.

```
NoMethodError: private method 'share_url' called for an instance of Tournament
```

모델에 `share_url` 메서드가 있지만 private 영역에 있었다. 뷰에서 직접 URL을 구성하는 걸로 우회했다.

```erb
data-share-url-url-value="<%= @tournament.share_token.present? ?
  "#{request.base_url}/t/#{@tournament.share_token}" : root_url %>"
```

---

## 4. API Serializer → Flutter Freezed 동기화

### 빠뜨리기 가장 쉬운 구간

웹에서 기능이 잘 동작해도 API serializer에 새 필드를 빼먹으면 앱에서는 null로 온다. serializer 수정은 한 줄이지만, 이걸 잊으면 앱 개발자가 "API에서 gender가 안 내려와요"라고 할 때까지 모른다.

```ruby
# app/serializers/api/v2/player_serializer.rb
def as_json
  {
    id: resource.id,
    name: resource.name,
    gender: resource.gender,  # 이 한 줄 추가
    # ...
  }
end
```

### Flutter 쪽 변경: 4개 파일

Freezed를 쓰면 모델 변경이 체계적이지만 파일 수가 많다.

**1) Model (API 응답 매핑)**

```dart
// data/models/app_models.dart
@Freezed(fromJson: true, toJson: true)
abstract class PlayerModel with _$PlayerModel {
  const factory PlayerModel({
    @_StringifyId() required String id,
    required String name,
    int? seed,
    String? gender,  // 추가
    // ...
  }) = _PlayerModel;
}
```

**2) Entity (도메인 모델)**

```dart
// domain/entities/app_entities.dart
@freezed
abstract class PlayerEntity with _$PlayerEntity {
  const factory PlayerEntity({
    required String id,
    required String name,
    String? gender,  // 추가
    // ...
  }) = _PlayerEntity;
}
```

**3) Repository (Model → Entity 매핑)**

```dart
PlayerEntity(
  id: player.id,
  name: player.displayName ?? player.name,
  gender: player.gender,  // 매핑 추가
  // ...
)
```

**4) UI (뱃지 표시)**

```dart
if (gender != null) ...[
  Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
    decoration: BoxDecoration(
      color: gender == 'male' ? Colors.blue.shade50 : Colors.pink.shade50,
      borderRadius: BorderRadius.circular(99),
    ),
    child: Text(
      gender == 'male' ? '남' : '여',
      style: TextStyle(
        fontSize: 10, fontWeight: FontWeight.w700,
        color: gender == 'male' ? Colors.blue.shade700 : Colors.pink.shade700,
      ),
    ),
  ),
],
```

변경 후 `dart run build_runner build --delete-conflicting-outputs`로 코드 재생성한다. `.freezed.dart`와 `.g.dart` 파일이 갱신된다.

### Freezed + json_serializable 조합의 장단점

| 장점 | 단점 |
|------|------|
| immutable 모델 자동 생성 | build_runner 실행 필요 |
| copyWith, ==, hashCode 자동 | 생성 파일이 많아 프로젝트 복잡도 증가 |
| JSON 직렬화 자동 | API 필드 변경 시 수동 업데이트 필요 |
| union type으로 상태 관리 | 러닝 커브 존재 |

실무에서 가장 번거로운 건 **API 필드 변경 시 수동 업데이트**다. serializer에 필드를 추가하면 Flutter 쪽도 같이 건드려야 한다. OpenAPI 스펙 자동 생성 같은 도구를 쓰면 해결되지만, 소규모 프로젝트에서는 오버엔지니어링이 될 수 있다.

---

## 5. precompiled assets 캐시 문제

### 개발 중에 JS가 반영 안 될 때

Stimulus controller의 `share` 메서드를 추가했는데 브라우저에서 동작하지 않았다. 원인은 이전에 `bin/rails assets:precompile`을 실행해서 `public/assets/`에 정적 파일이 생성된 상태였기 때문이다.

Rails 개발 모드에서는 `public/assets/`가 있으면 **Sprockets/Propshaft가 동적으로 서빙하지 않고 정적 파일을 그대로 내려준다**. importmap의 digest가 옛날 파일을 가리키고 있어서 새 코드가 로딩되지 않는 것이다.

```bash
rm -rf public/assets/
bin/rails tailwindcss:build
# 서버 재시작
```

이렇게 precompiled assets를 삭제하면 개발 모드에서 소스 파일을 직접 서빙하게 된다.

**교훈**: 개발 중에 `assets:precompile`을 실행했다면, JS/CSS 변경 후 반드시 `public/assets/`를 삭제하자.

---

## 6. 자유 대진표 라운드 추가 기능

### generate vs add_round: 기존 경기 보존 여부

자유 대진표에서 "대진표 생성" 버튼은 기존 대기 경기를 모두 취소하고 새로 만든다.

```ruby
# generate 액션
pending_matches = @tournament.matches.where(status: :scheduled)
pending_matches.each { |m| m.update!(status: :cancelled) }
```

라운드를 추가하고 싶을 때는 기존 경기를 유지하면서 새 라운드만 붙여야 한다. 별도의 `add_round` 액션을 만들었다.

```ruby
def add_round
  # 기존 경기 건드리지 않음
  round = next_round!
  assignments.each_with_index do |assignment, index|
    court = available_courts[index % available_courts.size]
    match = @tournament.matches.create!(round: round, court: court, status: :scheduled)
    # 선수 배정...
  end
end
```

### 삽질: set_tournament 누락 (또)

`add_round` 액션을 만들고 테스트했더니 또 에러가 났다.

```
NoMethodError: undefined method 'players' for nil
```

`@tournament`이 nil이다. `before_action :set_tournament`의 `only:` 배열에 `add_round`를 추가하지 않았기 때문이다.

```ruby
before_action :set_tournament, only: [
  :show, :add_player, :remove_player, :update_courts,
  :generate, :add_round,  # 추가!
  :start_match, :start_all_matches, :complete_match, :enter_score
]
```

같은 실수를 두 번 했다. `before_action`의 `only:` 옵션을 쓰면 새 액션마다 목록 갱신이 필요하다. `except:`를 쓰거나 아예 빼는 게 나을 수도 있지만, 인증이 필요 없는 액션이 섞여 있으면 `only:`가 안전하다.

---

## 풀스택 기능 추가 체크리스트

같은 실수를 반복하지 않기 위해 정리한 체크리스트다.

| 순서 | 항목 | 확인 |
|------|------|------|
| 1 | DB migration 실행 | `rails db:migrate` |
| 2 | Model에 enum/validation 추가 | |
| 3 | Controller 액션 생성 | |
| 4 | `before_action` 목록에 새 액션 포함 | |
| 5 | Route 추가 | |
| 6 | View에 UI 추가 | |
| 7 | API serializer에 새 필드 추가 | |
| 8 | Flutter Model에 필드 추가 | |
| 9 | Flutter Entity에 필드 추가 | |
| 10 | Repository 매핑 업데이트 | |
| 11 | `build_runner` 재실행 | |
| 12 | Flutter UI에 표시 | |
| 13 | `flutter analyze` 통과 확인 | |

12단계라 많아 보이지만, 실제로 빠뜨리는 건 4번(before_action)과 7번(serializer)이다. 이 두 가지만 의식적으로 챙겨도 대부분의 삽질을 방지할 수 있다.

---

## 결론

Rails + Flutter 풀스택에서 기능 하나를 추가하는 건 단순히 코드를 작성하는 것보다 **레이어 간 동기화를 관리하는 일**에 가깝다. DB 컬럼 하나가 8개 파일에 영향을 주고, `before_action` 한 줄 빠뜨리면 런타임 에러가 나고, precompiled assets가 캐시되면 새 JS가 안 먹는다.

체크리스트를 만들어 놓고 기계적으로 따르는 게 가장 확실한 방법이다. 특히 serializer와 before_action은 눈에 잘 안 띄지만 빠뜨렸을 때 디버깅이 오래 걸리는 항목이니 주의하자.
