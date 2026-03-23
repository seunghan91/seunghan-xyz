---
title: "Rails + Svelte 앱 UX/UI 전수 점검 및 개선 기록"
date: 2026-03-06
draft: false
tags: ["Svelte", "Rails", "UX", "Accessibility", "svelte-sonner", "Tailwind"]
description: "할일 관리 웹앱의 UX 문제를 전수 점검하고 시작일 UI 통일, Toast 알림, 터치 타겟, 비밀번호 토글을 개선한 과정"
cover:
  image: "/images/og/uxui-review-and-fix-svelte-rails.png"
  alt: "Uxui Review And Fix Svelte Rails"
  hidden: true
---

Rails 8 + Inertia.js + Svelte 5 조합으로 만든 웹앱을 운영하다가, 기능은 돌아가는데 세부 UX가 들쭉날쭉하다는 걸 느꼈다. 이번 글은 전수 점검 후 우선순위 높은 4가지를 직접 고친 기록이다.

기능을 빠르게 만들다 보면 각 화면이 독립적으로 개발되고, 결과적으로 "같은 기능인데 화면마다 동작이 다른" 상태가 된다. 사용자 입장에서 이런 불일치는 앱이 정돈되지 않은 느낌을 준다. 코드의 버그는 아니지만, 분명한 UX 버그다.

---

## 문제 발견: 같은 기능인데 UI가 다르다

가장 먼저 눈에 띈 건 **시작일 입력 UI가 화면마다 다르게 동작**하는 문제였다.

앱에는 할일을 만들 수 있는 진입점이 4곳이다.

- 대시보드 빠른 추가
- 모달(생성)
- 전체 페이지 생성
- 모달(수정)

| 위치 | 시작일 동작 |
|------|------------|
| 대시보드 빠른추가 | 피커가 항상 노출 + `+ 시작일` 버튼도 따로 존재 |
| 생성 모달 | 마감일 설정 후 `+ 시작일 추가` 버튼 클릭 시 피커 표시 |
| 전체 페이지 | 피커 항상 노출 |
| 수정 모달 | 피커 항상 노출 |

생성 모달만 UX가 깔끔했고, 나머지 3곳은 피커가 항상 보여서 폼이 불필요하게 복잡해 보였다. `+ 시작일` 버튼이 있는데 피커도 이미 떠 있으니 버튼의 의미가 모호했다.

이런 불일치가 생기는 원인은 단순하다. 각 진입점 컴포넌트가 서로 다른 시점에, 서로 다른 개발자(혹은 다른 정신 상태의 같은 개발자)가 만들기 때문이다. 컴포넌트로 추상화하지 않고 각자 인라인으로 구현하면 필연적으로 이렇게 된다.

### 해결: 생성 모달 패턴으로 통일

가장 UX가 좋았던 생성 모달 패턴을 기준으로 나머지 3곳을 통일했다. 핵심 원칙은 **"필요할 때만 보인다"** 는 것이다.

```svelte
<!-- Before: 피커가 항상 보임 -->
<div class="grid gap-2 sm:grid-cols-2">
  <div>
    <Label>시작일</Label>
    {#if startDate}
      <button onclick={() => startDate = ''}>제거</button>
    {:else}
      <button onclick={() => startDate = dueDate}>+ 시작일</button>
    {/if}
    <DueDatePicker value={...} />  <!-- 항상 렌더링 -->
  </div>
  <div>
    <Label>마감일</Label>
    <DueDatePicker value={...} />
  </div>
</div>
```

```svelte
<!-- After: 마감일 먼저, 시작일은 필요할 때만 -->
<div>
  <div class="flex items-center justify-between mb-1">
    <Label>마감일</Label>
    {#if dueDate && !startDate}
      <button onclick={() => startDate = dueDate}>+ 시작일 추가</button>
    {/if}
  </div>
  <DueDatePicker value={...} />
</div>

{#if startDate}
  <div>
    <div class="flex items-center justify-between mb-1">
      <Label>시작일</Label>
      <button onclick={() => startDate = ''}>제거</button>
    </div>
    <DueDatePicker value={...} />
  </div>
{/if}
```

변경 포인트:
1. **마감일이 주된 필드**라는 걸 레이아웃으로 표현 (위에 배치)
2. 마감일 설정 후에만 `+ 시작일 추가` 버튼 표시 → 흐름이 자연스러움
3. 시작일 피커는 버튼 클릭 시에만 나타남 → 폼 복잡도 감소

