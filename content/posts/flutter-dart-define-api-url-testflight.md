---
title: "Flutter TestFlight 빌드에서 API URL이 localhost로 고정되는 문제"
date: 2025-07-13
draft: true
tags: ["Flutter", "TestFlight", "dart-define", "iOS", "배포"]
description: "flutter build ipa에 --dart-define=API_URL을 추가하지 않으면 TestFlight 빌드가 localhost를 API 서버로 사용해서 모든 요청이 실패한다. Makefile에서 관리하는 방법을 정리한다."
cover:
  image: "/images/og/flutter-dart-define-api-url-testflight.png"
  alt: "Flutter Dart Define Api Url Testflight"
  hidden: true
---

Flutter 앱을 TestFlight에 올렸는데 실기기에서 모든 API 요청이 실패하는 경우, `--dart-define`으로 API URL이 주입되지 않아서 앱이 `localhost`로 요청을 보내고 있는 게 원인일 수 있다.

이 글에서는 문제의 증상, 근본 원인, 디버깅 방법, 수정 방법, 그리고 재발 방지를 위한 CI/CD 구성까지 단계별로 정리한다.

---

## 증상

- 시뮬레이터에서는 정상 동작 (로컬 서버에 연결되니까)
- TestFlight 빌드(실기기)에서는 로그인, API 호출 모두 실패
- 서버 로그에 해당 요청이 아예 안 찍힘 → 클라이언트가 서버에 요청 자체를 안 하고 있음
- Charles Proxy나 Proxyman으로 트래픽을 캡처하면 `http://localhost:3000`으로 요청이 나가는 것을 확인할 수 있음
- 에러 메시지는 보통 `SocketException: Connection refused` 또는 `Connection timed out`

시뮬레이터와 실기기의 동작이 다르면 환경 차이를 가장 먼저 의심해야 한다. 특히 API URL처럼 빌드 시점에 결정되는 값은 런타임 로그만으로는 파악하기 어렵다.

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

`String.fromEnvironment`는 컴파일 타임(build time) 상수다. 런타임에 환경 변수를 읽는 게 아니라, `flutter build` 명령이 실행되는 시점에 값이 바이너리 안에 박힌다. 따라서 빌드 명령에 `--dart-define`이 없으면 어떤 기기에서 실행하든 무조건 `defaultValue`가 사용된다.

### 왜 시뮬레이터에서는 동작하는가?

로컬 개발 시에는 두 가지 이유로 문제가 드러나지 않는다.

1. `flutter run` 명령에 `--dart-define=API_URL=http://localhost:3000`을 명시적으로 전달하고 있거나
2. `defaultValue`가 `http://localhost:3000`이고, 시뮬레이터는 맥의 localhost에 접근할 수 있어서 실제로 요청이 성공한다

두 경우 모두 개발 중에는 문제가 없다. 그러다가 `flutter build ipa`를 실행할 때 `--dart-define`을 빠뜨리면, 릴리즈 바이너리 안에 `localhost:3000`이 그대로 하드코딩된다. 실기기는 개발자의 맥에 접근할 수 없으니 모든 요청이 실패한다.

### dart-define의 동작 원리

`--dart-define`은 Dart의 `const` 컴파일 시스템과 연동된다. 빌드 도구(flutter build)가 dart2native 혹은 dart2js 컴파일러에게 `-D` 플래그로 값을 전달하고, 컴파일러가 `String.fromEnvironment` 호출을 해당 리터럴 값으로 교체한다. 즉 결과물 바이너리에는 `String.fromEnvironment` 코드가 아닌 실제 문자열이 들어간다.

이 덕분에 런타임 오버헤드가 없고, `const`로 선언된 환경 값을 switch문이나 if/else 분기에 활용해 데드코드 제거(tree-shaking)도 가능하다. 하지만 바로 이 때문에 빌드 명령에 값을 반드시 포함시켜야 한다는 제약이 생긴다.

---

## 디버깅 방법

### 1. Makefile 또는 빌드 스크립트 확인

가장 먼저 `flutter build ipa` 명령에 `--dart-define`이 있는지 확인한다.

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

### 2. 빌드된 바이너리에서 문자열 추출

이미 빌드된 IPA가 있다면 바이너리에서 직접 확인할 수 있다.

```bash
# IPA 파일 압축 해제
unzip app.ipa -d app_extracted

# 바이너리에서 localhost 검색
strings app_extracted/Payload/Runner.app/Runner | grep localhost

# 또는 API URL 패턴으로 검색
strings app_extracted/Payload/Runner.app/Runner | grep -E "https?://"
```

`localhost`가 나오면 `--dart-define`이 빠진 것이다.

### 3. 프록시로 실시간 트래픽 확인

Charles Proxy 또는 Proxyman을 설정하고 TestFlight 앱을 실행하면 실제로 어떤 URL로 요청이 나가는지 실시간으로 볼 수 있다. `localhost`로 요청이 나가면 즉시 `Connection refused`가 발생한다.

### 4. 로그 추가

의심스러우면 앱 시작 시점에 환경 값을 출력하도록 코드를 추가한다.

```dart
void main() {
  // 개발 중에만 사용, 배포 전 제거 권장
  debugPrint('API_URL: ${Environment.apiUrl}');
  runApp(const MyApp());
}
```

TestFlight 빌드에서 Xcode의 Devices and Simulators 창으로 실기기 로그를 확인하면 실제로 어떤 URL이 들어갔는지 알 수 있다.

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

`testflight` 타겟이 `build-ipa`에 의존하도록 구성해두면 `make testflight` 한 번으로 빌드부터 업로드까지 처리된다.

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

