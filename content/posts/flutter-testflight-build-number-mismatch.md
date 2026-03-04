---
title: "Flutter TestFlight 빌드 번호 불일치: pubspec.yaml +9인데 TestFlight에서 빌드 11로 표시되는 이유"
date: 2026-02-25
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "빌드번호", "CFBundleVersion"]
description: "pubspec.yaml에 +9로 설정했는데 TestFlight에서 빌드 11로 표시되는 이유와, 이후 빌드 번호 관리를 일치시키는 방법을 정리한다."
---

Flutter iOS 앱을 TestFlight에 업로드했을 때 `pubspec.yaml`에 설정한 빌드 번호와 TestFlight에 표시되는 빌드 번호가 다른 경우가 있다. 예를 들어 `version: 1.0.1+9`로 설정했는데 TestFlight에서는 빌드 11로 표시된다.

---

## 왜 빌드 번호가 달라지는가

Flutter의 빌드 번호 흐름:

```
pubspec.yaml version: 1.0.1+9
        ↓
flutter build ios --no-codesign
        ↓
CFBundleVersion = 9 (Runner.app)
        ↓
xcodebuild archive -allowProvisioningUpdates
        ↓
Xcode 자동 서명 과정에서 App Store Connect 최신 빌드 번호 조회
        ↓
최신 빌드가 10이면 → CFBundleVersion을 11로 덮어씀
        ↓
TestFlight에는 빌드 11로 업로드됨
```

`xcodebuild`에 `-allowProvisioningUpdates` 옵션을 주면 Xcode가 App Store Connect API를 통해 자동 서명을 처리하는데, 이 과정에서 **이미 업로드된 빌드 번호와 충돌을 피하기 위해 CFBundleVersion을 자동으로 증가**시킨다.

Apple은 같은 버전(CFBundleShortVersionString) 내에서 빌드 번호가 이전보다 커야 업로드를 허용하기 때문에, Xcode가 안전하게 최신 번호 + 1로 설정한다.

---

## 빌드 번호 확인 방법

업로드 후 실제 빌드 번호는 아래 방법으로 확인할 수 있다.

**1. App Store Connect 활동 내역 확인**

App Store Connect → 앱 선택 → TestFlight → 빌드 목록에서 실제 번호 확인

**2. altool 업로드 로그 확인**

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

업로드 성공 후 TestFlight 빌드 목록에서 실제 번호를 확인한다.

---

## pubspec.yaml 번호 맞추기

TestFlight에서 빌드 11로 올라갔다면 pubspec.yaml도 +11로 맞춰야 다음 빌드가 정확히 +12로 증가한다.

```yaml
# 업로드 후 실제 TestFlight 번호로 맞춤
version: 1.0.1+11
```

자동 증분 스크립트를 사용하는 경우:

```bash
#!/bin/bash
# increment-build-number.sh
PUBSPEC="$1"
VERSION_NAME=$(grep '^version:' "$PUBSPEC" | sed 's/version: *//;s/+.*//')
BUILD_NUMBER=$(grep '^version:' "$PUBSPEC" | sed 's/.*+//')
NEW_BUILD_NUMBER=$((BUILD_NUMBER + 1))
sed -i '' "s/^version: .*/version: ${VERSION_NAME}+${NEW_BUILD_NUMBER}/" "$PUBSPEC"
echo "Build: ${BUILD_NUMBER} -> ${NEW_BUILD_NUMBER}"
```

스크립트가 +9 → +10으로 올리더라도 Xcode가 또 덮어쓸 수 있으므로, **업로드 후 실제 TestFlight 번호를 확인하고 pubspec.yaml을 그 번호로 수동 동기화**하는 것이 안전하다.

---

## 정리

| 항목 | 값 |
|------|-----|
| pubspec.yaml | `version: 1.0.1+9` |
| Flutter 빌드 후 CFBundleVersion | `9` |
| App Store Connect 최신 빌드 | `10` |
| Xcode 자동 조정 후 CFBundleVersion | `11` |
| TestFlight 표시 빌드 번호 | **11** |

Apple이 빌드 번호를 자동 변경하는 것이 아니라, **`-allowProvisioningUpdates` 옵션과 함께 xcodebuild가 자동 서명하는 과정에서 충돌 방지를 위해 번호를 올린다.** 업로드 후 실제 번호를 확인하고 소스를 맞춰두는 습관이 필요하다.
