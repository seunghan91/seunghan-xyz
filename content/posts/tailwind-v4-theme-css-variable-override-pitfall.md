---
title: "Tailwind v4 테마 적용 삽질기 — CSS 변수가 안 먹는 진짜 이유"
date: 2026-03-19
draft: false
tags: ["Tailwind CSS", "CSS Variables", "디버깅", "테마", "Rails", "Propshaft"]
description: "Tailwind v4에서 멀티 테마를 만들다 겪은 세 가지 삽질. arbitrary value 전수 교체, CSS 변수 우선순위 함정, Turbo 파싱 에러까지."
---

Rails + Tailwind CSS v4 프로젝트에서 그랜드슬램 테마 시스템을 만들었다. 설정에서 Wimbledon(보라), Roland Garros(오렌지), US Open(네이비), Australian Open(스카이블루)을 고르면 앱 전체 색상이 바뀌는 기능이다.

이틀을 날렸다. 결론부터 말하면 **CSS 파일 로드 순서** 한 줄이 문제였다.

---

## 배경: Tailwind v4의 CSS 변수 컴파일 방식

Tailwind v4는 v3과 완전히 다른 방식으로 색상을 처리한다. 가장 중요한 변화는 **모든 유틸리티 클래스가 CSS 변수를 통해 동작한다는 것**이다.

```css
/* Tailwind v4가 bg-emerald-600을 컴파일한 결과 */
.bg-emerald-600 {
  background-color: var(--color-emerald-600);
}
```

v3에서는 `bg-emerald-600`이 `background-color: #059669` 같은 하드코딩 hex로 컴파일됐다. v4에서는 CSS 변수 참조로 바뀌었다. 이 차이가 테마 시스템의 핵심이다.

Tailwind v4는 빌드 시 `:root`에 모든 색상 변수를 선언한다:

```css
:root {
  --color-emerald-50: oklch(97.9% .021 166.113);
  --color-emerald-100: oklch(95% .052 163.051);
  /* ... */
  --color-emerald-600: oklch(59.6% .145 163.225);
  --color-emerald-900: oklch(37.8% .077 168.94);
}
```

이 변수를 오버라이드하면 `bg-emerald-600`이 자동으로 새 색상을 따른다. **코드 수정 없이 CSS 변수만 바꾸면 된다.** 이 원리를 이용해 테마 시스템을 설계했다.

---

## 테마 설계: data-app-theme으로 색상 전환

`<html>` 요소에 `data-app-theme` 속성을 설정하고, CSS에서 이 속성에 따라 `--color-emerald-*` 변수를 오버라이드하는 구조다:

```css
/* tokens.css */
[data-app-theme="wimbledon"] {
  --color-emerald-50: #f5f0ff;
  --color-emerald-600: #6a1a73;  /* 보라색 */
  --color-primary: #522398;
  --color-primary-500: #7B2082;
}

[data-app-theme="roland-garros"] {
  --color-emerald-50: #fff4ec;
  --color-emerald-600: #b04a0d;  /* 오렌지 */
  --color-primary: #C95917;
}
```

JavaScript나 서버 사이드에서 `data-app-theme`을 바꾸면 전체 UI 색상이 전환된다:

```javascript
document.documentElement.setAttribute('data-app-theme', 'wimbledon');
```

이론상 완벽해 보였다. 하지만 여기서부터 삽질이 시작됐다.

---

## 삽질 1: arbitrary value 전수 교체 — 93개 파일이 회색으로

"CSS 변수를 직접 참조하면 더 명확하지 않을까?"라는 생각으로, 프로젝트 전체의 emerald/amber 하드코딩 클래스를 Tailwind arbitrary value 문법으로 교체했다.

```erb
<%# Before — 원래 코드 %>
<button class="bg-emerald-600 hover:bg-emerald-700 text-white">

<%# After — arbitrary value로 교체 (이게 문제) %>
<button class="bg-[color:var(--color-primary-600)] hover:bg-[color:var(--color-primary-700)] text-white">
```

5개 에이전트를 병렬로 돌려서 93개 파일, 540곳 이상을 교체했다. 빌드도 성공, 서버도 정상 기동. 하지만 브라우저를 열자:

**전체 UI가 회색이었다.**

### 원인: JIT 스캐너가 arbitrary value를 인식하지 못함

Tailwind v4의 JIT 엔진은 소스 파일을 정적 분석해서 사용된 클래스를 추출한다. ERB 파일 안의 `bg-[color:var(--color-primary-600)]` 같은 복잡한 arbitrary value는 **스캐너가 제대로 파싱하지 못했다**.

```bash
# 빌드 결과에서 확인 — 클래스가 아예 생성되지 않았다
$ grep 'bg-\[color:var' app/assets/builds/tailwind.css
# (nothing)

# 반면 원래 emerald 클래스는 정상
$ grep 'bg-emerald-600' app/assets/builds/tailwind.css
.bg-emerald-600{background-color:var(--color-emerald-600)}
```

