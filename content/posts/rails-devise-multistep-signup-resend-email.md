---
title: "Rails 8 + Devise 다단계 회원가입 & Resend 이메일 삽질 기록"
date: 2025-12-20
draft: false
tags: ["Rails 8", "Devise", "Resend", "Svelte 5", "Inertia.js", "이메일", "디버깅"]
description: "역할별 조건부 다단계 회원가입 폼과 Resend 이메일 서비스 통합 과정에서 만난 삽질들 — gem 위치 오류, MAILER_FROM 미설정, Devise mailer sender 불일치까지."
cover:
  image: "/images/og/rails-devise-multistep-signup-resend-email.png"
  alt: "Rails Devise Multistep Signup Resend Email"
  hidden: true
---

Rails 8 + Inertia.js + Svelte 5 스택에서 역할별 다단계 회원가입과 Resend 이메일 서비스를 연동하면서 겪은 문제들을 정리한다.

---

## 1. 역할별 조건부 다단계 회원가입 폼

### 요구사항

사용자 역할이 두 종류인 서비스에서 회원가입 플로우를 다르게 가져가야 했다.

- **역할 A**: 기본 정보 → 업무 선택 → 소속 정보 (3단계)
- **역할 B**: 기본 정보 → 업무 선택 (2단계, 소속 정보 불필요)

### Svelte 5 Runes로 조건부 스텝 구현

`$derived`로 역할에 따라 전체 스텝 수와 버튼 동작을 동적으로 처리했다.

```svelte
<script lang="ts">
  let form = $state({
    name: '', email: '', password: '',
    role: '',       // 'type_a' | 'type_b'
    domain: '',
    company: '',
  });

  // 역할 A일 때만 3단계 소속 정보 스텝이 필요
  let needsOrgStep = $derived(form.role === 'type_a');
  let totalSteps = $derived(needsOrgStep ? 3 : 2);

  let currentStep = $state(1);

  function handleNext() {
    if (currentStep === 2 && !needsOrgStep) {
      // 역할 B: 2단계에서 바로 가입 완료
      submitForm();
    } else {
      currentStep++;
    }
  }

  async function submitForm() {
    // ...form submit
  }
</script>

<!-- Step 2: 역할 선택 -->
{#if currentStep === 2}
  <!-- 역할 카드 선택 UI -->
  <button onclick={handleNext}>
    {needsOrgStep ? '다음' : '가입 완료'}
  </button>
{/if}

<!-- Step 3: 소속 정보 (역할 A만) -->
{#if currentStep === 3 && needsOrgStep}
  <!-- 소속 정보 입력 -->
{/if}
```

핵심은 Step 2의 버튼 텍스트와 클릭 동작을 `needsOrgStep`으로 분기한 것이다. 버튼이 하나인데 두 가지 역할을 해야 할 때 `$derived`가 깔끔하게 해결해줬다.

### Rails 컨트롤러 — 역할 화이트리스트

관리자는 자가 등록을 막아야 했다. 화이트리스트 방식으로 처리했다.

```ruby
# app/controllers/web/registrations_controller.rb
ALLOWED_ROLES = %w[type_a type_b].freeze

def allowed_role(value)
  ALLOWED_ROLES.include?(value) ? value : nil
end

def build_resource(hash = {})
  super
  resource.role = allowed_role(params[:role]) || :type_a
  resource.domain = params[:domain]
end
```

프론트에서 어떤 값을 보내도 화이트리스트에 없으면 기본값으로 처리된다.

---

## 2. Resend 이메일 서비스 통합

### 기본 설정

```ruby
# Gemfile
gem "resend", "~> 0.15"
```

```ruby
# config/initializers/resend.rb
Resend.api_key = ENV.fetch("RESEND_API_KEY", nil)
```

```ruby
# config/environments/production.rb
config.action_mailer.delivery_method = :resend
```

개발 환경에서는 API 키가 없을 때 로거로 fallback:

```ruby
# config/environments/development.rb
if ENV["RESEND_API_KEY"].present?
  config.action_mailer.delivery_method = :resend
else
  config.action_mailer.delivery_method = :logger
end
```

### 웰컴 이메일

