---
title: "Rails 8 Cross-Project Pattern Application — rack-attack, PWA Banner, Sentry, FCM Multi-Device"
date: 2026-02-20
draft: false
tags: ["Rails", "Ruby", "PWA", "Sentry", "Hotwire", "Stimulus", "FCM"]
description: "Running two Rails 8 projects side by side revealed patterns working in one but missing in the other. Cross-applying rack-attack, PWA install banner, Sentry error tracking, FCM multi-device token management, and iOS deep link configuration."
cover:
  image: "/images/og/rails8-cross-project-patterns-and-improvements.png"
  alt: "Rails8 Cross Project Patterns And Improvements"
  hidden: true
categories: ["Rails"]
---


두 개의 Rails 8 프로젝트를 병렬로 운영하다 보면 한쪽에서 공들여 만든 패턴이 다른 쪽에는 빠져있는 경우가 자주 생긴다. 기능을 구현할 때는 당장의 요구사항에 집중하다 보니 다른 프로젝트의 좋은 구현을 챙기지 못하는 것이다.

이번에 두 프로젝트를 나란히 놓고 비교하면서 빠진 부분을 서로 채워주는 작업을 했다. 주로 보안, PWA 경험, 에러 추적, 푸시 알림 인프라에 관한 내용이다.

---

## 비교 분석 방법

두 프로젝트의 주요 파일을 나열하고 대조했다.

```
확인 항목
├── Gemfile (gem 목록)
├── config/initializers/ (설정 파일)
├── app/javascript/controllers/ (Stimulus 컨트롤러)
├── app/views/layouts/application.html.erb (레이아웃)
├── db/schema.rb (DB 스키마)
└── ios/ (iOS 네이티브 설정)
```

결과적으로 아래 6가지를 양방향으로 이식했다.

---

## 1. rack-attack — API 남용 방지

한 프로젝트에는 `rack-attack`이 있었고 다른 쪽에는 없었다. 투표, 댓글, OTP 발송 등 남용될 수 있는 엔드포인트가 있음에도 rate limit이 없는 상태였다.

**Gemfile**

```ruby
gem "rack-attack"
```

**config/application.rb**

```ruby
config.middleware.use Rack::Attack
```

**config/initializers/rack_attack.rb**

```ruby
class Rack::Attack
  Rack::Attack.enabled = !Rails.env.development?

  # OTP 발송: IP당 10분에 5회
  throttle("auth/send_code", limit: 5, period: 10.minutes) do |req|
    req.ip if req.path.start_with?("/sessions/send_code") && req.post?
  end

  # 핵심 행동(투표, 댓글): IP당 분당 20~30회
  throttle("core/action", limit: 30, period: 1.minute) do |req|
    req.ip if req.path.match?(%r{/core_action}) && req.post?
  end

  # 일반 API: IP당 분당 120회
  throttle("api/general", limit: 120, period: 1.minute) do |req|
    req.ip unless req.path.start_with?("/assets")
  end

  self.throttled_responder = lambda do |env|
    req = Rack::Request.new(env)
    if req.path.start_with?("/api/")
      [429, { "Content-Type" => "application/json" },
       [{ error: "요청이 너무 많습니다. 잠시 후 다시 시도해주세요." }.to_json]]
    else
      [429, { "Content-Type" => "text/html; charset=utf-8" },
       ["<h1>429 Too Many Requests</h1><p>잠시 후 다시 시도해주세요.</p>"]]
    end
  end
end
```

API와 HTML 응답을 경로 기준으로 분기한 게 포인트다. API는 JSON, 웹은 HTML로 응답해야 클라이언트가 올바르게 처리한다.

개발 환경에서는 `Rack::Attack.enabled = !Rails.env.development?`로 비활성화해야 테스트할 때 막히지 않는다.

---

## 2. PWA 설치 배너 (Stimulus 컨트롤러)

한 프로젝트에서 꽤 공들여 만든 PWA 설치 배너 컨트롤러가 있었다. iOS Safari, Android Chrome, 카카오톡 인앱 브라우저를 각각 감지하는 로직이 포함되어 있다.

