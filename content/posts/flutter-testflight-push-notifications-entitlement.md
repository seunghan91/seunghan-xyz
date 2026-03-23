---
title: "Flutter TestFlight 빌드 오류: Push Notifications 엔트리포인트 문제"
date: 2025-06-08
draft: true
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "배포"]
description: "Flutter iOS 앱을 TestFlight에 올리다 마주친 provisioning profile / aps-environment 오류 해결 과정"
cover:
  image: "/images/og/flutter-testflight-push-notifications-entitlement.png"
  alt: "Flutter Testflight Push Notifications Entitlement"
  hidden: true
---

Flutter 앱을 TestFlight에 처음 올려보면서 겪은 빌드 오류와 해결 과정을 정리한다. 증상은 단순하지만, 원인을 모르면 꽤 오래 헤맬 수 있는 문제다. provisioning profile, entitlements, APNs 설정이 어떻게 맞물리는지 함께 이해하면 이후에도 비슷한 오류를 빠르게 잡을 수 있다.

---

## 오류 상황

`flutter build ipa --release` 후 xcrun altool로 업로드를 시도하자 업로드 자체가 아니라 **빌드 단계**에서 Xcode 아카이브가 실패했다.

```
error: Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the aps-environment entitlement.
```

처음에는 altool 명령어 문제인 줄 알았지만, 아카이브 자체가 생성되지 않는 문제였다. 업로드 커맨드는 다음과 같다.

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "$APPLE_ID" \
  --password "$APPLE_APP_PASSWORD"
```

오류 메시지를 더 자세히 보면 두 가지 핵심 정보가 담겨 있다.

1. **"iOS Team Provisioning Profile: \*"** — Wildcard 프로비저닝 프로파일을 사용하고 있다는 것
2. **"aps-environment entitlement"** — APNs(Apple Push Notification service) 환경 설정이 프로파일과 충돌하고 있다는 것

이 두 가지 정보를 조합하면 원인이 명확하게 드러난다.

---

## 원인 분석

### entitlements 파일이란?

iOS 앱은 `.entitlements` 파일을 통해 특정 시스템 기능(Push Notifications, iCloud, App Groups 등)에 대한 접근 권한을 선언한다. 이 파일은 빌드 시 코드 서명(code signing)과 함께 처리되며, 앱이 요청하는 권한이 provisioning profile에 포함된 권한과 일치해야 한다.

`ios/Runner/Runner.entitlements` 파일에 아래 항목이 들어가 있었다.

```xml
<key>aps-environment</key>
<string>production</string>
```

이 키는 **Push Notifications 기능을 활성화한 Provisioning Profile**에서만 허용된다. Wildcard(`*`) 프로비저닝 프로파일은 Push Notifications을 지원하지 않기 때문에 아카이브 시점에 충돌이 발생한다.

### Wildcard 프로파일의 한계

Wildcard 프로파일(`*`)은 Bundle ID를 특정하지 않고 여러 앱에 공용으로 사용할 수 있는 간편한 프로파일이다. 하지만 이 편리함에는 제약이 따른다. Push Notifications, Game Center, In-App Purchase 등 **앱별 고유 설정이 필요한 기능**은 Wildcard 프로파일에서 지원되지 않는다. APNs 기능을 사용하려면 반드시 명시적 App ID(Explicit App ID)를 기반으로 한 프로파일이 필요하다.

### 언제 이 키가 생기나?

Xcode에서 **Signing & Capabilities** 탭에서 Push Notifications를 한 번이라도 추가하면 자동으로 entitlements 파일에 기록된다. 이후 기능을 제거해도 파일은 그대로 남는다.

Flutter 프로젝트에서는 `firebase_messaging` 같은 패키지를 설치하면서 Xcode에서 Push Notifications capability를 추가하는 경우가 흔하다. 그 과정에서 `aps-environment` 키가 entitlements 파일에 기록되고, 나중에 해당 패키지를 제거하거나 기능을 당장 쓰지 않더라도 키는 남아 있는 것이다.

또 다른 흔한 시나리오는 개발 중에 테스트 목적으로 Push Notifications를 잠깐 추가해봤다가 제거한 경우다. Xcode는 capability를 UI에서 제거해도 `.entitlements` 파일까지 자동으로 정리해주지 않는다.

---

## 해결 방법

### 즉각적인 해결: aps-environment 키 삭제

Push Notifications를 아직 구현하지 않은 단계라면 `Runner.entitlements`에서 해당 키를 삭제한다.

```xml
<!-- 삭제 전 -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
</plist>

