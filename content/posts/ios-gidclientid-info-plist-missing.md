---
title: "Flutter iOS Google Sign-In: GIDClientID가 Info.plist에 없을 때"
date: 2025-08-23
draft: true
tags: ["Flutter", "iOS", "Google Sign-In", "OAuth", "Info.plist"]
description: "GoogleService-Info.plist 없이 직접 Google OAuth를 연동할 때 GIDClientID를 Info.plist에 별도로 추가해야 한다. 누락 시 'No active configuration' 에러가 발생한다."
cover:
  image: "/images/og/ios-gidclientid-info-plist-missing.png"
  alt: "Ios Gidclientid Info Plist Missing"
  hidden: true
---

Flutter iOS 앱에서 Google Sign-In을 구현할 때 Firebase를 쓰지 않고 Google Cloud Console에서 직접 OAuth 클라이언트 ID를 발급받는 경우가 있다. 이때 `GIDClientID`를 `Info.plist`에 명시적으로 추가하지 않으면 런타임에 에러가 발생한다.

Firebase 프로젝트를 쓰는 경우 `GoogleService-Info.plist`가 이 역할을 자동으로 대신해주기 때문에 의식하지 못하고 지나치기 쉬운 설정이다. 이 글에서는 에러 원인과 해결 방법을 정리한다.

---

## 에러 메시지

```
PlatformException(google_sign_in, No active configuration.
Make sure GIDClientID is set in Info.plist., null, null)
```

---

## 원인

`google_sign_in` iOS SDK는 초기화 시 `Info.plist`에서 `GIDClientID` 키를 읽는다.

Firebase를 쓰는 경우 `GoogleService-Info.plist`를 프로젝트에 추가하면 SDK가 자동으로 해당 파일을 읽어서 처리해준다. 하지만 Firebase 없이 직접 OAuth를 쓰는 경우에는 이 파일이 없으므로 `Info.plist`에 직접 키를 추가해야 한다.

`Info.plist`에 URL Scheme(역방향 클라이언트 ID)만 추가하고 `GIDClientID`를 빠뜨리는 경우가 흔하다.

---

## 확인 방법

`Info.plist`를 열어서 두 가지가 모두 있는지 확인한다.

```xml
<!-- URL Scheme (역방향 클라이언트 ID) -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.{프로젝트번호}-{해시}</string>
    </array>
  </dict>
</array>

<!-- GIDClientID (정방향 클라이언트 ID) -->
<key>GIDClientID</key>
<string>{프로젝트번호}-{해시}.apps.googleusercontent.com</string>
```

URL Scheme과 `GIDClientID`는 같은 OAuth 클라이언트 ID의 앞뒤가 뒤집힌 형태다.

- URL Scheme: `com.googleusercontent.apps.{프로젝트번호}-{해시}`
- GIDClientID: `{프로젝트번호}-{해시}.apps.googleusercontent.com`

---

## 클라이언트 ID 확인 위치

**Google Cloud Console → API 및 서비스 → 사용자 인증 정보**

iOS 앱으로 등록된 OAuth 클라이언트 ID를 찾는다. 클라이언트 ID 형식이 `{숫자}-{영문해시}.apps.googleusercontent.com`이면 맞다.

---

## 수정

`Info.plist`에 `GIDClientID` 키를 추가한다.

```xml
<key>GIDClientID</key>
<string>123456789000-abcdefghijklmnop.apps.googleusercontent.com</string>
```

추가 후 앱을 재빌드하면 `PlatformException: No active configuration` 에러가 사라진다.

---

## 자주 하는 실수: URL Scheme만 추가하고 GIDClientID 누락

Google Sign-In iOS 설정 가이드를 따라 하다 보면 URL Scheme 추가에만 집중하게 된다. 역방향 클라이언트 ID를 URL Scheme에 추가하는 작업이 눈에 잘 띄는 반면, `GIDClientID` 추가는 별도 항목으로 설명되지 않는 경우가 많다.

결과적으로 URL Scheme은 있는데 `GIDClientID`가 없는 상태가 되고, 빌드는 되지만 실행 시 에러가 발생한다.

---

## Dart 코드 초기화 방식 (v7.x 이상)

`google_sign_in` 패키지 v7.x부터는 코드에서 클라이언트 ID를 직접 넘길 수도 있다.

```dart
// Info.plist 대신 코드에서 직접 설정하는 방법
final GoogleSignIn _googleSignIn = GoogleSignIn(
  clientId: '123456789000-abcdefghijklmnop.apps.googleusercontent.com',
  scopes: ['email'],
);
```

하지만 이 방법은 클라이언트 ID가 소스코드에 노출되므로, `Info.plist`에 설정하는 방법이 더 일반적이다.

---

## Firebase 사용 여부에 따른 설정 비교

| 방식 | 필요한 설정 |
|------|------------|
| Firebase 사용 | `GoogleService-Info.plist`만 프로젝트에 추가 |
| Firebase 미사용 | `Info.plist`에 `GIDClientID` + `CFBundleURLSchemes` 직접 추가 |

Firebase를 쓰는 프로젝트에서 코드를 복사해온 경우, Firebase 없는 환경에서는 위 설정이 필요하다는 점을 인지하지 못하고 지나치기 쉽다.

---

## 참고

- `google_sign_in` 패키지 v7.x부터는 `GoogleSignIn.instance`를 사용하는 방식으로 변경됐다.
- Firebase를 쓰는 경우에는 `GoogleService-Info.plist`만 프로젝트에 포함하면 별도 설정 불필요.
- Firebase 없이 직접 연동하는 경우에만 위 설정이 필요하다.
- Google Cloud Console에서 iOS 타입 OAuth 클라이언트 ID를 별도로 생성해야 한다 (Android, 웹 타입과 별개).
