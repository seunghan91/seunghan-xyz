---
title: "Connecting Unimplemented Flutter UI Components + Xcode 26 Beta WidgetKit Install Bug Workaround"
date: 2025-07-16
draft: false
tags: ["Flutter", "iOS", "Xcode", "WidgetKit", "LiveActivity", "Simulator"]
description: "Connecting UI components left as onTap: () {} in a Flutter app, and working around the WidgetKit extension simulator installation bug in Xcode 26.2 beta."
cover:
  image: "/images/og/flutter-dead-ui-fix-xcode26-widget-bug.png"
  alt: "Flutter Dead Ui Fix Xcode26 Widget Bug"
  hidden: true
---


Dealt with two problems back-to-back while working on a Flutter app.
One was a UI-level issue -- connecting components that were just shells with `onTap: () {}`.
The other was a problem in Xcode 26.2 beta where the app itself wouldn't install on the simulator due to extensions.

---

## 1. Connecting Non-Functional UI Components

A common situation during Flutter development: screens are all built, but buttons have `onPressed: () {}`, cards have `onTap: () {}`, and there's no actual behavior.

### Patterns by Type

**Notification Bell Icon**

A case where the UI exists but tapping isn't even possible because there's no `GestureDetector`.

```dart
// Before — just a Container
Container(
  child: Icon(Icons.notifications_outlined),
)

// After — wrapped with GestureDetector for routing
GestureDetector(
  onTap: () => context.push('/notifications'),
  child: Container(
    child: Icon(Icons.notifications_outlined),
  ),
)
```

**"View All" Text Button**

```dart
// Before
TextButton(onPressed: () {}, child: Text('View All'))

// After
TextButton(
  onPressed: () => context.push('/list-page'),
  child: Text('View All'),
)
```

**Card Tap -> Bottom Sheet**

A pattern where tapping a card shows a bottom sheet with detail info + action buttons.

```dart
GestureDetector(
  onTap: () => _showDetailSheet(context, item),
  child: Card(...),
)

void _showDetailSheet(BuildContext context, Item item) {
  showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (_) => Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(item.title),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              context.push('/create');
            },
            child: Text('Create New'),
          ),
        ],
      ),
    ),
  );
}
```

### Notification Page Structure

The app didn't have a notification page at all, so I created one from scratch.
It's based on dummy data but structured so it can be replaced with API integration later.

```dart
class _NotificationItem {
  final String id;
  final _NotifType type;
  final String title;
  final String body;
  final String? tripId;   // Related target ID
  final DateTime time;
  bool isRead;
}
```

Swipe-to-delete with `Dismissible`, read status handling in `BlocConsumer`.

```dart
Dismissible(
  key: Key(notif.id),
  direction: DismissDirection.endToStart,
  onDismissed: (_) => _dismiss(notif.id),
  child: InkWell(
    onTap: () {
      _markRead(notif.id);
      if (notif.relatedId != null) {
        context.push('/detail/${notif.relatedId}');
      }
    },
    child: NotificationTile(notif: notif),
  ),
)
```

### Fixing Existing Code Bugs

Three existing bugs discovered during the work:

**1) Missing BlocConsumer `listener`**

```dart
// Error: Required named parameter 'listener' must be provided
BlocConsumer<SomeBloc, SomeState>(
  builder: (context, state) { ... },
  // listener is missing
)

// Fix
BlocConsumer<SomeBloc, SomeState>(
  listener: (context, state) {},
  builder: (context, state) { ... },
)
```

**2) Missing `maybeMap` orElse -> dynamic return**

```dart
// Without orElse in maybeMap, return type becomes dynamic
// If shouldShow is dynamic, ternary operator causes compile error
final shouldShow = state.maybeMap(
  loaded: (data) => data.items.length >= 10,
  // no orElse → dynamic return
);

// Fix
final shouldShow = state.maybeMap(
  loaded: (data) => data.items.length >= 10,
  orElse: () => false,  // fixed to bool
);
```

**3) Import path typo**

```dart
// Wrong path (one extra directory depth)
import '../../bloc/some_bloc.dart';

// Correct path
import '../bloc/some_bloc.dart';
```

---

## 2. Xcode 26.2 Beta WidgetKit Extension Simulator Install Bug

Running `flutter run` on the simulator succeeds at the build stage but crashes during installation.

```
Unable to install Runner.app
Invalid placeholder attributes.
Failed to create app extension placeholder for PlugIns/SomeWidgetExtension.appex
Failed to create promise.
```

This occurred regardless of whether it was an iOS 18.x or iOS 26.x simulator.

### Cause

In Xcode 26.2 beta, `xcrun simctl install` fails when creating placeholders for WidgetKit/ActivityKit extensions. "Failed to create promise" means the promise object used internally during App Extension registration in the simulator failed to be created.

This appears to be a regression from Xcode 26 being in beta, and there are no issues on real devices.

### Workaround

Since the build itself succeeds, you can just remove the extension and install directly.

```bash
# 1. Build for simulator (extensions are included in the build)
flutter build ios --simulator --debug

# 2. Remove only the problematic extension
rm -rf build/ios/iphonesimulator/Runner.app/PlugIns/YourWidgetExtension.appex

# 3. Install directly with simctl
xcrun simctl install <DEVICE_UUID> build/ios/iphonesimulator/Runner.app

# 4. Launch
xcrun simctl launch <DEVICE_UUID> com.your.bundleid
```

Wrapping it in a Makefile makes it convenient:

```makefile
SIM_DEVICE_ID = <device-uuid>
BUNDLE_ID     = com.your.app.bundleid
WIDGET_EXT    = YourWidgetExtension.appex

run-sim:
	flutter build ios --simulator --debug
	rm -rf build/ios/iphonesimulator/Runner.app/PlugIns/$(WIDGET_EXT)
	xcrun simctl install $(SIM_DEVICE_ID) build/ios/iphonesimulator/Runner.app
	xcrun simctl launch $(SIM_DEVICE_ID) $(BUNDLE_ID)
```

After that, a single `make run-sim` does everything.

### Checking Booted Simulators

```bash
xcrun simctl list devices | grep Booted
```

The target simulator must be in `Booted` state. Installing on a `Shutdown` simulator gives the error `Unable to lookup in current state: Shutdown`.

```bash
# Boot simulator manually
xcrun simctl boot <DEVICE_UUID>
open -a Simulator
```

---

## Summary

| Problem | Cause | Solution |
|------|------|------|
| No tap event | Missing `GestureDetector` | Wrap + connect `context.push()` |
| View All empty function | `onPressed: () {}` | Connect route or bottom sheet |
| BlocConsumer compile error | Missing `listener` parameter | Specify even an empty listener |
| maybeMap type error | Missing `orElse` -> dynamic | Add `orElse: () => false` |
| Simulator install failure | Xcode 26 beta bug | Remove extension then simctl install |

The Xcode 26 beta bug will be resolved naturally after the official release.
Until then, proceed with development using the `make run-sim` workaround.
