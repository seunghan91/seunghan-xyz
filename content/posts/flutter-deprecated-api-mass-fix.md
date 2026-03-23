---
title: "Flutter Deprecated API 대규모 수정 - withOpacity, DropdownButtonFormField, Switch 등"
date: 2025-07-20
draft: false
tags: ["Flutter", "Dart", "deprecated", "flutter analyze", "리팩터링", "코드품질"]
description: "flutter analyze에서 쏟아지는 deprecated API 경고를 일괄 수정하는 방법. withOpacity, DropdownButtonFormField, Switch.activeColor, GoRouter 등 케이스별 패턴 정리"
cover:
  image: "/images/og/flutter-deprecated-api-mass-fix.png"
  alt: "Flutter Deprecated Api Mass Fix"
  hidden: true
---

Flutter 프로젝트를 오래 유지하다 보면 `flutter analyze`가 수백 개의 deprecated 경고를 뱉는 시점이 온다. 기능은 잘 돌아가지만 Warning이 쌓이면 진짜 문제가 묻힌다. 이번에 한 번에 200개 넘는 deprecated 경고를 정리하면서 나온 패턴들을 정리한다.

deprecated 경고를 방치하면 결국 세 가지 문제로 이어진다. 첫째, 다음 Flutter 메이저 업그레이드 때 deprecated가 removal로 전환되어 컴파일 에러가 터진다. 둘째, 실제 버그나 타입 에러가 경고 노이즈에 묻혀 코드 리뷰에서 놓치기 쉽다. 셋째, 팀 합류 시 "왜 경고가 이렇게 많아요?"라는 질문이 나오는 순간 기술 부채를 설명해야 하는 부담이 생긴다. 한 번 정리해두면 이후 유지 비용이 훨씬 줄어든다.

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

출력을 파일로 저장해두면 수정 전후 비교가 편하다.

```bash
flutter analyze --no-pub 2>&1 | tee analyze_before.txt
```

전체 경고 수를 빠르게 파악하려면 `grep -c "info\|warning\|error" analyze_before.txt`로 카운트한다. 수정 후 다시 실행해서 숫자가 줄었는지 확인하는 것이 기본 검증 루틴이다.

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

**왜 바뀌었나:** `withOpacity`는 내부적으로 항상 sRGB 색 공간에서 알파 채널만 덮어쓰는 방식이었다. Flutter 3.x에서 wide-gamut(Display P3 등) 색 공간을 지원하게 되면서, 특정 채널만 변경하는 더 일반적인 API인 `withValues`가 도입됐다. `withValues(alpha: 0.5)`는 현재 색 공간을 유지하면서 알파만 변경한다는 의미가 명확하고, 나중에 red/green/blue 채널도 같은 방식으로 바꿀 수 있다.

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

**주의해야 할 상황:** 폼 초기화 후 외부에서 값을 동적으로 바꿔야 하는 경우(예: 다른 드롭다운 선택에 따라 현재 드롭다운 값이 리셋되는 연동 폼)에는 단순 치환으로 해결이 안 될 수 있다. 이럴 때는 `FormField`를 상위에서 컨트롤하거나 `GlobalKey<FormState>`로 `reset()`을 명시 호출하는 방식을 검토해야 한다.

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

**Material 3 스위치의 색상 구성:** Material 3에서 Switch의 시각적 구성은 더 세분화됐다. thumb(원형 토글), track(배경 트랙), icon(thumb 내부 아이콘)이 각각 독립적인 색상 속성을 가진다. 활성 상태와 비활성 상태도 분리되어 있어서 `thumbColor`, `trackColor`에 `MaterialStateProperty`를 사용하면 상태별로 세밀하게 제어할 수 있다.

```dart
Switch(
  value: _isEnabled,
  onChanged: _onToggle,
  thumbColor: MaterialStateProperty.resolveWith((states) {
    if (states.contains(MaterialState.selected)) return Colors.blue;
    return Colors.grey;
  }),
  trackColor: MaterialStateProperty.resolveWith((states) {
    if (states.contains(MaterialState.selected)) return Colors.blue.withValues(alpha: 0.3);
    return Colors.grey.withValues(alpha: 0.3);
  }),
)
```

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

**실용적인 패턴 선택:**

| 목적 | 권장 코드 |
|---|---|
| 전체 경로 문자열 필요 | `uri.toString()` |
| 경로 부분만 비교 (`/home`, `/profile`) | `uri.path` |
| 쿼리 파라미터 파싱 | `uri.queryParameters` |
| 특정 경로로 시작 여부 확인 | `uri.path.startsWith('/admin')` |

GoRouter 5.x 이후 `GoRouterState`를 통해 경로 정보를 얻는 방법도 있다. `GoRouterState.of(context).uri`로 현재 라우트의 URI를 가져올 수 있으며, 이 방법이 `routeInformationProvider`를 직접 참조하는 것보다 더 명시적이다.

---

## 케이스 5: BuildContext async gap 경고

`async` 함수 내에서 `await` 이후 `context`를 사용하면 경고가 난다. 위젯이 dispose된 후 context를 참조할 수 있기 때문이다.

**문제 코드:**
```dart
Future<void> _onPickImage() async {
  final result = await ImagePicker().pickImage(source: ImageSource.gallery);
  if (result != null) {
    context.read<SomeBloc>().add(ImageSelected(result.path)); // warning
  }
}
```

