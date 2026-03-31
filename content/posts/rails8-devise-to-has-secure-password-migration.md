---
title: "Rails 8에서 Devise 걷어내기 — has_secure_password로 마이그레이션한 실전 기록"
date: 2026-03-31
draft: false
tags: ["rails", "authentication", "devise", "has_secure_password", "inertia"]
description: "Rails 8.1 프로젝트에서 Devise를 제거하고 has_secure_password로 전환한 실전 경험. Warden의 request.params 버그, encrypted_password→password_digest 마이그레이션, JWT 직접 구현까지."
---

## Devise가 Inertia.js와 싸우기 시작했다

Rails 8 + Inertia.js + Svelte 5 스택으로 운영하던 프로젝트에서 로그인이 안 되는 버그가 터졌다. 에러 메시지도 없고, 401만 돌아왔다.

로그를 보니 Warden의 `database_authenticatable` strategy가 `valid_for_params_auth? = false`를 찍고 있었다. 쿼리가 0개 — DB에 접근조차 안 한 것이다.

원인은 Devise의 Warden 미들웨어가 `request.params[:user]`를 읽는데, Inertia.js는 `{email, password}`를 flat하게 보내서 Rails의 ParamsWrapper가 `session` 키로 감싸버리는 구조적 충돌이었다.

```ruby
# Inertia.js가 보내는 것
{ email: "user@example.com", password: "secret" }

# Rails ParamsWrapper가 변환한 것
{ email: "...", password: "...", session: { email: "...", password: "..." } }

# Devise/Warden이 찾는 것
{ user: { email: "...", password: "..." } }  # ← 이게 없다
```

`normalize_sign_in_params`라는 핵으로 `params[:user]`를 세팅했지만, Warden은 ActionController의 params가 아니라 **Rack 레벨의 `request.params`**를 따로 읽었다. 두 객체는 완전히 별개다.

---

## Warden의 이중 params 구조 — 근본 원인

Warden은 Rack 미들웨어다. Rails의 ActionController 레이어보다 아래에서 동작한다. 그래서 `params[:user] = {...}`를 컨트롤러에서 세팅해도 Warden은 모른다.

```ruby
# 컨트롤러에서 이렇게 세팅하면
params[:user] = { email: params[:email], password: params[:password] }

# Warden은 이걸 안 본다. 대신 이걸 본다:
request.params["user"]  # ← Rack::Request#params, 별도 객체
```

