---
title: "Flutter image_picker Crash: Don't Pass limit: 1 to pickMultiImage"
date: 2026-03-08
draft: true
tags: ["Flutter", "iOS", "image_picker", "Debugging", "Dart"]
description: "Hitting 'cannot be lower 2:1' when tapping the photo button? The pickMultiImage limit parameter must be 2 or more. Here's why and how to fix it."
---

Tapped the photo button in a Flutter app and got hit with `cannot be lower 2:1`. No matching string anywhere in the codebase. Stack trace pointed vaguely into package internals.

---

## Symptom

Tapping the photo attachment button throws:

```
cannot be lower 2:1
```

No `2:1` string exists anywhere in the project code. The crash happens before the photo picker UI even appears — the app throws immediately after the button tap.

At first it seemed like an iOS permissions issue. Maybe `NSPhotoLibraryUsageDescription` was missing, or the simulator photo library had a weird state. But the permissions prompt appeared normally; the crash happened right when the picker was about to open. A permissions problem would have prevented the prompt from showing at all.

Looking more carefully at the stack trace:

```
PlatformException(invalid_arguments, cannot be lower 2:1, null, null)
    at Object.throw_ [as throw] (...)
    at image_picker_ios/...
```

It is a `PlatformException` originating inside the `image_picker_ios` package — native plugin territory, not Dart code. This clue made it clear: an API constraint violation, not a permissions or environment issue.

---

## Root Cause

This is a constraint inside `image_picker`'s `pickMultiImage(limit:)` parameter.

The problematic code:

```dart
// limit = maxCount - currentPhotoCount = 1 - 0 = 1 (when 0 photos selected)
final files = await _picker.pickMultiImage(limit: limit);
```

The screen capped photos at 1. When the user had 0 photos and tapped the button, `limit: 1` was passed straight into `pickMultiImage`.

`pickMultiImage` is a **multi-selection picker** — the `limit` must be `>= 2`. Passing `1` is semantically a single-image pick, which belongs to `pickImage`. The package enforces this and throws.

The message `cannot be lower 2:1` means: "limit cannot be lower than 2, but received 1."

### Why does this constraint exist?

Under the hood, `image_picker_ios` uses `PHPickerViewController` (introduced in iOS 14) to present the native photo picker. The `PHPickerConfiguration` object has a `selectionLimit` property: `0` means unlimited, `1` means single-selection mode.

When you call `pickMultiImage` with a `limit` parameter, the plugin sets `PHPickerConfiguration.selectionLimit` to that value. But the plugin also enforces a semantic invariant: `pickMultiImage` is for picking *multiple* images, so `limit >= 2` is required. If you want exactly one image, use `pickImage` — which internally configures the picker in single-selection mode (`selectionLimit = 1`).

This validation lives in the native Objective-C layer, so it cannot be caught at compile time in Dart. It surfaces at runtime as a `PlatformException`.

### Why is this bug easy to miss?

There are three reasons this bug tends to slip through.

**The error message is misleading.** `cannot be lower 2:1` looks like a ratio constraint — something about image dimensions or aspect ratios. A developer unfamiliar with this specific API behavior will likely spend time hunting through image processing code before suspecting the picker itself.

**The crash only happens in a specific state.** When there is already 1 photo, `remaining = 1 - 1 = 0`, which typically disables the add-photo button or takes a different code path. The crash only fires when the user taps the button with 0 photos — the very first photo addition. This makes it easy to overlook during manual testing if the tester always starts with an existing photo.

**The `limit` parameter is relatively new.** It was added in `image_picker 0.8.6` (late 2022). Developers who updated from an older version and added the `limit` parameter without reading the full changelog may have passed the computed `remaining` value without knowing about the `>= 2` constraint.

---

## Reproducing the Bug

```dart
// This will always crash when currentPhotos is empty
class PhotoService {
  final ImagePicker _picker = ImagePicker();
  List<XFile> _photos = [];
  final int maxPhotos = 1;

  Future<void> addPhoto() async {
    final remaining = maxPhotos - _photos.length; // = 1
    // When remaining == 1, pickMultiImage throws PlatformException
    final files = await _picker.pickMultiImage(limit: remaining);
    _photos.addAll(files);
  }
}
```

Run this, tap the add button with an empty photo list, and you will see the crash immediately.

---

## Debugging Process

Here is the step-by-step investigation that led to the fix.

**Step 1: Search for the error message**

Searching `cannot be lower 2:1` on Google returned sparse results — the error message is unusual enough that few people had written about it in searchable form. Switching to `image_picker limit 1 crash` and `pickMultiImage crash iOS` surfaced relevant GitHub issues.

**Step 2: Analyze the PlatformException code**

The exception code `invalid_arguments` is the key. This means the native layer received an argument it considers invalid. That narrows the investigation to any `image_picker` call where I was passing a dynamically computed value — not a hardcoded one.

**Step 3: Trace all `pickMultiImage` call sites**

