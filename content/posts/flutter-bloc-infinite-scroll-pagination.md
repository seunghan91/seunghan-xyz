---
title: "Flutter BLoC 무한스크롤 구현 — 외부 패키지 없이 레이어별로 설계하기"
date: 2025-09-20
draft: false
tags: ["Flutter", "BLoC", "무한스크롤", "페이지네이션", "ScrollController", "UX"]
description: "infinite_scroll_pagination 없이 순수 BLoC + ScrollController로 무한스크롤을 구현하는 방법. Datasource → Repository → BLoC → UI까지 레이어별로 어떻게 나눠야 하는지 정리했다."
cover:
  image: "/images/og/flutter-bloc-infinite-scroll-pagination.png"
  alt: "Flutter Bloc Infinite Scroll Pagination"
  hidden: true
---

목록을 처음에 전부 로드하면 느리다. 사용자가 스크롤할수록 자연스럽게 다음 데이터를 불러오는 무한스크롤이 필요했다.

`infinite_scroll_pagination` 같은 패키지도 있지만, 기존 BLoC 구조에 그대로 얹으려면 상태 설계를 패키지 방식에 맞춰야 해서 오히려 복잡해지는 경우가 있다. 외부 의존 없이 `ScrollController`만으로도 충분히 만들 수 있어서 그 방향으로 구현했다.

---

## 왜 Offset 기반인가

페이지네이션 방식은 두 가지다.

**Offset 기반 (page 번호)**
```
GET /items?page=1&per_page=20
GET /items?page=2&per_page=20
```

**Cursor 기반 (마지막 아이템 ID)**
```
GET /items?cursor=abc123&per_page=20
```

Cursor 방식이 "데이터가 중간에 삽입/삭제돼도 중복/누락 없다"는 점에서 이론적으로 더 우수하다. 하지만 대상 데이터가 법령/규정처럼 **자주 바뀌지 않는 정적 문서**라면 Offset 방식으로 충분하다.

구현도 단순하고, 백엔드에서 `page`와 `per_page` 쿼리 파라미터만 지원하면 된다.

---

## 레이어 설계

전체를 4단계 레이어로 나눴다.

```
Datasource    searchLawsPaginated(page, perPage) → LawsPage
Repository    getLawsPaginated(query, category, page, perPage) → LawsPage
BLoC          LoadLaws(첫 페이지), FetchMoreLaws(다음 페이지)
UI            ScrollController + ListView + 바텀 인디케이터
```

---

## 1. 응답 타입 정의

Repository 인터페이스에 결과를 담을 타입을 추가했다.

```dart
class LawsPage {
  final List<Law> laws;
  final bool hasMore;

  const LawsPage({required this.laws, required this.hasMore});
}
```

---

## 2. Datasource — API 호출

기존 `searchLaws()`는 그대로 두고, 페이지네이션 전용 메서드를 추가했다.

```dart
Future<LawsPage> searchLawsPaginated({
  String? query,
  String? category,
  int page = 1,
  int perPage = 20,
}) async {
  final params = <String, dynamic>{
    'page': page,
    'per_page': perPage,
  };
  if (query != null && query.isNotEmpty) params['q'] = query;
  if (category != null && category != '전체') params['category'] = category;

  final response = await _client.get<Map<String, dynamic>>(
    '/items/search',
    queryParameters: params,
  );

  final laws = _extractList(response.data);

  // 백엔드가 meta.has_more를 주면 사용, 없으면 length로 추정
  final meta = response.data?['meta'] as Map<String, dynamic>?;
  final hasMore = meta?['has_more'] as bool? ?? laws.length >= perPage;

  return LawsPage(laws: laws, hasMore: hasMore);
}
```

`has_more` 필드를 백엔드가 아직 내려주지 않더라도, `length >= perPage`로 추정할 수 있다. 정확하지는 않지만 실제로는 거의 맞는다.

---

## 3. BLoC — 이벤트와 상태 확장

기존 `LawsLoaded` 상태에 페이지네이션 필드를 추가했다.

```dart
class LawsLoaded extends LawsState {
  final List<Law> laws;
  final String? query;
  final String? activeCategory;
  final int currentPage;
  final bool hasMore;
  final bool isLoadingMore;

  const LawsLoaded({
    required this.laws,
    this.query,
    this.activeCategory,
    this.currentPage = 1,
    this.hasMore = true,
    this.isLoadingMore = false,
  });

  LawsLoaded copyWith({...}) => LawsLoaded(...);
}
```

이벤트는 두 가지다.

```dart
class LoadLaws extends LawsEvent {}       // 첫 페이지 (검색/카테고리 변경 포함)
class FetchMoreLaws extends LawsEvent {}  // 다음 페이지
```

핵심은 `LoadLaws`와 `FetchMoreLaws`의 역할을 완전히 분리하는 것이다.

```dart
// 첫 페이지 — 항상 page=1 부터 새로
Future<void> _onLoadLaws(LoadLaws event, Emitter<LawsState> emit) async {
  emit(LawsLoading());  // 전체 로딩 스피너
  try {
    final result = await repository.getLawsPaginated(
      query: event.query?.trim(),
      category: event.category,
      page: 1,
      perPage: _perPage,
    );
    emit(LawsLoaded(
      laws: result.laws,
      query: event.query?.trim(),
      activeCategory: event.category,
      currentPage: 1,
      hasMore: result.hasMore,
    ));
  } catch (e) {
    emit(LawsError(e.toString()));
  }
}

// 다음 페이지 — 기존 리스트에 append
Future<void> _onFetchMoreLaws(FetchMoreLaws event, Emitter<LawsState> emit) async {
  final current = state;
  if (current is! LawsLoaded) return;
  if (!current.hasMore || current.isLoadingMore) return;

  emit(current.copyWith(isLoadingMore: true));  // 바텀 스피너만
  try {
    final result = await repository.getLawsPaginated(
      query: current.query,
      category: current.activeCategory,
      page: current.currentPage + 1,
      perPage: _perPage,
    );
    emit(current.copyWith(
      laws: [...current.laws, ...result.laws],
      currentPage: current.currentPage + 1,
      hasMore: result.hasMore,
      isLoadingMore: false,
    ));
  } catch (_) {
    emit(current.copyWith(isLoadingMore: false));
    // 추가 로딩 실패 시 기존 데이터 유지, 조용히 실패
  }
}
```

