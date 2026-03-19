---
title: "Turbo Stream 누락 + BYE 슬롯 재활용 안 되는 버그 — Rails 8 대진표 디버깅 기록"
date: 2026-03-19
draft: false
tags: ["Rails 8", "Turbo Stream", "Stimulus", "Debugging", "대진표", "Bracket"]
description: "선수를 추가해도 반영이 안 되고, 자동배정을 다시 눌러도 빈 슬롯이 채워지지 않는 버그. 원인은 Turbo Stream 응답 누락과 auto_assign의 BYE 슬롯 제외 로직이었다. 삽질 과정과 수정 기록."
cover:
  image: "/images/og/rails-turbo-stream-bracket-bye-slot-debugging.png"
  alt: "Rails Turbo Stream Bracket BYE Slot Debugging"
  hidden: true
---

대진표 관리 앱에서 두 가지 버그가 동시에 나왔다.

1. **선수 추가 폼**이 작동하지 않는 것처럼 보임 — 추가 버튼을 눌러도 목록이 갱신 안 됨
2. **자동배정** 후 선수를 추가하고 다시 자동배정해도 빈 슬롯이 안 채워짐

겉으로 보면 "선수 생성이 안 된다"인데, 실제로는 두 개의 독립적인 버그가 동시에 나타난 케이스였다.

---

## 증상 정리

| 조작 | 기대 | 실제 |
|------|------|------|
| 선수 추가 폼 제출 | 목록에 즉시 반영 | 아무 변화 없음 (새로고침하면 있음) |
| 자동배정 → 선수 추가 → 자동배정 | 새 선수가 빈 슬롯에 배정 | "배정할 선수가 없습니다" or 변화 없음 |
| 빈 슬롯 표시 | 공란 | "BYE" 텍스트 노출 |

---

## 버그 1: Turbo Stream 응답 누락

### 원인

Rails 8 + Turbo 환경에서 `form_with`는 기본적으로 `turbo_stream` 포맷으로 제출한다. 컨트롤러의 `create` 액션이 이렇게 되어 있었다:

```ruby
def create
  @player = @tournament.players.build(player_params)

  if @player.save
    respond_to do |format|
      format.html { redirect_to players_path, notice: "Added." }
      format.json { render json: @player, status: :created }
      format.turbo_stream  # ← 블록 없음, 템플릿도 없음
    end
  end
end
```

`format.turbo_stream`이 블록 없이 호출되면 Rails는 `create.turbo_stream.erb`를 찾는다. 이 파일이 없으면 **ActionView::MissingTemplate** 에러가 발생한다. 하지만 Turbo가 이 에러를 조용히 삼키기 때문에, 사용자에게는 "버튼을 눌러도 아무 일도 안 일어남"으로 보인다.

같은 문제가 `update`, `destroy`, `update_status`, `withdraw` 액션에도 있었다. 전부 `format.turbo_stream` 블록이 비어 있었다.

### 수정

```ruby
def create
  @player = @tournament.players.build(player_params)

  if @player.save
    respond_to do |format|
      format.html { redirect_to players_path, notice: "Added." }
      format.json { render json: @player, status: :created }
      format.turbo_stream do
        @player = @tournament.players.build(status: :active)
        prepare_index_state
        flash.now[:notice] = "Player was successfully added."
        render :index  # index.turbo_stream.erb → 전체 목록 교체
      end
    end
  end
end
```

핵심: **turbo_stream 블록 안에서 상태를 리셋하고 `render :index`로 기존 turbo_stream 템플릿을 재활용**.

추가로, turbo_stream 템플릿이 `turbo_stream.replace "players-page"`를 호출하므로 타겟 ID가 HTML에 존재해야 한다:

```erb
<%# index.turbo_stream.erb %>
<%= turbo_stream.replace "players-page" do %>
  <%= render "page" %>
<% end %>
```

뷰에 `id="players-page"`가 빠져 있어서 교체 대상을 못 찾는 문제도 함께 수정했다.

### 교훈

> `format.turbo_stream` 블록 없이 호출하면 **반드시** 대응하는 `.turbo_stream.erb` 파일이 있어야 한다. 없으면 조용히 실패한다. 개발 중에는 브라우저 콘솔에서 `422` 응답을 확인하면 잡을 수 있다.

---

## 버그 2: 자동배정이 BYE 슬롯을 재활용하지 않음

### 배경

