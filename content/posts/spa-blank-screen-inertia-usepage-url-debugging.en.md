---
title: "SPA Blank Screen After Deploy: Inertia.js usePage().url is a String"
date: 2025-11-22
draft: false
tags: ["Rails", "Inertia.js", "Svelte", "SPA", "Debugging", "Deployment", "Playwright"]
categories: ["Rails", "Frontend"]
description: "Resolving blank screen after Rails + Inertia.js + Svelte app deployment through Playwright console error analysis. Runtime error from not knowing usePage().url is a string, not a URL object."
cover:
  image: "/images/og/spa-blank-screen-inertia-usepage-url-debugging.png"
  alt: "Spa Blank Screen Inertia Usepage Url Debugging"
  hidden: true
---

After deploying a Rails + Inertia.js + Svelte app, visiting the URL showed a **completely blank screen**. The server was responding normally and all assets were loading fine — but nothing was rendering. This post covers the full investigation, root cause, fix, and patterns to prevent this from happening again.

---

## Symptoms

- **Blank screen** (white background only) when accessing the deployed URL
- Works fine on the local development server
- No error page displayed — just silence
- No anomalies in the server logs (200 responses, normal request handling)

What makes this situation particularly frustrating is that from the server's perspective, everything is working perfectly. HTTP status code 200, no error logs, normal response times. The problem exists only inside the browser.

---

## Diagnosis

The key to debugging SPAs is a **layered, sequential approach**. Trying to see everything at once wastes time.

### Step 1: Check HTTP Response

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/
# 200
```

HTTP 200 OK. The server itself is responding normally. This rules out DNS, infrastructure, and SSL issues.

### Step 2: Check HTML Structure

```bash
curl -s https://example.com/ | head -30
```

```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="/vite/assets/application-xxx.css" />
  <script type="module" src="/vite/assets/application-xxx.js"></script>
</head>
<body>
  <div id="app" data-page="{...}"></div>
</body>
</html>
```

The HTML looks correct, and Inertia.js's `data-page` attribute is populated as expected. The Rails server-side rendering is not the problem. Inspecting the `data-page` JSON also confirmed that the component name, props, and other fields were properly serialized.

### Step 3: Check Asset Loading

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.js
# 200

curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.css
# 200
```

Both JS and CSS return 200 OK. Asset loading is not the issue. The Vite build artifacts are being served correctly.

### Step 4: Check Browser Console Errors (The Critical Clue)

This is where **Playwright MCP** came in — navigating to the page with a real browser and collecting console errors. This is information you simply cannot get from `curl`.

```
TypeError: Cannot read properties of undefined (reading 'pathname')
    at lt (application-xxx.js:1:5526)
    at jn (application-xxx.js:3:9357)
    at vendor-inertia-xxx.js:82:790
    at vendor-svelte-xxx.js:1:37413
```

There was a **JS runtime error**. Something was trying to read the `pathname` property off `undefined`. The stack trace points into minified bundles so the exact source location isn't obvious, but the word `pathname` is the key clue.

---

## Root Cause

The problem was in a layout component that checked the current URL path:

```svelte
<script lang="ts">
  import { usePage } from '@inertiajs/svelte'

  const page = usePage()

  // The problematic code
  const isMyPage = $derived($page.url.pathname.startsWith('/mypage'))
</script>
```

### The Core Issue: `usePage().url` is a **string**

Unlike the browser's `window.location` or a `URL` object, the `url` property returned by Inertia.js's `usePage()` is a **plain string — not a URL object**.

```typescript
// Inside Inertia.js, url looks like this
$page.url // "/mypage"     ← string
$page.url // "/products/1" ← string

// You cannot use it like a URL object
$page.url.pathname  // undefined! strings have no pathname property
$page.url.startsWith('/mypage')  // this is the correct approach
```

This confusion is easy to fall into because there are multiple ways to work with URLs in web development:

| Approach | Type | `.pathname` | `.startsWith()` |
|----------|------|-------------|-----------------|
| `window.location` | Location object | `/mypage` | not a method |
| `new URL(...)` | URL object | `/mypage` | not a method |
| `$page.url` (Inertia.js) | **string** | **undefined** | `/mypage` |

If you frequently use `window.location.pathname` or `new URL(href).pathname`, it's natural to assume `$page.url` is also an object. Especially if you've cast `$page` to `any` in TypeScript — the type checker won't catch this mistake at compile time.

### How Inertia.js Works Internally

When Inertia.js initializes the page, the Rails server responds with a `data-page` JSON payload that includes the `url` field as a string:

```json
{
  "component": "Home/Index",
  "props": { ... },
  "url": "/",
  "version": "abc123"
}
```

Inertia parses this JSON directly and uses it as the page state. The `url` field starts out as a string and stays that way. Even during SPA navigation, Inertia sets the new URL string directly into `page.url` — it never creates a parsed URL object.

### Why Did It Work Locally?

The local development environment already had the fixed version of this code. The deployed version had been built from the code before the fix was applied. In other words, **the local and deployed code were out of sync**.

This is one of the most common traps: you fix something locally but forget to commit, or you commit but forget to deploy, or you deploy the wrong branch. It's a fundamental reason to always verify behavior on the production URL after deploying, not just assume local == production.

---

## Fix

