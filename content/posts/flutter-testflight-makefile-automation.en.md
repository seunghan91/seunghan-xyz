---
title: "Flutter TestFlight Upload Automation - One-Line with Makefile"
date: 2025-08-20
draft: true
tags: ["Flutter", "TestFlight", "iOS", "Makefile", "Automation", "Deployment"]
description: "How to handle everything from flutter build ipa to xcrun altool upload in a single Makefile line, and the common IPA filename trap."
cover:
  image: "/images/og/flutter-testflight-makefile-automation.png"
  alt: "Flutter Testflight Makefile Automation"
  hidden: true
---

Uploading a Flutter iOS app to TestFlight involves a surprising number of manual steps: `flutter build ipa`, Xcode archive, altool upload — and each step has its own failure modes. Repeat this process a few times and mistakes creep in. Wrapping everything in a Makefile reduces it to a single `make testflight`. This post covers the full Makefile setup used in production projects, the common traps, build number management, and when a clean build is actually necessary.

---

## Why Makefile

Tools like Fastlane and GitHub Actions exist for a reason, but for local development they introduce overhead — Ruby dependencies, lane configuration, credential stores. A Makefile lives in the project root, has zero dependencies, and runs immediately after cloning on any machine that has Xcode installed.

For solo development or prototype-stage projects, that simplicity matters. If the project grows into a team workflow requiring CI/CD, migrating to Fastlane or GitHub Actions is straightforward. Until then, `make testflight` gets the job done.

---

## Prerequisites: App Store Connect API Key

The altool password-based authentication method is deprecated as of 2023. API key authentication is now the standard approach.

