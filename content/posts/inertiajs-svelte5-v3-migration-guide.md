---
title: "Inertia.js v2→v3 마이그레이션 — Svelte 5 + Rails 8 실전 삽질 기록"
date: 2026-04-04
draft: false
tags: ["inertia.js", "svelte5", "rails", "migration", "frontend"]
categories: ["Rails", "Frontend"]
description: "@inertiajs/svelte v2에서 v3로 업그레이드하면서 겪은 삽질 과정. $page store 제거, persistent layout 변환, script element 전환까지 실전 기록."
---

Rails 8 + Svelte 5 프로젝트에서 `@inertiajs/svelte`를 v2에서 v3로 올렸다. "패키지 버전만 올리면 되겠지"라는 안일한 생각으로 시작했다가 반나절을 날렸다. 이 글은 그 삽질의 기록이다.

---

## 왜 업그레이드해야 했나

프로젝트에서 Svelte 5를 쓰고 있었는데, `@inertiajs/svelte` v2는 Svelte 5를 "대충" 지원했다. 문제는 persistent layout이었다. Svelte 5는 컴포넌트를 함수로 컴파일하는데, Inertia v2는 `page.default.layout = AppLayout` 처럼 클래스 기반 컴포넌트에 속성을 추가하는 방식을 썼다. Svelte 5에서는 이게 작동하지 않았다.

결과적으로 40개 넘는 페이지에 `<AppLayout>`을 수동으로 감싸야 했다. 유지보수 악몽이었다.

v3가 2026년 3월 26일에 릴리즈됐고, Svelte 5를 네이티브 지원한다고 했다. persistent layout도 `<script context="module">`에서 `export const layout`으로 선언하면 된다고. 바로 업그레이드를 시작했다.

---

## 첫 시도: 패키지만 올리기 (실패)

```bash
pnpm add @inertiajs/svelte@^3.0.2
```

설치는 됐다. 서버를 재시작하고 브라우저를 열었다.

**빈 화면.**

콘솔을 열어보니:

```
TypeError: Cannot read properties of null (reading 'component')
    at rx (application.js:92:3314)
```

페이지 데이터를 못 찾는 거다. 왜?

---

## 핵심 변경 #1: data-page → script element

v2에서 Rails의 `inertia_rails` gem은 이렇게 렌더했다:

```html
<div id="app" data-page='{"component":"Dashboard","props":{...}}'></div>
```

v3의 `@inertiajs/core`는 완전히 다른 곳을 찾는다:

```html
<script data-page="app" type="application/json">
{"component":"Dashboard","props":{...}}
</script>
<div id="app"></div>
```

실제로 v3 소스 코드를 열어봤다:

```javascript
// @inertiajs/core v3 — getInitialPageFromDOM
var getInitialPageFromDOM = (id) => {
  const scriptEl = document.querySelector(
    `script[data-page="${id}"][type="application/json"]`
  );
  if (scriptEl?.textContent) {
    return JSON.parse(scriptEl.textContent);
  }
  return null;  // ← 여기서 null 반환 → 에러 발생
};
```

`<div data-page>`가 아니라 `<script data-page>`를 찾는다. 이걸 모르면 영원히 빈 화면만 본다.

### 해결: Rails initializer 설정

`inertia_rails` gem 3.15.0부터 script element 렌더링을 지원한다. initializer에 한 줄만 추가하면 된다:

```ruby
# config/initializers/inertia_rails.rb
InertiaRails.configure do |config|
  config.use_script_element_for_initial_page = true
end
```

이 설정을 켜면 Rails가 자동으로 `<script type="application/json">` 형태로 렌더한다. JSON을 HTML attribute에 넣지 않으니 entity encoding 오버헤드도 사라진다. 실제로 같은 데이터를 attribute에 넣으면 ~500자, script에 넣으면 ~300자로 약 40% 줄어든다고 한다.

---

## 핵심 변경 #2: $page store → $state rune

v2에서 `page`는 Svelte store였다. `$page.props.auth`처럼 `$` 접두사로 구독했다.

v3에서 `page`는 Svelte 5의 `$state` rune이다. store가 아니다.

```javascript
// v3 소스 — page.svelte.js
const page = $state({
  component: '',
  props: {},
  url: '',
  version: null,
});
export default page;
```

store가 아니니까 `.subscribe()`도 없고, `$page`라고 쓰면 에러가 난다:

```
TypeError: r.subscribe is not a function
```

이 에러가 나면 코드 어딘가에서 `$page`를 쓰고 있는 거다.

### 해결: 전수 조사 + 치환

프로젝트 전체에서 `$page`를 검색했다. 7개 파일, 16군데에서 사용 중이었다.

