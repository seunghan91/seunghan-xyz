---
title: "iOS 26 Liquid Glass 디자인 시스템을 웹에 적용하기 — Svelte 5 + CSS Custom Properties"
date: 2026-03-31
draft: false
tags: ["ios26", "design-system", "svelte", "css-custom-properties", "liquid-glass"]
categories: ["iOS", "Frontend"]
description: "Apple iOS 26의 Liquid Glass 디자인 토큰을 CSS Custom Properties로 추출하고, Svelte 5 Runes 컴포넌트로 만들어 Rails + Inertia.js 프로젝트에 적용한 실전 기록. backdrop-filter, 다크모드 셀렉터 삽질, npm 패키지화까지."
---

WWDC 2025에서 Apple이 발표한 Liquid Glass는 iOS 7 이후 가장 큰 UI 변화였다. 반투명 유리 재질에 빛이 굴절되는 듯한 효과가 핵심인데, 이걸 실제 웹 프로젝트에 적용해봤다. Figma Community Kit에서 디자인 토큰을 추출하고, CSS Custom Properties로 변환한 뒤, Svelte 5 컴포넌트로 만들어서 Rails + Inertia.js 프로젝트의 실제 페이지에 붙이는 전 과정을 정리한다.

결론부터 말하면, iOS 26 디자인 시스템은 웹에서도 충분히 구현 가능하다. 다만 다크모드 셀렉터 불일치 같은 함정이 있어서, 기존 프로젝트에 얹을 때는 CSS 변수 네이밍 컨벤션을 꼼꼼히 맞춰야 한다.

---

## Liquid Glass가 뭔지부터

Liquid Glass는 기존 Glassmorphism의 진화형이다. iOS 7때부터 써온 반투명 블러 효과에 **굴절(refraction)**, **반사 하이라이트(specular highlights)**, **컨텍스트 인식 변형**이 추가됐다.

| 특성 | Glassmorphism (iOS 7~) | Liquid Glass (iOS 26) |
|------|----------------------|----------------------|
| 배경 블러 | `backdrop-filter: blur()` | 동일 |
| 투명도 | 단일 rgba 배경 | 다중 레이어 + tint |
| 굴절 | 없음 | SVG `feDisplacementMap` |
| 하이라이트 | 없음 | inset box-shadow + ::after |
| 모드 | Light/Dark | Light/Dark/IC Light/IC Dark |

웹에서 Liquid Glass를 구현하는 핵심 CSS는 이렇다:

```css
.glass-panel {
  background: rgba(250, 250, 250, 0.7);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 0.5px solid rgba(255, 255, 255, 0.18);
  border-radius: 14px;
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.08);
}
```

`backdrop-filter`의 `blur()`와 `saturate()`를 조합하면 frosted glass 느낌이 나고, 반투명 border와 box-shadow로 깊이감을 준다. Apple 네이티브 앱처럼 완벽한 굴절 효과는 SVG `feDisplacementMap` 필터가 필요하지만, 웹 UI 수준에서는 `backdrop-filter`만으로도 충분히 그럴듯하다.

---

## 디자인 토큰 추출 — Figma에서 CSS Custom Properties로

Apple의 iOS & iPadOS 26 Figma Community Kit에서 디자인 토큰을 추출했다. 이 킷에는 색상, 타이포그래피, 스페이싱, Material(Liquid Glass), 애니메이션 값이 모두 들어있다.

추출한 토큰의 카테고리는 다음과 같다:

| 카테고리 | 토큰 수 | 예시 |
|----------|---------|------|
| System Colors | 12 | `--ios-color-red: #ff383c` |
| Labels | 4단계 | `--ios-label-primary: rgba(0,0,0,1)` |
| Backgrounds | 6 | `--ios-bg-primary: #ffffff` |
| Fills | 4단계 | `--ios-fill-primary: rgba(120,120,120,0.2)` |
| Grays | 8 | `--ios-gray: #8e8e93` |
| Separators | 2 | `--ios-separator: rgba(0,0,0,0.12)` |
| Liquid Glass | 5종 | `--ios-glass-bg: rgba(250,250,250,0.7)` |
| Typography | 11단계 | `--ios-type-body-size: 17px` |
| Animation | 6 | `--ios-duration-fast: 0.2s` |

