---
title: "Svelte 5 + Inertia.js 프로젝트 8개에 디자인 토큰 체계 잡기"
date: 2026-03-03
draft: false
tags: ["Svelte 5", "Inertia.js", "Design Tokens", "Tailwind CSS", "디자인 시스템", "CSS Custom Properties"]
description: "Rails + Inertia.js + Svelte 5 기반 프로젝트 8개를 운영하면서 디자인 시스템 적용 현황을 감사하고, 미적용 프로젝트에 CSS Custom Properties 기반 디자인 토큰을 일괄 구축한 과정을 정리한다."
cover:
  image: "/images/og/svelte-inertia-design-tokens-system.png"
  alt: "Svelte Inertia Design Tokens System"
  hidden: true
---

Rails + Inertia.js + Svelte 5 기반으로 여러 프로젝트를 운영하다 보면 하나의 고질적 문제가 생긴다. **각 프로젝트마다 색상, 타이포그래피, 간격 등의 디자인 기준이 제각각**이라는 점이다. 어떤 프로젝트는 `tailwind.config.js`에 체계적으로 정리되어 있고, 어떤 프로젝트는 `bg-[#3182F6]` 같은 하드코딩이 넘쳐난다.

이 문제는 프로젝트 수가 늘어날수록 더 심각해진다. 새 프로젝트를 시작할 때마다 색상을 다시 정의하고, 버튼 스타일을 다시 만들고, 폰트 크기 기준을 다시 잡아야 한다. 어느 프로젝트에서 잘 만든 컴포넌트를 다른 프로젝트로 복사하려 해도 디자인 기준이 달라서 그대로 쓸 수가 없다.

이번에 전체 프로젝트를 대상으로 디자인 토큰 감사(audit)를 하고, 미적용 프로젝트에 체계를 잡은 과정을 기록한다.

---

## 1. 현황 감사: 8개 프로젝트 디자인 시스템 점검

먼저 모든 Svelte + Inertia.js 프로젝트를 대상으로 4가지 기준을 확인했다.

| 기준 | 확인 항목 |
|------|----------|
| **UI 컴포넌트** | `components/ui/` 디렉토리 존재 여부와 컴포넌트 수 |
| **디자인 토큰** | `tokens.css` 또는 CSS 변수 정의 파일 존재 |
| **테마 시스템** | `theme.ts`, `tailwind.config.js`의 색상/타이포 확장 |
| **Storybook** | `.storybook/` 디렉토리와 stories 파일 |

이 4가지 기준을 선택한 이유가 있다. UI 컴포넌트 수는 프로젝트의 컴포넌트 재사용 성숙도를 나타내고, 디자인 토큰 파일 유무는 "값의 원본이 한 곳에 있는가"를 판별하는 핵심 지표다. 테마 시스템은 Tailwind와의 통합 수준을 보여주며, Storybook은 컴포넌트 문서화 및 독립 개발 환경의 존재를 의미한다.

### 감사 결과

```
프로젝트 A  ✅ 토큰 + Storybook + 카테고리별 컴포넌트 → 완전 적용
프로젝트 B  ⚠️ 18개 UI + design-system 문서 있으나 토큰 파일 없음
프로젝트 C  ⚠️ 22개 UI + theme.ts 있으나 토큰 체계 없음
프로젝트 D  ❌ 15개 UI 있으나 토큰/테마 없음 (보일러플레이트)
프로젝트 E  ❌ 5개 UI만, 토큰/테마 없음
프로젝트 F  ❌ 도메인별 컴포넌트만, 공통 UI 없음
프로젝트 G  ❌ 1개 UI만, 사실상 디자인 시스템 없음
프로젝트 H  ❌ 프론트엔드 구조 자체 미완성
```

8개 중 **완전 적용 1개, 부분 적용 2개, 미적용 5개**. 예상보다 심각했다.

