---
title: "Firebase Phone Auth Platform Setup Complete Guide - Android SHA-1, iOS APNs"
date: 2025-06-29
draft: true
tags: ["Firebase", "Android", "iOS", "APNs", "SHA-1", "Phone Auth"]
description: "Complete process for registering Android SHA-1 fingerprint and iOS APNs key setup to make Firebase phone authentication work on real devices."
cover:
  image: "/images/og/firebase-android-sha1-ios-apns-complete-setup.png"
  alt: "Firebase Android Sha1 Ios Apns Complete Setup"
  hidden: true
---

If Firebase phone auth works on the emulator but not on a real device, it is almost always because platform-specific settings are missing. This guide covers every required configuration for Android and iOS, including the underlying reasons, common debugging scenarios, and a complete checklist.

---

## Why Does It Work on the Emulator But Not on a Real Device?

Firebase Phone Auth uses a different authentication flow depending on the platform. On the emulator, Firebase allows test phone numbers without additional security verification. On real devices, two additional security layers activate.

**Android**: Firebase uses the Play Integrity API to verify that the installed APK is correctly signed through Google Play. The SHA-1 fingerprint of the app signing key must match what is registered in Firebase. If the fingerprint is not registered, the Integrity token cannot be issued and the phone number verification request is rejected.

**iOS**: Firebase delivers verification codes via APNs (Apple Push Notification service) silent push. Despite looking like an SMS on the surface, the delivery mechanism is a push notification channel internally. Without APNs configuration, the code never reaches the device.

Understanding these two mechanisms explains why a missing configuration results in a silent failure with no obvious error message.

---

## Android: SHA-1 Fingerprint Registration

Firebase Phone Auth uses the **Play Integrity API** on Android. This requires registering your app's signing key fingerprint (SHA-1) in Firebase. Without it, auth requests will fail entirely.

### 1. Extract SHA-1 from Keystore

```bash
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_STORE_PASSWORD
```

Example output:
```
SHA1: 64:60:03:0B:00:6F:E2:29:A4:40:DD:E3:44:3A:7D:32:39:2B:6A:42
SHA256: 24:83:18:41:D6:9A:E5:84:26:71:8E:A2:...
```

If you have a key.properties file, check the password there.

#### When You Also Need the Debug Keystore SHA-1

When running directly on a real device during development (`flutter run`), the APK is signed with the **debug keystore**, not the release keystore. In that case, the debug keystore SHA-1 must also be registered.

```bash
# Default debug keystore path on macOS/Linux
keytool -list -v \
  -keystore ~/.android/debug.keystore \
  -alias androiddebugkey \
  -storepass android
```

The common practice is to register **both** the debug SHA-1 and the release SHA-1 in Firebase Console. This allows real-device testing during development while keeping production functionality intact after release.

#### When Using Google Play App Signing

If you enroll your app in Play App Signing, the actual signing key on installed devices is managed by Google Play, not by the upload keystore you hold locally. In this case, you must register the SHA-1 from the **App signing key certificate** shown in Play Console, not the SHA-1 from your local upload keystore.

Play Console → Your App → Release → App Signing → **App signing key certificate** section.

This is a common source of confusion for developers who see phone auth working before Play App Signing enrollment and breaking afterward.

### 2. Register in Firebase Console

1. Firebase Console → Project Settings (gear icon)
2. **Your apps** section → Click Android app
3. **Add fingerprint** → Paste SHA-1 → Save
4. Add SHA-256 as well (recommended)

### 3. Re-download google-services.json

After registering fingerprints, you **must download a new** `google-services.json`.

Firebase Console → Android app → `Download google-services.json`

Replace the existing file (`android/app/google-services.json`) and rebuild the app.

```bash
flutter clean
flutter pub get
flutter run
```

Skipping `flutter clean` risks using a cached version of the previous configuration file. A clean build is strongly recommended after replacing `google-services.json`.

---

## iOS: APNs Key Registration

On iOS, Firebase Phone Auth delivers verification codes via **APNs (Apple Push Notification service)** silent push. Without APNs configuration, SMS won't arrive on real devices at all.

> Simulators work with Firebase test phone numbers without APNs. APNs configuration is only required for real devices.

### 1. Issue an APNs Authentication Key (Apple Developer Console)

