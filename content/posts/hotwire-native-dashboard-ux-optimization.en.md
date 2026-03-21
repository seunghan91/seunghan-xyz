---
title: "7 Real-World Pitfalls Building a Hotwire Native Mobile App with Rails 8 — CSP, Turbo Conflicts, and Performance"
date: 2026-03-21
draft: false
tags: ["Hotwire Native", "Rails 8", "Turbo", "Stimulus", "WKWebView", "iOS", "mobile app", "hybrid app", "bridge components", "Content Security Policy", "backdrop-filter performance", "Tailwind CSS", "importmap", "37signals", "web-first mobile", "Rails mobile app"]
description: "Practical debugging guide for building hybrid mobile apps with Hotwire Native and Rails 8. From CSP blocking CDN imports, Turbo const/let redeclaration errors, to backdrop-filter blur killing scroll performance with 120 GPU composite layers. Real fixes from a production app."
cover:
  image: ""
  alt: "Hotwire Native Rails 8 Dashboard UX Optimization"
  hidden: true
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

If you're building a mobile app with **Hotwire Native** and **Rails 8**, you'll eventually hit issues that don't show up in development but break things in production — especially on real iOS devices running inside WKWebView.

This post documents 7 real-world pitfalls I encountered while shipping a tournament management app (Turbo + Stimulus + ERB + Tailwind CSS 4) as a Hotwire Native iOS app. Each issue includes the symptom, root cause analysis, fix, and lessons learned.

If you're coming from the **37signals** ecosystem (Basecamp, HEY) or following **Joe Masilotti's** Hotwire Native tutorials, these are the kinds of problems you'll face once your app gets complex enough.

---

## Tech Stack

- **Backend**: Rails 8 + PostgreSQL + ActionCable
- **Frontend**: Hotwire (Turbo + Stimulus) + ERB + Tailwind CSS 4
- **Mobile**: Hotwire Native iOS (WKWebView wrapper)
- **Assets**: importmap-rails with CDN pins
- **Deploy**: Render.com

The dashboard page renders a grid of court cards (courts x rounds), a draggable player list, match listings, and statistics — all in one page. With 5 courts and 8 rounds, that's **40 court cards** rendered simultaneously.

---

## 1. Mobile WebView Horizontal Overflow

### Symptom

On the iOS app (WKWebView), the header buttons overflowed horizontally, creating an unwanted horizontal scroll. Court card contents were also clipped vertically.

Desktop Chrome showed no issues.

### Root Cause

Two compounding problems:

**Buttons without `flex-wrap`**: Four action buttons (`+ Round`, `Players`, `All Matches`, `Settings`) were in a `flex` container with `whitespace-nowrap` but no `flex-wrap`. On mobile screens (<375px), they couldn't fit in one line.

**`aspect-square` on court cards**: Each court card used `aspect-ratio: 1/1`, which in a 3-column mobile grid meant each card was ~110px tall — not enough vertical space for court number, two team names, VS indicator, score, and round label.

### Fix

```html
<!-- Add flex-wrap to button container -->
<div class="flex shrink-0 flex-wrap items-center gap-2">
  <!-- buttons here -->
</div>

<!-- Prevent horizontal overflow on the wrapper -->
<div class="theme-shell flex min-h-screen flex-col overflow-x-hidden">

<!-- Change court card aspect ratio from square to portrait -->
<div class="relative overflow-hidden rounded-xl aspect-[3/4]">
```

### Lessons Learned

- **Always add `overflow-x: hidden` to your root wrapper** in Hotwire Native apps. iOS Safari/WKWebView has bugs where `overflow-x: hidden` on `<body>` or `<html>` doesn't prevent scrolling.
- **Use `100%` instead of `100vw`** — Android Chrome includes scrollbar width in `100vw`, causing overflow.
- **`aspect-square` is dangerous on mobile** — `aspect-[3/4]` gives more vertical breathing room for content-heavy cards.

---

## 2. CDN Imports Blocked by Content Security Policy

