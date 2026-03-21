---
title: "Rails 8 + Devise Multi-Step Signup & Resend Email Debugging"
date: 2025-12-20
draft: false
tags: ["Rails 8", "Devise", "Resend", "Svelte 5", "Inertia.js", "Email", "Debugging"]
description: "Debugging struggles with role-based conditional multi-step signup form and Resend email service integration — gem placement error, missing MAILER_FROM, and Devise mailer sender mismatch."
cover:
  image: "/images/og/rails-devise-multistep-signup-resend-email.png"
  alt: "Rails Devise Multistep Signup Resend Email"
  hidden: true
categories: ["Rails"]
---


This documents the problems encountered while integrating role-based multi-step signup and the Resend email service on a Rails 8 + Inertia.js + Svelte 5 stack.

---

## 1. Role-Based Conditional Multi-Step Signup Form

### Requirements

In a service with two user roles, the signup flow needed to differ:

- **Role A**: Basic info -> Work selection -> Organization info (3 steps)
- **Role B**: Basic info -> Work selection (2 steps, organization info unnecessary)

### Implementing Conditional Steps with Svelte 5 Runes

Used `$derived` to dynamically handle total step count and button behavior based on role.

```svelte
<script lang="ts">
  let form = $state({
    name: '', email: '', password: '',
    role: '',       // 'type_a' | 'type_b'
    domain: '',
    company: '',
  });

  // Only role A needs the 3rd step for organization info
  let needsOrgStep = $derived(form.role === 'type_a');
  let totalSteps = $derived(needsOrgStep ? 3 : 2);

  let currentStep = $state(1);

  function handleNext() {
    if (currentStep === 2 && !needsOrgStep) {
      // Role B: complete signup directly from step 2
      submitForm();
    } else {
      currentStep++;
    }
  }

  async function submitForm() {
    // ...form submit
  }
</script>

<!-- Step 2: Role selection -->
{#if currentStep === 2}
  <!-- Role card selection UI -->
  <button onclick={handleNext}>
    {needsOrgStep ? 'Next' : 'Complete Signup'}
  </button>
{/if}

<!-- Step 3: Organization info (Role A only) -->
{#if currentStep === 3 && needsOrgStep}
  <!-- Organization info input -->
{/if}
```

The key was branching the Step 2 button text and click behavior using `needsOrgStep`. When a single button needs to serve two purposes, `$derived` solves it cleanly.

### Rails Controller -- Role Whitelist

Admin self-registration needed to be blocked. Handled with a whitelist approach.

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

No matter what value the frontend sends, if it is not in the whitelist, it falls back to the default.

---

## 2. Resend Email Service Integration

### Basic Setup

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

In the development environment, fallback to logger when there is no API key:

```ruby
# config/environments/development.rb
if ENV["RESEND_API_KEY"].present?
  config.action_mailer.delivery_method = :resend
else
  config.action_mailer.delivery_method = :logger
end
```

### Welcome Email

```ruby
# app/mailers/user_mailer.rb
class UserMailer < ApplicationMailer
  def welcome_email(user)
    @user = user
    @login_url = root_url + "login"
    mail(
      to: @user.email,
      subject: "Welcome, #{@user.name}"
    )
  end
end
```

```ruby
# After successful Devise registration
UserMailer.welcome_email(resource).deliver_later
```

---

## 3. Issue 1: `NameError: uninitialized constant Resend`

### Symptoms

Error occurs immediately when starting the server in the development environment.

```
NameError: uninitialized constant Resend (config/initializers/resend.rb)
```

### Cause

The `resend` gem was declared only in the `:production` group.

```ruby
# Problem: only in production group, so development cannot find it
group :production do
  gem "resend", "~> 0.15"
end
```

`config/initializers/resend.rb` loads in all environments, but since the gem is missing, the constant itself does not exist.

### Solution

```ruby
# Gemfile -- move to global scope
gem "resend", "~> 0.15"

group :production do
  gem "sentry-ruby"
  # ...
end
```

Resolved after `bundle install`.

---

## 4. Issue 2: Devise Email Sent from `noreply@localhost`

### Symptoms

Password reset email blocked in the Resend dashboard. Sender address was `noreply@localhost`.

### Cause

Devise looks at `config.mailer_sender`, and when not configured, the default is `noreply@localhost`.

```ruby
# config/initializers/devise.rb
config.mailer_sender = 'noreply@localhost'  # default value
```

Resend only allows `onboarding@resend.dev` as a sender for unauthenticated domains (for free testing).

### Solution

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

### Key Point

On Resend's free plan without domain verification, only `onboarding@resend.dev` is available, and this address can only receive test emails sent **to the Resend signup email**. Domain verification is required to send to actual users in production.

---

## 5. Issue 3: Hardcoded From Address in Existing Mailer

### Symptoms

`UserMailer` sends successfully, but `NotificationMailer` fails.

### Cause

The existing Mailer had a hardcoded from address.

```ruby
class NotificationMailer < ApplicationMailer
  # This address is an unauthenticated domain on Resend
  default from: "ServiceName <noreply@example.kr>"
end
```

### Solution

Remove the hardcoded `default from:`. Since `ApplicationMailer` reads from `ENV["MAILER_FROM"]`, just inheriting is enough.

```ruby
class NotificationMailer < ApplicationMailer
  # default from: removed -> inherits from ApplicationMailer
end
```

---

## Summary

| Problem | Cause | Solution |
|---------|-------|----------|
| `NameError: uninitialized constant Resend` | Gem only in `:production` group | Move to global scope |
| Devise email sent from `noreply@localhost` | `DEVISE_MAILER_SENDER` not configured | Specify in `.env` |
| Specific Mailer send failure | Hardcoded unauthenticated sender address | Inherit from `ApplicationMailer` |

### Environment Variables for Render Deployment

```yaml
# render.yaml
envVars:
  - key: RESEND_API_KEY
    sync: false        # Enter directly in dashboard
  - key: MAILER_FROM
    value: onboarding@resend.dev
  - key: DEVISE_MAILER_SENDER
    value: onboarding@resend.dev
```

Resend pairs well with Rails ActionMailer. It plugs in with a single line `delivery_method = :resend` and works without SMTP configuration. Once you verify your domain, it is ready for production use.
