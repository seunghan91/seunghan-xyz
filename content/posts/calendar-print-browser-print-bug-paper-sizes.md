---
title: "웹 캘린더 인쇄 기능의 함정: window.print()는 off-screen 엘리먼트를 무시한다"
date: 2026-03-06
draft: false
tags: ["Svelte", "CSS", "인쇄", "jsPDF", "html2canvas", "디버깅", "UX"]
description: "PDF/PNG 다운로드는 정상인데 브라우저 인쇄만 이미지 위치가 틀어지는 버그. html2canvas vs window.print()의 렌더링 차이, @media print 동적 주입으로 해결한 과정과 용지 크기/스케일 기능 구현기."
---

웹에서 캘린더를 출력하는 기능을 만들었다. PDF와 PNG 다운로드는 완벽한데, 브라우저 인쇄 버튼만 누르면 이미지 위치가 전혀 반영되지 않았다. 같은 데이터를 쓰는데 왜 결과가 다를까?

---

## 구조: 프리뷰와 숨겨진 내보내기 타겟

캘린더 출력 페이지의 구조는 이렇다:

```
┌─ 화면에 보이는 영역 ─────────────────┐
│ [설정 패널]        [프리뷰 영역]      │
│  - 기간 선택        캘린더 미리보기    │
│  - 테마/색상                          │
│  - 이미지 위치 슬라이더               │
└──────────────────────────────────────┘

┌─ 숨겨진 내보내기 타겟 ───────────────┐
│ <div class="fixed -left-[9999px]">   │  ← 화면 밖
│   <PrintableCalendar ... />          │
│ </div>                               │
└──────────────────────────────────────┘
```

프리뷰는 축소된 미리보기고, 실제 내보내기용 캘린더는 원본 크기로 화면 밖(`-left-[9999px]`)에 렌더링된다. PDF/PNG는 이 숨겨진 엘리먼트를 캡처한다.

---

## 원인: html2canvas vs window.print()

**PDF/PNG가 잘 되는 이유:**

```javascript
// html2canvas는 DOM 트리를 직접 읽어서 Canvas로 그린다
const canvas = await html2canvas(page, {
  scale: getCaptureScale(page),
  useCORS: true,
  backgroundColor: '#ffffff',
});
```

`html2canvas`는 엘리먼트의 **DOM 구조와 계산된 스타일**을 읽어서 Canvas에 다시 그리는 방식이다. 화면에 보이든 안 보이든 상관없다. `position: fixed; left: -9999px`이어도 DOM에 존재하면 정확히 캡처한다.

**인쇄가 안 되는 이유:**

```javascript
// window.print()는 브라우저의 렌더링 엔진을 그대로 사용한다
window.print();
```

`window.print()`는 **현재 페이지의 렌더링 결과**를 그대로 프린터로 보낸다. `fixed -left-[9999px]`에 있는 엘리먼트는 프린트 영역 밖이므로 출력에 포함되지 않는다. `.no-print` 클래스로 프리뷰를 숨기면, 숨겨진 내보내기 타겟도 여전히 화면 밖에 있어서 **빈 페이지**만 나온다.

---

## 해결: @media print CSS 동적 주입

인쇄 버튼 클릭 시 동적으로 print 전용 CSS를 주입하는 방식으로 해결했다:

```javascript
function printPage() {
  const styleId = 'calendar-print-page-style';

  // 기존 스타일 제거
  const existing = document.getElementById(styleId);
  if (existing) existing.remove();

  // 동적 CSS 주입
  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    @media print {
      @page { size: ${paperSize} ${orientation}; margin: 0; }

      /* 다른 모든 요소 숨기기 */
      body > *:not(.calendar-print-target) {
        display: none !important;
      }

      /* 숨겨진 내보내기 타겟을 화면에 복원 */
      .calendar-print-target {
        position: static !important;
        left: auto !important;
        top: auto !important;
        visibility: visible !important;
      }
    }
  `;
  document.head.appendChild(style);

  // 내보내기 타겟에 클래스 부여
  const exportEl = getExportElement();
  exportEl.classList.add('calendar-print-target');

  // 인쇄 후 정리
  window.addEventListener('afterprint', () => {
    style.remove();
    exportEl.classList.remove('calendar-print-target');
  }, { once: true });

  window.print();
}
```

핵심은 `position: static !important`으로 off-screen 엘리먼트를 문서 흐름으로 복원하는 것이다. `@media print` 안에서만 적용되므로 화면 표시에는 영향 없다.

---

## 함께 구현: 다중 용지 크기 지원

A4만 지원하던 것을 A3, A5, Letter, Legal까지 확장했다. 세 군데에서 모두 용지 크기를 반영해야 한다:

### 1. 캘린더 렌더링 (CSS)

```javascript
const PAPER_SIZES = {
  a3: { width: 297, height: 420 },
  a4: { width: 210, height: 297 },
  a5: { width: 148, height: 210 },
  letter: { width: 215.9, height: 279.4 },
  legal: { width: 215.9, height: 355.6 },
};

