---
title: "Flutter + Rails 인증 세션이 계속 풀리는 문제 - 3가지 원인과 해결"
date: 2025-09-27
draft: false
tags: ["Flutter", "Rails", "BLoC", "WebSocket", "Session", "디버깅"]
description: "Flutter BLoC 앱에서 로그인 세션이 자꾸 끊기는 현상을 서버 로그부터 추적하여 DTA 잔존 코드, WebSocket 클로저 캡처 버그, 토큰 수명 설정 3가지 원인을 찾고 해결한 기록"
cover:
  image: "/images/og/flutter-rails-auth-session-persistence-debugging.png"
  alt: "Flutter Rails Auth Session Persistence Debugging"
  hidden: true
---

Flutter BLoC 앱에서 로그인을 해도 세션이 자꾸 풀린다. 분명 SecureStorage에 토큰도 저장하고, Dio 인터셉터로 401 시 자동 갱신도 구현했는데 왜?

서버 로그부터 시작해서 원인 3개를 찾고 모두 고친 과정을 정리한다.

---

## 기술 스택

- **모바일**: Flutter + BLoC 패턴 + Dio HTTP + SecureStorage
- **서버**: Rails 8 API + ActionCable WebSocket
- **인증**: SHA-256 digest 기반 access token + JTI refresh token (90일)
- **실시간**: ActionCable WebSocket (토큰 기반 인증)

---

## 증상

1. 로그인 직후는 정상 동작
2. 시간이 지나면 API 요청이 401로 실패
3. 토큰 갱신은 되는 것 같은데 WebSocket이 끊어짐
4. 결국 앱이 미인증 상태로 전환

---

## 원인 1: 레거시 코드의 유령 - DTA 잔존 메서드

### 발견

서버 로그에서 토큰 갱신 시 `user.tokens` 관련 에러가 간헐적으로 보였다. 이전에 devise_token_auth(DTA)를 사용하다가 자체 토큰 시스템으로 마이그레이션했는데, `token_refresh_service.rb`에 DTA 시절 코드가 남아 있었다.

```ruby
# ❌ DTA 제거 후에도 남아있던 코드
def validate_google_oauth_token(user)
  token = user.tokens&.dig('default', 'access_token')  # NoMethodError!
  return true if token.blank?
  # ... Google OAuth 검증 로직
end
```

`User` 모델에서 `tokens` 컬럼/메서드는 DTA 제거 시 이미 삭제됐다. 하지만 이 코드는 `rescue => e` 블록 안에서 호출되어 에러가 잡히고 `true`를 반환했기 때문에, **에러가 발생하지만 정상 동작하는 것처럼 보이는** 최악의 상황이었다.

### 해결

OAuth 토큰 검증을 refresh 플로우에서 제거했다. OAuth 인증은 초기 로그인 시에만 검증하면 되고, refresh 플로우는 RefreshToken 자체의 만료/활성 상태로 판단하면 된다.

```ruby
# ✅ 수정 후
def validate_google_oauth_token(user)
  true  # OAuth 검증은 초기 로그인 시에만
end
```

이것만으로 ~130줄의 죽은 코드가 제거됐다.

---

## 원인 2: Dart 클로저의 함정 - WebSocket 스테일 토큰

### 발견

이게 핵심 원인이었다. ActionCable WebSocket 클라이언트를 생성할 때 토큰을 이렇게 전달하고 있었다:

```dart
// ❌ 문제 코드
final accessToken = await secureStorage.read('access_token');

actionCableClient = ActionCableClient(
  baseUrl: apiBaseUrl,
  getAccessToken: () => accessToken ?? '',  // 로컬 변수 캡처!
);
```

Dart에서 클로저는 **생성 시점의 변수 참조**를 캡처한다. `accessToken`은 `final` 로컬 변수이므로, Dio 인터셉터가 401 에러 후 새 토큰으로 갱신해도 WebSocket의 `getAccessToken` 클로저는 **여전히 옛날 토큰**을 반환한다.

흐름을 정리하면:

```
1. 앱 시작 → accessToken = "token_A" (로컬 변수)
2. WebSocket 생성 → getAccessToken: () => "token_A" (캡처됨)
3. 시간 경과 → token_A 만료
4. Dio 인터셉터 → 401 감지 → refresh → SecureStorage에 "token_B" 저장
5. WebSocket 재연결 시도 → getAccessToken() → "token_A" 반환 (스테일!)
6. WebSocket 인증 실패 → 연결 끊김
```

### 해결

세 가지를 함께 수정했다:

**1) 가변 토큰 필드 도입**

```dart
// ✅ 클래스 필드로 변경
String _latestAccessToken = '';

// WebSocket 생성 시
_latestAccessToken = accessToken;
actionCableClient = ActionCableClient(
  baseUrl: apiBaseUrl,
  getAccessToken: () => _latestAccessToken,  // 가변 필드 참조
);
```

