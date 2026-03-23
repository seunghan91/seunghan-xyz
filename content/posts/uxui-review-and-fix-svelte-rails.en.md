---
title: "Rails + Svelte App UX/UI Full Review and Improvement Record"
date: 2026-03-06
draft: false
tags: ["Svelte", "Rails", "UX", "Accessibility", "svelte-sonner", "Tailwind"]
description: "Full UX review of a todo management web app, improving start date UI consistency, toast notifications, touch targets, and password toggle."
cover:
  image: "/images/og/uxui-review-and-fix-svelte-rails.png"
  alt: "Uxui Review And Fix Svelte Rails"
  hidden: true
---

While running a web app built with Rails 8 + Inertia.js + Svelte 5, I noticed that even though the features were working correctly, the fine-grained UX felt inconsistent. This post is a record of a full audit and the four highest-priority issues I fixed.

When you build features quickly, each screen tends to be developed independently, and you end up with situations where "the same feature works differently depending on where you are." From the user's perspective, this inconsistency makes the app feel unpolished. It is not a functional bug in the traditional sense, but it is absolutely a UX bug.

---

## The Problem: Same Feature, Different UI

The most obvious issue was that **the start date input UI behaved differently on every screen**.

The app had four entry points for creating a task:

- Dashboard quick-add
- Create modal
- Full-page creation form
- Edit modal

| Location | Start date behavior |
|------|------------|
| Dashboard quick-add | Picker always visible + separate `+ Start date` button also present |
| Create modal | `+ Add start date` button appears after setting a due date; picker shows on click |
| Full-page form | Picker always visible |
| Edit modal | Picker always visible |

The create modal was the only one with a clean UX. The other three always showed the picker, making the form look unnecessarily complex. Having a `+ Start date` button while the picker was already visible made the button's purpose ambiguous.

The root cause is straightforward. Each entry point component was built at different times, possibly by different mindsets. Without abstracting the logic into a shared component, divergence is inevitable.

### Solution: Unify Around the Create Modal Pattern

I used the create modal as the reference pattern and updated the other three locations to match. The core principle is **"only show it when it's needed."**

```svelte
<!-- Before: picker always visible -->
<div class="grid gap-2 sm:grid-cols-2">
  <div>
    <Label>Start date</Label>
    {#if startDate}
      <button onclick={() => startDate = ''}>Remove</button>
    {:else}
      <button onclick={() => startDate = dueDate}>+ Start date</button>
    {/if}
    <DueDatePicker value={...} />  <!-- always rendered -->
  </div>
  <div>
    <Label>Due date</Label>
    <DueDatePicker value={...} />
  </div>
</div>
```

```svelte
<!-- After: due date first, start date only when needed -->
<div>
  <div class="flex items-center justify-between mb-1">
    <Label>Due date</Label>
    {#if dueDate && !startDate}
      <button onclick={() => startDate = dueDate}>+ Add start date</button>
    {/if}
  </div>
  <DueDatePicker value={...} />
</div>

{#if startDate}
  <div>
    <div class="flex items-center justify-between mb-1">
      <Label>Start date</Label>
      <button onclick={() => startDate = ''}>Remove</button>
    </div>
    <DueDatePicker value={...} />
  </div>
{/if}
```

What changed:
1. **Due date is the primary field**, expressed by placing it first in the layout
2. The `+ Add start date` button only appears after a due date is set — the flow feels natural
3. The start date picker only appears when the button is clicked — form complexity is reduced

This pattern follows the **Progressive Disclosure** principle: only surface additional options at the moment the user actually needs them. When a form opens, the user should see what the task is (content) and when it is due (due date). Start date is optional and only meaningful once a due date exists.

---

## Full Audit: 44 UX Issues

While fixing the start date issue, I took the opportunity to review the rest of the app. Here is what I found, grouped by severity:

### CRITICAL — Fix Immediately

**Emojis used as UI icons (☀️🕐📝🔔⭐)**

Emoji rendering varies by OS. On macOS you get a colorful sun icon; on some Windows builds it looks different. More critically, screen readers announce them literally — a star emoji reads as "star sign" with no context about its function. You also cannot control their size with `font-size` reliably, which breaks responsive layouts. The fix is to replace all emoji icons with SVG icons such as those from `lucide-svelte`.

**No focus trap in modals**

