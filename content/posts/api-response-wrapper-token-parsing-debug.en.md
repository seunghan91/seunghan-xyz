---
title: "Login Keeps Logging Out — Chain Bugs Caused by API Wrapper Format Mismatch"
date: 2025-12-02
draft: false
tags: ["Flutter", "Rails", "BLoC", "Debugging", "JWT", "Chrome Extension"]
description: "Tracing why a mobile app kept logging out led to discovering that a single API response wrapper format mismatch caused 5 bugs across Flutter, Rails, and Chrome Extension clients."
cover:
  image: "/images/og/api-response-wrapper-token-parsing-debug.png"
  alt: "Api Response Wrapper Token Parsing Debug"
  hidden: true
---

The mobile app keeps logging out. It works fine right after login, but when you background the app briefly and reopen it, the login screen appears.

Token storage in SecureStorage was verified, and 401 auto-refresh via Dio interceptor was implemented. So why?

---

## Reproducing the Symptom

1. Login to app -> works normally
2. Restart app around access token expiration time
3. -> Session restore fails, forced logout

Found a hint in the server logs.

```
FormatException: "user" field is missing or null
```

It was crashing while parsing the token refresh response.

---

## Understanding the Structure

The server wraps all API responses in a common wrapper.

```json
{
  "success": true,
  "status": "success",
  "data": {
    "user": { ... },
    "access_token": "...",
    "refresh_token": "..."
  },
  "meta": { "timestamp": "..." }
}
```

The login endpoint always returned this format. But at some point, the token refresh endpoint had been changed to return a flat structure without the `user` key inside `data`.

```json
{
  "success": true,
  "data": {
    "id": 1,
    "email": "...",
    "name": "...",
    "access_token": "...",
    "refresh_token": "..."
  }
}
```

Since `data.user` was missing, `AuthResponse.fromJson(json['user'])` threw an exception -> `clearAuthData()` called -> forced logout.

---

## Bug 1: Server — Refresh Response Format Mismatch

**Cause**: The token refresh service was returning `user.as_json(only: [:id, :email, :name])` (a truncated Hash) instead of a `UserService` object.

**Fix**:

```ruby
# Before — Service
@user_data = user&.as_json(only: [:id, :email, :name])
# Controller
response_data = result.user_data.merge(access_token: ..., refresh_token: ...)

# After — Service
@user_instance = user        # preserve original User object
@user_data = user&.as_json(only: [:id, :email, :name])

# Controller
user_obj = result.user_instance ? standard_user_response(result.user_instance) : result.user_data
response_data = { user: user_obj, access_token: ..., refresh_token: ... }
```

Reused the `standard_user_response(user)` helper that the login endpoint uses for consistency.

---

## Bug 2: Flutter — JWT Expiry Time Parsing Error

Token refresh was fixed, but the `_extractTokenExpiry` function was also broken.

It was manually parsing JSON after Base64 decoding the JWT payload.

```dart
// Before — manually splitting by comma/colon
final pairs = decoded.split(',');
for (final pair in pairs) {
  final kv = pair.split(':');
  if (kv.length == 2) {
    json[kv[0].replaceAll('"', '').trim()] = kv[1].replaceAll('"', '').trim();
  }
}
```

Simple cases like `"exp":1234567890` appeared to work, but parsing broke when values contained colons (`"iss":"https://..."`) or nested objects. If the `exp` field couldn't be read, `tokenExpiresAt` became null -> timer not set -> proactive refresh never triggered -> forced logout after expiration.

```dart
// After
final json = jsonDecode(decoded) as Map<String, dynamic>;
```

Just use the standard library. Why was this being parsed manually...

---

## Bugs 3-5: Chrome Extension — Same Format Mismatch in 3 Places

Checked the web side too. The Rails web app used Devise session-based auth so it wasn't affected, but the Chrome extension had 3 bugs with the same pattern.

**Common cause**: Needed to read `data.refresh_token` from the token refresh response body, but was reading it as if it were flat without knowing it was nested inside `data`.

```javascript
// Before
const newRefreshToken = data.refresh_token;  // undefined

// After
const newRefreshToken = data.data?.refresh_token;
```

Since `background.js`, `popup.js`, and `sidepanel.js` all implemented their own token refresh logic separately, the same bug was copied three times.

**`background.js` had one more bug**: The token validation function referenced variables not in scope.

```javascript
// Before — client, tokenType variables don't exist in this function scope
const refreshed = {
  client: response.headers.get('client') || client,        // possible ReferenceError
  'token-type': response.headers.get('token-type') || tokenType,  // possible ReferenceError
};

// After
const refreshed = {
  client: response.headers.get('client') || deviseAuth.client,
  'token-type': response.headers.get('token-type') || deviseAuth['token-type'] || 'Bearer',
};
```

Thanks to the server correctly setting `Access-Control-Expose-Headers` in CORS headers, the header fallback worked and no actual outage occurred. But in an environment without those headers, it would be a runtime error.

---

## Why Didn't It Break Immediately?

All three places had **header fallback**.

```javascript
'refresh-token': body?.data?.refresh_token
  || response.headers.get('refresh-token')   // <- this was actually doing the work
  || deviseAuth['refresh-token']
  || ''
```

Since the server also set the `refresh-token` response header, even when body parsing failed, the value was read from headers. Since it functionally worked, the bug was hard to discover.

Similarly in Flutter, even when `_extractTokenExpiry` returned null, it didn't crash immediately. The proactive refresh timer just wouldn't be set, and the Dio 401 interceptor served as a reactive fallback, covering most cases. The problem was specifically the cold start case when the app restarted and tried session restore with the refresh token, receiving a response without the `user` field.

---

## Summary

The core of this debugging session was that **clients were each interpreting the server response wrapper format differently**.

| Client | Bug | Actual Impact |
|--------|-----|---------------|
| Mobile app | Missing `user` key in refresh response | Forced app logout (direct cause) |
| Mobile app | JWT manual parsing error | Timer not set -> missed refresh timing |
| Chrome ext background | Body parsing error + undeclared variables | Masked by header fallback |
| Chrome ext popup | Body parsing error | Masked by header fallback |
| Chrome ext sidepanel | Body parsing error | Masked by header fallback |

**Lessons**:

1. **If you have a common response format, enforce it with explicit types/schemas.** When the server changes, all clients need to be updated together, but if it's only a verbal agreement, something will inevitably drift.

2. **Fallbacks hide bugs.** It appeared to work thanks to header fallback, but without it, the bug would have been discovered much sooner.

3. **When you copy the same logic to multiple files, bugs get copied too.** Having three files each implement their own token refresh logic was the problem itself.

4. **Use standard libraries.** Code that parses JSON with `split(',')` only pretends to work.
