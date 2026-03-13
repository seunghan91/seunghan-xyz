---
title: "App Store Connect ITMS-90683: Missing Info.plist Permission Purpose String Error Fix"
date: 2025-08-27
draft: false
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

The upload itself succeeded, but Apple automatically scans and sends this email before distribution. If not fixed, the app will be rejected during App Store review.

---

## Why This Error Occurs

iOS shows a permission popup to the user when accessing sensitive APIs like camera, photo library, or microphone. If the description text shown in this popup is missing from Info.plist, Apple treats it as an error.

Even if your app does not directly request the permission, **if a dependency package uses that API**, the purpose string is required. Packages like `file_picker`, `image_picker`, `photo_view` require the declaration regardless of whether the API is actually called.

---

## Fix: Add Purpose Strings to Info.plist

Add the corresponding keys and description strings to `ios/Runner/Info.plist`.

```xml
<!-- ios/Runner/Info.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <!-- Existing settings ... -->

    <!-- Photo library read permission -->
    <key>NSPhotoLibraryUsageDescription</key>
    <string>Access to the photo library is needed for document submission and profile photo upload.</string>

    <!-- Photo library save permission (when download feature exists) -->
    <key>NSPhotoLibraryAddUsageDescription</key>
    <string>Access is needed to save downloaded files to the photo library.</string>

    <!-- Camera permission -->
    <key>NSCameraUsageDescription</key>
    <string>Camera access is needed for taking photos and file uploads.</string>

</dict>
</plist>
```

---

## Common Purpose String List

| Key | Description | Related Packages |
|-----|-------------|-----------------|
| `NSPhotoLibraryUsageDescription` | Photo library read | image_picker, file_picker, photo_view |
| `NSPhotoLibraryAddUsageDescription` | Photo library save | image_gallery_saver, etc. |
| `NSCameraUsageDescription` | Camera | image_picker, camera |
| `NSMicrophoneUsageDescription` | Microphone | audio_recorder, video recording |
| `NSLocationWhenInUseUsageDescription` | Location (while in use) | geolocator, google_maps |
| `NSLocationAlwaysUsageDescription` | Location (background) | background_location |
| `NSContactsUsageDescription` | Contacts | contacts_service |
| `NSCalendarsUsageDescription` | Calendar | add_2_calendar, etc. |
| `NSFaceIDUsageDescription` | Face ID | local_auth |
| `NSBluetoothAlwaysUsageDescription` | Bluetooth | flutter_blue, etc. |

---

## How to Check Which Permissions Are Needed

The fastest way is to check the package README or the "iOS permissions" section on pub.dev. Alternatively, you can identify them from build warnings.

```bash
# Search for permission-related warnings in Xcode build logs
xcodebuild ... 2>&1 | grep -i "usage description"
```

Or compare against the list of keys already added in Info.plist.

```bash
# Check permission keys currently in Info.plist
/usr/libexec/PlistBuddy -c "Print" ios/Runner/Info.plist | grep "UsageDescription"
```

---

## Checking Warnings After Upload

After a successful TestFlight upload, check App Store Connect -> App -> TestFlight -> Build list for "Missing Compliance" or warning icons.

The email notification arrives too, but App Store Connect web provides more detailed information.

---

## Caution: Permissions Not Actually Used by the App

If you only add the purpose string without actually requesting that permission in the app, it may be rejected during review. According to Apple guideline 5.1.1, only permissions that are actually used should be declared.

If you implement file upload with `file_picker`, it internally accesses the photo library, so `NSPhotoLibraryUsageDescription` is legitimately needed. On the other hand, adding `NSCameraUsageDescription` when the camera is not used anywhere in the app may get caught during review.

---

## Fix -> Re-upload Flow

```
Add permission keys to Info.plist
        |
make testflight  (or flutter build ipa -> xcrun altool)
        |
UPLOAD SUCCEEDED
        |
No email from App Store Connect = success
```

If only changing permission strings, you might think you can re-upload immediately without incrementing the build number. However, re-uploading with the same build number is rejected rather than replacing the existing build. You must increment the build number.