Tailwind 공식 문서에서도 이 점을 명확히 한다:

> Tailwind는 소스 코드를 정적으로 분석합니다. 런타임에 구성되는 클래스명은 감지할 수 없습니다.

arbitrary value가 ERB의 `<%= %>`와 조합되거나, 특수문자가 많이 포함된 경우 스캐너가 유효한 클래스로 인식하지 못한다. 특히 `[color:var(--color-primary-600)]` 같은 패턴은 괄호가 중첩되어 파서가 경계를 잘못 잡을 수 있다.

### 교훈

> Tailwind v4는 `bg-emerald-600`을 이미 `var(--color-emerald-600)`으로 컴파일한다. arbitrary value로 바꿀 필요가 전혀 없다. 오히려 JIT 스캔 실패 위험만 높아진다.

`git checkout`으로 93개 파일을 모두 원복했다.

---

## 삽질 2: CSS 변수 오버라이드가 안 먹는다

arbitrary value를 포기하고 원래 방식으로 돌아왔다. `bg-emerald-600` 클래스 그대로 두고, tokens.css에서 `[data-app-theme]`으로 `--color-emerald-*` 변수를 오버라이드.

테마를 wimbledon으로 바꾸고 브라우저 콘솔에서 확인했다:

```javascript
document.documentElement.setAttribute('data-app-theme', 'wimbledon');

const root = getComputedStyle(document.documentElement);
root.getPropertyValue('--color-emerald-600');  // "#6a1a73" ✅ 보라색!
root.getPropertyValue('--color-primary');       // "#10b981" ❌ 여전히 초록색!
```

`--color-emerald-600`은 정상 오버라이드되는데 `--color-primary`는 여전히 기본 초록색이다. `--color-primary`를 참조하는 `theme-accent-panel`, `theme-button-primary` 같은 커스텀 클래스들이 전부 초록색 그대로다.

### 원인: CSS 로드 순서 + 동일 specificity

프로젝트의 CSS 로드 순서:

```erb
<%= stylesheet_link_tag "tokens", "tailwind", "application" %>
```

1. **tokens.css** 로드 → `:root` 변수 정의 + `[data-app-theme]` 오버라이드
2. **tailwind.css** 로드 → Tailwind가 tokens.css의 `:root` 값을 흡수해서 자체 `:root` 블록에 포함
3. **application.css** 로드 → 커스텀 유틸리티 클래스

여기서 핵심: **Tailwind v4는 tokens.css의 `:root` 변수를 흡수해서 tailwind.css의 `:root` 블록에 포함시킨다.** 그래서 tailwind.css에도 `:root { --color-primary: #10b981 }`이 들어간다.

CSS specificity를 비교하면:

| 선택자 | Specificity | 파일 | 로드 순서 |
|--------|------------|------|----------|
| `[data-app-theme="wimbledon"]` | (0,1,0) | tokens.css | 1번째 |
| `:root` | (0,1,0) | tailwind.css | 2번째 |

**`:root`와 `[data-app-theme]`의 specificity가 동일하다.** `:root`는 pseudo-class로 `(0,1,0)`, `[data-app-theme="wimbledon"]`은 attribute selector로 `(0,1,0)`. 같은 specificity에서는 **나중에 선언된 쪽이 이긴다.**

tokens.css가 먼저 로드되고 tailwind.css가 나중에 로드되므로, tailwind.css의 `:root { --color-primary: #10b981 }`이 tokens.css의 `[data-app-theme] { --color-primary: #522398 }`을 덮어쓴 것이다.

그런데 `--color-emerald-600`은 왜 정상 오버라이드됐을까? Tailwind v4는 `:root`에서 emerald 색상을 `oklch()` 형식으로 선언하고, tokens.css에서는 hex(`#6a1a73`)로 선언한다. Tailwind의 `:root` 선언은 `@layer theme` 안에 있어서 일반 CSS보다 우선순위가 낮다. 하지만 `--color-primary`는 tokens.css `:root`에서 가져온 값이 Tailwind의 일반 `:root` 블록에 들어가므로 layer 밖이다.

### 해결: 테마 블록을 tailwind.css 이후에 로드

```erb
<%# 로드 순서: tokens → tailwind → application %>
<%= stylesheet_link_tag "tokens", "tailwind", "application" %>
```

`[data-app-theme]` 블록을 tokens.css에서 **application.css 맨 끝**으로 이동했다. application.css는 tailwind.css 이후에 로드되므로, 동일 specificity에서 application.css가 이긴다.