이 패턴의 장점은 **Progressive Disclosure** 원칙을 따른다는 것이다. 사용자가 필요로 하는 순간에만 추가 옵션을 노출한다. 폼이 처음 열렸을 때 보여야 하는 정보는 "무엇을 할 것인가(할일 내용)"와 "언제까지(마감일)"로 충분하다. 시작일은 선택 사항이고, 마감일이 정해진 뒤에나 의미가 있다.

---

## 전수 점검: 44가지 UX 이슈

시작일 문제를 고치면서 다른 곳도 살펴봤다. 주요 카테고리별로 정리하면:

### CRITICAL — 즉시 수정 필요

**이모지를 UI 아이콘으로 사용 (☀️🕐📝🔔⭐)**

OS별 렌더링이 다르고, 스크린리더가 "별표 기호"로 읽어버린다. 크기 조절도 안 된다. 예를 들어 ☀️는 macOS에서 노란 태양 이미지지만, Windows에서는 다르게 보일 수 있다. 더 큰 문제는 `font-size`로 크기를 조절할 수 없어서 반응형 디자인에서 레이아웃이 깨진다. SVG 아이콘(`lucide-svelte` 등)으로 교체해야 한다.

**모달 포커스 트랩 없음**

Dialog 컴포넌트에 `aria-modal="true"`는 있었지만 Tab 키로 모달 뒤 요소에 접근 가능한 상태였다. 스크린리더 사용자는 모달인지 모르고 뒤 콘텐츠와 상호작용하게 된다. `aria-modal="true"`만으로는 충분하지 않다. 실제로 포커스를 모달 내부에 가두는 JavaScript 로직이 필요하다. 또는 `<dialog>` HTML 요소를 사용하면 브라우저가 기본 포커스 트랩을 제공한다.

**비밀번호 표시 토글 없음**

타이핑 확인이 안 되니 오타 시 처음부터 다시 입력해야 한다. 로그인 실패의 흔한 원인이며, 사용자 좌절의 주요 요인이다. WCAG 2.1 Success Criterion 1.3.5는 비밀번호 필드에 "show/hide" 기능을 권장한다.

**네트워크 에러 시 무응답**

`fetch()` 실패 시 `catch` 블록에서 state만 바꾸고 UI 피드백이 없었다. 사용자는 저장이 됐는지 안 됐는지 모른다. 특히 모바일 사용자는 네트워크 품질이 불안정하기 때문에 이 문제가 더 자주 발생한다.

### HIGH — 이번 스프린트 수정

- 터치 타겟 44px 미달 (Categories 편집/삭제 버튼 `p-1.5` ≈ 20px)
- 제출 버튼 성공/실패 피드백 없음
- `cursor-pointer` 누락 — 클릭 가능한 요소임을 시각적으로 알려야 한다
- 아이콘 전용 버튼 `aria-label` 없음 — 스크린리더가 버튼의 역할을 설명하지 못한다

### MEDIUM — 다음 스프린트

- 색상 대비율 WCAG AA 기준(4.5:1) 미달 구간 존재
- `prefers-reduced-motion` 미지원 — 모션 감수성 사용자를 위한 배려
- 빈 상태(Empty State) UI 없음 — 데이터가 없을 때 아무것도 표시되지 않아 앱이 고장난 것처럼 보임
- 낙관적 업데이트(Optimistic Update) 미적용 — 서버 응답 전에 UI를 먼저 업데이트하면 체감 속도가 빨라진다

---

## 이번에 실제로 고친 것

전체 이슈 중 이번 작업에서 고친 4가지를 상세히 기록한다.

### 1. Toast 알림 통일 (svelte-sonner)

이전엔 성공/실패 피드백이 제각각이었다.
- 성공: `window.location.reload()` (조용히 새로고침)
- 실패: 폼 상단에 텍스트만 표시, 일부는 `console.error()`만

`svelte-sonner`가 이미 `AppLayout`에 `<Toaster>`로 마운트돼 있었는데 정작 모달에선 안 쓰고 있었다. 라이브러리가 이미 있는데 쓰지 않는 상태였다.

```svelte
<!-- 기존 -->
} catch (err) {
  error = err?.message || '할 일 생성에 실패했습니다.';
} finally {
  submitting = false;
}
```

