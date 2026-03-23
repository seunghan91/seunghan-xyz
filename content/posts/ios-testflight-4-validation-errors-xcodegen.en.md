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

The upload itself succeeded, but four validation errors fired at once. This post covers what each error code means and exactly which configuration was missing in the xcodegen project.

---

## Background: What Is xcodegen

xcodegen is a tool that generates `.xcodeproj` files from a `project.yml` configuration. The main benefit is that `.xcodeproj` does not need to be committed to version control — anyone on the team or any CI environment can reproduce an identical Xcode project from the YAML file.

The catch is that xcodegen requires you to explicitly declare everything in `project.yml` that Xcode would otherwise configure automatically through its GUI. If you are not aware of these differences, you end up in a situation where local builds succeed but TestFlight validation fails every time.

---

## Root Cause

In this xcodegen-based project, the sources path defined in `project.yml` was the culprit.

```yaml
# project.yml
targets:
  MyApp:
    sources:
      - path: MyApp      # <- Only this directory was included
```

`Assets.xcassets` had been placed under `Sources/`, but since the sources entry only pointed to the `MyApp/` folder, **the icon assets were never included in the build bundle at all**.

xcodegen only includes files found under the declared sources paths when generating the Xcode project. If `Assets.xcassets` falls outside that scope, it never makes it into the compiled `.app` bundle. Uploading that bundle to App Store Connect triggers ITMS-90704 and ITMS-90905 together.

---

## Fix 1: Move Assets.xcassets to the Correct Location

```bash
mv ios/Sources/Assets.xcassets ios/MyApp/Assets.xcassets
```

The asset catalog must be inside the sources path (`MyApp/`) for xcodegen to pick it up.

After moving it, run `xcodegen generate` again so the change is reflected in `.xcodeproj`. Dragging files into Xcode directly has no lasting effect on an xcodegen project — the next `xcodegen generate` call will overwrite anything not described in `project.yml`. Always treat `project.yml` as the single source of truth.

### Expected Directory Layout

```
ios/
  MyApp/
    Assets.xcassets/         <- Must be here
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

## Fix 2: Add CFBundleIconName

It must be explicitly added to `info.properties` in `project.yml`.

```yaml
info:
  path: MyApp/Info.plist
  properties:
    CFBundleIconName: AppIcon      # <- Missing this causes ITMS-90905
```

Even if you add `ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon` to the build settings section, `CFBundleIconName` does not automatically get written into Info.plist. Both entries are required.

### What Each Setting Does

| Key | Location | Purpose |
|---|---|---|
| `ASSETCATALOG_COMPILER_APPICON_NAME` | Build Settings | Tells the asset catalog compiler which icon set to include in the build |
| `CFBundleIconName` | Info.plist | Tells the system which asset name to look for at runtime when loading the app icon |

When you create a project through the Xcode GUI, these two values are wired together and filled in automatically. xcodegen manages Build Settings and Info.plist independently, so both must be declared explicitly.

ITMS-90905 fires when App Store Connect cannot find the `CFBundleIconName` key in the uploaded bundle's Info.plist. Without it, the system has no way to know which asset name to use when loading the app icon.

---

## Fix 3: iPad Multitasking Orientations

Setting only iPhone orientations triggers an error when iPad multitasking support is evaluated. The fix is to declare them separately using the `~ipad` suffix key.

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

Even for an iPhone-only app, all four orientations must be included in the `~ipad` key for the multitasking error to go away.

### Why an iPhone App Needs iPad Orientations

The App Store allows iPhone-only apps to run on iPad in Compatibility Mode. When an iPhone app runs in a multitasking environment on iPad, the system reads the `UISupportedInterfaceOrientations~ipad` key. If that key is absent or does not list all four orientations, ITMS-90474 is triggered.

The `~ipad` suffix in Info.plist is the standard platform-specific override mechanism. xcodegen supports the same syntax directly in `project.yml`, so no manual Info.plist editing is needed.

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

### Validating Contents.json

After running the icon script, inspect `Contents.json` to confirm every entry has a `filename` field. Any size that was not generated will either be missing the field or have an empty string.

```json
{
  "images": [
    {
      "size": "60x60",
      "idiom": "iphone",
      "scale": "2x",
      "filename": "icon_120x120.png"
    }
  ]
}
```

If any size is missing, ITMS-90704 will fire, and the error message will tell you exactly which resolution is absent.

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

## Build to Upload Flow

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

## authenticationKeyPath Must Be an Absolute Path

Using a relative path in a Makefile causes `xcodebuild` to fail silently when it cannot locate the key file.

```makefile
# Wrong
ASC_KEY_PATH = ios/secrets/AuthKey_XXXX.p8

# Correct
ASC_KEY_PATH = $(PWD)/ios/secrets/AuthKey_XXXX.p8
```

`xcodebuild` does not always resolve relative paths from the working directory. Using `$(PWD)` in a Makefile produces an absolute path reliably. In CI environments, `$(CURDIR)` or `$(shell pwd)` works the same way.

---

## ExportOptions.plist Notes

The `ExportOptions.plist` used with `xcodebuild -exportArchive` has its own pitfall worth noting.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <!-- Only include this key if the app actually uses iCloud -->
    <!-- <key>iCloudContainerEnvironment</key> -->
    <!-- <string>Production</string> -->
</dict>
</plist>
```

The `iCloudContainerEnvironment` key must only be present if the app genuinely uses iCloud. Including it in an app that does not use iCloud causes a separate upload error.

---

## Quick Error Reference

| Code | Cause | Fix |
|---|---|---|
| ITMS-90704 | Specific icon resolution missing from the bundle | Check Assets.xcassets location, verify Contents.json size list |
| ITMS-90905 | CFBundleIconName absent from Info.plist | Add to project.yml info.properties explicitly |
| ITMS-90474 | iPad multitasking orientations incomplete | Add all four orientations under the `~ipad` suffix key |

---

## Key Takeaways

- xcodegen does not automatically sync Build Settings and Info.plist values the way the Xcode GUI does. `ASSETCATALOG_COMPILER_APPICON_NAME` and `CFBundleIconName` must both be declared explicitly.
- `Assets.xcassets` must live inside the directory listed under the sources path in `project.yml`. If it falls outside that scope it will not be included in the build bundle.
- Even for an iPhone-only app, `UISupportedInterfaceOrientations~ipad` must list all four orientations to avoid ITMS-90474 on App Store submission.
- Run `xcodegen generate` every time you change `project.yml`. Changes to the YAML are not reflected in `.xcodeproj` until the project is regenerated.
- Pass `authenticationKeyPath` as an absolute path. Use `$(PWD)` in Makefiles to construct it reliably.
- Fix all four of these and the upload ends with `UPLOAD SUCCEEDED with no errors`.
