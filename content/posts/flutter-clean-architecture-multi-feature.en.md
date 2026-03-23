---
title: "Flutter Clean Architecture in Practice - Adding Multiple Features at Once"
date: 2025-07-09
draft: true
tags: ["Flutter", "Clean Architecture", "BLoC", "GetIt"]
description: "Folder structure and dependency management lessons from adding Calendar, Laws, Legal Precedents, Q&A and other features using Clean Architecture."
cover:
  image: "/images/og/flutter-clean-architecture-multi-feature.png"
  alt: "Flutter Clean Architecture Multi Feature"
  hidden: true
---

When adding multiple features to a Flutter app at once, the first thing to worry about is folder structure.
Each feature looks simple on its own, but when several are added simultaneously, things get tangled fast.

There was a sprint where a Calendar, a Laws search screen, a Legal Precedents viewer, and a Q&A board all had to land at the same time. Each feature was independent in concept, but once they started merging into the same codebase, dependency management and folder organization started colliding. This post captures the patterns that emerged from working through that.

---

## Folder Structure Per Feature

Based on Clean Architecture, each feature follows this structure.

```
lib/features/{feature_name}/
  ├── data/
  │   ├── datasources/     # API calls
  │   └── repositories/    # Interface implementations
  ├── domain/
  │   ├── entities/        # Pure data models
  │   └── repositories/    # Interface definitions
  └── presentation/
      ├── bloc/            # BLoC (events/states)
      └── pages/           # UI
```

Following this pattern, the structure stays consistent no matter how many features are added.
Adding a new feature becomes as simple as copying the folder template and filling in the contents.

The core principle behind this structure is the **direction of layer dependencies**. `presentation` only depends on `domain`. `data` implements the interfaces defined in `domain`. `domain` depends on nothing. As features accumulate, the folder structure enforces this discipline.

Some teams add a use_case layer between domain and presentation, but when rapidly adding multiple features, the domain/repositories + BLoC combination is sufficient. Consistency beats over-engineering.

---

## The Common Repeating Pattern

Every feature's datasource has nearly identical boilerplate.

```dart
class LawsRemoteDatasource {
  final Dio _dio;
  final String _baseUrl;
  final String? _token;

  LawsRemoteDatasource({
    required Dio dio,
    required String baseUrl,
    String? token,
  })  : _dio = dio,
        _baseUrl = baseUrl,
        _token = token;

  Future<List<Law>> getLaws({int page = 1}) async {
    final response = await _dio.get(
      '$_baseUrl/api/v1/laws',
      options: Options(
        headers: {'Authorization': 'Bearer $_token'},
      ),
      queryParameters: {'page': page},
    );
    return (response.data['laws'] as List)
        .map((e) => Law.fromJson(e))
        .toList();
  }
}
```

The structure injects token, baseUrl, and Dio.
These three are provided externally when registering with `GetIt`.

If the repetition bothers you, creating a base abstract datasource class is an option. But when you are adding four or five features quickly, copy-paste-and-modify is often faster than premature abstraction. What matters is that **every datasource maintains the same constructor signature**. That keeps GetIt registration predictable.

Error handling is cleaner when the datasource layer catches `DioException` and converts it to a domain exception. That way the BLoC never needs to import anything from Flutter's networking layer.

```dart
Future<List<Law>> getLaws({int page = 1}) async {
  try {
    final response = await _dio.get(...);
    return (response.data['laws'] as List)
        .map((e) => Law.fromJson(e))
        .toList();
  } on DioException catch (e) {
    throw ServerException(message: e.message ?? 'Unknown error');
  }
}
```

---

## When There's a Lot of Repetition, Define Entities First

The common mistake when adding features quickly is with entities.
If you build them hastily from API responses, you'll get null errors later when accessing fields in the BLoC.

`fromJson` needs to be thorough -- nullable handling must be explicit.

```dart
class LegalPrecedent {
  final int id;
  final String caseNumber;
  final String? summary;       // can be null
  final DateTime decidedAt;

  LegalPrecedent({
    required this.id,
    required this.caseNumber,
    this.summary,
    required this.decidedAt,
  });

  factory LegalPrecedent.fromJson(Map<String, dynamic> json) {
    return LegalPrecedent(
      id: json['id'],
      caseNumber: json['case_number'],
      summary: json['summary'],  // just null if missing
      decidedAt: DateTime.parse(json['decided_at']),
    );
  }
}
```

Making fields nullable means more handling in the UI, but forcing non-null means parsing errors blow up at runtime. The compromise is making only fields that **the server guarantees will always be present** non-null.

### Common fromJson Errors You Will Hit

When writing multiple entities under time pressure, you will encounter these error patterns.

**`type 'Null' is not a subtype of type 'String'`**
: A non-null field received null from the API. Even when the API documentation claims a field is always present, real-world responses sometimes include null. Use `json['field']?.toString() ?? ''` instead of `json['field'] as String`, or make the field nullable in the entity.

**`type 'int' is not a subtype of type 'String'`**
: A value that looks like a string is actually coming down as an integer. Either call `.toString()` on the value or adjust the entity's type to match what the server actually sends.

**`FormatException: Invalid date format`**
: `DateTime.parse` only accepts ISO 8601. If the server sends `"2025-07-09 10:30:00"` without a timezone indicator, it will fail. Use `DateTime.tryParse` or add a custom parsing utility.

Once the entities are locked down, the layers above them fill in mechanically. If the entities are unstable, every layer above them will shift.

---

## Keep Repository Interfaces Short

