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

Firebase 프로젝트를 쓰는 경우 `GoogleService-Info.plist`가 이 역할을 자동으로 대신해주기 때문에 의식하지 못하고 지나치기 쉬운 설정이다. 이 글에서는 에러 원인과 해결 방법, 그리고 자주 발생하는 실수 패턴까지 정리한다.

---

## 에러 메시지

```
PlatformException(google_sign_in, No active configuration.
Make sure GIDClientID is set in Info.plist., null, null)
```

이 에러는 앱 실행 후 Google Sign-In 버튼을 처음 누르는 순간 발생한다. 빌드 단계에서는 아무런 경고도 없기 때문에 처음 보면 당황스럽다. 에러 메시지 자체는 명확하지만, Firebase를 쓰는 환경에서만 개발해왔다면 `GIDClientID`를 직접 설정해야 한다는 사실을 인지하지 못한 채 지나치기 쉽다.

---

## 배경: Firebase가 하는 일

`google_sign_in` Flutter 패키지는 내부적으로 Google Sign-In iOS SDK를 사용한다. 이 SDK는 초기화 시 설정 정보를 읽는데, 읽는 방법이 두 가지다.

1. **Firebase 사용 시**: 프로젝트에 포함된 `GoogleService-Info.plist`를 자동으로 파싱해서 `GIDClientID`를 포함한 여러 설정값을 추출한다.
2. **Firebase 미사용 시**: `Info.plist`에서 직접 `GIDClientID` 키를 읽는다.

Firebase를 쓰는 프로젝트에서는 `GoogleService-Info.plist` 하나만 추가하면 모든 설정이 자동으로 완성된다. 이 편리함에 익숙해지면, Firebase 없이 작업할 때 무엇을 직접 설정해야 하는지 파악하기 어려워진다.

---

## 원인

`google_sign_in` iOS SDK는 초기화 시 `Info.plist`에서 `GIDClientID` 키를 읽는다.

Firebase를 쓰는 경우 `GoogleService-Info.plist`를 프로젝트에 추가하면 SDK가 자동으로 해당 파일을 읽어서 처리해준다. 하지만 Firebase 없이 직접 OAuth를 쓰는 경우에는 이 파일이 없으므로 `Info.plist`에 직접 키를 추가해야 한다.

`Info.plist`에 URL Scheme(역방향 클라이언트 ID)만 추가하고 `GIDClientID`를 빠뜨리는 경우가 흔하다. URL Scheme은 Google Sign-In 완료 후 앱으로 돌아오기 위한 콜백 처리에 필요하고, `GIDClientID`는 SDK가 어떤 OAuth 앱으로 인증할지 식별하는 데 필요하다. 이 두 가지는 역할이 다르지만, 값은 같은 클라이언트 ID의 앞뒤가 뒤집힌 형태다.

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

예를 들어 클라이언트 ID가 `123456789000-abcdefghijklmnop.apps.googleusercontent.com`이라면:

- URL Scheme에 등록할 값: `com.googleusercontent.apps.123456789000-abcdefghijklmnop`
- `GIDClientID`에 등록할 값: `123456789000-abcdefghijklmnop.apps.googleusercontent.com`

둘 다 같은 OAuth 클라이언트를 가리키지만 형식이 다르다. URL Scheme은 iOS가 딥링크 라우팅에 쓰는 역방향 도메인 표기법이고, `GIDClientID`는 Google API 호출 시 사용하는 정방향 식별자다.

---

## 클라이언트 ID 확인 위치

**Google Cloud Console → API 및 서비스 → 사용자 인증 정보**

iOS 앱으로 등록된 OAuth 클라이언트 ID를 찾는다. 클라이언트 ID 형식이 `{숫자}-{영문해시}.apps.googleusercontent.com`이면 맞다.

몇 가지 주의할 점이 있다.

- **iOS 타입 클라이언트 ID를 써야 한다.** Android, 웹 타입과는 별개다. Google Cloud Console에서 새로운 OAuth 클라이언트 ID를 만들 때 애플리케이션 유형을 반드시 "iOS"로 선택해야 한다.
- **번들 ID가 일치해야 한다.** iOS 타입 클라이언트 ID를 만들 때 입력한 번들 ID와 Xcode 프로젝트의 번들 ID가 정확히 일치해야 인증이 성공한다.
- **Google Cloud 프로젝트와 연동 여부를 확인한다.** Firebase를 쓰지 않더라도 Google Cloud 프로젝트 안에서 OAuth 클라이언트 ID를 관리한다. 여러 프로젝트를 운영 중이라면 올바른 프로젝트를 선택했는지 확인한다.

---

## 수정

`Info.plist`에 `GIDClientID` 키를 추가한다.

```xml
<key>GIDClientID</key>
<string>123456789000-abcdefghijklmnop.apps.googleusercontent.com</string>
```

추가 후 앱을 재빌드하면 `PlatformException: No active configuration` 에러가 사라진다.

Flutter 프로젝트에서 `Info.plist`의 위치는 `ios/Runner/Info.plist`다. Xcode에서 직접 편집하거나 텍스트 에디터로 XML을 수정할 수 있다. Xcode에서 편집할 경우 Property List 에디터에서 `+` 버튼으로 새 키를 추가하고, 타입은 `String`, 값은 클라이언트 ID를 입력한다.

---

## 자주 하는 실수: URL Scheme만 추가하고 GIDClientID 누락

