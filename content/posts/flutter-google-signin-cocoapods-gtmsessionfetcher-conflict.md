---
title: "Flutter google_sign_in 추가 후 CocoaPods GTMSessionFetcher 버전 충돌 해결"
date: 2025-07-27
draft: true
tags: ["Flutter", "iOS", "CocoaPods", "Google Sign-In", "Troubleshooting"]
description: "Flutter 프로젝트에 google_sign_in 패키지를 추가하고 빌드하면 CocoaPods에서 GTMSessionFetcher/Core 버전 충돌이 발생할 수 있다. 원인과 해결 방법을 정리한다."
cover:
  image: "/images/og/flutter-google-signin-cocoapods-gtmsessionfetcher-conflict.png"
  alt: "Flutter Google Signin Cocoapods Gtmsessionfetcher Conflict"
  hidden: true
---

Flutter 앱에 `google_sign_in` 패키지를 추가하고 `flutter build ipa`를 실행했더니 CocoaPods 단계에서 빌드가 실패했다. 에러 메시지만 보면 단순한 버전 충돌처럼 보이지만, CocoaPods의 lock 파일 동작 방식을 이해하지 못하면 해결에 시간을 많이 쏟게 된다. 이 글에서는 충돌의 정확한 원인, 최소 범위 해결법, 그리고 전체 Google Sign-In 연동 과정을 정리한다.

---

## 에러 메시지

```
[!] CocoaPods could not find compatible versions for pod "GTMSessionFetcher/Core":
  In snapshot (Podfile.lock):
    GTMSessionFetcher/Core (< 5.0, = 4.5.0, >= 3.4)

  In Podfile:
    google_sign_in_ios was resolved to 0.0.1, which depends on
      GoogleSignIn (~> 8.0) was resolved to 8.0.0, which depends on
        GTMSessionFetcher/Core (~> 3.3)
```

핵심은 `Podfile.lock`에 고정된 `GTMSessionFetcher` 버전(4.5.0)과 `google_sign_in`이 요구하는 버전(`~> 3.3`)이 충돌한다는 것이다.

버전 제약 표기법 `~> 3.3`은 "3.3 이상, 4.0 미만"을 의미하는 pessimistic constraint operator다. 즉 `google_sign_in`은 3.x 계열을 원하는데, lock 파일에는 4.5.0이 박혀 있는 상황이다.

---

## 원인: CocoaPods lock 파일의 동작 방식

### Podfile.lock이란

`Podfile.lock`은 `pod install`이 성공했을 때 각 Pod의 정확한 버전을 기록하는 스냅샷 파일이다. 이후 팀원이 같은 프로젝트를 클론하거나 CI 서버에서 빌드할 때 동일한 버전을 재현하기 위해 존재한다.

CocoaPods는 `pod install` 시 `Podfile.lock`에 기록된 버전을 **최우선으로** 사용한다. Podfile에 새로운 의존성이 추가되더라도, 기존에 lock된 Pod은 재해석하지 않는다.

### 충돌이 발생하는 구체적인 시나리오

1. 기존 프로젝트에 Firebase SDK가 설치되어 있음
2. Firebase SDK는 내부적으로 `GTMSessionFetcher 4.5.0`을 사용하고 있고, 이 버전이 `Podfile.lock`에 고정되어 있음
3. `google_sign_in` 패키지를 `pubspec.yaml`에 추가하고 `flutter pub get` 실행
4. Flutter가 `ios/Podfile`에 `google_sign_in_ios` 의존성을 추가
5. `pod install` 실행 시 `google_sign_in_ios` → `GoogleSignIn ~> 8.0` → `GTMSessionFetcher/Core ~> 3.3` 의존성 체인이 형성됨
6. CocoaPods가 `GTMSessionFetcher 3.x`를 설치하려 하지만 lock 파일에는 `4.5.0`이 고정되어 있어 충돌 발생

### 왜 pod install만으로는 안 되는가

`pod install`은 lock 파일에 없는 새 Pod만 추가한다. 이미 lock된 `GTMSessionFetcher 4.5.0`은 건드리지 않기 때문에, 새로 추가된 `google_sign_in`의 요구사항(`~> 3.3`)과 기존 lock 버전(`4.5.0`)이 충돌하는 상태가 지속된다.

---

## 해결: 타겟 Pod만 업데이트

iOS 디렉토리에서 해당 Pod만 업데이트하면 된다.

