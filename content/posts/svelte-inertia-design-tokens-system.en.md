---
title: "Establishing Design Token System Across 8 Svelte 5 + Inertia.js Projects"
date: 2026-03-03
draft: false
tags: ["Svelte 5", "Inertia.js", "Design Tokens", "Tailwind CSS", "Design System", "CSS Custom Properties"]
categories: ["Frontend"]
description: "Auditing design system adoption across 8 Rails + Inertia.js + Svelte 5 projects and bulk-building CSS Custom Properties based design tokens for unadopted projects."
cover:
  image: "/images/og/svelte-inertia-design-tokens-system.png"
  alt: "Svelte Inertia Design Tokens System"
  hidden: true
---

When you run multiple projects on a Rails + Inertia.js + Svelte 5 stack, one persistent problem tends to surface: **each project ends up with its own inconsistent standards for colors, typography, and spacing**. One project has everything neatly organized in `tailwind.config.js`, while another is littered with hardcoded values like `bg-[#3182F6]`.

The problem compounds as the number of projects grows. Every new project means redefining colors from scratch, rebuilding button styles, and re-establishing font size conventions. Even when a component from one project is worth reusing in another, the differing design foundations make it impossible to drop it in as-is.

This post documents the process of auditing design token adoption across all projects and establishing a consistent system for those that lacked one.

---

## 1. The Audit: Checking Design System Health Across 8 Projects

The audit evaluated every Svelte + Inertia.js project against four criteria.

| Criterion | What Was Checked |
|-----------|-----------------|
| **UI Components** | Presence of `components/ui/` directory and component count |
| **Design Tokens** | Existence of `tokens.css` or a CSS variable definition file |
| **Theme System** | Color/typography extensions in `theme.ts` or `tailwind.config.js` |
| **Storybook** | Presence of `.storybook/` directory and story files |

These four criteria were chosen deliberately. Component count reflects how mature the project's reuse culture is. The presence of a token file determines whether there is a single source of truth for design values. The theme system reveals how deeply Tailwind is integrated. Storybook indicates whether components can be developed and documented in isolation.

### Audit Results

```
Project A  ✅ Tokens + Storybook + categorized components → Fully adopted
Project B  ⚠️ 18 UI components + design-system docs but no token file
Project C  ⚠️ 22 UI components + theme.ts but no token system
Project D  ❌ 15 UI components but no tokens/theme (boilerplate)
Project E  ❌ Only 5 UI components, no tokens/theme
Project F  ❌ Domain-specific components only, no shared UI
Project G  ❌ Only 1 UI component, effectively no design system
Project H  ❌ Frontend structure itself is incomplete
```

Out of 8 projects: **1 fully adopted, 2 partially adopted, 5 not adopted**. Worse than expected.

The partial-adoption cases (B and C) turned out to be the most difficult to address. With more than 10 components already built, the refactoring cost was higher than for the unadopted projects. Project C in particular had color values defined as TypeScript constants in `theme.ts`. Migrating these to CSS Custom Properties required finding every `COLORS.primary` reference in the codebase and replacing it with `var(--color-primary)`.

---

## 2. Reference Analysis: What the Fully Adopted Project Got Right

The fully adopted project's design system structure served as the reference model.

```
app/frontend/
├── css/
│   └── tokens.css              ← CSS Custom Properties (the core)
├── components/
│   ├── card/
│   ├── data-display/
│   ├── feedback/
│   ├── input/
│   ├── layout/
│   ├── navigation/
│   ├── overlay/
│   └── social/
├── stories/
│   ├── component/              ← Per-component stories
│   ├── overview/               ← Project overview docs
│   └── style/                  ← Colors, typography, spacing docs
└── .storybook/
    ├── main.js
    └── preview.js
```

The core of the system was `tokens.css`. Every design value was defined as a CSS Custom Property, referenced by both `tailwind.config.js` and Svelte component `<style>` blocks.

The component directory structure was also significant: components are organized by **UI pattern** rather than by domain. Categories like `card/`, `feedback/`, and `overlay/` are universally reusable regardless of the service. By contrast, most unadopted projects had domain-coupled structures like `components/PostCard.svelte` or `components/UserProfile.svelte`, which are not transferable across projects.

### tokens.css Structure (8 Sections)

