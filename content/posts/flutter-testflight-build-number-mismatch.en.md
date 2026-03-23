---
title: "Flutter TestFlight Build Number Mismatch: pubspec.yaml Says +9 but TestFlight Shows Build 11"
date: 2025-08-13
draft: true
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Build Number", "CFBundleVersion"]
description: "Why pubspec.yaml set to +9 shows as build 11 in TestFlight, and how to keep build numbers consistent going forward."
cover:
  image: "/images/og/flutter-testflight-build-number-mismatch.png"
  alt: "Flutter Testflight Build Number Mismatch"
  hidden: true
---

When uploading a Flutter iOS app to TestFlight, the build number set in `pubspec.yaml` sometimes differs from what TestFlight displays. For example, you set `version: 1.0.1+9` but TestFlight shows build 11. If you encounter this for the first time, it can be confusing. But once you understand the root cause, it is straightforward to handle. This post explains why it happens, how to debug it, and how to keep build numbers consistent going forward.

---

## Background: Flutter's iOS Build Number Structure

In a Flutter project, version information is managed through a single `version` field in `pubspec.yaml`.

```yaml
version: 1.0.1+9
```

Here, `1.0.1` is the marketing version (`CFBundleShortVersionString`) and the number after `+` is the build number (`CFBundleVersion`). When you run `flutter build ios`, the Flutter build system reads these values and automatically injects them into the Xcode project's `Info.plist`.

In iOS app distribution, the build number is the key that App Store Connect uses to identify each build. Within the same marketing version (e.g., 1.0.1), the build number must be strictly greater than any previously uploaded build. Violating this rule causes the upload to be rejected outright.

---

## Why the Build Number Differs

The heart of the issue is the `-allowProvisioningUpdates` flag and Xcode's Automatic Signing mechanism.

Flutter's build number flow, step by step:

```
pubspec.yaml version: 1.0.1+9
        |
flutter build ios --no-codesign
        |
CFBundleVersion = 9 (Runner.app)
        |
xcodebuild archive -allowProvisioningUpdates
        |
During Xcode automatic signing, queries latest build number from App Store Connect
        |
If latest build is 10 -> overwrites CFBundleVersion to 11
        |
Uploaded to TestFlight as build 11
```

When you pass the `-allowProvisioningUpdates` option to `xcodebuild`, Xcode handles automatic signing through the App Store Connect API. During this process, Xcode queries App Store Connect for the most recently uploaded build number under the current `CFBundleShortVersionString` (e.g., 1.0.1). If the current `CFBundleVersion` (9) is less than or equal to the latest uploaded build (10), Xcode **automatically overwrites `CFBundleVersion` to `latest number + 1` to prevent conflicts**.

Apple requires that within the same version string, the build number must be higher than any previously submitted build. So Xcode sets it safely to the latest number + 1 (that is, 11). This behavior is built into Xcode's automatic signing flow — it is not Apple making the change server-side.

### When Does This Problem Occur?

This mismatch tends to appear in the following situations:

- You manage `pubspec.yaml` build numbers manually and the number drifts out of sync with what App Store Connect actually has on record.
- You attempted a build multiple times with failures in between, so some intermediate build numbers were consumed in App Store Connect but never appeared locally.
- A CI/CD pipeline uses an auto-increment script that only updates `pubspec.yaml` without tracking the actual uploaded number.
- A teammate uploaded a build independently, advancing the counter in App Store Connect without updating the shared source.

---

## Internal Mechanics: Xcode Automatic Signing and the App Store Connect API

When Automatic Signing is enabled and you run `xcodebuild archive -allowProvisioningUpdates`, Xcode performs the following steps internally:

1. **Provisioning profile refresh**: Xcode connects to the Apple Developer Portal and automatically renews or creates a provisioning profile matching the team ID and bundle ID.

2. **Build number query**: Xcode queries the App Store Connect API for the most recently uploaded build number under the current `CFBundleShortVersionString`.

3. **Conflict detection and adjustment**: If the current `CFBundleVersion` (9) is less than or equal to the latest uploaded number (10), Xcode overwrites `CFBundleVersion` to `latest + 1` (11).

4. **Archive creation**: Xcode creates the `.xcarchive` with the adjusted build number.

5. **IPA export and upload**: `xcrun altool` or `xcodebuild -exportArchive` packages the IPA and uploads it to TestFlight.

Crucially, `pubspec.yaml` is never modified during this process. Only the build archive and the uploaded IPA carry the adjusted `CFBundleVersion`. This is why your local source and the TestFlight build list end up showing different numbers.

---

## How to Check the Actual Build Number

After upload, the actual build number can be verified through the following methods.

### 1. Check App Store Connect Activity

App Store Connect → Select app → TestFlight → Check the actual number in the build list.

Build processing typically takes 5 to 15 minutes. Once processing is complete, the build list shows the real build number.

### 2. Check the altool Upload Log

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Note the Delivery UUID from the upload log and find the corresponding build in the Activity tab of App Store Connect.

