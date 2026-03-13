---
title: "Apple Sign-In 403 Error: email_verified Type Mismatch and 3 Copy-Paste Bugs"
date: 2025-10-25
draft: false
tags: ["Rails", "Apple Sign-In", "OAuth", "JWT", "Debugging", "Flutter"]
description: "When Apple SSO login fails with 403 while Google works fine, the issue is the email_verified type difference in JWT and 3 bugs from code copy-paste."
cover:
  image: "/images/og/apple-sso-403-email-verified-type-mismatch.png"
  alt: "Apple Sso 403 Email Verified Type Mismatch"
  hidden: true
---

Apple Sign-In was failing with 403 Forbidden while Google Sign-In worked perfectly fine. Since Apple login worked correctly in another project using the same stack (Rails 8 + Flutter), I did a comparative analysis.

---

## Symptoms

- Apple login: **403 Forbidden**
- Google login: works fine
- Error message: `"Email not verified by Apple"`

---

## Cause 1: email_verified Type Mismatch (Core Issue)

Apple and Google return the `email_verified` field in JWT with **different types**.

| Provider | email_verified type | Example value |
|----------|---------------------|---------------|
| Google   | **boolean**         | `true`        |
| Apple    | **string or boolean** | `"true"` or `true` |

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
- `true == "true"` -> **`false`** (Ruby compares boolean with string)
- -> email_verified is set to false
- -> Controller returns 403

Google always returns boolean `true`, but the Google Auth Service used the value directly, so there was no issue:

```ruby
# Google Auth Service
email_verified: decoded_token["email_verified"]  # uses boolean as-is -> true
```

### Fix

```ruby
# AS-IS
email_verified: decoded_token["email_verified"] == "true"

# TO-BE: handles both boolean and string
email_verified: [true, "true"].include?(decoded_token["email_verified"])
```

---

## Cause 2: Unnecessary email_verified Forced Validation

The SSO controller was forcefully checking email_verified for Apple login:

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

Apple Sign-In inherently guarantees email verification through the Apple account itself, so this check is unnecessary. In fact, another project with the same stack didn't have this check and was working fine.

### Fix

Removed the email_verified validation block for Apple. Kept it for Google.

---

## Cause 3: Method Name Typo (Hidden Bug)

The error rendering method called on User creation failure had a typo:

```ruby
# SSO Controller
if user.persisted?
  # success handling...
else
  render_validation_error(user)   # singular - method doesn't exist!
end
```

The actual defined method:

```ruby
# ApiResponse concern
def render_validation_errors(record)  # plural - actual method
  # ...
end
```

This bug existed in the Google login code as well, but since Google User creation always succeeded, the else branch was never reached, so the bug was never exposed.

### Fix

```ruby
# AS-IS
render_validation_error(user)

# TO-BE
render_validation_errors(user)
```

---

## Why Did These Bugs Happen?

**Because Google SSO was implemented first, then that code was copy-pasted to create Apple SSO.**

```
Google SSO (original)                 Apple SSO (copy-paste)
───────────────────                   ──────────────────
email_verified: boolean true     ->   email_verified: string/boolean mixed
email always included            ->   email may be missing (Private Relay)
render_validation_error (typo)   ->   render_validation_error (typo copied)
```

- Google's type is consistent, so the string comparison wasn't a problem
- Google's User creation always succeeds, so the method typo was never exposed
- Apple hits both bugs

---

## Why Was Another Project Fine?

The other project with the same stack was using **Firebase Authentication**.

| Approach | Direct Apple JWT verification | Firebase token verification |
|----------|-------------------------------|---------------------------|
| email_verified handling | Manual type conversion needed | Firebase SDK normalizes |
| Verification logic | Manual implementation (RS256, public key) | Single `verify_firebase_token` call |
| Bug potential | High (types, missing fields, etc.) | Low (SDK handles it) |

With Firebase, you don't need to worry about email_verified type differences. But when verifying JWTs directly, you must check the **JWT spec differences between Apple and Google**.

---

## Lessons Learned

1. **Check the JWT spec for each provider** -- Apple and Google can have different types for the same field
2. **Always verify provider-specific differences after copy-paste** -- especially email_verified, email presence, and first login behavior
3. **Test error paths too** -- if you only test the happy path, you'll miss typos in the else branch
4. **When one provider works, do a comparative analysis** -- if Google works but Apple doesn't, the answer lies in the differences

---

## Apple vs Google JWT Differences Summary

| Field | Apple | Google |
|-------|-------|--------|
| `email_verified` | string `"true"` or boolean `true` | boolean `true` |
| `email` | Only provided on first login, Private Relay possible | Always provided |
| `name` | Only provided on first login | Always provided |
| Signing algorithm | RS256 | RS256 |
| Public Key URL | `appleid.apple.com/auth/keys` | `googleapis.com/oauth2/v3/certs` |
