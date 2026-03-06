---
title: "로그인이 자꾸 풀린다 — API 래퍼 포맷 불일치가 만든 연쇄 버그"
date: 2025-12-02
draft: false
tags: ["Flutter", "Rails", "BLoC", "디버깅", "JWT", "Chrome Extension"]
description: "모바일 앱 로그인이 자꾸 풀리는 증상을 추적해보니, 서버 응답 래퍼 포맷 불일치 하나가 Flutter, Rails, Chrome Extension 3개 클라이언트에 걸쳐 5개 버그로 이어져 있었다."
cover:
  image: "/images/og/api-response-wrapper-token-parsing-debug.png"
  alt: "Api Response Wrapper Token Parsing Debug"
  hidden: true
---

모바일 앱에서 로그인이 자꾸 풀린다. 로그인 직후는 정상인데, 앱을 잠깐 백그라운드로 내렸다가 다시 열면 로그인 화면이 뜬다.

SecureStorage에 토큰 저장도 확인했고, Dio 인터셉터로 401 자동 갱신도 구현되어 있는데 왜?

---

## 증상 재현

1. 앱 로그인 → 정상 동작
2. 액세스 토큰 만료 시점 전후로 앱 재시작
3. → 세션 복원 실패, 강제 로그아웃

서버 로그에서 힌트를 찾았다.

```
FormatException: "user" field is missing or null
```

토큰 갱신 응답을 파싱하다가 터지고 있었다.

---

## 구조 파악

서버는 모든 API 응답을 공통 래퍼로 감싼다.

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

로그인 엔드포인트는 항상 이 형식으로 반환했다. 그런데 토큰 갱신 엔드포인트는 어느 시점에가 `data` 안에 `user` 키를 빼고 flat하게 반환하도록 바뀌어 있었다.

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

`data.user`가 없으니 `AuthResponse.fromJson(json['user'])` 에서 예외 발생 → `clearAuthData()` 호출 → 강제 로그아웃.

---

## 버그 1: 서버 — 갱신 응답 포맷 불일치

**원인**: 토큰 갱신 서비스가 `UserService` 객체 대신 `user.as_json(only: [:id, :email, :name])` (축약된 Hash)만 반환하고 있었다.

**수정**:

```ruby
# 수정 전 — Service
@user_data = user&.as_json(only: [:id, :email, :name])
# Controller
response_data = result.user_data.merge(access_token: ..., refresh_token: ...)

# 수정 후 — Service
@user_instance = user        # 원본 User 객체 보존
@user_data = user&.as_json(only: [:id, :email, :name])

# Controller
user_obj = result.user_instance ? standard_user_response(result.user_instance) : result.user_data
response_data = { user: user_obj, access_token: ..., refresh_token: ... }
```

로그인 엔드포인트가 쓰는 `standard_user_response(user)` 헬퍼를 그대로 재사용해서 일관성 확보.

---

## 버그 2: Flutter — JWT 만료 시간 파싱 오류

토큰 갱신은 고쳤는데, `_extractTokenExpiry` 함수도 이상했다.

JWT payload를 Base64 디코딩한 뒤 JSON을 수동으로 파싱하고 있었다.

```dart
// 수정 전 — 콤마/콜론으로 문자열 직접 분해
final pairs = decoded.split(',');
for (final pair in pairs) {
  final kv = pair.split(':');
  if (kv.length == 2) {
    json[kv[0].replaceAll('"', '').trim()] = kv[1].replaceAll('"', '').trim();
  }
}
```

`"exp":1234567890` 같은 단순 케이스는 되는 척 하지만, 값에 콜론이 들어가거나(`"iss":"https://..."`) 중첩 객체가 있으면 파싱이 깨진다. `exp` 필드를 못 읽으면 `tokenExpiresAt`이 null → 타이머 미설정 → 프로액티브 갱신 안 됨 → 결국 만료 후 강제 로그아웃.

```dart
// 수정 후
final json = jsonDecode(decoded) as Map<String, dynamic>;
```

표준 라이브러리를 쓰면 된다. 왜 수동으로 파싱하고 있었는지...

---

## 버그 3~5: Chrome 확장 — 동일한 포맷 불일치가 3군데

