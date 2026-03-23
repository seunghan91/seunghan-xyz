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

처음에는 iOS 권한 문제인가 싶었다. `NSPhotoLibraryUsageDescription`이 빠졌거나, 시뮬레이터 사진 라이브러리 세팅이 이상한 건지 의심했다. 하지만 권한 팝업은 정상적으로 뜨다가 선택 화면이 열리기 직전에 크래시가 났다. 권한 문제라면 팝업 자체가 안 떴을 것이다.

에러 스택을 다시 들여다봤다.

```
PlatformException(invalid_arguments, cannot be lower 2:1, null, null)
    at Object.throw_ [as throw] (...)
    at image_picker_ios/...
```

`PlatformException`이고, 발생 지점이 `image_picker_ios` 패키지 내부였다. Flutter 코드가 아니라 네이티브 플러그인 쪽에서 던지는 예외다. 이 단서를 보고서야 `image_picker` API 제약 문제라는 걸 깨달았다.

---

## 원인

`image_picker`의 `pickMultiImage(limit:)` 파라미터 제약 때문이다.

문제가 된 코드:

```dart
// limit = maxCount - currentCount = 1 - 0 = 1 (사진 0장일 때)
final files = await _picker.pickMultiImage(limit: limit);
```

앱의 사진 최대 개수를 1장으로 제한하고 있었는데, 사진이 0장인 상태에서 버튼을 누르면 `limit: 1`이 그대로 `pickMultiImage`에 전달됐다.

`pickMultiImage`는 **다중 선택 피커**이기 때문에, `limit`이 `2` 미만이면 에러를 던진다. `limit: 1`은 사실상 단일 선택이므로 `pickImage`를 써야 한다.

에러 메시지 `cannot be lower 2:1`은 "limit은 2보다 낮을 수 없는데 1이 넘어왔다"는 의미다.

### 왜 이런 제약이 있는가?

iOS의 `PHPickerViewController` (iOS 14+에서 `image_picker`가 내부적으로 사용하는 네이티브 피커)는 `selectionLimit` 프로퍼티를 통해 선택 가능한 최대 개수를 지정한다. 이 값이 `0`이면 무제한, `1`이면 단일 선택 모드로 동작한다.

`image_picker_ios` 플러그인은 `pickMultiImage`를 호출할 때 `limit` 파라미터가 존재하면 `PHPickerConfiguration.selectionLimit`에 그 값을 세팅한다. 그런데 플러그인은 "다중 선택이라는 의도"에서 `limit >= 2`를 강제한다. `limit: 1`은 의미상 단일 선택이므로 `pickImage`를 쓰라는 것이다.

이 검증 로직은 네이티브 Objective-C 코드에 있기 때문에 Dart 수준에서는 컴파일 타임에 잡히지 않는다. 그래서 런타임에 `PlatformException`으로 터진다.

### 왜 발견하기 어려웠나?

이 버그가 교묘한 이유가 있다.

첫째, **에러 메시지가 직관적이지 않다.** `cannot be lower 2:1`이라는 문자열은 코드 어디에도 없고, 비율처럼 읽힌다. `2:1 ratio`를 연상시켜서 처음에는 이미지 크기 제약 관련 에러로 오해하기 쉽다.

둘째, **재현 조건이 특정 상태에서만 발생한다.** 사진이 이미 1장 있을 때는 `remaining = 1 - 1 = 0`이 되어 버튼 자체가 비활성화되거나 다른 분기를 탄다. 사진이 0장일 때만 `limit: 1`이 `pickMultiImage`에 전달된다. 즉, 빈 상태에서 첫 사진을 추가하는 시나리오에서만 터진다.

셋째, **`pickMultiImage(limit:)`는 Flutter 2.x 시절에 없던 파라미터다.** `image_picker 0.8.6`(2022년 말)에서 `limit` 파라미터가 추가됐다. 기존 코드에 `limit`을 추가한 개발자가 제약 조건을 모르고 그대로 계산값을 넘겼을 가능성이 높다.

---

## 재현 코드

```dart
// 이렇게 하면 사진 0장 상태에서 반드시 크래시 난다
class PhotoService {
  final ImagePicker _picker = ImagePicker();
  List<XFile> _photos = [];
  final int maxPhotos = 1;

  Future<void> addPhoto() async {
    final remaining = maxPhotos - _photos.length; // = 1
    // remaining이 1이면 pickMultiImage에서 PlatformException 발생
    final files = await _picker.pickMultiImage(limit: remaining);
    _photos.addAll(files);
  }
}
```

---

## 디버깅 과정

에러를 처음 마주쳤을 때 시도했던 과정을 공유한다.

