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

After adding the `google_sign_in` package to a Flutter app and running `flutter build ipa`, the build failed at the CocoaPods stage. The error message looks like a simple version conflict, but without understanding how CocoaPods lock files work, you can waste a lot of time chasing the wrong fix. This post covers the exact root cause, the minimal fix, and a complete walkthrough of the Google Sign-In integration process.

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

The version constraint `~> 3.3` is CocoaPods' pessimistic constraint operator, meaning "3.3 or higher, but less than 4.0." In other words, `google_sign_in` wants a 3.x release, but the lock file has 4.5.0 pinned in place.

---

## Root Cause: How CocoaPods Lock Files Work

### What is Podfile.lock?

`Podfile.lock` is a snapshot file that records the exact version of every Pod after a successful `pod install`. Its purpose is to ensure reproducibility — when a teammate clones the project or a CI server runs a build, they get exactly the same Pod versions.

CocoaPods treats `Podfile.lock` as **the highest priority source of truth** during `pod install`. Even when a new dependency is added to the Podfile, existing locked Pods are not re-resolved.

### The Specific Scenario That Causes This Conflict

1. The existing project already has Firebase SDK Pods installed.
2. Firebase SDK internally uses `GTMSessionFetcher 4.5.0`, and this version is pinned in `Podfile.lock`.
3. You add `google_sign_in` to `pubspec.yaml` and run `flutter pub get`.
4. Flutter adds the `google_sign_in_ios` dependency to `ios/Podfile`.
5. When `pod install` runs, it traces the dependency chain: `google_sign_in_ios` → `GoogleSignIn ~> 8.0` → `GTMSessionFetcher/Core ~> 3.3`.
6. CocoaPods tries to install `GTMSessionFetcher 3.x`, but the lock file has `4.5.0` pinned — conflict.

### Why pod install Alone Cannot Fix This

`pod install` only adds Pods that are not yet in the lock file. It does not re-resolve `GTMSessionFetcher 4.5.0`, which is already locked. So the new `google_sign_in` requirement (`~> 3.3`) remains permanently incompatible with the locked version (`4.5.0`), no matter how many times you run `pod install`.

---

## Solution: Update Only the Conflicting Pod

Update just the specific Pod from the iOS directory.

```bash
cd ios && pod update GTMSessionFetcher
```

`pod update [Pod name]` ignores the lock file constraint for that single Pod and re-resolves it from scratch. In this case, CocoaPods will find a version of `GTMSessionFetcher` that satisfies both Firebase and `google_sign_in`'s requirements simultaneously.

In practice, `GTMSessionFetcher` will be updated to a 4.x release that is also compatible with the `~> 3.3` constraint, or both sides will converge on a mutually compatible version.

### Why You Should Avoid a Full pod update

```bash
# Dangerous: upgrades every Pod to the latest version
cd ios && pod update

# Safe: updates only the conflicting Pod
cd ios && pod update GTMSessionFetcher
```

A full `pod update` upgrades every Pod in the project to its latest available version. Firebase, Crashlytics, and other SDKs could jump to versions with breaking changes, introducing new build errors or runtime bugs that are completely unrelated to your original problem. Always specify the target Pod explicitly.

After updating, rebuilding should succeed.

```bash
flutter build ipa --release
```

---

## Complete Integration Walkthrough

Here is the full sequence for integrating Google Sign-In into a Flutter iOS app.

### Step 1: Create an OAuth iOS Client in Google Cloud Console

Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create Credentials → OAuth client ID.

- Application type: **iOS**
- Bundle ID: the `PRODUCT_BUNDLE_IDENTIFIER` from your Xcode project (e.g., `com.example.myapp`)
- Team ID: the `DEVELOPMENT_TEAM` value from your Apple Developer account (10-character alphanumeric string)

After creation, download the `GoogleService-Info.plist` containing the **Client ID** and **Reversed Client ID**.

**Important:** Use the same Google Cloud project as your Firebase project. Creating the OAuth client in a different project will cause token verification failures at runtime, since Google's servers validate that the client ID belongs to the expected project.

### Step 2: Add CLIENT_ID to GoogleService-Info.plist

The `GoogleService-Info.plist` downloaded from Firebase Console may not include the OAuth `CLIENT_ID` by default. Add it manually using the values from the OAuth client you just created.

```xml
<key>CLIENT_ID</key>
<string>YOUR_CLIENT_ID.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
```

The `REVERSED_CLIENT_ID` is the `CLIENT_ID` with its dot-separated segments reversed. For example, if your Client ID is `123456-abcdef.apps.googleusercontent.com`, the Reversed Client ID is `com.googleusercontent.apps.123456-abcdef`.

