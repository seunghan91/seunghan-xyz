---
title: "Rails 8 프로젝트 간 패턴 교차 적용 — rack-attack, PWA 배너, Sentry, FCM 멀티디바이스"
date: 2026-02-20
draft: false
tags: ["Rails", "Ruby", "PWA", "Sentry", "Hotwire", "Stimulus", "FCM"]
description: "두 Rails 8 프로젝트를 나란히 운영하다 보니, 한쪽에서 잘 동작하는 패턴이 다른 쪽에는 빠져있는 경우가 많았다. 이번 글에서는 rack-attack, PWA 설치 배너, Sentry 에러 추적, FCM 멀티디바이스 토큰 관리, iOS 딥링크 설정을 교차 적용하면서 겪은 내용을 정리한다."
cover:
  image: "/images/og/rails8-cross-project-patterns-and-improvements.png"
  alt: "Rails8 Cross Project Patterns And Improvements"
  hidden: true
categories: ["Flutter", "Rails"]
---

두 개의 Rails 8 프로젝트를 병렬로 운영하다 보면 한쪽에서 공들여 만든 패턴이 다른 쪽에는 빠져있는 경우가 자주 생긴다. 기능을 구현할 때는 당장의 요구사항에 집중하다 보니 다른 프로젝트의 좋은 구현을 챙기지 못하는 것이다. 시간이 지날수록 두 프로젝트 사이의 품질 격차가 벌어지고, 한쪽에서는 해결된 문제를 다른 쪽에서 다시 삽질하는 상황이 생긴다.

이번에 두 프로젝트를 나란히 놓고 비교하면서 빠진 부분을 서로 채워주는 작업을 했다. 주로 보안, PWA 경험, 에러 추적, 푸시 알림 인프라에 관한 내용이다. 여섯 가지 항목 모두 "한번 제대로 만들면 모든 프로젝트에 적용해야 하는" 기반 인프라 성격의 것들이다.

---

## 비교 분석 방법

두 프로젝트의 주요 파일을 나열하고 대조했다. 임기응변식으로 스캔하는 것보다 체크리스트를 만들어 명시적으로 비교하는 편이 빠진 항목을 놓치지 않는다.

```
확인 항목
├── Gemfile (gem 목록)
├── config/initializers/ (설정 파일)
├── app/javascript/controllers/ (Stimulus 컨트롤러)
├── app/views/layouts/application.html.erb (레이아웃)
├── db/schema.rb (DB 스키마)
└── ios/ (iOS 네이티브 설정)
```

예를 들어 Gemfile 두 개를 나란히 놓고 보면 `rack-attack`이 한쪽에만 있다는 게 바로 보인다. 프로젝트 하나만 볼 때는 없는 게 당연하게 느껴지지만, 비교하는 순간 빠진 것이 명확해진다.

결과적으로 아래 6가지를 양방향으로 이식했다.

---

## 1. rack-attack — API 남용 방지

한 프로젝트에는 `rack-attack`이 있었고 다른 쪽에는 없었다. 투표, 댓글, OTP 발송 등 남용될 수 있는 엔드포인트가 있음에도 rate limit이 없는 상태였다. Rate limiting이 없으면 OTP 엔드포인트를 반복 호출해 SMS 발송 비용을 소진시키거나, 투표 엔드포인트를 스크립트로 두드려 결과를 조작하거나, 단순 서비스 과부하를 일으킬 수 있다.

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

API와 HTML 응답을 경로 기준으로 분기한 게 핵심 포인트다. API 클라이언트는 JSON을 기대하고, 브라우저 요청은 HTML을 기대한다. API 경로에 HTML로 응답하면 클라이언트의 JSON 파싱이 터지고, 웹 경로에 JSON으로 응답하면 사용자에게 알 수 없는 오류 화면이 보인다.

개발 환경에서는 `Rack::Attack.enabled = !Rails.env.development?`로 비활성화해야 한다. 개발 중에 rate limit에 막히면 디버깅이 매우 번거로워진다. test 환경과 production 환경에서는 활성화 상태를 유지한다.

