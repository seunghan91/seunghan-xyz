---
title: "Flutter BottomSheet Overlapping Navigation Bar: Switching to showDialog"
date: 2026-03-09
draft: false
tags: ["Flutter", "UI", "BottomSheet", "Dialog", "share_plus", "SQLite", "Debugging"]
description: "Solving the issue of showModalBottomSheet covering the bottom navigation bar by switching to a centered showDialog, while also fixing TextButton color readability and a SQLite backup PlatformException."
---

Using `showModalBottomSheet` for form input screens feels natural. But when your app has a bottom navigation bar, the sheet slides up and covers the navigation — it works functionally, but looks cluttered.

Three issues were fixed in one go:

1. Bottom sheet → centered modal conversion
2. `TextButton` cancel button rendering in yellow (unreadable)
3. `PlatformException` when sharing a SQLite file with `share_plus`

---

## Problem 1: BottomSheet Covers the Navigation Bar

### Symptom

An input form built with `showModalBottomSheet` overlaps the bottom navigation bar when it slides up. Even with `isScrollControlled: true`, the sheet extends over the navigation area.

### Root Cause

`showModalBottomSheet` renders as an overlay above the `Scaffold`, and the Z-axis layer conflicts with `bottomNavigationBar`. You can work around it with `SafeArea` or `padding`, but the UX remains awkward at a fundamental level.

### Fix: showDialog + Dialog Widget

For form input, a centered modal feels more natural. `Dialog` also handles keyboard insets automatically.

**Before (BottomSheet)**
```dart
await showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  backgroundColor: Colors.transparent,
  builder: (context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: StatefulBuilder(
        builder: (context, setModalState) {
          return Container(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(28),
              ),
            ),
            child: Form(/* ... */),
          );
        },
      ),
    );
  },
);
```

**After (Dialog)**
```dart
await showDialog<void>(
  context: context,
  builder: (dialogContext) {
    return StatefulBuilder(
      builder: (dialogContext, setModalState) {
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 24,
            vertical: 40,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(28),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
            child: SingleChildScrollView(
              child: Form(/* ... */),
            ),
          ),
        );
      },
    );
  },
);
```

### Migration Checklist

- **Remove handle bar**: Delete the drag indicator `Container(width: 44, height: 4, ...)` at the top of the sheet
- **Update borderRadius**: `BorderRadius.vertical(top:)` → `BorderRadius.circular(28)` (all four corners)
- **Remove keyboard padding**: `EdgeInsets.only(bottom: viewInsets.bottom)` is unnecessary — `Dialog` handles it automatically
- **Rename context variable**: `sheetContext` → `dialogContext` for clarity
- **Add cancel button**: Sheets can be swiped away, but Dialogs need an explicit cancel button
- **Fix showDatePicker context**: Any nested `showDatePicker` must use `dialogContext` to render on the correct layer

### For List Pickers That Need Height

For list pickers previously using `FractionallySizedBox(heightFactor: 0.74)`, replace with `ConstrainedBox`:

```dart
Dialog(
  child: ConstrainedBox(
    constraints: BoxConstraints(
      maxHeight: MediaQuery.of(dialogContext).size.height * 0.72,
    ),
    child: MyListPickerWidget(/* ... */),
  ),
)
```

Also clean up the decoration inside `MyListPickerWidget`:

```dart
// Before
return Container(
  decoration: BoxDecoration(
    borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    color: colorScheme.surface,
  ),
  child: SafeArea(top: false, child: Column(...)),
);

// After
return Padding(
  padding: const EdgeInsets.all(20),
  child: Column(...),
);
```

The `SafeArea(top: false, ...)` and `Container` decoration are now handled by the `Dialog` itself, so remove them. Watch out — removing these changes the closing parenthesis count.

---

## Problem 2: Cancel Button Text Renders in Yellow

### Symptom

The cancel `TextButton` inside `AlertDialog` or a custom `Dialog` renders in the app's theme primary color (yellow/amber). Yellow text on a white dialog background is nearly invisible.

### Root Cause

`TextButton`'s default `foregroundColor` follows `Theme.of(context).colorScheme.primary`. When the app's seed color is yellow or amber, cancel buttons inherit the same color.

### Fix

Explicitly set `onSurfaceVariant` on cancel buttons only. This color is typically a mid-tone gray, readable against any background.

```dart
TextButton(
  style: TextButton.styleFrom(
    foregroundColor: Theme.of(context).colorScheme.onSurfaceVariant,
  ),
  onPressed: () => Navigator.of(context).pop(false),
  child: const Text('Cancel'),
),
```

Primary action buttons (`FilledButton`) stay as-is. Toning down only the cancel button also aligns with Material 3 guidelines.

---

## Problem 3: PlatformException When Sharing SQLite Backup File

### Symptom

Sharing a SQLite `.db` file via `share_plus` throws a `PlatformException` on iOS.

```dart
// Original code
Future<void> exportBackup() async {
  final dbPath = p.join(await getDatabasesPath(), 'app.db');
  final tempDir = await getTemporaryDirectory();
  final backupPath = p.join(tempDir.path, 'app_backup.db');

  await File(dbPath).copy(backupPath);

  await SharePlus.instance.share(
    ShareParams(
      files: [XFile(backupPath, mimeType: 'application/octet-stream')],
      subject: 'App Data Backup',
    ),
  );
}
```

### Root Cause

Even without WAL mode, copying a SQLite file while the DB connection is open can result in a file where in-progress transactions or cached data isn't fully flushed. iOS can throw a platform-level validation error when passing such a file to the share sheet.

### Fix

Close the DB connection before copying. Calling `Database.close()` in `sqflite` flushes the cache to disk. With Riverpod, add a `closeAndReset()` method to `StorageService` and call it before exporting.

```dart
// StorageService
Future<void> closeAndReset() async {
  await _database?.close();
  _database = null;  // auto-reconnects on next access
}
```

```dart
// Export backup call site
Future<void> _exportBackup(BuildContext context, WidgetRef ref) async {
  try {
    // Close DB first to flush WAL/cache
    await ref.read(storageServiceProvider).closeAndReset();
    await ref.read(backupServiceProvider).exportBackup();
  } catch (e) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Export failed: $e')),
    );
  }
}
```

Setting `_database = null` after closing means the next DB access automatically reconnects. No need to restart the app or invalidate providers.

---

## Summary

| Problem | Cause | Fix |
|---------|-------|-----|
| BottomSheet covers navigation bar | Z-axis layer conflict | Replace with `showDialog` + `Dialog` |
| Cancel button text invisible | `TextButton` defaults to theme primary color | Explicitly set `onSurfaceVariant` |
| Backup share PlatformException | Copying file with DB connection open | Call `closeAndReset()` before copying |

None of these are bugs in Flutter or SQLite — they're natural solutions that emerge from understanding how the platform and framework actually behave.
