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

Both Google Sign-In and Apple Sign-In failed in TestFlight builds. They worked perfectly on the simulator but broke the moment the app was distributed through TestFlight. This is a surprisingly common pattern — authentication flows that appear healthy in development silently break in production builds because the two environments behave very differently under the hood.

This post walks through the two root causes I found, the exact debugging steps, and the configuration details that are easy to miss.

---

## Why the Simulator Hides These Bugs

Before diving into the fixes, it is worth understanding why simulators and TestFlight builds diverge so sharply on authentication.

The iOS Simulator does not enforce URL Scheme handling the same way a real device does. When Google Sign-In completes its OAuth flow, it attempts to return control to your app via a custom URL Scheme (`REVERSED_CLIENT_ID`). On a simulator, the system often handles this redirect more loosely — sometimes the SFSafariViewController session resolves without a strict scheme match, or the flow falls back to a web-based path that bypasses scheme validation entirely.

Firebase's token verification is similarly more permissive in debug builds. The SDK may accept credentials without fully verifying the server-side configuration against the Firebase project, especially in development environments where `DEBUG` flags are set.

Once you build for distribution — which TestFlight requires — all of these shortcuts disappear. The app is compiled in `Release` mode, URL Scheme handling is strict, and Firebase validates credentials against its server-side configuration in full. Any gap in setup that the simulator quietly worked around will surface as an immediate failure.

---

## Cause 1: Missing CLIENT_ID in GoogleService-Info.plist

When you first register an iOS app in Firebase Console and download `GoogleService-Info.plist`, `CLIENT_ID` and `REVERSED_CLIENT_ID` are typically included. However, if you download the file **before enabling Google Sign-In in Firebase Authentication**, these keys are generated without them.

This is the exact sequence that traps many developers: you set up Firebase early in a project, download the plist, add it to Xcode, and commit it. Weeks later you add Google Sign-In. You enable it in the Firebase Authentication console, test on the simulator, everything looks fine — but the plist you have on disk is still the old one without `CLIENT_ID`.

How to check:

```bash
grep -A1 "CLIENT_ID\|REVERSED_CLIENT_ID" ios/Runner/GoogleService-Info.plist
```

If nothing comes back, the keys are missing. You can also open the file directly and search for the `CLIENT_ID` key — a properly configured plist will have entries that look like:

```xml
<key>CLIENT_ID</key>
<string>XXXXXXXX-xxxx.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.XXXXXXXX-xxxx</string>
```

If these are absent, the entire Google Sign-In flow on a real device is broken at a foundational level.

### Why This Is a Problem

On iOS, Google Sign-In uses `SFSafariViewController` or `ASWebAuthenticationSession` to present the Google OAuth consent screen. When the user completes authentication, Google redirects the browser back to your app using a custom URL Scheme. That scheme must be registered in your app's `Info.plist` under `CFBundleURLSchemes`.

The value used for this scheme is `REVERSED_CLIENT_ID` — it looks like `com.googleusercontent.apps.{your-client-id}`. Without this value in your plist, you cannot register the scheme, and the redirect back to your app never arrives. The OAuth flow simply hangs or silently times out. On TestFlight (a real device, release build), this manifests as the Google login sheet appearing, the user authenticating, and then nothing happening — no callback, no error, the app just sits there.

### Solution

Go to Firebase Console → Project Settings → Your iOS App → then navigate to Authentication → Sign-in method and enable Google. Once enabled, go back to Project Settings and re-download `GoogleService-Info.plist`. Replace the existing file in your Xcode project — make sure the new file is actually added to the Runner target, not just copied into the directory.

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

The `REVERSED_CLIENT_ID` value is in the newly downloaded plist. Copy it exactly — including the `com.googleusercontent.apps.` prefix. Any typo here means the OAuth redirect will fail to match your app and authentication will never complete.

If your project uses `project.yml` with XcodeGen, make sure to add the URL scheme there as well and regenerate the Xcode project. Editing `Info.plist` directly in a XcodeGen project will be overwritten on the next `xcodegen generate` run.

---

## Cause 2: Firebase Apple Sign-In Provider Not Configured

Setting up the `sign_in_with_apple` package and `Runner.entitlements` is enough for the native Apple login UI to work. The system-level "Sign in with Apple" sheet will appear and the user can authenticate. But there are two separate steps in Apple Sign-In for a Firebase app:

1. Native Apple authentication (handled by the OS) — produces a credential with an identity token
2. Firebase credential exchange — your app passes that identity token to Firebase to create or sign into a Firebase user

Step 1 can succeed even with a completely broken Firebase Apple provider configuration. Step 2 will fail silently or throw a generic Firebase error if the Apple provider in Firebase is missing or misconfigured.

Items to configure in Firebase Console → Authentication → Sign-in method → **Apple**:

| Item | Description |
|------|-------------|
| Services ID | Services ID created in Apple Developer Portal |
| Apple Team ID | Team ID of your Apple Developer account |
| Key ID | ID of a key that has Sign in with Apple permission enabled |
| Private Key | The full contents of that key's .p8 file |

### Mistake 1: Trying to Use the APNs Key As-Is

This is extremely common. Most Flutter/Firebase projects already have an APNs key registered to enable push notifications. When it is time to configure Apple Sign-In, it is tempting to reuse the same key — it is already in your secrets folder, already registered in Firebase for FCM, so why not?

The problem is that a key created only for APNs does not have the "Sign in with Apple" capability checked. When Firebase receives an Apple identity token and attempts to verify it using this key, the verification fails because the key does not have the authority to validate Sign in with Apple tokens.