### Step 3: Add URL Scheme to Info.plist

Google Sign-In uses the OAuth 2.0 authorization flow: it opens Safari or an `SFSafariViewController`, and once authentication is complete it redirects back to your app. To handle this redirect, register `REVERSED_CLIENT_ID` as a URL scheme.

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

Without this, the user will complete authentication in Safari but the app will never receive the callback — the user stays stuck in the browser.

### Step 4: Add the Package to pubspec.yaml

```yaml
dependencies:
  google_sign_in: ^6.2.2
```

Running `flutter pub get` will automatically add the `google_sign_in_ios` dependency to `ios/Podfile`.

### Step 5: Resolve the Version Conflict

```bash
flutter pub get
cd ios && pod update GTMSessionFetcher
```

### Step 6: Build and Deploy

```bash
flutter build ipa --release
```

---

## Step-by-Step Debugging Approach

If the error feels overwhelming at first, work through these steps in order.

### Step 1: Identify the Conflicting Pod from the Error Message

Read the error message carefully. CocoaPods explicitly shows the full dependency chain that led to the conflict. In the example above, `GTMSessionFetcher` is identified as the conflicting Pod.

### Step 2: Check the Currently Pinned Version in Podfile.lock

```bash
cat ios/Podfile.lock | grep GTMSessionFetcher
```

Sample output:
```
  - GTMSessionFetcher/Core (4.5.0)
  - GTMSessionFetcher/Full (4.5.0)
GTMSessionFetcher/Core: 4.5.0
```

### Step 3: Run a Targeted Pod Update

```bash
cd ios && pod update GTMSessionFetcher
```

After updating, verify that the version in `Podfile.lock` has changed.

### Step 4: Retry the Build

```bash
flutter build ipa --release
```

If the same error persists, another Pod in the dependency chain may also be involved. Check the new error message for additional conflicting Pods and apply the same fix.

---

## Common Mistakes

- **Running `pod install` repeatedly**: As long as the lock file exists, the result will not change. You need `pod update [Pod name]`.
- **Running a full `pod update`**: This can upgrade unrelated Pods and introduce new build errors. Specify only the conflicting Pod.
- **Creating the OAuth client in the wrong project**: If the OAuth client is in a different Google Cloud project than Firebase, token verification will fail at runtime.
- **Mismatched `CLIENT_ID` and URL Scheme**: The `CLIENT_ID` in `GoogleService-Info.plist` and the `CFBundleURLSchemes` entry in `Info.plist` must correspond exactly. If either is missing or incorrect, the Google Sign-In callback will not work on iOS.
- **Forgetting to run flutter clean after pod update**: In some cases, stale Flutter build cache can keep the problem alive. Try `flutter clean && flutter pub get` followed by a fresh build.

---

## Prevention

A few habits can prevent this type of conflict from recurring.

### Check Native Dependencies Before Adding a New Package

Before adding a new Flutter package, look up its native dependency chain. Packages that use Google SDKs — such as `google_sign_in`, `googleapis`, or various Firebase plugins — frequently share libraries like `GTMSessionFetcher` and `GoogleUtilities`, making version conflicts with Firebase common.

### Commit Podfile.lock to Git

Always include `Podfile.lock` in your git repository. This prevents Pod version mismatches across team members and makes it possible to roll back to a known-good state when problems arise.

### Use pod install in CI, pod update Locally

In CI/CD pipelines, use `pod install` to reproduce the exact versions from the lock file. Reserve `pod update` for intentional version upgrades on your local development machine.

### Resolve Dependency Conflicts Immediately

Leaving conflicts unresolved causes them to compound. The next time you add a package, you may face multiple interacting conflicts that are much harder to untangle. Fixing them as soon as they appear, with the minimal targeted approach, keeps the dependency graph clean.

---

## Key Takeaways

- `Podfile.lock` is a snapshot file that pins Pod versions, and `pod install` always prioritizes it over new requirements.
- Both Firebase and `google_sign_in` depend on `GTMSessionFetcher`, making version conflicts between them common.
- The fix is `cd ios && pod update GTMSessionFetcher` — update only the conflicting Pod, not everything.
- A full `pod update` risks upgrading unrelated Pods and introducing new side effects; avoid it.
- When integrating Google Sign-In, `CLIENT_ID` in `GoogleService-Info.plist` and the URL Scheme in `Info.plist` must be configured as a matching pair.
- The OAuth client must be created in the same Google Cloud project as Firebase for token validation to succeed.
