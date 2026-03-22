---
title: "iOS WebView 채팅 메시지가 박스를 뚫고 나간다 — overflow-wrap: anywhere로 해결한 크로스프로젝트 수정기"
date: 2026-03-22
draft: false
tags: ["iOS", "CSS", "Rails", "Hotwire Native", "WebView"]
description: "Rails 8 Hotwire Native 앱에서 채팅 메시지가 컨테이너를 넘치는 버그를 overflow-wrap: anywhere로 수정한 과정. Tailwind break-words가 flexbox에서 작동하지 않는 이유와 iOS WKWebView 대응 best practice."
---

## 증상: 긴 메시지가 채팅 버블을 뚫고 나간다

Rails 8 + Hotwire Native로 만든 iOS 앱에서 채팅 기능을 테스트하던 중 문제를 발견했다. 긴 URL이나 공백 없는 연속 문자열을 보내면 메시지가 채팅 버블 영역을 벗어나 화면 밖으로 튀어나가는 현상이 발생했다.

웹 브라우저에서는 멀쩡하게 보이는데, iOS 네이티브 앱(WKWebView)에서만 문제가 재현됐다. 가로 스크롤이 생기고, 메시지 영역 전체 레이아웃이 깨져버린다.

처음엔 "Tailwind `break-words` 넣어놨는데 왜 안 되지?" 싶었지만, 파고 들어가보니 CSS `overflow-wrap`, flexbox intrinsic sizing, iOS WebKit 호환성이 복합적으로 얽힌 문제였다.

---

## 문제의 코드: Tailwind break-words는 왜 안 먹힐까

채팅 메시지 파셜은 이런 구조였다:

```erb
<%# app/views/chat_messages/_chat_message.html.erb %>
<div class="group flex gap-2.5 py-1.5">
  <div class="w-8 h-8 rounded-full shrink-0">...</div>
  <div class="flex-1 min-w-0">
    <p class="text-sm whitespace-pre-wrap break-words mt-0.5">
      <%= chat_message.body %>
    </p>
  </div>
</div>
```

`break-words` 클래스를 적용했고, 부모에 `min-w-0`도 넣었다. 그런데 iOS에서만 텍스트가 넘친다.

Tailwind의 `break-words` 클래스가 실제로 적용하는 CSS를 확인해보면:

```css
/* Tailwind break-words */
overflow-wrap: break-word;
```

이게 바로 문제의 핵심이다. `overflow-wrap: break-word`와 `overflow-wrap: anywhere`는 같아 보이지만 결정적인 차이가 있다.

---

## overflow-wrap: break-word vs anywhere — 결정적 차이

MDN 스펙을 보면 두 값의 정의가 거의 동일하다. 둘 다 "단어가 컨테이너를 넘치면 임의의 지점에서 줄바꿈을 허용"한다. 하지만 한 문장이 다르다:

| 속성 | 줄바꿈 동작 | min-content 계산 |
|------|-----------|-----------------|
| `break-word` | 넘치면 줄바꿈 | 줄바꿈을 **고려하지 않음** |
| `anywhere` | 넘치면 줄바꿈 | 줄바꿈을 **고려함** |

> `anywhere`: Soft wrap opportunities introduced by the word break **are considered** when calculating min-content intrinsic sizes.
>
> `break-word`: Soft wrap opportunities introduced by the word break are **NOT considered** when calculating min-content intrinsic sizes.

이게 무슨 뜻인가? Flexbox 컨테이너 안에서 자식 요소의 최소 너비(`min-content`)를 계산할 때:

- **`break-word`**: "이 텍스트는 줄바꿈 없이 한 줄로 놓으면 이 정도 너비야" → 컨테이너보다 넓어짐 → **넘침**
- **`anywhere`**: "줄바꿈이 가능하니까 최소 너비는 더 작아질 수 있어" → 컨테이너에 맞춤 → **정상**

채팅 UI는 대부분 flexbox 레이아웃이다. 프로필 이미지 옆에 메시지 영역을 `flex-1`로 배치하는 구조에서, `break-word`만으로는 flex item의 intrinsic minimum size 문제를 해결할 수 없다.

---

## 왜 iOS WebView에서만 문제가 심한가

데스크톱 Chrome에서는 `break-word`로도 대부분 정상적으로 보인다. iOS WKWebView에서 유독 문제가 심한 이유가 있다.

### 1. iOS Safari의 `overflow-wrap: anywhere` 지원 역사

`overflow-wrap: anywhere`는 비교적 최근에 브라우저 지원이 완성됐다:

