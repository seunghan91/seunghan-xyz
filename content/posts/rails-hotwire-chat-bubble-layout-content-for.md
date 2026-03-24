---
title: "Rails Hotwire 채팅 리디자인 — 버블 UI, 사이드바 채널 분리, content_for 레이아웃 트릭"
date: 2025-03-24
draft: false
tags: ["Rails", "Hotwire", "Tailwind CSS", "ViewComponent", "채팅 UI"]
description: "Rails + Hotwire 앱에서 iMessage 스타일 채팅 버블 구현, DM/채널 사이드바 분리, content_for로 특정 페이지에서만 레이아웃 섹션 숨기는 패턴까지 정리."
---

Rails로 채팅 기능을 만들다 보면 어느 순간 한계에 부딪힌다. 초기엔 textarea에 리스트로 메시지를 쌓는 구조로 충분하지만, 실제 사용자 앞에 놓으면 카카오톡이나 Slack을 쓰던 사람들 눈엔 영 어색해 보인다. 내 메시지는 오른쪽, 상대 메시지는 왼쪽 — 이 직관적인 패턴을 Rails + Turbo Streams 환경에서 어떻게 구현했는지 기록해둔다.

거기에 채팅방 진입점(DM) vs. 그룹 채널을 사이드바에서 구조적으로 분리한 방법, 그리고 특정 페이지에서만 공통 레이아웃 섹션을 숨기는 `content_for` 트릭까지 담았다.

---

## 채팅 버블 UI: 내 메시지 오른쪽, 상대 메시지 왼쪽

채팅 UI의 핵심은 단순하다. 누구 메시지냐에 따라 정렬 방향과 색상만 바꾸면 된다. Tailwind CSS의 `flex-row-reverse`와 `rounded-br-sm` 조합이 핵심이다.

### 기존 방식의 문제

처음엔 이렇게 단순하게 렌더링했다.

```erb
<% @chat_messages.each do |msg| %>
  <div class="p-3 rounded-lg bg-gray-100">
    <strong><%= msg.user.name %></strong>
    <p><%= msg.body %></p>
  </div>
<% end %>
```

모든 메시지가 같은 스타일, 같은 위치. 내가 보낸 건지 받은 건지 구분이 안 됐다. Perplexity에서 iMessage 버블 구현 방법을 찾아보니 핵심은 두 가지였다.

1. **flex 컨테이너에서 정렬 방향 전환** — `flex-row-reverse`로 내 메시지를 오른쪽으로
2. **border-radius 비대칭** — 말풍선 꼬리 느낌을 `rounded-br-sm` / `rounded-bl-sm`으로 표현

### 실제 적용한 파셜

```erb
<%# app/views/chat_messages/_chat_message.html.erb %>
<% is_mine = current_user && chat_message.user == current_user %>

<div id="<%= dom_id(chat_message) %>"
     class="flex items-end gap-2 px-4 py-1 <%= is_mine ? 'flex-row-reverse' : 'flex-row' %> group/bubble">

  <%# 상대방 아바타 (내 메시지엔 표시 안 함) %>
  <% unless is_mine %>
    <div class="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white"
         style="background: var(--color-primary-400);">
      <%= chat_message.user.name.first %>
    </div>
  <% end %>

  <%# 메시지 버블 %>
  <div class="max-w-[70%] flex flex-col <%= is_mine ? 'items-end' : 'items-start' %>">
    <% unless is_mine %>
      <span class="text-xs mb-1" style="color: var(--text-tertiary);">
        <%= chat_message.user.name %>
      </span>
    <% end %>

    <div class="px-4 py-2.5 text-sm leading-relaxed
                <%= is_mine
                      ? 'rounded-2xl rounded-br-sm text-white'
                      : 'rounded-2xl rounded-bl-sm' %>"
         style="<%= is_mine
                      ? 'background: var(--color-primary-500);'
                      : 'background: var(--surface-tertiary); color: var(--text-primary);' %>">
      <%= chat_message.body %>
    </div>

    <span class="text-xs mt-1" style="color: var(--text-tertiary);">
      <%= chat_message.created_at.strftime("%H:%M") %>
    </span>
  </div>
</div>
```

`is_mine` 변수 하나로 모든 분기가 갈린다. `flex-row-reverse`가 내 메시지를 오른쪽으로 밀고, `rounded-br-sm`이 말풍선 꼬리 방향을 만든다. 색상은 CSS 변수(`--color-primary-500`)를 써서 다크모드 대응도 자연스럽게 된다.

### Turbo Streams와의 궁합

