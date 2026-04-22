---
title: "Rails Turbo Frame으로 탭 SPA 만들기 -- 빈 페이지 함정과 해결법"
date: 2026-03-25
draft: false
tags: ["rails", "turbo-frame", "hotwire", "spa", "debugging"]
categories: ["Rails"]
description: "Rails Turbo Frame으로 탭 기반 SPA를 구현할 때 빈 페이지가 나오는 원인과 target _top, inline empty state 등 실전 해결 패턴을 정리했다."
---

## 상황: Turbo Frame 탭 UI에서 빈 페이지

Rails 8에서 인터뷰 빌더를 만들고 있었다. 하나의 페이지 안에 "내 인터뷰 작성", "전체 갤러리", "인터뷰 결과" 같은 탭을 두고, 탭을 클릭하면 콘텐츠 영역만 바뀌는 SPA 느낌의 UI였다.

구조는 이랬다:

```erb
<%# interview_app/show.html.erb — 탭 셸 %>
<nav>
  <button onclick="switchTab('wizard')">내 인터뷰</button>
  <button onclick="switchTab('gallery')">갤러리</button>
  <button onclick="switchTab('result')">결과</button>
</nav>

<turbo-frame id="interview-rails-content" src="/interviews/wizard" loading="lazy">
  <p>로딩 중...</p>
</turbo-frame>
```

탭을 클릭하면 JavaScript로 `railsFrame.src`를 바꿔서 콘텐츠를 교체한다. wizard, gallery, show 세 뷰 모두 같은 `turbo_frame_tag "interview-rails-content"`로 감싸져 있어서 frame ID가 매칭되고, 콘텐츠가 자연스럽게 스왑된다.

여기까지는 잘 동작했다. 문제는 갤러리에서 특정 인터뷰 카드를 클릭하거나, wizard의 "프레젠테이션" 탭을 누를 때 빈 페이지가 나온 것이다.

---

## Turbo Frame의 핵심 규칙 — 왜 빈 페이지가 나오는가

Turbo Frame에는 간단하지만 강력한 규칙이 있다:

> **frame 안의 링크를 클릭하면, 응답에서 같은 ID의 frame을 찾아 콘텐츠를 교체한다. 못 찾으면 에러.**

Turbo 7.3부터는 매칭되는 frame이 없으면 "Content missing" 에러를 콘솔에 찍고, 프레임 내용이 **비워진다**. 이전 7.2에서는 자동으로 전체 페이지 리로드를 시도했지만, 이 동작이 제거됐다.

브라우저 콘솔에 이런 에러가 찍힌다:

```
Uncaught (in promise) Error: The response (200) did not contain
the expected <turbo-frame id="interview-rails-content"> and will be ignored.
```

이건 세 가지 상황에서 발생한다:

| 상황 | 원인 | 결과 |
|------|------|------|
| frame 안 링크 → 매칭 frame 없는 페이지 | 응답에 `turbo-frame` 태그 없음 | 빈 프레임 |
| frame 안 폼 제출 → redirect | redirect된 페이지에 매칭 frame 없음 | 빈 프레임 |
| 세션 만료 → 로그인 리다이렉트 | 로그인 페이지에 매칭 frame 없음 | 빈 프레임 |

---

## 내가 겪은 구체적인 문제 두 가지

### 문제 1: 갤러리 카드 클릭 → show 페이지

갤러리(index)가 turbo frame 안에서 로드되고, 카드에 `link_to`가 걸려 있었다:

```erb
<%# interviews/index.html.erb %>
<%= turbo_frame_tag "interview-rails-content" do %>
  <% @interviews.each do |interview| %>
    <%= link_to interview_path(interview), class: "card" do %>
      <%= interview.display_name %>
    <% end %>
  <% end %>
<% end %>
```

카드를 클릭하면 Turbo가 `/interviews/2`를 fetch하고, 응답에서 `interview-rails-content` frame을 찾는다. show 페이지에도 같은 frame이 있으므로 콘텐츠가 교체된다 — **여기까진 정상**.

문제는 show 페이지 안에서 "갤러리로 돌아가기" 같은 링크를 클릭할 때다. 이 링크도 frame 안에 있으므로 Turbo가 frame 내에서 처리하려고 한다. 만약 대상 페이지에 매칭 frame이 없으면 빈 프레임이 된다.

### 문제 2: wizard의 6번 탭(프레젠테이션)

