---
title: "Flutter Material SnackBar 걷어내기 --- Overlay 기반 Glassmorphism Toast + Apple HIG 시스템 색상"
date: 2026-03-24
draft: false
tags: ["Flutter", "Glassmorphism", "Apple HIG", "Overlay", "UI"]
categories: ["Flutter"]
description: "Flutter 앱에서 Material SnackBar를 걷어내고 Overlay 기반 글라스모피즘 토스트를 직접 만든 과정. Apple HIG 시스템 색상, CupertinoIcons, BackdropFilter 성능까지 정리했다."
---

## Material SnackBar가 거슬리기 시작한 순간

Flutter 앱에서 Glass 디자인 시스템을 구축하면서 Material Design 컴포넌트를 하나씩 걷어내고 있었다. `AlertDialog`는 `GlassDialog`로, `Card`는 `GlassCard`로, `AppBar`는 `GlassAppBar`로. 하나씩 바꿔가니 앱 전체가 반투명 블러 기반의 통일된 느낌이 잡혔다.

그런데 문제가 하나 남았다. 토스트 알림이었다.

`ScaffoldMessenger.of(context).showSnackBar()`로 띄우는 Material `SnackBar`가 화면 하단에 불투명한 초록/파랑/주황 배경으로 뜨는데, Glass로 바뀐 나머지 UI와 전혀 어울리지 않았다. 하단 고정 위치도 마음에 안 들었다. iOS 네이티브 앱들처럼 상단에서 슬라이딩으로 내려왔다가 올라가는 토스트가 필요했다.

결론부터 말하면, `Overlay` 기반으로 커스텀 글라스모피즘 토스트를 직접 만들었다. Apple HIG 공식 시스템 색상을 적용하고, `CupertinoIcons`로 SF Symbols 느낌까지 살렸다. 이 글에서 그 과정을 정리한다.

---

## ScaffoldMessenger vs Overlay: 근본적인 차이

### ScaffoldMessenger의 한계

Flutter에서 토스트를 띄우는 기본 방법은 `ScaffoldMessenger`다.

```dart
ScaffoldMessenger.of(context).showSnackBar(
  SnackBar(
    content: Text('저장되었습니다'),
    backgroundColor: Colors.green.shade600,
    behavior: SnackBarBehavior.floating,
  ),
);
```

이 방식의 문제점은 명확하다:

| 항목 | ScaffoldMessenger | Overlay |
|------|------------------|---------|
| 위치 | 하단 고정 (상단 불가) | 어디든 자유 배치 |
| 디자인 | Material 스타일 강제 | 완전 커스텀 |
| Scaffold 의존 | 필수 (없으면 에러) | 불필요 |
| 애니메이션 | 제한적 (fade/slide) | 완전 제어 |
| 라우트 전환 | ScaffoldMessenger 범위 내 유지 | Overlay는 앱 전체 |

`ScaffoldMessenger`는 `Scaffold` 위젯 트리 안에서만 동작한다. `Scaffold`가 없는 화면에서 호출하면 `No ScaffoldMessenger widget found` 에러가 뜬다. 반면 `Overlay`는 `MaterialApp`이 기본으로 제공하는 오버레이 스택 위에 독립적으로 위젯을 띄울 수 있다.

### Overlay의 구조

`Overlay`는 Flutter가 제공하는 위젯 트리 위의 독립적인 레이어다. 공식 문서의 설명을 빌리면:

> An overlay is a Stack of entries that can be managed independently. Overlays let independent child widgets "float" visual elements on top of other widgets.

핵심은 `OverlayEntry`다. 이걸 `Overlay.of(context).insert()`로 삽입하면 현재 화면 위에 어떤 위젯이든 띄울 수 있다. `SnackBar`처럼 `Scaffold`에 종속되지 않으니 위치, 애니메이션, 스타일을 완전히 제어할 수 있다.

```dart
final overlay = Overlay.of(context);
final entry = OverlayEntry(
  builder: (context) => Positioned(
    top: MediaQuery.of(context).padding.top + 8,
    left: 16,
    right: 16,
    child: MyCustomToast(),
  ),
);
overlay.insert(entry);

// 나중에 제거
entry.remove();
```

이 패턴이 커스텀 토스트의 기본 골격이다.

---

## Apple HIG 시스템 색상: Flutter에서 네이티브 느낌 살리기

### Material Colors vs Apple System Colors

Flutter의 `Colors.green`, `Colors.red` 같은 Material 색상은 Apple의 시스템 색상과 다르다. 네이티브 iOS 느낌을 살리려면 Apple HIG(Human Interface Guidelines)에서 정의한 공식 hex 값을 직접 사용해야 한다.

