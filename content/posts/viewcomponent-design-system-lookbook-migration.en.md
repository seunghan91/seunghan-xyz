---
title: "Migrating a ViewComponent Design System to Lookbook — Rails 8 + Tailwind CSS 4 War Stories"
date: 2026-03-10
draft: false
tags: ["Rails 8", "ViewComponent", "Lookbook", "Design Tokens", "CSS Custom Properties", "Tailwind CSS 4", "Component System"]
description: "Real-world issues encountered while migrating 47 ViewComponents to a warm orange design system with Lookbook previews. CSS variable fallback traps, @!group URL mapping, String#[] TypeError, and more."
cover:
  image: "/images/og/viewcomponent-design-system-lookbook-migration.png"
  alt: "ViewComponent Design System Lookbook Migration"
  hidden: true
---

I migrated 47 ViewComponents in a Rails 8 project to a warm orange theme and built a full Lookbook preview system. Here are the real issues I ran into.

---

## Background

The project already had:
- **47 ViewComponents** across 15 categories (input, layout, navigation, card, typography, etc.)
- **CSS Custom Properties** based design tokens (`tokens.css`)
- **Tailwind CSS 4** + Propshaft asset pipeline

The goal was to adopt a BMC (Buy Me a Coffee) inspired warm orange theme with a dark sidebar and stone palette, and build **comprehensive Lookbook previews**.

---

## Issue 1: The Design Doc Was Done But The Code Wasn't

### Problem: "I updated the tokens... wait, I didn't?"

```css
/* Original tokens.css (33 lines) */
:root {
  --color-primary: #0000FF;
  --radius: 0px;
}
```

I wrote a thorough design system document specifying warm orange `#FF6B2C`, tiered border radius, surface tokens, etc. I even created 15 new components using the new design. But **I never actually updated `tokens.css`**. The document was perfect; the code was untouched.

### Fix

```css
/* Updated tokens.css (130 lines) */
:root {
  --color-primary-500: #FF6B2C;
  --color-primary: var(--color-primary-500);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius: var(--radius-md);  /* backward compat */
  --surface-sidebar: #1E293B;
  --border-default: #E7E5E4;
  /* ... full 120-line token system */
}
```

**Lesson**: Writing a design spec is not implementing it. Always add an **audit step** to verify the actual code matches the document.

---

## Issue 2: ViewComponent 4.x API Change

### Problem: `preview_paths` silently fails

```ruby
# Old API (ViewComponent 3.x)
config.view_component.preview_paths << Rails.root.join("test/components/previews")

# New API (ViewComponent 4.x)
config.view_component.previews.paths << Rails.root.join("test/components/previews")
```

RuboCop caught this automatically, but it's an easy miss if you're copying config from older tutorials.

### Bonus Issue: Wrong Rails App on Port 3000

Navigated to `localhost:3000/lookbook` and got a routing error from **a completely different Rails project**. A stale Puma process from another project was holding the port.

```bash
kill $(lsof -ti:3000)
rm -f tmp/pids/server.pid
bin/rails server -p 3000
```

**Lesson**: When juggling multiple Rails projects, always verify which app owns the port.

---

## Issue 3: CSS Variable Fallback — Safe at Runtime, Confusing in Code

### Problem: `#0000FF` still in 26 places

```ruby
# GnbComponent active style
"background: var(--color-primary, #0000FF); color: #fff;"
```

Since `tokens.css` now defines `--color-primary`, the `#0000FF` fallback is never used at runtime. **But having legacy hex codes scattered across 47 components is misleading** — it looks like the migration isn't done.

### Fix Strategy

- `var(--color-primary, #0000FF)` → `var(--color-primary-500)` (explicit token reference)
- `#fff` → `var(--text-inverse)`
- `#e0e0e0` → `var(--border-default)`

Full audit with grep:

```bash
grep -r "#0000FF" app/components/     # 5 files
grep -r "#e0e0e0" app/components/     # 13 files
grep -r "radius, 0)" app/components/  # 8 files
```

---

## Issue 4: `String#[]` TypeError in Lookbook Previews

### Problem: `no implicit conversion of Symbol into Integer`

Batch-tested all 344 preview URLs and found **10 returning 500 errors**.

The root cause was a type safety issue introduced during CSS variable refactoring:

```erb
<!-- After refactoring: DANGEROUS -->
<%= category[:label] || category["label"] || category %>
```

When `category` is a String like `"Design"`, calling `"Design"[:label]` invokes `String#[]` which expects an Integer index, not a Symbol. This raises `TypeError`.

### Fix

```erb
<%= category.is_a?(Hash) ? (category[:label] || category["label"]) : category %>
```

**Affected components:**
- `CategoryTabComponent` — categories can be string arrays
- `SlidingHighlightMenuComponent` — items can be string arrays
- `TableComponent` — columns/rows can be string arrays

For TableComponent, I added **auto-normalization**:

```ruby
def normalize_columns(columns)
  columns.map.with_index do |col, i|
    col.is_a?(Hash) ? col : { label: col.to_s, key: i }
  end
end
```

**Lesson**: When extending component props to accept Hash, always check if existing callers pass Strings. `obj[:key]` is only safe on Hash.

---

## Issue 5: Lookbook `@!group` Changes URL Structure

### Problem: 42 URLs return 404 but the pages exist

```ruby
# Button Preview
# @!group Sizes
def small; end
def medium; end
def large; end
# @!endgroup
```

Lookbook's `@!group` annotation **merges grouped methods into a single URL**:
- `/atoms/button/small` → 404
- `/atoms/button/sizes` → 200 (shows small + medium + large together)

My test script was building URLs from method names, not from Lookbook's actual routing.

### Fix

Extract actual URLs from Lookbook's rendered sidebar:

```bash
curl -sL "http://localhost:3000/lookbook" | \
  grep -o 'href="/lookbook/inspect/[^"]*"' | \
  sort -u > actual_urls.txt
# 310 actual URLs → all 200 OK
```

---

## Final Results

| Metric | Before | After |
|--------|--------|-------|
| tokens.css | 33 lines, `#0000FF` | 130 lines, warm orange `#FF6B2C` |
| Components | 47 (legacy colors) | 62 (21 modified/added, CSS variables) |
| Lookbook previews | None | 310 URLs, 7 levels (atoms→pages→ux_flows) |
| Hardcoded colors | `#0000FF` ×5, `#e0e0e0` ×13 | 0 |
| 500 errors | 10 | 0 |

---

## Key Takeaways

1. **Design doc ≠ implementation** — No matter how good the spec is, always audit actual code against it.
2. **CSS variable fallbacks are a trap** — `var(--token, #legacy)` works at runtime but creates false confidence. Remove fallbacks after token migration.
3. **Ruby's `String#[]` is type-unsafe** — `obj[:key]` crashes on Strings. Always guard with `is_a?(Hash)` in polymorphic components.
4. **Lookbook `@!group` merges URLs** — Don't assume method names map 1:1 to preview URLs.
5. **Port collisions are common** — Use `lsof -ti:PORT` habitually when working across multiple Rails apps.
6. **Batch-verify with curl** — Don't eyeball hundreds of previews. Automate with HTTP status codes.