부분 적용(B, C)이 오히려 더 까다로운 경우였다. UI 컴포넌트가 이미 10개 이상 만들어져 있어서 리팩토링 비용이 미적용 프로젝트보다 더 컸다. 특히 프로젝트 C는 `theme.ts`에 색상값이 TypeScript 상수로 정의되어 있었는데, 이를 CSS Custom Properties로 전환하면서 기존 코드에서 `COLORS.primary`로 참조하던 부분을 모두 `var(--color-primary)`로 바꿔야 했다.

---

## 2. 레퍼런스 분석: 잘 되어 있는 프로젝트의 구조

완전 적용된 프로젝트의 디자인 시스템 구조를 분석했다.

```
app/frontend/
├── css/
│   └── tokens.css              ← CSS Custom Properties (핵심)
├── components/
│   ├── card/
│   ├── data-display/
│   ├── feedback/
│   ├── input/
│   ├── layout/
│   ├── navigation/
│   ├── overlay/
│   └── social/
├── stories/
│   ├── component/              ← 컴포넌트별 stories
│   ├── overview/               ← 프로젝트 개요 문서
│   └── style/                  ← 색상, 타이포, 간격 문서
└── .storybook/
    ├── main.js
    └── preview.js
```

핵심은 `tokens.css`였다. 모든 디자인 값이 CSS Custom Properties로 정의되어 있고, `tailwind.config.js`와 Svelte 컴포넌트 양쪽에서 참조한다.

컴포넌트 디렉토리가 도메인이 아닌 **UI 패턴**으로 분류되어 있다는 점도 중요했다. `card/`, `feedback/`, `overlay/` 같은 구분은 어느 서비스든 재사용 가능한 분류다. 반면 미적용 프로젝트들은 대부분 `components/PostCard.svelte`, `components/UserProfile.svelte`처럼 도메인에 종속된 구조였다.

### tokens.css 구조 (8개 섹션)

```css
:root {
  /* 1. Colors — Primary (50-900 스케일) */
  --color-primary-50: #EBF4FF;
  --color-primary-100: #DBEAFE;
  --color-primary-500: #3182F6;
  --color-primary-600: #2563EB;
  --color-primary-900: #1E3A8A;

  /* 2. Colors — Semantic (success, warning, error, info) */
  --color-success: #05C072;
  --color-success-bg: #E8FFF5;
  --color-warning: #F5A623;
  --color-warning-bg: #FFF8E6;
  --color-error: #F04452;
  --color-error-bg: #FFF0F1;
  --color-info: #3182F6;

  /* 3. Colors — Gray Scale */
  --color-gray-50: #F9FAFB;
  --color-gray-100: #F2F4F6;
  --color-gray-200: #E5E8EB;
  --color-gray-400: #9EA6B2;
  --color-gray-600: #6B7684;
  --color-gray-900: #191F28;

  /* 4. Colors — Background, Surface, Border, Text */
  --color-bg-primary: #FFFFFF;
  --color-bg-surface: #F9FAFB;
  --color-border: #E5E8EB;
  --color-text-primary: #191F28;
  --color-text-secondary: #6B7684;
  --color-text-disabled: #9EA6B2;

  /* 5. Typography */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;
  --font-size-xs: 12px;
  --font-size-sm: 13px;
  --font-size-base: 15px;
  --font-size-lg: 17px;
  --font-size-xl: 20px;
  --font-size-2xl: 24px;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --line-height-tight: 1.3;
  --line-height-normal: 1.6;

  /* 6. Spacing (8px 그리드) */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-smd: 12px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --spacing-2xl: 48px;

  /* 7. Border Radius, Shadows, Z-Index */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.06), 0 4px 6px rgba(0, 0, 0, 0.04);
  --z-dropdown: 100;
  --z-modal: 200;
  --z-toast: 300;

  /* 8. Transitions, Touch Target */
  --transition-fast: 100ms ease;
  --transition-normal: 200ms ease;
  --transition-slow: 300ms ease;
  --touch-target-min: 44px;
}
```

이 8개 섹션 구조는 처음에 완전히 적용된 프로젝트에서 참고한 것이지만, 운영하면서 몇 가지를 추가했다. `--z-dropdown`, `--z-modal`, `--z-toast`처럼 z-index 체계를 토큰으로 정의해두면 모달 위에 드롭다운이 올라오는 z-index 충돌 문제를 원천 차단할 수 있다.

