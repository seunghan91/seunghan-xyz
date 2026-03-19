---
title: "Flutter icloud_storage_sync iOS Setup Complete Guide"
date: 2025-07-30
draft: true
tags: ["Flutter", "iCloud", "iOS", "entitlements", "Xcode"]
description: "For icloud_storage_sync to work on real devices, entitlements, Xcode Capability, and containerId must all be correct. Missing any one causes crashes."
cover:
  image: "/images/og/flutter-icloud-storage-sync-ios-setup.png"
  alt: "Flutter Icloud Storage Sync Ios Setup"
  hidden: true
---


The `icloud_storage_sync` package doesn't work just by adding the code. For it to work on real iOS devices, all three settings must be correct.

---

## 1. Runner.entitlements

Add iCloud-related keys to the `ios/Runner/Runner.entitlements` file.

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

`$(CFBundleIdentifier)` is automatically substituted with the bundle ID from `Info.plist` at build time.

---

## 2. Adding Xcode Capability

Modifying the entitlements file alone doesn't synchronize with the App ID in Apple Developer Portal. **You must add the Capability directly in Xcode.**

1. Select the `Runner` target in Xcode
2. **Signing & Capabilities** tab
3. **+ Capability** button -> Select `iCloud`
4. Check **iCloud Documents**
5. Verify `iCloud.$(CFBundleIdentifier)` in the Containers list

This action automatically activates the iCloud capability on the corresponding App ID in Apple Developer Portal and refreshes the provisioning profile.

---

## 3. containerId Format

The `containerId` used in code must follow the format `iCloud.` + bundleID.

```dart
// Wrong format
await _iCloudSync!.upload(
  containerId: 'myapp.backup',  // this format won't work
  ...
);

// Correct format
await _iCloudSync!.upload(
  containerId: 'iCloud.com.example.myapp',  // "iCloud." + bundleID
  ...
);
```

If the bundle ID is `com.example.myapp`, the containerId is `iCloud.com.example.myapp`. It must match `iCloud.$(CFBundleIdentifier)` in the entitlements.

---

## Symptoms When Configuration Is Missing

| Missing Item | Symptom |
|---|---|
| No entitlements permission | Crash on real device, simulator works fine |
| Xcode Capability not added | Entitlements mismatch error during distribution |
| containerId format error | Runtime error during upload/download |

All three must be correct for proper operation on real devices.

---

## Full Checklist

- [ ] `com.apple.developer.icloud-services` added to `Runner.entitlements`
- [ ] `com.apple.developer.ubiquity-container-identifiers` added to `Runner.entitlements`
- [ ] iCloud Capability added in Xcode Signing & Capabilities
- [ ] iCloud Documents checked
- [ ] containerId follows `iCloud.` + bundleID format
- [ ] Container ID in entitlements matches containerId in code
