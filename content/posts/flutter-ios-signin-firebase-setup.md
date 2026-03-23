---
title: "TestFlight 빌드에서 Google/Apple 로그인 둘 다 실패하는 이유"
date: 2025-08-03
draft: true
tags: ["Flutter", "iOS", "Firebase", "Google Sign-In", "Sign In with Apple", "TestFlight"]
description: "TestFlight 빌드에서 Google/Apple 로그인이 모두 실패한 원인은 GoogleService-Info.plist에 CLIENT_ID가 없었던 것과 Firebase Apple provider 미설정이었다."
cover:
  image: "/images/og/flutter-ios-signin-firebase-setup.png"
  alt: "Flutter Ios Signin Firebase Setup"
  hidden: true
---

TestFlight 빌드에서 Google 로그인, Apple 로그인 둘 다 실패했다. 시뮬레이터에서는 잘 됐는데 TestFlight에서만 터지는 케이스다. 에러 메시지도 명확하지 않고, 인증 흐름이 중간에 그냥 멈춰버리는 형태라 원인을 찾기가 쉽지 않다.

원인을 두 가지로 정리하기 전에, 왜 시뮬레이터에서는 되고 TestFlight에서만 안 되는지 먼저 짚고 넘어가는 게 이해에 도움이 된다.

---

## 왜 시뮬레이터는 통과하고 TestFlight에서 터지는가

iOS 시뮬레이터는 URL Scheme 처리를 실제 기기와 다르게 처리한다. Google Sign-In은 OAuth 인증이 끝나면 커스텀 URL Scheme(`REVERSED_CLIENT_ID`)을 통해 앱으로 제어권을 돌려준다. 시뮬레이터에서는 이 리다이렉트 처리가 느슨해서, Scheme이 정확히 매칭되지 않아도 `SFSafariViewController` 세션이 어찌저찌 마무리되거나, 웹 기반 폴백 경로로 빠지는 경우가 있다.

Firebase 토큰 검증도 마찬가지다. 디버그 빌드에서는 SDK가 서버 측 설정을 완전히 검증하지 않고 credential을 수락하는 경우가 있다.

TestFlight 빌드는 `Release` 모드로 컴파일된다. URL Scheme 처리가 엄격해지고, Firebase는 서버 측 설정과 credential을 완전히 대조한다. 시뮬레이터가 조용히 넘어갔던 모든 설정 빈틈이 여기서 한꺼번에 터진다.

---

## 원인 1: GoogleService-Info.plist에 CLIENT_ID 누락

Firebase Console에서 iOS 앱을 처음 등록할 때 `GoogleService-Info.plist`를 다운받으면 기본적으로 `CLIENT_ID`와 `REVERSED_CLIENT_ID`가 포함되어 있다. 그런데 **Google Sign-In을 Firebase Authentication에서 활성화하기 전에** 다운받으면 이 키들이 빠진 채로 생성된다.

많은 개발자가 빠지는 함정이 이거다. 프로젝트 초반에 Firebase 세팅하면서 plist를 받아 Xcode에 추가하고 커밋한다. 몇 주 후에 Google 로그인 기능을 추가하면서 Firebase Console에서 활성화하고, 시뮬레이터에서 잘 되니까 그냥 넘어간다. 그런데 디스크에 있는 plist는 여전히 `CLIENT_ID` 없는 옛날 버전이다.

확인 방법:

```bash
grep -A1 "CLIENT_ID\|REVERSED_CLIENT_ID" ios/Runner/GoogleService-Info.plist
```

아무것도 안 나오면 키가 없는 것이다. 파일을 직접 열어보면 제대로 설정된 plist에는 이런 항목이 있어야 한다:

```xml
<key>CLIENT_ID</key>
<string>XXXXXXXX-xxxx.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.XXXXXXXX-xxxx</string>
```

이 항목들이 없으면 실제 기기에서의 Google Sign-In 흐름은 근본부터 깨져 있는 거다.

### 왜 문제인가

iOS에서 Google Sign-In은 `SFSafariViewController` 또는 `ASWebAuthenticationSession`을 통해 Google OAuth 동의 화면을 보여준다. 사용자가 인증을 완료하면 Google이 커스텀 URL Scheme으로 앱에 리다이렉트를 보낸다. 이 Scheme이 바로 `REVERSED_CLIENT_ID` 값이고, 앱의 `Info.plist` `CFBundleURLSchemes`에 등록되어 있어야 한다.

이 값이 없으면 Scheme 등록 자체가 불가능하고, OAuth 콜백이 앱으로 돌아오지 못한다. TestFlight 빌드(실제 기기, 릴리스 모드)에서는 Google 로그인 창이 뜨고 사용자가 인증을 마치는데 이후 아무 일도 일어나지 않는다. 콜백도 없고 에러도 없이 그냥 멈춘다.

### 해결

Firebase Console → 프로젝트 설정 → iOS 앱으로 이동한 뒤, Authentication → 로그인 방법으로 가서 Google을 활성화한다. 활성화 후 프로젝트 설정으로 돌아가서 `GoogleService-Info.plist`를 재다운로드해 교체한다. 파일을 Xcode 프로젝트 디렉토리에 복사하는 것만으로는 부족하다 — Xcode에서 Runner 타겟에 실제로 추가되어 있는지 확인해야 한다.