- Chrome 80+ (2020년 2월)
- Firefox 63+ (2018년 10월)
- **iOS Safari 15.4+** (2022년 3월)

iOS 15.4 이전 버전에서는 `anywhere` 값 자체가 무시되어 `normal`과 동일하게 동작했다. 2026년 현재 대부분의 기기가 업데이트됐지만, 방어적으로 fallback을 함께 쓰는 것이 좋다.

### 2. WKWebView의 레이아웃 엔진 차이

WKWebView는 일반 Safari와 동일한 WebKit 엔진을 사용하지만, 앱 내 WebView 환경에서는 viewport 계산, safe area, 스크롤 동작 등이 미묘하게 다르다. 특히:

- **viewport width가 고정**: 네이티브 앱의 WebView는 화면 너비가 정확히 디바이스 너비로 고정되어, 데스크톱처럼 넓은 공간에서 자연스럽게 줄바꿈될 여유가 없다.
- **가로 스크롤 허용**: 일반적으로 WKWebView는 콘텐츠가 넘치면 가로 스크롤을 허용하는데, 이게 채팅 UI에서는 치명적이다.

### 3. Flexbox + 좁은 화면 조합

모바일 화면에서 채팅 UI를 그리면:

```
[프로필 32px] [flex-1 메시지 영역 ≈ 330px]
```

메시지 영역이 약 330px밖에 안 되는데, 여기에 긴 URL(`https://example.com/very/long/path/that/keeps/going/and/going`)이 들어오면 `break-word`로는 min-content 계산이 제대로 안 되어 해당 flex item이 부모를 넘어가는 것이다.

---

## 해결: 3가지 방어선

### 방어선 1: overflow-wrap: anywhere (핵심)

메시지 본문 요소에 `overflow-wrap: anywhere`를 직접 적용한다:

```erb
<%# overflow-wrap: anywhere — 긴 URL/연속문자가 iOS WebView에서 버블 밖으로 넘치는 것 방지 (break-words만으로 불충분) %>
<p class="text-sm whitespace-pre-wrap break-words mt-0.5"
   style="overflow-wrap: anywhere; word-break: break-word;">
  <%= chat_message.body %>
</p>
```

왜 inline style을 쓰는가? Tailwind 3에서는 `overflow-wrap: anywhere`에 대응하는 유틸리티 클래스가 없었다. Tailwind 4에서 `wrap-anywhere`가 추가됐지만, 프로젝트마다 Tailwind 버전이 다를 수 있으므로 inline style이 가장 확실하다.

`word-break: break-word`도 함께 넣는 이유는 구형 WebView에서의 fallback이다. `word-break: break-word`는 deprecated됐지만 여전히 대부분의 브라우저에서 동작한다.

### 방어선 2: overflow-x-hidden (컨테이너)

메시지 목록 스크롤 컨테이너에서 가로 스크롤을 차단한다:

```erb
<%# overflow-x-hidden: 긴 메시지가 가로 스크롤을 유발하는 것 차단 %>
<div class="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-1">
  <% @chat_messages.each do |msg| %>
    <%= render partial: "chat_messages/chat_message", locals: { chat_message: msg } %>
  <% end %>
</div>
```

`overflow-x-hidden`은 "혹시라도" 넘치는 콘텐츠가 가로 스크롤을 만드는 것을 완전히 차단하는 안전장치다.

### 방어선 3: 첨부파일명 truncate

채팅에서 파일을 첨부할 때, 파일명이 길면 역시 넘칠 수 있다:

```erb
<span class="truncate max-w-[200px]"><%= file.filename %></span>
```

Tailwind의 `truncate`는 `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`을 한 번에 적용한다. 파일명은 전체를 보여줄 필요가 없으므로 말줄임이 적합하다.

---

## Tailwind 4의 wrap-anywhere 유틸리티

Tailwind 4에서는 이 문제를 인지하고 공식 유틸리티를 추가했다:

```css
/* Tailwind 4 */
.wrap-break-word { overflow-wrap: break-word; }
.wrap-anywhere   { overflow-wrap: anywhere; }
.wrap-normal     { overflow-wrap: normal; }
```

Tailwind 4를 쓰고 있다면 `wrap-anywhere` 클래스를 바로 사용할 수 있다:

```html
<p class="whitespace-pre-wrap wrap-anywhere">긴 메시지...</p>
```

하지만 Tailwind 3 이하를 쓰는 프로젝트에서는 직접 CSS를 추가해야 한다:

```css
/* app/assets/stylesheets/custom.css */
.wrap-anywhere {
  overflow-wrap: anywhere;
}
```

