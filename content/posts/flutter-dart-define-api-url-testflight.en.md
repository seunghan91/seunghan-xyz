---
title: "Flutter TestFlight Build Where API URL is Stuck on localhost"
date: 2025-07-13
draft: true
tags: ["Flutter", "TestFlight", "dart-define", "iOS", "Deployment"]
description: "If you don't add --dart-define=API_URL to flutter build ipa, TestFlight builds use localhost as the API server, causing all requests to fail. Managing this with Makefile."
cover:
  image: "/images/og/flutter-dart-define-api-url-testflight.png"
  alt: "Flutter Dart Define Api Url Testflight"
  hidden: true
---

If you upload a Flutter app to TestFlight and all API requests fail on real devices, the cause might be that `--dart-define` wasn't used to inject the API URL, so the app is sending requests to `localhost`.

This post covers the symptoms, root cause, debugging steps, fix, and how to prevent it from happening again with a proper CI/CD setup.

---

## Symptoms

- Works fine on the simulator (since it connects to the local server)
- Login and all API calls fail on TestFlight builds (real devices)
- No corresponding requests appear in server logs — the client isn't making requests to the server at all
- Capturing traffic with Charles Proxy or Proxyman shows requests going to `http://localhost:3000`
- Error messages are typically `SocketException: Connection refused` or `Connection timed out`

When behavior differs between the simulator and a real device, environment differences should be the first thing you investigate. Values determined at build time — like API URLs — are particularly hard to spot from runtime logs alone.

---

## Root Cause

When using the pattern of injecting environment-specific API URLs via `--dart-define` in Flutter, omitting this argument from the build command causes the code's default value to be used.

```dart
// environment.dart
static const String apiUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://localhost:3000',  // This value is used without dart-define
);
```

During local development, you either pass `--dart-define` when running `flutter run`, or the default localhost value works fine since a local server is running.

But if you omit `--dart-define` when running `flutter build ipa`, `localhost` gets baked into the release binary as-is.

### Why does it work on the simulator?

There are two reasons the problem stays hidden during local development:

1. You're explicitly passing `--dart-define=API_URL=http://localhost:3000` to the `flutter run` command, or
2. The `defaultValue` is `http://localhost:3000` and the simulator can reach the Mac's localhost, so requests actually succeed

Neither case surfaces the problem during development. Then when you run `flutter build ipa` without `--dart-define`, the release binary has `localhost:3000` hardcoded inside it. Real devices have no access to your development machine, so every request fails.

### How dart-define works under the hood

`--dart-define` hooks into Dart's `const` compilation system. The build tool passes values to the dart2native (or dart2js) compiler using `-D` flags, and the compiler replaces `String.fromEnvironment` calls with the corresponding string literals. The resulting binary contains the actual string, not a `String.fromEnvironment` call.

This means there is zero runtime overhead, and environment values declared as `const` can be used in switch statements or if/else branches, enabling dead code elimination (tree-shaking). The trade-off is that you must supply the values at build time — there is no way to inject them later.

---

## Debugging Steps

### 1. Check your Makefile or build script

Start by verifying whether the `flutter build ipa` command includes `--dart-define`.

```makefile
# Wrong — missing --dart-define
build-ipa:
	flutter build ipa --release \
		--export-options-plist=$(EXPORT_OPTIONS)
```

```makefile
# Correct
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--export-options-plist=$(EXPORT_OPTIONS)
```

### 2. Extract strings from the built binary

If you already have an IPA, you can inspect the binary directly.

```bash
# Unzip the IPA
unzip app.ipa -d app_extracted

# Search for localhost in the binary
strings app_extracted/Payload/Runner.app/Runner | grep localhost

# Or search for any URL pattern
strings app_extracted/Payload/Runner.app/Runner | grep -E "https?://"
```

If `localhost` shows up, `--dart-define` was missing from the build command.

### 3. Capture live traffic with a proxy

Set up Charles Proxy or Proxyman and run the TestFlight app. You can watch in real time which URLs the app is requesting. Requests to `localhost` will immediately return `Connection refused`.

### 4. Add a startup log

If you're still not sure, add a temporary log at app startup.

```dart
void main() {
  // For debugging only — remove before shipping
  debugPrint('API_URL: ${Environment.apiUrl}');
  runApp(const MyApp());
}
```

You can read real device logs from Xcode's Devices and Simulators window while the TestFlight build is running, which shows exactly what value was compiled in.

---

## Fix

Add `--dart-define=API_URL=` to the build command.

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--export-options-plist=$(EXPORT_OPTIONS)

testflight: build-ipa
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)
```

Making `testflight` depend on `build-ipa` means `make testflight` handles the entire flow from build to upload in one step.

---

## Using Multiple dart-define Values

If you have multiple environment variables, repeat `--dart-define` for each one.

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--dart-define=GOOGLE_MAPS_KEY=AIzaSy... \
		--dart-define=ENVIRONMENT=production \
		--export-options-plist=$(EXPORT_OPTIONS)
```

