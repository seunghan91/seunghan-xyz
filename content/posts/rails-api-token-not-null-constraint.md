---
title: "Rails API 토큰 생성: NOT NULL 컬럼 누락으로 발생하는 오류"
date: 2026-02-24
draft: false
tags: ["Rails", "API", "Authentication", "디버깅"]
description: "Rails에서 API 토큰을 직접 create!로 생성할 때 NOT NULL 컬럼이 누락되면 발생하는 오류와, Service 객체를 사용해야 하는 이유"
---

Rails API 서버에서 소셜 로그인(SSO) 후 토큰을 발급하는 로직을 작성하다가 발생한 문제를 정리한다.

---

## 상황

Apple Sign In / Google Sign In 후 서버에서 access token과 refresh token을 발급해 클라이언트에 반환해야 한다. 컨트롤러에서 아래와 같이 직접 생성을 시도했다.

```ruby
token = user.api_tokens.create!(
  token_type: "bearer",
  expires_at: 1.hour.from_now
)
```

---

## 오류

```
ActiveRecord::NotNullViolation:
PG::NotNullViolation: ERROR: null value in column "token_digest"
violates not-null constraint
```

---

## 원인

`api_tokens` 테이블의 실제 스키마를 확인해보니 아래 컬럼들이 `NOT NULL`로 정의되어 있었다.

```ruby
# db/schema.rb
create_table "api_tokens" do |t|
  t.string   "token_digest",         null: false  # SHA-256 해시값
  t.string   "refresh_token_digest", null: false  # refresh token 해시값
  t.datetime "refresh_expires_at",   null: false  # refresh 만료 시각
  t.string   "jti",                  null: false  # JWT ID (중복 방지)
  # ...
end
```

직접 `create!`를 호출하면 이 컬럼들에 값이 자동으로 채워지지 않는다.

또한 `token_type`이라는 컬럼이 스키마에 존재하지 않아 `unknown attribute 'token_type'` 오류도 발생했다.

---

## 해결: Service 객체 사용

토큰 생성 로직을 담은 Service 객체(`ApiTokenService`)가 이미 구현되어 있었다. 컨트롤러에서 직접 모델을 다루지 않고 서비스를 통해야 한다.

```ruby
# 잘못된 방법
token = user.api_tokens.create!(token_type: "bearer", ...)

# 올바른 방법
token_pair = ApiTokenService.generate(user, request)

# 반환값 사용
render json: {
  access_token:  token_pair[:access_token],
  refresh_token: token_pair[:refresh_token],
  expires_at:    token_pair[:expires_at].iso8601
}
```

`ApiTokenService.generate`는 내부에서:
- 원본 토큰 문자열 생성 (클라이언트에 전달)
- SHA-256 해시 계산 후 `token_digest`에 저장 (DB에는 해시값만 저장)
- refresh token도 동일한 방식으로 처리
- `jti`, `expires_at`, `refresh_expires_at` 등 필수 컬럼 자동 설정

를 모두 처리한다.

---

## 왜 DB에 원본 토큰을 저장하지 않나

토큰 원본을 DB에 그대로 저장하면 DB가 유출됐을 때 모든 사용자의 토큰이 노출된다.

SHA-256 해시를 저장하면:
- 클라이언트가 토큰을 전송하면 서버가 해시 후 DB와 비교
- DB 유출 시 해시값으로는 원본 토큰을 역산할 수 없음
- 비밀번호 해싱과 동일한 원리 (다만 bcrypt 대신 SHA-256 사용)

```ruby
# 검증 시
digest = Digest::SHA256.hexdigest(raw_token)
token = ApiToken.find_by(token_digest: digest)
```

---

## 결론

Rails에서 복잡한 생성 로직(해시 계산, 여러 컬럼 동시 설정 등)이 필요한 모델은 Service 객체나 Model의 클래스 메서드로 래핑해서 사용하는 것이 안전하다. 컨트롤러에서 `create!`를 직접 호출하다 보면 필수 컬럼 누락이나 비즈니스 로직 우회 같은 문제가 생긴다.

다른 컨트롤러에서 동일한 토큰 발급이 필요할 때도 Service를 재사용하면 일관성이 보장된다.
