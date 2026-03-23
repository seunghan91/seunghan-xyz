---
title: "Flutter Firebase Phone Auth - SMS가 안 와요? 진단부터 코드 수정까지"
date: 2025-07-02
draft: false
tags: ["Flutter", "Firebase", "Phone Auth", "Rails", "Firebase Auth"]
description: "Firebase 전화 인증을 연동했는데 SMS가 안 오는 경우의 원인 분석과, 개발용 bypass 버튼이 Production에서 동작하지 않는 문제 해결"
cover:
  image: "/images/og/firebase-phone-auth-not-working-diagnosis.png"
  alt: "Firebase Phone Auth Not Working Diagnosis"
  hidden: true
---

Flutter 앱에 전화번호 인증을 붙이고 나서 "인증번호가 안 와요"라는 상황을 마주쳤다. 그리고 개발용 bypass 버튼을 눌러서 인증을 건너뛰고 회원가입을 시도하면 서버에서 "인증이 완료되지 않은 전화번호입니다"가 떴다. 두 문제를 같이 정리한다.

Firebase Phone Auth는 처음 연동하면 단순해 보이지만, 실제로는 플랫폼(Android/iOS)별 설정, 토큰 검증 구조, 개발/프로덕션 환경 간의 동작 차이 등 여러 레이어에서 문제가 생길 수 있다. 이 글은 실제로 겪은 증상과 그 원인, 해결책을 단계별로 정리한 것이다.

---

## 구조부터 파악

Flutter Firebase Phone Auth의 흐름은 이렇다.

```
Flutter → FirebaseAuth.verifyPhoneNumber() → Firebase가 SMS 직접 발송
                                ↓
                    사용자가 코드 입력
                                ↓
Flutter → Firebase로 코드 검증 → ID Token 획득
                                ↓
Flutter → 백엔드로 firebase_token 전송 → 서버가 토큰 검증 → PhoneVerification 레코드 생성
                                ↓
Flutter → 회원가입 요청 → 서버가 PhoneVerification 확인 후 유저 생성
```

핵심은 **SMS 발송 자체를 Firebase가 담당**한다는 점이다. Rails나 다른 백엔드에서 Twilio 등을 호출하는 구조가 아니다. Firebase가 직접 통신사를 통해 SMS를 보내고, 앱은 그 코드를 받아서 Firebase에 검증 요청을 보낸다. 서버는 Firebase에서 발급한 ID Token을 검증하는 역할만 한다.

이 구조를 이해하는 게 중요한 이유는, **문제가 발생했을 때 어느 레이어에서 막혔는지**를 빠르게 좁혀야 하기 때문이다. Firebase 설정 문제인지, 앱 코드 문제인지, 서버 로직 문제인지를 먼저 구분해야 한다.

---

## 문제 1: SMS가 안 오는 이유

Firebase Phone Auth가 동작하려면 Firebase Console에서 몇 가지 설정이 되어 있어야 한다. SMS가 아예 오지 않는다면 대부분 이 설정에서 막혀 있다.

**체크리스트:**
1. Authentication → Sign-in method → **전화** 활성화 여부
2. Android의 경우 **SHA-1 지문** 등록 여부
3. iOS의 경우 **APNs 키** 등록 여부

### Android: SHA-1 지문이 없으면 동작하지 않는다

특히 Android는 SHA-1 없이는 전화 인증이 아예 동작하지 않는다. Firebase가 앱 무결성을 검증하는 Play Integrity API와 연동되기 때문이다. Firebase는 인증 요청을 보낸 앱이 실제로 Firebase 프로젝트에 등록된 앱인지 확인하고, 그 검증 수단이 SHA-1/SHA-256 지문이다.

개발 중에는 debug keystore의 SHA-1을 등록하고, 릴리즈 빌드에서는 upload keystore의 SHA-1을 등록해야 한다. 두 가지 다 등록해두는 것이 안전하다.

```bash
# 업로드 키스토어에서 SHA-1 추출
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_PASSWORD
```

출력 결과에서 SHA1, SHA256 값을 복사해 Firebase Console → 프로젝트 설정 → Android 앱 → 디지털 지문 추가에 등록한다.

등록 후에는 **google-services.json을 새로 다운로드**해서 `android/app/`에 교체해야 한다. 이 파일에 지문 정보가 포함되기 때문이다. 지문을 등록하고도 파일을 교체하지 않으면 변경이 반영되지 않는다.

