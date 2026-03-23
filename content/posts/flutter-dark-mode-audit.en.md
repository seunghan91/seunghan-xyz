---
title: "Flutter Dark Mode Audit — Finding Hardcoded Colors"
date: 2026-03-09
draft: true
tags: ["Flutter", "DarkMode", "ThemeData", "ColorScheme", "UI"]
description: "A systematic audit of hardcoded color patterns in Flutter apps that break dark mode, with theme-adaptive replacements for each."
---

Even with a proper `ThemeData.dark()` configuration, hardcoded color references scattered across widgets will make screens look wrong in dark mode. Here's a full audit of the patterns I found and how to fix them.

---

## Why This Problem Exists

Flutter's theming system works through `ThemeData` and `ColorScheme`. When you provide both a `theme` and `darkTheme` to `MaterialApp`, Flutter automatically selects the correct theme based on the system brightness setting. In principle, this is all you need.

The issue comes from a common early-development habit: creating a static color class (`AppColors`) and referencing it directly everywhere in the widget tree. This works fine in light mode. But when you add `ThemeData.dark()` later, those hardcoded references are oblivious to the theme change — they will always return the light-mode value, regardless of what the system brightness is set to.

The result is a patchy dark mode: the scaffold background turns dark, but banners, cards, chips, and dividers stay light. At worst, you get white text on a white background — completely invisible content.

---

## Root Cause: Static Color Classes

Projects often have a structure like this:

```dart
class AppColors {
  static const background    = Color(0xFFF8FAFC); // light only
  static const surface       = Color(0xFFFFFFFF); // light only
  static const textSecondary = Color(0xFF64748B); // slate-500
  static const surfaceMuted  = Color(0xFFF1F5F9); // light gray
  static const primaryLight  = Color(0xFFEFF6FF); // light blue
  static const border        = Color(0xFFCBD5E1); // light border
  static const divider       = Color(0xFFE2E8F0); // light divider
  ...
}
```

When these are used directly in widgets rather than through `colorScheme`, they ignore dark mode entirely.

The class itself is not the problem — having named light-mode constants is fine. The problem is the access pattern: `AppColors.surfaceMuted` is always `0xFFF1F5F9`. It has no idea whether dark mode is active. It cannot adapt.

---

## Patterns and Fixes

### 1. Image Error Placeholder Background

When an image fails to load, showing a container with a hardcoded light-gray background produces a blindingly bright rectangle in dark mode.

```dart
// ❌ Blindingly bright in dark mode
errorBuilder: (_, __, ___) => Container(
  color: AppColors.surfaceMuted,  // 0xFFF1F5F9
  child: Icon(Icons.image_not_supported),
),

// ✅ colorScheme-based
errorBuilder: (_, __, ___) => Container(
  color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.08),
  child: Icon(Icons.image_not_supported),
),
```

`onSurface.withValues(alpha: 0.08)` resolves to a near-transparent black in light mode and a near-transparent white in dark mode. In both cases it produces a subtle, neutral tint that blends naturally with the surface behind it — without any explicit brightness check.

### 2. Category Badge / Chip Background

When category items have fixed pastel background colors (e.g., a "food" chip with `0xFFFFF3CD`), those pastels stick out prominently against a dark background.

```dart
// ❌ Light pastels always visible
decoration: BoxDecoration(color: category.bgColor),

// ✅ Brightness-aware
final isDark = Theme.of(context).brightness == Brightness.dark;
decoration: BoxDecoration(
  color: isDark
      ? category.color.withValues(alpha: 0.18)  // semi-transparent tint
      : category.bgColor,
),
```

In dark mode, the full-opacity pastel is replaced by the category's primary color at low opacity. The color identity is preserved, but the chip no longer competes with the dark background.

### 3. Info Banner / Tip Container

Informational banners with a solid light-blue background (`AppColors.primaryLight`) glow like a fluorescent light in dark mode.

```dart
// ❌ Solid light blue — glows in dark mode
color: AppColors.primaryLight,

// ✅ Semi-transparent primary
color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
```

This approach derives the banner color from the app's primary brand color, so brand consistency is maintained even as the theme changes. At 10% opacity, the result is a subtle tinted highlight rather than a glowing block.

