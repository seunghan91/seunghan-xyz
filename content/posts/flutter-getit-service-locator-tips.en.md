---
title: "Flutter GetIt Service Locator - Why It Gets Hard to Manage as Features Grow"
date: 2025-07-23
draft: true
tags: ["Flutter", "GetIt", "DI", "Dependency Injection"]
description: "Problems that arise as features grow when managing dependency injection with GetIt - registration order, token timing, and lazy vs eager selection criteria."
cover:
  image: "/images/og/flutter-getit-service-locator-tips.png"
  alt: "Flutter Getit Service Locator Tips"
  hidden: true
---

When managing dependency injection with `GetIt` in Flutter, things are fine at 5 features but start getting painful past 15. This post documents the concrete problems I ran into and the patterns that actually fix them.

---

## Basic Structure

A common starting point is a single `service_locator.dart` file where all GetIt registrations live. For small projects this works well — the entire dependency graph is visible in one place.

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

This gets called in `main.dart` after `WidgetsFlutterBinding.ensureInitialized()` and before `runApp()`:

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await setupServiceLocator(baseUrl: AppConfig.baseUrl);
  runApp(const MyApp());
}
```

Clean and readable at first. The trouble starts as features accumulate.

---

## Problem 1: Token Timing

A situation arises where you first register with `setupServiceLocator(token: null)` at app startup, then need to update the token after the user logs in.

`registerLazySingleton` creates the instance on the first call to `sl<T>()`. If the datasource was already accessed before login, the instance was created with a null token. Updating the token later has no effect on the already-instantiated object.

This bug is tricky to reproduce. During development, if no screen calls the API before login, everything looks fine. It surfaces in production only on specific user flows.

The naive fix is to unregister and re-register after login:

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

With 10 features this function balloons to 20+ lines of repetitive unregister/register pairs. Every new feature that needs authentication means adding two more lines here. It becomes a maintenance hazard.

The better solution is to stop injecting the token value directly into datasources. Instead, inject a `TokenProvider` singleton that holds the current token. Datasources reference the provider rather than storing the token themselves.

```dart
class TokenProvider {
  String? _token;
  void setToken(String token) => _token = token;
  void clearToken() => _token = null;
  String? get token => _token;
}

sl.registerSingleton<TokenProvider>(TokenProvider());

// In the datasource
class LawsRemoteDatasource {
  final Dio _dio;
  final String _baseUrl;
  final TokenProvider _tokenProvider;

  LawsRemoteDatasource({
    required Dio dio,
    required String baseUrl,
    required TokenProvider tokenProvider,
  })  : _dio = dio,
        _baseUrl = baseUrl,
        _tokenProvider = tokenProvider;

  Future<List<Law>> getLaws() async {
    final token = _tokenProvider.token; // always the latest token
    final response = await _dio.get(
      '$_baseUrl/laws',
      options: Options(headers: {'Authorization': 'Bearer $token'}),
    );
    // ...
  }
}
```

The key insight: the datasource holds a reference to the `TokenProvider` object, not to a token string. When the token changes, calling `sl<TokenProvider>().setToken(newToken)` propagates to every datasource on the next request — no re-instantiation needed. Logout is handled with a single `sl<TokenProvider>().clearToken()` call.

---

## Problem 2: Registration Order Dependencies

When registering `LawsRepository`, `LawsRemoteDatasource` must already be registered. `registerLazySingleton` has fewer order issues since it defers initialization, but `registerSingleton` creates the instance immediately — wrong order causes an immediate crash.

```
[GetIt] Object/factory with type LawsRemoteDatasource is not registered inside GetIt.
```

This error is disorienting, especially when a teammate added a new feature by inserting registration code in the middle of the file, silently breaking the ordering assumption.

A subtlety worth noting: even with `registerLazySingleton`, the factory closure captures `sl<T>()` calls at execution time, not at registration time. If the factory runs before a dependency is registered, it throws immediately. The name "lazy" refers to when the factory runs, not when dependency resolution happens.

Always register in order: datasource → repository → use case (if present) → BLoC. Group by feature block in the file so ordering issues are easy to spot.

```dart
// === Laws Feature ===
sl.registerLazySingleton<LawsRemoteDatasource>(...);
sl.registerLazySingleton<LawsRepository>(...);

// === Legal Precedents Feature ===
sl.registerLazySingleton<LegalPrecedentRemoteDatasource>(...);
sl.registerLazySingleton<LegalPrecedentRepository>(...);
```

Watch out for cross-feature dependencies. If `NotificationRepository` depends on `UserRepository`, the user feature block must come first. When cross-feature dependencies become common, a dependency diagram comment at the top of the file is worth the two minutes it takes to write.

---

## Problem 3: BLoC Needs registerFactory

BLoCs should be registered with `registerFactory`, not `registerLazySingleton`.

Using `registerLazySingleton` for a BLoC means navigating away from a screen and back reuses the same BLoC instance. The previous state persists, producing a bug where the screen shows stale data the user did not ask to see.

Concrete example: a laws search screen where the user typed a query, pressed back, then navigated back in. With a singleton BLoC, the previous search state — emitted results, scroll position, filter settings — is all still there. The user expected a fresh screen.

```dart
// Wrong - state is shared across screen visits
sl.registerLazySingleton<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);

