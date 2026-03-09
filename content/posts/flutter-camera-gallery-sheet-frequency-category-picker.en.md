---
title: "Flutter image_picker Camera/Gallery Bottom Sheet + Riverpod Frequency-Based Category Sorter"
date: 2026-03-09
draft: false
tags: ["Flutter", "Riverpod", "image_picker", "UX", "SharedPreferences", "DraggableScrollableSheet"]
description: "How I fixed a camera-only photo button with a bottom sheet picker, built frequency-based top-3 category shortcuts with Riverpod AsyncNotifier + SharedPreferences, and made a submit button change color based on emergency target."
---

While building a civic reporting Flutter app, I ran into three UX problems in a row:

1. The photo button only opened the gallery — no camera option
2. Categories kept growing, making the grid scroll-heavy
3. Switching to an emergency report target didn't change the submit button color

Here's how I fixed each one.

---

## Problem 1: image_picker only opens the gallery

### The issue

The photo button called `pickImage(source: ImageSource.gallery)` directly. Camera permissions were in place, but the UI never offered the option.

### Best practice check

Researching `image_picker` 1.2+ patterns, the answer was clear:

> When supporting both camera and gallery, show a **bottom sheet with two options**. Combining them into a single tap contradicts user expectations.

Key takeaways:
- Always check `mounted` after any `async` image-picker call — the widget may be disposed while the camera app is open
- Separate camera and gallery into **individual methods** for clean error handling

### Fix: Add takePhoto() to PhotoService

```dart
Future<PhotoAttachment?> takePhoto() async {
  try {
    final file = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (file == null) return null;
    final gps = await _extractGps(file);
    return PhotoAttachment(path: file.path, lat: gps.$1, lng: gps.$2);
  } catch (_) {
    return null;
  }
}
```

`imageQuality: 85` avoids unnecessarily large files for downstream processing.

### Fix: Bottom sheet with camera/gallery split

```dart
void _showPickerSheet(BuildContext context) {
  showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: CircleIcon(Icons.camera_alt_rounded, color: AppColors.info),
            title: const Text('Take a photo',
              style: TextStyle(fontWeight: FontWeight.w700)),
            onTap: () { Navigator.pop(ctx); onAddFromCamera(); },
          ),
          ListTile(
            leading: CircleIcon(Icons.photo_library_rounded, color: AppColors.primary),
            title: const Text('Choose from gallery',
              style: TextStyle(fontWeight: FontWeight.w700)),
            onTap: () { Navigator.pop(ctx); onAddFromGallery(); },
          ),
        ],
      ),
    ),
  );
}
```

A `StatelessWidget` can call `showModalBottomSheet` directly — all it needs is a `BuildContext`.

### Mounted check after async

```dart
Future<void> _addPhotoFromCamera() async {
  try {
    final photo = await ref.read(photoServiceProvider).takePhoto();
    if (photo == null) return;
    await _handlePickedPhotos([photo]);
  } catch (error) {
    if (mounted) {  // ← critical after any async gap
      messenger.showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }
}
```

Skip `mounted` and you'll get `setState called after dispose` when returning from the camera.

---

## Problem 2: Too many categories, too much scrolling

### The issue

The category list grew to 14 items. A 3-column grid puts everything at equal priority and forces users to scroll past rarely-used entries to find what they need.

### Approach: top-3 quick picks + full modal

Show the 3 most frequently used categories as large chips on the main screen. Everything else goes into a "View all ↓" modal.

The key question: how do we know which 3 are "most frequent"?
- **Hardcoded**: pick statistically common ones and leave them fixed
- **Usage tracking**: sort based on actual user selections

Hardcoded doesn't adapt to individual users, so I went with **SharedPreferences + frequency tracking**.

### Riverpod AsyncNotifier for frequency storage

