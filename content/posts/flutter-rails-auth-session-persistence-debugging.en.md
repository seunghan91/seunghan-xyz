---
title: "Flutter + Rails Auth Session Keeps Dropping - 3 Causes and Solutions"
date: 2025-09-27
draft: false
tags: ["Flutter", "Rails", "BLoC", "WebSocket", "Session", "Debugging"]
description: "Tracing login session drops in a Flutter BLoC app from server logs to find 3 causes: DTA residual code, WebSocket closure capture bug, and token lifetime settings."
cover:
  image: "/images/og/flutter-rails-auth-session-persistence-debugging.png"
  alt: "Flutter Rails Auth Session Persistence Debugging"
  hidden: true
---


Login sessions keep dropping in a Flutter BLoC app. Tokens are stored in SecureStorage, automatic renewal on 401 is implemented via Dio interceptors -- so why?

Starting from server logs, I found 3 causes and fixed all of them. Here is the full process.

---

## Tech Stack

- **Mobile**: Flutter + BLoC pattern + Dio HTTP + SecureStorage
- **Server**: Rails 8 API + ActionCable WebSocket
- **Auth**: SHA-256 digest-based access token + JTI refresh token (90 days)
- **Real-time**: ActionCable WebSocket (token-based auth)

---

## Symptoms

1. Works fine right after login
2. API requests start failing with 401 after some time
3. Token refresh seems to work, but WebSocket disconnects
4. App eventually transitions to unauthenticated state

---

## Cause 1: Ghost of Legacy Code - Residual DTA Methods

### Discovery

Server logs showed intermittent `user.tokens`-related errors during token refresh. The project had migrated from devise_token_auth (DTA) to a custom token system, but `token_refresh_service.rb` still had DTA-era code.

```ruby
# DTA code left behind after removal
def validate_google_oauth_token(user)
  token = user.tokens&.dig('default', 'access_token')  # NoMethodError!
  return true if token.blank?
  # ... Google OAuth verification logic
end
```

The `tokens` column/method on the `User` model was already deleted when DTA was removed. But this code was called inside a `rescue => e` block, so the error was caught and `true` was returned -- the worst case of **errors occurring while appearing to work normally**.

### Solution

Removed OAuth token verification from the refresh flow. OAuth authentication only needs to be verified at initial login; the refresh flow should rely on the RefreshToken's own expiry/active state.

```ruby
# After fix
def validate_google_oauth_token(user)
  true  # OAuth verification only at initial login
end
```

This alone removed ~130 lines of dead code.

---

## Cause 2: Dart Closure Trap - WebSocket Stale Token

### Discovery

This was the core cause. When creating the ActionCable WebSocket client, the token was passed like this:

```dart
// Problem code
final accessToken = await secureStorage.read('access_token');

actionCableClient = ActionCableClient(
  baseUrl: apiBaseUrl,
  getAccessToken: () => accessToken ?? '',  // Local variable capture!
);
```

In Dart, closures capture **the variable reference at creation time**. Since `accessToken` is a `final` local variable, even after the Dio interceptor refreshes the token on 401 error, the WebSocket's `getAccessToken` closure still returns the **old token**.

Here is the flow:

```
1. App starts → accessToken = "token_A" (local variable)
2. WebSocket created → getAccessToken: () => "token_A" (captured)
3. Time passes → token_A expires
4. Dio interceptor → detects 401 → refresh → stores "token_B" in SecureStorage
5. WebSocket reconnect attempt → getAccessToken() → returns "token_A" (stale!)
6. WebSocket auth failure → disconnected
```

### Solution

Three things were fixed together:

**1) Introduce a mutable token field**

```dart
// Changed to class field
String _latestAccessToken = '';

// When creating WebSocket
_latestAccessToken = accessToken;
actionCableClient = ActionCableClient(
  baseUrl: apiBaseUrl,
  getAccessToken: () => _latestAccessToken,  // References mutable field
);
```

**2) Token refresh callback from Dio interceptor**

```dart
// Add callback to DioClient
void Function(String newAccessToken)? onTokenRefreshed;

// Inside interceptor - after successful refresh
onTokenRefreshed?.call(newAccessToken);
```

```dart
// Connect callback in app
dioClient.onTokenRefreshed = (newAccessToken) {
  _latestAccessToken = newAccessToken;
  actionCableClient?.reconnectWithNewToken();
};
```

**3) WebSocket reconnection on AuthBloc state changes**

```dart
// When token changes in AuthAuthenticated state
if (newToken != _latestAccessToken) {
  _latestAccessToken = newToken;
  actionCableClient?.reconnectWithNewToken();
}
```

This ensures the WebSocket reconnects with the new token through all token refresh paths (proactive timer and reactive 401 interceptor).

---

## Cause 3: Token Lifetime Not Suited for Mobile

### Discovery

The server's access token lifetime was set to 24 hours for mobile as well.

```ruby
# Mobile using same 24 hours as web
when 'flutter'
  ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_HOURS', 24).to_i.hours
```

Mobile apps face different conditions than web -- background transitions, unstable networks, etc. Industry recommendations are 15-60 minutes for mobile access tokens and 30-90 days for refresh tokens.

### Solution

```ruby
# Mobile: 1 hour (combined with 90-day refresh token)
when 'flutter'
  ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_MINUTES', 60).to_i.minutes
```

The AuthBloc's proactive refresh timer was adjusted accordingly. With a 1-hour token, it auto-refreshes 8 minutes before expiry (at the 52-minute mark).

---

## Lessons Learned

### 1. After migration, do a full grep audit

When removing DTA, I cleaned up models and controllers but missed references deep in the service layer. The `rescue` block swallowed errors, delaying discovery.

```bash
# Essential after migration
grep -r "user.tokens" --include="*.rb" .
grep -r "devise_token_auth" --include="*.rb" .
```

### 2. Be careful about what Dart closures capture

If a `final` local variable is captured, its value never changes. For values that need to be refreshed like tokens, reference a mutable field or read from SecureStorage every time.

```dart
// Immutable capture
final token = await getToken();
callback: () => token

// Mutable reference
callback: () => _mutableTokenField

// Or read every time
callback: () async => await secureStorage.read('token')
```

### 3. Token strategies must differ for mobile and web

| | Mobile | Web |
|---|---|---|
| Access Token | 15-60 min | 1-24 hours |
| Refresh Token | 30-90 days | 7-30 days |
| Refresh Method | Proactive + Reactive | Mostly Reactive |
| WebSocket | Must reconnect on token refresh | Cookie-based possible |

### 4. WebSocket and HTTP auth must be managed separately

Even when the Dio interceptor refreshes the token, the WebSocket does not know. A mechanism to synchronize auth state across both channels is essential.

---

## Diagnosis Order Summary

```
1. Check server logs (Render dashboard)
   → Find 401 error patterns, token refresh errors

2. Trace code (server → client)
   → DTA residual code in token_refresh_service.rb
   → Flutter WebSocket closure capture issue

3. External verification (industry research)
   → Confirm mobile token lifetime recommendations
   → Confirm WebSocket stale token as #1 cause

4. Sequential fixes (in dependency order)
   → Remove server dead code → WebSocket reconnection → Token lifetime adjustment
```

Starting from server logs and tracing to the client was key. Looking only at the client would have missed Cause 1, and looking only at the server would have missed Cause 2.

> After fixing this bug, I got curious whether other projects had the same issue, so I cross-audited 7 Flutter apps. That story is in the [next post](/posts/flutter-auth-cross-audit/).
