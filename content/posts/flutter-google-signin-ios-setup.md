---
title: "Flutter Google Sign-In iOS 설정: GoogleService-Info.plist CLIENT_ID 누락 문제"
date: 2025-06-04
draft: true
tags: ["Flutter", "iOS", "Google Sign-In", "Firebase", "OAuth"]
description: "google_sign_in 패키지를 iOS에 연동할 때 GoogleService-Info.plist에 CLIENT_ID가 없으면 로그인이 동작하지 않는다. 설정 방법을 정리한다."
cover:
  image: "/images/og/flutter-google-signin-ios-setup.png"
  alt: "Flutter Google Signin Ios Setup"
  hidden: true
---

Flutter 앱에서 `google_sign_in` 패키지로 Google 로그인을 구현했는데 iOS에서만 동작하지 않는 경우, `GoogleService-Info.plist`에 `CLIENT_ID`가 없는 게 원인인 경우가 많다. Android는 정상 동작하는데 iOS만 안 된다면 거의 이 문제다. Android와 iOS가 서로 다른 방식으로 인증 정보를 읽기 때문에 Android 쪽이 잘 되더라도 iOS 쪽 OAuth 클라이언트가 누락된 채로 넘어가는 경우가 흔하다.

이 글에서는 근본 원인, 전체 설정 절차, 디버깅 방법, 재발 방지 팁을 정리한다.

---

## 문제

Android에서는 Google 로그인이 잘 되는데 iOS에서는 로그인 창이 뜨지 않거나 에러가 발생한다. 에러가 명시적으로 나오는 경우도 있다.

```
PlatformException(sign_in_failed, com.google.GIDSignIn, Error Domain=com.google.GIDSignIn Code=-4 ...)
```

에러 없이 조용히 실패하는 경우도 있다. `signIn()`이 null을 반환하거나 sign-in 시트 자체가 뜨지 않는 것이다.

Firebase 콘솔에서 iOS 앱을 등록하고 `GoogleService-Info.plist`를 다운로드해서 프로젝트에 추가했지만, 기본 다운로드 파일에는 `CLIENT_ID`가 포함되지 않는 경우가 있다. Firebase Console UI에서는 이 사실을 별도로 경고해주지 않기 때문에 놓치기 쉽다.

### 근본 원인

`google_sign_in` iOS 네이티브 SDK는 sign-in 플로우를 시작하기 위해 OAuth 2.0 클라이언트 ID가 필요하다. 이 값이 없으면 GIDSignIn 프레임워크는 인증 URL을 생성하지 못하고 전체 플로우가 조용히 실패하거나 모호한 에러를 던진다.

Firebase와 Google Cloud Console은 연관되어 있지만 별개의 시스템이다. Firebase 프로젝트를 생성하면 아래에 Google Cloud 프로젝트가 만들어진다. 하지만 Google Cloud Console의 **iOS OAuth 클라이언트**는 특정 조건에서만 자동으로 생성된다. 예를 들어 Firebase Authentication에서 Google Sign-In을 활성화할 때 생성된다. 이 단계를 건너뛰거나 나중에 활성화하면, 그 전에 다운로드한 plist에는 `CLIENT_ID`가 없다.

반면 Android는 SHA-1 지문 기반 인증을 `google-services.json`을 통해 처리하기 때문에 다른 플로우로 동작한다. 이것이 Android는 되고 iOS는 안 되는 이유다.

---

## 사전 준비

시작 전 확인 사항:

- `pubspec.yaml`에 `google_sign_in`이 추가된 Flutter 프로젝트
- Firebase 프로젝트에 iOS 앱 등록 완료 (번들 ID가 Flutter 프로젝트와 정확히 일치해야 함)
- 동일 프로젝트의 Firebase Console과 Google Cloud Console 접근 권한
- Xcode 설치 (URL Types 설정 확인에 필요)

---

