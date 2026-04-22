---
title: "Rails + Stimulus: Implementing 11 Controllers — Scroll, Carousel, Text Animation"
date: 2025-11-18
draft: false
tags: ["Rails", "Stimulus", "ViewComponent", "Lookbook", "JavaScript", "Animation"]
description: "Implementing 11 stub Stimulus controllers to actually work, including debugging the bug where Stimulus doesn't work in Lookbook previews."
cover:
  image: "/images/og/rails-stimulus-controllers-lookbook-debug.png"
  alt: "Rails Stimulus Controllers Lookbook Debug"
  hidden: true
categories: ["iOS", "Rails"]
---

When building a component library with Rails + ViewComponent + Lookbook, I ran into a situation where all my Stimulus controllers were stubs — empty shells. Out of 13 controllers, only 3 were actually working; the remaining 10 were single-line `connect() {}` placeholders. This post documents the debugging process and implementation decisions for all 11 controllers I built out.

The focus here is not just on the code itself, but on **why** I chose each approach, **what problems came up**, and **how I solved them**.

---

## What Was Being Implemented

I implemented 11 controllers across 4 waves, ordered by complexity and dependency. Going from direct DOM manipulation to scroll integration to RAF animation to interactive carousels means the patterns learned in each wave carry forward naturally to the next.

| Wave | Controllers | Key Techniques |
|------|------------|----------------|
| 1 | TagInput, FileDropzone, CategoryTab | DOM manipulation, drag events |
| 2 | ScrollReveal, ScrollScale, VideoScrubbing, HorizontalScroll | RAF throttle, IntersectionObserver, ResizeObserver |
| 3 | ScrambleText, RandomReveal | RAF animation loop, Fisher-Yates shuffle |
| 4 | ImageCarousel, CarouselContainer | drag/touch, translateX transitions |

---

## Bug #1: Stimulus Does Not Work at All Inside Lookbook Previews

This was the biggest blocker. I finished implementing the controllers, opened Lookbook, and nothing was interactive. Chrome DevTools showed the `data-controller` attributes were present, but Stimulus was never connecting to them.

Everything worked fine when I opened the components directly in the dev server — the bug only appeared inside Lookbook previews. At first I couldn't figure out whether this was a Stimulus bug, a ViewComponent issue, or something wrong with my own code.

### Cause

Lookbook renders its previews inside an `<iframe>`. This iframe has its own separate layout file:

```erb
<%# app/views/layouts/previews/preview.html.erb %>
<head>
  <%= stylesheet_link_tag "application" %>
  <%# javascript_importmap_tags was missing! %>
</head>
```

Only `stylesheet_link_tag` was present — `javascript_importmap_tags` was missing entirely. CSS was loading, but JavaScript was not being loaded at all inside the iframe.

An iframe is a completely independent browsing context. Even if JavaScript is loaded in the parent page, Stimulus will not connect to elements inside the iframe unless JavaScript is explicitly loaded there too. Once you understand this, the problem is obvious — but it is easy to assume Lookbook handles this automatically.

### Fix

```erb
<head>
  <%= stylesheet_link_tag "application" %>
  <%= javascript_importmap_tags %>
</head>
```

One line added, problem solved. If you are using Lookbook with Rails 8 Importmap, this is the first thing to check. There were two preview layout files, and both needed to be updated:

- `app/views/layouts/previews/preview.html.erb`
- `app/views/previews/preview.html.erb`

If you are using Webpacker or esbuild instead of Importmap, replace `javascript_importmap_tags` with the appropriate tag helper for your build tool.

---

## Wave 1: DOM Manipulation Controllers

### TagInput

A controller that adds tags on Enter or comma, removes them via an x button, and deletes the last tag on Backspace. Tag input UIs are common, but getting them right requires careful attention to duplicate prevention, XSS defense, focus management, and keyboard accessibility.