변수가 많아지면 가독성이 떨어지므로 별도 파일로 분리하는 방법도 있다.

### dart-define-from-file 사용 (Flutter 3.7+)

Flutter 3.7부터 `--dart-define-from-file` 옵션이 추가됐다. JSON 파일로 환경 변수를 관리할 수 있다.

```json
// config/production.json
{
  "API_URL": "https://api.example.com",
  "GOOGLE_MAPS_KEY": "AIzaSy...",
  "ENVIRONMENT": "production"
}
```

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define-from-file=config/production.json \
		--export-options-plist=$(EXPORT_OPTIONS)
```

이 방식은 변수가 많을 때 Makefile을 깔끔하게 유지하는 데 유용하다. 다만 JSON 파일을 git에 커밋할 때 API 키 같은 민감한 값이 포함되지 않도록 주의해야 한다.

---

## 여러 환경(staging, production)을 관리하는 경우

실무에서는 보통 development, staging, production 세 가지 환경을 운영한다.

```makefile
# 환경별 설정을 변수로 분리
PROD_API_URL = https://api.example.com
STAGING_API_URL = https://staging-api.example.com

build-ipa-prod:
	flutter build ipa --release \
		--dart-define=API_URL=$(PROD_API_URL) \
		--dart-define=ENVIRONMENT=production \
		--export-options-plist=ios/ExportOptions.plist

build-ipa-staging:
	flutter build ipa --release \
		--dart-define=API_URL=$(STAGING_API_URL) \
		--dart-define=ENVIRONMENT=staging \
		--export-options-plist=ios/ExportOptions.plist

testflight-prod: build-ipa-prod
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)

testflight-staging: build-ipa-staging
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)
```

이렇게 구성하면 `make testflight-staging`으로 스테이징 빌드를, `make testflight-prod`로 프로덕션 빌드를 각각 올릴 수 있다.

---

## 주의사항

`--dart-define`에 넣는 값은 빌드 시점에 바이너리에 포함된다. API 키처럼 민감한 값을 여기에 넣으면 앱 바이너리에서 추출 가능하다. 진짜 비밀 값은 서버에서 관리하고, 클라이언트에는 공개 키 또는 공개 URL 정도만 넣는 게 좋다.

보안 관점에서 `--dart-define`에 적합한 값과 그렇지 않은 값을 구분하면 다음과 같다.

| 적합한 값 | 부적합한 값 |
|-----------|------------|
| API 서버 URL | 데이터베이스 비밀번호 |
| Google Maps 공개 키 | 서버 시크릿 키 |
| 환경 플래그 (production/staging) | JWT 서명 키 |
| Firebase 프로젝트 ID | 결제 시크릿 키 |

---

## 재발 방지: CI/CD 구성

이 문제는 한 번 경험하고 나면 Makefile을 수정해서 해결하지만, 팀 규모가 커지거나 CI/CD를 도입할 때 다시 놓치기 쉽다.

### GitHub Actions 예시

```yaml
# .github/workflows/testflight.yml
name: Deploy to TestFlight

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Flutter
        uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.x'

      - name: Build IPA
        run: |
          flutter build ipa --release \
            --dart-define=API_URL=${{ secrets.PROD_API_URL }} \
            --dart-define=ENVIRONMENT=production \
            --export-options-plist=ios/ExportOptions.plist

      - name: Upload to TestFlight
        run: |
          xcrun altool --upload-app \
            --type ios \
            --file "build/ios/ipa/*.ipa" \
            --apiKey ${{ secrets.ASC_KEY_ID }} \
            --apiIssuer ${{ secrets.ASC_ISSUER_ID }}
```

GitHub Secrets에 `PROD_API_URL`, `ASC_KEY_ID`, `ASC_ISSUER_ID`를 등록해두면 CI 파이프라인이 자동으로 올바른 값을 주입해 빌드한다.

---

## 정리

| 상황 | API URL |
|------|---------|
| `flutter run` (로컬) | `--dart-define` 없으면 `defaultValue` 사용 |
| `flutter build ipa` | `--dart-define` 없으면 `defaultValue` 사용 |
| TestFlight / AppStore | Makefile에서 `--dart-define` 넣어야 production URL 사용 |

TestFlight 빌드는 결국 릴리즈 빌드이므로, Makefile이나 CI 스크립트에서 `--dart-define`을 관리하고 빠뜨리지 않도록 주의한다.

---

## Key Takeaways

- `String.fromEnvironment`는 런타임이 아닌 **컴파일 타임**에 값이 결정된다. 빌드 명령에 `--dart-define`이 없으면 어떤 기기에서 실행하든 `defaultValue`가 사용된다.
- **시뮬레이터에서 동작 → 실기기에서 실패** 패턴이 나타나면 환경 설정 문제를 가장 먼저 의심한다.
- `strings` 명령으로 빌드된 바이너리에서 직접 URL을 확인할 수 있다. 디버깅 시 가장 빠른 방법이다.
- Flutter 3.7+에서는 `--dart-define-from-file`로 JSON 파일에서 환경 변수를 일괄 주입할 수 있다. 변수가 많으면 이 방식이 더 관리하기 편하다.
- `--dart-define` 값은 바이너리에 포함되므로 API 서버 URL, 공개 키처럼 노출돼도 무방한 값만 넣는다. 시크릿 키는 서버에서 관리한다.
- Makefile의 `testflight` 타겟이 `build-ipa`에 의존하도록 설정하고, `build-ipa`에 `--dart-define`을 강제 포함시키면 실수를 줄일 수 있다.
- CI/CD(GitHub Actions 등)를 사용한다면 `--dart-define` 값을 GitHub Secrets에서 주입해 보안과 편의성을 모두 챙긴다.
