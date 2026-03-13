---
title: "Chrome Extension Content Script — Korean Insurance Auto-Fill, HTML Mock Screenshots, MOV to GIF"
date: 2025-10-28
draft: false
tags: ["Chrome Extension", "Browser Extension", "Playwright", "ffmpeg", "JavaScript", "content script"]
description: "Auto-fill for 10 Korean direct car insurance sites with JS rendering support, React/Vue Native Setter trick, HTML+Playwright store screenshots, and ffmpeg 2-pass GIF conversion."
cover:
  image: "/images/og/chrome-extension-insurance-autofill-playwright-gif.png"
  alt: "Chrome Extension Insurance Autofill Playwright Gif"
  hidden: true
---

Notes from extending the form auto-fill feature in a browser extension and the various struggles along the way.

---

## 1. Direct Car Insurance Site Content Script Auto-Fill

### Problem: Can't Read Form Structure via WebFetch on JS-Rendered Sites

Korean insurance company direct sites mostly use SPA/RIA architecture.

- Samsung Fire: SFMI proprietary RIA framework
- Hyundai Marine, DB Insurance: Spring MVC `.do` URL patterns
- KB Insurance, Meritz: Separate mobile/PC domains

Scraping URLs with `WebFetch` doesn't yield form field structures. I chose to **cover common industry field name patterns** instead of manually checking each site via DevTools.

### Industry-Common Field Name Patterns

Analyzing multiple insurance company HTML pages reveals fairly consistent field ID/name patterns:

```javascript
// Name
const NAME_SELECTORS = [
  'input[id*="custNm" i]',     // customer name
  'input[id*="insCustNm" i]',  // insured person name
  'input[id*="contrNm" i]',    // contractor name
  'input[id*="appcntNm" i]',   // applicant name
  'input[placeholder*="이름"]', // "name" in Korean
];

// Resident registration number front (6-digit birthdate)
const BIRTH_SELECTORS = [
  'input[id*="rrnFront" i]',
  'input[id*="jumin1" i]',
  'input[id*="resno1" i]',
  'input[placeholder*="앞 6자리"]', // "front 6 digits"
];

// Phone number
const PHONE_SELECTORS = [
  'input[id*="mobileNo" i]',
  'input[id*="hpNo" i]',
  'select[id*="mobileNo1" i]',  // split input prefix
];
```

### Skipping Security Keypads

The back portion of the resident registration number uses a security keypad, making auto-fill impossible. Detection logic:

```javascript
function isEncryptedInput(el) {
  if (!el) return true;
  if (el.readOnly || el.disabled) return true;
  const cls = (el.className || '').toLowerCase();
  if (/keypad|encrypt|security|virtual|seckey/.test(cls)) return true;
  if (el.dataset.encrypt === 'Y' || el.dataset.security === 'true') return true;
  return false;
}
```

### Why input.value = x Doesn't Work in React/Vue

React and Vue use a synthetic event system, so `el.value = x` alone doesn't trigger state change detection. You need the **Native Setter**:

```javascript
function setInputValue(el, val) {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
  )?.set;
  if (nativeSetter) nativeSetter.call(el, val);
  else el.value = val;

  ['input', 'change', 'keyup'].forEach(ev =>
    el.dispatchEvent(new Event(ev, { bubbles: true }))
  );
}
```

Calling the `value` setter from `HTMLInputElement.prototype` directly, then dispatching `input`/`change` events makes React/Vue update their state.

### Handling Split Phone Number Input

Insurance sites have both `010 | 1234 | 5678` three-field split and `01012345678` unified input:

```javascript
const splitPrefix = document.querySelector('select[id*="mobileNo1" i]');

if (splitPrefix) {
  setInputValue(splitPrefix, '010');
  setInputValue(mid4El, phone.slice(0, 4));
  setInputValue(last4El, phone.slice(4));
} else {
  setInputValue(unifiedEl, fullPhone);
}
```

### MutationObserver for SPA Form Rendering

Using `MutationObserver` to handle forms that render asynchronously after a click:

```javascript
let filled = false;

const obs = new MutationObserver(() => {
  if (!filled) tryFillForm();
});

obs.observe(document.body, {
  childList: true, subtree: true,
  attributes: true,
  attributeFilter: ['style', 'class', 'disabled', 'readonly'],
});

setTimeout(() => obs.disconnect(), 120_000); // disconnect after 2 minutes
```

### manifest.json Domain Addition Pattern

When adding new insurance company domains, you must add them to **both** `host_permissions` and `content_scripts.matches`:

```json
"host_permissions": [
  "https://*.samsungfire.com/*",
  "https://*.directanycar.co.kr/*",
  "https://*.hanwhadirect.com/*"
],
"content_scripts": [{
  "matches": [
    "https://*.samsungfire.com/*",
    "https://*.directanycar.co.kr/*",
    "https://*.hanwhadirect.com/*"
  ],
  "js": ["content.js"]
}]
```

