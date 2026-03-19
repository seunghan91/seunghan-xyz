---
title: "Tailwind CSS v4 테마 시스템 삽질기 — CSS 변수 오버라이드가 안 먹는 이유"
date: 2026-03-19
draft: false
tags: ["Tailwind CSS", "CSS", "디버깅", "테마", "Rails", "CSS Variables"]
description: "Tailwind v4에서 Grand Slam 테마(Wimbledon, Roland Garros 등)를 적용하려다 삽질한 기록. arbitrary value로 전수 교체했다가 전부 회색이 되고, CSS 변수 우선순위 문제까지 — 결국 해결은 CSS 로드 순서 한 줄이었다."
---

Rails + Tailwind CSS v4 프로젝트에서 그랜드슬램 테마 시스템(Wimbledon 보라, Roland Garros 오렌지 등)을 적용하려다 이틀을 날렸다. 결론부터 말하면 **CSS 파일 로드 순서** 한 줄이 문제였다.

---

## 목표

설정에서 테마를 바꾸면 앱 전체 색상이 바뀌는 시스템. `data-app-theme="wimbledon"`을 `<html>`에 설정하면 초록색(emerald) 기반 UI가 보라색으로 전환되어야 한다.

```css
/* tokens.css */
[data-app-theme="wimbledon"] {
  --color-emerald-50: #f5f0ff;
  --color-emerald-600: #6a1a73;
  --color-primary: #522398;
  /* ... */
}
```

Tailwind v4는 `bg-emerald-600`을 `background-color: var(--color-emerald-600)`으로 컴파일하므로, CSS 변수만 오버라이드하면 기존 클래스가 자동으로 테마를 따른다.

---

## 삽질 1: arbitrary value로 전수 교체 — 전부 회색

"테마에 맞게 CSS 변수를 직접 참조하자"는 생각으로 프로젝트 전체의 `bg-emerald-600`을 `bg-[color:var(--color-primary-600)]`으로 교체했다. 93개 파일, 540개 이상의 클래스를 바꿨다.

```erb
<%# Before %>
<button class="bg-emerald-600 hover:bg-emerald-700">

<%# After (WRONG) %>
<button class="bg-[color:var(--color-primary-600)] hover:bg-[color:var(--color-primary-700)]">
```

결과: **전체 UI가 회색으로 변했다.**

### 원인

Tailwind v4의 JIT 컴파일러가 `bg-[color:var(--color-primary-600)]` 같은 arbitrary value를 ERB 파일에서 **스캔하지 못했다.** 빌드 출력(tailwind.css)에 해당 클래스가 아예 생성되지 않았다.

```bash
# 빌드 결과에서 검색 — 없다
$ grep 'bg-\[color:var' app/assets/builds/tailwind.css
# (nothing)
```

반면 원래 클래스는 정상:
```bash
$ grep 'bg-emerald-600' app/assets/builds/tailwind.css
.bg-emerald-600{background-color:var(--color-emerald-600)}
```

### 교훈

> Tailwind v4는 `bg-emerald-600`을 이미 `var(--color-emerald-600)` CSS 변수로 컴파일한다. arbitrary value로 바꿀 필요가 전혀 없다.

모든 변경을 `git checkout`으로 원복했다.

---

## 삽질 2: CSS 변수 오버라이드가 안 먹는다

원래 클래스(`bg-emerald-600`)를 살리고 테마를 적용했더니, `--color-emerald-600`은 정상 오버라이드되는데 `--color-primary`는 여전히 기본값(초록색)이었다.

```js
// 브라우저 콘솔에서 확인
document.documentElement.setAttribute('data-app-theme', 'wimbledon');
getComputedStyle(document.documentElement)
  .getPropertyValue('--color-emerald-600'); // "#6a1a73" ✅ 보라색
getComputedStyle(document.documentElement)
  .getPropertyValue('--color-primary');     // "#10b981" ❌ 여전히 초록색!
```

### 원인: CSS 로드 순서 + 동일 specificity

CSS 로드 순서:
```erb
<%= stylesheet_link_tag "tokens", "tailwind", "application" %>
```

1. **tokens.css** — `:root` 변수 정의 + `[data-app-theme]` 오버라이드
2. **tailwind.css** — Tailwind가 tokens.css의 `:root` 값을 흡수해서 자체 `:root` 블록에 포함
3. **application.css** — 커스텀 유틸리티 클래스

