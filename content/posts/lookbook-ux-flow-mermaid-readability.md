---
title: "Lookbook UX Flow 가독성 개선 — Mermaid 순서도 + Step 템플릿 리디자인"
date: 2026-03-10
draft: false
tags: ["Rails", "Lookbook", "ViewComponent", "Mermaid", "UX", "Design System", "개발 문서화"]
description: "Lookbook 컴포넌트 프리뷰에서 UX Flow를 문서화할 때 가독성이 떨어지는 문제를 Mermaid.js 순서도와 Step 템플릿 리디자인으로 해결한 기록"
categories: ["Rails", "Frontend"]
---

Rails + Lookbook으로 UX Flow를 문서화하다가 "이게 뭔가..." 싶은 순간이 왔다. 각 Step이 와이어프레임 조각으로만 나오니, Lookbook 목록에서 봤을 때 전체 흐름이 전혀 안 보이는 것이다.

두 가지를 고쳤다.

1. **각 Flow에 Mermaid 순서도 Overview Step 추가**
2. **모든 Step 템플릿 구조 리디자인**

---

## 문제: Lookbook Step 프리뷰가 "맥락 없는 조각"처럼 보임

```ruby
# @label Admin UX Flow
# @logical_path ux_flows
class UxFlows::AdminFlowPreview < ViewComponent::Preview
  # @label 1. Login -> Admin Dashboard
  def step_1_login_dashboard
    render_with_template
  end
  # ...
end
```

각 `step_*` 메서드는 `render_with_template`으로 ERB 파일을 렌더링한다. ERB 파일 안에는 와이어프레임이 있고, 상단에 간단한 Step 네비게이션 바가 있다.

**기존 네비게이션 바 문제:**
- `①` `→` `②` `→` 형태의 인라인 텍스트 — 너무 작고 촘촘함
- 각 Step 썸네일만 봐서는 어떤 Flow인지, 몇 단계인지 알 수 없음
- Overview가 없어서 전체 흐름을 파악하려면 모든 Step을 직접 클릭해야 함

---

## 해결 1: Mermaid.js로 Overview Step 추가

### CDN 추가

`component_preview.html.erb` 레이아웃에 Mermaid CDN 한 줄 추가:

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({
    startOnLoad: true,
    theme: 'neutral',
    fontFamily: 'Pretendard Variable, Pretendard, sans-serif'
  });
</script>
```

### Preview 클래스에 overview 메서드 추가

각 Flow Preview 클래스 맨 위에 `overview` 메서드를 추가한다. Lookbook은 메서드 순서대로 렌더링하므로 `# @label 0. Flow Overview`가 첫 번째로 표시된다.

```ruby
class UxFlows::AdminFlowPreview < ViewComponent::Preview
  # @label 0. Flow Overview   ← 추가
  def overview
    render_with_template
  end

  # @label 1. Login -> Admin Dashboard
  def step_1_login_dashboard
    render_with_template
  end
  # ...
end
```

### Overview 템플릿 — Mermaid 다이어그램

`admin_flow_preview/overview.html.erb`:

```html
<div class="bg-stone-50 p-6">
  <div class="max-w-5xl mx-auto space-y-5">

    <!-- Header -->
    <div class="pb-5 border-b border-stone-200">
      <div class="flex items-center gap-2 mb-2">
        <span class="bg-rose-600 text-white text-xs font-bold px-3 py-1 rounded-full">ADMIN</span>
        <span class="text-xs text-stone-400">Flow Overview</span>
      </div>
      <h1 class="text-2xl font-bold text-stone-900">Admin UX Flow</h1>
      <p class="text-sm text-stone-500 mt-1">관리자 전체 흐름</p>
    </div>

    <!-- Mermaid -->
    <div class="bg-white border border-stone-200 rounded-xl p-6">
      <pre class="mermaid">
flowchart LR
    A([🔐 로그인]) --> B[관리자 대시보드\n전체 현황 파악]
    B --> C[기수·팀·과제 CRUD]
    B --> D[유저 관리]
    B --> E[공지 관리]

    style A fill:#f97316,color:#fff,stroke:#ea580c
    style B fill:#1e293b,color:#fff,stroke:#0f172a
    style C fill:#fef3c7,stroke:#f59e0b
    style D fill:#fef3c7,stroke:#f59e0b
    style E fill:#fef3c7,stroke:#f59e0b
      </pre>
    </div>

    <!-- Step 카드 -->
    <div class="grid grid-cols-2 gap-3">
      <% [
        { step: 1, title: "로그인 → 대시보드", desc: "..." },
        { step: 2, title: "기수/팀/과제 관리", desc: "..." }
      ].each do |s| %>
        <div class="bg-white border border-stone-200 rounded-xl p-4 flex items-start gap-3">
          <span class="w-9 h-9 rounded-full bg-rose-500 text-white flex items-center justify-center text-sm font-bold shrink-0">
            <%= s[:step] %>
          </span>
          <div>
            <p class="text-sm font-semibold text-stone-900"><%= s[:title] %></p>
            <p class="text-xs text-stone-500 mt-0.5"><%= s[:desc] %></p>
          </div>
        </div>
      <% end %>
    </div>

  </div>
</div>
```

`flowchart LR`(Left to Right)로 흐름이 한눈에 보이고, `style` 지시어로 역할별 색상도 구분된다.

---

## 해결 2: Step 템플릿 구조 리디자인

기존 Step 템플릿 구조:

```
[Step 네비게이션 바 — 작은 원 + 화살표]
[와이어프레임 (dashed border)]
[UX Notes — amber box + bullet list]
```

**바뀐 구조:**

```
[Page Header — 역할 badge + Step N/Total + 제목 + 설명]
[Step Progress Bar — 연결선 + 라벨]
[Wireframe — 브라우저 크롬 효과]
[UX Notes — 아이콘 + 개선된 타이포]
```

### Step Progress Bar — 연결선 + 라벨

핵심은 원 사이에 연결선(`h-0.5`)을 넣고, 라벨을 원 아래에 배치하는 것이다.

```erb
<%
  steps = ["로그인/대시보드", "기수·팀·과제", "유저 관리", "공지 관리"]
  current = 0  # 현재 Step (0-based)
%>

<div class="bg-white border border-stone-200 rounded-xl p-5">
  <div class="flex items-start">
    <% steps.each_with_index do |step, i| %>
      <% done = i < current; active = i == current %>

      <%# 연결선 (첫 Step 제외) %>
      <% if i > 0 %>
        <div class="flex-1 h-0.5 mt-4 <%= done ? 'bg-orange-300' : 'bg-stone-200' %>"></div>
      <% end %>

      <div class="flex flex-col items-center w-24 shrink-0">
        <%# Step 원 %>
        <span class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
          <%= active ? 'bg-orange-500 text-white ring-4 ring-orange-100'
              : done  ? 'bg-stone-700 text-white'
              :          'bg-stone-100 text-stone-400 border border-stone-200' %>">
          <%= i + 1 %>
        </span>
        <%# 라벨 %>
        <span class="text-xs mt-2 text-center leading-tight px-1
          <%= active ? 'font-semibold text-stone-900'
              : done  ? 'text-stone-500'
              :          'text-stone-400' %>">
          <%= step %>
        </span>
      </div>
    <% end %>
  </div>
</div>
```

- **완료된 Step**: `bg-stone-700` (진한 회색), 연결선 `bg-orange-300`
- **현재 Step**: `bg-orange-500` + `ring-4 ring-orange-100` (후광 효과)
- **미래 Step**: `bg-stone-100` + `border border-stone-200`

`mt-4`(16px)는 `w-8 h-8` 원의 중앙 높이와 일치한다.

### 와이어프레임 — 브라우저 크롬 효과

```html
<div class="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
  <!-- 브라우저 상단 바 -->
  <div class="flex items-center gap-3 px-5 py-3 bg-stone-50 border-b border-stone-200">
    <div class="flex gap-1.5">
      <span class="w-3 h-3 rounded-full bg-red-300"></span>
      <span class="w-3 h-3 rounded-full bg-yellow-300"></span>
      <span class="w-3 h-3 rounded-full bg-green-300"></span>
    </div>
    <span class="text-xs text-stone-400 font-mono">관리 / 기수 관리</span>
  </div>
  <!-- 와이어프레임 내용 -->
  <div class="p-6">
    <!-- ... -->
  </div>
</div>
```

`dashed border` 대신 macOS 트래픽라이트 + breadcrumb 상단 바로 "이건 페이지 미리보기"라는 맥락을 즉시 전달한다.

### UX Notes — 개선된 타이포

```html
<div class="bg-amber-50 border border-amber-200 rounded-xl p-5">
  <div class="flex items-center gap-2 mb-3">
    <span class="text-lg">💡</span>
    <h3 class="text-sm font-bold text-amber-900">UX Notes</h3>
  </div>
  <ul class="space-y-2">
    <% ["포인트 1", "포인트 2", "포인트 3"].each do |note| %>
      <li class="flex items-start gap-2 text-sm text-stone-700">
        <span class="text-amber-500 mt-0.5 shrink-0">→</span>
        <%= note %>
      </li>
    <% end %>
  </ul>
</div>
```

`<strong>UX Notes:</strong>` + `list-disc` 대신 아이콘 + `→` 화살표로 변경.

---

## 결과

| 변경 전 | 변경 후 |
|--------|--------|
| 번호+화살표 1줄 breadcrumb | 연결선+라벨 있는 Step Progress Bar |
| dashed border 와이어프레임 | 브라우저 크롬 + breadcrumb |
| 역할 구분 없음 | 역할 badge + Step N/Total |
| `<strong>UX Notes:</strong>` | 💡 + 볼드 타이틀 + `→` 아이템 |
| Step별 Overview 없음 | Mermaid 순서도 Overview |

변경한 파일은 총 16개 (Overview 3개 + Step 13개). 구조 개선은 ERB 템플릿에만 국한되어 컴포넌트 코드는 건드리지 않았다.

---

## 배운 것

**Lookbook 활용 팁:**
- `render_with_template`은 메서드명과 동일한 ERB 파일을 자동으로 찾는다
- 메서드 선언 순서 = Lookbook 사이드바 순서 → `overview`를 맨 위에 두면 자동으로 첫 번째 표시
- `# @label`로 사이드바 표시 이름 제어 가능

**Mermaid in Lookbook:**
- CDN 스크립트를 `component_preview.html.erb` 레이아웃에 한 번만 추가하면 모든 프리뷰에서 동작
- `<pre class="mermaid">` 블록 안에 다이어그램 코드 작성
- `startOnLoad: true`로 자동 렌더링

**Step Progress Bar:**
- 연결선의 `mt-4`는 원 크기(`w-8 = 32px`)의 절반(16px)과 일치해야 수평으로 정렬됨
- `done` / `active` / `upcoming` 세 상태로 분기하면 충분
