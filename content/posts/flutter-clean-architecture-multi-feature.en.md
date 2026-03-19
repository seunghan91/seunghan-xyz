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

---

## Checklist When Adding Multiple Features

These are the omission patterns I actually encountered.

**1. Missing service_locator registration**

If you create a feature but forget to register it with `GetIt`, you'll get a `Not registered` runtime error.
Think of it as a set: add feature -> register in service_locator.dart -> add route in main.dart.

**2. Missing main.dart route**

If you create a page but don't connect the route, naturally it can't be accessed.
But sometimes the error message comes in a different form than "route not found," which is confusing.

**3. Missing BLoC event class export**

If you don't barrel export event/state classes from the BLoC file, import paths get messy in the pages.
It's easier to include event and state files as `part` in the BLoC file header, or manage everything in a single file.

---

## Summary

- Unifying feature folder structure gives you momentum when adding multiple features simultaneously
- Defining nullable handling in entities clearly from the start prevents parsing errors later
- After adding a feature, don't forget these three: service_locator, route, and export
