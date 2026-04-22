---
title: "Flutter에서 iOS Live Activity 잠금화면 미리보기 만들기 — CustomPainter로 네이티브 위젯 재현"
date: 2026-03-26
draft: false
tags: ["Flutter", "iOS", "Live Activity", "CustomPainter", "UX"]
categories: ["iOS", "Flutter"]
description: "Flutter 설정 화면에서 iOS Live Activity 잠금화면을 미리 보여주는 위젯을 구현한 과정. CustomPainter로 원형 게이지를 그리고, 디스플레이 모드별 실시간 프리뷰를 제공하는 방법을 정리했다."
---

## 왜 Live Activity 미리보기가 필요했나

여행 앱에서 iOS Live Activity를 구현하고 나면, 사용자에게 표시 모드를 선택하게 하는 설정 화면이 필요하다. 일정 모드, 예산 모드, 자동 모드, 결합 모드 — 이렇게 네 가지 옵션이 있는데, 문제는 **이 모드를 바꿨을 때 잠금화면에서 실제로 어떻게 보이는지 사용자가 알 수 없다**는 점이었다.

설정 화면 하단에 Dynamic Island compact 형태의 간단한 미리보기는 있었다. 하지만 사용자가 Live Activity를 가장 많이 보는 곳은 잠금화면이다. 작은 알약 모양 미리보기로는 "이 모드를 선택하면 잠금화면이 이렇게 바뀝니다"를 전달하기 어려웠다.

결론은 명확했다. **iOS 잠금화면 Live Activity UI를 Flutter로 1:1 재현하는 미리보기 위젯**을 만들기로 했다.

---

## iOS Live Activity의 구조부터 파악하기

Flutter에서 재현하려면 원본 구조를 정확히 이해해야 한다. iOS Live Activity는 크게 네 가지 표시 영역이 있다.

| 영역 | 위치 | 특징 |
|------|------|------|
| Lock Screen | 잠금화면 하단 | 가장 넓은 공간, 풀 정보 표시 |
| Dynamic Island Expanded | DI 길게 누름 | 3개 영역(leading, trailing, bottom) |
| Dynamic Island Compact | DI 기본 | 아이콘 + 한 줄 텍스트 |
| Dynamic Island Minimal | DI 축소 | 아이콘만 |

미리보기 대상은 Lock Screen 뷰다. 이 뷰는 SwiftUI의 `ActivityConfiguration` 안에서 첫 번째 클로저로 정의된다.

```swift
ActivityConfiguration(for: TripActivityAttributes.self) { context in
    // Lock Screen View — 여기가 잠금화면에 표시되는 뷰
    LockScreenView(state: context.state)
} dynamicIsland: { context in
    // Dynamic Island 뷰들...
}
```

### Lock Screen 뷰의 구성 요소

기존 SwiftUI 코드에서 잠금화면 뷰는 이런 구조였다:

1. **헤더 영역** — 여행명 + 목적지 + 원형 예산 진행률 게이지
2. **구분선**
3. **다음 일정 섹션** — 장소 아이콘, 일정명, 위치, ETA
4. **예산 섹션** — 카드 아이콘, 오늘 지출, 일일 예산
5. **진행률 바** — 예산 사용 비율
6. **최근 지출** — 가장 최근 결제 내역

핵심은 **displayMode에 따라 섹션 표시가 달라진다**는 것이다.

```
auto / combined → 일정 + 예산 모두 표시
schedule       → 일정만 표시 (예산 숨김)
budget         → 예산만 표시 (일정 숨김)
```

---

## 기존 미리보기의 한계

기존 코드는 `_buildPreviewCard()` 메서드로 Dynamic Island compact 스타일의 간단한 미리보기를 제공했다.

