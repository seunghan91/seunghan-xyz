---
title: "Flutter iOS Google Sign-In: When GIDClientID is Missing from Info.plist"
date: 2025-08-23
draft: true
tags: ["Flutter", "iOS", "Google Sign-In", "OAuth", "Info.plist"]
description: "When integrating Google OAuth directly without GoogleService-Info.plist, GIDClientID must be separately added to Info.plist. Missing it causes 'No active configuration' error."
cover:
  image: "/images/og/ios-gidclientid-info-plist-missing.png"
  alt: "Ios Gidclientid Info Plist Missing"
  hidden: true
---


When implementing Google Sign-In in a Flutter iOS app, you may issue an OAuth client ID directly from Google Cloud Console without using Firebase. In this case, if you do not explicitly add `GIDClientID` to `Info.plist`, a runtime error occurs.

When using a Firebase project, `GoogleService-Info.plist` automatically handles this role, making it easy to overlook. This post covers the error cause and the fix.

---

## Error Message

```
PlatformException(google_sign_in, No active configuration.
Make sure GIDClientID is set in Info.plist., null, null)
```

---

## Cause

The `google_sign_in` iOS SDK reads the `GIDClientID` key from `Info.plist` during initialization.

When using Firebase, adding `GoogleService-Info.plist` to the project lets the SDK automatically read and process that file. However, when using OAuth directly without Firebase, this file does not exist, so you must add the key directly to `Info.plist`.

It is common to add only the URL Scheme (reversed client ID) to `Info.plist` and forget to add `GIDClientID`.

---

## How to Verify

Open `Info.plist` and check that both entries exist.

```xml
<!-- URL Scheme (reversed client ID) -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.{project-number}-{hash}</string>
    </array>
  </dict>
</array>

<!-- GIDClientID (forward client ID) -->
<key>GIDClientID</key>
<string>{project-number}-{hash}.apps.googleusercontent.com</string>
```

The URL Scheme and `GIDClientID` are the same OAuth client ID with the parts reversed.

- URL Scheme: `com.googleusercontent.apps.{project-number}-{hash}`
- GIDClientID: `{project-number}-{hash}.apps.googleusercontent.com`

---

## Where to Find the Client ID

**Google Cloud Console -> APIs & Services -> Credentials**

Find the OAuth client ID registered as an iOS app. The client ID format `{numbers}-{alphanumeric-hash}.apps.googleusercontent.com` confirms it.

---

## Fix

Add the `GIDClientID` key to `Info.plist`.

```xml
<key>GIDClientID</key>
<string>123456789000-abcdefghijklmnop.apps.googleusercontent.com</string>
```

After adding it and rebuilding the app, the `PlatformException: No active configuration` error disappears.

---

## Common Mistake: Adding Only URL Scheme and Missing GIDClientID

When following Google Sign-In iOS setup guides, you tend to focus on URL Scheme addition. Adding the reversed client ID to URL Schemes is a prominent step, while adding `GIDClientID` is often not described as a separate item.

As a result, you end up with the URL Scheme present but `GIDClientID` missing. The build succeeds but the error occurs at runtime.

---

## Dart Code Initialization (v7.x and Later)

Starting from `google_sign_in` package v7.x, you can also pass the client ID directly in code.

```dart
// Setting directly in code instead of Info.plist
final GoogleSignIn _googleSignIn = GoogleSignIn(
  clientId: '123456789000-abcdefghijklmnop.apps.googleusercontent.com',
  scopes: ['email'],
);
```

However, this method exposes the client ID in source code, so setting it in `Info.plist` is more common.

---

## Setup Comparison by Firebase Usage

| Method | Required Setup |
|--------|----------------|
| Using Firebase | Just add `GoogleService-Info.plist` to the project |
| Without Firebase | Manually add `GIDClientID` + `CFBundleURLSchemes` to `Info.plist` |

When copying code from a Firebase-based project, it is easy to miss that these settings are needed in a non-Firebase environment.

---

## References

- Starting from `google_sign_in` package v7.x, the API changed to use `GoogleSignIn.instance`.
- When using Firebase, including `GoogleService-Info.plist` in the project is sufficient with no additional setup needed.
- The above setup is only needed when integrating directly without Firebase.
- You must create a separate iOS-type OAuth client ID in Google Cloud Console (separate from Android and Web types).