throttle 수치에 대해서도 한마디. OTP 10분 5회는 꽤 보수적인 수치인데, 실제 사용자는 거의 대부분 1-2회 이내에 완료하므로 정상 사용에는 영향이 없다. 일반 API 분당 120회는 정상 사용 패턴에는 충분히 여유있는 수치지만 스크립트 공격은 효과적으로 차단한다.

---

## 2. PWA 설치 배너 (Stimulus 컨트롤러)

한 프로젝트에서 꽤 공들여 만든 PWA 설치 배너 컨트롤러가 있었다. iOS Safari, Android Chrome, 카카오톡 인앱 브라우저를 각각 감지하는 로직이 포함되어 있다. 한국 앱이라면 세 환경 모두 고려해야 하는데, 각각 동작 방식이 완전히 다르다.

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

주요 설계 포인트를 풀어서 설명하면:

**카카오톡 조기 종료**: 카카오톡 인앱 브라우저는 `beforeinstallprompt` 이벤트도 지원하지 않고 iOS 홈 화면 추가 흐름도 사용할 수 없다. 설치 배너를 보여줘도 실제로 설치가 안 되기 때문에 사용자만 혼란스러워진다. 카카오톡 UA가 감지되면 바로 리턴.

**Standalone 감지**: `window.matchMedia("(display-mode: standalone)")` 는 Android/데스크톱 PWA를 감지한다. `window.navigator.standalone` 은 iOS Safari 전용으로, 홈 화면에서 실행 중일 때 `true`를 반환한다. 두 가지를 모두 체크해야 이미 앱을 설치한 사용자에게 배너를 보여주는 실수를 방지할 수 있다.

**iOS vs. Android 분기**: Android Chrome은 사이트가 설치 가능한 상태일 때 `beforeinstallprompt` 이벤트를 발생시킨다. iOS Safari에는 그런 이벤트가 없다. 공유 버튼을 탭하고 "홈 화면에 추가"를 선택하라는 수동 안내 문구를 보여주는 게 전부다. 컨트롤러가 두 경로를 각각 처리한다.

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

모바일에서 댓글 입력창이 하단에 고정되어 있을 때, 소프트 키보드가 올라오면 입력창을 가리는 문제가 있다. Android에서는 브라우저가 `window.innerHeight`를 키보드 높이만큼 줄여주기 때문에 CSS 계산이 자연스럽게 동작한다. 문제는 iOS Safari인데, iOS Safari는 키보드가 올라와도 `window.innerHeight`가 변하지 않는다. 이 경우 `window.visualViewport`를 별도로 써야 한다.

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

`turbo-native` 클래스 체크가 중요한 이유가 있다. `visualViewport` resize 이벤트는 일부 브라우저에서 스크롤 중에도 빈번하게 발생한다. 이 리스너를 모든 웹 페이지에서 실행하면 불필요한 이벤트 오버헤드가 쌓인다. 하단 고정 UI가 네이티브 탭바와 겹치는 문제는 Hotwire Native 앱에서만 발생하므로, 해당 환경에서만 활성화하는 것이 맞다.

기본 오프셋 값(iOS 49px, Android 56px)은 각 플랫폼의 기본 탭바 높이에 해당한다. 키보드가 없을 때는 최소한 탭바를 피해야 하므로 이 값이 하한선이 된다. 키보드가 올라오면 overlap 계산이 우선순위를 가지며 입력창을 키보드 위로 밀어낸다.

---

## 4. Sentry 에러 추적

한 프로젝트에 Sentry가 없어서 추가했다. Sentry 없이 프로덕션을 운영하면 에러가 조용히 사라진다. 사용자가 직접 버그를 제보하거나 로그에서 이상한 점을 발견할 때까지 모르고 지나가는 것이다. Sentry를 붙이면 예상된 에러(라우팅 에러, 레코드 없음)와 실제 버그 모두에 대해 즉각적인 가시성을 확보할 수 있다.

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

주의할 점 세 가지:

**1. `enabled_environments` 명시적 제한**: 이것 없이는 개발 중 발생하는 모든 에러가 Sentry로 보고된다. 일상적인 개발 작업에서 생기는 노이즈로 에러 피드가 오염되고, 실제 프로덕션 이슈를 찾기 어려워진다. `production`과 `staging`으로 제한하면 신호 대 잡음비가 유지된다.

