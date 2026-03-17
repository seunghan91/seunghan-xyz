---
title: "Rails 대시보드에 DnD 카드 순서 변경 + 접기 구현 — SortableJS + Stimulus + CSS 트릭"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus", "SortableJS", "Hotwire", "Turbo Frame", "CSS", "localStorage", "Dashboard"]
description: "라이브러리 없이 구현하려다 실패한 DnD, SortableJS + Stimulus 조합으로 정착한 이유. 카드 높이 애니메이션을 scrollHeight 없이 해결하는 CSS grid-template-rows 트릭, localStorage로 레이아웃 상태를 persist하는 방법까지."
cover:
  image: "/images/og/stimulus-dnd-collapse-dashboard.png"
  alt: "Stimulus DnD Collapse Dashboard"
  hidden: true
---

스포츠 대회 관리 앱의 대시보드에 두 가지 기능을 추가하는 작업이었다.

1. **카드 순서 DnD 변경** — 내 경기 / 대진표 / 경기 목록 카드를 원하는 순서로 재배치
2. **카드 접기/펼치기** — 관심 없는 섹션을 접어 화면을 간결하게

각각은 단순해 보이지만, Turbo Frame lazy loading과 함께 동작해야 하고, 새로고침 후에도 상태가 유지되어야 한다는 조건이 붙으면 신경 쓸 게 늘어난다.

---

## 1. DnD 라이브러리 선택

처음에는 native HTML5 Drag & Drop API로 직접 구현했다. `dragstart`, `dragover`, `drop` 이벤트를 다 붙이고 DOM 조작으로 순서를 바꾸는 방식인데, 실제로 동작하게 만드는 건 어렵지 않다.

문제는 **터치 디바이스**였다. HTML5 drag API는 모바일 브라우저에서 지원이 불완전하다. 특히 iOS Safari에서 터치로 드래그하면 작동하지 않는다. 모바일 사용자가 더 많은 앱이라 이건 패스할 수 없었다.

대안으로 검토한 라이브러리들:

| 라이브러리 | 크기 (gzip) | 터치 지원 | Stimulus 통합 | 특이사항 |
|---|---|---|---|---|
| **SortableJS** | ~10KB | ✅ 완전 지원 | 매우 쉬움 | Rails 커뮤니티 표준 |
| Dragula | ~5KB | ⚠️ 부분적 | 보통 | 멀티 컨테이너 약함 |
| Interact.js | ~25KB | ✅ 완전 지원 | 복잡 | 리사이즈까지 필요할 때 |
| Pragmatic DnD | ~15KB | ✅ 완전 지원 | 복잡 | 접근성 우수, Atlassian 제작 |

**SortableJS**로 결정. Rails/Hotwire 생태계에서 가장 많이 검증됐고, Stimulus 컨트롤러 패턴과 자연스럽게 맞는다.

### importmap 추가

CDN ESM 버전을 importmap에 pin하는 것으로 충분하다.

```ruby
# config/importmap.rb
pin "sortablejs", to: "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm"
```

---

## 2. Stimulus 컨트롤러 설계