또는 `@supports`를 사용한 progressive enhancement:

```css
@supports (overflow-wrap: anywhere) {
  .wrap-anywhere {
    overflow-wrap: anywhere;
  }
}
@supports not (overflow-wrap: anywhere) {
  .wrap-anywhere {
    word-break: break-word;
  }
}
```

---

## Flexbox에서 텍스트 오버플로우가 발생하는 근본 원인

이 문제를 더 깊이 이해하려면 flexbox의 `min-width: auto` 기본값을 알아야 한다.

CSS 스펙에 따르면, flex item의 기본 `min-width`는 `0`이 아니라 **`auto`**다. `auto`는 콘텐츠의 `min-content` 크기와 같다. 즉, flex item은 기본적으로 콘텐츠의 최소 크기보다 작아지지 않는다.

```
Flex container (width: 400px)
├── Profile image (width: 32px, flex-shrink: 0)
└── Message area (flex: 1, min-width: auto ← 문제!)
    └── "https://very-long-url-that-keeps-going-forever..."
        min-content width = URL 전체 길이 = 800px
```

이 상황에서:

1. 메시지 영역의 `min-width: auto`는 URL의 `min-content` (800px)이 됨
2. Flex item은 800px보다 줄어들 수 없음
3. 컨테이너(400px)를 넘침

**해결 조합**:

```
min-w-0 + overflow-wrap: anywhere
```

- `min-w-0`은 flex item이 콘텐츠 크기와 관계없이 줄어들 수 있게 한다
- `overflow-wrap: anywhere`는 줄어든 너비에서 텍스트가 줄바꿈되게 한다

이 두 개를 함께 써야 완벽하다. `min-w-0` 없이 `anywhere`만 쓰면 일부 케이스에서 여전히 넘칠 수 있고, `min-w-0`만 쓰고 `break-word`만 있으면 `min-content` 계산 차이 때문에 넘칠 수 있다.

---

## 크로스프로젝트 점검: 같은 패턴이 여기저기 있었다

한 프로젝트에서 문제를 발견한 후, 같은 기술 스택(Rails + Hotwire Native)으로 만든 다른 앱들도 점검했다.

| 프로젝트 | 채팅 구현 방식 | 문제 유무 | 수정 내용 |
|----------|-------------|---------|-----------|
| 프로젝트 A (ERB) | ERB partial + Turbo Stream | O | `overflow-wrap: anywhere` + `overflow-x-hidden` |
| 프로젝트 B (ERB) | ERB + AI 채팅 | O | `break-words` 추가 + `overflow-wrap: anywhere` + `overflow-x-hidden` |
| 프로젝트 C (Svelte) | Inertia.js + Svelte | O | `overflow-wrap: anywhere` + `overflow-x-hidden` |
| 프로젝트 D (ERB) | Hotwire Native 전용 | 채팅 UI 없음 | 수정 불필요 |

공통 패턴: **모든 채팅 UI에서 `whitespace-pre-wrap`은 있지만 `overflow-wrap: anywhere`는 빠져있었다.**

`whitespace-pre-wrap`은 줄바꿈 문자(`\n`)를 보존하면서 자동 줄바꿈도 허용하는데, 이것만으로는 공백 없는 긴 문자열의 줄바꿈을 강제하지 않는다. 반드시 `overflow-wrap`과 함께 사용해야 한다.

---

## Hotwire Native iOS 앱에서의 CSS best practice 체크리스트

채팅 UI뿐 아니라, Hotwire Native 앱 전반에 적용할 수 있는 텍스트 오버플로우 방어 패턴을 정리한다.

### 1. 메시지/댓글 등 사용자 입력 텍스트

```css
/* 사용자가 입력한 텍스트가 표시되는 모든 요소 */
.user-content {
  white-space: pre-wrap;      /* 줄바꿈 보존 + 자동 줄바꿈 */
  overflow-wrap: anywhere;    /* 긴 단어/URL 강제 줄바꿈 */
  word-break: break-word;     /* 구형 WebView fallback */
}
```

### 2. Flexbox 레이아웃 안의 텍스트

```css
/* flex 컨테이너의 텍스트 자식 요소 */
.flex-text-child {
  min-width: 0;               /* flex item이 콘텐츠보다 작아질 수 있게 */
  overflow-wrap: anywhere;    /* min-content 계산에 줄바꿈 반영 */
}
```

### 3. 스크롤 컨테이너

