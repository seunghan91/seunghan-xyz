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

No `2:1` string exists anywhere in the project code.

---

## Root Cause

This is a constraint inside `image_picker`'s `pickMultiImage(limit:)` parameter.

The problematic code:

```dart
// limit = 1 - currentPhotoCount = 1 (when 0 photos selected)
final files = await _picker.pickMultiImage(limit: limit);
```

The screen capped photos at 1. When the user had 0 photos and tapped the button, `limit: 1` was passed straight into `pickMultiImage`.

`pickMultiImage` is a **multi-selection picker** — the `limit` must be `>= 2`. Passing `1` is semantically a single-image pick, which belongs to `pickImage`. The package enforces this and throws.

The message `cannot be lower 2:1` means: "limit cannot be lower than 2, but received 1."

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

---

## Summary

| Scenario | Method to use |
|----------|--------------|
| Pick exactly 1 photo | `pickImage()` |
| Pick up to N photos (N ≥ 2) | `pickMultiImage(limit: n)` |
| Pick unlimited photos | `pickMultiImage()` (omit limit) |

Using `pickMultiImage` on a screen that allows only 1 photo was wrong from the start. The common pattern of `remaining = maxCount - currentCount` fed directly into `pickMultiImage` will blow up the moment `remaining` hits 1.

`limit: 1` looks innocent but the package validates `>= 2` internally — watch out.
