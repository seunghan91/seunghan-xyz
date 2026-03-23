---
title: "Apple Sign-In 403 에러: email_verified 타입 불일치와 복붙 버그 3종 세트"
date: 2025-10-25
draft: false
tags: ["Rails", "Apple Sign-In", "OAuth", "JWT", "디버깅", "Flutter"]
description: "Apple SSO 로그인이 403으로 실패하는데 Google은 정상인 경우, JWT의 email_verified 타입 차이와 코드 복붙에서 발생한 버그 3가지를 정리한다."
cover:
  image: "/images/og/apple-sso-403-email-verified-type-mismatch.png"
  alt: "Apple Sso 403 Email Verified Type Mismatch"
  hidden: true
---

Apple Sign-In이 403 Forbidden으로 실패하는데, Google Sign-In은 정상 동작하는 상황이었다. 동일한 스택(Rails 8 + Flutter)의 다른 프로젝트에서는 Apple 로그인이 잘 되고 있어서 비교 분석했다.

결론부터 말하면, 세 가지 독립적인 버그가 동시에 존재했고, 모두 "Google SSO 코드를 복붙해서 Apple SSO를 만든" 과정에서 생겨났다.

---

## 증상

- Apple 로그인: **403 Forbidden**
- Google 로그인: 정상 성공
- 에러 메시지: `"Email not verified by Apple"`
- 개발 환경에서는 재현되지 않고 프로덕션에서만 발생 (Apple 테스트 계정 이슈)

---

## 배경: Apple과 Google JWT는 다르다

OAuth 2.0 / OIDC 표준은 `email_verified` 필드가 boolean이어야 한다고 명시하고 있다. 하지만 현실에서 Apple은 이 필드를 **문자열 `"true"`로 반환하는 경우가 있다**. 이건 Apple의 공식 문서에도 명확히 나와 있지 않은 엣지 케이스다.

Apple ID JWT를 직접 디코딩해보면:

```json
// Apple이 반환하는 JWT payload 예시 1 (boolean)
{
  "iss": "https://appleid.apple.com",
  "sub": "000123.abcdef...",
  "email": "user@privaterelay.appleid.com",
  "email_verified": true
}

// Apple이 반환하는 JWT payload 예시 2 (string - 이게 문제)
{
  "iss": "https://appleid.apple.com",
  "sub": "000123.abcdef...",
  "email": "user@privaterelay.appleid.com",
  "email_verified": "true"
}
```

Google은 항상 boolean을 반환한다. 이 차이가 첫 번째 버그의 원인이다.

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
- `true == "true"` → **`false`** (Ruby에서 boolean과 string 비교는 항상 false)
- → email_verified가 false로 설정됨
- → 컨트롤러에서 403 반환

Google은 항상 boolean `true`를 반환하지만, Google Auth Service에서는 직접 값을 사용했기 때문에 문제없었다:

```ruby
# Google Auth Service
email_verified: decoded_token["email_verified"]  # boolean 그대로 사용 → true
```

Ruby에서 `==` 비교는 타입을 엄격하게 구분한다. `true == "true"`는 `false`다. JavaScript와 달리 암묵적 형변환이 없다.

### 수정

```ruby
# AS-IS
email_verified: decoded_token["email_verified"] == "true"

# TO-BE: boolean과 string 모두 처리
email_verified: [true, "true"].include?(decoded_token["email_verified"])
```

`Array#include?`를 사용하면 `true`(boolean)든 `"true"`(string)든 둘 다 `true`로 평가된다. Apple이 어떤 타입으로 반환하더라도 안전하게 처리된다.

더 방어적으로 작성하려면 이렇게도 할 수 있다:

```ruby
# 더 명시적인 방어 코드
email_verified: decoded_token["email_verified"].to_s == "true"
```

`to_s`를 먼저 호출하면 boolean이든 string이든 일관되게 문자열로 변환한 뒤 비교한다. 단, `nil`인 경우 `""`가 되어 `false`로 평가되므로 `nil` 처리도 자동으로 된다.

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

이 코드는 Google SSO 코드를 복붙하면서 그대로 가져온 것이다. Google의 경우 email_verified 체크가 의미 있을 수 있다. 하지만 **Apple Sign-In은 이미 Apple 계정 자체에서 이메일 인증을 보장**한다.

Apple Developer 문서에 따르면:
- Apple Sign-In으로 로그인하는 사용자는 반드시 Apple ID를 가지고 있어야 한다
- Apple ID 생성 시 이메일 인증이 필수다
- 따라서 Apple Sign-In을 통해 오는 사용자의 이메일은 이미 검증된 상태다

즉, `email_verified`가 `false`인 Apple 사용자는 정상적인 Apple Sign-In 플로우에서는 존재하지 않는다. 이 체크 자체가 방어 논리로서 가치가 없고, 오히려 타입 버그와 맞물려 정상 사용자를 403으로 차단하는 역할을 했다.

### 수정

Apple 쪽 email_verified 검증 블록 삭제. Google은 그대로 유지.

```ruby
def apple
  user_info = AppleAuthService.verify_identity_token(identity_token)

  # email_verified 체크 제거 - Apple Sign-In은 이미 이메일 인증 보장
  # ...
end
```

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

만약 이 코드가 실행됐다면 `NoMethodError`가 발생했을 것이다. Rails API 서버에서 처리되지 않은 예외는 500으로 떨어지지만, 이 경우 실제로는 원인 1, 2에 의해 이미 403이 반환된 상황이어서 이 코드까지 도달하지 않았다.

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