The domain layer repository only defines the interface. The implementation lives in the data layer.

```dart
// domain/repositories/laws_repository.dart
abstract class LawsRepository {
  Future<List<Law>> getLaws({int page});
  Future<Law> getLawDetail(int id);
}
```

Write the interface first, fill in the implementation later.
When adding many features, defining all interfaces upfront gives you flexibility in the order you write BLoCs.

With the interface in place, you can implement the BLoC without waiting for the datasource and repository implementation to be finished. In a team context, the interface can be merged first and different engineers can implement each layer in parallel.

The data layer implementation is a thin wrapper around the datasource.

```dart
// data/repositories/laws_repository_impl.dart
class LawsRepositoryImpl implements LawsRepository {
  final LawsRemoteDatasource _datasource;

  LawsRepositoryImpl({required LawsRemoteDatasource datasource})
      : _datasource = datasource;

  @override
  Future<List<Law>> getLaws({int page = 1}) async {
    return await _datasource.getLaws(page: page);
  }

  @override
  Future<Law> getLawDetail(int id) async {
    return await _datasource.getLawDetail(id);
  }
}
```

Caching logic, offline fallback, or error transformation can be added at this layer without touching the domain interface or the BLoC.

---

## GetIt Registration: Order and Grouping

When adding multiple features simultaneously, `service_locator.dart` grows fast. Grouping registration by feature keeps it manageable.

```dart
// lib/core/di/service_locator.dart
Future<void> setupDependencies() async {
  // Shared dependencies
  _setupCore();

  // Feature-specific dependencies
  _setupLawsFeature();
  _setupPrecedentsFeature();
  _setupCalendarFeature();
  _setupQnaFeature();
}

void _setupLawsFeature() {
  sl.registerLazySingleton<LawsRemoteDatasource>(
    () => LawsRemoteDatasource(
      dio: sl<Dio>(),
      baseUrl: sl<AppConfig>().baseUrl,
      token: sl<AuthManager>().token,
    ),
  );

  sl.registerLazySingleton<LawsRepository>(
    () => LawsRepositoryImpl(datasource: sl<LawsRemoteDatasource>()),
  );

  sl.registerFactory<LawsBloc>(
    () => LawsBloc(repository: sl<LawsRepository>()),
  );
}
```

`registerLazySingleton` creates the instance on first access. `registerFactory` creates a new instance each time. BLoCs should almost always use `registerFactory`. If a BLoC is registered as a singleton, its state persists across screen navigations when it should be fresh, leading to stale-state bugs that are hard to trace.

---

## Checklist When Adding Multiple Features

These are the omission patterns encountered firsthand.

**1. Missing service_locator registration**

If you create a feature but forget to register it with `GetIt`, you'll get a `Not registered` runtime error.
Think of it as a set: add feature -> register in service_locator.dart -> add route in main.dart.

`Not registered: LawsBloc` is obvious enough, but `Not registered: LawsRepository` -- where the BLoC internally depends on something unregistered -- requires tracing through the stack. GetIt resolves lazily, so the error does not surface at app startup. It surfaces exactly when the user navigates to the broken screen.

**2. Missing main.dart route**

If you create a page but don't connect the route, naturally it can't be accessed.
But sometimes the error message comes in a different form than "route not found," which is confusing.

With go_router, missing routes throw a `GoException`. With Navigator 1.0's `onGenerateRoute`, unhandled route names fall through to `unknownRoute`. Either way, the symptom is the same: the screen never appears.

**3. Missing BLoC event class export**

If you don't barrel export event/state classes from the BLoC file, import paths get messy in the pages.
It's easier to include event and state files as `part` in the BLoC file header, or manage everything in a single file.

```dart
// presentation/bloc/laws_bloc.dart
part 'laws_event.dart';
part 'laws_state.dart';

class LawsBloc extends Bloc<LawsEvent, LawsState> {
  // ...
}
```

With `part`, importing `laws_bloc.dart` gives access to the events and states as well. The internal files remain separate for organization, but the consuming page only needs one import.

**4. Missing BlocProvider in the widget tree**

Registering a BLoC with GetIt is not enough. If `BlocProvider` is absent from the widget tree, calling `BlocProvider.of<LawsBloc>` throws an error. The cleanest place to provide it is in the route definition.

```dart
GoRoute(
  path: '/laws',
  builder: (context, state) => BlocProvider(
    create: (_) => sl<LawsBloc>()..add(LoadLaws()),
    child: const LawsPage(),
  ),
),
```

Triggering the initial event in `create` -- `..add(LoadLaws())` -- means the page starts loading as soon as it is opened, without requiring an `initState` call in the widget.

---

## Key Takeaways

- **Standardized folder structure creates development velocity.** When the structure is fixed, adding a new feature becomes a template operation. Time is spent implementing, not deciding where files go.

- **Entity design is the foundation for every layer above it.** Get the nullable handling right and write `fromJson` carefully. Unstable entities ripple upward through the repository, BLoC state, and UI rendering.

- **Defining repository interfaces first unlocks parallel work.** With interfaces in place, BLoC implementation and datasource implementation can proceed simultaneously. Writing tests also becomes straightforward because the interface is mockable from the start.

- **The registration trio must travel together.** service_locator registration, route connection, and BLoC export are all required when adding a feature. Any single omission causes a runtime failure that can take significant time to trace.

- **Register BLoCs with `registerFactory`, not `registerLazySingleton`.** Singleton BLoCs persist state across navigations, leading to stale data appearing on screens that should start fresh. A factory ensures each navigation creates a clean instance.
