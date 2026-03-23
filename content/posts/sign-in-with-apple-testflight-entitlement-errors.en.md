---
title: "Two Back-to-Back TestFlight Build Errors After Adding Sign In with Apple"
date: 2025-09-10
draft: true
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Sign In with Apple", "Deployment"]
description: "After enabling Sign In with Apple in Apple Developer Portal and regenerating provisioning profiles, resolving two consecutive entitlement errors in the build."
cover:
  image: "/images/og/sign-in-with-apple-testflight-entitlement-errors.png"
  alt: "Sign In With Apple Testflight Entitlement Errors"
  hidden: true
---

While adding Sign In with Apple to a Flutter iOS app, I hit two different build errors back to back on the way to getting a TestFlight build out. The causes were distinct, so I'm documenting both here.

---

## Background

Enabling Sign In with Apple is not just a matter of writing code. You also need to add the capability to your App ID in Apple Developer Portal and **regenerate your provisioning profile**. Existing profiles do not include the Sign In with Apple entitlement, so a build against an old profile will fail.

One thing that trips people up repeatedly: Xcode GUI interactions and Flutter plugin additions are not enough on their own. A provisioning profile explicitly lists the entitlements the app is permitted to use. Without regenerating the profile, no matter how correctly you implement Sign In with Apple in code, you will be blocked either at the build stage or when uploading to App Store Connect.

### Setup Steps

In order:

1. Go to [developer.apple.com](https://developer.apple.com) → Identifiers → select your App ID
2. Check **Sign In with Apple** → Edit → select "Enable as a primary App ID" → Save
3. Go to Profiles → Edit your existing App Store profile → Generate → Download
4. Copy the downloaded `.mobileprovision` file into `~/Library/MobileDevice/Provisioning Profiles/`
5. Open Xcode and verify the correct profile is selected under Signing & Capabilities

After completing these steps, things seem ready — but running `flutter build ipa` still produces errors.

### Flutter Project Specifics

In Flutter projects, `ios/Runner.xcodeproj/project.pbxproj` and `ios/Runner/Runner.entitlements` are often edited directly rather than through the Xcode GUI. When Xcode adds a capability through its interface, it automatically updates both the entitlements file and the pbxproj — but when you manage these files manually, mismatches between the two are easy to introduce.

Plugins like `sign_in_with_apple` can also hook into the build process and attempt to inject entries into `Runner.entitlements` at build time. When that happens, Xcode detects that the file was modified mid-build and throws an error.

---

## Error 1: Entitlements file was modified during the build

```
Error (Xcode): Entitlements file "Runner.entitlements" was modified during the build,
which is not supported. You can disable this error by setting
'CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION' to 'YES'
```

### Cause

During the build, Xcode processes entitlements as part of the code signing step. It merges the entitlements from your file with what the provisioning profile expects, producing a final set that gets embedded in the signed binary. If the source file changes during this process — even slightly — Xcode treats it as an integrity violation and aborts the build.

This happens frequently after adding the Sign In with Apple capability because the `sign_in_with_apple` plugin registers a build phase hook that modifies `Runner.entitlements` at build time. Xcode then detects that the file it started signing has been altered and stops.

### Fix

Add the following flag to all three build configurations (Debug, Release, and Profile) for the Runner target in `ios/Runner.xcodeproj/project.pbxproj`:

```
CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;
```

Open the pbxproj file in a text editor and place this line immediately above the `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;` line. There are three Runner target build configurations (Debug, Release, Profile), so you need to add it in all three places.

To find the right lines quickly:

```bash
# Find all lines containing CODE_SIGN_ENTITLEMENTS in the pbxproj
grep -n "CODE_SIGN_ENTITLEMENTS" ios/Runner.xcodeproj/project.pbxproj
```

Use the line numbers from the output to locate each occurrence, then insert `CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;` directly above each one.

Here is what the relevant section should look like after the edit:

```
/* Debug */
buildSettings = {
    CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;  /* added */
    CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements;
    CODE_SIGN_IDENTITY = "Apple Distribution";
    ...
};
```

With this flag set, Xcode permits in-flight modifications to the entitlements file during the build, and the error disappears.

---

## Error 2: Entitlements not found and could not be included in profile

```
Error (Xcode): Entitlements com.apple.developer.devicecheck.appattest-environment
and com.apple.developer.usernotifications.time-sensitive not found and could not
be included in profile. These likely are not valid entitlements and should be
removed from your entitlements file.
```

### Cause

If `Runner.entitlements` contains any entitlement key that is **not present in the provisioning profile**, the build fails.

- `com.apple.developer.devicecheck.appattest-environment` — the App Attest capability. It must be explicitly enabled on the App ID in Developer Portal before the provisioning profile will include it.
- `com.apple.developer.usernotifications.time-sensitive` — Time Sensitive Notifications. Same requirement: must be enabled on the App ID separately.

These had been added to the entitlements file in advance, intending to use them later — but because they had never been activated in Developer Portal, the provisioning profile did not list them. The mismatch between the file and the profile caused the build to fail.

A provisioning profile is generated by Apple's servers and contains only the capabilities that are enabled for that App ID at the time of generation. Even if you write a perfectly correct entitlement key in `Runner.entitlements`, if that key is absent from the profile, the code signing step will detect the discrepancy and fail.

Pre-adding entitlements "for future use" is a common habit, and it is exactly what causes this error.

### Understanding the Runner.entitlements File Structure

`Runner.entitlements` is a plist XML file. If only Sign In with Apple is active, it should look like this:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.applesignin</key>
    <array>
        <string>Default</string>
    </array>
</dict>
</plist>
```

Any entry added here that has no corresponding entry in the provisioning profile will trigger the error.

### Fix

Remove any entitlements from `Runner.entitlements` that are not yet enabled in Developer Portal:

```xml
<!-- Remove: App Attest is not enabled in Developer Portal -->
<key>com.apple.developer.devicecheck.appattest-environment</key>
<string>production</string>

<!-- Remove: Time Sensitive Notifications is not enabled in Developer Portal -->
<key>com.apple.developer.usernotifications.time-sensitive</key>
<true/>
```

When you are actually ready to use these capabilities, the correct sequence is: enable the capability on the App ID in Developer Portal → regenerate and reinstall the provisioning profile → then add the entitlement key back to `Runner.entitlements`.

### How to Check What Entitlements Are in Your Profile

You can inspect the contents of a downloaded `.mobileprovision` file directly to see which entitlements it includes:

```bash
# Print the Entitlements section from a provisioning profile
security cms -D -i ~/Library/MobileDevice/Provisioning\ Profiles/YOUR_PROFILE.mobileprovision \
  | grep -A 30 "<key>Entitlements</key>"
```

Cross-referencing this output with your `Runner.entitlements` file is the fastest way to identify any mismatch.

---

## Core Principle

**The entitlements file and the provisioning profile must match exactly.**

Entitlement keys in the file but absent from the profile cause build errors. Conversely, if a capability is in the profile but missing from the entitlements file, the feature simply will not work at runtime. Every time you add a new capability, three steps must happen together:

1. Enable the capability on the App ID in Developer Portal
2. Regenerate and reinstall the provisioning profile
3. Add the corresponding key to `Runner.entitlements`

Skipping or reordering any of these steps will result in either a build error or silent runtime failure.

---

## From Successful Build to TestFlight Upload

Once both errors are resolved and `flutter build ipa` completes cleanly, you can upload to TestFlight:

```bash
# Build the release IPA
flutter build ipa --release

# Upload to TestFlight using App Store Connect API Key
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

After uploading, check the TestFlight tab in App Store Connect for processing status. If you see a "Missing Compliance" warning, add the following key to `Info.plist` to declare your app's encryption status:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

---

## Key Takeaways

1. **Enabling Sign In with Apple is a three-part operation**: activate the capability in Developer Portal, regenerate the provisioning profile, then update `Runner.entitlements`. Miss any one step and the build breaks.

2. **`CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES` is nearly mandatory for Flutter projects using the Sign In with Apple plugin.** The plugin modifies the entitlements file at build time, and Xcode will refuse to proceed without this flag.

3. **Pre-adding entitlements "for later use" causes real problems.** Keep `Runner.entitlements` in sync with what Developer Portal has actually enabled. Add entitlement keys only when the corresponding capability is active in the profile.

4. **Always inspect the provisioning profile directly.** The `security cms -D -i` command reveals exactly which entitlements a profile contains. Comparing this against your entitlements file is the single most useful first step in debugging any signing-related build failure.

5. **All three build configurations — Debug, Release, and Profile — must be updated consistently.** If you only patch one configuration in the pbxproj, you will see errors that appear only in certain build modes, which can be confusing to diagnose.
