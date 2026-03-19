---
title: "Flutter Singleton with Eager iOS Plugin Initialization Causes Crash"
date: 2025-08-10
draft: true
tags: ["Flutter", "iOS", "Plugin", "Singleton", "Crash", "Initialization"]
description: "Eagerly creating native plugin instances in singleton class fields causes crashes because plugin channels open before Flutter engine initialization. Solved with lazy initialization."
cover:
  image: "/images/og/flutter-singleton-plugin-eager-init-crash.png"
  alt: "Flutter Singleton Plugin Eager Init Crash"
  hidden: true
---


There is a common mistake when using the singleton pattern in Flutter apps that use iOS native plugins: eagerly creating the plugin instance as a class field.

---

## The Problematic Pattern

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  // Eagerly created as a class field
  final _iCloudSync = IcloudStorageSync();
}
```

`static final instance = CloudSyncService._()` executes the moment the class is **first referenced** in Dart. Simply having an `import` at the top of `main.dart` can trigger the static field initializer.

This point in time may be before `WidgetsFlutterBinding.ensureInitialized()`, and before the Flutter engine's plugin channel registration is complete. Creating a native plugin instance like `IcloudStorageSync()` in this state will **crash because the platform channel cannot be found**.

---

## Solution: Lazy Initialization

Declare the plugin instance as nullable and create it only when it is first used.

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  // Declared as nullable, created on first use
  IcloudStorageSync? _iCloudSync;

  Future<void> upload(String filePath, String destination) async {
    // Lazy init with ??= operator
    _iCloudSync ??= IcloudStorageSync();

    await _iCloudSync!.upload(
      containerId: 'iCloud.com.example.myapp',
      filePath: filePath,
      destinationRelativePath: destination,
    );
  }
}
```

Since `upload()` is called after `WidgetsFlutterBinding.ensureInitialized()` completes in `main()`, the plugin channels are already registered at that point.

---

## Why It Does Not Crash in Debug

Debug builds use JIT compilation with slower execution speed, creating a time gap between Flutter engine initialization and singleton creation. Release builds (AOT) execute faster, exposing the timing collision.

If crashes only occur in TestFlight builds but everything works fine on the simulator, suspect this pattern.

---

## Scope of Impact

This issue applies to **all packages that wrap iOS native plugins**, not just `icloud_storage_sync`.

- `local_auth`
- `flutter_secure_storage`
- `permission_handler`
- `sign_in_with_apple`
- Any other package that uses platform channels

If your singleton services use any of these packages, switching them all to lazy initialization is the safe approach.