```javascript
// app/javascript/controllers/tag_input_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["input", "container"]

  connect() {
    this.tags = []
  }

  addTag(event) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault()
      const value = this.inputTarget.value.trim().replace(/,$/, "")
      if (value && !this.tags.includes(value)) {
        this.tags.push(value)
        this._renderTag(value)
        this.inputTarget.value = ""
      }
    }
  }

  removeOnBackspace(event) {
    if (event.key === "Backspace" && this.inputTarget.value === "") {
      this._removeLastTag()
    }
  }

  removeTag(event) {
    const chip = event.currentTarget.closest("[data-tag]")
    const value = chip?.dataset.tag
    if (value) {
      this.tags = this.tags.filter(t => t !== value)
      chip.remove()
    }
  }

  _renderTag(value) {
    const chip = document.createElement("span")
    chip.dataset.tag = value
    chip.className = "tag-chip"
    chip.innerHTML = `${this._escapeHtml(value)} <button data-action="click->tag-input#removeTag">×</button>`
    this.containerTarget.insertBefore(chip, this.inputTarget)
  }

  _removeLastTag() {
    const last = this.containerTarget.querySelector("[data-tag]:last-of-type")
    if (last) {
      this.tags = this.tags.filter(t => t !== last.dataset.tag)
      last.remove()
    }
  }

  _escapeHtml(text) {
    return text.replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]))
  }
}
```

The `_escapeHtml` helper exists specifically to prevent XSS when injecting user input via `innerHTML`. Without it, a user could type `<img src=x onerror=alert(1)>` as a tag value and have it execute as HTML.

The ERB connection pattern:

```erb
<div data-controller="tag-input" class="tag-input-wrapper">
  <div data-tag-input-target="container">
    <input
      data-tag-input-target="input"
      data-action="keydown->tag-input#addTag keydown->tag-input#removeOnBackspace"
    />
  </div>
</div>
```

Multiple actions for the same event can be listed space-separated in `data-action`. This wires two action methods to the same `keydown` event on the input.

### CategoryTab — Sliding Underline Indicator Animation

The original implementation simply toggled a background color on the active tab. I replaced it with a sliding underline indicator. A background color toggle is simple to implement but visually stiff; an indicator that smoothly travels between tabs produces a much more polished UX.

The core of the implementation is reading the selected tab's `offsetLeft` and `offsetWidth` and applying those values to an indicator `<span>`:

```javascript
_moveIndicator(index) {
  const tab = this.element.querySelectorAll("[role='tab']")[index]
  if (!tab || !this.hasIndicatorTarget) return
  this.indicatorTarget.style.width = `${tab.offsetWidth}px`
  this.indicatorTarget.style.left = `${tab.offsetLeft}px`
}
```

Adding `transition: width 0.3s ease, left 0.3s ease` to the indicator element makes it glide smoothly when switching tabs. Since `offsetLeft` is relative to the parent element, the indicator's container needs `position: relative` for the positioning to be accurate.

On initial render, `connect()` should find the currently active tab and call `_moveIndicator` with its index. Without this, the indicator will be in the wrong position on page load and snap into place only after the first tab click.

### FileDropzone

A file drag-and-drop controller must handle all four events: `dragenter`, `dragover`, `dragleave`, and `drop`. The most common mistake is forgetting to call `event.preventDefault()` inside `dragover` — without it, the browser will not fire the `drop` event.

A subtler issue is that `dragleave` fires when the cursor moves over a child element, which triggers unexpected "drag exited" state changes. The counter technique solves this cleanly:

```javascript
connect() {
  this._dragCounter = 0
}

onDragEnter() {
  this._dragCounter++
  this.element.classList.add("drag-over")
}

onDragLeave() {
  this._dragCounter--
  if (this._dragCounter === 0) {
    this.element.classList.remove("drag-over")
  }
}

onDrop(event) {
  event.preventDefault()
  this._dragCounter = 0
  this.element.classList.remove("drag-over")
  const files = Array.from(event.dataTransfer.files)
  // handle files
}
```

---

## Wave 2: Scroll-Based Controllers

Scroll events must be throttled with RAF (requestAnimationFrame) without exception. Touching the DOM on every scroll event causes jank. Scroll events fire dozens of times per second, and calling `getBoundingClientRect()` in each handler triggers continuous forced reflows.

The RAF throttle pattern works like this: when a scroll event fires, schedule a RAF callback and set a flag to indicate a frame is already pending. The actual DOM update happens once in that next animation frame. If a frame is already scheduled, subsequent scroll events during that frame are no-ops.

```javascript
connect() {
  this._ticking = false
  this._onScroll = () => {
    if (!this._ticking) {
      requestAnimationFrame(() => {
        this._update()
        this._ticking = false
      })
      this._ticking = true
    }
  }
  window.addEventListener("scroll", this._onScroll, { passive: true })
}

disconnect() {
  window.removeEventListener("scroll", this._onScroll)
}
```

The `{ passive: true }` option tells the browser that this handler will never call `preventDefault()`, allowing the browser to optimize scroll performance. Without it, the browser must wait for each handler to finish before deciding whether to proceed with the scroll.

