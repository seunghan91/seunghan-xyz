---
title: "Flutter Google Sign-In iOS Setup: Missing CLIENT_ID in GoogleService-Info.plist"
date: 2025-06-04
draft: true
tags: ["Flutter", "iOS", "Google Sign-In", "Firebase", "OAuth"]
description: "When integrating google_sign_in package on iOS, login won't work if GoogleService-Info.plist is missing CLIENT_ID. Setup instructions."
cover:
  image: "/images/og/flutter-google-signin-ios-setup.png"
  alt: "Flutter Google Signin Ios Setup"
  hidden: true
---

When implementing Google Sign-In with the `google_sign_in` package in a Flutter app and it only fails on iOS, the cause is often a missing `CLIENT_ID` in `GoogleService-Info.plist`. This is one of the most common Flutter iOS authentication pitfalls — the Android side works perfectly because `google-services.json` is structured differently, and the asymmetry creates a misleading situation where developers assume the configuration is complete.

This guide walks through the root cause, the full configuration steps, common debugging techniques, and prevention tips so you don't run into this again.

---

## The Problem

Google Sign-In works fine on Android, but on iOS the login dialog doesn't appear or an error occurs. Sometimes the error is explicit:

```
PlatformException(sign_in_failed, com.google.GIDSignIn, Error Domain=com.google.GIDSignIn Code=-4 ...)
```

Other times it silently fails — the sign-in sheet never shows and `signIn()` returns null without throwing.

You registered the iOS app in Firebase Console and added the downloaded `GoogleService-Info.plist` to the project, but the default download file sometimes doesn't include `CLIENT_ID`. This is not obvious from the Firebase Console UI, which doesn't warn you that the OAuth client hasn't been created yet.

### Root Cause

The `google_sign_in` iOS native SDK requires an OAuth 2.0 client ID to initiate the sign-in flow. Without it, the GIDSignIn framework cannot construct the authorization URL and the entire flow fails silently or throws a vague error.

Firebase and Google Cloud Console are related but separate systems. When you create a Firebase project, a Google Cloud project is created underneath it. However, an **iOS OAuth client** in Google Cloud Console is only created automatically in certain circumstances — for example, when you enable Google Sign-In in the Firebase Authentication section. If you skip that step or enable it later, the plist you downloaded earlier won't have `CLIENT_ID`.

In contrast, Android uses SHA-1 fingerprint-based authentication via `google-services.json`, which follows a different flow. This is why the Android side works while iOS silently breaks.

---

## Prerequisites

Before starting, make sure you have:

- A Flutter project with `google_sign_in` added to `pubspec.yaml`
- A Firebase project with an iOS app registered (bundle ID must match your app exactly)
- Access to both Firebase Console and Google Cloud Console for the same project
- Xcode installed (needed to verify URL Types configuration)

---

## Step 1: Verify the iOS OAuth Client in Google Cloud Console

