---
title: "iOS Distribution Certificate Full Setup: Distribution Cert to APNs to Provisioning Profile to TestFlight"
date: 2025-06-18
draft: false
tags: ["iOS", "Flutter", "Xcode", "TestFlight", "Provisioning", "Deployment"]
description: "Complete iOS deployment flow from Distribution certificate to APNs certificate, Provisioning Profile creation, and xcodebuild API Key build."
cover:
  image: "/images/og/ios-codesign-testflight-full-setup.png"
  alt: "Ios Codesign Testflight Full Setup"
  hidden: true
---


This is a summary of reconfiguring code signing settings from scratch while uploading a Flutter app to TestFlight. The process uses manual signing + App Store Connect API Key instead of Xcode automatic signing.

---

## Overall Flow

```
[1] Issue Distribution Certificate
[2] Issue APNs Certificate (CSR generation required)
[3] Enable Push Notifications on App ID
[4] Create Provisioning Profile (App Store, Push included)
[5] xcodebuild archive + export (API Key authentication)
[6] Upload to TestFlight via xcrun altool
```

---

## 1. Distribution Certificate

Apple Developer -> Certificates -> + -> Select **Apple Distribution**.

If your team already has a distribution certificate, download the `.cer` file and double-click to install it in Keychain.

Verify installation:

```bash
security find-identity -v -p codesigning | grep "Apple Distribution"
# 3) B5B332... "Apple Distribution: Your Name (TEAMID)"
```

---

## 2. APNs Certificate (for Push Notifications)

Push Notifications require a separate APNs certificate. This is used by the server to send push notifications.

### CSR File Generation

Using the terminal directly is more convenient than the Keychain Access GUI.

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout ~/Desktop/push.key \
  -out ~/Desktop/push.csr \
  -subj "/emailAddress=your@email.com/CN=App Push/C=KR"
```

### Issuing from Apple Developer

Certificates -> + -> Select **Apple Push Notification service SSL (Sandbox & Production)** -> Upload `push.csr` -> Download `aps.cer`.

This `.cer` file is used for **server-side push delivery**. It is not directly used in iOS app builds.

---

## 3. Enable Push Notifications on App ID

Identifiers -> Select the App ID -> Check **Push Notifications** -> Save.

This step must be done first to create a Provisioning Profile that includes Push Notifications. If the order is reversed, the Push option appears as disabled during profile creation.

---

## 4. Create Provisioning Profile

Profiles -> + -> **Distribution -> App Store Connect** -> Select App ID -> Select Distribution Certificate -> Enter name -> Generate -> Download.

Install the downloaded `.mobileprovision` file:

```bash
cp ~/Downloads/myapp.mobileprovision \
  ~/Library/MobileDevice/Provisioning\ Profiles/myapp.mobileprovision
```

Double-clicking to install saves it with a UUID-based filename. Copying directly lets you manage it with a custom name.

Verify Push Notifications inclusion:

```bash
strings ~/Library/MobileDevice/Provisioning\ Profiles/myapp.mobileprovision \
  | grep "aps-environment"
# If <key>aps-environment</key> appears, Push is included
```

---

## 5. Archive + Export with xcodebuild

`flutter build ipa` internally calls xcodebuild, but if no Apple account is logged in to Xcode, Automatic signing selects a Wildcard profile. Wildcard does not support Push Notifications, causing the archive step to fail.

### App Store Connect API Key Method

Authenticating with an API Key without account login, combined with the `-allowProvisioningUpdates` flag, automatically finds and uses the appropriate profile.

```bash
xcodebuild archive \
  -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -archivePath /tmp/myapp.xcarchive \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_KEYID.p8 \
  -authenticationKeyID KEYID \
  -authenticationKeyIssuerID your-issuer-uuid \
  FLUTTER_BUILD_NUMBER=4 \
  FLUTTER_BUILD_NAME=1.0.0
```

ExportOptions.plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>TEAMID</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
```

Export:

```bash
xcodebuild -exportArchive \
  -archivePath /tmp/myapp.xcarchive \
  -exportPath /tmp/myapp_ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_KEYID.p8 \
  -authenticationKeyID KEYID \
  -authenticationKeyIssuerID your-issuer-uuid
```

---

## 6. TestFlight Upload

API Key method:

```bash
xcrun altool --upload-app \
  --type ios \
  -f /tmp/myapp_ipa/app.ipa \
  --apiKey KEYID \
  --apiIssuer your-issuer-uuid
```

On success:

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Check build status via App Store Connect API:

```python
import jwt, time, requests

key = open('AuthKey_KEYID.p8').read()
token = jwt.encode({
    'iss': 'your-issuer-uuid',
    'iat': int(time.time()),
    'exp': int(time.time()) + 1200,
    'aud': 'appstoreconnect-v1'
}, key, algorithm='ES256', headers={'kid': 'KEYID'})

# Look up app ID
r = requests.get(
    'https://api.appstoreconnect.apple.com/v1/apps',
    params={'filter[bundleId]': 'com.example.myapp'},
    headers={'Authorization': f'Bearer {token}'}
)
app_id = r.json()['data'][0]['id']

# List builds
r = requests.get(
    f'https://api.appstoreconnect.apple.com/v1/builds',
    params={'filter[app]': app_id, 'sort': '-uploadedDate', 'limit': 5},
    headers={'Authorization': f'Bearer {token}'}
)
for b in r.json()['data']:
    attrs = b['attributes']
    print(attrs['version'], attrs['processingState'])
```

When `processingState` is `VALID`, the build is ready for TestFlight distribution.

---

## Batch Managing Provisioning Profiles for Multiple Apps

With multiple apps comes multiple profiles. A script to check them all at once:

```bash
# Batch check for Push Notifications inclusion
for f in ~/Library/MobileDevice/Provisioning\ Profiles/*.mobileprovision; do
  name=$(basename "$f")
  has_aps=$(strings "$f" 2>/dev/null | grep -c "aps-environment")
  bundle=$(strings "$f" 2>/dev/null | grep "com\." | grep -v "apple\|dtd" | head -1 | tr -d '<>string/')
  [ "$has_aps" -gt 0 ] && mark="Y" || mark="N"
  echo "$mark $name | $bundle"
done
```

---

## Common Errors

### Wildcard Profile + Push Conflict

```
Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the Push Notifications capability.
```

Cause: `Runner.entitlements` has the `aps-environment` key but a Wildcard profile is in use.

Fix: Switch to an explicit App ID profile, or remove the key from entitlements if Push is not needed.

### Duplicate Build Number

```
ERROR ITMS-90189: "Redundant Binary Upload"
```

The build number (+N) in `pubspec.yaml`'s `version: 1.0.0+N` must be incremented before uploading.

### No Accounts Warning

```
Error (Xcode): No Accounts: Add a new account in Accounts settings.
```

Even without an Apple account in Xcode, `-allowProvisioningUpdates` + API Key method still proceeds with the build. It appears as a warning but can be ignored.

---

## Summary

| Item | Purpose |
|------|---------|
| `distribution.cer` | App code signing (needed at build time) |
| `aps.cer` | Server -> device push delivery (needed on server) |
| `.mobileprovision` | Bundle of App ID + certificate + capabilities (needed at build time) |
| API Key `.p8` | App Store Connect authentication (upload, provisioning automation) |

Xcode automatic signing is convenient, but for CI environments or special features like Push, manual profile management is more reliable.
