---
title: "iOS TestFlight 업로드 4가지 검증 오류 — xcodegen 프로젝트 완전 해결"
date: 2025-12-09
draft: true
tags: ["iOS", "TestFlight", "xcodegen", "App Store Connect", "altool"]
description: "altool 업로드 후 나오는 CFBundleIconName 누락, 120x120 아이콘 없음, iPad 멀티태스킹 오리엔테이션, Assets.xcassets 경로 문제 4가지를 xcodegen project.yml 기준으로 해결한 기록"
cover:
  image: "/images/og/ios-testflight-4-validation-errors-xcodegen.png"
  alt: "Ios Testflight 4 Validation Errors Xcodegen"
  hidden: true
---

`xcrun altool --upload-app` 성공 직후 App Store Connect에서 이메일이 왔다.

```
ITMS-90704: Missing Icon - The bundle does not contain an app icon for iPhone of exactly '120x120' pixels...
ITMS-90704: Missing Icon - The bundle does not contain an app icon for iPad of exactly '152x152' pixels...
ITMS-90905: Missing Info.plist value - CFBundleIconName
ITMS-90474: The orientations UIInterfaceOrientationPortrait were provided... you need to include all orientations to support iPad multitasking
```

4가지 오류가 한꺼번에. 하나씩 해결한 기록이다.

---

## 원인 분석

xcodegen 기반 프로젝트에서 `project.yml`의 sources 경로가 문제였다.

```yaml
# project.yml
targets:
  MyApp:
    sources:
      - path: MyApp      # ← 여기만 포함
```

`Assets.xcassets`를 `Sources/` 하위에 만들어뒀는데, sources가 `MyApp/` 폴더만 바라보고 있어서 **빌드에 아이콘이 아예 포함되지 않은 것**이었다.

---

## 해결 1: Assets.xcassets 올바른 위치로 이동

```bash
mv ios/Sources/Assets.xcassets ios/MyApp/Assets.xcassets
```

sources 경로(`MyApp/`) 안에 있어야 xcodegen이 인식한다.

---

## 해결 2: CFBundleIconName 추가

`project.yml`의 `info.properties`에 명시적으로 추가해야 한다.

```yaml
info:
  path: MyApp/Info.plist
  properties:
    CFBundleIconName: AppIcon      # ← 이걸 빠뜨리면 ITMS-90905
```

`ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon`을 settings에 넣어도 Info.plist에 `CFBundleIconName`이 자동으로 들어가지 않는다. 둘 다 필요하다.

---

## 해결 3: iPad 멀티태스킹 오리엔테이션

iPhone용 오리엔테이션만 설정하면 iPad 멀티태스킹 지원 시 오류가 난다. `~ipad` suffix key로 별도 지정해야 한다.

```yaml
properties:
  UISupportedInterfaceOrientations:
    - UIInterfaceOrientationPortrait
  UISupportedInterfaceOrientations~ipad:       # ← iPad 전용
    - UIInterfaceOrientationPortrait
    - UIInterfaceOrientationPortraitUpsideDown
    - UIInterfaceOrientationLandscapeLeft
    - UIInterfaceOrientationLandscapeRight
```

iPhone 앱이라도 이 4가지를 `~ipad` 키에 모두 넣어야 멀티태스킹 오류가 사라진다.

---

## 해결 4: AppIcon 사이즈 확인

`apply_icon.py` 같은 스크립트로 아이콘을 만들 때 `Contents.json`에 누락 사이즈가 없는지 확인한다.

TestFlight가 요구하는 주요 사이즈:
- iPhone: 120×120 (60pt @2x), 180×180 (60pt @3x)
- iPad: 152×152 (76pt @2x), 167×167 (83.5pt @2x)
- App Store: 1024×1024 (ios-marketing)

```python
IOS_SIZES = [
    {"size": 20,   "scale": 1, "idiom": "iphone"},
    {"size": 20,   "scale": 2, "idiom": "iphone"},
    {"size": 20,   "scale": 3, "idiom": "iphone"},
    {"size": 29,   "scale": 1, "idiom": "iphone"},
    {"size": 29,   "scale": 2, "idiom": "iphone"},
    {"size": 29,   "scale": 3, "idiom": "iphone"},
    {"size": 40,   "scale": 2, "idiom": "iphone"},
    {"size": 40,   "scale": 3, "idiom": "iphone"},
    {"size": 60,   "scale": 2, "idiom": "iphone"},   # 120x120
    {"size": 60,   "scale": 3, "idiom": "iphone"},   # 180x180
    {"size": 20,   "scale": 1, "idiom": "ipad"},
    {"size": 20,   "scale": 2, "idiom": "ipad"},
    {"size": 29,   "scale": 1, "idiom": "ipad"},
    {"size": 29,   "scale": 2, "idiom": "ipad"},
    {"size": 40,   "scale": 1, "idiom": "ipad"},
    {"size": 40,   "scale": 2, "idiom": "ipad"},
    {"size": 76,   "scale": 1, "idiom": "ipad"},
    {"size": 76,   "scale": 2, "idiom": "ipad"},     # 152x152
    {"size": 83.5, "scale": 2, "idiom": "ipad"},     # 167x167
    {"size": 1024, "scale": 1, "idiom": "ios-marketing"},
]
```

---

## 최종 project.yml 구조 (핵심 부분)

```yaml
targets:
  MyApp:
    type: application
    platform: iOS
    sources:
      - path: MyApp          # Assets.xcassets가 여기 안에 있어야 함
    info:
      path: MyApp/Info.plist
      properties:
        CFBundleIconName: AppIcon
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationPortrait
        UISupportedInterfaceOrientations~ipad:
          - UIInterfaceOrientationPortrait
          - UIInterfaceOrientationPortraitUpsideDown
          - UIInterfaceOrientationLandscapeLeft
          - UIInterfaceOrientationLandscapeRight
    settings:
      base:
        ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon
```

---

## 빌드 → 업로드 흐름

```bash
# 1. Xcode 프로젝트 재생성
cd ios && xcodegen generate

# 2. 아카이브
xcodebuild archive \
  -project ios/MyApp.xcodeproj \
  -scheme MyApp \
  -configuration Release \
  -archivePath ios/build/MyApp.xcarchive \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID \
  CODE_SIGN_STYLE=Automatic \
  DEVELOPMENT_TEAM=YOUR_TEAM_ID

# 3. IPA 추출
xcodebuild -exportArchive \
  -archivePath ios/build/MyApp.xcarchive \
  -exportPath ios/build/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID

# 4. TestFlight 업로드
xcrun altool --upload-app \
  --type ios \
  --file "ios/build/ipa/MyApp.ipa" \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

---

## 주의: authenticationKeyPath는 절대경로여야 한다

Makefile에서 상대경로로 쓰면 `xcodebuild`가 못 찾는다.

```makefile
# 잘못됨
ASC_KEY_PATH = ios/secrets/AuthKey_XXXX.p8

# 올바름
ASC_KEY_PATH = $(PWD)/ios/secrets/AuthKey_XXXX.p8
```

이 4가지를 잡고 나면 `UPLOAD SUCCEEDED with no errors`가 뜬다.