```css
:root {
  /* 1. Colors — Primary (50-900 scale) */
  --color-primary-50: #EBF4FF;
  --color-primary-100: #DBEAFE;
  --color-primary-500: #3182F6;
  --color-primary-600: #2563EB;
  --color-primary-900: #1E3A8A;

  /* 2. Colors — Semantic (success, warning, error, info) */
  --color-success: #05C072;
  --color-success-bg: #E8FFF5;
  --color-warning: #F5A623;
  --color-warning-bg: #FFF8E6;
  --color-error: #F04452;
  --color-error-bg: #FFF0F1;
  --color-info: #3182F6;

  /* 3. Colors — Gray Scale */
  --color-gray-50: #F9FAFB;
  --color-gray-100: #F2F4F6;
  --color-gray-200: #E5E8EB;
  --color-gray-400: #9EA6B2;
  --color-gray-600: #6B7684;
  --color-gray-900: #191F28;

  /* 4. Colors — Background, Surface, Border, Text */
  --color-bg-primary: #FFFFFF;
  --color-bg-surface: #F9FAFB;
  --color-border: #E5E8EB;
  --color-text-primary: #191F28;
  --color-text-secondary: #6B7684;
  --color-text-disabled: #9EA6B2;

  /* 5. Typography */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;
  --font-size-xs: 12px;
  --font-size-sm: 13px;
  --font-size-base: 15px;
  --font-size-lg: 17px;
  --font-size-xl: 20px;
  --font-size-2xl: 24px;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --line-height-tight: 1.3;
  --line-height-normal: 1.6;

  /* 6. Spacing (8px grid) */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-smd: 12px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --spacing-2xl: 48px;

  /* 7. Border Radius, Shadows, Z-Index */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.06), 0 4px 6px rgba(0, 0, 0, 0.04);
  --z-dropdown: 100;
  --z-modal: 200;
  --z-toast: 300;

  /* 8. Transitions, Touch Target */
  --transition-fast: 100ms ease;
  --transition-normal: 200ms ease;
  --transition-slow: 300ms ease;
  --touch-target-min: 44px;
}
```

The 8-section structure was borrowed from the reference project, with a few additions over time. Tokenizing z-index values like `--z-dropdown`, `--z-modal`, and `--z-toast` proactively prevents the classic bug where a dropdown appears behind a modal due to an ad hoc z-index conflict.

---

## 3. Key Design Decisions

### Why Both Tailwind Config and CSS Custom Properties Are Necessary

In Tailwind CSS 4, the `@theme` block serves as a CSS-first configuration layer. So why is a separate `tokens.css` file still needed?

```
tokens.css (Source of Truth)
├── The canonical definition of all design values
├── Used directly in Svelte <style> blocks
├── Accessible via JavaScript's getComputedStyle
└── Framework-agnostic (shareable with Flutter webviews)

@theme or tailwind.config.js (Integration Layer)
├── Generates Tailwind utility classes
├── bg-primary, text-gray-600, etc.
└── Mirrors or references values from tokens.css
```

There are real-world scenarios where Tailwind alone falls short. Complex CSS written inside Svelte's `<style>` blocks, runtime color value reads for Canvas API or SVG manipulation, and sharing the same color baseline with a Flutter webview all require direct access to CSS Custom Properties. In these cases, `var(--color-primary)` works even where Tailwind classes cannot be applied.

For **Tailwind CSS 3** projects using `tailwind.config.js`, values in tokens.css are mirrored 1:1 in the config:

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#3182F6',  // matches tokens.css --color-primary-500
          50: '#EBF4FF',
          600: '#2563EB',
        },
        gray: {
          50: '#F9FAFB',       // matches tokens.css --color-gray-50
          900: '#191F28',
        },
      },
      borderRadius: {
        lg: '12px',            // matches tokens.css --radius-lg
      },
    },
  },
}
```

For **Tailwind CSS 4** projects using `@theme`, tokens.css is imported at the top of `application.css`, and the same values are registered in the `@theme` block:

```css
/* application.css */
@import "../css/tokens.css";    /* load first */
@import "tailwindcss";

@theme {
  --color-primary: #3182F6;     /* same value as tokens.css */
  --color-primary-50: #EBF4FF;
  --color-primary-600: #2563EB;
  --radius-lg: 12px;
}
```

Tailwind CSS 4's `@theme` block automatically exposes CSS Custom Properties as Tailwind utilities. Registering `--color-primary` in `@theme` means `bg-primary`, `text-primary`, and `border-primary` are automatically generated. Having the same value in both tokens.css and `@theme` may look redundant, but the two serve different purposes: tokens.css handles CSS runtime access, while `@theme` handles Tailwind build-time class generation.

### Dark Mode Token Strategy

For projects that support dark mode, light mode defaults are defined on `:root` and overridden in the `.dark` selector:

```css
:root {
  --color-bg-primary: #FFFFFF;
  --color-bg-surface: #F9FAFB;
  --color-text-primary: #191F28;
  --color-text-secondary: #6B7684;
  --color-border: #E5E8EB;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04);
}

