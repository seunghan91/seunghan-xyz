---
title: "flutter build ipa Failure Cause and TestFlight Deployment with --no-codesign + API Key"
date: 2025-11-04
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Makefile", "Code Signing", "Deployment Automation"]
description: "Why flutter build ipa fails without a Development certificate, and how to deploy to TestFlight without Xcode account login using --no-codesign + App Store Connect API Key."
cover:
  image: "/images/og/flutter-ipa-no-codesign-api-key-testflight.png"
  alt: "Flutter Ipa No Codesign Api Key Testflight"
  hidden: true
---

When managing Flutter iOS apps across multiple Apple accounts, you may find that `make testflight` works perfectly in one project but the same Makefile fails in another. Here is a case I ran into today.

---

## Symptoms

```
Error (Xcode): No signing certificate "iOS Development" found:
   No "iOS Development" signing certificate matching team ID "XXXXXXXX"
   with a private key was found.
```

Running `flutter build ipa` fails with this error. The Distribution certificate is in the Keychain, but it says the Development certificate is missing.

---

## Cause: What Happens Inside `flutter build ipa`

`flutter build ipa` internally runs the following sequence:

```
flutter build ipa
  └─ flutter build ios --release        ← Problem occurs here
       └─ xcodebuild -configuration Release
            └─ Xcode automatic signing pipeline
                 ├─ Check Xcode account login
                 ├─ Check iOS Development certificate  ← Fails if missing
                 └─ Create provisioning profile
```

You might think only a Distribution certificate is needed since it is for TestFlight upload, but Xcode automatic signing **also requires a Development certificate** at build time. This is to support simulator and real device debug builds.

**Summary:**
- `flutter build ipa` → Requires Xcode account login + Development cert
- `flutter build ios --no-codesign` → Skips the signing process entirely

---

## Why It Worked in Another Project

Comparing two projects:

| | Project A (Success) | Project B (Failure) |
|---|---|---|
| Apple Team | Team 1 | Team 2 |
| Xcode Login | Logged in | Not logged in |
| Development cert | Present | Missing |
| Distribution cert | Present | Present |
| Makefile approach | `--no-codesign` + xcodebuild | `flutter build ipa` |

Project A was already using the `--no-codesign` approach, so it succeeded. Project B was using `flutter build ipa`, so it failed.

If only a Distribution certificate is in the Keychain and you are not logged into Xcode with that team, `flutter build ipa` will always fail.

---

## Solution: `--no-codesign` + xcodebuild API Key

### Overall Flow

```
flutter build ios --release --no-codesign    ← Build without signing
      ↓
xcodebuild archive                            ← Auto-sign + archive with API Key
      ↓
xcodebuild -exportArchive                     ← Export IPA
      ↓
xcrun altool --upload-app                     ← Upload to TestFlight
```

Building with `--no-codesign` generates only the iOS app binary without signing. Then the `xcodebuild archive` step uses the App Store Connect API Key to automatically handle signing and provisioning. No Xcode account login is needed at all.

---

## Full Makefile

```makefile
# App Store Connect API Key
ASC_API_KEY_PATH ?= /path/to/AuthKey_XXXXXXXX.p8
ASC_API_KEY_ID ?= XXXXXXXX
ASC_API_ISSUER_ID ?= xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

FLUTTER := flutter
SCHEME := Runner
ARCHIVE_PATH := build/ios/xcarchive/Runner.xcarchive
IPA_DIR := build/ios/ipa

.PHONY: clean build-testflight testflight

clean:
	@rm -rf build/

build-testflight: clean
	@echo "▶ Flutter build (no-codesign)..."
	@$(FLUTTER) build ios --release --no-codesign

	@echo "▶ xcodebuild archive (API Key signing)..."
	@xcodebuild \
		-workspace ios/Runner.xcworkspace \
		-scheme $(SCHEME) \
		-configuration Release \
		-destination "generic/platform=iOS" \
		-derivedDataPath build/derived_data \
		-archivePath $(ARCHIVE_PATH) \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		DEVELOPMENT_TEAM=YOUR_TEAM_ID \
		archive \
		-allowProvisioningUpdates

	@echo "▶ Export IPA..."
	@xcodebuild -exportArchive \
		-archivePath $(ARCHIVE_PATH) \
		-exportPath $(IPA_DIR) \
		-exportOptionsPlist ios/ExportOptions.plist \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		-allowProvisioningUpdates

upload:
	@IPA_FILE=$$(ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1); \
	if [ -z "$$IPA_FILE" ]; then echo "No IPA found, run make build-testflight first"; exit 1; fi; \
	xcrun altool --upload-app \
		--type ios \
		--file "$$IPA_FILE" \
		--apiKey $(ASC_API_KEY_ID) \
		--apiIssuer $(ASC_API_ISSUER_ID)

testflight: build-testflight upload
	@echo "TestFlight upload complete"
```