<!-- 삭제 후 -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
</dict>
</plist>
```

이후 다시 빌드하면 정상 통과된다.

### Xcode에서 확인하는 방법

텍스트 에디터로 직접 수정하는 것 외에, Xcode에서도 확인할 수 있다.

1. `ios/Runner.xcworkspace`를 Xcode로 열기
2. 왼쪽 파일 트리에서 `Runner` 타겟 선택
3. **Signing & Capabilities** 탭으로 이동
4. Push Notifications capability가 추가되어 있다면 우측의 `-` 버튼으로 제거
5. `Runner.entitlements` 파일을 직접 열어 `aps-environment` 키가 없는지 확인

Xcode에서 capability를 제거한 후에도 `.entitlements` 파일에 키가 남아 있는 경우가 있으므로, 파일을 직접 열어서 확인하는 것이 안전하다.

---

## xcrun altool로 TestFlight 업로드

빌드 오류를 해결했다면 이제 정상적으로 업로드할 수 있다. Apple Developer 계정의 **앱 암호(App-Specific Password)**를 사용한다.

```bash
# 앱 암호 생성: https://appleid.apple.com → 앱 암호 생성
# 형식: xxxx-xxxx-xxxx-xxxx

xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx"
```

App Store Connect API Key를 사용하는 방식도 있다. 이 방법은 2단계 인증(2FA)을 우회할 수 있어 CI/CD 파이프라인에 적합하다.

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --apiKey "YOUR_KEY_ID" \
  --apiIssuer "YOUR_ISSUER_ID"
```

업로드 성공 시 아래와 같이 출력된다.

```
No errors uploading archive at 'build/ios/ipa/app.ipa'.
```

Delivery UUID가 발급되며, 보통 수 분 내로 App Store Connect → TestFlight에서 빌드가 처리된다. 처음에는 "처리 중" 상태로 보이다가 완료되면 테스터에게 배포 가능한 상태가 된다.

### altool 대신 notarytool 사용 (macOS 13+)

macOS Ventura(13.0) 이후부터 `xcrun altool`은 deprecated 상태다. 대신 `xcrun notarytool`을 사용하는 것이 권장된다.

```bash
xcrun notarytool submit "build/ios/ipa/app.ipa" \
  --apple-id "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx" \
  --team-id "YOUR_TEAM_ID" \
  --wait
```

현재 Flutter 공식 문서에서는 여전히 altool을 예시로 사용하는 경우가 많지만, 장기적으로는 notarytool 또는 Transporter 앱을 통한 업로드로 전환하는 것이 좋다.

---

## Push Notifications를 나중에 추가할 때

실제로 Push Notifications를 구현할 때가 되면 올바른 순서로 진행해야 한다.

### 설정 순서

