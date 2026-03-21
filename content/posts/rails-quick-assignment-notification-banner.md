---
title: "Rails 깜짝 과제 기능 + 1회성 알림 배너 — 기존 모델 재활용과 localStorage 활용"
date: 2026-03-12
draft: false
tags: ["Rails", "Turbo", "JavaScript", "localStorage", "ViewComponent", "UX"]
description: "스터디 운영 중 즉석 과제를 빠르게 만들고 멘티에게 1회성 알림 배너로 알려주는 기능을 구현했다. 새 모델 없이 기존 Assignment/Submission 시스템을 재활용하고, localStorage로 배너 dismiss 상태를 관리한 과정을 정리한다."
cover:
  image: ""
  alt: "Rails Quick Assignment Notification Banner"
  hidden: true
categories: ["Rails"]
---

스터디를 운영하다 보면 세션 중간에 즉석으로 과제를 내야 할 때가 있다. 기존 관리자 페이지를 통하면 여러 단계를 거쳐야 하고, 멘티들은 새 과제가 생긴 걸 바로 알 수 없다는 문제가 있었다.

이 글에서는 **새 모델 없이 기존 시스템을 재활용**하여 깜짝 과제 기능을 만들고, **1회성 알림 배너**로 멘티에게 즉시 알려주는 구현 과정을 정리한다.

---

## 문제 정의

1. **과제 생성이 느리다**: 관리자 대시보드에서 여러 필드를 채워야 한다
2. **멘티가 모른다**: 새 과제가 생겨도 목록을 직접 확인하기 전까지 알 수 없다
3. **1회성이어야 한다**: 알림을 본 뒤에는 다시 보여주지 않아야 한다

---

## 설계 결정: 새 모델 vs 기존 모델 재활용

처음에는 `QuickAssignment`나 `Notification` 같은 새 모델을 만들 수 있었지만, 분석해보니 기존 구조로 충분했다.

```
기존 모델 구조
├── Assignment (title, description, due_at, submission_type, published)
├── Submission (user_id, assignment_id, status, content)
└── StudySession (title, session_date)
```

깜짝 과제는 결국 **`published: true`로 즉시 공개되는 Assignment**일 뿐이다. 제출/피드백 흐름도 기존 Submission 시스템을 그대로 쓰면 된다.

**YAGNI 원칙 적용**: 새 테이블, 마이그레이션, 모델, 연관관계를 만들 필요 없이 컨트롤러 액션 2개와 뷰 1개만 추가하면 된다.

---

## 구현 1: 깜짝 과제 생성

### 라우팅

```ruby
resources :assignments, only: [:index, :show] do
  collection do
    get  :quick_new
    post :quick_create
  end
end
```

`collection` 라우트로 `/assignments/quick_new`와 `/assignments/quick_create`를 추가했다. 기존 Assignment 리소스 안에 넣어서 URL 구조를 일관되게 유지한다.

### 컨트롤러

```ruby
before_action :require_admin_or_mentor_admin, only: [:quick_new, :quick_create]

def quick_new
  @assignment = Assignment.new(
    submission_type: :mixed,
    published: true,
    max_file_size_mb: 50,
    allowed_extensions: "pdf,docx,pptx,hwp,png,jpg,jpeg"
  )
  @study_sessions = current_cohort.study_sessions.ordered
end

def quick_create
  @assignment = Assignment.new(quick_assignment_params)
  @assignment.published = true

  if @assignment.save
    redirect_to assignment_path(@assignment), notice: "깜짝 과제가 생성되었습니다!"
  else
    @study_sessions = current_cohort.study_sessions.ordered
    render :quick_new, status: :unprocessable_entity
  end
end
```

핵심은 `published: true`를 강제하는 것이다. 일반 과제는 관리자가 공개 여부를 선택하지만, 깜짝 과제는 생성 즉시 공개되어야 한다.

권한은 `admin`과 `mentor_admin`만 허용한다. 일반 멘토는 과제를 만들 수 없다.

### 마감 시간 프리셋 UI

폼에서 가장 고민한 부분은 마감 시간 입력이다. `datetime-local` 입력만으로는 즉석 상황에서 불편하므로 프리셋 버튼을 추가했다.

```javascript
function setDeadline(hours) {
  const d = new Date();
  d.setHours(d.getHours() + hours);
  setDateInput(d);
}

function setDeadlineToday() {
  const d = new Date();
  d.setHours(23, 59, 0, 0);
  setDateInput(d);
}
```

`1시간 후`, `3시간 후`, `오늘 23:59`, `내일 23:59` — 4개 프리셋으로 대부분의 시나리오를 커버한다. 프리셋을 누르면 `datetime-local` input에 값이 채워지면서 버튼이 하이라이트된다.

### 제출 방식 라디오 카드

```erb
<% { mixed: "전부 가능", url_only: "URL만",
     file_only: "파일만", text_only: "텍스트만" }.each do |value, label| %>
  <label style="...">
    <input type="radio" name="assignment[submission_type]" value="<%= value %>"
           <%= "checked" if @assignment.submission_type == value.to_s %>>
    <div><%= label %></div>
  </label>
<% end %>
```

기존 Assignment 모델의 `submission_type` enum을 그대로 활용한다. 2x2 그리드 라디오 카드 UI로 시각적 선택감을 높였다.

---

## 구현 2: 1회성 알림 배너

### 서버 사이드 필터링

