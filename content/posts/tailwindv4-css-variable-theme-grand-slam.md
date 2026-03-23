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
categories: ["Rails", "Frontend"]
---

테마 시스템을 구현할 때 흔히 생각하는 방법은 컴포넌트마다 조건부 클래스를 추가하는 것이다. 하지만 기존 코드를 건드리지 않고 CSS 변수 한 블록만으로 앱 전체 색상을 바꿀 수 있다면? Tailwind v4에서는 그게 가능하다.

---

## Tailwind v4의 CSS 변수 컴파일 방식

이 패턴 전체를 가능하게 만드는 아키텍처 변화는 미묘하지만 근본적이다. Tailwind v4는 유틸리티 클래스를 하드코딩된 값이 아니라 CSS 변수 참조로 컴파일한다.

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

Tailwind v3에서는 `bg-emerald-700`이 `background-color: #047857`로 컴파일됐다. 스타일시트에 hex 값이 직접 박혔다. v4에서는 `background-color: var(--color-emerald-700)`으로 컴파일된다. 실제 색상 값은 `:root`에 선언된 CSS 커스텀 프로퍼티에 저장된다.

**이 차이가 핵심이다.** CSS 커스텀 프로퍼티는 cascade를 따르며, 우선순위가 충분한 셀렉터 안에서 언제든 재정의할 수 있다. 스코프 셀렉터 안에서 `--color-emerald-700`을 오버라이드하면, 그 스코프 내에서 `bg-emerald-700`을 사용하는 모든 요소가 새 값을 즉시 반영한다. JavaScript로 클래스를 교체할 필요도 없고, 리렌더링도 없다. CSS가 원래 처리하는 방식 그대로다.

다크모드 구현의 원리와 똑같다. `<html>`에 `[data-theme="dark"]`나 `.dark` 셀렉터를 붙이면 색상 변수가 오버라이드되고 전체 서브트리가 반응한다. 우리의 멀티 테마 시스템은 이 아이디어를 임의의 색상 팔레트 수만큼 일반화한 것이다.

---

## 테마 구조 설계

앱의 메인 색상이 `emerald` 계열이라면, 테마는 속성 스코프 셀렉터 안에서 `--color-emerald-*` 변수 세트를 통째로 교체하는 방식으로 구현할 수 있다.

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

Wimbledon 블록과 나머지 테마 간의 의도적인 비대칭에 주목할 필요가 있다. Wimbledon은 50–900 전체 스케일을 오버라이드한다. 색상 계열 자체가 초록에서 보라로 완전히 바뀌기 때문이다. 반면 Roland Garros, US Open, Australian Open은 핵심 stop point인 500과 700만 오버라이드한다. 최소 오버라이드 전략은 CSS를 간결하게 유지한다. 기본값과 실제로 달라지는 변수만 재선언하면 된다.

---

## 색상 선택 근거

각 테마의 색상은 해당 대회의 공식 브랜드 아이덴티티에서 가져왔다.

| 테마 | 주색 | 보조색 | 근거 |
|------|------|--------|------|
| Wimbledon | `#522398` (Pantone 268C) | `#00653A` (Pantone 349C) | 올잉글랜드클럽 공식 보라/초록 |
| Roland Garros | `#C95917` | `#02503B` | 붉은 클레이 코트 + 숲 녹색 |
| US Open | `#003DA5` (USTA Blue) | `#FFB300` | USTA 공식 블루 + 골드 |
| Australian Open | `#0085CA` (Process Blue) | `#84BD00` | 공식 블루 + 라임 |

Pantone 기반의 정확한 브랜드 색상을 사용하는 것이 중요한 이유는, CSS 변수 오버라이드가 충분한 명도 대비를 유지해야만 테마 전환이 실제로 동작하기 때문이다. 테마별 `--shadow-focus` 변수는 접근성 측면에서 특히 중요하다. 키보드 포커스 링은 새로운 주색 대비 명확하게 보여야 한다. Wimbledon 보라 위에 일반적인 파란색 glow를 올리거나, Roland Garros 주황 위에 그린 glow를 올리면 시각적으로 충돌한다.

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

