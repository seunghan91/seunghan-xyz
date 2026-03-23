---
title: "Cross-Audit of Authentication Security Across 7 Flutter Apps - Pre-iOS Submission Check"
date: 2025-10-21
draft: true
tags: ["Flutter", "Security", "SecureStorage", "SharedPreferences", "Authentication"]
description: "Bulk audit of auth/security across 7 Flutter apps before iOS 1.0 submission, discovering and fixing 3 patterns: SharedPreferences plaintext storage, missing 401 refresh, and PII exposure."
cover:
  image: "/images/og/flutter-auth-cross-audit.png"
  alt: "Flutter Auth Cross Audit"
  hidden: true
---

After [fixing 3 session bugs](/posts/flutter-rails-auth-session-persistence-debugging/) in a Flutter + Rails app, I got curious: **do the same problems exist in other projects?**

I ran an authentication/security cross-audit across 7 Flutter apps ahead of iOS 1.0 submission. Patterns that are easy to overlook when reviewing one app at a time become immediately obvious when comparing multiple projects side by side. The short answer: **apps using Supabase or Firebase auth SDKs were all fine, and vulnerabilities only appeared in apps with custom JWT implementations.**

---

## Why a Cross-Audit

When the same developer maintains multiple projects, the same mistakes get copied. If you stored tokens in SharedPreferences in your first app, there is a good chance your second and third apps carry the exact same boilerplate.

Reviewing a single app in isolation makes it easy to shrug and think "this is probably fine." Comparing seven at once makes patterns jump out immediately. The iOS App Store review process is also strict about privacy handling, and a rejection means waiting days for a re-review. One comprehensive sweep before submission is far more efficient.

---

## Scope and Method

Seven apps were audited. For each one I checked `pubspec.yaml` for authentication-related packages, then ran grep across the entire `lib/` directory.

Three areas were the focus:

1. **Token storage location** — SharedPreferences or FlutterSecureStorage
2. **401 handling logic** — whether a refresh is attempted, and what happens on failure
3. **PII storage method** — whether names, birth dates, emails, etc. are stored in plaintext

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

App A was the exception — a custom JWT app that was clean. That app deliberately introduced SecureStorage during initial development. Later apps were written from scratch or pulled boilerplate from other sources rather than referencing App A, which is how the problems crept in.

---

## Pattern 1: Tokens Stored in Plaintext via SharedPreferences

SharedPreferences stores data **without encryption** — as XML on Android and a `.plist` file on iOS. On a rooted device or with iTunes backup analysis tools, anyone can read those tokens. Found in App B and App C.

```dart
// ❌ SharedPreferences - plaintext storage
final prefs = await SharedPreferences.getInstance();
await prefs.setString('auth_token', token);
await prefs.setString('refresh_token', refreshToken);
```

iOS provides the Keychain and Android provides the Keystore — both are hardware-backed secure storage areas. The `flutter_secure_storage` package abstracts both behind a single API.

```dart
// ✅ FlutterSecureStorage - iOS Keychain / Android Keystore
const storage = FlutterSecureStorage();
await storage.write(key: 'auth_token', value: token);
await storage.write(key: 'refresh_token', value: refreshToken);
```

The fix only swapped the internal implementation while keeping the external API the same, minimizing changes at call sites. Because all token-related methods were already centralized in a single `TokenStorage` class, there was exactly one place to change.

`SharedPreferences` supports multiple types (`String`, `int`, `bool`, `double`, `List<String>`), while `FlutterSecureStorage` is `String`-only. Non-String types require manual conversion:

```dart
// storing a bool
await storage.write(key: 'is_guest', value: isGuest.toString());

// reading a bool
final raw = await storage.read(key: 'is_guest');
final isGuest = raw == 'true';
```

---

## Pattern 2: Logging Out on 401 Without Token Refresh

App B just cleared the token on 401 and stopped there. App C only logged it and did nothing at all. In both cases, users would get abruptly thrown to the login screen while actively using the app.

```dart
// ❌ Token deletion without refresh attempt
if (error.response?.statusCode == 401) {
  tokenStorage.clearTokens();  // User has to log in again
}
```

A 401 has two possible meanings: the access token expired, or authentication actually failed. The vast majority of real-world 401s are expired access tokens. The correct response is to use the refresh token to obtain a new access token and retry the original request.

App B had a refresh endpoint on the server, so a full flow was implemented:

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

This runs inside a Dio interceptor. There is an important gotcha: **if the refresh request itself returns 401, you get an infinite loop.** The fix is a flag tracking whether a refresh is already in progress, combined with excluding the refresh endpoint from the interceptor:

```dart
bool _isRefreshing = false;

Future<bool> _attemptTokenRefresh() async {
  if (_isRefreshing) return false;
  _isRefreshing = true;
  try {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken == null) return false;
    // Call the refresh endpoint directly, bypassing the interceptor
    final resp = await _rawDio.post('/auth/refresh',
        data: {'refresh_token': refreshToken});
    await _tokenStorage.saveTokens(
      accessToken: resp.data['access_token'],
      refreshToken: resp.data['refresh_token'],
    );
    return true;
  } catch (_) {
    return false;
  } finally {
    _isRefreshing = false;
  }
}
```

App C did not have a refresh endpoint on the server at all, so the full implementation was not possible. Instead, an `onUnauthorized` callback was added so the UI layer could handle the situation appropriately. That is the best you can do without a server-side change.

---

## Pattern 3: PII Stored in Plaintext via SharedPreferences

App D's authentication itself was secure through Firebase Auth, but it was storing guest users' **personal information** — date of birth, gender, and name — in SharedPreferences.

Firebase Auth only manages basic user fields like `uid`, `email`, and `displayName`. App D is a horoscope service where even guest users provide their birth date and name. That data was being dropped into SharedPreferences.

```dart
// ❌ PII in plaintext
await prefs.setString('guest_profile', jsonEncode({
  'birthDate': '1990-05-15', 'gender': 'male', 'name': 'John Doe',
}));
```

By App Store review standards, birth date, name, and gender are sensitive personal data. Storing them without encryption is grounds for rejection. It is also a problem under GDPR and similar privacy regulations.

```dart
// ✅ Encrypted with SecureStorage
await storage.write(
  key: 'guest_profile',
  value: jsonEncode({
    'birthDate': '1990-05-15',
    'gender': 'male',
    'name': 'John Doe',
  }),
);
```

The code change was simple, but **tracing why the data ended up in SharedPreferences in the first place was the more important step.** It turned out the flutter_secure_storage dependency had never been added during the initial prototype phase, and that code shipped to production without anyone noticing.

---

## Edge Cases Found During the Audit

A straight grep pass does not catch everything.

**App B's duplicate token storage**: The main token storage class was migrated to SecureStorage, but a separate file was writing a token copy into SharedPreferences as a "fast read cache." It had been added for performance and became a security hole. A second grep with `grep -r "auth_token" --include="*.dart" lib/` caught it.

**App C's migration problem**: When moving from SharedPreferences to SecureStorage, existing users had their tokens in SharedPreferences and nothing in SecureStorage. Those users would be logged out on the next app launch. Forced logout is bad UX, but as a one-time security fix it was acceptable — it was documented in the release notes.

```dart
// Migration: if a token exists in SharedPreferences, remove it and prompt re-login
Future<void> migrateTokenStorage() async {
  final prefs = await SharedPreferences.getInstance();
  final oldToken = prefs.getString('auth_token');
  if (oldToken != null) {
    await prefs.remove('auth_token');
    await prefs.remove('refresh_token');
    // Do not copy to SecureStorage — require the user to log in again
  }
}
```

---

## Key Takeaways

**Custom implementation vs SDK**: Every issue was in a custom JWT implementation. SDKs handle token storage, refresh, and expiration automatically. If you do build custom JWT auth, here is a checklist:

- [ ] Using SecureStorage for token storage?
- [ ] Attempting token refresh on 401?
- [ ] Logging out on refresh failure?
- [ ] Preventing infinite loops if the refresh request itself returns 401?
- [ ] Synchronizing tokens for WebSocket connections?
- [ ] Handling storage migration for app updates?

**The right use for SharedPreferences**: It belongs exclusively to **non-sensitive preferences** where exposure causes no harm — dark mode, language selection, onboarding completion state. Never put tokens or PII in there.

**The same mistake replicates**: Boilerplate code is especially vulnerable. The first implementation sets the template for every app that follows. Investing in a well-built auth module once — and sharing it across projects — prevents the entire class of bugs described here.

**Quick pre-submission scan**:

```bash
# Check all SharedPreferences usage
grep -r "SharedPreferences" --include="*.dart" lib/

# Check for token key names
grep -rn "auth_token\|refresh_token\|access_token" --include="*.dart" lib/

# Check for PII field names
grep -rn "birthDate\|birth_date\|phoneNumber\|phone_number" --include="*.dart" lib/
```

Running these three commands takes five minutes and surfaces the majority of plaintext sensitive data issues. Five minutes is a good trade for avoiding an App Store rejection.

**The value of cross-auditing**: Comparing multiple projects side by side is far more effective at spotting patterns than reviewing a single project in isolation. This is especially true for areas like authentication where the same structure is repeated. Going forward, the plan is to extract the auth module into a shared package so every app uses the same implementation — making it impossible to accidentally ship the wrong version.
