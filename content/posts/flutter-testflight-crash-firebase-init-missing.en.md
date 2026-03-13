---
title: "Flutter TestFlight Crash - Missing Firebase.initializeApp()"
date: 2025-08-16
draft: false
tags: ["Flutter", "Firebase", "iOS", "TestFlight", "Crash"]
description: "If you add firebase_core but don't call Firebase.initializeApp(), release builds crash. Why it works in debug but only crashes in TestFlight, and the fix."
cover:
  image: "/images/og/flutter-testflight-crash-firebase-init-missing.png"
  alt: "Flutter Testflight Crash Firebase Init Missing"
  hidden: true
---


Uploaded a TestFlight build and the app terminated immediately on launch. It worked fine on the simulator and in debug builds. The cause was a missing `Firebase.initializeApp()` call.

---

## Why It Works in Debug but Crashes in Release

When `firebase_core` is added, the iOS native Firebase SDK gets included in the app binary through CocoaPods. When the app runs, the iOS runtime detects `GoogleService-Info.plist` and starts internal native SDK initialization.

If `Firebase.initializeApp()` is not called from the Flutter Dart layer, **synchronization between the native SDK and the Dart bridge breaks.** In debug builds, execution is slower with more timing slack, so it may slip through. But release builds use AOT compilation with faster execution, exposing the timing difference and causing a crash.

---

## Fix

```dart
// Wrong code - running other services without Firebase initialization
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SomeService.instance.initialize();
  runApp(const MyApp());
}
```

```dart
// Correct code - Firebase must be initialized first
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  await SomeService.instance.initialize();
  runApp(const MyApp());
}
```

`firebase_options.dart` is generated with the FlutterFire CLI.

```bash
dart pub global activate flutterfire_cli
flutterfire configure
```

---

## Defensive Coding

Wrapping Firebase initialization in try-catch ensures the app at least launches even if Firebase init fails.

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } catch (e) {
    debugPrint('Firebase init failed: $e');
  }

  try {
    await SomeService.instance.initialize();
  } catch (e) {
    debugPrint('SomeService init failed: $e');
  }

  runApp(const MyApp());
}
```

Even if Firebase fails, `runApp()` is still reached, and the crash report will contain a more meaningful stack trace.

---

## Checklist

- [ ] Is `Firebase.initializeApp()` called first in `main()`?
- [ ] Is `GoogleService-Info.plist` in `ios/Runner/`?
- [ ] Does `firebase_options.dart` exist in the project?
- [ ] Is `DefaultFirebaseOptions.currentPlatform` passed as options?