```dart
const _defaultFrequencies = <String, int>{
  'dasan120:illegal-parking': 500,
  'dasan120:noise': 300,
  'dasan120:illegal-dumping': 200,
  // ...based on national complaint statistics as seed values
};

class CategoryFrequencyNotifier extends AsyncNotifier<Map<String, int>> {
  @override
  Future<Map<String, int>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    if (raw == null) return Map.from(_defaultFrequencies);
    final stored = (jsonDecode(raw) as Map<String, dynamic>)
        .map((k, v) => MapEntry(k, (v as num).toInt()));
    // merge so newly added categories get sensible defaults
    return {..._defaultFrequencies, ...stored};
  }

  Future<void> increment(String label, ReportTarget target) async {
    final key = '${target.name}:$label';
    final current = await future;
    final updated = {...current, key: (current[key] ?? 0) + 100};
    state = AsyncValue.data(updated);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, jsonEncode(updated));
  }
}
```

Each selection adds +100. Defaults are 500, so after 5 uses a category overtakes the default and rises to the top 3.

### Derived provider for top-N calculation

```dart
final topCategoriesProvider =
    Provider.family<List<ReportCategory>, ReportTarget>((ref, target) {
  final freqsAsync = ref.watch(categoryFrequencyProvider);
  final freqs = switch (freqsAsync) {
    AsyncData(:final value) => value,
    _ => _defaultFrequencies,  // show defaults while loading
  };

  return ReportCategory.forTarget(target)
      .where((c) => c.label != 'other')
      .toList()
    ..sort((a, b) {
        final ka = '${target.name}:${a.label}';
        final kb = '${target.name}:${b.label}';
        return (freqs[kb] ?? 0).compareTo(freqs[ka] ?? 0);
      });
});
```

`Provider.family` recomputes automatically when `target` changes — swipe from one report target to another and the top 3 update instantly.

**Riverpod 3.x gotcha**: `AsyncValue.valueOrNull` no longer exists. Use Dart 3 pattern matching instead:

```dart
// ❌ compile error in Riverpod 3.x
final freqs = ref.watch(categoryFrequencyProvider).valueOrNull ?? defaults;

// ✅
final freqs = switch (ref.watch(categoryFrequencyProvider)) {
  AsyncData(:final value) => value,
  _ => defaults,
};
```

### DraggableScrollableSheet for the full picker modal

```dart
DraggableScrollableSheet(
  expand: false,
  initialChildSize: 0.55,
  maxChildSize: 0.88,
  minChildSize: 0.35,
  builder: (ctx, scrollController) => Column(
    children: [
      // header ...
      Expanded(
        child: GridView.builder(
          controller: scrollController, // ← must connect this
          // ...
        ),
      ),
    ],
  ),
)
```

The `scrollController` from the builder **must** be passed to the `GridView`. Without it, dragging the sheet and scrolling the grid conflict and neither works properly.

---

## Problem 3: Emergency target change doesn't affect button color

### The issue

The app has multiple report targets — one standard, two emergency. Users can swipe between them. The target selector chips correctly turned red for emergency targets, but the main submit button always stayed green.

### Fix: Derive accentColor from emergency flag

```dart
// Inside _FloatingSubmitButton.build()

final accentColor = emergency ? AppColors.error : AppColors.primary;
final accentDark  = emergency ? const Color(0xFFDC2626) : AppColors.primaryDark;

gradient: LinearGradient(
  colors: isReady
      ? [
          accentColor.withValues(alpha: 0.92),
          accentDark.withValues(alpha: 0.92),
        ]
      : hasStartedInput
      ? [
          Colors.white.withValues(alpha: 0.72),
          accentColor.withValues(alpha: 0.18), // subtle tint before ready
        ]
      : [ /* neutral white/grey */ ],
),

BoxShadow(
  color: statusColor.withValues(alpha: isReady ? 0.32 : 0.10),
  blurRadius: isReady ? 28 : 18,
),
```

The subtle tint in `hasStartedInput` state is intentional — even before the form is complete, the button hints at urgency.

The target chips already had this logic. The submit button was the only piece that hadn't caught up, which broke the visual consistency.

---

## Summary

| Problem | Key fix |
|---------|---------|
| Camera button missing | Bottom sheet 2-option picker; `mounted` check after async |
| Category grid too long | Frequency-based top-3 chips + DraggableScrollableSheet full modal |
| Button color not contextual | `accentColor`/`accentDark` driven by `emergency` flag |

The most time-consuming part was discovering that Riverpod 3.x dropped `valueOrNull`. Most online examples and even AI suggestions still use the old API. Dart 3 pattern matching on `AsyncValue` is the correct modern approach.
