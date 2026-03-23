---
title: "Flutter TestFlight Build Error: Push Notifications Entitlement Issue"
date: 2025-06-08
draft: true
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Deployment"]
description: "Resolving provisioning profile / aps-environment errors encountered while uploading a Flutter iOS app to TestFlight."
cover:
  image: "/images/og/flutter-testflight-push-notifications-entitlement.png"
  alt: "Flutter Testflight Push Notifications Entitlement"
  hidden: true
---

This post documents the build errors and their solutions encountered while uploading a Flutter app to TestFlight for the first time. The symptom looks simple, but without knowing the root cause, you can spend a surprisingly long time debugging it. Understanding how provisioning profiles, entitlements, and APNs configuration interact will help you resolve similar errors quickly in the future.

---

## Error Situation

After running `flutter build ipa --release` and attempting to upload with xcrun altool, the failure occurred not during upload but at the **build stage** where the Xcode archive failed.

```
error: Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the aps-environment entitlement.
```

At first glance it looks like an issue with the altool command, but the actual problem is that the archive itself cannot be created. The upload command in question:

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "$APPLE_ID" \
  --password "$APPLE_APP_PASSWORD"
```

Looking at the error message more carefully, it contains two pieces of critical information:

1. **"iOS Team Provisioning Profile: \*"** — a Wildcard provisioning profile is in use
2. **"aps-environment entitlement"** — the APNs environment setting is conflicting with the profile

Combining these two clues makes the root cause immediately clear.

---

## Root Cause Analysis

### What is an entitlements file?

iOS apps declare access to certain system capabilities (Push Notifications, iCloud, App Groups, etc.) through a `.entitlements` file. This file is processed alongside code signing during the build, and the permissions the app declares must match those included in the provisioning profile.

The `ios/Runner/Runner.entitlements` file contained the following entry:

```xml
<key>aps-environment</key>
<string>production</string>
```

This key is only permitted in **Provisioning Profiles that have the Push Notifications capability enabled**. Wildcard (`*`) provisioning profiles do not support Push Notifications, so a conflict occurs at archive time.

### The Limits of Wildcard Profiles

A Wildcard profile (`*`) is a convenient profile that can be used across multiple apps without targeting a specific Bundle ID. However, this convenience comes with restrictions. Capabilities that **require per-app unique configuration** — Push Notifications, Game Center, In-App Purchase, and others — are not supported by Wildcard profiles. To use APNs, you must use a profile based on an explicit App ID.

### When Does This Key Get Created?

If you add Push Notifications even once in Xcode's **Signing & Capabilities** tab, it is automatically written to the entitlements file. Even if you remove the capability later, the file entry remains.

In Flutter projects, it is common to add Push Notifications capability in Xcode when installing packages like `firebase_messaging`. The `aps-environment` key then gets written to the entitlements file, and even if you later remove the package or no longer need the feature, the key stays behind.

Another common scenario is adding Push Notifications temporarily for testing during development and then removing it. Xcode does not automatically clean up the `.entitlements` file when you remove a capability from the UI.

---

## Solution

### Immediate Fix: Delete the aps-environment Key

If Push Notifications have not been implemented yet, delete the key from `Runner.entitlements`.

```xml
<!-- Before deletion -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
</plist>

<!-- After deletion -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
</dict>
</plist>
```

Rebuilding after this change will pass successfully.

### Checking and Fixing in Xcode

In addition to editing the file directly in a text editor, you can also verify things in Xcode:

1. Open `ios/Runner.xcworkspace` in Xcode
2. Select the `Runner` target in the left file tree
3. Navigate to the **Signing & Capabilities** tab
4. If the Push Notifications capability is listed, remove it using the `-` button on the right
5. Open `Runner.entitlements` directly and confirm the `aps-environment` key is gone

Because Xcode sometimes leaves the key in the `.entitlements` file even after removing the capability through the UI, opening the file directly to verify is the safest approach.

---

## Uploading to TestFlight with xcrun altool

With the build error resolved, you can now upload normally. Use an **App-Specific Password** from your Apple account.

```bash
# Generate app password at: https://appleid.apple.com -> Generate App Password
# Format: xxxx-xxxx-xxxx-xxxx

xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx"
```

You can also use an App Store Connect API Key, which avoids Two-Factor Authentication prompts and is better suited for CI/CD pipelines.

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --apiKey "YOUR_KEY_ID" \
  --apiIssuer "YOUR_ISSUER_ID"
```

On successful upload, the output is:

```
No errors uploading archive at 'build/ios/ipa/app.ipa'.
```