그 다음 `Info.plist`에 URL Scheme 추가:

```xml
<key>CFBundleURLTypes</key>
<array>
    <!-- 기존 Scheme들 -->
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLName</key>
        <string>Google Sign-In</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.XXXXXXXX-xxxx</string>
        </array>
    </dict>
</array>
```

`REVERSED_CLIENT_ID` 값은 새로 받은 `GoogleService-Info.plist`에서 확인하면 된다. `com.googleusercontent.apps.` 접두사를 포함해서 정확히 복사해야 한다. 오타 하나가 OAuth 리다이렉트 매칭을 실패시켜 인증이 끝까지 완료되지 않는다.

XcodeGen을 쓰는 프로젝트라면 `project.yml`에도 URL Scheme을 추가하고 `xcodegen generate`를 다시 돌려야 한다. `Info.plist`를 직접 수정해도 다음 `xcodegen generate` 실행 시 덮어씌워진다.

---

## 원인 2: Firebase Apple Sign-In provider 미설정

`sign_in_with_apple` 패키지와 `Runner.entitlements`만 설정해두면 네이티브 Apple 로그인 UI 자체는 동작한다. 시스템 레벨의 "Apple로 로그인" 시트가 뜨고 사용자가 인증할 수 있다. 그런데 Firebase 앱에서 Apple Sign-In에는 두 단계가 있다:

1. 네이티브 Apple 인증 (OS가 처리) — identity token이 담긴 credential 생성
2. Firebase credential 교환 — 앱이 그 identity token을 Firebase에 넘겨서 Firebase 사용자를 만들거나 로그인

1단계는 Firebase Apple provider 설정이 완전히 망가져 있어도 성공할 수 있다. 2단계는 Firebase의 Apple provider가 없거나 잘못 설정되어 있으면 조용히 실패하거나 generic Firebase 에러를 던진다.

Firebase Console → Authentication → 로그인 방법 → **Apple**에서 설정해야 하는 항목들:

| 항목 | 설명 |
|------|------|
| 서비스 ID | Apple Developer Portal에서 생성한 Services ID |
| Apple 팀 ID | Apple Developer 계정의 Team ID |
| 키 ID | Sign in with Apple 권한이 있는 키의 ID |
| 비공개 키 | 해당 키의 .p8 파일 내용 |

흔히 하는 실수가 두 가지다.

### 실수 1: APNs 키를 그대로 쓰려고 함

매우 흔한 케이스다. 대부분의 Flutter/Firebase 프로젝트에는 이미 APNs 키가 등록되어 있다. Apple Sign-In 설정할 때 이 키를 재사용하고 싶은 게 당연하다 — 이미 secrets 폴더에 있고, FCM용으로 Firebase에도 등록되어 있으니.

문제는 APNs 용도로만 생성한 키는 "Sign in with Apple" 권한이 체크되어 있지 않다는 점이다. Firebase가 Apple identity token을 받아서 이 키로 검증을 시도하면, 키에 해당 권한이 없으니 검증에 실패한다.

해결 방법은 간단하다. Apple Developer Portal → Certificates, Identifiers & Profiles → Keys로 가서 기존 키를 클릭하고, Sign in with Apple을 체크하고 저장한다. 키 파일 자체(.p8 파일)는 변경되지 않는다. 권한은 Apple 서버 측에 저장된다. secrets 폴더의 기존 파일 그대로 사용하면 된다.

권한 추가 후 Firebase Console에서 Apple Sign-In provider에 키 ID와 .p8 내용을 입력한다.

### 실수 2: Services ID 없이 진행

Services ID는 앱의 Bundle ID와 별개의 개체다. Firebase가 Apple 인증 콜백을 처리하기 위한 OAuth 클라이언트 식별자다. 이 단계를 건너뛰면 Firebase가 Apple OAuth 흐름을 자기 쪽에서 완료할 수 없다.

Apple Developer Portal → Certificates, Identifiers & Profiles → Identifiers → `+` 버튼 → "Services IDs" 선택 → `com.yourapp.siwa` 같은 역도메인 형식 식별자로 등록한다(관례상 Bundle ID에 `.siwa`를 붙여서 구별한다).

생성 후 Sign in with Apple Configure에서 반드시:

- **Primary App ID**: 실제 앱의 Bundle ID (예: `com.yourapp.app`)
- **Domains and Subdomains**: `{Firebase 프로젝트 ID}.firebaseapp.com`
- **Return URLs**: `https://{Firebase 프로젝트 ID}.firebaseapp.com/__/auth/handler`

를 등록해야 한다.

Return URL이 핵심이다. Apple이 인증 완료 후 사용자를 보내는 곳이 여기다. Firebase의 `/__/auth/handler`가 토큰을 받아 검증하고 로그인 흐름을 마무리한다. 이 URL이 없거나 오타가 있으면, Apple은 인증은 마치는데 결과를 보낼 유효한 목적지가 없어서 흐름이 끊긴다.