The fix is straightforward: go to Apple Developer Portal → Certificates, Identifiers & Profiles → Keys → click your existing key → edit it to add "Sign in with Apple" → save. The key file itself (the `.p8` file) does not change — the capability is stored server-side in Apple's system. You do not need to re-download the key or update anything in your secrets folder.

After enabling the capability, go back to Firebase Console and add the Key ID and the `.p8` contents to the Apple Sign-In provider configuration.

### Mistake 2: Proceeding without a Services ID

A Services ID is a separate entity from your app's Bundle ID. It is Apple's mechanism for identifying the OAuth client that Firebase uses to handle the Apple authentication callback. If you skip this step, Firebase cannot complete the Apple OAuth flow on its end.

Create it in Apple Developer Portal → Certificates, Identifiers & Profiles → Identifiers → click the `+` button → choose "Services IDs" → register with a reverse-domain identifier like `com.yourapp.siwa` (convention: append `.siwa` to your bundle ID to distinguish it).

After creation, click the Services ID and configure Sign in with Apple:

- **Primary App ID**: Select your actual app's Bundle ID (e.g., `com.yourapp.app`)
- **Domains and Subdomains**: `{your-firebase-project-id}.firebaseapp.com`
- **Return URLs**: `https://{your-firebase-project-id}.firebaseapp.com/__/auth/handler`

The Return URL is critical. This is where Apple sends the user after authentication. Firebase's auth handler at `/__/auth/handler` receives the token, validates it, and completes the sign-in flow. If this URL is missing or has a typo, Apple completes authentication on its end but has nowhere to send the result — the flow terminates.

Once the Services ID is configured, enter its identifier in Firebase Console under the Apple Sign-In provider's "Services ID" field.

---

## Debugging When You Are Not Sure Which Step Is Failing

If you are troubleshooting authentication failures in a TestFlight build and are not sure whether the failure is at step 1 (native Apple auth) or step 2 (Firebase credential exchange), add temporary logging around the Firebase `signInWithCredential` call:

```dart
try {
  final appleCredential = await SignInWithApple.getAppleIDCredential(
    scopes: [
      AppleIDAuthorizationScopes.email,
      AppleIDAuthorizationScopes.fullName,
    ],
  );

  final oauthCredential = OAuthProvider("apple.com").credential(
    idToken: appleCredential.identityToken,
    rawNonce: rawNonce,
  );

  final userCredential = await FirebaseAuth.instance
      .signInWithCredential(oauthCredential);

  print("Firebase UID: ${userCredential.user?.uid}");
} on FirebaseAuthException catch (e) {
  print("Firebase error: ${e.code} — ${e.message}");
} catch (e) {
  print("Unexpected error: $e");
}
```

A `FirebaseAuthException` with code `invalid-credential` or `web-context-cancelled` points to the Firebase provider configuration. If `getAppleIDCredential` itself throws, the issue is with the native entitlements or Capabilities setup in Xcode. This distinction narrows down whether the problem is in Apple Developer Portal, Firebase Console, or your Xcode project.

For Google Sign-In failures, check if `GoogleSignIn().signIn()` returns `null` (user cancelled or redirect failed) versus throwing an exception (configuration error). A `null` return that happens immediately after the Google sheet dismisses usually means the URL Scheme redirect failed.

---

## Post-Configuration Checklist

```
GoogleService-Info.plist
├── Verify CLIENT_ID exists
└── Verify REVERSED_CLIENT_ID exists

Info.plist (or project.yml if using XcodeGen)
└── REVERSED_CLIENT_ID value registered in CFBundleURLSchemes

Firebase Console → Authentication → Sign-in method
├── Google Sign-In: Enabled
└── Apple Sign-In
    ├── Services ID entered (e.g., com.yourapp.siwa)
    ├── Team ID entered
    ├── Key ID entered (key must have Sign in with Apple permission)
    └── Private key (.p8 contents) entered

Apple Developer Portal
├── Key: Sign in with Apple capability enabled
└── Services ID
    ├── Primary App ID: your app's Bundle ID
    ├── Domains: {project-id}.firebaseapp.com
    └── Return URLs: https://{project-id}.firebaseapp.com/__/auth/handler
```

On the simulator, Firebase token verification may work loosely or get mock-handled, so issues frequently only surface in distribution builds. The safest approach is to treat the simulator as a UI preview tool and use a physical device with a debug or ad-hoc build to verify authentication flows before submitting to TestFlight.

---

## Key Takeaways

- **Download `GoogleService-Info.plist` after enabling Google Sign-In** in Firebase Authentication, not before. The order matters — the file content reflects which providers are enabled at the time of download.
- **`REVERSED_CLIENT_ID` must be registered as a URL Scheme** in `Info.plist`. Without this, the Google OAuth redirect callback never reaches the app on a real device.
- **Apple Sign-In has two independent layers**: the native OS authentication (entitlements + Apple Developer) and the Firebase credential exchange (Firebase Console configuration). Both must be correct.
- **Reusing an APNs key for Sign in with Apple is a common trap**. Add the Sign in with Apple capability to the existing key in Apple Developer Portal — no need to create a new key or re-download the `.p8` file.
- **Services ID configuration, specifically the Return URL**, is the most frequently skipped step. Without it, Apple's OAuth flow completes but has no valid destination to deliver the credential.
- **The simulator is not a reliable test environment for authentication**. Always verify auth flows on a physical device with a release or ad-hoc build before pushing to TestFlight.
