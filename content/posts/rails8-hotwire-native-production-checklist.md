---
title: "Rails 8 + Hotwire Native iOS 실전 삽질 체크리스트 — 세션, CSRF, 채팅, 코트맵까지"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Hotwire Native", "Turbo Native", "iOS", "WKWebView", "CSRF", "ActionCable", "Tailwind CSS 4"]
description: "Rails 8 + Hotwire Native iOS 앱을 만들면서 겪은 실전 이슈 10가지. 세션 쿠키 영속성, CSRF 토큰 핸들링, ActionCable 인증 불일치, 채팅 스크롤 FAB, 코트맵 기능까지 해결 과정을 정리했다."
cover:
  image: "/images/og/rails8-hotwire-native-production-checklist.png"
  alt: "Rails 8 Hotwire Native Production Checklist"
  hidden: true
---

Rails 8 + Hotwire Native로 iOS 앱을 만들면서 겪은 실전 이슈들을 정리했다. 공식 문서에 안 나오는 것들 위주로.

---

## 1. WKWebView 세션 쿠키가 앱 종료 시 날아간다

### 증상
앱을 완전히 종료(kill) 후 재실행하면 로그인이 풀린다.

### 원인
Rails 기본 `cookie_store`는 만료 시간이 없는 **세션 쿠키**를 생성한다. WKWebView는 앱 종료 시 세션 쿠키를 삭제할 수 있다.

### 해결
```ruby
# config/initializers/session_store.rb
Rails.application.config.session_store :cookie_store,
  key: "_app_session",
  expire_after: 30.days,
  same_site: :lax
```

`expire_after`를 설정하면 **영속 쿠키**가 되어 앱 종료 후에도 유지된다.

> `same_site: :strict`는 절대 사용하지 말 것. WKWebView에서 쿠키 전송이 안 된다.

---

## 2. API 컨트롤러에서 CSRF 토큰 문제

### 증상
네이티브 앱에서 `POST /api/v1/device_tokens` 호출 시 422 또는 CSRF 에러.

### 원인
API base controller가 `ApplicationController`를 상속하면서 `protect_from_forgery`가 적용된다. 네이티브 앱은 HTML meta 태그에서 CSRF 토큰을 읽을 수 없다.

### 해결
```ruby
class Api::V1::BaseController < ApplicationController
  skip_forgery_protection
  before_action :authenticate_user!
end
```

웹 뷰 내 폼은 Turbo가 자동으로 CSRF 토큰을 첨부하므로 문제없다. API 네임스페이스만 skip하면 된다.

---

## 3. CSRF 토큰 만료 시 500 에러 대신 우아한 처리

### 증상
로그아웃 후 `reset_session` → 이전 페이지의 CSRF 토큰이 stale → 폼 제출 시 `ActionController::InvalidAuthenticityToken` 500 에러.

### 해결
```ruby
class ApplicationController < ActionController::Base
  rescue_from ActionController::InvalidAuthenticityToken, with: :handle_invalid_csrf

  private

  def handle_invalid_csrf
    sign_out if user_signed_in?
    respond_to do |format|
      format.html { redirect_to new_session_path, alert: "세션이 만료되었습니다." }
      format.json { render json: { error: "session_expired" }, status: :unauthorized }
      format.any { head :unauthorized }
    end
  end
end
```

사용자는 500 페이지 대신 로그인 화면으로 부드럽게 이동한다.

---

## 4. ActionCable 인증이 session과 안 맞는다

### 증상
ActionCable WebSocket 연결이 인증 실패. `reject_unauthorized_connection` 발생.

### 원인
```ruby
# 문제: cookies.encrypted[:user_id]를 체크하지만 실제로 설정된 적 없음
def find_verified_user
  User.find_by(id: cookies.encrypted[:user_id] || request.session[:user_id])
end
```

`sign_in` 메서드는 `session[:user_id]`만 설정한다. `cookies.encrypted[:user_id]`는 한 번도 설정된 적 없다.

### 해결
```ruby
def find_verified_user
  User.find_by(id: request.session[:user_id])
end
```

인증 방식을 통일하자. session 기반이면 session만, cookie 기반이면 cookie만.