```dart
// 기존 미리보기 — Dynamic Island compact 시뮬레이션
Container(
  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
  decoration: BoxDecoration(
    color: AppColors.grey900,
    borderRadius: BorderRadius.circular(24),  // 알약 형태
  ),
  child: Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(Icons.airplanemode_active, color: AppColors.info, size: 20),
      Column(
        children: [
          Text(_getPreviewPrimaryText()),   // "스시 오마카세" or "32,000원"
          Text(_getPreviewSecondaryText()), // "1시간 후" or "64%"
        ],
      ),
    ],
  ),
)
```

문제점:
- 알약 형태의 compact 뷰는 실제 잠금화면과 전혀 다른 모양이다
- 텍스트 두 줄로는 모드 간 차이를 체감하기 어렵다
- 원형 예산 게이지, 진행률 바, 일정/예산 섹션 같은 핵심 요소가 없다

---

## Flutter로 잠금화면 Live Activity 재현하기

### 전체 컨테이너 설계

iOS 잠금화면 Live Activity는 어두운 배경에 밝은 텍스트로 표시된다. Flutter에서는 `Color(0xFF1C1C1E)` — iOS의 `systemGray6` dark 색상을 배경으로 사용했다.

```dart
Container(
  padding: const EdgeInsets.all(16),
  decoration: BoxDecoration(
    color: const Color(0xFF1C1C1E),  // iOS dark system background
    borderRadius: BorderRadius.circular(16),
  ),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      // 헤더, 일정, 예산 섹션들...
    ],
  ),
)
```

### 모드별 섹션 표시 로직

디스플레이 모드에 따라 어떤 섹션을 보여줄지 결정하는 로직이 핵심이다.

```dart
final showSchedule = _selectedMode != LiveActivityDisplayMode.budget;
final showBudget = _selectedMode != LiveActivityDisplayMode.schedule;
```

`auto`와 `combined`는 둘 다 일정+예산을 보여주고, `schedule`은 일정만, `budget`은 예산만 표시한다. 이렇게 두 개의 boolean 값만으로 깔끔하게 분기할 수 있다.

### 실제 여행 데이터 혼합

미리보기에서 가장 효과적인 건 **실제 데이터와 샘플 데이터를 섞는 것**이다. 여행명과 목적지는 실제 데이터를 사용하고, 일정과 예산은 샘플 데이터를 쓴다.

```dart
final tripName = widget.trip.name.isNotEmpty ? widget.trip.name : '오사카 여행';
final destination = widget.trip.destination?.isNotEmpty == true
    ? widget.trip.destination!
    : '일본 오사카';
```

사용자가 "도쿄 여행"이라는 이름의 여행을 보고 있다면, 미리보기에도 "도쿄 여행"이 뜬다. "내 여행에서 이렇게 보이겠구나"라는 감각을 바로 줄 수 있다.

---

## CustomPainter로 원형 예산 게이지 구현

iOS Live Activity에서 가장 눈에 띄는 UI 요소는 오른쪽 상단의 원형 예산 진행률 게이지다. SwiftUI에서는 `Circle().trim()` + `.stroke()`로 간단하게 만들 수 있지만, Flutter에는 동일한 위젯이 없다.

### SwiftUI 원본 코드

```swift
ZStack {
    Circle()
        .stroke(Color.gray.opacity(0.3), lineWidth: 4)
    Circle()
        .trim(from: 0, to: min(CGFloat(state.budgetProgress ?? 0), 1.0))
        .stroke(
            state.isOverBudget ? Color.red : Color.blue,
            style: StrokeStyle(lineWidth: 4, lineCap: .round)
        )
        .rotationEffect(.degrees(-90))
    Text("\(state.budgetProgressPercent)%")
        .font(.caption2)
        .fontWeight(.bold)
}
.frame(width: 44, height: 44)
```

### Flutter CustomPainter로 변환

Flutter에서는 `CustomPainter`를 사용해 Canvas에 직접 그려야 한다.

