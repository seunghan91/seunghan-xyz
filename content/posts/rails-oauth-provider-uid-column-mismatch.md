---
title: "Rails OAuth: PG::UndefinedColumn users.uid 에러 — 컬럼명 불일치"
date: 2025-09-06
draft: true
tags: ["Rails", "OAuth", "PostgreSQL", "Apple Sign-In", "디버깅"]
description: "Rails OAuth 컨트롤러에서 uid 컬럼을 참조했지만 실제 DB 컬럼명이 provider_uid인 경우 PG::UndefinedColumn 에러가 발생한다. 로그로 확인하는 방법과 수정 방법을 정리한다."
cover:
  image: "/images/og/rails-oauth-provider-uid-column-mismatch.png"
  alt: "Rails Oauth Provider Uid Column Mismatch"
  hidden: true
categories: ["Rails"]
---

Apple Sign-In / Google Sign-In 연동 후 클라이언트에서는 500 에러만 보이는데, 서버 로그를 보면 실제 원인이 다른 경우가 있다. 오늘 마주친 케이스를 정리한다.

SSO 연동 초기에는 클라이언트(Flutter) 쪽 설정 문제인지, 서버 쪽 문제인지 구분하기가 쉽지 않다. 클라이언트 개발자 입장에서는 네트워크 응답이 `401` 또는 `500`으로 돌아오면 우선 토큰 생성 로직, Apple/Google 콘솔 설정, Bundle ID나 Client ID 불일치를 의심하게 된다. 하지만 서버 로그를 열어보면 전혀 다른 레이어의 에러가 찍혀 있을 때가 많다. 이 글에서는 서버 DB 컬럼명 불일치로 인한 `PG::UndefinedColumn` 에러를 빠르게 진단하고 수정하는 방법을 다룬다.

---

## 발생 환경

- Rails 8.x + PostgreSQL
- Flutter 클라이언트 → Rails API 서버로 Apple/Google ID 토큰 전달
- 서버에서 토큰 검증 후 `User` 레코드를 upsert하는 구조
- 새 프로젝트에서 기존 프로젝트 OAuth 컨트롤러 코드를 복사해 사용

이런 환경에서 마이그레이션은 `provider_uid`로 정의했지만, 복사해온 컨트롤러 코드는 `uid`를 그대로 참조하고 있었다.

---

## 에러

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 ...
```

Rails 서버 로그에는 위 PostgreSQL 에러가 전체 스택 트레이스와 함께 출력된다. 하지만 클라이언트(Flutter)에서는 `401 Unauthorized` 또는 `500 Internal Server Error`로만 보인다. 서버 로그를 직접 확인하지 않으면 원인을 파악하기 어렵다.

클라이언트에서 보이는 응답 예시:

```json
{
  "error": "Internal server error"
}
```

이 응답만 보면 토큰 문제인지, 설정 문제인지, DB 문제인지 전혀 알 수 없다. **서버 로그를 먼저 확인하는 것이 진단의 첫 번째 단계다.**

---

## 원인

OAuth 사용자를 찾는 컨트롤러 코드에서 `uid` 컬럼을 참조했지만, 실제 DB 스키마에는 `uid` 컬럼이 없고 `provider_uid`라는 이름으로 정의되어 있었다.

```ruby
# 잘못된 코드 — uid 컬럼이 실제로는 존재하지 않음
user = User.find_by(provider: provider, uid: uid)
user.uid = uid
```

ActiveRecord는 `find_by(uid: ...)` 호출을 그대로 SQL로 변환한다. `uid` 컬럼이 DB에 없으면 PostgreSQL이 `PG::UndefinedColumn` 에러를 던진다. Rails는 이 에러를 잡아서 500 응답으로 변환하고, 클라이언트는 내용 없는 에러 응답만 받는다.

```ruby
# 올바른 코드 — 실제 컬럼명 provider_uid 사용
user = User.find_by(provider: provider, provider_uid: uid)
user.provider_uid = uid
```

---

## 왜 이런 실수가 생기나

### 1. Devise OmniAuth 관례에서 오는 혼동

[devise](https://github.com/heartcombo/devise) + [omniauth](https://github.com/omniauth/omniauth) 조합을 사용하는 프로젝트는 보통 `uid` 컬럼을 그대로 사용한다. Devise OmniAuth 공식 문서의 예시 코드도 `uid`를 기준으로 작성되어 있다.

```ruby
# Devise OmniAuth 공식 예시 패턴
def self.from_omniauth(auth)
  where(provider: auth.provider, uid: auth.uid).first_or_create do |user|
    user.email = auth.info.email
    user.password = Devise.friendly_token[0, 20]
  end
