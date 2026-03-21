---
title: "Hotwire Native WebView Debugging Collection — 8 Common Issues When Wrapping Rails WebView in Native Apps"
date: 2025-11-25
draft: false
tags: ["Rails", "Hotwire", "Turbo Native", "iOS", "Android", "WebView", "WKWebView"]
description: "Top 8 UX bugs that occur in WebView when building iOS/Android apps with Rails + Hotwire Native, and how to solve them with CSS and path configuration."
cover:
  image: "/images/og/hotwire-native-webview-8-fixes.png"
  alt: "Hotwire Native Webview 8 Fixes"
  hidden: true
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---


When wrapping a Rails app with Hotwire Native (Turbo Native) to build iOS/Android native apps, there are quite a few things that work fine in the browser but behave strangely in WebView. Here are the issues encountered during actual development and the fixes applied, all in one place.

Most can be resolved with a few lines of CSS or one line in the path configuration JSON.

---

## 1. Double-Tap Zoom / 300ms Click Delay

### Symptoms

Double-tapping a button quickly zooms the screen. Even a single tap feels slightly delayed (about 300ms).

### Cause

iOS WKWebView holds the first tap event for ~300ms to detect double-tap zoom gestures. With `user-scalable=yes` (viewport default), both pinch zoom and double-tap zoom are active.

### Fix

```html
<!-- Viewport meta tag in layout HTML -->
<meta name="viewport"
  content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
```

```css
html, body {
  touch-action: manipulation; /* Disable double-tap zoom gesture -> instant tap response */
}
```

`touch-action: manipulation` allows scrolling and pinch zoom but disables double-tap zoom. Combined with `user-scalable=no`, it is fully blocked.

---

## 2. iOS Rubber-Band Scroll / Pull-to-Refresh Conflict

### Symptoms

Pulling up from the top of the page causes the entire screen to bounce, or unintentionally triggers Hotwire Native's pull-to-refresh.

### Cause

iOS's default rubber-band scroll behavior propagates to layers outside the WebView. Hotwire Native attaches a Pull-to-Refresh gesture recognizer on top of the WebView, and the two layers conflict.

### Fix

```css
html, body {
  overscroll-behavior-y: contain; /* Block scroll chain within WebView */
}
```

