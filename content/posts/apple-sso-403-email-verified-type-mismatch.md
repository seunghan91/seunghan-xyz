---
title: "Apple Sign-In 403 에러: email_verified 타입 불일치와 복붙 버그 3종 세트"
date: 2026-02-27
draft: false
tags: ["Rails", "Apple Sign-In", "OAuth", "JWT", "디버깅", "Flutter"]
description: "Apple SSO 로그인이 403으로 실패하는데 Google은 정상인 경우, JWT의 email_verified 타입 차이와 코드 복붙에서 발생한 버그 3가지를 정리한다."
---

Apple Sign-In이 403 Forbidden으로 실패하는데, Google Sign-In은 정상 동작하는 상황이었다. 동일한 스택(Rails 8 + Flutter)의 다른 프로젝트에서는 Apple 로그인이 잘 되고 있어서 비교 분석했다.

---

## 증상

- Apple 로그인: **403 Forbidden**
- Google 로그인: 정상 성공
- 에러 메시지: `"Email not verified by Apple"`

---

## 원인 1: email_verified 타입 불일치 (핵심)

Apple과 Google은 JWT에서 `email_verified` 필드를 **다른 타입**으로 반환한다.

| Provider | email_verified 타입 | 값 예시 |
|----------|---------------------|---------|
| Google   | **boolean**         | `true`  |
| Apple    | **string 또는 boolean** | `"true"` 또는 `true` |

문제의 코드:

```ruby
# Apple Auth Service
{
  uid: decoded_token["sub"],
  email: decoded_token["email"],
  email_verified: decoded_token["email_verified"] == "true"  # string 비교
}
```

Apple이 boolean `true`를 반환하면:
- `true == "true"` → **`false`** (Ruby에서 boolean과 string 비교)
- → email_verified가 false로 설정됨
- → 컨트롤러에서 403 반환

Google은 항상 boolean `true`를 반환하지만, Google Auth Service에서는 직접 값을 사용했기 때문에 문제없었다:

```ruby
# Google Auth Service
email_verified: decoded_token["email_verified"]  # boolean 그대로 사용 → true
```

### 수정

```ruby
# AS-IS
email_verified: decoded_token["email_verified"] == "true"

# TO-BE: boolean과 string 모두 처리
email_verified: [true, "true"].include?(decoded_token["email_verified"])
```

---

## 원인 2: 불필요한 email_verified 강제 검증

SSO 컨트롤러에서 Apple 로그인 시 email_verified를 강제 체크하고 있었다:

```ruby
def apple
  user_info = AppleAuthService.verify_identity_token(identity_token)

  # 이 체크가 403을 반환
  unless user_info[:email_verified]
    return render_forbidden("Email not verified by Apple")
  end
  # ...
end
```

Apple Sign-In은 Apple 계정 자체가 이메일 인증을 보장하므로, 이 체크는 불필요하다. 실제로 동일 스택의 다른 프로젝트에서는 이 체크가 없었고 정상 동작 중이었다.

### 수정

Apple 쪽 email_verified 검증 블록 삭제. Google은 그대로 유지.

---

## 원인 3: 메서드명 오타 (숨겨진 버그)

User 생성 실패 시 호출하는 에러 렌더링 메서드에 오타가 있었다:

```ruby
# SSO Controller
if user.persisted?
  # 성공 처리...
else
  render_validation_error(user)   # 단수형 - 존재하지 않는 메서드!
end
```

실제 정의된 메서드:

```ruby
# ApiResponse concern
def render_validation_errors(record)  # 복수형 - 실제 메서드
  # ...
end
```

이 버그는 Google 로그인에서도 동일하게 존재했지만, Google은 User 생성이 항상 성공해서 else 분기를 타지 않았기 때문에 발견되지 않았다.

### 수정

```ruby
# AS-IS
render_validation_error(user)

# TO-BE
render_validation_errors(user)
```

---

## 왜 이런 버그가 생겼나

**Google SSO를 먼저 구현하고, 그 코드를 복붙해서 Apple SSO를 만들었기 때문.**

```
Google SSO (원본)                     Apple SSO (복붙)
───────────────────                   ──────────────────
email_verified: boolean true     →   email_verified: string/boolean 혼용
email 항상 포함                   →   email 누락 가능 (Private Relay)
render_validation_error (오타)   →   render_validation_error (오타 그대로 복사)
```

- Google은 타입이 일관적이라 string 비교가 문제 안 됨
- Google은 User 생성이 항상 성공해서 메서드 오타가 노출 안 됨
- Apple은 둘 다 터짐

---

## 다른 프로젝트는 왜 괜찮았나

동일 스택의 다른 프로젝트는 **Firebase Authentication**을 사용하고 있었다.

| 방식 | Apple JWT 직접 검증 | Firebase 토큰 검증 |
|------|---------------------|-------------------|
| email_verified 처리 | 직접 타입 변환 필요 | Firebase SDK가 정규화 |
| 검증 로직 | 직접 구현 (RS256, public key) | `verify_firebase_token` 한 줄 |
| 버그 가능성 | 높음 (타입, 필드 누락 등) | 낮음 (SDK가 처리) |

Firebase를 쓰면 email_verified 타입 차이를 신경 쓸 필요가 없다. 하지만 직접 JWT를 검증하는 경우에는 **Apple과 Google의 JWT 스펙 차이**를 반드시 확인해야 한다.

---

## 교훈

1. **Provider별 JWT 스펙을 확인하라** — Apple과 Google은 같은 필드도 타입이 다를 수 있다
2. **복붙 후 반드시 Provider별 차이를 검증하라** — 특히 email_verified, email 존재 여부, 첫 로그인 동작
3. **에러 경로도 테스트하라** — 정상 경로만 테스트하면 else 분기의 오타를 못 잡는다
4. **성공하는 Provider가 있으면 비교 분석하라** — Google은 되고 Apple은 안 되면, 차이점에 답이 있다

---

## Apple vs Google JWT 차이 요약

| 필드 | Apple | Google |
|------|-------|--------|
| `email_verified` | string `"true"` 또는 boolean `true` | boolean `true` |
| `email` | 첫 로그인에만 제공, Private Relay 가능 | 항상 제공 |
| `name` | 첫 로그인에만 제공 | 항상 제공 |
| 서명 알고리즘 | RS256 | RS256 |
| Public Key URL | `appleid.apple.com/auth/keys` | `googleapis.com/oauth2/v3/certs` |