1. Log in to [developer.apple.com](https://developer.apple.com/account)
2. **Certificates, Identifiers & Profiles → Keys**
3. Click the **+** button
4. Check **Apple Push Notifications service (APNs)**
5. Enter a name and click **Continue → Register**
6. Click **Download** → Save the `.p8` file

> An APNs key is tied to the entire **developer account**, not to a specific app. A single key covers all apps under the account.

> Warning: The `.p8` file can only be **downloaded once**. If you lose it, you must revoke the key and generate a new one.

Record the **Key ID** displayed on screen and your account's **Team ID**.

#### APNs Certificate vs APNs Key

Apple supports two formats for APNs configuration:

- **APNs Certificate** (legacy): `.p12` format, issued per app, expires annually and requires renewal
- **APNs Key** (recommended): `.p8` format, applies to the entire account, never expires

Firebase supports both, but the **APNs Key (.p8)** approach is far simpler to manage. No renewal deadlines and a single key serves all apps under the account.

### 2. Upload the APNs Key to Firebase Console

1. Firebase Console → Project Settings
2. **Cloud Messaging** tab
3. **Apple app configuration** section → Select the iOS app
4. **APNs Authentication Key** → **Upload**
   - Select the `.p8` file
   - Enter Key ID
   - Enter Team ID

### 3. Verify iOS Project Settings

For a Flutter project, these two files must be properly configured.

**`ios/Runner/Runner.entitlements`**
```xml
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
```

Use `development` for local debug builds (`flutter run`) and `production` for TestFlight or App Store distribution. A mismatch here causes silent push to be silently dropped by the system.

**`ios/Runner/Info.plist`**
```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
    <string>fetch</string>
    <string>remote-notification</string>  <!-- this must be present -->
</array>
```

The `remote-notification` entry in `UIBackgroundModes` is required for the app to receive Firebase's silent push even when it is in the background. Without it, the APNs delivery succeeds at the system level but the app never processes the code.

If **Signing & Capabilities → Push Notifications** capability is added in Xcode, the entitlements file is managed automatically.

### 4. Common iOS Troubleshooting Scenarios

**Symptom**: No response after entering the phone number (timeout)

Likely causes:
- `aps-environment` set to `development` while testing an App Store or TestFlight build (or vice versa)
- APNs key not registered in Firebase Console Cloud Messaging tab
- Push Notifications capability not added in Xcode

**Symptom**: Works on simulator, fails on TestFlight build

Cause: `aps-environment` set to `development` in a distribution build. TestFlight and App Store builds use the `production` APNs channel exclusively.

**Symptom**: reCAPTCHA web view appears instead of the code entry screen

When Firebase cannot receive the APNs silent push, it automatically falls back to a reCAPTCHA web challenge. If you see this unexpected web view on a real device, missing or misconfigured APNs is almost always the cause.

---

## Key File Management

The APNs `.p8` file contains sensitive credentials. If you store it in the project repository, add the path to `.gitignore` immediately.

```bash
# .gitignore
ios/secrets/
*.p8
.env
```

Recording key metadata in an `.env` file makes onboarding and team sharing easier while keeping the actual file out of version control.

```bash
# .env
APNS_KEY_ID=XXXXXXXXXX
APNS_KEY_PATH=ios/secrets/AuthKey_XXXXXXXXXX.p8
APPLE_TEAM_ID=XXXXXXXXXX
```

For teams managing multiple projects, storing the `.p8` file in a location outside the repository (such as `~/.secrets/` or a shared secrets vault) and recording only the path in `.env` reduces the risk of accidental exposure.

---

## Using Firebase Test Phone Numbers

To test without receiving actual SMS messages, you can register test phone numbers in Firebase Console.

**Firebase Console → Authentication → Sign-in method → Phone → Test phone numbers**

| Phone number | Verification code |
|-------------|------------------|
| +82 10-1111-1111 | 111111 |

When a verification request is sent to a registered test number, the specified code passes authentication without any actual SMS being sent. This is invaluable for automated testing and development environments where real carrier delivery is impractical.

One critical point: **test phone numbers bypass APNs and SHA-1 verification**. A successful test with a test number on the emulator does not confirm that real-device delivery will work. Always validate the full flow on a physical device using a real phone number before shipping.

---

## Setup Completion Checklist

```
Android
├── [ ] Firebase Console -> Authentication -> Phone enabled
├── [ ] Release keystore SHA-1 registered
├── [ ] Debug keystore SHA-1 registered (for real-device dev testing)
├── [ ] If using Play App Signing: SHA-1 from Play Console signing certificate
├── [ ] SHA-256 fingerprint registered (recommended)
└── [ ] google-services.json re-downloaded, replaced, and flutter clean run

iOS
├── [ ] APNs authentication key issued (Apple Developer) - .p8 + Key ID + Team ID
├── [ ] APNs key uploaded to Firebase Console Cloud Messaging tab
├── [ ] aps-environment set correctly in Runner.entitlements (dev vs. production)
├── [ ] remote-notification Background Mode added to Info.plist
└── [ ] Push Notifications capability added in Xcode

Common
└── [ ] Firebase test phone numbers registered (optional, for dev/staging)
```

If even one item is missing, phone auth will silently fail on real devices. Working through this checklist sequentially is the most reliable debugging approach.

---

## Key Takeaways

- **Emulator success does not equal real-device success.** The emulator bypasses security verification. On real devices, both SHA-1 (Android) and APNs (iOS) are mandatory.
- **Always re-download google-services.json after registering SHA-1.** The file embeds fingerprint data. Replace it, then run `flutter clean` before rebuilding.
- **A reCAPTCHA fallback on a real device means APNs is not working.** If you see a web-based captcha appearing during phone auth, check the APNs configuration first.
- **APNs Key (.p8) applies account-wide and never expires.** There is no need to issue a separate key per app and no annual renewal deadline. It is strictly superior to the legacy Certificate (.p12) approach.
- **Google Play App Signing changes where the signing SHA-1 comes from.** If phone auth breaks after enrolling in Play App Signing, the SHA-1 must come from Play Console, not from your local upload keystore.
- **Match aps-environment to your build type.** Development builds need `development`; TestFlight and App Store builds need `production`. A wrong value here causes silent failures with no obvious error.
