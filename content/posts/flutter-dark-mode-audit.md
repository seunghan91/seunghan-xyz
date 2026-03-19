---
title: "Flutter 앱 다크 모드 전수 점검 — 하드코딩 색상 잡아내기"
date: 2026-03-09
draft: true
tags: ["Flutter", "DarkMode", "ThemeData", "ColorScheme", "UI"]
description: "Flutter 앱의 다크 모드를 전수 점검하면서 발견한 하드코딩 색상 패턴과 theme-adaptive 코드로 바꾸는 방법을 정리한다."
---

Flutter 앱에 다크 모드를 지원하도록 `ThemeData.dark()`를 붙여도, 코드 곳곳에 **하드코딩된 색상**이 남아 있으면 다크 모드에서 화면이 깨진다. 이번에 앱 전 화면을 점검하면서 패턴을 정리했다.

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

---

## 발견된 패턴과 수정법

### 1. 이미지 에러 플레이스홀더 배경

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

### 2. 카테고리 뱃지/칩 배경색

카테고리별로 `bgColor`가 파스텔로 고정되어 있을 때, 다크 모드에서도 밝은 배경이 그대로 노출된다.

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

### 3. 정보 배너 / 팁 컨테이너 배경

```dart
// ❌ 0xFFEFF6FF — 다크 모드에서 형광등처럼 밝음
color: AppColors.primaryLight,

// ✅ primary 색상에서 알파값 빼기
color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
```

### 4. 바텀시트 드래그 핸들

```dart
// ❌ 라이트 경계색 고정
color: AppColors.border,  // 0xFFCBD5E1

// ✅
color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.18),
```

### 5. ThemeData 내부의 하드코딩

`_baseTheme(ColorScheme colorScheme)` 같이 공통 테마를 만들 때도 하드코딩이 숨어있다.

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