| 파일 | 변경 내용 |
|------|----------|
| `AppLayout.svelte` | `($page.props as any).auth` → `(page.props as any).auth` |
| `Sidebar.svelte` | `($page.props.boards as Board[])` → `(page.props.boards as Board[])` |
| `Navigation.svelte` | `($page.props as any)` → `(page.props as any)` 2곳 |
| `Dashboard.svelte` | `($page.props as any)` → `(page.props as any)` 3곳 |
| `Home.svelte` | `$page.props.auth` → `page.props.auth` 5곳 |
| `Posts/Show.svelte` | `$page.props.auth` → `page.props.auth` 3곳 |
| `ContentGating.svelte` | `$page.props.auth` → `page.props.auth` 1곳 |

핵심은 `$` 접두사만 제거하는 거다. import는 그대로 `import { page } from '@inertiajs/svelte'`로 유지.

---

## 핵심 변경 #3: persistent layout 방식

v2에서 persistent layout이 제대로 작동하지 않아서 모든 페이지에 수동으로 `<AppLayout>`을 감쌌었다:

```svelte
<!-- v2 방식: 수동 래핑 (41개 파일 전부) -->
<script lang="ts">
  import AppLayout from '@/layouts/AppLayout.svelte';
  // ... 컴포넌트 로직
</script>

<AppLayout>
  <div class="dashboard">
    <!-- 페이지 내용 -->
  </div>
</AppLayout>
```

v3에서는 `<script context="module">`에서 layout을 export하면 Inertia가 알아서 관리한다:

```svelte
<!-- v3 방식: persistent layout -->
<script context="module">
  import AppLayout from '@/layouts/AppLayout.svelte'
  export const layout = AppLayout
</script>

<script lang="ts">
  // ... 컴포넌트 로직 (AppLayout import 불필요)
</script>

<div class="dashboard">
  <!-- 페이지 내용 (AppLayout 래핑 불필요) -->
</div>
```

41개 파일을 전부 변환했다. 기계적인 작업이라 스크립트로 처리했지만, `<svelte:head>` 블록이 `<AppLayout>` 안에 들어가면 안 되는 등 엣지 케이스가 있었다.

### 변환 시 주의사항

`<svelte:head>`는 Svelte에서 최상위에만 올 수 있다. `<AppLayout>` 안에 넣으면 이런 에러가 난다:

```
[vite-plugin-svelte] Messages/Index.svelte:81:0
`<svelte:head>` tags cannot be inside elements or blocks
```

4개 파일에서 이 문제가 있었다. `<svelte:head>`를 `<AppLayout>` 밖으로 빼야 한다.

---

## 핵심 변경 #4: router 이벤트 이름

v3에서 두 개의 router 이벤트 이름이 바뀌었다:

| v2 이벤트 | v3 이벤트 | 설명 |
|----------|----------|------|
| `invalid` | `httpException` | 서버가 non-Inertia 응답 반환 시 |
| `exception` | `networkError` | 네트워크 오류 발생 시 |

```javascript
// v2
router.on('invalid', () => { navigation.reset() })
router.on('exception', () => { navigation.reset() })

// v3
router.on('httpException', () => { navigation.reset() })
router.on('networkError', () => { navigation.reset() })
```

이름 변경이 전부다. 콜백 시그니처는 동일하다. v3에서는 per-visit 콜백도 추가됐다:

```javascript
router.post('/users', data, {
  onHttpException: (response) => {
    // 이 요청에만 적용되는 에러 핸들링
    return false  // 에러 페이지로 이동 방지
  }
})
```

---

## setup 함수는 어떻게?

v2에서는 `mount`를 import해서 수동으로 호출했다:

```javascript
// v2
import { mount } from 'svelte'

createInertiaApp({
  resolve: name => { /* ... */ },
  setup({ el, App, props }) {
    mount(App, { target: el, props })
  },
})
```

v3에서는 setup을 아예 안 넘겨도 된다. 내부적으로 알아서 `mount`를 호출한다:

```javascript
// v3 — setup 생략 가능
createInertiaApp({
  resolve: name => {
    const pages = import.meta.glob('../pages/**/*.svelte', { eager: true })
    return pages[`../pages/${name}.svelte`]
  },
  // setup 생략 → v3가 자동으로 mount(App, { target, props }) 호출
})
```

v3 소스를 직접 열어보면 이렇다:

```javascript
// createInertiaApp.js 내부
if (setup) {
  await setup({ el: target, App, props });
} else {
  // setup 없으면 자동 마운트
  mount(App, { target, props, context });
}
```

---

## 삽질 타임라인

실제로 겪은 순서를 정리하면:

1. `pnpm add @inertiajs/svelte@3.0.2` → 빈 화면
2. `Cannot read properties of null (reading 'component')` 에러 확인
3. v3 소스에서 `getInitialPageFromDOM` 발견 → script element를 찾는다는 걸 알게 됨
4. `inertia_rails` initializer에 `use_script_element_for_initial_page = true` 추가
5. 서버 재시작 → `r.subscribe is not a function` 에러
6. `$page` store → `page` rune 변환 (7파일)
7. persistent layout 수동 래핑 → `export const layout` 변환 (41파일)
8. `<svelte:head>` 위치 문제 수정 (4파일)
9. router 이벤트 이름 변경
10. 전체 테스트 통과 확인 (537/538)