```css
/* 세로 스크롤 영역에서 가로 넘침 차단 */
.scroll-container {
  overflow-y: auto;
  overflow-x: hidden;         /* 가로 스크롤 완전 차단 */
}
```

### 4. 파일명, 이메일 등 긴 단일 라인 텍스트

```css
/* 한 줄로 표시하되 넘치면 말줄임 */
.single-line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;           /* 또는 부모 너비에 맞게 */
}
```

### 5. native.css에 전역 방어 추가

Hotwire Native 앱 전용 CSS에 아예 전역 규칙을 넣어두는 방법도 있다:

```css
/* native.css — iOS WebView 전용 */
body.native-app p,
body.native-app span,
body.native-app div {
  overflow-wrap: anywhere;
  word-break: break-word;
}
```

다만 이건 너무 광범위할 수 있어서, 실제로는 사용자 입력 텍스트가 표시되는 영역에만 선택적으로 적용하는 것을 권장한다.

---

## 디버깅 팁: iOS Simulator + Safari Web Inspector

이런 CSS 레이아웃 문제를 디버깅할 때 유용한 도구 조합이 있다.

### Safari Web Inspector로 WKWebView 디버깅

1. Mac의 Safari > Settings > Advanced > "Show features for web developers" 체크
2. iOS Simulator에서 앱 실행
3. Safari > Develop > Simulator > 해당 WebView 선택
4. Elements 탭에서 해당 요소의 Computed Style 확인

여기서 `overflow-wrap`의 computed value를 확인하면, `anywhere`가 실제로 적용되고 있는지 바로 알 수 있다. Safari의 일부 버전에서는 `overflow-wrap: anywhere`를 인식하면서도 computed value에 `break-word`로 표시하는 경우도 있었으니 주의.

### Box Model로 넘침 확인

Elements 탭에서 넘치는 요소를 선택하고 Box Model을 보면, 해당 요소의 실제 렌더링 너비가 부모보다 큰지 바로 확인할 수 있다. `min-width: auto` 문제라면 요소의 너비가 비정상적으로 크게 잡혀있는 것을 볼 수 있다.

---

## 알려진 함정들

### 1. white-space: nowrap과 충돌

`white-space: nowrap`이 설정된 요소에서는 `overflow-wrap`이 아무 효과가 없다. `nowrap`이 줄바꿈 자체를 금지하기 때문이다. `whitespace-pre-wrap`이나 `whitespace-normal`과 함께 사용해야 한다.

### 2. table 안에서 작동하지 않음

`<table>` 안의 `<td>` 등에서는 `overflow-wrap: anywhere`만으로 줄바꿈이 안 될 수 있다. 테이블에서는 `table-layout: fixed`와 테이블 너비를 명시해야 한다:

```css
table {
  table-layout: fixed;
  width: 100%;
}
td {
  overflow-wrap: anywhere;
}
```

### 3. contenteditable 요소

`contenteditable="true"` 요소에서는 `overflow-wrap` 동작이 일반 텍스트 요소와 다를 수 있다. 입력 중 커서 위치 계산과 충돌할 수 있으므로, 입력 필드가 아닌 **출력 요소에만** 적용하는 것이 안전하다.

### 4. CSS-in-JS 프레임워크에서의 우선순위

Svelte나 React에서 scoped style을 쓰는 경우, inline style의 specificity가 더 높으므로 `style="overflow-wrap: anywhere"` 방식이 확실하다. 클래스 기반으로 하려면 해당 프레임워크의 스타일 우선순위를 확인해야 한다.

---

## 결론

"채팅 메시지가 박스를 넘친다"는 단순해 보이는 버그 뒤에는 CSS 스펙의 미묘한 차이, flexbox의 기본 동작, iOS WebKit의 호환성 이슈가 겹쳐있었다.

핵심 정리:

1. **Tailwind `break-words`(`overflow-wrap: break-word`)만으로는 부족하다** — flexbox 안에서 `min-content` 계산에 줄바꿈이 반영되지 않아 넘칠 수 있다.
2. **`overflow-wrap: anywhere`가 정답이다** — iOS Safari 15.4+ 에서 지원, `word-break: break-word`를 fallback으로 함께 사용한다.
3. **`min-w-0` + `overflow-wrap: anywhere` + `overflow-x-hidden`이 완벽한 3중 방어선이다.**
4. 한 프로젝트에서 발견한 문제는 같은 스택의 다른 프로젝트에도 있을 확률이 높다 — 크로스프로젝트 점검 습관을 들이자.

CSS 한 줄이 레이아웃을 살리기도 하고, 깨뜨리기도 한다.
