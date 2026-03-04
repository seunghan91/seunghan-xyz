---
title: "7개 Flutter 앱 인증 보안 크로스 감사 - iOS 제출 전 점검"
date: 2026-02-26T12:00:00+09:00
draft: false
tags: ["Flutter", "보안", "SecureStorage", "SharedPreferences", "인증"]
description: "iOS 1.0 제출 전 7개 Flutter 앱의 인증/보안을 일괄 점검하여 SharedPreferences 평문 저장, 401 갱신 미구현, PII 노출 3가지 패턴을 발견하고 수정한 기록"
---

[이전 글](/posts/flutter-rails-auth-session-persistence-debugging/)에서 Flutter + Rails 앱의 세션 버그 3개를 고쳤다. 고치고 나니 궁금해졌다. **다른 프로젝트에도 같은 문제가 있지 않을까?**

iOS 1.0 제출을 앞둔 7개 Flutter 앱을 대상으로 인증/보안 크로스 감사를 진행했다.

---

## 감사 결과 요약

| 프로젝트 | 인증 방식 | 결과 |
|---|---|---|
| 앱 A (부동산 계약서) | 자체 JWT + SecureStorage | ✅ 양호 |
| 앱 B (AI 여행) | 자체 JWT + SharedPreferences | 🔴 3건 |
| 앱 C (팀 관리) | 자체 JWT + SharedPreferences | 🔴 2건 |
| 앱 D (운세/MBTI) | Firebase Auth + Supabase | 🔴 1건 |
| 앱 E (필름 스캐너) | Supabase Auth | ✅ 양호 |
| 앱 F (AI 미디어) | Supabase Auth | ✅ 양호 |
| 앱 G (음성 대화) | - | ⏭️ 미확인 |

**Supabase SDK가 인증을 관리하는 앱은 모두 양호**했고, **자체 JWT 구현 앱에서만 문제**가 있었다.

---

## 패턴 1: SharedPreferences에 토큰 평문 저장

SharedPreferences는 Android에서 XML, iOS에서 plist로 **암호화 없이** 저장된다. 앱 B, 앱 C에서 발견.

```dart
// ❌ SharedPreferences - 평문 저장
final prefs = await SharedPreferences.getInstance();
await prefs.setString('auth_token', token);

// ✅ FlutterSecureStorage - iOS Keychain / Android Keystore
const storage = FlutterSecureStorage();
await storage.write(key: 'auth_token', value: token);
```

수정은 내부 구현만 교체하고 API는 유지하여 호출부 변경을 최소화했다. `bool` 같은 비-String 타입은 `value.toString()` / `value == 'true'`로 변환.

---

## 패턴 2: 401 에러 시 토큰 갱신 없이 로그아웃

앱 B는 401을 받으면 토큰만 지우고 끝, 앱 C는 로그만 찍고 방치.

```dart
// ❌ 갱신 없이 토큰 삭제만
if (error.response?.statusCode == 401) {
  tokenStorage.clearTokens();  // 사용자는 다시 로그인해야 함
}
```

앱 B는 refresh token 갱신 → 원래 요청 재시도 → 실패 시 로그아웃 플로우를 추가했다.

```dart
// ✅ 401 → refresh 시도 → 재시도 → fallback
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

앱 C는 서버에 refresh 엔드포인트가 없어서 `onUnauthorized` 콜백으로 최소 대응.

---

## 패턴 3: PII가 SharedPreferences에 평문 저장

앱 D는 Firebase Auth로 인증 자체는 안전하지만, 게스트 사용자의 **개인정보**(생년월일, 성별, 이름)를 SharedPreferences에 저장하고 있었다. App Store 심사에서 개인정보 보호 위반으로 리젝될 수 있다.

```dart
// ❌ PII를 평문으로
await prefs.setString('guest_profile', jsonEncode({
  'birthDate': '1990-05-15', 'gender': 'male', 'name': '홍길동',
}));

// ✅ SecureStorage로 암호화
await storage.write(key: 'guest_profile', value: jsonEncode({...}));
```

---

## 교훈

**자체 구현 vs SDK**: 문제는 모두 자체 JWT에서 발생. SDK를 쓰면 저장/갱신/만료가 자동이다. 자체 구현 시 체크리스트:
- [ ] SecureStorage 사용 여부
- [ ] 401 시 refresh 시도 여부
- [ ] 갱신 실패 시 로그아웃 처리
- [ ] WebSocket 토큰 동기화

**SharedPreferences 용도**: 다크모드, 언어, 온보딩 같은 비민감 설정 값 전용. 토큰/PII는 절대 넣지 말 것.

**같은 실수는 복제된다**: 보일러플레이트 코드일수록 첫 번째 구현이 중요하다.

**iOS 제출 전 한 줄 점검**:

```bash
grep -r "SharedPreferences" --include="*.dart" lib/
```

이것만으로도 민감 데이터 평문 저장 여부를 빠르게 확인할 수 있다.