**2. `excluded_exceptions`에 `Rack::Attack::Throttled` 추가**: 놓치기 쉬운 부분이다. rack-attack이 요청을 throttle하면 `Rack::Attack::Throttled` 예외를 발생시킨다. 이 예외를 제외하지 않으면 rate limit에 걸린 요청 하나하나가 Sentry 에러로 쌓인다. 이것들은 버그가 아니라 의도된 동작인데, 트래픽이 조금만 몰려도 Sentry 대시보드가 이 이벤트들로 가득 차고 Sentry 할당량도 빠르게 소진된다.

**3. `send_default_pii = false` 명시**: 기본값이지만 명시적으로 쓰는 게 낫다. Sentry 공식 문서 예시가 `true`를 보여주는 경우가 있는데, 그걸 그대로 복사해 내부 서비스에 붙이면 사용자 IP, 세션 쿠키, 요청 본문이 Sentry 서버로 나간다. 설정에 명시해두면 의도가 분명해지고 실수로 바뀌는 것을 방지할 수 있다.

`before_send` 람다는 추가 방어막으로, 특정 요청 필드를 스크럽한다. `send_default_pii = false`를 써도 예외 컨텍스트에 따라 요청 본문에 민감한 필드가 포함될 수 있다. `email`, `code`, `token`, `password`를 이벤트 데이터에서 지워버리면 이 값들이 절대 인프라 밖으로 나가지 않는다.

Render 배포라면 `SENTRY_DSN` 환경변수를 추가한 뒤 수동 재배포를 트리거하거나 다음 자동 배포를 기다리면 된다. 콘솔에서 `Sentry.capture_message("test")`를 실행해서 연동이 정상인지 확인하면 된다.

---

## 5. FCM 토큰 테이블 분리 (멀티디바이스)

한 프로젝트에서 Firebase 푸시 알림 토큰을 `users` 테이블의 단일 컬럼(`firebase_token`)으로 관리하고 있었다. 이 방식의 근본적인 한계는 사용자당 기기 하나만 지원한다는 것이다. 새로 로그인할 때마다 이전 토큰을 덮어쓰므로, 가장 최근에 로그인한 기기에만 알림이 간다.

구체적인 실패 사례:

- 폰과 태블릿을 함께 쓰는 사용자는 마지막으로 로그인한 기기에만 알림을 받는다.
- 폰을 새로 바꾼 경우, 이전 폰이 FCM 토큰 만료 전까지 계속 알림을 받을 수 있다.
- 웹 푸시 토큰, iOS 토큰, Android 토큰을 구분할 수 없어서 기기별 발송 제어가 불가능하다.

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

`device_name` 컬럼은 선택사항이지만 디버깅할 때 유용하다. `"iPhone 15 Pro"`나 `"Chrome on macOS"` 같은 값을 저장하면 어드민 패널에서 토큰 목록을 사람이 읽기 쉽게 만들 수 있다.

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

`register` 메서드가 `find_or_create_by` 대신 `find_or_initialize_by`를 쓰는 이유가 있다. 같은 기기에서 앱을 빠르게 두 번 열면 같은 토큰이 두 번 등록 요청될 수 있는데, `find_or_create_by`는 이 경우 uniqueness 에러를 낼 수 있다. `find_or_initialize_by + update!` 패턴은 이미 존재하는 레코드를 업데이트하기 때문에 race condition에서도 안전하다.

**FcmService에 유저 단위 발송 추가**

```ruby
# 유저의 모든 활성 기기로 발송
def self.send_to_user(user:, title:, body:, data: {})
  tokens = user.fcm_tokens.active.pluck(:token)
  return if tokens.blank?
  send_to_tokens(tokens: tokens, title: title, body: body, data: data)
end
```

**만료된 토큰 자동 비활성화**

FCM API는 만료된 토큰(앱 삭제, 알림 권한 취소 등)으로 발송을 시도하면 404를 반환한다. 이 응답을 받았을 때 토큰을 즉시 비활성화하지 않으면 만료 토큰이 계속 쌓이고, 대규모 발송 시 매번 실패하는 토큰들이 늘어나 Firebase API 사용량과 발송 성능 모두에 악영향을 준다.