```dart
class _BudgetCirclePainter extends CustomPainter {
  final double progress;

  _BudgetCirclePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 2;

    // 배경 원 (회색 트랙)
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = Colors.white12
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3.5,
    );

    // 진행률 호 (12시 방향부터 시계 방향)
    final sweepAngle = 2 * 3.14159 * progress.clamp(0.0, 1.0);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -3.14159 / 2,   // 시작점: 12시 방향 (-π/2)
      sweepAngle,       // 호 각도: 2π * progress
      false,
      Paint()
        ..color = progress > 1.0 ? Colors.red : const Color(0xFF0A84FF)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3.5
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(_BudgetCirclePainter oldDelegate) =>
      oldDelegate.progress != progress;
}
```

핵심 포인트를 정리하면:

| 요소 | SwiftUI | Flutter CustomPainter |
|------|---------|----------------------|
| 배경 원 | `Circle().stroke()` | `canvas.drawCircle()` |
| 진행률 호 | `Circle().trim(from:to:)` | `canvas.drawArc()` |
| 시작점 | `.rotationEffect(.degrees(-90))` | 시작각 `-π/2` |
| 둥근 끝 | `StrokeStyle(lineCap: .round)` | `StrokeCap.round` |
| 색상 분기 | 삼항 연산자 | 동일 |

`drawArc`의 시작 각도가 `-π/2`인 이유는 Canvas의 기본 0도가 3시 방향(오른쪽)이기 때문이다. 12시 방향에서 시작하려면 반시계 방향으로 90도, 즉 `-π/2` 라디안을 지정한다.

### 위젯에 통합

```dart
SizedBox(
  width: 40,
  height: 40,
  child: CustomPaint(
    painter: _BudgetCirclePainter(progress: 0.64),
    child: const Center(
      child: Text(
        '64%',
        style: TextStyle(
          color: Colors.white,
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
    ),
  ),
)
```

`CustomPaint`의 `child` 속성에 `Text`를 넣으면 Canvas 위에 텍스트가 렌더링된다. 별도의 `Stack`이 필요 없다.

---

## 일정 섹션과 예산 섹션 구현

### 일정 섹션

iOS 위젯에서 일정 섹션은 주황색 핀 아이콘 + 일정명 + 위치 + ETA로 구성된다.

```dart
if (showSchedule) ...[
  Row(
    children: [
      // 주황색 배경의 위치 아이콘
      Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: Colors.orange.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(6),
        ),
        child: const Icon(Icons.location_on,
            color: Colors.orange, size: 18),
      ),
      const SizedBox(width: 10),
      // 일정 정보
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('다음 일정',
              style: TextStyle(color: Colors.white38, fontSize: 11)),
            Text('스시 오마카세',
              style: TextStyle(color: Colors.white, fontSize: 14,
                fontWeight: FontWeight.w500)),
            Text('도톤보리',
              style: TextStyle(color: Colors.white38, fontSize: 11)),
          ],
        ),
      ),
      // ETA
      Text('1시간 후',
        style: TextStyle(color: Color(0xFF0A84FF), fontSize: 14,
          fontWeight: FontWeight.w600)),
    ],
  ),
]
```

iOS에서 `systemBlue`는 라이트 모드에서 `#007AFF`, 다크 모드에서 `#0A84FF`다. 잠금화면 Live Activity는 항상 다크 배경이므로 `Color(0xFF0A84FF)`를 사용했다.

### 예산 섹션

예산 섹션은 녹색 카드 아이콘 + 오늘 지출 + 일일 예산 + 진행률 바 + 최근 지출로 구성된다.

```dart
if (showBudget) ...[
  Row(
    children: [
      Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: Colors.green.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(6),
        ),
        child: const Icon(Icons.credit_card,
            color: Colors.green, size: 18),
      ),
      const SizedBox(width: 10),
      Expanded(/* 오늘 지출 */),
      Column(/* 일일 예산 */),
    ],
  ),
  // 진행률 바
  ClipRRect(
    borderRadius: BorderRadius.circular(2),
    child: LinearProgressIndicator(
      value: 0.64,
      backgroundColor: Colors.white12,
      valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF0A84FF)),
      minHeight: 4,
    ),
  ),
  // 최근 지출
  Text('최근: 라멘 · 1,200엔',
    style: TextStyle(color: Colors.white38, fontSize: 11)),
]
```

