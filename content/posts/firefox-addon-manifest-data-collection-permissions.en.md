---
title: "Firefox Extension AMO Submission: data_collection_permissions Error Fix"
date: 2025-09-17
draft: true
tags: ["Firefox", "Browser Extension", "AMO", "Manifest V3", "Chrome Extension"]
description: "Resolving the required data_collection_permissions error and manifest.json configuration when submitting extensions to Firefox Add-ons (AMO)."
cover:
  image: "/images/og/firefox-addon-manifest-data-collection-permissions.png"
  alt: "Firefox Addon Manifest Data Collection Permissions"
  hidden: true
---

When porting a Chrome extension to Firefox and submitting to [AMO (addons.mozilla.org)](https://addons.mozilla.org), you will encounter errors that simply do not exist in the Chrome Web Store. The `data_collection_permissions` field, which became mandatory for all new extensions starting November 2025, is particularly easy to stumble on. This post documents the trial-and-error process, the correct solution, and the key manifest.json differences you need to handle when porting from Chrome to Firefox.

---

## Background: Why Port a Chrome Extension to Firefox?

If you already have a Chrome Web Store extension and want Firefox users to benefit from it, you need to submit it to AMO separately. It sounds straightforward, but the two browsers differ meaningfully in their extension APIs and manifest specifications. Code that works perfectly in Chrome can throw errors in Firefox, and the AMO validator will flag Chrome-specific fields as hard errors.

Porting a Manifest V3 (MV3) extension requires several mandatory changes. And starting November 2025, the addition of the required `data_collection_permissions` field means even previously accepted extensions may hit new errors on resubmission.

---

## Problem 1: QR Image Not Showing in the Popup

There was an issue where images appeared broken in the extension popup. The initial suspicion was a Content Security Policy (CSP) problem, but the actual cause was far simpler: **image files were missing from the packaged zip**. The files existed in the local development directory but were absent from the build that was uploaded to the store.

### Root Cause

On macOS, running a plain `zip -r extension.zip .` silently includes several unwanted artifacts:

- `__MACOSX/` directory: macOS resource fork data
- `.DS_Store`: directory metadata files
- `._` prefixed files: extended attribute sidecar files

These files do not affect extension behavior, but they pollute the zip structure and can cause unexpected warnings during AMO validation. The reverse problem also occurs: a `store_assets/` folder containing marketplace screenshots and banners, kept in the project root for convenience, can accidentally end up inside the distributable zip.

### Fix: Clean zip Packaging

```bash
cd my_extension && zip -r ../extension.zip . \
  -x ".*" "__MACOSX/*" "*.DS_Store" "store_assets/*"
```

Always verify the output after packaging:

```bash
unzip -l extension.zip | grep "image_file"
```

Use `unzip -l` to print the zip contents and visually confirm that required image files are present and no unwanted files are included. Adding this verification step to your pre-release checklist will prevent silent packaging bugs from reaching reviewers.

---

## Chrome to Firefox Porting: manifest.json Differences

### 1. Background Configuration: service_worker vs scripts

This is the most commonly encountered difference. Chrome MV3 runs background scripts as Service Workers. Firefox MV3 does not fully support the Service Worker model and instead uses the `scripts` array:

```json
// Wrong -- Chrome-only (errors on Firefox)
"background": {
  "service_worker": "background.js"
}

// Correct -- Firefox
"background": {
  "scripts": ["background.js"]
}

// Never do this -- both together (causes errors)
"background": {
  "service_worker": "background.js",
  "scripts": ["background.js"]
}
```

If your extension needs to support both browsers, the standard approach is to use a build script that generates separate `manifest.json` files per browser target. There is no way to write a single manifest that satisfies both Chrome and Firefox simultaneously.

There are also behavioral differences worth noting. Chrome's Service Worker becomes inactive (idle) when there are no events, conserving memory. Firefox's background script remains alive as long as the browser is running. This affects how you manage in-memory state and may require different initialization patterns in each version.

### 2. browser_specific_settings Is Required

Firefox requires the `gecko` block to identify the extension and manage updates. This field does not exist in Chrome:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0"
  }
}
```

The `id` field must be in email format or `{uuid}` format. `strict_min_version` specifies the minimum supported Firefox version. MV3 support began in Firefox 109; version 128 is a reasonable baseline targeting the mid-2024 LTS release. Adjust based on which APIs your extension actually uses.

If you omit the `id`, AMO will auto-assign a UUID. However, if your extension relies on auto-updates outside of AMO or communicates with other extensions, explicitly specifying a stable ID is the safer choice.

### 3. The `windows` Permission Is Not Supported

In Firefox, including `"windows"` in your `permissions` array generates a warning because it is not a recognized permission value:

```json
// Wrong -- warning on Firefox
"permissions": ["storage", "activeTab", "windows", "tabs"]