Go to [Google Cloud Console](https://console.cloud.google.com) and select your Firebase project. Navigate to **APIs & Services → Credentials**.

Look for an OAuth 2.0 client entry with type **iOS**. When you create a Firebase project, an iOS OAuth client is sometimes created automatically. The client ID format is:

```
{project-number}-{hash}.apps.googleusercontent.com
```

If you don't see an iOS OAuth client here, you need to create one manually (see the section below on creating it from scratch).

---

## Step 2: Add Two Keys to GoogleService-Info.plist

Open `ios/Runner/GoogleService-Info.plist` in a text editor or Xcode. Check whether `CLIENT_ID` and `REVERSED_CLIENT_ID` already exist. If they're missing, add them:

```xml
<key>CLIENT_ID</key>
<string>{project-number}-{hash}.apps.googleusercontent.com</string>

<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{project-number}-{hash}</string>
```

`REVERSED_CLIENT_ID` is the CLIENT_ID with its dot-separated segments reversed. This is not a typo or coincidence — it becomes the custom URL scheme that iOS uses to redirect back to your app after the Google OAuth flow completes in Safari or ASWebAuthenticationSession.

Example:
```
CLIENT_ID:          1234567890-abcdef.apps.googleusercontent.com
REVERSED_CLIENT_ID: com.googleusercontent.apps.1234567890-abcdef
```

The reversal pattern: take each dot-separated part and list them in reverse order.

---

## Step 3: Register the URL Scheme in Info.plist

The URL Scheme must be registered in `ios/Runner/Info.plist` so iOS knows to redirect back to your app when the OAuth flow completes in the browser.

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.{project-number}-{hash}</string>
        </array>
    </dict>
</array>
```

The value inside `CFBundleURLSchemes` must exactly match `REVERSED_CLIENT_ID` from `GoogleService-Info.plist`. A single character mismatch here causes the OAuth redirect to fail silently — the browser completes the flow but iOS cannot return the user to your app.

---

## Step 4: Verify in Xcode

Open the project in Xcode. Select the **Runner** target, go to the **Info** tab, and scroll to **URL Types**. You should see an entry with the `REVERSED_CLIENT_ID` value listed under URL Schemes.

If it's not there even after editing `Info.plist` directly, add it manually in Xcode:

1. Click the `+` button under URL Types
2. Leave Identifier blank or set it to `com.google`
3. Set Role to **Editor**
4. Under URL Schemes, enter the `REVERSED_CLIENT_ID` value

This Xcode-level registration is the authoritative source — it writes back to `Info.plist` when you save.

---

## How the google_sign_in Package Works on iOS

The `google_sign_in` iOS implementation reads `GoogleService-Info.plist` at app startup via the `GIDSignIn` native framework and automatically configures the client ID. You don't need to pass `clientId` in Dart code — if it's in the plist, it's picked up automatically.

```dart
// No clientId needed in Dart code when plist is configured correctly
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: ['email', 'profile'],
);
```

However, if you're working in a multi-environment setup (dev/staging/prod) with different Firebase projects, you may need to pass `clientId` explicitly:

```dart
final GoogleSignIn _googleSignIn = GoogleSignIn(
  clientId: 'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com',
  scopes: ['email', 'profile'],
);
```

Android, on the other hand, reads `client_id` from `google-services.json` using SHA-1 fingerprint matching. This is why Android works without the plist changes.

---

## When CLIENT_ID Is Missing from Firebase iOS App Registration

When adding an iOS app in Firebase Console and downloading `GoogleService-Info.plist`, the `CLIENT_ID` key may be absent. This happens when:

- The iOS OAuth client was never created in Google Cloud Console
- Google Sign-In was not enabled in Firebase Authentication before downloading the plist
- The plist was downloaded immediately after project creation before OAuth clients were provisioned

**Option A: Create the OAuth client manually**

1. Google Cloud Console → **Credentials → + Create Credentials → OAuth client ID**
2. Application type: **iOS**
3. Enter your app's Bundle ID (must match exactly what's in your Flutter project)
4. Click Create
5. Copy the generated client ID
6. Manually add `CLIENT_ID` and `REVERSED_CLIENT_ID` to `GoogleService-Info.plist`

**Option B: Re-download from Firebase Console**

After enabling Google Sign-In in Firebase Authentication, re-download `GoogleService-Info.plist` from Firebase Console → Project Settings → Your Apps. The newly downloaded file should include `CLIENT_ID` automatically.

Always compare the new file with the existing one before replacing to avoid overwriting custom keys you may have added.

---

## Debugging Steps

If Google Sign-In still doesn't work after the configuration above, try these debugging steps:

**1. Check the plist is added to the Xcode target**

In Xcode, select `GoogleService-Info.plist` in the file navigator. In the File Inspector on the right, verify that **Target Membership** includes the Runner target. If the file is in the project folder but not added to the target, it won't be bundled into the app.

**2. Print the client ID at runtime**

```dart
import 'package:flutter/services.dart';

