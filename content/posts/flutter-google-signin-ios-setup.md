---
title: "Flutter Google Sign-In iOS 설정: GoogleService-Info.plist CLIENT_ID 누락 문제"
date: 2026-02-24
draft: false
tags: ["Flutter", "iOS", "Google Sign-In", "Firebase", "OAuth"]
description: "google_sign_in 패키지를 iOS에 연동할 때 GoogleService-Info.plist에 CLIENT_ID가 없으면 로그인이 동작하지 않는다. 설정 방법을 정리한다."
---

Flutter 앱에서 `google_sign_in` 패키지로 Google 로그인을 구현했는데 iOS에서만 동작하지 않는 경우, `GoogleService-Info.plist`에 `CLIENT_ID`가 없는 게 원인인 경우가 많다.

---

## 문제

Android에서는 Google 로그인이 잘 되는데 iOS에서는 로그인 창이 뜨지 않거나 에러가 발생한다.

Firebase 콘솔에서 iOS 앱을 등록하고 `GoogleService-Info.plist`를 다운로드해서 프로젝트에 추가했지만, 기본 다운로드 파일에는 `CLIENT_ID`가 포함되지 않는 경우가 있다.

---

## GoogleService-Info.plist에 CLIENT_ID 추가

### 1. iOS OAuth 클라이언트 확인

Google Cloud Console → **API 및 서비스 → 사용자 인증 정보**로 이동한다.

Firebase 프로젝트를 생성하면 자동으로 iOS용 OAuth 클라이언트가 생성되어 있다. 클라이언트 ID 형식은 아래와 같다.

```
{프로젝트번호}-{해시값}.apps.googleusercontent.com
```

### 2. plist에 두 가지 키 추가

`ios/Runner/GoogleService-Info.plist` 파일에 아래 두 키를 추가한다.

```xml
<key>CLIENT_ID</key>
<string>{프로젝트번호}-{해시값}.apps.googleusercontent.com</string>

<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{프로젝트번호}-{해시값}</string>
```

`REVERSED_CLIENT_ID`는 CLIENT_ID를 뒤집은 형태다. 점(`.`)으로 구분된 각 세그먼트를 역순으로 나열하면 된다.

예시:
```
CLIENT_ID:          1234567890-abcdef.apps.googleusercontent.com
REVERSED_CLIENT_ID: com.googleusercontent.apps.1234567890-abcdef
```

---

## Info.plist에 URL Scheme 등록

`ios/Runner/Info.plist`에 URL Scheme을 추가해야 구글 로그인 후 앱으로 다시 돌아올 수 있다.

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.{프로젝트번호}-{해시값}</string>
        </array>
    </dict>
</array>
```

여기서 등록하는 URL Scheme 값이 `REVERSED_CLIENT_ID`와 동일해야 한다.

---

## google_sign_in 패키지 동작 방식

`google_sign_in` iOS 구현체는 앱 시작 시 `GoogleService-Info.plist`를 읽어서 자동으로 클라이언트 ID를 설정한다. 별도의 코드에서 clientId를 넘기지 않아도 plist에 있으면 자동 적용된다.

```dart
// 코드에서 별도 설정 없이도 plist를 자동으로 읽는다
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: ['email', 'profile'],
);
```

반면 Android는 `google-services.json`에서 `client_id`를 읽는다.

---

## Firebase iOS 앱 등록 시 CLIENT_ID가 없는 경우

Firebase 콘솔에서 iOS 앱을 추가하고 `GoogleService-Info.plist`를 다운로드할 때 `CLIENT_ID` 키가 없는 경우가 있다. 이는 Google Cloud Console에서 iOS용 OAuth 클라이언트가 아직 생성되지 않았기 때문이다.

해결 방법:

1. Google Cloud Console → **사용자 인증 정보 → + 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
2. 애플리케이션 유형: **iOS**
3. 번들 ID 입력 후 생성
4. 생성된 클라이언트 ID를 plist에 수동으로 추가

또는 Firebase 콘솔 → 프로젝트 설정 → 내 앱 → `GoogleService-Info.plist` 다시 다운로드하면 자동으로 포함되어 있을 수 있다.

---

## 체크리스트

- [ ] `GoogleService-Info.plist`에 `CLIENT_ID` 키 존재 여부 확인
- [ ] `GoogleService-Info.plist`에 `REVERSED_CLIENT_ID` 키 존재 여부 확인
- [ ] `Info.plist`의 `CFBundleURLSchemes`에 `REVERSED_CLIENT_ID` 값 등록 여부 확인
- [ ] Xcode에서 Runner 타겟의 URL Types에도 동일한 scheme 등록 여부 확인

iOS Google Sign-In 문제의 대부분은 이 네 가지 중 하나가 빠진 경우다.
