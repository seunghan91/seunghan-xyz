---
title: "From MCP Tool Integration to Flutter Settings Toggle — Debugging Record"
date: 2025-12-13
draft: false
tags: ["Rails", "Flutter", "BLoC", "MCP", "RSpec", "HydratedBloc"]
description: "Created categories on the server via MCP but they don't show in the app? From API response field omission to Flutter Freezed entity fixes and settings toggle implementation."
cover:
  image: "/images/og/mcp-flutter-rails-system-category-debug.png"
  alt: "Mcp Flutter Rails System Category Debug"
  hidden: true
categories: ["Rails"]
---


I created categories on the server side using MCP tools. But the new categories were not visible in the mobile app.

It seemed like a simple problem, but the deeper I dug, the more layers were tangled together.

---

## The Beginning: Categories Created via MCP Not Showing in App

I created system categories like `dev/`, `memory` on the server through MCP tools. Calling the API directly showed the data. Refreshing the app did not show them.

First hypothesis: Is the app using a cache?
-> No. It was dispatching `PapersLoadRequested` + `PaperCategoriesLoadRequested` events in order, and the server was returning normal responses.

Second hypothesis: Is the API filtering?
-> Checked the Rails controller. No filter. Returning everything.

Third hypothesis: Is the Flutter app filtering?
-> Yes. Filter code that had been left behind -- unclear whether intentionally or not.

---

## Step 1: The `is_system` Field Was Missing from API Response

The response serialization in Rails `paper_categories_controller.rb`:

```ruby
# Before
{
  id: paper_category.id.to_s,
  name: paper_category.name,
  color: paper_category.color,
  order: paper_category.order,
  updated_at: paper_category.updated_at.to_i,
  _count: { papers: paper_category.papers.count }
}
```

The `is_system` field existed in the DB but was not included in the response. Added it to all five places: index, show, create, update, reorder.

```ruby
is_system: paper_category.is_system,
```

---

## Step 2: Add Field to Flutter Freezed Entity

The `PaperCategory` domain entity (using Freezed):

```dart
// Before
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

Added `isSystem` field:

```dart
@freezed
class PaperCategory with _$PaperCategory {
  const factory PaperCategory({
    required String id,
    required String name,
    required String color,
    required DateTime createdAt,
    required DateTime updatedAt,
    @Default(false) bool isSystem,  // Added
  }) = _PaperCategory;
}
```

When adding a field with Freezed, code generation is mandatory:

```bash
dart run build_runner build --delete-conflicting-outputs
```

Forgetting this causes a compile error rather than a runtime error, so it gets caught quickly, but it should be run habitually.

Also added to the DTO:

```dart
@JsonKey(name: 'is_system')
final bool isSystem;

// Also in the fromJson custom parser
isSystem: json['is_system'] as bool? ?? false,
```

The `?? false` default is important because existing data may return null when the field does not exist.

---

## Step 3: Control via Settings Instead of Simply Hiding

The initial thought was "just hide system categories." But there are cases where you want to browse categories created via MCP in the app too.

So the decision was to control it with a toggle in the settings tab.

### Add HydratedBloc Settings State

Added `showSystemCategories` field to `SettingsState`:

```dart
@freezed
class SettingsState with _$SettingsState {
  const factory SettingsState({
    // ... existing fields
    @Default(false) bool showSystemCategories,  // Default: hidden
  }) = _SettingsState;
}
```

`fromJson`/`toJson` must also be added for HydratedBloc to guarantee persistence. If forgotten, a bug appears where settings reset to defaults on app restart.

Event:

```dart
class SettingsShowSystemCategoriesChanged extends SettingsEvent {
  final bool enabled;
  const SettingsShowSystemCategoriesChanged(this.enabled);
}
```

Handler:

```dart
on<SettingsShowSystemCategoriesChanged>((event, emit) {
  emit(state.copyWith(showSystemCategories: event.enabled));
});
```

### Add Toggle to Settings Screen

```dart
BlocSelector<SettingsBloc, SettingsState, bool>(
  selector: (state) => state.showSystemCategories,
  builder: (context, showSystemCategories) => SwitchListTile(
    secondary: const Icon(Icons.folder_special_outlined),
    title: const Text('Show system categories'),
    subtitle: const Text('Show MCP-synced categories in the notes tab'),
    value: showSystemCategories,
    onChanged: (value) {
      context.read<SettingsBloc>().add(
        SettingsShowSystemCategoriesChanged(value),
      );
    },
  ),
),
```

Using `BlocSelector` rebuilds this widget only when `showSystemCategories` changes. Using `BlocBuilder` to watch the entire state would cause unnecessary rebuilds when other settings change.

### Filter in Category List Screen

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

One mistake was made here. After wrapping `PaperCategoryFilter` with `BlocSelector`, a closing parenthesis was missed, causing a compile error. Bracket management gets tricky as Flutter widget tree nesting gets deeper.

---

## Step 4: Testing

If the feature is implemented, tests should come along.

### Rails RSpec

The API response structure is nested, so helper methods were created first:

```ruby
def categories_list
  JSON.parse(response.body).dig('data', 'data')
end

def category_data
  JSON.parse(response.body)['data']
end
```

Response structure: `{ success: true, data: { data: [...], meta: {...} } }`

Using only `json['data']` returns a Hash, not an Array. Nested access via `dig` is needed.

Key test cases:

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

Among system categories, only the root (`dev`) has `is_system: true`; subcategories are `false`. Explicitly capturing this rule in tests reduces confusion later.

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

Persistence testing is important. When using `HydratedBloc`, you should verify with unit tests that `toJson`/`fromJson` actually work. If you add a new field and forget the serialization code, settings reset after app restart -- and this kind of bug is hard to find manually.

---

## Migration Idempotency (Another Debugging Story This Week)

This week a `PG::DuplicateColumn` error occurred on the deployment server. A migration that ran fine locally broke in production.

Cause: The column already existed, but `add_column` tried to run again.

How to ensure idempotency in Rails migrations:

```ruby
# Column
unless column_exists?(:paper_categories, :is_system)
  add_column :paper_categories, :is_system, :boolean, default: false, null: false
end

# Index
unless index_exists?(:paper_categories, [:user_id, :is_system])
  add_index :paper_categories, [:user_id, :is_system]
end
```

Or in Rails 6.1+:

```ruby
add_column :paper_categories, :is_system, :boolean, default: false, null: false,
           if_not_exists: true
```

DB state differences between local and production can happen anytime. It is important to make migrations idempotent from the start.

---

## Summary

Takeaways from this work:

1. **API response design**: Just because a field exists in the DB does not mean it is automatically included in the response. Fields must be explicitly serialized.

2. **Run build_runner after modifying Freezed entities**: Do not skip this. It belongs in CI.

3. **HydratedBloc + toJson/fromJson**: When adding new fields, update serialization code too. Verify with persistence unit tests.

4. **BlocSelector vs BlocBuilder**: Use `BlocSelector` when watching specific fields. It prevents unnecessary rebuilds.

5. **Migration idempotency**: Defend with `column_exists?`, `index_exists?`, or `if_not_exists: true`.

Adding a single feature involves many layers. API -> DTO -> Entity -> Repository -> BLoC Event/State -> UI -> Test. Following each layer in order ensures nothing is missed.