문제는 specificity:

| 선택자 | Specificity | 파일 |
|--------|------------|------|
| `[data-app-theme="wimbledon"]` | (0,1,0) | tokens.css (1번째 로드) |
| `:root` | (0,1,0) | tailwind.css (2번째 로드) |

**동일한 specificity에서는 나중에 로드된 선언이 이긴다.** Tailwind의 `:root { --color-primary: #10b981 }`이 tokens.css의 `[data-app-theme] { --color-primary: #522398 }`을 덮어쓴 것이다.

참고로 `--color-emerald-600`은 오버라이드가 됐는데, 이건 Tailwind `:root`에서 `--color-emerald-600: oklch(...)` 형태로 선언하고 tokens.css에서 `[data-app-theme]`으로 hex 값을 덮어쓰면서, attribute selector의 매칭 조건이 달라 별도 경로로 적용되었기 때문이다.

### 해결: 테마 블록을 application.css로 이동

```erb
<%# 로드 순서: tokens → tailwind → application %>
<%= stylesheet_link_tag "tokens", "tailwind", "application" %>
```

`[data-app-theme]` 블록을 tokens.css에서 **application.css 맨 끝**으로 이동했다. tailwind.css 이후에 로드되므로, 동일 specificity에서 application.css가 이긴다.

```css
/* application.css (tailwind 이후 로드) */

/* Wimbledon: Purple + Green */
[data-app-theme="wimbledon"] {
  --color-emerald-50: #f5f0ff;
  --color-emerald-600: #6a1a73;
  --color-primary: #522398;
  --color-primary-500: #7B2082;
  /* ... */
}
```

결과: 모든 변수가 정상 오버라이드.

---

## 삽질 3: Turbo `&&` 파싱 에러

Turbo Drive로 페이지 전환할 때마다 콘솔에 에러가 발생했다:

```
SyntaxError: Failed to execute 'appendChild' on 'Node': Unexpected token '&'
```

### 원인

`<head>` 안의 inline `<script>`에 `&&` 연산자가 있었다. Turbo가 페이지 전환 시 `<head>`의 script를 DOM에 복사하는데, 이 과정에서 `&&`를 HTML 엔티티로 파싱하면서 에러가 발생했다.

### 해결

```html
<%# data-turbo-permanent으로 Turbo가 매번 복사하지 않게 함 %>
<script data-turbo-permanent id="theme-restore">
  // ... && 연산자가 포함된 코드 ...
</script>
```

`data-turbo-permanent`를 추가하면 Turbo가 이 script를 최초 로드 후 재사용하므로 복사 에러가 사라진다.

---

## 정리: 핵심 교훈 3가지

### 1. Tailwind v4에서 색상 테마를 적용하려면 CSS 변수만 오버라이드하라

```css
/* ✅ 올바른 방법: emerald-* 클래스 그대로 두고 변수만 바꿈 */
[data-app-theme="wimbledon"] {
  --color-emerald-600: #6a1a73;
}

/* ❌ 잘못된 방법: arbitrary value로 클래스 전수 교체 */
bg-[color:var(--color-primary-600)]  /* Tailwind이 생성 못 할 수 있음 */
```

### 2. CSS 변수 오버라이드는 **로드 순서**가 specificity만큼 중요하다

`:root`와 `[data-attr="value"]`는 specificity가 같다 (둘 다 `(0,1,0)`). 나중에 로드된 파일이 이긴다.

```
tokens.css → tailwind.css → application.css
                ↑ Tailwind가 :root 변수를 여기에 넣음
                  → 테마 오버라이드는 반드시 이 뒤에 와야 함
```

### 3. Turbo Drive + inline script에서 `&&`는 `data-turbo-permanent`으로 보호하라

Turbo가 `<head>` script를 DOM으로 복사할 때 특수문자가 깨질 수 있다. `data-turbo-permanent`로 한 번만 로드되게 하면 해결된다.

---

## 최종 변경 diff

```
tokens.css       → [data-app-theme] 블록 제거 (application.css로 이동)
application.css  → 테마 오버라이드 블록 추가 (tailwind.css 뒤에 로드)
application.html → <script data-turbo-permanent> 추가
```

총 3개 파일, 실질적 코드 변경은 0줄. **코드를 바꾼 게 아니라 CSS 선언 위치만 옮겼다.**