`connect()` 라이프사이클 콜백은 페이지 로드마다 저장된 테마를 재적용한다. Hotwire(Turbo Drive) 앱에서는 초기 로드 시 한 번, 그리고 컨트롤러 엘리먼트가 재연결되는 전체 Turbo 네비게이션 시마다 호출된다. Turbo Frame 부분 업데이트의 경우 `<html>` 속성이 이미 설정된 상태이므로 재적용이 필요 없다.

컨트롤러는 `<body>`에 붙인다. 설정 페이지뿐만 아니라 앱 어디서나 테마 버튼을 렌더링할 수 있도록.

```html
<body data-controller="theme">
  ...
</body>
```

`select()` 액션은 각 버튼의 `data-action="theme#select"`로 연결된다. DOM 내에 테마 선택 UI가 몇 개가 있든 모두 `<body>`의 동일한 컨트롤러 인스턴스를 공유한다.

---

## FOUC 방지

Stimulus 컨트롤러는 JavaScript가 파싱된 후에야 실행된다. 그 사이에 페이지가 기본 테마로 깜빡이는 FOUC(Flash of Unstyled Content)가 발생한다. 느린 연결이나 스크립트 파싱이 지연되는 환경에서는 이 간격이 눈에 띄게 길어질 수 있다. 페이지가 초록(기본 emerald 팔레트)으로 렌더링되다가 컨트롤러가 활성화되면 보라색으로 전환되는 것이다. 시각적으로 불쾌하다.

해결책은 `<head>` 안에 인라인 스크립트를 넣어 CSS보다 먼저 테마를 동기적으로 적용하는 것이다.

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

이 스크립트는 HTML 파싱 중 동기적으로 실행된다. 외부 CSS나 JavaScript가 로드되기 전에 먼저 실행된다. 브라우저가 CSSOM을 구성하고 첫 프레임을 그릴 시점에는 `data-app-theme`이 이미 `<html>`에 설정되어 있다. CSS 속성 셀렉터가 즉시 매칭되고, 사용자는 첫 번째 페인트부터 올바른 테마를 보게 된다.

`try/catch`는 `localStorage` 접근이 차단된 환경 — 시크릿 모드의 엄격한 설정, 일부 브라우저 확장 프로그램, 임베디드 웹뷰 — 에서의 에러를 막기 위한 것이다. catch 블록은 의도적으로 비워뒀다. 저장소를 사용할 수 없으면 기본 테마로 표시하는 것이 맞다.

이 인라인 스크립트 in head 기법은 사실상 모든 다크모드 구현이 플래시를 방지하는 방식이다. 검증된 패턴을 그대로 재사용하는 것이다.

---

## 설정 페이지의 테마 선택 UI

테마 선택 UI는 각각 색상 스와치와 미니어처 앱 미리보기를 보여주는 버튼 그리드로 구성한다. 버튼 하나의 구조:

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

스와치와 프리뷰가 Tailwind 클래스 대신 인라인 `style` 속성으로 하드코딩된 hex 값을 사용한다는 점에 주목하자. 이것은 의도적인 선택이다. 미리보기는 현재 활성 테마에 관계없이 항상 해당 테마의 색상을 보여줘야 한다. 스와치에 `bg-emerald-700`을 사용하면 활성 테마가 바뀔 때 스와치 색상도 함께 바뀐다 — 정적 참조로서의 미리보기 목적이 무너진다.

`ring-2 ring-offset-2`는 Stimulus `_apply()`에서 활성 테마일 때 토글된다. `aria-pressed`도 함께 업데이트하므로 스크린 리더는 활성 테마 버튼을 "Wimbledon, 눌림"으로 올바르게 고지한다.

---

## 다크모드와의 조합

테마 시스템은 다크모드와 자연스럽게 조합된다. 두 시스템은 직교하는 셀렉터를 사용한다.

