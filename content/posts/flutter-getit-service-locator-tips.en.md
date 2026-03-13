---
title: "Flutter GetIt Service Locator - Why It Gets Hard to Manage as Features Grow"
date: 2025-07-23
draft: false
tags: ["Flutter", "GetIt", "DI", "Dependency Injection"]
description: "Problems that arise as features grow when managing dependency injection with GetIt - registration order, token timing, and lazy vs eager selection criteria."
cover:
  image: "/images/og/flutter-getit-service-locator-tips.png"
  alt: "Flutter Getit Service Locator Tips"
  hidden: true
---


When managing dependency injection with `GetIt` in Flutter, things are fine at 5 features but start getting painful past 15.
Here's what I ran into today.

---

## Basic Structure

A structure where all GetIt registrations are packed into a single `service_locator.dart` file.

```dart
final sl = GetIt.instance;

Future<void> setupServiceLocator({
  required String baseUrl,
  String? token,
}) async {
  // External libraries
  sl.registerLazySingleton<Dio>(() => Dio());

  // Datasources
  sl.registerLazySingleton<LawsRemoteDatasource>(
    () => LawsRemoteDatasource(
      dio: sl<Dio>(),
      baseUrl: baseUrl,
      token: token,
    ),
  );

  // Repositories
  sl.registerLazySingleton<LawsRepository>(
    () => LawsRepositoryImpl(datasource: sl<LawsRemoteDatasource>()),
  );
}
```

---

## Problem 1: Token Timing

A situation arises where you first register with `setupServiceLocator(token: null)` at app startup, then need to update the token after login.

`registerLazySingleton` creates the instance when `sl<T>()` is first called.
That means if the datasource was already used before login, the instance was created with a null token.

The solution is either `sl.resetLazySingleton<T>()` or re-registering after login.

```dart
Future<void> updateToken(String token) async {
  // Re-register datasources that need the token
  sl.unregister<LawsRemoteDatasource>();
  sl.registerLazySingleton<LawsRemoteDatasource>(
    () => LawsRemoteDatasource(
      dio: sl<Dio>(),
      baseUrl: sl<String>(instanceName: 'baseUrl'),
      token: token,
    ),
  );

  // Repository must also be re-registered to point to the new datasource
  sl.unregister<LawsRepository>();
  sl.registerLazySingleton<LawsRepository>(
    () => LawsRepositoryImpl(datasource: sl<LawsRemoteDatasource>()),
  );
}
```

This code gets longer as features increase. For this reason, instead of injecting the token directly into datasources, there's also the approach of creating a separate `TokenProvider` singleton for reference.

```dart
class TokenProvider {
  String? _token;
  void setToken(String token) => _token = token;
  String? get token => _token;
}

sl.registerSingleton<TokenProvider>(TokenProvider());

// In the datasource
class LawsRemoteDatasource {
  final TokenProvider _tokenProvider;

  Future<List<Law>> getLaws() async {
    final token = _tokenProvider.token;  // always the latest token
    // ...
  }
}
```

This approach is much easier to manage when there are many features.

---

## Problem 2: Registration Order Dependencies

When registering `LawsRepository`, `LawsRemoteDatasource` must already be registered.
`registerLazySingleton` has fewer order issues since it initializes lazily, but `registerSingleton` creates immediately, so wrong order means immediate error.

```
[GetIt] Object/factory with type LawsRemoteDatasource is not registered inside GetIt.
```

When adding features, always register in order: datasource -> repository -> (usecase if needed).
Grouping by feature blocks in the file makes it easy to find order issues later.

```dart
// === Laws Feature ===
sl.registerLazySingleton<LawsRemoteDatasource>(...);
sl.registerLazySingleton<LawsRepository>(...);

// === Legal Precedents Feature ===
sl.registerLazySingleton<LegalPrecedentRemoteDatasource>(...);
sl.registerLazySingleton<LegalPrecedentRepository>(...);
```

---

## Problem 3: BLoC Needs registerFactory

BLoCs should be registered with `registerFactory`, not `registerLazySingleton`.

Using `registerLazySingleton` means closing and reopening a screen reuses the same BLoC instance.
The previous state persists, causing a bug where the screen unintentionally shows old data.

```dart
// Wrong - state is shared
sl.registerLazySingleton<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);

// Correct - new instance each time
sl.registerFactory<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);
```

In the page, wrapping with `BlocProvider` and calling `sl<LawsBloc>()` gives a fresh BLoC each time.

```dart
BlocProvider(
  create: (_) => sl<LawsBloc>()..add(LoadLaws()),
  child: LawsListPage(),
)
```

---

## Summary

| Registration Method | Use Case |
|---|---|
| `registerSingleton` | Single objects shared app-wide (TokenProvider, Dio, etc.) |
| `registerLazySingleton` | Datasource, Repository - have creation cost but okay to share state |
| `registerFactory` | BLoC - needs a new instance per screen |

Once you hit 10+ features, service_locator.dart starts exceeding 200 lines.
Splitting into per-feature functions like `setupLawsDependencies()`, `setupCalendarDependencies()` and calling them from `setupServiceLocator()` is easier to manage.
