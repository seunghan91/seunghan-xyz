---
title: "레퍼런스 디자인을 분석해서 컴포넌트 시스템 확장하기 — Svelte 5 + Storybook 10"
date: 2026-02-27
draft: false
tags: ["Svelte 5", "Storybook", "디자인 시스템", "CSS Custom Properties", "컴포넌트", "레퍼런스 분석", "Vite 7"]
description: "레퍼런스 앱의 시각적 구조를 분석하고, 기존 23개 컴포넌트에 9개를 추가하면서 디자인 토큰과 템플릿 체계를 잡은 과정. 구성만 따라가되 스타일은 기존 다크 테마를 유지하는 전략."
cover:
  image: "/images/og/storybook-reference-design-component-system.png"
  alt: "Storybook Reference Design Component System"
  hidden: true
---

디자인 시스템이 어느 정도 잡힌 프로젝트에서 레퍼런스 앱을 받았을 때, "완전히 똑같이"가 아니라 **"구성(composition)만 동일하게"** 적용하고 싶었다. 색상·폰트·모드를 통째로 바꾸는 건 기존 작업을 날리는 일이고, 그렇다고 레퍼런스를 무시하면 디자이너와의 싱크가 깨진다. 이 글은 그 균형점을 찾는 과정을 정리한 기록이다.

---

## 배경

기존 프로젝트에는 이미 다음이 갖춰져 있었다:

- **23개 공유 컴포넌트** (8개 카테고리: layout, navigation, input, overlay, card, data-display, social, feedback)
- **CSS Custom Properties 기반 디자인 토큰** (colors, typography, spacing, radius, shadows, glassmorphism)
- **Storybook 10 + Svelte 5** 환경 (51개 story variants)
- **다크 테마 글래스모피즘** 디자인

여기에 디자이너가 참조용으로 보내준 레퍼런스 앱 이미지를 분석해서, **기존 디자인을 깨지 않으면서 구조적 패턴만 흡수**하는 작업을 진행했다.

기존 시스템이 이미 견고하게 구성되어 있었기 때문에, 처음부터 다시 만드는 방식은 처음부터 배제했다. 대신 "레퍼런스에서 무엇을 가져올 수 있는가"라는 질문에서 출발했다.

---

## 1단계: 레퍼런스 비주얼 해킹

레퍼런스 앱의 화면 구조를 분석하는 첫 번째 작업은 ASCII로 레이아웃을 분해하는 것이다. 이미지를 그대로 코드로 옮기려 하면 세부 스타일에 눈이 가기 쉽지만, ASCII 다이어그램으로 추상화하면 **레이아웃의 골격**만 남는다.

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

이 다이어그램 하나로 "이 화면에 필요한 컴포넌트의 종류와 배치"가 명확해진다. 좌측은 사용자 입력 영역, 우측은 결과·시각화 영역이라는 2-Panel 구조가 핵심이다.

### 시각적 차이 분석표

레퍼런스와 기존 프로젝트의 스타일 차이를 정리했다. 이 표의 목적은 "무엇을 가져갈지"가 아니라 **"무엇을 가져가지 않을지"를 명확히 하는 것**이다.

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

위 표에서 모드(light/dark), 색상, 아이콘 스타일은 **가져가지 않는** 항목이다. 반면 레이아웃 구조, 일정 표시 방식, 태그 입력 방식은 **가져갈** 항목이다.

### 가져갈 구조 패턴 6가지

스타일 차이 분석을 마치면, 실제로 흡수할 패턴만 추려낼 수 있다.

1. **Input → Result 2-Panel** (좌: 입력, 우: 시각화)
2. **Tag Chip System** (카테고리/관심사 시각적 선택)
3. **Budget Range Slider** (수치 입력 대신 슬라이더로 예산 범위 설정)
4. **Day-by-Day Accordion** (접기/펼치기 일정 — 날짜별로 펼쳐 보는 패턴)
5. **Route Map Visualization** (점선 루트 + 번호 마커로 이동 경로 표시)
6. **Section Header** (제목 + 부제 + 액션 버튼 패턴 — 섹션 단위 레이아웃 단위)