---

## 3. 핵심 설계 결정

### Tailwind 설정 vs CSS Custom Properties — 둘 다 필요한 이유

Tailwind CSS 4에서는 `@theme` 블록이 CSS-first 설정 역할을 한다. 그렇다면 `tokens.css`가 왜 별도로 필요할까?

```
tokens.css (Source of Truth)
├── 모든 디자인 값의 원본
├── Svelte <style> 블록에서 직접 사용
├── JavaScript에서 getComputedStyle로 접근
└── 프레임워크 무관 (Flutter 연동 시 참조)

@theme 또는 tailwind.config.js (Integration Layer)
├── Tailwind 유틸리티 클래스 생성
├── bg-primary, text-gray-600 등
└── tokens.css 값을 참조하거나 동일값 유지
```

Tailwind만으로는 부족한 경우가 실무에서 자주 발생한다. Svelte의 `<style>` 블록에서 복잡한 CSS를 작성할 때, JavaScript에서 런타임에 색상값을 읽어야 할 때(Canvas API, Three.js, SVG 조작 등), 또는 Flutter 웹뷰와 동일한 색상 기준을 공유해야 할 때가 그렇다. 이런 경우에 `var(--color-primary)`는 Tailwind 클래스가 없는 환경에서도 작동한다.

**Tailwind CSS 3** 프로젝트 (`tailwind.config.js` 사용)에서는 tokens.css와 config 파일의 값을 1:1로 일치시킨다.

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#3182F6',  // tokens.css --color-primary-500 과 동일
          50: '#EBF4FF',
          600: '#2563EB',
        },
        gray: {
          50: '#F9FAFB',      // tokens.css --color-gray-50 과 동일
          900: '#191F28',
        },
      },
      borderRadius: {
        lg: '12px',           // tokens.css --radius-lg 과 동일
      },
    },
  },
}
```

**Tailwind CSS 4** 프로젝트 (`@theme` 사용)에서는 tokens.css를 `application.css` 최상단에서 import하고, `@theme`에서 동일한 값을 등록한다.

```css
/* application.css */
@import "../css/tokens.css";    /* ← 먼저 로드 */
@import "tailwindcss";

@theme {
  --color-primary: #3182F6;     /* tokens.css와 동일 값 */
  --color-primary-50: #EBF4FF;
  --color-primary-600: #2563EB;
  --radius-lg: 12px;
}
```

Tailwind CSS 4의 `@theme` 블록은 CSS Custom Properties를 Tailwind 유틸리티로 자동 노출한다. 즉 `--color-primary`를 `@theme`에 등록하면 `bg-primary`, `text-primary`, `border-primary` 클래스가 자동 생성된다. tokens.css와 @theme에 같은 값을 두 번 쓰는 것이 중복처럼 보이지만, 역할이 다르다. tokens.css는 CSS 런타임에서의 접근성을 담당하고, @theme는 Tailwind 빌드 타임 클래스 생성을 담당한다.

### 다크 모드 토큰 전략

다크 모드를 지원하는 프로젝트에서는 `:root`에 라이트 모드 기본값을, `.dark` 셀렉터에서 오버라이드한다.

```css
:root {
  --color-bg-primary: #FFFFFF;
  --color-bg-surface: #F9FAFB;
  --color-text-primary: #191F28;
  --color-text-secondary: #6B7684;
  --color-border: #E5E8EB;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04);
}

:root.dark {
  --color-bg-primary: #0D0D0D;
  --color-bg-surface: #1A1A1A;
  --color-text-primary: #F5F5F5;
  --color-text-secondary: #9EA6B2;
  --color-border: #2D2D2D;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.25);
}
```

이렇게 하면 Svelte 컴포넌트에서 다크 모드를 신경 쓸 필요 없이 `var(--color-bg-primary)`만 쓰면 된다. 다크 모드 전환은 `<html>` 태그에 `.dark` 클래스를 토글하는 것만으로 전체 UI가 바뀐다.

Inertia.js + Rails 환경에서는 다크 모드 토글 상태를 `localStorage`에 저장하고, Rails 레이아웃에서 초기 렌더링 전에 적용하는 패턴을 쓴다:

```html
<!-- app/views/layouts/application.html.erb -->
<script>
  // 레이아웃 렌더링 전 다크 모드 적용 (깜빡임 방지)
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark');
  }
