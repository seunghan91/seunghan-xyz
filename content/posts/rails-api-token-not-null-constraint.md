---
title: "Rails API 토큰 생성: NOT NULL 컬럼 누락으로 발생하는 오류"
date: 2025-06-22
draft: true
tags: ["Rails", "API", "Authentication", "디버깅"]
description: "Rails에서 API 토큰을 직접 create!로 생성할 때 NOT NULL 컬럼이 누락되면 발생하는 오류와, Service 객체를 사용해야 하는 이유"
cover:
  image: "/images/og/rails-api-token-not-null-constraint.png"
  alt: "Rails Api Token Not Null Constraint"
  hidden: true
categories: ["Rails"]
---

Rails API 서버에서 소셜 로그인(SSO) 후 토큰을 발급하는 로직을 작성하다가 발생한 문제를 정리한다.

---

## 상황

Apple Sign In / Google Sign In 후 서버에서 access token과 refresh token을 발급해 클라이언트에 반환해야 한다. 모바일 앱이나 SPA에서 소셜 로그인을 구현할 때 흔히 겪는 흐름이다.

1. 클라이언트가 Apple/Google로부터 identity token(또는 authorization code)을 받아 서버에 전달한다.
2. 서버는 해당 토큰을 검증한 후 내부 사용자 레코드를 찾거나 생성한다.
3. 서버가 자체 access token과 refresh token을 발급해 클라이언트에 반환한다.
4. 이후 API 요청은 이 access token을 `Authorization: Bearer <token>` 헤더로 전달한다.

3번 단계, 즉 토큰을 직접 발급하는 부분에서 컨트롤러에 아래와 같이 작성했다.

```ruby
token = user.api_tokens.create!(
  token_type: "bearer",
  expires_at: 1.hour.from_now
)
```

간단해 보이는 코드지만 즉시 오류가 발생했다.

---

## 오류

```
ActiveRecord::NotNullViolation:
PG::NotNullViolation: ERROR: null value in column "token_digest"
violates not-null constraint
```

PostgreSQL이 NOT NULL 제약 조건 위반을 감지하고 INSERT 자체를 거부한 것이다. Rails의 `ActiveRecord::NotNullViolation`은 이 DB 레벨 오류를 래핑한 예외다.

추가로, 잠시 후 다른 시도에서는 이런 오류도 발생했다.

```
ActiveRecord::UnknownAttributeError:
unknown attribute 'token_type' for ApiToken.
```

두 오류 모두 같은 근본 원인에서 비롯된다. 테이블 스키마를 제대로 파악하지 않고 모델을 직접 다루려 했기 때문이다.

---

## 원인 분석

`api_tokens` 테이블의 실제 스키마를 확인해보니 아래 컬럼들이 `NOT NULL`로 정의되어 있었다.

```ruby
# db/schema.rb
create_table "api_tokens" do |t|
  t.string   "token_digest",         null: false  # SHA-256 해시값
  t.string   "refresh_token_digest", null: false  # refresh token 해시값
  t.datetime "refresh_expires_at",   null: false  # refresh 만료 시각
  t.string   "jti",                  null: false  # JWT ID (중복 방지)
  t.integer  "user_id",              null: false
  t.datetime "expires_at",           null: false
  t.datetime "created_at",           null: false
  t.datetime "updated_at",           null: false
end
```

`create!`에 넘긴 파라미터는 `token_type`과 `expires_at` 두 가지뿐이었다. 결과적으로 두 가지 문제가 동시에 터진 셈이다.

**문제 1: NOT NULL 컬럼에 값이 없음**

`token_digest`, `refresh_token_digest`, `refresh_expires_at`, `jti`는 모두 NOT NULL이지만 코드에서 아무런 값도 전달하지 않았다. ActiveRecord는 이 컬럼들을 `nil`로 남긴 채 INSERT를 시도하고, PostgreSQL이 제약 조건 위반으로 거부한다.

**문제 2: 존재하지 않는 컬럼을 지정함**

`token_type`은 스키마에 없는 컬럼이다. 다른 프레임워크나 라이브러리(예: Doorkeeper)의 컬럼명을 혼동한 결과였다. Rails는 이를 `UnknownAttributeError`로 알린다.

**더 근본적인 문제**

