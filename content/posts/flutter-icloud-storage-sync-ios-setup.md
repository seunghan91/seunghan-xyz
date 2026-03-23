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

`icloud_storage_sync` 패키지는 코드만 추가한다고 되지 않는다. iOS 실기기에서 동작하려면 세 가지 설정이 모두 맞아야 한다. 하나라도 빠지면 시뮬레이터에서는 멀쩡하다가 실기기에서 크래시가 난다. 이 글은 그 세 가지 설정과 각각 누락 시 발생하는 증상, 디버깅 방법, 그리고 재발 방지 체크리스트를 다룬다.

---

## 왜 이렇게 복잡한가 — 근본 원인

iCloud 연동은 Apple의 **entitlement 기반 권한 시스템** 위에서 동작한다. 앱이 iCloud 컨테이너에 접근하려면:

1. 앱 바이너리에 **entitlements** 서명이 있어야 하고
2. Apple Developer Portal의 **App ID**에 iCloud capability가 활성화되어 있어야 하며
3. 그 App ID로 발급된 **provisioning profile**이 기기에 설치되어야 한다

Flutter 프로젝트에서는 여기에 한 가지가 추가된다. Dart 코드에서 넘기는 `containerId` 문자열이 entitlements에 등록된 컨테이너 ID와 **정확히 일치**해야 한다. 이 네 개의 퍼즐 조각 중 하나라도 맞지 않으면 런타임 오류 또는 크래시로 이어진다.

시뮬레이터에서는 iCloud 접근 권한 검사를 건너뛰는 경우가 많아 문제가 드러나지 않는다. 실기기에서 처음 테스트할 때 갑자기 크래시가 터지는 이유가 여기 있다.

---

## 1. Runner.entitlements

`ios/Runner/Runner.entitlements` 파일에 iCloud 관련 키를 추가한다. 이 파일이 없으면 새로 생성한다.

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

`$(CFBundleIdentifier)`는 빌드 시 `Info.plist`의 번들 ID로 자동 치환된다. 예를 들어 번들 ID가 `com.example.myapp`이면 실제 서명에는 `iCloud.com.example.myapp`이 들어간다.

### entitlements 파일이 실제로 사용되는지 확인하는 방법

Xcode 프로젝트에서 entitlements 파일이 올바르게 연결되어 있는지 확인해야 한다.

1. Xcode에서 `Runner` 타겟 선택
2. **Build Settings** 탭
3. `Code Signing Entitlements` 항목 검색
4. 값이 `Runner/Runner.entitlements`로 설정되어 있는지 확인

이 경로가 비어 있거나 잘못 설정되어 있으면 entitlements 파일을 아무리 수정해도 빌드에 반영되지 않는다.

### 여러 scheme을 사용하는 경우

Debug/Release/Profile 각 빌드 설정에 개별적으로 entitlements 경로가 지정되는 경우가 있다. `Any iOS SDK` 외에 특정 설정 행에 다른 값이 있는지도 확인한다.

---

## 2. Xcode Capability 추가

entitlements 파일만 수정하면 Apple Developer Portal의 App ID와 동기화되지 않는다. **Xcode에서 직접 Capability를 추가해야 한다.**

1. Xcode에서 `Runner` 타겟 선택
2. **Signing & Capabilities** 탭
3. **+ Capability** 버튼 → `iCloud` 선택
4. **iCloud Documents** 체크
5. Containers 목록에 `iCloud.$(CFBundleIdentifier)` 확인

이 작업을 하면 Apple Developer Portal의 해당 App ID에 iCloud capability가 자동으로 활성화되고, provisioning profile이 갱신된다.

### 이 단계를 건너뛰면 어떻게 되나

entitlements 파일에 직접 키를 추가했더라도, Developer Portal의 App ID에 iCloud capability가 없으면 새 provisioning profile을 다운로드해도 iCloud 권한이 포함되지 않는다. 결과적으로 Archive 후 TestFlight나 App Store 배포 시 entitlements 불일치 오류가 발생한다.

```
error: Provisioning profile "..." doesn't include the "com.apple.developer.icloud-services" entitlement.
```

이 오류는 개발 빌드(직접 연결한 기기)에서는 Xcode가 자동으로 provisioning을 관리해줘서 보이지 않다가, 배포 시에 터지는 경우가 많다.

### Containers 목록이 비어 있는 경우

Capability를 추가했는데 Containers 목록이 비어 있거나 `iCloud.$(CFBundleIdentifier)`가 자동으로 추가되지 않는다면:

- Developer Portal에서 해당 App ID가 실제로 등록되어 있는지 확인한다.
- Xcode에서 **Automatically manage signing**이 켜져 있는지 확인한다.
- 수동으로 `+` 버튼을 눌러 컨테이너 ID를 직접 추가할 수도 있다.

---

## 3. containerId 형식

코드에서 사용하는 `containerId`는 반드시 `iCloud.` + 번들ID 형식이어야 한다.