이 토큰들을 CSS Custom Properties 파일로 정리했다. `--ios-` 프리픽스를 붙여서 기존 Tailwind CSS 변수와 충돌하지 않게 했다.

```css
:root {
  /* System Colors */
  --ios-color-red: #ff383c;
  --ios-color-blue: #0088ff;
  --ios-color-green: #34c759;
  --ios-color-purple: #cb30e0;
  
  /* Labels — 4단계 opacity */
  --ios-label-primary: rgba(0, 0, 0, 1);
  --ios-label-secondary: rgba(60, 60, 67, 0.6);
  --ios-label-tertiary: rgba(60, 60, 67, 0.3);
  
  /* Backgrounds */
  --ios-bg-primary: #ffffff;
  --ios-bg-grouped-secondary: #ffffff;
  
  /* Liquid Glass Material */
  --ios-glass-bg: rgba(250, 250, 250, 0.7);
  --ios-glass-radius-large: 14px;
  --ios-glass-shadow-blur: 40px;
  
  /* Animation */
  --ios-duration-fast: 0.2s;
  --ios-easing-default: cubic-bezier(0.2, 0, 0, 1);
  --ios-easing-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

타이포그래피는 SF Pro 폰트 기준 11단계로, 각 단계마다 size, line-height, letter-spacing, weight(regular + emphasized)가 정의된다:

```css
.ios-body {
  font-size: var(--ios-type-body-size);       /* 17px */
  line-height: var(--ios-type-body-lh);       /* 22px */
  letter-spacing: var(--ios-type-body-ls);    /* -0.43px */
  font-weight: var(--ios-type-body-weight);   /* 400 */
}

.ios-body.ios-emphasized {
  font-weight: var(--ios-type-body-weight-em); /* 600 */
}
```

Material(Liquid Glass) CSS 클래스도 함께 만들었다:

```css
.ios-glass {
  background: var(--ios-glass-bg);
  border-radius: var(--ios-glass-radius-large);
  box-shadow: 0 0 var(--ios-glass-shadow-blur) rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 0.5px solid rgba(255, 255, 255, 0.18);
}
```

---

## Svelte 5 Runes 컴포넌트 만들기

CSS 토큰만으로는 재사용이 불편하다. Svelte 5의 Runes 문법(`$props()`, `$state()`, `$derived()`)으로 컴포넌트화했다.

### SegmentedControl — iOS 스타일 탭 전환

```svelte
<script lang="ts">
  let {
    segments = [],
    selected = $bindable(0),
    onchange = undefined,
  }: {
    segments: { label: string; value: string }[]
    selected: number
    onchange?: (index: number, value: string) => void
  } = $props()

  function select(index: number) {
    selected = index
    onchange?.(index, segments[index].value)
  }
</script>