---

## 5. 로그인 페이지 모바일 웹 UX — 폼이 스크롤 아래로 밀린다

### 증상
모바일 웹에서 로그인 페이지 접속 시, 역할 소개 카드(운영자/선수/스태프) 3개가 먼저 보이고 실제 로그인 폼은 스크롤해야 보인다.

### 해결
```erb
<%# 모바일: 폼 먼저 / 데스크탑: 2컬럼 %>
<div class="flex flex-col-reverse gap-10 lg:grid lg:grid-cols-2 lg:items-start">
  <%# 역할 카드: 데스크탑에서만 표시 %>
  <div class="hidden lg:block">...</div>

  <%# 로그인 폼: 항상 먼저 %>
  <div class="mx-auto w-full max-w-md">...</div>
</div>
```

핵심: `flex-col-reverse` + `hidden lg:block` 조합으로 모바일에서는 폼만, 데스크탑에서는 2컬럼 레이아웃.

---

## 6. `time_ago_in_words`가 "약 1시간"으로 뭉개진다

### 증상
대회 당일 "다음 경기 32분 후"가 필요한데 "약 1시간 후"로 표시된다.

### 원인
Rails `time_ago_in_words`는 45분 이상이면 "about 1 hour"로 반올림한다.

### 해결
분 단위 직접 계산:
```erb
<% diff_minutes = ((scheduled_at - Time.current) / 60).round %>
<% if diff_minutes > 0 %>
  <span class="text-amber-600">
    (<%= diff_minutes >= 60 ? "#{diff_minutes / 60}시간 #{diff_minutes % 60}분 후" : "#{diff_minutes}분 후" %>)
  </span>
<% elsif diff_minutes > -5 %>
  <span class="text-emerald-600">(곧 시작)</span>
<% else %>
  <span class="text-red-500">
    (<%= (-diff_minutes) >= 60 ? "#{(-diff_minutes) / 60}시간 #{(-diff_minutes) % 60}분 전" : "#{-diff_minutes}분 전" %>)
  </span>
<% end %>
```

추가로 한국어 `distance_in_words` 번역도 필요하다:
```yaml
ko:
  datetime:
    distance_in_words:
      x_minutes:
        one: "1분"
        other: "%{count}분"
      about_x_hours:
        one: "약 1시간"
        other: "약 %{count}시간"
      # ... 전체 키 필요
```

---

## 7. Turbo Frame 안의 링크가 외부 페이지로 안 간다

### 증상
스코어보드(turbo_frame_tag lazy load) 안의 "코트 맵" 버튼을 누르면 `Content missing` 에러. 페이지 이동이 안 된다.

### 원인
Turbo Frame 내부의 링크는 기본적으로 **같은 frame 안에서** 응답을 로드하려 한다. 외부 페이지를 frame 안에 넣으려 하니 turbo-frame ID가 없어서 실패.

### 해결
```erb
<%= link_to some_path,
    data: { turbo_frame: "_top" } do %>
  ...
<% end %>
```

`data-turbo-frame="_top"`으로 전체 페이지 네비게이션을 강제한다.

---

## 8. 채팅 메시지 영역이 스크롤 안 된다 (flex 레이아웃 함정)

### 증상
채팅 메시지가 27개인데 스크롤바 없이 전체 페이지가 늘어난다. `overflow-y-auto`가 안 먹힌다.

### 원인
CSS flexbox에서 `flex: 1`인 자식은 기본 `min-height: auto`로 컨텐츠 크기만큼 커진다. `overflow`가 작동하려면 부모가 높이를 제한해야 한다.

### 해결
```html
<!-- 부모: flex 컬럼 + 고정 높이 -->
<div class="flex flex-col" style="height: calc(100dvh - 10rem);">
  <div class="shrink-0">헤더</div>

  <!-- 핵심: min-h-0 + overflow-hidden -->
  <div class="relative flex-1 min-h-0 overflow-hidden">
    <div class="h-full overflow-y-auto">
      <!-- 메시지들 -->
    </div>
  </div>

  <div class="shrink-0">입력창</div>
</div>
```