### Symptom

Three cascading errors in the browser console:

```
Loading script 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm'
violates Content Security Policy directive: "script-src 'self' 'unsafe-inline'"

Failed to register controller: dashboard-dnd
TypeError: Failed to fetch dynamically imported module

Connecting to 'https://cdn.jsdelivr.net/sm/...' violates CSP "connect-src"
```

The SortableJS-powered drag-and-drop Stimulus controller failed to load entirely.

### Root Cause

The `importmap.rb` had a CDN pin for SortableJS:

```ruby
# config/importmap.rb
pin "sortablejs", to: "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm"
```

But `content_security_policy.rb` didn't include `cdn.jsdelivr.net` in the allowed sources:

```ruby
# Missing jsdelivr in CSP
policy.script_src :self, :unsafe_inline, "https://us-assets.i.posthog.com"
```

This is easy to miss because development environments often have looser CSP enforcement.

### Fix

```ruby
# config/initializers/content_security_policy.rb
Rails.application.configure do
  config.content_security_policy do |policy|
    policy.script_src  :self, :unsafe_inline,
                       "https://us-assets.i.posthog.com",
                       "https://cdn.jsdelivr.net"
    policy.connect_src :self,
                       "https://us.i.posthog.com",
                       "https://us-assets.i.posthog.com",
                       "https://cdn.jsdelivr.net"  # for source maps
  end
end
```

Server restart required (initializer change).

### Lessons Learned

**Every time you add a CDN pin to importmap, update your CSP.** Create a checklist:
1. Add pin to `config/importmap.rb`
2. Add domain to `script_src` in CSP
3. Add domain to `connect_src` if source maps are needed
4. Test in production mode (`RAILS_ENV=production rails s`)

---

## 3. Turbo Page Transitions Cause `const`/`let` Redeclaration Errors

### Symptom

Navigating away from the dashboard and coming back triggered:

```
Uncaught SyntaxError: Identifier 'STORAGE_KEY' has already been declared
```

This error repeated dozens of times, breaking all JavaScript functionality on the page — filters, sorting, and match list toggles all stopped working.

### Root Cause

The ERB view had an inline `<script>` block with `const` and `let` declarations:

```html
<script>
  const STORAGE_KEY = 'friendly_dashboard_52'
  let currentMatchSort = 'round'
  let roundDescending = true
  // ...
</script>
```

**How Turbo page transitions work:**
1. Fetch the new page
2. Replace `<body>` using `replaceWith`
3. Execute `<script>` tags in the new body

The problem is in step 3: the **previous page's `const`/`let` declarations still exist in the global scope** when the new script tries to re-declare them. JavaScript spec says `const`/`let` cannot be redeclared in the same scope — hence `SyntaxError`.

`var` allows redeclaration, so it doesn't have this problem. But simply switching to `var` can cause state pollution between page loads.

### Fix

Wrap the entire script in an **IIFE (Immediately Invoked Function Expression)** to isolate the scope:

```html
<script>
;(function() {
  var STORAGE_KEY = 'friendly_dashboard_<%= @tournament.id %>'
  var currentMatchSort = 'round'
  var roundDescending = true

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        roundFilter: currentRoundFilter,
        roundDescending: roundDescending,
        matchSort: currentMatchSort
      }))
    } catch(e) {}
  }

  // Must use window.* for inline onclick handlers
  window.filterRounds = function(filter) {
    currentRoundFilter = filter
    // DOM manipulation...
    saveState()
  }

  // Restore state on page load
  var saved = loadState()
  if (saved) {
    if (saved.roundFilter !== 'all') window.filterRounds(saved.roundFilter)
    if (saved.roundDescending === false) window.toggleRoundOrder()
  }
})()
</script>
```

### The Pattern

| Pattern | Turbo Safe? | Why |
|---------|-------------|-----|
| `const x = 1` | No | Cannot redeclare |
| `let x = 1` | No | Cannot redeclare |
| `var x = 1` (global) | Partial | Redeclares but previous value leaks |
| **IIFE + `var`** | **Yes** | Function scope isolates everything |
| **Stimulus controller** | **Yes** | Best practice — has connect/disconnect lifecycle |

