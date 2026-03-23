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

When running two Rails 8 projects in parallel, patterns carefully built in one project often end up missing in the other. When implementing features, you naturally focus on the immediate requirements at hand — and it is easy to overlook a well-crafted solution from a sibling project that would save you significant time and headaches.

This time I deliberately placed both projects side by side and did a systematic cross-pollination pass. The focus was on security hardening, progressive web app experience, error tracking, and push notification infrastructure — the kind of foundational plumbing that rarely makes it into sprint planning but matters enormously in production.

---

## Comparison Methodology

The first step was generating a structured checklist of the key files to compare across both projects. Rather than doing an ad-hoc scan, I made the comparison explicit:

```
Checklist
├── Gemfile (gem list)
├── config/initializers/ (initializer files)
├── app/javascript/controllers/ (Stimulus controllers)
├── app/views/layouts/application.html.erb (layout)
├── db/schema.rb (DB schema)
└── ios/ (iOS native configuration)
```

Going through each category systematically made gaps obvious. Something like a missing `rack_attack.rb` initializer is trivially visible when you compare two Gemfiles line by line, but easy to miss when you only ever work on one project at a time.

The result was six items that needed to be cross-applied in both directions.

---

## 1. rack-attack — Preventing API Abuse

One project had `rack-attack` configured, the other did not. The unprotected project had endpoints for voting, commenting, and OTP code sending — all of them susceptible to abuse — but no rate limiting whatsoever. Without rate limiting, a bad actor can hammer the OTP endpoint to exhaust SMS quotas, flood voting endpoints to skew results, or simply degrade the service for legitimate users.

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

  # OTP sending: 5 requests per IP per 10 minutes
  throttle("auth/send_code", limit: 5, period: 10.minutes) do |req|
    req.ip if req.path.start_with?("/sessions/send_code") && req.post?
  end

  # Core actions (voting, commenting): 30 requests per IP per minute
  throttle("core/action", limit: 30, period: 1.minute) do |req|
    req.ip if req.path.match?(%r{/core_action}) && req.post?
  end

  # General API: 120 requests per IP per minute
  throttle("api/general", limit: 120, period: 1.minute) do |req|
    req.ip unless req.path.start_with?("/assets")
  end

  self.throttled_responder = lambda do |env|
    req = Rack::Request.new(env)
    if req.path.start_with?("/api/")
      [429, { "Content-Type" => "application/json" },
       [{ error: "Too many requests. Please try again later." }.to_json]]
    else
      [429, { "Content-Type" => "text/html; charset=utf-8" },
       ["<h1>429 Too Many Requests</h1><p>Please try again later.</p>"]]
    end
  end