1. Go to [App Store Connect → Users and Access → Integrations → App Store Connect API](https://appstoreconnect.apple.com/access/integrations/api)
2. Generate a new key (role: App Manager or higher)
3. Download the `.p8` file — **it can only be downloaded once**, so store it safely
4. Note the Key ID and Issuer ID

Place the `.p8` file at `~/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8`. altool automatically searches this directory, so you do not need to hardcode the absolute path in `ExportOptions.plist`.

---

## Final Makefile

```makefile
.PHONY: build-ipa testflight clean

EXPORT_OPTIONS  = ios/ExportOptions.plist
API_KEY         = YOUR_API_KEY_ID
API_ISSUER      = YOUR_ISSUER_ID
IPA_DIR         = build/ios/ipa
IPA_FILE        = $(IPA_DIR)/Talkk.ipa  # <- Must match the app's Display Name exactly

build-ipa:
	flutter build ipa --release --export-options-plist=$(EXPORT_OPTIONS)

testflight: build-ipa
	@echo "Uploading to TestFlight..."
	xcrun altool --upload-app \
		--type ios \
		--file "$(IPA_FILE)" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER) \
		--verbose
	@echo "TestFlight upload complete!"

clean:
	flutter clean && flutter pub get
```

The `testflight` target depends on `build-ipa`, so running `make testflight` executes build then upload in sequence. The `--verbose` flag prints upload progress in real time. Without it, a large IPA upload will appear to hang with no output — always include it.

---

## ExportOptions.plist Configuration

`flutter build ipa` internally runs Xcode archive and then exports the IPA. This process requires a plist file specifying the signing method, team ID, and App Store Connect API credentials. If this file is missing or contains wrong values, the build fails mid-way through the Xcode archive phase.

```xml
<!-- ios/ExportOptions.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>stripSwiftSymbols</key>
    <true/>
    <key>uploadSymbols</key>
    <true/>
    <key>authenticationKeyID</key>
    <string>YOUR_API_KEY_ID</string>
    <key>authenticationKeyIssuerID</key>
    <string>YOUR_ISSUER_ID</string>
    <key>authenticationKeyPath</key>
    <string>/Users/yourname/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8</string>
</dict>
</plist>
```

Setting `signingStyle` to `automatic` lets Xcode manage provisioning profiles automatically. Manual signing requires specifying a bundle ID to profile UUID mapping under the `provisioningProfiles` key. For solo development, automatic is far less maintenance.

Setting `uploadSymbols` to `true` uploads dSYM files alongside the IPA. This is what allows Crashlytics and App Store Connect to symbolicate crash stack traces — without it, you see memory addresses instead of readable function names.

One specific pitfall: **do not include the `iCloudContainerEnvironment` key in apps that do not use iCloud**. It will cause the upload to fail with a cryptic error. This key is only required when iCloud Drive or CloudKit entitlements are configured.

---

## Common Trap: IPA Filename

When first setting up the Makefile, the natural instinct is to name the file `Runner.ipa` or `app_name.ipa`. Both are wrong. The IPA filename generated by `flutter build ipa` is derived from the app's **Display Name**, not the Xcode target name.

```bash
# Check the actual filename after build
ls build/ios/ipa/
# DistributionSummary.plist
# ExportOptions.plist
# Packaging.log
# Talkk.ipa  <- Generated from Display Name, not "Runner"
```

The `CFBundleDisplayName` in `Info.plist`, or the Display Name field in Xcode's target settings, becomes the filename. If the app name contains spaces, the IPA filename will too — `My App.ipa`. Spaces in file paths are handled by quoting the `$(IPA_FILE)` variable, which the Makefile above already does.

If `IPA_FILE` does not match the actual generated filename, the upload step fails with:

```
ERROR: File does not exist at path: build/ios/ipa/app.ipa
```

The build has already succeeded at that point — it is only the upload that fails. This happens again after renaming the app if the Makefile is not updated.

For a more resilient setup, discover the IPA dynamically instead of hardcoding the name:

```makefile
IPA_FILE = $(shell ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1)
```

The risk here is that leftover IPA files from a previous build may be picked up instead of the new one. A safer approach is to clear the output directory before each build:

```makefile
build-ipa:
	rm -rf $(IPA_DIR)
	flutter build ipa --release --export-options-plist=$(EXPORT_OPTIONS)
```

This guarantees there is only ever one IPA in the directory.

---

## Build Number Management

TestFlight requires the build number to increase within the same version to accept a new build. Uploading the same build number again produces:

```
ERROR ITMS-90189: "Redundant Binary Upload.
You've already uploaded a build with build number '3' for version number '1.0.1'."
```

Flutter manages version and build number together in `pubspec.yaml`:

```yaml
# pubspec.yaml
version: 1.0.1+3
#        ^     ^
#     version  build number
```

The build output confirms what numbers were used:

```
[✓] App Settings Validation
    * Version Number: 1.0.1
    * Build Number: 3
```

To automate the increment with a shell one-liner:

```bash
# Auto-increment build number in pubspec.yaml
CURRENT=$(grep "^version:" pubspec.yaml | sed 's/.*+//')
NEXT=$((CURRENT + 1))
sed -i '' "s/+$CURRENT$/+$NEXT/" pubspec.yaml
```

Integrated into Makefile:

```makefile
bump:
	@CURRENT=$$(grep "^version:" pubspec.yaml | sed 's/.*+//'); \
	NEXT=$$((CURRENT + 1)); \
	sed -i '' "s/+$$CURRENT$$/+$$NEXT/" pubspec.yaml; \
	echo "Build number: $$CURRENT -> $$NEXT"

testflight: bump build-ipa
	...
```

One subtlety: if `bump` is a dependency of `testflight`, the build number increments even when the build fails. The number is wasted and the gap in the sequence appears in App Store Connect's build list. A cleaner approach is to run `make bump` manually before `make testflight`, or to trigger the bump only after a confirmed successful upload.

---

## Full Deployment Flow

```
Increment pubspec.yaml build number
        |
flutter clean && flutter pub get  (optional, only when needed)
        |
make testflight
   |-- flutter build ipa --release --export-options-plist=...
   |       |
   |   Xcode archive (~1 min 30 sec)
   |       |
   |   IPA export (~1 min 50 sec)
   +-- xcrun altool --upload-app ...
           |
       UPLOAD SUCCEEDED
           |
App Store Connect processing (5-10 min)
           |
Distributed to TestFlight testers
```

Once set up, each subsequent release is: increment build number, run `make testflight`. Total elapsed time is roughly 3 minutes for the build, 1-2 minutes for the upload, and 5-10 minutes for App Store Connect to finish processing.

It is normal for a build to not appear in TestFlight immediately after the upload completes. The build will show as "Processing" in App Store Connect until it passes automated checks, then testers receive a notification.

---

## When a Clean Build Is Needed

Running `flutter clean` before every build adds 2-3 minutes to each cycle. It is only necessary in specific situations:

- Replacing `google-services.json` (Android Firebase configuration change)
- Replacing `GoogleService-Info.plist` (iOS Firebase configuration change)
- Changing package versions in `pubspec.yaml`
- Modifying the iOS `Podfile`
- Upgrading Xcode or the Flutter SDK

When Firebase config files are replaced without a clean build, the old configuration can remain embedded in the output. The app will connect to the wrong Firebase project and the symptom — wrong notifications, wrong Analytics data — appears only at runtime, not during the build. This is one of the more disorienting failure modes because the build and upload succeed without errors.

The safe sequence after any of the above changes:

```bash
flutter clean
flutter pub get
cd ios && pod install && cd ..
make testflight
```

`pod install` is required after adding a new iOS package or upgrading an existing one. Skipping it causes CocoaPods dependency mismatch errors during the Xcode archive phase, which can look like mysterious signing or framework errors before you realize the Pods are stale.

---

## Common Errors and Fixes

**`No signing certificate "iOS Distribution" found`**

Automatic signing is configured but no distribution certificate exists in the Keychain. Open Xcode, go to Settings → Accounts, select the Apple ID, and download the certificates. If the certificate has expired, a new one needs to be created through the developer portal.

**`Unable to process request - PLA Update available`**

A new agreement is pending in App Store Connect. Log into [App Store Connect](https://appstoreconnect.apple.com) directly and accept the updated agreement before retrying.

**`altool: command not found`**

Xcode Command Line Tools are not installed. Run `xcode-select --install` and wait for the installation to complete.

**Build shows "Missing Compliance" in TestFlight after upload**

Export compliance information is absent. Add `ITSAppUsesNonExemptEncryption` to `Info.plist`:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

For apps that do not implement custom encryption (most apps using standard HTTPS), `false` is the correct value. Setting this prevents the manual compliance question from appearing after each upload.

---

## Key Takeaways

- The `IPA_FILE` variable must exactly match the `CFBundleDisplayName`-based filename. It will not be `Runner.ipa`.
- Place the `.p8` API key at `~/.appstoreconnect/private_keys/` so altool finds it automatically without hardcoded paths.
- Set `uploadSymbols: true` in `ExportOptions.plist` so crash reports are properly symbolicated in both Crashlytics and App Store Connect.
- Do not add `iCloudContainerEnvironment` to apps without iCloud entitlements — it silently breaks the upload.
- After replacing Firebase config files, changing package versions, or modifying the Podfile, always run `flutter clean` followed by `pod install` before building.
- Build number auto-increment is convenient but should be triggered after a confirmed successful upload, not as a pre-build step, to avoid wasting build numbers on failed builds.