Turbo Streams로 실시간 메시지를 브로드캐스트할 때도 이 파셜이 그대로 쓰인다. `current_user`를 파셜에서 쓰는 게 찝찝할 수 있는데, Rails의 `current_user`는 thread-safe한 `Current` 객체를 통해 접근하므로 문제없다.

```ruby
# 메시지 모델 또는 after_create_commit
after_create_commit do
  broadcast_append_to channel,
    partial: "chat_messages/chat_message",
    locals: { chat_message: self },
    target: "messages"
end
```

---

## 사이드바 구조 개편: DM vs. 채널 분리

Slack을 보면 좌측 사이드바에 채널 목록이 있고, DM은 별도 섹션으로 구분돼 있다. 처음엔 `/chats`에 채널과 DM을 한꺼번에 두었는데, 사용하다 보니 두 개념이 섞여서 혼란스러웠다.

### 문제 상황

- `/chats` 인덱스: 채널과 DM이 탭으로 구분됨
- 사이드바: 채팅 링크 하나
- 결과: 채널이 어디 있는지 모르겠다는 피드백

### 해결책

`/chats`는 DM 전용으로 만들고, 공지사항/자기소개 같은 그룹 채널은 사이드바 커뮤니티 섹션 아래 "채널" 항목으로 올렸다.

**사이드바 컴포넌트**에서 채널을 동적으로 가져오려면 데이터를 레이아웃까지 흘려보내야 한다. Rails의 `helper_method`가 깔끔한 해결책이다.

```ruby
# app/controllers/application_controller.rb
helper_method :sidebar_chat_channels

def sidebar_chat_channels
  return [] unless authenticated?

  @sidebar_chat_channels ||= current_user
    .chat_channels
    .order(:name)
    .map do |ch|
      {
        name: ch.direct_message? ? ch.display_name_for(current_user) : ch.name,
        href: "/chats/#{ch.id}",
        direct_message: ch.direct_message?
      }
    end
rescue StandardError
  []
end
```

레이아웃에서 이 helper를 컴포넌트로 전달한다.

```erb
<%# app/views/layouts/application.html.erb %>
<%= render Layout::AppShellComponent.new(
  ...
  chat_channels: sidebar_chat_channels
) %>
```

**사이드바 컴포넌트**는 채널 목록을 받아서 특정 채널만 필터링한다.

```ruby
# app/components/layout/sidebar_component.rb
ALLOWED_CHANNEL_NAMES = %w[공지사항 자기소개].freeze

def channel_sidebar_items
  return [] if @chat_channels.blank?

  @chat_channels
    .reject { |c| c[:direct_message] }
    .select { |c| ALLOWED_CHANNEL_NAMES.any? { |n| c[:name].include?(n) } }
    .map do |ch|
      {
        label: "# #{ch[:name]}",
        href: ch[:href],
        icon: "hash"
      }
    end
end
```

그리고 커뮤니티 그룹에 `children:` 키로 채널 목록을 넣는다.

```ruby
def mentee_menu_groups
  # ... 생략 ...
  if group[:group] == "커뮤니티"
    channel_items = channel_sidebar_items
    channels_parent = channel_items.any? ? [{
      id: "community_channels",
      label: "채널",
      href: nil,
      icon: "hash",
      children: channel_items
    }] : []
    next group.merge(items: [*group[:items], *channels_parent])
  end
end
```

이제 사이드바에서 커뮤니티 > 채널 > 공지사항 / 자기소개 구조로 접힌다. `/chats` 인덱스 페이지는 DM만 보여주도록 단순화했다.

```erb
<%# app/views/chat_channels/index.html.erb %>
<h1>다이렉트 메시지</h1>

<% dm_channels = @chat_channels.select(&:direct_message?) %>
<% dm_channels.each do |channel| %>
  <%= render partial: "chat_channels/channel_item", locals: { channel: channel } %>
<% end %>
```

---

## content_for로 특정 페이지 레이아웃 제어

공통 레이아웃에 "Dashboard Mode" 같은 섹션을 박아두면, 특정 페이지(예: iframe을 전체 화면으로 써야 하는 페이지)에서 그 섹션이 방해가 된다. 높이 계산이 맞지 않거나, 불필요한 여백이 생기는 것이다.

### 문제: iframe 페이지의 높이 오버플로우

인터뷰 빌더 페이지는 iframe이 화면을 꽉 채워야 했다.

```css
/* 기존 */
.interview-iframe-wrapper {
  margin: -1.5rem;          /* 레이아웃 padding 상쇄 */
  height: calc(100vh - 56px - 3rem);  /* 헤더 + py-6 */
}
```

계산 자체는 맞았는데, 공통 레이아웃에 "Dashboard Mode" 박스가 있어서 그 높이(~100px)만큼 iframe이 뷰포트를 초과해 스크롤이 생겼다.