A Delivery UUID is issued, and the build typically appears in App Store Connect -> TestFlight within a few minutes. It first shows as "Processing" and becomes available for distribution to testers once complete.

### Using notarytool Instead of altool (macOS 13+)

Since macOS Ventura (13.0), `xcrun altool` has been deprecated. Using `xcrun notarytool` is now recommended.

```bash
xcrun notarytool submit "build/ios/ipa/app.ipa" \
  --apple-id "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx" \
  --team-id "YOUR_TEAM_ID" \
  --wait
```

While many Flutter tutorials still show altool in their examples, migrating to notarytool or the Transporter app for uploads is the better long-term choice.

---

## When Adding Push Notifications Later

When the time comes to actually implement Push Notifications, you need to follow the correct sequence.

### Setup Order

1. **Enable Push Notifications on the App ID in Apple Developer Console**
   - [developer.apple.com](https://developer.apple.com) -> Certificates, Identifiers & Profiles -> Identifiers
   - Select the explicit App ID for your app -> Enable Push Notifications under Capabilities

2. **Issue an APNs Key or APNs Certificate**
   - APNs Key: shared across multiple apps, no expiry (recommended)
   - APNs Certificate: issued per app, expires after 1 year

3. **Create a new Provisioning Profile**
   - Create an explicit profile based on the App ID, not a Wildcard
   - Choose a Distribution profile (App Store or Ad Hoc)

4. **Add the capability in Xcode**
   - Signing & Capabilities -> Add Push Notifications
   - `aps-environment: production` will be automatically added to `Runner.entitlements`

5. **Configure the firebase_messaging or flutter_local_notifications package**

### When Using FCM Without flutter_local_notifications

Even if you only use the `firebase_messaging` package, APNs configuration is mandatory. Firebase Cloud Messaging (FCM) uses APNs as its backend on iOS. If you do not register your APNs Key in the Firebase Console, FCM messages will never reach iOS devices.

---

## Debugging Tips

### Common Pattern of Entitlement Mismatch Errors

Similar errors can occur with other entitlement keys as well.

| Error Key | Cause | Solution |
|---|---|---|
| `aps-environment` | Leftover Push Notifications capability | Delete key or use explicit profile |
| `com.apple.developer.icloud-container-identifiers` | Leftover iCloud capability | Delete key or use iCloud-enabled profile |
| `com.apple.security.application-groups` | Leftover App Groups capability | Use App Groups-enabled profile |

### Pre-Build Entitlements File Checklist

```bash
# Check the current entitlements file contents
cat ios/Runner/Runner.entitlements

# Check provisioning profiles installed locally
ls ~/Library/MobileDevice/Provisioning\ Profiles/
```

Provisioning profile files (`.mobileprovision`) are in binary format, but you can inspect their contents with the `security` command:

```bash
security cms -D -i ~/Library/MobileDevice/Provisioning\ Profiles/YOUR_PROFILE.mobileprovision
```

Find the `<key>Entitlements</key>` section in the output XML and check whether the `aps-environment` key is present. If it is not, the profile does not support Push Notifications.

---

## Summary

| Situation | Action |
|---|---|
| Push not implemented, Wildcard profile | Delete `aps-environment` key |
| Push implemented, explicit App ID profile | Keep `aps-environment: production` |
| Development / simulator testing | `aps-environment: development` |
| CI/CD automated deployment | Use App Store Connect API Key |

The entitlements file is frequently auto-modified by Xcode UI operations, so checking this file first when encountering build errors is a good practice. In particular, if the build suddenly breaks after adding or removing a package, or after touching the Signing & Capabilities tab, inspecting the `.entitlements` file contents is the fastest path to the root cause.

---

## Key Takeaways

- The `aps-environment` key is only valid with a **provisioning profile based on an explicit App ID** that has Push Notifications enabled. Using it with a Wildcard profile causes archive failure.
- Removing the Push Notifications capability from Xcode's Signing & Capabilities tab does **not** automatically delete the `aps-environment` key from the `.entitlements` file. You must open the file and remove the key manually.
- If Push Notifications are not yet implemented, deleting the key from the entitlements file is the fastest fix.
- When actually implementing Push Notifications, follow the sequence: enable capability on the App ID in Apple Developer Console → issue an APNs Key → create an explicit provisioning profile → add the capability in Xcode.
- Even when using only `firebase_messaging`, APNs configuration is required, and the APNs Key must be registered in the Firebase Console for FCM messages to work on iOS.
- When a build error occurs, comparing the contents of `ios/Runner/Runner.entitlements` against the Entitlements section of the provisioning profile in use is the most reliable way to identify the root cause.
