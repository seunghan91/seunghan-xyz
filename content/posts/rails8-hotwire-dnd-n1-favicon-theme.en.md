---
title: "Rails 8 Hotwire War Stories — DnD Assignment, N+1 Auto-Detection, Theme-Aware Favicons"
date: 2026-03-21
draft: false
tags: ["Rails 8", "Hotwire", "Turbo Stream", "Stimulus", "N+1", "Prosopite", "DnD", "Favicon", "iOS"]
description: "Implementing drag-and-drop player assignment with Turbo Stream + Stimulus, discovering 121-query N+1 issues and adopting Prosopite, plus dynamic theme-aware favicons and iOS app icon switching"
categories: ["iOS", "Rails"]
---

Three real-world problems encountered while building a real-time tournament dashboard with Rails 8 + Hotwire, and the exact steps taken to resolve each one. These issues are not edge cases — they reflect the natural friction points of the Hotwire programming model that become apparent only at runtime.

---

## 1. Turbo Stream + Stimulus DnD: Events Vanish After DOM Replacement

### The Problem

The feature: drag a player chip onto a court card, send a POST to the server, and get back a Turbo Stream response that replaces both the court card and the player list.

The first drag works perfectly. **The second drag produces nothing — no event, no request, no response.**

This is one of the most disorienting Hotwire bugs to encounter because everything looks correct in the DOM. The elements are there, the `data-controller` attributes are present, and the Stimulus controller is registered. But nothing fires.

### Root Cause

Stimulus controllers attach event listeners during `connect()`. When Turbo Stream replaces a chunk of the DOM, the old elements — along with their listeners — are discarded. The new elements rendered by the server start with a clean slate: no `dragstart`, no `dragover`, no `drop` handlers.

The wrong pattern looks like this:

```javascript
// Bad: listeners attached once, lost on DOM replacement
connect() {
  this.chipTargets.forEach(chip => {
    chip.addEventListener("dragstart", this.dragStart.bind(this))
  })
}
```

After Turbo Stream fires, `this.chipTargets` still resolves, but those are new DOM nodes. The old handlers are gone and the new nodes have none.

### Fix: targetConnected Lifecycle + Double Defense

Stimulus 3.x provides target lifecycle callbacks: `[target]TargetConnected(element)` fires every time a matching target is inserted into the DOM, including after Turbo Stream replacements. This is the right hook.

However, in some environments (particularly Safari or older Hotwire versions), `targetConnected` does not reliably fire on initial `connect()`. The safe approach is to call the setup function from both places:

```javascript
connect() {
  this._boundDragStart = this.dragStart.bind(this)
  this._boundDragOver = this.dragOver.bind(this)
  this._boundDrop = this.drop.bind(this)
  // Fallback: manually setup targets already in the DOM at connect time
  this.chipTargets.forEach(chip => this._setupChip(chip))
}

// Automatically called when a new [data-target="...chip"] enters the DOM
chipTargetConnected(chip) {
  this._setupChip(chip)
}

chipTargetDisconnected(chip) {
  this._teardownChip(chip)
}

_setupChip(chip) {
  if (chip.dataset.dragBound) return  // idempotency guard
  chip.dataset.dragBound = "1"
  chip.setAttribute("draggable", "true")
  chip.addEventListener("dragstart", this._boundDragStart)
}

_teardownChip(chip) {
  chip.removeEventListener("dragstart", this._boundDragStart)
  delete chip.dataset.dragBound
}
```

The `dragBound` dataset flag prevents double-binding if both `connect()` and `targetConnected` fire for the same element. The `_teardownChip` cleanup prevents memory leaks on elements that Turbo Stream removes.

### Bonus Trap: Turbo Stream Replace Loses the Target ID

A second, unrelated issue surfaced during testing. After the first successful drag, the second drag had a different failure: the Turbo Stream response found no element to replace.

The cause: `turbo_stream.replace("player-list-container", partial: "player_list")` replaces the element whose `id` matches the first argument. But if the partial being rendered does not itself include that `id` attribute on its root element, then after the first replacement, the `id` is gone from the DOM. The second replacement has no target to find.