end
```

이 코드를 Devise 없이 자체 OAuth 구현에 재활용할 때, 스키마에서 컬럼명을 `provider_uid`로 다르게 정의했다면 불일치가 발생한다.

### 2. 프로젝트 간 코드 복사

새 프로젝트를 시작할 때 기존 프로젝트의 OAuth 컨트롤러를 복사하는 경우가 많다. 기존 프로젝트에서는 `uid`로 동작했더라도, 새 프로젝트 마이그레이션에서 `provider_uid`로 명명했다면 컨트롤러 코드를 그대로 붙여넣으면 이 문제가 생긴다.

### 3. 마이그레이션과 컨트롤러 작성 순서의 불일치

마이그레이션을 먼저 작성하고 컨트롤러를 나중에 작성할 때, 또는 반대로 컨트롤러를 먼저 작성하고 마이그레이션을 나중에 맞출 때 이름이 어긋날 수 있다. 특히 여러 명이 동시에 작업하는 팀 환경에서 자주 발생한다.

---

## 확인 방법

### 1. schema.rb에서 컬럼명 확인

가장 신뢰할 수 있는 방법은 `db/schema.rb`를 직접 확인하는 것이다. 이 파일은 현재 DB 상태를 반영한다.

```ruby
# db/schema.rb
create_table "users", force: :cascade do |t|
  t.string "email",        null: false
  t.string "provider"
  t.string "provider_uid"   # uid가 아님 — 이 이름을 컨트롤러에서 써야 한다
  t.string "display_name"
  t.string "avatar_url"
  t.timestamps
end
```

### 2. Rails 콘솔에서 직접 확인

```bash
bundle exec rails c
User.column_names
# => ["id", "email", "provider", "provider_uid", "display_name", "avatar_url", "created_at", "updated_at"]

# uid나 provider 관련 컬럼만 필터링
User.column_names.grep(/uid|provider/)
# => ["provider", "provider_uid"]
```

### 3. grep으로 schema.rb 빠르게 조회

```bash
grep -A 20 'create_table "users"' db/schema.rb
```

### 4. 서버 로그에서 실제 쿼리 확인

Rails 개발 환경에서는 실행된 SQL이 로그에 출력된다. 에러 발생 직전 쿼리를 보면 어떤 컬럼명이 참조되고 있는지 바로 알 수 있다.

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 AND ...
                                                    ^^^
                                            이 컬럼명이 틀렸다
```

---

## 수정

`find_by`와 속성 할당 모두 실제 컬럼명으로 맞춰준다. 파라미터명(`uid`)은 그대로 유지하고, DB 컬럼 참조 부분(`provider_uid`)만 수정한다.

```ruby
def create_or_update_oauth_user!(provider:, uid:, email:, name:, avatar_url:)
  # provider + provider_uid 조합으로 먼저 찾고, 없으면 이메일로 찾는다
  user = User.find_by(provider: provider, provider_uid: uid) ||
         User.find_by(email: email.downcase)
  user ||= User.new

  user.provider     = provider
  user.provider_uid = uid          # uid → provider_uid
  user.email        = email.downcase
  user.display_name = name         # name → display_name (이것도 확인 필요)
  user.avatar_url   = avatar_url   # image → avatar_url (이것도 확인 필요)
  user.save!
  user
end
```

수정 후 Rails 콘솔에서 동작을 직접 검증하면 좋다.

```bash
bundle exec rails c

# 테스트용 upsert 호출
user = create_or_update_oauth_user!(
  provider: "apple",
  uid: "test.apple.uid.001",
  email: "test@example.com",
  name: "테스트 유저",
  avatar_url: nil
)
puts user.persisted?   # => true
puts user.provider_uid # => "test.apple.uid.001"
```