Failing to call `removeEventListener` in `disconnect()` leaves a dangling scroll listener after the controller is removed from the DOM. In a Turbo Drive app, controllers are disconnected on navigation, so cleanup is essential.

### ScrollReveal — Character-by-Character Color Reveal

This controller splits text into individual `<span>` elements, one per character, and changes their color progressively as the user scrolls. Characters start in a muted inactive color and transition to the active color as scroll progress advances.

```javascript
connect() {
  const text = this.element.textContent.trim()
  this.chars = text.split("")
  this.element.innerHTML = this.chars
    .map(c => c === " "
      ? " "
      : `<span style="color:${this.inactiveColorValue}">${c}</span>`)
    .join("")
  this.spans = this.element.querySelectorAll("span")
  // ... attach scroll listener
}

_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = (window.innerHeight * 0.8 - rect.top) / rect.height
  const count = Math.floor(this.spans.length * Math.min(Math.max(progress, 0), 1))
  this.spans.forEach((s, i) => {
    s.style.color = i < count ? this.activeColorValue : this.inactiveColorValue
  })
}
```

`window.innerHeight * 0.8` defines the trigger point at 80% of the viewport height. When the top of the element reaches this point during scroll, the reveal begins. Adjusting this multiplier changes when the effect starts relative to the viewport.

Space characters are passed through as plain HTML rather than being wrapped in `<span>`. Wrapping spaces would cause them to get colored too, but more importantly it maintains word spacing without requiring `&nbsp;` hacks.

### VideoScrubbing

This controller maps scroll position to `video.currentTime`, letting users scrub through a video by scrolling. An IntersectionObserver is used to attach the scroll listener only when the video is in the viewport, avoiding unnecessary scroll processing when the element is off-screen.

```javascript
_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = Math.min(Math.max(
    -rect.top / (rect.height - window.innerHeight), 0), 1)
  if (this.hasVideoTarget && this.videoTarget.duration) {
    this.videoTarget.currentTime = this.videoTarget.duration * progress
  }
}
```

The video element requires `muted playsinline preload="auto"` attributes. Without `preload="auto"`, the browser does not load video metadata before the user interacts with it, meaning `duration` is `NaN` and nothing works. The browser needs to know the total duration to compute `currentTime` from a progress value.

The video file must also be in a format that supports frame-accurate seeking — typically MP4/H.264. Setting `currentTime` on a video triggers a decode operation in the browser, so performance depends on file format and encoding.

### HorizontalScroll — Vertical Scroll Mapped to Horizontal Translation

This controller converts vertical scroll progress into a horizontal `translateX` transform inside a sticky container. The outer container is given a height of `100vh + scrollDistance` to create the scroll room, while the inner track stays fixed on screen via `position: sticky`.

This is the same technique used on many Apple product pages: content appears fixed while the user scrolls, and the progression of scrolling drives a horizontal pan.

```javascript
_setup() {
  const trackWidth = this.trackTarget.scrollWidth
  const scrollDistance = trackWidth - window.innerWidth
  this.element.style.height = `${window.innerHeight + scrollDistance}px`
  this._scrollDistance = scrollDistance
}

_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = Math.min(Math.max(-rect.top / this._scrollDistance, 0), 1)
  this.trackTarget.style.transform = `translateX(-${progress * this._scrollDistance}px)`
}
```

`scrollWidth` is the total scrollable width of the track element. Subtracting the viewport width gives the actual distance the track needs to travel. This distance also becomes the extra height added to the container to provide enough scroll room.

A ResizeObserver should call `_setup()` again whenever the viewport size changes, since `scrollDistance` depends on both the track content width and the viewport width.

---

## Wave 3: Text Animation Controllers

### ScrambleText

Text starts as a jumble of random characters and resolves left-to-right into the actual content. This is the effect commonly seen in hacker films and cyberpunk UIs. The implementation is a RAF loop that calculates which characters have "settled" based on elapsed time.

```javascript
_animate(timestamp) {
  if (!this._startTime) this._startTime = timestamp
  const elapsed = timestamp - this._startTime
  const progress = Math.min(elapsed / this.durationValue, 1)
  const settledCount = Math.floor(this._text.length * progress)

  const result = this._text.split("").map((char, i) => {
    if (i < settledCount) return char
    if (char === " ") return " "
    return this.charsetValue[Math.floor(Math.random() * this.charsetValue.length)]
  }).join("")

  this.element.textContent = result

  if (progress < 1) {
    this._rafId = requestAnimationFrame(this._animate.bind(this))
  }
}
```

