---
title: "Flutter Firebase Phone Auth - SMS Not Arriving? From Diagnosis to Code Fix"
date: 2025-07-02
draft: false
tags: ["Flutter", "Firebase", "Phone Auth", "Rails", "Firebase Auth"]
categories: ["Flutter", "Rails"]
description: "Root cause analysis when Firebase phone auth SMS doesn't arrive, and fixing the issue where dev bypass button doesn't work in production."
cover:
  image: "/images/og/firebase-phone-auth-not-working-diagnosis.png"
  alt: "Firebase Phone Auth Not Working Diagnosis"
  hidden: true
---

After integrating phone number verification into a Flutter app, I ran into the dreaded "the verification code isn't arriving" situation. And when pressing the dev bypass button to skip verification and attempt signup, the server returned "Phone number verification not completed." This post documents both issues: what caused them and how to fix them.

Firebase Phone Auth looks straightforward on the surface, but it has several layers where things can break — platform-specific configuration (Android vs. iOS), token verification flow, and behavioral differences between development and production environments. Understanding which layer is failing is the key to diagnosing these problems quickly.

---

## Understanding the Structure First

The Flutter Firebase Phone Auth flow works like this:

```
Flutter -> FirebaseAuth.verifyPhoneNumber() -> Firebase sends SMS directly
                                |
                    User enters the code
                                |
Flutter -> Verify code with Firebase -> Get ID Token
                                |
Flutter -> Send firebase_token to backend -> Server verifies token -> Creates PhoneVerification record
                                |
Flutter -> Signup request -> Server checks PhoneVerification -> Creates user
```

The key point is that **Firebase handles SMS delivery directly**. This is not a structure where Rails or another backend calls Twilio or any other SMS provider. Firebase communicates directly with carriers to send the SMS. The app receives the code, sends a verification request back to Firebase, and Firebase returns an ID Token. The backend's only role is to verify that ID Token.

Understanding this architecture matters when diagnosing failures. You need to quickly narrow down whether the issue is in Firebase configuration, app code, or server logic. Each layer fails in a distinct way.

---

## Problem 1: Why SMS Doesn't Arrive

For Firebase Phone Auth to work, several settings must be correctly configured in Firebase Console. If SMS isn't arriving at all, the issue is almost always at this configuration layer.

**Checklist:**
1. Authentication -> Sign-in method -> **Phone** enabled
2. For Android: **SHA-1 fingerprint** registered
3. For iOS: **APNs key** registered

### Android: Phone Auth Will Not Work Without SHA-1

Android in particular will not do phone auth at all without SHA-1. This is because Firebase integrates with the Play Integrity API for app integrity verification. Firebase needs to confirm that the app making the authentication request is actually the app registered in the Firebase project — and the SHA-1/SHA-256 fingerprint is the mechanism for that verification.

During development, you need to register the SHA-1 from your debug keystore. For release builds, register the SHA-1 from your upload keystore. Registering both is the safest approach.

```bash
# Extract SHA-1 from upload keystore
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_PASSWORD
```

Copy the SHA1 and SHA256 values from the output and register them at Firebase Console -> Project Settings -> Android app -> Add fingerprint.

After registration, you **must re-download google-services.json** and replace it in `android/app/`. The fingerprint information is embedded in this file. Registering the fingerprint without replacing the file means the change never takes effect in your app.

A practical tip: when testing on the emulator, use Firebase Console's Authentication -> Test phone numbers feature. You can define a phone number and a fixed code, and Firebase will accept that code without sending a real SMS. This speeds up development significantly and avoids hitting SMS quotas.

### iOS: Silent Push Requires APNs Key

On iOS, Firebase Phone Auth uses Silent Push Notifications to verify the app. Firebase sends a silent push to the app to confirm it is alive and responding correctly before proceeding with authentication. Because of this, an APNs (Apple Push Notification service) key must be registered.

Issue the APNs key from Apple Developer Console -> Certificates, IDs & Profiles -> Keys, then register it in Firebase Console -> Project Settings -> Cloud Messaging tab. You need to provide the key file (.p8), the Key ID, and the Team ID.

Without an APNs key, calling `verifyPhoneNumber` on a real iOS device either produces no response at all or throws an unhandled exception. The failure is silent in many cases, which makes it difficult to diagnose without knowing to check this first.

---

## Problem 2: Why Dev Bypass Doesn't Work in Production

During development, it is common to add a button like this:

```dart
// Skip verification button
onPressed: () {
  setState(() => _currentStep = 2); // only advances UI to next step
}
```

This is useful when you need to rapidly test UI flows or develop features unrelated to authentication. The problem is that this button only changes the UI step — **it does not create a PhoneVerification record on the server.**

### You Need to Understand the Server-Side Verification Logic

The Rails server checks whether phone verification was completed by looking for a database record during signup:

```ruby
# RegisterUserCommand
def check_phone_verification!
  verification = PhoneVerification.find_by(phone_number: @phone_number)

  unless verification&.verified?
    raise CommandError.new(
      error: "Phone number verification not completed.",
      verification_required: true
    )
  end
end

def skip_verification?
  Rails.env.development? || Rails.env.test?
  # <- returns false in production, verification cannot be bypassed
end
```

In the development environment (`RAILS_ENV=development`), `skip_verification?` returns `true`, so signup works even without a record. But on a production server like Render, there must be a `PhoneVerification` record in the database for signup to succeed.

