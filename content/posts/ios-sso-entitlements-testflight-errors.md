---
title: "iOS TestFlight 배포 삽질 모음: SSO 에러부터 entitlements mismatch까지"
date: 2026-02-25
draft: false
tags: ["iOS", "Flutter", "TestFlight", "Apple Sign-In", "Google OAuth", "Provisioning", "배포"]
description: "Apple Sign-In 에러 1000, Google OAuth 400 invalid_request, entitlements mismatch, BGTaskSchedulerPermittedIdentifiers 누락까지. TestFlight 배포 과정에서 만난 에러들과 해결법 정리."
---

Flutter 앱 여러 개를 TestFlight에 올리면서 반복적으로 마주친 에러들을 정리했다.

---

## 1. Apple Sign-In 에러 1000

```
SignInWithAppleAuthorizationException(AuthorizationErrorCode.unknown,
The operation couldn't be completed.
(com.apple.AuthenticationServices.AuthorizationError error 1000.))
```

### 원인

`Runner.entitlements`에 Sign in with Apple capability가 없어서 발생한다.

### 해결

**두 곳 모두** 설정해야 한다.

**① `ios/Runner/Runner.entitlements`**

```xml
<key>com.apple.developer.applesignin</key>
<array>
    <string>Default</string>
</array>
```

**② Apple Developer Console**

`developer.apple.com` → Identifiers → 앱 Bundle ID 선택 → **Sign in with Apple** 체크 → Save

프로비저닝 프로파일이 이미 있다면 재생성이 필요하다.

> entitlements 파일만 수정하고 Console에서 활성화하지 않으면 여전히 에러 1000이 발생한다.

---

## 2. Google OAuth 에러 400: invalid_request

```
오류 400: invalid_request
요청 세부정보: flowName=GeneralOAuthFlow
```

Flutter `google_sign_in` 패키지로 로그인 시도하면 Google 로그인 창이 뜨지 않고 브라우저에서 400 에러가 발생한다.

### 원인 파악

로그인 실패 시 리다이렉트 URL에 `authError` 파라미터가 포함된다. base64 디코딩하면 실제 원인을 볼 수 있다.

```bash
python3 -c "
import base64
encoded = '<authError 파라미터 값>'
print(base64.b64decode(encoded + '==').decode('utf-8', errors='replace'))
"
# 결과: "Custom scheme URIs are not allowed for 'WEB' client type."
```

### 원인

`GoogleService-Info.plist`의 `CLIENT_ID`가 **Web 타입** OAuth 클라이언트였다.

`google_sign_in` 패키지는 iOS 타입 클라이언트의 커스텀 URL 스킴(`com.googleusercontent.apps.{ID}:/oauthredirect`)으로 리다이렉트한다. Web 타입은 이 방식을 허용하지 않는다.

### 해결

Google Cloud Console에서 **iOS 타입** OAuth 클라이언트를 새로 생성해야 한다.

- Application type: `iOS` (Web이 아님)
- Bundle ID: 앱 번들 ID 입력
- Team ID: Apple 팀 ID

생성 후 `.plist` 파일을 다운로드해서 세 곳을 업데이트한다.

**① `ios/Runner/GoogleService-Info.plist`**

```xml
<key>CLIENT_ID</key>
<string>{iOS_CLIENT_ID}.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{iOS_CLIENT_ID}</string>
```

**② `ios/Runner/Info.plist`**

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.{iOS_CLIENT_ID}</string>
        </array>
    </dict>
</array>
```

**③ 백엔드 환경변수**

```
GOOGLE_CLIENT_ID={iOS_CLIENT_ID}.apps.googleusercontent.com
```

백엔드에서 JWT의 `aud` 클레임을 검증할 때 iOS CLIENT_ID와 일치해야 한다.

> CLI나 Firebase SDK로는 iOS 타입 OAuth 클라이언트를 생성할 수 없다. Google Cloud Console UI에서만 가능하다.

---

## 3. Provisioning Profile Entitlements Mismatch

```
Provisioning profile "iOS Team Provisioning Profile: com.example.app"
doesn't match the entitlements file's value for the
com.apple.developer.default-data-protection entitlement.
```

### 원인

`Runner.entitlements`에 선언된 capability가 현재 프로비저닝 프로파일에 포함되어 있지 않을 때 발생한다.

주로 문제가 되는 항목들:

- `com.apple.developer.default-data-protection`
- `com.apple.developer.icloud-container-identifiers`
- `com.apple.developer.icloud-services`

### 해결

두 가지 방법 중 선택한다.

**방법 A: Apple Developer Console에서 capability 활성화**

해당 App ID에서 필요한 capability를 활성화하고 프로비저닝 프로파일을 재생성한다.

**방법 B: 사용하지 않는 entitlement 제거 (권장)**

앱에서 실제로 사용하지 않는 capability라면 `Runner.entitlements`에서 제거한다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <!-- 실제로 사용하는 것만 남긴다 -->
    <key>aps-environment</key>
    <string>production</string>
    <key>com.apple.developer.applesignin</key>
    <array>
        <string>Default</string>
    </array>
</dict>
</plist>
```

