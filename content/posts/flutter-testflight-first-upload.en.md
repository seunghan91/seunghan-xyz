---
title: "Flutter App TestFlight First Upload — Common Pitfalls"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "TestFlight", "AppStoreConnect", "Xcode"]
description: "A collection of pitfalls encountered when uploading a Flutter app to TestFlight for the first time: wrong DEVELOPMENT_TEAM, ASC REST API limitations, export compliance warnings, and build number conflicts."
---

Uploading a Flutter app to TestFlight for the first time involves several small configuration details that can block the process. Here's a record of the issues I ran into.

---

## 1. Wrong DEVELOPMENT_TEAM

When working across multiple Apple developer accounts, `DEVELOPMENT_TEAM` in `project.pbxproj` can end up set to the wrong team ID. The archive succeeds but upload fails with a signing error.

```bash
# Check current setting
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj

# Bulk replace
sed -i '' 's/DEVELOPMENT_TEAM = OLD_TEAM_ID/DEVELOPMENT_TEAM = NEW_TEAM_ID/g' \
  ios/Runner.xcodeproj/project.pbxproj
```

---

## 2. App Store Connect REST API Cannot Create Apps

Attempting to create an app via the ASC REST API returns **403 FORBIDDEN**:

```json
{
  "status": "403",
  "title": "You do not have access to this resource"
}
```

The `apps` resource only supports GET and PATCH. **New app creation must be done through the ASC web portal.** There is no workaround via the API.

---

## 3. ExportOptions.plist

`flutter build ipa` calls `xcodebuild -exportArchive` under the hood, which requires an export options file for App Store distribution.

```xml
<!-- ios/ExportOptions.plist -->
<?xml version="1.0" encoding="UTF-8"?>
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

> **Note**: Adding `iCloudContainerEnvironment` to apps that don't use iCloud will cause an upload error.

---

## 4. Export Compliance Warning

Without the following key in `Info.plist`, TestFlight or App Store review will ask about encryption compliance:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

For apps that don't use custom encryption, setting this to `false` silences the prompt entirely.

---

## 5. Uploading with xcrun altool

Using an ASC API key allows CLI uploads without logging into App Store Connect manually.

```bash
# Build
flutter build ipa --release --build-number=1 --build-name=1.0.0

# Upload
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

Success output:
```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## 6. Build Number Conflict

Reusing a build number that was already uploaded results in a 409 error:

```
Redundant Binary Upload. You've already uploaded a build
with build number '2' for version number '1.0.0'.
```

This happens even if the previous upload was interrupted mid-way — ASC registers the attempt. Increment the build number and rebuild.

```bash
flutter build ipa --release --build-number=3 --build-name=1.0.0
```

---

## Summary

| Problem | Cause | Fix |
|---------|-------|-----|
| Signing error | Wrong `DEVELOPMENT_TEAM` | `sed` replace in pbxproj |
| 403 on app creation | REST API doesn't allow it | Use ASC web portal |
| Compliance warning | Missing `ITSAppUsesNonExemptEncryption` | Add `false` to `Info.plist` |
| Build number conflict | Previous upload registered | Increment `--build-number` |
