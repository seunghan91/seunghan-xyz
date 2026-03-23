---
title: "Flutter 앱 다크 모드 전수 점검 — 하드코딩 색상 잡아내기"
date: 2026-03-09
draft: true
tags: ["Flutter", "DarkMode", "ThemeData", "ColorScheme", "UI"]
description: "Flutter 앱의 다크 모드를 전수 점검하면서 발견한 하드코딩 색상 패턴과 theme-adaptive 코드로 바꾸는 방법을 정리한다."
---

Flutter 앱에 다크 모드를 지원하도록 `ThemeData.dark()`를 붙여도, 코드 곳곳에 **하드코딩된 색상**이 남아 있으면 다크 모드에서 화면이 깨진다. 이번에 앱 전 화면을 점검하면서 패턴을 정리했다.

---

## 왜 이 문제가 생기는가

Flutter의 테마 시스템은 `ThemeData`와 `ColorScheme`을 통해 앱 전체에 일관된 색상을 적용하는 구조다. `MaterialApp`에 `theme`과 `darkTheme`을 각각 설정하면, 시스템 밝기 설정에 따라 Flutter가 자동으로 올바른 테마를 선택한다.

문제는 개발 초기에 빠른 구현을 위해 정적 색상 클래스(`AppColors`)를 만들고, 위젯 곳곳에서 그 값을 직접 참조하는 습관에서 비롯된다. 라이트 모드에서는 정상 동작하지만, 나중에 `ThemeData.dark()`를 추가해도 이미 하드코딩된 참조들은 테마 전환을 전혀 반영하지 않는다.

결과적으로 다크 모드를 켜면 배경만 어두워지고, 배너·카드·칩·구분선은 여전히 밝은 라이트 색상으로 남아 화면이 얼룩덜룩해진다. 심한 경우 흰 배경 위에 흰 텍스트가 겹쳐 아무것도 보이지 않는 상황도 발생한다.

---

## 문제의 근원: 정적 색상 클래스

프로젝트에는 흔히 이런 구조가 있다.

```dart
class AppColors {
  static const background = Color(0xFFF8FAFC);    // 라이트 전용
  static const surface    = Color(0xFFFFFFFF);    // 라이트 전용
  static const textSecondary = Color(0xFF64748B); // 슬레이트-500
  static const surfaceMuted  = Color(0xFFF1F5F9); // 라이트 회색
  static const primaryLight  = Color(0xFFEFF6FF); // 라이트 파란색
  static const border        = Color(0xFFCBD5E1); // 라이트 경계
  static const divider       = Color(0xFFE2E8F0); // 라이트 구분선
  ...
}
```

`ThemeData.dark()`에서 `scaffoldBackgroundColor`나 `colorScheme.surface`를 올바르게 설정해도, 위 색상들을 **위젯에서 직접 참조**하면 다크 모드에서 밝게 튀어나온다.

이 클래스 자체가 나쁜 것은 아니다. 라이트 전용 상수로 존재하는 건 괜찮다. 문제는 `Theme.of(context)`를 통하지 않고 위젯 트리 어디서나 직접 가져다 쓰는 방식이다. `AppColors.surfaceMuted`는 항상 `0xFFF1F5F9`이고, 다크 모드가 켜졌는지 여부를 절대 알지 못한다.

---

## 발견된 패턴과 수정법

### 1. 이미지 에러 플레이스홀더 배경

이미지 로드 실패 시 보여주는 컨테이너 배경에 밝은 회색을 직접 지정하면, 다크 모드에서 눈부신 밝은 사각형이 나타난다.

```dart
// ❌ 다크 모드에서 눈부신 밝은 회색
errorBuilder: (_, __, ___) => Container(
  color: AppColors.surfaceMuted,  // 0xFFF1F5F9
  child: Icon(Icons.image_not_supported),
),

// ✅ colorScheme 기반
errorBuilder: (_, __, ___) => Container(
  color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.08),
  child: Icon(Icons.image_not_supported),
),
```

`onSurface.withValues(alpha: 0.08)`는 라이트 모드에서 `0x14000000`(거의 투명한 검정), 다크 모드에서 `0x14FFFFFF`(거의 투명한 흰색)로 자동 계산된다. 두 모드 모두에서 배경과 자연스럽게 어우러지는 미묘한 회색빛을 낸다.

### 2. 카테고리 뱃지/칩 배경색

카테고리별로 `bgColor`가 파스텔로 고정되어 있을 때, 다크 모드에서도 밝은 배경이 그대로 노출된다. 예를 들어 "음식" 카테고리의 배경이 `0xFFFFF3CD`(연한 노란색)이라면, 다크 화면에서 그 칩만 눈에 띄게 밝다.

