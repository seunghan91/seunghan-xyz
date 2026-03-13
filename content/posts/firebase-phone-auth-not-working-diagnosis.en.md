---
title: "Flutter Firebase Phone Auth - SMS Not Arriving? From Diagnosis to Code Fix"
date: 2025-07-02
draft: false
tags: ["Flutter", "Firebase", "Phone Auth", "Rails", "Firebase Auth"]
description: "Root cause analysis when Firebase phone auth SMS doesn't arrive, and fixing the issue where dev bypass button doesn't work in production."
cover:
  image: "/images/og/firebase-phone-auth-not-working-diagnosis.png"
  alt: "Firebase Phone Auth Not Working Diagnosis"
  hidden: true
---

After integrating phone number verification into a Flutter app, I faced the situation of "the verification code isn't arriving." And when pressing the dev bypass button to skip verification and attempt signup, the server returned "Phone number verification not completed." Documenting both issues together.

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

The key point is that **Firebase handles SMS delivery directly**. It's not a structure where Rails or another backend calls Twilio.

---

## Problem 1: Why SMS Doesn't Arrive

For Firebase Phone Auth to work, several settings need to be configured in Firebase Console.

**Checklist:**
1. Authentication -> Sign-in method -> **Phone** enabled
2. For Android: **SHA-1 fingerprint** registered
3. For iOS: **APNs key** registered

Android in particular won't do phone auth at all without SHA-1. This is because Firebase integrates with the Play Integrity API for app integrity verification.

```bash
# Extract SHA-1 from upload keystore
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_PASSWORD
```

Copy the SHA1 and SHA256 values from the output and register them at Firebase Console -> Project Settings -> Android app -> Add fingerprint.

After registration, you **must re-download google-services.json** and replace it in `android/app/`. The fingerprint information is included in this file.

---

## Problem 2: Why Dev Bypass Doesn't Work in Production

During development, it's common to create a button like this:

```dart
// Skip verification button
onPressed: () {
  setState(() => _currentStep = 2); // only advances UI to next step
}
```

This button only changes the UI step and **doesn't create a PhoneVerification record on the server.**

Then the server (Rails) fails this check during signup:

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
  # <- returns false in production, can't pass verification
end
```

In the development environment, `skip_verification?` returns `true` so it works fine, but on a production server like Render, it becomes false and gets blocked.

---

## Solution

### Server Side: Control Bypass via Environment Variable

Added an `ENABLE_TEST_BYPASS` environment variable to make it controllable even in production.

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

### Flutter Side: Make Bypass Button Handle Server Too

Instead of just changing the UI step, modified to send an auth request with code `111111` to the server.

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
    // If phone number exists, also handle bypass auth on server
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

---

## Summary

| Problem | Cause | Solution |
|---------|-------|----------|
| SMS not received (Android) | Firebase SHA-1 not registered | Extract from keystore and register in Firebase Console |
| SMS not received (iOS) | APNs key not registered | Issue from Apple Developer and upload to Firebase |
| Signup fails after bypass | Only UI skipped, no server PhoneVerification record | Bypass button sends `111111` code to server for auth |
| Production bypass not working | `skip_verification?` only allows dev/test environments | Introduced `ENABLE_TEST_BYPASS` environment variable |

Firebase Phone Auth code itself is simple when settings are correct. Issues always arise from **platform-specific settings** and **development/production environment differences**.