// Correct -- remove windows
"permissions": ["storage", "activeTab", "tabs"]
```

The `browser.windows` API is available in Firefox without a dedicated permission. The `tabs` permission alone provides access to window-level information in most use cases.

### 4. API Namespace Differences

Chrome uses the `chrome.*` namespace; Firefox recommends `browser.*`. Firefox does support `chrome.*` as an alias, but the Promise-based API only works correctly under `browser.*`. For cross-browser development, using the `webextension-polyfill` library gives you a unified Promise-based API that works in both environments without branching.

---

## The data_collection_permissions Debugging Journey

Starting November 2025, **all new Firefox extensions** must declare `data_collection_permissions` in `manifest.json`. Mozilla introduced this requirement as part of a broader push for user privacy transparency. If the field is missing, the AMO automatic validator blocks submission with a hard error.

The error messages alone do not make the correct value obvious. Without reading the official documentation carefully, the correct syntax runs counter to intuition, leading to a predictable sequence of wrong attempts.

### Attempt 1: Wrong -- Using `is_exempt`

The first instinct was to look for an exemption flag: "If the extension doesn't collect data, there must be an `is_exempt` property."

```json
"data_collection_permissions": {
  "is_exempt": true,
  "description": "No data is collected."
}
```

> Error: `must have required property 'required'`

The `is_exempt` property does not exist in the specification. The AMO validator reports that the `required` property is missing.

### Attempt 2: Wrong -- `required: false`

The next guess was a boolean: "Data collection is not required, so set it to false."

```json
"data_collection_permissions": {
  "required": false
}
```

> Error: `"required" must be array`

The `required` field must be an array, not a boolean.

### Attempt 3: Wrong -- Empty Array `required: []`

"No data is collected, so an empty array should represent that."

```json
"data_collection_permissions": {
  "required": []
}
```

> Error: validation failed

An empty array is syntactically valid JSON, but the AMO validator does not accept it. The array must contain at least one valid value.

### Attempt 4: Correct -- `required: ["none"]`

```json
"data_collection_permissions": {
  "required": ["none"]
}
```

**This is the correct answer.** Extensions that do not collect any data must explicitly declare `"none"` in the array. The field is not optional silence -- it requires a positive declaration that no data is collected.

### Other Valid Values for data_collection_permissions

For extensions that do collect user data, you must declare the categories of data being collected. The values recognized by Mozilla include:

- `"none"`: No data collected
- `"location"`: Location data
- `"health"`: Health-related data
- `"financial"`: Financial information
- `"credentials"`: Authentication data (passwords, tokens)
- `"usage_data"`: Usage statistics and analytics

If you collect multiple categories, include all of them in the array:

```json
"data_collection_permissions": {
  "required": ["usage_data"],
  "optional": ["location"]
}
```

The `required` key covers data that is essential to the extension's core functionality. The `optional` key covers data collected only with explicit user consent.

---

## Placement: Inside `gecko` vs Top-Level

One more source of confusion: should `data_collection_permissions` go inside `browser_specific_settings.gecko`, or at the top level of `manifest.json`?

Based on the current Mozilla specification and AMO validator behavior, it must be **inside the `gecko` block**:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0",
    "data_collection_permissions": {
      "required": ["none"]
    }
  }
}
```

Placing it at the top level either goes unrecognized by the AMO validator or produces a different error. Stick to the nested placement.

---

