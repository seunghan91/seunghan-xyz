---
title: "Flutter Clean Architecture 실전 - Feature 여러 개 한 번에 추가하기"
date: 2025-07-09
draft: true
tags: ["Flutter", "Clean Architecture", "BLoC", "GetIt"]
description: "달력, 법령, 판례, Q&A 등 여러 Feature를 Clean Architecture 구조로 한 번에 추가하면서 겪은 폴더 구조와 의존성 관리 정리"
cover:
  image: "/images/og/flutter-clean-architecture-multi-feature.png"
  alt: "Flutter Clean Architecture Multi Feature"
  hidden: true
---

Flutter 앱에 기능을 한 번에 여러 개 추가할 때 가장 먼저 고민되는 건 폴더 구조다.
기능 하나하나는 단순해 보여도, 여러 개가 동시에 들어오면 금방 엉킨다.

달력, 법령 검색, 판례 조회, Q&A 게시판을 한 스프린트 안에 동시에 추가해야 했던 상황이 있었다. 각 기능은 독립적이었지만, 코드베이스에 합류하는 순간 의존성과 폴더 구조가 뒤엉키기 시작했다. 이 글은 그 과정에서 정리된 패턴들을 담고 있다.

---

## Feature별 폴더 구조

Clean Architecture를 기반으로 각 Feature를 아래 구조로 만든다.

```
lib/features/{feature_name}/
  ├── data/
  │   ├── datasources/     # API 호출
  │   └── repositories/    # 인터페이스 구현체
  ├── domain/
  │   ├── entities/        # 순수 데이터 모델
  │   └── repositories/    # 인터페이스 정의
  └── presentation/
      ├── bloc/            # BLoC (이벤트/상태)
      └── pages/           # UI
```

이걸 따르면 기능이 몇 개가 늘어도 구조는 동일하다.
새 기능 추가 = 폴더 복사 + 내용 채우기 수준이 된다.

이 구조의 핵심은 **레이어 간 의존성 방향**이다. `presentation`은 `domain`에만 의존하고, `data`는 `domain`의 인터페이스를 구현한다. `domain`은 어떤 레이어에도 의존하지 않는다. 기능이 늘어날 때마다 이 원칙이 흔들리지 않도록 폴더 구조가 강제한다.

use_case 레이어를 추가하는 팀도 있지만, 여러 기능을 빠르게 추가하는 상황에서는 domain/repositories + BLoC 조합으로 충분했다. 오버엔지니어링보다 일관성이 더 중요하다.

---

## 공통으로 반복되는 패턴

모든 Feature의 datasource는 거의 동일한 뼈대를 가진다.

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

토큰, baseUrl, Dio를 주입받는 구조다.
`GetIt`으로 등록할 때 이 세 가지를 외부에서 넣어준다.

반복이 눈에 보인다면 base datasource 추상 클래스를 하나 만드는 것도 방법이다. 하지만 4~5개 feature를 빠르게 추가하는 상황이라면 오히려 추상화보다 복사-붙여넣기 후 수정이 더 빠를 수 있다. 중요한 건 **각 datasource가 동일한 생성자 시그니처를 유지하는 것**이다. GetIt 등록 코드가 예측 가능해진다.

에러 처리는 datasource 레이어에서 `DioException`을 잡아 도메인 예외로 변환하는 게 깔끔하다. 그래야 BLoC에서 Flutter/네트워크 라이브러리에 의존하지 않아도 된다.

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

## 반복이 많으면 entity부터 먼저 잡아라

기능을 빠르게 추가할 때 실수하는 지점이 entity다.
API 응답을 보고 대충 만들면, 나중에 BLoC에서 필드 접근할 때 null이 터진다.

fromJson을 꼼꼼하게, 특히 nullable 처리를 명확히 해야 한다.

```dart
class LegalPrecedent {
  final int id;
  final String caseNumber;
  final String? summary;       // null 가능
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
      summary: json['summary'],  // null이면 그냥 null
      decidedAt: DateTime.parse(json['decided_at']),
    );
  }
}
```

필드를 nullable로 열어두면 UI에서 처리가 늘어나지만, non-null로 강제하면 파싱 오류가 런타임에 터진다. 타협점은 데이터가 **항상 존재한다고 서버에서 보장하는 것만** non-null로 두는 것이다.

### fromJson 디버깅 시 자주 만나는 오류들

여러 entity를 빠르게 작성하다 보면 반드시 만나는 오류 패턴이 있다.

**`type 'Null' is not a subtype of type 'String'`**
: non-null 필드에 null이 들어온 경우다. API 문서에 "항상 있다"고 적혀 있어도 실제로는 null이 오는 케이스가 있다. `json['field'] as String` 대신 `json['field']?.toString() ?? ''` 패턴을 쓰거나 nullable로 내려야 한다.

**`type 'int' is not a subtype of type 'String'`**
: 숫자처럼 생긴 값이 실제로는 정수로 내려오는 경우다. `json['id'].toString()`으로 강제 변환하거나 엔티티 타입을 조정한다.

**`FormatException: Invalid date format`**
: `DateTime.parse`는 ISO 8601 형식만 받는다. 서버에서 `"2025-07-09 10:30:00"` 형태로 내려오면 실패한다. `DateTime.tryParse`를 쓰거나 별도 파싱 로직을 추가해야 한다.

entity를 먼저 확정하고 나면 나머지 레이어는 기계적으로 채워진다. entity 설계가 흔들리면 위 레이어 전체가 흔들린다.

---

## Repository 인터페이스는 짧게

도메인 레이어의 repository는 인터페이스만 정의한다. 구현은 data 레이어에 있다.

