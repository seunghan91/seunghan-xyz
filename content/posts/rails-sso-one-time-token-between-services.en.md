---
title: "Building SSO Between Rails Services: One-Time Token + HMAC Approach"
date: 2026-02-10
draft: false
tags: ["Rails", "SSO", "Devise", "Svelte", "Render", "Security", "Service Integration"]
description: "Implementing SSO between two Rails apps without OAuth2. Delegating user authentication with One-Time Token + HMAC signing without external libraries, connected to Render deployment."
cover:
  image: "/images/og/rails-sso-one-time-token-between-services.png"
  alt: "Rails Sso One Time Token Between Services"
  hidden: true
categories: ["Rails", "Frontend"]
---

There are two Rails apps. One is an **internal staff app** — OTP login only, restricted to a specific domain. The other is a **review and management system** built on Devise + JWT. Internal employees need access to both, but creating and managing separate accounts for each was not a path worth taking.

> "If a user is already logged into the internal app, can't they just click a button and get into the review system automatically?"

Wiring up OAuth2 would be the textbook solution, but setting up Doorkeeper, managing scopes, configuring clients — for just two internal services that already trust each other, that felt like significant overhead. A simpler approach made more sense here.

---

## Why Not OAuth2?

OAuth2 is the right choice when you need to support third-party clients, granular permission scopes, token refresh flows, or public-facing integrations. For two internal Rails services that already share infrastructure and an operations team, OAuth2 introduces:

- An authorization server that needs its own maintenance
- A Doorkeeper setup with client registration and scope management
- Token refresh logic on the SP side
- More attack surface than the problem actually requires

The One-Time Token + HMAC pattern solves the core need — "trust this user because Service A already authenticated them" — with no new dependencies, no new servers, and code that mirrors an existing HMAC webhook pattern already in the codebase.

---

## Architecture: One-Time Token + HMAC

There was already a webhook integration between the two services. ITSM events were being forwarded between them using HMAC-SHA256 signatures, so the same pattern was reused for SSO.

```
[Service A - user clicks "Login with internal account"]
  → Redirect to Service B /sso/authorize (check auth status + issue token)
  → Redirect back → Service A /sso/callback?token=xxx&state=yyy
  → Service A POSTs to Service B /sso/verify (with HMAC signature)
  → Service B validates and returns user info
  → Service A creates Devise session
```

**Core security mechanisms:**

- **Token**: Single-use, 5-minute expiry, persisted in DB with `used_at` tracking
- **HMAC-SHA256**: Proves the verify request came from the trusted SP, not an attacker
- **state parameter**: CSRF protection — stored in session, compared on callback
- **redirect_uri allowlist**: Prevents open redirect attacks by whitelisting valid destinations

The flow is deliberately short. The token lives for at most 5 minutes and can only be used once. Even if an attacker intercepted the callback URL, they would need the shared HMAC secret to get the verify endpoint to return anything.

---

## IdP Side (Token-Issuing Service)

The Identity Provider (IdP) is the internal staff app. It owns the authoritative user records and is responsible for issuing and validating tokens.

### SsoToken Model

The model is intentionally minimal. The `valid` scope combines two conditions: the token must not have been consumed yet (`used_at` is nil), and it must not have expired.

```ruby
class SsoToken < ApplicationRecord
  belongs_to :user

  scope :valid, -> { where(used_at: nil).where("expires_at > ?", Time.current) }

  def use!
    update!(used_at: Time.current)
  end
end
```

Migration:

```ruby
create_table :sso_tokens do |t|
  t.string :token, null: false, index: { unique: true }
  t.references :user, null: false, foreign_key: true
  t.string :redirect_uri, null: false
  t.string :state, null: false
  t.string :client_id, null: false
  t.datetime :expires_at, null: false
  t.datetime :used_at
  t.timestamps
end
```

The `client_id` column records which SP requested the token. If you later need to support multiple SPs, this is the field you filter or audit on. The `state` column stores the value passed in by the SP for round-trip CSRF validation.

### SSO Controller