웹 쪽도 점검했다. Rails 웹 앱은 Devise 세션 기반이라 해당 없었는데, Chrome 확장에서 같은 패턴의 버그가 3개 있었다.

**공통 원인**: 토큰 갱신 응답 body에서 `data.refresh_token`을 읽어야 하는데 `data` 안에 nested된 걸 모르고 flat으로 읽음.

```javascript
// 수정 전
const newRefreshToken = data.refresh_token;  // undefined

// 수정 후
const newRefreshToken = data.data?.refresh_token;
```

`background.js`, `popup.js`, `sidepanel.js` 세 파일 모두 각자 토큰 갱신 로직을 별도 구현하다 보니 같은 버그가 세 번 복사되어 있었다.

**`background.js`에는 추가 버그 하나 더**: 토큰 검증 함수에서 스코프에 없는 변수를 참조하고 있었다.

```javascript
// 수정 전 — client, tokenType 변수가 이 함수 스코프에 없음
const refreshed = {
  client: response.headers.get('client') || client,        // ReferenceError 가능
  'token-type': response.headers.get('token-type') || tokenType,  // ReferenceError 가능
};

// 수정 후
const refreshed = {
  client: response.headers.get('client') || deviseAuth.client,
  'token-type': response.headers.get('token-type') || deviseAuth['token-type'] || 'Bearer',
};
```

서버가 CORS 헤더에 `Access-Control-Expose-Headers`를 올바르게 설정해둔 덕분에 헤더 폴백이 동작해서 실제 장애는 안 났지만, 헤더가 없는 환경에서는 런타임 에러.

---

## 왜 즉시 터지지 않았나

세 곳 모두 **header fallback**이 있었다.

```javascript
'refresh-token': body?.data?.refresh_token
  || response.headers.get('refresh-token')   // ← 이게 실제로 동작하고 있었음
  || deviseAuth['refresh-token']
  || ''
```

서버가 `refresh-token` 응답 헤더도 함께 설정하기 때문에 body 파싱이 실패해도 헤더에서 값을 읽어왔다. 기능상 동작하니 버그를 발견하기 어려웠다.

Flutter도 마찬가지로 `_extractTokenExpiry`가 null을 반환해도 즉시 터지지는 않는다. 프로액티브 갱신 타이머가 안 걸릴 뿐이고, Dio 401 인터셉터가 reactive fallback 역할을 해주기 때문에 대부분의 케이스는 커버됐다. 문제는 앱 재시작 시 콜드 스타트에서 refresh token으로 session restore 시도하다가 `user` 필드 없는 응답을 받는 케이스였다.

---

## 정리

이번 삽질의 핵심은 **서버 응답 래퍼 포맷을 클라이언트들이 제각각 인식하고 있었다**는 것.

| 클라이언트 | 버그 | 실제 영향 |
|---------|------|---------|
| 모바일 앱 | 갱신 응답에 `user` 키 없음 | 앱 강제 로그아웃 (직접적 원인) |
| 모바일 앱 | JWT 수동 파싱 오류 | 타이머 미설정 → 갱신 타이밍 놓침 |
| Chrome 확장 background | body 파싱 오류 + 미선언 변수 | 헤더 폴백으로 마스킹 |
| Chrome 확장 popup | body 파싱 오류 | 헤더 폴백으로 마스킹 |
| Chrome 확장 sidepanel | body 파싱 오류 | 헤더 폴백으로 마스킹 |

**교훈**:

1. **공통 응답 포맷이 있다면 명시적 타입/스키마로 강제해야 한다.** 서버에서 바꾸면 모든 클라이언트를 같이 업데이트해야 하는데, 구두 약속만 있으면 어디선가 반드시 어긋난다.

2. **폴백이 버그를 숨긴다.** header fallback 덕분에 동작하는 것처럼 보였지만, 그게 없었으면 훨씬 빨리 발견했을 것이다.

3. **같은 로직을 여러 파일에 복사하면 버그도 같이 복사된다.** 3개 파일에 각자 토큰 갱신 로직을 구현한 것 자체가 문제였다.

4. **표준 라이브러리를 써라.** JSON을 `split(',')` 으로 파싱하는 코드는 동작하는 척만 한다.