// 가로/세로 모드에 따라 width/height 반전
let pageWidth = orientation === 'landscape'
  ? `${paper.height}mm` : `${paper.width}mm`;
```

### 2. PDF 생성 (jsPDF)

```javascript
const pdf = new jsPDF(
  isLandscape ? 'l' : 'p',   // orientation
  'mm',                        // unit
  paperSize                    // 'a3', 'a4', 'letter' 등
);
```

### 3. 브라우저 인쇄 (@page CSS)

```css
@page { size: A3 landscape; margin: 0; }
```

세 가지가 모두 같은 용지 크기를 참조하지 않으면 출력 결과가 달라진다.

---

## 캘린더 스케일: CSS Custom Property 활용

달력 요소의 크기를 일괄 조절하기 위해 CSS custom property `--scale`을 사용했다:

```css
.calendar-page {
  --scale: 1;  /* JavaScript에서 동적으로 설정 */
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

슬라이더로 60~140% 범위를 조절하면 `--scale`이 0.6~1.4로 바뀌고, 모든 텍스트와 여백이 비례해서 조절된다. 개별 요소를 하나씩 건드리지 않아도 되니 유지보수가 편하다.

---

## UX 개선: 내보내기 버튼 위치

기존에는 PDF/PNG/인쇄 버튼이 아코디언 설정 패널의 맨 아래에 있었다. 설정을 다 접으면 버튼이 안 보인다.

```
Before:                        After:
┌─ 설정 패널 ──────┐          ┌─ 내보내기 ─────────┐
│ ▸ 기간 선택      │          │ [PDF] [PNG] [인쇄]  │
│ ▸ 테마           │          │ A4 · 세로           │
│ ▸ 레이아웃       │          └────────────────────┘
│ ▸ 콘텐츠         │          ┌─ 출력 설정 ────────┐
│ ▸ 이미지         │          │ ▸ 기간 선택        │
│ ▸ 내보내기  ← 여기│          │ ▸ 테마             │
└─────────────────┘          │ ▸ 레이아웃         │
                             │ ▸ 콘텐츠           │
                             │ ▸ 이미지           │
                             └────────────────────┘
```

내보내기 카드를 최상단에 독립 배치하고, 현재 선택된 용지 크기와 방향을 라벨로 보여준다.

---

## 핵심 교훈

| 방식 | 렌더링 원리 | off-screen 요소 |
|------|------------|-----------------|
| html2canvas | DOM 구조를 읽어 Canvas에 재구성 | **캡처됨** |
| window.print() | 브라우저 렌더링 결과를 그대로 사용 | **무시됨** |

**`html2canvas`와 `window.print()`는 완전히 다른 렌더링 파이프라인**이다. 하나가 잘 된다고 다른 하나도 될 거라 생각하면 안 된다. 숨겨진 엘리먼트를 내보내기 타겟으로 쓰는 패턴에서는 인쇄 시 반드시 `@media print`로 위치를 복원해야 한다.

---

## 참고

- [MDN: Window.print()](https://developer.mozilla.org/en-US/docs/Web/API/Window/print)
- [MDN: @page CSS at-rule](https://developer.mozilla.org/en-US/docs/Web/CSS/@page)
- [html2canvas 공식 문서](https://html2canvas.hertzen.com/)
- [jsPDF GitHub](https://github.com/parallax/jsPDF)