```javascript
// app_banner_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["pwaBanner", "iosBanner", "androidBanner"]

  #deferredPrompt = null

  connect() {
    const ua = navigator.userAgent.toLowerCase()

    // 카카오톡 인앱 브라우저 — PWA 설치 불가
    if (ua.includes("kakaotalk")) return

    // 이미 PWA로 실행 중
    const isStandalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    if (isStandalone) return

    // Hotwire Native 앱 (body에 클래스 있음)
    if (document.body.classList.contains("turbo-native")) return

    // 이미 닫은 적 있음
    if (localStorage.getItem("pwa_banner_dismissed")) return

    const isIos = /iphone|ipad|ipod/.test(ua)

    if (!isIos) {
      window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault()
        this.#deferredPrompt = e
        if (this.hasPwaBannerTarget) this.pwaBannerTarget.hidden = false
        this.androidBannerTargets.forEach((el) => (el.hidden = false))
      })
    } else {
      const isSafari = /safari/.test(ua) && !/crios|fxios/.test(ua)
      if (isSafari && this.hasPwaBannerTarget) {
        this.pwaBannerTarget.hidden = false
        if (this.hasIosBannerTarget) this.iosBannerTarget.hidden = false
      }
    }
  }

  async installPwa() {
    if (!this.#deferredPrompt) return
    this.#deferredPrompt.prompt()
    const { outcome } = await this.#deferredPrompt.userChoice
    if (outcome === "accepted") localStorage.setItem("pwa_banner_dismissed", "1")
    this.#deferredPrompt = null
    if (this.hasPwaBannerTarget) this.pwaBannerTarget.hidden = true
  }

  dismiss() {
    if (this.hasPwaBannerTarget) this.pwaBannerTarget.hidden = true
    localStorage.setItem("pwa_banner_dismissed", "1")
  }
}
```

레이아웃에서는 Hotwire Native 앱일 때 배너를 렌더링하지 않도록 조건을 걸었다.

```erb
<% unless turbo_native_app? %>
  <div data-controller="app-banner">
    <div data-app-banner-target="pwaBanner" hidden class="fixed top-0 ...">
      ...
      <p data-app-banner-target="iosBanner" hidden>
        Safari 하단 공유 버튼 → 홈 화면에 추가
      </p>
      <button data-app-banner-target="androidBanner" hidden
              data-action="click->app-banner#installPwa">설치</button>
      <button data-action="click->app-banner#dismiss">✕</button>
    </div>
  </div>
<% end %>
```

`Rails 8 + importmap`에서 `pin_all_from "app/javascript/controllers"` 설정이 되어 있으면 파일만 추가하면 자동으로 등록된다. 별도 import 추가 불필요.

---

## 3. 모바일 키보드 겹침 보정 (visualViewport)

모바일에서 댓글 입력창이 하단에 고정되어 있을 때, 소프트 키보드가 올라오면 입력창을 가리는 문제가 있다. iOS Safari는 특히 `window.innerHeight`가 키보드 높이를 반영하지 않아서 `window.visualViewport`를 별도로 써야 한다.

```javascript
// comment_form_controller.js (일부)
connect() {
  if (document.body.classList.contains("turbo-native")) {
    this._onViewportChange = this._syncOffset.bind(this)
    window.addEventListener("resize", this._onViewportChange)
    window.visualViewport?.addEventListener("resize", this._onViewportChange)
  }
}

disconnect() {
  if (!this._onViewportChange) return
  window.removeEventListener("resize", this._onViewportChange)
  window.visualViewport?.removeEventListener("resize", this._onViewportChange)
  this._onViewportChange = null
}

_syncOffset() {
  if (!this.hasComposerTarget) return
  const rect = this.composerTarget.getBoundingClientRect()
  const viewportHeight = window.visualViewport?.height ?? window.innerHeight
  const overlap = Math.max(0, Math.ceil(rect.bottom - viewportHeight))
  const ua = navigator.userAgent
  // iOS 탭바 49px, Android 56px 기본 오프셋
  const baseOffset = /iPad|iPhone|iPod/.test(ua) ? 49 : /Android/.test(ua) ? 56 : 52
  const offset = Math.max(baseOffset, overlap)
  this.composerTarget.style.setProperty("--comment-input-bottom-offset", `${offset}px`)
}
```

Hotwire Native 앱에서만 실행되도록 `turbo-native` 클래스 체크가 중요하다. 웹 브라우저에서는 불필요하고 성능 낭비가 된다.

---

## 4. Sentry 에러 추적

한 프로젝트에 Sentry가 없어서 추가했다.

**Gemfile**

```ruby
gem "sentry-ruby"
gem "sentry-rails"
```

**config/initializers/sentry.rb**

```ruby
Sentry.init do |config|
  config.dsn = ENV["SENTRY_DSN"]
  config.breadcrumbs_logger = [:active_support_logger, :http_logger]
  config.enabled_environments = %w[production staging]

  # production에서 5% 트랜잭션만 추적 (비용 절감)
  config.traces_sample_rate = Rails.env.production? ? 0.05 : 0.0

  # 내부 서비스 → 개인정보 전송 안 함
  config.send_default_pii = false

  config.before_send = lambda do |event, _hint|
    event.request&.data&.delete("email")
    event.request&.data&.delete("code")
    event.request&.data&.delete("token")
    event.request&.data&.delete("password")
    event
  end

  config.excluded_exceptions += %w[
    ActionController::RoutingError
    ActionController::InvalidAuthenticityToken
    ActiveRecord::RecordNotFound
    Rack::Attack::Throttled
  ]
end
```