### Lessons Learned

- **Never use `const`/`let` in inline `<script>` tags** in a Turbo-powered app
- IIFE + `var` + `window.functionName` is the safe pattern for quick inline scripts
- For anything beyond simple toggles, move the logic to a **Stimulus controller**

---

## 4. Turbo Stream Toast Notifications Never Disappear

### Symptom

After clicking "Auto Assign", a success toast ("3 matches assigned") appeared at the bottom of the screen — and stayed there forever. It never faded out or disappeared.

### Root Cause

The controller appended toast HTML via Turbo Stream with `data-controller='auto-dismiss'`:

```ruby
turbo_stream.append("toast-container",
  "<div data-controller='auto-dismiss' data-auto-dismiss-delay-value='3000'>
    #{notice}
  </div>".html_safe)
```

But **the `auto_dismiss_controller.js` file didn't exist.** With importmap-based eager loading, Stimulus auto-registers any controller file in `app/javascript/controllers/`. No file = no registration = no behavior.

### Fix

```javascript
// app/javascript/controllers/auto_dismiss_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { delay: { type: Number, default: 3000 } }

  connect() {
    this.timeout = setTimeout(() => {
      this.element.style.transition = "opacity 0.3s ease-out"
      this.element.style.opacity = "0"
      setTimeout(() => this.element.remove(), 300)
    }, this.delayValue)
  }

  disconnect() {
    if (this.timeout) clearTimeout(this.timeout)
  }
}
```

### Lessons Learned

- When using `data-controller` on dynamically inserted elements (Turbo Stream), **verify the controller file exists**
- Always implement `disconnect()` to clean up timers and prevent memory leaks
- A fade-out animation before `remove()` makes the UX feel polished

---

## 5. `backdrop-filter: blur()` Destroys Scroll Performance

### Symptom

Scrolling through 40 court cards felt janky — noticeable frame drops on desktop Chrome, and much worse on the iOS WKWebView.

### Root Cause

Each court card had `backdrop-filter: blur()` in **3 places**:

```html
<!-- Team A name background -->
<div style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);">

<!-- VS score background -->
<div style="background: rgba(0,0,0,0.4); backdrop-filter: blur(8px);">

<!-- Team B name background -->
<div style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);">
```

40 cards x 3 blur elements = **120 GPU composite layers**.

**How `backdrop-filter: blur()` works internally:**
1. Render everything behind the element to an offscreen buffer
2. Apply Gaussian blur to that buffer
3. Composite the blurred image with the element on top

This happens **every frame** during scrolling (60 times per second). With 120 elements doing this simultaneously, the GPU saturates — especially on mobile devices with limited GPU memory (iOS typically allocates ~1/3 of total GPU memory to WKWebView).

### Fix

Remove all `backdrop-filter: blur()` and keep only the `rgba()` semi-transparent background:

```diff
- style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);"
+ style="background: rgba(255,255,255,0.15);"
```

Additionally, add CSS `contain: content` to each card to isolate repaint boundaries:

```html
<div class="court-card" style="contain: content;">
```

### Performance Impact

| Metric | Before | After |
|--------|--------|-------|
| GPU composite layers | ~120 | 0 |
| Scroll FPS | 30-45fps (janky) | 60fps (smooth) |
| Visual difference | Blurred backgrounds | Nearly identical (semi-transparent) |
| GPU memory | High | Minimal |

### Lessons Learned

- **`backdrop-filter: blur()` is beautiful on 1-2 elements, catastrophic on 40+**
- Mobile WebViews have stricter GPU memory limits than desktop browsers
- `background: rgba(...)` without blur provides sufficient visual separation in most cases
- **CSS `contain: content`** is a low-cost optimization that prevents repaint propagation — each card's repaint stays contained

---

## 6. Legacy Database Values Displayed Raw in Views