핵심 원칙: **구조는 레퍼런스, 스타일은 기존 다크 테마**.

---

## 2단계: 필요한 신규 컴포넌트 도출

구조 패턴을 확정한 뒤, 기존 컴포넌트 목록과 매핑하면 "커버되지 않는 공백"이 보인다. 이 매핑 작업이 가장 중요하다. **"새로 만들 것"과 "기존 것을 재사용할 것"을 구분**해야 중복 개발을 막을 수 있기 때문이다.

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

ScheduleItem은 기존에 페이지 안에 인라인으로 작성되어 있던 패턴을 컴포넌트로 추출한 케이스다. 이처럼 "신규 생성"이 아니라 "추출"로 분류하는 것이 중요하다. 추출은 인터페이스를 확정하는 작업이지, 로직을 새로 만드는 작업이 아니다.

---

## 3단계: 디자인 토큰 확장

신규 컴포넌트를 구현하기 전에 토큰 먼저 확장했다. 토큰 없이 컴포넌트를 만들면 하드코딩된 값이 컴포넌트마다 흩어지게 된다. 나중에 테마를 바꾸거나 라이트 모드를 추가할 때 컴포넌트를 하나씩 수정해야 한다.

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

토큰을 변수로 분리하면 나중에 라이트 모드 전환이나 테마 변경 시 컴포넌트 코드를 수정하지 않아도 된다. 예를 들어, `data-theme="light"` 속성을 루트에 붙이고 토큰 값만 오버라이드하면 모든 컴포넌트가 자동으로 라이트 모드 스타일을 따른다.

---

## 4단계: 병렬 컴포넌트 개발

9개 컴포넌트를 6개 에이전트로 병렬 개발했다. 각 컴포넌트의 핵심 설계를 간단히 정리한다.

### Chip (input/)

선택 가능한 태그·필터 칩이다. 단순히 보이지만, 접근성을 제대로 처리하는 게 핵심이다. toggle 버튼이므로 `aria-pressed`를 사용한다. `role="checkbox"`가 아닌 `button`으로 구현하는 이유는, 체크박스는 폼 데이터 제출을 위한 것이고 Chip은 UI 필터링을 위한 것이기 때문이다.

```svelte
<button class="chip" class:selected {onclick} aria-pressed={selected}>
  {label}
</button>

<style>
  .chip {
    height: var(--chip-height);
    padding: 0 var(--chip-padding-x);
    border-radius: var(--chip-radius);
    background: var(--chip-bg);
    color: var(--chip-text);
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 200ms ease;
    min-height: 44px; /* iOS touch target */
  }
  .chip.selected {
    background: var(--chip-bg-selected);
    color: var(--chip-text-selected);
    box-shadow: 0 0 12px rgba(32, 178, 170, 0.25);
  }
  .chip:focus-visible {
    outline: 2px solid var(--chip-bg-selected);
    outline-offset: 2px;
  }
</style>
```

`min-height: 44px`는 iOS Human Interface Guidelines의 터치 타겟 최소 크기다. 시각적으로 작은 Chip이라도 터치 영역은 충분히 확보해야 한다.

### Accordion (data-display/)

Day-by-Day 일정 표시용. chevron 회전 애니메이션, badge 지원. Svelte 5의 `{@render children?.()}` 패턴으로 슬롯을 대체했다.

```svelte
<script lang="ts">
  let { title, badge, children } = $props<{
    title: string;
    badge?: string;
    children?: Snippet;
  }>();
  let isOpen = $state(false);
  const toggle = () => (isOpen = !isOpen);
</script>

<div class="accordion" class:open={isOpen}>
  <button class="accordion-header" onclick={toggle} aria-expanded={isOpen}>
    <span class="accordion-chevron" style="transform: rotate({isOpen ? 90 : 0}deg)">›</span>
    <span class="accordion-title">{title}</span>
    {#if badge}<span class="accordion-badge">{badge}</span>{/if}
  </button>
  {#if isOpen}
    <div class="accordion-content">{@render children?.()}</div>
  {/if}
</div>
```

