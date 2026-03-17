---
title: "Tailwind v4 CSS 변수 오버라이드로 앱 전체 테마 교체하기"
date: 2026-03-17
draft: false
tags: ["Tailwind CSS", "CSS Custom Properties", "Stimulus", "Rails", "테마 시스템", "Hotwire"]
description: "Tailwind v4에서 CSS 변수 오버라이드만으로 앱 전체 색상을 바꾸는 테마 시스템 구현. data-app-theme 속성 셀렉터 + Stimulus + localStorage 패턴으로 FOUC 없이 다크모드처럼 여러 컬러 테마를 지원하는 방법."
cover:
  image: "/images/og/tailwindv4-css-variable-theme-grand-slam.png"
  alt: "Tailwind v4 CSS Variable Theme System"
  hidden: true
---

테마 시스템을 구현할 때 흔히 생각하는 방법은 컴포넌트마다 조건부 클래스를 추가하는 것이다. 하지만 기존 코드를 건드리지 않고 CSS 변수 한 블록만으로 앱 전체 색상을 바꿀 수 있다면? Tailwind v4에서는 그게 가능하다.

---

## Tailwind v4의 CSS 변수 컴파일 방식

Tailwind v4는 유틸리티 클래스를 CSS 변수 참조로 컴파일한다.

```css
/* Tailwind v4가 생성하는 CSS */
.bg-emerald-700 {
  background-color: var(--color-emerald-700);
}
.text-emerald-600 {
  color: var(--color-emerald-600);
}
.border-emerald-500 {
  border-color: var(--color-emerald-500);
}
```

`bg-emerald-700`이 `background-color: #047857`(하드코딩)이 아니라 `var(--color-emerald-700)` 참조라는 뜻이다. **`--color-emerald-700` 변수 값만 바꾸면 `bg-emerald-700`을 쓰는 모든 요소가 한꺼번에 바뀐다.**

---

## 테마 구조 설계

앱의 메인 색상이 `emerald` 계열이라면, 테마는 `--color-emerald-*` 변수를 통째로 교체하는 방식으로 구현할 수 있다.

```css
/* tokens.css — 기존 emerald 변수는 그대로 두고, 테마 블록만 추가 */

[data-app-theme="wimbledon"] {
  --color-emerald-50:  #f5f0ff;
  --color-emerald-100: #ede0ff;
  --color-emerald-200: #dcc8ff;
  --color-emerald-300: #c4a3ff;
  --color-emerald-400: #a87eff;
  --color-emerald-500: #7B2082;
  --color-emerald-600: #6a1a73;
  --color-emerald-700: #522398;
  --color-emerald-800: #3d1870;
  --color-emerald-900: #2c1050;
  --color-primary: #522398;
  --color-accent:  #00653A;
  --shadow-focus: 0 0 0 3px rgba(82, 35, 152, 0.2);
}

[data-app-theme="roland-garros"] {
  --color-emerald-500: #C95917;
  --color-emerald-700: #963d08;
  --color-primary: #C95917;
  --color-accent:  #02503B;
  --shadow-focus: 0 0 0 3px rgba(201, 89, 23, 0.2);
}

[data-app-theme="us-open"] {
  --color-emerald-500: #003DA5;
  --color-emerald-700: #002370;
  --color-primary: #003DA5;
  --color-accent:  #FFB300;
  --shadow-focus: 0 0 0 3px rgba(0, 61, 165, 0.2);
}

[data-app-theme="australian-open"] {
  --color-emerald-500: #0085CA;
  --color-emerald-700: #005a8c;
  --color-primary: #0085CA;
  --color-accent:  #84BD00;
  --shadow-focus: 0 0 0 3px rgba(0, 133, 202, 0.2);
}
```

`<html>` 요소에 `data-app-theme="wimbledon"`이 붙으면, 그 하위의 모든 `bg-emerald-700`, `text-emerald-500`, `border-emerald-600` 등이 Wimbledon 보라색으로 바뀐다. HTML 한 줄도 수정하지 않고.

---

## 색상 선택 근거

각 테마의 색상은 해당 대회의 공식 아이덴티티 색상에서 가져왔다.

| 테마 | 주색 | 보조색 | 근거 |
|------|------|--------|------|
| Wimbledon | `#522398` (Pantone 268C) | `#00653A` (Pantone 349C) | 올잉글랜드클럽 공식 보라/초록 |
| Roland Garros | `#C95917` | `#02503B` | 붉은 클레이 코트 + 숲 녹색 |
| US Open | `#003DA5` (USTA Blue) | `#FFB300` | USTA 공식 블루 + 골드 |
| Australian Open | `#0085CA` (Process Blue) | `#84BD00` | 공식 블루 + 라임 |

