---
title: "Google One Tap Returns 200 But Session Doesn't Persist"
date: 2026-03-08
draft: false
tags: ["Rails", "Devise", "Google One Tap", "OAuth", "Session", "Debugging"]
description: "Google One Tap login returns 200 OK, but navigating to the dashboard redirects back to the sign-in page. The root cause was setting session[:user_id] directly instead of using Devise's sign_in method."
---

Google One Tap login returns 200 OK. The frontend handles the redirect. Everything looks fine. Then the user hits the dashboard and gets bounced back to the login page.

---

## Symptoms

Server logs:

```
POST /users/auth/google_one_tap → 200 OK (36ms)
GET  /dashboard                 → 302 Found
     Redirected to /users/sign_in
     Filter chain halted as :require_web_user! rendered or redirected
GET  /users/sign_in             → 200 OK
```

The One Tap endpoint succeeded. The redirect happened. The response looked correct. But the auth filter blocked access to the dashboard.

---

## Root Cause

Looking at the controller code, the problem is immediately visible.

**One Tap action (buggy code):**

```ruby
def google_one_tap
  # ... token verification and user lookup ...

  reset_session
  session[:user_id] = user.id           # ← the problem
  session[:authenticated_at] = Time.current.iso8601

  render json: { success: true, redirect_to: dashboard_path }
end
```

**Auth filter:**

```ruby
def require_web_user!
  return if user_signed_in?  # checks Devise warden session
  redirect_to '/users/sign_in'
end
```

Writing to `session[:user_id]` means nothing to `user_signed_in?`.

Devise manages sessions through warden, an authentication middleware. Warden stores its own session key (something like `warden.user.user.key`), not `session[:user_id]`. Since `user_signed_in?` checks the warden session, manually setting `session[:user_id]` has no effect on authentication state.

The One Tap endpoint "succeeded," but **from Devise's perspective, nobody logged in.**

### Comparison with email/password login

The regular login action uses Devise's `sign_in` method:

```ruby
def create
  # ...
  sign_in(user, remember_me: remember_me)  # Devise writes to warden session
  redirect_to dashboard_path
end
```

Only the One Tap action was using a different approach.

---

## Fix

```ruby
def google_one_tap
  # ... token verification and user lookup ...

  # BEFORE
  # reset_session
  # session[:user_id] = user.id
  # session[:authenticated_at] = Time.current.iso8601

  # AFTER: same as regular login — use Devise sign_in
  clear_auth_bridge_session!
  reset_session
  sign_in(user, remember_me: true)

  render json: { success: true, redirect_to: dashboard_path }
end
```

Calling `sign_in(user)` tells Devise to record the user in the warden session. After that, `user_signed_in?` correctly returns `true`.

---

## How Did This Happen?

Google One Tap has a different flow from standard form login or OmniAuth callbacks. The frontend receives a Google credential token and POSTs it directly to a backend endpoint — no OmniAuth redirect involved. This means you write a custom action from scratch.

When writing a custom action like this, it's easy to treat it like a JSON API endpoint and reach for `session[:user_id] = user.id`. That approach works fine in an API-only app using token auth. But **in a session-based web app using Devise, you must go through `sign_in`** — that's the only way to write to the warden session.

---

## Lessons

1. **Always use Devise's `sign_in` in a Devise app** — writing to `session[:user_id]` directly is invisible to Devise's auth checks
2. **200 OK doesn't mean success** — verify that the intended side effect (session persistence, successful redirect) actually happened
3. **Read the logs in sequence** — POST succeeds then GET returns 302: the POST didn't save state correctly
4. **Compare with a working similar action** — putting the regular login action and the One Tap action side by side made the difference immediately obvious

---

## Devise Session vs Direct Session

| Approach | Code | user_signed_in? | When to use |
|----------|------|-----------------|-------------|
| Devise sign_in | `sign_in(user)` | true | Session-based web auth |
| Direct session | `session[:user_id] = user.id` | false | Non-Devise apps |
| warden directly | `warden.set_user(user)` | true | Low-level access (not recommended) |

In a Rails + Devise stack, `sign_in` is the right call.
