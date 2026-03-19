---
title: "Why Both Google and Apple Login Fail in TestFlight Builds"
date: 2025-08-03
draft: true
tags: ["Flutter", "iOS", "Firebase", "Google Sign-In", "Sign In with Apple", "TestFlight"]
description: "Google and Apple login both failing in TestFlight builds was caused by missing CLIENT_ID in GoogleService-Info.plist and unconfigured Firebase Apple provider."
cover:
  image: "/images/og/flutter-ios-signin-firebase-setup.png"
  alt: "Flutter Ios Signin Firebase Setup"
  hidden: true
---


Both Google Sign-In and Apple Sign-In failed in TestFlight builds. It worked fine on the simulator but only crashed on TestFlight.

---

## Cause 1: Missing CLIENT_ID in GoogleService-Info.plist

When you first register an iOS app in Firebase Console and download `GoogleService-Info.plist`, `CLIENT_ID` and `REVERSED_CLIENT_ID` are typically included. However, if you download it **before enabling Google Sign-In in Firebase**, these keys are generated without them.

How to check:

```bash
grep -A1 "CLIENT_ID\|REVERSED_CLIENT_ID" ios/Runner/GoogleService-Info.plist
```

If nothing comes back, the keys are missing.

### Why This Is a Problem

On iOS, Google Sign-In requires a URL Scheme registered in the app to receive OAuth callbacks. This URL Scheme is the `REVERSED_CLIENT_ID` value. Without the value, you can't register the scheme in `Info.plist`, and consequently the app can't return from the Google login dialog after authentication.

### Solution

Firebase Console -> Project Settings -> iOS App -> **Authentication -> Sign-in method -> Enable Google**, then re-download and replace `GoogleService-Info.plist`.

Then add the URL Scheme to `Info.plist`:

```xml
<key>CFBundleURLTypes</key>
<array>
    <!-- Existing Schemes -->
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLName</key>
        <string>Google Sign-In</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.XXXXXXXX-xxxx</string>
        </array>
    </dict>
</array>
```

The `REVERSED_CLIENT_ID` value can be found in the newly downloaded `GoogleService-Info.plist`.

---

## Cause 2: Firebase Apple Sign-In Provider Not Configured

Setting up the `sign_in_with_apple` package and `Runner.entitlements` is enough for the native Apple login itself to work. But if the Apple provider isn't properly registered in Firebase, the step where Apple credentials are passed to Firebase will fail.

Items to configure in Firebase Console -> Authentication -> Sign-in method -> **Apple**:

| Item | Description |
|------|------|
| Services ID | Services ID created in Apple Developer |
| Apple Team ID | Team ID of the Apple Developer account |
| Key ID | ID of the key with Sign in with Apple permission |
| Private Key | Contents of that key's .p8 file |

Two common mistakes here.

**Mistake 1: Trying to use the APNs key as-is**

If the key was created in Apple Developer Portal only for APNs purposes, it doesn't have Sign in with Apple permission. Registering this key in Firebase will fail during token verification.

You can add Sign in with Apple permission to the existing key. Click the key in the Keys list -> check Sign in with Apple -> Save. The key file itself (p8) doesn't change, so you can use the existing file.

**Mistake 2: Proceeding without a Services ID**

The Services ID is an identifier for Firebase to handle Apple OAuth callbacks. Create it in Apple Developer Portal -> Identifiers -> + -> Services IDs.

After creation, you must configure in **Sign in with Apple Configure**:
- Primary App ID: The actual app's Bundle ID
- Domains: `{project-id}.firebaseapp.com`
- Return URLs: `https://{project-id}.firebaseapp.com/__/auth/handler`

If you omit this callback URL, Apple won't know where to return after authentication and will fail.

---

## Post-Configuration Checklist

```
GoogleService-Info.plist
├── Verify CLIENT_ID exists
└── Verify REVERSED_CLIENT_ID exists

Info.plist
└── REVERSED_CLIENT_ID value registered in CFBundleURLSchemes

Firebase Console
├── Google Sign-In: Enabled
└── Apple Sign-In
    ├── Services ID entered
    ├── Team ID entered
    ├── Key ID entered (key with Sign in with Apple permission)
    └── Private key (.p8 contents) entered

Apple Developer Portal
├── Key: Sign in with Apple permission activated
└── Services ID: Callback URL registered
```

On the simulator, Firebase token verification may work loosely or get mock-handled, so there are many cases where issues only surface in distribution builds. It's better to run through the checklist before uploading to TestFlight.
