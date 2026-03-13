---
title: "Flutter BLoC Infinite Scroll Implementation — Layer-by-Layer Design Without External Packages"
date: 2025-09-20
draft: false
tags: ["Flutter", "BLoC", "Infinite Scroll", "Pagination", "ScrollController", "UX"]
description: "Implementing infinite scroll with pure BLoC + ScrollController without infinite_scroll_pagination. How to split responsibilities across Datasource, Repository, BLoC, and UI layers."
cover:
  image: "/images/og/flutter-bloc-infinite-scroll-pagination.png"
  alt: "Flutter Bloc Infinite Scroll Pagination"
  hidden: true
---


Loading the entire list upfront is slow. I needed infinite scroll that naturally loads the next batch of data as the user scrolls.

Packages like `infinite_scroll_pagination` exist, but fitting them into an existing BLoC structure sometimes means redesigning your state to match the package's approach, which can actually make things more complex. Since it's perfectly achievable with just `ScrollController` and no external dependencies, I went that route.

---

## Why Offset-Based

There are two pagination approaches.

**Offset-based (page number)**
```
GET /items?page=1&per_page=20
GET /items?page=2&per_page=20
```

**Cursor-based (last item ID)**
```
GET /items?cursor=abc123&per_page=20
```

Cursor-based is theoretically superior in that "there are no duplicates or missing items even when data is inserted/deleted in between." But if the target data is static documents like laws and regulations that **rarely change**, the offset approach is sufficient.

Implementation is also simpler -- the backend only needs to support `page` and `per_page` query parameters.

---

## Layer Design

The whole thing is split into 4 layers.

```
Datasource    searchLawsPaginated(page, perPage) → LawsPage
Repository    getLawsPaginated(query, category, page, perPage) → LawsPage
BLoC          LoadLaws (first page), FetchMoreLaws (next page)
UI            ScrollController + ListView + bottom indicator
```

---

## 1. Response Type Definition

Added a type to hold results in the Repository interface.

```dart
class LawsPage {
  final List<Law> laws;
  final bool hasMore;

  const LawsPage({required this.laws, required this.hasMore});
}
```

---

## 2. Datasource — API Call

Left the existing `searchLaws()` untouched and added a pagination-specific method.

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
  if (category != null && category != 'All') params['category'] = category;

  final response = await _client.get<Map<String, dynamic>>(
    '/items/search',
    queryParameters: params,
  );

  final laws = _extractList(response.data);

  // Use meta.has_more from backend if available, otherwise estimate from length
  final meta = response.data?['meta'] as Map<String, dynamic>?;
  final hasMore = meta?['has_more'] as bool? ?? laws.length >= perPage;

  return LawsPage(laws: laws, hasMore: hasMore);
}
```

Even if the backend doesn't provide a `has_more` field yet, you can estimate with `length >= perPage`. It's not perfectly accurate, but works in practice.

---

## 3. BLoC — Extending Events and States

Added pagination fields to the existing `LawsLoaded` state.

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

Two events.

```dart
class LoadLaws extends LawsEvent {}       // First page (including search/category changes)
class FetchMoreLaws extends LawsEvent {}  // Next page
```

The key is completely separating the roles of `LoadLaws` and `FetchMoreLaws`.

```dart
// First page — always start fresh from page=1
Future<void> _onLoadLaws(LoadLaws event, Emitter<LawsState> emit) async {
  emit(LawsLoading());  // Full-screen loading spinner
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

// Next page — append to existing list
Future<void> _onFetchMoreLaws(FetchMoreLaws event, Emitter<LawsState> emit) async {
  final current = state;
  if (current is! LawsLoaded) return;
  if (!current.hasMore || current.isLoadingMore) return;

  emit(current.copyWith(isLoadingMore: true));  // Bottom spinner only
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
    // On additional load failure, keep existing data and fail silently
  }
}
```

The difference in error handling is critical.
- First page failure -> Transition to `LawsError` state (full error screen)
- Additional page failure -> Keep existing `LawsLoaded` state, just set `isLoadingMore` to false (no data loss)

Imagine scrolling past 50 items and then seeing a full error screen because the next page failed to load. That's the worst UX.

---

## 4. UI — ScrollController and Bottom Indicator

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
    // Pre-fetch next page when 300px from the bottom
    if (pos.pixels >= pos.maxScrollExtent - _fetchThreshold) {
      final state = context.read<LawsBloc>().state;
      if (state is LawsLoaded && state.hasMore && !state.isLoadingMore) {
        context.read<LawsBloc>().add(const FetchMoreLaws());
      }
    }
  }
```

The reason for pre-fetching at 300px is so the next data loads before the user reaches the end of the scroll. Too early and API calls become excessive; too late and a loading spinner appears. 200-400px is the sweet spot.

The ListView uses `itemCount: laws.length + 1`, with the last item serving as the bottom indicator.

```dart
RefreshIndicator(
  onRefresh: _onRefresh,
  child: ListView.separated(
    controller: _scrollController,
    physics: const AlwaysScrollableScrollPhysics(),
    itemCount: laws.length + 1,
    itemBuilder: (context, index) {
      if (index == laws.length) {
        // Bottom item
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
              child: Text('All ${laws.length} items loaded'),
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

`AlwaysScrollableScrollPhysics()` is needed so that pull-to-refresh works even when there are few items.

---

## Pull-to-Refresh Handling

When the search query or category changes, `LoadLaws` is automatically dispatched, starting fresh from page=1.

Pull-to-refresh uses the same `LoadLaws`.

```dart
Future<void> _onRefresh() async {
  context.read<LawsBloc>().add(LoadLaws(
    query: _searchController.text.trim(),
    category: _activeCategory,
  ));
  // Wait until loading completes
  await context.read<LawsBloc>().stream.firstWhere(
    (s) => s is LawsLoaded || s is LawsError,
  );
}
```

Using `stream.firstWhere` to wait for the next completion state makes the RefreshIndicator disappear at the right moment.

---

## What the Backend Needs

Even if the frontend is ready, it's useless if the backend doesn't support pagination. For Rails, this is the bare minimum.

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

By fetching `limit(per_page + 1)` and checking if the count exceeds `per_page`, you can determine if there's a next page. This is a common pattern that avoids the need for a separate COUNT query.

---

## Summary

| Aspect | Choice | Reason |
|---|---|---|
| Pagination method | Offset (page number) | Static data, simpler implementation |
| Detection method | ScrollController | No additional packages needed |
| External packages | None | Integrates naturally with existing BLoC structure |
| Fetch timing | 300px before bottom | Pre-load before reaching scroll end |
| Error handling | First page: full error, Additional pages: keep existing data | Minimize UX disruption |

The most important part is handling errors differently for `LoadLaws` and `FetchMoreLaws`. A first-load failure and an additional-load failure are completely different situations from the user experience perspective.
