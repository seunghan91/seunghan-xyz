---
title: "Sign In with Apple 추가 후 TestFlight 빌드 에러 2연타 해결"
date: 2025-09-10
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Sign In with Apple", "배포"]
description: "Apple Developer Portal에서 Sign In with Apple을 활성화하고 프로비저닝 프로파일을 재생성한 뒤, 빌드에서 연달아 터진 두 가지 entitlement 에러 해결 과정"
cover:
  image: "/images/og/sign-in-with-apple-testflight-entitlement-errors.png"
  alt: "Sign In With Apple Testflight Entitlement Errors"
  hidden: true
---

Flutter iOS 앱에 Sign In with Apple을 추가하면서 TestFlight 빌드까지 두 가지 에러를 연달아 만났다. 각각 원인이 달라서 정리해둔다.

---

## 배경

Sign In with Apple을 활성화하려면 코드만 짜면 되는 게 아니다. Apple Developer Portal에서 App ID에 capability를 추가하고, 프로비저닝 프로파일을 **반드시 재생성**해야 한다. 기존 프로파일은 Sign In with Apple entitlement를 포함하지 않으므로 그냥 빌드하면 실패한다.

순서대로 하면:

1. [developer.apple.com](https://developer.apple.com) → Identifiers → App ID 선택
2. **Sign In with Apple** 체크 → Edit → "Enable as a primary App ID" 선택 → Save
3. Profiles → 기존 App Store 프로파일 Edit → Generate → Download
4. 다운받은 `.mobileprovision` 파일을 `~/Library/MobileDevice/Provisioning Profiles/` 에 복사

여기까지 하면 준비 완료처럼 보이는데, 막상 `flutter build ipa` 를 돌리면 에러가 나온다.

---

## 에러 1: Entitlements file was modified during the build

```
Error (Xcode): Entitlements file "Runner.entitlements" was modified during the build,
which is not supported. You can disable this error by setting
'CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION' to 'YES'
```

### 원인

Xcode가 빌드 중 자동으로 entitlements를 처리하는 과정에서 `Runner.entitlements` 파일을 수정하는데, 이걸 탐지하고 에러로 처리한다. Sign In with Apple capability를 새로 추가한 뒤에 자주 발생한다.

### 해결

`ios/Runner.xcodeproj/project.pbxproj`에서 Runner 타겟의 Debug / Release / Profile 세 가지 build configuration에 각각 추가:

```
CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;
```

pbxproj를 직접 열면 `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;` 라인 바로 위에 넣으면 된다. Runner 타겟 설정이 3개(Debug/Release/Profile)이므로 3군데 모두 추가해야 한다.

---

## 에러 2: Entitlements not found and could not be included in profile

```
Error (Xcode): Entitlements com.apple.developer.devicecheck.appattest-environment
and com.apple.developer.usernotifications.time-sensitive not found and could not
be included in profile. These likely are not valid entitlements and should be
removed from your entitlements file.
```

### 원인

`Runner.entitlements`에 적어둔 entitlement 중에 **프로비저닝 프로파일에 등록되지 않은 항목**이 있으면 빌드가 막힌다.

- `com.apple.developer.devicecheck.appattest-environment` — App Attest 기능. Developer Portal App ID에서 활성화하지 않으면 프로파일에 포함 안 됨.
- `com.apple.developer.usernotifications.time-sensitive` — Time Sensitive Notifications. 마찬가지로 App ID에서 별도 활성화 필요.

나중에 쓰려고 미리 entitlements 파일에 적어둔 항목들이었는데, 실제 프로파일엔 없으니 충돌이 난 것.

### 해결

당장 사용하지 않는 entitlement는 `Runner.entitlements`에서 제거한다.

```xml
<!-- 제거 -->
<key>com.apple.developer.devicecheck.appattest-environment</key>
<string>production</string>

<!-- 제거 -->
<key>com.apple.developer.usernotifications.time-sensitive</key>
<true/>
```

나중에 실제로 쓸 때가 되면, Developer Portal에서 App ID에 해당 capability를 추가하고 프로파일 재생성 후 다시 추가하면 된다.

---

## 핵심 원칙

**entitlements 파일과 프로비저닝 프로파일은 반드시 일치해야 한다.**

프로파일에 없는 entitlement를 파일에 적어두면 빌드 에러가 난다. 반대로 프로파일에 있는데 파일에 없으면 해당 기능이 작동 안 한다. 새 capability를 추가할 때마다:

1. Developer Portal App ID → capability 추가
2. 프로비저닝 프로파일 재생성 & 재설치
3. `Runner.entitlements`에 항목 추가

이 세 단계가 항상 같이 따라다닌다.