설령 스키마를 정확히 파악했다 하더라도 `create!`를 직접 쓰면 안 된다. `token_digest`에 저장할 값은 단순한 문자열이 아니라 "원본 토큰을 SHA-256으로 해시한 값"이다. 이 해시 계산 로직을 컨트롤러에서 매번 직접 작성하면 코드 중복, 보안 취약점, 유지보수 어려움이 생긴다.

---

## 디버깅 과정

이런 오류를 처음 마주쳤을 때의 디버깅 순서를 정리한다.

**1. 스키마 확인**

가장 먼저 할 일은 `db/schema.rb` 또는 해당 테이블의 마이그레이션 파일을 확인하는 것이다.

```bash
# schema.rb에서 테이블 정의 찾기
grep -A 20 'create_table "api_tokens"' db/schema.rb
```

NOT NULL 컬럼이 무엇인지, 어떤 컬럼이 실제로 존재하는지 파악한다.

**2. 기존 Service/Helper 코드 탐색**

`api_token`이나 `token` 키워드로 프로젝트 내 기존 코드를 검색한다.

```bash
grep -r "ApiToken" app/services/
grep -r "generate.*token\|token.*generate" app/
```

대부분의 Rails 프로젝트에서 토큰 발급처럼 복잡한 로직은 이미 Service 객체나 Model 클래스 메서드로 구현되어 있다.

**3. 오류 메시지 그대로 읽기**

`PG::NotNullViolation: ERROR: null value in column "token_digest"` 에서 `"token_digest"`가 문제 컬럼이다. 이 컬럼에 어떤 값이 들어가야 하는지를 스키마와 기존 코드에서 추적하면 해결 방향이 보인다.

---

## 해결: Service 객체 사용

토큰 생성 로직을 담은 `ApiTokenService`가 이미 구현되어 있었다. 컨트롤러에서 직접 모델을 다루지 않고 서비스를 통해야 한다.

```ruby
# 잘못된 방법
token = user.api_tokens.create!(token_type: "bearer", expires_at: 1.hour.from_now)

# 올바른 방법
token_pair = ApiTokenService.generate(user, request)

# 반환값 사용
render json: {
  access_token:  token_pair[:access_token],
  refresh_token: token_pair[:refresh_token],
  expires_at:    token_pair[:expires_at].iso8601
}
```

`ApiTokenService.generate`는 내부에서 아래 모든 작업을 처리한다.

- `SecureRandom.hex(32)` 등으로 원본 토큰 문자열 생성 (클라이언트에 전달)
- `Digest::SHA256.hexdigest(raw_token)`으로 해시 계산 후 `token_digest`에 저장
- refresh token도 동일한 방식으로 생성 및 해시 저장
- `SecureRandom.uuid`로 `jti` 생성 (JWT ID, 재사용 방지용)
- `expires_at`, `refresh_expires_at` 자동 설정

컨트롤러는 단지 서비스를 호출하고 결과를 JSON으로 렌더링하면 끝이다.

---

## 왜 DB에 원본 토큰을 저장하지 않나

토큰 원본을 DB에 그대로 저장하면 DB가 유출됐을 때 모든 사용자의 토큰이 그대로 노출된다. 공격자는 즉시 모든 계정에 접근할 수 있다.

SHA-256 해시를 저장하면:

- 클라이언트가 토큰을 전송하면 서버가 해시 후 DB와 비교한다.
- DB가 유출되더라도 해시값으로는 원본 토큰을 역산할 수 없다.
- 비밀번호 해싱과 동일한 원리다. 다만 비밀번호에는 bcrypt/argon2처럼 느린 해시가 적합하지만, API 토큰은 이미 충분한 엔트로피(256비트)를 가지므로 빠른 SHA-256으로도 안전하다.

```ruby
# 토큰 검증 시
def authenticate_token(raw_token)
  digest = Digest::SHA256.hexdigest(raw_token)
  ApiToken.find_by(token_digest: digest)
end
```

검증 흐름은 단순하다. 요청 헤더에서 `raw_token`을 꺼내 해시하고, 그 해시가 DB에 존재하는지 확인하면 된다. 원본 토큰은 서버 메모리에 잠깐 존재했다가 사라지고, DB에는 절대 저장되지 않는다.

---

## jti (JWT ID)는 왜 필요한가

`jti`는 토큰의 고유 식별자다. 주요 용도는 두 가지다.

**토큰 재사용 방지 (Replay Attack 방지)**

탈취된 refresh token이 재사용되는 것을 막을 수 있다. refresh token을 사용할 때 서버가 해당 `jti`를 무효화(blacklist)하면, 같은 refresh token을 두 번 사용할 수 없다.

