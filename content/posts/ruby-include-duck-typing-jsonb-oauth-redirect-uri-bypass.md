---
title: "Ruby `.include?` 가 보안 hole 을 우연히 닫은 사건 — duck typing 과 jsonb `||` 의 합작"
date: 2026-05-16T09:00:00+09:00
draft: false
tags: ["ruby", "rails", "postgresql", "oauth", "security"]
description: "Rails OAuth IdP 의 redirect_uri 검증에서 String#include? 와 Array#include? 의 dispatch 차이로 보안 hole 이 우연히 만들어졌다가 jsonb `||` 한 줄로 또 우연히 닫힌 사고. 3층 방어로 invariant 화한 과정."
---

OAuth 인증 서버를 직접 운영하면 어느 시점 한 번은 `redirect_uri` 검증을 손볼 일이 생긴다. 이번에 그 코드를 다시 들여다보다가 같은 줄이 데이터 형태에 따라 두 가지 완전히 다른 의미로 작동하고 있었다는 걸 발견했다. 한 줄짜리 SQL UPDATE 가 그 사이에 의도치 않게 보안 hole 을 만들었다가 다른 한 줄짜리 SQL UPDATE 가 또 의도치 않게 그 hole 을 닫았는데, 동시에 정상 OAuth 흐름도 깨버렸다. 결과적으로 같은 코드 한 줄이 시간에 따라 substring 매칭이었다가 element-wise 매칭으로 dispatch 가 바뀌었다.

이게 어떻게 가능한지, 그리고 같은 함정을 다시 안 만들기 위해 어떻게 invariant 를 박았는지 정리해본다. Ruby duck typing 의 익숙한 패턴이 어떻게 보안 surface 로 바뀌는지가 핵심.

---

## 문제의 코드

`OauthApplication` 모델에 다음 메서드가 있었다.

```ruby
def redirect_uri_allowed?(candidate)
  return false if candidate.blank?
  return false unless redirect_uris.include?(candidate)
  return sandbox_redirect_uri?(candidate) if tier_sandbox?
  true
end
```

`redirect_uris` 컬럼은 Postgres jsonb 타입.

```ruby
t.jsonb "redirect_uris", default: [], null: false
```

ActiveRecord 가 jsonb 컬럼을 deserialize 하면 보통 Ruby Array 가 돼서 `Array#include?` 가 element-wise 매칭으로 동작한다. 등록된 callback URL 과 들어온 후보 URL 이 정확히 같아야 통과. 이게 RFC 9700 가 명시하는 "MUST utilize exact string matching" 요구사항을 만족하는 방식이다.

문제는 jsonb 컬럼이 항상 Array 로 deserialize 되는 건 아니라는 거다. **jsonb 는 scalar string, scalar number, boolean, null 도 담을 수 있는 컨테이너**라서 그 컬럼의 값이 `'"foo"'::jsonb` (jsonb string scalar) 이면 ActiveRecord 는 그걸 Ruby `String` 으로 deserialize 한다.

그리고 Ruby 에서 `String#include?` 는 element-wise 매칭이 아니라 **substring 매칭**이다.

```ruby
"hello".include?("ell")  # => true (부분 문자열 매칭)
["hello"].include?("ell") # => false (정확 일치 아님)
```