**2) Dio 인터셉터에서 토큰 갱신 콜백**

```dart
// DioClient에 콜백 추가
void Function(String newAccessToken)? onTokenRefreshed;

// 인터셉터 내부 - 갱신 성공 후
onTokenRefreshed?.call(newAccessToken);
```

```dart
// 앱에서 콜백 연결
dioClient.onTokenRefreshed = (newAccessToken) {
  _latestAccessToken = newAccessToken;
  actionCableClient?.reconnectWithNewToken();
};
```

**3) AuthBloc 상태 변화 시 WebSocket 재연결**

```dart
// AuthAuthenticated 상태에서 토큰이 변경되면
if (newToken != _latestAccessToken) {
  _latestAccessToken = newToken;
  actionCableClient?.reconnectWithNewToken();
}
```

이렇게 하면 토큰이 갱신되는 모든 경로(proactive 타이머, reactive 401 인터셉터)에서 WebSocket이 새 토큰으로 재연결된다.

---

## 원인 3: 모바일에 맞지 않는 토큰 수명

### 발견

서버의 access token 수명이 모바일에도 24시간으로 설정되어 있었다.

```ruby
# ❌ 모바일도 웹과 동일한 24시간
when 'flutter'
  ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_HOURS', 24).to_i.hours
```

모바일 앱은 백그라운드 전환, 네트워크 불안정 등 웹과 다른 환경이다. 업계 권장 사항은 모바일 access token 15~60분, refresh token 30~90일이다.

### 해결

```ruby
# ✅ 모바일: 1시간 (refresh token 90일과 조합)
when 'flutter'
  ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_MINUTES', 60).to_i.minutes
```

AuthBloc의 proactive refresh 타이머도 이에 맞춰 조정했다. 1시간 토큰 기준 만료 8분 전(52분 시점)에 자동 갱신한다.

---

## 교훈

### 1. 마이그레이션 후에는 grep으로 전수 조사하라

DTA를 제거할 때 모델과 컨트롤러는 정리했지만, 서비스 레이어 깊숙한 곳의 참조를 놓쳤다. `rescue` 블록이 에러를 삼켜서 발견이 늦어졌다.

```bash
# 마이그레이션 후 필수
grep -r "user.tokens" --include="*.rb" .
grep -r "devise_token_auth" --include="*.rb" .
```

### 2. Dart 클로저는 "무엇을" 캡처하는지 주의하라

`final` 로컬 변수를 캡처하면 그 값은 영원히 바뀌지 않는다. 토큰처럼 갱신되어야 하는 값은 가변 필드를 참조하거나, 매번 SecureStorage에서 읽도록 해야 한다.

```dart
// ❌ 불변 캡처
final token = await getToken();
callback: () => token

// ✅ 가변 참조
callback: () => _mutableTokenField

// ✅ 또는 매번 조회
callback: () async => await secureStorage.read('token')
```

### 3. 모바일과 웹의 토큰 전략은 달라야 한다

| | 모바일 | 웹 |
|---|---|---|
| Access Token | 15~60분 | 1~24시간 |
| Refresh Token | 30~90일 | 7~30일 |
| 갱신 방식 | Proactive + Reactive | Reactive 위주 |
| WebSocket | 토큰 갱신 시 재연결 필수 | 쿠키 기반 가능 |

### 4. WebSocket과 HTTP 인증은 별개로 관리하라

Dio 인터셉터가 토큰을 갱신해도 WebSocket은 모른다. 두 채널의 인증 상태를 동기화하는 메커니즘이 반드시 필요하다.

---

## 진단 순서 요약

```
1. 서버 로그 확인 (Render dashboard)
   → 401 에러 패턴, 토큰 갱신 에러 발견

2. 코드 추적 (서버 → 클라이언트)
   → token_refresh_service.rb의 DTA 잔존 코드
   → Flutter WebSocket 클로저 캡처 문제

3. 외부 검증 (업계 사례 조사)
   → 모바일 토큰 수명 권장 사항 확인
   → WebSocket 스테일 토큰이 #1 원인 확인

4. 순차 수정 (의존성 순서대로)
   → 서버 죽은 코드 제거 → WebSocket 재연결 → 토큰 수명 조정
```

서버 로그에서 시작해서 클라이언트까지 추적하는 것이 핵심이었다. 클라이언트만 봤으면 원인 1을 놓쳤을 것이고, 서버만 봤으면 원인 2를 놓쳤을 것이다.

> 이 버그를 고친 뒤 다른 프로젝트에도 같은 문제가 있는지 궁금해져서 7개 Flutter 앱을 크로스 감사했다. 그 이야기는 [다음 글](/posts/flutter-auth-cross-audit/)에서.