```css
/* 테마: 주 색상 스케일 오버라이드 */
[data-app-theme="wimbledon"] {
  --color-emerald-700: #522398;
}

/* 다크모드: 배경색과 텍스트 톤 오버라이드 */
.dark {
  --color-gray-50: #1a1a1a;
  --color-gray-900: #f5f5f5;
}

/* 조합: 다크 Wimbledon 테마 */
.dark [data-app-theme="wimbledon"] {
  --color-emerald-700: #6b35b0; /* 어두운 배경에서 약간 밝게 */
}
```

이것으로 `테마 × 모드` 매트릭스가 만들어진다. 작성해야 할 CSS는 별도의 값이 필요한 교차점 블록뿐이다. 대부분의 경우 기본 테마 오버라이드와 다크모드 오버라이드만으로 충분하고, 조합 상태는 자동으로 처리된다.

---

## 왜 이 방식이 좋은가

**기존 코드 수정 없음.** 컴포넌트 전체를 뒤져서 `bg-emerald-700` 참조를 찾고 조건부 로직으로 감쌀 필요가 없다. 변경 범위가 CSS 토큰 파일 하나로 완전히 한정된다.

**런타임 오버헤드 없음.** 테마 전환은 `<html>`에 속성 하나를 설정하는 것이다. 나머지는 브라우저 내장 CSS cascade가 처리한다. DOM을 순회하는 JavaScript도 없고, 클래스 조작도 없고, 가상 DOM 리컨실리에이션도 없다.

**간단한 확장성.** 새 테마 추가는 CSS 블록 하나 추가하면 끝이다. 테마 삭제는 그 블록을 지우면 된다. 테마 수가 늘어도 코드 복잡성은 다른 곳에서 증가하지 않는다.

**테스트 가능하고 예측 가능함.** 모든 테마는 변수 값의 결정론적 집합이다. `document.documentElement.setAttribute('data-app-theme', 'wimbledon')`을 브라우저나 테스트 환경에서 호출하고 computed styles를 검사하면 시각적 정확성을 검증할 수 있다.

핵심 조력자는 Tailwind v4의 아키텍처적 전환이다 — 컴파일 결과물에서 하드코딩된 색상 값 대신 CSS 변수 참조를 사용하게 된 것. 이 변화는 테마 시스템 구축 비용을 크게 낮췄다. 그리고 이것은 전용 테마 기능으로 의도된 것이 아니라, Tailwind v4의 새로운 CSS-first 구성 모델의 결과로 발생한 변화다. 우리는 전용 테마 API가 아니라 컴파일러가 동작하는 방식을 활용하는 것이다. 그래서 이 패턴은 마이너 버전에 걸쳐 안정적이다.

---

## 핵심 정리

- Tailwind v4는 `bg-emerald-700`을 하드코딩 hex가 아닌 `var(--color-emerald-700)`으로 컴파일한다. 이 변화가 이 패턴 전체의 기반이다.
- `<html>`의 속성 셀렉터(`[data-app-theme="..."]`) 안에서 CSS 커스텀 프로퍼티를 오버라이드하면, 모든 자손 요소 — 앱 전체 — 에 HTML 변경 없이 전파된다.
- 사용자 선택을 `localStorage`에 저장하고 `<head>` 안의 동기 인라인 스크립트로 적용해 FOUC를 제거한다. 모든 다크모드 구현이 사용하는 기법과 동일하다.
- Stimulus 컨트롤러를 `<body>`에 마운트해서 테마 버튼이 앱 어디에나 있을 수 있도록 한다.
- 테마 선택 UI의 스와치는 Tailwind 클래스가 아닌 인라인 style로 하드코딩해야 한다. 현재 활성 테마에 관계없이 항상 해당 테마의 색상을 보여줘야 하기 때문이다.
- `.dark [data-app-theme="..."]` 교차 셀렉터로 다크모드와 자연스럽게 조합된다.
- 새 테마는 CSS 블록 하나 추가로 끝난다. 다른 곳은 아무것도 바꿀 필요 없다.
