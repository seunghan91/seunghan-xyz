---
title: "Flutter UI Full Audit — GlassAppBar TabBar Overflow and Colors.white Light Mode Bug"
date: 2025-09-24
draft: false
tags: ["Flutter", "UI", "GlassAppBar", "TabBar", "overflow", "Dark Mode", "Light Mode"]
description: "Full audit of bottom overflow and Colors.white text bugs across all app screens. The preferredSize mechanism and why white text disappears in light mode."
cover:
  image: "/images/og/flutter-glassappbar-tabbar-overflow-colors-white-lightmode.png"
  alt: "Flutter Glassappbar Tabbar Overflow Colors White Lightmode"
  hidden: true
---


When you build a Flutter app long enough, there are two bugs you inevitably encounter at least once.

One is the `bottom overflowed by N pixels` error, the other is text becoming invisible against the background in light mode.

Both have simple causes, but until you do a full audit of all screens, it's easy to just think "something's off on a few screens." It wasn't until I swept through all 50 pages of the app that the pattern became clear.

---

## The Real Cause of GlassAppBar + TabBar Overflow

I was using a custom `GlassAppBar`. Attaching `bottom: TabBar(...)` creates tabs below the AppBar.

```dart
GlassAppBar(
  title: 'Monitoring',
  bottom: TabBar(
    tabs: [
      Tab(icon: Icon(Icons.list), text: 'List'),
      Tab(icon: Icon(Icons.bar_chart), text: 'Status'),
    ],
  ),
)
```

This produced a `bottom overflowed` error on only certain screens. TabBars on other screens were fine.

The difference was in GlassAppBar's internal `preferredSize` implementation.

```dart
class GlassAppBar extends StatelessWidget implements PreferredSizeWidget {
  final double bottomHeight;

  const GlassAppBar({
    this.bottomHeight = 0,  // default is 0
    ...
  });

  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + bottomHeight);
}
```

`preferredSize` is a contract where the Scaffold tells the AppBar "I'll give you this much space." When the actually rendered height differs, it overflows.

**Required bottomHeight by TabBar type:**
- Text-only tabs (Tab(text: ...)): **48px**
- Icon+text tabs (Tab(icon: ..., text: ...)): **80px** (icon 24 + text + padding)

```dart
GlassAppBar(
  title: 'Monitoring',
  bottomHeight: 80,  // icon+text tabs
  bottom: TabBar(...),
)
```

Without specifying this, `preferredSize` is set to only `kToolbarHeight` (56px), but the actual rendering is taller, causing overflow.

---

## When There's a TabBar, Fix ListView Padding Too

When a TabBar is attached to the AppBar, the actual starting position of the body changes too. This is especially true when using `extendBodyBehindAppBar: true`.

The existing code had hardcoded values like this.

```dart
ListView(
  padding: const EdgeInsets.fromLTRB(16, 100, 16, 24),
  // top: 100 = roughly the AppBar height I guess...
```

This works for now but breaks when TabBar height changes or the device's top safe area differs.

The right approach is to calculate based on MediaQuery.

```dart
ListView(
  padding: EdgeInsets.fromLTRB(
    16,
    MediaQuery.paddingOf(context).top + kToolbarHeight + 80, // statusBar + toolbar + tabBar
    16,
    24,
  ),
```

---

## Colors.white Text — Disappearing in Light Mode Bug

A pattern that frequently occurs when developing only in dark mode.

```dart
Text(
  document.name,
  style: const TextStyle(color: Colors.white),
)
```

Since the dark mode background is a dark color like `#1A1A2E`, white text is clearly visible. But switching to light mode makes the background close to white, and white text completely disappears.

The fix is simple. Use `colors.text` created via `ThemeExtension`.

```dart
final colors = context.glassColors;

Text(
  document.name,
  style: TextStyle(color: colors.text),  // dark: white, light: dark color auto-switch
)
```

In `GlassColors`, the `text` color is defined like this.

```dart
// Dark mode
static const GlassColors dark = GlassColors(
  text: Color(0xFFFFFFFF),  // white
  ...
);

// Light mode
static const GlassColors light = GlassColors(
  text: Color(0xFF1A1A2E),  // dark navy
  ...
);
```

Once set up, the appropriate color is automatically applied regardless of mode.

---

## Some Colors.white Should Stay As-Is

During the full audit, it was important to distinguish that not every `Colors.white` should be fixed.

**Should fix -- text on widgets with transparent/white backgrounds:**
```dart
// On GlassCard
Text(title, style: const TextStyle(color: Colors.white))  // wrong

// AlertDialog title
Text('Delete', style: const TextStyle(color: Colors.white))  // wrong
```

**Should keep -- on dark-colored backgrounds:**
```dart
// Icon on gradient button
Icon(Icons.send, color: Colors.white)  // correct

// Number on red badge background
Text('$count', style: TextStyle(color: Colors.white))  // correct (on colors.error background)

// Initial on circular avatar background
Text(name[0], style: TextStyle(color: Colors.white))  // correct (on accent gradient background)
```

The judgment criteria is simple. **Check the parent Container's color/gradient.** If the background is explicitly set to a dark color in code, keep `Colors.white`. If it's a theme-based background like `GlassCard`, `AlertDialog`, or `colors.surface`, replace with `colors.text`.

---

## How the Full Audit Was Done

50 files is too many to check manually, so I used grep to identify patterns first.

```bash
# Find files with TabBar
grep -rn "bottom: TabBar" lib/ --include="*.dart"

# List files with Colors.white text
grep -rn "color: Colors\.white" lib/ --include="*.dart"
```

Then I actually read the files to check "what background is this `Colors.white` sitting on."

The TabBar overflow turned out to be an actual bug in only one file; the rest were all on dark backgrounds like `GlassDecoration.button` and were fine. With many false alarms, there was no choice but to verify each one individually.

---

## Key Checklist

When building a custom AppBar + TabBar:

- [ ] Does `preferredSize` include the TabBar height?
- [ ] +48 for text-only tabs, +80 for icon+text tabs
- [ ] Does the body's ListView/Column top padding reflect AppBar + TabBar height?

When using `Colors.white` text:

- [ ] Is the parent's background color explicitly set to a dark color in code?
- [ ] If not, replace with `colors.text`
- [ ] Don't forget to remove `const` from `const TextStyle(color: Colors.white)`