```ruby
class Auth::SsoController < ApplicationController
  ALLOWED_REDIRECT_URIS = -> {
    ENV.fetch("SSO_ALLOWED_REDIRECT_URIS", "").split(",").map(&:strip)
  }
  SSO_SHARED_SECRET = -> { ENV.fetch("SSO_SHARED_SECRET") }

  before_action :require_authentication, only: [:authorize]
  skip_before_action :verify_authenticity_token, only: [:verify]

  # GET /auth/sso/authorize
  def authorize
    redirect_uri = params[:redirect_uri]

    unless ALLOWED_REDIRECT_URIS.call.any? { |uri| redirect_uri.start_with?(uri) }
      return render plain: "Invalid redirect_uri", status: :bad_request
    end

    sso_token = SsoToken.create!(
      token: SecureRandom.urlsafe_base64(32),
      user: current_user,
      redirect_uri: redirect_uri,
      state: params[:state],
      client_id: params[:client_id],
      expires_at: 5.minutes.from_now
    )

    redirect_to "#{redirect_uri}?token=#{sso_token.token}&state=#{params[:state]}",
                allow_other_host: true
  end

  # POST /auth/sso/verify
  def verify
    request_body = request.body.read
    signature = request.headers["X-Signature-SHA256"]

    unless valid_signature?(request_body, signature)
      return render json: { error: "Invalid signature" }, status: :unauthorized
    end

    token = JSON.parse(request_body)["token"]
    sso_token = SsoToken.valid.find_by(token: token)

    return render json: { error: "Invalid or expired token" }, status: :unauthorized unless sso_token

    sso_token.use!
    render json: { email: sso_token.user.email, name: sso_token.user.name }
  end

  private

  def valid_signature?(body, signature)
    return false unless signature.present?
    expected = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', SSO_SHARED_SECRET.call, body)}"
    ActiveSupport::SecurityUtils.secure_compare(expected, signature)
  end
end
```

**Important detail about `require_authentication`:** When an unauthenticated user hits `/auth/sso/authorize`, the `before_action` will redirect them to the login page. The entire SSO authorize URL — including all query parameters — must be saved to `session[:return_to]` at that point. After OTP authentication, `redirect_back_or(dashboard_path)` should restore this saved URL, and the SSO flow will resume from where it left off. Without this, the user completes login but loses the SSO context and has to start over.

**Why `skip_before_action :verify_authenticity_token` on `/verify`?** The verify endpoint is called server-to-server by the SP's Rails backend, not by a browser form. Rails CSRF protection is browser-session-based and not applicable here. The HMAC signature in `X-Signature-SHA256` is the equivalent protection mechanism for this server-to-server call.

---

## SP Side (Delegating Service)

The Service Provider (SP) is the review/management system. It delegates authentication to the IdP and receives a verified user identity back.

### SSO Service

```ruby
require "faraday"
require "openssl"

class SsoService
  SSO_SHARED_SECRET = -> { ENV.fetch("SSO_SHARED_SECRET") }

  def self.authorize_url(redirect_uri:, state:)
    params = { client_id: "my_service", redirect_uri: redirect_uri, state: state }
    "#{ENV.fetch('IDP_URL')}/auth/sso/authorize?#{params.to_query}"
  end

  def self.verify_token(token)
    body = { token: token }.to_json
    signature = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', SSO_SHARED_SECRET.call, body)}"

    response = Faraday.new(url: ENV.fetch('IDP_URL')).post("auth/sso/verify") do |req|
      req.body = body
      req.headers["Content-Type"] = "application/json"
      req.headers["X-Signature-SHA256"] = signature
    end

    return nil unless response.success?
    JSON.parse(response.body)
  rescue Faraday::Error
    nil
  end
end
```

The `verify_token` method returns `nil` on any error — network failure, non-2xx response, or JSON parse error — rather than raising. The calling code treats `nil` as an authentication failure and redirects to the login page. This keeps the error surface simple and predictable.

### Callback Controller

```ruby
class SsoController < ApplicationController
  def initiate
    state = SecureRandom.urlsafe_base64(32)
    session[:sso_state] = state

    redirect_to SsoService.authorize_url(
      redirect_uri: sso_callback_url,
      state: state
    ), allow_other_host: true
  end

  def callback
    # CSRF protection: validate state parameter
    unless ActiveSupport::SecurityUtils.secure_compare(
      params[:state], session.delete(:sso_state).to_s
    )
      redirect_to login_path, alert: "Authentication failed (state mismatch)"
      return
    end

    user_data = SsoService.verify_token(params[:token])
    return redirect_to login_path, alert: "Authentication failed" unless user_data

    # Find or provision the user
    user = User.find_or_initialize_by(email: user_data["email"])
    if user.new_record?
      user.assign_attributes(
        name: user_data["name"],
        role: :reviewer,         # Default role for SSO users
        password: SecureRandom.hex(16),
        sso_provider: "internal"
      )
      user.save!
    end

    sign_in(user)
    redirect_to root_path, notice: "Logged in successfully."
  end
end
```

