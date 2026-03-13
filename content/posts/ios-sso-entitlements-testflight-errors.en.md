---
title: "iOS TestFlight Deployment Debugging: From SSO Errors to Entitlements Mismatch"
date: 2025-08-30
draft: false
tags: ["iOS", "Flutter", "TestFlight", "Apple Sign-In", "Google OAuth", "Provisioning", "Deployment"]
description: "Apple Sign-In error 1000, Google OAuth 400 invalid_request, entitlements mismatch, BGTaskSchedulerPermittedIdentifiers missing — errors encountered during TestFlight deployment and their fixes."
cover:
  image: "/images/og/ios-sso-entitlements-testflight-errors.png"
  alt: "Ios Sso Entitlements Testflight Errors"
  hidden: true
---


Here are the errors repeatedly encountered while uploading multiple Flutter apps to TestFlight.

---

## 1. Apple Sign-In Error 1000

```
SignInWithAppleAuthorizationException(AuthorizationErrorCode.unknown,
The operation couldn't be completed.
(com.apple.AuthenticationServices.AuthorizationError error 1000.))
```

### Cause

This occurs because the Sign in with Apple capability is missing from `Runner.entitlements`.

### Solution

**Both** places must be configured.

**1. `ios/Runner/Runner.entitlements`**

```xml
<key>com.apple.developer.applesignin</key>
<array>
    <string>Default</string>
</array>
```

**2. Apple Developer Console**

`developer.apple.com` -> Identifiers -> Select app Bundle ID -> Check **Sign in with Apple** -> Save

If a provisioning profile already exists, it needs to be regenerated.

> If you only modify the entitlements file without activating it in the Console, error 1000 still occurs.

---

## 2. Google OAuth Error 400: invalid_request

```
Error 400: invalid_request
Request details: flowName=GeneralOAuthFlow
```

When attempting login with the Flutter `google_sign_in` package, the Google login screen does not appear and a 400 error occurs in the browser.

### Root Cause Analysis

When login fails, the redirect URL contains an `authError` parameter. Base64 decoding reveals the actual cause.

```bash
python3 -c "
import base64
encoded = '<authError parameter value>'
print(base64.b64decode(encoded + '==').decode('utf-8', errors='replace'))
"
# Result: "Custom scheme URIs are not allowed for 'WEB' client type."
```

### Cause

The `CLIENT_ID` in `GoogleService-Info.plist` was a **Web type** OAuth client.

The `google_sign_in` package redirects using the custom URL scheme of an iOS-type client (`com.googleusercontent.apps.{ID}:/oauthredirect`). Web type does not allow this method.

### Solution

You must create a new **iOS type** OAuth client in Google Cloud Console.

- Application type: `iOS` (not Web)
- Bundle ID: Enter the app bundle ID
- Team ID: Apple team ID

After creation, download the `.plist` file and update three places.

**1. `ios/Runner/GoogleService-Info.plist`**

```xml
<key>CLIENT_ID</key>
<string>{iOS_CLIENT_ID}.apps.googleusercontent.com</string>
<key>REVERSED_CLIENT_ID</key>
<string>com.googleusercontent.apps.{iOS_CLIENT_ID}</string>
```

**2. `ios/Runner/Info.plist`**

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.{iOS_CLIENT_ID}</string>
        </array>
    </dict>
</array>
```

**3. Backend environment variable**

```
GOOGLE_CLIENT_ID={iOS_CLIENT_ID}.apps.googleusercontent.com
```

When the backend verifies the JWT `aud` claim, it must match the iOS CLIENT_ID.

> iOS-type OAuth clients cannot be created via CLI or Firebase SDK. It is only possible through the Google Cloud Console UI.

---

## 3. Provisioning Profile Entitlements Mismatch

```
Provisioning profile "iOS Team Provisioning Profile: com.example.app"
doesn't match the entitlements file's value for the
com.apple.developer.default-data-protection entitlement.
```

### Cause

This occurs when a capability declared in `Runner.entitlements` is not included in the current provisioning profile.

Common problematic items:

- `com.apple.developer.default-data-protection`
- `com.apple.developer.icloud-container-identifiers`
- `com.apple.developer.icloud-services`

### Solution

Choose one of two approaches.

**Option A: Enable capability in Apple Developer Console**

Enable the required capability on the App ID and regenerate the provisioning profile.

**Option B: Remove unused entitlements (recommended)**

If the app does not actually use the capability, remove it from `Runner.entitlements`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <!-- Keep only what is actually used -->
    <key>aps-environment</key>
    <string>production</string>
    <key>com.apple.developer.applesignin</key>
    <array>
        <string>Default</string>
    </array>
</dict>
</plist>
```