<div class="ios-segmented" role="tablist">
  {#each segments as segment, i (segment.value)}
    <button
      class="ios-segmented__item"
      class:ios-segmented__item--active={i === selected}
      role="tab"
      aria-selected={i === selected}
      onclick={() => select(i)}
      type="button"
    >
      {segment.label}
    </button>
  {/each}
</div>
```

스타일은 `<style>` 블록에서 iOS 26 토큰을 참조한다:

```css
.ios-segmented {
  display: flex;
  background: var(--ios-fill-quaternary);
  border-radius: 8px;
  padding: 2px;
}

.ios-segmented__item--active {
  background: var(--ios-bg-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
```

### StatCard — 통계 카드

```svelte
<script lang="ts">
  let {
    label, value,
    color = 'default',
    href = undefined,
    active = false,
    onclick = undefined,
  } = $props()
</script>

{#if href}
  <a {href} class="ios-stat-card ios-glass-interactive">
    <span class="ios-footnote ios-text-secondary">{label}</span>
    <span class="ios-title1 ios-emphasized" style:color={colorMap[color]}>
      {value}
    </span>
  </a>
{/if}
```

`ios-glass-interactive` 클래스를 붙이면 hover시 살짝 밝아지고, active시 `scale(0.98)`로 눌리는 느낌이 난다. Apple의 터치 피드백을 CSS transition으로 흉내낸 거다.

### 만든 컴포넌트 목록

| 컴포넌트 | 용도 | iOS 26 대응 |
|----------|------|-------------|
| `SegmentedControl` | 탭 전환 | Segmented Control |
| `StatCard` | 통계 수치 표시 | Grouped List Card |
| `SearchBar` | 검색/필터 영역 | Search Bar + Form |
| `FormField` | 입력 필드 래퍼 | List Row Input |
| `Pagination` | 페이지 네비게이션 | Custom |

---

## 삽질 1: 다크모드 셀렉터 불일치

여기서 첫 번째 삽질이 있었다. iOS 26 디자인 토큰 CSS의 다크모드는 `[data-theme="dark"]` 셀렉터를 사용한다:

```css
/* 원본 토큰 CSS */
[data-theme="dark"] {
  --ios-label-primary: rgba(255, 255, 255, 1);
  --ios-bg-primary: #000000;
  /* ... */
}
```

그런데 프로젝트는 `.dark` 클래스 기반이었다:

```typescript
// theme.ts
export function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.toggle('dark', mode === 'dark');
}
```

결과적으로 다크모드에서 iOS 26 변수가 전혀 안 바뀌었다. 라이트모드 값이 그대로 적용되면서 어두운 배경에 검은 텍스트가 나왔다.

**해결**: 토큰 CSS의 셀렉터를 `.dark`로 변경했다.

```css
/* 수정 후 */
.dark {
  --ios-label-primary: rgba(255, 255, 255, 1);
  --ios-bg-primary: #000000;
}
```

이건 디자인 시스템을 다른 프로젝트에 적용할 때 반드시 확인해야 할 포인트다. 다크모드 구현 방식은 프로젝트마다 다르다:

| 방식 | 셀렉터 | 사용처 |
|------|--------|--------|
| `class` 기반 | `.dark` | Tailwind CSS 기본값 |
| `data-theme` 속성 | `[data-theme="dark"]` | DaisyUI, 일부 디자인 시스템 |
| `prefers-color-scheme` | `@media` 쿼리 | OS 설정 자동 추적 |

제일 안전한 방법은 세 가지를 모두 지원하는 것이다:

```css
/* 1. class 기반 */
.dark { --ios-label-primary: rgba(255,255,255,1); }

/* 2. data-theme 기반 */
[data-theme="dark"] { --ios-label-primary: rgba(255,255,255,1); }

/* 3. OS 설정 fallback */
@media (prefers-color-scheme: dark) {
  :root:not(.light) { --ios-label-primary: rgba(255,255,255,1); }
}
```

---

## 삽질 2: Tailwind CSS와 CSS Custom Properties 공존

두 번째 걱정은 기존 Tailwind CSS와의 충돌이었다. 결론적으로 **전혀 문제없다.** 

CSS Custom Properties(`--ios-*`)는 글로벌 `:root`에 선언되지만, Tailwind의 유틸리티 클래스(`bg-gray-50`, `text-sm`)와 다른 네임스페이스를 쓰기 때문에 충돌하지 않는다. 하나의 페이지에서 Tailwind 클래스와 iOS 26 변수를 혼용해도 된다.

```svelte
<!-- Tailwind과 iOS 26 토큰 혼용 가능 -->
<div class="max-w-screen-xl mx-auto">
  <h1 class="ios-large-title ios-emphasized">제목</h1>
  <div style="background: var(--ios-bg-grouped-secondary);">
    <!-- iOS 26 스타일 영역 -->
  </div>
</div>
```

`application.css`에서의 import 순서만 지켜주면 된다:

```css
@import "tailwindcss";

/* iOS 26 — Tailwind 뒤에 로드 */
@import "../css/ios26/tokens.css";
@import "../css/ios26/typography.css";
@import "../css/ios26/materials.css";
```

---

## npm 패키지화 — pnpm link로 로컬 개발

CSS 파일을 직접 복사하는 건 빠르지만, 여러 프로젝트에서 쓰려면 npm 패키지가 낫다. 디자인 시스템이 이미 pnpm 모노레포 구조로 되어 있었기 때문에 패키지화는 간단했다.

### 패키지 구조

```
ios26-design-system/
├── packages/
│   ├── tokens/           # JSON → CSS/JS/Dart 빌드
│   │   ├── src/          # 5개 JSON 소스
│   │   ├── build.js      # 커스텀 빌드 스크립트
│   │   └── package.json
│   └── svelte-inertia/   # 프레임워크 레디 CSS
│       ├── tokens.css    # --ios-* 변수 (수작업)
│       ├── typography.css
│       ├── materials.css
│       └── package.json
├── pnpm-workspace.yaml
└── package.json          # Turborepo + Changesets
```

여기서 중요한 발견이 있었다. `tokens/` 패키지의 빌드 출력물(`--color-accent-red`)과 `svelte-inertia/` 패키지의 수작업 CSS(`--ios-color-red`)가 **변수명이 달랐다.** 빌드 스크립트가 JSON의 구조를 기계적으로 변환하다 보니 네이밍이 달라진 거다.

```
빌드 출력: --color-accent-red     (자동 생성)
수작업 CSS: --ios-color-red        (프레임워크 레디)
```

컴포넌트들이 `--ios-*` 네이밍을 쓰고 있었기 때문에, `svelte-inertia` 패키지를 링크하는 게 맞았다.

### pnpm link 연결

```bash
cd my-project/web
pnpm link /path/to/ios26-design-system/packages/svelte-inertia
```

그러면 `node_modules/@ios26_design_system/svelte-inertia`가 심볼릭 링크로 생긴다. CSS import를 패키지 경로로 변경:

```css
@import "@ios26_design_system/svelte-inertia/tokens.css";
@import "@ios26_design_system/svelte-inertia/typography.css";
@import "@ios26_design_system/svelte-inertia/materials.css";
```

Vite가 `node_modules` 안의 CSS 파일도 잘 resolve해줘서 빌드가 바로 통과했다.

### 배포 환경에서의 함정

그런데 이 방식은 **로컬에서만 작동한다.** CI/CD 서버(Render, Vercel 등)에는 심볼릭 링크가 없기 때문에 빌드가 실패한다:

```
ENOENT: no such file or directory, open 
'/opt/render/project/src/web/node_modules/@ios26_design_system/...'
```

배포 환경에서는 두 가지 선택지가 있다:

1. **CSS 파일을 프로젝트에 직접 복사** (간단, 즉시 배포 가능)
2. **npm publish** 후 정식 의존성으로 설치 (정석, Changesets로 버전 관리)

결국 배포를 위해 CSS 파일을 프로젝트 내부에 복사해두고, 로컬 개발 시에만 pnpm link를 쓰는 하이브리드 방식을 택했다.

---

## 삽질 3: Devise 제거 후유증

디자인 시스템과 직접 관련은 없지만, 같은 배포 사이클에서 만난 문제라 기록한다. Rails의 Devise 인증 라이브러리를 제거하고 `has_secure_password`로 마이그레이션한 후, 프로덕션에서 빌드가 실패했다.

```ruby
# NoMethodError 발생
class RegistrationsController < Api::V1::BaseController
  respond_to :json  # <- 이 줄이 문제
end
```

`respond_to :json`은 `ActionController::MimeResponds` 모듈의 클래스 매크로인데, Devise가 없으면 API 컨트롤러에서 자동으로 include되지 않는다. 어차피 모든 액션에서 `render json:`을 직접 쓰고 있었기 때문에 `respond_to :json` 줄을 삭제하면 해결됐다.

프레임워크를 교체할 때는 **전수조사**가 필수다. `grep -r "respond_to\s+:" app/controllers/`로 잔재를 찾아서 3개 컨트롤러에서 동일한 문제를 발견하고 모두 수정했다.

이 외에도 Devise 잔재가 더 있었다:

```bash
# 발견된 잔재들
config/initializers/devise.rb.bak    # 백업 파일
config/locales/devise.en.yml         # 번역 파일
VersionInfoModal.svelte              # UI에 Devise 라이선스 표시
```

빌드에는 영향 없지만, 불필요한 파일은 깨끗이 정리하는 게 맞다.

---

## 실전 적용 결과

iOS 26 디자인 시스템을 적용한 페이지의 구성은 이렇다:

```
application.css
├── tailwindcss (기존)
├── css/ios26/tokens.css      ← 색상, 레이아웃, 글래스 변수
├── css/ios26/typography.css  ← SF Pro 타이프 스케일
└── css/ios26/materials.css   ← Liquid Glass 유틸리티 클래스
```

```
components/ios/
├── SegmentedControl.svelte   ← 탭 전환
├── StatCard.svelte           ← 통계 카드
├── SearchBar.svelte          ← 필터 영역
├── FormField.svelte          ← 입력 필드
└── Pagination.svelte         ← 페이지 네비게이션
```

기존 Tailwind 스타일 페이지와 iOS 26 스타일 페이지가 같은 레이아웃 안에서 공존한다. CSS Custom Properties는 격리가 잘 되기 때문에, 한 페이지만 바꿔도 다른 페이지에 영향이 없다.

---

## iOS 26 Liquid Glass 웹 구현 시 주의사항

### backdrop-filter 성능

`backdrop-filter: blur(40px)`는 GPU를 사용하기 때문에 보통은 빠르지만, 블러 반경이 크거나 겹치는 요소가 많으면 저사양 기기에서 프레임 드롭이 생긴다. 모바일에서는 `blur(20px)` 이하를 권장한다.

### Safari와 -webkit- 프리픽스

2026년 현재에도 Safari에서 `backdrop-filter`는 `-webkit-` 프리픽스가 필요하다. 둘 다 선언해야 한다:

```css
backdrop-filter: blur(40px) saturate(180%);
-webkit-backdrop-filter: blur(40px) saturate(180%);
```

### SVG 굴절 효과의 한계

진짜 Liquid Glass처럼 배경이 왜곡되는 refraction 효과는 SVG `feDisplacementMap` 필터로 구현 가능하지만, **Chromium 기반 브라우저에서만** 제대로 작동한다. Safari에서는 SVG 필터와 `backdrop-filter` 조합이 불안정하다. 실제 프로덕션에서는 frosted glass(블러 + 투명) 수준이 현실적이다.

### 접근성(a11y)

반투명 배경 위의 텍스트는 대비가 낮아지기 쉽다. WCAG AA 기준 4.5:1 대비를 반드시 확인해야 한다. iOS 26 토큰의 `--ios-label-primary`가 `rgba(0,0,0,1)` 순수 검정인 이유도 이 때문이다.

---

## 결론

iOS 26 Liquid Glass를 웹에 적용하는 건 생각보다 실용적이었다. CSS Custom Properties로 토큰화하면 Tailwind과도 공존하고, Svelte 5 Runes와 조합하면 깔끔한 컴포넌트를 만들 수 있다.

핵심 정리:

1. **`backdrop-filter: blur() saturate()`** 조합이 Liquid Glass의 80%다
2. **CSS Custom Properties**로 토큰화하면 프레임워크 독립적으로 재사용 가능하다
3. **다크모드 셀렉터**는 반드시 프로젝트의 방식에 맞춰야 한다 (`.dark` vs `[data-theme]` vs `@media`)
4. **pnpm link**는 로컬 개발에 편하지만, CI/CD에서는 npm publish가 필요하다
5. SVG 굴절 효과는 Chromium only — 프로덕션에서는 블러 수준이 현실적이다

Figma 토큰 → CSS 변수 → Svelte 컴포넌트 → npm 패키지 파이프라인을 한번 구축해두면, 다음 프로젝트에는 `pnpm add @org/design-tokens`만으로 iOS 26 스타일을 쓸 수 있다.
