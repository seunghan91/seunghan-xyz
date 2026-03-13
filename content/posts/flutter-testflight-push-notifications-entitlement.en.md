---
title: "Flutter TestFlight Build Error: Push Notifications Entitlement Issue"
date: 2025-06-08
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Deployment"]
description: "Resolving provisioning profile / aps-environment errors encountered while uploading a Flutter iOS app to TestFlight."
cover:
  image: "/images/og/flutter-testflight-push-notifications-entitlement.png"
  alt: "Flutter Testflight Push Notifications Entitlement"
  hidden: true
---


Here are the build errors and solutions encountered while uploading a Flutter app to TestFlight for the first time.

---

## Error Situation

After running `flutter build ipa --release` and attempting to upload with xcrun altool, the failure occurred not during upload but at the **build stage** where the Xcode archive failed.

```
error: Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the aps-environment entitlement.
```

Upload command:

```bash
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "$APPLE_ID" \
  --password "$APPLE_APP_PASSWORD"
```

---

## Cause

The `ios/Runner/Runner.entitlements` file contained the following entry.

```xml
<key>aps-environment</key>
<string>production</string>
```

This key is only allowed in **Provisioning Profiles that have Push Notifications capability enabled**. Wildcard (`*`) provisioning profiles do not support Push Notifications, so a conflict occurs at archive time.

### When Does This Key Get Created?

If you add Push Notifications even once in Xcode's **Signing & Capabilities** tab, it is automatically written to the entitlements file. Even if you remove the capability later, the file entry remains.

---

## Solution

If Push Notifications has not been implemented yet, delete the key from `Runner.entitlements`.

```xml
<!-- Before deletion -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist ...>
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
</plist>

<!-- After deletion -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist ...>
<plist version="1.0">
<dict>
</dict>
</plist>
```

Rebuilding after this will pass successfully.

---

## Uploading to TestFlight with xcrun altool

Use an **App-Specific Password** from the Apple Developer account.

```bash
# Generate app password: https://appleid.apple.com -> Generate App Password
# Format: xxxx-xxxx-xxxx-xxxx

xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --username "your@apple.com" \
  --password "xxxx-xxxx-xxxx-xxxx"
```

On successful upload, the output is:

```
No errors uploading archive at 'build/ios/ipa/app.ipa'.
```

A Delivery UUID is issued, and the build typically appears in App Store Connect -> TestFlight within a few minutes.

---

## When Adding Push Notifications Later

When the time comes to actually implement Push Notifications:

1. Issue an **APNs Key** or **APNs Certificate** in Apple Developer Console
2. Enable Push Notifications capability on the App ID (App Identifier)
3. Create a new Provisioning Profile with that App ID (not Wildcard)
4. Re-add the `aps-environment` key to `Runner.entitlements`

You must use an **explicit App ID profile** instead of a Wildcard profile.

---

## Summary

| Situation | Action |
|---|---|
| Push not implemented, Wildcard profile | Delete `aps-environment` key |
| Push implemented, explicit App ID profile | Keep `aps-environment: production` |
| Development simulator testing | `aps-environment: development` |

The entitlements file is frequently auto-modified by Xcode UI operations, so checking this file first when encountering build errors is a good practice.
