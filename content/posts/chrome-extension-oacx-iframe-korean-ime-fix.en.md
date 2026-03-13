---
title: "Chrome Extension iframe OACX Auto-Fill Not Working — Timing and Korean IME Issues"
date: 2026-01-23
draft: false
tags: ["Chrome Extension", "Manifest V3", "iframe", "OACX", "Korean IME", "Debugging", "MutationObserver"]
description: "Built a government site OACX auto-fill extension but name input fails on certain sites. The cause was iframe async rendering timing and Korean IME composition events."
cover:
  image: "/images/og/chrome-extension-oacx-iframe-korean-ime-fix.png"
  alt: "Chrome Extension Oacx Iframe Korean Ime Fix"
  hidden: true
---

I built a Chrome extension that auto-fills the OACX (simplified authentication) form on Korean government sites. It worked on most sites, but got feedback saying "the name field isn't being filled" on a specific major site.

---

## Symptoms

- Extension auto-fills name, birthdate, and phone number when the simplified auth popup opens
- Works correctly on most government sites (Gov24, National Health Insurance, etc.)
- **Only on a specific site, the name field was empty** -- birthdate and phone number also weren't filled

---

## Investigation: Checking Actual DOM Structure with Playwright

Opened the page reported by the user directly using Playwright MCP.

### Step 1: Main Page Snapshot

Clicking the "Simplified Auth" button on the main page opens a **layer popup + iframe**.

```yaml
- heading "Layer Popup"
  - iframe [ref=e214]   # <-- OACX loads here
```

### Step 2: Inspecting Inside the iframe

Ran JavaScript inside the iframe to check the actual DOM:

```js
// evaluate inside iframe
const inputs = document.querySelectorAll('input, select');
```

Result:

```json
{
  "inputCount": 11,
  "hasOacxContainer": true,
  "url": "https://example.go.kr/oacx/index.jsp",
  "inputs": [
    { "id": "oacx_name",  "dataId": "oacx_name",  "type": "text",     "placeholder": "홍길동" },
    { "id": "oacx_birth", "dataId": "oacx_birth", "type": "text",     "placeholder": "19900101" },
    { "id": "oacx_phone2","dataId": "oacx_phone2","type": "text",     "placeholder": "12341234" },
    { "dataId": "oacx_phone0", "type": "select-one", "title": "Carrier selection" },
    { "dataId": "oacx_phone1", "type": "select-one", "title": "Phone prefix selection" },
    { "id": "totalAgree", "type": "checkbox" }
  ]
}
```

**It was using the standard OACX structure (`data-id="oacx_name"`, etc.) exactly.** So why wasn't it working?

---

## Cause 1: iframe Async Rendering Timing

### Problem Structure

This site loads OACX in a **same-domain iframe**:

```
Parent page (*.go.kr)
  +-- iframe (src="about:blank" -> JS navigates to oacx/index.jsp)
       +-- #oacxEmbededContents  <- container
            +-- input[data-id="oacx_name"]  <- form fields (created async)
```

The content script runs inside iframes too with `all_frames: true`. The problem was the **execution order**:

1. iframe navigates to `oacx/index.jsp`
2. Content script executes at `document_idle`
3. `detectOACX()` -> finds `#oacxEmbededContents` -> calls `autoFill()` immediately
4. **But `input[data-id="oacx_name"]` hasn't been rendered yet** (OACX JS creates it async)
5. `document.querySelector('input[data-id="oacx_name"]')` -> **returns null**
6. `setInputValue(null, name)` -> does nothing (silent fail)
7. `filled = true` is set -> **no retry**

### The Problem with Existing Code

```js
async function autoFill() {
    // ... auth check ...
    filled = true;  // set to true right here

    // If name field doesn't exist yet -> null -> silent fail
    setInputValue(
      document.querySelector('input[data-id="oacx_name"]'),
      info.name
    );
}
```

Once `filled = true` is set, the MutationObserver won't call `autoFill()` again.

### Fix: waitForEl -- Wait Until Field Appears