```svelte
<script lang="ts">
  const page = usePage()

  // Fixed: compare directly as string + optional chaining
  const isMyPage = $derived(($page as any)?.url?.startsWith('/mypage') ?? false)
</script>
```

What changed:
1. Removed `.pathname` — since `url` is a string, call `.startsWith()` directly on it
2. Added **optional chaining** (`?.`) — guards against `$page` or `url` not yet being initialized
3. Added **nullish coalescing** (`?? false`) — returns `false` as a safe default when the value is `undefined`

### A More Type-Safe Approach

To avoid `any` casts and leverage TypeScript properly, use Inertia.js's type generics:

```typescript
import { usePage } from '@inertiajs/svelte'
import type { Page } from '@inertiajs/core'

interface AppPageProps {
  flash: { notice?: string; alert?: string }
  unread_message_count: number
}

const page = usePage<AppPageProps>()

// page.url is correctly inferred as string type
const isMyPage = $derived($page.url?.startsWith('/mypage') ?? false)
```

With this approach, `$page.url` is typed as `string`, so any attempt to access `.pathname` will produce a compile-time error rather than a silent runtime crash.

---

## Additional Safety: Defensive `inertia_share`

When sharing global data via `inertia_share`, it is good practice to add rescue handling so that errors from a not-yet-migrated database do not cause blank screens. This is especially relevant on the initial deploy to a new server, where the app might start before migrations have run.

```ruby
# ApplicationController
inertia_share do
  {
    flash: { notice: flash[:notice], alert: flash[:alert] },
    unread_message_count: -> { safe_unread_count }
  }
end

private

def safe_unread_count
  return 0 unless current_user
  current_user.conversations.sum(:unread_count_for_user)
rescue ActiveRecord::StatementInvalid
  0  # Table does not exist yet (before migration runs)
end
```

Why this pattern matters: on PaaS platforms like Render.com, the deployment process runs `bundle exec rails db:migrate` and then restarts the app. During the brief window between the app booting and the migration completing, the old app version may try to query a table that doesn't exist yet, triggering `ActiveRecord::StatementInvalid`. Since `inertia_share` runs on every request, an error here means a blank screen on every page.

---

## Automating Post-Deploy Diagnostics with Playwright

The most decisive tool in this investigation was Playwright. You can programmatically collect JS runtime errors from a deployed site without opening a browser manually.

```javascript
// playwright-console-check.js
const { chromium } = require('playwright')

async function checkConsoleErrors(url) {
  const browser = await chromium.launch()
  const page = await browser.newPage()

  const errors = []
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })
  page.on('pageerror', err => {
    errors.push(`Page error: ${err.message}`)
  })

  await page.goto(url, { waitUntil: 'networkidle' })

  await browser.close()

  if (errors.length > 0) {
    console.log('Console errors found:')
    errors.forEach(e => console.log(' -', e))
    process.exit(1)
  } else {
    console.log('No console errors found.')
  }
}

checkConsoleErrors('https://example.com')
```

This script can be integrated into your CI/CD pipeline to automatically verify that no runtime errors appear after each deployment. On GitHub Actions, you can run this with the official `playwright/action` to get a headless browser in the CI environment.

---

## Key Takeaways

### 1. Blank Screen in SPA = Suspect a JS Runtime Error First

The most common cause of a blank screen in an SPA:
- The server returns HTTP 200, but JavaScript throws an error before rendering completes
- `curl` shows everything is fine, but the browser fails silently — **always check the console**
- In Svelte or React, an unhandled error in a top-level component will leave the entire page blank

### 2. Know the Exact Type of Every Framework API

Whether `$page.url` is a string or a URL object is documented in Inertia.js, but it is easy to confuse with `window.location` when coding quickly. Even with TypeScript, casting to `any` disables type checking entirely and turns runtime errors invisible at compile time.

Common Inertia.js type pitfalls:
- `$page.url` → string (no `.pathname`, no `.host`, etc.)
- `$page.props.user` → requires TypeScript generic to be typed correctly
- `router.visit()` → asynchronous, but does not return a Promise

### 3. The Layered Debugging Stack for Deployed SPAs

```
Layer 1: curl -s -w "%{http_code}"  — HTTP status
Layer 2: curl + HTML inspection     — Server rendering check
Layer 3: curl asset URLs            — JS/CSS loading check
Layer 4: Playwright / Browser DevTools  — JS runtime errors
```

Each layer eliminates a class of problems. Most blank-screen SPA issues surface at Layer 4, which requires a real browser to reproduce. Playwright makes this automatable and scriptable.

### 4. Local Success Does Not Mean Production Success

Fixing code locally means nothing until it is committed, pushed, and deployed. This sounds obvious, but it is surprisingly easy to confirm the fix locally and move on, leaving the production environment still running the broken version.

After every deploy, verify behavior on the actual production URL. Automating this as a smoke test removes the human error factor entirely.

---

## TL;DR

| Item | Detail |
|------|--------|
| **Symptom** | Blank screen after SPA deployment |
| **Initial suspicion** | Server error? Asset loading failure? |
| **Actual cause** | Accessing `.pathname` on `usePage().url`, which is a string in Inertia.js |
| **Fix** | Use `.startsWith()` directly + optional chaining |
| **Key tool** | Playwright automated console error collection |
| **Prevention** | Use Inertia type generics; add post-deploy smoke tests |