// Correct - fresh instance every time the screen opens
sl.registerFactory<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);
```

In the page, wrapping with `BlocProvider` and calling `sl<LawsBloc>()` delivers a fresh BLoC on each navigation:

```dart
BlocProvider(
  create: (_) => sl<LawsBloc>()..add(LoadLaws()),
  child: LawsListPage(),
)
```

The exception is app-wide BLoCs that genuinely need to share state across the entire session — `AuthBloc` tracking login status, `ConnectivityBloc` monitoring network state, or a shopping cart BLoC. These belong in `registerLazySingleton` because you want exactly one instance for the app's lifetime.

The decision rule is straightforward: if the BLoC should reset when the user navigates away from its screen, use `registerFactory`. If the BLoC manages state that must persist across the whole session, use `registerLazySingleton`.

---

## Problem 4: Splitting the File Before It Becomes Unmanageable

Once you cross 10 features, `service_locator.dart` regularly exceeds 200 lines. Scrolling through it to find a specific registration becomes tedious, and merge conflicts are frequent when multiple developers add features simultaneously.

The solution is to move each feature's registrations into a dedicated file inside the feature's folder.

```dart
// lib/core/di/service_locator.dart
Future<void> setupServiceLocator({
  required String baseUrl,
}) async {
  _registerCore(baseUrl: baseUrl);
  await setupLawsDependencies();
  await setupLegalPrecedentsDependencies();
  await setupCalendarDependencies();
  // one line per feature
}

void _registerCore({required String baseUrl}) {
  sl.registerSingleton<TokenProvider>(TokenProvider());
  sl.registerLazySingleton<Dio>(() => _createDio());
  sl.registerSingleton<String>(baseUrl, instanceName: 'baseUrl');
}
```

```dart
// lib/features/laws/di/laws_dependencies.dart
Future<void> setupLawsDependencies() async {
  sl.registerLazySingleton<LawsRemoteDatasource>(
    () => LawsRemoteDatasource(
      dio: sl<Dio>(),
      baseUrl: sl<String>(instanceName: 'baseUrl'),
      tokenProvider: sl<TokenProvider>(),
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

Each feature owns its DI code. The developer working on the laws feature touches only `laws_dependencies.dart`. Merge conflicts in the service locator file drop to near zero.

The one tradeoff: it is now possible to have ordering bugs at the inter-feature level. If `setupNotificationsDependencies()` is called before `setupUserDependencies()` and notifications depend on the user repository, you get the familiar "not registered" error. Keep the call order in `setupServiceLocator()` consistent with the feature dependency graph.

---

## Debugging Tips

GetIt errors at runtime tend to be one of two types.

**"Object/factory with type X is not registered inside GetIt"** almost always means a registration order problem. Find where the type is registered and trace whether its dependency is registered before it. Check for feature files that call `sl<T>()` inside a factory without the dependency being set up first.

**"Tried to register a type that is already registered"** happens when `registerLazySingleton` or `registerSingleton` is called on a type that was registered in a previous call — typically in an `updateToken`-style function that forgot to `unregister` first. Use `sl.unregister<T>()` before re-registering, or pass `allowReassignment: true` if you know what you are doing.

For async registrations using `registerSingletonAsync`, call `allReady()` before starting the app to ensure everything has resolved:

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await setupServiceLocator(baseUrl: AppConfig.baseUrl);
  await sl.allReady(); // waits for all async singletons
  runApp(const MyApp());
}
```

During development, dropping `sl.isRegistered<T>()` checks into a debug screen or `flutter run --verbose` logging can surface registration problems before they cause hard-to-trace runtime crashes.

---

## Summary

| Registration Method | Use Case |
|---|---|
| `registerSingleton` | Single objects shared app-wide (TokenProvider, Dio, etc.) |
| `registerLazySingleton` | Datasource, Repository — have creation cost but okay to share state |
| `registerFactory` | BLoC — needs a fresh instance per screen |
| `registerSingletonAsync` | Singletons requiring async initialization (SharedPreferences, local DB) |

Once you hit 10+ features, `service_locator.dart` starts exceeding 200 lines. Splitting into per-feature setup functions like `setupLawsDependencies()` and `setupCalendarDependencies()`, called from `setupServiceLocator()`, keeps things manageable as the project grows.

---

## Key Takeaways

- **Token timing bugs** are best solved with the `TokenProvider` pattern. Inject an object that holds the token, not the token string itself — no re-registration needed when the token changes.
- **Registration order** must always follow datasource → repository → use case → BLoC. `registerSingleton` is especially unforgiving since it instantiates immediately.
- **BLoCs are almost always `registerFactory`**. Using `registerLazySingleton` for screen-scoped BLoCs causes stale state bugs that are annoying to track down.
- **Split the file at 200 lines**. Feature-scoped DI files reduce merge conflicts and make each feature self-contained.
- `"is not registered"` is a registration order problem. `"is already registered"` is a duplicate registration problem.