또한 에뮬레이터에서 테스트할 때는 Firebase Console의 Authentication → Test phone numbers 기능을 이용하는 것이 좋다. 실제 SMS가 발송되지 않고 미리 지정한 코드로 인증할 수 있어 개발 속도가 빠르다.

### iOS: APNs 키가 없으면 Silent Push가 동작하지 않는다

iOS에서 Firebase Phone Auth는 Silent Push Notification을 사용해 앱을 검증한다. Firebase가 앱에 Silent Push를 보내서 앱이 살아있는지, 정상적으로 응답하는지 확인하는 구조다. 이 때문에 APNs(Apple Push Notification service) 키가 반드시 등록되어 있어야 한다.

APNs 키는 Apple Developer Console → Certificates, IDs & Profiles → Keys에서 발급하며, Firebase Console → 프로젝트 설정 → 클라우드 메시징 탭에 등록한다. 키 파일(.p8)과 Key ID, Team ID 세 가지를 등록해야 한다.

APNs 키가 없으면 iOS 실기기에서 `verifyPhoneNumber`를 호출해도 아무 반응이 없거나, `[ERROR:flutter/runtime/dart_vm_initializer.cc] Unhandled Exception` 류의 오류가 발생할 수 있다.

---

## 문제 2: 개발용 bypass가 Production에서 안 되는 이유

개발 중에는 흔히 이런 버튼을 만든다.

```dart
// 인증 패스하기 버튼
onPressed: () {
  setState(() => _currentStep = 2); // UI만 다음 단계로
}
```

빠르게 UI를 테스트하거나 다른 기능을 개발할 때 인증 단계를 건너뛰는 용도로 유용하다. 문제는 이 버튼이 UI 스텝만 바꿔줄 뿐, **서버에 PhoneVerification 레코드를 만들지 않는다**는 것이다.

### 서버 측 검증 로직을 이해해야 한다

Rails 서버에서는 회원가입 시 전화번호 인증이 완료되었는지를 DB 레코드로 확인한다.

```ruby
# RegisterUserCommand
def check_phone_verification!
  verification = PhoneVerification.find_by(phone_number: @phone_number)

  unless verification&.verified?
    raise CommandError.new(
      error: "인증이 완료되지 않은 전화번호입니다.",
      verification_required: true
    )
  end
end

def skip_verification?
  Rails.env.development? || Rails.env.test?
  # ← production에서는 false, 검증 통과 불가
end
```

개발 환경(`RAILS_ENV=development`)에서는 `skip_verification?`이 `true`를 반환하므로 레코드가 없어도 통과되지만, Render 같은 Production 서버에서는 반드시 `PhoneVerification` 레코드가 있어야 한다.

결국 개발 환경에서는 bypass 버튼이 잘 동작하지만, TestFlight나 실제 서비스 환경에서는 동일한 버튼을 눌러도 회원가입이 실패한다. 이 차이를 인식하지 못하면 "개발에서는 됐는데 릴리즈 빌드에서 안 된다"는 상황에 빠진다.

---

## 해결 방법

### 서버 측: 환경변수로 bypass 제어

`ENABLE_TEST_BYPASS` 환경변수를 추가해 Production에서도 제어 가능하게 만들었다. 베타 테스트나 QA 기간 동안 실제 SMS 없이도 인증 플로우를 테스트할 수 있게 해준다.

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

Render 대시보드에서 `ENABLE_TEST_BYPASS=true`를 추가하면 테스트 기간 동안 bypass가 동작한다. 정식 출시 전에 제거하면 된다.

이 방식의 장점은 코드를 수정하지 않고도 환경변수 하나로 bypass를 켜고 끌 수 있다는 것이다. 내부 테스터에게만 bypass 기능이 있는 앱을 배포하고, 출시 시점에 환경변수를 제거하면 된다.

### Flutter 측: bypass 버튼이 서버도 처리하도록

버튼에서 단순히 UI 스텝만 바꾸는 대신, 서버에 `111111` 코드로 인증 요청을 보내도록 수정했다. `verificationId`를 빈 문자열로 넘기면 Firebase 플로우를 완전히 건너뛰고 서버에 직접 인증 요청을 보내는 분기를 탄다.