Services ID 설정이 완료되면 Firebase Console의 Apple Sign-In provider "서비스 ID" 항목에 해당 식별자를 입력한다.

---

## 어느 단계에서 실패하는지 모를 때 디버깅하기

TestFlight 빌드에서 Apple Sign-In 실패를 디버깅할 때, 1단계(네이티브 Apple 인증)에서 실패하는지 2단계(Firebase credential 교환)에서 실패하는지 구별이 안 된다면 `signInWithCredential` 호출 주변에 임시 로그를 추가한다:

```dart
try {
  final appleCredential = await SignInWithApple.getAppleIDCredential(
    scopes: [
      AppleIDAuthorizationScopes.email,
      AppleIDAuthorizationScopes.fullName,
    ],
  );

  final oauthCredential = OAuthProvider("apple.com").credential(
    idToken: appleCredential.identityToken,
    rawNonce: rawNonce,
  );

  final userCredential = await FirebaseAuth.instance
      .signInWithCredential(oauthCredential);

  print("Firebase UID: ${userCredential.user?.uid}");
} on FirebaseAuthException catch (e) {
  print("Firebase 에러: ${e.code} — ${e.message}");
} catch (e) {
  print("예상치 못한 에러: $e");
}
```

`FirebaseAuthException`이 `invalid-credential` 또는 `web-context-cancelled` 코드로 발생하면 Firebase provider 설정 문제다. `getAppleIDCredential` 자체가 throw되면 Xcode의 entitlements나 Capabilities 설정 문제다. 이 구별로 원인이 Apple Developer Portal인지, Firebase Console인지, Xcode 프로젝트 설정인지를 좁힐 수 있다.

Google Sign-In 실패의 경우, `GoogleSignIn().signIn()`이 `null`을 반환하는지(사용자 취소 또는 리다이렉트 실패) 아니면 예외를 던지는지(설정 에러)를 확인한다. Google 시트가 닫히자마자 즉시 `null`이 반환되면 URL Scheme 리다이렉트 실패일 가능성이 높다.

---

## 설정 완료 후 체크리스트

```
GoogleService-Info.plist
├── CLIENT_ID 존재 여부 확인
└── REVERSED_CLIENT_ID 존재 여부 확인

Info.plist (XcodeGen 사용 시 project.yml)
└── CFBundleURLSchemes에 REVERSED_CLIENT_ID 값 등록

Firebase Console → Authentication → 로그인 방법
├── Google Sign-In: 활성화
└── Apple Sign-In
    ├── 서비스 ID 입력 (예: com.yourapp.siwa)
    ├── 팀 ID 입력
    ├── 키 ID 입력 (Sign in with Apple 권한 있는 키)
    └── 비공개 키 (.p8 내용) 입력

Apple Developer Portal
├── 해당 키: Sign in with Apple 권한 활성화
└── Services ID
    ├── Primary App ID: 실제 앱 Bundle ID
    ├── Domains: {프로젝트 ID}.firebaseapp.com
    └── Return URLs: https://{프로젝트 ID}.firebaseapp.com/__/auth/handler
```

시뮬레이터에서는 Firebase 토큰 검증이 느슨하게 동작하거나 mock 처리가 돼서 넘어가는 경우가 많아서 배포 빌드에서만 터지는 케이스가 많다. 시뮬레이터는 UI 확인 도구로만 쓰고, 실제 기기 + 디버그 또는 ad-hoc 빌드로 인증 흐름을 검증한 뒤 TestFlight에 올리는 게 가장 안전하다.

---

## Key Takeaways

- **`GoogleService-Info.plist`는 Google Sign-In 활성화 이후에 다운받아야 한다.** 순서가 중요하다 — 파일 내용은 다운로드 시점에 활성화된 provider를 반영한다.
- **`REVERSED_CLIENT_ID`는 `Info.plist`의 URL Scheme으로 반드시 등록해야 한다.** 이 값이 없으면 실제 기기에서 Google OAuth 리다이렉트 콜백이 앱에 도달하지 못한다.
- **Apple Sign-In에는 두 개의 독립적인 레이어가 있다**: OS 레벨 네이티브 인증(entitlements + Apple Developer)과 Firebase credential 교환(Firebase Console 설정). 둘 다 맞아야 한다.
- **APNs 키를 Apple Sign-In에 재사용하는 건 흔한 함정이다.** Apple Developer Portal에서 기존 키에 Sign in with Apple 권한만 추가하면 된다 — 새 키를 만들거나 .p8 파일을 재다운로드할 필요 없다.
- **Services ID 설정, 특히 Return URL**이 가장 많이 건너뛰는 단계다. 이게 없으면 Apple의 OAuth 흐름은 완료되지만 credential을 전달할 유효한 목적지가 없다.
- **시뮬레이터는 인증 흐름의 신뢰할 수 있는 테스트 환경이 아니다.** TestFlight 제출 전에 항상 실제 기기에서 릴리스 또는 ad-hoc 빌드로 인증을 검증해야 한다.
