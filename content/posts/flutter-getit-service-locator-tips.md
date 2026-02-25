---
title: "Flutter GetIt service_locator - Feature 늘어날수록 관리가 힘든 이유"
date: 2026-02-25
draft: false
tags: ["Flutter", "GetIt", "DI", "의존성 주입"]
description: "GetIt으로 의존성 주입 관리하다가 Feature가 늘면서 생기는 문제들 - 등록 순서, 토큰 타이밍, lazy vs eager 선택 기준"
---

Flutter에서 `GetIt`으로 의존성 주입을 관리하다 보면, Feature가 5개일 때는 괜찮다가 15개가 넘으면 슬슬 힘들어진다.
오늘 겪은 것들 위주로 정리한다.

---

## 기본 구조

`service_locator.dart` 파일 하나에 GetIt 등록을 몰아넣는 구조다.

```dart
final sl = GetIt.instance;

Future<void> setupServiceLocator({
  required String baseUrl,
  String? token,
}) async {
  // 외부 라이브러리
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

## 문제 1: 토큰 타이밍

앱 시작 시 `setupServiceLocator(token: null)`로 먼저 등록하고, 로그인 후에 토큰을 갱신해야 하는 상황이 생긴다.

`registerLazySingleton`은 처음 `sl<T>()`를 호출할 때 인스턴스를 만든다.
즉, 로그인 전에 이미 datasource를 사용했다면 token이 null인 채로 인스턴스가 생성된다.

해결책은 로그인 후 `sl.resetLazySingleton<T>()` 또는 아예 재등록하는 것이다.

```dart
Future<void> updateToken(String token) async {
  // 토큰이 필요한 datasource들 재등록
  sl.unregister<LawsRemoteDatasource>();
  sl.registerLazySingleton<LawsRemoteDatasource>(
    () => LawsRemoteDatasource(
      dio: sl<Dio>(),
      baseUrl: sl<String>(instanceName: 'baseUrl'),
      token: token,
    ),
  );

  // Repository도 새 datasource를 바라봐야 하므로 같이 재등록
  sl.unregister<LawsRepository>();
  sl.registerLazySingleton<LawsRepository>(
    () => LawsRepositoryImpl(datasource: sl<LawsRemoteDatasource>()),
  );
}
```

Feature가 많아질수록 이 코드가 길어진다. 이 때문에 토큰을 datasource에 직접 주입하지 않고, 별도의 `TokenProvider` 싱글톤을 만들어서 참조하는 방식도 있다.

```dart
class TokenProvider {
  String? _token;
  void setToken(String token) => _token = token;
  String? get token => _token;
}

sl.registerSingleton<TokenProvider>(TokenProvider());

// datasource에서
class LawsRemoteDatasource {
  final TokenProvider _tokenProvider;

  Future<List<Law>> getLaws() async {
    final token = _tokenProvider.token;  // 항상 최신 토큰
    // ...
  }
}
```

이 방식이 Feature 많을 때 훨씬 관리가 편하다.

---

## 문제 2: 등록 순서 의존성

`LawsRepository`를 등록할 때 `LawsRemoteDatasource`가 먼저 등록되어 있어야 한다.
`registerLazySingleton`은 늦게 초기화되므로 순서 문제가 덜하지만, `registerSingleton`은 즉시 생성하기 때문에 순서가 틀리면 바로 에러난다.

```
[GetIt] Object/factory with type LawsRemoteDatasource is not registered inside GetIt.
```

Feature 추가 시 항상 datasource → repository → (필요하면 usecase) 순으로 등록해야 한다.
파일에서 Feature 블록 단위로 묶어서 정리해두면 나중에 순서 문제가 생겨도 찾기 쉽다.

```dart
// === Laws Feature ===
sl.registerLazySingleton<LawsRemoteDatasource>(...);
sl.registerLazySingleton<LawsRepository>(...);

// === Legal Precedents Feature ===
sl.registerLazySingleton<LegalPrecedentRemoteDatasource>(...);
sl.registerLazySingleton<LegalPrecedentRepository>(...);
```

---

## 문제 3: BLoC는 registerFactory

BLoC는 `registerLazySingleton`이 아니라 `registerFactory`로 등록해야 한다.

`registerLazySingleton`으로 등록하면 화면을 닫았다가 다시 열어도 동일한 BLoC 인스턴스를 재사용한다.
이전 상태가 남아있어서 화면이 의도치 않게 예전 데이터를 보여주는 버그가 생긴다.

```dart
// 잘못된 방법 - 상태가 공유됨
sl.registerLazySingleton<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);

// 올바른 방법 - 매번 새 인스턴스
sl.registerFactory<LawsBloc>(
  () => LawsBloc(repository: sl<LawsRepository>()),
);
```

페이지에서는 `BlocProvider`로 감싸면서 `sl<LawsBloc>()`을 호출하면 매번 새로운 BLoC를 받는다.

```dart
BlocProvider(
  create: (_) => sl<LawsBloc>()..add(LoadLaws()),
  child: LawsListPage(),
)
```

---

## 정리

| 등록 방식 | 사용처 |
|---|---|
| `registerSingleton` | 앱 전체에서 공유되는 단일 객체 (TokenProvider, Dio 등) |
| `registerLazySingleton` | Datasource, Repository - 생성 비용이 있지만 상태 공유해도 되는 것 |
| `registerFactory` | BLoC - 화면마다 새 인스턴스가 필요한 것 |

Feature가 10개 이상 되면 service_locator.dart가 200줄을 넘기 시작한다.
Feature별로 `setupLawsDependencies()`, `setupCalendarDependencies()` 같은 함수로 분리하고 `setupServiceLocator()`에서 호출하는 방식이 관리하기 편하다.