```ruby
if response.status == 404 && (token = message.dig(:token))
  FcmToken.deactivate(token)
end
```

---

## 6. iOS URL Scheme 딥링크 (Info.plist)

Hotwire Native iOS 앱에서 외부 앱(결제, 인증 등)으로 이동한 뒤 돌아올 때 쓸 커스텀 URL scheme을 Info.plist에 추가해야 한다. 이게 없으면 외부 앱에서 돌아올 수가 없다. 사용자는 결제 앱이나 Safari에 갇혀 내 앱으로 돌아오는 경로를 찾지 못한다.

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

`CFBundleURLName`은 scheme의 역 DNS 식별자로, bundle identifier와 맞추는 게 관례다. `CFBundleURLSchemes` 배열에 실제 scheme 문자열을 넣는다. 외부 앱에서 `yourappscheme://callback?result=success`를 호출하면 iOS가 해당 URL을 내 앱으로 라우팅한다.

Swift 쪽에서는 `SceneDelegate`에서 수신 URL을 처리하면 된다:

```swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    guard let url = URLContexts.first?.url else { return }
    navigator.route(url)
}
```

XcodeGen(`project.yml`)을 쓴다면 Info.plist를 직접 수정하지 말고 `project.yml`의 해당 타겟 `Info` 키 아래에 URL type을 추가해야 한다. Info.plist를 직접 수정하면 다음 `xcodegen generate` 실행 시 덮어써진다.

---

## 정리

| 항목 | 핵심 포인트 |
|------|-------------|
| rack-attack | 개발 환경 비활성화, API/HTML 응답 분기, Throttled 예외는 Sentry 제외 |
| PWA 배너 | iOS/Android/카카오톡 분기, turbo-native 환경 제외, localStorage 상태 관리 |
| 키보드 오프셋 | `window.visualViewport` 사용, turbo-native 앱에서만 활성화 |
| Sentry | `send_default_pii = false`, production/staging만 활성화, 5% 샘플링 |
| FCM 토큰 | 단일 컬럼 → 별도 테이블, upsert 패턴, 404 자동 비활성화 |
| iOS 딥링크 | `CFBundleURLTypes` Info.plist 추가 필수 |

---

## 배운 것들

여러 Rails 프로젝트를 병렬로 운영하면 지식 격차 문제가 시간이 갈수록 심해진다. 각 프로젝트가 각자의 해법을 쌓아가고, 의도적인 동기화 단계 없이는 스프린트를 거듭할수록 격차가 벌어진다.

도움이 되는 습관 몇 가지:

**정기적인 크로스 프로젝트 점검을 일정에 넣는다.** Gemfile과 initializer 디렉토리를 30분만 비교해봐도 대부분의 격차를 조기에 발견할 수 있다. 프로덕션 사고가 난 뒤에 발견하는 것보다 훨씬 낫다.

**기반 패턴 레퍼런스 목록을 개인적으로 관리한다.** rack-attack 설정, Sentry 설정, FCM 토큰 관리는 이미 풀린 문제다. 한번 제대로 만들어두고 모든 프로젝트에 일관되게 적용하는 것이, 매번 처음부터 다시 만들거나 없어서 프로덕션 사고를 겪는 것보다 훨씬 적은 비용이다.

**보안과 관찰 가능성을 선택이 아닌 필수 인프라로 본다.** Rate limiting, 에러 추적, 푸시 알림 신뢰성은 기능이 아니다. 기능이 올라서는 바닥이다. 초기에 붙이는 비용은 낮다. 프로덕션 사고 이후에 붙이는 비용은 높다.

이번 글에서 다룬 여섯 가지 항목은 모두 "모든 프로젝트에 있어야 하는 풀린 문제" 범주에 속한다. 교차 적용에는 하루가 채 안 걸렸고, 결과적으로 두 프로젝트 모두 이전보다 더 안전하고 더 관찰 가능하고 더 안정적인 상태가 됐다.