**User provisioning on first login:** New SSO users are created automatically with a random password (since they will never use it — they always authenticate via SSO) and a default `reviewer` role. The `sso_provider: "internal"` attribute lets you distinguish SSO accounts from regular Devise accounts in queries and admin views.

**`session.delete(:sso_state)` vs `session[:sso_state]`:** Using `delete` rather than just reading the value is deliberate. It clears the state from the session in a single atomic operation, so a replayed callback URL cannot reuse an old state value.

---

## Render Deployment Pitfall

### env var updates on `autoDeploy: no` services deploy from old commits

When you update environment variables via the Render API or Render MCP, Render automatically triggers a redeploy. However, for services configured with `autoDeploy: no`, this redeployment does **not** use the latest commit in your repository — it rebuilds from the **last manually deployed commit**.

The sequence that caused the problem:

1. Added new SSO code and pushed to the repository
2. Updated `SSO_SHARED_SECRET` and `IDP_URL` via Render API
3. Render triggered a redeploy — but from the old commit, before the SSO code existed
4. The SSO login button was missing because the view code had not been deployed yet

The fix is to trigger a manual deploy via the Render REST API after updating environment variables, pointing explicitly at the latest commit:

```bash
curl -X POST "https://api.render.com/v1/services/{SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache": "do_not_clear"}'
```

The deploy response includes the commit message and SHA. Verify these match your latest push before assuming the deployment succeeded.

---

## Frontend: The Login Button

In a Svelte + Inertia.js application, the SSO button must use a plain `<a>` tag rather than Inertia's `<Link>` component or `router.visit()`. Inertia intercepts navigation and sends XHR requests, which prevents the full-page redirect that SSO requires. The browser needs to actually navigate to the IdP's `/sso/authorize` endpoint, which then redirects back to the SP's callback URL. XHR cannot participate in this redirect chain.

```svelte
<a
  href="/sso/initiate"
  class="w-full flex items-center justify-center gap-2 py-3 px-4
         bg-[#1e3a5f] hover:bg-[#162d4a] text-white rounded-xl transition-all"
>
  <svg><!-- shield icon --></svg>
  Login with internal account
  <span class="text-xs text-white/70">Staff only</span>
</a>
```

This button was placed above the existing email/password form with an "or" divider between them.

---

## Routes

Add these routes to both applications.

**IdP (`config/routes.rb`):**

```ruby
namespace :auth do
  get  "sso/authorize", to: "sso#authorize"
  post "sso/verify",    to: "sso#verify"
end
```

**SP (`config/routes.rb`):**

```ruby
get  "sso/initiate",  to: "sso#initiate",  as: :sso_initiate
get  "sso/callback",  to: "sso#callback",  as: :sso_callback
```

---

## Environment Variables

Both services share the same `SSO_SHARED_SECRET` value. Treat it as a high-value secret: rotate it the same way you would rotate a database password.

**IdP:**
```
SSO_SHARED_SECRET=<long-random-value>
SSO_ALLOWED_REDIRECT_URIS=https://review-system.example.com/sso/callback
```

**SP:**
```
SSO_SHARED_SECRET=<same-long-random-value>
IDP_URL=https://internal-app.example.com
```

---

## Key Takeaways

- **OAuth2 is not always the right tool.** For two trusted internal services, One-Time Token + HMAC achieves the same security goals with far less infrastructure.
- **Reuse existing patterns.** If HMAC webhook signing already exists between your services, extending it to SSO means developers already understand the security model.
- **One-time tokens are non-negotiable.** The `used_at` column and the `valid` scope together ensure each token can only be exchanged once, eliminating replay attacks.
- **`ActiveSupport::SecurityUtils.secure_compare` is not optional.** Regular string comparison is vulnerable to timing attacks. Always use constant-time comparison for HMAC validation.
- **The `state` parameter prevents CSRF.** Generate it fresh on each SSO initiation, store it in the session, and delete it (not just read it) when validating the callback.
- **Whitelist `redirect_uri`.** An open redirect combined with a valid token is a credential-theft vulnerability. Validate against an explicit allowlist, not a prefix guess.
- **Render `autoDeploy: no` + env var update = old-code deploy.** Always trigger a manual deploy after updating env vars, and verify the commit SHA in the deploy response.
- **Use a plain `<a>` tag for SSO in Inertia.js apps.** Inertia's XHR-based navigation breaks redirect-dependent auth flows.