end
```

The key design decision here is branching the response format based on the request path. API clients expect JSON; browser requests expect HTML. Returning JSON for a web request causes a confusing user experience, and returning HTML to an API client breaks JSON parsing. Splitting on the path prefix handles both correctly.

The `Rack::Attack.enabled = !Rails.env.development?` line is equally important. Leaving rate limiting active in development will cause your own requests to get blocked when running tests or doing rapid manual testing. Disable it in development, but keep it active in test and production environments.

A practical note on the throttle limits: the numbers above are starting points. OTP throttling at 5 per 10 minutes is conservative — legitimate users rarely need to resend more than once or twice. The general API limit of 120 per minute is generous enough for normal usage but blocks scripted attacks effectively.

---

## 2. PWA Install Banner (Stimulus Controller)

One project had a polished PWA install banner controller that handled the three distinct browser environments you encounter in a Korean-market app: iOS Safari, Android Chrome, and KakaoTalk's in-app browser. The logic for each differs significantly, and naive implementations tend to break in at least one of these environments.

```javascript
// app_banner_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["pwaBanner", "iosBanner", "androidBanner"]

  #deferredPrompt = null

  connect() {
    const ua = navigator.userAgent.toLowerCase()

    // KakaoTalk in-app browser — PWA installation not possible
    if (ua.includes("kakaotalk")) return

    // Already running as a PWA (standalone mode)
    const isStandalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    if (isStandalone) return

    // Hotwire Native app (body has the turbo-native class)
    if (document.body.classList.contains("turbo-native")) return

    // User has already dismissed the banner
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

A few points worth calling out in this implementation:

**KakaoTalk early return**: KakaoTalk's in-app browser does not support the `beforeinstallprompt` event or the iOS standalone install flow. Showing an install banner in KakaoTalk would just confuse users, so the controller returns immediately when it detects the KakaoTalk user agent.

**Standalone detection**: Checking `window.matchMedia("(display-mode: standalone)")` covers the Android/desktop PWA case. The `window.navigator.standalone` property is Apple-specific and returns `true` when the app is launched from the iOS home screen. Both checks together ensure you never show the install banner to users who have already installed the app.

**iOS vs. Android divergence**: Android Chrome fires the `beforeinstallprompt` event when the browser determines the site is installable. iOS Safari has no such event — you can only show a manual instruction prompt directing users to tap the share button and select "Add to Home Screen." The controller handles both paths.

In the layout, the banner is conditionally rendered to skip Hotwire Native app sessions entirely:

```erb
<% unless turbo_native_app? %>
  <div data-controller="app-banner">
    <div data-app-banner-target="pwaBanner" hidden class="fixed top-0 ...">
      ...
      <p data-app-banner-target="iosBanner" hidden>
        Tap the Share button at the bottom of Safari, then select "Add to Home Screen"
      </p>
      <button data-app-banner-target="androidBanner" hidden
              data-action="click->app-banner#installPwa">Install</button>
      <button data-action="click->app-banner#dismiss">&#x2715;</button>
    </div>
  </div>
<% end %>
```

With `Rails 8 + importmap`, if you have `pin_all_from "app/javascript/controllers"` configured in `config/importmap.rb`, adding the controller file to the directory is all you need — no manual import registration required.

---

## 3. Mobile Keyboard Overlap Compensation (visualViewport)

When a comment input or reply composer is pinned to the bottom of the viewport, the soft keyboard on mobile can overlap it. On Android, browsers typically resize `window.innerHeight` to account for the keyboard, so a simple CSS calculation works. iOS Safari is the problematic case: `window.innerHeight` does not shrink when the keyboard appears. You have to listen to `window.visualViewport` instead.

```javascript
// comment_form_controller.js (excerpt)
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
  // iOS tab bar: 49px, Android nav bar: 56px base offset
  const baseOffset = /iPad|iPhone|iPod/.test(ua) ? 49 : /Android/.test(ua) ? 56 : 52
  const offset = Math.max(baseOffset, overlap)
  this.composerTarget.style.setProperty("--comment-input-bottom-offset", `${offset}px`)
}
```

Scoping this to `turbo-native` only is deliberate. The `visualViewport` resize event fires frequently during scrolling on some browsers — running this on every web page load would add unnecessary listener overhead. Hotwire Native app users are the ones with bottom-pinned UI that overlaps the native tab bar, so restricting it to that context keeps the code focused and the web experience unaffected.

The base offset values (49px for iOS, 56px for Android) correspond to the default heights of native tab bars on each platform. When the keyboard is not visible, the offset needs to clear the tab bar at minimum. When the keyboard is visible, the overlap calculation takes over and pushes the composer above the keyboard.

---

## 4. Sentry Error Tracking

One project had no Sentry integration. In production, this means errors disappear silently — you only find out about them when a user reports something is broken, or when you happen to notice an anomaly in your logs. Adding Sentry gives you immediate visibility into both expected errors (routing errors, record not found) and genuine bugs.

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

  # Only trace 5% of transactions in production to control costs
  config.traces_sample_rate = Rails.env.production? ? 0.05 : 0.0

  # Do not send personally identifiable information to Sentry
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

Three points deserve particular attention:

**1. Restrict `enabled_environments` explicitly.** Without this, every error that occurs during local development gets reported to Sentry. This pollutes your error feed with noise from routine development work and makes it harder to spot real production issues. Restricting to `production` and `staging` keeps the signal-to-noise ratio high.

**2. Add `Rack::Attack::Throttled` to `excluded_exceptions`.** This one is easy to miss. When rack-attack throttles a request, it raises `Rack::Attack::Throttled`. Without this exclusion, Sentry captures every rate-limited request as an error, which floods your Sentry dashboard with events that are not bugs — they are expected behaviour. These events can also consume your Sentry quota quickly during any moderate traffic spike.

**3. Be explicit about `send_default_pii = false`.** This is the default, but Sentry's own official documentation examples sometimes show `send_default_pii = true`. If you copy-paste from those examples into an internal service, you will inadvertently send user IP addresses, session cookies, and request bodies to Sentry's servers. Being explicit in the config makes the intent clear and prevents accidental drift.

The `before_send` lambda adds a second layer of protection by scrubbing specific request fields. Even with `send_default_pii = false`, the request body can still contain sensitive fields depending on the exception context. Deleting `email`, `code`, `token`, and `password` from the event data ensures those values never leave your infrastructure.

For Render deployments, after adding `SENTRY_DSN` to the environment variables, trigger a manual deploy or wait for the next auto-deploy. Verify the integration is working by intentionally triggering a test error or using `Sentry.capture_message("test")` in a console.

---

## 5. FCM Token Table Separation (Multi-Device)

One project was storing the Firebase Cloud Messaging push token as a single `firebase_token` column on the `users` table. This approach has a fundamental limitation: it only supports one device per user at a time. Each new login overwrites the previous token, which means only the most recently used device receives notifications.

The specific failure modes are:

- A user with a phone and a tablet only receives notifications on whichever device they logged in on last.
- When a user gets a new phone, their old phone may still receive notifications until the FCM token expires.
- There is no way to distinguish web push tokens from iOS APNs bridge tokens from Android FCM tokens, making device-specific notification routing impossible.

The fix is to extract FCM tokens into their own table.

**Migration**

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

The `device_name` column is optional but useful for debugging — you can store something like `"iPhone 15 Pro"` or `"Chrome on macOS"` to make the token list human-readable in an admin panel.

**Model**

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

The `register` method uses `find_or_initialize_by` rather than `find_or_create_by` to avoid a race condition. If the same token is registered twice — which can happen when a user opens the app on the same device twice in quick succession — the second call updates the existing record rather than raising a uniqueness validation error.

**Adding user-level broadcast to FcmService**

```ruby
# Send to all active devices for a user
def self.send_to_user(user:, title:, body:, data: {})
  tokens = user.fcm_tokens.active.pluck(:token)
  return if tokens.blank?
  send_to_tokens(tokens: tokens, title: title, body: body, data: data)
end
```

**Automatic deactivation of expired tokens**

FCM returns a 404 status code when you attempt to send to a token that has been invalidated — for example, when a user uninstalls the app or revokes notification permissions. Catching this response and deactivating the token immediately keeps your token table clean and prevents repeated failed send attempts:

```ruby
if response.status == 404 && (token = message.dig(:token))
  FcmToken.deactivate(token)
end
```

Without this cleanup, expired tokens accumulate over time, and every broadcast to a large user base will include a growing tail of dead tokens. This degrades send performance and inflates Firebase API usage.

---

## 6. iOS URL Scheme Deep Links (Info.plist)

Hotwire Native iOS apps frequently need to hand off to external apps — payment processors, authentication providers, OAuth flows — and then receive control back when the external flow completes. Without a registered custom URL scheme in `Info.plist`, the external app has no way to return to your app. The user ends up stranded in Safari or the payment app with no path back.

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

The `CFBundleURLName` is a reverse-DNS identifier for your scheme and should match your bundle identifier. The `CFBundleURLSchemes` array contains the actual scheme strings. When the external app calls `yourappscheme://callback?result=success`, iOS routes that URL back to your app.

On the Swift side, handle the incoming URL in `SceneDelegate`:

```swift
func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    guard let url = URLContexts.first?.url else { return }
    // Route the URL to your Hotwire navigator or handle the callback
    navigator.route(url)
}
```

If you are using XcodeGen (via a `project.yml`), add the URL type under the `Info` key of the relevant target rather than editing `Info.plist` directly. Editing `Info.plist` directly gets overwritten on the next `xcodegen generate` run.

---

## Summary

| Item | Key Points |
|------|------------|
| rack-attack | Disable in development, branch API/HTML responses, exclude `Throttled` from Sentry |
| PWA banner | Handle iOS/Android/KakaoTalk separately, skip turbo-native sessions, manage state with localStorage |
| Keyboard offset | Use `window.visualViewport`, activate only in turbo-native apps |
| Sentry | `send_default_pii = false`, restrict to production/staging, 5% sampling rate |
| FCM tokens | Single column → separate table, upsert pattern, auto-deactivate on 404 |
| iOS deep links | `CFBundleURLTypes` in Info.plist is required for external app callbacks |

---

## Key Takeaways

Running multiple Rails projects in parallel creates a knowledge divergence problem that gets worse over time. Each project accumulates its own solutions, and without a deliberate synchronization step, the gap between them widens with every sprint.

A few practices that help:

**Schedule periodic cross-project audits.** Even a 30-minute pass of comparing Gemfiles and initializer directories between projects catches most divergence early, before it becomes a production incident.

**Keep a personal reference list of foundational patterns.** Things like rack-attack configuration, Sentry setup, and FCM token management are solved problems. Codifying the solution once and applying it consistently across projects is significantly less work than re-deriving the solution from scratch or debugging a production issue because the pattern was missing.

**Treat security and observability as non-optional infrastructure.** Rate limiting, error tracking, and push notification reliability are not features — they are the floor that features stand on. The cost of adding them early is low. The cost of adding them after a production incident is high.

The six items covered in this post are all in the category of "solved problems that should exist in every project." Cross-applying them took less than a day, and the result is two projects that are both more secure, more observable, and more reliable than they were before.