### 해결: content_for로 조건부 렌더링

레이아웃에 `unless` 조건 하나 추가하면 된다.

```erb
<%# app/views/layouts/application.html.erb %>
<% unless content_for?(:hide_dashboard_header) %>
  <div class="mb-6 rounded-3xl border bg-white shadow-sm overflow-hidden">
    <!-- Dashboard 섹션 -->
  </div>
<% end %>
```

그리고 숨기고 싶은 페이지에서 content_for로 플래그를 세운다.

```erb
<%# app/views/mentor/interview_app/show.html.erb %>
<% content_for :title, "AI 인터뷰 빌더" %>
<% content_for :hide_dashboard_header, "1" %>
```

이걸로 해당 페이지에서만 대시보드 박스가 사라진다. 높이 계산도 원래 의도대로 작동한다.

### iframe 높이 구조 개선

동시에 iframe 래퍼 구조도 flex column으로 바꿨다. 탭바는 `flex-shrink: 0`으로 고정하고, iframe은 `flex: 1`로 나머지 공간을 차지하게 했다.

```css
.interview-page-wrapper {
  margin: -1.5rem;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 3rem);
}

.interview-tabs-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: var(--surface-primary);
  border-bottom: 1px solid var(--border-default);
}

.interview-iframe-wrapper {
  flex: 1;
  overflow: hidden;
}

.interview-iframe-wrapper iframe {
  width: 100%;
  height: 100%;
  border: none;
}
```

`height: 100%`만 쓰면 부모가 flex item이 아닐 때 제대로 계산이 안 될 수 있는데, flex column + `flex: 1` 조합은 이런 문제가 없다.

---

## 게시판 레이아웃: 2컬럼 그리드 → 단일 컬럼

커뮤니티 게시글 상세 페이지가 본문이 너무 좁아 보인다는 피드백이 있었다. 코드를 열어보니 원인이 바로 보였다.

```erb
<%# 기존 %>
<section class="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
  <!-- 본문 (55% 너비) -->
  <!-- 댓글 (45% 너비) -->
</section>
```

블로그 스타일 게시글을 2컬럼으로 나눠서 본문이 화면의 절반만 쓰고 있었다. 댓글을 옆에 두는 게 처음엔 세련돼 보였지만 긴 본문에선 오히려 답답했다.

```erb
<%# 변경 후 %>
<section class="space-y-6">
  <!-- 본문 (전체 너비) -->
  <!-- 댓글 (전체 너비, 아래 배치) -->
</section>
```

단순한 변경이지만 읽기 경험이 훨씬 나아졌다. 본문을 다 읽고 댓글로 자연스럽게 스크롤되는 흐름이다.

---

## 패턴 정리

이번 작업에서 반복적으로 나온 패턴들을 정리하면:

| 상황 | 패턴 |
|------|------|
| 내/상대 메시지 구분 | `is_mine = current_user == msg.user` + `flex-row-reverse` |
| 공통 레이아웃 데이터 공급 | `helper_method` + 레이아웃에서 컴포넌트에 주입 |
| 페이지별 레이아웃 제어 | `content_for :flag` + `content_for?(:flag)` |
| iframe 전체화면 | flex column + `flex: 1` + `margin: -padding` |
| 컨텐츠 너비 문제 | 2컬럼 grid → `space-y` 단일 컬럼 |

---

## 정리

Rails + Hotwire + ViewComponent 스택에서 채팅 UI를 iMessage 스타일로 바꾸는 건 생각보다 코드가 적다. Tailwind의 `flex-row-reverse`와 `rounded-br-sm` / `rounded-bl-sm`으로 방향과 꼬리를 잡고, CSS 변수로 색상을 토큰화해두면 다크모드까지 자연스럽게 대응된다.

`content_for` 패턴은 Rails를 쓰면서 의외로 자주 쓰게 된다. 특정 페이지에서 head에 스크립트를 추가하거나, 사이드바 메뉴를 교체하거나, 이번처럼 특정 섹션을 숨기는 데도 쓸 수 있다. 플래그 이름만 잘 짓고 레이아웃에 `content_for?` 조건을 추가하면 된다.

사이드바의 DM/채널 분리는 단순해 보이지만 UX 차이가 꽤 크다. 채널은 "내가 구독한 그룹"이고 DM은 "특정 사람과의 대화"다. 이 두 개념이 같은 공간에 섞이면 사용자 입장에서 항상 찾는 데 시간이 걸린다.

---

관련 포스트: [Rails Stimulus 컨트롤러로 마크다운 에디터 만들기](/posts/rails-stimulus-markdown-editor)