Flutter의 `LinearProgressIndicator`를 `ClipRRect`로 감싸서 iOS의 `ProgressView`와 비슷한 둥근 모서리를 적용했다.

---

## 실시간 모드 전환이 동작하는 원리

모드 선택 시 `setState`가 호출되면서 `_selectedMode`가 바뀌고, `_buildPreviewCard()`가 다시 빌드된다.

```dart
Future<void> _selectMode(LiveActivityDisplayMode mode) async {
  if (_selectedMode == mode) return;

  setState(() {
    _selectedMode = mode;  // 이 변경이 미리보기를 다시 그린다
    _isUpdating = true;
  });

  // 서버 업데이트 + 로컬 Live Activity 업데이트...
}
```

`_buildPreviewCard()` 안에서 `showSchedule`과 `showBudget`이 `_selectedMode`에 의존하므로, 모드를 바꿀 때마다 미리보기의 섹션이 즉시 변한다. 별도의 애니메이션 없이도 자연스럽다.

---

## SwiftUI ↔ Flutter UI 변환 시 알아두면 좋은 것들

이번 작업을 하면서 SwiftUI와 Flutter 사이의 UI 변환 패턴이 정리됐다.

### 색상 시스템

| iOS (다크 모드) | SwiftUI | Flutter |
|----------------|---------|---------|
| 시스템 배경 | `.clear` / 자동 | `Color(0xFF1C1C1E)` 명시 |
| 시스템 블루 | `.blue` → `#0A84FF` | `Color(0xFF0A84FF)` |
| 보조 텍스트 | `.secondary` | `Colors.white38` ~ `Colors.white54` |
| 구분선 | `Divider()` | `Divider(color: Colors.white12)` |

SwiftUI는 다크 모드에서 색상이 자동으로 적응하지만, Flutter는 명시적으로 지정해야 한다. 특히 잠금화면은 항상 다크 배경이므로 `.secondary`에 대응하는 `Colors.white38`을 직접 써야 한다.

### 레이아웃 대응

| SwiftUI | Flutter |
|---------|---------|
| `VStack(alignment: .leading, spacing: 12)` | `Column(crossAxisAlignment: CrossAxisAlignment.start)` + `SizedBox(height: 12)` |
| `HStack { ... Spacer() ... }` | `Row(children: [Expanded(...), ...])` |
| `Circle().trim().stroke()` | `CustomPainter` + `drawArc` |
| `ProgressView(value:)` | `LinearProgressIndicator(value:)` |
| `.padding()` | `Padding(padding: EdgeInsets.all(16))` |

SwiftUI의 `Spacer()`는 Flutter에서 `Expanded` 또는 `Spacer()`로 대응된다. 그런데 `Row` 안에서 한쪽을 밀어내고 싶을 때는 `Expanded`로 감싸는 게 더 자연스럽다.

---

## ActivityKit의 displayMode 설계 패턴

Live Activity에서 displayMode를 설계할 때 참고할 만한 패턴이 있다.

### 데이터 모델 (Swift)

```swift
struct TripActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var displayMode: String?  // "auto" | "schedule" | "budget" | "combined"
        var tripName: String
        var nextScheduleName: String?
        var todaySpent: String
        var budgetProgress: Double?
        // ...
    }
}
```

`displayMode`를 ContentState에 포함시킨 이유는, **서버 푸시로 업데이트할 때 모드도 함께 보낼 수 있기 때문**이다. 사용자가 앱에서 모드를 바꾸면 서버에 저장하고, 서버가 푸시할 때 해당 모드를 반영한다.

### 모드 enum 확장 (Swift)

