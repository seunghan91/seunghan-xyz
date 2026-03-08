---
title: "Flutter iOS TestFlight Upload Failure: objective_c.framework Simulator Slice Error"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "Xcode", "TestFlight", "Makefile", "Build Error"]
description: "Root cause and Makefile automation fix for IOSSIMULATOR platform tag and x86_64 slice errors when uploading a Flutter IPA to TestFlight via altool"
---

After building a Flutter app with `flutter build ipa --release`, TestFlight rejected the upload via altool.
Here's what happened, why it happened, and how I automated the fix.

---

## The Error

```
UPLOAD FAILED with 3 errors

Invalid executable. The "Runner.app/Frameworks/objective_c.framework/objective_c"
executable references an unsupported platform in the x86_64 slice.
Simulator platforms aren't permitted.

Invalid executable. The "Runner.app/Frameworks/objective_c.framework/objective_c"
executable references an unsupported platform in the arm64 slice.
Simulator platforms aren't permitted.

Unsupported Architectures. The executable for
Runner.app/Frameworks/objective_c.framework contains unsupported architectures '[x86_64]'.
```

The build succeeded and the IPA was generated just fine — the problem was at upload time.

---

## Root Cause

Flutter's Dart FFI package `objective_c` ships as a **fat binary (universal binary)** that supports both iOS device (arm64) and simulator (x86_64, arm64-simulator) to make development convenient.

Two separate issues cause the App Store rejection:

**Issue 1: x86_64 slice included**

The simulator-only x86_64 architecture ends up in the App Store submission IPA. Apple doesn't allow simulator architectures in App Store builds.

**Issue 2: arm64 slice has an IOSSIMULATOR platform tag**

Even after removing x86_64 with `lipo`, the arm64 slice itself has an `LC_BUILD_VERSION` load command with platform set to `IOSSIMULATOR`. Apple's validator catches this too.

```bash
# Check the platform tag
vtool -show-build Runner.app/Frameworks/objective_c.framework/objective_c

# Problematic output
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform IOSSIMULATOR   ← this is the problem
    minos 14.0
```

---

## Fix

### Step 1: Remove the x86_64 slice

```bash
FW="Runner.xcarchive/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"
lipo -remove x86_64 "$FW" -output "$FW"
```

### Step 2: Fix the arm64 platform tag to IOS

```bash
vtool -set-build-version ios 13.0 17.0 -replace \
  -output "$FW.tmp" "$FW"
mv "$FW.tmp" "$FW"
```

`vtool` invalidates the code signature, so you **must do this inside the xcarchive** and then re-export (which re-signs the binary).

> **Gotcha**: If you unzip the IPA, modify the binary directly, and re-zip, you'll get `Missing or invalid signature` on upload. Always modify the xcarchive, not the IPA.

### Step 3: Re-export the IPA (with re-signing)

```bash
xcodebuild -exportArchive \
  -archivePath "Runner.xcarchive" \
  -exportPath "build/ios/ipa" \
  -exportOptionsPlist "ios/ExportOptions.plist"
```

Xcode re-signs the modified binary with your distribution certificate and packages a fresh IPA.

---

## Makefile Automation

Doing this by hand every time is tedious. Here's a `fix-frameworks` Make target wired into `build-ipa`:

```makefile
ARCHIVE       = mobile/build/ios/archive/Runner.xcarchive
IPA_DIR       = mobile/build/ios/ipa
IOS_DIR       = mobile/ios
DEPLOY_TARGET = 13.0

build-ipa:
	cd mobile && flutter build ipa --release \
		--export-options-plist=ios/ExportOptions.plist
	$(MAKE) fix-frameworks
	@echo "=== IPA ready ==="

fix-frameworks:
	@ARCHIVE="$(ARCHIVE)"; \
	FW="$$ARCHIVE/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"; \
	if [ ! -f "$$FW" ]; then echo "objective_c.framework not found, skipping"; exit 0; fi; \
	echo "=== Fixing objective_c.framework ==="; \
	ARCHS=$$(lipo -archs "$$FW" 2>/dev/null); \
	if echo "$$ARCHS" | grep -q x86_64; then \
		lipo -remove x86_64 "$$FW" -output "$$FW.tmp" && mv "$$FW.tmp" "$$FW"; \
		echo "  ✓ Removed x86_64 slice"; \
	fi; \
	PLATFORM=$$(vtool -show-build "$$FW" 2>/dev/null | grep "platform " | awk '{print $$2}'); \
	if [ "$$PLATFORM" != "IOS" ]; then \
		vtool -set-build-version ios $(DEPLOY_TARGET) 17.0 -replace \
			-output "$$FW.tmp" "$$FW" 2>&1 | grep -v warning || true; \
		mv "$$FW.tmp" "$$FW"; \
		echo "  ✓ Fixed platform tag: $$PLATFORM → IOS"; \
	fi; \
	echo "=== Re-exporting IPA ==="; \
	xcodebuild -exportArchive \
		-archivePath "$$ARCHIVE" \
		-exportPath "$(IPA_DIR)" \
		-exportOptionsPlist "$(IOS_DIR)/ExportOptions.plist" 2>&1 | tail -3

testflight: bump-build build-ipa
	xcrun altool --upload-app \
		-f $(IPA_DIR)/*.ipa \
		-t ios \
		--apiKey $(ASC_API_KEY) \
		--apiIssuer $(ASC_ISSUER) 2>&1 | tail -5
```

Now `make testflight` handles everything: bump build number → build → fix frameworks → upload.

---

## Failure Attempts Summary

| Attempt | Result | Reason |
|---------|--------|--------|
| Unzip IPA → lipo → re-zip | ❌ `Missing or invalid signature` | Modified binary without re-signing |
| xcarchive → lipo only | ❌ `IOSSIMULATOR platform in arm64 slice` | Platform tag survives after arch removal |
| xcarchive → lipo + vtool + re-export | ✅ Upload succeeded | Correct order |

---

## Why This Happens

Flutter's `objective_c` package provides Dart FFI access to the Objective-C runtime. It ships as a universal binary so it works in the simulator during development. The Flutter build pipeline currently doesn't strip simulator slices from these FFI frameworks before packaging the App Store IPA.

React Native works around this by adding a `strip-frameworks.sh` script as an Xcode build phase in the Podfile. You can do something similar in Flutter, but post-processing in a Makefile target is simpler and doesn't require touching Xcode project files.
