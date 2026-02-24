---
title: "Flutter TestFlight 빌드 오류: Push Notifications 엔트리포인트 문제"
date: 2026-02-24
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "배포"]
description: "Flutter iOS 앱을 TestFlight에 올리다 마주친 provisioning profile / aps-environment 오류 해결 과정"
---

Flutter 앱을 TestFlight에 처음 올려보면서 겪은 빌드 오류와 해결 과정을 정리한다.

---

## 오류 상황

`flutter build ipa --release` 후 xcrun altool로 업로드를 시도하자 업로드 자체가 아니라 **빌드 단계**에서 Xcode 아카이브가 실패했다.

```
error: Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the aps-environment entitlement.
```

업로드 커맨드:

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "$APPLE_ID" \
  --password "$APPLE_APP_PASSWORD"
```

---

## 원인

`ios/Runner/Runner.entitlements` 파일에 아래 항목이 들어가 있었다.

```xml
<key>aps-environment</key>
<string>production</string>
```

이 키는 **Push Notifications 기능을 활성화한 Provisioning Profile**에서만 허용된다. Wildcard(`*`) 프로비저닝 프로파일은 Push Notifications을 지원하지 않기 때문에 아카이브 시점에 충돌이 발생한다.

### 언제 이 키가 생기나?

Xcode에서 **Signing & Capabilities** 탭에서 Push Notifications를 한 번이라도 추가하면 자동으로 entitlements 파일에 기록된다. 이후 기능을 제거해도 파일은 그대로 남는다.

---

## 해결

Push Notifications를 아직 구현하지 않은 단계라면 `Runner.entitlements`에서 해당 키를 삭제한다.

```xml
<!-- 삭제 전 -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist ...>
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
</plist>

<!-- 삭제 후 -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist ...>
<plist version="1.0">
<dict>
</dict>
</plist>
```

이후 다시 빌드하면 정상 통과된다.

---

## xcrun altool로 TestFlight 업로드

Apple Developer 계정의 **앱 암호(App-Specific Password)**를 사용한다.

```bash
# 앱 암호 생성: https://appleid.apple.com → 앱 암호 생성
# 형식: xxxx-xxxx-xxxx-xxxx

xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx"
```

업로드 성공 시 아래와 같이 출력된다.

```
No errors uploading archive at 'build/ios/ipa/app.ipa'.
```

Delivery UUID가 발급되며, 보통 수 분 내로 App Store Connect → TestFlight에서 빌드가 처리된다.

---

## Push Notifications를 나중에 추가할 때

실제로 Push Notifications를 구현할 때가 되면:

1. Apple Developer Console에서 **APNs Key** 또는 **APNs Certificate** 발급
2. 앱 ID(App Identifier)에서 Push Notifications 기능 활성화
3. 해당 App ID로 새 Provisioning Profile 생성 (Wildcard 아님)
4. `Runner.entitlements`에 `aps-environment` 키 재추가

Wildcard 프로파일 대신 **명시적 App ID 프로파일**을 사용해야 한다.

---

## 정리

| 상황 | 처리 방법 |
|---|---|
| Push 미구현, Wildcard 프로파일 | `aps-environment` 키 삭제 |
| Push 구현, 명시적 App ID 프로파일 | `aps-environment: production` 유지 |
| 개발 중 시뮬레이터 테스트 | `aps-environment: development` |

entitlements 파일은 Xcode UI 조작으로 자동 변경되는 경우가 많아서 빌드 오류 시 이 파일을 먼저 확인하는 것이 좋다.