```dart
// ❌ 라이트 파스텔 그대로
decoration: BoxDecoration(color: category.bgColor),

// ✅ brightness 분기
final isDark = Theme.of(context).brightness == Brightness.dark;
decoration: BoxDecoration(
  color: isDark
      ? category.color.withValues(alpha: 0.18)  // 반투명 색조
      : category.bgColor,
),
```

다크 모드에서는 파스텔 배경 대신 카테고리의 원색(`category.color`)을 낮은 불투명도로 사용한다. 색상 정체성은 유지하면서 배경과 조화롭게 어우러진다.

### 3. 정보 배너 / 팁 컨테이너 배경

"이것을 알고 계셨나요?" 같은 정보성 배너에 `AppColors.primaryLight`(연한 파란색)를 직접 쓰면 다크 모드에서 형광등처럼 보인다.

```dart
// ❌ 0xFFEFF6FF — 다크 모드에서 형광등처럼 밝음
color: AppColors.primaryLight,

// ✅ primary 색상에서 알파값 빼기
color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
```

이 패턴은 앱의 주 브랜드 색상을 기준으로 배너 배경을 만들기 때문에, 테마가 바뀌어도 브랜드 일관성이 유지된다.

### 4. 바텀시트 드래그 핸들

```dart
// ❌ 라이트 경계색 고정
color: AppColors.border,  // 0xFFCBD5E1

// ✅
color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.18),
```

드래그 핸들은 배경보다 살짝 밝거나 어두운 정도면 충분하다. `onSurface`에 낮은 투명도를 적용하면 두 모드 모두에서 자연스러운 핸들이 만들어진다.

### 5. ThemeData 내부의 하드코딩

`_baseTheme(ColorScheme colorScheme)` 같이 공통 테마를 만들 때도 하드코딩이 숨어있다. 이 경우는 특히 위험한데, `ThemeData` 내부이므로 "테마는 잘 설정했다"고 착각하기 쉽다.

```dart
// ❌ dividerTheme — 라이트 색 고정
dividerTheme: const DividerThemeData(color: AppColors.divider),

// ✅ brightness 분기
dividerTheme: DividerThemeData(
  color: colorScheme.brightness == Brightness.dark
      ? AppColors.darkDivider
      : AppColors.divider,
),

// ❌ chip 테두리 고정
side: BorderSide(color: AppColors.divider.withValues(alpha: 0.7)),

// ✅
side: BorderSide(
  color: colorScheme.brightness == Brightness.dark
      ? AppColors.darkDivider.withValues(alpha: 0.7)
      : AppColors.divider.withValues(alpha: 0.7),
),

// ❌ hintStyle 색 고정
hintStyle: const TextStyle(color: AppColors.textTertiary),

// ✅ colorScheme 기반 불투명도
hintStyle: TextStyle(
  color: colorScheme.onSurface.withValues(alpha: 0.38),
),
```

`ThemeData` 내부에서는 `Theme.of(context)`를 쓸 수 없으므로, 인자로 받은 `colorScheme`의 `brightness`로 분기한다.

---

## 디버깅 방법

다크 모드 문제를 빠르게 찾으려면 다음 순서로 접근한다.

**1단계: grep으로 하드코딩 참조 전수 검색**

```bash
# 하드코딩 색상 직접 참조 찾기
grep -rn "AppColors\." lib/ | grep "color:"

# Color( 직접 사용 찾기
grep -rn "Color(0x" lib/ --include="*.dart"
```

**2단계: 에뮬레이터에서 다크 모드 토글**

Android 에뮬레이터의 빠른 설정 패널이나 iOS 시뮬레이터의 `Shift+Cmd+A`로 다크 모드를 빠르게 전환하면서 화면을 스캔한다.

**3단계: Flutter DevTools의 Widget Inspector 활용**

문제가 되는 위젯을 Widget Inspector에서 선택하면 `color` 속성에 지정된 값을 직접 확인할 수 있다.

**4단계: 밝기 오버라이드로 특정 화면 강제 테스트**

```dart
// 특정 화면만 강제로 다크 모드 테스트
Theme(
  data: Theme.of(context).copyWith(
    brightness: Brightness.dark,
  ),
  child: YourScreen(),
)
```

---

## 점검 체크리스트

전수 점검 시 이 패턴들을 검색하면 빠르다.

```bash
# 하드코딩 색상 직접 참조 찾기
grep -rn "AppColors\." lib/ | grep "color:"
```

