---
title: "TestFlight 빌드에서 Google/Apple 로그인 둘 다 실패하는 이유"
date: 2026-02-25
draft: false
tags: ["Flutter", "iOS", "Firebase", "Google Sign-In", "Sign In with Apple", "TestFlight"]
description: "TestFlight 빌드에서 Google/Apple 로그인이 모두 실패한 원인은 GoogleService-Info.plist에 CLIENT_ID가 없었던 것과 Firebase Apple provider 미설정이었다."
---

TestFlight 빌드에서 Google 로그인, Apple 로그인 둘 다 실패했다. 시뮬레이터에서는 잘 됐는데 TestFlight에서만 터지는 케이스다.

---

## 원인 1: GoogleService-Info.plist에 CLIENT_ID 누락

Firebase Console에서 iOS 앱을 처음 등록할 때 `GoogleService-Info.plist`를 다운받으면 기본적으로 `CLIENT_ID`와 `REVERSED_CLIENT_ID`가 포함되어 있다. 그런데 **Google Sign-In을 Firebase에서 활성화하기 전에** 다운받으면 이 키들이 빠진 채로 생성된다.

확인 방법:

```bash
grep -A1 "CLIENT_ID\|REVERSED_CLIENT_ID" ios/Runner/GoogleService-Info.plist
```

아무것도 안 나오면 키가 없는 것.

### 왜 문제인가

iOS에서 Google Sign-In은 OAuth 콜백을 받기 위해 앱에 URL Scheme이 등록되어 있어야 한다. 이 URL Scheme이 바로 `REVERSED_CLIENT_ID` 값이다. 값이 없으니 `Info.plist`에 Scheme 등록도 못 하고, 결과적으로 Google 로그인 창에서 인증 후 앱으로 돌아오지 못한다.

### 해결

Firebase Console → 프로젝트 설정 → iOS 앱 → **Authentication → Sign-in method → Google 활성화** 후 `GoogleService-Info.plist`를 재다운로드해서 교체한다.

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

`REVERSED_CLIENT_ID` 값은 새로 받은 `GoogleService-Info.plist`에서 확인하면 된다.

---

## 원인 2: Firebase Apple Sign-In provider 미설정

`sign_in_with_apple` 패키지와 `Runner.entitlements`만 설정해두면 네이티브 Apple 로그인 자체는 동작한다. 그런데 Firebase에 Apple provider가 제대로 등록되어 있지 않으면, Apple에서 받은 credential을 Firebase에 넘기는 단계에서 실패한다.

Firebase Console → Authentication → Sign-in method → **Apple**에서 설정해야 하는 항목들:

| 항목 | 설명 |
|------|------|
| 서비스 ID | Apple Developer에서 생성한 Services ID |
| Apple 팀 ID | Apple Developer 계정의 Team ID |
| 키 ID | Sign in with Apple 권한이 있는 키의 ID |
| 비공개 키 | 해당 키의 .p8 파일 내용 |

여기서 흔히 실수하는 게 두 가지다.

**실수 1: APNs 키를 그대로 쓰려고 함**

Apple Developer Portal에서 키를 만들 때 APNs 용도로만 생성한 경우, Sign in with Apple 권한이 없다. 이 키를 Firebase에 등록하면 토큰 검증에서 실패한다.

기존 키에 Sign in with Apple 권한을 추가할 수 있다. Keys 목록에서 해당 키 클릭 → Sign in with Apple 체크 → Save. 키 파일 자체(p8)는 변경되지 않으므로 기존 파일 그대로 사용하면 된다.

**실수 2: Services ID 없이 진행**

Services ID는 Firebase가 Apple OAuth 콜백을 처리하기 위한 식별자다. Apple Developer Portal → Identifiers → + → Services IDs로 생성한다.

생성 후 반드시 **Sign in with Apple Configure**에서:
- Primary App ID: 실제 앱의 Bundle ID
- Domains: `{프로젝트ID}.firebaseapp.com`
- Return URLs: `https://{프로젝트ID}.firebaseapp.com/__/auth/handler`

를 등록해야 한다. 이 콜백 URL을 빠뜨리면 Apple이 인증 후 어디로 돌아가야 할지 몰라서 실패한다.

---

## 설정 완료 후 체크리스트

```
GoogleService-Info.plist
├── CLIENT_ID 존재 여부 확인
└── REVERSED_CLIENT_ID 존재 여부 확인

Info.plist
└── CFBundleURLSchemes에 REVERSED_CLIENT_ID 값 등록

Firebase Console
├── Google Sign-In: 활성화
└── Apple Sign-In
    ├── 서비스 ID 입력
    ├── 팀 ID 입력
    ├── 키 ID 입력 (Sign in with Apple 권한 있는 키)
    └── 비공개 키 (.p8 내용) 입력

Apple Developer Portal
├── 해당 키: Sign in with Apple 권한 활성화
└── Services ID: 콜백 URL 등록
```

시뮬레이터에서는 Firebase 토큰 검증이 느슨하게 동작하거나 mock 처리가 돼서 넘어가는 경우가 있어서 배포 빌드에서만 터지는 케이스가 많다. TestFlight 올리기 전에 위 체크리스트 한 번씩 확인하는 게 낫다.