The Dialog component had `aria-modal="true"` but Tab key navigation could still reach elements behind the modal. A screen reader user could interact with background content without knowing they were inside a modal. `aria-modal="true"` alone is not enough — you need JavaScript to actually trap focus within the modal boundaries. Alternatively, using the native `<dialog>` HTML element gives you focus trapping for free.

**No password visibility toggle**

Without being able to see what you typed, a single typo means retyping the entire password from scratch. This is one of the most common reasons for failed login attempts. WCAG 2.1 Success Criterion 1.3.5 recommends providing a show/hide toggle for password fields.

**Silent failure on network errors**

When `fetch()` failed, the `catch` block only updated an internal state variable but showed no UI feedback. The user had no idea whether their data was saved or not. This is especially problematic for mobile users on unreliable networks.

### HIGH — Fix This Sprint

- Touch targets below 44px (Categories edit/delete buttons at `p-1.5` ≈ 20px)
- No success/failure feedback on submit buttons
- Missing `cursor-pointer` — users cannot tell if an element is clickable
- Icon-only buttons have no `aria-label` — screen readers cannot describe the button's purpose

### MEDIUM — Next Sprint

- Color contrast ratio below WCAG AA standard (4.5:1) in some areas
- No `prefers-reduced-motion` support — users sensitive to motion are not accommodated
- No empty state UI — when there is no data, the app looks broken rather than empty
- No optimistic updates — updating the UI before server confirmation improves perceived speed significantly

---

## What I Actually Fixed This Time

Here are the four issues I addressed in this work session in detail.

### 1. Unified Toast Notifications (svelte-sonner)

Previously, success and failure feedback was inconsistent across the app:
- Success: `window.location.reload()` — a silent page refresh with no message
- Failure: text-only error displayed at the top of the form; some handlers only called `console.error()`

`svelte-sonner` was already mounted as `<Toaster>` in `AppLayout`, but the modals were not using it at all. The library was there; nobody was calling it.

```svelte
<!-- Before -->
} catch (err) {
  error = err?.message || 'Failed to create task.';
} finally {
  submitting = false;
}
```

```svelte
<!-- After -->
import { toast } from 'svelte-sonner';

// On success
toast.success('Task created successfully.');
window.location.reload();

// On failure
} catch (err) {
  const msg = err?.message || 'Failed to create task.';
  error = msg;       // keep inline form error for context
  toast.error(msg);  // also show as toast for immediate visibility
}
```

There is a reason to keep both the inline `error` state and the toast. The inline error message provides context about which part of the form has a problem. The toast provides immediate, prominent feedback about what action failed. The two complement each other.

Applied to: create modal, edit modal (save and delete), dashboard quick-add.

The real benefit here is not just "a toast appears." The user now knows clearly whether they can proceed to their next action. Before this change, a user might reload the page or retry the submission wondering whether the first attempt had gone through.

Every async operation has three states that must be handled: **loading**, **success**, and **error**. Handling only the happy path is one of the most common UX oversights in web development.

### 2. Expanding Touch Targets to 44px

Small buttons on mobile are a significant source of user frustration. The WCAG minimum is 44×44px.

The edit, share, and delete buttons on the Categories page were using `p-1.5`, resulting in approximately 20px hit areas: 16px icon + 6px padding × 2 = 28px. That is less than two-thirds of the minimum.

```svelte
<!-- Before -->
<button class="p-1.5 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition">

<!-- After -->
<button class="p-2.5 -m-1 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition cursor-pointer">
```

The key insight here is the `–m-1` negative margin. Increasing padding alone would shift surrounding layout. By adding negative margin to compensate, the **visual size stays the same** while the interactive area grows. This is a practical pattern for improving touch accessibility without touching the layout.

The math: `p-2.5` = 10px padding, so 16px icon + 10px × 2 = 36px. Combined with `-m-1` (4px negative margin on each side), the effective click area reaches approximately 44px without any layout change.

`cursor-pointer` was also added at the same time. The default CSS cursor is `default`, which gives no visual indication that an icon button is interactive. This is a small addition but reduces cognitive friction.

### 3. Password Show/Hide Toggle

Applied to both Login and Register screens. Svelte 5's `$state` rune manages the visibility flag.

```svelte
let showPassword = $state(false);
```