## Final Firefox manifest.json Template

Minimum configuration for an extension that does not collect data:

```json
{
  "manifest_version": 3,
  "name": "My Extension",
  "version": "1.0.0",
  "permissions": ["storage", "activeTab", "tabs"],
  "action": {
    "default_popup": "popup.html"
  },
  "content_scripts": [
    {
      "matches": ["https://example.com/*"],
      "js": ["content.js"],
      "all_frames": true,
      "run_at": "document_idle"
    }
  ],
  "background": {
    "scripts": ["background.js"]
  },
  "browser_specific_settings": {
    "gecko": {
      "id": "your-extension@example.com",
      "strict_min_version": "128.0",
      "data_collection_permissions": {
        "required": ["none"]
      }
    }
  }
}
```

---

## AMO Submission Notes

### Source Code Submission

> "Do you use code generators, minifiers, webpack, etc.?"

If written in pure HTML/CSS/JS without build tools, select **"No"**. Source code equals distribution code, so no separate submission is needed.

If you use webpack, Vite, esbuild, or any other bundler, you must submit source code separately. AMO reviewers compare the distribution code against the source to verify there is no obfuscated malicious behavior. Submitting minified or bundled code without source will result in the review being rejected.

### innerHTML Warning

AMO validation produces a warning for any `innerHTML` assignment:

> Unsafe assignment to innerHTML

This is a warning, not a blocking error, so it will not prevent submission. However, it may place the extension under additional scrutiny during the manual review stage, since `innerHTML` can be a vector for XSS vulnerabilities.

Where possible, replace `innerHTML` assignments with `textContent` for plain text, or use DOM APIs (`createElement`, `appendChild`) for structured content. If you must use `innerHTML` with data that could contain user input, a sanitization library like DOMPurify is required. Never assign unescaped user input directly to `innerHTML`.

### eval and Dynamic Code Execution

`eval()`, the `Function()` constructor, and passing strings to `setTimeout` or `setInterval` are treated as hard errors by AMO. MV3's Content Security Policy explicitly prohibits these patterns. If your extension needs dynamic behavior, restructure the code to avoid runtime code generation entirely.

### Firefox for Android

For desktop-only extensions, Android compatibility testing can be skipped. During AMO submission, simply check desktop only in the platform selection.

Firefox for Android (Fenix) has a different and more limited extension API surface compared to the desktop version. An extension that works correctly on desktop may not function at all on Android, so avoid checking Android unless you have explicitly tested on the mobile platform.

---

## Key Takeaways

1. **`data_collection_permissions` is mandatory from November 2025.** Even if your extension collects no data, you must declare `"required": ["none"]` explicitly. An empty array and a boolean are both invalid.

2. **Place `data_collection_permissions` inside `browser_specific_settings.gecko`, not at the top level.** The AMO validator will not recognize it at the root of `manifest.json`.

3. **`background.service_worker` does not work in Firefox.** Firefox MV3 uses `background.scripts` (an array). Never include both `service_worker` and `scripts` in the same manifest.

4. **Explicitly set `browser_specific_settings.gecko.id`.** Auto-assigned UUIDs from AMO can cause problems down the line with updates and cross-extension communication.

5. **Exclude `__MACOSX/` and `.DS_Store` when zipping on macOS.** Use the `-x ".*" "__MACOSX/*"` flags and verify the contents with `unzip -l` before uploading.

6. **Chrome and Firefox cannot share a single `manifest.json`.** Use a build script to generate browser-specific manifests from a shared source of truth.

7. **The `innerHTML` warning can trigger additional manual review.** It does not block submission, but replacing it with `textContent` or DOM APIs is the safer long-term approach.

---

## Reference Documentation

- [Firefox built-in consent for data collection - Extension Workshop](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Announcing data collection consent changes - Mozilla Add-ons Blog](https://blog.mozilla.org/addons/2025/10/23/data-collection-consent-changes-for-new-firefox-extensions/)
- [manifest.json - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json)
- [browser_specific_settings - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/browser_specific_settings)
- [Porting a Google Chrome extension - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Porting_a_Google_Chrome_extension)