</script>
```

### 프로젝트별 브랜드 색상 분리

모든 프로젝트가 같은 구조를 공유하되, 브랜드 색상만 다르게 설정했다.

```
프로젝트별 Primary Color:
├── 서비스 A: Blue      #2563EB  (차량 커뮤니티)
├── 서비스 B: Sky Blue  #0EA5E9  (음성 소셜)
├── 서비스 C: Toss Blue #3182F6  (관리자)
├── 서비스 D: Toss Blue #3183F6  (팀 매칭)
└── 보일러플레이트: Toss Blue #3182F6 (커스터마이징 포인트 주석 포함)
```

색상 외의 나머지 토큰(간격, 폰트 크기, 반지름, 그림자)은 모든 프로젝트에서 동일하다. 덕분에 한 프로젝트에서 만든 컴포넌트를 다른 프로젝트로 복사해도 `--spacing-md`, `--radius-lg` 같은 변수가 그대로 작동한다.

---

## 4. 일괄 적용 과정

### 병렬 실행

5개 프로젝트에 동시에 토큰 파일을 생성했다. 각 프로젝트마다:

1. `app/frontend/css/` 디렉토리 생성
2. 프로젝트의 기존 색상/설정 분석 (application.css, tailwind.config.js)
3. 8개 섹션으로 구성된 `tokens.css` 생성
4. 기존 CSS 파일에 `@import` 추가

Claude Code를 활용해 여러 프로젝트를 병렬로 처리했다. 각 프로젝트의 기존 `tailwind.config.js`를 분석한 뒤, 정의된 색상값과 일치하는 tokens.css를 자동 생성하도록 했다. 이 과정에서 가장 중요한 것은 **기존 값과의 정합성**이었다.

### 기존 설정과의 정합성 확인

가장 신경 쓴 부분은 **기존 tailwind.config.js나 @theme 블록의 값과 tokens.css가 정확히 일치하는지** 확인하는 것이었다.

예를 들어, 한 프로젝트의 `tailwind.config.js`에 이미 정의된 그림자 값:

```js
// tailwind.config.js
boxShadow: {
  sm: '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06)',
}
```

이 값을 tokens.css에 그대로 옮겼다:

```css
:root {
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
}
```

만약 tokens.css에 임의로 다른 값을 넣으면, 기존 컴포넌트에서 쓰는 `shadow-md` Tailwind 클래스와 새 컴포넌트에서 쓰는 `var(--shadow-md)`가 다른 그림자를 표시하게 된다. 이는 결코 허용할 수 없는 불일치다.

### 보일러플레이트 프로젝트의 특수 처리

보일러플레이트로 쓰는 프로젝트에는 커스터마이징 포인트에 주석을 달았다.

```css
:root {
  /* ===== Customize: Brand Color ===== */
  /* 새 프로젝트 시작 시 아래 Primary 색상을 변경하세요 */
  /* 색상 팔레트 생성: https://uicolors.app/create */
  --color-primary: #3182F6;
  --color-primary-50: #EBF4FF;
  --color-primary-100: #DBEAFE;
  --color-primary-500: #3182F6;
  --color-primary-600: #2563EB;
  --color-primary-900: #1E3A8A;

  /* ===== Customize: Font Family ===== */
  /* 한글 프로젝트: Pretendard, 영문 전용: Inter */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;

  /* ===== Do NOT Customize Below ===== */
  /* 아래 값은 모든 프로젝트 공통 — 변경하지 마세요 */
  --spacing-sm: 8px;
  /* ... */
}
```

이렇게 주석을 구분해두면 새 프로젝트를 시작할 때 무엇을 바꿔야 하고 무엇을 그대로 두어야 하는지 명확해진다.

---

## 5. 적용 후 달라진 점

### Before: 하드코딩된 값

```svelte
<button class="bg-[#3182F6] hover:bg-[#2876E5] rounded-[12px]
  shadow-[0_4px_6px_rgba(0,0,0,0.04)] text-[14px] font-semibold">
  저장
