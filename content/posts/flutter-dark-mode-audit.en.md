---
title: "Flutter Dark Mode Audit — Finding Hardcoded Colors"
date: 2026-03-09
draft: true
tags: ["Flutter", "DarkMode", "ThemeData", "ColorScheme", "UI"]
description: "A systematic audit of hardcoded color patterns in Flutter apps that break dark mode, with theme-adaptive replacements for each."
---

Even with a proper `ThemeData.dark()` configuration, hardcoded color references scattered across widgets will make screens look wrong in dark mode. Here's a full audit of the patterns I found and how to fix them.

---

## Root Cause: Static Color Classes

Projects often have a structure like this:

```dart
class AppColors {
  static const background    = Color(0xFFF8FAFC); // light only
  static const surfaceMuted  = Color(0xFFF1F5F9); // light gray
  static const primaryLight  = Color(0xFFEFF6FF); // light blue
  static const border        = Color(0xFFCBD5E1); // light border
  static const divider       = Color(0xFFE2E8F0); // light divider
  ...
}
```

When these are used directly in widgets rather than through `colorScheme`, they ignore dark mode entirely.

---

## Patterns and Fixes

### 1. Image Error Placeholder Background

```dart
// ❌ Blindingly bright in dark mode
errorBuilder: (_, __, ___) => Container(
  color: AppColors.surfaceMuted,
  child: Icon(Icons.image_not_supported),
),

// ✅ colorScheme-based
errorBuilder: (_, __, ___) => Container(
  color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.08),
  child: Icon(Icons.image_not_supported),
),
```

### 2. Category Badge / Chip Background

```dart
// ❌ Light pastels always visible
decoration: BoxDecoration(color: category.bgColor),

// ✅ Brightness-aware
final isDark = Theme.of(context).brightness == Brightness.dark;
decoration: BoxDecoration(
  color: isDark
      ? category.color.withValues(alpha: 0.18)
      : category.bgColor,
),
```

### 3. Info Banner / Tip Container

```dart
// ❌ Solid light blue — glows in dark mode
color: AppColors.primaryLight,

// ✅ Semi-transparent primary
color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
```

### 4. Bottom Sheet Drag Handle

```dart
// ❌ Fixed light border color
color: AppColors.border,

// ✅
color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.18),
```

### 5. Hardcoded Values Inside ThemeData

```dart
// ❌ Divider always uses light color
dividerTheme: const DividerThemeData(color: AppColors.divider),

// ✅
dividerTheme: DividerThemeData(
  color: colorScheme.brightness == Brightness.dark
      ? AppColors.darkDivider
      : AppColors.divider,
),

// ❌ Chip border always light
side: BorderSide(color: AppColors.divider.withValues(alpha: 0.7)),

// ✅
side: BorderSide(
  color: colorScheme.brightness == Brightness.dark
      ? AppColors.darkDivider.withValues(alpha: 0.7)
      : AppColors.divider.withValues(alpha: 0.7),
),

// ❌ Hint text color hardcoded
hintStyle: const TextStyle(color: AppColors.textTertiary),

// ✅
hintStyle: TextStyle(
  color: colorScheme.onSurface.withValues(alpha: 0.38),
),
```

---

## Audit Checklist

```bash
# Quick scan for direct color references
grep -rn "AppColors\." lib/ | grep "color:"
```

| Item | Risky Pattern | Replacement |
|------|---------------|-------------|
| Placeholder background | `AppColors.surfaceMuted` | `onSurface.withValues(alpha: 0.08)` |
| Category badge bg | `category.bgColor` directly | Brightness branch |
| Info banner bg | `AppColors.primaryLight` | `primary.withValues(alpha: 0.10)` |
| Divider color | `AppColors.divider` in ThemeData | `colorScheme.brightness` branch |
| Hint text | `TextStyle(color: AppColors.textTertiary)` | `onSurface.withValues(alpha: 0.38)` |
| Drag handle | `AppColors.border` | `onSurface.withValues(alpha: 0.18)` |

---

## Guidelines

- **Backgrounds / containers**: Use `colorScheme.surface` or `onSurface.withValues(alpha: ...)`
- **Text**: Use `Theme.of(context).textTheme.*` or `colorScheme.onSurface`-based colors
- **Dividers / borders**: Branch on `brightness` inside `ThemeData`
- **Semantic / category colors**: Use `color.withValues(alpha: 0.15~0.20)` in dark mode for a natural tint

Following these rules prevents most "bright flash" issues when dark mode is enabled.