If `cancelAnimationFrame(this._rafId)` is not called in `disconnect()`, the RAF loop continues running after the controller is removed from the DOM. An orphaned RAF loop has no visible effect but still executes on every frame, wasting CPU cycles and holding a reference to the element in memory.

An IntersectionObserver triggers the animation when the element enters the viewport. Using `threshold: 0.3` starts the animation when 30% of the element is visible:

```javascript
connect() {
  this._observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        this._startTime = null
        this._rafId = requestAnimationFrame(this._animate.bind(this))
        this._observer.unobserve(this.element)
      }
    },
    { threshold: 0.3 }
  )
  this._observer.observe(this.element)
}

disconnect() {
  if (this._rafId) cancelAnimationFrame(this._rafId)
  if (this._observer) this._observer.disconnect()
}
```

`unobserve` stops monitoring after the first trigger, preventing the animation from restarting every time the user scrolls past the element. If repeating the animation is desired, omit `unobserve` and reset `_startTime` to `null` instead.

### RandomReveal

Characters appear one by one in a random order, each transitioning from `opacity: 0; filter: blur(8px)` to fully visible. Where ScrambleText settles characters left-to-right, RandomReveal reveals them in a shuffled sequence using staggered `setTimeout` calls.

```javascript
connect() {
  const text = this.element.textContent.trim()
  const chars = text.split("")

  // Wrap each character in a span, initially hidden with blur
  this.element.innerHTML = chars.map((c, i) =>
    `<span data-index="${i}" style="opacity:0;filter:blur(8px);transition:opacity 0.4s,filter 0.4s">${c}</span>`
  ).join("")

  // Fisher-Yates shuffle
  const indices = chars.map((_, i) => i)
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]]
  }

  // Reveal characters in shuffled order with stagger
  const spans = this.element.querySelectorAll("span")
  indices.forEach((charIndex, order) => {
    setTimeout(() => {
      spans[charIndex].style.opacity = "1"
      spans[charIndex].style.filter = "blur(0)"
    }, this.delayValue + order * this.staggerValue)
  })
}
```

Fisher-Yates guarantees a truly uniform random distribution of permutations. The commonly seen `arr.sort(() => Math.random() - 0.5)` approach has a statistical bias toward certain orderings and should be avoided.

Since many `setTimeout` calls are queued, all of them must be cancelled in `disconnect()`. Store the IDs in an array:

```javascript
this._timers = []
indices.forEach((charIndex, order) => {
  const id = setTimeout(() => { ... }, delay)
  this._timers.push(id)
})

disconnect() {
  this._timers?.forEach(clearTimeout)
}
```

---

## Wave 4: Carousel Controllers

### ImageCarousel — Drag, Touch, Keyboard, and Button Navigation

The most important detail in a carousel is the drag threshold. Without a minimum drag distance, clicking on a slide image will accidentally trigger a slide change. A 50px threshold means: drag less than 50px and treat it as a click; drag 50px or more and advance the slide.

```javascript
onDragStart(event) {
  this._dragStartX = event.clientX ?? event.touches?.[0].clientX
  this._isDragging = true
}

onDragEnd(event) {
  if (!this._isDragging) return
  const endX = event.clientX ?? event.changedTouches?.[0].clientX
  const diff = this._dragStartX - endX

  if (Math.abs(diff) > 50) {
    diff > 0 ? this.next() : this.prev()
  }
  this._isDragging = false
}
```

The `event.clientX ?? event.touches?.[0].clientX` pattern handles both mouse and touch events in a single method. Mouse events expose `clientX` directly; touch events store the contact point in the `touches` array.

One important detail: in `touchend` events, the `touches` array is empty because the touch has ended. The coordinates of the completed touch are in `event.changedTouches`, not `event.touches`.

Autoplay is implemented with `setInterval`, but the interval should be reset whenever the user interacts manually. This prevents the awkward situation where the carousel auto-advances immediately after the user has just changed the slide:

```javascript
_resetAutoPlay() {
  if (this._autoPlayTimer) clearInterval(this._autoPlayTimer)
  if (this.autoPlayValue) {
    this._autoPlayTimer = setInterval(() => this.next(), this.autoPlayIntervalValue)
  }
}
```

Calling `_resetAutoPlay()` at the end of every `next()` and `prev()` call restarts the autoplay countdown from zero after each manual interaction.

Keyboard accessibility is also worth including. Add `keydown->image-carousel#onKeydown` to `data-action` and handle `ArrowLeft` and `ArrowRight`. The carousel container needs `tabindex="0"` to be focusable.