`contain` consumes scrolling only within the current scroll container without propagating outside. For cases like modal pages where Pull-to-Refresh itself is unnecessary, disable it entirely in the path configuration (see #7).

---

## 3. Tap Highlight Overlay

### Symptoms

Tapping a link or button flashes a blue semi-transparent rectangle overlay. It looks natural in a browser but awkward inside a native app.

### Cause

WebKit draws default tap feedback on focusable elements. The color varies by browser, but blue is the default for iOS Safari / WKWebView.

### Fix

```css
* {
  -webkit-tap-highlight-color: transparent;
}
```

Set transparent globally, and for elements that need actual tap feedback, use `:active` styles separately.

---

## 4. Text Selection During Drag Scrolling

### Symptoms

Holding your finger down while scrolling selects text and the iOS magnifier appears.

### Cause

WebView allows text selection by default. When dragging with a finger to scroll, the browser sometimes interprets it as text drag selection.

### Fix

```css
/* Global: prevent selection */
body {
  -webkit-user-select: none;
  user-select: none;
}

/* Re-enable selection for input fields only */
input,
textarea,
[contenteditable] {
  -webkit-user-select: auto;
  user-select: auto;
}
```

If input fields are also blocked, text copy/paste becomes impossible, so they must be explicitly re-enabled.

---

## 5. Android Auto Font Enlargement on Landscape Rotation

### Symptoms

Rotating the device to landscape suddenly increases the font size. The layout breaks.

### Cause

Android WebView (`WebSettings`) automatically increases `textZoom` in landscape mode for readability. The same issue occurs via CSS.

### Fix (CSS)

```css
html, body {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
```

Setting `WebView.settings.textZoom = 100` on the native Android side is the fundamental fix, but CSS blocks it in most cases.

---

## 6. Horizontal Scroll and iOS Back Gesture Conflict

### Symptoms

Swiping left/right on horizontal scroll areas like category tabs or sliders triggers iOS's Edge Swipe (back gesture) simultaneously, causing page transition.

### Cause

Horizontal scroll events from the WebView bubble up to layers outside WKWebView (native navigation layer).

### Fix

```css
/* Apply to containers with horizontal scrolling */
.overflow-x-auto,
[data-scroll-horizontal] {
  overscroll-behavior-x: contain;
}
```

To apply only for Hotwire Native, narrow the scope under `body.turbo-native`.

```css
.turbo-native .overflow-x-auto {
  overscroll-behavior-x: contain;
}
```

---

## 7. Pull-to-Refresh Conflict in Modals

### Symptoms

Swiping down on an iOS modal sheet triggers both the modal dismiss gesture and pull-to-refresh simultaneously.

### Cause

Hotwire Native attaches Pull-to-Refresh globally to the WebView. The iOS sheet dismiss (swipe down) shares the same gesture direction.

### Fix (path configuration)

```json
{
  "rules": [
    {
      "patterns": ["/sign_in", "/sign_up", "/verify"],
      "properties": {
        "context": "modal",
        "presentation": "push",
        "pull_to_refresh_enabled": false
      }
    },
    {
      "patterns": ["/settings", "/profile/edit"],
      "properties": {
        "context": "modal",
        "presentation": "push",
        "pull_to_refresh_enabled": false
      }
    }
  ]
}
```

It is safest to explicitly set `pull_to_refresh_enabled: false` on all routes with `context: modal`. If missed, you never know when it will trigger.

---

## 8. Safe Area (Notch / Dynamic Island / Home Indicator)

### Symptoms

Top content is hidden behind the iPhone notch or Dynamic Island. Bottom buttons overlap the home indicator.

### Cause

Without `viewport-fit=cover`, the `env(safe-area-inset-*)` variables compute to 0.

### Fix

```html
<!-- viewport-fit=cover is required -->
<meta name="viewport"
  content="width=device-width,initial-scale=1,viewport-fit=cover">
```

```css
/* Main content area inside Hotwire Native app */
.turbo-native main {
  padding-top: max(1rem, env(safe-area-inset-top));
  padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));
}
```

Using `max()` ensures minimum padding even on devices where safe-area-inset is 0 (devices with a home button).

---

## At a Glance

| # | Problem | Fix | File |
|---|------|----------|------|
| 1 | Double-tap zoom / 300ms delay | `user-scalable=no` + `touch-action: manipulation` | layout HTML + CSS |
| 2 | Rubber-band scroll / PTR conflict | `overscroll-behavior-y: contain` | CSS |
| 3 | Tap highlight | `-webkit-tap-highlight-color: transparent` | CSS |
| 4 | Drag text selection | `user-select: none` (except input fields) | CSS |
| 5 | Android auto font enlargement | `-webkit-text-size-adjust: 100%` | CSS |
| 6 | Horizontal scroll vs. back gesture conflict | `overscroll-behavior-x: contain` | CSS |
| 7 | Modal PTR conflict | `pull_to_refresh_enabled: false` | path configuration |
| 8 | Safe Area | `viewport-fit=cover` + `env(safe-area-inset-*)` | layout HTML + CSS |

---

## Complete CSS in One Block

It is convenient to collect all the above in one file.

```css
/* -- Hotwire Native WebView UX Fixes ----------------------------- */

/* 1. Remove 300ms delay + 2. Prevent rubber-band scroll + 5. Android auto font enlargement */
html, body {
  touch-action: manipulation;
  overscroll-behavior-y: contain;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

/* 3. Remove tap highlight */
* {
  -webkit-tap-highlight-color: transparent;
}

/* 4. Prevent text selection */
body {
  -webkit-user-select: none;
  user-select: none;
}

input, textarea, [contenteditable] {
  -webkit-user-select: auto;
  user-select: auto;
}

/* 6. Isolate horizontal scroll areas */
.turbo-native .overflow-x-auto {
  overscroll-behavior-x: contain;
}

/* 8. Safe Area */
.turbo-native main {
  padding-top: max(1rem, env(safe-area-inset-top));
  padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));
}
```

Covering just these basics noticeably improves the perceived quality of a Hotwire Native WebView.