에러 처리 방식의 차이가 중요하다.
- 첫 페이지 실패 → `LawsError` 상태로 전환 (전체 에러 화면)
- 추가 페이지 실패 → 기존 `LawsLoaded` 유지, `isLoadingMore`만 false로 (데이터 손실 없음)

스크롤을 50개 넘어서 내려왔는데 다음 페이지 로딩이 실패했다고 전체 에러 화면이 뜨면 최악이다.

---

## 4. UI — ScrollController와 바텀 인디케이터

```dart
class _ListPageState extends State<ListPage> {
  final _scrollController = ScrollController();
  static const _fetchThreshold = 300.0;

  @override
  void initState() {
    super.initState();
    context.read<LawsBloc>().add(const LoadLaws());
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    super.dispose();
  }

  void _onScroll() {
    final pos = _scrollController.position;
    // 하단 300px 남으면 미리 다음 페이지 fetch
    if (pos.pixels >= pos.maxScrollExtent - _fetchThreshold) {
      final state = context.read<LawsBloc>().state;
      if (state is LawsLoaded && state.hasMore && !state.isLoadingMore) {
        context.read<LawsBloc>().add(const FetchMoreLaws());
      }
    }
  }
```

300px 전에 미리 fetch하는 이유는 사용자가 스크롤 끝에 닿기 전에 다음 데이터가 로드되도록 하기 위해서다. 너무 일찍 잡으면 API 호출이 과도해지고, 너무 늦게 잡으면 로딩 스피너가 보인다. 200~400px 사이가 적당하다.

ListView는 `itemCount: laws.length + 1`로 설정하고, 마지막 아이템을 바텀 인디케이터로 쓴다.

```dart
RefreshIndicator(
  onRefresh: _onRefresh,
  child: ListView.separated(
    controller: _scrollController,
    physics: const AlwaysScrollableScrollPhysics(),
    itemCount: laws.length + 1,
    itemBuilder: (context, index) {
      if (index == laws.length) {
        // 바텀 아이템
        if (isLoadingMore) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2.5)),
          );
        }
        if (!hasMore && laws.isNotEmpty) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Center(
              child: Text('총 ${laws.length}개를 모두 불러왔습니다'),
            ),
          );
        }
        return const SizedBox.shrink();
      }
      return ItemCard(item: laws[index]);
    },
  ),
),
```

`AlwaysScrollableScrollPhysics()`는 pull-to-refresh가 아이템이 적을 때도 동작하게 하기 위해 필요하다.

---

## pull-to-refresh 처리

검색어/카테고리가 변경되면 자동으로 `LoadLaws`가 dispatch되어 page=1부터 새로 시작한다.

pull-to-refresh도 같은 `LoadLaws`를 쓴다.

```dart
Future<void> _onRefresh() async {
  context.read<LawsBloc>().add(LoadLaws(
    query: _searchController.text.trim(),
    category: _activeCategory,
  ));
  // 로딩이 끝날 때까지 대기
  await context.read<LawsBloc>().stream.firstWhere(
    (s) => s is LawsLoaded || s is LawsError,
  );
}
```

`stream.firstWhere`로 다음 완료 상태를 기다리면 RefreshIndicator가 적절한 시점에 사라진다.

---

## 백엔드에 필요한 것

프론트가 준비됐어도 백엔드가 페이지네이션을 지원하지 않으면 소용없다. Rails 기준으로 최소한 이 정도면 된다.

```ruby
def index
  laws = Law.all
  laws = laws.where(category: params[:category]) if params[:category].present?
  laws = laws.where("title LIKE ?", "%#{params[:q]}%") if params[:q].present?

  page     = (params[:page]     || 1).to_i
  per_page = (params[:per_page] || 20).to_i.clamp(1, 100)

  paginated = laws.offset((page - 1) * per_page).limit(per_page + 1)
  has_more  = paginated.length > per_page
  items     = paginated.first(per_page)

  render json: {
    data: items.map { |l| LawSerializer.new(l).as_json },
    meta: { has_more: has_more, page: page, per_page: per_page }
  }
end
```

`limit(per_page + 1)`을 가져와서 `per_page`개를 초과하면 다음 페이지가 있다는 걸 알 수 있다. 별도의 COUNT 쿼리 없이 처리하는 흔한 패턴이다.

---

## 정리

| 구분 | 선택 | 이유 |
|---|---|---|
| 페이지네이션 방식 | Offset (page 번호) | 정적 데이터, 구현 단순 |
| 감지 방법 | ScrollController | 추가 패키지 불필요 |
| 외부 패키지 | 없음 | 기존 BLoC 구조와 자연스럽게 통합 |
| fetch 시점 | 하단 300px 전 | 스크롤 끝 닿기 전에 미리 로드 |
| 에러 처리 | 첫 페이지: 전체 에러, 추가 페이지: 기존 데이터 유지 | UX 손실 최소화 |

가장 중요한 부분은 `LoadLaws`와 `FetchMoreLaws`의 에러 처리를 다르게 가져가는 것이다. 첫 로딩 실패와 추가 로딩 실패는 사용자 경험에서 완전히 다른 상황이다.
