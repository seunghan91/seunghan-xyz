---
title: "Hotwire Native WebView 삽질 모음 — 네이티브 앱에 Rails WebView 래핑할 때 자주 겪는 8가지 문제"
date: 2025-11-25
draft: false
tags: ["Rails", "Hotwire", "Turbo Native", "iOS", "Android", "WebView", "WKWebView"]
description: "Rails + Hotwire Native로 iOS/Android 앱을 만들 때 WebView에서 터지는 대표 8가지 UX 버그와 CSS·path configuration으로 해결한 방법을 정리했다."
cover:
  image: "/images/og/hotwire-native-webview-8-fixes.png"
  alt: "Hotwire Native Webview 8 Fixes"
  hidden: true
---

Rails 앱을 Hotwire Native(Turbo Native)로 래핑해서 iOS/Android 네이티브 앱을 만들다 보면,
브라우저에서는 멀쩡한데 WebView에서만 이상하게 동작하는 것들이 꽤 많다.
실제로 작업하면서 겪은 문제와 적용한 수정을 한 곳에 정리해 둔다.

대부분 CSS 몇 줄 또는 path configuration JSON 한 줄로 끝난다.

---

## 1. 더블탭 줌 / 300ms 클릭 딜레이

### 증상

버튼을 빠르게 두 번 탭하면 화면이 확대된다. 단순 탭에도 눌렸다는 느낌이 살짝 늦다 (약 300ms).

### 원인

iOS WKWebView는 더블탭 줌 제스처를 감지하기 위해 첫 번째 탭 이벤트를 ~300ms 동안 잡아둔다.
`user-scalable=yes`(viewport 기본값) 상태에서는 핀치 줌과 더블탭 줌이 활성화되어 있다.

### 수정

```html
<!-- layout HTML의 viewport 메타 태그 -->
<meta name="viewport"
  content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
```

```css
html, body {
  touch-action: manipulation; /* 더블탭 줌 제스처 비활성화 → 탭 즉각 반응 */
}
```

`touch-action: manipulation`은 스크롤과 핀치 줌은 허용하고, 더블탭 줌만 비활성화한다.
`user-scalable=no`와 함께 쓰면 확실히 막힌다.

---

## 2. iOS 탄성 스크롤 (Rubber-band) / Pull-to-Refresh 충돌

### 증상

페이지 최상단에서 위로 당기면 화면이 통째로 튀어오르거나,
의도치 않게 Hotwire Native의 당겨서 새로고침이 트리거된다.

### 원인

iOS의 기본 탄성 스크롤(rubber-band) 동작이 WebView 바깥 레이어까지 전파된다.
Hotwire Native가 WebView 위에 Pull-to-Refresh 제스처 인식을 붙여놨는데 두 레이어가 충돌한다.

### 수정

```css
html, body {
  overscroll-behavior-y: contain; /* 스크롤 체인을 WebView 내부에서 차단 */
}
```

`contain`은 현재 스크롤 컨테이너 내에서만 스크롤을 소비하고 바깥으로 전파하지 않는다.
모달 페이지처럼 Pull-to-Refresh 자체가 필요 없는 경우는 path configuration에서 아예 끈다 (7번 참고).

---

## 3. 탭 하이라이트 오버레이

### 증상

링크나 버튼을 탭하면 파란 반투명 사각형 오버레이가 번쩍인다.
브라우저에서는 자연스럽지만 네이티브 앱 안에서는 어색하다.

### 원인

WebKit이 포커스 가능한 요소에 기본 탭 피드백을 그린다.
색상은 브라우저마다 다르지만 iOS Safari / WKWebView에서는 파란색이 기본이다.

### 수정

```css
* {
  -webkit-tap-highlight-color: transparent;
}
```

전체에 투명을 주되, 실제 탭 피드백이 필요한 요소에는 `:active` 스타일로 별도 표현하면 된다.

---

## 4. 드래그 스크롤 중 텍스트 선택

### 증상

스크롤하다 손가락을 오래 누르면 텍스트가 선택되고 iOS 확대경(magnifier)이 떠오른다.

### 원인

WebView는 기본적으로 텍스트 선택이 허용된다.
손가락으로 드래그하면서 스크롤할 때 브라우저가 이를 텍스트 드래그 선택으로 인식하기도 한다.

### 수정

```css
/* 전체: 선택 방지 */
body {
  -webkit-user-select: none;
  user-select: none;
}

/* 입력 필드만 선택 허용 재활성화 */
input,
textarea,
[contenteditable] {
  -webkit-user-select: auto;
  user-select: auto;
}
```

입력 필드까지 막으면 텍스트 복사·붙여넣기가 불가능해지므로 명시적으로 풀어줘야 한다.

---

## 5. Android 가로 회전 시 폰트 자동 확대

### 증상

기기를 가로로 돌리면 폰트가 갑자기 커진다. 레이아웃이 틀어진다.

### 원인

Android WebView(`WebSettings`)는 가독성을 위해 가로 모드에서 `textZoom`을 자동으로 올린다.
CSS로도 동일한 현상이 발생한다.

### 수정 (CSS)

```css
html, body {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
```

