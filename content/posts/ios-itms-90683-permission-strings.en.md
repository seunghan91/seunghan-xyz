---
title: "App Store Connect ITMS-90683: Missing Info.plist Permission Purpose String Error Fix"
date: 2025-08-27
draft: true
tags: ["Flutter", "iOS", "App Store Connect", "TestFlight", "Info.plist", "Permissions"]
description: "How to fix ITMS-90683 error emails after TestFlight upload. Handling missing permission description strings like NSPhotoLibraryUsageDescription, NSCameraUsageDescription."
cover:
  image: "/images/og/ios-itms-90683-permission-strings.png"
  alt: "Ios Itms 90683 Permission Strings"
  hidden: true
---

After uploading an IPA to TestFlight, you receive an email from App Store Connect a few minutes later.

```
ITMS-90683: Missing purpose string in Info.plist
The app's Info.plist file is missing a required purpose string for
one or more of the following API categories: NSPhotoLibraryUsageDescription
```

The upload itself succeeded, but Apple automatically scans the binary before distribution and sends this email when it detects missing declarations. If not fixed, the app will be rejected during App Store review — not just warned. This article explains what triggers the error, how to fix it correctly, and how to avoid common mistakes that cause rejection even after adding the strings.

---

## Why This Error Occurs

iOS enforces a privacy-first policy through the permission system. Every sensitive API — camera, photo library, microphone, location, contacts, and more — requires a human-readable explanation string in `Info.plist`. When the system prompts the user for permission, this string appears in the dialog. Apple's automated binary analysis tool, run on every upload to App Store Connect, verifies that these strings exist whenever it detects usage of the corresponding API entitlements in the binary.

The key nuance that catches many developers off guard: **you do not need to call the API yourself**. If any dependency in your app's dependency tree links against a framework that uses a protected API, the binary will contain references to that API, and Apple's scanner will flag the missing purpose string regardless of whether your code ever triggers the permission at runtime.

This is especially common in Flutter apps, where packages like `image_picker`, `file_picker`, `photo_view`, `camera`, `geolocator`, or `local_auth` pull in native iOS frameworks that reference protected APIs. Even if you use `file_picker` only for PDFs and never touch photos, the package's native code touches `PHPhotoLibrary`, so `NSPhotoLibraryUsageDescription` becomes required.

---

## How Apple Detects the Violation

When you upload an IPA, App Store Connect processes the binary through a static analysis pipeline. This pipeline:

1. Disassembles the Mach-O binary and inspects linked frameworks.
2. Checks for usage of privacy-sensitive APIs (camera capture, CoreLocation, Contacts, etc.).
3. Cross-references those usages against the `Info.plist` entries in the IPA bundle.
4. Sends an automated email for each missing purpose string.

The email typically arrives within 5–10 minutes of upload. The build still appears in TestFlight, but it carries a warning state and cannot be promoted to App Store submission until all violations are resolved.

---

## Fix: Add Purpose Strings to Info.plist

Add the corresponding keys and description strings to `ios/Runner/Info.plist`. The string value must be a meaningful, user-facing explanation — Apple reviewers read these and will reject vague placeholders like "We need this permission."

```xml
<!-- ios/Runner/Info.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <!-- Existing settings ... -->

    <!-- Photo library read permission -->
    <key>NSPhotoLibraryUsageDescription</key>
    <string>Access to the photo library is needed to attach documents and upload profile photos.</string>

    <!-- Photo library save permission (when download feature exists) -->
    <key>NSPhotoLibraryAddUsageDescription</key>
    <string>Access is needed to save downloaded files to your photo library.</string>

    <!-- Camera permission -->
    <key>NSCameraUsageDescription</key>
    <string>Camera access is needed to take photos and scan documents for upload.</string>

    <!-- Microphone permission -->
    <key>NSMicrophoneUsageDescription</key>
    <string>Microphone access is needed to record audio messages.</string>

</dict>
</plist>
</dict>
```

Write strings that are specific enough to pass review. Generic strings like "Required for app functionality" are a common rejection reason under Apple guideline 5.1.1. Describe the actual feature the user will experience.

---

## Complete Purpose String Reference

| Key | Protected Resource | Commonly Triggered By |
|-----|-------------------|----------------------|
| `NSPhotoLibraryUsageDescription` | Photo library (read) | image_picker, file_picker, photo_view |
| `NSPhotoLibraryAddUsageDescription` | Photo library (write/save) | image_gallery_saver, share_plus |
| `NSCameraUsageDescription` | Camera | image_picker, camera, qr_code_scanner |
| `NSMicrophoneUsageDescription` | Microphone | audio_recorder, video recording, record |
| `NSLocationWhenInUseUsageDescription` | Location (foreground) | geolocator, google_maps, mapbox |
| `NSLocationAlwaysAndWhenInUseUsageDescription` | Location (background) | background_geolocation |
| `NSLocationAlwaysUsageDescription` | Location (legacy background) | older geolocator versions |
| `NSContactsUsageDescription` | Contacts | contacts_service, flutter_contacts |
| `NSCalendarsUsageDescription` | Calendars | add_2_calendar, device_calendar |
| `NSFaceIDUsageDescription` | Face ID / biometrics | local_auth |
| `NSBluetoothAlwaysUsageDescription` | Bluetooth | flutter_blue, flutter_reactive_ble |
| `NSBluetoothPeripheralUsageDescription` | Bluetooth peripheral | older flutter_blue versions (iOS 12) |
| `NSMotionUsageDescription` | Motion / accelerometer | sensors_plus |
| `NSHealthShareUsageDescription` | HealthKit (read) | health |
| `NSHealthUpdateUsageDescription` | HealthKit (write) | health |
| `NSSpeechRecognitionUsageDescription` | Speech recognition | speech_to_text |
| `NSRemindersUsageDescription` | Reminders | flutter_local_notifications (some configs) |