```js
// MutationObserver-based element waiting
function waitForEl(selector, timeout = 3000) {
    return new Promise(resolve => {
        const el = document.querySelector(selector);
        if (el) return resolve(el);

        const t = setTimeout(() => {
            obs.disconnect();
            resolve(null);
        }, timeout);

        const obs = new MutationObserver(() => {
            const found = document.querySelector(selector);
            if (found) {
                clearTimeout(t);
                obs.disconnect();
                resolve(found);
            }
        });

        obs.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true
        });
    });
}
```

Usage in `autoFill()`:

```js
filled = true;

// Wait up to 3 seconds for input field async rendering
const nameEl = await waitForEl('input[data-id="oacx_name"]', 3000);
if (!nameEl) {
    filled = false;  // reset -> MutationObserver can retry
    return;
}

// Proceed with normal auto-fill
setInputValue(nameEl, info.name);
```

---

## Cause 2: Korean Name and IME Composition Events

### Problem

The existing `setInputValue` only dispatched these events:

```js
function setInputValue(el, value) {
    nativeSetter.call(el, value);      // React-compatible value setting
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
}
```

The name field contains **Korean characters** (e.g., "홍길동"). Korean is entered through an IME (Input Method Editor) in browsers, which fires `compositionstart` -> `compositionupdate` -> `compositionend` events.

Some web frameworks **don't recognize Korean input without composition events.** Birthdate (numbers) and phone number (numbers) don't go through IME, so they don't have this issue.

### Fix: Add Composition Events for Korean Detection

```js
function setInputValue(el, value) {
    if (!el) return;
    el.dispatchEvent(new Event('focus', { bubbles: true }));

    const nativeSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype, 'value'
    )?.set;
    if (nativeSetter) nativeSetter.call(el, value);
    else el.value = value;

    // Fire IME composition events if Korean characters detected
    if (/[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(value)) {
        el.dispatchEvent(new CompositionEvent('compositionstart', {
            bubbles: true
        }));
        el.dispatchEvent(new CompositionEvent('compositionend', {
            bubbles: true,
            data: value
        }));
    }

    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
}
```

The Korean regex `/[ㄱ-ㅎㅏ-ㅣ가-힣]/` checks if the value contains Korean characters, and only adds composition events when it does.

---

## What I Learned During Debugging

### 1. Analyzing Government Site DOM with Playwright MCP

Most Korean government sites use SPA frameworks like WebSquare, and static scraping returns blank pages. With Playwright:

```
navigate -> wait -> snapshot -> click -> snapshot -> evaluate
```

This flow lets you reproduce the actual user flow while inspecting the DOM. The `evaluate` feature was especially useful for running JavaScript directly inside iframes to check exact attribute values.

### 2. The Trap of iframe src="about:blank"

This site creates the iframe with `src="about:blank"` and navigates to the actual URL via JavaScript. In this case:

- Chrome detects the navigation and injects content scripts (`all_frames: true` required)
- But the iframe content's **rendering timing** differs from the parent page
- Even with `document_idle` execution, async-created elements may not exist yet

### 3. The Danger of Silent Fail

```js
function setInputValue(el, value) {
    if (!el) return;  // if el is null, just skip
    // ...
}
```

This pattern is defensive coding but makes debugging difficult. If the element isn't found but there's no error, it's hard to figure out "why it's not working." For critical fields, a **wait -> retry -> reset on failure** pattern is more appropriate.

### 4. Korean Input Is Different from English/Numbers

When typing Korean in a browser, internally:

```
keydown -> compositionstart -> compositionupdate(ㅎ) -> compositionupdate(호)
-> compositionupdate(홍) -> compositionend(홍) -> input -> keyup
```

Programmatically setting `el.value = '홍길동'` skips this entire process. If a framework depends on composition events, the value may be set but not recognized as "inputted."

---

## Summary

| Problem | Cause | Solution |
|---------|-------|----------|
| Name/birthdate/phone all not filled | OACX container detected -> immediate execution -> input fields don't exist yet | `waitForEl()` waits for input to appear (3s timeout) |
| Name field not recognized by framework | Missing Korean IME composition events | Add `compositionstart`/`compositionend` when Korean detected |
| No retry after failure | `filled = true` followed by silent fail | Reset `filled = false` when fields not found |

Async rendering inside iframes and Korean IME -- both are common issues in the Korean web environment, but when they overlap, they're hard to track down.
