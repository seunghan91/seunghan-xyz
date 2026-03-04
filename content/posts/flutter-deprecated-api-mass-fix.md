---
title: "Flutter Deprecated API 대규모 수정 - withOpacity, DropdownButtonFormField, Switch 등"
date: 2026-02-25
draft: false
tags: ["Flutter", "Dart", "deprecated", "flutter analyze", "리팩터링", "코드품질"]
description: "flutter analyze에서 쏟아지는 deprecated API 경고를 일괄 수정하는 방법. withOpacity, DropdownButtonFormField, Switch.activeColor, GoRouter 등 케이스별 패턴 정리"
---

Flutter 프로젝트를 오래 유지하다 보면 `flutter analyze`가 수백 개의 deprecated 경고를 뱉는 시점이 온다. 기능은 잘 돌아가지만 Warning이 쌓이면 진짜 문제가 묻힌다. 이번에 한 번에 200개 넘는 deprecated 경고를 정리하면서 나온 패턴들을 정리한다.

---

## 진단: flutter analyze로 현황 파악

```bash
flutter analyze --no-pub
```

`--no-pub`을 붙이면 pub 패키지 재분석을 건너뛰어 빠르다. 출력에서 카테고리별로 분류해보면 대부분 몇 가지 패턴이 반복된다.

```
info • 'withOpacity' is deprecated ... • lib/core/theme/app_theme.dart:45:22
info • 'value' is deprecated and shouldn't be used. Use 'initialValue' instead ...
info • 'activeColor' is deprecated ... Use 'activeThumbColor' instead.
warning • Unused import: 'package:go_router/go_router.dart' ...
```

---

## 케이스 1: Color.withOpacity → withValues(alpha:)

가장 많이 나오는 deprecation이다. 거의 모든 색상 투명도 처리 코드가 해당된다.

**변경 전:**
```dart
color: Colors.blue.withOpacity(0.5)
color: theme.accent.withOpacity(0.16)
border: Border.all(color: colors.border.withOpacity(0.3))
```

**변경 후:**
```dart
color: Colors.blue.withValues(alpha: 0.5)
color: theme.accent.withValues(alpha: 0.16)
border: Border.all(color: colors.border.withValues(alpha: 0.3))
```

파일이 많으면 sed로 한 번에 바꾼다.

```bash
# 프로젝트 전체 일괄 치환 (macOS)
find lib -name "*.dart" -exec sed -i '' 's/\.withOpacity(\([^)]*\))/.withValues(alpha: \1)/g' {} \;
```

치환 후 `flutter analyze`로 다시 확인한다. 간혹 변수명이 `withOpacity`인 메서드를 직접 구현한 경우 오탐이 생기니 결과를 꼭 검토한다.

---

## 케이스 2: DropdownButtonFormField.value → initialValue

Flutter 3.x 이후 `DropdownButtonFormField`의 초기값 설정 파라미터명이 바뀌었다.

**변경 전:**
```dart
DropdownButtonFormField<String>(
  value: _selectedCategory,
  items: ...,
  onChanged: (v) => setState(() => _selectedCategory = v),
)
```

**변경 후:**
```dart
DropdownButtonFormField<String>(
  initialValue: _selectedCategory,
  items: ...,
  onChanged: (v) => setState(() => _selectedCategory = v),
)
```

`value`와 `initialValue`는 동작 방식에 미묘한 차이가 있다. `value`는 controlled 방식으로 외부 상태와 항상 동기화되고, `initialValue`는 초기값만 지정한다. 대부분의 경우 `initialValue`로 바꿔도 동작이 같다.

---

## 케이스 3: Switch.activeColor → activeThumbColor

`Switch` 위젯의 색상 프로퍼티들이 Material 3 기준으로 세분화됐다.

**변경 전:**
```dart
Switch(
  value: _isEnabled,
  onChanged: _onToggle,
  activeColor: Colors.blue,
)
```

**변경 후:**
```dart
Switch(
  value: _isEnabled,
  onChanged: _onToggle,
  activeThumbColor: Colors.blue,
)
```

트랙 색상을 함께 바꾸고 싶다면 `activeTrackColor`도 추가한다. 기존 `activeColor`는 thumb과 track 모두 같은 색으로 설정했지만, 새 API는 분리되어 있다.

---

## 케이스 4: GoRouter location → uri.toString()

GoRouter에서 현재 경로를 가져올 때 `.location` 대신 `.uri`를 써야 한다.

**변경 전:**
```dart
final currentPath = GoRouter.of(context)
    .routeInformationProvider
    .value
    .location;
```

**변경 후:**
```dart
final currentPath = GoRouter.of(context)
    .routeInformationProvider
    .value
    .uri
    .toString();
```

`location`은 String이었고, `uri`는 `Uri` 객체다. 경로 비교나 startsWith 같은 용도라면 `toString()` 없이 `uri.path`를 쓰는 게 더 적절하다.

---

## 케이스 5: BuildContext async gap 경고

`async` 함수 내에서 `await` 이후 `context`를 사용하면 경고가 난다. 위젯이 dispose된 후 context를 참조할 수 있기 때문이다.

**문제 코드:**
```dart
Future<void> _onPickImage() async {
  final result = await ImagePicker().pickImage(source: ImageSource.gallery);
  if (result != null) {
    context.read<SomeBloc>().add(ImageSelected(result.path)); // ⚠️
  }
}
```

**수정:**
```dart
Future<void> _onPickImage() async {
  final result = await ImagePicker().pickImage(source: ImageSource.gallery);
  if (!mounted) return; // ← 추가
  if (result != null) {
    context.read<SomeBloc>().add(ImageSelected(result.path));
  }
}
```

`await` 직후 `if (!mounted) return;`을 추가하는 게 표준 패턴이다.

---

## 케이스 6: 기타 자잘한 경고들

**불필요한 string interpolation:**
```dart
// 전 (경고)
Text('${someVariable}')
Text('?id=${widget.id}')  // 중괄호 불필요

// 후
Text('$someVariable')
Text('?id=$widget.id')    // 단, 프로퍼티 접근 시엔 중괄호 필요
Text('?id=${widget.id}')  // 이 경우엔 중괄호 있어야 함
```

**불필요한 toList():**
```dart
// 전
...answers.toList().map((a) => Widget())

// 후 (spread 연산자는 Iterable을 직접 받음)
...answers.map((a) => Widget())
```

**Null-safe 연산자 오용:**
```dart
// non-nullable 변수에 ?. 쓰는 경우
final list = <String>[];
list?.map(...)  // ⚠️ list is non-nullable

// 수정
list.map(...)
```

---

## 정리: 우선순위 접근법

1. **`flutter analyze --no-pub`** 실행해서 전체 현황 파악
2. **withOpacity** 부터 - 수가 가장 많고 sed 한 줄로 해결됨
3. **warning 레벨** (미사용 import, 미사용 변수) - 파일별 수동 수정
4. **info 레벨** 나머지 deprecation - 케이스별로 패턴 파악 후 수정
5. 수정 후 `flutter analyze --no-pub` 재실행으로 검증

한 번 정리해두면 이후엔 PR 머지 전 `flutter analyze` 결과를 확인하는 습관만으로 유지할 수 있다.