`aria-expanded`를 사용해 스크린 리더가 열림/닫힘 상태를 인식할 수 있게 했다. chevron 회전은 CSS transition 대신 인라인 style로 처리해 Svelte 5의 반응성을 직접 활용했다.

### SplitPanel (layout/)

데스크톱: 좌우 분할. 모바일(768px 이하): 세로 스택. `leftWidth`를 prop으로 받아 CSS 변수로 주입하면, 부모에서 너비를 유연하게 제어할 수 있다.

```svelte
<div class="split-panel" style="--sp-left-width: {leftWidth};">
  <aside class="split-left">{@render left?.()}</aside>
  <main class="split-right">{@render right?.()}</main>
</div>

<style>
  .split-panel {
    display: flex;
    gap: var(--sp-gap, 24px);
    height: 100%;
  }
  .split-left {
    width: var(--sp-left-width, var(--panel-left-width));
    max-width: var(--sp-left-max, var(--panel-left-max));
    flex-shrink: 0;
    overflow-y: auto;
  }
  .split-right {
    flex: 1;
    min-width: 0; /* flex child 오버플로우 방지 */
    overflow-y: auto;
  }
  @media (max-width: 768px) {
    .split-panel { flex-direction: column; }
    .split-left { width: 100%; max-width: 100%; }
  }
</style>
```

`min-width: 0`은 flex child에서 자주 빠뜨리는 속성이다. 이게 없으면 내용이 길어질 때 오른쪽 패널이 부모 밖으로 넘친다.

### RangeSlider (input/)

예산 슬라이더. `<input type="range">`의 기본 스타일을 리셋하고, CSS gradient로 fill 트랙을 표현한다. `--fill` 변수는 현재 값에 따라 JavaScript에서 계산해 인라인으로 주입한다.

```css
.range-input {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: var(--slider-track-height);
  background: linear-gradient(to right,
    var(--slider-track-fill) 0%,
    var(--slider-track-fill) var(--fill),
    var(--slider-track-bg) var(--fill),
    var(--slider-track-bg) 100%
  );
  border-radius: 9999px;
  outline: none;
}

.range-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: var(--slider-thumb-size);
  height: var(--slider-thumb-size);
  border-radius: 50%;
  background: var(--slider-track-fill);
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(32, 178, 170, 0.4);
}
```

### SegmentedControl (input/)

기간 선택 `[3일][5일][7일][10일]`처럼 단일 선택 버튼 그룹이다. `role="radiogroup"` + 각 버튼에 `aria-checked`를 붙여 라디오 버튼의 접근성 의미를 유지했다. 실제 `<input type="radio">`를 쓰지 않는 이유는 스타일 제어의 자유도 때문이다.

```svelte
<div role="radiogroup" aria-label={label} class="segmented-control">
  {#each options as option}
    <button
      role="radio"
      aria-checked={value === option.value}
      class:active={value === option.value}
      onclick={() => onchange(option.value)}
    >
      {option.label}
    </button>
  {/each}
</div>
```

### ScheduleItem (card/)

Schedule 페이지 안에 인라인으로 반복되던 패턴을 컴포넌트로 추출했다. 타임라인 도트 + 시간 + 카테고리 배지 + 위치 정보로 구성된다. 추출 전에는 동일한 마크업이 페이지 곳곳에 흩어져 있어 스타일 수정 시 모든 위치를 찾아야 했다.

### Section, RouteHighlight, MapMarker

- **Section**: 제목 + 부제 + 오른쪽 액션 버튼 슬롯. 페이지 내 섹션 구분의 표준 단위.
- **RouteHighlight**: 장소 이름 + 짧은 설명 + 이미지 썸네일. 지도 우측 패널에서 경유지를 나열할 때 사용.
- **MapMarker**: 번호가 들어간 원형 마커. `<MapMarker number={3} />` 형태로 사용.