```javascript
// app/javascript/controllers/dashboard_dnd_controller.js
import { Controller } from "@hotwired/stimulus"
import Sortable from "sortablejs"

export default class extends Controller {
  static values = { storageKey: { type: String, default: "dashboard-layout-v1" } }

  connect() {
    this._restoreOrder()
    this._restoreCollapsed()

    this._sortable = new Sortable(this.element, {
      handle: ".dnd-handle",  // 그립 아이콘만 드래그 트리거
      animation: 150,
      ghostClass: "dnd-ghost",
      chosenClass: "dnd-chosen",
      onEnd: () => this._saveOrder()
    })
  }

  disconnect() {
    this._sortable?.destroy()
  }

  toggle(event) {
    const card    = event.currentTarget.closest("[data-card-id]")
    const content = card?.querySelector(".card-collapsible")
    const icon    = card?.querySelector("[data-toggle-icon]")
    if (!content) return

    const collapsing = !content.classList.contains("collapsed")
    content.classList.toggle("collapsed", collapsing)
    icon?.classList.toggle("rotate-180", collapsing)
    this._saveCollapsed()
  }

  _saveOrder() {
    const order = Array.from(this.element.children)
      .map(el => el.dataset.cardId)
      .filter(Boolean)
    localStorage.setItem(this.storageKeyValue, JSON.stringify(order))
  }

  _restoreOrder() {
    try {
      const order = JSON.parse(localStorage.getItem(this.storageKeyValue) || "[]")
      order.forEach(id => {
        const el = this.element.querySelector(`:scope > [data-card-id="${id}"]`)
        if (el) this.element.appendChild(el)
      })
    } catch (_) {}
  }

  _saveCollapsed() {
    const collapsed = Array.from(
      this.element.querySelectorAll(".card-collapsible.collapsed")
    ).map(el => el.closest("[data-card-id]")?.dataset.cardId).filter(Boolean)
    localStorage.setItem(this.storageKeyValue + "-collapsed", JSON.stringify(collapsed))
  }

  _restoreCollapsed() {
    try {
      const collapsed = JSON.parse(
        localStorage.getItem(this.storageKeyValue + "-collapsed") || "[]"
      )
      collapsed.forEach(id => {
        const card = this.element.querySelector(`:scope > [data-card-id="${id}"]`)
        card?.querySelector(".card-collapsible")?.classList.add("collapsed")
        card?.querySelector("[data-toggle-icon]")?.classList.add("rotate-180")
      })
    } catch (_) {}
  }
}
```

### 설계 포인트 두 가지

**`handle: ".dnd-handle"` 지정이 필수다.** 핸들 없이 전체 카드를 드래그 가능하게 하면, 카드 내부의 버튼 클릭이나 스크롤이 드래그와 충돌한다. 대진표 카드는 핀치줌/패닝이 붙어 있어 특히 문제가 된다.

**`_restoreOrder()`는 `connect()` 초반에, SortableJS 초기화 전에 실행한다.** DOM을 먼저 정렬하고 나서 SortableJS를 붙여야 한다. 순서가 반대면 DnD 초기 상태가 저장된 순서와 달라진다.

---

## 3. 카드 접기/펼치기 — height 애니메이션 문제

카드를 접을 때 높이를 0으로 애니메이션하는 건 언뜻 단순해 보이지만 함정이 있다.

### `max-height` 트릭의 한계

흔히 쓰는 방법:

```css
.collapsible { max-height: 1000px; transition: max-height 0.3s ease; overflow: hidden; }
.collapsible.collapsed { max-height: 0; }
```

문제는 **실제 높이와 max-height 차이만큼 애니메이션이 끊긴다**는 것. 카드가 200px인데 max-height가 1000px이면, 접힐 때 처음 800px은 즉시 "사라진 것처럼" 보이고 나머지 200px만 애니메이션된다.

JS로 `element.scrollHeight`를 측정해서 동적으로 설정하는 방법도 있지만, **Turbo Frame 내용이 lazy load로 나중에 채워지는 경우** scrollHeight가 0 또는 스켈레톤 높이만 잡힌다.

### CSS `grid-template-rows` 트릭

```css
.card-collapsible {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 0.25s ease;
}
.card-collapsible.collapsed {
  grid-template-rows: 0fr;
}
.card-collapsible > * {
  overflow: hidden;
  min-height: 0;  /* 이게 없으면 0fr이 실제로 0이 안 된다 */
}
```

핵심은 `grid-template-rows: 1fr → 0fr` 전환이다. CSS Grid는 `fr` 단위를 트랜지션할 수 있고, 내부 요소의 `min-height: 0`이 있으면 컨텐츠 높이가 얼마든 정확히 0까지 애니메이션된다.

**장점:**
- JS로 높이를 측정할 필요 없음
- 내용이 나중에 채워져도 올바르게 동작
- `display: none`과 달리 접혀 있는 동안에도 레이아웃 계산 유지