## 1단계: Google Cloud Console에서 iOS OAuth 클라이언트 확인

[Google Cloud Console](https://console.cloud.google.com)에서 Firebase 프로젝트를 선택하고 **API 및 서비스 → 사용자 인증 정보**로 이동한다.

유형이 **iOS**인 OAuth 2.0 클라이언트 항목이 있는지 확인한다. Firebase 프로젝트 생성 시 자동으로 만들어지는 경우도 있다. 클라이언트 ID 형식은 아래와 같다.

```
{프로젝트번호}-{해시값}.apps.googleusercontent.com
```

iOS OAuth 클라이언트가 없다면 직접 생성해야 한다 (아래 "CLIENT_ID가 없는 경우" 섹션 참고).

---

## 2단계: GoogleService-Info.plist에 두 가지 키 추가

`ios/Runner/GoogleService-Info.plist` 파일을 텍스트 에디터나 Xcode로 열어서 `CLIENT_ID`와 `REVERSED_CLIENT_ID` 키가 있는지 확인한다. 없으면 아래를 추가한다.

```xml
<key>CLIENT_ID</key>
<string>{프로젝트번호}-{해시값}.apps.googleusercontent.com</string>

<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{프로젝트번호}-{해시값}</string>
```

`REVERSED_CLIENT_ID`는 CLIENT_ID를 점(`.`)으로 구분된 세그먼트 단위로 역순 나열한 값이다. 오타가 아니다. iOS가 Safari 또는 ASWebAuthenticationSession에서 OAuth 플로우를 마친 후 앱으로 다시 리다이렉트하는 커스텀 URL scheme이 된다.

예시:
```
CLIENT_ID:          1234567890-abcdef.apps.googleusercontent.com
REVERSED_CLIENT_ID: com.googleusercontent.apps.1234567890-abcdef
```

---

## 3단계: Info.plist에 URL Scheme 등록

`ios/Runner/Info.plist`에 URL Scheme을 추가해야 OAuth 플로우가 브라우저에서 완료된 후 iOS가 앱으로 돌아올 수 있다.

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

`CFBundleURLSchemes` 안의 값이 `GoogleService-Info.plist`의 `REVERSED_CLIENT_ID`와 정확히 같아야 한다. 한 글자라도 다르면 OAuth 리다이렉트가 조용히 실패한다. 브라우저에서 플로우는 완료되지만 iOS가 앱으로 돌아오지 못한다.

---

## 4단계: Xcode에서 확인

Xcode에서 프로젝트를 열고 **Runner** 타겟을 선택한 후 **Info** 탭으로 이동해 **URL Types** 섹션을 확인한다. `REVERSED_CLIENT_ID` 값이 URL Schemes에 등록되어 있어야 한다.

`Info.plist`를 직접 편집했는데도 Xcode에 반영이 안 된다면 Xcode에서 직접 추가한다.

1. URL Types 아래 `+` 버튼 클릭
2. Identifier는 비워두거나 `com.google`로 설정
3. Role을 **Editor**로 설정
4. URL Schemes에 `REVERSED_CLIENT_ID` 값 입력

Xcode 레벨에서의 이 등록이 권위 있는 소스다. 저장하면 `Info.plist`에 반영된다.

---

## google_sign_in 패키지가 iOS에서 동작하는 방식

`google_sign_in` iOS 구현체는 앱 시작 시 `GIDSignIn` 네이티브 프레임워크를 통해 `GoogleService-Info.plist`를 읽고 클라이언트 ID를 자동으로 설정한다. Dart 코드에서 `clientId`를 넘기지 않아도 plist에 있으면 자동 적용된다.

```dart
// plist가 올바르게 설정되어 있으면 Dart 코드에서 별도 설정 불필요
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: ['email', 'profile'],
);
```

다만 개발/스테이징/프로덕션 등 여러 Firebase 프로젝트를 사용하는 환경이라면 Dart 코드에서 `clientId`를 직접 지정하는 방법도 있다.

```dart
final GoogleSignIn _googleSignIn = GoogleSignIn(
  clientId: 'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com',
  scopes: ['email', 'profile'],
);
```

Android는 `google-services.json`에서 SHA-1 지문 매칭으로 `client_id`를 읽기 때문에 plist 변경 없이도 동작한다. 이 차이가 Android는 되고 iOS는 안 되는 상황을 만든다.

---

## Firebase iOS 앱 등록 시 CLIENT_ID가 없는 경우

Firebase 콘솔에서 iOS 앱을 추가하고 `GoogleService-Info.plist`를 다운로드할 때 `CLIENT_ID` 키가 없는 경우가 있다. 다음 상황에서 발생한다.

- Google Cloud Console에서 iOS OAuth 클라이언트가 한 번도 생성되지 않은 경우
- Firebase Authentication에서 Google Sign-In을 활성화하기 전에 plist를 다운로드한 경우
- 프로젝트 생성 직후, OAuth 클라이언트가 프로비저닝되기 전에 다운로드한 경우

**방법 A: OAuth 클라이언트 직접 생성**

1. Google Cloud Console → **사용자 인증 정보 → + 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
2. 애플리케이션 유형: **iOS**
3. 번들 ID 입력 후 생성
4. 생성된 클라이언트 ID를 복사해서 plist에 수동으로 추가

**방법 B: Firebase Console에서 plist 재다운로드**

Firebase Authentication에서 Google Sign-In을 활성화한 후, Firebase Console → 프로젝트 설정 → 내 앱 → `GoogleService-Info.plist` 다시 다운로드하면 `CLIENT_ID`가 자동으로 포함된다.

기존 파일과 교체하기 전에 항상 비교해서 커스텀 키를 덮어쓰지 않도록 주의한다.

---

## 디버깅 단계

위 설정을 모두 했는데도 Google Sign-In이 안 된다면 아래 방법으로 디버깅한다.

**1. plist가 Xcode 타겟에 추가되어 있는지 확인**

Xcode의 파일 내비게이터에서 `GoogleService-Info.plist`를 선택한다. 오른쪽 File Inspector에서 **Target Membership**에 Runner 타겟이 체크되어 있는지 확인한다. 파일이 프로젝트 폴더에 있더라도 타겟에 추가되지 않으면 앱에 번들되지 않는다.

**2. 런타임에 CLIENT_ID 출력**

```dart
import 'package:flutter/services.dart';

final plist = await rootBundle.loadString('ios/Runner/GoogleService-Info.plist');
print(plist); // CLIENT_ID가 있는지 확인
```

이 방법은 소스 파일을 읽는 것이므로 번들된 버전과 다를 수 있다. 번들된 버전 확인은 Xcode 빌드 결과물에서 확인한다.

**3. 네이티브 로그 확인**

`flutter run` 대신 Xcode에서 직접 빌드하고 실행하면 GIDSignIn 초기화 에러를 포함한 전체 네이티브 콘솔 출력을 볼 수 있다. Xcode 없이는 보이지 않는 중요한 에러 메시지가 있는 경우가 많다.

**4. 번들 ID 일치 여부 확인**

Xcode 프로젝트의 `PRODUCT_BUNDLE_IDENTIFIER`가 Google Cloud Console에서 OAuth 클라이언트를 생성할 때 입력한 번들 ID와 정확히 일치해야 한다. 대소문자 하나만 달라도 인증이 실패한다.

**5. 클린 빌드**

plist 파일 수정 후에는 반드시 Xcode에서 클린 빌드를 한다. **Product → Clean Build Folder** (Shift+Cmd+K) 후 재빌드. 캐시된 빌드가 구버전 plist 데이터를 서빙하는 경우가 있다.

---

## 재발 방지 팁

**Firebase CLI로 plist 생성 사용**

`firebase init` 명령으로 Firebase CLI를 사용하면 Google Sign-In이 활성화되어 있을 때 모든 OAuth 키가 포함된 plist 파일을 생성해준다. 수동 설정 실수를 줄일 수 있다.

**plist 파일을 버전 관리에 포함**

`GoogleService-Info.plist`를 git 저장소에 포함하거나 (키 노출이 우려된다면 보안 시크릿 관리 도구 사용) 안전한 방법으로 공유한다. 새 기기에서 프로젝트를 클론할 때 항상 올바른 설정이 있어야 한다.

**CI에서 설정 검증**

CI 스크립트에 필수 키 검증 단계를 추가한다.

```bash
if ! grep -q "CLIENT_ID" ios/Runner/GoogleService-Info.plist; then
  echo "ERROR: CLIENT_ID missing from GoogleService-Info.plist"
  exit 1
fi
```

**프로젝트 문서에 설명 추가**

README나 CLAUDE.md에 iOS OAuth 클라이언트를 Google Cloud Console에서 별도로 생성해야 한다는 사실을 명시한다. 팀원이나 미래의 자신이 같은 실수를 반복하지 않도록.

---

## 체크리스트

- [ ] `GoogleService-Info.plist`에 `CLIENT_ID` 키 존재 여부 확인
- [ ] `GoogleService-Info.plist`에 `REVERSED_CLIENT_ID` 키 존재 여부 확인
- [ ] `Info.plist`의 `CFBundleURLSchemes`에 `REVERSED_CLIENT_ID` 값 등록 여부 확인
- [ ] Xcode에서 Runner 타겟의 URL Types에도 동일한 scheme 등록 여부 확인
- [ ] `GoogleService-Info.plist`가 Xcode의 Runner 타겟에 추가되어 있는지 확인 (폴더에만 있는 게 아니라)
- [ ] Xcode의 번들 ID가 Google Cloud Console에서 OAuth 클라이언트 생성 시 사용한 번들 ID와 일치하는지 확인
- [ ] plist 수정 후 클린 빌드 실행 여부 확인

iOS Google Sign-In 문제의 대부분은 이 일곱 가지 중 하나가 빠진 경우다.

---

## Key Takeaways

- **근본 원인**: iOS `google_sign_in`은 `GoogleService-Info.plist`에 OAuth 2.0 클라이언트 ID가 있어야 동작한다. Firebase가 항상 이 값을 포함해서 파일을 생성하지는 않는다. 언제, 어떻게 다운로드했느냐에 따라 다르다.
- **Android가 다른 이유**: Android는 SHA-1 지문 매칭 방식으로 `google-services.json`을 사용하기 때문에 iOS OAuth 클라이언트가 없어도 동작한다. 이 구조 차이가 Android는 되고 iOS만 안 되는 상황을 만든다.
- **두 개의 plist, 두 개의 키**: `GoogleService-Info.plist`에는 `CLIENT_ID`와 `REVERSED_CLIENT_ID`가 필요하고, `Info.plist`에는 `REVERSED_CLIENT_ID` 값을 `CFBundleURLSchemes` 항목으로 등록해야 한다.
- **URL scheme이 핵심**: 이 값이 없으면 iOS가 OAuth 플로우 완료 후 앱으로 돌아올 수 없어 조용한 실패가 발생한다.
- **Xcode에서 항상 확인**: plist 직접 편집도 유효하지만 Xcode의 URL Types 패널이 권위 있는 소스다. 나중에 Xcode에서 설정을 변경하면 직접 편집한 내용을 덮어쓸 수 있다.
- **가장 빠른 해결책**: Firebase Authentication에서 Google Sign-In을 활성화한 후 Firebase Console에서 `GoogleService-Info.plist`를 재다운로드하는 것이 `CLIENT_ID`가 없을 때 가장 빠른 해결 방법이다.