```svelte
<!-- 개선 -->
import { toast } from 'svelte-sonner';

// 성공 시
toast.success('할 일이 생성되었습니다.');
window.location.reload();

// 실패 시
} catch (err) {
  const msg = err?.message || '할 일 생성에 실패했습니다.';
  error = msg;       // 폼 내부 에러 유지 (인라인 에러 메시지)
  toast.error(msg);  // 토스트로도 표시 (화면 상단에 알림)
}
```

`error` 상태를 유지하면서 동시에 토스트로도 표시하는 이유가 있다. 폼 내부 에러 메시지는 "어떤 필드에 문제가 있는지"를 컨텍스트와 함께 알려주고, 토스트는 "어떤 작업이 실패했는지"를 즉각적으로 알려준다. 두 가지가 서로 보완된다.

적용 범위: 생성 모달, 수정 모달(저장/삭제), 대시보드 빠른 추가.

이 변경으로 얻은 효과는 단순히 "토스트가 뜬다"가 아니다. 사용자가 다음 행동을 취해도 되는지 여부를 명확하게 알 수 있게 됐다. 토스트가 뜨기 전에는 "혹시 저장이 됐나?" 하며 페이지를 새로고침하거나 다시 시도하는 불필요한 행동이 발생할 수 있었다.

### 2. 터치 타겟 44px 확대

모바일에서 작은 버튼은 사용자를 화나게 만든다. WCAG 기준 최소 44×44px이다.

Categories 페이지의 편집/공유/삭제 버튼이 `p-1.5`(약 20px)였다. 16px 아이콘 + 6px 패딩 × 2 = 28px. 기준의 절반 수준이다.

```svelte
<!-- Before -->
<button class="p-1.5 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition">

<!-- After -->
<button class="p-2.5 -m-1 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition cursor-pointer">
```

`-m-1`을 함께 쓴 게 포인트다. 패딩을 늘려도 **시각적 레이아웃은 그대로** 유지하면서 터치 영역만 확대된다.

계산해보면: `p-2.5` = 10px, 아이콘 16px + 10px × 2 = 36px. 아직 44px에는 못 미치지만 `-m-1`(4px negative margin)을 양쪽에 더하면 실질 클릭 영역은 44px가 된다. 네거티브 마진 트릭은 버튼의 시각적 크기를 건드리지 않고 인터랙션 영역만 넓힌다. 레이아웃 변경 없이 접근성을 개선하는 실용적인 방법이다.

`cursor-pointer`도 함께 추가했다. CSS의 기본 커서는 `default`라 아이콘 버튼이 클릭 가능한지 시각적으로 구분이 안 된다. 작은 추가지만 인지적 마찰을 줄인다.

### 3. 비밀번호 표시/숨기기 토글

Login과 Register 모두 적용했다. Svelte 5의 `$state` rune을 사용해 상태를 관리한다.

```svelte
let showPassword = $state(false);
```

```svelte
<div class="relative mt-1">
  <Input
    id="password"
    type={showPassword ? 'text' : 'password'}
    bind:value={password}
    placeholder="••••••••"
    required
    autocomplete="current-password"
  />
  <button
    type="button"
    class="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-text-sub hover:text-text-main cursor-pointer"
    onclick={() => (showPassword = !showPassword)}
    aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
    tabindex="-1"
  >
    {#if showPassword}
      <!-- EyeOff SVG -->
    {:else}
      <!-- Eye SVG -->
    {/if}
  </button>
</div>
```

`tabindex="-1"`이 중요한 디테일이다. Tab으로 폼을 이동할 때 토글 버튼에 포커스가 걸리지 않도록 한다. 비밀번호 필드에서 Tab을 누르면 자연스럽게 다음 입력 필드(또는 제출 버튼)로 이동해야 한다. 토글 버튼은 보조 기능이므로 Tab 흐름을 방해하지 않는 것이 맞다.

`aria-label`도 함께 설정했다. 버튼에 텍스트가 없고 아이콘만 있으면 스크린리더가 무슨 버튼인지 알 수 없다. 현재 상태에 따라 `aria-label`을 동적으로 바꿔서 "현재 비밀번호가 보이는 상태"인지 "숨겨진 상태"인지도 알려준다.

`autocomplete="current-password"`도 추가했다. 브라우저 자동완성이 올바르게 작동하도록 힌트를 준다. 사소해 보이지만 패스워드 매니저 사용자들에게 큰 차이를 만든다.

