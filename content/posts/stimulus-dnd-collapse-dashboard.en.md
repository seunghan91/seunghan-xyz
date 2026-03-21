---
title: "Dashboard Card DnD Reordering + Collapse in Rails — SortableJS + Stimulus + CSS Trick"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus", "SortableJS", "Hotwire", "Turbo Frame", "CSS", "localStorage", "Dashboard"]
description: "Why native HTML5 drag-and-drop failed and how SortableJS + Stimulus solved it. A CSS grid-template-rows trick for height animation without measuring scrollHeight, and localStorage persistence for layout state across reloads."
cover:
  image: "/images/og/stimulus-dnd-collapse-dashboard.png"
  alt: "Stimulus DnD Collapse Dashboard"
  hidden: true
categories: ["Rails", "Hotwire"]
---

I was adding two features to the dashboard of a sports tournament management app:

1. **DnD card reordering** — drag cards to rearrange sections (My Matches / Bracket / Match List)
2. **Card collapse/expand** — fold away sections you don't need

Each sounds simple, but add Turbo Frame lazy loading and a requirement that layout state survives page reloads, and there's more to think about than it first appears.

---

## 1. Choosing a DnD Library

My first attempt used the native HTML5 Drag & Drop API directly — `dragstart`, `dragover`, `drop`. It works fine on desktop, but the problem is **touch devices**. The HTML5 drag API has incomplete support on iOS Safari; touch-dragging simply doesn't work there.

Since mobile is the primary platform, this was a non-starter.

Libraries I evaluated:

| Library | Size (gzip) | Touch | Stimulus integration | Notes |
|---|---|---|---|---|
| **SortableJS** | ~10KB | ✅ Full | Very easy | Rails community standard |
| Dragula | ~5KB | ⚠️ Partial | OK | Weak multi-container support |
| Interact.js | ~25KB | ✅ Full | Complex | Good when resize is also needed |
| Pragmatic DnD | ~15KB | ✅ Full | Complex | Great accessibility, by Atlassian |

Went with **SortableJS** — most battle-tested in the Rails/Hotwire ecosystem and a natural fit for Stimulus controllers.

### Adding via importmap

Pin the CDN ESM version:

```ruby
# config/importmap.rb
pin "sortablejs", to: "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm"
```

---

## 2. Stimulus Controller Design

```javascript
// app/javascript/controllers/dashboard_dnd_controller.js
import { Controller } from "@hotwired/stimulus"
import Sortable from "sortablejs"

export default class extends Controller {
  static values = { storageKey: { type: String, default: "dashboard-layout-v1" } }

  connect() {
    this._restoreOrder()
    this._restoreCollapsed()

    this._sortable = new Sortable(this.element, {
      handle: ".dnd-handle",  // only the grip icon triggers drag
      animation: 150,
      ghostClass: "dnd-ghost",
      chosenClass: "dnd-chosen",
      onEnd: () => this._saveOrder()
    })
  }

  disconnect() {
    this._sortable?.destroy()
  }

  toggle(event) {
    const card    = event.currentTarget.closest("[data-card-id]")
    const content = card?.querySelector(".card-collapsible")
    const icon    = card?.querySelector("[data-toggle-icon]")
    if (!content) return

    const collapsing = !content.classList.contains("collapsed")
    content.classList.toggle("collapsed", collapsing)
    icon?.classList.toggle("rotate-180", collapsing)
    this._saveCollapsed()
  }

  _saveOrder() {
    const order = Array.from(this.element.children)
      .map(el => el.dataset.cardId)
      .filter(Boolean)
    localStorage.setItem(this.storageKeyValue, JSON.stringify(order))
  }

  _restoreOrder() {
    try {
      const order = JSON.parse(localStorage.getItem(this.storageKeyValue) || "[]")
      order.forEach(id => {
        const el = this.element.querySelector(`:scope > [data-card-id="${id}"]`)
        if (el) this.element.appendChild(el)
      })
    } catch (_) {}
  }

  _saveCollapsed() {
    const collapsed = Array.from(
      this.element.querySelectorAll(".card-collapsible.collapsed")
    ).map(el => el.closest("[data-card-id]")?.dataset.cardId).filter(Boolean)
    localStorage.setItem(this.storageKeyValue + "-collapsed", JSON.stringify(collapsed))
  }

  _restoreCollapsed() {
    try {
      const collapsed = JSON.parse(
        localStorage.getItem(this.storageKeyValue + "-collapsed") || "[]"
      )
      collapsed.forEach(id => {
        const card = this.element.querySelector(`:scope > [data-card-id="${id}"]`)
        card?.querySelector(".card-collapsible")?.classList.add("collapsed")
        card?.querySelector("[data-toggle-icon]")?.classList.add("rotate-180")
      })
    } catch (_) {}
  }
}
```

### Two design decisions worth noting

