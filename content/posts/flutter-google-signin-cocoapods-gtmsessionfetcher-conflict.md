---
title: "Flutter google_sign_in 추가 후 CocoaPods GTMSessionFetcher 버전 충돌 해결"
date: 2026-02-25
draft: false
tags: ["Flutter", "iOS", "CocoaPods", "Google Sign-In", "Troubleshooting"]
description: "Flutter 프로젝트에 google_sign_in 패키지를 추가하고 빌드하면 CocoaPods에서 GTMSessionFetcher/Core 버전 충돌이 발생할 수 있다. 원인과 해결 방법을 정리한다."
---

Flutter 앱에 `google_sign_in` 패키지를 추가하고 `flutter build ipa`를 실행했더니 CocoaPods 단계에서 빌드가 실패했다.

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

---

## 원인

기존 프로젝트에 Firebase 관련 Pod들이 이미 설치되어 있으면 `Podfile.lock`에 `GTMSessionFetcher` 버전이 고정된다. 새로 추가한 `google_sign_in` 패키지의 네이티브 의존성인 `GoogleSignIn` SDK는 `GTMSessionFetcher/Core ~> 3.3`을 요구하는데, lock 파일에 잡힌 버전과 호환되지 않으면 충돌이 발생한다.

CocoaPods는 `Podfile.lock`의 버전을 우선하기 때문에 `pod install`만으로는 해결되지 않는다.

---

## 해결

iOS 디렉토리에서 해당 Pod만 업데이트하면 된다.

```bash
cd ios && pod update GTMSessionFetcher
```

이렇게 하면 `GTMSessionFetcher`가 모든 의존성을 만족하는 버전으로 재해석된다. 전체 `pod update`를 하면 다른 Pod까지 불필요하게 올라갈 수 있으니 타겟을 지정하는 게 안전하다.

업데이트 후 다시 빌드하면 정상적으로 통과한다.

```bash
flutter build ipa --release
```

---

## 전체 과정 요약

Google Sign-In을 Flutter iOS에 추가하려면 아래 순서로 진행한다.

### 1. Google Cloud Console에서 OAuth iOS 클라이언트 생성

- 애플리케이션 유형: iOS
- 번들 ID: Xcode 프로젝트의 `PRODUCT_BUNDLE_IDENTIFIER` 값
- 팀 ID: Apple Developer의 `DEVELOPMENT_TEAM` 값

생성하면 **Client ID**와 **Reversed Client ID**가 포함된 plist 파일을 다운로드할 수 있다.

### 2. GoogleService-Info.plist에 CLIENT_ID 추가

Firebase 콘솔에서 다운로드한 `GoogleService-Info.plist`에는 OAuth `CLIENT_ID`가 기본 포함되지 않는 경우가 있다. 직접 추가해야 한다.

```xml
<key>CLIENT_ID</key>
<string>YOUR_CLIENT_ID.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
```

### 3. Info.plist에 URL Scheme 추가

Google Sign-In 콜백을 받기 위해 `REVERSED_CLIENT_ID`를 URL scheme으로 등록한다.

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

### 4. pubspec.yaml에 패키지 추가

```yaml
dependencies:
  google_sign_in: ^6.2.2
```

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

## 삽질 포인트

- `pod install`만 하면 lock 파일 제약 때문에 해결되지 않는다. 반드시 `pod update [패키지명]`으로 타겟 업데이트가 필요하다.
- `pod update` (전체)는 다른 Pod 버전까지 올릴 수 있어서 사이드이펙트 위험이 있다. 충돌 나는 Pod만 지정하는 게 좋다.
- Google Cloud Console에서 OAuth 클라이언트를 만들 때 Firebase 프로젝트와 같은 프로젝트 번호인지 확인해야 한다. 다른 프로젝트에 만들면 토큰 검증에서 실패한다.
- `GoogleService-Info.plist`의 `CLIENT_ID`와 `Info.plist`의 URL Scheme은 쌍으로 설정해야 한다. 하나라도 빠지면 iOS에서 Google 로그인이 동작하지 않는다.