Some insurance companies have two domains for the same service (e.g., Samsung Fire's standard direct vs. Anycar direct). You have to check the store page or ad links to find out.

---

## 2. SVG Icons to PNG Regeneration (rsvg-convert)

Replaced toolbar icons with SVG and extracted PNGs using rsvg-convert:

```bash
brew install librsvg   # install if missing

rsvg-convert -w 16  -h 16  icon.svg -o icon16.png
rsvg-convert -w 48  -h 48  icon.svg -o icon48.png
rsvg-convert -w 128 -h 128 icon.svg -o icon128.png
```

Syncing Chrome icons to Firefox:

```bash
cp icons/icon*.png ../firefox_extension/icons/
```

---

## 3. Chrome Web Store Screenshots -- HTML Mockups + Playwright

### Web Store Screenshot Requirements
- 1280x800 or 640x400
- JPEG or **24-bit PNG (no alpha)**
- Maximum 5

Actual screen captures risk exposing personal information, so I chose to **create HTML mockups** and capture them pixel-perfect with Playwright.

### HTML Mockup Key: Fixed Viewport

```html
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1280px;
    height: 800px;
    overflow: hidden;   /* this is the key */
  }
</style>
```

With `overflow: hidden`, Playwright captures exactly 1280x800.

### Playwright Capture Script

```javascript
// capture.js
const { chromium } = require('playwright');
const path = require('path');

const files = [
  '01_hero.html', '02_autofill.html', '03_setup.html',
  '04_insurance.html', '05_security.html',
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  for (const f of files) {
    await page.goto(`file://${path.join(__dirname, f)}`);
    await page.waitForTimeout(600);   // wait for fonts/images to load
    await page.screenshot({
      path: f.replace('.html', '.png'),
      fullPage: false,   // capture only viewport size
    });
    console.log(`Done: ${f}`);
  }

  await browser.close();
})();
```

```bash
node capture.js
# Done: 01_hero.html
# Done: 02_autofill.html
# ...
```

`fullPage: false` is important. Setting it to `true` captures the full HTML content height, breaking the 1280x800 constraint.

---

## 4. MOV to GIF Conversion (ffmpeg 2-pass)

To get high-quality GIFs from screen recording `.mov` files, you need a two-step process: **palette generation -> GIF conversion**.

### Basic 2-pass Command

```bash
# Step 1: Generate palette
ffmpeg -ss 0 -t 15 -i input.mov \
  -vf "fps=12,scale=716:-1,palettegen=stats_mode=diff" \
  palette.png

# Step 2: Generate GIF
ffmpeg -ss 0 -t 15 -i input.mov -i palette.png \
  -lavfi "fps=12,scale=716:-1 [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  output.gif
```

`stats_mode=diff` optimizes the palette better when there are frequent scene changes.
`dither=bayer:bayer_scale=5:diff_mode=rectangle` gives the best quality-to-file-size ratio.

### Speed Control: setpts

| Purpose | Filter | Description |
|---------|--------|-------------|
| Slow (0.75x) | `setpts=1.35*PTS` | Increase PTS = slower |
| Fast (1.5x) | `setpts=0.655*PTS` | Decrease PTS = faster |
| Compress to 15s | `setpts=(15/original_seconds)*PTS` | Calculate from original length |

Compressing a 22.9-second original to 15 seconds:

```bash
PTS=$(echo "scale=3; 15/22.9" | bc)   # -> 0.655
ffmpeg ... -vf "setpts=${PTS}*PTS,fps=15,scale=716:-1" ...
```

### 5 Variant Patterns

| Variant | ss | t | Filter |
|---------|----|---|--------|
| Full shot original speed | 0 | 15 | `fps=12,scale=716:-1` |
| Full shot slow (0.75x) | 0 | 11 | `setpts=1.35*PTS,fps=10,scale=716:-1` |
| Key area crop | 0 | 15 | `crop=850:680:291:231,fps=12,scale=716:-1` |
| Full fast | 0 | full length | `setpts=0.655*PTS,fps=15,scale=716:-1` |
| Impact loop | 6 | 7 | `fps=15,scale=640:-1` |

Placing the `-ss` option **before** `-i` is much faster (seeks before input demuxing).

---

## Lessons from Today

1. **Korean insurance SPA sites can't be read via WebFetch** -- covering industry-common field name patterns is the better approach.

2. **React/Vue input auto-fill requires Native Setter + Event dispatch** -- `el.value = x` alone won't trigger state changes.

3. **The same company can have two different domains** -- if you only add one to the manifest, the extension won't work on the other channel's site.

4. **HTML mockups are best for store screenshots** -- cleaner than actual app captures and no risk of personal data exposure. `overflow: hidden` + `fullPage: false` for pixel-perfect captures.

5. **2-pass palette is the way for GIFs** -- much better quality-to-file-size ratio. Recommended: `dither=bayer:bayer_scale=5:diff_mode=rectangle`.
