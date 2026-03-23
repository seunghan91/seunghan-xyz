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

The `icloud_storage_sync` package doesn't work just by adding the code. For it to work on real iOS devices, all three settings must be correct. Missing even one of them will cause your app to run fine on the simulator but crash the moment it hits a real device. This guide covers all three required configurations, the symptoms of each misconfiguration, how to debug them, and a checklist to prevent them from happening again.

---

## Why Is This So Complicated — Root Cause

iCloud integration operates on top of Apple's **entitlement-based permission system**. For an app to access an iCloud container, four things must all be true simultaneously:

1. The app binary must be signed with the correct **entitlements**
2. The **App ID** in Apple Developer Portal must have iCloud capability enabled
3. A **provisioning profile** issued for that App ID must be installed on the device
4. The `containerId` string passed in Dart code must **exactly match** the container ID registered in entitlements

On the simulator, iCloud permission checks are often skipped entirely. This is why everything appears to work during development and only falls apart on the first real device test.

---

## 1. Runner.entitlements

Add iCloud-related keys to the `ios/Runner/Runner.entitlements` file. Create the file if it does not exist.

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

`$(CFBundleIdentifier)` is automatically substituted with the bundle ID from `Info.plist` at build time. If the bundle ID is `com.example.myapp`, the signed entitlement will contain `iCloud.com.example.myapp`.

### Verifying the entitlements file is actually being used

It is not enough to have the entitlements file on disk — it must be referenced in the Xcode project configuration.

1. Open Xcode and select the `Runner` target
2. Go to the **Build Settings** tab
3. Search for `Code Signing Entitlements`
4. Confirm the value is set to `Runner/Runner.entitlements`

If this field is empty or points to a non-existent path, Xcode will silently ignore the entitlements file and the iCloud permissions will never be included in the build.

### Multiple schemes or build configurations

If your project uses separate Debug, Release, and Profile configurations, each can have its own entitlements path setting. Check that none of the individual configuration rows override the value with something different or empty.

---

## 2. Adding Xcode Capability

Modifying the entitlements file alone does not synchronize with the App ID in Apple Developer Portal. **You must add the Capability directly in Xcode.**

1. Select the `Runner` target in Xcode
2. Open the **Signing & Capabilities** tab
3. Click **+ Capability** and select `iCloud`
4. Check **iCloud Documents**
5. Verify that `iCloud.$(CFBundleIdentifier)` appears in the Containers list

This action automatically activates the iCloud capability on the corresponding App ID in Apple Developer Portal and triggers a provisioning profile refresh.

### What happens if you skip this step

Even if you manually added the entitlement keys to the `.entitlements` file, the App ID in Developer Portal will not have iCloud capability registered. When you download a fresh provisioning profile, it will not include iCloud entitlements. The result is an error during Archive validation or App Store submission:

```
error: Provisioning profile "..." doesn't include the
"com.apple.developer.icloud-services" entitlement.
```

This error is particularly deceptive because it never appears during direct device debugging — Xcode manages signing automatically in that flow. It only surfaces during distribution, which can make it hard to connect to the root cause.

### Containers list is empty after adding the capability

If the Containers list is empty or `iCloud.$(CFBundleIdentifier)` was not automatically added:

- Verify that the App ID is actually registered in Developer Portal under the correct team.
- Confirm that **Automatically manage signing** is enabled in Xcode.
- If needed, click the `+` button in the Containers section and manually enter the container ID in the format `iCloud.your.bundle.id`.

---

## 3. containerId Format

The `containerId` used in Dart code must follow the format `iCloud.` + bundleID exactly.

```dart
// Wrong format
await _iCloudSync!.upload(
  containerId: 'myapp.backup',  // this format will not work
  ...
);

// Correct format
await _iCloudSync!.upload(
  containerId: 'iCloud.com.example.myapp',  // "iCloud." + bundleID
  ...
);
```

If the bundle ID is `com.example.myapp`, the containerId must be `iCloud.com.example.myapp`. It must match `iCloud.$(CFBundleIdentifier)` in the entitlements file exactly — including case.

