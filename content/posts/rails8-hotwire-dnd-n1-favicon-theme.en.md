---
title: "Rails 8 Hotwire War Stories — DnD Assignment, N+1 Auto-Detection, Theme-Aware Favicons"
date: 2026-03-21
draft: false
tags: ["Rails 8", "Hotwire", "Turbo Stream", "Stimulus", "N+1", "Prosopite", "DnD", "Favicon", "iOS"]
description: "Implementing drag-and-drop player assignment with Turbo Stream + Stimulus, discovering 121-query N+1 issues and adopting Prosopite, plus dynamic theme-aware favicons and iOS app icon switching"
categories: ["Rails"]
---

Three real-world problems encountered while building a real-time dashboard with Rails 8 + Hotwire, and how each was solved.

---

## 1. Turbo Stream + Stimulus DnD: Events Vanish After DOM Replacement

### Problem

Built a drag-and-drop interface where player chips can be dragged onto court cards. On drop, a POST request fires, and the server responds with Turbo Stream to replace the court card and player list.

First drag works. **Second drag doesn't respond at all.**

### Root Cause

Event listeners were attached once in `connect()`. When Turbo Stream replaces the DOM elements, the new elements have no listeners.

### Fix: targetConnected + Double Defense

```javascript
connect() {
  this._boundDragStart = this.dragStart.bind(this)
  // Also setup existing targets (fallback for environments where
  // targetConnected doesn't fire)
  this.chipTargets.forEach(chip => this._setupChip(chip))
}

// Called automatically when new targets appear in DOM
chipTargetConnected(chip) { this._setupChip(chip) }
chipTargetDisconnected(chip) { this._teardownChip(chip) }

_setupChip(chip) {
  if (chip.dataset.dragBound) return  // prevent double-bind
  chip.dataset.dragBound = "1"
  chip.setAttribute("draggable", "true")
  chip.addEventListener("dragstart", this._boundDragStart)
}
```

### Bonus Trap: Turbo Stream Replace Loses Target ID

When using `turbo_stream.replace("player-list-container", partial: "player_list")`, the **partial itself must contain** `id="player-list-container"`. Otherwise the first replace removes the ID from the DOM, and subsequent replaces can't find the target.

---

## 2. 121 Queries N+1: Catching It Before Users Do

### Problem

Dashboard felt sluggish when navigating. Rails log revealed:

```
Completed 200 OK in 340ms (ActiveRecord: 104ms (121 queries, 40 cached))
```

### Root Cause

A service object computed per-player statistics by calling individual model methods:

```ruby
# Each of these triggers a separate DB query per player
player.completed_matches_count  # SELECT COUNT(*)...
player.wins_count               # loads match_players, iterates
player.win_rate                 # calls both above again
```

With 11 players: 11 × 4 = 44 extra queries on top of base queries.

### Fix: In-Memory Aggregation

```ruby
player_match_counts = Hash.new(0)
player_win_counts = Hash.new(0)

# Single pass over already-loaded matches — 0 additional queries
completed_matches.each do |match|
  all_ids = match.match_players.map(&:participant_id)
  all_ids.each { |pid| player_match_counts[pid] += 1 }

  winner_ids = match.winner_team == "team_a" ? team_a_ids : team_b_ids
  winner_ids.each { |pid| player_win_counts[pid] += 1 }
end
```

### Permanent Fix: Prosopite Auto-Detection

The real problem is **relying on humans to notice slowness**. Install Prosopite to catch N+1 queries automatically:

```ruby
# Gemfile
gem "prosopite", group: :development

# config/environments/development.rb
Prosopite.rails_logger = true
Prosopite.raise = false  # set true to fail on N+1

# application_controller.rb
around_action :prosopite_scan, if: -> { Rails.env.development? }

def prosopite_scan
  Prosopite.scan
  yield
ensure
  Prosopite.finish
end
```

Unlike Bullet, Prosopite has **zero false positives** — it only flags when the same call stack produces the same query fingerprint 2+ times.

---

## 3. Theme-Aware Favicons + iOS App Icons

### Problem

Theme changes update CSS variables instantly, but the browser favicon stays the same. iOS app icon is also static.

### Fix 1: Dynamic SVG Favicon via Blob URL

SVG favicons can't access the page's CSS variables (separate rendering context). Generate the SVG in JavaScript and create a Blob URL:

```javascript
_updateFavicon(theme) {
  const colors = THEME_COLORS[theme]
  const svg = `<svg ...><rect fill="${colors.bg}"/>...</svg>`
  const blob = new Blob([svg], { type: "image/svg+xml" })
  const url = URL.createObjectURL(blob)

  const link = document.querySelector('link[rel="icon"][type="image/svg+xml"]')
  if (link.dataset.blobUrl) URL.revokeObjectURL(link.dataset.blobUrl)
  link.href = url
  link.dataset.blobUrl = url
}
```

### Fix 2: iOS App Icon via Alternate Icons + Bridge

iOS supports `setAlternateIconName()` since iOS 10.3. Combined with Hotwire Native's Bridge Components:

```swift
// Native: AppIconComponent.swift
class AppIconComponent: BridgeComponent {
    override class var name: String { "app-icon" }

    override func onReceive(message: Message) {
        guard let data: Payload = message.data() else { return }
        UIApplication.shared.setAlternateIconName(iconName)
        reply(to: message.id)
    }
}
```

```javascript
// Web: theme_controller.js
_updateAppIcon(theme) {
  window.webkit?.messageHandlers?.["app-icon"]?.postMessage({ theme })
}
```

Theme selection → favicon changes instantly + iOS app icon updates on home screen.

---

## Summary

| Issue | Cause | Fix | Lesson |
|-------|-------|-----|--------|
| DnD breaks after first use | Turbo Stream replaces DOM, events lost | `targetConnected` lifecycle | Stimulus and Turbo Stream lifecycles must be synchronized |
| 121 queries per page | N+1 in service object | In-memory aggregation + Prosopite | Without auto-detection, users find your N+1s |
| Favicon ignores theme | SVG favicon is a separate context | Blob URL generation | Browser favicon has no access to page CSS |
