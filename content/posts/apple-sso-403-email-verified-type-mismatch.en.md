---
title: "Apple Sign-In 403 Error: email_verified Type Mismatch and 3 Copy-Paste Bugs"
date: 2025-10-25
draft: false
tags: ["Rails", "Apple Sign-In", "OAuth", "JWT", "Debugging", "Flutter"]
categories: ["iOS", "Flutter"]
description: "When Apple SSO login fails with 403 while Google works fine, the issue is the email_verified type difference in JWT and 3 bugs from code copy-paste."
cover:
  image: "/images/og/apple-sso-403-email-verified-type-mismatch.png"
  alt: "Apple Sso 403 Email Verified Type Mismatch"
  hidden: true
---

Apple Sign-In was failing with 403 Forbidden while Google Sign-In worked perfectly fine. Since Apple login worked correctly in another project using the same stack (Rails 8 + Flutter), I did a comparative analysis to find the root cause.

The short answer: three independent bugs existed simultaneously, and all three originated from copy-pasting the Google SSO implementation to create the Apple SSO implementation.

---

## Symptoms

- Apple login: **403 Forbidden**
- Google login: works fine
- Error message: `"Email not verified by Apple"`
- Reproducible in production only, not in development (Apple test account quirk)

---

## Background: Apple and Google JWTs Are Not the Same

The OAuth 2.0 / OIDC specification says the `email_verified` claim should be a boolean. In practice, Apple sometimes returns this field as the **string `"true"`** instead of the boolean `true`. This edge case is not clearly documented in Apple's official developer documentation.

Decoding an Apple ID JWT directly reveals:

```json
// Apple JWT payload example 1 (boolean)
{
  "iss": "https://appleid.apple.com",
  "sub": "000123.abcdef...",
  "email": "user@privaterelay.appleid.com",
  "email_verified": true
}

// Apple JWT payload example 2 (string — this is the problem)
{
  "iss": "https://appleid.apple.com",
  "sub": "000123.abcdef...",
  "email": "user@privaterelay.appleid.com",
  "email_verified": "true"
}
```

Google always returns a boolean. This inconsistency is the root of the first bug.

---

## Cause 1: email_verified Type Mismatch (Core Issue)

Apple and Google return the `email_verified` field in JWT with **different types**.

| Provider | email_verified type   | Example value        |
|----------|-----------------------|----------------------|
| Google   | **boolean**           | `true`               |
| Apple    | **string or boolean** | `"true"` or `true`   |

The problematic code:

```ruby
# Apple Auth Service
{
  uid: decoded_token["sub"],
  email: decoded_token["email"],
  email_verified: decoded_token["email_verified"] == "true"  # string comparison
}
```

When Apple returns boolean `true`:
- `true == "true"` evaluates to **`false`** in Ruby (strict type comparison, no implicit coercion)
- `email_verified` is set to `false`
- The controller returns 403

Google always returns boolean `true`, and the Google Auth Service used the value directly without any comparison, so there was no issue:

```ruby
# Google Auth Service
email_verified: decoded_token["email_verified"]  # uses boolean as-is -> true
```

Ruby's `==` operator performs strict type comparison. Unlike JavaScript, there is no implicit type coercion — `true == "true"` is always `false`.

### Fix

```ruby
# Before
email_verified: decoded_token["email_verified"] == "true"

# After: handles both boolean and string
email_verified: [true, "true"].include?(decoded_token["email_verified"])
```

Using `Array#include?` evaluates both `true` (boolean) and `"true"` (string) as truthy. Regardless of which type Apple returns, the check works correctly.

A more defensive alternative:

```ruby
# Explicit defensive approach
email_verified: decoded_token["email_verified"].to_s == "true"
```

Calling `.to_s` first converts both boolean and string to a string before comparison. A bonus: if the value is `nil`, `.to_s` returns `""`, which evaluates to `false` — so `nil` is handled automatically.

---

## Cause 2: Unnecessary email_verified Forced Validation

The SSO controller was forcefully checking `email_verified` for Apple login:

```ruby
def apple
  user_info = AppleAuthService.verify_identity_token(identity_token)

  # This check returns 403
  unless user_info[:email_verified]
    return render_forbidden("Email not verified by Apple")
  end
  # ...
end
```

This code was carried over unchanged from the Google SSO implementation via copy-paste. While an `email_verified` check might make sense for Google in some contexts, **Apple Sign-In already guarantees email verification at the Apple account level**.

According to Apple's developer documentation:
- Users logging in with Apple Sign-In must have an Apple ID
- Creating an Apple ID requires email verification
- Therefore, any user arriving through Apple Sign-In has an already-verified email address

In other words, an Apple Sign-In user with `email_verified: false` cannot exist under normal circumstances. This validation check had no defensive value. Instead, it combined with the type mismatch bug in Cause 1 to block legitimate users with a 403.

### Fix

Remove the `email_verified` validation block from the Apple controller. Keep it in the Google controller.

```ruby
def apple
  user_info = AppleAuthService.verify_identity_token(identity_token)

  # Removed email_verified check — Apple Sign-In already guarantees email verification
  # ...
end
```

---

## Cause 3: Method Name Typo (Hidden Bug)

The error rendering method called on User creation failure had a typo:

```ruby
# SSO Controller
if user.persisted?
  # success handling...
else
  render_validation_error(user)   # singular — this method does not exist!
end
```

The actual defined method:

```ruby
# ApiResponse concern
def render_validation_errors(record)  # plural — the real method
  # ...
end
```