### CarouselContainer — Responsive Visible Item Count

A ResizeObserver recalculates item widths whenever the container dimensions change. In a responsive layout, the number of visible items changes with viewport size. The `visible` value can be updated via media queries, and the ResizeObserver picks up the change and recalculates the layout.

```javascript
_updateLayout() {
  const items = this.itemTargets
  if (!items.length) return
  const containerWidth = this.element.offsetWidth
  const gap = 16
  const itemWidth = (containerWidth - gap * (this.visibleValue - 1)) / this.visibleValue
  items.forEach(item => {
    item.style.minWidth = `${itemWidth}px`
    item.style.maxWidth = `${itemWidth}px`
  })
  this._itemWidth = itemWidth + gap
  this._goTo(this._currentIndex)
}
```

Both `minWidth` and `maxWidth` are set because in a flex container, items can grow or shrink from their specified `width`. Setting only `width` may not override flex behavior; constraining both min and max ensures the item is exactly the calculated size.

The final `_goTo(this._currentIndex)` call recalculates the `translateX` value for the current slide after the layout has changed. Without this, the active slide's position would be stale after a resize.

---

## Verification: Accessing the Iframe with Playwright

Because Lookbook previews are rendered inside an iframe, standard Playwright locators cannot reach the preview DOM. The `frameLocator` API is required. An iframe's DOM is entirely separate from the parent page's DOM.

```javascript
// Access the iframe's document
const iframe = page.frameLocator('iframe[title="viewport"]')

// Verify Stimulus connection and read computed values
const result = await iframe.locator('body').evaluate((el) => {
  const ctrl = el.querySelector('[data-controller="category-tab"]')
  return {
    connected: !!ctrl,
    indicatorLeft: ctrl?.querySelector('[data-category-tab-target="indicator"]')?.style.left
  }
})
```

The `evaluate()` callback runs inside the browser context. To verify that a Stimulus controller is working, check DOM attributes and computed styles rather than trying to access the controller instance directly — Stimulus does not expose instances in a standard way on DOM elements.

Verification points for each controller:

- **CategoryTab**: Confirm the indicator's `left` value changes after clicking a tab
- **TagInput**: Confirm a `data-tag` chip appears after pressing Enter
- **ScrambleText**: Confirm the element's text matches the original after the animation completes
- **ImageCarousel**: Confirm the track's `translateX` value changes after clicking next
- **CarouselContainer**: Confirm `translate3d` updates after clicking next

---

## Summary

Key things to watch for when using Stimulus with Rails and Lookbook:

1. **Add `javascript_importmap_tags` to the preview layout** — without it, Stimulus does not load inside the iframe at all
2. **Always RAF-throttle scroll event handlers** — also set `{ passive: true }` on the listener
3. **Clean up everything in `disconnect()`** — scroll listeners, RAF callbacks, `setTimeout` timers, IntersectionObservers, and ResizeObservers all need explicit cleanup
4. **Use `preload="auto"` on scrubbing videos** — without it, `duration` is `NaN` and scrubbing does nothing
5. **Use `frameLocator` to reach Lookbook previews in Playwright** — standard locators cannot access iframe content

---

## Key Takeaways

- **The Lookbook iframe bug** is the first thing to check when setting up a Rails 8 Importmap project with Lookbook. Adding `javascript_importmap_tags` to the preview layout file is a one-line fix, but without it nothing in Stimulus will work inside any preview.
- **RAF throttling is not optional** for scroll handlers that touch the DOM. The pattern is always the same — copy it once and reuse it across every scroll-based controller.
- **Thorough `disconnect()` cleanup** is critical in Turbo Drive applications. Scroll listeners, RAF loops, setTimeout callbacks, IntersectionObservers, and ResizeObservers all outlive the controller if not explicitly torn down, causing memory leaks and subtle bugs on subsequent navigations.
- **The drag threshold** in carousel controllers is a UX detail that users will notice even if they cannot articulate what is wrong. A 50px minimum drag distance cleanly separates intent-to-click from intent-to-swipe.
- **Fisher-Yates shuffle** produces a statistically uniform distribution. The `array.sort(() => Math.random() - 0.5)` shortcut is tempting but introduces bias — use Fisher-Yates for any shuffle that needs to appear truly random.
- **IntersectionObserver for animation triggers** is more performant than checking `getBoundingClientRect()` on every scroll event. For one-shot animations like ScrambleText, calling `unobserve` after the first trigger eliminates ongoing observation overhead.