```dart
// auth_repository_impl.dart
Future<bool> verifyCode(String phoneNumber, String code, String verificationId) async {
  // verificationId가 비어있으면 Firebase 스킵 → 서버 직접 호출
  if (verificationId.isEmpty) {
    await _apiClient.verifyCode({'phone_number': phoneNumber, 'code': code});
    return true;
  }

  // 일반 Firebase 흐름
  final firebaseToken = await _firebasePhoneAuth.verifyCodeAndGetToken(verificationId, code);
  await _apiClient.firebaseVerifyPhone({'firebase_token': firebaseToken});
  await _firebasePhoneAuth.signOut();
  return true;
}
```

```dart
// register_screen.dart - bypass 버튼
onPressed: () {
  final phone = _phoneController.text.trim();
  if (phone.length >= 10) {
    // 전화번호 있으면 서버에도 bypass 인증 처리
    context.read<AuthBloc>().add(
      AuthDevBypassVerificationRequested(phoneNumber: phone),
    );
  } else {
    setState(() => _currentStep = 2);
  }
},
```

BLoC에서는 `verificationId`를 빈 문자열로 넘겨 bypass 경로를 타게 한다.

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

이 구조의 핵심은 bypass 버튼이 실제 인증 플로우와 동일한 서버 사이드 상태를 만든다는 것이다. Firebase 토큰 검증만 건너뛰고, 서버에 `PhoneVerification` 레코드는 정상적으로 생성된다. 덕분에 이후 회원가입 요청도 정상 처리된다.

---

## 트러블슈팅 시 유용한 접근법

실제로 Firebase Phone Auth 문제를 디버깅할 때 유용했던 방법들이다.

**Firebase 콘솔 로그 확인:** Firebase Console → Authentication → Users 탭에서 인증 시도 기록을 확인할 수 있다. 시도 자체가 없다면 앱에서 요청이 Firebase에 도달하지 않은 것이다.

**Flutter 측 에러 로그:** `FirebaseAuth.verifyPhoneNumber`의 `verificationFailed` 콜백에서 `FirebaseAuthException`을 출력하면 구체적인 오류 코드를 볼 수 있다. `invalid-app-credential`, `quota-exceeded`, `app-not-authorized` 같은 코드가 원인을 정확히 가리킨다.

**Android 로그캣:** `adb logcat | grep -i firebase`로 실기기에서 Firebase SDK의 내부 로그를 확인할 수 있다. SHA-1 불일치나 Play Integrity 실패 같은 메시지가 여기서 나온다.

**테스트 전화번호 활용:** Firebase Console → Authentication → Sign-in method → Phone → Test phone numbers에 번호와 코드를 등록해두면, 실제 SMS 발송 없이 앱의 인증 플로우를 테스트할 수 있다. 이 번호에는 SMS quota가 적용되지 않는다.

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| SMS 미수신 (Android) | Firebase SHA-1 미등록 | 키스토어에서 추출 후 Firebase Console 등록 + google-services.json 재다운로드 |
| SMS 미수신 (iOS) | APNs 키 미등록 | Apple Developer에서 발급 후 Firebase 업로드 |
| bypass 후 회원가입 실패 | UI만 스킵, 서버 PhoneVerification 레코드 없음 | bypass 버튼이 서버에 `111111` 코드로 인증 처리 |
| Production bypass 불가 | `skip_verification?`이 dev/test 환경만 허용 | `ENABLE_TEST_BYPASS` 환경변수 도입 |

Firebase Phone Auth는 설정이 맞으면 코드 자체는 간단하다. 문제는 항상 **플랫폼별 설정**과 **개발/프로덕션 환경 차이**에서 발생한다.

---

## Key Takeaways

- Firebase Phone Auth에서 SMS가 오지 않으면 가장 먼저 SHA-1(Android), APNs 키(iOS) 등록 여부를 확인한다.
- Android SHA-1 등록 후에는 반드시 `google-services.json`을 재다운로드해 교체해야 변경이 반영된다.
- 개발용 bypass 버튼은 서버 사이드 상태(PhoneVerification 레코드)까지 함께 만들어야 Production에서도 동작한다.
- 환경변수 `ENABLE_TEST_BYPASS`로 bypass 기능을 켜고 끄면, 코드 수정 없이 베타 테스트와 정식 출시를 구분할 수 있다.
- `verifyPhoneNumber`의 `verificationFailed` 콜백과 Android 로그캣은 원인 파악에 핵심적인 정보를 제공한다.