```erb
<%# Wrong: the partial renders a div with no id %>
<div class="flex items-center gap-2">
  <% @players.each do |p| %>
    ...
  <% end %>
</div>

<%# Correct: the partial wraps its content in the target element %>
<div id="player-list-container">
  <div class="flex items-center gap-2">
    <% @players.each do |p| %>
      ...
    <% end %>
  </div>
</div>
```

**Rule:** The `id` passed to `turbo_stream.replace` must exist on the outermost element inside the partial. Turbo Stream replaces the element matching that id with the rendered partial. If the partial does not re-emit that id, the DOM loses the handle permanently.

### Why This Is Easy to Miss

Both bugs pass manual smoke testing. The first drag succeeds, so a quick test gives a green result. It is only on the second interaction — or in an automated test that chains two drag operations — that the breakage appears. Adding `targetConnected` hooks and verifying partial IDs should be part of any Hotwire DnD implementation checklist.

---

## 2. 121 Queries on a Single Page: Catching N+1 Before Users Do

### The Problem

The match tab on the dashboard felt sluggish. No error, no timeout — just a noticeable pause on every navigation. The Rails log confirmed the suspicion:

```
Completed 200 OK in 340ms (Views: 165ms | ActiveRecord: 104ms (121 queries, 40 cached))
```

121 database queries for a single page render. With 40 of them cached, the real hit was 81 round-trips to the database, contributing over 100ms of ActiveRecord time.

### Root Cause: Per-Player Queries in a Service Object

The dashboard used a service object to compute player statistics for display. The implementation called instance methods on each player model object:

```ruby
# N+1: each method call fires one or more SQL queries per player
player_stats = players.map do |player|
  {
    matches_played: player.completed_matches_count,  # SELECT COUNT(*)
    wins:           player.wins_count,               # loads match_players, iterates
    losses:         player.losses_count,             # separate COUNT
    win_rate:       player.win_rate,                 # calls wins + matches again
  }
end
```

With 11 players and 4 queries per player, that alone adds 44 queries. The base page load added more through similar patterns in other parts of the view, reaching 121 total.

### Immediate Fix: In-Memory Aggregation Over Preloaded Data

The matches and their `match_players` associations were already loaded earlier in the service object. Instead of querying per player, a single pass over the already-loaded data computes all statistics without hitting the database again:

```ruby
player_match_counts = Hash.new(0)
player_win_counts   = Hash.new(0)

completed_matches.each do |match|
  team_a_ids = match.match_players.select(&:team_a?).map(&:participant_id)
  team_b_ids = match.match_players.select(&:team_b?).map(&:participant_id)

  (team_a_ids + team_b_ids).each { |pid| player_match_counts[pid] += 1 }

  winner_ids = match.winner_team == "team_a" ? team_a_ids : team_b_ids
  winner_ids.each { |pid| player_win_counts[pid] += 1 }
end

player_stats = players.map do |player|
  matches = player_match_counts[player.id]
  wins    = player_win_counts[player.id]
  {
    matches_played: matches,
    wins:           wins,
    losses:         matches - wins,
    win_rate:       matches > 0 ? (wins.to_f / matches * 100).round(1) : 0,
  }
end
```

Result: the 44 per-player queries drop to zero. Total queries on the page fell from 121 to around 12, and response time dropped from 340ms to under 80ms.

### The Right Fix: Prosopite for Automatic Detection

The in-memory aggregation fixed this specific N+1. But the underlying problem is that **N+1 bugs require a human to notice a slowness before they get investigated**. That is not acceptable in a development workflow. The answer is automatic detection on every request.

