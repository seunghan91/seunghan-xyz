---
title: "Flutter image_picker pickMultiImage에 limit: 1 넘기면 나는 크래시"
date: 2026-03-08
draft: true
tags: ["Flutter", "iOS", "image_picker", "디버깅", "Dart"]
description: "사진 추가 버튼을 누르면 'cannot be lower 2:1' 에러가 발생하는 원인과 해결법. pickMultiImage의 limit 파라미터는 2 이상이어야 한다."
---

Flutter 앱에서 사진 추가 버튼을 누르는 순간 `cannot be lower 2:1` 에러가 떴다. 처음엔 어디서 나는 에러인지 감도 못 잡았다.

---

## 증상

사진 첨부 버튼을 누르면 앱이 에러를 뱉는다.

```
cannot be lower 2:1
```

코드 어디에도 `2:1`이라는 문자열이 없다. 에러 스택도 애매하게 패키지 내부를 가리키고 있었다.

---

## 원인

`image_picker`의 `pickMultiImage(limit:)` 파라미터 제약 때문이다.

문제가 된 코드:

```dart
// limit = 1 - 현재사진수 = 1 (사진 0장일 때)
final files = await _picker.pickMultiImage(limit: limit);
```

앱의 사진 최대 개수를 1장으로 제한하고 있었는데, 사진이 0장인 상태에서 버튼을 누르면 `limit: 1`이 그대로 `pickMultiImage`에 전달됐다.

`pickMultiImage`는 **다중 선택 피커**이기 때문에, `limit`이 `2` 미만이면 에러를 던진다. `limit: 1`은 사실상 단일 선택이므로 `pickImage`를 써야 한다.

에러 메시지 `cannot be lower 2:1`은 "limit은 2보다 낮을 수 없는데 1이 넘어왔다"는 의미다.

---

## 해결

`limit == 1`인 경우 `pickImage`로 분기 처리했다.

```dart
Future<List<PhotoAttachment>> pickPhotos({int limit = 10}) async {
  final List<XFile> files;
  if (limit == 1) {
    // pickMultiImage는 limit >= 2 이상이어야 함
    final file = await _picker.pickImage(source: ImageSource.gallery);
    files = file != null ? [file] : [];
  } else {
    files = await _picker.pickMultiImage(limit: limit);
  }

  final photos = <PhotoAttachment>[];
  for (final file in files) {
    // EXIF GPS 추출 등 후처리...
    photos.add(PhotoAttachment(path: file.path));
  }
  return photos;
}
```

---

## 정리

| 상황 | 써야 할 메서드 |
|------|--------------|
| 1장만 선택 | `pickImage()` |
| 2장 이상 선택 | `pickMultiImage(limit: n)` (n >= 2) |
| 제한 없이 여러 장 | `pickMultiImage()` (limit 생략) |

사진 최대 허용 개수가 1장인 화면에서 `pickMultiImage`를 쓰는 건 처음부터 맞지 않았다. `remaining = maxCount - currentCount` 계산 후 `pickMultiImage`에 그대로 넘기는 패턴은 `remaining`이 1이 되는 순간 터진다.

`limit: 1`이 아무 문제 없을 것처럼 생겼는데, 패키지 내부에서 `>= 2` 검증을 하고 있으니 주의.