</button>
```

이런 코드는 여러 문제를 안고 있다. `#3182F6`이 무엇을 의미하는지 코드만 보고 알 수 없다. 이 색상을 다른 색상으로 바꾸려면 전체 코드베이스에서 hex값을 찾아 모두 교체해야 한다. 다크 모드를 추가하려면 모든 하드코딩 값에 조건부 로직을 추가해야 한다.

### After: 토큰 참조

```svelte
<button class="bg-primary hover:bg-primary-600 rounded-xl shadow-md text-label">
  저장
</button>

<!-- 또는 Svelte style 블록에서 복잡한 케이스 처리 -->
<style>
  .custom-card {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    transition: var(--transition-normal);
    min-height: var(--touch-target-min);
  }

  .custom-card:hover {
    box-shadow: var(--shadow-lg);
  }
</style>
```

토큰 참조 방식으로 전환하면 의미가 명확해진다. `bg-primary`는 "이 버튼이 Primary 액션이다"라는 의미를 담고, `var(--color-border)`는 "표준 테두리 색상"임을 즉시 알 수 있다. 브랜드 색상을 바꾸려면 `tokens.css`의 `--color-primary` 값 하나만 수정하면 된다.

### 최종 현황

```
Before                          After
─────────────────────          ─────────────────────
완전 적용: 1개                  완전 적용: 1개 (변경 없음)
부분 적용: 2개                  체계 완비: 4개 (+2 기존 부분 → 토큰 추가)
미적용:   5개                  토큰 적용: 3개 (+3 신규)
                               미완성:   1개 (프론트엔드 미구축)
```

미완성으로 남은 프로젝트 H는 Rails 서버 사이드 렌더링만 있고 Inertia.js가 아직 연동되지 않은 상태다. 프론트엔드 구조 자체를 먼저 잡아야 하므로 디자인 토큰 적용은 그 이후로 미뤘다.

---

## 6. 삽질 포인트와 교훈

### Tailwind CSS 3 vs 4 혼재

같은 스택인데도 프로젝트 생성 시점에 따라 Tailwind 3(`tailwind.config.js`)과 4(`@theme` 블록)가 섞여 있었다. tokens.css는 둘 다에서 작동하므로 통합 계층 역할을 한다.

Tailwind 3 프로젝트에서 4로 업그레이드할 때도 tokens.css가 완충 역할을 한다. 먼저 tokens.css를 기반으로 컴포넌트를 리팩토링해두면, 이후 Tailwind 설정 파일 형식이 바뀌어도 CSS Custom Properties 부분은 그대로 유지된다.

### 다크 모드 토큰 설계의 함정

처음에는 `--color-dark-bg-primary`처럼 다크 모드 전용 변수를 별도로 만들려 했다. 하지만 이러면 컴포넌트에서 매번 분기해야 한다.

```css
/* ❌ 안 좋은 방법 */
.card { background: var(--color-bg-primary); }
.dark .card { background: var(--color-dark-bg-primary); }
```

대신 **같은 변수명을 .dark 셀렉터에서 오버라이드**하면 컴포넌트 코드가 깔끔해진다.

```css
/* ✅ 좋은 방법 */
:root { --color-bg-primary: #FFFFFF; }
:root.dark { --color-bg-primary: #0D0D0D; }

.card { background: var(--color-bg-primary); }  /* 다크 모드 자동 대응 */
```

이 패턴의 핵심은 **CSS Custom Properties의 상속(cascading) 특성**을 활용한다는 점이다. `:root.dark`에서 정의된 변수는 하위 모든 요소에서 오버라이드된 값을 사용한다. 컴포넌트는 변수명만 참조하면 되고, 어떤 값이 실제로 적용될지는 상위 컨텍스트가 결정한다.