---

## How to Identify Which Permissions Your App Needs

### Method 1: Check package documentation

The fastest approach is to read the "iOS Setup" or "Permissions" section of each package's README on pub.dev. Most well-maintained packages explicitly list which `Info.plist` keys are required.

### Method 2: Scan Xcode build logs

After building the app, search the build output for usage description warnings:

```bash
# Scan Xcode build output for permission-related messages
xcodebuild -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  build 2>&1 | grep -i "usage description"
```

### Method 3: Inspect the current Info.plist

Check which keys are already declared:

```bash
# List all UsageDescription keys already in Info.plist
/usr/libexec/PlistBuddy -c "Print" ios/Runner/Info.plist | grep "UsageDescription"
```

### Method 4: Audit linked frameworks in the IPA

For a deeper audit, unzip the IPA and use `otool` to inspect linked libraries:

```bash
unzip -o build/ios/ipa/YourApp.ipa -d /tmp/ipa_inspect
otool -L /tmp/ipa_inspect/Payload/Runner.app/Runner | grep -E "Photos|Camera|CoreLocation|Contacts|CoreMotion|HealthKit|CoreBluetooth|Speech"
```

Any framework listed there that maps to a protected API category will require a corresponding purpose string.

---

## Checking for Violations After Upload

After a successful TestFlight upload:

1. Go to App Store Connect → Your App → TestFlight → Builds.
2. Look for a yellow warning icon or "Missing Compliance" label next to the build.
3. Click the build to see the detailed violation list.

The email notification typically arrives faster, but the web UI gives the full structured list of all violations in one place — useful when multiple purpose strings are missing simultaneously.

---

## Caution: Declaring Permissions You Do Not Use

Adding a purpose string without the corresponding feature in the app is a rejection risk. Apple guideline 5.1.1 (Data Collection and Storage) requires that apps only request permissions they actually use, and reviewers test this during review.

A practical example: `file_picker` internally references `PHPhotoLibrary` to allow photo selection, so `NSPhotoLibraryUsageDescription` is genuinely required. However, if your app has no camera-facing feature and you add `NSCameraUsageDescription` pre-emptively "just in case," a reviewer who finds no camera UI in the app can reject it under 5.1.1.

The correct approach is to audit each package's native implementation, confirm it actually triggers the permission at runtime for a feature your app exposes, and only then add the string.

---

## Fix and Re-upload Flow

```
1. Identify missing keys from the ITMS-90683 email
           |
2. Add keys + meaningful description strings to ios/Runner/Info.plist
           |
3. Increment build number (CFBundleVersion) in pubspec.yaml or Info.plist
           |
4. Rebuild the IPA
           make testflight
           (or: flutter build ipa --release && xcrun altool --upload-app ...)
           |
5. UPLOAD SUCCEEDED
           |
6. Wait 5-10 minutes — no email from App Store Connect = clean
```

One critical point: re-uploading with the same build number is rejected outright. App Store Connect does not replace existing builds. Even if the only change is adding a purpose string, you must increment `CFBundleVersion` before re-uploading.

If you use a `Makefile` target like `make testflight`, ensure the version bump is part of the build step or handle it manually in `pubspec.yaml` before running the command.

---

## Flutter-Specific: project.yml and XcodeGen

If your Flutter project uses XcodeGen with a `project.yml` file to manage the Xcode project, **do not edit `Info.plist` directly**. The `Info.plist` is regenerated from `project.yml` every time you run `make gen-ios` or `xcodegen generate`. Changes made directly to `Info.plist` will be overwritten.

Instead, declare the purpose strings in `project.yml` under the target's `info` block:

```yaml
targets:
  Runner:
    info:
      path: ios/Runner/Info.plist
      properties:
        NSPhotoLibraryUsageDescription: "Access to the photo library is needed to attach documents and upload profile photos."
        NSCameraUsageDescription: "Camera access is needed to take photos and scan documents for upload."
        NSMicrophoneUsageDescription: "Microphone access is needed to record audio messages."
```

Then regenerate the Xcode project:

```bash
make gen-ios
# or: xcodegen generate
```

This ensures your purpose strings survive future project regeneration.

---

## Key Takeaways

- ITMS-90683 fires when a binary references a protected iOS API but `Info.plist` lacks the corresponding purpose string — even if your own code never calls that API directly.
- Transitive dependencies (Flutter packages) are the most common cause. Audit `pubspec.yaml` dependencies against the purpose string table above.
- Purpose strings must be meaningful and feature-specific. Vague strings ("Required for app functionality") are a rejection risk under Apple guideline 5.1.1.
- Do not pre-emptively add purpose strings for permissions your app does not use. Apple reviewers test this.
- Always increment the build number before re-uploading, even for Info.plist-only changes.
- If using XcodeGen (`project.yml`), add purpose strings there, not directly in `Info.plist`.
- After re-upload, wait 5–10 minutes. No email from App Store Connect means the binary passed the automated scan.
