---
title: "Firefox Extension AMO Submission: data_collection_permissions Error Fix"
date: 2025-09-17
draft: false
tags: ["Firefox", "Browser Extension", "AMO", "Manifest V3", "Chrome Extension"]
description: "Resolving the required data_collection_permissions error and manifest.json configuration when submitting extensions to Firefox Add-ons (AMO)."
cover:
  image: "/images/og/firefox-addon-manifest-data-collection-permissions.png"
  alt: "Firefox Addon Manifest Data Collection Permissions"
  hidden: true
---

When porting a Chrome extension to Firefox and submitting to [AMO (addons.mozilla.org)](https://addons.mozilla.org), you'll encounter errors that didn't exist in the Chrome Web Store. The `data_collection_permissions` field, which became mandatory from November 2025, is particularly easy to stumble on.

---

## Symptom: QR Image Not Showing?

There was an issue where images appeared broken in the extension popup. The cause was simple -- **image files were missing from the packaged zip**. The files existed in the local development environment but were absent from the store upload build.

### Fix: Clean zip Packaging

```bash
cd my_extension && zip -r ../extension.zip . \
  -x ".*" "__MACOSX/*" "*.DS_Store" "store_assets/*"
```

On macOS, zipping includes `__MACOSX/` folders and `.DS_Store` files, which should be excluded. Store asset folders like `store_assets/` are also unnecessary for the extension itself.

Always verify after packaging:
```bash
unzip -l extension.zip | grep "image_file"
```

---

## Chrome to Firefox Porting: manifest.json Differences

### 1. background Configuration

Chrome uses `service_worker`, Firefox MV3 uses `scripts`:

```json
// Wrong - Chrome style (errors on Firefox)
"background": {
  "service_worker": "background.js"
}

// Correct - Firefox style
"background": {
  "scripts": ["background.js"]
}

// Wrong - both together (causes errors)
"background": {
  "service_worker": "background.js",
  "scripts": ["background.js"]
}
```

### 2. browser_specific_settings Required

Firefox requires `gecko` settings:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0"
  }
}
```

### 3. windows Permission Not Supported

`"permissions": ["windows"]` is not valid in Firefox. It will show a warning and should be removed.

```json
// Wrong - warning on Firefox
"permissions": ["storage", "activeTab", "windows", "tabs"]

// Correct - remove windows
"permissions": ["storage", "activeTab", "tabs"]
```

---

## data_collection_permissions Struggle Log

Starting November 2025, **all new Firefox extensions** must declare `data_collection_permissions` in manifest.json. Omitting it blocks submission with an error during AMO validation.

### Attempt 1: Wrong -- Using `is_exempt`

```json
"data_collection_permissions": {
  "is_exempt": true,
  "description": "No data is collected."
}
```
> Error: `must have required property 'required'`

The `is_exempt` property doesn't exist.

### Attempt 2: Wrong -- `required: false`

```json
"data_collection_permissions": {
  "required": false
}
```
> Error: `"required" must be array`

It needs to be an array, not a boolean.

### Attempt 3: Wrong -- Empty array `required: []`

```json
"data_collection_permissions": {
  "required": []
}
```
> Error: validation failed

Empty arrays don't work either.

### Attempt 4: Correct -- `required: ["none"]`

```json
"data_collection_permissions": {
  "required": ["none"]
}
```

**This is the answer.** Extensions that don't collect data must specify `"none"` in the array.

---

## Final Firefox manifest.json Template

Minimum configuration for an extension that doesn't collect data:

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

If written in pure HTML/CSS/JS without build tools, select **"No"**. Source code = distribution code, so no separate submission needed.

### innerHTML Warning

AMO validation shows a warning for `innerHTML` usage:

> Unsafe assignment to innerHTML

This is a warning (not an error), so it won't block submission, but replace with `textContent` or DOM APIs where possible.

### Firefox for Android

For desktop-only extensions, you can skip Android compatibility testing. Just check desktop only in the platform selection during AMO submission.

---

## Reference Documentation

- [Firefox built-in consent for data collection - Extension Workshop](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Announcing data collection consent changes - Mozilla Add-ons Blog](https://blog.mozilla.org/addons/2025/10/23/data-collection-consent-changes-for-new-firefox-extensions/)
- [manifest.json - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json)