Register에서는 비밀번호와 비밀번호 확인 두 필드를 각각 독립된 상태로 관리한다. 두 필드가 같은 상태를 공유하면 하나를 토글할 때 다른 것도 같이 토글되어 혼란스럽다.

```svelte
let showPassword = $state(false)
let showPasswordConfirmation = $state(false)
```

### 4. 시작일 UI 통일 (앞 섹션의 연장)

앞서 설명한 시작일 패턴 통일을 대시보드, 전체 페이지 생성, 수정 모달 3곳에 적용했다. 수정 모달은 기존 값이 있을 수 있으므로 초기값 처리에 주의가 필요하다. 시작일이 이미 설정되어 있으면 피커를 바로 표시하고, 없으면 버튼만 표시한다. 이 로직 자체는 동일하지만 수정 모달에서는 서버에서 받은 값으로 초기 상태를 세팅해야 한다.

```svelte
// 수정 모달에서의 초기값 처리
let startDate = $state(task.startDate ?? '')
let dueDate = $state(task.dueDate ?? '')
// startDate가 있으면 {#if startDate} 블록이 자동으로 피커를 보여준다
```

---

## 점검 결과 요약 (44건)

| 심각도 | 건수 | 주요 내용 |
|--------|------|----------|
| CRITICAL | 8 | 이모지 아이콘, 모달 포커스, 비번 토글, 에러 피드백, z-index |
| HIGH | 12 | 터치 타겟, 로딩 상태, aria-label, 키보드 접근 |
| MEDIUM | 16 | 대비율, prefers-reduced-motion, 빈 상태, 낙관적 업데이트 |
| LOW | 8 | 스피너 통일, 키보드 드래그, overflow 처리 등 |

이번에 고친 건 44건 중 4건이다. 하지만 CRITICAL 8건 중 3건(비밀번호 토글, 에러 피드백 Toast, 피커 불일치)을 처리했으니 체감 개선은 숫자 이상이다. 나머지 CRITICAL 이슈인 이모지 아이콘 교체와 모달 포커스 트랩은 다음 스프린트에서 처리할 예정이다.

---

## 핵심 교훈 (Key Takeaways)

기능이 돌아가더라도 UX 체감은 작은 디테일에서 결정된다는 걸 다시 실감했다.

**1. 같은 기능이 여러 진입점에 있으면 패턴 통일이 필수다.**

컴포넌트 단위로 뽑아두지 않으면 수정할 때 n곳을 다 찾아다녀야 한다. 이번 시작일 수정이 딱 그 케이스였다. 하나로 수정하면 될 걸 4곳을 찾아 동일한 변경을 반복했다. 다음엔 `StartDateField` 같은 공용 컴포넌트로 추상화할 것이다.

**2. 피드백 없는 비동기는 항상 나쁘다.**

`fetch()` 성공/실패에 항상 사용자가 인지할 수 있는 응답을 줘야 한다. `window.location.reload()`만 하면 사용자는 "저장이 된 건가?" 한 박자 불안해한다. Toast처럼 즉각적인 피드백이 있으면 그 불안이 사라진다. 비동기 작업에는 세 가지 상태를 항상 처리해야 한다: 로딩(loading), 성공(success), 실패(error).

**3. 터치 타겟은 눈에 안 보이는 영역이다.**

시각적으로 크기가 작아도 `padding + negative margin` 트릭으로 클릭 영역만 키울 수 있다. `-m-1`과 `p-2.5` 조합이 유용하다. 레이아웃을 건드리지 않고 접근성을 개선할 수 있는 실용적인 패턴이다.

**4. `tabindex="-1"` 버튼은 의도적이다.**

보조 UI(토글, 지우기 등)를 Tab 순서에서 제외하면 키보드 사용자의 흐름이 자연스러워진다. 모든 UI 요소가 Tab으로 접근 가능해야 하는 것은 아니다. 주요 흐름을 방해하지 않는 보조 기능은 마우스/포인터로만 접근 가능하게 두는 것이 오히려 더 좋은 경험이다.

**5. 접근성 점검은 기능 개발과 함께 가야 한다.**

나중에 몰아서 하려면 44건짜리 리스트가 된다. 컴포넌트를 만들 때 `aria-label`, 터치 타겟, 포커스 관리를 함께 고려하면 나중에 고칠 것이 훨씬 줄어든다.