```dart
// 잘못된 형식
await _iCloudSync!.upload(
  containerId: 'myapp.backup',  // 이 형식은 안 됨
  ...
);

// 올바른 형식
await _iCloudSync!.upload(
  containerId: 'iCloud.com.example.myapp',  // "iCloud." + 번들ID
  ...
);
```

번들 ID가 `com.example.myapp`이라면 containerId는 `iCloud.com.example.myapp`이다. entitlements의 `iCloud.$(CFBundleIdentifier)`와 일치해야 한다.

### containerId를 상수로 관리하는 패턴

프로젝트 전체에서 일관성을 유지하려면 containerId를 한 곳에서 관리하는 것이 좋다.

```dart
// lib/constants/storage_constants.dart
class StorageConstants {
  static const String iCloudContainerId = 'iCloud.com.example.myapp';
}

// 사용처
await _iCloudSync!.upload(
  containerId: StorageConstants.iCloudContainerId,
  ...
);
```

번들 ID가 바뀌거나 flavor를 사용하는 경우 이 상수 하나만 수정하면 된다.

### Flutter flavor 사용 시 주의사항

`flutter_flavorizr` 등으로 dev/staging/production flavor를 구분하면 각 flavor마다 번들 ID가 달라진다. 예를 들어:

- dev: `com.example.myapp.dev`
- production: `com.example.myapp`

이 경우 containerId도 flavor에 따라 달라져야 한다. 환경 변수 또는 Dart define으로 containerId를 주입하는 방식을 권장한다.

```dart
// --dart-define=ICLOUD_CONTAINER_ID=iCloud.com.example.myapp
const iCloudContainerId = String.fromEnvironment(
  'ICLOUD_CONTAINER_ID',
  defaultValue: 'iCloud.com.example.myapp',
);
```

---

## 설정 누락 시 증상과 디버깅

| 누락 항목 | 증상 | 디버깅 방법 |
|---|---|---|
| entitlements 권한 없음 | 실기기에서 크래시, 시뮬레이터는 정상 | Xcode Console에서 `entitlement` 키워드로 로그 확인 |
| Xcode Capability 미추가 | 배포 시 entitlements 불일치 오류 | Archive 후 Validate App 단계에서 오류 메시지 확인 |
| containerId 형식 오류 | 업로드/다운로드 시 런타임 오류 | `flutter run --verbose`로 Dart 스택 트레이스 확인 |
| entitlements 파일 경로 미설정 | 빌드는 성공하나 iCloud 접근 불가 | Build Settings > Code Signing Entitlements 확인 |

### 실기기 크래시 로그 보는 방법

1. Xcode → **Window** → **Devices and Simulators**
2. 해당 기기 선택 → **Open Console**
3. 앱 실행 후 크래시 발생 시 `NSUbiquityIdentityToken` 또는 `entitlement` 키워드로 필터링

또는 터미널에서:

```bash
flutter run --verbose 2>&1 | grep -i "icloud\|entitlement\|ubiquity"
```

### 가장 흔한 실수: 시뮬레이터에서만 테스트

시뮬레이터는 iCloud 권한 검사를 완전히 구현하지 않는다. `icloud_storage_sync`는 시뮬레이터에서 파일을 로컬 디렉토리에 저장하는 fallback을 사용하기도 한다. 반드시 **실기기에서 최종 테스트**를 해야 한다.

---

## 전체 체크리스트

- [ ] `Runner.entitlements`에 `com.apple.developer.icloud-services` 추가
- [ ] `Runner.entitlements`에 `com.apple.developer.ubiquity-container-identifiers` 추가
- [ ] Xcode Build Settings > `Code Signing Entitlements` 경로가 올바르게 설정됨
- [ ] Xcode Signing & Capabilities에서 iCloud Capability 추가
- [ ] iCloud Documents 체크됨
- [ ] Containers 목록에 `iCloud.$(CFBundleIdentifier)` 또는 실제 컨테이너 ID 확인
- [ ] containerId가 `iCloud.` + 번들ID 형식인가
- [ ] entitlements의 container ID와 코드의 containerId가 일치하는가
- [ ] 실기기에서 테스트 완료 (시뮬레이터 아님)
- [ ] flavor를 사용한다면 각 flavor별 containerId가 올바르게 분리되어 있는가

---

## Key Takeaways

- `icloud_storage_sync`는 entitlements, Xcode Capability, containerId 세 가지가 **동시에** 맞아야 실기기에서 동작한다.
- 시뮬레이터는 iCloud 권한 검사를 건너뛰기 때문에 실기기 테스트로만 검증할 수 있다.
- entitlements 파일을 직접 수정해도 Xcode Capability를 추가하지 않으면 배포 시 provisioning profile 불일치 오류가 발생한다.
- containerId는 반드시 `iCloud.` 접두사를 포함해야 하며, entitlements의 값과 정확히 일치해야 한다.
- Flutter flavor 환경에서는 각 flavor마다 containerId를 별도로 관리해야 한다.
- 상수 파일 또는 Dart define으로 containerId를 중앙 관리하면 실수를 줄일 수 있다.