### 8px 그리드의 예외

대부분의 간격은 8px 배수(8, 16, 24, 32...)로 충분하지만, 4px(`--spacing-xs`)과 12px(`--spacing-smd`)은 실무에서 반드시 필요하다. 특히 12px은 아이콘과 텍스트 사이, 뱃지 내부 패딩 등에 자주 쓰인다.

처음에는 "순수 8px 그리드"를 고집했는데, 아이콘(16px)과 텍스트 사이에 8px 간격을 두면 너무 넓고 4px는 너무 좁았다. 결국 12px 예외를 인정하고 `--spacing-smd`라는 이름으로 토큰화했다. 완벽한 수학적 그리드보다 실용성이 우선이다.

### Touch Target 44px는 필수

모바일 웹뷰를 지원하는 프로젝트에서 `--touch-target-min: 44px`을 토큰으로 정의해두면, 버튼 최소 높이를 일관되게 유지할 수 있다. iOS HIG 기준이며, Material Design은 48px을 권장한다.

특히 Rails + Inertia.js 프로젝트 중 일부는 Hotwire Native나 Flutter 웹뷰로도 접근한다. 모바일 네이티브 앱에서 웹뷰를 사용할 때 터치 타겟이 작으면 사용자 경험이 급격히 나빠진다. 토큰으로 정의해두면 모든 버튼과 탭에서 일관되게 적용할 수 있다.

### CSS Custom Properties와 Svelte의 reactivity

Svelte 5에서 `$state`로 관리하는 동적 값을 CSS Custom Properties로 넘길 때는 인라인 스타일로 처리해야 한다:

```svelte
<script>
  let primaryColor = $state('#3182F6');
</script>

<!-- 동적 토큰 오버라이드 -->
<div style="--color-primary: {primaryColor};">
  <button class="bg-primary">동적 색상 버튼</button>
</div>
```

이 패턴은 화이트라벨 서비스나 사용자 테마 커스터마이징 기능을 구현할 때 유용하다.

---

## 마무리

디자인 토큰은 "있으면 좋은 것"이 아니라 **프로젝트가 2개 이상이면 필수**다. 특히 같은 기술 스택을 공유하는 프로젝트라면, 토큰 구조를 통일해두면 새 프로젝트 시작 시 보일러플레이트에서 색상만 바꾸면 된다.

핵심 정리:

1. **tokens.css를 Source of Truth로** — Tailwind 설정과 분리하되 값은 동기화
2. **다크 모드는 같은 변수명 오버라이드** — 컴포넌트 코드 단순화
3. **8개 섹션 표준화** — Colors, Typography, Spacing, Radius, Shadows, Z-Index, Transitions, Touch Target
4. **브랜드 색상만 프로젝트별 분리** — 나머지 구조는 동일하게 유지

---

## Key Takeaways

- **디자인 토큰 감사는 정기적으로 해야 한다.** 프로젝트를 계속 추가하다 보면 어느 순간 통제 불능 상태가 된다. 초기에 기준을 잡지 않으면 나중에 리팩토링 비용이 기하급수적으로 늘어난다.
- **tokens.css 하나로 Tailwind 3/4 모두 지원 가능하다.** 같은 팀 내에서 Tailwind 버전이 혼재할 때, CSS Custom Properties 계층을 기반으로 하면 버전 차이를 흡수할 수 있다.
- **컴포넌트를 먼저 만들면 토큰 체계 도입이 어려워진다.** 하드코딩된 컴포넌트가 쌓일수록 리팩토링 비용이 커진다. 새 프로젝트는 무조건 토큰부터 잡고 시작하자.
- **보일러플레이트에 주석으로 커스터마이징 포인트를 명시하면** 새 팀원이나 미래의 자신이 빠르게 온보딩할 수 있다.
- **CSS Custom Properties는 JavaScript에서도 읽힌다.** Canvas, WebGL, 애니메이션 라이브러리 등 CSS 밖에서도 동일한 토큰값을 참조할 수 있어 일관성이 유지된다.