네이티브 Android 쪽에서 `WebView.settings.textZoom = 100`을 직접 설정하는 방법이 근본 해결이지만,
CSS로도 대부분 막힌다.

---

## 6. 수평 스크롤과 iOS 뒤로가기 제스처 충돌

### 증상

카테고리 탭, 가로 슬라이더 같은 수평 스크롤 영역을 좌우로 스와이프하면
iOS의 Edge Swipe(뒤로가기) 제스처가 같이 발동해서 페이지가 전환된다.

### 원인

WebView의 수평 스크롤 이벤트가 WKWebView 바깥(네이티브 네비게이션 레이어)까지 버블링된다.

### 수정

```css
/* 수평 스크롤이 있는 컨테이너에 적용 */
.overflow-x-auto,
[data-scroll-horizontal] {
  overscroll-behavior-x: contain;
}
```

Hotwire Native 전용으로만 적용하고 싶다면 `body.turbo-native` 하위로 스코프를 좁힌다.

```css
.turbo-native .overflow-x-auto {
  overscroll-behavior-x: contain;
}
```

---

## 7. 모달에서 Pull-to-Refresh 충돌

### 증상

iOS 모달 시트를 위에서 아래로 스와이프하면 모달 닫기 제스처와 당겨서 새로고침이 동시에 발동된다.

### 원인

Hotwire Native는 WebView에 Pull-to-Refresh를 전역으로 붙인다.
iOS 시트 dismiss(아래로 스와이프)와 제스처 방향이 겹친다.

### 수정 (path configuration)

```json
{
  "rules": [
    {
      "patterns": ["/sign_in", "/sign_up", "/verify"],
      "properties": {
        "context": "modal",
        "presentation": "push",
        "pull_to_refresh_enabled": false
      }
    },
    {
      "patterns": ["/settings", "/profile/edit"],
      "properties": {
        "context": "modal",
        "presentation": "push",
        "pull_to_refresh_enabled": false
      }
    }
  ]
}
```

`context: modal`인 모든 라우트에 `pull_to_refresh_enabled: false`를 명시하는 게 안전하다.
빠뜨리면 언제 터질지 모른다.

---

## 8. Safe Area (노치 / 다이나믹 아일랜드 / 홈 인디케이터)

### 증상

iPhone 노치 또는 다이나믹 아일랜드 뒤로 상단 콘텐츠가 가려진다.
홈 인디케이터 위에 하단 버튼이 겹친다.

### 원인

`viewport-fit=cover` 없이는 `env(safe-area-inset-*)` 변수 자체가 0으로 계산된다.

### 수정

```html
<!-- viewport-fit=cover 필수 -->
<meta name="viewport"
  content="width=device-width,initial-scale=1,viewport-fit=cover">
```

```css
/* Hotwire Native 앱 내 메인 콘텐츠 영역 */
.turbo-native main {
  padding-top: max(1rem, env(safe-area-inset-top));
  padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));
}
```

`max()` 함수를 쓰면 safe-area-inset이 0인 기기(홈버튼 있는 기기)에서도 최소 패딩을 보장한다.

---

## 한눈에 보기

| # | 문제 | 수정 방법 | 파일 |
|---|------|----------|------|
| 1 | 더블탭 줌 / 300ms 딜레이 | `user-scalable=no` + `touch-action: manipulation` | layout HTML + CSS |
| 2 | 탄성 스크롤 / PTR 충돌 | `overscroll-behavior-y: contain` | CSS |
| 3 | 탭 하이라이트 | `-webkit-tap-highlight-color: transparent` | CSS |
| 4 | 드래그 텍스트 선택 | `user-select: none` (입력 필드 제외) | CSS |
| 5 | Android 폰트 자동 확대 | `-webkit-text-size-adjust: 100%` | CSS |
| 6 | 수평 스크롤 ↔ 뒤로가기 충돌 | `overscroll-behavior-x: contain` | CSS |
| 7 | 모달 PTR 충돌 | `pull_to_refresh_enabled: false` | path configuration |
| 8 | Safe Area | `viewport-fit=cover` + `env(safe-area-inset-*)` | layout HTML + CSS |

---

## 전체 CSS 한 블록

위 내용을 한 파일에 모아두면 편하다.

```css
/* ── Hotwire Native WebView UX Fixes ─────────────────────── */

/* 1. 300ms 딜레이 제거 + 2. 탄성 스크롤 방지 + 5. Android 폰트 자동 확대 */
html, body {
  touch-action: manipulation;
  overscroll-behavior-y: contain;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

/* 3. 탭 하이라이트 제거 */
* {
  -webkit-tap-highlight-color: transparent;
}

/* 4. 텍스트 선택 방지 */
body {
  -webkit-user-select: none;
  user-select: none;
}

input, textarea, [contenteditable] {
  -webkit-user-select: auto;
  user-select: auto;
}

/* 6. 수평 스크롤 영역 격리 */
.turbo-native .overflow-x-auto {
  overscroll-behavior-x: contain;
}

/* 8. Safe Area */
.turbo-native main {
  padding-top: max(1rem, env(safe-area-inset-top));
  padding-bottom: calc(1.5rem + env(safe-area-inset-bottom));
}
```

이 정도만 챙겨도 Hotwire Native WebView의 체감 품질이 꽤 올라간다.