---

## 5단계: 페이지 템플릿 체계

9개 컴포넌트를 독립적으로 만드는 것에서 그치지 않고, 자주 반복될 레이아웃 패턴을 **페이지 템플릿**으로 추상화했다. 템플릿은 "어떤 컴포넌트를 어떻게 배치하는가"를 미리 결정해두는 것으로, 새 페이지를 만들 때 템플릿만 가져다 쓰면 레이아웃 결정을 반복하지 않아도 된다.

| 템플릿 | 구조 | 적용 페이지 |
|--------|------|-----------|
| **SplitPanelTemplate** | 좌(Input) + 우(Result) | AI 추천, 지도 플래너 |
| **DayTimelineTemplate** | DateChips + Day Accordion | 일정 관리 |
| **ListWithFilterTemplate** | Chip 필터 + 리스트 | 지출, 쇼핑, 체크리스트 |
| **CardGridTemplate** | 헤더 + 카드 그리드 | 여행 목록, 앨범 |
| **FormSectionTemplate** | Section + 입력 컴포넌트 | 여행 생성, 프로필 편집 |

예를 들어 `SplitPanelTemplate`은 다음과 같이 사용한다:

```svelte
<SplitPanelTemplate>
  {#snippet left()}
    <AiChatInput />
    <ChipGroup options={interestOptions} bind:selected />
    <RangeSlider label="예산" bind:value={budget} min={0} max={500000} />
    <SegmentedControl options={durationOptions} bind:value={duration} />
    <Button variant="primary" onclick={handleGenerate}>여행 계획 생성</Button>
  {/snippet}
  {#snippet right()}
    <TripHeader trip={generatedTrip} />
    <RouteMap waypoints={waypoints} />
    <Accordion title="Day 1">
      <ScheduleItem time="09:00" place="인천공항" category="교통" />
    </Accordion>
  {/snippet}
</SplitPanelTemplate>
```

이런 식으로 템플릿이 있으면, 새 AI 기능 페이지를 만들 때 레이아웃을 처음부터 결정할 필요가 없다.

---

## 삽질 기록

### Storybook 10 + Vite 7 호환성

Storybook 8.x는 Vite 7과 호환되지 않는다. peer dependency가 `vite@"^4 || ^5 || ^6"`으로 걸려 있어서 Vite 7을 사용하는 프로젝트에서는 설치 자체가 막히거나, 설치되더라도 빌드 시 에러가 난다. Storybook 10.2.15로 올려야 했다.

```bash
# 이렇게 하면 안 됨
npm i @storybook/svelte-vite@8.6.14  # vite 7 미지원, peer dep 에러

# 이렇게 해야 함
npm i storybook@10.2.15 @storybook/svelte-vite@10.2.15
```

Storybook을 메이저 버전 단위로 올릴 때는 공식 migration 가이드를 먼저 확인하는 것이 좋다. 8.x → 10.x 사이에 여러 breaking change가 있었다.

### @storybook/blocks vs @storybook/addon-docs

Storybook 10에서는 `@storybook/blocks`가 별도 패키지가 아니다. 8.x 시절에는 `@storybook/blocks`를 따로 설치하고 import했지만, 10.x에서는 `@storybook/addon-docs`에 통합되었다. MDX 파일에서 Meta를 import하는 경로를 바꿔야 한다.

```js
// 8.x (안 됨 — 모듈을 찾을 수 없음)
import { Meta } from '@storybook/blocks';

// 10.x (됨)
import { Meta } from '@storybook/addon-docs/blocks';
```

그리고 `main.js`의 addons 배열에 `@storybook/addon-docs`를 명시해야 MDX 파일이 빌드된다. 이게 없으면 MDX 파일이 무시된다.

```js
// .storybook/main.js
export default {
  addons: [
    '@storybook/addon-docs',
    // ...other addons
  ],
};
```

### Svelte 5 runes 마이그레이션