Apple은 light/dark 모드별로 다른 hex 값을 정의한다. 다크 모드에서는 밝기를 약간 올려서 어두운 배경 위에서도 동일한 인지적 밝기를 유지한다.

| 상태 | Light Mode | Dark Mode | 용도 |
|------|-----------|-----------|------|
| Success | `#34C759` | `#30D158` | 완료, 성공 |
| Info | `#007AFF` | `#0A84FF` | 정보, 안내 |
| Warning | `#FF9500` | `#FF9F0A` | 주의, 경고 |
| Error | `#FF3B30` | `#FF453A` | 오류, 실패 |

RGB로 보면 차이가 미미해 보이지만, 실제 어두운 배경 위에서 보면 다크 모드 색상이 확실히 더 잘 보인다. Apple이 이 값을 따로 정의한 이유가 있다.

### Flutter에서의 적용

```dart
final isDark = Theme.of(context).brightness == Brightness.dark;

// Apple HIG 공식 시스템 그린
final successColor = isDark
    ? const Color(0xFF30D158)  // dark
    : const Color(0xFF34C759); // light
```

Flutter에는 `CupertinoColors.systemGreen` 같은 `CupertinoDynamicColor`도 있다. 이건 `BuildContext`를 기반으로 자동으로 light/dark를 전환해주는데, 문제는 `resolveFrom(context)`를 호출해야 실제 색상값이 나온다는 점이다. 토스트처럼 `Overlay` 위에서 별도 context로 동작하는 경우에는 직접 hex를 지정하는 게 더 확실하다.

### CupertinoIcons: SF Symbols의 Flutter 서브셋

아이콘도 Material Icons 대신 `CupertinoIcons`를 사용했다. `cupertino_icons` 패키지는 Apple의 SF Symbols 라이브러리의 서브셋을 Flutter에서 쓸 수 있게 해준다.

| 상태 | Material Icons | CupertinoIcons (SF Symbols) |
|------|---------------|----------------------------|
| Success | `Icons.check_circle_rounded` | `CupertinoIcons.checkmark_circle_fill` |
| Info | `Icons.info_rounded` | `CupertinoIcons.info_circle_fill` |
| Warning | `Icons.warning_rounded` | `CupertinoIcons.exclamationmark_triangle_fill` |
| Error | `Icons.error_rounded` | `CupertinoIcons.xmark_circle_fill` |

두 아이콘 세트를 나란히 놓고 비교하면 차이가 확 느껴진다. CupertinoIcons 쪽이 선이 더 가늘고, 라운딩이 iOS 특유의 부드러운 곡선을 따른다. Glass 디자인과 훨씬 자연스럽게 어울린다.

---

## GlassToast 구현: 핵심 구조

### 전체 아키텍처

```
GlassToast.show(context, message, type)
    │
    ├─ Overlay.of(context).insert(OverlayEntry)
    │
    └─ _GlassToastWidget (StatefulWidget)
        ├─ AnimationController (slide + fade)
        ├─ SlideTransition (위에서 아래로)
        ├─ FadeTransition (투명도)
        ├─ GestureDetector (탭/스와이프 dismiss)
        └─ ClipRRect + BackdropFilter (글라스 효과)
            └─ Container (반투명 배경 + 얇은 보더)
                └─ Row [Icon, Text]
```

### 정적 API 설계

토스트는 앱 어디서든 한 줄로 호출할 수 있어야 한다. `static` 메서드로 만들어서 인스턴스 생성 없이 바로 사용한다.

```dart
class GlassToast {
  GlassToast._();

  static OverlayEntry? _currentEntry;
  static Timer? _autoHideTimer;

  static void show(
    BuildContext context, {
    required String message,
    GlassToastType type = GlassToastType.info,
    Duration duration = const Duration(seconds: 3),
  }) {
    if (!context.mounted) return;
    dismiss(); // 기존 토스트가 있으면 먼저 제거

    final overlay = Overlay.of(context);
    _currentEntry = OverlayEntry(
      builder: (context) => _GlassToastWidget(
        message: message,
        type: type,
        duration: duration,
        onDismiss: dismiss,
      ),
    );
    overlay.insert(_currentEntry!);
    _autoHideTimer = Timer(duration + Duration(milliseconds: 300), dismiss);
  }

  static void dismiss() {
    _autoHideTimer?.cancel();
    _autoHideTimer = null;
    _currentEntry?.remove();
    _currentEntry = null;
  }
}
```

`dismiss()`를 먼저 호출해서 동시에 여러 토스트가 겹치는 걸 방지한다. `context.mounted` 체크도 빠뜨리면 안 된다. 비동기 작업 후 호출되면 이미 dispose된 context일 수 있다.