> `default-data-protection` is a security policy setting, so removing it does not affect app behavior.

---

## 4. Xcode Manual Signing Conflicts with Automatic Signing

```
Runner has conflicting provisioning settings. Runner is automatically signed,
but provisioning profile PROFILE_NAME has been manually specified.
```

### Cause

A specific provisioning profile is hardcoded in `project.pbxproj` while the build command requests Automatic signing, causing a conflict.

### Solution

Change manual signing settings to Automatic in `ios/Runner.xcodeproj/project.pbxproj`.

```bash
sed -i '' \
  -e 's/CODE_SIGN_STYLE = Manual;/CODE_SIGN_STYLE = Automatic;/g' \
  -e 's/CODE_SIGN_IDENTITY = "iPhone Distribution";/CODE_SIGN_IDENTITY = "iPhone Developer";/g' \
  -e '/PROVISIONING_PROFILE_SPECIFIER = ".*";/d' \
  ios/Runner.xcodeproj/project.pbxproj
```

---

## 5. TestFlight Upload Failure: Missing BGTaskSchedulerPermittedIdentifiers

```
Missing Info.plist value. The Info.plist key 'BGTaskSchedulerPermittedIdentifiers'
must contain a list of identifiers used to submit and handle tasks
when 'UIBackgroundModes' has a value of 'processing'.
```

### Cause

When `UIBackgroundModes` in `Info.plist` contains `processing`, `BGTaskSchedulerPermittedIdentifiers` must also be present. This combination typically arises when using the `workmanager` package.

### Solution

Check the task names passed to `registerPeriodicTask` or `registerOneOffTask` in the code, then add them to `Info.plist`.

```xml
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>your_task_name_here</string>
</array>
<key>UIBackgroundModes</key>
<array>
    <string>fetch</string>
    <string>processing</string>
</array>
```

Verify task names in Dart code:

```bash
grep -r "registerPeriodicTask\|registerOneOffTask" lib/ --include="*.dart"
```

---

## 6. Two-Stage Build Instead of flutter build ipa

`flutter build ipa` handles the entire build including codesigning in one step. It is prone to failure with entitlements issues or when no Xcode account is logged in.

Splitting into two stages is more reliable.

```bash
# Stage 1: Build app without codesigning
flutter build ios --release --no-codesign

# Stage 2: Archive directly with App Store Connect API Key
xcodebuild archive \
  -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -archivePath build/ios/archive/Runner.xcarchive \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID \
  CODE_SIGN_STYLE=Automatic \
  DEVELOPMENT_TEAM=YOUR_TEAM_ID

# Stage 3: IPA export
xcodebuild -exportArchive \
  -archivePath build/ios/archive/Runner.xcarchive \
  -exportPath build/ios/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_KEYID.p8 \
  -authenticationKeyID YOUR_KEY_ID \
  -authenticationKeyIssuerID YOUR_ISSUER_ID

# Stage 4: TestFlight upload
xcrun altool --upload-app \
  --type ios \
  --file "build/ios/ipa/app.ipa" \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

Including API Key info in `ExportOptions.plist` allows the export stage to work without an account as well.

```xml
<key>authenticationKeyID</key>
<string>YOUR_KEY_ID</string>
<key>authenticationKeyIssuerID</key>
<string>YOUR_ISSUER_ID</string>
<key>authenticationKeyPath</key>
<string>/path/to/AuthKey_KEYID.p8</string>
```

Wrapping it in a Makefile lets you finish with a single `make testflight`.

---

## Checklist

Items to verify before TestFlight deployment:

- [ ] Only used capabilities are declared in `Runner.entitlements`
- [ ] Those capabilities are activated on the App ID in Apple Developer Console
- [ ] If `UIBackgroundModes: processing` exists, `BGTaskSchedulerPermittedIdentifiers` is also present
- [ ] Google OAuth CLIENT_ID is iOS type, not Web type
- [ ] No hardcoded provisioning profiles in `project.pbxproj`
- [ ] Build number is higher than the previous upload