1. **Apple Developer Console**에서 해당 App ID의 Push Notifications 기능 활성화
   - [developer.apple.com](https://developer.apple.com) → Certificates, Identifiers & Profiles → Identifiers
   - 앱의 명시적 App ID 선택 → Capabilities에서 Push Notifications 활성화

2. **APNs Key 또는 APNs Certificate 발급**
   - APNs Key: 여러 앱에서 공유 가능, 만료 없음 (권장)
   - APNs Certificate: 앱별 발급, 1년 만료

3. **새 Provisioning Profile 생성**
   - Wildcard가 아닌 해당 App ID 기반의 명시적 프로파일 생성
   - Distribution 프로파일(App Store/Ad Hoc) 선택

4. **Xcode에서 capability 추가**
   - Signing & Capabilities → Push Notifications 추가
   - `Runner.entitlements`에 `aps-environment: production` 자동 추가됨

5. **Firebase Messaging 또는 flutter_local_notifications 패키지 설정**

### flutter_local_notifications 없이 FCM만 쓸 때

`firebase_messaging` 패키지만 사용하는 경우에도 APNs 설정은 필수다. Firebase Cloud Messaging(FCM)은 iOS에서 APNs를 백엔드로 사용하기 때문이다. Firebase Console에서 APNs Key를 등록해두지 않으면 FCM 메시지가 iOS 기기에 도달하지 않는다.

---

## 디버깅 팁

### entitlements 불일치 오류의 일반적인 패턴

비슷한 오류가 다른 entitlement 키에서도 발생할 수 있다.

| 오류 키 | 원인 | 해결 |
|---|---|---|
| `aps-environment` | Push Notifications capability 잔재 | 키 삭제 또는 명시적 프로파일 사용 |
| `com.apple.developer.icloud-container-identifiers` | iCloud capability 잔재 | 키 삭제 또는 iCloud 지원 프로파일 사용 |
| `com.apple.security.application-groups` | App Groups 잔재 | App Groups 지원 프로파일 사용 |

### 빌드 전 entitlements 파일 점검 체크리스트

```bash
# 현재 entitlements 파일 내용 확인
cat ios/Runner/Runner.entitlements

# 사용 중인 프로비저닝 프로파일 확인 (Xcode 빌드 로그에서)
# 또는 직접 확인
ls ~/Library/MobileDevice/Provisioning\ Profiles/
```

provisioning profile 파일(`.mobileprovision`)은 바이너리 형식이지만 `security` 명령으로 내용을 확인할 수 있다.

```bash
security cms -D -i ~/Library/MobileDevice/Provisioning\ Profiles/YOUR_PROFILE.mobileprovision
```

출력 XML에서 `<key>Entitlements</key>` 섹션을 찾아 `aps-environment` 키가 포함되어 있는지 확인한다. 포함되어 있지 않다면 해당 프로파일은 Push Notifications를 지원하지 않는다는 의미다.

---

## 정리

| 상황 | 처리 방법 |
|---|---|
| Push 미구현, Wildcard 프로파일 | `aps-environment` 키 삭제 |
| Push 구현, 명시적 App ID 프로파일 | `aps-environment: production` 유지 |
| 개발 중 시뮬레이터 테스트 | `aps-environment: development` |
| CI/CD 자동 배포 | App Store Connect API Key 사용 |

entitlements 파일은 Xcode UI 조작으로 자동 변경되는 경우가 많아서 빌드 오류 시 이 파일을 먼저 확인하는 것이 좋다. 특히 패키지를 추가하거나 제거한 후, 또는 Signing & Capabilities 탭에서 뭔가를 건드린 후에 갑자기 빌드가 깨지면 `.entitlements` 파일의 내용을 점검하자.

---

## Key Takeaways

- `aps-environment` 키는 Push Notifications capability가 포함된 **명시적 App ID 기반 프로비저닝 프로파일**에서만 유효하다. Wildcard 프로파일과 함께 쓰면 아카이브 단계에서 실패한다.
- Xcode에서 Push Notifications capability를 **제거해도** `.entitlements` 파일의 `aps-environment` 키는 자동으로 삭제되지 않는다. 파일을 직접 열어 수동으로 제거해야 한다.
- Push Notifications를 아직 구현하지 않았다면, entitlements 파일에서 해당 키를 삭제하는 것이 가장 빠른 해결책이다.
- Push Notifications를 실제로 구현할 때는 Apple Developer Console에서 App ID 설정 → APNs Key 발급 → 명시적 프로파일 생성 → Xcode capability 추가의 순서를 지켜야 한다.
- `firebase_messaging`을 사용하는 경우도 APNs 설정은 필수이며, Firebase Console에 APNs Key를 등록해야 FCM 메시지가 iOS에서 작동한다.
- 빌드 오류가 발생하면 `ios/Runner/Runner.entitlements` 파일과 사용 중인 프로비저닝 프로파일의 Entitlements 섹션을 대조해보는 것이 근본 원인 파악에 도움이 된다.