wizard 뷰에는 슬라이드 1~5 탭과 6번 "프레젠테이션" 탭이 있었다. 6번은 별도 페이지(`/interviews/:id`)로 이동하는 링크였다:

```erb
<%= link_to interview_path(@interview),
    data: { turbo_frame: "_top" } do %>
  <span>6</span> 프레젠테이션
<% end %>
```

`data-turbo-frame="_top"`을 줬으니 전체 페이지 네비게이션이 되어야 한다. 그런데 show 페이지 전체가 `turbo_frame_tag`로 감싸져 있었다. 전체 페이지 로드 시 `<turbo-frame>` 커스텀 엘리먼트는 자식을 정상적으로 렌더링하지만, 그 안에서 링크를 클릭하면 다시 frame 안 네비게이션이 된다.

---

## 해결법 1: `target: "_top"` — frame 탈출의 기본기

가장 직관적인 해결법이다. frame 안의 모든 링크가 전체 페이지로 네비게이션하게 만든다:

```erb
<%# 방법 A: 개별 링크에 적용 %>
<%= link_to "갤러리로 돌아가기", interviews_path,
    data: { turbo_frame: "_top" } %>

<%# 방법 B: frame 자체에 target 설정 (안의 모든 링크에 적용) %>
<%= turbo_frame_tag "interview-rails-content", target: "_top" do %>
  <%# 이 안의 모든 링크는 전체 페이지 네비게이션 %>
<% end %>
```

방법 B를 쓰면 frame 안의 **모든** 링크와 폼이 전체 페이지를 대상으로 한다. 폼 validation 에러를 frame 안에서 보여주고 싶다면 이 방법은 안 맞는다. 하지만 "결과 보기" 같은 읽기 전용 페이지에서는 완벽하다.

실제로 적용한 코드:

```erb
<%# interviews/show.html.erb %>
<%= turbo_frame_tag "interview-rails-content", target: "_top" do %>
  <%# 프로필 헤더 %>
  <div class="profile-header">
    <%= @interview.display_name %>의 AI 여정 요약
  </div>

  <%# 슬라이드 섹션들 %>
  <% sections.each do |section| %>
    <%# ... 내용 렌더링 ... %>
  <% end %>
<% end %>
```

이렇게 하면:
- 탭 셸(interview_app)의 turbo frame이 show 콘텐츠를 로드할 때 → frame 매칭으로 정상 스왑
- show 안의 링크를 클릭할 때 → `target="_top"` 덕분에 전체 페이지 네비게이션
- 직접 `/interviews/2`로 접근할 때 → turbo-frame 커스텀 엘리먼트가 자식을 정상 렌더링

---

## 해결법 2: 하이브리드 탭 — turbo frame + inline 콘텐츠 전환

모든 탭이 서버에서 콘텐츠를 가져올 필요는 없다. "게시된 인터뷰가 없습니다" 같은 빈 상태(empty state)를 보여줘야 할 때, 서버 요청 없이 클라이언트에서 바로 보여줄 수 있다.

```erb
<%# 탭 정의 — 서버 로드(turbo) vs 인라인(inline_empty) %>
<%
  all_tabs = []
  all_tabs << { key: "wizard", label: "내 인터뷰 작성",
                src_type: "turbo", src: wizard_interviews_path }
  all_tabs << { key: "gallery", label: "전체 갤러리",
                src_type: "turbo", src: interviews_path }

  if @published_interview
    all_tabs << { key: "result", label: "인터뷰 결과",
                  src_type: "turbo", src: interview_path(@published_interview) }
  else
    all_tabs << { key: "result_empty", label: "인터뷰 결과",
                  src_type: "inline_empty" }
  end
%>
```

HTML에는 turbo frame과 inline empty state div를 나란히 두고, JavaScript로 전환한다:

```html
<div id="content-area">
  <!-- 서버 콘텐츠용 turbo frame -->
  <turbo-frame id="interview-rails-content"
               src="/interviews/wizard" loading="lazy">
    <p>로딩 중...</p>
  </turbo-frame>

  <!-- 인라인 빈 상태 (초기에는 숨김) -->
  <div id="empty-state" style="display: none;">
    <h3>아직 게시된 인터뷰가 없습니다</h3>
    <p>인터뷰를 작성하고 게시하면 여기에 결과가 표시됩니다.</p>
    <button onclick="switchTab('wizard')">
      인터뷰 작성하러 가기
    </button>
  </div>
</div>
```

JavaScript 전환 로직:

```javascript
function switchTab(tabKey) {
  // 탭 버튼 active 상태 업데이트
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.tab === tabKey);
  });

  const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabKey}"]`);
  const srcType = activeBtn?.dataset.srcType;
  const railsFrame = document.getElementById('interview-rails-content');
  const emptyState = document.getElementById('empty-state');

  if (srcType === 'turbo') {
    // 서버 콘텐츠: turbo frame 표시
    railsFrame.style.display = '';
    emptyState.style.display = 'none';

    const src = activeBtn.dataset.src;
    if (src && railsFrame.src !== src) {
      railsFrame.src = src;  // frame src 변경 → 자동 fetch
    }
  } else if (srcType === 'inline_empty') {
    // 인라인 빈 상태: turbo frame 숨기고 div 표시
    railsFrame.style.display = 'none';
    emptyState.style.display = '';
  }
}
```

이 패턴의 장점:
- `@published_interview`가 nil일 때 `interview_path(nil)`로 에러 나는 걸 방지
- 빈 상태를 보여주기 위해 서버 요청을 하지 않음
- "인터뷰 작성하러 가기" 버튼으로 다른 탭으로 즉시 전환 가능

---

## Turbo Frame 탭 구현의 5가지 함정

실전에서 여러 번 걸려 넘어진 것들을 정리했다.

### 1. frame 안 링크의 기본 동작

frame 안의 모든 `<a>` 태그와 `<form>`은 **자동으로 frame 내 네비게이션**이 된다. 이건 Turbo의 핵심 설계다. frame 밖으로 나가려면 반드시 명시적으로 지정해야 한다.

```erb
<%# 이 링크는 frame 안에서 처리됨 (기본 동작) %>
<%= link_to "상세보기", interview_path(interview) %>

<%# 이 링크는 전체 페이지 네비게이션 %>
<%= link_to "상세보기", interview_path(interview),
    data: { turbo_frame: "_top" } %>
```

### 2. Turbo 7.3의 breaking change

Turbo 7.2까지는 매칭 frame을 못 찾으면 자동으로 전체 페이지를 다시 로드했다. 7.3부터 이 동작이 제거되고 "Content missing" 에러만 표시된다. 7.2에서 동작하던 코드가 7.3 업그레이드 후 갑자기 빈 페이지가 나올 수 있다.

### 3. `turbo-visit-control` meta 태그의 이중 요청

로그인 페이지처럼 항상 전체 페이지로 로드돼야 하는 페이지에는 `turbo_page_requires_reload` 헬퍼를 쓸 수 있다:

```erb
<%# 로그인 페이지 상단에 추가 %>
<% turbo_page_requires_reload %>
```

하지만 이 방법은 GET 요청이 **두 번** 발생한다. Turbo가 frame 요청으로 페이지를 받고, meta 태그를 발견하고, 전체 페이지 로드를 다시 시도하기 때문이다. 성능이 중요하다면 `turbo:frame-missing` 이벤트를 직접 처리하는 게 낫다.

### 4. `turbo:frame-missing` 이벤트 글로벌 핸들러

매칭 frame이 없을 때 자동으로 전체 페이지 방문으로 전환하는 글로벌 핸들러:

```javascript
document.addEventListener("turbo:frame-missing", event => {
  if (event.detail.response.redirected) {
    event.preventDefault();
    event.detail.visit(event.detail.response);
  }
});
```

이 코드는 redirect 응답일 때만 전체 페이지 방문을 시도한다. 모든 `frame-missing`에 대해 `preventDefault()`를 걸면, 정당한 에러까지 무시하게 되니 조건을 꼭 넣어야 한다.

### 5. lazy loading frame의 src 변경 타이밍

`loading="lazy"`인 frame은 뷰포트에 보일 때만 로드된다. 하지만 JavaScript로 `frame.src`를 변경하면 lazy 설정과 무관하게 **즉시** 요청이 발생한다. 탭 전환 시 `frame.src`를 바꾸는 건 lazy 속성과 충돌하지 않는다.

```javascript
// lazy frame이라도 src 변경 시 즉시 fetch
const frame = document.getElementById('my-frame');
frame.src = '/new-content';  // 즉시 요청 발생
```

---

## Turbo Frame vs Turbo Stream — 탭 UI에는 뭘 써야 하나

| 기준 | Turbo Frame | Turbo Stream |
|------|-------------|-------------|
| 업데이트 대상 | 단일 영역 | 여러 영역 동시 |
| 동작 방식 | frame ID 매칭으로 교체 | action(append, replace 등) 지정 |
| 탭 UI 적합성 | 좋음 — 하나의 콘텐츠 영역 교체 | 과함 — 단일 영역에는 불필요 |
| 활성 탭 표시 | 별도 JS 필요 | Stream으로 탭 UI도 업데이트 가능 |
| URL 변경 | frame 네비게이션은 URL 안 바뀜 | Stream은 URL과 무관 |

탭 UI는 "하나의 영역을 교체"하는 전형적인 Turbo Frame 유스케이스다. 다만 활성 탭 표시는 Turbo Frame만으로 안 되므로 JavaScript(Stimulus)를 조합해야 한다. 활성 탭 + 콘텐츠를 동시에 업데이트하고 싶다면 Turbo Stream이 더 깔끔할 수 있지만, 대부분의 경우 Frame + 약간의 JS면 충분하다.

---

## frame 안에서 `target` 속성의 동작 정리

`target` 속성이 어디에 붙느냐에 따라 동작이 달라진다:

```erb
<%# 1. frame 자체에 target="_top" %>
<%= turbo_frame_tag "content", target: "_top" do %>
  <%# 안의 모든 링크/폼 → 전체 페이지 네비게이션 %>
  <%= link_to "링크", some_path %>  <%# → 전체 페이지 %>