---

## 유사한 컬럼 불일치 패턴

같은 유형의 실수가 다른 컬럼에서도 발생할 수 있다. OAuth 구현 시 자주 혼동되는 컬럼명을 정리했다.

| 잘못된 컬럼명 | 실제 컬럼명 | 상황 |
|---|---|---|
| `uid` | `provider_uid` | OAuth 사용자 식별자 |
| `name` | `display_name` | 사용자 표시 이름 |
| `image` | `avatar_url` | 프로필 이미지 URL |
| `token` | `access_token` | OAuth 액세스 토큰 |
| `refresh_token` | `oauth_refresh_token` | 토큰 갱신용 |
| `expires_at` | `token_expires_at` | 토큰 만료 시각 |

Devise OmniAuth 관례(`uid`, `name`, `image`, `token`)와 자체 스키마 컬럼명이 다를 때 이 문제가 발생한다. 다른 프로젝트에서 코드를 복사해올 때 **컬럼명 대조 확인**을 루틴으로 만들어두는 것이 좋다.

---

## 예방책

### 1. 컨트롤러 작성 전 schema.rb 먼저 확인

OAuth 컨트롤러를 작성하기 전에 `db/schema.rb`에서 실제 컬럼명을 먼저 확인하는 습관을 들이면 이런 실수를 줄일 수 있다. 특히 코드를 복사해올 때 반드시 확인한다.

```bash
# 컨트롤러 작성 전 컬럼 확인
grep -A 30 'create_table "users"' db/schema.rb
```

### 2. model alias 활용 (신중하게)

모델에 명시적으로 alias를 정의해두면 기존 코드와 호환성을 유지하면서 유연하게 대응할 수 있다.

```ruby
# app/models/user.rb
alias_attribute :uid, :provider_uid
```

`alias_attribute`를 사용하면 `user.uid`와 `user.provider_uid` 모두 동작한다. 그러나 alias를 남용하면 어떤 컬럼명이 실제 DB 컬럼인지 파악하기 어려워지고, 팀원들에게 혼란을 줄 수 있다. 레거시 코드와 인터페이스를 맞춰야 하는 상황이 아니라면 컬럼명 자체를 일관되게 쓰는 편이 낫다.

### 3. 마이그레이션 + 컨트롤러 동시 작성 / 코드 리뷰

마이그레이션을 작성할 때 컨트롤러 코드도 함께 작성하거나, 코드 리뷰 체크리스트에 "DB 컬럼명과 코드 일치 여부"를 항목으로 추가해두면 팀 단위에서 이 실수를 방지할 수 있다.

### 4. RSpec 모델 테스트로 조기 발견

컬럼 존재 여부를 검증하는 간단한 테스트를 추가하면 CI 단계에서 조기에 발견할 수 있다.

```ruby
# spec/models/user_spec.rb
RSpec.describe User, type: :model do
  it "has provider_uid column" do
    expect(User.column_names).to include("provider_uid")
    expect(User.column_names).not_to include("uid")
  end
end
```

---

## Key Takeaways

- **클라이언트의 401/500 에러는 서버 로그를 먼저 확인한다.** 서버 로그에 `PG::UndefinedColumn`이 찍혀 있다면 클라이언트 설정이 아니라 DB 컬럼명 불일치가 원인이다.
- **`PG::UndefinedColumn`의 가장 흔한 원인은 코드 복사 시 컬럼명 불일치다.** Devise OmniAuth 예시(`uid`)를 자체 스키마(`provider_uid`)에 그대로 적용하면 발생한다.
- **`db/schema.rb`가 정답이다.** 현재 DB 상태는 `schema.rb`에 가장 정확하게 반영되어 있다. `User.column_names`로 Rails 콘솔에서도 바로 확인할 수 있다.
- **수정은 단순하다.** `find_by`와 속성 할당에서 잘못된 컬럼명을 실제 컬럼명으로 교체하면 된다.
- **`alias_attribute`는 임시방편으로만 사용한다.** 장기적으로는 컬럼명을 일관되게 유지하는 것이 코드베이스를 깔끔하게 유지하는 방법이다.