```erb
<% new_assignments = @assignments.select { |a| a.created_at > 24.hours.ago } %>
<% if new_assignments.any? && !current_user.admin? && !current_user.mentor? %>
  <% new_assignments.each do |na| %>
    <% next if na.submission_for(current_user) %>
    <!-- 배너 HTML -->
  <% end %>
<% end %>
```

3중 필터를 적용한다:

1. **시간 필터**: 24시간 이내 생성된 과제만
2. **역할 필터**: 멘티에게만 표시 (관리자/멘토 제외)
3. **제출 필터**: 이미 제출한 과제는 배너 미노출

### 클라이언트 사이드 dismiss

```javascript
function dismissBanner(id) {
  var el = document.getElementById('banner-' + id);
  if (el) {
    el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    el.style.opacity = '0';
    el.style.transform = 'translateY(-8px)';
    setTimeout(function() { el.remove(); }, 300);
  }
  var dismissed = JSON.parse(localStorage.getItem('dismissed_banners') || '[]');
  if (dismissed.indexOf(id) === -1) {
    dismissed.push(id);
    localStorage.setItem('dismissed_banners', JSON.stringify(dismissed));
  }
}
```

**왜 localStorage인가?**

- DB에 `notification_reads` 테이블을 만들면 마이그레이션, 모델, API가 필요하다
- 이 배너는 24시간만 노출되는 일시적 UI이다
- 사용자가 브라우저를 바꾸면 다시 보여도 큰 문제가 없다
- localStorage는 즉시 동작하고 서버 요청이 없다

### Turbo 호환성

```javascript
function hideDismissedBanners() {
  var dismissed = JSON.parse(localStorage.getItem('dismissed_banners') || '[]');
  dismissed.forEach(function(id) {
    var el = document.getElementById('banner-' + id);
    if (el) el.remove();
  });
}

document.addEventListener('turbo:load', hideDismissedBanners);
document.addEventListener('DOMContentLoaded', hideDismissedBanners);
```

Rails + Turbo 환경에서는 `DOMContentLoaded`만으로는 부족하다. Turbo가 페이지를 교체할 때는 `turbo:load` 이벤트를 사용해야 한다. 두 이벤트를 모두 리스닝하면 첫 방문과 Turbo 네비게이션 모두에서 정상 동작한다.

### CSS 애니메이션

```css
@keyframes banner-slide-in {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

배너가 등장할 때 위에서 아래로 살짝 슬라이드하면서 나타나고, dismiss할 때는 반대 방향으로 사라진다. 간단하지만 UI 피드백으로 충분하다.

---

## 삽질 포인트

### 1. WKWebView에서 CSS custom properties

iOS 앱이 WKWebView로 웹을 보여주는 구조라서 CSS 관련 주의가 필요했다. `color-mix()` 함수는 Safari 16.4+에서 지원하는데, WKWebView의 iOS 버전에 따라 지원 여부가 달라진다. 이 프로젝트는 iOS 16+ 타겟이라 문제없었지만, 더 낮은 버전을 지원해야 한다면 fallback이 필요하다.

```css
/* color-mix 사용 — iOS 16.4+ WKWebView에서 동작 */
background: linear-gradient(135deg,
  color-mix(in srgb, var(--color-primary-500) 8%, white),
  color-mix(in srgb, var(--color-primary-500) 14%, white));
```

### 2. 사이드바 역할 분기 누락

처음에는 사이드바 메뉴가 `admin`과 `mentor` 두 역할만 체크하고 있었다. `mentor_admin`이나 `ops_admin` 역할의 사용자는 관리자 메뉴를 볼 수 없는 버그가 있었다.

```ruby
# Before — mentor_admin이 관리 메뉴를 못 봄
groups.concat(ADMIN_EXTRA) if @current_user_role == "admin"
groups.concat(mentor_extra) if %w[admin mentor].include?(@current_user_role)

# After — 역할별 정확한 분기
def admin_role?
  %w[admin mentor_admin ops_admin].include?(@current_user_role)
end

def mentor_capable_role?
  %w[admin mentor mentor_admin].include?(@current_user_role)
end
```

역할이 2개를 넘어가면 개별 비교 대신 메서드로 추출하는 게 읽기도 좋고 실수도 줄어든다.

### 3. Turbo에서 이벤트 리스너 중복

`DOMContentLoaded`와 `turbo:load`를 모두 걸면 첫 페이지 로드 시 `hideDismissedBanners()`가 두 번 호출될 수 있다. 하지만 이 함수는 DOM에서 요소를 제거하는 것이라 두 번 호출되어도 두 번째 실행 시 이미 요소가 없으므로 안전하다. 멱등성(idempotency)이 보장되는 설계다.

---

## 정리

| 항목 | 선택 | 이유 |
|------|------|------|
| 새 모델 | X | 기존 Assignment/Submission으로 충분 |
| Notification 테이블 | X | 24시간짜리 일시 UI에 과도 |
| localStorage | O | 서버 요청 없이 즉시 동작 |
| collection 라우트 | O | 기존 리소스 구조 유지 |
| Turbo 이벤트 | O | SPA 네비게이션 대응 필수 |

핵심 교훈: **기존 시스템을 최대한 재활용하고, 일시적 UI 상태는 클라이언트에서 관리한다.** 새 테이블과 마이그레이션을 추가하기 전에 기존 모델의 속성만으로 해결할 수 있는지 먼저 검토하자.
