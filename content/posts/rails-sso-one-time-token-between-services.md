---
title: "Rails 서비스 간 SSO 직접 구현하기: One-Time Token + HMAC 방식"
date: 2026-02-10
draft: false
tags: ["Rails", "SSO", "Devise", "Svelte", "Render", "보안", "서비스간연동"]
description: "OAuth2 없이 두 Rails 앱 사이에 SSO를 직접 구현한 과정. One-Time Token + HMAC 서명 방식으로 외부 라이브러리 없이 사용자 인증을 위임하고, Render 배포까지 연결한 기록."
cover:
  image: "/images/og/rails-sso-one-time-token-between-services.png"
  alt: "Rails Sso One Time Token Between Services"
  hidden: true
---

두 개의 Rails 앱이 있다. 하나는 **내부 직원용** 앱(OTP 로그인, 특정 도메인 전용), 다른 하나는 **심사/관리 시스템**으로 Devise + JWT 기반이다. 내부 직원이 심사 시스템에도 접근해야 하는데, 계정을 따로 만들어 관리하기 싫었다.

> "이미 내부 앱에 로그인돼 있으면, 심사 시스템에서 버튼 하나로 자동 로그인되면 안 되나?"

OAuth2를 붙이면 정석이지만, Doorkeeper 설정하고 scope 관리하고... 내부 서비스 두 개 사이에 그게 과할 수 있다. 더 단순한 방법을 택했다.

---

## 구조 선택: One-Time Token + HMAC

이미 두 서비스 사이에 webhook 연동이 있었다. ITSM 이벤트를 다른 서비스에 전달할 때 HMAC-SHA256으로 서명하는 패턴이 있었고, 이걸 SSO에도 그대로 쓰기로 했다.

```
[Service A - 로그인 버튼 클릭]
  → Service B /sso/authorize (로그인 여부 확인 + 토큰 발급)
  → Redirect → Service A /sso/callback?token=xxx&state=yyy
  → Service A가 Service B에 POST /sso/verify (HMAC 서명)
  → Service B가 유저 정보 반환
  → Service A Devise 세션 생성
```

핵심 보안 장치:
- **Token**: 일회용, 5분 만료, DB 저장 (`used_at` 체크)
- **HMAC-SHA256**: Verify 요청이 신뢰된 서비스에서 온 것인지 검증
- **state**: CSRF 방지 (세션에 저장, callback에서 비교)
- **redirect_uri 화이트리스트**: 허용된 주소로만 리다이렉트

---

## IdP 쪽 구현 (토큰 발급 서비스)

### SsoToken 모델

```ruby
class SsoToken < ApplicationRecord
  belongs_to :user

  scope :valid, -> { where(used_at: nil).where("expires_at > ?", Time.current) }

  def use!
    update!(used_at: Time.current)
  end
end
```

마이그레이션:

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

### SSO 컨트롤러

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

    # redirect_uri 화이트리스트 검증
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

**포인트**: `require_authentication`이 미로그인 유저를 로그인 페이지로 보낼 때, SSO authorize URL 전체(쿼리 파라미터 포함)를 `session[:return_to]`에 저장해야 한다. OTP 인증 후 `redirect_back_or(dashboard_path)`로 돌아오면 SSO 흐름이 이어진다.

---

## SP 쪽 구현 (로그인 위임 서비스)

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

### 콜백 컨트롤러

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
    # CSRF 방지: state 검증
    unless ActiveSupport::SecurityUtils.secure_compare(
      params[:state], session.delete(:sso_state).to_s
    )
      redirect_to login_path, alert: "인증 실패 (state mismatch)"
      return
    end

    user_data = SsoService.verify_token(params[:token])
    return redirect_to login_path, alert: "인증 실패" unless user_data

    # 유저 생성 또는 조회
    user = User.find_or_initialize_by(email: user_data["email"])
    if user.new_record?
      user.assign_attributes(
        name: user_data["name"],
        role: :reviewer,         # SSO 유저 기본 역할
        password: SecureRandom.hex(16),
        sso_provider: "internal"
      )
      user.save!
    end

    sign_in(user)
    redirect_to root_path, notice: "로그인되었습니다."
  end
end
```

---

## Render 배포 시 삽질한 부분

### autoDeploy: no 서비스에서 env var 업데이트가 구 커밋으로 배포됨

환경변수를 Render API/MCP로 업데이트하면 자동으로 재배포가 트리거된다. 그런데 `autoDeploy: no`인 서비스는 **env var 업데이트 시점의 최신 커밋이 아니라 마지막으로 배포됐던 커밋**으로 빌드한다.

새 코드를 push한 뒤 env var을 업데이트했는데, 막상 배포된 건 push 전 코드였다. 버튼이 안 보이는 이유가 여기 있었다.

**해결**: Render REST API로 수동 배포 트리거.

```bash
curl -X POST "https://api.render.com/v1/services/{SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache": "do_not_clear"}'
```

응답에서 최신 커밋 메시지를 확인해 제대로 된 버전이 배포됐는지 검증할 수 있다.

---

## 프론트엔드: 로그인 버튼

Svelte + Inertia.js 환경에서 SSO 버튼은 **Inertia router가 아닌 일반 `<a>` 태그**를 써야 한다. Inertia는 내부 XHR 요청을 보내는데, SSO 흐름은 외부 서비스로 실제 페이지 이동(redirect)이 필요하기 때문이다.

```svelte
<a
  href="/sso/initiate"
  class="w-full flex items-center justify-center gap-2 py-3 px-4
         bg-[#1e3a5f] hover:bg-[#162d4a] text-white rounded-xl transition-all"
>
  <svg><!-- shield icon --></svg>
  내부 계정으로 로그인
  <span class="text-xs text-white/70">직원 전용</span>
</a>
```

기존 이메일/비밀번호 폼 위에 `또는` 구분선과 함께 배치했다.

---

## 마무리

OAuth2가 표준이지만, 내부 서비스 두 개 사이라면 One-Time Token + HMAC 조합이 훨씬 가볍고 직관적이다. 이미 서비스 간 HMAC webhook이 있다면 동일 패턴을 SSO에 재사용할 수 있어서 코드 일관성도 좋다.

핵심 체크리스트:
- [ ] Token은 반드시 일회용 (`used_at`)
- [ ] 만료 시간 짧게 (5분 이하)
- [ ] HMAC 검증에 `ActiveSupport::SecurityUtils.secure_compare` 사용 (타이밍 공격 방지)
- [ ] `state` 파라미터로 CSRF 방지
- [ ] redirect_uri 화이트리스트 필수
- [ ] Render `autoDeploy: no` 서비스는 env var 업데이트 후 수동 배포 확인