```dart
// domain/repositories/laws_repository.dart
abstract class LawsRepository {
  Future<List<Law>> getLaws({int page});
  Future<Law> getLawDetail(int id);
}
```

인터페이스를 먼저 쓰고, 구현체는 나중에 채운다.
기능이 많을 때 인터페이스를 먼저 다 정의해두면 BLoC 작성 순서가 유연해진다.

인터페이스가 먼저 있으면 BLoC을 구현하는 동안 datasource와 repository 구현체가 아직 완성되지 않아도 컴파일이 된다. 팀 작업이라면 인터페이스를 먼저 PR로 올려두고 각자 레이어를 병렬로 구현할 수 있다.

data 레이어의 구현체는 이렇게 된다.

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

repository 구현체는 datasource를 감싸는 얇은 래퍼다. 에러 변환이나 캐싱 로직이 필요하다면 이 레이어에 추가하면 된다.

---

## GetIt 등록: 순서와 그룹화

여러 Feature를 동시에 추가할 때 service_locator.dart가 빠르게 길어진다. 기능별로 등록 함수를 분리하는 게 관리하기 편하다.

```dart
// lib/core/di/service_locator.dart
Future<void> setupDependencies() async {
  // 공통 의존성
  _setupCore();

  // Feature별 의존성
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

`registerLazySingleton`은 처음 참조될 때 생성되고, `registerFactory`는 매번 새 인스턴스를 만든다. BLoC은 보통 `registerFactory`로 등록한다. 위젯이 사라질 때 BLoC도 dispose되어야 하기 때문이다.

---

## 여러 Feature 추가 시 체크리스트

실제로 겪은 누락 패턴들이다.

**1. service_locator 등록 누락**

Feature를 만들어놓고 `GetIt`에 등록을 빠뜨리면 런타임에 `Not registered` 에러가 난다.
Feature 추가 → service_locator.dart 등록 → main.dart 라우트 추가를 세트로 묶어서 생각해야 한다.

`Not registered: LawsBloc` 같은 에러는 명확하지만, `Not registered: LawsRepository`처럼 BLoC이 내부적으로 참조하는 의존성이 누락된 경우는 스택 트레이스를 따라가야 원인을 찾을 수 있다. GetIt은 lazy 등록이기 때문에 앱 시작 시 오류가 터지지 않고 실제 호출 시점에 터진다.

**2. main.dart 라우트 누락**

페이지를 만들고 라우트를 안 연결하면 당연히 접근이 안 된다.
그런데 에러 메시지가 "route not found"가 아니라 다른 형태로 나올 때가 있어서 헷갈린다.

go_router를 쓰는 경우 `GoRouter`의 `routes` 목록에 추가하지 않으면 `GoException`이 발생한다. Navigator 1.0 방식이라면 `onGenerateRoute`에서 누락된 케이스가 `unknownRoute`로 떨어진다. 어느 쪽이든 화면이 안 뜨는 증상은 같다.

**3. BLoC 이벤트 클래스 export 누락**

BLoC 파일에서 이벤트/상태 클래스를 barrel export하지 않으면, 페이지에서 import할 때 경로가 꼬인다.
BLoC 파일 상단에 event, state 파일을 part로 포함하거나, 단일 파일로 관리하는 게 편하다.

```dart
// presentation/bloc/laws_bloc.dart
part 'laws_event.dart';
part 'laws_state.dart';

class LawsBloc extends Bloc<LawsEvent, LawsState> {
  // ...
}
```

`part` 방식을 쓰면 `laws_bloc.dart` 하나만 import해도 이벤트와 상태가 함께 접근된다. 파일이 분리되어 있어도 외부에서는 단일 진입점처럼 쓸 수 있다.

**4. BlocProvider 누락**

BLoC을 GetIt에 등록했어도 위젯 트리에 `BlocProvider`를 안 감싸면 `BlocProvider.of<LawsBloc>` 호출 시 오류가 난다. 페이지 라우트 정의 부분에서 `BlocProvider`로 감싸거나, 페이지 최상단 위젯에서 제공해야 한다.

```dart
GoRoute(
  path: '/laws',
  builder: (context, state) => BlocProvider(
    create: (_) => sl<LawsBloc>()..add(LoadLaws()),
    child: const LawsPage(),
  ),
),
```

---

## Key Takeaways

- **폴더 구조 통일이 속도를 만든다.** Feature 구조를 표준화하면 새 기능 추가가 템플릿 복사 수준으로 줄어든다. 구조를 고민하는 시간이 사라지고 구현에 집중할 수 있다.

- **Entity 설계가 전체 레이어의 기반이다.** API 응답을 바탕으로 nullable 처리를 명확히 하고 fromJson을 꼼꼼하게 작성해야 한다. entity가 흔들리면 BLoC 상태, UI 렌더링 모두 흔들린다.

- **Repository 인터페이스를 먼저 정의하면 병렬 작업이 가능하다.** 인터페이스만 있으면 datasource 구현과 BLoC 구현을 동시에 진행할 수 있다. 테스트 작성도 mock을 쓸 수 있어서 편해진다.

- **등록 3종 세트를 빠뜨리지 말 것.** service_locator 등록 + 라우트 연결 + BLoC export는 feature 추가 시 항상 세트로 따라온다. 하나라도 빠지면 런타임 오류로 디버깅 시간을 날린다.

- **GetIt에서 BLoC은 `registerFactory`로 등록한다.** BLoC이 singleton으로 등록되면 dispose 타이밍이 꼬여서 이전 상태가 새 화면에 남아있는 버그가 생긴다. 매번 새 인스턴스를 만드는 `registerFactory`가 맞다.
