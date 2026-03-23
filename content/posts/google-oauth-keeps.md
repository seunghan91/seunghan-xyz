---
title: "Flutter 앱 Google OAuth 동의 화면 인증 셋업 정리"
date: 2025-06-11
draft: true
tags: ["Flutter", "OAuth", "Google", "앱개발"]
description: "Google Cloud Console OAuth 동의 화면 구성 및 인증 제출 과정에서 겪은 삽질 정리"
cover:
  image: "/images/og/google-oauth-keeps.png"
  alt: "Google Oauth Keeps"
  hidden: true
---

Flutter 앱에 Google 로그인을 붙이면서 OAuth 동의 화면 인증까지 진행한 과정을 정리한다.

Firebase 없이 Google Cloud Console에서 직접 OAuth 클라이언트 ID를 발급받아 연동하는 경우, 동의 화면 설정과 인증 제출 과정에서 예상치 못한 에러가 자주 발생한다. 공식 문서에는 잘 나오지 않는 실제로 겪은 삽질 위주로 기록한다.

---

## 전체 흐름 요약

1. Google Cloud Console에서 OAuth 2.0 클라이언트 ID 생성 (iOS 타입)
2. 동의 화면 브랜딩 설정
3. 앱 도메인 및 개인정보처리방침 URL 등록
4. 필요한 범위(scope) 설정
5. 인증 제출 및 프로덕션 전환

이 흐름은 단순해 보이지만 각 단계마다 검증 로직이 숨어 있어서, 조건을 정확히 맞추지 않으면 제출 자체가 막히거나 나중에 반려된다.

---

## OAuth 클라이언트 ID 생성

Google Cloud Console의 **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**에서 생성한다.

Flutter iOS 앱의 경우 애플리케이션 유형을 **iOS**로 선택한다. Bundle ID를 입력하면 클라이언트 ID와 함께 `.plist` 파일을 다운로드할 수 있다. 이 파일에는 `REVERSED_CLIENT_ID`가 포함되어 있으며, 이것이 iOS에서 OAuth 리다이렉트 URL로 사용된다.

Android의 경우 **SHA-1 인증서 지문**이 필요하다. 디버그 빌드와 릴리즈 빌드의 지문이 다르므로, 릴리즈 배포 전에 반드시 릴리즈 키스토어의 SHA-1도 추가해두어야 한다.

```bash
# 디버그 키스토어 SHA-1 확인
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
```

Flutter 프로젝트에서는 `google_sign_in` 패키지를 사용한다.

```yaml
# pubspec.yaml
dependencies:
  google_sign_in: ^6.2.0
```

iOS의 경우 `Info.plist`에 `REVERSED_CLIENT_ID`를 URL Scheme으로 등록해야 앱으로 돌아오는 콜백이 동작한다.

```xml
<!-- ios/Runner/Info.plist -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
    </array>
  </dict>
</array>
```

---

## 브랜딩 설정

Google Cloud Console → **API 및 서비스 → OAuth 동의 화면 → 브랜딩** 에서 아래 항목을 입력한다.

- **앱 이름**: 동의 화면에 표시될 이름 (홈페이지 본문과 반드시 일치해야 함)
- **사용자 지원 이메일**: 문의용 이메일
- **앱 도메인**: 홈페이지, 개인정보처리방침, 서비스 약관 URL
- **승인된 도메인**: 위 URL들의 루트 도메인

"승인된 도메인"은 등록한 URL들의 최상위 도메인만 입력한다. 예를 들어 개인정보처리방침 URL이 `https://dcode-labs.com/keeps/privacy/`라면 승인된 도메인에는 `dcode-labs.com`만 입력한다. 서브도메인이나 경로는 불필요하며 오히려 오류를 유발할 수 있다.

---

## 삽질 1: 앱 이름 불일치 에러

저장 후 인증 제출 시 아래 에러가 발생할 수 있다.

> OAuth 동의 화면에 구성된 앱 이름이 홈페이지의 앱 이름과 일치하지 않습니다.

