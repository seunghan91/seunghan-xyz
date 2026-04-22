---
title: "Analyzing Reference Design to Extend Component System — Svelte 5 + Storybook 10"
date: 2026-02-27
draft: false
tags: ["Svelte 5", "Storybook", "Design System", "CSS Custom Properties", "Components", "Reference Analysis", "Vite 7"]
categories: ["Frontend"]
description: "Analyzing the visual structure of a reference app, adding 9 components to existing 23 while establishing design tokens and template system. Following the structure but maintaining the existing dark theme."
cover:
  image: "/images/og/storybook-reference-design-component-system.png"
  alt: "Storybook Reference Design Component System"
  hidden: true
---

When you receive a reference app for a project that already has a reasonably mature design system, the temptation is to either copy it pixel-for-pixel or ignore it entirely. Neither option is good. Rewriting everything from scratch discards existing work; ignoring the reference breaks alignment with the designer. This post documents how I found the balance: absorbing the **structural patterns** from the reference while keeping the existing dark glassmorphism theme intact.

---

## Background

The existing project already had a solid foundation:

- **23 shared components** across 8 categories: layout, navigation, input, overlay, card, data-display, social, feedback
- **CSS Custom Properties-based design tokens** covering colors, typography, spacing, radius, shadows, and glassmorphism effects
- **Storybook 10 + Svelte 5** environment with 51 story variants
- **Dark theme glassmorphism** design language

The designer sent over a reference app — a light-mode travel planner with a green accent palette — and the goal was to absorb the layout ideas from it **without dismantling the existing visual system**.

Because the existing system was already well-structured, rebuilding from scratch was never on the table. Instead, the starting question was: "What structural patterns from the reference can we adopt?"

---

## Step 1: Visual Hacking the Reference

The first step in analyzing a reference app is to decompose it into an ASCII layout diagram. When you look at a polished screenshot, your eyes jump to colors and details. Abstracting it to ASCII forces you to think only about the **skeletal layout**.

```
+-------------------+-------------------------+
|  LEFT PANEL       |  RIGHT PANEL            |
|  (Input/Creation) |  (Result/Visualization) |
|                   |                         |
|  [AI Chat Input]  |  [Trip Header]          |
|  [Tag Chips]      |  [MAP + Route Lines]    |
|  [Budget Slider]  |  [Route Highlights]     |
|  [Duration Btns]  |  [Day-by-Day Accordion] |
|  [CTA Button]     |                         |
+-------------------+-------------------------+
|  Bottom Tab: [Home] [AI] [Map] [Profile]    |
+--------------------------------------------- +
```

From this single diagram, the component inventory and placement become clear. The 2-Panel split — left for user input, right for results and visualization — is the defining structural pattern.

### Visual Difference Analysis

Before deciding what to adopt, it is equally important to decide what to leave behind. This table documents every style difference between the reference and the existing project:

| Element | Reference | Existing Project |
|---------|-----------|-----------------|
| Mode | Light (white bg) | Dark (glassmorphism) |
| Accent | Green (#4ADE80) | Teal (#20B2AA) |
| Cards | White + shadow | Semi-transparent glass + border |
| Radius | 16–24px | 12–16px |
| Icons | Filled | Outline |
| Layout | 2-column split | Single column + tabs |
| Schedule view | Day accordion | Date tabs + list |
| Tag input | Pill chip selection | Direct text input |

Mode, color, and icon style are all items on the **do not adopt** list. Layout structure, schedule display pattern, and tag input mechanism are the **adopt** list.

### 6 Structural Patterns to Absorb

Once the style differences are mapped out, the structural patterns that are worth adopting become obvious:

1. **Input → Result 2-Panel** (left: input, right: visualization)
2. **Tag Chip System** (visual selection of categories and interests)
3. **Budget Range Slider** (slider-based budget range instead of numeric input)
4. **Day-by-Day Accordion** (collapsible schedule, one accordion per day)
5. **Route Map Visualization** (dashed route lines + numbered markers)
6. **Section Header** (title + subtitle + action button — standard section-level layout unit)

Core principle: **structure from the reference, style from the existing dark theme**.

---

## Step 2: Identifying New Components Needed

With the structural patterns confirmed, mapping them against the existing component list reveals the gaps — the things that do not yet exist. This mapping step is critical. **Distinguishing what to build new from what to reuse** is how you prevent duplicate development.

| Reference Element | Existing Component | Decision |
|------------------|-------------------|----------|
| Tag Chips | — | **New**: Chip |
| Budget Slider | — | **New**: RangeSlider |
| Duration [7][10][14] | — | **New**: SegmentedControl |
| Day Accordion | — | **New**: Accordion |
| Route Highlight Card | — | **New**: RouteHighlight |
| Numbered Map Marker | — | **New**: MapMarker |
| Section Title | — | **New**: Section |
| 2-Column Panel | — | **New**: SplitPanel |
| Schedule Timeline Item | (inline in page) | **Extract**: ScheduleItem |
| CTA Button | Button.svelte | Reuse existing |
| Modal | Modal.svelte | Reuse existing |
| Budget Bar | BudgetProgress.svelte | Reuse existing |

Result: **10 existing components reused, 9 new components created**.

ScheduleItem is worth calling out separately. It was not truly "new" — the pattern already existed, written inline inside a page component. Extracting it into a standalone component is about formalizing an interface, not inventing new logic. Classifying it as an "extract" rather than "new" keeps the scope honest.

---

## Step 3: Extending Design Tokens

Before writing any component code, the token system was extended first. If you write components without tokens, hardcoded values scatter across every file. When you later want to change the theme or add light mode support, you have to hunt through every component.

Six new token groups were added to the existing `tokens.css`:

```css
:root {
  /* ...existing tokens preserved... */

  /* Chip / Tag System */
  --chip-height:          32px;
  --chip-padding-x:       12px;
  --chip-radius:          9999px;    /* pill shape */
  --chip-bg:              rgba(32, 178, 170, 0.10);
  --chip-bg-selected:     #20B2AA;
  --chip-text:            rgba(255, 255, 255, 0.55);
  --chip-text-selected:   #FFFFFF;

  /* Accordion System */
  --accordion-header-height: 48px;
  --accordion-bg-open:    rgba(255, 255, 255, 0.03);

  /* Slider / Range Input */
  --slider-track-height:  4px;
  --slider-track-fill:    #20B2AA;
  --slider-thumb-size:    20px;

  /* Split Panel */
  --panel-left-width:     400px;
  --panel-left-max:       40%;

  /* Section Header */
  --section-title-size:   17px;
  --section-title-weight: 600;
  --section-spacing:      32px;
}
```

With tokens defined as CSS variables, switching to a light theme later is straightforward: add a `data-theme="light"` attribute to the root element and override the token values. No component code needs to change.

---

## Step 4: Parallel Component Development

All 9 components were developed in parallel across 6 agents. Here is the key design decision for each.

### Chip (input/)

A selectable tag or filter chip. The implementation looks simple, but getting accessibility right is the real challenge. Because a chip is a toggle, `aria-pressed` is the correct attribute — not `role="checkbox"`. Checkboxes are for form submission; chips are for UI filtering.

```svelte
<button class="chip" class:selected {onclick} aria-pressed={selected}>
  {label}
</button>

<style>
  .chip {
    height: var(--chip-height);
    padding: 0 var(--chip-padding-x);
    border-radius: var(--chip-radius);
    background: var(--chip-bg);
    color: var(--chip-text);
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 200ms ease;
    min-height: 44px; /* iOS touch target minimum */
  }
  .chip.selected {
    background: var(--chip-bg-selected);
    color: var(--chip-text-selected);
    box-shadow: 0 0 12px rgba(32, 178, 170, 0.25);
  }
  .chip:focus-visible {
    outline: 2px solid var(--chip-bg-selected);
    outline-offset: 2px;
  }
</style>
```

The `min-height: 44px` comes from iOS Human Interface Guidelines. Even a visually small chip needs a sufficiently large touch target.

### Accordion (data-display/)

Used for Day-by-Day schedule display. Supports a chevron rotation animation and an optional badge. The Svelte 5 `{@render children?.()}` pattern replaces the legacy slot API.

```svelte
<script lang="ts">
  let { title, badge, children } = $props<{
    title: string;
    badge?: string;
    children?: Snippet;
  }>();
  let isOpen = $state(false);
  const toggle = () => (isOpen = !isOpen);
</script>

<div class="accordion" class:open={isOpen}>
  <button class="accordion-header" onclick={toggle} aria-expanded={isOpen}>
    <span class="accordion-chevron" style="transform: rotate({isOpen ? 90 : 0}deg)">›</span>
    <span class="accordion-title">{title}</span>
    {#if badge}<span class="accordion-badge">{badge}</span>{/if}
  </button>
  {#if isOpen}
    <div class="accordion-content">{@render children?.()}</div>
  {/if}
</div>
```

`aria-expanded` tells screen readers whether the accordion is open or closed. The chevron rotation is handled via inline style rather than a CSS class transition, directly leveraging Svelte 5 reactivity.

### SplitPanel (layout/)

Desktop: left–right split. Mobile (≤768px): vertical stack. Accepting `leftWidth` as a prop and injecting it as a CSS variable gives the parent component flexible control over the panel proportions without needing extra props.

```svelte
<div class="split-panel" style="--sp-left-width: {leftWidth};">
  <aside class="split-left">{@render left?.()}</aside>
  <main class="split-right">{@render right?.()}</main>
</div>

<style>
  .split-panel {
    display: flex;
    gap: var(--sp-gap, 24px);
    height: 100%;
  }
  .split-left {
    width: var(--sp-left-width, var(--panel-left-width));
    max-width: var(--sp-left-max, var(--panel-left-max));
    flex-shrink: 0;
    overflow-y: auto;
  }
  .split-right {
    flex: 1;
    min-width: 0; /* prevents flex child overflow */
    overflow-y: auto;
  }
  @media (max-width: 768px) {
    .split-panel { flex-direction: column; }
    .split-left { width: 100%; max-width: 100%; }
  }
</style>
```

`min-width: 0` on flex children is easy to forget. Without it, long content inside the right panel overflows its parent container.

### RangeSlider (input/)

The budget slider uses a native `<input type="range">` with its default styles fully reset. A CSS gradient technique renders the filled track: the `--fill` custom property is calculated from the current value in JavaScript and injected as an inline style.

```css
.range-input {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: var(--slider-track-height);
  background: linear-gradient(to right,
    var(--slider-track-fill) 0%,
    var(--slider-track-fill) var(--fill),
    var(--slider-track-bg) var(--fill),
    var(--slider-track-bg) 100%
  );
  border-radius: 9999px;
  outline: none;
}

.range-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: var(--slider-thumb-size);
  height: var(--slider-thumb-size);
  border-radius: 50%;
  background: var(--slider-track-fill);
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(32, 178, 170, 0.4);
}
```

### SegmentedControl (input/)

A single-select button group for options like `[3 days][5 days][7 days][10 days]`. The component uses `role="radiogroup"` with `aria-checked` on each option to preserve the semantic meaning of radio buttons, while keeping full visual control via custom CSS. Using actual `<input type="radio">` elements would require significantly more effort to style consistently across browsers.

```svelte
<div role="radiogroup" aria-label={label} class="segmented-control">
  {#each options as option}
    <button
      role="radio"
      aria-checked={value === option.value}
      class:active={value === option.value}
      onclick={() => onchange(option.value)}
    >
      {option.label}
    </button>
  {/each}
</div>
```

### ScheduleItem (card/)

This was an extraction, not a new creation. A pattern of timeline dot + time + category badge + location was repeated inline across multiple pages. Extracting it into a named component means style changes now happen in one place. Before the extraction, updating the visual appearance of a timeline item required finding and editing every occurrence manually.

### Section, RouteHighlight, MapMarker

- **Section**: Title + subtitle + right-aligned action button slot. The standard unit for dividing a page into named sections.
- **RouteHighlight**: Location name + short description + image thumbnail. Used in the right panel of a split layout to list waypoints along a route.
- **MapMarker**: A circular marker with a number inside. Used as `<MapMarker number={3} />`.

---

## Step 5: Page Template System

Building 9 standalone components is not enough on its own. The next step is to formalize the **page templates** — the recurring layout patterns that will appear across multiple pages. A template encodes "which components go where" so that future page development does not require repeating layout decisions from scratch.

| Template | Structure | Applied Pages |
|----------|-----------|--------------|
| **SplitPanelTemplate** | Left (Input) + Right (Result) | AI recommendations, map planner |
| **DayTimelineTemplate** | DateChips + Day Accordion | Itinerary management |
| **ListWithFilterTemplate** | Chip filter + list | Expenses, shopping, checklist |
| **CardGridTemplate** | Header + card grid | Trip list, photo album |
| **FormSectionTemplate** | Section + input components | Trip creation, profile editing |

For example, `SplitPanelTemplate` in use looks like this:

```svelte
<SplitPanelTemplate>
  {#snippet left()}
    <AiChatInput />
    <ChipGroup options={interestOptions} bind:selected />
    <RangeSlider label="Budget" bind:value={budget} min={0} max={500000} />
    <SegmentedControl options={durationOptions} bind:value={duration} />
    <Button variant="primary" onclick={handleGenerate}>Generate Itinerary</Button>
  {/snippet}
  {#snippet right()}
    <TripHeader trip={generatedTrip} />
    <RouteMap waypoints={waypoints} />
    <Accordion title="Day 1">
      <ScheduleItem time="09:00" place="Incheon Airport" category="Transport" />
    </Accordion>
  {/snippet}
</SplitPanelTemplate>
```

With this template in place, any new AI feature page can be scaffolded by dropping in the template and filling the snippets, rather than rebuilding the two-column layout from scratch every time.

---

## Troubleshooting Notes

### Storybook 10 + Vite 7 Compatibility

Storybook 8.x does not support Vite 7. Its peer dependency is locked to `vite@"^4 || ^5 || ^6"`, which means installation either fails outright or produces build errors at runtime when used with Vite 7. Upgrading to Storybook 10.2.15 was necessary.

```bash
# This does not work
npm i @storybook/svelte-vite@8.6.14  # Vite 7 unsupported, peer dep error

# This works
npm i storybook@10.2.15 @storybook/svelte-vite@10.2.15
```

When upgrading Storybook across major versions, always check the official migration guide first. There are multiple breaking changes between 8.x and 10.x.

### @storybook/blocks vs @storybook/addon-docs

In Storybook 10, `@storybook/blocks` no longer exists as a separate package. In 8.x, it was installed and imported independently. In 10.x, it was merged into `@storybook/addon-docs`. Any MDX file using the old import path will fail to resolve the module.

```js
// 8.x — fails with "Cannot find module"
import { Meta } from '@storybook/blocks';

// 10.x — correct
import { Meta } from '@storybook/addon-docs/blocks';
```

`@storybook/addon-docs` also needs to be explicitly listed in the `addons` array of `main.js`, otherwise MDX files are silently ignored during the build.

```js
// .storybook/main.js
export default {
  addons: [
    '@storybook/addon-docs',
    // ...other addons
  ],
};
```

### Svelte 5 Runes Migration

Components written with the Svelte 4 `export let` syntax cause prop detection to fail in Storybook. Storybook's Svelte 5 integration is designed around the runes API (`$props()`), so components still using legacy syntax will have empty ArgsTable panels or incorrectly displayed props. 26 page components were migrated in bulk to the `$props()` syntax.

```svelte
// Before (Svelte 4)
export let trip;
export let user = null;

// After (Svelte 5 runes)
let { trip, user = null }: { trip: Trip; user?: User | null } = $props();
```

Specifying TypeScript types inside the `$props()` destructuring also makes the type information visible in Storybook's ArgsTable.

### formatCurrency Duplicated Across 13 Files

The same `formatCurrency` function was defined inline in 13 different files. It was extracted into a shared utility, with one exception: one file used a slightly different implementation that did not divide by 100. That variant was kept local and documented explicitly, because blindly unifying "almost identical" implementations is a common source of subtle bugs.

```ts
// src/lib/utils/format.ts (shared utility)
export function formatCurrency(amount: number, currency = 'KRW'): string {
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}
```

### Layout.svelte as a 428-Line Monolith

The `Layout.svelte` component had grown to 428 lines, handling navigation, menus, modals, and tab bars all in one file. It was split into four independent components:

- `TopNavBar.svelte` (152 lines) — top navigation bar
- `PillBottomNav.svelte` (79 lines) — bottom tab navigation
- `UserMenu.svelte` (74 lines) — user menu dropdown
- `SearchModal.svelte` (119 lines) — search modal

The split criterion was: "can this be replaced independently?" For example, swapping out the bottom tab style now requires touching only `PillBottomNav.svelte`, not a 428-line file where the tab bar logic is tangled with the top nav and modal code.

---

## Final Results

| Metric | Before | After |
|--------|--------|-------|
| Shared components | 23 | **32** (+9) |
| Design token categories | 9 | **15** (+6) |
| Storybook variants | 51 | **~80** |
| Page templates | 0 | **5** |
| Persona workflows | Undefined | **10** |

---

## Key Takeaways

**The practical approach is not to copy a reference app but to extract only its structural patterns and absorb them into the existing system.**

Colors, fonts, and mode (dark/light) stay as-is in the existing token system. Layout patterns — split panels, accordions, chip filters — get adopted. The result is an expanded UX that maintains visual consistency.

More specifically:

1. **Separate style from structure.** Take the "what exists" from the reference; reinterpret the "how it looks" to fit the existing system.
2. **Define tokens before writing components.** Hardcoding values inside components means touching every component when the theme changes. Tokens centralize that control.
3. **Distinguish extraction from creation.** Formalizing an existing inline pattern into a named component is an extraction. Only genuinely new concepts count as new components. Keeping the scope honest prevents inflated estimates.
4. **Build templates, not just components.** A library of components is more useful when common combinations are formalized as templates. Templates eliminate repeated layout decision-making on every new page.
5. **Verify peer dependencies before upgrading major versions.** Storybook, Vite, and Svelte each have breaking changes across major versions. Checking the peer dependency matrix before upgrading saves hours of debugging confusing build errors.
