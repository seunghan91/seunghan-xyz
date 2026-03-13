---
title: "Cross-Audit of Authentication Security Across 7 Flutter Apps - Pre-iOS Submission Check"
date: 2025-10-21
draft: false
tags: ["Flutter", "Security", "SecureStorage", "SharedPreferences", "Authentication"]
description: "Bulk audit of auth/security across 7 Flutter apps before iOS 1.0 submission, discovering and fixing 3 patterns: SharedPreferences plaintext storage, missing 401 refresh, and PII exposure."
cover:
  image: "/images/og/flutter-auth-cross-audit.png"
  alt: "Flutter Auth Cross Audit"
  hidden: true
---


After [fixing 3 session bugs](/posts/flutter-rails-auth-session-persistence-debugging/) in a Flutter + Rails app, I got curious: **do the same problems exist in other projects?**

I ran an authentication/security cross-audit across 7 Flutter apps ahead of iOS 1.0 submission.

---

## Audit Results Summary

| Project | Auth Method | Result |
|---|---|---|
| App A (Real Estate Contracts) | Custom JWT + SecureStorage | ✅ Good |
| App B (AI Travel) | Custom JWT + SharedPreferences | 🔴 3 issues |
| App C (Team Management) | Custom JWT + SharedPreferences | 🔴 2 issues |
| App D (Horoscope/MBTI) | Firebase Auth + Supabase | 🔴 1 issue |
| App E (Film Scanner) | Supabase Auth | ✅ Good |
| App F (AI Media) | Supabase Auth | ✅ Good |
| App G (Voice Chat) | - | ⏭️ Not checked |

**All apps where Supabase SDK manages auth were fine**, and **only apps with custom JWT implementations had problems**.

---

## Pattern 1: Tokens Stored in Plaintext via SharedPreferences

SharedPreferences stores data **without encryption** -- as XML on Android and plist on iOS. Found in App B and App C.

```dart
// ❌ SharedPreferences - plaintext storage
final prefs = await SharedPreferences.getInstance();
await prefs.setString('auth_token', token);

// ✅ FlutterSecureStorage - iOS Keychain / Android Keystore
const storage = FlutterSecureStorage();
await storage.write(key: 'auth_token', value: token);
```

The fix only swapped the internal implementation while keeping the API the same, minimizing changes at call sites. Non-String types like `bool` were converted with `value.toString()` / `value == 'true'`.

---

## Pattern 2: Logging Out on 401 Without Token Refresh

App B just cleared the token on 401 and called it done; App C only logged it and did nothing.

```dart
// ❌ Token deletion without refresh attempt
if (error.response?.statusCode == 401) {
  tokenStorage.clearTokens();  // User has to log in again
}
```

App B got a proper flow: refresh token renewal -> retry original request -> logout on failure.

```dart
// ✅ 401 → refresh attempt → retry → fallback
if (error.response?.statusCode == 401) {
  final refreshed = await _attemptTokenRefresh();
  if (refreshed) {
    final opts = error.requestOptions;
    opts.headers['Authorization'] = 'Bearer ${await _tokenStorage.getToken()}';
    return handler.resolve(await Dio().fetch(opts));
  }
  await _tokenStorage.clearTokens();
  _handleUnauthorized();
}
```

App C didn't have a refresh endpoint on the server, so it got a minimal `onUnauthorized` callback as a stopgap.

---

## Pattern 3: PII Stored in Plaintext via SharedPreferences

App D's authentication itself was secure through Firebase Auth, but it was storing guest users' **personal information** (date of birth, gender, name) in SharedPreferences. This could lead to App Store rejection for privacy policy violations.

```dart
// ❌ PII in plaintext
await prefs.setString('guest_profile', jsonEncode({
  'birthDate': '1990-05-15', 'gender': 'male', 'name': 'John Doe',
}));

// ✅ Encrypted with SecureStorage
await storage.write(key: 'guest_profile', value: jsonEncode({...}));
```

---

## Lessons Learned

**Custom implementation vs SDK**: All issues were in custom JWT implementations. SDKs handle storage/refresh/expiration automatically. Checklist for custom implementations:
- [ ] Using SecureStorage?
- [ ] Attempting refresh on 401?
- [ ] Logging out on refresh failure?
- [ ] WebSocket token synchronization?

**SharedPreferences purpose**: Exclusively for non-sensitive settings like dark mode, language, onboarding. Never store tokens or PII.

**The same mistakes replicate**: The more boilerplate code you copy, the more the first implementation matters.

**One-line check before iOS submission**:

```bash
grep -r "SharedPreferences" --include="*.dart" lib/
```

This alone can quickly verify whether sensitive data is being stored in plaintext.