When the list grows long, it becomes harder to read. You can split it into a separate file instead.

### Using dart-define-from-file (Flutter 3.7+)

Flutter 3.7 introduced the `--dart-define-from-file` option, which lets you manage environment variables in a JSON file.

```json
// config/production.json
{
  "API_URL": "https://api.example.com",
  "GOOGLE_MAPS_KEY": "AIzaSy...",
  "ENVIRONMENT": "production"
}
```

```makefile
build-ipa:
	flutter build ipa --release \
		--dart-define-from-file=config/production.json \
		--export-options-plist=$(EXPORT_OPTIONS)
```

This keeps the Makefile clean when you have many variables. Just be careful not to commit sensitive values like API secrets to the JSON file if it's tracked by git.

---

## Managing Multiple Environments (staging, production)

In practice, most projects run at least development, staging, and production environments.

```makefile
PROD_API_URL    = https://api.example.com
STAGING_API_URL = https://staging-api.example.com

build-ipa-prod:
	flutter build ipa --release \
		--dart-define=API_URL=$(PROD_API_URL) \
		--dart-define=ENVIRONMENT=production \
		--export-options-plist=ios/ExportOptions.plist

build-ipa-staging:
	flutter build ipa --release \
		--dart-define=API_URL=$(STAGING_API_URL) \
		--dart-define=ENVIRONMENT=staging \
		--export-options-plist=ios/ExportOptions.plist

testflight-prod: build-ipa-prod
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)

testflight-staging: build-ipa-staging
	xcrun altool --upload-app \
		--type ios \
		--file "build/ios/ipa/app.ipa" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER)
```

With this setup, `make testflight-staging` uploads a staging build and `make testflight-prod` uploads a production build.

---

## Security Considerations

Values passed via `--dart-define` are embedded in the binary at build time. If you put sensitive values like API secrets here, they can be extracted from the app binary using tools like `strings` or a binary disassembler.

Keep truly secret values on the server side. Only include values that are safe to expose in the client binary.

| Safe to include | Avoid including |
|-----------------|-----------------|
| API server URL | Database passwords |
| Google Maps public key | Server secret keys |
| Environment flag (production/staging) | JWT signing keys |
| Firebase project ID | Payment secret keys |

---

## Preventing Recurrence: CI/CD Setup

Once you fix the Makefile, the problem goes away locally. But when a team grows or CI/CD is added later, it is easy to miss `--dart-define` again in a new pipeline configuration.

### GitHub Actions example

```yaml
# .github/workflows/testflight.yml
name: Deploy to TestFlight

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Flutter
        uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.x'

      - name: Build IPA
        run: |
          flutter build ipa --release \
            --dart-define=API_URL=${{ secrets.PROD_API_URL }} \
            --dart-define=ENVIRONMENT=production \
            --export-options-plist=ios/ExportOptions.plist

      - name: Upload to TestFlight
        run: |
          xcrun altool --upload-app \
            --type ios \
            --file "build/ios/ipa/*.ipa" \
            --apiKey ${{ secrets.ASC_KEY_ID }} \
            --apiIssuer ${{ secrets.ASC_ISSUER_ID }}
```

Store `PROD_API_URL`, `ASC_KEY_ID`, and `ASC_ISSUER_ID` in GitHub Secrets. The pipeline injects the correct values automatically at build time, so the problem cannot reoccur from a forgotten flag.

---

## Summary

| Situation | API URL |
|-----------|---------|
| `flutter run` (local) | Uses `defaultValue` without `--dart-define` |
| `flutter build ipa` | Uses `defaultValue` without `--dart-define` |
| TestFlight / App Store | Must include `--dart-define` in Makefile for production URL |

A TestFlight build is ultimately a release build. Manage `--dart-define` in your Makefile or CI script and make sure it is never omitted.

---

## Key Takeaways

- `String.fromEnvironment` is resolved at **compile time**, not runtime. Without `--dart-define` in the build command, `defaultValue` is used on every device, no exceptions.
- The **simulator works, real device fails** pattern is a strong signal to check environment configuration first.
- Use the `strings` command to inspect a built binary directly — it is the fastest way to confirm which URL was compiled in.
- Flutter 3.7+ supports `--dart-define-from-file` for injecting multiple variables from a JSON file, which keeps the Makefile readable as the number of variables grows.
- Values passed via `--dart-define` are embedded in the binary and can be extracted. Only include URLs and public keys — keep secret credentials server-side.
- Make the `testflight` Makefile target depend on `build-ipa`, and enforce `--dart-define` inside `build-ipa`. This makes it structurally impossible to upload a build without the correct URL.
- In CI/CD (GitHub Actions and similar), inject `--dart-define` values from secrets. This keeps credentials out of source code while ensuring every automated build uses the right configuration.
