---
title: "Flutter App TestFlight First Upload — Common Pitfalls"
date: 2026-03-09
draft: true
tags: ["Flutter", "iOS", "TestFlight", "AppStoreConnect", "Xcode"]
description: "A collection of pitfalls encountered when uploading a Flutter app to TestFlight for the first time: wrong DEVELOPMENT_TEAM, ASC REST API limitations, export compliance warnings, and build number conflicts."
---

Uploading a Flutter app to TestFlight for the first time involves more subtle configuration than most developers expect. When working entirely from the CLI — without the Xcode GUI — or when managing multiple Apple developer accounts simultaneously, small misconfigurations can block the entire pipeline. This post walks through every issue I encountered in order, including root causes, debugging steps, and prevention strategies.

---

## 1. Wrong DEVELOPMENT_TEAM

### Problem

When working across multiple Apple developer accounts, `DEVELOPMENT_TEAM` in `project.pbxproj` can silently end up set to the wrong team ID. This happens especially when you start a new project by copying an existing `ios/` directory, or when Xcode opens the project under a different account and auto-updates the signing settings.

The archive step completes without errors, but upload fails with a signing error:

```
error: exportArchive: No signing certificate "iOS Distribution" found
```

Or during the upload stage:

```
The bundle identifier "com.example.app" is not registered for the selected team.
```

### Root Cause

`project.pbxproj` contains `DEVELOPMENT_TEAM` in multiple places — one per build configuration (Debug and Release), sometimes more depending on targets. Xcode updates these independently, so mixed team IDs across configurations are easy to accumulate without noticing.

### Fix

```bash
# Check current setting
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj

# Bulk replace
sed -i '' 's/DEVELOPMENT_TEAM = OLD_TEAM_ID/DEVELOPMENT_TEAM = NEW_TEAM_ID/g' \
  ios/Runner.xcodeproj/project.pbxproj

# Verify the result
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj
```

After replacing, run `flutter clean && flutter build ipa` to rebuild from scratch. If you see any lines with an empty value (`DEVELOPMENT_TEAM = ""`), replace those as well — they can cause Xcode to fall back to an unexpected signing identity.

### Prevention

If you version-control the `ios/` directory (which you should for Flutter projects), make it a habit to inspect `DEVELOPMENT_TEAM` values before committing `project.pbxproj`. In CI pipelines, add an explicit `sed` replacement step at the start of the build script so the correct team ID is always applied regardless of what was committed.

---

## 2. App Store Connect REST API Cannot Create Apps

### Problem

Attempting to automate app creation via the ASC REST API returns **403 FORBIDDEN**, even with an Admin-role API key:

```json
{
  "status": "403",
  "title": "You do not have access to this resource",
  "detail": "You do not have access to the resource"
}
```

### Root Cause

The `apps` resource in the ASC REST API only supports GET (list/detail) and PATCH (update). POST — creating a new app record — is not part of the API specification at all. Apple's own documentation states: "You cannot create an app using the API."

This is intentional. Creating an app involves agreeing to developer program terms, registering a bundle identifier, configuring content rights, and making legal commitments that Apple requires to go through the web portal with an authenticated human session.

### Fix

**New app creation must be done through the ASC web portal — there is no API workaround.**

1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. My Apps → click the **+** button → New App
3. Enter the bundle ID, app name, primary language, SKU, and user access settings
4. Once the app record exists, all subsequent metadata updates, build associations, and review submissions can be automated via the REST API

The bundle ID must be registered in advance at [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list), or you can create it inline during the new app flow on the portal.

### Prevention

Document the "create app on ASC web portal" step explicitly in your app release checklist. It is easy to assume API automation covers everything — noting this exception up front prevents wasted debugging time.

---

## 3. ExportOptions.plist

### Problem

`flutter build ipa` calls `xcodebuild -exportArchive` internally. Without a correct export options file, the build either fails at the IPA packaging step or produces an IPA for the wrong distribution method (for example, `development` instead of `app-store`).

