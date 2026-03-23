---
title: "SPA 배포 후 빈 화면: Inertia.js usePage().url은 string이다"
date: 2025-11-22
draft: false
tags: ["Rails", "Inertia.js", "Svelte", "SPA", "디버깅", "배포", "Playwright"]
description: "Rails + Inertia.js + Svelte 앱 배포 후 빈 화면이 나오는 문제를 Playwright 콘솔 에러 분석으로 해결한 과정. usePage().url이 URL 객체가 아닌 string인 점을 놓쳐서 발생한 런타임 에러였다."
cover:
  image: "/images/og/spa-blank-screen-inertia-usepage-url-debugging.png"
  alt: "Spa Blank Screen Inertia Usepage Url Debugging"
  hidden: true
---

Rails + Inertia.js + Svelte 앱을 배포한 뒤 접속하면 **완전히 빈 화면**만 보였다. 서버는 정상이고 에셋도 다 로드되는데 화면이 안 그려지는 상황. 원인 추적부터 해결까지, 그리고 재발 방지를 위한 패턴까지 정리한다.

---

## 증상

- 배포된 URL 접속 시 **빈 화면** (흰색 배경만 표시)
- 로컬 개발 서버에서는 정상 동작
- 아무런 에러 페이지 없이 그냥 빈 화면
- 서버 로그에도 이상한 점 없음 (200 응답, 정상적인 요청 처리)

이 상황이 특히 짜증스러운 이유는, 서버 입장에서는 완전히 정상 동작하고 있기 때문이다. HTTP 상태 코드도 200, 에러 로그도 없다. 문제는 브라우저 안에서만 발생한다.

---

## 진단 과정

SPA 디버깅의 핵심은 **레이어별 순서 있는 접근**이다. 한 번에 전체를 보려 하면 오히려 시간이 걸린다.

### Step 1: HTTP 응답 확인

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/
# 200
```

HTTP 200 OK. 서버 자체는 정상 응답 중이다. 즉 DNS, 인프라, SSL 문제가 아니다.

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

HTML은 정상이고, Inertia.js의 `data-page` 속성도 정상적으로 들어가 있다. Rails 서버 쪽 렌더링은 문제없다. `data-page` JSON 내용도 확인해 보면 페이지 컴포넌트 이름, props 등이 올바르게 직렬화되어 있었다.

### Step 3: 에셋 로딩 확인

```bash
curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.js
# 200

curl -s -o /dev/null -w "%{http_code}" https://example.com/vite/assets/application-xxx.css
# 200
```

JS, CSS 모두 200 OK. 에셋 로딩 문제는 아니다. Vite 빌드 결과물이 올바르게 서빙되고 있다.

### Step 4: 브라우저 콘솔 에러 확인 (결정적 단서)

여기서 **Playwright MCP**를 사용해 실제 브라우저로 접속하고 콘솔 에러를 수집했다. `curl`로는 절대 볼 수 없는 정보다.

```
TypeError: Cannot read properties of undefined (reading 'pathname')
    at lt (application-xxx.js:1:5526)
    at jn (application-xxx.js:3:9357)
    at vendor-inertia-xxx.js:82:790
    at vendor-svelte-xxx.js:1:37413
```

**JS 런타임 에러**가 있었다. `pathname`이라는 프로퍼티를 `undefined`에서 읽으려 했다. 스택 트레이스가 minify된 번들을 가리키고 있어서 직접적인 소스 위치는 알 수 없지만, `pathname`이라는 단어가 핵심 단서다.

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

왜 이런 혼동이 생기냐면, 웹 개발을 하다 보면 URL을 다루는 방식이 여러 가지이기 때문이다:

| 접근 방식 | 타입 | `.pathname` | `.startsWith()` |
|-----------|------|-------------|-----------------|
| `window.location` | Location 객체 | `/mypage` | 없음 |
| `new URL(...)` | URL 객체 | `/mypage` | 없음 |
| `$page.url` (Inertia.js) | **string** | **undefined** | `/mypage` |

`window.location.pathname`이나 `new URL(href).pathname` 패턴을 자주 쓰다 보면, `$page.url`도 당연히 객체일 거라고 착각하게 된다. 특히 TypeScript를 사용하더라도 `$page`를 `any`로 캐스팅한 상태라면 이런 실수가 컴파일 타임에 잡히지 않는다.

### Inertia.js의 내부 동작

Inertia.js가 페이지를 초기화할 때, Rails 서버가 응답하는 `data-page` JSON에는 `url` 필드가 문자열로 포함된다:

```json
{
  "component": "Home/Index",
  "props": { ... },
  "url": "/",
  "version": "abc123"
}
```

이 JSON을 그대로 파싱해서 페이지 상태로 사용하기 때문에, `url`은 처음부터 string 타입이다. SPA 네비게이션을 할 때도 Inertia는 새 URL 문자열을 그대로 `page.url`에 넣는다. URL 파싱 객체를 만들지 않는다.

### 왜 로컬에서는 됐나?

로컬 개발 환경에서는 이 코드가 이미 수정된 상태였고, 배포된 버전은 수정 전 코드가 빌드되어 올라가 있었다. 즉 **로컬과 배포 코드 불일치** 상태.

이것이 가장 흔한 함정 중 하나다. 로컬에서 고쳤는데 커밋을 안 했거나, 커밋했는데 배포를 안 한 경우. 또는 브랜치를 잘못 배포한 경우도 있다.

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

### 더 타입 안전한 방법

TypeScript 타입을 제대로 활용하려면 `any` 캐스팅을 피하고 Inertia.js의 타입 정의를 활용하는 것이 좋다:

```typescript
import { usePage } from '@inertiajs/svelte'
import type { Page } from '@inertiajs/core'

