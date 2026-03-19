---
title: "Flutter google_sign_in CocoaPods GTMSessionFetcher Version Conflict Resolution"
date: 2025-07-27
draft: true
tags: ["Flutter", "iOS", "CocoaPods", "Google Sign-In", "Troubleshooting"]
description: "When adding google_sign_in package to a Flutter project and building, a GTMSessionFetcher/Core version conflict can occur in CocoaPods. Cause and solution."
cover:
  image: "/images/og/flutter-google-signin-cocoapods-gtmsessionfetcher-conflict.png"
  alt: "Flutter Google Signin Cocoapods Gtmsessionfetcher Conflict"
  hidden: true
---


After adding the `google_sign_in` package to a Flutter app and running `flutter build ipa`, the build failed at the CocoaPods stage.

---

## Error Message

```
[!] CocoaPods could not find compatible versions for pod "GTMSessionFetcher/Core":
  In snapshot (Podfile.lock):
    GTMSessionFetcher/Core (< 5.0, = 4.5.0, >= 3.4)

  In Podfile:
    google_sign_in_ios was resolved to 0.0.1, which depends on
      GoogleSignIn (~> 8.0) was resolved to 8.0.0, which depends on
        GTMSessionFetcher/Core (~> 3.3)
```

The core issue is that the `GTMSessionFetcher` version pinned in `Podfile.lock` (4.5.0) conflicts with the version required by `google_sign_in` (`~> 3.3`).

---

## Cause

When Firebase-related Pods are already installed in an existing project, the `GTMSessionFetcher` version gets pinned in `Podfile.lock`. The newly added `google_sign_in` package's native dependency, the `GoogleSignIn` SDK, requires `GTMSessionFetcher/Core ~> 3.3`, and when it's incompatible with the version in the lock file, a conflict occurs.

Since CocoaPods prioritizes `Podfile.lock` versions, `pod install` alone won't resolve it.

---

## Solution

Just update the specific Pod from the iOS directory.

```bash
cd ios && pod update GTMSessionFetcher
```

This re-resolves `GTMSessionFetcher` to a version that satisfies all dependencies. Running a full `pod update` could unnecessarily upgrade other Pods, so specifying the target is safer.

After updating, rebuilding succeeds normally.

```bash
flutter build ipa --release
```

---

## Full Process Summary

To add Google Sign-In to Flutter iOS, follow these steps.

### 1. Create OAuth iOS Client in Google Cloud Console

- Application type: iOS
- Bundle ID: `PRODUCT_BUNDLE_IDENTIFIER` value from the Xcode project
- Team ID: `DEVELOPMENT_TEAM` value from Apple Developer

After creation, you can download a plist file containing the **Client ID** and **Reversed Client ID**.

### 2. Add CLIENT_ID to GoogleService-Info.plist

The `GoogleService-Info.plist` downloaded from Firebase Console may not include the OAuth `CLIENT_ID` by default. You need to add it manually.

```xml
<key>CLIENT_ID</key>
<string>YOUR_CLIENT_ID.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
```

### 3. Add URL Scheme to Info.plist

Register the `REVERSED_CLIENT_ID` as a URL scheme to receive Google Sign-In callbacks.

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleTypeRole</key>
    <string>Editor</string>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
    </array>
  </dict>
</array>
```

### 4. Add Package to pubspec.yaml

```yaml
dependencies:
  google_sign_in: ^6.2.2
```

### 5. Resolve Version Conflict with pod update

```bash
flutter pub get
cd ios && pod update GTMSessionFetcher
```

### 6. Build and Deploy

```bash
flutter build ipa --release
```

---

## Pain Points

- `pod install` alone won't work due to lock file constraints. You must use `pod update [package_name]` for a targeted update.
- `pod update` (full) can upgrade other Pod versions too, risking side effects. It's better to specify only the conflicting Pod.
- When creating an OAuth client in Google Cloud Console, verify it's the same project number as your Firebase project. Creating it in a different project will cause token verification to fail.
- The `CLIENT_ID` in `GoogleService-Info.plist` and the URL Scheme in `Info.plist` must be configured as a pair. If either is missing, Google Sign-In won't work on iOS.