```css
/* application.css — tailwind.css 이후에 로드됨 */

/* Wimbledon: Purple + Green */
[data-app-theme="wimbledon"] {
  --color-emerald-50: #f5f0ff;
  --color-emerald-600: #6a1a73;
  --color-primary: #522398;
  --color-primary-500: #7B2082;
  --color-primary-600: #6a1a73;
  --shadow-focus: 0 0 0 3px rgba(82, 35, 152, 0.2);
}
```

변경 후 확인:

```javascript
root.getPropertyValue('--color-primary');  // "#522398" ✅ 보라색!
```

모든 변수가 정상 오버라이드된다. 스크린샷으로 확인하면 버튼, 카드 배경, 뱃지, 그라데이션이 전부 보라색 톤으로 전환된다.

### 이 패턴이 위험한 이유

이 문제는 **개발 중에는 발견하기 어렵다.** tokens.css의 `:root`에서 `--color-primary: var(--color-primary-500)`으로 선언하면, 개발 서버에서는 캐시 상태에 따라 되기도 하고 안 되기도 한다. 특히 Propshaft의 에셋 fingerprinting이 이전 빌드를 서빙하면 "아까까지 됐는데?"라는 상황이 된다.

확실한 디버깅 방법:

```javascript
// 브라우저 콘솔에서 변수 값 직접 확인
getComputedStyle(document.documentElement)
  .getPropertyValue('--color-primary');

// 스타일시트 로드 순서 확인
document.styleSheets.forEach((s, i) =>
  console.log(i, s.href?.split('/').pop())
);
```

---

## 삽질 3: Turbo Drive + inline script의 && 파싱 에러

테마 전환과 별개로, 페이지 이동할 때마다 콘솔에 에러가 떴다:

```
SyntaxError: Failed to execute 'appendChild' on 'Node': Unexpected token '&'
    at mt.copyNewHeadScriptElements (turbo.min.js:19:27488)
```

### 원인: Turbo의 head 병합 메커니즘

Turbo Drive는 페이지 전환 시 새 페이지의 `<head>`를 기존 `<head>`와 병합한다. 이 과정에서 `<script>` 태그를 DOM에 복사하는데, inline script 안의 `&&` 연산자가 HTML 엔티티로 파싱되면서 SyntaxError가 발생했다.

문제가 된 코드:

```html
<script>
  var t = (serverTheme && serverTheme !== 'default')
    ? serverTheme : localStorage.getItem('easy-bracket-theme');
  if (t && t !== 'default') { /* ... */ }
</script>
```

`&&`는 JavaScript에서는 정상이지만, Turbo가 innerHTML로 script를 복사할 때 HTML parser가 `&`를 엔티티 시작으로 인식한다.

### 해결: data-turbo-permanent

```html
<script data-turbo-permanent id="theme-restore">
  // Turbo가 이 script를 매 네비게이션마다 복사하지 않음
  var t = (serverTheme && serverTheme !== 'default') ...
</script>
```

`data-turbo-permanent`를 추가하면 Turbo가 이 요소를 최초 로드 후 **재사용**한다. 매번 DOM에서 제거하고 다시 삽입하지 않으므로 파싱 에러가 사라진다. Turbo 공식 문서에서도 `<head>` 안의 script에는 이 속성을 권장한다.

추가로 ERB에서 `<%= server_theme.to_json %>`을 `<%= raw server_theme.to_json %>`으로 바꿔서 Rails의 HTML escape도 방지했다.

---

## Tailwind v4 테마 시스템 설계 가이드

위 삽질을 거쳐 정리한 **올바른 멀티 테마 구현 패턴**이다.

### 1단계: 기본 테마 정의 (tokens.css)

```css
/* tokens.css — 디자인 토큰 정의만 */
:root {
  --color-primary-50: #ecfdf5;
  --color-primary-500: #10b981;
  --color-primary-600: #059669;
  --color-primary-700: #047857;
  --surface-body: #F4F2F7;
  --surface-card: #FFFFFF;
  --text-heading: #1A1523;
  --text-body: #6B6280;
}
```

### 2단계: emerald 클래스 그대로 사용 (views)

```erb
<%# bg-emerald-600은 자동으로 var(--color-emerald-600)을 참조 %>
<button class="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl px-4 py-2">
  시작하기
</button>
```

Tailwind v4가 알아서 CSS 변수로 컴파일한다. arbitrary value 쓸 필요 없다.

### 3단계: 테마 오버라이드 (application.css — tailwind 이후 로드)

```css
/* application.css — 반드시 tailwind.css 이후에 로드 */

[data-app-theme="wimbledon"] {
  --color-emerald-50: #f5f0ff;
  --color-emerald-600: #6a1a73;
  --color-primary: #522398;
  --color-primary-500: #7B2082;
}

[data-app-theme="roland-garros"] {
  --color-emerald-50: #fff4ec;
  --color-emerald-600: #b04a0d;
  --color-primary: #C95917;
  --color-primary-500: #C95917;
}
```