---

## Stimulus 컨트롤러

테마 선택, 저장, 적용을 담당하는 Stimulus 컨트롤러.

```javascript
// app/javascript/controllers/theme_controller.js
import { Controller } from "@hotwired/stimulus"

const STORAGE_KEY = "app-theme"

export default class extends Controller {
  connect() {
    const saved = localStorage.getItem(STORAGE_KEY) || "default"
    this._apply(saved)
  }

  select(event) {
    const theme = event.currentTarget.dataset.themeValue
    localStorage.setItem(STORAGE_KEY, theme)
    this._apply(theme)
  }

  _apply(theme) {
    if (theme === "default") {
      document.documentElement.removeAttribute("data-app-theme")
    } else {
      document.documentElement.setAttribute("data-app-theme", theme)
    }

    // 활성 버튼 표시
    this.element.querySelectorAll("[data-theme-value]").forEach(el => {
      const isActive = el.dataset.themeValue === theme
      el.setAttribute("aria-pressed", isActive ? "true" : "false")
      el.classList.toggle("ring-2", isActive)
      el.classList.toggle("ring-offset-2", isActive)
    })
  }
}
```

컨트롤러는 `<body>`에 붙인다. 설정 페이지뿐만 아니라 앱 어디서나 테마 버튼을 렌더링할 수 있도록.

```html
<body data-controller="theme">
  ...
</body>
```

---

## FOUC 방지

Stimulus 컨트롤러는 JavaScript가 파싱된 후에야 실행된다. 그 사이에 페이지가 기본 테마로 깜빡이는 FOUC(Flash of Unstyled Content)가 발생한다.

해결책은 `<head>` 안에 인라인 스크립트를 넣어 CSS보다 먼저 테마를 적용하는 것이다.

```html
<!-- layouts/application.html.erb의 <head> 맨 위 -->
<script>
  try {
    var t = localStorage.getItem('app-theme');
    if (t && t !== 'default') {
      document.documentElement.setAttribute('data-app-theme', t);
    }
  } catch(e) {}
</script>
```

`try/catch`는 localStorage 접근이 차단된 환경(시크릿 모드 일부 설정 등)에서의 에러를 막기 위한 것이다. 10줄도 안 되는 코드가 다크모드 구현과 동일한 문제를 동일한 방식으로 해결한다.

---

## 설정 페이지의 테마 선택 UI

버튼 하나의 구조:

```html
<button
  type="button"
  data-action="theme#select"
  data-theme-value="wimbledon"
  class="flex flex-col items-center gap-2 p-3 rounded-xl border-2 border-transparent
         hover:border-emerald-300 transition-all duration-150 cursor-pointer"
  aria-pressed="false"
>
  <!-- 색상 스와치 -->
  <div class="w-16 h-4 rounded-full overflow-hidden flex">
    <div class="flex-1" style="background: #522398;"></div>
    <div class="flex-1" style="background: #00653A;"></div>
  </div>

  <!-- 미니 앱 프리뷰 -->
  <div class="w-12 h-16 rounded-lg overflow-hidden border border-gray-200"
       style="background: #f5f0ff;">
    <div class="h-3 w-full" style="background: #522398;"></div>
    <div class="p-1 space-y-1">
      <div class="h-1.5 rounded" style="background: #7B2082; opacity: 0.7;"></div>
      <div class="h-1.5 rounded w-3/4" style="background: #7B2082; opacity: 0.4;"></div>
    </div>
  </div>

  <span class="text-xs font-medium text-gray-700">Wimbledon</span>
</button>
```

`ring-2 ring-offset-2`는 Stimulus `_apply()`에서 활성 테마일 때 토글된다. `aria-pressed`도 함께 업데이트하므로 접근성도 챙겨진다.

---

## 왜 이 방식이 좋은가

1. **기존 코드 수정 없음**: `bg-emerald-700`이 쓰인 컴포넌트를 찾아다닐 필요가 없다.
2. **런타임 오버헤드 없음**: JavaScript로 클래스를 교체하는 것이 아니라 CSS 변수 하나가 바뀌는 것.
3. **다크모드와 조합 가능**: `[data-app-theme="wimbledon"].dark {}` 처럼 다크모드와 교차 적용도 된다.
4. **점진적 확장**: 새 테마 추가는 CSS 블록 하나 추가하면 끝.

Tailwind v4로 올라오면서 `bg-*` 유틸리티가 하드코딩 값이 아니라 CSS 변수 참조로 바뀐 것이 핵심이다. 이 변화가 테마 시스템 구현 비용을 크게 낮춰준다.
