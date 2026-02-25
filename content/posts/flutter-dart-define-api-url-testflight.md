---
title: "Flutter TestFlight 빌드에서 API URL이 localhost로 고정되는 문제"
date: 2026-02-25
draft: false
tags: ["Flutter", "TestFlight", "dart-define", "iOS", "배포"]
description: "flutter build ipa에 --dart-define=API_URL을 추가하지 않으면 TestFlight 빌드가 localhost를 API 서버로 사용해서 모든 요청이 실패한다. Makefile에서 관리하는 방법을 정리한다."
---

Flutter 앱을 TestFlight에 올렸는데 실기기에서 모든 API 요청이 실패하는 경우, `--dart-define`으로 API URL이 주입되지 않아서 앱이 `localhost`로 요청을 보내고 있는 게 원인일 수 있다.

---

## 증상

- 시뮬레이터에서는 정상 동작 (로컬 서버에 연결되니까)
- TestFlight 빌드(실기기)에서는 로그인, API 호출 모두 실패
- 서버 로그에 해당 요청이 아예 안 찍힘 → 클라이언트가 서버에 요청 자체를 안 하고 있음

---

## 원인

Flutter에서 환경별 API URL을 `--dart-define`으로 주입받는 패턴을 쓰는 경우, 빌드 명령에 이 인자를 빠뜨리면 코드 내 기본값이 사용된다.

```dart
// environment.dart
static const String apiUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://localhost:3000',  // dart-define 없으면 이 값 사용
);
```

로컬 개발 시에는 `flutter run`으로 실행하면서 `--dart-define`을 넘기거나, 아예 기본값이 localhost여도 로컬 서버가 떠 있어서 동작한다.

그런데 `flutter build ipa`를 실행할 때 `--dart-define`을 빠뜨리면 릴리즈 빌드에도 `localhost`가 그대로 들어간다.

---

## 확인 방법

`Makefile`이나 빌드 스크립트를 열어서 `flutter build ipa` 명령에 `--dart-define`이 있는지 확인한다.

```makefile
# 잘못된 예시
build-ipa:
	flutter build ipa --release \
		--export-options-plist=$(EXPORT_OPTIONS)
```

```makefile
# 올바른 예시
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--export-options-plist=$(EXPORT_OPTIONS)
```

---

## 수정

빌드 명령에 `--dart-define=API_URL=`을 추가한다.

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--export-options-plist=$(EXPORT_OPTIONS)

testflight: build-ipa
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)
```

---

## dart-define을 여러 개 쓰는 경우

환경 변수가 여러 개라면 각각 `--dart-define`을 반복해서 추가한다.

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--dart-define=GOOGLE_MAPS_KEY=AIzaSy... \
		--dart-define=ENVIRONMENT=production \
		--export-options-plist=$(EXPORT_OPTIONS)
```

---

## 주의사항

`--dart-define`에 넣는 값은 빌드 시점에 바이너리에 포함된다. API 키처럼 민감한 값을 여기에 넣으면 앱 바이너리에서 추출 가능하다. 진짜 비밀 값은 서버에서 관리하고, 클라이언트에는 공개 키 또는 공개 URL 정도만 넣는 게 좋다.

---

## 정리

| 상황 | API URL |
|------|---------|
| `flutter run` (로컬) | `--dart-define` 없으면 `defaultValue` 사용 |
| `flutter build ipa` | `--dart-define` 없으면 `defaultValue` 사용 |
| TestFlight / AppStore | Makefile에서 `--dart-define` 넣어야 production URL 사용 |

TestFlight 빌드는 결국 릴리즈 빌드이므로, Makefile이나 CI 스크립트에서 `--dart-define`을 관리하고 빠뜨리지 않도록 주의한다.
