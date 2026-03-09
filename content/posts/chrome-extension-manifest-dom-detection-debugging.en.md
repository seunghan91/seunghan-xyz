---
title: "Chrome Extension Debugging Lessons — Domain Whitelist, Duplicate Listeners, Closure Pitfalls"
date: 2026-03-09
draft: false
tags: ["Chrome Extension", "Firefox Extension", "Manifest V3", "JavaScript", "Debugging"]
description: "Four mistakes made while developing a Chrome/Firefox extension: blocking DOM detection flow, duplicate event listeners, missing closure references, and AMO packaging errors."
cover:
  image: ""
  alt: ""
  hidden: true
---

When maintaining a Chrome extension, "this should definitely work, why doesn't it?" comes up more often than expected. I made four consecutive mistakes in a short period, each with a different root cause. Writing them down.

---

## 1. A `return` in the dispatch block silently kills generic detection

Content scripts typically end with a pattern like this:

```js
if (isSomeSpecificPage()) {
  doSomethingSpecific();
  return; // ← exits here
}

// Generic DOM detection (MutationObserver, etc.)
const observer = new MutationObserver(() => { ... });
observer.observe(document.body, { childList: true, subtree: true });
```

After adding a feature for a specific domain with an early `return`, the generic DOM detection never ran in a popup window on that domain.

The broken flow:
1. User clicks a button on domain A → popup opens on domain B
2. Domain B also matched `isSomeSpecificPage()` (using `hostname.endsWith(...)`)
3. The popup only needed generic detection, but `return` blocked it entirely

**Fix**: Remove the dispatch block if the feature isn't actually needed on that page, or tighten the condition to an exact match (`hostname === 'exact.domain.com'`).

---

## 2. `<all_urls>` vs. specific domain list — Chrome Web Store review perspective

Using `<all_urls>` in `host_permissions` seemed convenient at first. But Chrome Web Store requires **separate justification** for broad permissions, which can delay or reject submissions.

Listing specific domains instead:
- Gives reviewers clear context for each domain's purpose
- Satisfies **least privilege** without unnecessary access
- Makes the intent of each update transparent during re-review

Practical note: `host_permissions` and `content_scripts.matches` in `manifest.json` must always **match exactly**. Updating only one means the extension either has permission but the script isn't injected, or the script is injected but API calls are blocked.

When adding new domains, include a reason in the Notes to Reviewer field:

```
Added *.example.go.kr to support [service name] which uses
[feature]. The extension only activates when specific DOM
elements are detected, and no data is sent to external servers.
```

---

## 3. Duplicate event listeners — `addEventListener` called every time a view opens

The popup UI had an initialization function called every time the edit view opened.

```js
document.getElementById('btn-edit').addEventListener('click', () => {
  // fill values...

  initTabBar('edit-tab-bar', 'edit');       // ← called every time
  initCondSelect('edit-cp-sel', 'edit-cp'); // ← called every time
  initSecToggles();                          // ← called every time
});
```

`initCondSelect` attaches a `change` listener to a `select` element internally. Opening the edit view twice attaches two listeners, three times means three. When the select value changes, show/hide runs N times and the panel ends up in an unexpected state.

**Fix**: Register event listeners exactly once at `DOMContentLoaded`. The key is separating value-filling (`el.value = ...`) from listener registration (`addEventListener`).

```js
// Run once
initCondSelect('edit-cp-sel', 'edit-cp');

// Run on each btn-edit click (values only)
document.getElementById('btn-edit').addEventListener('click', () => {
  cpSel.value = info.coupangLoginType || '';
  cpSel.dispatchEvent(new Event('change')); // reuse existing listener
});
```

Using `dispatchEvent(new Event('change'))` triggers the existing listener, so show/hide logic doesn't need to be duplicated.

---

## 4. Closure `data` reference — why editing fails after saving

The structure loaded `data` at `DOMContentLoaded` and passed it to various functions.

```js
document.addEventListener('DOMContentLoaded', async () => {
  const data = await chrome.storage.local.get([...]);
  // data.userInfo === undefined (new user)

  initSignup(); // data not passed
  initMain(data);
});
```

Even after `initSignup` saves user info, `data.userInfo` inside `initMain`'s closure is still `undefined`. So clicking the edit button right after saving hits `if (!info) return` and exits early.

**Fix**: Pass the `data` object to `initSignup` and update `data.userInfo` directly after saving.

```js
initSignup(data); // pass data reference

// inside initSignup
async function save() {
  await chrome.storage.local.set({ userInfo });
  data.userInfo = userInfo; // updates the same object → reflected in initMain's closure
}
```

Since JavaScript objects are passed by reference, updating a property on the shared `data` object is immediately visible in other closures that hold a reference to it.

---

## 5. Firefox AMO packaging — zip structure error

When uploading to Firefox Add-ons, this error appeared:

```
manifest.json was not found at the root of the extension.
The package file must be a ZIP of the extension's files themselves,
not of the containing directory.
```

The cause was simple: zipping from the parent directory included the folder itself.

```bash
# ❌ Wrong — results in firefox_extension/manifest.json
zip -r output.zip firefox_extension/

# ✅ Correct — manifest.json is at the root
cd firefox_extension && zip -r ../output.zip .
```

Chrome Web Store works the same way. Always **go inside the extension folder** before zipping.

---

## 6. Firefox AMO innerHTML warning

The AMO linter flagged this:

```
Unsafe assignment to innerHTML
firefox_extension/content.js line 401
```

The code looked like this:

```js
function showHint(messageHtml) {
  el.querySelector('#msg').innerHTML = messageHtml; // ← warning
}

showHint('A message.<br><b>Bold text</b> too.');
```

`messageHtml` only ever receives static string literals in the code, but the linter sees a variable assignment and flags it as potentially dynamic.

**Fix**: Build a small DOM helper that only handles `<br>` and `<b>` tags.

```js
function renderSafeHtml(container, html) {
  container.textContent = '';
  html.split(/(<br\s*\/?>|<b>[^<]*<\/b>)/g).forEach(part => {
    if (/^<br/i.test(part)) {
      container.appendChild(document.createElement('br'));
    } else if (/^<b>/i.test(part)) {
      const b = document.createElement('b');
      b.textContent = part.replace(/<\/?b>/gi, '');
      container.appendChild(b);
    } else if (part) {
      container.appendChild(document.createTextNode(part));
    }
  });
}
```

Even when the input is a static string, AMO requires DOM manipulation to pass review.

---

## Summary

| Mistake | Cause | Fix |
|---|---|---|
| Generic detection not running in popup | `return` in dispatch block cuts the flow | Narrow the condition or remove the block |
| CWS review delays | `<all_urls>` broad permission | List specific domains explicitly |
| Save button behavior unstable | Duplicate event listeners | Init once, repeat only value-filling |
| Edit fails after saving | Missing `data` reference in closure | Pass `data` object and update directly |
| AMO packaging error | Zipping the folder itself | Zip from inside the extension folder |
| AMO innerHTML warning | HTML string assigned to variable | Replace with DOM helper |

The common thread across all these mistakes was assuming "this obviously should work." Extension development is trickier than it looks when it comes to domain matching, script injection timing, and event registration order.
