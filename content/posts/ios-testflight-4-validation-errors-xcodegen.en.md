---
title: "iOS TestFlight Upload 4 Validation Errors — Complete Fix with xcodegen"
date: 2025-12-09
draft: true
tags: ["iOS", "TestFlight", "xcodegen", "App Store Connect", "altool"]
description: "Fixing 4 validation errors after altool upload: missing CFBundleIconName, no 120x120 icon, iPad multitasking orientation, and Assets.xcassets path issues, all in xcodegen project.yml."
cover:
  image: "/images/og/ios-testflight-4-validation-errors-xcodegen.png"
  alt: "Ios Testflight 4 Validation Errors Xcodegen"
  hidden: true
---


Right after a successful `xcrun altool --upload-app`, an email arrived from App Store Connect.

```
ITMS-90704: Missing Icon - The bundle does not contain an app icon for iPhone of exactly '120x120' pixels...
ITMS-90704: Missing Icon - The bundle does not contain an app icon for iPad of exactly '152x152' pixels...
ITMS-90905: Missing Info.plist value - CFBundleIconName
ITMS-90474: The orientations UIInterfaceOrientationPortrait were provided... you need to include all orientations to support iPad multitasking
```

4 errors at once. Here is the record of fixing them one by one.

---

## Cause Analysis

In the xcodegen-based project, the sources path in `project.yml` was the issue.

```yaml
# project.yml
targets:
  MyApp:
    sources:
      - path: MyApp      # <- Only this was included
```

`Assets.xcassets` was created under `Sources/`, but since sources only pointed to the `MyApp/` folder, **icons were not included in the build at all**.

---

## Fix 1: Move Assets.xcassets to the Correct Location

```bash
mv ios/Sources/Assets.xcassets ios/MyApp/Assets.xcassets
```

It must be inside the sources path (`MyApp/`) for xcodegen to recognize it.

---

## Fix 2: Add CFBundleIconName

It must be explicitly added to `info.properties` in `project.yml`.

```yaml
info:
  path: MyApp/Info.plist
  properties:
    CFBundleIconName: AppIcon      # <- Missing this causes ITMS-90905
```

Even if you add `ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon` to settings, `CFBundleIconName` does not automatically get added to Info.plist. Both are needed.

---

## Fix 3: iPad Multitasking Orientations

Setting only iPhone orientations causes errors when iPad multitasking support is required. You need to specify them separately with the `~ipad` suffix key.

```yaml
properties:
  UISupportedInterfaceOrientations:
    - UIInterfaceOrientationPortrait
  UISupportedInterfaceOrientations~ipad:       # <- iPad-specific
    - UIInterfaceOrientationPortrait
    - UIInterfaceOrientationPortraitUpsideDown
    - UIInterfaceOrientationLandscapeLeft
    - UIInterfaceOrientationLandscapeRight
```

Even for an iPhone app, all 4 orientations must be included in the `~ipad` key for the multitasking error to disappear.

---

## Fix 4: Verify AppIcon Sizes

When generating icons with a script like `apply_icon.py`, verify that no sizes are missing from `Contents.json`.

Key sizes required by TestFlight:
- iPhone: 120x120 (60pt @2x), 180x180 (60pt @3x)
- iPad: 152x152 (76pt @2x), 167x167 (83.5pt @2x)
- App Store: 1024x1024 (ios-marketing)

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

## Final project.yml Structure (Key Parts)

```yaml
targets:
  MyApp:
    type: application
    platform: iOS
    sources:
      - path: MyApp          # Assets.xcassets must be inside here
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

## Build -> Upload Flow

```bash
# 1. Regenerate Xcode project
cd ios && xcodegen generate

# 2. Archive
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

# 3. Export IPA
xcodebuild -exportArchive \
  -archivePath ios/build/MyApp.xcarchive \
  -exportPath ios/build/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID

# 4. TestFlight upload
xcrun altool --upload-app \
  --type ios \
  --file "ios/build/ipa/MyApp.ipa" \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

---

## Note: authenticationKeyPath Must Be an Absolute Path

Using a relative path in a Makefile causes `xcodebuild` to not find it.

```makefile
# Wrong
ASC_KEY_PATH = ios/secrets/AuthKey_XXXX.p8

# Correct
ASC_KEY_PATH = $(PWD)/ios/secrets/AuthKey_XXXX.p8
```

After fixing all 4 issues, `UPLOAD SUCCEEDED with no errors` appears.