[Prosopite](https://github.com/charkost/prosopite) instruments ActiveRecord to detect N+1 patterns during development. Unlike [Bullet](https://github.com/flyerhzm/bullet), which works via association loading heuristics and produces false positives, Prosopite tracks query fingerprints per call stack. It only reports a pattern when the exact same query (same fingerprint) is executed from the same call stack location more than a configurable minimum number of times. This means no false positives, and no alert fatigue.

Setup is four steps:

```ruby
# Gemfile
group :development do
  gem "prosopite"
end
```

```ruby
# config/environments/development.rb
config.after_initialize do
  Prosopite.rails_logger = true   # N+1 warnings appear in development.log
  Prosopite.raise = false         # flip to true to make N+1s fail the request
  Prosopite.min_n_queries = 2     # flag after 2+ repeated queries
end
```

```ruby
# app/controllers/application_controller.rb
around_action :prosopite_scan, if: -> { Rails.env.development? }

private

def prosopite_scan
  Prosopite.scan
  yield
ensure
  Prosopite.finish
end
```

After this, every controller action is automatically scanned. N+1 patterns appear in the log immediately:

```
[Prosopite] N+1 queries detected:
  SELECT "match_players".* FROM "match_players" WHERE "match_players"."match_id" = $1
  ↳ app/models/match.rb:34:in `wins_count'
  Called 11 times from app/services/player_stats_service.rb:22
```

The log output names the source file and line. Finding an N+1 goes from "user reports slowness → manual log investigation → bisect the query" to "open the log, read the warning, fix the line." The development loop tightens considerably.

To grep for warnings during a session:

```bash
grep 'Prosopite' log/development.log
```

---

## 3. Theme-Aware Favicons and iOS App Icons

### The Problem

The app supports multiple visual themes — each with a distinct color palette. CSS variables update instantly on theme change. But the browser tab favicon stays on the default icon regardless of the selected theme. In the iOS app (Hotwire Native), the home screen app icon is similarly static.

These are low-priority cosmetic issues in isolation. Together, they break the cohesion of a well-themed interface: the UI changes, but the identity markers do not follow.

### Fix 1: Dynamic SVG Favicon via Blob URL

The natural first attempt is to use an SVG favicon and embed CSS variables in it. This does not work. SVG favicons render in a separate browser context that has no access to the page's computed CSS custom properties. `var(--color-primary)` inside a favicon SVG resolves to nothing.

The correct approach generates the SVG content in JavaScript with the resolved color values, creates a Blob from that string, and replaces the favicon `<link>` element's `href` with the Blob URL:

```javascript
// theme_controller.js (Stimulus)
const THEME_COLORS = {
  "default":   { bg: "#047857", stroke: "#ecfdf5" },
  "wimbledon": { bg: "#522398", stroke: "#f5f0ff" },
  "us-open":   { bg: "#003DA5", stroke: "#eef3ff" },
  "hardcourt": { bg: "#c05e1a", stroke: "#fff7ed" },
}

_updateFavicon(theme) {
  const colors = THEME_COLORS[theme] ?? THEME_COLORS["default"]

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
    <rect width="512" height="512" rx="96" fill="${colors.bg}"/>
    <circle cx="256" cy="256" r="120" fill="none" stroke="${colors.stroke}" stroke-width="24"/>
    <line x1="136" y1="256" x2="376" y2="256" stroke="${colors.stroke}" stroke-width="24"/>
    <line x1="256" y1="136" x2="256" y2="376" stroke="${colors.stroke}" stroke-width="24"/>
  </svg>`

  const blob = new Blob([svg], { type: "image/svg+xml" })
  const url  = URL.createObjectURL(blob)

  const link = document.querySelector('link[rel="icon"][type="image/svg+xml"]')
  if (!link) return

  // Revoke the previous Blob URL to avoid memory leaks
  if (link.dataset.blobUrl) URL.revokeObjectURL(link.dataset.blobUrl)

  link.href = url
  link.dataset.blobUrl = url
}
```

One additional concern: on initial page load, the favicon uses the static file until JavaScript runs, causing a brief flash back to the default icon. To prevent this, add a small inline script in `<head>` that reads the stored theme preference from `localStorage` and calls the same Blob URL logic before the rest of the page renders:

```html
<head>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <script>
    // Runs synchronously before paint — no favicon flash
    (function() {
      const theme = localStorage.getItem("theme") || "default"
      const colors = { default: { bg: "#047857", stroke: "#ecfdf5" }, /* ... */ }
      const c = colors[theme] || colors.default
      const svg = `<svg ...><rect fill="${c.bg}"/>...</svg>`
      const blob = new Blob([svg], { type: "image/svg+xml" })
      document.querySelector('link[rel="icon"]').href = URL.createObjectURL(blob)
    })()
  </script>
</head>
```

### Fix 2: iOS App Icon via Alternate Icons and Hotwire Native Bridge

iOS has supported runtime app icon changes via `UIApplication.shared.setAlternateIconName()` since iOS 10.3. Hotwire Native's Bridge Component architecture makes it straightforward to wire this to the web layer.

**Step 1: Register alternate icons in the Asset Catalog**

Each theme gets its own `.appiconset` in `Assets.xcassets`:

```
Assets.xcassets/
├── AppIcon.appiconset/           (default, required)
├── AppIcon-Wimbledon.appiconset/
├── AppIcon-USOpen.appiconset/
└── AppIcon-Hardcourt.appiconset/
```

**Step 2: Declare alternate icons in Info.plist**

```xml
<key>CFBundleIcons</key>
<dict>
  <key>CFBundleAlternateIcons</key>
  <dict>
    <key>AppIcon-Wimbledon</key>
    <dict>
      <key>CFBundleIconFiles</key>
      <array><string>AppIcon-Wimbledon</string></array>
      <key>UIPrerenderedIcon</key>
      <false/>
    </dict>
    <key>AppIcon-USOpen</key>
    <dict>
      <key>CFBundleIconFiles</key>
      <array><string>AppIcon-USOpen</string></array>
      <key>UIPrerenderedIcon</key>
      <false/>
    </dict>
  </dict>
</dict>
```

**Step 3: Implement the Bridge Component in Swift**

```swift
// AppIconComponent.swift
import HotwireNative
import UIKit

struct AppIconPayload: Decodable {
    let theme: String
}

class AppIconComponent: BridgeComponent {
    override class var name: String { "app-icon" }

    private let themeToIconName: [String: String?] = [
        "default":   nil,              // nil resets to the primary icon
        "wimbledon": "AppIcon-Wimbledon",
        "us-open":   "AppIcon-USOpen",
        "hardcourt": "AppIcon-Hardcourt",
    ]

    override func onReceive(message: Message) {
        guard let data: AppIconPayload = message.data() else { return }
        let iconName = themeToIconName[data.theme] ?? nil

        UIApplication.shared.setAlternateIconName(iconName) { error in
            if let error { print("[AppIconComponent] error: \(error)") }
        }

        reply(to: message)
    }
}
```

**Step 4: Call the bridge from the web Stimulus controller**

```javascript
// theme_controller.js
_updateAppIcon(theme) {
  // Only fires inside Hotwire Native iOS; no-op in browser
  window.webkit?.messageHandlers?.["app-icon"]?.postMessage({ theme })
}

themeChanged(theme) {
  this._applyTheme(theme)
  this._updateFavicon(theme)
  this._updateAppIcon(theme)
  localStorage.setItem("theme", theme)
}
```

The result: a single theme selection triggers favicon update in the browser tab, app icon update on the iOS home screen, and CSS variable update in the UI — all from the same Stimulus action.

**Note on iOS behavior:** `setAlternateIconName` shows a system alert the first time it runs ("You have changed the icon for..."). This is an iOS system restriction and cannot be suppressed. It only appears once per icon change, so it is a minor UX friction rather than a blocking issue.

---

## Key Takeaways

| Issue | Root Cause | Fix | Core Lesson |
|-------|------------|-----|-------------|
| DnD breaks after first use | Turbo Stream replaces DOM, event listeners lost | `targetConnected` lifecycle callback + idempotency guard | Stimulus and Turbo Stream lifecycles must be explicitly synchronized |
| 121 queries per page | Per-player N+1 in service object | In-memory aggregation over preloaded data + Prosopite | Without automatic detection, N+1s surface as user complaints, not dev warnings |
| Favicon ignores theme change | SVG favicons render in a separate context without CSS variable access | Blob URL generation in JavaScript | The browser favicon pipeline is isolated from the page's CSS environment |
| iOS app icon is static | No native hook from web layer | Hotwire Native Bridge Component + `setAlternateIconName` | Bridge Components are the right abstraction for web-to-native capability calls |

Rails 8 + Hotwire's model — "server sends HTML, browser applies it" — is genuinely simple at the conceptual level. But DOM lifecycle management, N+1 query discipline, and browser rendering context boundaries remain entirely the developer's responsibility. These problems do not surface in tutorials; they surface in production dashboards at the moment a user drags a chip for the second time.

The three fixes described here cost less than a day combined. The Prosopite setup in particular pays ongoing dividends: every new N+1 introduced anywhere in the codebase now produces an immediate log warning rather than waiting for a user to notice latency.
