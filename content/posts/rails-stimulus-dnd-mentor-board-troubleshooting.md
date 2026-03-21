---
title: "Rails + Stimulus 드래그앤드롭 멘토 배정 보드에서 만난 삽질 5가지"
date: 2026-03-12
draft: false
tags: ["Rails 8", "Stimulus", "DnD", "importmap", "iOS", "WKWebView", "세션 쿠키", "ViewComponent"]
description: "Stimulus 컨트롤러가 로드 안 되는 문제, 디자인 토큰 배경색 충돌, iOS 앱 세션 쿠키 만료, 토글 버튼 조건부 렌더링 함정까지 — 하루 동안 만난 실전 버그 5가지를 정리했다."
cover:
  image: "/images/og/rails-stimulus-dnd-mentor-board-troubleshooting.png"
  alt: "Rails Stimulus DnD Mentor Board Troubleshooting"
  hidden: true
categories: ["Rails", "Hotwire"]
---

Rails 8 앱에서 멘토-팀 배정을 드래그앤드롭으로 관리하는 보드를 만들었다. Stimulus 컨트롤러 + `fetch` + 서버 사이드 HTML 교체 방식이었는데, "되는 줄 알았던" 기능들이 프로덕션에서 하나씩 터졌다.

---

## 1. Stimulus 컨트롤러가 아예 로드 안 됨

### 증상

`data-controller="mentor-assignment-board"`를 붙였는데 드래그가 안 먹는다. 브라우저 콘솔에 에러도 없다.

### 원인

`importmap-rails`를 쓰는 프로젝트에서 **한 번이라도 `rails assets:precompile`을 실행**하면 `public/assets/` 디렉토리가 생긴다. 이후 개발 환경에서도 Rails는 이 정적 파일을 우선 서빙한다.

문제는 precompile 시점에 존재하지 않았던 Stimulus 컨트롤러들이 `public/assets/`에 없다는 것. Rails가 `public/assets/`를 먼저 보기 때문에, `app/javascript/controllers/`에 있는 새 파일을 무시한다.

```
Importmap skipped missing path: controllers/mentor_assignment_board_controller.js
```

### 해결

```bash
rm -rf public/assets
```

개발 환경에서는 `public/assets/`가 없어야 importmap이 `app/javascript/`를 직접 참조한다. CI/CD에서만 precompile이 돌아야 한다.

### 교훈

> importmap 프로젝트에서 Stimulus 컨트롤러가 인식 안 되면, 제일 먼저 `public/assets/` 존재 여부를 확인하라.

---

## 2. 카드 배경색이 페이지 배경과 합쳐짐

### 증상

멘토 제출 리뷰 페이지에서 카드 헤더가 페이지 배경에 녹아들어 경계가 보이지 않았다. "디자인이 적용 안 된 것 같다"는 피드백.

### 원인

CSS 디자인 토큰 시스템에서:
- 페이지 배경: `--surface-secondary` (`#fafaf9`)
- 카드 헤더: `--surface-secondary` (`#fafaf9`)

같은 토큰을 두 곳에 썼으니 당연히 구분이 안 된다.

### 해결

카드 헤더를 `--surface-tertiary`(`#f5f5f4`)로 변경하고, 전체 콘텐츠를 `--surface-primary`(흰색) 카드로 감쌌다.

```erb
<!-- 전체를 흰색 카드로 감싸기 -->
<section class="rounded-3xl border p-6"
  style="background: var(--surface-primary); border-color: var(--border-default);">

  <!-- 필터 탭은 tertiary -->
  <div style="background: var(--surface-tertiary);">
    ...
  </div>
</section>
```

### 교훈

> 디자인 토큰은 "이름"이 아니라 "실제 값의 차이"를 확인해야 한다. 토큰 이름이 달라도 값이 같으면 시각적 구분이 없다.

---

## 3. iOS 앱 로그인이 계속 풀림

### 증상

WKWebView 기반 iOS 앱에서 로그인 후 앱을 종료하고 다시 열면 로그인이 풀려있다. 웹 브라우저에서는 문제없다.

### 원인

Rails 기본 세션 쿠키는 **브라우저 세션 쿠키**(만료 시간 없음)다. 일반 브라우저는 탭을 닫아도 세션을 유지하지만, **WKWebView는 앱 프로세스가 종료되면 세션 쿠키를 삭제**한다.

### 해결

`config/initializers/session_store.rb`를 만들어 영속 쿠키로 변경:

```ruby
Rails.application.config.session_store :cookie_store,
  key: "_app_session",
  expire_after: 30.days
```

`expire_after`를 지정하면 `Set-Cookie` 헤더에 `Max-Age`가 추가되어 WKWebView도 디스크에 쿠키를 저장한다.

### 교훈