> `default-data-protection`은 보안 정책 설정이라 제거해도 앱 동작에 영향 없다.

---

## 4. Xcode 수동 서명이 Automatic 서명과 충돌

```
Runner has conflicting provisioning settings. Runner is automatically signed,
but provisioning profile PROFILE_NAME has been manually specified.
```

### 원인

`project.pbxproj`에 특정 프로비저닝 프로파일이 하드코딩되어 있는데 빌드 커맨드에서 Automatic 서명을 요청할 때 충돌한다.

### 해결

`ios/Runner.xcodeproj/project.pbxproj`에서 수동 서명 설정을 Automatic으로 변경한다.

```bash
sed -i '' \
  -e 's/CODE_SIGN_STYLE = Manual;/CODE_SIGN_STYLE = Automatic;/g' \
  -e 's/CODE_SIGN_IDENTITY = "iPhone Distribution";/CODE_SIGN_IDENTITY = "iPhone Developer";/g' \
  -e '/PROVISIONING_PROFILE_SPECIFIER = ".*";/d' \
  ios/Runner.xcodeproj/project.pbxproj
```

---

## 5. TestFlight 업로드 실패: BGTaskSchedulerPermittedIdentifiers 누락

```
Missing Info.plist value. The Info.plist key 'BGTaskSchedulerPermittedIdentifiers'
must contain a list of identifiers used to submit and handle tasks
when 'UIBackgroundModes' has a value of 'processing'.
```

### 원인

`Info.plist`의 `UIBackgroundModes`에 `processing`이 있으면 `BGTaskSchedulerPermittedIdentifiers`도 반드시 있어야 한다. 보통 `workmanager` 패키지를 쓸 때 이 조합이 생긴다.

### 해결

코드에서 `registerPeriodicTask` 또는 `registerOneOffTask`에 넘기는 task 이름을 확인한 뒤 `Info.plist`에 추가한다.

```xml
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>your_task_name_here</string>
</array>
<key>UIBackgroundModes</key>
<array>
    <string>fetch</string>
    <string>processing</string>
</array>
```

Dart 코드에서 task 이름 확인:

```bash
grep -r "registerPeriodicTask\|registerOneOffTask" lib/ --include="*.dart"
```

---

## 6. flutter build ipa 대신 2단계 빌드

`flutter build ipa`는 codesigning을 포함한 전체 빌드를 한 번에 처리한다. entitlements 문제나 Xcode 계정 미로그인 상태에서는 실패하기 쉽다.

대신 2단계로 나눠서 처리하면 더 안정적이다.

```bash
# 1단계: codesigning 없이 앱 빌드
flutter build ios --release --no-codesign

# 2단계: App Store Connect API Key로 직접 archive
xcodebuild archive \
  -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -archivePath build/ios/archive/Runner.xcarchive \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID \
  CODE_SIGN_STYLE=Automatic \
  DEVELOPMENT_TEAM=YOUR_TEAM_ID

# 3단계: IPA export
xcodebuild -exportArchive \
  -archivePath build/ios/archive/Runner.xcarchive \
  -exportPath build/ios/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID

# 4단계: TestFlight 업로드
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

`ExportOptions.plist`에 API Key 정보를 포함해두면 export 단계에서도 계정 없이 동작한다.

```xml
<key>authenticationKeyID</key>
<string>YOUR_KEY_ID</string>
<key>authenticationKeyIssuerID</key>
<string>YOUR_ISSUER_ID</string>
<key>authenticationKeyPath</key>
<string>/path/to/AuthKey_KEYID.p8</string>
```

Makefile로 묶어두면 `make testflight` 한 줄로 끝난다.

---

## 체크리스트

TestFlight 배포 전 확인 사항:

- [ ] `Runner.entitlements`에 사용하는 capability만 선언되어 있는가
- [ ] Apple Developer Console에서 해당 capability가 App ID에 활성화되어 있는가
- [ ] `UIBackgroundModes: processing`이 있으면 `BGTaskSchedulerPermittedIdentifiers`도 있는가
- [ ] Google OAuth CLIENT_ID가 Web 타입이 아닌 iOS 타입인가
- [ ] `project.pbxproj`에 하드코딩된 프로비저닝 프로파일이 없는가
- [ ] 빌드 번호가 이전보다 높은가
