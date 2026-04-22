---
title: "Flutter iOS TestFlight Upload Failure: objective_c.framework Simulator Slice Error"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "Xcode", "TestFlight", "Makefile", "Build Error"]
categories: ["iOS", "Flutter"]
description: "Root cause and Makefile automation fix for IOSSIMULATOR platform tag and x86_64 slice errors when uploading a Flutter IPA to TestFlight via altool"
---

After building a Flutter app with `flutter build ipa --release`, TestFlight rejected the upload via altool.
Here's what happened, why it happened, and how I automated the fix with a reusable Makefile target.

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

The build succeeded and the IPA was generated without any issues — the rejection happened at upload time, not at build time. This distinction matters because it means the problem isn't in your Xcode settings or your Flutter project configuration per se; it lives inside a third-party framework binary that Flutter embeds silently.

---

## Root Cause

Flutter's Dart FFI package `objective_c` ships as a **fat binary (universal binary)** that supports both iOS device (arm64) and simulator (x86_64, arm64-simulator) to make development convenient.

The problem is that Apple's App Store validation pipeline rejects any binary that contains simulator code or simulator-tagged load commands. Two separate issues trigger three validation errors:

**Issue 1: x86_64 slice included**

The simulator-only x86_64 architecture ends up in the App Store submission IPA. Apple does not allow simulator architectures in App Store builds. This is the most visible error and the one most developers try to fix first — but fixing only this is not enough.

**Issue 2: arm64 slice has an IOSSIMULATOR platform tag**

Even after stripping the x86_64 slice with `lipo`, the remaining arm64 slice carries an `LC_BUILD_VERSION` Mach-O load command with the platform field set to `IOSSIMULATOR`. Apple's validator inspects this load command independently and rejects the binary a second time.

```bash
# Check the platform tag
vtool -show-build Runner.app/Frameworks/objective_c.framework/objective_c

# Problematic output
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform IOSSIMULATOR   <- this is the problem
    minos 14.0
    sdk 17.0
```

The `LC_BUILD_VERSION` load command is embedded at compile time. When the `objective_c` package is compiled with simulator support enabled, the resulting binary records `IOSSIMULATOR` as its target platform. Stripping the x86_64 slice removes one architecture but does not touch the load command metadata on the arm64 slice. Both issues must be resolved before Apple's validator will accept the IPA.

---

## Understanding the Tools: lipo vs vtool

Before walking through the fix, it helps to understand what each tool does.

**`lipo`** — the multi-architecture binary tool. It creates, inspects, and modifies fat binaries. A fat binary is a single file that contains multiple architecture slices concatenated together. `lipo -archs` lists which slices are present; `lipo -remove` strips one out.

**`vtool`** — the Mach-O load command editor. It reads and rewrites the metadata headers inside a Mach-O binary. The `LC_BUILD_VERSION` load command records which platform (iOS, macOS, IOSSIMULATOR, etc.) and which minimum OS version the binary was built for. `vtool -set-build-version` rewrites this in-place.

**Why vtool invalidates code signatures**: Code signing in iOS works by computing a cryptographic hash over the binary's contents, including its Mach-O headers. When `vtool` rewrites a load command, it changes bytes in the header, which breaks the existing signature hash. That's why the fix must happen before `xcodebuild -exportArchive` re-signs the binary with your distribution certificate.

---

## The Fix: Three Steps in the Right Order

### Step 1: Remove the x86_64 slice

Work inside the xcarchive, not the IPA. The xcarchive contains the unpackaged app bundle before signing, which is what you need.

```bash
FW="Runner.xcarchive/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"
lipo -remove x86_64 "$FW" -output "$FW.tmp" && mv "$FW.tmp" "$FW"
```

Verify the result:

```bash
lipo -archs "$FW"
# Should output: arm64
```

### Step 2: Rewrite the arm64 platform tag to IOS

```bash
vtool -set-build-version ios 13.0 17.0 -replace \
  -output "$FW.tmp" "$FW"
mv "$FW.tmp" "$FW"
```

The arguments to `-set-build-version` are: `platform minos sdk`. Use `ios` (not `IOSSIMULATOR`), your app's deployment target for `minos`, and the SDK version for `sdk`. The `-replace` flag tells vtool to overwrite the existing `LC_BUILD_VERSION` rather than adding a second one.

Verify the result:

```bash
vtool -show-build "$FW"
# Should show: platform IOS
```

`vtool` invalidates the code signature, so you **must do this inside the xcarchive** and then re-export (which re-signs the binary with your distribution certificate).

> **Gotcha**: If you unzip the IPA, modify the binary directly, and re-zip, you'll get `Missing or invalid signature` on upload. Always modify the xcarchive, not the IPA. The IPA is a signed artifact — the xcarchive is the intermediate workspace where modifications are safe.