---

## 4. HTML 구조

각 카드 슬롯의 구조:

```html
<!-- 외부 래퍼: data-card-id가 DnD 정렬의 기준 -->
<div data-card-id="scoreboard">

  <!-- 드래그 핸들 + 접기 버튼 -->
  <div class="dnd-handle flex items-center justify-between px-3 py-1.5
              bg-slate-50 border border-b-0 border-slate-200
              rounded-t-2xl cursor-grab active:cursor-grabbing select-none">
    <div class="flex items-center gap-2 text-slate-400">
      <!-- 6점 그립 아이콘 -->
      <svg viewBox="0 0 10 16" fill="currentColor" class="h-3.5 w-3.5">
        <circle cx="2" cy="2" r="1.5"/><circle cx="8" cy="2" r="1.5"/>
        <circle cx="2" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/>
        <circle cx="2" cy="14" r="1.5"/><circle cx="8" cy="14" r="1.5"/>
      </svg>
      <span class="text-[10px] font-semibold uppercase tracking-[.24em]">내 경기</span>
    </div>
    <button data-action="click->dashboard-dnd#toggle">
      <svg data-toggle-icon class="h-3.5 w-3.5 transition-transform duration-200" ...>
        <polyline points="18 15 12 9 6 15"/>
      </svg>
    </button>
  </div>

  <!-- 접히는 콘텐츠 영역 -->
  <div class="card-collapsible">
    <div><!-- grid trick을 위한 inner wrapper -->
      <section id="scoreboard-section">
        <%= turbo_frame_tag "scoreboard_frame", src: ..., loading: :lazy do %>
          <!-- 스켈레톤 -->
        <% end %>
      </section>
    </div>
  </div>

</div>
```

**시각 연결:** 드래그 핸들 스트립은 `rounded-t-2xl border-b-0`, 카드 콘텐츠는 `rounded-b-2xl`로 설정해서 하나의 카드처럼 보이게 했다.

---

## 5. Turbo Frame과의 호환

Turbo Frame lazy loading(`loading: :lazy`)은 뷰포트에 들어올 때 로드된다.

**`_restoreOrder()`는 DOM 이동만 하고 로드는 트리거하지 않는다.** `connect()` 실행 시점에 아직 프레임이 로드되지 않았을 수 있고, `appendChild()`로 요소를 이동해도 다시 로드하지 않는다. 최종 순서대로 DOM이 정렬된 뒤 뷰포트에 들어오면 정상적으로 lazy load된다.

**접힌 상태로 복원된 카드**는 뷰포트 외부에 있는 것과 동일하므로 로드되지 않는다. 사용자가 펼칠 때 뷰포트에 진입하면 그때 로드된다. 의도치 않은 이점이지만, 불필요한 API 호출을 줄여주는 효과가 있다.

---

## 6. DnD Ghost 스타일

SortableJS 기본 ghost는 그냥 반투명이다. CSS로 조금 더 다듬었다:

```css
.dnd-ghost {
  opacity: 0.35;
  border-radius: 1rem;
  background: #e2e8f0;
}
.dnd-chosen {
  box-shadow: 0 20px 40px -8px rgba(0, 0, 0, 0.18);
}
```

`dnd-chosen`은 드래그 중인 실제 요소(ghost가 아닌 원본)에 붙는다. 살짝 떠오르는 느낌을 주기 위해 shadow를 강하게 줬다.

---

## 결과

- 3개 카드 모두 드래그 핸들로 순서 변경 가능
- 각 카드 우측 상단 chevron으로 접기/펼치기 (애니메이션 포함)
- 순서 + 접힌 상태 모두 `localStorage`에 저장, 새로고침 후 복원
- Turbo Frame lazy loading과 충돌 없음
- 모바일(터치), 데스크탑 동일하게 동작

라이브러리 추가는 SortableJS 하나, 새 Stimulus 컨트롤러 하나, CSS 몇 줄로 끝났다.
