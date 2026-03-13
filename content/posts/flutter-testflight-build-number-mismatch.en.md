---
title: "Flutter TestFlight Build Number Mismatch: pubspec.yaml Says +9 but TestFlight Shows Build 11"
date: 2025-08-13
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Build Number", "CFBundleVersion"]
description: "Why pubspec.yaml set to +9 shows as build 11 in TestFlight, and how to keep build numbers consistent going forward."
cover:
  image: "/images/og/flutter-testflight-build-number-mismatch.png"
  alt: "Flutter Testflight Build Number Mismatch"
  hidden: true
---


When uploading a Flutter iOS app to TestFlight, the build number set in `pubspec.yaml` sometimes differs from what TestFlight displays. For example, you set `version: 1.0.1+9` but TestFlight shows build 11.

---

## Why the Build Number Differs

Flutter's build number flow:

```
pubspec.yaml version: 1.0.1+9
        |
flutter build ios --no-codesign
        |
CFBundleVersion = 9 (Runner.app)
        |
xcodebuild archive -allowProvisioningUpdates
        |
During Xcode automatic signing, queries latest build number from App Store Connect
        |
If latest build is 10 -> overwrites CFBundleVersion to 11
        |
Uploaded to TestFlight as build 11
```

When you pass the `-allowProvisioningUpdates` option to `xcodebuild`, Xcode handles automatic signing through the App Store Connect API. During this process, it **automatically increments CFBundleVersion to avoid conflicts with already uploaded build numbers**.

Apple requires that within the same version (CFBundleShortVersionString), the build number must be higher than the previous one for upload to be accepted. So Xcode safely sets it to the latest number + 1.

---

## How to Check the Build Number

After upload, the actual build number can be verified through the following methods.

**1. Check App Store Connect Activity**

App Store Connect -> Select app -> TestFlight -> Check actual number in build list

**2. Check altool Upload Log**

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

After a successful upload, check the actual number in the TestFlight build list.

---

## Syncing the pubspec.yaml Number

If TestFlight uploaded as build 11, pubspec.yaml should be updated to +11 so the next build correctly increments to +12.

```yaml
# Match to actual TestFlight number after upload
version: 1.0.1+11
```

If using an auto-increment script:

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

Even if the script increments +9 to +10, Xcode may overwrite it again. The safe approach is to **check the actual TestFlight number after upload and manually sync pubspec.yaml to that number**.

---

## Summary

| Item | Value |
|------|-----|
| pubspec.yaml | `version: 1.0.1+9` |
| CFBundleVersion after Flutter build | `9` |
| App Store Connect latest build | `10` |
| CFBundleVersion after Xcode auto-adjustment | `11` |
| TestFlight displayed build number | **11** |

It is not Apple that automatically changes the build number -- it is **xcodebuild incrementing the number during automatic signing with the `-allowProvisioningUpdates` option to prevent conflicts.** Make a habit of checking the actual number after upload and syncing the source accordingly.
