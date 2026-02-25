---
title: "Rails OAuth: PG::UndefinedColumn users.uid 에러 — 컬럼명 불일치"
date: 2026-02-25
draft: false
tags: ["Rails", "OAuth", "PostgreSQL", "Apple Sign-In", "디버깅"]
description: "Rails OAuth 컨트롤러에서 uid 컬럼을 참조했지만 실제 DB 컬럼명이 provider_uid인 경우 PG::UndefinedColumn 에러가 발생한다. 로그로 확인하는 방법과 수정 방법을 정리한다."
---

Apple Sign-In / Google Sign-In 연동 후 클라이언트에서는 500 에러만 보이는데, 서버 로그를 보면 실제 원인이 다른 경우가 있다. 오늘 마주친 케이스를 정리한다.

---

## 에러

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 ...
```

클라이언트(Flutter)에서는 `401 Unauthorized`로 보인다.

---

## 원인

OAuth 사용자를 찾는 컨트롤러 코드에서 `uid` 컬럼을 참조했지만, 실제 DB 스키마에는 `uid` 컬럼이 없고 `provider_uid`라는 이름으로 정의되어 있었다.

```ruby
# 잘못된 코드
user = User.find_by(provider: provider, uid: uid)
user.uid = uid
```

```ruby
# 올바른 코드
user = User.find_by(provider: provider, provider_uid: uid)
user.provider_uid = uid
```

---

## 왜 이런 실수가 생기나

OAuth를 처음 설계할 때 Devise 스타일의 `uid`를 떠올려 컬럼명을 결정하기 전에 코드를 먼저 작성하는 경우가 있다.

또는 다른 프로젝트에서 코드를 복사해올 때 해당 프로젝트의 컬럼명(`uid`)이 현재 프로젝트(`provider_uid`)와 달라서 그대로 붙여넣으면 이 문제가 생긴다.

---

## 확인 방법

### 1. schema.rb에서 컬럼명 확인

```ruby
# db/schema.rb
create_table "users", force: :cascade do |t|
  t.string "provider"
  t.string "provider_uid"   # uid가 아님
  # ...
end
```

### 2. 직접 쿼리 확인

```bash
bundle exec rails c
User.column_names.grep(/uid|provider/)
# => ["provider", "provider_uid"]
```

---

## 수정

`find_by`와 속성 할당 모두 실제 컬럼명으로 맞춰준다.

```ruby
def create_or_update_oauth_user!(provider:, uid:, email:, name:, avatar_url:)
  user = User.find_by(provider: provider, provider_uid: uid) ||
         User.find_by(email: email.downcase)
  user ||= User.new

  user.provider     = provider
  user.provider_uid = uid      # uid → provider_uid
  user.email        = email.downcase
  # ...
  user.save!
  user
end
```

---

## 교훈

클라이언트 쪽에서 SSO 에러가 나면 반사적으로 클라이언트(토큰, 설정 파일)를 의심하게 된다. 그런데 서버 로그를 먼저 보면 `PG::UndefinedColumn` 같은 DB 에러가 바로 찍혀 있는 경우가 많다.

소셜 로그인 실패 시 클라이언트 로그보다 **서버 로그를 먼저** 확인하는 게 빠르다.
