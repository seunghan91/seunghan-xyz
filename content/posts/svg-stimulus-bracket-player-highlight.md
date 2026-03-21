---
title: "SVG 대진표에 Stimulus.js로 선수 하이라이트 구현 — Rails 8 + ViewComponent 삽질기"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus.js", "SVG", "ViewComponent", "Hotwire", "토너먼트", "인터랙션"]
description: "SVG로 렌더링된 토너먼트 대진표에서 선수를 클릭하면 해당 선수가 출전하는 모든 경기를 하이라이트하는 기능. data-* 속성, Stimulus targets, 투명 클릭 rect 레이어 설계."
categories: ["Rails", "Hotwire"]
---

Rails 8 + ViewComponent로 만든 SVG 기반 토너먼트 대진표에 인터랙션을 추가하면서 겪은 내용을 정리했다.

목표는 간단했다: **대진표에서 특정 선수를 클릭하면 그 선수가 출전하는 모든 경기 카드를 색상으로 강조**하기.

---

## 배경: SVG로 렌더링된 대진표

이 프로젝트의 대진표는 HTML div 카드가 아닌 **SVG**로 렌더링된다. `BracketTreeComponent` (ViewComponent)가 각 경기 슬롯 좌표를 계산해 SVG `<rect>`, `<text>`, `<circle>` 등으로 출력한다.

```erb
<%# bracket_tree_component.html.erb %>
<svg width="<%= svg_width %>" height="<%= svg_height %>">
  <% slots.each do |slot| %>
    <% x = x_position(slot.round) %>
    <% y = y_position(slot) %>
    <g id="bracket_slot_<%= slot.id %>">
      <rect x="<%= x %>" y="<%= y %>" width="216" height="88" rx="10" fill="#fff" />
      <text x="<%= x + 46 %>" y="<%= y + 42 %>"><%= team_a_name %></text>
      <text x="<%= x + 46 %>" y="<%= y + 70 %>"><%= team_b_name %></text>
    </g>
  <% end %>
</svg>
```

SVG는 HTML과 달리 `hover:`, `ring-` 같은 Tailwind 클래스가 직접 먹히지 않는다. 그래서 처음엔 어떻게 접근할지 고민이 됐다.

---

## 설계: 세 가지 레이어

Stimulus + SVG 조합에서 인터랙션은 **세 개의 레이어**로 분리하면 깔끔하다.

### 1. 데이터 레이어 — 참가자 ID 임베딩

각 경기 `<g>` 태그에 선수 ID를 data 속성으로 박아둔다.

```ruby
# bracket_tree_component.rb
def team_participant_ids(slot, team_side)
  return [] if slot.bye?
  match = slot.match
  return [] unless match
  match.public_send("#{team_side}_players").filter_map(&:participant_id)
end
```

```erb
<% a_ids = team_participant_ids(slot, :team_a).join(",") %>
<% b_ids = team_participant_ids(slot, :team_b).join(",") %>

<g id="bracket_slot_<%= slot.id %>"
   data-bracket-highlight-target="slot"
   data-bracket-highlight-team-a-ids="<%= a_ids %>"
   data-bracket-highlight-team-b-ids="<%= b_ids %>">
```

### 2. 시각 레이어 — 숨겨진 하이라이트 rect

각 팀 행 위치에 맞는 반투명 인디고 `<rect>`를 미리 그려두고 기본값은 `display:none`으로 숨긴다. 이게 클릭 시 켜지는 강조 밴드다.

