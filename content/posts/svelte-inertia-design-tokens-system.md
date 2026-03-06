---
title: "Svelte 5 + Inertia.js 프로젝트 8개에 디자인 토큰 체계 잡기"
date: 2026-03-06
draft: false
tags: ["Svelte 5", "Inertia.js", "Design Tokens", "Tailwind CSS", "디자인 시스템", "CSS Custom Properties"]
description: "Rails + Inertia.js + Svelte 5 기반 프로젝트 8개를 운영하면서 디자인 시스템 적용 현황을 감사하고, 미적용 프로젝트에 CSS Custom Properties 기반 디자인 토큰을 일괄 구축한 과정을 정리한다."
---

Rails + Inertia.js + Svelte 5 기반으로 여러 프로젝트를 운영하다 보면 하나의 고질적 문제가 생긴다. **각 프로젝트마다 색상, 타이포그래피, 간격 등의 디자인 기준이 제각각**이라는 점이다. 어떤 프로젝트는 `tailwind.config.js`에 체계적으로 정리되어 있고, 어떤 프로젝트는 `bg-[#3182F6]` 같은 하드코딩이 넘쳐난다.

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

### tokens.css 구조 (8개 섹션)

```css
:root {
  /* 1. Colors — Primary (50-900 스케일) */
  --color-primary-500: #XXXXXX;

  /* 2. Colors — Semantic (success, warning, error, info) */
  --color-success: #XXXXXX;

  /* 3. Colors — Gray Scale */
  --color-gray-50: #XXXXXX;

  /* 4. Colors — Background, Surface, Border, Text */
  --color-bg-primary: #XXXXXX;
  --color-text-primary: rgba(255, 255, 255, 0.92);

  /* 5. Typography */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;
  --font-size-base: 15px;

  /* 6. Spacing (8px 그리드) */
  --spacing-sm: 8px;
  --spacing-md: 16px;

  /* 7. Border Radius, Shadows, Z-Index */
  --radius-lg: 12px;
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.50);

  /* 8. Transitions, Touch Target */
  --transition-normal: 200ms ease;
  --touch-target-min: 44px;
}
```

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

**Tailwind CSS 3** 프로젝트 (`tailwind.config.js` 사용)에서는 tokens.css와 config 파일의 값을 1:1로 일치시킨다.

**Tailwind CSS 4** 프로젝트 (`@theme` 사용)에서는 tokens.css를 `application.css` 최상단에서 import하고, `@theme`에서 동일한 값을 등록한다.

```css
/* application.css */
@import "../css/tokens.css";    /* ← 먼저 로드 */
@import "tailwindcss";

@theme {
  --color-primary: #3182F6;     /* tokens.css와 동일 값 */
}
```

### 다크 모드 토큰 전략

다크 모드를 지원하는 프로젝트에서는 `:root`에 라이트 모드 기본값을, `.dark` 셀렉터에서 오버라이드한다.

```css
:root {
  --color-bg-primary: #FFFFFF;
  --color-text-primary: #191F28;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04);
}

:root.dark {
  --color-bg-primary: #0D0D0D;
  --color-text-primary: #F5F5F5;
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.25);
}
```

이렇게 하면 Svelte 컴포넌트에서 다크 모드를 신경 쓸 필요 없이 `var(--color-bg-primary)`만 쓰면 된다.

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

---

## 4. 일괄 적용 과정

### 병렬 실행

5개 프로젝트에 동시에 토큰 파일을 생성했다. 각 프로젝트마다:

1. `app/frontend/css/` 디렉토리 생성
2. 프로젝트의 기존 색상/설정 분석 (application.css, tailwind.config.js)
3. 8개 섹션으로 구성된 `tokens.css` 생성
4. 기존 CSS 파일에 `@import` 추가

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

### 보일러플레이트 프로젝트의 특수 처리

보일러플레이트로 쓰는 프로젝트에는 커스터마이징 포인트에 주석을 달았다.

```css
:root {
  /* ===== Customize: Brand Color ===== */
  /* 프로젝트에 맞게 Primary 색상 변경 */
  --color-primary: #3182F6;
  --color-primary-50: #EBF4FF;
  /* ... */

  /* ===== Customize: Font Family ===== */
  --font-family-primary: 'Pretendard', system-ui, sans-serif;
}
```

---

## 5. 적용 후 달라진 점

### Before: 하드코딩된 값

```svelte
<button class="bg-[#3182F6] hover:bg-[#2876E5] rounded-[12px]
  shadow-[0_4px_6px_rgba(0,0,0,0.04)] text-[14px] font-semibold">
  저장
</button>
```

### After: 토큰 참조

```svelte
<button class="bg-primary hover:bg-primary-600 rounded-xl shadow-md text-label">
  저장
</button>

<!-- 또는 Svelte style 블록에서 -->
<style>
  .custom-card {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    transition: var(--transition-normal);
  }
</style>
```

### 최종 현황

```
Before                          After
─────────────────────          ─────────────────────
완전 적용: 1개                  완전 적용: 1개 (변경 없음)
부분 적용: 2개                  체계 완비: 4개 (+2 기존 부분 → 토큰 추가)
미적용:   5개                  토큰 적용: 3개 (+3 신규)
                               미완성:   1개 (프론트엔드 미구축)
```

---

## 6. 삽질 포인트와 교훈

### Tailwind CSS 3 vs 4 혼재

같은 스택인데도 프로젝트 생성 시점에 따라 Tailwind 3(`tailwind.config.js`)과 4(`@theme` 블록)가 섞여 있었다. tokens.css는 둘 다에서 작동하므로 통합 계층 역할을 한다.

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

### 8px 그리드의 예외

대부분의 간격은 8px 배수(8, 16, 24, 32...)로 충분하지만, 4px(`--spacing-xs`)과 12px(`--spacing-smd`)은 실무에서 반드시 필요하다. 특히 12px은 아이콘과 텍스트 사이, 뱃지 내부 패딩 등에 자주 쓰인다.

### Touch Target 44px는 필수

모바일 웹뷰를 지원하는 프로젝트에서 `--touch-target-min: 44px`을 토큰으로 정의해두면, 버튼 최소 높이를 일관되게 유지할 수 있다. iOS HIG 기준이며, Material Design은 48px을 권장한다.

---

## 마무리

디자인 토큰은 "있으면 좋은 것"이 아니라 **프로젝트가 2개 이상이면 필수**다. 특히 같은 기술 스택을 공유하는 프로젝트라면, 토큰 구조를 통일해두면 새 프로젝트 시작 시 보일러플레이트에서 색상만 바꾸면 된다.

핵심 정리:

1. **tokens.css를 Source of Truth로** — Tailwind 설정과 분리하되 값은 동기화
2. **다크 모드는 같은 변수명 오버라이드** — 컴포넌트 코드 단순화
3. **8개 섹션 표준화** — Colors, Typography, Spacing, Radius, Shadows, Z-Index, Transitions, Touch Target
4. **브랜드 색상만 프로젝트별 분리** — 나머지 구조는 동일하게 유지
