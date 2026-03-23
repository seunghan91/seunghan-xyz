---
title: "Google One Tap Returns 200 But Session Doesn't Persist"
date: 2026-03-08
draft: true
tags: ["Rails", "Devise", "Google One Tap", "OAuth", "Session", "Debugging"]
description: "Google One Tap login returns 200 OK, but navigating to the dashboard redirects back to the sign-in page. The root cause was setting session[:user_id] directly instead of using Devise's sign_in method."
---

Google One Tap login returns 200 OK. The frontend handles the redirect. Everything looks fine. Then the user hits the dashboard and gets bounced back to the login page.

At first this looks like a CORS issue, a SameSite cookie problem, or a bug in the frontend redirect logic. The actual cause is simpler — and more embarrassing: a fundamental misunderstanding of how Devise manages session state.

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

What makes this especially confusing: if you inspect the session in the Rails console right after the One Tap request, `session[:user_id]` is set correctly. The server said success, the session has a value — so why does the auth filter say the user is not authenticated?

---

## Background: How Google One Tap Works

Google One Tap differs from a standard OAuth 2.0 redirect flow in a significant way.

Standard OAuth works like this: user clicks "Sign in with Google" → browser redirects to Google's auth page → user approves → Google redirects back to your callback URL → OmniAuth processes the callback on the server side. OmniAuth handles a lot of the heavy lifting, including session management.

One Tap works differently. The Google SDK runs in the browser and issues a credential token (a signed JWT) directly to the page. Your frontend JavaScript receives that token and POSTs it to your backend. There is no server-side redirect. There is no OmniAuth callback. You write a custom controller action from scratch and handle everything yourself.

This is where the mistake happens. When you implement everything from scratch, you also have to implement the parts that OmniAuth was quietly doing for you — including the part where Devise gets told about the logged-in user.

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

### How Devise and Warden Interact

Devise does not implement authentication logic directly. It delegates to [warden](https://github.com/wardencommunity/warden), a Rack middleware layer that manages its own session structure independently of the regular Rails session hash.

When Devise authenticates a user, warden stores something like this in the session:

```ruby
session["warden.user.user.key"] = [[user.id], user.authenticatable_salt]
```

`user_signed_in?` internally calls `warden.authenticated?(:user)`, which checks for the presence and validity of `session["warden.user.user.key"]`. It never looks at `session[:user_id]`. Those are completely separate keys.

So from the One Tap endpoint's perspective, the login succeeded. From Devise's perspective, **nobody logged in.** The session contains a `user_id`, but the warden session — the only thing `user_signed_in?` cares about — is empty.

### Comparison with Email/Password Login

The regular login action uses Devise's `sign_in` method:

```ruby
def create
  # ...
  sign_in(user, remember_me: remember_me)  # Devise writes to warden session
  redirect_to dashboard_path
end
```

`sign_in` internally calls `warden.set_user(user)`, which writes the correct session structure. After that call, `user_signed_in?` returns `true`.

Only the One Tap action was using a different approach.

---

## Fix

```ruby
def google_one_tap
  # ... token verification and user lookup ...

  # BEFORE (broken)
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

The `remember_me: true` flag is optional. One Tap is a low-friction gesture, not an explicit "log me in" action, so whether to grant a persistent session is a product decision.

---

## How Did This Happen?

Google One Tap has a different flow from standard form login or OmniAuth callbacks. The frontend receives a Google credential token and POSTs it directly to a backend endpoint — no OmniAuth redirect involved. This means you write a custom action from scratch.

When writing a custom action that accepts JSON and returns JSON, the mental model shifts toward "API endpoint." In an API-only app using token-based auth, writing `session[:user_id] = user.id` might even be the right call. But **in a session-based web app using Devise, you must go through `sign_in`** — that is the only path into the warden session that `user_signed_in?` will recognize.

There is a second subtle issue: the order of `reset_session` and `sign_in` matters. `reset_session` invalidates the current session and issues a new session ID, which is the correct defense against session fixation attacks. It must be called before `sign_in`, not after — calling it after `sign_in` would wipe the warden session you just wrote.

---

## Debugging Process

Here is what the investigation actually looked like, in order.

**Step 1: Browser DevTools → Network tab**

Checked the Set-Cookie header on the POST response. The session cookie was being issued correctly. The problem was not in cookie transmission.

**Step 2: Decode the session in the Rails console**

Used `ActionDispatch::Session::CookieStore` to decode the session cookie contents. `user_id` was present. `warden.user.user.key` was absent. This narrowed the problem to the Devise/warden layer.

**Step 3: Trace the `user_signed_in?` method**

Opened the Devise source: `user_signed_in?` → `warden.authenticated?(:user)` → checks `session["warden.user.user.key"]`. No reference to `session[:user_id]` anywhere in that chain.

**Step 4: Put the working login action next to the broken one**

`sessions#create` uses `sign_in`. The One Tap action does not. That was the complete diff.

---

## Devise Session vs Direct Session

| Approach | Code | user_signed_in? | When to use |
|----------|------|-----------------|-------------|
| Devise sign_in | `sign_in(user)` | true | Session-based web auth |
| Direct session | `session[:user_id] = user.id` | false | Non-Devise apps |
| warden directly | `warden.set_user(user)` | true | Low-level access (not recommended) |

`warden.set_user(user)` technically works but bypasses Devise's internal hooks — callbacks like `after_sign_in_path_for`, `after_sign_in` hooks, and tracking logic. `sign_in` runs all of those correctly. Unless you have a specific reason to drop to the warden layer, always use `sign_in`.

In a Rails + Devise stack, `sign_in` is the right call.

---

## Key Takeaways

1. **Always use Devise's `sign_in` in a Devise app** — writing to `session[:user_id]` is invisible to Devise's authentication checks. Devise manages sessions through warden, and the two session structures are completely independent of each other.

2. **200 OK does not mean success** — verify that the intended side effect (session persistence, successful redirect) actually occurred. "The server processed the request" and "the desired state was saved" are different questions.

3. **Read the logs in sequence** — POST succeeds, then GET returns 302: the POST did not save state correctly. Do not be misled by each request appearing to succeed in isolation.

4. **Compare with a working similar action** — putting the regular login action and the One Tap action side by side made the difference immediately obvious. When writing new auth flows, always reference an existing working flow.

5. **Order matters: `reset_session` before `sign_in`** — `reset_session` must be called first to prevent session fixation attacks. Calling it after `sign_in` will destroy the warden session you just created.