### ExportOptions.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>destination</key>
    <string>upload</string>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
</dict>
</plist>
```

Setting `manageAppVersionAndBuildNumber: false` lets you control the build number directly from the Makefile.

---

## Applying the Same Pattern to Native Swift (Xcode) Projects

Pure Xcode projects (Swift/SwiftUI) without Flutter use the same approach. Just remove the `flutter build ios --no-codesign` step.

```makefile
# For Swift/Xcode projects

ASC_API_KEY_PATH ?= /path/to/AuthKey_XXXXXXXX.p8
ASC_API_KEY_ID ?= XXXXXXXX
ASC_API_ISSUER_ID ?= xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

XCPROJECT := MyApp/MyApp.xcodeproj
SCHEME := MyApp
ARCHIVE_PATH := build/MyApp.xcarchive
IPA_DIR := build/ipa

.PHONY: testflight increment-build archive export upload

increment-build:
	@cd $(dir $(XCPROJECT)) && agvtool next-version -all
	@echo "Build number: $$(cd $(dir $(XCPROJECT)) && agvtool what-version -terse)"

archive:
	@mkdir -p build
	@xcodebuild \
		-project $(XCPROJECT) \
		-scheme $(SCHEME) \
		-configuration Release \
		-destination "generic/platform=iOS" \
		-derivedDataPath build/derived_data \
		-archivePath $(ARCHIVE_PATH) \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		DEVELOPMENT_TEAM=YOUR_TEAM_ID \
		-allowProvisioningUpdates \
		archive

export: archive
	@xcodebuild -exportArchive \
		-archivePath $(ARCHIVE_PATH) \
		-exportPath $(IPA_DIR) \
		-exportOptionsPlist MyApp/ExportOptions.plist \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		-allowProvisioningUpdates

upload:
	@IPA_FILE=$$(ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1); \
	xcrun altool --upload-app --type ios --file "$$IPA_FILE" \
		--apiKey $(ASC_API_KEY_ID) --apiIssuer $(ASC_API_ISSUER_ID)

testflight: increment-build archive export upload
	@echo "TestFlight upload complete"
```

Use `agvtool next-version -all` to auto-increment the build number before deploying. This is more reliable than editing Info.plist directly.

---

## Issuing an App Store Connect API Key

[App Store Connect](https://appstoreconnect.apple.com) -> Users and Access -> Integrations -> App Store Connect API -> + button

- **Role**: Developer or above (App Manager recommended)
- **.p8 file**: Can only be downloaded once at issuance; if lost, you need to reissue
- **Key ID / Issuer ID**: Displayed at the top of the API Keys tab

Place the issued `.p8` file at `~/.appstoreconnect/private_keys/AuthKey_{KEY_ID}.p8` so that `xcrun altool` can find it automatically.

```bash
mkdir -p ~/.appstoreconnect/private_keys
cp AuthKey_XXXXXXXX.p8 ~/.appstoreconnect/private_keys/
```

---

## Summary

| Approach | Xcode Account Login | Development cert | Result |
|---|---|---|---|
| `flutter build ipa` | Required | Required | Fails if missing |
| `flutter build ios --no-codesign` + xcodebuild API Key | Not required | Not required | Always succeeds |

If you manage multiple Apple team accounts or work in CI/CD environments where Xcode login is difficult, the `--no-codesign` + API Key approach is far more reliable. Deployment is possible with only the Distribution certificate in the Keychain.