// Read the plist and verify CLIENT_ID is present
final plist = await rootBundle.loadString('ios/Runner/GoogleService-Info.plist');
print(plist); // Check for CLIENT_ID in the output
```

Note: this reads the source file, not the bundled one. For the bundled version, check Xcode's build products.

**3. Enable verbose logging**

In your `AppDelegate.swift`, add GIDSignIn debug logging:

```swift
import GoogleSignIn

@UIApplicationMain
class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // GIDSignIn will log errors to console if configuration is wrong
    GeneratedPluginRegistrant.register(with: self)
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
```

Run from Xcode (not `flutter run`) to see the full native console output, including GIDSignIn initialization errors.

**4. Verify bundle ID matches**

The Bundle ID in your Xcode project (`PRODUCT_BUNDLE_IDENTIFIER`) must exactly match the Bundle ID used when creating the OAuth client in Google Cloud Console. Even a minor difference (e.g., uppercase vs. lowercase) will cause authentication to fail.

**5. Clean build folder**

After editing plist files, always do a clean build in Xcode: **Product → Clean Build Folder** (Shift+Cmd+K), then rebuild. Cached builds can serve stale plist data.

---

## Prevention Tips

**Use Firebase CLI to generate plist files**

The Firebase CLI (`firebase init`) generates plist files that include all necessary OAuth keys when Google Sign-In is enabled. Using the CLI reduces the chance of manual configuration errors.

**Commit plist files to version control**

Add `GoogleService-Info.plist` to your git repository (or a secure secrets manager if you're concerned about key exposure). This ensures the correct configuration is always present when cloning the project on a new machine.

**Validate configuration in CI**

Add a CI step that checks for required keys in `GoogleService-Info.plist`:

```bash
# In your CI script
if ! grep -q "CLIENT_ID" ios/Runner/GoogleService-Info.plist; then
  echo "ERROR: CLIENT_ID missing from GoogleService-Info.plist"
  exit 1
fi
```

**Document the OAuth client setup**

Add a note in your project README or CLAUDE.md explaining that Google Cloud Console requires an iOS OAuth client to be created separately from the Firebase project setup. This prevents future developers from making the same mistake.

---

## Checklist

- [ ] `CLIENT_ID` key exists in `GoogleService-Info.plist`
- [ ] `REVERSED_CLIENT_ID` key exists in `GoogleService-Info.plist`
- [ ] `REVERSED_CLIENT_ID` value is registered in `CFBundleURLSchemes` in `Info.plist`
- [ ] The same scheme is registered in Xcode Runner target's URL Types
- [ ] `GoogleService-Info.plist` is added to the Runner target in Xcode (not just the folder)
- [ ] Bundle ID in Xcode matches the one used to create the OAuth client in Google Cloud Console
- [ ] Clean build performed after making plist changes

Most iOS Google Sign-In issues trace back to one of these seven items.

---

## Key Takeaways

- **The root cause** is that iOS `google_sign_in` requires an OAuth 2.0 client ID in `GoogleService-Info.plist`, which Firebase does not always include automatically depending on when and how you download the file.
- **Android works differently** — it uses SHA-1 fingerprint matching via `google-services.json`, so the missing iOS OAuth client goes unnoticed until you test on a real device or iOS simulator.
- **Two plist files, two keys**: `GoogleService-Info.plist` needs `CLIENT_ID` and `REVERSED_CLIENT_ID`; `Info.plist` needs the `REVERSED_CLIENT_ID` value as a `CFBundleURLSchemes` entry.
- **The URL scheme is critical** — without it, iOS cannot redirect back to your app after the OAuth flow, causing silent failures.
- **Always verify in Xcode** — editing plist files directly is fine, but the Xcode URL Types panel is the authoritative source and will overwrite manual edits if you change settings there later.
- **Re-downloading the plist** from Firebase Console after enabling Google Sign-In in Firebase Authentication is often the fastest fix when `CLIENT_ID` is missing.
