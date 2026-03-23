---
title: "7개 Flutter 앱 인증 보안 크로스 감사 - iOS 제출 전 점검"
date: 2025-10-21
draft: true
tags: ["Flutter", "보안", "SecureStorage", "SharedPreferences", "Authentication"]
description: "iOS 1.0 제출 전 7개 Flutter 앱의 인증/보안을 일괄 점검하여 SharedPreferences 평문 저장, 401 갱신 미구현, PII 노출 3가지 패턴을 발견하고 수정한 기록"
cover:
  image: "/images/og/flutter-auth-cross-audit.png"
  alt: "Flutter Auth Cross Audit"
  hidden: true
---

[이전 글](/posts/flutter-rails-auth-session-persistence-debugging/)에서 Flutter + Rails 앱의 세션 버그 3개를 고쳤다. 고치고 나니 궁금해졌다. **다른 프로젝트에도 같은 문제가 있지 않을까?**

iOS 1.0 제출을 앞둔 7개 Flutter 앱을 대상으로 인증/보안 크로스 감사를 진행했다. 앱 하나씩 따로 보면 놓치기 쉬운 패턴이 여러 프로젝트를 한꺼번에 비교하면 선명하게 드러난다. 결론부터 말하자면, **Supabase나 Firebase 같은 인증 SDK를 쓰는 앱은 문제가 없었고, 자체 JWT를 구현한 앱에서만 취약점이 나왔다.**

---

## 왜 크로스 감사인가

동일한 개발자가 여러 프로젝트를 운영하면 같은 실수가 복제된다. 첫 번째 앱에서 토큰을 SharedPreferences에 저장하는 코드를 짰다면, 두 번째 세 번째 앱도 동일한 보일러플레이트를 복사했을 가능성이 높다.

단일 앱 리뷰는 상대적인 비교가 없어서 "그냥 이렇게 쓰는 거 아닌가"라고 넘어가기 쉽다. 크로스 감사는 **7개를 나란히 놓고 보기 때문에 패턴이 바로 눈에 띈다.** 특히 iOS App Store 심사는 개인정보 처리에 까다롭고, 한 번 리젝 받으면 재심사까지 시간이 걸린다. 제출 전 한 번에 정리하는 게 낫다.

---

## 감사 대상과 방법

총 7개 앱을 점검했다. 각 앱의 `pubspec.yaml`에서 인증 관련 패키지를 확인하고, `lib/` 디렉토리 전체를 grep으로 훑었다.

주로 확인한 항목은 세 가지다.

1. **토큰 저장 위치** - SharedPreferences인지 FlutterSecureStorage인지
2. **401 처리 로직** - refresh 시도 여부, 실패 시 fallback
3. **개인정보(PII) 저장 방식** - 이름, 생년월일, 이메일 등이 평문인지

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

앱 A는 자체 JWT임에도 양호했는데, 이 앱은 처음 개발할 때 SecureStorage를 의도적으로 도입했던 앱이다. 이후 앱들이 앱 A를 참고하지 않고 새로 짰거나 다른 소스에서 보일러플레이트를 가져오면서 문제가 생겼다.

---

## 패턴 1: SharedPreferences에 토큰 평문 저장

SharedPreferences는 Android에서 XML 파일로, iOS에서 `.plist` 파일로 **암호화 없이** 저장된다. 루팅된 기기나 iTunes 백업 분석 도구를 쓰면 누구나 토큰을 읽을 수 있다. 앱 B, 앱 C에서 발견.

```dart
// ❌ SharedPreferences - 평문 저장
final prefs = await SharedPreferences.getInstance();
await prefs.setString('auth_token', token);
await prefs.setString('refresh_token', refreshToken);
```

iOS는 Keychain, Android는 Keystore라는 하드웨어 기반 보안 영역을 제공한다. `flutter_secure_storage` 패키지가 이 두 가지를 동일한 API로 추상화한다.

```dart
// ✅ FlutterSecureStorage - iOS Keychain / Android Keystore
const storage = FlutterSecureStorage();
await storage.write(key: 'auth_token', value: token);
await storage.write(key: 'refresh_token', value: refreshToken);
```

