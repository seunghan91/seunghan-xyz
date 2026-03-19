---
title: "Flutter icloud_storage_sync iOS 설정 완전 가이드"
date: 2025-07-30
draft: true
tags: ["Flutter", "iCloud", "iOS", "entitlements", "Xcode"]
description: "icloud_storage_sync 패키지를 실기기에서 동작시키려면 entitlements, Xcode Capability, containerId 세 가지가 모두 맞아야 한다. 하나라도 빠지면 실기기에서 크래시."
cover:
  image: "/images/og/flutter-icloud-storage-sync-ios-setup.png"
  alt: "Flutter Icloud Storage Sync Ios Setup"
  hidden: true
---

`icloud_storage_sync` 패키지는 코드만 추가한다고 되지 않는다. iOS 실기기에서 동작하려면 세 가지 설정이 모두 맞아야 한다.

---

## 1. Runner.entitlements

`ios/Runner/Runner.entitlements` 파일에 iCloud 관련 키를 추가한다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.icloud-services</key>
    <array>
        <string>CloudDocuments</string>
    </array>
    <key>com.apple.developer.ubiquity-container-identifiers</key>
    <array>
        <string>iCloud.$(CFBundleIdentifier)</string>
    </array>
</dict>
</plist>
```

`$(CFBundleIdentifier)`는 빌드 시 `Info.plist`의 번들 ID로 자동 치환된다.

---

## 2. Xcode Capability 추가

entitlements 파일만 수정하면 Apple Developer Portal의 App ID와 동기화되지 않는다. **Xcode에서 직접 Capability를 추가해야 한다.**

1. Xcode에서 `Runner` 타겟 선택
2. **Signing & Capabilities** 탭
3. **+ Capability** 버튼 → `iCloud` 선택
4. **iCloud Documents** 체크
5. Containers 목록에 `iCloud.$(CFBundleIdentifier)` 확인

이 작업을 하면 Apple Developer Portal의 해당 App ID에 iCloud capability가 자동으로 활성화되고, provisioning profile이 갱신된다.

---

## 3. containerId 형식

코드에서 사용하는 `containerId`는 반드시 `iCloud.` + 번들ID 형식이어야 한다.

```dart
// ❌ 잘못된 형식
await _iCloudSync!.upload(
  containerId: 'myapp.backup',  // 이 형식은 안 됨
  ...
);

// ✅ 올바른 형식
await _iCloudSync!.upload(
  containerId: 'iCloud.com.example.myapp',  // "iCloud." + 번들ID
  ...
);
```

번들 ID가 `com.example.myapp`이라면 containerId는 `iCloud.com.example.myapp`이다. entitlements의 `iCloud.$(CFBundleIdentifier)`와 일치해야 한다.

---

## 설정 누락 시 증상

| 누락 항목 | 증상 |
|---|---|
| entitlements 권한 없음 | 실기기에서 크래시, 시뮬레이터는 정상 |
| Xcode Capability 미추가 | 배포 시 entitlements 불일치 오류 |
| containerId 형식 오류 | 업로드/다운로드 시 런타임 오류 |

세 가지가 모두 맞아야 실기기에서 정상 동작한다.

---

## 전체 체크리스트

- [ ] `Runner.entitlements`에 `com.apple.developer.icloud-services` 추가
- [ ] `Runner.entitlements`에 `com.apple.developer.ubiquity-container-identifiers` 추가
- [ ] Xcode Signing & Capabilities에서 iCloud Capability 추가
- [ ] iCloud Documents 체크됨
- [ ] containerId가 `iCloud.` + 번들ID 형식인가
- [ ] entitlements의 container ID와 코드의 containerId가 일치하는가