### 슬라이딩 애니메이션

상단에서 내려오는 느낌을 주기 위해 `SlideTransition`과 `FadeTransition`을 조합했다.

```dart
_controller = AnimationController(
  vsync: this,
  duration: const Duration(milliseconds: 300),
);

_slideAnimation = Tween<Offset>(
  begin: const Offset(0, -1), // 화면 위쪽 바깥
  end: Offset.zero,           // 원래 위치
).animate(CurvedAnimation(
  parent: _controller,
  curve: Curves.easeOutCubic,      // 들어올 때 부드럽게
  reverseCurve: Curves.easeInCubic, // 나갈 때 빠르게
));
```

`Curves.easeOutCubic`은 시작이 빠르고 끝이 느린 커브다. 토스트가 "톡" 하고 나타나서 제자리에 부드럽게 안착하는 느낌을 준다. 반대로 사라질 때는 `easeInCubic`으로 처음 느리다가 빠르게 올라간다.

### 스와이프 dismiss

iOS 알림처럼 위로 스와이프하면 토스트가 사라지는 기능도 넣었다.

```dart
GestureDetector(
  onVerticalDragEnd: (details) {
    if (details.velocity.pixelsPerSecond.dy < -100) {
      _controller.reverse().then((_) {
        if (mounted) widget.onDismiss();
      });
    }
  },
  // ...
)
```

`velocity.pixelsPerSecond.dy < -100`은 위쪽으로 초당 100px 이상의 속도로 스와이프했을 때를 감지한다. 너무 낮으면 실수로 터치해도 사라지고, 너무 높으면 의도적으로 밀어도 반응이 없다. 100~150 사이가 적당하다.

---

## BackdropFilter 글라스 효과와 성능

### 글라스 효과의 핵심 패턴

글라스모피즘의 시각적 구성 요소는 세 가지다:

1. **BackdropFilter**: 뒤쪽 콘텐츠에 블러를 건다
2. **반투명 배경색**: 완전 투명하면 블러가 안 보이고, 불투명하면 글라스가 아니다
3. **얇은 보더**: 유리 가장자리의 빛 반사를 표현한다

```dart
ClipRRect(
  borderRadius: BorderRadius.circular(16),
  child: BackdropFilter(
    filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
    child: Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        // 반투명 배경
        color: (isDark ? const Color(0xFF2C2C2E) : Colors.white)
            .withValues(alpha: 0.72),
        // 유리 가장자리 보더
        border: Border.all(
          color: Colors.white.withValues(alpha: isDark ? 0.08 : 0.25),
          width: 0.5,
        ),
      ),
    ),
  ),
)
```

`sigma` 값은 블러 강도를 결정한다. 6~12는 은은한 블러, 20~30은 강한 프로스트 글라스 느낌이다. 토스트에는 24를 썼다. 상단에 잠깐 떠있는 요소라 배경이 강하게 흐려져야 텍스트가 잘 읽힌다.

### 성능 주의사항

