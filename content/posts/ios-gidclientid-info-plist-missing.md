---
title: "Flutter iOS Google Sign-In: GIDClientID가 Info.plist에 없을 때"
date: 2026-02-25
draft: false
tags: ["Flutter", "iOS", "Google Sign-In", "OAuth", "Info.plist"]
description: "GoogleService-Info.plist 없이 직접 Google OAuth를 연동할 때 GIDClientID를 Info.plist에 별도로 추가해야 한다. 누락 시 'No active configuration' 에러가 발생한다."
---

Flutter iOS 앱에서 Google Sign-In을 구현할 때 Firebase를 쓰지 않고 Google Cloud Console에서 직접 OAuth 클라이언트 ID를 발급받는 경우가 있다. 이때 `GIDClientID`를 `Info.plist`에 명시적으로 추가하지 않으면 런타임에 에러가 발생한다.

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

## 참고

- `google_sign_in` 패키지 v7.x부터는 `GoogleSignIn.instance`를 사용하는 방식으로 변경됐다.
- Firebase를 쓰는 경우에는 `GoogleService-Info.plist`만 프로젝트에 포함하면 별도 설정 불필요.
- Firebase 없이 직접 연동하는 경우에만 위 설정이 필요하다.
