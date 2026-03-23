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

When using a Firebase project, `GoogleService-Info.plist` automatically handles this role, making it easy to overlook. This post covers the error cause, the fix, debugging steps, and the common mistake patterns that lead to this problem in the first place.

---

## Error Message

```
PlatformException(google_sign_in, No active configuration.
Make sure GIDClientID is set in Info.plist., null, null)
```

This error appears the first time you tap the Google Sign-In button after launching the app. There is no warning during the build phase, so it can catch you off guard. The message is explicit enough once you understand the underlying mechanism, but if you have only ever worked with Firebase-based setups, the requirement to set `GIDClientID` manually is not obvious.

---

## Background: What Firebase Does for You

The `google_sign_in` Flutter package uses the Google Sign-In iOS SDK internally. During initialization, the SDK needs to read its configuration. It has two ways to do this:

1. **With Firebase**: The SDK automatically parses `GoogleService-Info.plist` bundled with the project, extracting `GIDClientID` along with other values.
2. **Without Firebase**: The SDK reads the `GIDClientID` key directly from `Info.plist`.

In a Firebase project, dropping `GoogleService-Info.plist` into the project is all you need — the SDK handles the rest automatically. This convenience makes it easy to forget what actually needs to be configured when Firebase is not in the picture.

---

## Cause

The `google_sign_in` iOS SDK reads the `GIDClientID` key from `Info.plist` during initialization.

When using Firebase, adding `GoogleService-Info.plist` to the project lets the SDK automatically read and process that file. However, when using OAuth directly without Firebase, this file does not exist, so you must add the key directly to `Info.plist`.

It is common to add only the URL Scheme (reversed client ID) to `Info.plist` and forget to add `GIDClientID`. The URL Scheme handles the OAuth redirect callback so iOS can return control to your app after sign-in. `GIDClientID` is what the SDK uses to identify which OAuth application to authenticate against. Both are required and both derive from the same client ID string — just formatted differently.

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

The URL Scheme and `GIDClientID` are the same OAuth client ID with the components in reverse order.

- URL Scheme: `com.googleusercontent.apps.{project-number}-{hash}`
- GIDClientID: `{project-number}-{hash}.apps.googleusercontent.com`

For example, if your client ID is `123456789000-abcdefghijklmnop.apps.googleusercontent.com`:

- URL Scheme value: `com.googleusercontent.apps.123456789000-abcdefghijklmnop`
- `GIDClientID` value: `123456789000-abcdefghijklmnop.apps.googleusercontent.com`

Both point to the same OAuth client but use different notations. The URL Scheme uses reverse domain notation, which is how iOS routes deep links. `GIDClientID` is the forward identifier used when calling Google APIs.

---

## Where to Find the Client ID

**Google Cloud Console -> APIs & Services -> Credentials**

Find the OAuth client ID registered as an iOS app. The client ID format `{numbers}-{alphanumeric-hash}.apps.googleusercontent.com` confirms it is the right one.

A few things to watch out for:

- **You must use an iOS-type client ID.** Android and Web client IDs are separate. When creating a new OAuth client ID in Google Cloud Console, make sure to select "iOS" as the application type.
- **The bundle ID must match.** The bundle ID you entered when creating the iOS client ID must exactly match your Xcode project's bundle ID. A mismatch will cause authentication to fail even with the correct `GIDClientID` set.
- **Check the correct Google Cloud project.** Even without Firebase, OAuth client IDs are managed inside a Google Cloud project. If you run multiple projects, confirm you are looking at the right one.

---

## Fix

Add the `GIDClientID` key to `Info.plist`.

```xml
<key>GIDClientID</key>
<string>123456789000-abcdefghijklmnop.apps.googleusercontent.com</string>
```

After adding it and rebuilding the app, the `PlatformException: No active configuration` error disappears.

In a Flutter project, `Info.plist` lives at `ios/Runner/Info.plist`. You can edit it directly as XML in any text editor, or open it in Xcode using the Property List editor. In Xcode, click the `+` button to add a new row, set the type to `String`, enter `GIDClientID` as the key, and paste your client ID as the value.

---

## Common Mistake: Adding Only the URL Scheme and Forgetting GIDClientID