**1단계: 에러 메시지 검색**

`cannot be lower 2:1`로 구글링을 했다. 유사한 이슈가 `image_picker` GitHub에 올라와 있었지만, 제목들이 제각각이어서 찾기가 쉽지 않았다. "limit 1 crash", "pickMultiImage crash iOS" 키워드로 다시 검색하니 관련 이슈를 찾을 수 있었다.

**2단계: 스택 트레이스 분석**

```
PlatformException(invalid_arguments, cannot be lower 2:1, null, null)
```

`invalid_arguments`라는 코드가 있다. 이건 내가 잘못된 인자를 넘겼다는 뜻이다. 그렇다면 `image_picker` API 중 내가 인자를 동적으로 계산해서 넘기는 곳이 어디인지 찾아봤다.

**3단계: `pickMultiImage` 호출부 추적**

프로젝트에서 `pickMultiImage`를 호출하는 곳을 찾아보니 한 곳이었고, 거기서 `limit` 값이 `remaining = maxPhotos - currentCount`로 계산되고 있었다. `maxPhotos = 1`, `currentCount = 0`이면 `remaining = 1`. 바로 이것이 원인이었다.

**4단계: 공식 문서 확인**

`image_picker` 공식 문서와 소스코드를 확인하니 `pickMultiImage`의 `limit` 파라미터에 대한 설명이 있었다:

> `limit`: The maximum number of images to pick. Must be 2 or greater.

짧고 명확한 설명이었지만, API 사용 중에 이 문서를 꼼꼼히 읽지 않았던 게 실수였다.

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

### 더 방어적인 접근

`limit <= 0`인 엣지 케이스도 처리하면 더 견고하다.

```dart
Future<List<PhotoAttachment>> pickPhotos({int limit = 10}) async {
  // limit이 0 이하면 아무것도 선택할 수 없는 상태 — 호출 자체를 막는다
  if (limit <= 0) return [];

  final List<XFile> files;
  if (limit == 1) {
    final file = await _picker.pickImage(source: ImageSource.gallery);
    files = file != null ? [file] : [];
  } else {
    // limit >= 2
    files = await _picker.pickMultiImage(limit: limit);
  }

  final photos = <PhotoAttachment>[];
  for (final file in files) {
    photos.add(PhotoAttachment(path: file.path));
  }
  return photos;
}
```

UI 레이어에서도 이중으로 방어하는 게 좋다. `remaining <= 0`이면 버튼 자체를 비활성화한다.

```dart
// 예: 사진 추가 버튼 활성화 조건
bool get canAddPhoto => currentPhotos.length < maxPhotos;

// 위젯에서
ElevatedButton(
  onPressed: canAddPhoto ? _onAddPhotoTapped : null,
  child: Text('사진 추가'),
)
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

---

## 예방 팁

이 문제를 미리 막으려면 몇 가지 습관이 도움이 된다.

**1. `pickMultiImage` 호출 전 assert 추가**

개발 중에는 `assert`로 잘못된 인자를 빠르게 잡는다.

```dart
Future<List<XFile>> pickMultiImageSafe(ImagePicker picker, {int? limit}) async {
  assert(limit == null || limit >= 2,
      'pickMultiImage limit must be null or >= 2. Got $limit. Use pickImage for single selection.');
  return picker.pickMultiImage(limit: limit);
}
```

**2. 사진 추가 로직을 별도 서비스로 캡슐화**

분기 로직을 한 곳에만 두면, 나중에 스펙이 바뀌어도 수정 지점이 하나다.

**3. `image_picker` 버전 업데이트 시 체인지로그 확인**

`limit` 파라미터처럼 네이티브 제약이 생기는 변경은 체인지로그에 기록된다. 버전을 올릴 때 `CHANGELOG.md`를 확인하는 습관이 이런 런타임 에러를 예방한다.

---

## Key Takeaways

- `pickMultiImage(limit:)`의 `limit`은 반드시 `2` 이상이어야 한다. `1`을 넘기면 `PlatformException`이 발생한다.
- 에러 메시지 `cannot be lower 2:1`은 "limit이 2 미만인데 1이 왔다"는 뜻이다. 비율 관련 에러가 아니다.
- 단일 사진 선택은 `pickImage(source: ImageSource.gallery)`를 사용한다.
- `remaining = maxCount - currentCount`를 `pickMultiImage`에 그대로 넘기는 패턴은 위험하다. `remaining == 1`이 되는 순간 크래시가 난다.
- UI에서 `remaining <= 0`일 때 버튼을 비활성화하는 방어 코드를 추가하면 이중으로 안전하다.