The result is that the bypass button works fine in the development environment, but fails in TestFlight or any production-like environment. Developers who do not recognize this difference end up confused by "it worked in dev but fails in the release build."

---

## Solution

### Server Side: Control Bypass via Environment Variable

Adding an `ENABLE_TEST_BYPASS` environment variable makes it possible to control bypass behavior even in production. This allows you to test the full authentication flow without real SMS during beta testing or QA periods.

```ruby
# phone_verification_service.rb
def beta_test_mode?(phone_number, code)
  (!Rails.env.production? || ENV["ENABLE_TEST_BYPASS"] == "true") && code == "111111"
end

# register_user_command.rb
def skip_verification?
  Rails.env.development? || Rails.env.test? || ENV["ENABLE_TEST_BYPASS"] == "true"
end
```

Adding `ENABLE_TEST_BYPASS=true` in the Render dashboard enables bypass during the testing period. Remove it before official launch.

The advantage of this approach is that bypass can be toggled on and off with a single environment variable without touching code. You can distribute an app to internal testers with bypass enabled, then disable it at launch time simply by removing the variable.

### Flutter Side: Make the Bypass Button Handle the Server Too

Instead of just changing the UI step, modify the bypass button to send an authentication request with code `111111` to the server. Passing an empty string as `verificationId` takes a branch that skips Firebase entirely and calls the server directly.

```dart
// auth_repository_impl.dart
Future<bool> verifyCode(String phoneNumber, String code, String verificationId) async {
  // If verificationId is empty, skip Firebase -> call server directly
  if (verificationId.isEmpty) {
    await _apiClient.verifyCode({'phone_number': phoneNumber, 'code': code});
    return true;
  }

  // Normal Firebase flow
  final firebaseToken = await _firebasePhoneAuth.verifyCodeAndGetToken(verificationId, code);
  await _apiClient.firebaseVerifyPhone({'firebase_token': firebaseToken});
  await _firebasePhoneAuth.signOut();
  return true;
}
```

```dart
// register_screen.dart - bypass button
onPressed: () {
  final phone = _phoneController.text.trim();
  if (phone.length >= 10) {
    // If phone number is present, handle bypass auth on server too
    context.read<AuthBloc>().add(
      AuthDevBypassVerificationRequested(phoneNumber: phone),
    );
  } else {
    setState(() => _currentStep = 2);
  }
},
```

In the BLoC, pass an empty string as `verificationId` to take the bypass path.

```dart
// auth_bloc.dart
Future<void> _onDevBypassVerificationRequested(...) async {
  await _authRepository.verifyCode(
    event.phoneNumber,
    '111111',
    '', // empty = bypass Firebase
  );
  emit(state.copyWith(isCodeVerified: true));
}
```

The key insight in this design is that the bypass button now creates the same server-side state as a real verification. It skips only the Firebase token verification step, but the `PhoneVerification` record is created normally on the server. Signup works correctly after this.

---

## Useful Debugging Approaches

Techniques that proved valuable when diagnosing Firebase Phone Auth issues in practice:

**Check Firebase Console logs:** Firebase Console -> Authentication -> Users tab shows a history of authentication attempts. If there are no attempts recorded, the request never reached Firebase from the app.

**Flutter error callbacks:** The `verificationFailed` callback in `FirebaseAuth.verifyPhoneNumber` receives a `FirebaseAuthException`. Logging its `code` field gives precise error codes like `invalid-app-credential`, `quota-exceeded`, or `app-not-authorized` — each pointing directly at a specific cause.

**Android Logcat:** Running `adb logcat | grep -i firebase` on a real device surfaces internal Firebase SDK logs. Messages about SHA-1 mismatch or Play Integrity failure appear here and are not visible anywhere else.

**Test phone numbers:** Firebase Console -> Authentication -> Sign-in method -> Phone -> Test phone numbers lets you register a phone number and a fixed code. Verification against this number does not send a real SMS and is not subject to SMS quotas. It is the most reliable way to test the full authentication flow in development.

---

## Summary

| Problem | Cause | Solution |
|---------|-------|----------|
| SMS not received (Android) | Firebase SHA-1 not registered | Extract from keystore, register in Firebase Console, re-download google-services.json |
| SMS not received (iOS) | APNs key not registered | Issue from Apple Developer and upload to Firebase |
| Signup fails after bypass | Only UI skipped, no server PhoneVerification record | Bypass button sends `111111` code to server for auth |
| Production bypass not working | `skip_verification?` only allows dev/test environments | Introduced `ENABLE_TEST_BYPASS` environment variable |

Firebase Phone Auth code itself is straightforward when the configuration is correct. Issues always arise from **platform-specific settings** and **development/production environment differences**.

---

## Key Takeaways

- When SMS is not arriving, check SHA-1 (Android) and APNs key (iOS) registration before looking at anything else.
- After registering Android SHA-1, you must re-download `google-services.json` and replace the file — the change does not take effect otherwise.
- A dev bypass button must create the server-side state (PhoneVerification record) to work correctly in production environments.
- The `ENABLE_TEST_BYPASS` environment variable allows toggling bypass behavior without code changes, cleanly separating beta testing from production launch.
- The `verificationFailed` callback and Android Logcat are the most direct sources of diagnostic information when Firebase Phone Auth silently fails.
