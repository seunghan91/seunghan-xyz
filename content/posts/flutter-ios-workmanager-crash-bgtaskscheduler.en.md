---
title: "Flutter iOS Crash: workmanager BGTaskScheduler NSException Not Caught by Dart try-catch"
date: 2025-08-06
draft: true
tags: ["Flutter", "iOS", "workmanager", "BGTaskScheduler", "crash"]
description: "When using workmanager on iOS, BGTaskScheduler throws ObjC NSExceptions that can't be caught by Dart try-catch, causing app crashes. Root cause analysis and solution."
cover:
  image: "/images/og/flutter-ios-workmanager-crash-bgtaskscheduler.png"
  alt: "Flutter Ios Workmanager Crash Bgtaskscheduler"
  hidden: true
---

There are cases where a Flutter app uploaded to TestFlight crashes immediately on launch. If the crash isn't caught despite wrapping it in try-catch, it's likely the `workmanager` package's iOS BGTaskScheduler issue.

This article walks through the crash analysis process from a real production app, covering the root cause, solutions, and how to prevent it from happening again.

---

## Symptoms

- App crashes immediately on launch (splash screen doesn't even appear)
- Same behavior on both simulator and real device
- App dies despite being wrapped in `try-catch`
- Works fine on local debug builds but crashes only on release builds
- Xcode console shows no output, or only very brief logs
- Crash may not appear in Firebase Crashlytics (crash happens before initialization completes)

The last symptom is particularly confusing. Crashlytics captures crashes after app initialization, but BGTaskScheduler exceptions occur before the app fully launches, so reports can be missing entirely.

---

## Debugging Steps

### Step 1: Run a Release Build Directly from Xcode

If the crash only happens on TestFlight, the first step is to run a release build directly from Xcode.

```bash
# Change the scheme to Release in Xcode:
# Product → Scheme → Edit Scheme → Run → Build Configuration: Release
```

You can see the NSException message directly in the Xcode console.

### Step 2: Inspect the Crash Report File

To analyze a crash without Xcode or TestFlight, look at the crash reports stored on the device. macOS crash reports are saved as `.ips` files in `~/Library/Logs/DiagnosticReports/`.

```bash
ls ~/Library/Logs/DiagnosticReports/ | grep Runner
# Runner-2026-02-25-190740.ips
```

The `.ips` file can be parsed as JSON.

```python
import json
with open('Runner-2026-02-25-190740.ips') as f:
    content = f.read()
lines = content.split('\n', 1)
data = json.loads(lines[1])

exc = data.get('exception', {})
print('Type:', exc.get('type'))    # EXC_BAD_ACCESS
print('Signal:', exc.get('signal')) # SIGSEGV
```

Actual crash stack trace:

```
-[NSAssertionHandler handleFailureInMethod:object:file:lineNumber:description:]
-[BGTaskScheduler _unsafe_submitTaskRequest:error:]
-[BGTaskScheduler submitTaskRequest:error:]
static WorkmanagerPlugin.schedulePeriodicTask(taskIdentifier:earliestBeginInSeconds:)
WorkmanagerPlugin.registerPeriodicTask(request:completion:)
...
UIApplicationMain
```

If `NSAssertionHandler` and `_unsafe_submitTaskRequest` appear at the top of the stack, BGTaskScheduler threw an NSException.

### Step 3: Set an NSException Breakpoint in Xcode

If you can reproduce the issue, use Xcode's Exception Breakpoint:

1. Open Debug Navigator (Cmd+6)
2. Click the `+` button at the bottom left
3. Select `Exception Breakpoint`
4. Set Exception to `Objective-C`, Break to `On Throw`

This lets you see the exact point where the NSException is thrown and inspect the full call stack.

---

## Root Cause

### How BGTaskScheduler Uses NSException

The `workmanager` package uses `BGTaskScheduler` on iOS to register background tasks. `BGTaskScheduler` throws an **Objective-C NSException** when any of the following conditions are not met:

1. **Task ID not in `Info.plist`**: Using an identifier not listed in `BGTaskSchedulerPermittedIdentifiers`
2. **Not running on a real device**: Attempting to register a BGProcessingTask on the simulator
3. **iOS version below 13**: BGTaskScheduler is only supported on iOS 13 and later
4. **Duplicate registration**: Attempting to register an already-registered task identifier

Condition 1 is the most common mistake — adding workmanager to `pubspec.yaml` without registering the task identifier in `Info.plist`.

### Why Dart try-catch Cannot Catch NSExceptions

```dart
// This code does not work
try {
  await Workmanager().initialize(callbackDispatcher);
  await Workmanager().registerPeriodicTask(...);
} catch (e) {
  // NSException is not caught here
  // The app just crashes
}
```

Dart's exception handling system operates entirely within the Dart VM. When Dart code calls a native method through a Flutter plugin, exceptions thrown in the native layer (Objective-C/Swift) do not cross the Dart VM boundary.

The exact sequence is:

1. Dart calls native code via `MethodChannel`
2. Native code (WorkmanagerPlugin) calls BGTaskScheduler
3. BGTaskScheduler throws an NSException
4. **The ObjC runtime unwinds the stack, causing undefined behavior in an ARC environment**
5. The process is forcefully terminated

Swift's `do-catch` cannot directly handle ObjC NSExceptions either. Swift can only catch errors that conform to the `Error` protocol. To catch an ObjC NSException, you need an Objective-C wrapper.

```objc
// Only ObjC code can catch NSException
@try {
    [BGTaskScheduler.sharedScheduler submitTaskRequest:request error:&error];
} @catch (NSException *exception) {
    // Caught here
}
```

Because the workmanager plugin does not include this kind of handling internally, the exception propagates unchecked and terminates the app.

---

## Solutions

### Option 1: Disable workmanager on iOS (Recommended)

workmanager's iOS support is officially **experimental**. Using it only on Android is the safest approach.

```dart
import 'dart:io';
import 'package:workmanager/workmanager.dart';

Future<void> initialize() async {
  // Don't run on iOS
  if (Platform.isIOS) return;

  try {
    await Workmanager().initialize(callbackDispatcher);
    await Workmanager().registerPeriodicTask(
      'my_task',
      'my_task',
      frequency: const Duration(minutes: 15),
    );
  } catch (e) {
    print('Workmanager init failed: $e');
  }
}
```

Place the `Platform.isIOS` check as early as possible — ideally inside `main()` or at the very top of your app initialization logic.

### Option 2: Remove workmanager Entirely

If periodic background sync is not essential on iOS, removing workmanager altogether is the cleanest approach.

**Remove from pubspec.yaml:**

```yaml
dependencies:
  # removed
  # workmanager: ^0.9.0
```

**Remove related entries from Info.plist:**

```xml
<!-- Remove this entire section -->
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>my_task_identifier</string>
</array>
<key>UIBackgroundModes</key>
<array>
    <string>fetch</string>
    <string>processing</string>
</array>
```

After running `flutter pub get`, make sure to run `pod install` again inside the `ios/` directory.

### Option 3: iOS Background Task Alternatives

If you need background processing on iOS, consider these alternatives to workmanager.

**`background_fetch` package**: Supports iOS BGAppRefreshTask and has more stable iOS support than workmanager.

```dart
import 'package:background_fetch/background_fetch.dart';

BackgroundFetch.configure(
  BackgroundFetchConfig(
    minimumFetchInterval: 15,
    stopOnTerminate: false,
    enableHeadless: true,
  ),
  _onBackgroundFetch,
  _onBackgroundFetchTimeout,
);
```

**`flutter_background_service` package**: Use this when you need long-running services. Note that iOS has strict time limits on background execution.

**Sync on foreground resume**: If background execution is not strictly required, syncing when the app returns to the foreground is the most iOS-compatible approach.

```dart
// Using AppLifecycleObserver
class _AppState extends State<App> with WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _syncData();
    }
  }
}
```

---

## Important Notes

Even if you register task IDs in `BGTaskSchedulerPermittedIdentifiers`, BGTaskScheduler may still throw exceptions on the simulator or on certain iOS versions. If crashes occur despite correct `Info.plist` settings, the ObjC exception issue should still be suspected.

The current status of workmanager iOS support can be checked at the [official repository issues](https://github.com/fluttercommunity/flutter_workmanager).

---

## Prevention

### Test Release Builds in CI/CD

This bug often does not reproduce on debug builds. Add a release build step to your CI pipeline.

```yaml
# GitHub Actions example
- name: Build iOS Release
  run: |
    flutter build ios --release --no-codesign
```

### Platform Guard Code Review Checklist

For team projects, establish a code review checklist that requires `Platform.isIOS` guards whenever a package with known iOS issues is used.

### Pin the workmanager Version

If you continue using workmanager, pin a verified version in `pubspec.yaml` rather than using a range constraint.

```yaml
dependencies:
  workmanager: 0.5.2  # pin exact version instead of ^0.5.2
```

---

## Key Takeaways

- **Dart try-catch cannot catch ObjC NSExceptions.** When a Flutter plugin throws an NSException in the native layer, the app terminates immediately with no chance for Dart-level recovery.
- **BGTaskScheduler uses NSException for precondition failures.** Missing Info.plist entries, simulator environments, and duplicate registrations are all common triggers.
- **workmanager's iOS support is officially experimental.** For production apps, disabling it on iOS with a `Platform.isIOS` guard is the safest strategy.
- **Crash reports can be analyzed by parsing `.ips` files directly.** Combined with Xcode Exception Breakpoints, this gives you fast, precise root cause identification.
- **Debug builds may not reproduce the crash at all.** Including release build tests in CI is strongly recommended to catch this class of bug before it reaches users.