가장 시간이 오래 걸린 건 1~3번이었다. "왜 빈 화면이지?"를 해결하는 데 에러 메시지가 너무 모호했다. 결국 v3 소스 코드를 직접 읽어서 원인을 찾았다.

---

## v2 vs v3 주요 차이점 정리

| 항목 | v2 | v3 |
|------|----|----|
| **Svelte 지원** | Svelte 4 + 5 (부분) | Svelte 5 전용 |
| **page 데이터** | `$page` (store) | `page` ($state rune) |
| **초기 페이지** | `<div data-page="...">` | `<script type="application/json">` |
| **persistent layout** | `page.default.layout` (v5에서 미작동) | `export const layout` (context module) |
| **HTTP 클라이언트** | Axios 의존 | 내장 XHR (~15KB 절감) |
| **에러 이벤트** | `invalid` / `exception` | `httpException` / `networkError` |
| **setup** | 필수 (mount 직접 호출) | 선택 (자동 마운트) |
| **layout props** | 없음 (workaround 필요) | `setLayoutProps` 내장 |
| **optimistic update** | 수동 구현 | 내장 API |

---

## inertia_rails gem 버전 확인

Rails 쪽에서는 gem 버전이 중요하다:

```bash
bundle list | grep inertia
# inertia_rails (3.16.0) ← 3.15.0 이상이면 OK
```

3.15.0 미만이면 `use_script_element_for_initial_page` 옵션 자체가 없다. 업그레이드가 필요하다:

```ruby
# Gemfile
gem "inertia_rails", ">= 3.15.0"
```

```bash
bundle update inertia_rails
```

---

## application.js 최종 형태

삽질 끝에 정리된 엔트리포인트:

```javascript
// @inertiajs/svelte v3 + Svelte 5 + Rails 8
import '../styles/application.css'
import { createInertiaApp, router } from '@inertiajs/svelte'
import { theme } from '../stores/theme'
import { navigation, isNavigationPending } from '../stores/navigation'

// CSRF token (Rails)
router.on('before', (event) => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
  if (csrfToken) {
    event.detail.visit.headers['X-CSRF-Token'] = csrfToken
  }
})

// Navigation progress
router.on('start', () => { navigation.start() })
router.on('finish', () => { navigation.finish() })
router.on('httpException', () => { navigation.reset() })  // v3 이름
router.on('networkError', () => { navigation.reset() })   // v3 이름

isNavigationPending.subscribe((pending) => {
  document.documentElement.dataset.inertiaPending = pending ? 'true' : 'false'
})

theme.init()

// Inertia App — setup 생략, v3 자동 마운트
createInertiaApp({
  resolve: name => {
    const pages = import.meta.glob('../pages/**/*.svelte', { eager: true })
    return pages[`../pages/${name}.svelte`]
  },
})
```

v2 대비 코드가 훨씬 간결해졌다. `import { mount } from 'svelte'`도 필요 없고, setup 콜백도 없고, AppLayout import도 없다.

---

## 페이지 컴포넌트 최종 형태

```svelte
<!-- Dashboard.svelte — v3 persistent layout -->
<script context="module">
  import AppLayout from '@/layouts/AppLayout.svelte'
  export const layout = AppLayout
</script>

<script lang="ts">
  let { stats, user } = $props()
</script>

<div class="dashboard">
  <h1>내 대시보드</h1>
  <p>안녕하세요, {user?.name}님</p>
  <!-- 페이지 내용 -->
</div>
```

`<AppLayout>`으로 감싸지 않아도 된다. Inertia가 `export const layout`을 읽어서 자동으로 래핑한다. 페이지 간 이동해도 레이아웃은 유지되고, 사이드바 상태도 보존된다.

---

## 결론

Inertia v2 → v3 마이그레이션은 "패키지 버전 올리기"가 아니라 "아키텍처 전환"이다. 핵심 변경 4가지를 정리하면:

1. **`use_script_element_for_initial_page = true`** — Rails initializer 필수
2. **`$page` → `page`** — store 구독 제거, $state rune 직접 접근
3. **`export const layout`** — 수동 래핑에서 선언적 layout으로
4. **`httpException` / `networkError`** — router 이벤트 이름 변경

에러 메시지만으로는 원인을 알기 어렵다. v3 소스 코드를 직접 읽어보는 게 가장 빠른 디버깅 방법이었다. 특히 `getInitialPageFromDOM`이 script element를 찾는다는 걸 알기 전까지는 왜 빈 화면인지 전혀 감을 못 잡았다.

업그레이드 후 체감되는 개선:
- 41개 파일에서 수동 `<AppLayout>` 래핑 제거 → 코드 300줄 감소
- persistent layout이 진짜로 작동 → 사이드바 상태 유지
- Axios 의존 제거 → 번들 ~15KB 절감
- 초기 페이지 페이로드 ~40% 감소 (script element)

삽질은 반나절이었지만, 결과물은 충분히 가치 있었다.