핵심: **`--color-emerald-*`과 `--color-primary-*` 둘 다 오버라이드**해야 한다. emerald은 Tailwind 유틸리티 클래스가 참조하고, primary는 커스텀 CSS 클래스(`theme-button-primary` 등)가 참조한다.

### 4단계: 테마 전환 (JavaScript)

```javascript
function setTheme(theme) {
  if (theme && theme !== 'default') {
    document.documentElement.setAttribute('data-app-theme', theme);
  } else {
    document.documentElement.removeAttribute('data-app-theme');
  }
  localStorage.setItem('easy-bracket-theme', theme);
}
```

### 5단계: 다크 모드와 테마 조합

Tailwind v4에서 다크 모드와 멀티 테마를 함께 사용하려면 별도 선택자가 필요하다:

```css
/* 다크 모드도 application.css에서 오버라이드 */
.dark {
  --surface-body: #020617;
  --surface-card: rgba(255,255,255,0.05);
  --text-heading: #f8fafc;
  --text-body: #94a3b8;
}

/* 다크 모드 + 테마 조합 */
.dark[data-app-theme="wimbledon"] {
  --color-emerald-50: #1a0a2e;
  --color-emerald-600: #9b5de5;
}
```

---

## Rails + Propshaft 환경에서의 주의사항

### CSS 로드 순서 선언

```erb
<%# layout에서 정확한 순서 유지 %>
<%= stylesheet_link_tag "tokens", "tailwind", "application",
    "data-turbo-track": "reload" %>
```

| 순서 | 파일 | 역할 |
|------|------|------|
| 1 | tokens.css | 디자인 토큰 `:root` 정의, 타이포그래피, 스페이싱 |
| 2 | tailwind.css | Tailwind 빌드 출력 (`:root` 변수 포함) |
| 3 | application.css | 커스텀 유틸리티 + **테마 오버라이드** |

### Propshaft 에셋 캐시 문제

Propshaft는 fingerprinted 에셋을 서빙한다. CSS를 수정한 후 변경이 반영 안 되면:

```bash
rm -f public/assets/.manifest.json
RAILS_ENV=development bin/rails assets:precompile
# 서버 재시작
```

manifest를 삭제하면 Propshaft가 새 fingerprint로 에셋을 재생성한다.

### @source 디렉티브 (Tailwind v4)

ERB 파일이 자동 스캔되지 않으면 `@source` 디렉티브를 추가한다:

```css
/* tailwind 진입점 CSS */
@import "tailwindcss";

@source "../views/**/*.{erb,haml,html,slim}";
@source "../components/**/*.html";
@source "../javascript/**/*.{js,jsx,ts,tsx}";
```

---

## 정리: 핵심 교훈 세 가지

### 1. Tailwind v4에서 색상 테마는 CSS 변수 오버라이드로 충분하다

`bg-emerald-600`을 `bg-[color:var(--color-primary-600)]`으로 바꾸지 마라. Tailwind v4가 이미 CSS 변수로 컴파일한다. arbitrary value는 JIT 스캔 실패 위험만 높인다.

### 2. CSS 변수 오버라이드는 로드 순서가 specificity만큼 중요하다

`:root`와 `[data-attr="value"]`는 specificity가 같다 (둘 다 `(0,1,0)`). 동일 specificity에서는 **나중에 로드된 파일이 이긴다.** 테마 오버라이드는 반드시 Tailwind 빌드 이후에 로드되는 CSS에 넣어야 한다.

```
tokens.css → tailwind.css → application.css
                ↑ Tailwind가 :root를 여기에 넣음
                  → 테마 오버라이드는 반드시 이 뒤!
```

### 3. Turbo Drive + inline script는 data-turbo-permanent으로 보호하라

Turbo가 `<head>` script를 DOM에 복사할 때 `&&`, `<`, `>` 같은 문자가 HTML 엔티티로 파싱될 수 있다. `data-turbo-permanent`로 한 번만 로드되게 하면 해결된다.

---

## 최종 변경 diff

```
tokens.css       → [data-app-theme] 블록 제거 (application.css로 이동)
application.css  → 테마 오버라이드 블록 추가 (tailwind 뒤에 로드)
application.html → <script data-turbo-permanent> 추가
```

총 3개 파일. 실질적 코드 변경은 0줄. **코드를 바꾼 게 아니라 CSS 선언 위치만 옮겼다.**

540곳을 바꿨다가 되돌리고, 다시 바꿨다가 또 되돌리고, 결국 파일 3개만 고쳤다. CSS는 단순해 보이지만, 변수 해석 타이밍과 cascade 규칙을 정확히 이해하지 못하면 이렇게 삽질한다.
