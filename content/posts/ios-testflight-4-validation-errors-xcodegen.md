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

업로드 자체는 성공했지만 4가지 검증 오류가 동시에 떴다. 각 에러 코드의 의미와 xcodegen 프로젝트에서 정확히 어떤 설정이 빠져 있었는지 하나씩 기록한다.

---

## 배경: xcodegen이란

xcodegen은 `project.yml` 파일을 기반으로 `.xcodeproj`를 자동 생성하는 도구다. `.xcodeproj` 파일을 git에 커밋하지 않아도 되고, 팀원이나 CI 환경에서 동일한 Xcode 프로젝트를 재현할 수 있다는 장점이 있다.

문제는 Xcode GUI에서 설정하면 자동으로 처리되는 항목들을 xcodegen에서는 `project.yml`에 명시적으로 기술해야 한다는 점이다. 이 차이를 모르면 로컬 빌드는 성공하고 TestFlight 검증에서만 실패하는 상황을 맞닥뜨린다.

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

xcodegen은 sources 경로 아래의 파일만 Xcode 프로젝트에 포함시킨다. `Assets.xcassets`가 sources 범위 밖에 있으면 빌드 결과물인 `.app` 번들에 아이콘 에셋이 들어가지 않는다. 이 상태로 App Store Connect에 업로드하면 ITMS-90704, ITMS-90905 에러가 함께 발생한다.

---

## 해결 1: Assets.xcassets 올바른 위치로 이동

```bash
mv ios/Sources/Assets.xcassets ios/MyApp/Assets.xcassets
```

sources 경로(`MyApp/`) 안에 있어야 xcodegen이 인식한다.

이동 후 `xcodegen generate`를 다시 실행해야 변경 사항이 `.xcodeproj`에 반영된다. Xcode에서 직접 파일을 드래그해 추가하는 방식은 xcodegen 프로젝트에서 의미가 없다. 다음 번 `xcodegen generate` 실행 시 반영되지 않은 변경 사항은 날아간다. 항상 `project.yml`을 소스 오브 트루스로 관리해야 한다.

### 디렉토리 구조 예시

```
ios/
  MyApp/
    Assets.xcassets/         ← 여기 있어야 함
      AppIcon.appiconset/
        Contents.json
        icon_120x120.png
        icon_180x180.png
        ...
    Info.plist
    AppDelegate.swift
    ...
  project.yml
```

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

### 두 설정의 역할 차이

| 키 | 위치 | 역할 |
|---|---|---|
| `ASSETCATALOG_COMPILER_APPICON_NAME` | Build Settings | 컴파일러가 asset catalog에서 어떤 아이콘 세트를 빌드에 포함할지 지정 |
| `CFBundleIconName` | Info.plist | 런타임에 시스템이 번들에서 아이콘을 찾을 때 참조하는 키 |

Xcode GUI에서 프로젝트를 만들면 두 값이 연동되어 자동으로 채워지지만, xcodegen은 Build Settings와 Info.plist를 독립적으로 관리하기 때문에 둘 다 명시해야 한다.

ITMS-90905는 App Store Connect가 업로드된 번들의 Info.plist에서 `CFBundleIconName` 키를 찾지 못할 때 발생한다. 키가 없으면 시스템이 앱 아이콘을 어떤 에셋 이름으로 로드해야 하는지 알 수 없다.

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

### 왜 iPhone 전용 앱인데 iPad 오리엔테이션이 필요한가

App Store는 iPhone 전용 앱이더라도 iPad에서 실행할 수 있도록 허용한다(Compatibility Mode). iPad에서 iPhone 앱을 멀티태스킹 환경에서 실행할 때 시스템은 `UISupportedInterfaceOrientations~ipad` 키를 참조한다. 이 키가 없거나 4가지 오리엔테이션이 모두 포함되지 않으면 ITMS-90474 오류가 발생한다.

Info.plist에서 `~ipad` suffix는 플랫폼별 오버라이드(platform-specific override)를 의미한다. xcodegen의 `project.yml`에서도 동일한 문법이 지원된다.

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

### Contents.json 검증 방법

아이콘 스크립트를 실행한 뒤 `Contents.json`의 모든 항목에 `filename` 필드가 있는지 확인한다. 파일이 존재하지 않는 항목은 `filename`이 없거나 빈 문자열로 남는다.

```json
{
  "images": [
    {
      "size": "60x60",
      "idiom": "iphone",
      "scale": "2x",
      "filename": "icon_120x120.png"   // 이 필드가 있어야 함
    }
  ]
}
```

누락된 사이즈가 있으면 ITMS-90704가 발생하며, 어떤 사이즈가 없는지 에러 메시지에서 정확히 알려준다.

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

`xcodebuild`는 현재 디렉토리를 기준으로 상대경로를 해석하지 않는 경우가 있다. `$(PWD)`를 사용해 항상 절대경로로 변환해서 전달하는 것이 안전하다. CI 환경에서는 `$(CURDIR)` 또는 `$(shell pwd)`를 사용하는 패턴도 동일하게 작동한다.

---

## ExportOptions.plist 주의사항

`xcodebuild -exportArchive`에 사용하는 `ExportOptions.plist`에도 주의할 점이 있다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <!-- iCloud를 사용하지 않으면 아래 키 넣지 말 것 -->
    <!-- <key>iCloudContainerEnvironment</key> -->
    <!-- <string>Production</string> -->
</dict>
</plist>
```

`iCloudContainerEnvironment` 키는 iCloud를 실제로 사용하는 앱에서만 포함해야 한다. 사용하지 않는 앱에 이 키를 넣으면 업로드 단계에서 별도의 오류가 발생한다.

---

## 오류 코드 빠른 참조

| 코드 | 원인 | 해결 |
|---|---|---|
| ITMS-90704 | 번들에 특정 해상도 아이콘 없음 | Assets.xcassets 위치 확인, Contents.json 사이즈 목록 확인 |
| ITMS-90905 | Info.plist에 CFBundleIconName 없음 | project.yml info.properties에 명시 |
| ITMS-90474 | iPad 멀티태스킹 오리엔테이션 불완전 | `~ipad` suffix로 4가지 오리엔테이션 모두 추가 |

---

## Key Takeaways

- xcodegen은 Xcode GUI와 달리 Build Settings와 Info.plist 값을 자동으로 연동하지 않는다. `ASSETCATALOG_COMPILER_APPICON_NAME`과 `CFBundleIconName` 둘 다 명시해야 한다.
- `Assets.xcassets`는 반드시 `project.yml`의 sources 경로 안에 위치해야 한다. sources 범위 밖이면 빌드 번들에 포함되지 않는다.
- iPhone 전용 앱이더라도 App Store 제출 시 `UISupportedInterfaceOrientations~ipad`에 4가지 오리엔테이션을 모두 넣어야 ITMS-90474가 발생하지 않는다.
- `xcodegen generate`는 `project.yml`을 변경한 뒤 항상 다시 실행해야 `.xcodeproj`에 반영된다.
- `authenticationKeyPath`는 절대경로로 전달해야 한다. Makefile에서는 `$(PWD)`를 활용한다.
- 이 4가지를 모두 잡고 나면 `UPLOAD SUCCEEDED with no errors`가 뜬다.