```svelte
<div class="relative mt-1">
  <Input
    id="password"
    type={showPassword ? 'text' : 'password'}
    bind:value={password}
    placeholder="••••••••"
    required
    autocomplete="current-password"
  />
  <button
    type="button"
    class="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-text-sub hover:text-text-main cursor-pointer"
    onclick={() => (showPassword = !showPassword)}
    aria-label={showPassword ? 'Hide password' : 'Show password'}
    tabindex="-1"
  >
    {#if showPassword}
      <!-- EyeOff SVG icon -->
    {:else}
      <!-- Eye SVG icon -->
    {/if}
  </button>
</div>
```

Several details are worth highlighting:

**`tabindex="-1"`**: When the user presses Tab to move through the form, focus should not land on the toggle button. Password field → Tab → next field (or submit button) is the expected flow. The toggle is a supporting control, not a primary form element, so it should not interrupt keyboard navigation.

**Dynamic `aria-label`**: An icon-only button without a label is invisible to screen readers. By changing the label dynamically based on the current state, screen reader users also know whether the password is currently visible or hidden.

**`autocomplete="current-password"`**: This hint tells the browser and password managers how to handle this field correctly. It seems minor but makes a real difference for users who rely on password managers.

For the Register form, which has both a password and a password confirmation field, each field gets its own independent state:

```svelte
let showPassword = $state(false)
let showPasswordConfirmation = $state(false)
```

Sharing a single state between the two fields would toggle both simultaneously, which is confusing. Independent states allow users to reveal one field without affecting the other.

### 4. Start Date UI Unification (continuation)

The pattern described in the first section was applied to all three remaining locations: dashboard quick-add, full-page create form, and edit modal. The edit modal required one additional consideration: the initial value may already be set from a saved task.

```svelte
// Edit modal: initialize from server-side task data
let startDate = $state(task.startDate ?? '')
let dueDate = $state(task.dueDate ?? '')
// If startDate is non-empty, the {#if startDate} block automatically
// renders the picker without any additional logic needed.
```

The beauty of the conditional rendering approach is that the same template handles both "no start date" and "has start date" states correctly. There is no need for a separate `showStartDatePicker` boolean — the presence of an actual date value drives the UI state directly.

---

## Audit Summary (44 Issues)

| Severity | Count | Key Areas |
|--------|------|----------|
| CRITICAL | 8 | Emoji icons, modal focus trap, password toggle, error feedback, z-index |
| HIGH | 12 | Touch targets, loading states, aria-labels, keyboard access |
| MEDIUM | 16 | Contrast ratio, prefers-reduced-motion, empty states, optimistic updates |
| LOW | 8 | Spinner consistency, keyboard drag support, overflow handling, etc. |

Four out of 44 issues were addressed in this session. However, three of those were CRITICAL issues — password toggle, error feedback via toast, and the date picker inconsistency — so the real-world improvement in user experience is proportionally larger than 4/44 would suggest. The remaining CRITICAL issues (emoji icon replacement and modal focus trap) are scheduled for the next sprint.

---

## Key Takeaways

Working through this audit reinforced that UX quality is determined by small details, not just working features.

**1. When the same feature has multiple entry points, consistent behavior is mandatory.**

Without abstracting into a shared component, you will have to hunt down and update every location individually when something needs to change. The start date fix was exactly that case — four places with identical changes. The next step is to extract this into a shared `StartDateField` component.

**2. Async operations with no feedback are always a problem.**

Every `fetch()` call needs a user-visible response for both success and failure. A silent page reload leaves the user wondering whether the save worked. A toast notification eliminates that uncertainty immediately. Always handle loading, success, and error states explicitly.

**3. Touch targets are invisible but critical.**

A button can look small visually while having a large interactive area. The `padding + negative margin` trick — specifically `p-2.5 -m-1` — expands the click area without changing the visual layout. This is a practical, low-effort way to meet WCAG touch target requirements without a design overhaul.

**4. `tabindex="-1"` on supporting controls is intentional.**

Removing secondary UI elements (toggles, clear buttons, etc.) from Tab order makes the keyboard navigation flow feel natural. Not every interactive element needs to be reachable via Tab. Supporting controls that complement the main flow are often better left accessible by pointer only.

**5. Accessibility reviews need to be part of the development cycle.**

Doing it all at once results in a list of 44 items. Building in `aria-label`, touch target sizing, and focus management at the time a component is created dramatically reduces the remediation work later. Treat each component as shipped only when these basics are in place.