같은 메서드 이름, 같은 시그니처, 완전히 다른 의미. 이게 Ruby duck typing 의 본질이다 — receiver 의 클래스에 따라 다른 메서드가 호출된다. solnic.dev 가 [duck typing 과 type safety](https://solnic.dev/duck-typing-vs-type-safety-in-ruby/) 에 대해 쓴 글에서 정확히 이 위험을 지적했다.

> "Most bugs are caused by unexpected or invalid values that are leaking into places of your system where it doesn't know how to handle them properly."

`redirect_uris.include?(candidate)` 라는 한 줄 코드는 `redirect_uris` 가 Array 라는 전제 위에서만 의도대로 작동한다. 전제가 깨지는 순간 같은 코드가 다른 의미를 가진다.

---

## Stage 1 — substring 매칭으로 우연히 작동하던 시기

데이터베이스에 있는 `redirect_uris` 값이 다음 형태였다.

```
"[\"https://idp.example.com/callback\",\"https://idp.example.com/widget.html\"]"
```

따옴표 패턴을 잘 보면 이게 **jsonb array 가 아니라 jsonb scalar string** 이다. 그 string 의 내용이 우연히 JSON-encoded array literal 처럼 생긴 거지, jsonb 입장에서는 그냥 한 덩어리 string. `jsonb_typeof()` 로 찍어보면 `string` 이 나온다.

ActiveRecord 가 deserialize 하면:

```ruby
app.redirect_uris.class
# => String
app.redirect_uris
# => "[\"https://idp.example.com/callback\",\"https://idp.example.com/widget.html\"]"
```

이 상태에서 OAuth authorize 흐름이 `redirect_uri=https://idp.example.com/callback` 으로 들어오면:

```ruby
redirect_uris.include?("https://idp.example.com/callback")
# => true (substring 매칭)
```

**우연히 통과**한다. 등록된 blob string 안에 후보 URL 이 부분 문자열로 들어있으니까. OAuth 가 작동하니 아무도 데이터 형태를 의심 안 한다.

하지만 이게 보안 hole 이다. 다음도 통과한다.

```ruby
redirect_uris.include?("https://idp.example.com/cal")     # → true
redirect_uris.include?("\\\",\\\"https://idp.example.com") # → true
redirect_uris.include?(",")                                # → true
```

빈 문자열에 가까운 짧은 substring 만 등록된 blob 안에 우연히 들어있으면 다 매칭이다. RFC 9700 가 명시하는 exact string match 가 깨진 상태. ACSAC 2023 논문 ["OAuth 2.0 Redirect URI Validation Falls Short, Literally"](https://dl.acm.org/doi/fullHtml/10.1145/3627106.3627140) 가 16개 메이저 IdP 중 6개 (Atlassian, Facebook, GitHub, Microsoft, NAVER, VK 포함) 에서 path confusion 으로 비슷한 부분 매칭 결함을 실증했다. 이걸 우리도 한 RP 에서 무의식적으로 재현하고 있었다.

이 corruption 이 어디서 들어왔는지는 git history 로 추정 가능했다. 이전에 누군가 raw SQL 마이그레이션에서 jsonb 컬럼을 만지면서 이런 패턴을 썼다.

```ruby
current = JSON.parse(app["redirect_uris"].to_s.presence || "[]") rescue []
```

`exec_query` 가 jsonb 를 이미 deserialize 한 Ruby Array 를 반환하는데, 거기에 `.to_s` 를 하면 `'["a", "b"]'` 라는 문자열이 되고, `JSON.parse` 가 다시 array 로 되돌리는 둥글둥글한 패턴이다. 이 자체는 잘못 동작하면서 통과하는 코드인데, 어떤 경로에선가 이게 jsonb 컬럼에 **Array 가 아니라 그 array 의 to_s 결과 (string)** 를 박아넣는 일이 일어났다. 이후 그 string 이 deserialize 와 substring 매칭으로 운 좋게 작동하면서 아무도 알아채지 못했다.

---

## Stage 2 — jsonb `||` 한 줄이 모든 걸 바꿔놓은 순간

새 URL 하나를 `redirect_uris` 에 추가하려고 단순한 raw SQL 을 돌렸다.

```sql
UPDATE oauth_applications
SET    redirect_uris = redirect_uris || '["https://idp.example.com/logout-target"]'::jsonb
WHERE  name = 'some-rp';
```

의도: 기존 redirect_uris 목록 끝에 URL 한 줄 append. 보통 jsonb `||` 가 array 두 개 concat 하는 동작.

[Postgres 공식 문서](https://www.postgresql.org/docs/current/functions-json.html) 의 `||` operator 설명을 자세히 보면 다음 문장이 있다.

> "All other cases are treated by converting a non-array input into a single-element array, and then proceeding as for two arrays."

즉 `scalar || array` 가 들어오면 Postgres 는 **scalar 를 single-element array 로 wrap 한 다음** concat 한다.

이게 무슨 의미인지 docs 의 예제로 보면:

```
'{"a": "b"}'::jsonb || '42'::jsonb  →  [{"a": "b"}, 42]
```

object 와 scalar 가 들어왔는데 array `[object, scalar]` 가 나온다. 우리 케이스도 정확히 이거다.

```
before: '"[\"a\",\"b\"]"'::jsonb           ← jsonb string scalar
        || '["new-url"]'::jsonb            ← jsonb array

after:  ['"[\"a\",\"b\"]"', 'new-url']     ← jsonb array of two strings
```

UPDATE 한 줄로 `redirect_uris` 의 jsonb 타입이 string 에서 array 로 바뀌었다. 그리고 array 의 element 0 자리에는 원래 그 string scalar 값이 통째로 들어갔다.

ActiveRecord 가 이제 deserialize 하면 Ruby `Array` 다. 그러므로 `.include?` 도 `Array#include?` 로 dispatch 가 바뀐다.

```ruby
app.redirect_uris.class
# => Array
app.redirect_uris
# => [
#      "[\"https://idp.example.com/callback\",\"https://idp.example.com/widget.html\"]",
#      "https://idp.example.com/logout-target"
#    ]

app.redirect_uris.include?("https://idp.example.com/callback")
# => false  (element-wise 매칭이라 element 0 의 nested string 과는 같지 않음)

app.redirect_uris.include?("https://idp.example.com/logout-target")
# => true  (element 1 과 정확히 일치)
```

여기서 두 가지가 동시에 일어났다.

1. **부작용으로 보안 hole 이 닫혔다.** substring 매칭이 element-wise 매칭으로 바뀌었으니 부분 일치하는 임의 URL 이 더 이상 통과 못 한다.
2. **부작용으로 정상 OAuth 도 깨졌다.** 등록된 callback URL `https://idp.example.com/callback` 도 element-wise 매칭에서 fail. element 0 의 nested string 안에 글자 그대로 들어있긴 하지만 jsonb array element 로는 따로 떨어져 있지 않으니까. authorize 흐름이 `invalid_request: redirect_uri not registered` 로 떨어지기 시작했다.

내가 한 일은 단순 URL 추가였다. 한 줄짜리 SQL. 그 결과로 같은 Ruby 코드의 dispatch 가 substring → element-wise 로 바뀌면서 trade-off 가 의도 밖에서 발생했다. 자물쇠를 바꾸려고 한 게 아니라 그냥 새 열쇠를 끼웠을 뿐인데 잠금 메커니즘 자체가 바뀐 셈이다.

---

## 정상화 — Stage C, flat array of plain URI strings

원하는 최종 상태는 분명하다. `redirect_uris` 는 항상 jsonb array of plain URI strings 여야 한다. 등록된 URL 들이 각각 별도 element 로 들어가 있어야 element-wise 매칭이 의도대로 동작한다.

데이터 정상화 자체는 마이그레이션 하나로 끝났다. 핵심은 raw SQL 이 아니라 **자기 자신을 검증하는 마이그레이션**이라는 점.

```ruby
class FixRedirectUrisCorruption < ActiveRecord::Migration[8.0]
  TARGET = [
    "https://idp.example.com/callback",
    "https://idp.example.com/widget.html",
    "https://idp.example.com/logout-target"
  ].freeze

  def up
    ActiveRecord::Base.transaction do
      row = ActiveRecord::Base.connection.exec_query(
        "SELECT id FROM oauth_applications WHERE name = $1 LIMIT 1 FOR UPDATE",
        "lock", [ ... ]
      ).first
      raise "row not found" if row.nil?

      target_json = ActiveRecord::Base.connection.quote(TARGET.to_json)
      rows_updated = ActiveRecord::Base.connection.exec_update(
        "UPDATE oauth_applications SET redirect_uris = #{target_json}::jsonb, updated_at = NOW() " \
        "WHERE id = $1 AND name = $2",
        "fix", [ ... ]
      )
      raise "expected 1 row, got #{rows_updated}" unless rows_updated == 1

      verified = ActiveRecord::Base.connection.exec_query(
        "SELECT redirect_uris FROM oauth_applications WHERE id = $1",
        "verify", [ ... ]
      ).first["redirect_uris"]
      raise "post-write check failed" unless verified.is_a?(Array) && verified == TARGET
    end
  end

  def down
    raise ActiveRecord::IrreversibleMigration,
          "rollback would re-arm the substring-match security hole"
  end
end
```

요점은 단순한 UPDATE 가 아니라 다음 4가지를 모두 단일 트랜잭션에서 한다는 것.

| 단계 | 이유 |
|---|---|
| `SELECT … FOR UPDATE` row lock | read / decide / write 사이에 다른 writer 가 끼어드는 걸 방지. concurrent admin UI save 와의 race 차단 |
| `WHERE id = ? AND name = ?` 이중 매칭 | 잘못된 row 를 만지지 않음 |
| `affected_rows == 1` assert | 의도한 row 정확히 하나만 변경됐는지 |
| 사후 reselect + 값 비교 | 트리거나 cast 가 값을 비틀지 않았는지 |

그리고 `down` 은 `IrreversibleMigration` 으로 막아놨다. 데이터 repair 는 forward-only 다 — 롤백하면 보안 hole 을 다시 열어주는 셈이니까.

---

## 같은 함정이 다시 안 들어오게 — 3층 방어

데이터 정상화만 하면 즉시 위험은 사라지지만 같은 corruption 이 다시 들어올 통로가 셋이나 있다.

1. **raw-SQL 마이그레이션** — model 검증을 우회해서 jsonb scalar string 을 박을 수 있음
2. **ActiveRecord 쓰기** — validator 가 escape hatch 가 있으면 비 Array 값도 통과
3. **in-memory 객체** — 테스트 mock 이나 mid-flight assignment 가 String 을 박으면 메서드 dispatch 가 또 substring 매칭

각각의 통로를 따로 막아야 한다.

### Layer 1 — Postgres CHECK constraint

raw-SQL 까지 차단하려면 데이터베이스 차원에서 막아야 한다.

```sql
ALTER TABLE oauth_applications
ADD CONSTRAINT oauth_applications_redirect_uris_shape
CHECK (
  jsonb_typeof(redirect_uris) = 'array'
  AND NOT jsonb_path_exists(
    redirect_uris,
    '$[*] ? (@.type() != "string"
             || @ like_regex "^\s*[\[\{]"
             || !(@ like_regex "^[A-Za-z][A-Za-z0-9+.-]*:"))'
  )
);
```

이 predicate 가 reject 하는 것:

- jsonb scalar string (Stage 1 형태)
- array 안에 non-string element
- array 안의 string 이 `[` 나 `{` 로 시작 (Stage 2 의 nested JSON-encoded 형태)
- array 안의 string 이 URI scheme 으로 시작 안 함

RFC 3986 scheme production (`ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )`) 을 정규식으로 직접 검사한다. `com.example.app://callback` 같은 모바일 앱 custom scheme 도 통과 — host 검증은 Ruby 쪽에서. DB 는 구조만 보장한다.

CHECK constraint 추가 전에 prod 의 모든 row 가 이 predicate 를 통과하는지 preflight 로 확인 필수.

```sql
SELECT count(*) FROM oauth_applications WHERE NOT (... 같은 predicate ...);
```

0이 안 나오면 추가 자체가 실패한다.

### Layer 2 — Model validator escape hatch 제거

기존 validator 는 이렇게 생겼었다.

```ruby
def redirect_uris_are_uris
  return unless redirect_uris.is_a?(Array)  # ← 이 줄이 문제

  redirect_uris.each do |uri|
    parsed = URI.parse(uri.to_s)
    ...
  end
end
```

`return unless Array` 가 escape hatch. nil 이나 String 이 들어오면 검증 자체를 건너뛴다. 이걸 hard rejection 으로 바꿨다.

```ruby
def redirect_uris_are_uris
  unless redirect_uris.is_a?(Array)
    errors.add(:redirect_uris, "must be an array of URI strings (got: #{redirect_uris.class})")
    return
  end

  redirect_uris.each do |uri|
    unless uri.is_a?(String)
      errors.add(:redirect_uris, "must contain only strings")
      next
    end

    if uri.match?(/\A\s*[\[\{]/)
      errors.add(:redirect_uris, "must not contain JSON-encoded values")
      next
    end

    parsed = URI.parse(uri)
    next if parsed.scheme.present? && parsed.host.present?
    errors.add(:redirect_uris, "must contain absolute URIs")
  rescue URI::InvalidURIError
    errors.add(:redirect_uris, "contains invalid URI")
  end
end
```

ActiveRecord 를 거치는 쓰기는 이제 jsonb scalar string 이나 nested JSON-encoded element 가 절대 들어갈 수 없다.

### Layer 3 — Runtime dispatch guard

DB CHECK 와 validator 둘 다 영구 저장되는 값만 검증한다. 그런데 in-memory 객체는?

```ruby
app = OauthApplication.find(id)
app.redirect_uris = '["a", "b"]'  # ← validator 안 거치고 직접 할당, String
app.redirect_uri_allowed?("a")    # ← 여기서 또 String#include? 발사
```

테스트 코드, factory mock, 또는 controller 의 build-but-not-save 패턴에서 이런 일이 일어날 수 있다. validator 가 막아도 그 시점은 `save` 호출 때고, 그 전에 `redirect_uri_allowed?` 가 호출되면 여전히 substring 매칭이 일어난다.

```ruby
def redirect_uri_allowed?(candidate)
  return false if candidate.blank?
  return false unless redirect_uris.is_a?(Array)  # ← 추가
  return false unless redirect_uris.include?(candidate)
  ...
end
```

한 줄짜리 가드. 메서드 자체가 자기 호출 시점에 receiver 형태를 확인한다. 이게 marker test 다 — `redirect_uris` 가 절대 String 이 될 수 없다는 invariant 가 코드 안에 명시적으로 박힌다.

---

## 결론 — Ruby `.include?` 가 보안 surface 라는 것

이 사고에서 가장 단단한 교훈은 한 줄이다.

> **`.include?` 를 호출하기 전에 `is_a?(Array)` 를 확인하라.**

특히 다음 조건이면 더 엄격하게.

- receiver 가 사용자 등록 데이터 (DB 컬럼) 인 경우
- 그 데이터가 인증·인가 결정에 쓰이는 경우
- jsonb 같은 동적 타입 컨테이너에서 deserialize 되는 경우

Ruby duck typing 은 보통 도움 되는데, 같은 메서드 이름이 receiver 클래스에 따라 다른 의미를 가지는 메서드들 (`include?`, `[]`, `each`, `size`, `to_s`) 은 데이터 형태가 invariant 가 아닐 때 의미가 부드럽게 바뀌어버린다. 그 의미 변화가 보안 결정의 의미 변화로 직결되면 hole 이 된다.

방어는 세 층으로 나누는 게 정답이었다.

| Layer | 차단 대상 | 비용 |
|---|---|---|
| Postgres CHECK constraint | raw SQL bypass, 잘못된 jsonb shape | 마이그레이션 1개 |
| Model validator (escape hatch 제거) | ActiveRecord 쓰기 | 메서드 한 개 수정 |
| Runtime dispatch guard | in-memory mock, 미저장 객체 | 메서드 한 줄 추가 |

이 셋을 다 깔면 `redirect_uri_allowed?` 의 `.include?` dispatch 가 절대 String#include? 로 떨어지지 않는다. 어떤 통로로 들어와도 차단된다.

그리고 이 셋 중 어떤 layer 도 다른 두 layer 를 대체할 수 없다는 게 핵심. CHECK constraint 만 있으면 in-memory misuse 못 막고, validator 만 있으면 raw SQL 못 막고, runtime guard 만 있으면 persistent corruption 누적된다. 하나만 골라서 의존하면 다른 통로가 열려 있다.

---

## 마이그레이션 작성할 때 다시는 안 하기로 다짐한 것

이번 사고를 가능하게 한 가장 오래된 코드는 다음 패턴이다.

```ruby
current = JSON.parse(app["redirect_uris"].to_s.presence || "[]") rescue []
```

`exec_query` 결과를 `to_s` + `JSON.parse` 로 한 바퀴 돌리는 거. 표면적으로는 "어떤 형태로 와도 array 로 normalize 한다" 처럼 보이지만, 실제로는 받은 값이 이미 Array 일 때 `to_s` 가 string 화하고 다시 parse 하는 의미 없는 round-trip 이다. 그리고 정작 받은 값이 Array 가 아닐 때는 `rescue []` 가 silent 하게 빈 배열로 둔갑시킨다. silent overwrite 위험까지 같이 들어있다.

raw SQL 마이그레이션에서 jsonb 컬럼을 만질 때 다음 규칙을 따로 박아뒀다.

1. `exec_query` 결과는 이미 deserialize 된 Ruby type 이라 `to_s` + `JSON.parse` 가 필요 없다
2. 받은 값이 예상 shape (Array, Hash, String 중 어느 것) 인지 `is_a?` 로 explicit 검증
3. unknown shape 면 `rescue []` 가 아니라 `raise` — silent overwrite 절대 금지
4. 단일 row repair 는 항상 트랜잭션 + FOR UPDATE + affected_rows assert + 사후 reselect

이 4개 중 하나라도 빠뜨리면 같은 종류의 데이터 손상이 또 들어올 수 있다.

---

## 회고

가장 인상 깊었던 점은, 보안 hole 이 의도하지 않은 부작용으로 닫혔다는 것 자체였다. 자물쇠가 우연히 잘 잠기고 있다는 게 자물쇠가 잘 동작한다는 증거는 절대 아니다. 어떤 방향에서 들어오는 input 도 의도된 매칭 의미로 평가되는지를 따로 검증해야 한다.

그리고 같은 코드 한 줄이 시간에 따라 다른 의미를 가질 수 있다는 사실을 코드 리뷰 단계에서 잡아내는 건 쉽지 않다. 데이터 shape 의 invariant 가 코드의 dispatch 의미를 결정하는데, invariant 가 코드 안에 명시적으로 박혀 있지 않으면 `.include?` 라는 익숙한 한 줄이 시한폭탄이 된다.

다음에 OAuth 관련 코드를 들여다볼 일이 생기면, 가장 먼저 보는 건 redirect_uri 검증 메서드와 그 receiver 의 데이터 shape invariant 다. 그게 깨져 있으면 다른 어떤 코드 품질 지표도 의미가 없다.