```bash
cd ios && pod update GTMSessionFetcher
```

`pod update [Pod명]`은 지정된 Pod 하나만 lock 파일 제약을 무시하고 재해석한다. 이 경우 CocoaPods는 `GTMSessionFetcher`를 Firebase와 `google_sign_in` 양쪽의 요구사항을 모두 만족하는 버전으로 재결정한다.

실제로는 `GTMSessionFetcher 4.x`가 `~> 3.3` 요구사항과 호환되도록 업데이트되거나, 양쪽 모두 수용할 수 있는 공통 버전으로 재설정된다.

### 왜 전체 pod update는 피해야 하는가

```bash
# 위험: 모든 Pod을 최신 버전으로 올림
cd ios && pod update

# 안전: 충돌 Pod만 업데이트
cd ios && pod update GTMSessionFetcher
```

전체 `pod update`는 프로젝트의 모든 Pod을 최신 버전으로 올린다. Firebase, Crashlytics 등 다른 SDK들이 예상치 못한 breaking change를 포함한 버전으로 올라갈 수 있고, 이로 인해 새로운 빌드 에러나 런타임 버그가 생길 수 있다. 충돌 Pod만 명시적으로 지정하는 것이 훨씬 안전하다.

업데이트 후 다시 빌드하면 정상적으로 통과한다.

```bash
flutter build ipa --release
```

---

## 전체 과정 요약

Google Sign-In을 Flutter iOS 앱에 연동하는 전체 흐름은 다음과 같다.

### 1. Google Cloud Console에서 OAuth iOS 클라이언트 생성

[Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create Credentials → OAuth client ID

- 애플리케이션 유형: **iOS**
- 번들 ID: Xcode 프로젝트의 `PRODUCT_BUNDLE_IDENTIFIER` 값 (예: `com.example.myapp`)
- 팀 ID: Apple Developer 계정의 `DEVELOPMENT_TEAM` 값 (10자리 영숫자)

생성하면 **Client ID**와 **Reversed Client ID**가 포함된 `GoogleService-Info.plist` 파일을 다운로드할 수 있다.

**중요:** Firebase 프로젝트와 동일한 Google Cloud 프로젝트 번호를 사용해야 한다. 다른 프로젝트에 OAuth 클라이언트를 만들면 구글 서버에서 토큰 검증 시 프로젝트 불일치 에러가 발생한다.

### 2. GoogleService-Info.plist에 CLIENT_ID 추가

Firebase Console에서 다운로드한 `GoogleService-Info.plist`에는 OAuth `CLIENT_ID`가 기본 포함되지 않는 경우가 있다. Google Cloud Console에서 생성한 Client ID를 직접 추가해야 한다.

```xml
<key>CLIENT_ID</key>
<string>YOUR_CLIENT_ID.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
```

`REVERSED_CLIENT_ID`는 `CLIENT_ID`를 점(`.`) 기준으로 뒤집은 값이다. 예를 들어 Client ID가 `123456-abcdef.apps.googleusercontent.com`이라면, Reversed Client ID는 `com.googleusercontent.apps.123456-abcdef`가 된다.

### 3. Info.plist에 URL Scheme 추가

Google Sign-In은 OAuth 2.0 인증 흐름에서 사파리 또는 SFSafariViewController를 열고, 인증이 완료되면 앱으로 리다이렉트한다. 이 리다이렉트를 받기 위해 `REVERSED_CLIENT_ID`를 URL scheme으로 등록해야 한다.

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleTypeRole</key>
    <string>Editor</string>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
    </array>
  </dict>
</array>
```

이 설정이 없으면 사용자가 구글 계정 선택 화면에서 인증을 완료해도 앱으로 돌아오지 못하고 사파리에 머물게 된다.

### 4. pubspec.yaml에 패키지 추가

```yaml
dependencies:
  google_sign_in: ^6.2.2
```

`flutter pub get`을 실행하면 Flutter가 자동으로 iOS의 `Podfile`에 `google_sign_in_ios` 의존성을 추가한다.

### 5. pod update로 버전 충돌 해결

```bash
flutter pub get
cd ios && pod update GTMSessionFetcher
```

### 6. 빌드 및 배포

```bash
flutter build ipa --release
```

---

## 디버깅 단계별 접근법

에러가 처음 발생했을 때 막막하게 느껴진다면 아래 순서로 확인해보자.

### 1단계: 에러 메시지에서 충돌 Pod 특정

에러 메시지를 꼼꼼히 읽으면 어떤 Pod이 어떤 버전을 요구하는지 의존성 체인이 명시된다. 위 예시에서는 `GTMSessionFetcher`가 충돌 Pod임을 확인할 수 있다.

### 2단계: Podfile.lock에서 현재 고정 버전 확인

```bash
cat ios/Podfile.lock | grep GTMSessionFetcher
```

출력 예시:
```
  - GTMSessionFetcher/Core (4.5.0)
  - GTMSessionFetcher/Full (4.5.0)
GTMSessionFetcher/Core: 4.5.0
```

### 3단계: 타겟 Pod 업데이트

```bash
cd ios && pod update GTMSessionFetcher
```

업데이트 후 `Podfile.lock`에서 버전이 변경되었는지 확인한다.

### 4단계: 빌드 재시도

```bash
flutter build ipa --release
```

동일한 에러가 반복된다면 의존성 체인에 다른 Pod도 관여하고 있을 수 있다. 에러 메시지에서 새로운 충돌 Pod을 확인하고 같은 방법으로 반복한다.

---

## 자주 하는 실수

- **`pod install`만 반복 실행**: lock 파일이 있는 한 결과가 바뀌지 않는다. 반드시 `pod update [Pod명]`이 필요하다.
- **전체 `pod update` 실행**: 다른 Pod까지 올라가서 새로운 빌드 에러가 생길 수 있다. 충돌 Pod만 지정하자.
- **OAuth 클라이언트를 잘못된 프로젝트에 생성**: Firebase 프로젝트와 다른 Google Cloud 프로젝트에 만들면 런타임에서 토큰 검증 실패가 발생한다.
- **`CLIENT_ID`와 URL Scheme 불일치**: `GoogleService-Info.plist`의 `CLIENT_ID`와 `Info.plist`의 `CFBundleURLSchemes`는 반드시 대응되어야 한다. 하나라도 빠지거나 잘못된 값이면 iOS에서 Google 로그인 콜백이 동작하지 않는다.
- **`pod update` 후 Flutter clean 미실행**: 간혹 Flutter 빌드 캐시가 남아있어 문제가 지속되는 경우가 있다. `flutter clean && flutter pub get` 후 재빌드해보자.

---

## 예방 방법

같은 문제가 반복되지 않도록 하려면 몇 가지 습관을 들이는 것이 좋다.

### 새 패키지 추가 시 의존성 체인 미리 확인

새 Flutter 패키지를 추가하기 전에 해당 패키지의 네이티브 의존성을 미리 파악해두자. `google_sign_in`처럼 Google SDK를 사용하는 패키지들은 `GTMSessionFetcher`, `GoogleUtilities` 등 공유 라이브러리를 사용하는 경우가 많아 Firebase와 충돌이 잦다.

### Podfile.lock을 git에 커밋

`Podfile.lock`은 반드시 git에 포함시켜야 한다. 팀원 간 Pod 버전 불일치를 방지하고, 문제 발생 시 이전 상태로 되돌릴 수 있다.

### CI에서 pod update 대신 pod install 사용

CI/CD 파이프라인에서는 `pod install`을 사용해 lock 파일의 버전을 그대로 재현한다. `pod update`는 로컬 개발 환경에서 의도적으로 버전을 올릴 때만 사용한다.

### 의존성 충돌 발생 시 즉시 해결

충돌을 방치하면 다음 패키지 추가 시 더 복잡한 충돌이 쌓인다. 발생 즉시 최소 범위로 해결하는 습관이 중요하다.

---

## Key Takeaways

- `Podfile.lock`은 Pod 버전을 고정하는 스냅샷 파일이며, `pod install`은 이 파일을 우선시한다.
- Firebase와 `google_sign_in` 모두 `GTMSessionFetcher`를 사용하기 때문에 버전 충돌이 자주 발생한다.
- 해결책은 `cd ios && pod update GTMSessionFetcher`로 충돌 Pod 하나만 타겟 업데이트하는 것이다.
- 전체 `pod update`는 사이드이펙트 위험이 있으므로 피해야 한다.
- Google Sign-In 연동 시 `GoogleService-Info.plist`의 `CLIENT_ID`와 `Info.plist`의 URL Scheme은 반드시 쌍으로 설정해야 한다.
- OAuth 클라이언트는 Firebase 프로젝트와 동일한 Google Cloud 프로젝트에 생성해야 토큰 검증이 통과된다.