<% end %>

<%# 2. 개별 링크에 data-turbo-frame %>
<%= turbo_frame_tag "content" do %>
  <%# 기본: frame 안 네비게이션 %>
  <%= link_to "A", path_a %>  <%# → frame 안에서 교체 %>

  <%# 이것만 전체 페이지 %>
  <%= link_to "B", path_b, data: { turbo_frame: "_top" } %>
<% end %>

<%# 3. 다른 frame 타겟팅 %>
<%= link_to "C", path_c, data: { turbo_frame: "other-frame" } %>
<%# → "other-frame" ID를 가진 frame의 콘텐츠 교체 %>
```

중요한 점: **원래 frame의 `target` 속성은 보존된다**. frame의 콘텐츠가 교체되어도 `target="_top"`은 원래 frame 엘리먼트에 남아있다. 응답으로 온 frame의 `target`이 아니라, 페이지에 원래 있던 frame의 `target`이 적용된다.

---

## 최종 아키텍처: 탭 셸 패턴

이 경험을 바탕으로 정리한 탭 셸 패턴이다:

```
탭 셸 (interview_app/show.html.erb)
├─ 탭 네비게이션 (JavaScript로 탭 전환)
│
├─ Turbo Frame (서버 콘텐츠)
│  ├─ wizard 뷰 ← turbo_frame_tag 매칭
│  ├─ gallery 뷰 ← turbo_frame_tag 매칭
│  └─ show 뷰   ← turbo_frame_tag + target="_top"
│
├─ Empty State DIV (인라인 콘텐츠)
│  └─ "게시된 인터뷰가 없습니다" + CTA 버튼
│
└─ iframe (외부 React 앱, 필요한 경우)
```

탭 전환 시:
1. **turbo** 타입: `railsFrame.src` 변경 → Turbo가 자동으로 fetch + 스왑
2. **inline_empty** 타입: turbo frame 숨기고 빈 상태 div 표시
3. **iframe** 타입: turbo frame 숨기고 iframe 표시

이 패턴으로 서버 렌더링, 클라이언트 빈 상태, 외부 앱을 하나의 탭 UI에 자연스럽게 섞을 수 있다.

---

## 교훈

Turbo Frame은 단순해 보이지만 "frame 안의 링크는 frame 안에서 처리된다"는 규칙을 놓치면 삽질한다. 특히 Turbo 7.3 이후 매칭 frame이 없을 때의 동작이 "자동 폴백"에서 "에러"로 바뀐 건 꽤 큰 breaking change였다.

빈 페이지 디버깅 시 가장 먼저 할 일은 **브라우저 콘솔을 확인**하는 것이다. Turbo는 "Content missing" 에러를 콘솔에 친절하게 찍어준다. 네트워크 탭에서는 200 OK가 뜨는데 화면이 비어있다면, 십중팔구 frame 매칭 실패다.

`target="_top"`은 은탄환이 아니다. frame 안에서 폼 validation 에러를 보여줘야 하는 경우에는 쓸 수 없다. 상황에 따라 `target="_top"`, `turbo:frame-missing` 이벤트, `turbo-visit-control` meta 태그를 적절히 골라 써야 한다.