### 4. Bottom Sheet Drag Handle

```dart
// ❌ Fixed light border color
color: AppColors.border,  // 0xFFCBD5E1

// ✅
color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.18),
```

A drag handle just needs to be slightly lighter or darker than the surface behind it. Applying a low-opacity `onSurface` achieves exactly that in both modes, without any explicit brightness branching.

### 5. Hardcoded Values Inside ThemeData

This is the most insidious category. When you write a `_baseTheme(ColorScheme colorScheme)` helper function, it feels like you are doing things correctly — you are inside the theme! But hardcoded color references still break dark mode.

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

Inside `ThemeData`, you cannot call `Theme.of(context)`, so you must branch on the `brightness` property of the `colorScheme` argument passed into the helper function.

---

## Debugging Approach

A structured approach to finding dark mode problems:

**Step 1: grep for hardcoded references**

```bash
# Find direct AppColors references used as color values
grep -rn "AppColors\." lib/ | grep "color:"

# Find inline Color() literals
grep -rn "Color(0x" lib/ --include="*.dart"
```

**Step 2: Toggle dark mode on the emulator**

Use the Quick Settings panel on an Android emulator or `Shift+Cmd+A` on the iOS Simulator to rapidly switch between light and dark while scrolling through every screen. Visual scanning is still the fastest way to catch issues that grep misses (dynamic colors, conditional logic, etc.).

**Step 3: Flutter DevTools — Widget Inspector**

Select the offending widget in Widget Inspector to inspect its rendered `color` value directly. This confirms whether the value is hardcoded or theme-derived.

**Step 4: Force dark mode on a specific screen**

To isolate and test a single screen without changing system settings:

```dart
Theme(
  data: Theme.of(context).copyWith(
    brightness: Brightness.dark,
  ),
  child: YourScreen(),
)
```

This is especially useful for writing golden tests that validate dark mode appearance.

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

---

## Prevention: Stopping Hardcoding in New Code

Fixing problems after the fact is expensive. These approaches prevent them from being introduced in the first place.

**Team conventions and code review**: Agree on a rule that `AppColors.*` should never appear directly as a `color:` argument in a widget. Enforce this in code review. This single rule catches the majority of dark mode regressions before they land.

**BuildContext extensions**: Wrapping common patterns in extension methods reduces the chance of mistakes.

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

Widgets then use `context.subtleBackground` instead of `AppColors.surfaceMuted`, and the implementation is always `colorScheme`-based by construction.

**ThemeExtension for custom semantic colors**: Available since Flutter 3.x, `ThemeExtension` allows custom colors to live inside the theme system rather than outside it.

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

// Light theme
ThemeData.light().copyWith(
  extensions: [
    AppThemeExtension(
      categoryChipBackground: AppColors.primaryLight,
      bannerBackground: AppColors.primaryLight,
    ),
  ],
)

// Dark theme
ThemeData.dark().copyWith(
  extensions: [
    AppThemeExtension(
      categoryChipBackground: AppColors.primary.withValues(alpha: 0.18),
      bannerBackground: AppColors.primary.withValues(alpha: 0.10),
    ),
  ],
)
```

Widgets access the values via `Theme.of(context).extension<AppThemeExtension>()!.bannerBackground`. Flutter selects the correct extension instance based on the active theme, so the widget code itself never needs to branch on brightness.

---

## Key Takeaways

- Adding `ThemeData.dark()` is necessary but not sufficient. Widgets must retrieve colors through `colorScheme` for the theme switch to actually take effect.
- Static color classes (`AppColors`) are not inherently bad, but referencing them directly in widget `color:` properties makes those widgets theme-blind.
- The alpha-value pattern (`onSurface.withValues(alpha: ...)`) is the simplest adaptive solution: it works correctly in both modes without any explicit brightness check.
- Hardcoded colors can hide inside `ThemeData` helper functions. Even code that looks like "proper" theming can silently ignore dark mode.
- `ThemeExtension` is the most scalable long-term architecture: custom semantic colors live inside the theme system and are automatically selected by Flutter.
- A single grep command (`grep -rn "AppColors\." lib/ | grep "color:"`) gives you a complete list of candidates to review in any codebase.