주의할 점:

1. `enabled_environments`를 production/staging으로 제한하지 않으면 개발 중 매번 Sentry에 이벤트가 쌓인다.
2. `excluded_exceptions`에 `Rack::Attack::Throttled`를 넣어야 rate limit 자체가 에러로 보고되지 않는다.
3. `send_default_pii = false`는 기본값이지만 명시적으로 쓰는 게 낫다. Sentry 공식 문서는 `true`를 예시로 보여주는데, 내부 서비스에서 무심코 쓰면 사용자 IP나 세션 쿠키가 외부로 나간다.

Render 배포라면 환경변수 업데이트 후 자동 재배포를 확인하면 된다.

---

## 5. FCM 토큰 테이블 분리 (멀티디바이스)

한 프로젝트에서 Firebase 푸시 알림 토큰을 users 테이블의 단일 컬럼(`firebase_token`)으로 관리하고 있었다. 이 방식의 문제:

- 기기를 2대 이상 쓰면 마지막 로그인 기기에만 알림이 간다
- 기기 교체 시 이전 토큰을 추적하거나 무효화할 방법이 없다
- 웹/iOS/Android 구분도 불가능하다

별도 테이블로 분리했다.

**마이그레이션**

```ruby
create_table :fcm_tokens do |t|
  t.references :user, null: false, foreign_key: true
  t.string :token,       null: false
  t.string :device_type, null: false, default: "web"  # web | ios | android
  t.string :device_name
  t.boolean :active,     null: false, default: true
  t.datetime :last_used_at
  t.timestamps
end

add_index :fcm_tokens, :token, unique: true
add_index :fcm_tokens, [:user_id, :active]
```

**모델**

```ruby
class FcmToken < ApplicationRecord
  belongs_to :user

  scope :active, -> { where(active: true) }

  def self.register(user:, token:, device_type: "web", device_name: nil)
    record = find_or_initialize_by(token: token)
    record.update!(
      user: user,
      device_type: device_type,
      device_name: device_name,
      active: true,
      last_used_at: Time.current
    )
    record
  end

  def self.deactivate(token)
    find_by(token: token)&.update!(active: false)
  end
end
```

**FcmService에 유저 단위 발송 추가**

```ruby
# 유저의 모든 활성 기기로 발송
def self.send_to_user(user:, title:, body:, data: {})
  tokens = user.fcm_tokens.active.pluck(:token)
  return if tokens.blank?
  send_to_tokens(tokens: tokens, title: title, body: body, data: data)
end
```

FCM API에서 404 응답이 오면 (만료된 토큰) 자동으로 비활성화하는 처리도 추가했다.

```ruby
if response.status == 404 && (token = message.dig(:token))
  FcmToken.deactivate(token)
end
```

---

## 6. iOS URL Scheme 딥링크 (Info.plist)

Hotwire Native iOS 앱에서 외부 앱(결제, 인증 등)이 돌아올 때 쓸 커스텀 URL scheme을 Info.plist에 추가해야 한다. 이게 없으면 외부 앱에서 돌아올 수가 없다.

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLName</key>
    <string>com.yourapp.app</string>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>yourappscheme</string>
    </array>
  </dict>
</array>
```

SceneController에서 해당 scheme을 수신하는 처리를 추가하면 완성이다.

---

## Summary

| 항목 | 핵심 포인트 |
|------|-------------|
| rack-attack | 개발 환경 비활성화, API/HTML 응답 분기, Throttled 예외는 Sentry 제외 |
| PWA 배너 | iOS/Android/카카오톡 분기, turbo-native 환경 제외, localStorage 상태 관리 |
| 키보드 오프셋 | `window.visualViewport` 사용, turbo-native 앱에서만 활성화 |
| Sentry | `send_default_pii = false`, production/staging만 활성화, 5% 샘플링 |
| FCM 토큰 | 단일 컬럼 → 별도 테이블, upsert 패턴, 404 자동 비활성화 |
| iOS 딥링크 | `CFBundleURLTypes` Info.plist 추가 필수 |

Rails 프로젝트가 여러 개면 주기적으로 나란히 놓고 비교하는 습관이 도움이 된다. 한쪽에서 해결한 문제를 다른 쪽에서 다시 삽질하는 일을 막을 수 있다.
