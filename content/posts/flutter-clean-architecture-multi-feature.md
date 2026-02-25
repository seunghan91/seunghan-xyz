---
title: "Flutter Clean Architecture 실전 - Feature 여러 개 한 번에 추가하기"
date: 2026-02-25
draft: false
tags: ["Flutter", "Clean Architecture", "BLoC", "GetIt"]
description: "달력, 법령, 판례, Q&A 등 여러 Feature를 Clean Architecture 구조로 한 번에 추가하면서 겪은 폴더 구조와 의존성 관리 정리"
---

Flutter 앱에 기능을 한 번에 여러 개 추가할 때 가장 먼저 고민되는 건 폴더 구조다.
기능 하나하나는 단순해 보여도, 여러 개가 동시에 들어오면 금방 엉킨다.

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

---

## 여러 Feature 추가 시 체크리스트

실제로 겪은 누락 패턴들이다.

**1. service_locator 등록 누락**

Feature를 만들어놓고 `GetIt`에 등록을 빠뜨리면 런타임에 `Not registered` 에러가 난다.
Feature 추가 → service_locator.dart 등록 → main.dart 라우트 추가를 세트로 묶어서 생각해야 한다.

**2. main.dart 라우트 누락**

페이지를 만들고 라우트를 안 연결하면 당연히 접근이 안 된다.
그런데 에러 메시지가 "route not found"가 아니라 다른 형태로 나올 때가 있어서 헷갈린다.

**3. Bloc 이벤트 클래스 export 누락**

BLoC 파일에서 이벤트/상태 클래스를 barrel export하지 않으면, 페이지에서 import할 때 경로가 꼬인다.
BLoC 파일 상단에 event, state 파일을 part로 포함하거나, 단일 파일로 관리하는 게 편하다.

---

## 정리

- Feature 폴더 구조를 통일하면 여러 개를 동시에 추가할 때 속도가 붙는다
- Entity의 nullable 처리를 처음부터 명확히 해야 나중에 파싱 오류를 막는다
- Feature 추가 후 service_locator, 라우트, export 세 가지를 빠뜨리지 말 것