:root.dark {
  --color-bg-primary: #0D0D0D;
  --color-bg-surface: #1A1A1A;
  --color-text-primary: #F5F5F5;
  --color-text-secondary: #9EA6B2;
  --color-border: #2D2D2D;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.25);
}
```

With this approach, Svelte components never need to think about dark mode. Writing `var(--color-bg-primary)` is sufficient; toggling the `.dark` class on the `<html>` element switches the entire UI.

In the Inertia.js + Rails environment, the dark mode toggle state is stored in `localStorage` and applied before the initial render in the Rails layout to prevent a flash of the wrong theme:

```html
<!-- app/views/layouts/application.html.erb -->
<script>
  // Apply dark mode before layout renders to avoid flash
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark');
  }
</script>
```

### Per-Project Brand Color Separation

All projects share the same token structure, with only the brand color varying per project:

```
Per-project Primary Color:
├── Service A: Blue      #2563EB  (vehicle community)
├── Service B: Sky Blue  #0EA5E9  (voice social)
├── Service C: Toss Blue #3182F6  (admin panel)
├── Service D: Toss Blue #3183F6  (team matching)
└── Boilerplate: Toss Blue #3182F6 (with customization comments)
```

Every token outside of color — spacing, font sizes, border radii, shadows — is identical across all projects. This means a component built in one project can be copied to another and have `--spacing-md`, `--radius-lg`, and similar tokens work out of the box.

---

## 4. The Bulk Application Process

### Running in Parallel

Token files were generated for all 5 projects simultaneously. For each project, the steps were:

1. Create the `app/frontend/css/` directory
2. Analyze the project's existing colors and configuration (`application.css`, `tailwind.config.js`)
3. Generate `tokens.css` with all 8 sections
4. Add `@import` to the existing CSS entry file

Claude Code was used to process multiple projects in parallel. Each project's existing `tailwind.config.js` was analyzed, and a tokens.css consistent with its defined values was generated automatically. The critical requirement throughout was **value consistency with the existing configuration**.

### Ensuring Consistency with Existing Configurations

The most important concern was making sure **tokens.css values exactly matched the existing `tailwind.config.js` or `@theme` block**.

For example, shadow values already defined in one project's `tailwind.config.js`:

```js
// tailwind.config.js
boxShadow: {
  sm: '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06)',
}
```

These were copied verbatim into tokens.css:

```css
:root {
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
}
```

If tokens.css had been populated with different values, the `shadow-md` Tailwind class used in existing components and the `var(--shadow-md)` used in new components would render different shadows. That kind of inconsistency is unacceptable.

### Special Handling for the Boilerplate Project

The project used as a boilerplate template received comments marking every customization point:

```css
:root {
  /* ===== Customize: Brand Color ===== */
  /* Change the Primary color to match the new project */
  /* Color palette generator: https://uicolors.app/create */
  --color-primary: #3182F6;
  --color-primary-50: #EBF4FF;
  --color-primary-100: #DBEAFE;
  --color-primary-500: #3182F6;
  --color-primary-600: #2563EB;
  --color-primary-900: #1E3A8A;

  /* ===== Customize: Font Family ===== */
  /* Korean projects: Pretendard, English-only: Inter */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;

  /* ===== Do NOT Customize Below ===== */
  /* These values are shared across all projects — do not modify */
  --spacing-sm: 8px;
  /* ... */
}
```

Clear comments separating what should be changed from what should stay the same make onboarding faster for new team members and future-self.

---

## 5. What Changed After Adoption

### Before: Hardcoded Values

```svelte
<button class="bg-[#3182F6] hover:bg-[#2876E5] rounded-[12px]
  shadow-[0_4px_6px_rgba(0,0,0,0.04)] text-[14px] font-semibold">
  Save
</button>
```

This code carries several problems. `#3182F6` gives no indication of its semantic meaning from the code alone. Changing this color requires searching the entire codebase for the hex value and replacing every occurrence. Adding dark mode support means adding conditional logic to every hardcoded value.

### After: Token References

```svelte
<button class="bg-primary hover:bg-primary-600 rounded-xl shadow-md text-label">
  Save
</button>

<!-- Or using the Svelte style block for complex cases -->
<style>
  .custom-card {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    transition: var(--transition-normal);
    min-height: var(--touch-target-min);
  }

  .custom-card:hover {
    box-shadow: var(--shadow-lg);
  }
</style>
```

Switching to token references makes intent immediately clear. `bg-primary` communicates that this is a primary action button. `var(--color-border)` tells the reader this is the standard border color without needing to check a color chart. To rebrand a project, only `--color-primary` in `tokens.css` needs to change.

### Final State

