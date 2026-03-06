---
title: "레퍼런스 디자인을 분석해서 컴포넌트 시스템 확장하기 — Svelte 5 + Storybook 10"
date: 2026-03-06
draft: false
tags: ["Svelte 5", "Storybook", "디자인 시스템", "CSS Custom Properties", "컴포넌트", "레퍼런스 분석", "Vite 7"]
description: "레퍼런스 앱의 시각적 구조를 분석하고, 기존 23개 컴포넌트에 9개를 추가하면서 디자인 토큰과 템플릿 체계를 잡은 과정. 구성만 따라가되 스타일은 기존 다크 테마를 유지하는 전략."
---

디자인 시스템이 어느 정도 잡힌 프로젝트에서 레퍼런스 앱을 받았을 때, "완전히 똑같이"가 아니라 **"구성(composition)만 동일하게"** 적용하고 싶었다. 이 글은 그 과정을 정리한 기록이다.

---

## 배경

기존 프로젝트에는 이미 다음이 갖춰져 있었다:
- **23개 공유 컴포넌트** (8개 카테고리: layout, navigation, input, overlay, card, data-display, social, feedback)
- **CSS Custom Properties 기반 디자인 토큰** (colors, typography, spacing, radius, shadows, glassmorphism)
- **Storybook 10 + Svelte 5** 환경 (51개 story variants)
- **다크 테마 글래스모피즘** 디자인

여기에 디자이너가 참조용으로 보내준 레퍼런스 앱 이미지를 분석해서, **기존 디자인을 깨지 않으면서 구조적 패턴만 흡수**하는 작업을 진행했다.

---

## 1단계: 레퍼런스 비주얼 해킹

레퍼런스 앱의 화면 구조를 ASCII로 분해했다.

```
+-------------------+-------------------------+
|  LEFT PANEL       |  RIGHT PANEL            |
|  (Input/Creation) |  (Result/Visualization) |
|                   |                         |
|  [AI Chat Input]  |  [Trip Header]          |
|  [Tag Chips]      |  [MAP + Route Lines]    |
|  [Budget Slider]  |  [Route Highlights]     |
|  [Duration Btns]  |  [Day-by-Day Accordion] |
|  [CTA Button]     |                         |
+-------------------+-------------------------+
|  Bottom Tab: [Home] [AI] [Map] [Profile]    |
+--------------------------------------------- +
```

### 시각적 차이 분석표