기존 Svelte 4 문법(`export let`)이 섞여 있으면 Storybook에서 prop 인식이 안 된다. Storybook의 Svelte 5 지원은 runes 문법(`$props()`)을 기준으로 설계되었기 때문에, Svelte 4 문법으로 작성된 컴포넌트는 ArgsTable이 비거나 prop이 잘못 표시될 수 있다. 26개 페이지를 `$props()` 문법으로 일괄 변환했다.

```svelte
// Before (Svelte 4)
export let trip;
export let user = null;

// After (Svelte 5 runes)
let { trip, user = null }: { trip: Trip; user?: User | null } = $props();
```

TypeScript 타입을 `$props()` 제네릭으로 명시하면, Storybook의 ArgsTable에 타입 정보도 함께 표시된다.

### formatCurrency 13개 파일 중복

13개 파일에서 동일한 `formatCurrency` 함수가 인라인으로 정의되어 있었다. 공용 유틸로 추출하되, 한 파일만 다른 구현(100으로 나누지 않는 방식)이어서 그건 로컬 유지했다. 이런 "거의 같은데 조금 다른" 케이스는 무조건 통합하면 버그가 생기므로, 차이를 문서화하고 다른 구현임을 명시해두었다.

```ts
// src/lib/utils/format.ts (공통 유틸)
export function formatCurrency(amount: number, currency = 'KRW'): string {
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}
```

### Layout.svelte 428줄 모놀리스

428줄짜리 Layout 컴포넌트를 4개로 분리했다:

- `TopNavBar.svelte` (152줄) — 상단 네비게이션 바
- `PillBottomNav.svelte` (79줄) — 하단 탭 네비게이션
- `UserMenu.svelte` (74줄) — 유저 메뉴 드롭다운
- `SearchModal.svelte` (119줄) — 검색 모달

분리 기준은 "독립적으로 교체 가능한가"였다. 예를 들어 하단 탭을 PillBottomNav에서 다른 스타일로 바꾸고 싶을 때, 분리 전에는 428줄 파일을 수정해야 했지만 이제는 PillBottomNav.svelte만 건드리면 된다.

---

## 최종 결과

| 지표 | Before | After |
|------|--------|-------|
| 공유 컴포넌트 | 23개 | **32개** (+9) |
| 디자인 토큰 종류 | 9종 | **15종** (+6) |
| Storybook variants | 51개 | **~80개** |
| 페이지 템플릿 | 0개 | **5개** |
| 페르소나 워크플로우 | 미정의 | **10개** |

---

## 핵심 교훈

**레퍼런스를 "따라 만드는" 것이 아니라 "구조만 추출해서 기존 시스템에 녹이는" 접근이 훨씬 실용적이다.**

색상, 폰트, 모드(dark/light)는 기존 토큰을 그대로 쓰고, 레이아웃 패턴(split panel, accordion, chip filter)만 가져오면 일관성을 유지하면서 UX를 확장할 수 있다.

구체적으로 정리하면:

1. **스타일과 구조를 분리하라.** 레퍼런스의 "무엇이 있는가"는 가져가되, "어떻게 생겼는가"는 기존 시스템에 맞게 재해석한다.
2. **토큰을 먼저 정의하라.** 컴포넌트 코드 안에 하드코딩하면 나중에 모든 컴포넌트를 수정해야 한다.
3. **추출과 신규 생성을 구분하라.** 이미 존재하는 패턴을 컴포넌트로 분리하는 것은 "추출"이고, 진짜로 새로운 것만 "신규"다.
4. **템플릿까지 만들어라.** 컴포넌트를 만들고 끝내지 말고, 자주 쓰이는 조합을 템플릿으로 정의해두면 이후 개발 속도가 크게 올라간다.
5. **호환성 문제는 메이저 버전 단위로 확인하라.** Storybook, Vite, Svelte 모두 메이저 버전마다 breaking change가 있다. 버전을 올리기 전에 peer dependency를 먼저 확인하는 습관이 필요하다.