### Root Cause

`xcodebuild -exportArchive` requires an `-exportOptionsPlist` parameter that specifies the distribution method, team ID, code signing style, and other packaging preferences. Flutter looks for this file at `ios/ExportOptions.plist` and passes it automatically when it exists.

### Fix

Create `ios/ExportOptions.plist` with the following content:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

Key explanations:

| Key | Description |
|-----|-------------|
| `method` | `app-store` for distribution, `development` for local testing, `ad-hoc` for direct device install |
| `teamID` | Your 10-character Apple Developer team ID |
| `uploadBitcode` | Bitcode is deprecated since Xcode 14. Set to `false` |
| `uploadSymbols` | Set to `true` to enable symbolicated crash reports in ASC |
| `signingStyle` | `automatic` lets Xcode manage provisioning profiles; `manual` requires explicit profile names |

> **Important**: Adding `iCloudContainerEnvironment` to apps that do not use iCloud will cause the following upload error:
>
> ```
> The value for key 'iCloudContainerEnvironment' in your ExportOptions.plist is not valid.
> ```
>
> Only include that key if your app actively uses iCloud containers.

### Prevention

Commit `ios/ExportOptions.plist` to version control. Since this file is per-app and per-team, include verifying its `teamID` value as part of your pre-release checklist.

---

## 4. Export Compliance Warning

### Problem

After uploading to TestFlight — or during App Store review — Apple presents an encryption compliance prompt, or you receive the following warning email after the altool upload finishes processing:

```
ITMS-90725: SDK Encryption Usage — Your app uses encryption, but does not have the
required export compliance documentation.
```

This forces a manual compliance confirmation step every time you submit a new build.

### Root Cause

Under U.S. Export Administration Regulations (EAR), apps that use encryption technology are subject to export controls. Apple enforces this by requiring developers to declare whether their app uses non-exempt encryption. HTTPS/TLS — used by virtually every app — technically counts as encryption under these rules.

When `ITSAppUsesNonExemptEncryption` is absent from `Info.plist`, Apple treats compliance as unresolved and triggers the confirmation flow on every build submission.

### Fix

Add the following key to `ios/Runner/Info.plist`:

```xml
<!-- ios/Runner/Info.plist -->
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

Setting this to `false` declares that the app uses only exempt encryption (standard HTTPS/TLS provided by the OS, no custom cryptographic implementations). This is the correct value for the vast majority of consumer apps.

If your app implements its own encryption algorithms, uses a VPN, or includes a custom secure communication protocol, set this to `true` and submit an Encryption Registration Number (ERN) document through the portal.

### Prevention

Add `ITSAppUsesNonExemptEncryption` to `Info.plist` when the project is first created. Discovering this during TestFlight validation means an extra rebuild-and-reupload cycle that is entirely avoidable.

---

## 5. Uploading with xcrun altool

### Background

There are two main CLI tools for uploading to App Store Connect:

- **`xcrun altool`**: The older but still fully functional option. Supports both Apple ID credentials and API key authentication.
- **`xcrun notarytool`**: The newer tool, but designed for macOS app notarization — not applicable to iOS IPAs.

API key authentication is preferred for CI/CD because it does not require two-factor authentication.

### Generating an ASC API Key

1. App Store Connect → Users and Access → Keys tab
2. Click **+** to generate a new key (Role: Admin or App Manager)
3. Download the `.p8` file — this is available **only once**. Store it securely.
4. Note the Key ID (10-character string) and Issuer ID (UUID)

### Upload Command

```bash
# Build the IPA
flutter build ipa --release --build-number=1 --build-name=1.0.0

# Upload to App Store Connect
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

The `.p8` file must be located at `~/.appstoreconnect/private_keys/AuthKey_YOUR_KEY_ID.p8`. If stored elsewhere, pass the full path with `--apiKeyPath` instead of `--apiKey`.

