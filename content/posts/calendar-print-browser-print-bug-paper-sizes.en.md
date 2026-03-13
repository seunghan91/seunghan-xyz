---
title: "The Trap of Web Calendar Printing: window.print() Ignores Off-Screen Elements"
date: 2026-01-20
draft: false
tags: ["Svelte", "CSS", "Printing", "jsPDF", "html2canvas", "Debugging", "UX"]
description: "PDF/PNG downloads work fine but browser print breaks image positions. The rendering difference between html2canvas and window.print(), solved with dynamic @media print injection, plus paper size/scale implementation."
cover:
  image: "/images/og/calendar-print-browser-print-bug-paper-sizes.png"
  alt: "Calendar Print Browser Print Bug Paper Sizes"
  hidden: true
---

I built a calendar printing feature for the web. PDF and PNG downloads worked perfectly, but when hitting the browser print button, image positions weren't reflected at all. Same data, so why different results?

---

## Structure: Preview and Hidden Export Target

The calendar print page had this structure:

```
+-- Visible Area ----------------------------+
| [Settings Panel]    [Preview Area]         |
|  - Date range       Calendar preview       |
|  - Theme/Color                             |
|  - Image position slider                   |
+--------------------------------------------+

+-- Hidden Export Target --------------------+
| <div class="fixed -left-[9999px]">        |  <- off-screen
|   <PrintableCalendar ... />               |
| </div>                                    |
+--------------------------------------------+
```

The preview is a scaled-down thumbnail, while the actual export calendar is rendered at full size off-screen (`-left-[9999px]`). PDF/PNG capture this hidden element.

---

## Cause: html2canvas vs window.print()

**Why PDF/PNG work fine:**

```javascript
// html2canvas reads the DOM tree directly and draws it to Canvas
const canvas = await html2canvas(page, {
  scale: getCaptureScale(page),
  useCORS: true,
  backgroundColor: '#ffffff',
});
```

`html2canvas` reads the element's **DOM structure and computed styles** and redraws them onto a Canvas. It doesn't matter whether the element is visible or not. Even with `position: fixed; left: -9999px`, as long as it exists in the DOM, it captures accurately.

**Why printing doesn't work:**

```javascript
// window.print() uses the browser's rendering engine as-is
window.print();
```

`window.print()` sends the **current page rendering result** directly to the printer. Elements at `fixed -left-[9999px]` are outside the print area and are not included in the output. If you hide the preview with a `.no-print` class, the hidden export target is still off-screen, resulting in a **blank page**.

---

## Solution: Dynamic @media print CSS Injection

Solved by dynamically injecting print-specific CSS when the print button is clicked:

```javascript
function printPage() {
  const styleId = 'calendar-print-page-style';

  // Remove existing style
  const existing = document.getElementById(styleId);
  if (existing) existing.remove();

  // Dynamic CSS injection
  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    @media print {
      @page { size: ${paperSize} ${orientation}; margin: 0; }

      /* Hide all other elements */
      body > *:not(.calendar-print-target) {
        display: none !important;
      }

      /* Restore hidden export target to document flow */
      .calendar-print-target {
        position: static !important;
        left: auto !important;
        top: auto !important;
        visibility: visible !important;
      }
    }
  `;
  document.head.appendChild(style);

  // Add class to export target
  const exportEl = getExportElement();
  exportEl.classList.add('calendar-print-target');

  // Clean up after printing
  window.addEventListener('afterprint', () => {
    style.remove();
    exportEl.classList.remove('calendar-print-target');
  }, { once: true });

  window.print();
}
```

The key is restoring the off-screen element to document flow with `position: static !important`. Since it only applies within `@media print`, it doesn't affect the on-screen display.

---

## Also Implemented: Multiple Paper Size Support

Extended from A4-only to A3, A5, Letter, and Legal. Paper size must be reflected in three places:

### 1. Calendar Rendering (CSS)

```javascript
const PAPER_SIZES = {
  a3: { width: 297, height: 420 },
  a4: { width: 210, height: 297 },
  a5: { width: 148, height: 210 },
  letter: { width: 215.9, height: 279.4 },
  legal: { width: 215.9, height: 355.6 },
};

// Swap width/height based on landscape/portrait mode
let pageWidth = orientation === 'landscape'
  ? `${paper.height}mm` : `${paper.width}mm`;
```

### 2. PDF Generation (jsPDF)

```javascript
const pdf = new jsPDF(
  isLandscape ? 'l' : 'p',   // orientation
  'mm',                        // unit
  paperSize                    // 'a3', 'a4', 'letter', etc.
);
```

### 3. Browser Print (@page CSS)

```css
@page { size: A3 landscape; margin: 0; }
```

If all three don't reference the same paper size, the output will differ.

---

## Calendar Scale: CSS Custom Property

Used a CSS custom property `--scale` to uniformly adjust calendar element sizes:

```css
.calendar-page {
  --scale: 1;  /* dynamically set from JavaScript */
}

.month-header {
  font-size: calc(20px * var(--scale));
}

.day-header {
  font-size: calc(11px * var(--scale));
}

.day-number {
  font-size: calc(12px * var(--scale));
}

.task-chip {
  font-size: calc(8px * var(--scale));
}
```

When the slider adjusts from 60% to 140%, `--scale` changes from 0.6 to 1.4, and all text and margins scale proportionally. No need to touch individual elements, making maintenance easy.

---

## UX Improvement: Export Button Placement

Previously, the PDF/PNG/Print buttons were at the bottom of the accordion settings panel. When all settings were collapsed, the buttons were invisible.

```
Before:                        After:
+-- Settings Panel --+          +-- Export ---------+
| > Date range       |          | [PDF] [PNG] [Print]|
| > Theme            |          | A4 - Portrait      |
| > Layout           |          +-------------------+
| > Content          |          +-- Print Settings -+
| > Image            |          | > Date range      |
| > Export  <- here  |          | > Theme           |
+--------------------+          | > Layout          |
                                | > Content         |
                                | > Image           |
                                +-------------------+
```

Placed the export card independently at the top, showing the currently selected paper size and orientation as a label.

---

## Key Takeaways

| Method | Rendering Principle | Off-screen elements |
|--------|--------------------|--------------------|
| html2canvas | Reads DOM structure and reconstructs on Canvas | **Captured** |
| window.print() | Uses browser rendering result as-is | **Ignored** |

**`html2canvas` and `window.print()` use completely different rendering pipelines.** Just because one works doesn't mean the other will. When using a hidden element as an export target, you must restore its position with `@media print` for printing.

---

## References

- [MDN: Window.print()](https://developer.mozilla.org/en-US/docs/Web/API/Window/print)
- [MDN: @page CSS at-rule](https://developer.mozilla.org/en-US/docs/Web/CSS/@page)
- [html2canvas documentation](https://html2canvas.hertzen.com/)
- [jsPDF GitHub](https://github.com/parallax/jsPDF)