> 네이티브 앱 래퍼(WKWebView, Android WebView)를 쓸 때는 세션 쿠키의 영속성을 반드시 확인하라. 브라우저와 동작이 다르다.

---

## 4. 조건부 렌더링으로 + 버튼이 사라짐

### 증상

멘토 배정 보드의 각 팀 카드에 "멘토 추가" 버튼(+)을 넣었는데, 특정 팀에서 버튼이 보이지 않는다.

### 원인

```erb
<% addable_mentors = all_mentors.reject { |m| assigned_ids.include?(m.id) } %>
<% if addable_mentors.any? %>
  <!-- + 버튼 -->
<% end %>
```

"이미 배정된 멘토를 제외한 목록"이 비면 버튼 자체가 사라진다. 그런데 **한 멘토가 여러 팀에 동시 배정 가능**한 구조였다. 모든 멘토가 해당 팀에 이미 있으면 버튼이 없어지고, 실수로 빼버린 멘토를 다시 넣을 방법이 없어진다.

### 해결

+ 버튼을 **항상 표시**하고, 드롭다운에 전체 멘토 목록을 보여주되 **이미 배정된 멘토는 체크 표시**, 미배정은 점으로 구분:

```erb
<%# 항상 표시 — 조건 없음 %>
<div class="relative">
  <button type="button" title="멘토 추가/제거">+</button>
  <div class="dropdown">
    <% all_mentors.each do |mentor| %>
      <% assigned = assigned_ids.include?(mentor.id) %>
      <button data-action="click->board#toggleMentor"
              data-assigned="<%= assigned %>">
        <%= assigned ? "✓" : "●" %> <%= mentor.name %>
      </button>
    <% end %>
  </div>
</div>
```

Stimulus 액션도 `addMentor`에서 `toggleMentor`로 변경. 배정됨 → 클릭하면 제거, 미배정 → 클릭하면 추가:

```javascript
async toggleMentor(event) {
  const { mentorId, targetTeamId, assigned } = event.currentTarget.dataset
  const isAssigned = assigned === "true"

  // 배정됨 → 제거 (팀→미배정), 미배정 → 추가 (미배정→팀)
  const sourceTeamId = isAssigned ? targetTeamId : ""
  const destTeamId = isAssigned ? "" : targetTeamId

  const response = await fetch(this.urlValue, {
    method: "PATCH",
    headers: { /* CSRF + JSON */ },
    body: JSON.stringify({
      mentor_id: mentorId,
      source_team_id: sourceTeamId,
      target_team_id: destTeamId
    })
  })

  // 서버에서 갱신된 HTML 반환 → innerHTML 교체
  const data = await response.json()
  this.boardTarget.innerHTML = data.html
}
```

### 교훈

> "추가할 대상이 없으면 버튼을 숨긴다"는 논리가 항상 옳지 않다. 다대다 관계에서는 토글 패턴이 더 유연하다.

---

## 5. 권한 조건에서 역할 하나 빠뜨림

### 증상

관리자는 보이는 "빠른 과제 만들기" 버튼이 멘토에게는 보이지 않는다.

### 원인

뷰와 컨트롤러 양쪽에서 `admin? || mentor_admin?`만 체크하고 `mentor?`를 빠뜨렸다.

```ruby
# 컨트롤러
def require_admin_or_mentor_admin
  unless current_user.admin? || current_user.mentor_admin?
    redirect_to root_path, alert: "권한이 없습니다."
  end
end
```

```erb
<!-- 뷰 -->
<% if current_user.admin? || current_user.mentor_admin? %>
  <%= link_to "빠른 과제 만들기", quick_new_path %>
<% end %>
```

### 해결

양쪽 모두에 `current_user.mentor?` 추가.

### 교훈

> 권한 체크는 뷰와 컨트롤러 **양쪽을 반드시 동시에 수정**해야 한다. 한쪽만 고치면 버튼은 보이는데 접근 불가이거나, 접근은 되는데 버튼이 안 보이는 상태가 된다.

---

## 정리

| 문제 | 근본 원인 | 해결 시간 |
|------|-----------|-----------|
| Stimulus 미로드 | `public/assets/` 잔재 | 10분 |
| 카드 배경 합쳐짐 | 같은 토큰 값 사용 | 15분 |
| iOS 로그인 풀림 | 세션 쿠키 영속성 | 5분 |
| + 버튼 사라짐 | 조건부 렌더링 함정 | 30분 |
| 권한 누락 | 뷰/컨트롤러 불일치 | 5분 |

하루에 5가지를 만났지만, 각각은 코드 몇 줄 수정으로 해결됐다. 문제는 **원인 파악까지의 시간**이다. "왜 안 되지?"에서 "아, 이거였네"까지의 간극을 줄이는 게 경험이라는 걸 다시 느꼈다.