`min-h-0`이 없으면 `flex-1`이 컨텐츠를 감싸지 않고 늘어난다. 이건 Tailwind CSS FAQ에도 나오는 흔한 함정이다.

---

## 9. 채팅 스크롤 FAB 버튼 (맨 위로 / 맨 아래로)

### 구현
Stimulus 컨트롤러에 스크롤 감지를 추가하고, 위치에 따라 FAB 버튼을 토글한다:

```javascript
// chat_controller.js
_onScroll() {
  const el = this.messagesTarget
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  const distFromTop = el.scrollTop

  // 맨 아래에서 200px 이상 떨어지면 "↓ 맨 아래로" 표시
  this.scrollDownTarget.classList.toggle("hidden", distFromBottom < 200)
  // 맨 위에서 300px 이상 내려가면 "↑ 맨 위로" 표시
  this.scrollUpTarget.classList.toggle("hidden", distFromTop < 300)
}

goToBottom() {
  this.messagesTarget.scrollTo({ top: this.messagesTarget.scrollHeight, behavior: "smooth" })
}

goToTop() {
  this.messagesTarget.scrollTo({ top: 0, behavior: "smooth" })
}
```

FAB 버튼은 `absolute` 포지셔닝으로 메시지 영역 위에 떠 있게 한다:
```erb
<button data-chat-target="scrollDown"
        data-action="click->chat#goToBottom"
        class="hidden absolute bottom-3 right-3 z-10
               flex h-9 w-9 items-center justify-center
               rounded-full bg-emerald-500 text-white shadow-md">
  <svg><!-- ↓ 아이콘 --></svg>
</button>
```

---

## 10. 대회 생성 시 단식/복식/혼합복식 선택

### 설계
기존 `Tournament` 모델에 `match_type` enum을 추가:

```ruby
enum :match_type, { singles: 0, doubles: 1, mixed_doubles: 2 }, default: :singles

def players_per_team
  singles? ? 1 : 2
end
```

`format_summary`에도 반영해서 대회 상세에 "복식 · 3세트 6게임 · 듀스 · 7점 타이브레이크" 형태로 표시.

이미 `MatchPlayer`에 `team_side`와 `position`이 있어서 한 팀에 여러 선수를 넣는 구조는 갖춰져 있었다. 모델 레벨에서 `match_type` 정보만 추가하면 됐다.

---

## 보너스: 채팅 메시지에 아바타 표시

프로필 이미지가 있으면 Active Storage variant, 없으면 이름 첫 글자 + MD5 해시 색상:

```erb
<% if sender_user&.profile_image&.attached? %>
  <%= image_tag sender_user.profile_image.variant(resize_to_fill: [32, 32]),
      class: "h-8 w-8 rounded-full object-cover" %>
<% else %>
  <div class="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white"
       style="background: #<%= Digest::MD5.hexdigest(name)[0..5] %>;">
    <%= name.first %>
  </div>
<% end %>
```

---

## 체크리스트

| # | 항목 | 확인 |
|---|------|------|
| 1 | `session_store`에 `expire_after` + `same_site: :lax` | |
| 2 | API 컨트롤러 `skip_forgery_protection` | |
| 3 | `InvalidAuthenticityToken` rescue 처리 | |
| 4 | ActionCable 인증이 sign_in 방식과 일치 | |
| 5 | `allow_browser`에서 네이티브 앱 User-Agent 제외 | |
| 6 | CSP에 외부 서비스(결제 등) frame-src 허용 | |
| 7 | Turbo Frame 내 외부 링크에 `turbo_frame: "_top"` | |
| 8 | flex 레이아웃 스크롤 영역에 `min-h-0` | |
| 9 | 한국어 `distance_in_words` i18n 번역 | |
| 10 | 프로덕션 SSL + secure cookies 설정 | |

---

## 참고

- [Hotwire Native iOS - HotwireConfig.swift](https://github.com/hotwired/hotwire-native-ios)
- [Joe Masilotti - Hotwire Native by Example](https://masilotti.com/hotwire-native-by-example/)
- [37signals - Announcing Hotwire Native 1.2](https://dev.37signals.com/announcing-hotwire-native-v1-2/)