8인 대진표에 5명이 참가하면:
- 슬롯 8개 생성
- 자동배정 → 5명 배정, **나머지 3개는 `bye: true`로 마킹**

나중에 선수 2명을 추가하고 다시 자동배정을 누르면, 남은 BYE 슬롯에 배정되어야 한다.

### 원인

자동배정 로직이 이랬다:

```ruby
def auto_assign
  empty_slots = first_round.bracket_slots
    .where(player_id: nil, bye: false)  # ← BYE 슬롯 제외!
    .to_a

  empty_slots.each do |slot|
    player = unassigned_players.shift
    if player
      slot.update!(player_id: player.id, bye: false)
    else
      slot.update!(player_id: nil, bye: true)  # 남은 슬롯 → BYE
    end
  end
end
```

첫 자동배정에서 남은 슬롯이 `bye: true`로 바뀌면, 두 번째 자동배정 때 `where(bye: false)` 조건에서 완전히 제외된다. 새 선수를 추가해도 배정할 슬롯이 0개다.

반면 **랜덤 재배정**(`reassign_random`)은 모든 슬롯을 먼저 `bye: false`로 리셋한 후 재배정하기 때문에 정상 작동했다.

### 수정

```ruby
def auto_assign
  # 빈 슬롯 + BYE 슬롯 모두 활용
  empty_slots = first_round.bracket_slots
    .where(player_id: nil, bye: false).to_a
  bye_slots = first_round.bracket_slots
    .where(bye: true).to_a
  assignable_slots = empty_slots + bye_slots

  assignable_slots.each do |slot|
    player = unassigned_players.shift
    if player
      slot.update!(player_id: player.id, bye: false)
    else
      slot.update!(player_id: nil, bye: true)
    end
  end
end
```

빈 슬롯을 먼저 채우고, 그래도 선수가 남으면 BYE 슬롯을 되찾아서 배정한다. BYE 슬롯이 `bye: false`로 바뀌면서 자연스럽게 재활용된다.

### 검증

```
# 시나리오: 8슬롯, 처음 4명 → 추가 2명 → 추가 2명

1차 자동배정: 4명 배정, 4 BYE
선수 2명 추가 → 2차 자동배정: 6명 배정, 2 BYE  ✅
선수 2명 추가 → 3차 자동배정: 8명 배정, 0 BYE  ✅
```

---

## 부수 수정: BYE 슬롯 표시

대진표에서 빈 슬롯이 "BYE"라고 표시되는 것도 같이 수정했다. 운영자 입장에서 BYE는 "아직 배정 안 된 빈자리"인데 "BYE"라고 쓰면 "부전승"으로 오해할 수 있다.

```erb
<%# Before %>
<span class="text-[11px] italic text-muted">BYE</span>

<%# After — 공란 %>
<span class="text-[11px] text-muted">&nbsp;</span>
```

데스크탑, 모바일 뷰 모두 동일하게 수정.

---

## helper_method 누락

네비게이션 바에서 `managed_tournaments_scope`를 호출하는데 이 메서드가 `helper_method`로 노출되지 않아서 `NameError`가 발생했다.

```ruby
# Before
helper_method :app_home_path, :managed_tournament_dashboard_ready?

# After
helper_method :app_home_path, :managed_tournament_dashboard_ready?, :managed_tournaments_scope
```

컨트롤러에 정의된 private 메서드를 뷰에서 쓰려면 반드시 `helper_method`로 선언해야 한다. 뷰 파셜에서 직접 호출하면 `NameError`가 조용히 나온다.

---

## 정리

| 증상 | 실제 원인 | 분류 |
|------|----------|------|
| 선수 추가 안 됨 | turbo_stream 응답 누락 (템플릿 없음) | Turbo 설정 |
| 자동배정 재실행 안 됨 | BYE 슬롯이 쿼리에서 제외됨 | 비즈니스 로직 |
| 빈 슬롯에 "BYE" 표시 | 하드코딩된 BYE 텍스트 | UI |
| 네비게이션 에러 | helper_method 선언 누락 | Rails 설정 |

겉으로 하나의 버그("선수 추가가 안 됨")로 보이지만, 실제로는 네 개의 독립적인 문제가 동시에 나타난 경우였다. Turbo Stream은 실패해도 사용자에게 에러를 보여주지 않기 때문에, **브라우저 개발자 도구의 Network 탭을 먼저 확인**하는 습관이 중요하다.
