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
categories: ["Rails", "Frontend"]
---

두 개의 Rails 앱이 있다. 하나는 **내부 직원용** 앱(OTP 로그인, 특정 도메인 전용), 다른 하나는 **심사/관리 시스템**으로 Devise + JWT 기반이다. 내부 직원이 심사 시스템에도 접근해야 하는데, 계정을 따로 만들어 관리하기 싫었다.

> "이미 내부 앱에 로그인돼 있으면, 심사 시스템에서 버튼 하나로 자동 로그인되면 안 되나?"

OAuth2를 붙이면 정석이지만, Doorkeeper 설정하고 scope 관리하고... 내부 서비스 두 개 사이에 그게 과할 수 있다. 더 단순한 방법을 택했다.

---

## OAuth2를 안 쓴 이유

OAuth2는 서드파티 클라이언트 지원, 세밀한 권한 범위(scope) 관리, 토큰 갱신 흐름, 공개 API 연동이 필요할 때 올바른 선택이다. 하지만 같은 팀이 운영하는 두 내부 서비스 사이에서 OAuth2를 도입하면 다음을 감수해야 한다.

- 별도로 관리해야 하는 인가 서버
- 클라이언트 등록과 scope 정의가 필요한 Doorkeeper 설정
- SP 쪽의 토큰 갱신 로직
- 실제 문제 크기에 비해 과도한 공격 표면

One-Time Token + HMAC 패턴은 핵심 요구사항인 "Service A가 이미 인증한 사용자임을 Service B에 위임한다"를 새 의존성 없이, 기존 HMAC webhook 패턴을 그대로 재사용해 해결한다.

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

흐름은 의도적으로 짧게 설계했다. 토큰은 최대 5분만 유효하고 딱 한 번만 쓸 수 있다. 공격자가 callback URL을 가로채더라도, verify 엔드포인트에서 유효한 응답을 받으려면 공유 HMAC 비밀값이 있어야 한다.

---

## IdP 쪽 구현 (토큰 발급 서비스)

IdP(Identity Provider)는 내부 직원 앱이다. 권한 있는 사용자 레코드를 보유하고, 토큰 발급과 검증을 담당한다.

### SsoToken 모델

모델은 의도적으로 최소한으로 유지했다. `valid` 스코프는 두 조건을 결합한다: 아직 사용되지 않았고(`used_at`이 nil), 만료되지 않은 토큰.

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

`client_id` 컬럼은 어느 SP가 토큰을 요청했는지 기록한다. 나중에 여러 SP를 지원해야 할 때 필터링이나 감사(audit)에 사용할 수 있다. `state` 컬럼은 CSRF 검증을 위해 SP가 전달한 값을 저장한다.

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

**포인트**: `require_authentication`이 미로그인 유저를 로그인 페이지로 보낼 때, SSO authorize URL 전체(쿼리 파라미터 포함)를 `session[:return_to]`에 저장해야 한다. OTP 인증 후 `redirect_back_or(dashboard_path)`로 돌아오면 SSO 흐름이 이어진다. 저장하지 않으면 로그인은 완료되지만 SSO 컨텍스트를 잃어버려 처음부터 다시 시작해야 한다.

**`/verify`에 `skip_before_action :verify_authenticity_token`을 쓰는 이유**: verify 엔드포인트는 브라우저 폼이 아닌 SP의 Rails 백엔드가 서버 간 호출로 접근한다. Rails CSRF 보호는 브라우저 세션 기반이므로 이 경우에는 적용되지 않는다. 서버 간 호출에서는 `X-Signature-SHA256`의 HMAC 서명이 동등한 보호 역할을 한다.

---

## SP 쪽 구현 (로그인 위임 서비스)

SP(Service Provider)는 심사/관리 시스템이다. 인증을 IdP에 위임하고, 검증된 사용자 정보를 돌려받는다.

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

`verify_token`은 네트워크 오류, 2xx가 아닌 응답, JSON 파싱 오류 등 모든 실패 케이스에서 예외를 던지지 않고 `nil`을 반환한다. 호출 코드는 `nil`을 인증 실패로 처리해 로그인 페이지로 리다이렉트한다.

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

**첫 로그인 시 유저 자동 프로비저닝**: 신규 SSO 유저는 랜덤 비밀번호(SSO를 통해서만 로그인하므로 실제로 사용되지 않음)와 기본 `reviewer` 역할로 자동 생성된다. `sso_provider: "internal"` 속성은 관리자 화면이나 쿼리에서 SSO 계정과 일반 Devise 계정을 구분하는 데 사용한다.