### 3. Query Directly via the App Store Connect API

Using the App Store Connect REST API, you can query the current latest build number from a script:

```bash
# After generating a JWT token, query the build list
curl -H "Authorization: Bearer $JWT_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=$APP_ID&sort=-version&limit=1"
```

This is useful in CI/CD pipelines to programmatically determine the latest build number before uploading.

### 4. List Builds with xcrun altool

```bash
xcrun altool --list-apps \
  --apiKey $ASC_KEY_ID \
  --apiIssuer $ASC_ISSUER_ID
```

---

## Syncing the pubspec.yaml Number

If TestFlight uploaded as build 11, `pubspec.yaml` should be updated to `+11` so the next build correctly increments to `+12`.

```yaml
# Match to actual TestFlight number after upload
version: 1.0.1+11
```

### Auto-Increment Script

If you use an auto-increment script:

```bash
#!/bin/bash
# increment-build-number.sh
PUBSPEC="$1"
VERSION_NAME=$(grep '^version:' "$PUBSPEC" | sed 's/version: *//;s/+.*//')
BUILD_NUMBER=$(grep '^version:' "$PUBSPEC" | sed 's/.*+//')
NEW_BUILD_NUMBER=$((BUILD_NUMBER + 1))
sed -i '' "s/^version: .*/version: ${VERSION_NAME}+${NEW_BUILD_NUMBER}/" "$PUBSPEC"
echo "Build: ${BUILD_NUMBER} -> ${NEW_BUILD_NUMBER}"
```

Even if the script increments +9 to +10, Xcode may overwrite it again during the signing process. The safe approach is to **check the actual TestFlight number after upload and manually sync `pubspec.yaml` to that number**.

### Automated Sync Using the App Store Connect API

A more robust approach is to query App Store Connect for the current latest build number before uploading and set the next number explicitly:

```bash
#!/bin/bash
# sync-build-number.sh
# Query App Store Connect for the latest build number and update pubspec.yaml

PUBSPEC="pubspec.yaml"
APP_ID="your_app_id"
JWT_TOKEN=$(python3 generate_jwt.py)  # Script to generate App Store Connect JWT

LATEST_BUILD=$(curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=$APP_ID&sort=-version&limit=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['attributes']['version'])")

NEXT_BUILD=$((LATEST_BUILD + 1))
VERSION_NAME=$(grep '^version:' "$PUBSPEC" | sed 's/version: *//;s/+.*//')
sed -i '' "s/^version: .*/version: ${VERSION_NAME}+${NEXT_BUILD}/" "$PUBSPEC"
echo "Set build number to $NEXT_BUILD (latest was $LATEST_BUILD)"
```

---

## Root Cause Summary and Prevention Tips

### Summary Table

| Item | Value |
|------|-----|
| pubspec.yaml | `version: 1.0.1+9` |
| CFBundleVersion after Flutter build | `9` |
| App Store Connect latest build | `10` |
| CFBundleVersion after Xcode auto-adjustment | `11` |
| TestFlight displayed build number | **11** |

It is not Apple that automatically changes the build number — it is **`xcodebuild` incrementing the number during automatic signing with the `-allowProvisioningUpdates` option to prevent conflicts**.

### Prevention Tips

**1. Always verify and sync the number after each upload.**

After every release build, check the actual build number in TestFlight and update `pubspec.yaml` to match. In a team environment, commit this update so everyone stays in sync.

**2. Sign manually without `-allowProvisioningUpdates`.**

If you manage provisioning profiles and certificates yourself, you can build without `-allowProvisioningUpdates`. Without this flag, Xcode does not query App Store Connect, so no automatic number adjustment happens. The trade-off is that you need to manage provisioning profile expiration yourself.

**3. Use App Store Connect as the single source of truth for build numbers in CI/CD.**

If you have a CI/CD pipeline, treat App Store Connect — not `pubspec.yaml` — as the authoritative source for build numbers. Before each build, query the API for the latest number, set `pubspec.yaml` to `latest + 1`, then proceed with the build.

**4. Track build numbers with git tags.**

```bash
git tag "build-11" -m "TestFlight build 11 (1.0.1)"
git push origin "build-11"
```

Linking TestFlight build numbers to git commits makes it easy to trace exactly which code went into which build and to roll back if needed.

---

## Key Takeaways

- Flutter's `pubspec.yaml` build number (`+N`) is injected as `CFBundleVersion` at `flutter build ios` time, but `xcodebuild -allowProvisioningUpdates` can overwrite it.
- The overwrite happens because Xcode queries App Store Connect for the latest uploaded build number and, if the current number is less than or equal to that value, automatically adjusts to `latest + 1`.
- This is local behavior inside Xcode's automatic signing flow, not a server-side change by Apple.
- The immediate fix is to check the actual build number in TestFlight after upload and manually sync `pubspec.yaml` to that number.
- For long-term reliability, the most stable setup is a CI/CD pipeline that treats App Store Connect as the single source of truth for build numbers, querying the API before every build.