**`handle: ".dnd-handle"` is essential.** Without a handle, clicking buttons or scrolling inside a card competes with the drag gesture. One of the cards has a pinch-zoom/pan canvas — without an explicit handle this would be unusable.

**`_restoreOrder()` runs before `new Sortable()`.** Sort the DOM first, then initialize SortableJS on the already-sorted list. If you do it the other way around, SortableJS starts with the original (unsorted) state.

---

## 3. Card Collapse Animation — The Height Problem

Animating height to zero sounds trivial. It isn't.

### Why `max-height` is frustrating

The common approach:

```css
.collapsible { max-height: 1000px; transition: max-height 0.3s ease; overflow: hidden; }
.collapsible.collapsed { max-height: 0; }
```

The problem: **the animation duration covers the full max-height range, not the actual height.** If the card is 200px tall but max-height is 1000px, collapsing "wastes" 800px worth of transition time doing nothing, then compresses 200px in the remaining fraction. It looks broken.

You can fix this with JS by measuring `scrollHeight` and setting it as the max-height. But when the card content is a **Turbo Frame loaded lazily**, `scrollHeight` at the time you need it might be 0 or just the skeleton height.

### The `grid-template-rows` trick

```css
.card-collapsible {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 0.25s ease;
}
.card-collapsible.collapsed {
  grid-template-rows: 0fr;
}
.card-collapsible > * {
  overflow: hidden;
  min-height: 0;  /* without this, 0fr doesn't actually reach 0 */
}
```

CSS Grid can transition `fr` values. Going from `1fr` to `0fr` collapses the content exactly to zero, no matter what the actual height is — no JS measurement needed.

**Benefits:**
- No height measurement in JS
- Works correctly even when content is loaded after the fact
- Unlike `display: none`, the element stays in layout while collapsed

---

## 4. HTML Structure

```html
<!-- Outer wrapper: data-card-id is what SortableJS tracks -->
<div data-card-id="scoreboard">

  <!-- Drag handle + collapse button -->
  <div class="dnd-handle flex items-center justify-between px-3 py-1.5
              bg-slate-50 border border-b-0 border-slate-200
              rounded-t-2xl cursor-grab active:cursor-grabbing select-none">
    <div class="flex items-center gap-2 text-slate-400">
      <!-- 6-dot grip icon -->
      <svg viewBox="0 0 10 16" fill="currentColor" class="h-3.5 w-3.5">
        <circle cx="2" cy="2" r="1.5"/><circle cx="8" cy="2" r="1.5"/>
        <circle cx="2" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/>
        <circle cx="2" cy="14" r="1.5"/><circle cx="8" cy="14" r="1.5"/>
      </svg>
      <span class="text-[10px] font-semibold uppercase tracking-[.24em]">My Matches</span>
    </div>
    <button data-action="click->dashboard-dnd#toggle">
      <svg data-toggle-icon class="h-3.5 w-3.5 transition-transform duration-200" ...>
        <polyline points="18 15 12 9 6 15"/>
      </svg>
    </button>
  </div>

  <!-- Collapsible content -->
  <div class="card-collapsible">
    <div><!-- inner wrapper required for the grid trick -->
      <section id="scoreboard-section">
        <%= turbo_frame_tag "scoreboard_frame", src: ..., loading: :lazy do %>
          <!-- skeleton -->
        <% end %>
      </section>
    </div>
  </div>

</div>
```

**Visual join:** the drag handle uses `rounded-t-2xl border-b-0` and the card content uses `rounded-b-2xl`, so they read as a single connected card.

---

## 5. Compatibility with Turbo Frame Lazy Loading

Turbo Frame lazy loading triggers when the frame enters the viewport.

**`_restoreOrder()` only moves DOM nodes — it doesn't retrigger loading.** At `connect()` time, frames probably haven't loaded yet. Moving them with `appendChild` doesn't cause a reload. After the DOM is sorted, frames load normally when they scroll into view.

**Cards restored as collapsed** are effectively outside the viewport, so their frames don't load until the user expands them. This is an unintentional but useful side effect — it eliminates unnecessary API calls for sections the user never views.

---

## 6. Ghost Styles

SortableJS's default ghost is just transparent. A bit of CSS makes it feel more polished:

```css
.dnd-ghost {
  opacity: 0.35;
  border-radius: 1rem;
  background: #e2e8f0;
}
.dnd-chosen {
  box-shadow: 0 20px 40px -8px rgba(0, 0, 0, 0.18);
}
```

`dnd-chosen` is applied to the actual dragged element (not the ghost placeholder). The strong shadow gives it a "lifted" feel.

---

## Result

- All 3 cards reorderable via drag handle
- Each card collapses/expands with a smooth animation via the chevron button
- Order + collapsed state persisted to `localStorage`, restored on reload
- No conflicts with Turbo Frame lazy loading
- Works identically on mobile (touch) and desktop

The total addition: one library pin (SortableJS), one new Stimulus controller, a few lines of CSS.