수정할 때는 내부 구현만 교체하고 API는 유지하여 호출부 변경을 최소화했다. 토큰 관련 메서드를 한 클래스(`TokenStorage`)에 모아두었기 때문에 변경 지점이 하나였다.

`SharedPreferences`는 `String`, `int`, `bool`, `double`, `List<String>` 같은 다양한 타입을 지원하지만 `FlutterSecureStorage`는 `String`만 지원한다. `bool` 같은 타입은 아래처럼 변환한다.

```dart
// bool 저장
await storage.write(key: 'is_guest', value: isGuest.toString());

// bool 읽기
final raw = await storage.read(key: 'is_guest');
final isGuest = raw == 'true';
```

---

## 패턴 2: 401 에러 시 토큰 갱신 없이 로그아웃

앱 B는 401을 받으면 토큰만 지우고 끝이었다. 앱 C는 로그만 찍고 아무것도 하지 않았다. 두 경우 모두 사용자 입장에서는 앱을 사용하다가 갑자기 로그인 화면으로 튕겨 나가는 경험을 하게 된다.

```dart
// ❌ 갱신 없이 토큰 삭제만
if (error.response?.statusCode == 401) {
  tokenStorage.clearTokens();  // 사용자는 다시 로그인해야 함
}
```

401은 두 가지 경우다. 하나는 access token이 만료된 것이고, 다른 하나는 실제 인증 실패다. 대부분의 경우 access token 만료이며, 이때는 refresh token으로 새 access token을 발급받아 원래 요청을 재시도하면 된다.

앱 B에는 refresh 엔드포인트가 서버에 있었기 때문에 전체 플로우를 구현했다.

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

`Dio` interceptor 안에서 refresh를 시도하는 구조다. 주의할 점이 있다. **refresh 요청 자체가 401을 받으면 무한 루프에 빠진다.** 이를 방지하기 위해 refresh 진행 중임을 나타내는 플래그와, refresh 엔드포인트는 interceptor 처리에서 제외하는 로직을 추가했다.