```
Before                          After
─────────────────────          ─────────────────────
Fully adopted:  1              Fully adopted:  1 (unchanged)
Partial:        2              Complete system: 4 (+2 partial → tokens added)
Not adopted:    5              Tokens applied:  3 (+3 new)
                               Incomplete:      1 (frontend not yet built)
```

Project H, the one remaining incomplete, has only Rails server-side rendering in place and has not yet had Inertia.js integrated. Design tokens are deferred until the frontend structure itself is established.

---

## 6. Pitfalls and Lessons Learned

### Tailwind CSS 3 and 4 Mixed Together

Even within the same technology stack, different projects were using Tailwind 3 (`tailwind.config.js`) and Tailwind 4 (`@theme` block) depending on when they were created. Because tokens.css works with both, it acts as a unifying layer that bridges the version gap.

When eventually upgrading a Tailwind 3 project to 4, having tokens.css already in place acts as a buffer. Components that have already been refactored to use CSS Custom Properties remain unaffected by changes to the Tailwind configuration format.

### The Dark Mode Token Design Trap

The initial instinct was to create separate dark mode variables like `--color-dark-bg-primary`. But this forces every component to branch on dark mode explicitly:

```css
/* ❌ Wrong approach */
.card { background: var(--color-bg-primary); }
.dark .card { background: var(--color-dark-bg-primary); }
```

Instead, **overriding the same variable name in the `.dark` selector** keeps component code clean:

```css
/* ✅ Correct approach */
:root { --color-bg-primary: #FFFFFF; }
:root.dark { --color-bg-primary: #0D0D0D; }

.card { background: var(--color-bg-primary); }  /* dark mode handled automatically */
```

The key insight here is leveraging the **cascading inheritance behavior of CSS Custom Properties**. Variables defined on `:root.dark` override the value for all descendant elements. Components only need to reference the variable name; the context determines which actual value gets applied.

### Exceptions to the 8px Grid

Most spacing values follow the 8px grid (8, 16, 24, 32...), but 4px (`--spacing-xs`) and 12px (`--spacing-smd`) are unavoidable in practice. 12px in particular comes up constantly: gaps between icons and labels, internal padding for badges and chips, and compact list item spacing.

The initial goal was to enforce a pure 8px grid, but an 8px gap between a 16px icon and its label text felt too wide, while 4px felt too tight. 12px was the pragmatic middle ground, so it was formalized as `--spacing-smd`. Practical usability takes precedence over mathematical purity.

### 44px Touch Target Is Non-Negotiable

Defining `--touch-target-min: 44px` as a token in projects that support mobile webviews ensures a consistent minimum touch target across all buttons and interactive elements. This is the iOS Human Interface Guidelines standard; Material Design recommends 48px.

Several of the Rails + Inertia.js projects are also accessed via Hotwire Native or Flutter webviews. When native mobile apps use webviews, small touch targets cause a dramatic drop in usability. Having the value defined as a token guarantees consistent enforcement across every button and tab.

### CSS Custom Properties and Svelte Reactivity

When passing Svelte 5 `$state`-managed dynamic values to CSS Custom Properties, inline styles are required:

```svelte
<script>
  let primaryColor = $state('#3182F6');
</script>

<!-- Dynamic token override -->
<div style="--color-primary: {primaryColor};">
  <button class="bg-primary">Dynamic color button</button>
</div>
```

This pattern is useful for white-label services or any feature that allows user-driven theme customization.

---

## Conclusion

Design tokens are not a nice-to-have. **If you run more than one project, they are mandatory.** Especially when projects share the same technology stack, standardizing the token structure means starting a new project is as simple as changing the brand color in a boilerplate.

Summary:

1. **Make tokens.css the source of truth** — Keep it separate from Tailwind configuration, but keep values in sync
2. **Override the same variable name for dark mode** — Simplifies component code
3. **Standardize 8 sections** — Colors, Typography, Spacing, Radius, Shadows, Z-Index, Transitions, Touch Target
4. **Separate only the brand color per project** — Everything else stays identical

---

## Key Takeaways

- **Audit design token adoption regularly.** As projects accumulate, things spiral out of control faster than expected. The refactoring cost grows exponentially if a standard is not established early.
- **One tokens.css file supports both Tailwind 3 and 4.** When Tailwind versions are mixed within the same team, a CSS Custom Properties layer absorbs the version differences cleanly.
- **Building components before establishing tokens makes token adoption harder.** The more hardcoded components accumulate, the higher the refactoring cost. Always define tokens before writing the first component.
- **Annotating customization points in boilerplate files speeds up onboarding** for new team members and future maintainers.
- **CSS Custom Properties are readable from JavaScript.** Canvas APIs, WebGL, and animation libraries can all reference the same token values outside of CSS, ensuring consistency across rendering contexts.
