---
title: "Flutter Firebase Phone Auth - SMS가 안 와요? 진단부터 코드 수정까지"
date: 2026-02-25
draft: false
tags: ["Flutter", "Firebase", "Phone Auth", "Rails", "인증"]
description: "Firebase 전화 인증을 연동했는데 SMS가 안 오는 경우의 원인 분석과, 개발용 bypass 버튼이 Production에서 동작하지 않는 문제 해결"
---

Flutter 앱에 전화번호 인증을 붙이고 나서 "인증번호가 안 와요"라는 상황을 마주쳤다. 그리고 개발용 bypass 버튼을 눌러서 인증을 건너뛰고 회원가입을 시도하면 서버에서 "인증이 완료되지 않은 전화번호입니다"가 떴다. 두 문제를 같이 정리한다.

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

핵심은 **SMS 발송 자체를 Firebase가 담당**한다는 점이다. Rails나 다른 백엔드에서 Twilio 등을 호출하는 구조가 아니다.

---

## 문제 1: SMS가 안 오는 이유

Firebase Phone Auth가 동작하려면 Firebase Console에서 몇 가지 설정이 되어 있어야 한다.

**체크리스트:**
1. Authentication → Sign-in method → **전화** 활성화 여부
2. Android의 경우 **SHA-1 지문** 등록 여부
3. iOS의 경우 **APNs 키** 등록 여부

특히 Android는 SHA-1 없이는 전화 인증이 아예 동작하지 않는다. Firebase가 앱 무결성을 검증하는 Play Integrity API와 연동되기 때문이다.

```bash
# 업로드 키스토어에서 SHA-1 추출
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_PASSWORD
```

출력 결과에서 SHA1, SHA256 값을 복사해 Firebase Console → 프로젝트 설정 → Android 앱 → 디지털 지문 추가에 등록한다.

등록 후에는 **google-services.json을 새로 다운로드**해서 `android/app/`에 교체해야 한다. 이 파일에 지문 정보가 포함되기 때문이다.

---

## 문제 2: 개발용 bypass가 Production에서 안 되는 이유

개발 중에는 흔히 이런 버튼을 만든다.

```dart
// 인증 패스하기 버튼
onPressed: () {
  setState(() => _currentStep = 2); // UI만 다음 단계로
}
```

이 버튼은 UI 스텝만 바꿔줄 뿐, **서버에 PhoneVerification 레코드를 만들지 않는다.**

그러면 서버(Rails)에서 회원가입 시 이런 체크를 통과하지 못한다.

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

개발 환경에서는 `skip_verification?`이 `true`를 반환하므로 문제없이 동작하지만, Render 같은 Production 서버에서는 false가 되어 막힌다.

---

## 해결 방법

### 서버 측: 환경변수로 bypass 제어

`ENABLE_TEST_BYPASS` 환경변수를 추가해 Production에서도 제어 가능하게 만들었다.

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

### Flutter 측: bypass 버튼이 서버도 처리하도록

버튼에서 단순히 UI 스텝만 바꾸는 대신, 서버에 `111111` 코드로 인증 요청을 보내도록 수정했다.

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

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| SMS 미수신 (Android) | Firebase SHA-1 미등록 | 키스토어에서 추출 후 Firebase Console 등록 |
| SMS 미수신 (iOS) | APNs 키 미등록 | Apple Developer에서 발급 후 Firebase 업로드 |
| bypass 후 회원가입 실패 | UI만 스킵, 서버 PhoneVerification 레코드 없음 | bypass 버튼이 서버에 `111111` 코드로 인증 처리 |
| Production bypass 불가 | `skip_verification?`이 dev/test 환경만 허용 | `ENABLE_TEST_BYPASS` 환경변수 도입 |

Firebase Phone Auth는 설정이 맞으면 코드 자체는 간단하다. 문제는 항상 **플랫폼별 설정**과 **개발/프로덕션 환경 차이**에서 발생한다.
