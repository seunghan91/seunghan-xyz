---
title: "Flutter TestFlight Build Where API URL is Stuck on localhost"
date: 2025-07-13
draft: false
tags: ["Flutter", "TestFlight", "dart-define", "iOS", "Deployment"]
description: "If you don't add --dart-define=API_URL to flutter build ipa, TestFlight builds use localhost as the API server, causing all requests to fail. Managing this with Makefile."
cover:
  image: "/images/og/flutter-dart-define-api-url-testflight.png"
  alt: "Flutter Dart Define Api Url Testflight"
  hidden: true
---


If you upload a Flutter app to TestFlight and all API requests fail on real devices, the cause might be that `--dart-define` wasn't used to inject the API URL, so the app is sending requests to `localhost`.

---

## Symptoms

- Works fine on the simulator (since it connects to the local server)
- Login and all API calls fail on TestFlight builds (real devices)
- No corresponding requests appear in server logs -> The client isn't making requests to the server at all

---

## Cause

When using the pattern of injecting environment-specific API URLs via `--dart-define` in Flutter, omitting this argument from the build command causes the code's default value to be used.

```dart
// environment.dart
static const String apiUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: 'http://localhost:3000',  // This value is used without dart-define
);
```

During local development, you either pass `--dart-define` when running `flutter run`, or the default localhost value works fine since a local server is running.

But if you omit `--dart-define` when running `flutter build ipa`, `localhost` gets baked into the release build as-is.

---

## How to Verify

Open the `Makefile` or build script and check whether the `flutter build ipa` command includes `--dart-define`.

```makefile
# Wrong example
build-ipa:
	flutter build ipa --release \
		--export-options-plist=$(EXPORT_OPTIONS)
```

```makefile
# Correct example
build-ipa:
	flutter build ipa --release \
		--dart-define=API_URL=https://api.example.com \
		--export-options-plist=$(EXPORT_OPTIONS)
```

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

---

## Important Note

Values passed via `--dart-define` are embedded in the binary at build time. If you put sensitive values like API keys here, they can be extracted from the app binary. Keep truly secret values on the server, and only include public keys or public URLs in the client.

---

## Summary

| Situation | API URL |
|------|---------|
| `flutter run` (local) | Uses `defaultValue` without `--dart-define` |
| `flutter build ipa` | Uses `defaultValue` without `--dart-define` |
| TestFlight / App Store | Must include `--dart-define` in Makefile for production URL |

A TestFlight build is ultimately a release build, so manage `--dart-define` in your Makefile or CI script and make sure it's never omitted.