Google이 홈페이지 URL을 크롤링해서 **페이지 본문에 렌더링된 텍스트**와 콘솔에 입력한 앱 이름을 비교한다.

`<title>` 태그나 `<meta>` 태그만으로는 통과되지 않는다. 실제 DOM에 보이는 텍스트여야 한다. JavaScript로 동적으로 렌더링되는 SPA라면 크롤러가 해당 텍스트를 읽지 못할 수도 있으므로, 정적 HTML에 직접 포함시키는 것이 안전하다.

### 해결

홈페이지 HTML 본문에 콘솔 앱 이름과 동일한 텍스트를 추가한다.

```html
<p>앱 이름 (콘솔에 입력한 것과 동일하게)</p>
```

Hugo, Jekyll 같은 정적 사이트 생성기를 쓰는 경우 헤더나 푸터에 앱 이름 텍스트를 명시적으로 넣어두면 된다. 스타일로 숨기는 방식(`display: none`)은 크롤러가 인식하는지 불분명하므로, 시각적으로 자연스러운 위치에 텍스트를 배치하는 것을 권장한다.

---

## 데이터 액세스 (범위)

**단순 Google 로그인만 구현한다면 범위를 추가하지 않아도 된다.**

`openid`, `email`, `profile`은 Google Sign-In에 기본 포함된 범위로, 콘솔에서 별도 추가 없이 자동 동작하며 별도 심사도 필요 없다.

범위 추가가 필요한 경우:

| 기능 | 범위 | 심사 |
|---|---|---|
| Google Drive 저장 | `drive.file` | 민감 범위 심사 |
| Gmail | `gmail.*` | 제한 범위 심사 |
| Google Calendar | `calendar` | 민감 범위 심사 |

불필요한 범위를 추가하면 심사 난이도만 올라가므로 실제 사용하는 것만 추가한다.

Flutter 코드에서 `google_sign_in` 패키지의 `scopes` 파라미터와 콘솔에 등록한 범위가 일치해야 한다. 코드에 선언만 하고 콘솔에 미등록이면 런타임에서 오류가 발생한다.

```dart
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: [
    'email',
    'profile',
    // 추가 범위가 필요한 경우에만 여기에 선언
    // 'https://www.googleapis.com/auth/drive.file',
  ],
);
```

---

## 인증 제출

- **테스트 상태**: 콘솔에 등록한 테스트 계정만 로그인 가능
- **프로덕션 상태**: 인증 완료 후 모든 Google 계정 사용자 로그인 가능

브랜딩, 데이터 액세스 설정 완료 후 **인증** 탭에서 제출한다.

제출 전에 모든 필수 항목이 입력되었는지 확인한다. 특히 개인정보처리방침 URL은 Google 봇이 실제로 접근 가능한 상태여야 하며, 제출 시점에 URL이 404를 반환하면 즉시 반려된다.

---

## 삽질 2: 개인정보처리방침 URL 검증 실패

앱 도메인 항목에 입력한 개인정보처리방침 URL이 Google 봇에게 접근 가능해야 한다.

Hugo 블로그처럼 정적 사이트를 운영하는 경우 배포가 완료된 URL이어야 하며, `localhost`나 미배포 URL은 검증을 통과하지 못한다. 인증 제출 전에 실제 URL로 접근이 되는지 먼저 확인한다.

Netlify나 GitHub Pages를 사용하는 경우, 브랜치 배포 URL(`deploy-preview-xxx.netlify.app`)이 아닌 실제 프로덕션 도메인 URL을 입력해야 한다. 또한 URL에 `robots.txt`로 크롤링을 차단해두었다면 Google 봇도 접근하지 못하므로 주의한다.

개인정보처리방침 페이지에는 다음 내용이 최소한으로 포함되어야 Google의 검토를 통과하기 쉽다.

- 수집하는 데이터 종류 (이름, 이메일 등)
- 데이터 사용 목적
- 데이터 보관 및 삭제 정책
- 문의처 이메일

