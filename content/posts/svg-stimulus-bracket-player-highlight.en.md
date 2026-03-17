---
title: "Player Highlight on SVG Bracket with Stimulus.js — Rails 8 + ViewComponent"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus.js", "SVG", "ViewComponent", "Hotwire", "Tournament", "Interaction"]
description: "Click a player in an SVG-rendered tournament bracket to highlight all their matches. Three-layer design: data attributes, hidden highlight rects, transparent click overlays — plus pre-deployment test fixes."
---

I added click-to-highlight interactivity to an SVG-based tournament bracket built with Rails 8 and ViewComponent. Here's what I ran into.

The goal: **click a player's row in the bracket → all matches featuring that player get a subtle color highlight**.

---

## Background: SVG-rendered bracket

The bracket isn't HTML divs — it's a pure SVG rendered by a `BracketTreeComponent` (ViewComponent). The component calculates coordinates for each match slot and emits `<rect>`, `<text>`, `<circle>`, and connector `<path>` elements.

```erb
<%# bracket_tree_component.html.erb %>
<svg width="<%= svg_width %>" height="<%= svg_height %>">
  <% slots.each do |slot| %>
    <% x = x_position(slot.round) %>
    <% y = y_position(slot) %>
    <g id="bracket_slot_<%= slot.id %>">
      <rect x="<%= x %>" y="<%= y %>" width="216" height="88" rx="10" fill="#fff" />
      <text x="<%= x + 46 %>" y="<%= y + 42 %>"><%= team_a_name %></text>
      <text x="<%= x + 46 %>" y="<%= y + 70 %>"><%= team_b_name %></text>
    </g>
  <% end %>
</svg>
```

Unlike HTML, Tailwind utility classes like `hover:` and `ring-` don't work directly on SVG elements. So the approach needed rethinking.

---

## Design: three layers

For SVG + Stimulus interaction, splitting concerns into three layers keeps things clean.

### Layer 1: Data — embed participant IDs

Attach participant IDs to each match `<g>` tag as data attributes.

```ruby
# bracket_tree_component.rb
def team_participant_ids(slot, team_side)
  return [] if slot.bye?
  match = slot.match
  return [] unless match
  match.public_send("#{team_side}_players").filter_map(&:participant_id)
end
```

```erb
<% a_ids = team_participant_ids(slot, :team_a).join(",") %>
<% b_ids = team_participant_ids(slot, :team_b).join(",") %>

<g id="bracket_slot_<%= slot.id %>"
   data-bracket-highlight-target="slot"
   data-bracket-highlight-team-a-ids="<%= a_ids %>"
   data-bracket-highlight-team-b-ids="<%= b_ids %>">
```

### Layer 2: Visual — hidden highlight rects

Draw semi-transparent indigo `<rect>` elements at each team row's position, hidden by default (`display:none`). These are the highlight bands that appear on click.

SVG follows the painter's algorithm — later elements paint over earlier ones. The highlight rects must come **after the white background rect but before the text content** so they tint the row without obscuring the text.

```erb
<%# After background rect, before text %>
<rect class="bracket-player-hl-a"
      x="<%= x + 3 %>" y="<%= y + 24 %>"
      width="<%= MATCH_WIDTH - 3 %>" height="25"
      fill="rgba(99,102,241,0.12)"
      style="display:none; pointer-events:none" />
<rect class="bracket-player-hl-b"
      x="<%= x + 3 %>" y="<%= y + 49 %>"
      width="<%= MATCH_WIDTH - 3 %>" height="32"
      fill="rgba(99,102,241,0.12)"
      style="display:none; pointer-events:none" />
```

### Layer 3: Click — transparent overlay rects

Stack `fill="transparent"` rects on top of everything to capture click events. They must be the **last children in the group** to sit above all other content.

```erb
<%# Last in group %>
<% if a_ids.present? %>
  <rect x="<%= x + 3 %>" y="<%= y + 24 %>"
        width="<%= MATCH_WIDTH - 3 %>" height="25"
        fill="transparent" style="cursor:pointer"
        data-action="click->bracket-highlight#selectTeam"
        data-bracket-highlight-ids-param="<%= a_ids %>" />
<% end %>
<% if b_ids.present? %>
  <rect x="<%= x + 3 %>" y="<%= y + 49 %>"
        width="<%= MATCH_WIDTH - 3 %>" height="32"
        fill="transparent" style="cursor:pointer"
        data-action="click->bracket-highlight#selectTeam"
        data-bracket-highlight-ids-param="<%= b_ids %>" />
<% end %>
```

---

## Stimulus controller

The controller stores the selected IDs and walks every slot to show or hide the highlight rects.

```javascript
// bracket_highlight_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["slot"]

  connect() {
    this.selectedIds = null
  }

  selectTeam(event) {
    event.stopPropagation()

    const ids = (event.params.ids || "").split(",").filter(Boolean)
    if (!ids.length) return

    // Click same row again → deselect
    if (this.#sameSelection(ids)) {
      this.selectedIds = null
    } else {
      this.selectedIds = ids
    }

    this.#applyHighlights()
  }

  #sameSelection(ids) {
    if (!this.selectedIds) return false
    const sort = (arr) => [...arr].sort().join(",")
    return sort(ids) === sort(this.selectedIds)
  }

  #applyHighlights() {
    this.slotTargets.forEach((slot) => {
      const aIds = (slot.dataset.bracketHighlightTeamAIds || "").split(",").filter(Boolean)
      const bIds = (slot.dataset.bracketHighlightTeamBIds || "").split(",").filter(Boolean)

      const aMatch = this.selectedIds?.some((id) => aIds.includes(id)) ?? false
      const bMatch = this.selectedIds?.some((id) => bIds.includes(id)) ?? false

      slot.querySelector(".bracket-player-hl-a")?.style.setProperty("display", aMatch ? "" : "none")
      slot.querySelector(".bracket-player-hl-b")?.style.setProperty("display", bMatch ? "" : "none")
    })
  }
}
```

---

## Pre-deployment test failures

Before the SVG work, I ran `bin/rails test` and found 7 failures. Each was a different kind of mismatch.

### 1. Redirect path mismatch

Tests assumed login would redirect to `root_path`, but the controller routes signed-in users to `dashboard_path` via a helper. Fixed by aligning test expectations with actual behaviour.

### 2. ViewComponent test data type

The component template accessed `player[:name]` (hash), but the test supplied plain strings `["Name 1", "Name 2"]`. Fixed by passing hashes:

```ruby
# Before
players: ["Name 1", "Name 2"]

# After
players: [{ name: "Name 1" }, { name: "Name 2" }]
```

### 3. Settings page guest access

A `before_action :authenticate_user_or_participant!` was sending unauthenticated visitors to an `enter_path` route. The settings page should render for guests (showing a signup prompt); only `PATCH` needs protection.

```ruby
class SettingsController < ApplicationController
  skip_before_action :authenticate_user!, raise: false
  before_action :require_user!, only: [:update]
end
```

### 4. Native app guest redirect

Hotwire Native unauthenticated requests were redirected to `enter_path` instead of `new_session_path`. Fixed to use the standard login route.

---

## Takeaways

- **SVG interaction is all about render order.** The sequence must be: background → highlight bands → content → transparent click overlay.
- **`data-*` attributes and Stimulus work on SVG elements with no special setup.** `data-action`, `data-controller`, and `data-*-target` all work out of the box.
- **`fill="transparent"` receives click events; `fill="none"` may not.** This tripped me up briefly.
- **Run the full test suite before deployment.** "It's implemented" and "the tests pass" are two different things.