**선택적 토큰 무효화**

특정 사용자의 특정 세션만 로그아웃시켜야 할 때, `jti`로 정확히 그 토큰만 삭제할 수 있다. "모든 기기에서 로그아웃" 기능도 해당 사용자의 모든 `api_tokens` 레코드를 삭제하면 구현된다.

---

## 예방: 유사한 오류를 피하는 패턴

이 오류는 스키마를 확인하지 않고 모델을 직접 다루는 습관에서 비롯된다. 몇 가지 패턴으로 예방할 수 있다.

**패턴 1: 복잡한 생성 로직은 항상 Service 객체 또는 클래스 메서드로 래핑**

```ruby
# Model 클래스 메서드 방식
class ApiToken < ApplicationRecord
  def self.generate_for(user, request)
    raw_token = SecureRandom.hex(32)
    create!(
      user: user,
      token_digest: Digest::SHA256.hexdigest(raw_token),
      jti: SecureRandom.uuid,
      expires_at: 1.hour.from_now,
      refresh_token_digest: Digest::SHA256.hexdigest(SecureRandom.hex(32)),
      refresh_expires_at: 30.days.from_now
    )
  end
end
```

**패턴 2: 마이그레이션에 `null: false` 컬럼을 추가할 때는 반드시 default 값 또는 before_validation 콜백 설정**

NOT NULL 컬럼이 자동 생성되는 값이라면 모델 레벨에서 보완할 수 있다.

```ruby
class ApiToken < ApplicationRecord
  before_validation :set_jti, on: :create

  private

  def set_jti
    self.jti ||= SecureRandom.uuid
  end
end
```

이렇게 하면 `create!` 시 `jti`를 빠뜨려도 모델이 자동으로 채워준다. 다만 보안상 민감한 토큰 해시는 컨트롤러나 콜백에 분산하지 않고 Service 객체에 집중시키는 편이 낫다.

**패턴 3: 새 모델을 다루기 전에 항상 스키마 확인**

```bash
rails db:schema:dump  # 최신 schema.rb 유지
grep -A 30 'create_table "api_tokens"' db/schema.rb
```

---

## 결론

Rails에서 복잡한 생성 로직이 필요한 모델은 Service 객체나 Model 클래스 메서드로 래핑해서 사용하는 것이 안전하다. 컨트롤러에서 `create!`를 직접 호출하다 보면 필수 컬럼 누락, 비즈니스 로직 우회, 보안 처리 누락 같은 문제가 생긴다.

이번 사례에서 얻은 교훈은 단순하다. 새로운 모델을 다루기 전에 반드시 스키마를 확인하고, 기존에 구현된 Service나 헬퍼 메서드가 있는지 먼저 찾아봐야 한다. 대부분의 Rails 프로젝트는 복잡한 도메인 로직을 이미 어딘가에 캡슐화해두고 있다.

다른 컨트롤러에서 동일한 토큰 발급이 필요할 때도 Service를 재사용하면 일관성이 보장되고, 추후 토큰 만료 정책이나 해시 알고리즘을 변경할 때도 한 곳만 수정하면 된다.

---

## Key Takeaways

- `ActiveRecord::NotNullViolation`은 DB의 NOT NULL 제약 조건을 위반할 때 발생한다. 오류 메시지에 나온 컬럼명을 `db/schema.rb`에서 추적하면 원인을 빠르게 파악할 수 있다.
- `ActiveRecord::UnknownAttributeError`는 스키마에 없는 컬럼명을 `create!`에 넘길 때 발생한다. 다른 프레임워크 컬럼명과 혼동하기 쉬우므로 항상 스키마를 먼저 확인한다.
- 토큰처럼 복잡한 생성 로직(해시 계산, 여러 컬럼 동시 설정)은 Service 객체 또는 Model 클래스 메서드로 캡슐화한다. 컨트롤러는 서비스를 호출하고 결과를 렌더링하는 역할만 담당한다.
- DB에는 원본 토큰이 아닌 SHA-256 해시를 저장한다. DB 유출 시에도 원본 토큰을 역산할 수 없어 보안이 강화된다.
- `jti`(JWT ID)는 토큰의 고유 식별자로, 재사용 방지와 선택적 무효화에 사용된다.
- 새 모델을 다루기 전에 스키마를 확인하고, 기존에 구현된 Service가 있는지 먼저 검색하는 습관이 이런 오류를 예방한다.