Google은 타입이 일관적이라 string 비교가 문제 안 됐다. Google은 User 생성이 항상 성공해서 메서드 오타가 노출되지 않았다. Apple은 둘 다 터졌다.

복붙 기반 개발의 위험은 **원본 코드의 버그와 원본 코드가 가정하는 동작 방식이 그대로 전파된다**는 것이다. 원본이 잘 동작한다는 사실이 오히려 복붙 결과물의 버그를 숨긴다.

---

## Apple Private Relay 이슈: email도 주의가 필요하다

이번 디버깅 과정에서 `email_verified` 외에 `email` 필드도 주의해야 한다는 것을 재확인했다.

Apple Sign-In에는 **Private Relay** 기능이 있다. 사용자가 앱에 실제 이메일을 공유하지 않기로 선택하면, Apple은 `@privaterelay.appleid.com` 도메인의 익명 이메일을 제공한다. 그리고 **이 이메일은 최초 로그인 시에만 JWT에 포함된다**.

```
첫 로그인: email = "abc123@privaterelay.appleid.com"  ← JWT에 포함
재로그인:  email = nil  ← JWT에 없음!
```

Google은 항상 실제 이메일을 반환한다. 복붙 코드에서 email이 nil인 경우를 처리하지 않으면 DB 제약 조건 위반(NOT NULL)이 발생하거나 예상치 못한 동작이 생긴다.

```ruby
# Apple Auth Service - email nil 처리 필요
{
  uid: decoded_token["sub"],
  email: decoded_token["email"],  # nil일 수 있음!
  email_verified: [true, "true"].include?(decoded_token["email_verified"])
}
```

`sub` 필드는 항상 존재하므로, Apple 사용자는 `sub`를 기본 식별자로 사용하고 email은 보조 수단으로 취급해야 한다.

---

## 다른 프로젝트는 왜 괜찮았나

동일 스택의 다른 프로젝트는 **Firebase Authentication**을 사용하고 있었다.

| 방식 | Apple JWT 직접 검증 | Firebase 토큰 검증 |
|------|---------------------|-------------------|
| email_verified 처리 | 직접 타입 변환 필요 | Firebase SDK가 정규화 |
| 검증 로직 | 직접 구현 (RS256, public key) | `verify_firebase_token` 한 줄 |
| Public Key 관리 | Apple JWKS 직접 호출 | Firebase SDK가 처리 |
| 버그 가능성 | 높음 (타입, 필드 누락 등) | 낮음 (SDK가 처리) |

Firebase를 쓰면 email_verified 타입 차이를 신경 쓸 필요가 없다. Firebase Authentication은 Apple, Google, Facebook 등 여러 Provider의 JWT 차이를 내부적으로 정규화해서 일관된 인터페이스를 제공한다.

하지만 직접 JWT를 검증하는 방식을 선택한 경우에는 **Apple과 Google의 JWT 스펙 차이**를 반드시 확인해야 한다.

---

## Apple JWT 직접 검증 시 체크리스트

Apple Sign-In JWT를 직접 검증하는 경우 반드시 확인해야 할 항목들:

1. **`email_verified` 타입**: boolean `true`와 string `"true"` 모두 처리
2. **`email` 누락**: `sub`를 기본 식별자로, `email`은 nil 가능성 고려
3. **`name` 누락**: 첫 로그인에만 포함, 이후 nil
4. **Public Key 캐싱**: `https://appleid.apple.com/auth/keys` 응답은 캐싱 권장 (만료 주기 확인)
5. **`iss` 검증**: `https://appleid.apple.com`인지 확인
6. **`aud` 검증**: 자신의 Bundle ID / Client ID인지 확인
7. **`exp` 검증**: 토큰 만료 여부 확인

---

## Apple vs Google JWT 차이 요약

| 필드 | Apple | Google |
|------|-------|--------|
| `email_verified` | string `"true"` 또는 boolean `true` | boolean `true` |
| `email` | 첫 로그인에만 제공, Private Relay 가능 | 항상 제공 |
| `name` | 첫 로그인에만 제공 | 항상 제공 |
| 서명 알고리즘 | RS256 | RS256 |
| Public Key URL | `appleid.apple.com/auth/keys` | `googleapis.com/oauth2/v3/certs` |
| `sub` 형식 | `000123.abc...` (점 포함) | 숫자 문자열 |
| 토큰 유효기간 | 10분 | 1시간 |

---

## Key Takeaways

- **Apple JWT의 `email_verified`는 boolean과 string 두 가지 타입이 모두 올 수 있다.** `== "true"` 단순 비교는 boolean `true`를 false로 평가한다. `[true, "true"].include?()` 또는 `.to_s == "true"` 패턴을 사용해야 한다.
- **Apple Sign-In은 이메일 인증을 자체적으로 보장한다.** 컨트롤러에서 `email_verified` 재검증은 불필요하고, 타입 버그와 결합하면 정상 사용자를 차단한다.
- **복붙 기반 Provider 구현은 원본의 가정을 그대로 이어받는다.** Google 코드의 숨겨진 오타, Google 전용 타입 처리 방식이 Apple 코드에 그대로 전파된다.
- **에러 경로는 별도로 테스트해야 한다.** 정상 경로만 테스트하면 else 분기의 버그는 프로덕션에서 처음 드러난다.
- **한 Provider가 성공하고 다른 Provider가 실패하면, 차이점에 답이 있다.** Provider별 JWT 스펙을 나란히 비교하는 것이 디버깅의 출발점이다.
- **Firebase를 쓰면 이 문제가 없다.** 직접 JWT 검증을 선택했다면 Provider별 스펙 차이를 직접 처리해야 한다는 비용이 따른다.