Successful output:

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Transferred 27MB in 1.3 seconds
```

### Processing Delay After Upload

A successful upload does not immediately mean the build is available in TestFlight. App Store Connect processes the binary in the background — checking entitlements, encryption compliance, SDK usage, and more. This typically takes **5 to 15 minutes**. You will receive an email notification when processing completes (or if it fails).

Do not attempt to re-upload the same build number during this window, as the in-flight upload is already registered on Apple's servers.

---

## 6. Build Number Conflict

### Problem

Reusing a build number that was previously uploaded — even if that upload was interrupted or the build was later deleted — results in a 409 conflict error:

```
Redundant Binary Upload. You've already uploaded a build
with build number '2' for version number '1.0.0'.
```

### Root Cause

App Store Connect uses the `(version number, build number)` pair as a unique key for each binary. Once a build number is registered — even from an interrupted upload or a build that never completed processing — it cannot be reused for the same version. This is by design to maintain an immutable audit trail of every binary that was ever submitted.

The most common scenario: an upload fails halfway due to a network error, you assume nothing was registered, and you retry with the same build number. The retry fails with 409.

### Fix

Increment the build number and rebuild:

```bash
flutter build ipa --release --build-number=3 --build-name=1.0.0
```

To check which build numbers are already registered for a given app, either inspect the TestFlight tab in the ASC portal, or query the REST API:

```bash
# List recent builds via ASC REST API (requires jq)
curl -s -H "Authorization: Bearer $ASC_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=APP_ID&sort=-uploadedDate&limit=5" \
  | jq '.data[].attributes | {version, buildAudienceType, uploadedDate}'
```

### Prevention

Automate build numbers using a timestamp format to eliminate conflicts entirely:

```bash
BUILD_NUMBER=$(date +%Y%m%d%H%M)
flutter build ipa --release --build-number=$BUILD_NUMBER --build-name=1.0.0
```

The format `YYYYMMDDHHMM` generates a 12-digit number that is always unique and chronologically sortable, making it easy to identify when each build was produced.

---

## Summary

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| Signing error | Wrong `DEVELOPMENT_TEAM` in pbxproj | `sed` bulk replace, then clean build |
| 403 on app creation | REST API does not support POST for apps | Create the app manually on ASC web portal |
| IPA packaging failure | Missing `ExportOptions.plist` | Create `ios/ExportOptions.plist` with correct `method` and `teamID` |
| Compliance warning | Missing `ITSAppUsesNonExemptEncryption` | Add key with value `false` to `Info.plist` |
| Build number conflict | Previous upload already registered the number | Increment `--build-number` and rebuild |

---

## Key Takeaways

- **`DEVELOPMENT_TEAM` appears in multiple places inside `project.pbxproj`.** Always use `grep` to see every occurrence, then `sed` to replace all of them at once. Verify the result before rebuilding.
- **App creation via the ASC REST API is not possible.** The API covers app management, not app registration. New apps must be created through the web portal — document this step explicitly in your release checklist.
- **Only include `iCloudContainerEnvironment` in `ExportOptions.plist` if your app actually uses iCloud.** One unnecessary key in this file will fail the entire upload.
- **Set `ITSAppUsesNonExemptEncryption = false` in `Info.plist` at project creation time.** Finding this issue at upload time adds an unnecessary rebuild-and-reupload cycle.
- **Automate build numbers with timestamps.** Manually managing build numbers leads to collisions, especially when uploads are interrupted. A `YYYYMMDDHHMM` format is always unique and self-documenting.
- **A successful upload confirmation is not the same as TestFlight availability.** Allow 5–15 minutes for Apple's backend processing. Monitor the notification email rather than repeatedly checking the portal.
- **Interrupted uploads still consume the build number.** Even if `xcrun altool` exits with an error after partially transmitting, ASC may have registered the build number. Always increment before retrying.