이 문제는 Devise GitHub Issues에서도 반복적으로 보고된 건이다. [#3978](https://github.com/heartcombo/devise/issues/3978)과 [#142](https://github.com/wardencommunity/warden/issues/142)에서 같은 현상이 논의됐다.

해결 방법은 두 가지였다:

1. `request.params`에도 같이 세팅하기 (땜질)
2. Devise를 아예 제거하기 (근본 해결)

```ruby
# 땜질 버전 — 이러면 동작은 한다
def normalize_sign_in_params
  user_params = { "email" => params[:email], "password" => params[:password] }
  params[resource_name] = user_params
  request.params[resource_name.to_s] = user_params  # Rack 레벨도 세팅
end
```

3개 컨트롤러(sessions, registrations, passwords)에 이 핵을 복붙해야 했다. 이건 유지보수 부채가 쌓이는 구조다.

---

## Rails 8의 인증 생태계 — 2026년 현재

Rails 8은 `rails generate authentication` 명령어로 내장 인증 스캐폴드를 제공한다. DHH가 Rails World 2024에서 직접 소개했고, Kaigi on Rails 2025에서 Maeshima Shinichi가 상세 발표한 바 있다.

생성되는 구조:

| 파일 | 역할 |
|------|------|
| `User` 모델 | `has_secure_password`, bcrypt 해싱 |
| `Session` 모델 | DB 기반 세션 추적, `has_secure_token` |
| `Current` 모델 | `ActiveSupport::CurrentAttributes` 기반 현재 사용자 |
| `Authentication` concern | `require_authentication`, `current_user`, `sign_in/out` |
| `SessionsController` | 로그인/로그아웃 |
| `PasswordsController` | 비밀번호 리셋 (토큰 기반) |

Devise와 비교하면:

| 기능 | Devise | Rails 8 내장 |
|------|--------|-------------|
| 로그인/로그아웃 | ✅ 자동 | ✅ 생성됨 |
| 회원가입 | ✅ registerable | ❌ 직접 구현 |
| 비밀번호 리셋 | ✅ recoverable | ✅ 생성됨 |
| 이메일 확인 | ✅ confirmable | ❌ 직접 구현 |
| 계정 잠금 | ✅ lockable | ❌ 직접 구현 |
| Remember me | ✅ rememberable | ❌ 직접 구현 |
| OmniAuth | ✅ omniauthable | ❌ 직접 연동 |
| 미들웨어 | Warden (Rack) | 없음 (컨트롤러 레벨) |
| 코드 가시성 | gem 내부 | 프로젝트 내 직접 코드 |
| Inertia.js 호환 | ⚠️ params 충돌 | ✅ 네이티브 호환 |

커뮤니티 흐름을 보면, 2025-2026년 기준으로 Devise는 "레거시 선택"으로 인식되기 시작했다. 새 프로젝트는 내장 auth를 쓰고, 기존 프로젝트도 마이그레이션하는 사례가 늘고 있다.

---

## 마이그레이션 실전: 핵심 변경 사항

### 1. encrypted_password → password_digest

Devise와 `has_secure_password`는 둘 다 bcrypt를 쓴다. 컬럼 이름만 다르다.

```ruby
# db/migrate/20260331_migrate_devise_to_has_secure_password.rb
class MigrateDeviseToHasSecurePassword < ActiveRecord::Migration[8.1]
  def change
    rename_column :users, :encrypted_password, :password_digest

    create_table :sessions do |t|
      t.references :user, null: false, foreign_key: true
      t.string :token, null: false
      t.string :ip_address
      t.string :user_agent
      t.timestamps
    end
    add_index :sessions, :token, unique: true
  end
end
```

rename만 하면 기존 비밀번호가 그대로 동작한다. bcrypt 해시 포맷이 동일하기 때문이다. 별도의 비밀번호 재해싱이나 사용자 재설정은 불필요하다.

단, Rails 3-4 시절부터 운영한 앱이라면 SHA-1 기반 레거시 해시가 섞여있을 수 있다. 이 경우 커스텀 인증 로직으로 레거시 해시 → bcrypt 자동 업그레이드를 구현해야 한다.

### 2. User 모델 — Devise 제거

```ruby
# Before
class User < ApplicationRecord
  devise :database_authenticatable, :registerable,
         :recoverable, :rememberable, :validatable,
         :jwt_authenticatable, jwt_revocation_strategy: JwtDenylist
end

# After
class User < ApplicationRecord
  has_secure_password

  has_many :sessions, dependent: :destroy

  validates :email, presence: true, uniqueness: true,
            format: { with: URI::MailTo::EMAIL_REGEXP }
  normalizes :email, with: ->(email) { email.strip.downcase }

  def self.authenticate_by(email:, password:)
    user = find_by(email: email.to_s.strip.downcase)
    user&.authenticate(password) || nil
  end
end
```

`has_secure_password`가 제공하는 것:
- `password`, `password_confirmation` 가상 속성
- `authenticate(password)` 메서드
- `password_digest` 컬럼에 bcrypt 해시 자동 저장
- 비밀번호 존재 검증 (생성 시)

### 3. Authentication Concern

Devise의 `authenticate_user!`, `current_user`, `user_signed_in?`을 대체한다.

```ruby
# app/controllers/concerns/authentication.rb
module Authentication
  extend ActiveSupport::Concern

  included do
    helper_method :current_user, :user_signed_in?
  end

  def sign_in(user)
    sess = user.sessions.create!(
      token: SecureRandom.urlsafe_base64(32),
      ip_address: request.remote_ip,
      user_agent: request.user_agent
    )
    session[:session_token] = sess.token
  end

  def sign_out
    current_session&.destroy
    session.delete(:session_token)
    @current_user = nil
  end

  def current_user
    @current_user ||= current_session&.user
  end

  def user_signed_in?
    current_user.present?
  end

  def authenticate_user!
    unless user_signed_in?
      flash[:alert] = "로그인이 필요합니다."
      redirect_to login_path
    end
  end

  private

  def current_session
    return @current_session if defined?(@current_session)
    token = session[:session_token]
    @current_session = Session.includes(:user).find_by(token: token) if token
  end
end
```

Devise와 메서드 이름을 동일하게 유지했다. 기존 코드에서 `before_action :authenticate_user!`나 `current_user` 호출을 하나도 안 바꿔도 된다.

### 4. SessionsController — 핵 제거

```ruby
# Before: normalize_sign_in_params 핵이 필요했음
module Web
  class SessionsController < Devise::SessionsController
    def create
      normalize_sign_in_params
      super
    end

    private
    def normalize_sign_in_params
      user_params = { "email" => params[:email], "password" => params[:password] }
      params[resource_name] = user_params
      request.params[resource_name.to_s] = user_params
    end
  end
end

# After: 직접 읽으면 끝
module Web
  class SessionsController < ApplicationController
    def create
      user = User.authenticate_by(
        email: params[:email],
        password: params[:password]
      )

      unless user
        flash[:alert] = "이메일 또는 비밀번호가 올바르지 않습니다."
        redirect_to login_path
        return
      end

      sign_in(user)
      redirect_to after_sign_in_path_for(user), notice: "로그인되었습니다."
    end
  end
end
```

Inertia.js가 보내는 flat params를 그대로 읽는다. Warden도 없고, normalize 핵도 없다. 30줄이면 충분하다.

---

## JWT 인증 — devise-jwt 대체

모바일 API용 JWT 인증도 직접 구현했다. `devise-jwt`가 내부적으로 `Warden::JWTAuth::UserEncoder`를 쓰는데, 이것도 Warden 의존이다.

```ruby
# app/services/jwt_service.rb
module JwtService
  SECRET = Rails.application.secret_key_base
  ALGORITHM = "HS256"

  def self.encode(user)
    payload = {
      sub: user.id,
      exp: 30.days.from_now.to_i,
      iat: Time.current.to_i
    }
    JWT.encode(payload, SECRET, ALGORITHM)
  end

  def self.decode(token)
    decoded = JWT.decode(token, SECRET, true, algorithm: ALGORITHM)
    decoded.first
  rescue JWT::DecodeError, JWT::ExpiredSignature
    nil
  end

  def self.revoke(token)
    payload = decode(token)
    JwtDenylist.create!(jti: payload["jti"]) if payload
  end
end
```

`jwt` gem 하나로 해결. `devise-jwt`의 500줄짜리 추상화 대신 50줄이면 된다.

---

## 마이그레이션 중 만난 함정들

### 함정 1: Inertia.js의 XHR 분기

마이그레이션 직후 로그인하면 JSON 응답이 그대로 화면에 뿌려지는 버그가 생겼다.

```
All Inertia requests must receive a valid Inertia response, 
however a plain JSON response was received.
{"success":true,"redirect_to":"/"}
```

원인은 새 SessionsController에서 `request.xhr?` 체크로 JSON 분기를 넣었는데, Inertia.js가 XHR(AJAX)로 요청을 보내서 JSON 분기로 빠진 것이다.

```ruby
# 잘못된 코드
if request.format.json? || request.xhr?
  render json: { success: true, redirect_to: "/" }  # Inertia도 여기로 빠짐
else
  redirect_to "/"
end

# 올바른 코드
redirect_to after_sign_in_path_for(user), notice: "로그인되었습니다."
```

Inertia.js 환경에서는 XHR/JSON 분기를 넣지 말고, 항상 redirect로 응답해야 한다. Inertia가 알아서 SPA 내비게이션으로 처리한다.

### 함정 2: prod DB 비밀번호 해시

`encrypted_password`를 `password_digest`로 rename한 뒤 Rails runner로 비밀번호를 재설정했는데, 로컬에서 동작 안 했다.

```ruby
u = User.find_by(email: "test@example.com")
u.authenticate("password123!")  # => false
```

원인: SQL로 직접 INSERT한 계정은 bcrypt 해시가 아니라 평문이 들어갔었다. `has_secure_password`의 `password=` 세터를 거쳐야 bcrypt로 해싱된다.

```ruby
# 올바른 방법
u.password = "password123!"
u.password_confirmation = "password123!"
u.save!
u.authenticate("password123!")  # => User 객체 반환
```

### 함정 3: devise.rb 초기화 파일

Devise를 Gemfile에서 제거하면 `config/initializers/devise.rb`에서 에러가 난다. 삭제하거나 `.bak`으로 이름 변경해야 한다.

```bash
# 에러
NameError: uninitialized constant Devise

# 해결
mv config/initializers/devise.rb config/initializers/devise.rb.bak
```

---

## 같이 진행한 Rails 8.0 → 8.1 업그레이드

Devise 제거와 동시에 Rails 버전도 올렸다. 8.1에서 주의할 변경:

```ruby
# deprecated (8.0)
ActiveRecord::Base.connection.execute("SELECT 1")

# 8.1 권장
ActiveRecord::Base.lease_connection.execute("SELECT 1")
```

`config.load_defaults`도 8.0 → 8.1로 변경. `config/application.rb`에서 한 줄 수정이면 된다.

---

## 마이그레이션 결과 비교

| 항목 | Before (Devise) | After (has_secure_password) |
|------|----------------|---------------------------|
| 인증 gem | devise + devise-jwt (2개) | jwt (1개) |
| 미들웨어 | Warden (Rack 레벨) | 없음 (컨트롤러 레벨) |
| normalize 핵 | 3개 컨트롤러에 중복 | 불필요 |
| 코드 가시성 | gem 내부 블랙박스 | 프로젝트 내 직접 코드 |
| Inertia.js 호환 | ⚠️ request.params 충돌 | ✅ 네이티브 |
| 총 변경 | 28 files, +558 -356 | — |
| 소요 시간 | — | 약 3시간 |

---

## Devise를 유지해야 하는 경우

모든 프로젝트에서 Devise를 제거해야 하는 건 아니다.

**Devise가 여전히 좋은 선택인 경우:**
- OmniAuth 연동이 복잡한 경우 (Google, Apple, GitHub 등 다수)
- Confirmable, Lockable, Timeoutable 등 고급 모듈을 적극 사용하는 경우
- 인증 로직을 직접 관리할 여유가 없는 소규모 팀

**제거를 권장하는 경우:**
- Inertia.js, Hotwire 등 모던 프론트엔드와 함께 쓰는 경우
- 실제 사용하는 Devise 모듈이 3개 이하인 경우
- Rails 8.1+ 에서 새로 시작하는 프로젝트
- Warden의 Rack 레벨 params 읽기 때문에 핵이 필요한 경우

내 경우 5개 모듈(database_authenticatable, registerable, recoverable, rememberable, validatable)만 썼고, 그 중 직접 구현이 어려운 건 없었다. 오히려 `has_secure_password` + `generates_token_for` 조합이 더 깔끔했다.

---

## 결론

Devise 제거의 핵심 이득은 "코드가 내 프로젝트 안에 있다"는 점이다. Warden이 `request.params`를 어떻게 읽는지, strategy 캐싱이 언제 초기화되는지 — 이런 걸 더 이상 몰라도 된다.

bcrypt 해시가 호환되기 때문에 `rename_column :encrypted_password, :password_digest` 한 줄로 기존 비밀번호를 보존할 수 있다. 이게 마이그레이션의 가장 큰 안심 포인트였다.

Rails 8.1의 `rails generate authentication`이 정식 스캐폴드를 제공하는 시점에서, Devise가 프로젝트에 가져다주는 가치보다 가져가는 복잡도가 더 크다면 제거를 고려해볼 만하다.
