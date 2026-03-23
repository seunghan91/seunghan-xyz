---
title: "Sign In with Apple 추가 후 TestFlight 빌드 에러 2연타 해결"
date: 2025-09-10
draft: true
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

iOS 앱을 배포할 때 종종 간과하는 부분이 있다. Xcode에서 capability를 체크하거나, Flutter 플러그인을 추가하는 것만으로는 충분하지 않다는 점이다. 프로비저닝 프로파일은 해당 앱에서 사용할 수 있는 entitlement 목록을 명시적으로 담고 있다. 프로파일을 재생성하지 않으면, 아무리 코드에서 Sign In with Apple을 구현해도 빌드 단계 또는 App Store Connect 업로드 단계에서 막힌다.

### 준비 순서

순서대로 하면:

1. [developer.apple.com](https://developer.apple.com) → Identifiers → App ID 선택
2. **Sign In with Apple** 체크 → Edit → "Enable as a primary App ID" 선택 → Save
3. Profiles → 기존 App Store 프로파일 Edit → Generate → Download
4. 다운받은 `.mobileprovision` 파일을 `~/Library/MobileDevice/Provisioning Profiles/` 에 복사
5. Xcode에서 프로젝트를 열고 Signing & Capabilities 탭에서 프로파일이 올바르게 선택됐는지 확인

여기까지 하면 준비 완료처럼 보이는데, 막상 `flutter build ipa` 를 돌리면 에러가 나온다.

### Flutter 프로젝트의 특수성

Flutter 프로젝트에서는 Xcode GUI 대신 `ios/Runner.xcodeproj/project.pbxproj`와 `ios/Runner/Runner.entitlements` 파일을 직접 편집하는 경우가 많다. Xcode에서 capability를 추가하면 자동으로 entitlements 파일과 pbxproj가 갱신되지만, 수동으로 파일을 관리하는 경우에는 두 파일 간의 불일치가 발생하기 쉽다.

또한 `flutter_sign_in_with_apple` 같은 플러그인을 추가하면 플러그인 자체가 `Runner.entitlements`에 항목을 주입하려 할 수 있다. 이 과정에서 빌드 중 파일이 수정되면서 아래 에러가 터진다.

---

## 에러 1: Entitlements file was modified during the build

```
Error (Xcode): Entitlements file "Runner.entitlements" was modified during the build,
which is not supported. You can disable this error by setting
'CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION' to 'YES'
```

### 원인

Xcode가 빌드 중 자동으로 entitlements를 처리하는 과정에서 `Runner.entitlements` 파일을 수정하는데, 이걸 탐지하고 에러로 처리한다. Sign In with Apple capability를 새로 추가한 뒤에 자주 발생한다.

구체적으로는 Xcode의 빌드 시스템이 코드 서명 단계에서 entitlements를 병합하려 한다. 이 과정에서 원본 파일과 최종 서명에 쓰일 파일 사이에 차이가 생기면, Xcode는 이를 무결성 위반으로 판단하고 빌드를 중단한다. `sign_in_with_apple` 플러그인처럼 빌드 단계에 후크를 걸어 entitlements를 조작하는 플러그인이 있을 때 특히 빈번하게 나타난다.

### 해결

`ios/Runner.xcodeproj/project.pbxproj`에서 Runner 타겟의 Debug / Release / Profile 세 가지 build configuration에 각각 추가:

```
CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;
```

pbxproj를 직접 열면 `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;` 라인 바로 위에 넣으면 된다. Runner 타겟 설정이 3개(Debug/Release/Profile)이므로 3군데 모두 추가해야 한다.

파일 내에서 찾는 방법:

```bash
# pbxproj에서 CODE_SIGN_ENTITLEMENTS가 있는 줄을 모두 찾아 확인
grep -n "CODE_SIGN_ENTITLEMENTS" ios/Runner.xcodeproj/project.pbxproj
```

출력 결과에서 줄 번호를 확인한 뒤, 각 줄 바로 위에 `CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;`를 삽입하면 된다.

아래는 pbxproj에서 해당 섹션이 어떻게 보이는지 예시다:

```
/* Debug */
buildSettings = {
    CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;  /* 추가 */
    CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;
    CODE_SIGN_IDENTITY = "Apple Distribution";
    ...
};
```

이 설정을 추가하면 Xcode가 빌드 중 entitlements 파일 수정을 허용하므로 에러가 사라진다.

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

프로비저닝 프로파일은 Apple 서버에서 생성될 때 해당 App ID에 활성화된 capability 목록만을 포함한다. `Runner.entitlements`에 아무리 정확한 entitlement 키를 써도, 프로파일 자체에 그 키가 없으면 코드 서명 단계에서 불일치가 감지되어 빌드가 실패한다.

개발하면서 "나중에 쓸 것 같은" entitlement를 미리 추가해 두는 경우가 있는데, 이게 바로 이 에러의 주범이 된다. 실제로 Developer Portal에서 활성화하지 않은 capability는 entitlements 파일에서도 빠져 있어야 한다.

### Runner.entitlements 파일 구조 이해

`Runner.entitlements`는 plist 형식의 XML 파일이다. 예를 들어 Sign In with Apple만 활성화된 상태라면 이렇게 생겼다:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.applesignin</key>
    <array>
        <string>Default</string>
    </array>
</dict>
</plist>
```

여기에 아직 Developer Portal에서 활성화하지 않은 항목을 추가하면 에러가 발생한다.

### 해결

당장 사용하지 않는 entitlement는 `Runner.entitlements`에서 제거한다.

```xml
<!-- 제거: App Attest가 Developer Portal에서 활성화되어 있지 않은 경우 -->
<key>com.apple.developer.devicecheck.appattest-environment</key>
<string>production</string>

<!-- 제거: Time Sensitive Notifications가 Developer Portal에서 활성화되어 있지 않은 경우 -->
<key>com.apple.developer.usernotifications.time-sensitive</key>
<true/>
```

나중에 실제로 쓸 때가 되면, Developer Portal에서 App ID에 해당 capability를 추가하고 프로파일 재생성 후 다시 추가하면 된다.

### 프로파일에 어떤 entitlement가 포함됐는지 확인하는 방법

다운받은 `.mobileprovision` 파일의 내용을 확인하면, 프로파일이 어떤 entitlement를 허용하는지 볼 수 있다:

```bash
# mobileprovision 파일에서 Entitlements 섹션 출력
security cms -D -i ~/Library/MobileDevice/Provisioning\ Profiles/YOUR_PROFILE.mobileprovision \
  | grep -A 30 "<key>Entitlements</key>"
```

이 명령으로 프로파일에 실제로 포함된 entitlement 목록을 확인하고, `Runner.entitlements`와 대조하면 불일치를 빠르게 찾을 수 있다.

---

## 핵심 원칙

**entitlements 파일과 프로비저닝 프로파일은 반드시 일치해야 한다.**

프로파일에 없는 entitlement를 파일에 적어두면 빌드 에러가 난다. 반대로 프로파일에 있는데 파일에 없으면 해당 기능이 작동 안 한다. 새 capability를 추가할 때마다:

1. Developer Portal App ID → capability 추가
2. 프로비저닝 프로파일 재생성 & 재설치
3. `Runner.entitlements`에 항목 추가

이 세 단계가 항상 같이 따라다닌다.

이 원칙을 지키지 않으면 에러 2처럼 "프로파일에 없는 항목이 entitlements에 있는" 상황이 생기거나, 반대로 "프로파일에는 있는데 코드에서 해당 기능이 동작하지 않는" 더 조용한 버그가 생긴다.

---

## 빌드 후 TestFlight 업로드까지의 흐름

에러를 모두 해결하고 `flutter build ipa`가 성공했다면, TestFlight 업로드 단계를 진행할 수 있다.

```bash
# IPA 파일 빌드
flutter build ipa --release

# TestFlight에 업로드 (App Store Connect API Key 사용)
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

업로드 후 App Store Connect의 TestFlight 탭에서 처리 상태를 확인한다. "Missing Compliance" 관련 경고가 뜨면 `Info.plist`에 아래 키를 추가해 수출 규정을 명시해야 한다:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

---

## 정리: 이번에 배운 것들

1. **Sign In with Apple 활성화는 3단계 작업이다**: Developer Portal capability 활성화 → 프로파일 재생성 → entitlements 파일 업데이트. 하나라도 빠지면 빌드가 깨진다.

2. **`CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES`는 Flutter 프로젝트에서 Sign In with Apple 플러그인 사용 시 거의 필수적이다**. 빌드 중 플러그인이 entitlements를 조작하기 때문에 이 설정 없이는 빌드가 통과하지 못한다.

3. **"나중에 쓸 것 같아서" 미리 추가한 entitlement는 독이 된다**. 실제로 Developer Portal에서 활성화하기 전까지는 entitlements 파일에서도 빼 두어야 한다.

4. **프로파일 내용을 직접 확인하는 습관을 들이자**. `security cms -D -i` 명령으로 프로파일이 담고 있는 entitlement를 바로 확인할 수 있다. entitlements 파일과 대조하는 것이 디버깅의 첫 번째 단계다.

5. **Debug / Release / Profile 세 가지 build configuration 모두 일관성 있게 설정해야 한다**. pbxproj 수정 시 한 configuration에만 추가하면 특정 빌드 타입에서만 에러가 재현되는 혼란스러운 상황이 생길 수 있다.
