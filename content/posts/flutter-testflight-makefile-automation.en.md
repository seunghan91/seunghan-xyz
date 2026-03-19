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


The process of uploading a Flutter iOS app to TestFlight has many steps. `flutter build ipa`, Xcode archive, altool upload... Bundling them in a Makefile lets you do it all with a single `make testflight`.

---

## Final Makefile

```makefile
.PHONY: build-ipa testflight clean

EXPORT_OPTIONS  = ios/ExportOptions.plist
API_KEY         = YOUR_API_KEY_ID
API_ISSUER      = YOUR_ISSUER_ID
IPA_DIR         = build/ios/ipa
IPA_FILE        = $(IPA_DIR)/Talkk.ipa  # <- Must match the app's Display Name

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

---

## ExportOptions.plist Configuration

`flutter build ipa` internally creates an IPA after Xcode archiving. This process requires a file specifying the signing method, team ID, App Store Connect API key, etc.

```xml
<!-- ios/ExportOptions.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
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

The App Store Connect API key is issued at [App Store Connect -> Users and Access -> Keys](https://appstoreconnect.apple.com/access/integrations/api). Place the API key `.p8` file in `~/.appstoreconnect/private_keys/` and altool will find it automatically.

---

## Common Trap: IPA Filename

When first setting up this Makefile, it is easy to set the filename as `app_name.ipa` or `Runner.ipa`. But the actual IPA filename generated follows the **app's Display Name**.

```bash
# Check actual filename after build
ls build/ios/ipa/
# DistributionSummary.plist
# ExportOptions.plist
# Packaging.log
# Talkk.ipa  <- Based on Display Name
```

The `CFBundleDisplayName` in `Info.plist` or Xcode's Display Name setting becomes the filename. If the Makefile's `IPA_FILE` variable does not match the actual filename, you get:

```
ERROR: File does not exist at path: build/ios/ipa/app.ipa
```

If you change the app name, the Makefile must be updated as well.

---

## Build Number Management

TestFlight requires the build number to increase within the same version to accept a new build. This is managed in the Flutter project's `pubspec.yaml`.

```yaml
# pubspec.yaml
version: 1.0.1+3
#        ^     ^
#     version  build number
```

When running `flutter build ipa`, the version/build number is displayed in the build output.

```
[✓] App Settings Validation
    * Version Number: 1.0.1
    * Build Number: 3
```

The build number must be incremented for each TestFlight deployment. To automate with a script:

```bash
# Auto-increment build number in pubspec.yaml
CURRENT=$(grep "^version:" pubspec.yaml | sed 's/.*+//')
NEXT=$((CURRENT + 1))
sed -i '' "s/+$CURRENT$/+$NEXT/" pubspec.yaml
```

---

## Full Deployment Flow

```
Increment pubspec.yaml build number
        |
flutter clean && flutter pub get
        |
make testflight
   |-- flutter build ipa --release --export-options-plist=...
   |       |
   |   Xcode archive (~1 min 30 sec)
   |       |
   |   IPA generation (~1 min 50 sec)
   +-- xcrun altool --upload-app ...
           |
       UPLOAD SUCCEEDED
           |
App Store Connect processing (5-10 min)
           |
Distributed to TestFlight testers
```

Once set up, subsequent deployments are just: increment build number and run `make testflight`.

---

## When a Clean Build Is Needed

In the following situations, you must run `flutter clean` before rebuilding:

- Replacing `google-services.json` (Android Firebase config change)
- Replacing `GoogleService-Info.plist` (iOS Firebase config change)
- Changing package versions in `pubspec.yaml`
- Modifying the iOS `Podfile`

If you change Firebase config files and build without `flutter clean`, the old config may persist.

```bash
flutter clean
flutter pub get
cd ios && pod install && cd ..
make testflight
```

Including pod install makes it bulletproof.