| 체크 항목 | 위험 패턴 | 대체 방법 |
|-----------|-----------|-----------|
| 플레이스홀더 배경 | `color: AppColors.surfaceMuted` | `onSurface.withValues(alpha: 0.08)` |
| 뱃지/칩 배경 | `category.bgColor` 직접 | brightness 분기 |
| 배너 배경 | `AppColors.primaryLight` | `primary.withValues(alpha: 0.10)` |
| 구분선 색 | `AppColors.divider` (ThemeData 내부) | colorScheme brightness 분기 |
| hint 텍스트 | `TextStyle(color: AppColors.textTertiary)` | `onSurface.withValues(alpha: 0.38)` |
| 드래그 핸들 | `AppColors.border` | `onSurface.withValues(alpha: 0.18)` |

---

## 안전한 기준

- **배경/컨테이너 색**: 반드시 `colorScheme.surface`, `colorScheme.onSurface.withValues(alpha: ...)` 사용
- **텍스트 색**: `Theme.of(context).textTheme.*` 스타일 사용 또는 `colorScheme.onSurface` 기반
- **구분선/테두리**: `ThemeData` 내에서 brightness 분기 처리
- **카테고리/시맨틱 색**: 다크 모드에서는 `color.withValues(alpha: 0.15~0.20)` 패턴이 자연스럽다

이 기준만 지켜도 `ThemeData.dark()`를 켰을 때 화면이 밝게 튀는 문제는 대부분 잡힌다.

---

## 예방: 신규 코드에서 하드코딩 막기

사후 수정보다 처음부터 막는 편이 낫다.

**린트 규칙 활용**: `analysis_options.yaml`에 커스텀 린트를 추가하거나, 코드 리뷰에서 `AppColors.*`를 `color:` 속성에 직접 넣는 패턴을 차단하는 규칙을 팀 내 합의한다.

**Extension 메서드로 추상화**: 자주 쓰는 패턴은 `BuildContext` extension으로 감싸면 실수를 줄일 수 있다.

```dart
extension ThemeExtension on BuildContext {
  Color get subtleBackground =>
      Theme.of(this).colorScheme.onSurface.withValues(alpha: 0.08);

  Color get dividerColor =>
      Theme.of(this).colorScheme.onSurface.withValues(alpha: 0.12);

  bool get isDark =>
      Theme.of(this).brightness == Brightness.dark;
}
```

그러면 위젯에서 `context.subtleBackground`처럼 쓸 수 있고, 내부 구현은 항상 `colorScheme` 기반이 보장된다.

**ThemeExtension 활용**: Flutter 3.x부터 지원하는 `ThemeExtension`을 사용하면 커스텀 색상도 테마 시스템 안에 포함시킬 수 있다.

```dart
@immutable
class AppThemeExtension extends ThemeExtension<AppThemeExtension> {
  final Color categoryChipBackground;
  final Color bannerBackground;

  const AppThemeExtension({
    required this.categoryChipBackground,
    required this.bannerBackground,
  });

  @override
  AppThemeExtension copyWith({...}) => ...;

  @override
  AppThemeExtension lerp(AppThemeExtension? other, double t) => ...;
}

// 라이트 테마
ThemeData.light().copyWith(
  extensions: [
    AppThemeExtension(
      categoryChipBackground: AppColors.primaryLight,
      bannerBackground: AppColors.primaryLight,
    ),
  ],
)

// 다크 테마
ThemeData.dark().copyWith(
  extensions: [
    AppThemeExtension(
      categoryChipBackground: AppColors.primary.withValues(alpha: 0.18),
      bannerBackground: AppColors.primary.withValues(alpha: 0.10),
    ),
  ],
)
```

위젯에서는 `Theme.of(context).extension<AppThemeExtension>()!.bannerBackground`로 접근하면, 다크/라이트 여부에 따라 올바른 색이 자동으로 선택된다.

---

## Key Takeaways

- `ThemeData.dark()`를 추가하는 것만으로는 충분하지 않다. 위젯이 `colorScheme`을 통해 색상을 조회해야만 테마 전환이 실제로 작동한다.
- 정적 색상 클래스(`AppColors`)는 그 자체로 나쁘지 않지만, 위젯에서 직접 참조하는 순간 다크 모드 적응력을 잃는다.
- 알파값 기반 패턴(`onSurface.withValues(alpha: ...)`)은 모드별 별도 색상 없이도 두 테마에서 자연스럽게 동작하는 가장 간단한 해법이다.
- `ThemeData` 내부에도 하드코딩이 숨어있을 수 있다. 공통 테마 함수를 만들 때도 반드시 `colorScheme.brightness`로 분기해야 한다.
- `ThemeExtension`을 활용하면 커스텀 색상도 테마 시스템 안에서 완전히 관리할 수 있어, 장기적으로 가장 확장성 있는 구조다.
- grep 한 줄(`grep -rn "AppColors\." lib/ | grep "color:"`)로 문제 후보를 빠르게 전수 검색할 수 있다.
