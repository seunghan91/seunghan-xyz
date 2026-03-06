---
title: "Rails + Svelte 앱 UX/UI 전수 점검 및 개선 기록"
date: 2026-03-06
draft: false
tags: ["Svelte", "Rails", "UX", "Accessibility", "svelte-sonner", "Tailwind"]
description: "할일 관리 웹앱의 UX 문제를 전수 점검하고 시작일 UI 통일, Toast 알림, 터치 타겟, 비밀번호 토글을 개선한 과정"
---

Rails 8 + Inertia.js + Svelte 5 조합으로 만든 웹앱을 운영하다가, 기능은 돌아가는데 세부 UX가 들쭉날쭉하다는 걸 느꼈다. 이번 글은 전수 점검 후 우선순위 높은 4가지를 직접 고친 기록이다.

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

### 해결: 생성 모달 패턴으로 통일

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

---

## 전수 점검: 44가지 UX 이슈

시작일 문제를 고치면서 다른 곳도 살펴봤다. 주요 카테고리별로 정리하면:

### CRITICAL — 즉시 수정 필요

**이모지를 UI 아이콘으로 사용 (☀️🕐📝🔔⭐)**
OS별 렌더링이 다르고, 스크린리더가 "별표 기호"로 읽어버린다. 크기 조절도 안 된다. SVG 아이콘(`lucide-svelte` 등)으로 교체해야 한다.

**모달 포커스 트랩 없음**
Dialog 컴포넌트에 `aria-modal="true"`는 있었지만 Tab 키로 모달 뒤 요소에 접근 가능한 상태였다. 스크린리더 사용자는 모달인지 모르고 뒤 콘텐츠와 상호작용하게 된다.

**비밀번호 표시 토글 없음**
타이핑 확인이 안 되니 오타 시 처음부터 다시 입력해야 한다. 로그인 실패의 흔한 원인.

**네트워크 에러 시 무응답**
`fetch()` 실패 시 `catch` 블록에서 state만 바꾸고 UI 피드백이 없었다. 사용자는 저장이 됐는지 안 됐는지 모른다.

### HIGH — 이번 스프린트 수정

- 터치 타겟 44px 미달 (Categories 편집/삭제 버튼 `p-1.5` ≈ 20px)
- 제출 버튼 성공/실패 피드백 없음
- `cursor-pointer` 누락
- 아이콘 전용 버튼 `aria-label` 없음

---

## 이번에 실제로 고친 것

전체 이슈 중 이번 작업에서 고친 4가지를 상세히 기록한다.

### 1. Toast 알림 통일 (svelte-sonner)

이전엔 성공/실패 피드백이 제각각이었다.
- 성공: `window.location.reload()` (조용히 새로고침)
- 실패: 폼 상단에 텍스트만 표시, 일부는 `console.error()`만

`svelte-sonner`가 이미 `AppLayout`에 `<Toaster>`로 마운트돼 있었는데 정작 모달에선 안 쓰고 있었다.

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
  error = msg;       // 폼 내부 에러 유지
  toast.error(msg);  // 토스트로도 표시
}
```

적용 범위: 생성 모달, 수정 모달(저장/삭제), 대시보드 빠른 추가.

### 2. 터치 타겟 44px 확대

모바일에서 작은 버튼은 사용자를 화나게 만든다. WCAG 기준 최소 44×44px.

Categories 페이지의 편집/공유/삭제 버튼이 `p-1.5`(약 20px)였다.

```svelte
<!-- Before -->
<button class="p-1.5 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition">

<!-- After -->
<button class="p-2.5 -m-1 text-text-sub hover:text-primary rounded-lg hover:bg-bg-grey transition cursor-pointer">
```

`-m-1`을 함께 쓴 게 포인트. 패딩을 늘려도 **시각적 레이아웃은 그대로** 유지하면서 터치 영역만 확대된다.

### 3. 비밀번호 표시/숨기기 토글

Login과 Register 모두 적용. 상태 변수 하나로 `type` 속성을 토글한다.

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

`tabindex="-1"`이 중요한 디테일이다. Tab으로 폼 이동 시 토글 버튼에 걸리지 않도록 해서 Tab 흐름을 방해하지 않는다.

Register는 비밀번호 + 비밀번호 확인 두 필드 모두 각각 독립된 토글 상태를 가진다.

```svelte
let showPassword = $state(false)
let showPasswordConfirmation = $state(false)
```

---

## 점검 결과 요약 (44건)

| 심각도 | 건수 | 주요 내용 |
|--------|------|----------|
| CRITICAL | 8 | 이모지 아이콘, 모달 포커스, 비번 토글, 에러 피드백, z-index |
| HIGH | 12 | 터치 타겟, 로딩 상태, aria-label, 키보드 접근 |
| MEDIUM | 16 | 대비율, prefers-reduced-motion, 빈 상태, 낙관적 업데이트 |
| LOW | 8 | 스피너 통일, 키보드 드래그, overflow 처리 등 |

---

## 느낀 점

기능이 돌아가더라도 UX 체감은 작은 디테일에서 결정된다는 걸 다시 실감했다.

특히 이번에 배운 것들:

1. **같은 기능이 여러 진입점에 있으면 패턴 통일이 필수다.** 컴포넌트 단위로 뽑아두지 않으면 수정할 때 n곳을 다 찾아다녀야 한다.

2. **피드백 없는 비동기는 항상 나쁘다.** `fetch()` 성공/실패에 항상 사용자가 인지할 수 있는 응답을 줘야 한다. `window.location.reload()`만 하면 사용자는 "저장이 된 건가?" 한 박자 불안해한다.

3. **터치 타겟은 눈에 안 보이는 영역이다.** 시각적으로 크기가 작아도 `padding + negative margin` 트릭으로 클릭 영역만 키울 수 있다. `-m-1`과 `p-2.5` 조합이 유용하다.

4. **`tabindex="-1"` 버튼은 의도적이다.** 보조 UI(토글, 지우기 등)를 Tab 순서에서 제외하면 키보드 사용자의 흐름이 자연스러워진다.