### Managing containerId as a constant

To maintain consistency across the project and avoid typos, define containerId in a single location:

```dart
// lib/constants/storage_constants.dart
class StorageConstants {
  static const String iCloudContainerId = 'iCloud.com.example.myapp';
}

// Usage
await _iCloudSync!.upload(
  containerId: StorageConstants.iCloudContainerId,
  ...
);
```

If the bundle ID ever changes or you need to support multiple environments, only this constant needs to be updated.

### Handling Flutter flavors

When using `flutter_flavorizr` or a similar setup, each flavor typically has a different bundle ID:

- dev: `com.example.myapp.dev`
- production: `com.example.myapp`

Each flavor requires its own containerId. The recommended approach is to inject it via Dart defines at build time:

```dart
// Pass --dart-define=ICLOUD_CONTAINER_ID=iCloud.com.example.myapp at build time
const iCloudContainerId = String.fromEnvironment(
  'ICLOUD_CONTAINER_ID',
  defaultValue: 'iCloud.com.example.myapp',
);
```

You also need to register separate iCloud containers in Developer Portal for each flavor's bundle ID, and add each one to the entitlements file if you want to support multiple flavors from a single build target.

---

## Symptoms and Debugging by Missing Configuration

| Missing Item | Symptom | How to Debug |
|---|---|---|
| No entitlements permission | Crash on real device, simulator works fine | Check Xcode Console for `entitlement` or `ubiquity` keywords |
| Xcode Capability not added | Entitlements mismatch error during distribution | Check error messages at the Validate App step after Archive |
| containerId format error | Runtime error during upload or download | Run `flutter run --verbose` and inspect the Dart stack trace |
| Entitlements file path not set | Build succeeds but iCloud access silently fails | Check Build Settings > Code Signing Entitlements |

### Reading crash logs from a real device

1. Open Xcode and go to **Window** > **Devices and Simulators**
2. Select the device and click **Open Console**
3. Run the app, trigger the crash, and filter for `NSUbiquityIdentityToken` or `entitlement`

From the terminal:

```bash
flutter run --verbose 2>&1 | grep -i "icloud\|entitlement\|ubiquity"
```

### The most common mistake: only testing on the simulator

The iOS simulator does not fully implement iCloud permission enforcement. Some versions of `icloud_storage_sync` fall back to storing files in a local directory on the simulator, making everything appear to work. Always do a **final test on a physical device** before considering the integration complete.

---

## Full Checklist

- [ ] `com.apple.developer.icloud-services` added to `Runner.entitlements`
- [ ] `com.apple.developer.ubiquity-container-identifiers` added to `Runner.entitlements`
- [ ] Xcode Build Settings > `Code Signing Entitlements` path is correctly configured
- [ ] iCloud Capability added in Xcode Signing & Capabilities
- [ ] iCloud Documents is checked
- [ ] Containers list shows `iCloud.$(CFBundleIdentifier)` or the explicit container ID
- [ ] containerId in Dart code follows the `iCloud.` + bundleID format
- [ ] Container ID in entitlements matches containerId in code exactly
- [ ] Tested on a real physical device (not just the simulator)
- [ ] If using flavors, each flavor has its own containerId configured correctly

---

## Key Takeaways

- `icloud_storage_sync` requires all three configurations — entitlements, Xcode Capability, and containerId — to be correct **at the same time** for real device operation.
- The iOS simulator skips iCloud permission enforcement, which means real-device testing is the only way to validate the integration.
- Manually editing the entitlements file without adding the Xcode Capability causes provisioning profile mismatches during distribution that never appear during local development.
- The `containerId` must include the `iCloud.` prefix and must match the entitlements value character-for-character.
- In Flutter flavor setups, each flavor's bundle ID requires its own iCloud container registration and a separate containerId value.
- Centralizing containerId in a constant or Dart define reduces the risk of typos and makes multi-environment management straightforward.