| 요소 | 레퍼런스 | 기존 프로젝트 |
|------|---------|-------------|
| 모드 | Light (white bg) | Dark (glassmorphism) |
| 액센트 | Green (#4ADE80) | Teal (#20B2AA) |
| 카드 | 흰색 + shadow | 반투명 glass + border |
| Radius | 16-24px | 12-16px |
| 아이콘 | Filled | Outline |
| 레이아웃 | 2-column split | 단일 컬럼 + 탭 |
| 일정 보기 | Day accordion | 날짜 탭 + 리스트 |
| 태그 입력 | Pill chip 선택 | 직접 텍스트 입력 |

### 가져갈 구조 패턴 6가지

1. **Input -> Result 2-Panel** (좌: 입력, 우: 시각화)
2. **Tag Chip System** (카테고리/관심사 시각적 선택)
3. **Budget Range Slider** (수치 입력 대신 슬라이더)
4. **Day-by-Day Accordion** (접기/펼치기 일정)
5. **Route Map Visualization** (점선 루트 + 번호 마커)
6. **Section Header** (제목 + 부제 + 액션 버튼 패턴)

핵심 원칙: **구조는 레퍼런스, 스타일은 기존 다크 테마**.

---

## 2단계: 필요한 신규 컴포넌트 도출

레퍼런스 구조를 기존 컴포넌트에 매핑하면, 커버되지 않는 부분이 명확하게 보인다.

| 레퍼런스 요소 | 기존 컴포넌트 | 결론 |
|-------------|-------------|------|
| Tag Chips | -- | **신규**: Chip |
| Budget Slider | -- | **신규**: RangeSlider |
| Duration [7][10][14] | -- | **신규**: SegmentedControl |
| Day Accordion | -- | **신규**: Accordion |
| Route Highlight Card | -- | **신규**: RouteHighlight |
| Numbered Map Marker | -- | **신규**: MapMarker |
| Section Title | -- | **신규**: Section |
| 2-Column Panel | -- | **신규**: SplitPanel |
| Schedule Timeline Item | (페이지 내장) | **추출**: ScheduleItem |
| CTA Button | Button.svelte | 기존 사용 |
| Modal | Modal.svelte | 기존 사용 |
| Budget Bar | BudgetProgress.svelte | 기존 사용 |

결과: **기존 10개 재활용, 9개 신규 생성**.

---

## 3단계: 디자인 토큰 확장

기존 `tokens.css`에 신규 컴포넌트를 위한 토큰 6종을 추가했다.

```css
:root {
  /* ...기존 토큰 유지... */

  /* Chip / Tag System */
  --chip-height:          32px;
  --chip-padding-x:       12px;
  --chip-radius:          9999px;    /* pill 형태 */
  --chip-bg:              rgba(32, 178, 170, 0.10);
  --chip-bg-selected:     #20B2AA;
  --chip-text:            rgba(255, 255, 255, 0.55);
  --chip-text-selected:   #FFFFFF;

  /* Accordion System */
  --accordion-header-height: 48px;
  --accordion-bg-open:    rgba(255, 255, 255, 0.03);

  /* Slider / Range Input */
  --slider-track-height:  4px;
  --slider-track-fill:    #20B2AA;
  --slider-thumb-size:    20px;

  /* Split Panel */
  --panel-left-width:     400px;
  --panel-left-max:       40%;

  /* Section Header */
  --section-title-size:   17px;
  --section-title-weight: 600;
  --section-spacing:      32px;
}
```

토큰을 변수로 분리하면 나중에 라이트 모드 전환이나 테마 변경 시 컴포넌트 코드를 수정하지 않아도 된다.

---

## 4단계: 병렬 컴포넌트 개발

9개 컴포넌트를 6개 에이전트로 병렬 개발했다. 각 컴포넌트의 핵심 설계를 간단히 정리한다.

### Chip (input/)

선택 가능한 태그/필터 칩. `aria-pressed`로 접근성 처리.

```svelte
<button class="chip" class:selected {onclick} aria-pressed={selected}>
  {label}
</button>

<style>
  .chip {
    height: var(--chip-height);
    border-radius: var(--chip-radius);
    background: var(--chip-bg);
    color: var(--chip-text);
    transition: all 200ms ease;
    min-height: 44px; /* iOS touch target */
  }
  .chip.selected {
    background: var(--chip-bg-selected);
    color: var(--chip-text-selected);
    box-shadow: 0 0 12px rgba(32, 178, 170, 0.25);
  }
</style>
```

### Accordion (data-display/)

Day-by-Day 일정 표시용. chevron 회전 애니메이션, badge 지원.

```svelte
<div class="accordion" class:open={isOpen}>
  <button class="accordion-header" onclick={toggle}>
    <span class="accordion-chevron"><!-- rotate 90deg when open --></span>
    <span class="accordion-title">{title}</span>
    {#if badge}<span class="accordion-badge">{badge}</span>{/if}
  </button>
  {#if isOpen}
    <div class="accordion-content">{@render children?.()}</div>
  {/if}
</div>
```

### SplitPanel (layout/)

데스크톱: 좌우 분할. 모바일(768px 이하): 세로 스택.

```svelte
<div class="split-panel" style="--sp-left-width: {leftWidth};">
  <aside class="split-left">{@render left?.()}</aside>
  <main class="split-right">{@render right?.()}</main>
</div>

<style>
  .split-panel { display: flex; gap: var(--sp-gap); }
  .split-left { width: var(--sp-left-width); max-width: var(--sp-left-max); }
  .split-right { flex: 1; }
  @media (max-width: 768px) {
    .split-panel { flex-direction: column; }
    .split-left { width: 100%; max-width: 100%; }
  }
</style>
```

### RangeSlider (input/)

예산 슬라이더. CSS gradient으로 fill 트랙 표현.

```css
.range-input {
  background: linear-gradient(to right,
    var(--slider-track-fill) 0%, var(--slider-track-fill) var(--fill),
    var(--slider-track-bg) var(--fill), var(--slider-track-bg) 100%
  );
}
```

### SegmentedControl (input/)

기간 선택 `[3일][5일][7일][10일]`. `role="radiogroup"` + `aria-checked`.

### ScheduleItem (card/)

타임라인 도트 + 시간 + 카테고리 배지 + 위치. Schedule 페이지에서 추출한 패턴.

### Section, RouteHighlight, MapMarker

각각 섹션 래퍼, 장소 하이라이트 카드, 번호 원형 마커.

---

## 5단계: 페이지 템플릿 체계

9개 컴포넌트를 조합해서 5개 재사용 가능한 페이지 템플릿을 정의했다.

| 템플릿 | 구조 | 적용 페이지 |
|--------|------|-----------|
| **SplitPanelTemplate** | 좌(Input) + 우(Result) | AI 추천, 지도 플래너 |
| **DayTimelineTemplate** | DateChips + Day Accordion | 일정 관리 |
| **ListWithFilterTemplate** | Chip 필터 + 리스트 | 지출, 쇼핑, 체크리스트 |
| **CardGridTemplate** | 헤더 + 카드 그리드 | 여행 목록, 앨범 |
| **FormSectionTemplate** | Section + 입력 컴포넌트 | 여행 생성, 프로필 편집 |

---

## 삽질 기록

### Storybook 10 + Vite 7 호환성

Storybook 8.x는 Vite 7과 호환되지 않는다. peer dependency가 `vite@"^4 || ^5 || ^6"`으로 걸려 있어서 Storybook 10.2.15로 올려야 했다.

```
# 이렇게 하면 안 됨
npm i @storybook/svelte-vite@8.6.14  # vite 7 미지원

# 이렇게 해야 함
npm i storybook@10.2.15 @storybook/svelte-vite@10.2.15
```

### @storybook/blocks vs @storybook/addon-docs

Storybook 10에서는 `@storybook/blocks`가 별도 패키지가 아니다. MDX에서 Meta import 경로를 바꿔야 한다.

```js
// 8.x (안 됨)
import { Meta } from '@storybook/blocks';

// 10.x (됨)
import { Meta } from '@storybook/addon-docs/blocks';
```

그리고 `main.js`의 addons에 `@storybook/addon-docs`를 명시해야 MDX 파일이 빌드된다.

### Svelte 5 runes 마이그레이션

기존 Svelte 4 문법(`export let`)이 섞여 있으면 Storybook에서 prop 인식이 안 된다. 26개 페이지를 `$props()` 문법으로 일괄 변환했다.

```svelte
// Before (Svelte 4)
export let trip;
export let user = null;

// After (Svelte 5)
let { trip, user = null }: { trip: Trip; user?: User | null } = $props();
```

### formatCurrency 13개 파일 중복

13개 파일에서 동일한 함수가 인라인으로 정의되어 있었다. 공용 유틸로 추출하되, 한 파일만 다른 구현(100으로 나누지 않음)이어서 그건 로컬 유지.

### Layout.svelte 428줄 모놀리스

428줄짜리 Layout을 4개 컴포넌트로 분리: TopNavBar(152), PillBottomNav(79), UserMenu(74), SearchModal(119).

---

## 최종 결과

| 지표 | Before | After |
|------|--------|-------|
| 공유 컴포넌트 | 23개 | **32개** (+9) |
| 디자인 토큰 종류 | 9종 | **15종** (+6) |
| Storybook variants | 51개 | **~80개** |
| 페이지 템플릿 | 0개 | **5개** |
| 페르소나 워크플로우 | 미정의 | **10개** |

핵심 교훈: 레퍼런스를 "따라 만드는" 것이 아니라 **구조만 추출해서 기존 시스템에 녹이는 접근**이 훨씬 실용적이다. 색상, 폰트, 모드(dark/light)는 기존 토큰을 그대로 쓰고, 레이아웃 패턴(split panel, accordion, chip filter)만 가져오면 일관성을 유지하면서 UX를 확장할 수 있다.