```dart
bool _isRefreshing = false;

Future<bool> _attemptTokenRefresh() async {
  if (_isRefreshing) return false;
  _isRefreshing = true;
  try {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken == null) return false;
    // refresh 요청은 interceptor 적용 없이 직접 호출
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

앱 C는 서버에 refresh 엔드포인트가 없어서 전체 구현이 불가능했다. 대신 `onUnauthorized` 콜백을 추가해서 UI 레이어에서 적절히 처리할 수 있게 최소한의 인터페이스만 뒀다. 서버 수정 없이 할 수 있는 최선이다.

---

## 패턴 3: PII가 SharedPreferences에 평문 저장

앱 D는 Firebase Auth로 인증 자체는 안전하지만, 게스트 사용자의 **개인정보**(생년월일, 성별, 이름)를 SharedPreferences에 저장하고 있었다.

Firebase Auth는 로그인한 사용자의 `uid`, `email`, `displayName` 같은 기본 정보만 관리한다. 앱 D는 운세 서비스 특성상 게스트 사용자도 생년월일과 이름을 입력하게 되어 있는데, 이 데이터를 SharedPreferences에 넣고 있었다.

```dart
// ❌ PII를 평문으로
await prefs.setString('guest_profile', jsonEncode({
  'birthDate': '1990-05-15', 'gender': 'male', 'name': '홍길동',
}));
```

App Store 심사 기준에서 생년월일, 이름, 성별은 민감한 개인정보다. 암호화 없이 저장되면 심사 리젝 사유가 될 수 있고, GDPR이나 국내 개인정보보호법 관점에서도 문제가 된다.

```dart
// ✅ SecureStorage로 암호화
await storage.write(
  key: 'guest_profile',
  value: jsonEncode({
    'birthDate': '1990-05-15',
    'gender': 'male',
    'name': '홍길동',
  }),
);
```

수정 자체는 간단하지만, **왜 이 데이터가 SharedPreferences에 들어갔는지 추적하는 게 더 중요했다.** 확인해보니 초기 프로토타입에서 빠르게 구현할 때 SecureStorage 의존성을 추가하지 않았고, 그 코드가 그대로 프로덕션에 올라간 경우였다.

---

## 디버깅 중 만난 엣지 케이스

크로스 감사를 하다 보면 단순 grep으로는 잡히지 않는 케이스도 있었다.

**앱 B의 토큰 복수 저장**: 메인 토큰 저장 클래스는 SecureStorage로 바꿨는데, 캐시용으로 `SharedPreferences`에 토큰을 하나 더 써두는 코드가 다른 파일에 있었다. "빠른 읽기를 위해" 만들어둔 캐시였는데 보안 구멍이었다. `grep -r "auth_token" --include="*.dart" lib/`로 재검색해서 잡아냈다.

**앱 C의 토큰 동기화 문제**: SharedPreferences → SecureStorage로 마이그레이션하면서 기존 앱 업데이트 유저를 고려해야 했다. 기존 사용자는 SharedPreferences에 토큰이 있고 SecureStorage에는 없다. 이 경우 자동으로 로그아웃 처리했다. 강제 로그아웃이 UX 상 나쁘지만, 보안을 위한 단회성 조치이므로 릴리즈 노트에 명시했다.

```dart
// 마이그레이션: SharedPreferences에 남은 토큰 있으면 삭제 후 재로그인 유도
Future<void> migrateTokenStorage() async {
  final prefs = await SharedPreferences.getInstance();
  final oldToken = prefs.getString('auth_token');
  if (oldToken != null) {
    await prefs.remove('auth_token');
    await prefs.remove('refresh_token');
    // SecureStorage에는 저장하지 않음 - 재로그인 유도
  }
}
```

---

## 교훈과 Key Takeaways

**자체 구현 vs SDK**: 문제는 모두 자체 JWT에서 발생했다. SDK를 쓰면 저장/갱신/만료가 자동이다. 자체 구현 시 반드시 체크해야 할 목록:

- [ ] 토큰 저장에 SecureStorage 사용 여부
- [ ] 401 시 refresh 시도 여부
- [ ] refresh 실패 시 로그아웃 처리
- [ ] refresh 요청 자체의 무한 루프 방지
- [ ] WebSocket 연결의 토큰 동기화
- [ ] 앱 업데이트 시 스토리지 마이그레이션

**SharedPreferences 용도**: 다크모드, 언어 설정, 온보딩 완료 여부처럼 **유출되어도 피해가 없는 비민감 설정 값** 전용으로만 써야 한다. 토큰이나 PII는 절대 넣지 말 것.

**같은 실수는 복제된다**: 보일러플레이트 코드일수록 첫 번째 구현이 중요하다. 스타터 템플릿이나 공통 모듈에서 한 번 잘 만들어두면 이후 앱들은 자연스럽게 안전한 패턴을 따르게 된다.

**iOS 제출 전 빠른 점검**:

```bash
# SharedPreferences 사용처 전체 확인
grep -r "SharedPreferences" --include="*.dart" lib/

# auth_token, refresh_token 키워드 확인
grep -rn "auth_token\|refresh_token\|access_token" --include="*.dart" lib/

# PII 키워드 확인
grep -rn "birthDate\|birth_date\|phoneNumber\|phone_number" --include="*.dart" lib/
```

이 세 줄만 실행해도 민감 데이터 평문 저장 여부를 빠르게 파악할 수 있다. 5분짜리 점검으로 App Store 리젝을 피할 수 있다면 충분히 가치 있는 습관이다.

**크로스 감사의 가치**: 단일 앱 코드 리뷰보다 여러 앱을 나란히 놓고 보는 게 패턴 발견에 훨씬 효과적이다. 인증/보안처럼 같은 구조가 반복되는 영역은 특히 그렇다. 앞으로 새 프로젝트를 시작할 때는 인증 모듈을 공통 패키지로 분리해서 모든 앱이 동일한 구현을 공유하도록 할 계획이다.
