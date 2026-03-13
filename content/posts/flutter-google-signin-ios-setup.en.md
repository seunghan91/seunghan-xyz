---
title: "Flutter Google Sign-In iOS Setup: Missing CLIENT_ID in GoogleService-Info.plist"
date: 2025-06-04
draft: false
tags: ["Flutter", "iOS", "Google Sign-In", "Firebase", "OAuth"]
description: "When integrating google_sign_in package on iOS, login won't work if GoogleService-Info.plist is missing CLIENT_ID. Setup instructions."
cover:
  image: "/images/og/flutter-google-signin-ios-setup.png"
  alt: "Flutter Google Signin Ios Setup"
  hidden: true
---


When implementing Google Sign-In with the `google_sign_in` package in a Flutter app and it only fails on iOS, the cause is often a missing `CLIENT_ID` in `GoogleService-Info.plist`.

---

## Problem

Google Sign-In works fine on Android, but on iOS the login dialog doesn't appear or an error occurs.

You registered the iOS app in Firebase Console and added the downloaded `GoogleService-Info.plist` to the project, but the default download file sometimes doesn't include `CLIENT_ID`.

---

## Adding CLIENT_ID to GoogleService-Info.plist

### 1. Verify the iOS OAuth Client

Go to Google Cloud Console -> **APIs & Services -> Credentials**.

When you create a Firebase project, an iOS OAuth client is automatically created. The client ID format is:

```
{project-number}-{hash}.apps.googleusercontent.com
```

### 2. Add Two Keys to the plist

Add the following two keys to the `ios/Runner/GoogleService-Info.plist` file.

```xml
<key>CLIENT_ID</key>
<string>{project-number}-{hash}.apps.googleusercontent.com</string>

<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{project-number}-{hash}</string>
```

`REVERSED_CLIENT_ID` is the CLIENT_ID reversed. Simply reverse the order of segments separated by dots (`.`).

Example:
```
CLIENT_ID:          1234567890-abcdef.apps.googleusercontent.com
REVERSED_CLIENT_ID: com.googleusercontent.apps.1234567890-abcdef
```

---

## Registering URL Scheme in Info.plist

A URL Scheme must be added to `ios/Runner/Info.plist` so the app can return from Google login.

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

The URL Scheme value registered here must match the `REVERSED_CLIENT_ID`.

---

## How the google_sign_in Package Works

The `google_sign_in` iOS implementation reads `GoogleService-Info.plist` at app startup and automatically configures the client ID. You don't need to pass the clientId in code -- if it's in the plist, it's applied automatically.

```dart
// Automatically reads the plist without separate configuration in code
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: ['email', 'profile'],
);
```

Android, on the other hand, reads `client_id` from `google-services.json`.

---

## When CLIENT_ID Is Missing from Firebase iOS App Registration

When adding an iOS app in Firebase Console and downloading `GoogleService-Info.plist`, the `CLIENT_ID` key may be missing. This is because the iOS OAuth client hasn't been created yet in Google Cloud Console.

Solution:

1. Google Cloud Console -> **Credentials -> + Create Credentials -> OAuth client ID**
2. Application type: **iOS**
3. Enter Bundle ID and create
4. Manually add the generated client ID to the plist

Alternatively, Firebase Console -> Project Settings -> Your Apps -> re-download `GoogleService-Info.plist` -- it may be included automatically.

---

## Checklist

- [ ] Verify `CLIENT_ID` key exists in `GoogleService-Info.plist`
- [ ] Verify `REVERSED_CLIENT_ID` key exists in `GoogleService-Info.plist`
- [ ] Verify `REVERSED_CLIENT_ID` value is registered in `CFBundleURLSchemes` in `Info.plist`
- [ ] Verify the same scheme is registered in Xcode Runner target's URL Types

Most iOS Google Sign-In issues come from one of these four being missing.
