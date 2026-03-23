---
title: "Flutter GetIt service_locator - Feature 늘어날수록 관리가 힘든 이유"
date: 2025-07-23
draft: true
tags: ["Flutter", "GetIt", "DI", "의존성 주입"]
description: "GetIt으로 의존성 주입 관리하다가 Feature가 늘면서 생기는 문제들 - 등록 순서, 토큰 타이밍, lazy vs eager 선택 기준"
cover:
  image: "/images/og/flutter-getit-service-locator-tips.png"
  alt: "Flutter Getit Service Locator Tips"
  hidden: true
---

Flutter에서 `GetIt`으로 의존성 주입을 관리하다 보면, Feature가 5개일 때는 괜찮다가 15개가 넘으면 슬슬 힘들어진다.
오늘 겪은 것들 위주로 정리한다.

---

## 기본 구조

`service_locator.dart` 파일 하나에 GetIt 등록을 몰아넣는 구조다.
소규모 프로젝트에서는 이 방식이 단순하고 파악하기 쉽다. 전체 의존성 그래프를 한 파일에서 볼 수 있기 때문이다.

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

이 파일을 `main.dart`에서 `WidgetsFlutterBinding.ensureInitialized()` 이후, `runApp()` 이전에 호출한다.

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await setupServiceLocator(baseUrl: AppConfig.baseUrl);
  runApp(const MyApp());
}
```

여기까지는 깔끔하다. 문제는 Feature가 쌓이면서 시작된다.

---

## 문제 1: 토큰 타이밍

앱 시작 시 `setupServiceLocator(token: null)`로 먼저 등록하고, 로그인 후에 토큰을 갱신해야 하는 상황이 생긴다.

`registerLazySingleton`은 처음 `sl<T>()`를 호출할 때 인스턴스를 만든다.
즉, 로그인 전에 이미 datasource를 사용했다면 token이 null인 채로 인스턴스가 생성된다.
이후 토큰을 업데이트해도 이미 생성된 인스턴스는 null 토큰을 갖고 있다.

이 버그는 재현하기 까다롭다. 로그인 전에 API를 호출하는 화면이 없으면 개발 중에는 문제가 없다가, 프로덕션에서 특정 플로우에서만 터진다.

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

Feature가 많아질수록 이 코드가 길어진다. Feature가 10개면 `updateToken` 함수 안에서 20줄 이상의 unregister/register 코드가 반복된다.

이 때문에 토큰을 datasource에 직접 주입하지 않고, 별도의 `TokenProvider` 싱글톤을 만들어서 참조하는 방식이 훨씬 낫다.

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

이 방식의 핵심은 datasource가 토큰 값이 아닌 토큰을 제공하는 객체를 참조한다는 것이다. 토큰이 바뀌어도 인스턴스를 재생성할 필요가 없다. `TokenProvider.setToken(newToken)`만 호출하면 모든 datasource가 다음 요청부터 새 토큰을 사용한다.

로그아웃 처리도 `TokenProvider._token = null`로 끝난다.

---

## 문제 2: 등록 순서 의존성

`LawsRepository`를 등록할 때 `LawsRemoteDatasource`가 먼저 등록되어 있어야 한다.
`registerLazySingleton`은 늦게 초기화되므로 순서 문제가 덜하지만, `registerSingleton`은 즉시 생성하기 때문에 순서가 틀리면 바로 에러난다.

```
[GetIt] Object/factory with type LawsRemoteDatasource is not registered inside GetIt.
```

이 에러가 나오면 당황하기 쉽다. 특히 팀원이 새 Feature를 추가하면서 파일 중간에 등록 코드를 끼워넣었을 때 기존에 잘 되던 것이 갑자기 깨진다.

`registerLazySingleton`을 쓰더라도 예외 상황이 있다. 팩토리 내부에서 `sl<T>()`를 호출할 때 해당 타입이 등록되어 있지 않으면 즉시 예외가 발생한다. lazy라는 이름에 속으면 안 된다 — 팩토리 함수가 실행되는 시점에 의존성이 없으면 터진다.

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

Feature 간 의존성이 생기는 경우도 주의해야 한다. 예를 들어 `NotificationRepository`가 `UserRepository`를 필요로 한다면, `UserRepository` 블록이 반드시 먼저 와야 한다. 이런 크로스-Feature 의존성이 생기기 시작하면 파일 상단에 의존성 다이어그램 주석을 달아두는 것이 도움이 된다.

---

## 문제 3: BLoC는 registerFactory

BLoC는 `registerLazySingleton`이 아니라 `registerFactory`로 등록해야 한다.

`registerLazySingleton`으로 등록하면 화면을 닫았다가 다시 열어도 동일한 BLoC 인스턴스를 재사용한다.
이전 상태가 남아있어서 화면이 의도치 않게 예전 데이터를 보여주는 버그가 생긴다.

예를 들어 법령 목록 화면에서 검색어를 입력하고 뒤로 갔다가 다시 들어오면 검색어가 그대로 남아있다. 사용자는 깨끗한 상태를 기대하는데 이전 검색 결과가 보이는 것이다.

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

반면 앱 전역에서 상태를 공유해야 하는 BLoC — 예를 들어 인증 상태를 관리하는 `AuthBloc`이나 네트워크 상태를 추적하는 `ConnectivityBloc` — 는 `registerLazySingleton`이 맞다. 이 BLoC들은 앱 생명주기 동안 단 하나의 인스턴스가 유지되어야 한다.

판단 기준은 간단하다: 화면 단위로 초기화되어야 하면 `registerFactory`, 앱 전체에서 하나의 상태를 공유해야 하면 `registerLazySingleton`.

---

## 문제 4: Feature 분리 — 파일이 200줄을 넘기 시작할 때

Feature가 10개 이상 되면 `service_locator.dart`가 200줄을 넘기 시작한다.
이 시점부터 파일이 커서를 올리고 내리는 스크롤 지옥이 된다.

Feature별로 함수를 분리하는 것이 답이다.

```dart
// lib/core/di/service_locator.dart
Future<void> setupServiceLocator({
  required String baseUrl,
}) async {
  _registerCore(baseUrl: baseUrl);
  await _registerLawsFeature();
  await _registerLegalPrecedentsFeature();
  await _registerCalendarFeature();
  // ...
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

각 Feature 폴더 안에 `di/` 디렉터리를 두고 `{feature}_dependencies.dart` 파일을 만드는 패턴이다.
Feature 담당자가 자신의 DI 코드를 직접 관리하게 되어 충돌도 줄고, 어디를 수정해야 하는지도 명확해진다.

---

## 디버깅 팁

GetIt 관련 버그는 에러 메시지만 보면 원인을 파악하기 어려울 때가 있다.

**"is not registered inside GetIt"** 에러가 나면 먼저 등록 순서를 확인한다. `service_locator.dart`에서 해당 타입이 실제로 등록되는 위치를 찾고, 의존하는 타입보다 나중에 등록되는지 확인한다.

**"Tried to register a type that is already registered"** 에러는 `updateToken` 같은 함수에서 `unregister` 없이 재등록을 시도할 때 발생한다. `allowReassignment: true` 옵션을 쓰거나, unregister 후 register 패턴을 일관되게 유지한다.

개발 중 전체 등록 상태를 확인하고 싶을 때는 GetIt의 `allReady()` 메서드를 활용할 수 있다.

```dart
// 모든 async 등록이 완료될 때까지 대기
await sl.allReady();
```

`registerSingletonAsync`를 쓰는 경우 이 체크가 특히 유용하다.

---

## 정리

| 등록 방식 | 사용처 |
|---|---|
| `registerSingleton` | 앱 전체에서 공유되는 단일 객체 (TokenProvider, Dio 등) |
| `registerLazySingleton` | Datasource, Repository - 생성 비용이 있지만 상태 공유해도 되는 것 |
| `registerFactory` | BLoC - 화면마다 새 인스턴스가 필요한 것 |
| `registerSingletonAsync` | 비동기 초기화가 필요한 싱글톤 (SharedPreferences, DB 등) |

Feature가 10개 이상 되면 service_locator.dart가 200줄을 넘기 시작한다.
Feature별로 `setupLawsDependencies()`, `setupCalendarDependencies()` 같은 함수로 분리하고 `setupServiceLocator()`에서 호출하는 방식이 관리하기 편하다.

---

## Key Takeaways

- **토큰 타이밍 문제**는 `TokenProvider` 패턴으로 해결한다. 토큰 값을 직접 주입하지 말고 토큰을 보관하는 객체를 주입하면 재등록이 필요 없다.
- **등록 순서**는 항상 datasource → repository → usecase → bloc 순을 지킨다. `registerSingleton`은 즉시 생성이므로 특히 주의한다.
- **BLoC는 무조건 `registerFactory`**. 화면 단위 BLoC에 `registerLazySingleton`을 쓰면 상태 잔류 버그가 생긴다.
- **파일이 200줄을 넘으면** Feature별 DI 파일로 분리할 시점이다.
- `is not registered` 에러는 대부분 등록 순서 문제다. `is already registered` 에러는 중복 등록이다.