### Symptom

The player list showed tennis skill levels as raw numbers like "4.0" and "3.5" instead of the localized labels ("Beginner", "Intermediate", etc.) that the settings form now uses.

### Root Cause

The settings form was updated to use Korean skill level labels, but seed user data in the database still had NTRP numeric values. The views directly outputted `player.user.ntrp_level` without any transformation.

### Fix

Added a backward-compatible mapping helper:

```ruby
# app/helpers/application_helper.rb
module ApplicationHelper
  NTRP_TO_LEVEL = {
    "2.0" => "Beginner", "2.5" => "Beginner",
    "3.0" => "Elementary", "3.5" => "Elementary",
    "4.0" => "Intermediate", "4.5" => "Advanced",
    "5.0" => "Expert", "5.5" => "Expert"
  }.freeze

  VALID_LEVELS = %w[Beginner Elementary Intermediate Advanced Expert].freeze

  def display_tennis_level(raw_level)
    return nil if raw_level.blank?
    return raw_level if VALID_LEVELS.include?(raw_level)
    NTRP_TO_LEVEL[raw_level] || raw_level
  end
end
```

This approach:
- Passes through new-format values unchanged
- Converts old numeric values to new labels
- Falls back to displaying the raw value for any unknown format (defensive coding)
- **No database migration needed**

---

## 7. Wrong Redirect After Status Change

### Symptom

Clicking "Revert to Registration" on the dashboard redirected to the Settings page (`/settings`) instead of back to the dashboard. Users were confused — they were working on the dashboard and suddenly landed on an unfamiliar page.

### Root Cause

```ruby
# Hard-coded redirect to settings
redirect_to settings_tournament_path(@tournament),
  notice: "Changed to registration phase. Edit your settings."
```

The developer's intent was "go to settings so you can make changes", but the user's context was "I was on the dashboard, keep me there."

### Fix

```ruby
redirect_to dashboard_path_for(@tournament),
  notice: "Changed to registration phase."
```

Using a mode-aware helper that returns the correct dashboard path:

```ruby
def dashboard_path_for(tournament)
  case tournament.mode.to_sym
  when :free_play   then tournament_free_play_dashboard_path(tournament)
  when :round_robin then tournament_round_robin_dashboard_path(tournament)
  when :friendly    then tournament_friendly_dashboard_path(tournament)
  else tournament_path(tournament)
  end
end
```

### Lessons Learned

Redirect targets should follow the **user's context**, not the developer's intention. After a status change, users expect to land where they were — not where the developer thinks they should go next.

---

## Summary

| # | Issue | Root Cause | Category |
|---|-------|-----------|----------|
| 1 | Horizontal overflow | Missing `flex-wrap` + `aspect-square` | Mobile layout |
| 2 | CDN blocked by CSP | importmap pin without CSP update | Security policy |
| 3 | `const` redeclaration | Turbo + inline script conflict | Turbo compatibility |
| 4 | Toast never dismisses | Missing Stimulus controller file | Stimulus |
| 5 | Scroll performance | 120x `backdrop-filter: blur()` | CSS performance |
| 6 | Raw DB values shown | Legacy data without view mapping | Data compatibility |
| 7 | Wrong redirect | Hard-coded redirect path | UX flow |

Most of these are **"works in development, breaks in production"** issues. The `backdrop-filter` performance problem is particularly insidious — it's unnoticeable on a high-end development machine but painfully obvious on a real mobile device.

**Hotwire Native** is an incredible framework for shipping mobile apps with your existing Rails codebase. The 37signals team (Basecamp, HEY) has proven it works at scale. But as your app grows in complexity — especially with data-heavy dashboards rendering dozens of interactive components — you'll need to pay attention to the pitfalls where web assumptions meet mobile reality.

The good news: every issue here had a straightforward fix. The key is knowing what to look for.

---

*Building with Hotwire Native? I'd love to hear about your experiences. You can find more Rails + Hotwire posts on this blog.*