**수정:**
```dart
Future<void> _onPickImage() async {
  final result = await ImagePicker().pickImage(source: ImageSource.gallery);
  if (!mounted) return; // 추가
  if (result != null) {
    context.read<SomeBloc>().add(ImageSelected(result.path));
  }
}
```

`await` 직후 `if (!mounted) return;`을 추가하는 게 표준 패턴이다.

**왜 이게 실제 문제가 되나:** 사용자가 이미지 선택 다이얼로그를 열고 뒤로 가기로 화면을 나가면, `pickImage` Future가 완료될 때 해당 위젯은 이미 dispose된 상태다. 이때 `context`를 통해 BLoC이나 Navigator에 접근하면 `FlutterError: setState() called after dispose()` 또는 Provider `ProviderNotFoundException`이 발생할 수 있다. `mounted` 체크는 이런 race condition을 막는 가장 단순한 방어 코드다.

**StatelessWidget과 StatefulWidget의 차이:** `mounted`는 `State` 클래스의 속성이므로 `StatefulWidget` 내부에서만 사용 가능하다. `StatelessWidget`에서 async gap이 발생하는 경우는 구조 자체를 재검토해야 한다. 일반적으로 비동기 작업이 필요하다면 `StatefulWidget`으로 전환하거나 상태 관리 레이어(BLoC, Riverpod 등)로 로직을 올리는 것이 맞다.

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
list?.map(...)  // warning: list is non-nullable

// 수정
list.map(...)
```

**불필요한 const 키워드 누락:** `flutter analyze`는 const 생성자 호출에 `const`를 붙일 수 있는 경우 `prefer_const_constructors` 경고를 내기도 한다. 위젯 트리에서 const를 적극 활용하면 불필요한 rebuild를 줄일 수 있다는 점에서 단순 스타일 경고 이상의 의미가 있다.

```dart
// 경고: const를 추가할 수 있음
Padding(
  padding: EdgeInsets.all(16),
  child: Text('Hello'),
)

// 수정
const Padding(
  padding: EdgeInsets.all(16),
  child: Text('Hello'),
)
```

---

## 일괄 수정 전략: 규모에 따라 다르게 접근

경고 수가 50개 미만이라면 IDE에서 "Fix All" 또는 "Quick Fix" 기능으로 대부분 처리된다. VSCode의 경우 Problems 패널에서 같은 종류의 경고를 한 번에 수정하는 기능을 제공한다.

경고가 100개를 넘어가면 sed, awk, 또는 간단한 Python 스크립트로 일괄 치환하는 게 효율적이다. 특히 `withOpacity`처럼 패턴이 명확한 경우는 정규식 치환으로 빠르게 해결된다. 치환 후에는 반드시 `git diff`로 변경 범위를 검토하고, 특이한 케이스가 없는지 확인해야 한다.

경고 종류가 다양하고 케이스별로 판단이 필요한 경우는 카테고리별로 분리해서 순서대로 처리한다. `flutter analyze` 출력에서 경고 메시지 유형별로 grep해서 집중 수정하는 방식이 효과적이다.

```bash
# withOpacity 관련 경고만 추출
grep "withOpacity" analyze_before.txt

# Switch.activeColor 관련만 추출
grep "activeColor" analyze_before.txt
```

---

## 정리: 우선순위 접근법

1. **`flutter analyze --no-pub`** 실행해서 전체 현황 파악
2. **withOpacity** 부터 - 수가 가장 많고 sed 한 줄로 해결됨
3. **warning 레벨** (미사용 import, 미사용 변수) - 파일별 수동 수정
4. **info 레벨** 나머지 deprecation - 케이스별로 패턴 파악 후 수정
5. 수정 후 `flutter analyze --no-pub` 재실행으로 검증

한 번 정리해두면 이후엔 PR 머지 전 `flutter analyze` 결과를 확인하는 습관만으로 유지할 수 있다.

---

## Key Takeaways

- `withOpacity`는 `withValues(alpha:)`로 교체한다. sed 한 줄로 전체 일괄 처리가 가능하며, wide-gamut 색 공간 지원을 위한 Flutter 내부 변경의 결과다.
- `DropdownButtonFormField`의 `value` → `initialValue` 전환은 대부분 무난하지만, 외부 상태와 동기화가 필요한 controlled form의 경우 로직 검토가 필요하다.
- `Switch.activeColor`는 Material 3에서 thumb/track이 분리되면서 `activeThumbColor`로 바뀌었다. 세밀한 상태별 제어가 필요하다면 `MaterialStateProperty`를 활용한다.
- GoRouter의 `.location`은 `.uri.toString()` 또는 `.uri.path`로 대체한다. 용도에 따라 둘 중 하나를 선택한다.
- async 함수에서 `await` 이후 `context` 참조 전 `if (!mounted) return;`은 실제 크래시를 막는 안전장치다. 경고를 끄려는 목적이 아니라 방어 코드로 이해해야 한다.
- `flutter analyze`를 CI에 넣어두면 경고가 쌓이기 전에 차단할 수 있다. `flutter analyze --fatal-infos`로 info 레벨까지 에러로 처리하는 강도 높은 기준도 고려할 만하다.