```ruby
# app/mailers/user_mailer.rb
class UserMailer < ApplicationMailer
  def welcome_email(user)
    @user = user
    @login_url = root_url + "login"
    mail(
      to: @user.email,
      subject: "가입을 환영합니다, #{@user.name}님"
    )
  end
end
```

```ruby
# Devise 회원가입 성공 후
UserMailer.welcome_email(resource).deliver_later
```

---

## 3. 삽질 1: `NameError: uninitialized constant Resend`

### 증상

개발 환경에서 서버를 올리자마자 에러 발생.

```
NameError: uninitialized constant Resend (config/initializers/resend.rb)
```

### 원인

`resend` gem이 `:production` group에만 선언되어 있었다.

```ruby
# 문제: production 그룹에만 있어서 development에서 못 찾음
group :production do
  gem "resend", "~> 0.15"
end
```

`config/initializers/resend.rb`는 모든 환경에서 로드되는데, gem이 없으니 상수 자체가 없는 것.

### 해결

```ruby
# Gemfile — 전역으로 이동
gem "resend", "~> 0.15"

group :production do
  gem "sentry-ruby"
  # ...
end
```

`bundle install` 후 해결.

---

## 4. 삽질 2: Devise 이메일이 `noreply@localhost`로 발송

### 증상

비밀번호 재설정 메일이 Resend 대시보드에서 막힘. 발신자 주소가 `noreply@localhost`.

### 원인

Devise는 `config.mailer_sender`를 보는데, 이게 설정 안 되어 있으면 `noreply@localhost`가 기본값.

```ruby
# config/initializers/devise.rb
config.mailer_sender = 'noreply@localhost'  # 기본값
```

Resend는 인증된 도메인이 아니면 `onboarding@resend.dev`만 발신자로 허용한다 (무료 테스트용).

### 해결

```bash
# .env
DEVISE_MAILER_SENDER=onboarding@resend.dev
MAILER_FROM=onboarding@resend.dev
```

```ruby
# config/initializers/devise.rb
config.mailer_sender = ENV.fetch("DEVISE_MAILER_SENDER", "noreply@example.com")
```

```ruby
# app/mailers/application_mailer.rb
class ApplicationMailer < ActionMailer::Base
  default from: ENV.fetch("MAILER_FROM", "noreply@example.com")
  layout "mailer"
end
```

### 핵심 포인트

Resend 무료 플랜에서 도메인 미인증 상태면 `onboarding@resend.dev`만 사용 가능하고, 이 주소는 **Resend 가입 이메일로만** 수신 테스트가 된다. 프로덕션에서 실제 사용자에게 발송하려면 도메인 인증 필수.

---

## 5. 삽질 3: 기존 Mailer의 하드코딩된 from 주소

### 증상

`UserMailer`는 정상 발송되는데, `NotificationMailer`는 발송 실패.

### 원인

기존 Mailer에 from 주소가 하드코딩되어 있었다.

```ruby
class NotificationMailer < ApplicationMailer
  # 이 주소는 Resend에서 인증 안 된 도메인
  default from: "서비스명 <noreply@example.kr>"
end
```

### 해결

하드코딩된 `default from:` 제거. `ApplicationMailer`에서 `ENV["MAILER_FROM"]`을 읽으므로 상속만 하면 된다.

```ruby
class NotificationMailer < ApplicationMailer
  # default from: 제거 → ApplicationMailer 상속
end
```

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| `NameError: uninitialized constant Resend` | gem이 `:production` group에만 있음 | 전역으로 이동 |
| Devise 메일이 `noreply@localhost` 발송 | `DEVISE_MAILER_SENDER` 미설정 | `.env`에 명시 |
| 특정 Mailer 발송 실패 | 하드코딩된 미인증 발신자 주소 | `ApplicationMailer` 상속 |

### Render 배포 시 환경변수

```yaml
# render.yaml
envVars:
  - key: RESEND_API_KEY
    sync: false        # 대시보드에서 직접 입력
  - key: MAILER_FROM
    value: onboarding@resend.dev
  - key: DEVISE_MAILER_SENDER
    value: onboarding@resend.dev
```

Resend는 Rails의 ActionMailer와 궁합이 좋다. `delivery_method = :resend` 한 줄로 붙고, SMTP 설정 없이 동작한다. 도메인 인증만 하면 바로 프로덕션에서 쓸 수 있다.
