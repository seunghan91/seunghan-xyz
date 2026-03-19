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

If Firebase phone auth works on the emulator but not on a real device, it's almost always because platform-specific settings are missing. Here's a guide for each required configuration on Android and iOS.

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

### 2. Register in Firebase Console

1. Firebase Console -> Project Settings (gear icon)
2. **Your apps** section -> Click Android app
3. **Add fingerprint** -> Paste SHA-1 -> Save
4. Add SHA-256 as well (recommended)

### 3. Re-download google-services.json

After registering fingerprints, you **must download a new** `google-services.json`.

Firebase Console -> Android app -> `Download google-services.json`

Replace the existing file (`android/app/google-services.json`) and rebuild the app.

```bash
flutter clean
flutter pub get
flutter run
```

---

## iOS: APNs Key Registration

On iOS, Firebase Phone Auth delivers verification codes via **APNs (Apple Push Notification service)** silent push. Without APNs configuration, SMS won't arrive on real devices at all.

> Simulators work with Firebase test phone numbers without APNs. This is only needed for real devices.

### 1. Issue APNs Authentication Key (Apple Developer Console)

1. Log in to [developer.apple.com](https://developer.apple.com/account)
2. **Certificates, Identifiers & Profiles -> Keys**
3. Click **+** button
4. Check **Apple Push Notifications service (APNs)**
5. Enter a name and click **Continue -> Register**
6. Click **Download** -> Save the `.p8` file

> Warning: The `.p8` file can only be **downloaded once**. If you lose it, you'll need to reissue.

Note the **Key ID** shown on screen and your account's **Team ID**.

### 2. Upload APNs Key to Firebase Console

1. Firebase Console -> Project Settings
2. **Cloud Messaging** tab
3. **Apple app configuration** section -> Select iOS app
4. **APNs Authentication Key** -> **Upload**
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

**`ios/Runner/Info.plist`**
```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
    <string>fetch</string>
    <string>remote-notification</string>  <!-- this must be present -->
</array>
```

If **Signing & Capabilities -> Push Notifications** capability is added in Xcode, the entitlements file is managed automatically.

---

## Key File Management

The APNs `.p8` file is security-sensitive. If storing it in the project, be sure to add it to `.gitignore`.

```bash
# .gitignore
ios/secrets/
*.p8
.env
```

Recording key information in an `.env` file makes team sharing easier.

```bash
# .env
APNS_KEY_ID=XXXXXXXXXX
APNS_KEY_PATH=ios/secrets/AuthKey_XXXXXXXXXX.p8
APPLE_TEAM_ID=XXXXXXXXXX
```

---

## Using Firebase Test Phone Numbers

To test without receiving actual SMS, you can register test numbers in Firebase Console.

**Firebase Console -> Authentication -> Sign-in method -> Phone -> Test phone numbers**

| Phone number | Verification code |
|-------------|------------------|
| +82 10-1111-1111 | 111111 |

When a verification request is sent to a registered number, the specified code passes authentication without actual SMS. Very useful for development/staging environments.

---

## Setup Completion Checklist

```
Android
├── [ ] Firebase Console -> Authentication -> Phone enabled
├── [ ] SHA-1 fingerprint registered
├── [ ] SHA-256 fingerprint registered (recommended)
└── [ ] google-services.json re-downloaded and replaced

iOS
├── [ ] APNs authentication key issued (Apple Developer)
├── [ ] APNs key uploaded to Firebase Console -> Cloud Messaging
├── [ ] aps-environment set in Runner.entitlements
└── [ ] remote-notification Background Mode added to Info.plist

Common
└── [ ] Firebase test phone numbers registered (optional)
```

If even one setting is missing, it won't work on real devices. Going through the checklist in order is the fastest approach.