### Step 3: Re-export the IPA (with re-signing)

```bash
xcodebuild -exportArchive \
  -archivePath "Runner.xcarchive" \
  -exportPath "build/ios/ipa" \
  -exportOptionsPlist "ios/ExportOptions.plist"
```

`xcodebuild -exportArchive` reads the modified xcarchive, runs the full signing pipeline against your distribution certificate and provisioning profile, and produces a fresh IPA. The resulting binary will have a valid signature that covers the corrected load commands.

---

## Makefile Automation

Doing this manually every release is error-prone. Here's a `fix-frameworks` Make target wired into `build-ipa`. The script is defensive: it checks whether the framework exists before proceeding, and skips each step if it's already in the correct state (useful if a future Flutter version fixes this upstream).

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
		echo "  Removed x86_64 slice"; \
	fi; \
	PLATFORM=$$(vtool -show-build "$$FW" 2>/dev/null | grep "platform " | awk '{print $$2}'); \
	if [ "$$PLATFORM" != "IOS" ]; then \
		vtool -set-build-version ios $(DEPLOY_TARGET) 17.0 -replace \
			-output "$$FW.tmp" "$$FW" 2>&1 | grep -v warning || true; \
		mv "$$FW.tmp" "$$FW"; \
		echo "  Fixed platform tag: $$PLATFORM -> IOS"; \
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

Now `make testflight` handles everything: bump build number → build → fix frameworks → upload to TestFlight.

The `fix-frameworks` target is also idempotent: if you run it on a build where the framework is already correct (or absent), it exits cleanly without side effects. This makes it safe to include unconditionally in `build-ipa` even if a future version of the `objective_c` package resolves the issue.

---

## Failure Attempts Summary

| Attempt | Result | Reason |
|---------|--------|--------|
| Unzip IPA → lipo → re-zip | `Missing or invalid signature` | Modified binary without re-signing |
| xcarchive → lipo only | `IOSSIMULATOR platform in arm64 slice` | Platform tag survives after arch removal |
| xcarchive → lipo + vtool + re-export | Upload succeeded | Correct order: modify, then re-sign |

The first attempt is the most intuitive but wrong. The second attempt addresses the right location but misses the second error. Only the third attempt resolves both issues in the right sequence.

---

## Why This Happens

Flutter's `objective_c` package provides Dart FFI access to the Objective-C runtime. It ships as a universal binary so it works in the simulator during development. The Flutter build pipeline currently does not strip simulator slices from these FFI frameworks before packaging the App Store IPA.

This is a known gap in Flutter's iOS release toolchain. The `flutter build ipa` command handles many things — archiving, basic validation, and initial export — but it does not post-process embedded frameworks to remove simulator artifacts. The assumption seems to be that `xcodebuild` stripping handles this, but Dart FFI frameworks built outside the Xcode dependency graph are not covered by that process.

React Native addresses a similar problem by adding a `strip-frameworks.sh` script as an Xcode build phase in the Podfile. The script iterates over all embedded frameworks and strips non-device architectures before the archive is created. You could adopt the same pattern in a Flutter project by adding a custom build phase to the Xcode project, but that requires editing `project.pbxproj` directly or maintaining a post-install hook — both fragile. Post-processing in a Makefile target after archiving is simpler and keeps all release logic in one place.

If you have multiple Dart FFI packages in your project (for example, packages that wrap C or Objective-C libraries), run `find Runner.xcarchive -name "*.framework" -exec lipo -archs {}/$(basename {}) \; 2>/dev/null` to check whether any other frameworks carry simulator slices. The `fix-frameworks` target above targets only `objective_c.framework` by name, so you would need to extend it if other frameworks show the same issue.

---

## Key Takeaways

- `flutter build ipa` does not strip simulator slices from Dart FFI frameworks. The resulting IPA will be rejected by TestFlight's altool validator.
- Two separate issues must be fixed: the x86_64 architecture slice (via `lipo -remove`) and the `IOSSIMULATOR` platform tag on the arm64 slice (via `vtool -set-build-version`).
- Both fixes must be applied to the xcarchive, not the IPA. The IPA is a signed artifact; modifying it post-signing breaks the signature. The xcarchive is the pre-signing workspace.
- After modifying the binary, run `xcodebuild -exportArchive` to re-sign with your distribution certificate and produce a fresh, valid IPA.
- Automating this in a Makefile `fix-frameworks` target keeps the fix reproducible and invisible — `make testflight` just works.
- Check for other Dart FFI frameworks in your project if you use packages that wrap native C or Objective-C code. They may carry the same simulator slice issue.