interface AppPageProps {
  flash: { notice?: string; alert?: string }
  unread_message_count: number
}

const page = usePage<AppPageProps>()

// page.url은 string 타입으로 올바르게 추론됨
const isMyPage = $derived($page.url?.startsWith('/mypage') ?? false)
```

이렇게 하면 `$page.url`이 `string`으로 타입 추론되어, `.pathname`을 잘못 접근하려 하면 컴파일 에러로 잡을 수 있다.

---

## 추가 안전 장치

글로벌 데이터를 `inertia_share`로 공유할 때, DB 마이그레이션이 아직 실행되지 않은 환경에서도 에러가 나지 않도록 rescue 처리를 추가해두는 것이 좋다. 특히 새 서버에 최초 배포할 때 마이그레이션 전에 앱이 먼저 뜨는 경우가 있다.

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

이 패턴이 필요한 이유: Render.com 같은 PaaS에서는 배포 시 마이그레이션 커맨드(`bundle exec rails db:migrate`)를 실행하고 나서 앱이 재시작되는데, 그 짧은 시간 동안 구버전 앱이 새 테이블을 조회하려다 `ActiveRecord::StatementInvalid`가 발생할 수 있다. `inertia_share`는 모든 요청에서 실행되므로 여기서 에러가 나면 빈 화면이 된다.

---

## Playwright로 배포 사이트 자동 진단하기

이번 디버깅에서 가장 결정적인 도구는 Playwright였다. 배포 사이트의 JS 런타임 에러를 자동으로 수집할 수 있다.

```javascript
// playwright-console-check.js
const { chromium } = require('playwright')

async function checkConsoleErrors(url) {
  const browser = await chromium.launch()
  const page = await browser.newPage()

  const errors = []
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })
  page.on('pageerror', err => {
    errors.push(`Page error: ${err.message}`)
  })

  await page.goto(url, { waitUntil: 'networkidle' })

  await browser.close()

  if (errors.length > 0) {
    console.log('Console errors found:')
    errors.forEach(e => console.log(' -', e))
    process.exit(1)
  } else {
    console.log('No console errors found.')
  }
}

checkConsoleErrors('https://example.com')
```

이 스크립트를 CI/CD 파이프라인에 포함시키면, 배포 후 자동으로 런타임 에러 여부를 체크할 수 있다. GitHub Actions에서는 `playwright/action`을 사용해 headless 브라우저를 실행할 수 있다.

---

## 핵심 정리

### 1. SPA 빈 화면 = JS 런타임 에러를 의심하라

SPA에서 빈 화면이 나올 때 가장 흔한 원인:
- HTTP 200이지만 JS에서 에러가 터져 렌더링이 안 됨
- `curl`로는 정상인데 브라우저에서만 문제가 발생 → **콘솔 에러 확인 필수**
- 특히 Svelte나 React에서 최상위 컴포넌트에 에러가 나면 화면 전체가 빈 상태가 된다

### 2. 프레임워크 API의 타입을 정확히 알아야 한다

`$page.url`이 string인지 URL 객체인지는 Inertia.js 문서에 나와 있지만, 빠르게 코딩할 때 `window.location`과 혼동하기 쉽다. TypeScript를 쓰더라도 `any` 캐스팅하면 타입 체크가 무력화된다.

일반적인 함정 목록:
- `$page.url` → string (`.pathname` 없음)
- `$page.props.user` → TypeScript 제네릭으로 타입 지정 필요
- Inertia의 `router.visit()` → 비동기지만 Promise를 반환하지 않음

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

배포 후에는 항상 프로덕션 URL에서 직접 확인하는 습관을 들이자. smoke test를 자동화하면 더 좋다.

---

## TL;DR

| 항목 | 내용 |
|------|------|
| **증상** | SPA 배포 후 빈 화면 |
| **오해** | 서버 문제? 에셋 로딩 실패? |
| **실제 원인** | Inertia.js `usePage().url`이 string인데 `.pathname` 접근 |
| **해결** | `.startsWith()` 직접 사용 + optional chaining |
| **핵심 도구** | Playwright 콘솔 에러 자동 수집 |
| **재발 방지** | Inertia 타입 제네릭 활용, 배포 후 smoke test |