---

## 삽질 3: 테스트 상태에서 "앱이 확인되지 않음" 경고

OAuth 동의 화면이 **테스트** 상태일 때 등록된 테스트 계정 외의 계정으로 로그인하면 "앱이 확인되지 않았습니다" 경고가 표시된다. 이는 정상이며, 인증 제출 후 프로덕션으로 전환되면 사라진다.

테스트 단계에서는 콘솔의 **테스트 사용자** 항목에 테스트 계정 이메일을 추가해두면 경고 없이 로그인 가능하다.

한 가지 더: 테스트 사용자로 등록된 계정이라도 앱에 이미 로그인되어 있는 세션이 있으면 간혹 경고가 다시 나타날 수 있다. 이런 경우 `accounts.google.com`에서 해당 앱의 액세스 권한을 취소하고 다시 로그인하면 해결된다.

---

## 인증 심사 소요 기간

Google OAuth 인증 심사는 민감 범위가 없는 경우(기본 로그인만) 수 일 내에 완료되는 편이다. 민감 범위(`drive`, `gmail` 등)가 포함된 경우 수 주~수 개월이 걸릴 수 있으며, 공식 앱 웹사이트와 데모 영상 제출이 필요하다.

기본 Google 로그인만 사용하는 앱이라면 별도 심사 없이 프로덕션 전환이 바로 가능하다.

심사 상태는 Google Cloud Console의 **OAuth 동의 화면 → 인증** 탭에서 확인할 수 있다. 반려된 경우 사유가 함께 표시되므로, 수정 후 재제출하면 된다. 재제출은 횟수 제한 없이 가능하다.

---

## 프로덕션 전환 이후 주의사항

프로덕션으로 전환된 이후에도 앱 이름, 개인정보처리방침 URL, 범위 등을 변경하면 재심사가 필요할 수 있다. 특히 민감 범위를 새로 추가하는 경우 기존 프로덕션 상태가 일시적으로 테스트 상태로 돌아갈 수 있다.

앱이 출시된 상태에서 범위를 변경해야 한다면, 변경 사항을 최소화하고 심사 기간 동안 기존 기능에 영향이 없도록 기능 플래그를 사용하는 것을 권장한다.

---

## Key Takeaways

- **앱 이름**은 콘솔 입력값과 홈페이지 DOM에 렌더링된 텍스트가 반드시 일치해야 한다. `<title>`이나 `<meta>`만으로는 부족하다.
- **개인정보처리방침 URL**은 제출 시점에 Google 봇이 실제로 접근 가능한 배포된 URL이어야 한다.
- **기본 Google 로그인**(`openid`, `email`, `profile`)은 별도 범위 추가 없이 심사 없이 프로덕션 전환이 가능하다.
- **테스트 상태**에서의 "앱이 확인되지 않음" 경고는 정상 동작이며, 테스트 사용자 등록으로 우회할 수 있다.
- **iOS**는 `REVERSED_CLIENT_ID`를 URL Scheme으로, **Android**는 릴리즈 키스토어 SHA-1을 반드시 등록해야 한다.
- 민감 범위 없이 기본 로그인만 쓴다면 심사 소요 기간은 수 일 이내로 짧다.

---

## 정리

| 항목 | 주의사항 |
|------|---------|
| 앱 이름 | 콘솔 입력값과 홈페이지 DOM 텍스트 일치 필요 |
| 개인정보처리방침 URL | 실제 접근 가능한 배포된 URL이어야 함 |
| 범위(scope) | 기본 로그인만이면 추가 불필요 |
| 테스트 계정 | 테스트 상태에서는 등록된 계정만 경고 없이 로그인 가능 |
| 인증 제출 | 민감 범위 없으면 프로덕션 전환 즉시 가능 |
| iOS 설정 | REVERSED_CLIENT_ID를 URL Scheme으로 Info.plist에 등록 필요 |
| Android 설정 | 디버그/릴리즈 키스토어 SHA-1 모두 콘솔에 등록 필요 |
