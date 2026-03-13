---
title: "Flutter iOS Crash: workmanager BGTaskScheduler NSException Not Caught by Dart try-catch"
date: 2025-08-06
draft: false
tags: ["Flutter", "iOS", "workmanager", "BGTaskScheduler", "crash"]
description: "When using workmanager on iOS, BGTaskScheduler throws ObjC NSExceptions that can't be caught by Dart try-catch, causing app crashes. Root cause analysis and solution."
cover:
  image: "/images/og/flutter-ios-workmanager-crash-bgtaskscheduler.png"
  alt: "Flutter Ios Workmanager Crash Bgtaskscheduler"
  hidden: true
---


There are cases where a Flutter app uploaded to TestFlight crashes immediately on launch. If the crash isn't caught despite wrapping it in try-catch, it's likely the `workmanager` package's iOS BGTaskScheduler issue.

---

## Symptoms

- App crashes immediately on launch (splash screen doesn't even appear)
- Same behavior on both simulator and real device
- App dies despite being wrapped in `try-catch`
- Works fine on local debug builds but crashes only on release builds

---

## Crash Log Analysis

macOS crash reports are saved as `.ips` files in `~/Library/Logs/DiagnosticReports/`.

```bash
ls ~/Library/Logs/DiagnosticReports/ | grep Runner
# Runner-2026-02-25-190740.ips
```

Parsing the `.ips` file reveals the stack trace.

```python
import json
with open('Runner-2026-02-25-190740.ips') as f:
    content = f.read()
lines = content.split('\n', 1)
data = json.loads(lines[1])

exc = data.get('exception', {})
print('Type:', exc.get('type'))   # EXC_BAD_ACCESS
print('Signal:', exc.get('signal'))  # SIGSEGV
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

---

## Cause

The `workmanager` package uses `BGTaskScheduler` on iOS to register background tasks. `BGTaskScheduler` throws an **Objective-C NSException** when the task ID isn't in `Info.plist`'s `BGTaskSchedulerPermittedIdentifiers` or other conditions aren't met.

The problem is that Dart's `try-catch` **cannot catch ObjC NSExceptions**.

```dart
// This code doesn't work
try {
  await Workmanager().initialize(callbackDispatcher);
  await Workmanager().registerPeriodicTask(...);
} catch (e) {
  // NSException is not caught here
  // App just crashes
}
```

Swift's `do-catch` also can't directly catch ObjC `NSException`. ObjC exceptions lead to undefined behavior in ARC environments, causing immediate app termination.

---

## Solutions

### Option 1: Disable workmanager on iOS

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

### Option 2: Remove workmanager Entirely

If periodic background sync isn't essential on iOS, removing workmanager altogether is the cleanest approach.

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

---

## Important Notes

Even if you register task IDs in `BGTaskSchedulerPermittedIdentifiers`, BGTaskScheduler may throw exceptions on the simulator or certain iOS versions. If crashes occur despite correct `Info.plist` settings, suspect the ObjC exception issue.

The current status of workmanager iOS support can be checked at the [official repository issues](https://github.com/fluttercommunity/flutter_workmanager).