`BackdropFilter`는 Flutter에서 가장 비용이 큰 위젯 중 하나다. Flutter GitHub 이슈 [#32804](https://github.com/flutter/flutter/issues/32804)에서도 오랫동안 성능 문제가 논의됐다.

핵심 최적화 규칙:

1. **반드시 ClipRRect/ClipRect로 감싸라**: 클리핑 없이 BackdropFilter를 쓰면 전체 화면을 블러 처리한다. `ClipRRect`로 토스트 영역만 클리핑하면 GPU 부하가 크게 줄어든다.

2. **중첩 BackdropFilter 피하라**: 토스트 + 다이얼로그 + 앱바가 동시에 블러를 걸면 프레임 드롭이 온다. 같은 화면에 3개 이상 BackdropFilter가 겹치지 않도록 설계해야 한다.

3. **BackdropGroup 활용**: Flutter 최신 버전에서는 `BackdropFilter.grouped()`와 `BackdropGroup`을 지원한다. 여러 BackdropFilter가 같은 입력을 공유하면 한 번만 블러를 계산한다.

4. **Impeller 엔진 활성화**: Flutter의 Impeller 렌더링 엔진이 BackdropFilter 성능을 크게 개선했다. Android에서는 `AndroidManifest.xml`에서 활성화할 수 있다.

토스트는 화면에 하나만 뜨고 크기도 작으니 성능 문제가 거의 없지만, Glass 디자인 시스템 전체를 운영할 때는 이 규칙들을 지키는 게 중요하다.

---

## FeedbackService 교체: 기존 코드 영향 최소화

토스트를 교체할 때 가장 신경 쓴 부분은 기존 코드에 미치는 영향이다. 앱 전체에서 `FeedbackService.showSuccess()`, `FeedbackService.showInfo()`, `FeedbackService.showWarning()`을 호출하는 곳이 수십 군데였다.

### 전략: 인터페이스 유지, 내부만 교체

`FeedbackService`의 public API는 그대로 두고, 내부 구현만 `GlassToast`로 바꿨다.

```dart
// Before
static void showSuccess(BuildContext context, String message, {
  Duration duration = const Duration(seconds: 2),
}) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Row(children: [
        const Icon(Icons.check_circle, color: Colors.white),
        const SizedBox(width: 8),
        Expanded(child: Text(message)),
      ]),
      backgroundColor: Colors.green.shade600,
      behavior: SnackBarBehavior.floating,
    ),
  );
}

// After
static void showSuccess(BuildContext context, String message, {
  Duration duration = const Duration(seconds: 2),
}) {
  GlassToast.show(
    context,
    message: message,
    type: GlassToastType.success,
    duration: duration,
  );
}
```

호출하는 쪽은 코드 변경 없이 자동으로 새 토스트가 적용된다. `context.showSnackBar()` 같은 extension 메서드도 같은 방식으로 교체했다.

### `withOpacity` deprecated 주의

Flutter 최신 버전에서는 `Color.withOpacity()`가 deprecated됐다. `withValues(alpha:)`를 써야 한다.

```dart
// deprecated
Colors.white.withOpacity(0.3)

// 올바른 방법
Colors.white.withValues(alpha: 0.3)
```

이유는 precision loss 때문이다. `withOpacity`는 내부적으로 `int`로 변환하면서 소수점 이하 정밀도를 잃을 수 있다. `withValues`는 이 문제가 없다.

---

## 결과물과 동작 방식

최종 토스트는 이렇게 동작한다:

1. 상단 SafeArea 아래에서 슬라이드 인
2. 글라스 블러 배경 + Apple HIG 색상 아이콘
3. 설정 시간(기본 3초) 후 슬라이드 아웃
4. 위로 스와이프하면 즉시 dismiss
5. 탭해도 dismiss
6. 새 토스트가 오면 기존 토스트 자동 제거

```dart
// 사용법
GlassToast.show(context, message: '저장 완료', type: GlassToastType.success);
GlassToast.show(context, message: '네트워크 불안정', type: GlassToastType.warning);
GlassToast.dismiss(); // 수동 제거
```

---

## 디자인 가이드에 기록하기

이런 디자인 시스템 변경은 프로젝트 가이드 문서에 반드시 기록해야 한다. 안 그러면 다음에 작업할 때 또 Material `SnackBar`를 쓰게 된다.

`CLAUDE.md`(프로젝트 가이드 문서)에 Material → Glass 매핑 테이블을 추가했다:

| 용도 | Material (사용 금지) | Glass (사용) |
|------|---------------------|-------------|
| 토스트/알림 | `SnackBar` | `GlassToast.show()` |
| 다이얼로그 | `AlertDialog` | `GlassDialog.show()` |
| 바텀시트 | `showModalBottomSheet` | `GlassSheet` |
| 버튼 | `ElevatedButton` | `GlassButton` |
| 텍스트필드 | `TextField` | `GlassTextField` |

이렇게 해두면 새 화면을 만들 때 어떤 컴포넌트를 써야 하는지 바로 알 수 있다. AI 코딩 도구를 쓸 때도 이 가이드를 참조해서 자동으로 Glass 컴포넌트를 사용하게 된다.

---

## 정리

Material Design의 `SnackBar`는 빠르게 프로토타입할 때는 편하지만, 커스텀 디자인 시스템을 운영하기 시작하면 한계가 명확하다. `Overlay` 기반으로 직접 만들면 위치, 애니메이션, 스타일을 완전히 제어할 수 있고, `Scaffold` 의존성도 사라진다.

Apple HIG 시스템 색상은 `Colors.green` 같은 Material 색상과 다르다. 네이티브 느낌을 살리려면 공식 hex 값을 직접 쓰고, light/dark 모드별로 다른 값을 적용해야 한다. `CupertinoIcons`를 쓰면 아이콘에서도 iOS 느낌이 확 살아난다.

`BackdropFilter`는 비용이 크지만, `ClipRRect`로 영역을 제한하고 중첩을 피하면 토스트 수준에서는 성능 문제가 없다. Glass 디자인 시스템을 확장할 때는 `BackdropGroup` 같은 최적화 기법을 미리 알아두는 게 좋다.
