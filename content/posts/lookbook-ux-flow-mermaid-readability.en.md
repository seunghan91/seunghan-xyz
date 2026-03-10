---
title: "Improving Lookbook UX Flow Readability — Mermaid Flowchart + Step Template Redesign"
date: 2026-03-10
draft: false
tags: ["Rails", "Lookbook", "ViewComponent", "Mermaid", "UX", "Design System", "Documentation"]
description: "How I fixed poor readability in Lookbook component previews for UX Flow documentation using Mermaid.js flowcharts and a full step template redesign"
---

While documenting UX flows with Rails + Lookbook, I hit a moment of "something feels off." Each Step only showed wireframe fragments, so looking at the Lookbook list gave zero sense of the overall flow.

I fixed two things:

1. **Add a Mermaid flowchart Overview step to each flow**
2. **Redesign all Step template structures**

---

## The Problem: Lookbook Step Previews Feel Like "Context-Free Fragments"

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

Each `step_*` method renders an ERB template via `render_with_template`. The ERB contains a wireframe with a simple step navigation bar at the top.

**Problems with the original navigation bar:**
- Inline `① → ② →` format — too small, too dense
- Thumbnails in the Lookbook list don't show which flow this is or how many steps exist
- No overview means you have to click every step to understand the full flow

---

## Fix 1: Add a Mermaid.js Overview Step

### Add CDN

One line in the `component_preview.html.erb` layout:

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

### Add overview method to Preview class

Add an `overview` method at the top of each Flow Preview class. Since Lookbook renders in method declaration order, `# @label 0. Flow Overview` appears first.

```ruby
class UxFlows::AdminFlowPreview < ViewComponent::Preview
  # @label 0. Flow Overview   ← added
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

### Overview template — Mermaid diagram

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
    </div>

    <!-- Mermaid -->
    <div class="bg-white border border-stone-200 rounded-xl p-6">
      <pre class="mermaid">
flowchart LR
    A([🔐 Login]) --> B[Admin Dashboard\nOverall Stats]
    B --> C[Cohort/Team/Assignment CRUD]
    B --> D[User Management]
    B --> E[Notice Management]

    style A fill:#f97316,color:#fff,stroke:#ea580c
    style B fill:#1e293b,color:#fff,stroke:#0f172a
    style C fill:#fef3c7,stroke:#f59e0b
    style D fill:#fef3c7,stroke:#f59e0b
    style E fill:#fef3c7,stroke:#f59e0b
      </pre>
    </div>

    <!-- Step cards -->
    <div class="grid grid-cols-2 gap-3">
      <% [
        { step: 1, title: "Login → Dashboard", desc: "..." },
        { step: 2, title: "CRUD Management", desc: "..." }
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

`flowchart LR` (Left to Right) makes the flow immediately readable. The `style` directive separates roles by color.

---

## Fix 2: Step Template Structure Redesign

**Before:**
```
[Step nav bar — small circles + arrows]
[Wireframe (dashed border box)]
[UX Notes — amber box + bullet list]
```

**After:**
```
[Page Header — role badge + Step N/Total + title + description]
[Step Progress Bar — connecting lines + labels]
[Wireframe — browser chrome effect]
[UX Notes — icon + improved typography]
```

### Step Progress Bar — connecting lines + labels

The key is inserting `h-0.5` connecting lines between circles and placing labels below each circle.

```erb
<%
  steps = ["Login/Dashboard", "Cohort/Team/Assignment", "User Management", "Notice Management"]
  current = 0  # current step (0-based)
%>

<div class="bg-white border border-stone-200 rounded-xl p-5">
  <div class="flex items-start">
    <% steps.each_with_index do |step, i| %>
      <% done = i < current; active = i == current %>

      <%# Connecting line (skip for first step) %>
      <% if i > 0 %>
        <div class="flex-1 h-0.5 mt-4 <%= done ? 'bg-orange-300' : 'bg-stone-200' %>"></div>
      <% end %>

      <div class="flex flex-col items-center w-24 shrink-0">
        <%# Step circle %>
        <span class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
          <%= active ? 'bg-orange-500 text-white ring-4 ring-orange-100'
              : done  ? 'bg-stone-700 text-white'
              :          'bg-stone-100 text-stone-400 border border-stone-200' %>">
          <%= i + 1 %>
        </span>
        <%# Label %>
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

State mapping:
- **Done**: `bg-stone-700` (dark gray), line `bg-orange-300`
- **Active**: `bg-orange-500` + `ring-4 ring-orange-100` (glow ring)
- **Upcoming**: `bg-stone-100` + `border border-stone-200`

`mt-4` (16px) on the connecting line matches the vertical center of the `w-8 h-8` (32px) circle.

### Wireframe — browser chrome effect

```html
<div class="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
  <!-- Browser top bar -->
  <div class="flex items-center gap-3 px-5 py-3 bg-stone-50 border-b border-stone-200">
    <div class="flex gap-1.5">
      <span class="w-3 h-3 rounded-full bg-red-300"></span>
      <span class="w-3 h-3 rounded-full bg-yellow-300"></span>
      <span class="w-3 h-3 rounded-full bg-green-300"></span>
    </div>
    <span class="text-xs text-stone-400 font-mono">Admin / Cohort Management</span>
  </div>
  <!-- Wireframe content -->
  <div class="p-6">
    <!-- ... -->
  </div>
</div>
```

Replacing `dashed border` with macOS traffic lights + breadcrumb instantly communicates "this is a page preview."

### UX Notes — improved typography

```html
<div class="bg-amber-50 border border-amber-200 rounded-xl p-5">
  <div class="flex items-center gap-2 mb-3">
    <span class="text-lg">💡</span>
    <h3 class="text-sm font-bold text-amber-900">UX Notes</h3>
  </div>
  <ul class="space-y-2">
    <% ["Point 1", "Point 2", "Point 3"].each do |note| %>
      <li class="flex items-start gap-2 text-sm text-stone-700">
        <span class="text-amber-500 mt-0.5 shrink-0">→</span>
        <%= note %>
      </li>
    <% end %>
  </ul>
</div>
```

Changed from `<strong>UX Notes:</strong>` + `list-disc` to icon + `→` arrows.

---

## Result

| Before | After |
|--------|-------|
| Inline `① → ②` breadcrumb | Step Progress Bar with connecting lines |
| Dashed border wireframe | Browser chrome + path breadcrumb |
| No role distinction | Role badge + Step N/Total |
| `<strong>UX Notes:</strong>` | 💡 + bold title + `→` items |
| No flow overview | Mermaid flowchart Overview |

16 files changed total (3 overviews + 13 steps). The improvements are ERB-only — no component code touched.

---

## Takeaways

**Lookbook tips:**
- `render_with_template` automatically finds the ERB matching the method name
- Method declaration order = Lookbook sidebar order → put `overview` first to pin it at the top
- `# @label` controls the display name in the sidebar

**Mermaid in Lookbook:**
- Add the CDN script once in `component_preview.html.erb` — works across all previews
- Write diagram code inside `<pre class="mermaid">` blocks
- `startOnLoad: true` handles auto-rendering

**Step Progress Bar alignment:**
- The connecting line's `mt-4` must match half the circle size (`w-8 = 32px` → 16px = `mt-4`) to align horizontally
- Three states (`done` / `active` / `upcoming`) is sufficient