**`session.delete(:sso_state)` vs `session[:sso_state]`**: 읽기만 하지 않고 `delete`를 쓰는 것은 의도적이다. 단일 원자 연산으로 세션에서 state를 제거해, 이전 callback URL이 재전송되더라도 오래된 state 값을 재사용할 수 없게 막는다.

---

## Render 배포 시 삽질한 부분

### autoDeploy: no 서비스에서 env var 업데이트가 구 커밋으로 배포됨

환경변수를 Render API/MCP로 업데이트하면 자동으로 재배포가 트리거된다. 그런데 `autoDeploy: no`인 서비스는 **env var 업데이트 시점의 최신 커밋이 아니라 마지막으로 배포됐던 커밋**으로 빌드한다.

실제로 겪은 순서:

1. SSO 코드를 추가하고 저장소에 push
2. Render API로 `SSO_SHARED_SECRET`과 `IDP_URL` 업데이트
3. Render가 재배포 트리거 — 하지만 SSO 코드가 없는 이전 커밋으로 빌드
4. 로그인 버튼이 보이지 않는 이유가 여기 있었다

**해결**: Render REST API로 수동 배포 트리거.

```bash
curl -X POST "https://api.render.com/v1/services/{SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache": "do_not_clear"}'
```

응답에서 커밋 메시지와 SHA를 확인해 제대로 된 버전이 배포됐는지 검증할 수 있다.

---

## 프론트엔드: 로그인 버튼

Svelte + Inertia.js 환경에서 SSO 버튼은 **Inertia router가 아닌 일반 `<a>` 태그**를 써야 한다. Inertia는 내부 XHR 요청을 보내는데, SSO 흐름은 외부 서비스로 실제 페이지 이동(redirect)이 필요하기 때문이다. 브라우저가 IdP의 `/sso/authorize`로 실제 네비게이션을 해야 하고, IdP는 다시 SP의 callback URL로 리다이렉트한다. XHR은 이 리다이렉트 체인에 참여할 수 없다.

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

## 라우트 설정

양쪽 앱에 각각 라우트를 추가한다.

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

## 환경변수

양쪽 서비스가 동일한 `SSO_SHARED_SECRET` 값을 공유한다. 데이터베이스 비밀번호를 교체하는 것과 동일한 기준으로 관리하고 주기적으로 교체한다.

**IdP:**
```
SSO_SHARED_SECRET=<긴-랜덤-값>
SSO_ALLOWED_REDIRECT_URIS=https://review-system.example.com/sso/callback
```

**SP:**
```
SSO_SHARED_SECRET=<동일한-긴-랜덤-값>
IDP_URL=https://internal-app.example.com
```

---

## 핵심 체크리스트

- **OAuth2가 항상 정답은 아니다.** 두 내부 서비스 사이라면 One-Time Token + HMAC 조합이 훨씬 가볍고 직관적이다.
- **기존 패턴을 재사용하라.** 서비스 간 HMAC webhook이 이미 있다면, SSO에 동일 패턴을 적용해도 팀 전체가 보안 모델을 이미 이해하고 있다.
- **Token은 반드시 일회용이다.** `used_at` 컬럼과 `valid` 스코프가 함께 작동해 재전송 공격을 차단한다.
- **`ActiveSupport::SecurityUtils.secure_compare`는 선택이 아니다.** 일반 문자열 비교는 타이밍 공격에 취약하다. HMAC 검증에는 항상 상수 시간 비교를 사용한다.
- **`state` 파라미터로 CSRF를 방지한다.** SSO 시작 시마다 새로 생성하고, 세션에 저장하고, callback 검증 시 읽기만 하지 말고 `delete`로 삭제한다.
- **`redirect_uri` 화이트리스트는 필수다.** 오픈 리다이렉트와 유효한 토큰의 조합은 자격증명 탈취 취약점이 된다. 명시적 허용 목록으로 검증한다.
- **Render `autoDeploy: no` + env var 업데이트 = 구 코드 배포.** env var 업데이트 후 반드시 수동 배포를 트리거하고, 응답의 커밋 SHA를 확인한다.
- **Inertia.js 환경에서 SSO는 일반 `<a>` 태그를 사용한다.** Inertia의 XHR 기반 네비게이션은 리다이렉트 의존적인 인증 흐름을 망가뜨린다.