Google Sign-In iOS 설정 가이드를 따라 하다 보면 URL Scheme 추가에만 집중하게 된다. 역방향 클라이언트 ID를 URL Scheme에 추가하는 작업이 눈에 잘 띄는 반면, `GIDClientID` 추가는 별도 항목으로 설명되지 않는 경우가 많다.

결과적으로 URL Scheme은 있는데 `GIDClientID`가 없는 상태가 되고, 빌드는 되지만 실행 시 에러가 발생한다.

이 실수가 특히 잦은 이유가 있다. Google의 공식 Flutter 통합 가이드는 Firebase를 전제로 작성된 경우가 많다. `google_sign_in` 패키지의 README도 Firebase 연동을 기본 경로로 안내한다. Firebase 없이 직접 연동하는 방법은 별도 섹션이나 주석 형태로 언급되어 있어서 놓치기 쉽다.

또 다른 패턴은 Firebase를 쓰던 프로젝트에서 코드를 복사해오는 경우다. Flutter 코드 자체는 거의 동일하게 동작하지만, `GoogleService-Info.plist`가 없는 환경에서는 iOS 레이어의 초기화가 실패한다. 이 경우 "왜 똑같은 코드인데 여기서는 안 되지?" 하는 혼란이 생긴다.

---

## 디버깅 체크리스트

에러가 발생했을 때 확인할 순서다.

1. `ios/Runner/Info.plist`에 `GIDClientID` 키가 있는지 확인
2. `GIDClientID` 값이 정방향 형식(`{숫자}-{해시}.apps.googleusercontent.com`)인지 확인 (역방향 형식을 잘못 넣는 경우가 있다)
3. `CFBundleURLSchemes`에 역방향 클라이언트 ID(`com.googleusercontent.apps.{숫자}-{해시}`)가 있는지 확인
4. Google Cloud Console에서 iOS 타입 OAuth 클라이언트 ID가 등록되어 있는지 확인
5. 클라이언트 ID 생성 시 입력한 번들 ID와 앱의 번들 ID가 일치하는지 확인
6. `GoogleService-Info.plist`가 없는 상태인지 확인 (파일이 있으면 SDK가 해당 파일을 우선적으로 읽는다)

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

v7.x에서는 API 구조도 변경됐다. 기존의 인스턴스 생성 방식 외에 `GoogleSignIn.instance`를 사용하는 싱글턴 패턴도 지원한다. 하지만 `clientId`를 코드에서 주입하는 방식 자체는 v7.x에서도 동작한다. 단, `Info.plist` 방식이 설정과 코드를 분리한다는 점에서 여전히 권장된다.

소스코드에 클라이언트 ID를 넣는 것이 보안 위협이 되냐는 질문을 받는다. OAuth 클라이언트 ID는 공개 식별자로, 그 자체가 비밀은 아니다. 하지만 `Info.plist`에 두면 환경별로 다른 값을 쓰거나(개발/스테이징/프로덕션), 릴리즈 빌드에서 다른 클라이언트 ID를 쓰는 등의 유연성이 생긴다.

---

## Firebase 사용 여부에 따른 설정 비교

| 방식 | 필요한 설정 |
|------|------------|
| Firebase 사용 | `GoogleService-Info.plist`만 프로젝트에 추가 |
| Firebase 미사용 | `Info.plist`에 `GIDClientID` + `CFBundleURLSchemes` 직접 추가 |

Firebase를 쓰는 프로젝트에서 코드를 복사해온 경우, Firebase 없는 환경에서는 위 설정이 필요하다는 점을 인지하지 못하고 지나치기 쉽다.

두 방식 모두 내부적으로는 동일한 Google Sign-In iOS SDK를 사용한다. 차이는 SDK가 설정값을 어디서 읽어오느냐다. Firebase 방식은 `GoogleService-Info.plist`가 자동 소스 역할을 하고, Firebase 없는 방식은 `Info.plist`가 명시적 소스 역할을 한다.

Firebase를 나중에 추가하거나 제거하는 경우에도 이 차이를 인지하고 있어야 한다. Firebase를 제거하면서 `GoogleService-Info.plist`를 삭제했는데 `Info.plist`에 `GIDClientID`를 추가하지 않으면 기존에 잘 되던 Google Sign-In이 갑자기 에러를 낸다.

---

## Key Takeaways

- Firebase 없이 Google Sign-In을 쓰면 `GIDClientID`를 `Info.plist`에 직접 추가해야 한다
- URL Scheme(역방향 클라이언트 ID)과 `GIDClientID`(정방향 클라이언트 ID)는 둘 다 필요하다. 역할이 다르다
- Google Cloud Console에서 반드시 iOS 타입 OAuth 클라이언트 ID를 별도로 생성해야 한다
- 에러 메시지 `No active configuration`은 항상 `GIDClientID` 누락을 먼저 의심한다
- Firebase를 제거하면서 `GoogleService-Info.plist`를 삭제했다면, `Info.plist`에 `GIDClientID`를 직접 추가해야 Google Sign-In이 계속 동작한다

---

## 참고

- `google_sign_in` 패키지 v7.x부터는 `GoogleSignIn.instance`를 사용하는 방식으로 변경됐다.
- Firebase를 쓰는 경우에는 `GoogleService-Info.plist`만 프로젝트에 포함하면 별도 설정 불필요.
- Firebase 없이 직접 연동하는 경우에만 위 설정이 필요하다.
- Google Cloud Console에서 iOS 타입 OAuth 클라이언트 ID를 별도로 생성해야 한다 (Android, 웹 타입과 별개).