SVG 렌더 순서(painter's algorithm)에 따라 반드시 **흰색 배경 rect 다음, 텍스트 content 이전**에 삽입해야 텍스트 위를 가리지 않는다.

```erb
<%# 배경 rect 이후, 텍스트 이전 %>
<rect class="bracket-player-hl-a"
      x="<%= x + 3 %>" y="<%= y + 24 %>"
      width="<%= MATCH_WIDTH - 3 %>" height="25"
      fill="rgba(99,102,241,0.12)"
      style="display:none; pointer-events:none" />
<rect class="bracket-player-hl-b"
      x="<%= x + 3 %>" y="<%= y + 49 %>"
      width="<%= MATCH_WIDTH - 3 %>" height="32"
      fill="rgba(99,102,241,0.12)"
      style="display:none; pointer-events:none" />
```

### 3. 클릭 레이어 — 투명 rect 오버레이

텍스트와 아바타 위에 `fill="transparent"` rect를 올린다. 클릭 이벤트를 받는 전용 레이어다. SVG 렌더 순서상 **그룹의 가장 마지막**에 위치해야 모든 요소 위에 오버레이된다.

```erb
<%# 그룹 마지막에 %>
<% if a_ids.present? %>
  <rect x="<%= x + 3 %>" y="<%= y + 24 %>"
        width="<%= MATCH_WIDTH - 3 %>" height="25"
        fill="transparent" style="cursor:pointer"
        data-action="click->bracket-highlight#selectTeam"
        data-bracket-highlight-ids-param="<%= a_ids %>" />
<% end %>
<% if b_ids.present? %>
  <rect x="<%= x + 3 %>" y="<%= y + 49 %>"
        width="<%= MATCH_WIDTH - 3 %>" height="32"
        fill="transparent" style="cursor:pointer"
        data-action="click->bracket-highlight#selectTeam"
        data-bracket-highlight-ids-param="<%= b_ids %>" />
<% end %>
```

---

## Stimulus 컨트롤러

컨트롤러 로직은 단순하다. 클릭된 ID 목록을 기억하고, 전체 슬롯을 순회하며 해당 ID를 포함하는 슬롯의 하이라이트 rect를 보여준다.

```javascript
// bracket_highlight_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["slot"]

  connect() {
    this.selectedIds = null
  }

  selectTeam(event) {
    event.stopPropagation()

    const ids = (event.params.ids || "").split(",").filter(Boolean)
    if (!ids.length) return

    // 같은 선수 재클릭 → 해제
    if (this.#sameSelection(ids)) {
      this.selectedIds = null
    } else {
      this.selectedIds = ids
    }

    this.#applyHighlights()
  }

  #sameSelection(ids) {
    if (!this.selectedIds) return false
    const sort = (arr) => [...arr].sort().join(",")
    return sort(ids) === sort(this.selectedIds)
  }

  #applyHighlights() {
    this.slotTargets.forEach((slot) => {
      const aIds = (slot.dataset.bracketHighlightTeamAIds || "").split(",").filter(Boolean)
      const bIds = (slot.dataset.bracketHighlightTeamBIds || "").split(",").filter(Boolean)

      const aMatch = this.selectedIds?.some((id) => aIds.includes(id)) ?? false
      const bMatch = this.selectedIds?.some((id) => bIds.includes(id)) ?? false

      slot.querySelector(".bracket-player-hl-a")?.style.setProperty("display", aMatch ? "" : "none")
      slot.querySelector(".bracket-player-hl-b")?.style.setProperty("display", bMatch ? "" : "none")
    })
  }
}
```

---

## 배포 전 테스트 수정에서 겪은 것들

SVG 기능 작업 전에 `bin/rails test`를 돌렸더니 7개 실패가 나왔다. 타입이 각기 달랐다.

### 1. 리다이렉트 경로 불일치

로그인 후 `root_path`로 리다이렉트된다고 테스트가 가정했는데, 실제 컨트롤러는 로그인 여부에 따라 `dashboard_path`로 분기했다. 테스트 기대값을 실제 동작에 맞게 수정.

### 2. ViewComponent 테스트 데이터 타입

컴포넌트 템플릿이 `player[:name]`으로 접근하는데, 테스트는 `["이름1", "이름2"]` 문자열 배열로 넘겼다. 해시 배열 `[{ name: "이름1" }]`으로 수정.

```ruby
# 수정 전
players: ["이름1", "이름2"]

# 수정 후
players: [{ name: "이름1" }, { name: "이름2" }]
```

### 3. Settings 페이지 게스트 접근

`before_action :authenticate_user_or_participant!`가 게스트를 `enter_path`로 보내고 있었다. 설정 페이지는 게스트도 볼 수 있어야 하고(회원가입 안내 표시), 수정(PATCH)만 막으면 됐다.

```ruby
class SettingsController < ApplicationController
  skip_before_action :authenticate_user!, raise: false
  before_action :require_user!, only: [:update]
end
```

### 4. 네이티브 앱 게스트 리다이렉트

Hotwire Native 앱에서 미로그인 상태로 접근하면 `enter_path`로 보내던 것을 `new_session_path`로 통일.

---

## 배운 점

- **SVG 인터랙션은 레이어 순서가 전부다.** 배경 → 하이라이트 밴드 → 콘텐츠 → 투명 클릭 오버레이 순서를 지켜야 한다.
- **SVG 요소에도 `data-*` 속성과 Stimulus가 그대로 동작한다.** 특별한 설정 없이 `data-action`, `data-controller`, `data-*-target`이 모두 작동한다.
- **`fill="transparent"`는 클릭 이벤트를 받는다.** `fill="none"`은 클릭 이벤트가 안 통과할 수 있으므로 주의.
- **배포 전 테스트 전수 실행은 필수다.** "구현했다"와 "테스트가 통과한다"는 다른 문제다.