This bug existed in the Google SSO code as well, but Google's User creation always succeeds, so the `else` branch was never reached, and the typo was never exposed.

Had this code actually been executed, it would have raised a `NoMethodError`. In a Rails API server, an unhandled exception typically results in a 500 response. In practice, Causes 1 and 2 triggered a 403 before this code was ever reached, which is why the typo went undetected.

### Fix

```ruby
# Before
render_validation_error(user)

# After
render_validation_errors(user)
```

---

## Why Did These Bugs Happen?

**Google SSO was implemented first, then that code was copy-pasted to create Apple SSO.**

```
Google SSO (original)                   Apple SSO (copy-paste)
─────────────────────────               ─────────────────────────────
email_verified: boolean true       ->   email_verified: string/boolean mixed
email always present               ->   email may be absent (Private Relay)
render_validation_error (typo)     ->   render_validation_error (typo copied)
```

- Google's type is consistent, so the string comparison never triggered the bug
- Google's User creation always succeeds, so the method name typo was never reached
- Apple exposed both bugs immediately

This is the core danger of copy-paste-based development: **the original code's bugs and the assumptions it was built on propagate to the new code**. The fact that the original works perfectly actually hides the defects in the copy.

---

## The Apple Private Relay Problem: email Also Needs Attention

While debugging the `email_verified` issue, another difference became apparent: the `email` field also behaves differently from Google.

Apple Sign-In includes a **Private Relay** feature. When a user chooses not to share their real email with an app, Apple provides an anonymous email on the `@privaterelay.appleid.com` domain. Critically, **this email is only included in the JWT on the first login**.

```
First login:  email = "abc123@privaterelay.appleid.com"  <- present in JWT
Re-login:     email = nil  <- absent from JWT
```

Google always returns the real email address. If the copy-pasted Apple code does not handle a `nil` email, the result is either a database constraint violation (NOT NULL) or unexpected behavior in email-dependent logic.

```ruby
# Apple Auth Service — nil email must be handled
{
  uid: decoded_token["sub"],
  email: decoded_token["email"],  # can be nil!
  email_verified: [true, "true"].include?(decoded_token["email_verified"])
}
```

The `sub` field is always present in Apple JWTs. Apple users should be identified primarily by `sub`, treating `email` as supplementary information that may not always be available.

---

## Why Was Another Project Fine?

The other project using the same stack was using **Firebase Authentication**.

| Approach                  | Direct Apple JWT verification         | Firebase token verification         |
|---------------------------|---------------------------------------|--------------------------------------|
| `email_verified` handling | Manual type conversion required       | Firebase SDK normalizes it           |
| Verification logic        | Manual implementation (RS256, JWKS)   | Single `verify_firebase_token` call  |
| Public key management     | Must fetch from Apple JWKS endpoint   | Firebase SDK handles it              |
| Bug potential             | High (types, missing fields, etc.)    | Low (SDK abstracts the differences)  |

With Firebase, you never need to worry about `email_verified` type differences. Firebase Authentication normalizes the differences between Apple, Google, Facebook, and other providers internally, exposing a consistent interface regardless of the underlying JWT structure.

Choosing to verify JWTs directly is a valid architectural decision — it removes the Firebase dependency and reduces vendor lock-in — but it comes with the responsibility of handling every provider's quirks manually.

---

## Apple JWT Verification Checklist

When verifying Apple Sign-In JWTs directly, make sure to cover:

1. **`email_verified` type**: handle both boolean `true` and string `"true"`
2. **`email` may be absent**: use `sub` as the primary identifier; treat `email` as optional
3. **`name` only on first login**: `given_name` and `family_name` are absent on subsequent logins
4. **Cache the public keys**: responses from `https://appleid.apple.com/auth/keys` should be cached (respect cache headers)
5. **Validate `iss`**: must be `https://appleid.apple.com`
6. **Validate `aud`**: must match your Bundle ID or Service ID
7. **Validate `exp`**: reject expired tokens (Apple tokens expire after 10 minutes)

---

## Apple vs Google JWT Differences Summary

| Field               | Apple                                      | Google                          |
|---------------------|--------------------------------------------|---------------------------------|
| `email_verified`    | string `"true"` or boolean `true`          | boolean `true`                  |
| `email`             | Only on first login, Private Relay possible | Always present                 |
| `name`              | Only on first login                        | Always present                  |
| Signing algorithm   | RS256                                      | RS256                           |
| Public Key URL      | `appleid.apple.com/auth/keys`              | `googleapis.com/oauth2/v3/certs` |
| `sub` format        | `000123.abc...` (contains a dot)           | Numeric string                  |
| Token expiry        | 10 minutes                                 | 1 hour                          |

---

## Key Takeaways

- **Apple's `email_verified` can be either a boolean or a string.** A simple `== "true"` comparison evaluates boolean `true` as `false`. Use `[true, "true"].include?()` or `.to_s == "true"` instead.
- **Apple Sign-In already guarantees email verification.** Re-validating `email_verified` in your controller is unnecessary, and when combined with the type bug, it blocks legitimate users.
- **Copy-pasting a Provider implementation inherits the original's assumptions.** Hidden typos in the Google code, and type handling designed only for Google's consistent boolean, transfer unchanged into the Apple code.
- **Test error paths explicitly.** Testing only the happy path leaves bugs in the `else` branch undiscovered until production.
- **When one provider succeeds and another fails, the differences are the answer.** A side-by-side comparison of provider JWT specs is the most direct path to the root cause.
- **Firebase abstracts all of this.** Choosing direct JWT verification is a valid trade-off, but it means owning every provider-specific quirk yourself.