```swift
extension TripActivityAttributes.ContentState {
    var displayModeEnum: DisplayMode {
        switch displayMode {
        case "schedule": return .schedule
        case "budget": return .budget
        case "combined": return .combined
        default: return .auto
        }
    }
}
```

### Flutter 측 enum

```dart
enum LiveActivityDisplayMode {
  auto, schedule, budget, combined;

  String get value => name;
  String get displayName => switch (this) {
    auto => '자동',
    schedule => '일정 중심',
    budget => '예산 중심',
    combined => '결합',
  };
}
```

Swift와 Flutter 양쪽에서 같은 문자열 값(`"auto"`, `"schedule"` 등)을 사용하는 게 중요하다. Method Channel을 통해 데이터가 오갈 때 변환 실수를 방지할 수 있다.

---

## 미리보기 vs 실제 iOS 위젯 — 주의할 점

Flutter 미리보기는 어디까지나 **시뮬레이션**이다. 실제 iOS 위젯과 100% 동일하게 만들 필요는 없고, 몇 가지 차이를 인지하고 있으면 된다.

| 항목 | 실제 iOS | Flutter 미리보기 |
|------|----------|----------------|
| 배경 처리 | `activityBackgroundTint` 자동 | 하드코딩 색상 |
| AOD 대응 | `isLuminanceReduced` 환경 변수 | 미대응 (불필요) |
| 폰트 | SF Pro (시스템 폰트) | 앱 기본 폰트 |
| 모서리 | `ContainerRelativeShape` | `BorderRadius.circular(16)` |
| 인터랙션 | 탭 → 앱 이동 | 없음 (미리보기용) |

Apple의 Human Interface Guidelines에 따르면, Live Activity는 **14pt 표준 마진**을 사용하고, 둥근 모서리는 `ContainerRelativeShape`으로 외곽 모서리와 조화를 이루게 해야 한다. Flutter 미리보기에서는 `16px` 패딩과 `16` 라운드로 근사하게 맞췄다.

---

## `shouldRepaint` 최적화

`CustomPainter`를 쓸 때 흔히 놓치는 부분이 `shouldRepaint`다.

```dart
@override
bool shouldRepaint(_BudgetCirclePainter oldDelegate) =>
    oldDelegate.progress != progress;
```

이 메서드가 `true`를 반환해야만 `paint()`가 다시 호출된다. 무조건 `true`를 반환하면 불필요한 리페인트가 발생한다. 이번 케이스에서는 `progress` 값이 바뀔 때만 다시 그리면 되므로, 값 비교로 최적화했다.

미리보기에서는 고정 값(0.64)을 쓰고 있어서 실제로 리페인트가 발생할 일은 거의 없다. 하지만 나중에 실제 데이터를 바인딩하게 되면 이 최적화가 의미를 갖는다.

---

## 결론

iOS Live Activity 잠금화면을 Flutter로 재현하는 건 생각보다 간단했다. SwiftUI의 `Circle().trim()`이 Flutter에서는 `CustomPainter` + `drawArc`가 되고, `VStack` / `HStack`은 `Column` / `Row`가 된다. 색상만 다크 모드용으로 명시해주면 된다.

핵심은 **설정 화면에서 미리보기를 제공하면 사용자가 모드 선택에 대한 확신을 갖게 된다**는 점이다. "이걸 선택하면 잠금화면이 어떻게 바뀌지?"라는 불확실성을 제거하는 것만으로도 UX가 크게 개선된다.

이전에 작성한 [Flutter 글라스모피즘 디자인 시스템](/posts/flutter-bear-editor-glassmorphism-design/) 글에서도 다뤘지만, 네이티브 플랫폼의 디자인 패턴을 Flutter로 가져올 때는 1:1 복제보다 **핵심 요소의 충실한 재현**이 중요하다. 원형 게이지, 섹션 분리, 색상 체계 — 이 세 가지만 잘 맞추면 사용자는 "실제 잠금화면에서 이렇게 보이겠구나"를 충분히 인식할 수 있다.
