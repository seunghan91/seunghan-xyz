---
title: "SPA 배포 후 빈 화면: Inertia.js usePage().url은 string이다"
date: 2026-03-02
draft: false
tags: ["Rails", "Inertia.js", "Svelte", "SPA", "디버깅", "배포", "Playwright"]
description: "Rails + Inertia.js + Svelte 앱 배포 후 빈 화면이 나오는 문제를 Playwright 콘솔 에러 분석으로 해결한 과정. usePage().url이 URL 객체가 아닌 string인 점을 놓쳐서 발생한 런타임 에러였다."
---

Rails + Inertia.js + Svelte 앱을 배포한 뒤 접속하면 **완전히 빈 화면**만 보였다. 서버는 정상이고 에셋도 다 로드되는데 화면이 안 그려지는 상황. 원인 추적부터 해결까지 정리한다.

---

## 증상

- 배포된 URL 접속 시 **빈 화면** (흰색 배경만 표시)
- 로컬 개발 서버에서는 정상 동작
- 아무런 에러 페이지 없이 그냥 빈 화면

---

## 진단 과정

### Step 1: HTTP 응답 확인

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/
# 200
```

HTTP 200 OK. 서버 자체는 정상 응답 중이다.

### Step 2: HTML 구조 확인

```bash
curl -s https://example.com/ | head -30
```

```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="/vite/assets/application-xxx.css" />
  <script type="module" src="/vite/assets/application-xxx.js"></script>
</head>
<body>
  <div id="app" data-page="{...}"></div>
</body>
</html>
```

HTML은 정상이고, Inertia.js의 `data-page` 속성도 정상적으로 들어가 있다.

### Step 3: 에셋 로딩 확인

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.js
# 200

curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.css
# 200
```

JS, CSS 모두 200 OK. 에셋 로딩 문제는 아니다.

### Step 4: 브라우저 콘솔 에러 확인 (결정적 단서)

여기서 **Playwright MCP**를 사용해 실제 브라우저로 접속하고 콘솔 에러를 수집했다.

```
TypeError: Cannot read properties of undefined (reading 'pathname')
    at lt (application-xxx.js:1:5526)
    at jn (application-xxx.js:3:9357)
    at vendor-inertia-xxx.js:82:790
    at vendor-svelte-xxx.js:1:37413
```

**JS 런타임 에러**가 있었다. `pathname`이라는 프로퍼티를 `undefined`에서 읽으려 했다.

---

## 근본 원인

문제는 레이아웃 컴포넌트에서 현재 URL 경로를 체크하는 코드였다:

```svelte
<script lang="ts">
  import { usePage } from '@inertiajs/svelte'

  const page = usePage()

  // 문제의 코드
  const isMyPage = $derived($page.url.pathname.startsWith('/mypage'))
</script>
```

### 핵심: `usePage().url`은 **string**이다

브라우저의 `window.location`이나 `URL` 객체와 달리, Inertia.js의 `usePage()`가 반환하는 `url` 프로퍼티는 **URL 객체가 아닌 순수 문자열**이다.

```typescript
// Inertia.js 내부에서 url은 이런 형태
$page.url // "/mypage"     ← string
$page.url // "/products/1" ← string

// URL 객체처럼 쓸 수 없다
$page.url.pathname  // undefined! string에는 pathname이 없다
$page.url.startsWith('/mypage')  // 이것이 올바른 사용법
```

| 접근 방식 | 타입 | `.pathname` | `.startsWith()` |
|-----------|------|-------------|-----------------|
| `window.location` | Location 객체 | `/mypage` | `/mypage` |
| `new URL(...)` | URL 객체 | `/mypage` | 에러 |
| `$page.url` (Inertia.js) | **string** | **undefined** | `/mypage` |

### 왜 로컬에서는 됐나?

로컬 개발 환경에서는 이 코드가 이미 수정된 상태였고, 배포된 버전은 수정 전 코드가 빌드되어 올라가 있었다. 즉 **로컬과 배포 코드 불일치** 상태.

---

## 해결

```svelte
<script lang="ts">
  const page = usePage()

  // 수정: string으로 직접 비교 + optional chaining
  const isMyPage = $derived(($page as any)?.url?.startsWith('/mypage') ?? false)
</script>
```

변경 포인트:
1. `.pathname` 제거 - `url`이 string이므로 직접 `.startsWith()` 사용
2. **optional chaining** (`?.`) - `$page`나 `url`이 아직 초기화되지 않은 경우 대비
3. **nullish coalescing** (`?? false`) - undefined일 때 기본값 false

---

## 추가 안전 장치

글로벌 데이터를 `inertia_share`로 공유할 때, DB 마이그레이션이 아직 실행되지 않은 환경에서도 에러가 나지 않도록 rescue 처리:

```ruby
# ApplicationController
inertia_share do
  {
    flash: { notice: flash[:notice], alert: flash[:alert] },
    unread_message_count: -> { safe_unread_count }
  }
end

private

def safe_unread_count
  return 0 unless current_user
  current_user.conversations.sum(:unread_count_for_user)
rescue ActiveRecord::StatementInvalid
  0  # 테이블이 아직 없는 경우 (마이그레이션 전)
end
```

---

## 교훈

### 1. SPA 빈 화면 = JS 런타임 에러를 의심하라

SPA에서 빈 화면이 나올 때 가장 흔한 원인:
- HTTP 200이지만 JS에서 에러가 터져 렌더링이 안 됨
- `curl`로는 정상인데 브라우저에서만 문제 → **콘솔 에러 확인 필수**

### 2. 프레임워크 API의 타입을 정확히 알아야 한다

`$page.url`이 string인지 URL 객체인지는 Inertia.js 문서에 나와 있지만, 빠르게 코딩할 때 `window.location`과 혼동하기 쉽다. TypeScript를 쓰더라도 `any` 캐스팅하면 타입 체크가 무력화된다.

### 3. 배포 디버깅 도구 계층

```
1단계: curl -s -w "%{http_code}" (HTTP 상태)
2단계: curl + HTML 분석 (서버 렌더링 확인)
3단계: 에셋 URL curl (JS/CSS 로딩 확인)
4단계: Playwright/브라우저 DevTools (JS 런타임 에러)
```

특히 4단계에서 **Playwright를 사용한 자동 콘솔 에러 수집**이 결정적이었다. 수동으로 브라우저 열지 않고도 배포 사이트의 런타임 에러를 프로그래밍으로 감지할 수 있다.

### 4. 로컬 ≠ 배포 환경

코드를 수정해도 **커밋 + 배포**하지 않으면 프로덕션에는 반영되지 않는다. 당연한 이야기지만, 로컬에서 잘 되는 것만 확인하고 "됐다"고 넘어가면 배포 환경에서 구버전 코드가 동작하고 있을 수 있다.

---

## TL;DR

| 항목 | 내용 |
|------|------|
| **증상** | SPA 배포 후 빈 화면 |
| **오해** | 서버 문제? 에셋 로딩 실패? |
| **실제 원인** | Inertia.js `usePage().url`이 string인데 `.pathname` 접근 |
| **해결** | `.startsWith()` 직접 사용 + optional chaining |
| **핵심 도구** | Playwright 콘솔 에러 자동 수집 |