When following Google Sign-In iOS setup guides, attention naturally focuses on the URL Scheme step. Adding the reversed client ID to `CFBundleURLSchemes` is a prominent, well-explained step. Adding `GIDClientID` is often buried in a separate section or mentioned only as a passing note, making it easy to skip.

The result: the URL Scheme is present, `GIDClientID` is absent, the build succeeds, and the error only surfaces at runtime.

This mistake is especially common for a few reasons. Google's official Flutter integration guides frequently assume Firebase is in use. The `google_sign_in` package README treats Firebase as the default path. The Firebase-free integration steps exist but are presented as an alternative rather than a primary workflow.

Another common source of this bug is copying code from a Firebase-based project. The Flutter-side code looks nearly identical whether you use Firebase or not. But the iOS layer fails to initialize when `GoogleService-Info.plist` is absent and `Info.plist` has not been updated. The result is confusing: identical Dart code that works in one project and fails in another.

---

## Debugging Checklist

If you encounter the error, check these items in order:

1. Confirm `GIDClientID` key exists in `ios/Runner/Info.plist`
2. Confirm the `GIDClientID` value is in forward format (`{numbers}-{hash}.apps.googleusercontent.com`), not reverse format — putting the reversed string here is a common copy-paste error
3. Confirm `CFBundleURLSchemes` contains the reversed client ID (`com.googleusercontent.apps.{numbers}-{hash}`)
4. Confirm an iOS-type OAuth client ID is registered in Google Cloud Console
5. Confirm the bundle ID in the client ID registration matches your app's bundle ID exactly
6. Confirm `GoogleService-Info.plist` is not present in the project — if it is, the SDK reads from it and ignores `Info.plist`

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

However, this method embeds the client ID in source code. Setting it in `Info.plist` is the more common approach because it separates configuration from code.

v7.x also introduced the `GoogleSignIn.instance` singleton pattern as an alternative to creating instances directly. Either approach works, but the preference for keeping `clientId` in `Info.plist` holds regardless of which initialization style you use.

Whether embedding a client ID in source code is a security concern is a fair question. OAuth client IDs are public identifiers — they are not secrets in the same way an API secret key is. However, keeping the value in `Info.plist` gives you the flexibility to use different client IDs per build environment (development, staging, production) without changing Dart code.

---

## Setup Comparison by Firebase Usage

| Method | Required Setup |
|--------|----------------|
| Using Firebase | Just add `GoogleService-Info.plist` to the project |
| Without Firebase | Manually add `GIDClientID` + `CFBundleURLSchemes` to `Info.plist` |

When copying code from a Firebase-based project, it is easy to miss that these settings are needed in a non-Firebase environment.

Both approaches use the same Google Sign-In iOS SDK under the hood. The difference is only where the SDK reads its configuration from. With Firebase, `GoogleService-Info.plist` acts as the automatic source. Without Firebase, `Info.plist` is the explicit source.

This distinction also matters when adding or removing Firebase from an existing project. If you remove Firebase and delete `GoogleService-Info.plist` without adding `GIDClientID` to `Info.plist`, Google Sign-In will break even though you did not change any Dart code. The failure happens silently during the iOS SDK initialization phase, making it harder to trace if you are not familiar with this behavior.

---

## Key Takeaways

- Without Firebase, `GIDClientID` must be added to `Info.plist` manually — it is not inferred from anywhere else
- Both the URL Scheme (reversed client ID) and `GIDClientID` (forward client ID) are required; they serve different purposes even though they derive from the same string
- You must create a separate iOS-type OAuth client ID in Google Cloud Console — Android and Web client IDs are not interchangeable
- `No active configuration` always means `GIDClientID` is missing or unreadable; check `Info.plist` first
- If you remove Firebase from a project, add `GIDClientID` to `Info.plist` immediately to keep Google Sign-In working

---

## References

- Starting from `google_sign_in` package v7.x, the API changed to use `GoogleSignIn.instance`.
- When using Firebase, including `GoogleService-Info.plist` in the project is sufficient with no additional setup needed.
- The above setup is only needed when integrating directly without Firebase.
- You must create a separate iOS-type OAuth client ID in Google Cloud Console (separate from Android and Web types).