There was exactly one call site in the project. The `limit` argument was `remaining = maxPhotos - currentCount`. With `maxPhotos = 1` and `currentCount = 0`, the result was `1`. Case closed.

**Step 4: Verify against the official documentation**

Checking the `image_picker` documentation confirmed the constraint:

> `limit`: The maximum number of images to pick. Must be 2 or greater.

The note is there, but it is easy to miss when you are reading API signatures rather than full documentation. The method name `pickMultiImage` itself should have been the hint — "multi" implies more than one.

---

## Fix

Branch on `limit == 1` and use `pickImage` instead.

```dart
Future<List<PhotoAttachment>> pickPhotos({int limit = 10}) async {
  final List<XFile> files;
  if (limit == 1) {
    // pickMultiImage requires limit >= 2
    final file = await _picker.pickImage(source: ImageSource.gallery);
    files = file != null ? [file] : [];
  } else {
    files = await _picker.pickMultiImage(limit: limit);
  }

  final photos = <PhotoAttachment>[];
  for (final file in files) {
    // post-processing (EXIF extraction, etc.)
    photos.add(PhotoAttachment(path: file.path));
  }
  return photos;
}
```

### Defensive extension

Handle the `limit <= 0` edge case too, for a more robust implementation.

```dart
Future<List<PhotoAttachment>> pickPhotos({int limit = 10}) async {
  // limit <= 0 means no slots available — bail out immediately
  if (limit <= 0) return [];

  final List<XFile> files;
  if (limit == 1) {
    final file = await _picker.pickImage(source: ImageSource.gallery);
    files = file != null ? [file] : [];
  } else {
    // limit >= 2, safe to call pickMultiImage
    files = await _picker.pickMultiImage(limit: limit);
  }

  final photos = <PhotoAttachment>[];
  for (final file in files) {
    photos.add(PhotoAttachment(path: file.path));
  }
  return photos;
}
```

Add a second layer of defense in the UI by disabling the button when no slots remain.

```dart
bool get canAddPhoto => currentPhotos.length < maxPhotos;

// In the widget:
ElevatedButton(
  onPressed: canAddPhoto ? _onAddPhotoTapped : null,
  child: const Text('Add Photo'),
)
```

This ensures the picker is never invoked with an invalid `limit` even if something bypasses the service layer check.

---

## Summary

| Scenario | Method to use |
|----------|--------------|
| Pick exactly 1 photo | `pickImage()` |
| Pick up to N photos (N >= 2) | `pickMultiImage(limit: n)` |
| Pick unlimited photos | `pickMultiImage()` (omit limit) |

Using `pickMultiImage` on a screen that allows only 1 photo was wrong from the start. The common pattern of `remaining = maxCount - currentCount` fed directly into `pickMultiImage` will blow up the moment `remaining` hits 1.

`limit: 1` looks innocent but the package validates `>= 2` internally — watch out.

---

## Prevention Tips

A few habits will help avoid this class of bug in the future.

**1. Add an assert before calling `pickMultiImage`**

In development builds, an assert will surface the problem immediately with a clear message rather than a cryptic `PlatformException`.

```dart
Future<List<XFile>> pickMultiImageSafe(ImagePicker picker, {int? limit}) async {
  assert(
    limit == null || limit >= 2,
    'pickMultiImage limit must be null or >= 2. Got $limit. '
    'Use pickImage() for single-image selection.',
  );
  return picker.pickMultiImage(limit: limit);
}
```

**2. Encapsulate photo-picking logic in a single service**

Keeping the branching logic in one place means a future spec change (e.g., raising `maxPhotos` from 1 to 3) only requires editing one file. Scattering `pickMultiImage` calls across the codebase makes it hard to audit for this kind of constraint.

**3. Read changelogs when updating `image_picker`**

The `limit` parameter introduced a native-layer constraint that did not exist before. The changelog documented it, but skipping changelogs during dependency bumps is a common habit that leads to exactly this type of runtime surprise.

**4. Test the empty-state first**

Bugs like this only surface in a specific initial state (zero photos). Make it a habit to test the first interaction with a feature from a completely empty state — it catches off-by-one errors and similar edge cases early.

---

## Key Takeaways

- `pickMultiImage(limit:)` requires `limit >= 2`. Passing `1` throws a `PlatformException` at runtime with the message `cannot be lower 2:1`.
- The error message looks like a ratio constraint but it is not. It means: "the limit value cannot be lower than 2, and you passed 1."
- Use `pickImage(source: ImageSource.gallery)` for single-photo selection.
- The pattern `remaining = maxCount - currentCount` passed directly into `pickMultiImage` is dangerous. It crashes the moment `remaining` reaches `1`.
- Guard against invalid states in both the service layer (`if (limit == 1)` branch) and the UI layer (disable the button when `remaining <= 0`).
- The bug only reproduces when the photo list is empty, making it easy to miss in manual testing if you always start with existing photos.
