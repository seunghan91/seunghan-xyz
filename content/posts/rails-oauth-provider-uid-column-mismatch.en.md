---
title: "Rails OAuth: PG::UndefinedColumn users.uid Error — Column Name Mismatch"
date: 2025-09-06
draft: true
tags: ["Rails", "OAuth", "PostgreSQL", "Apple Sign-In", "Debugging"]
description: "When Rails OAuth controller references uid column but the actual DB column is provider_uid, PG::UndefinedColumn error occurs. How to verify with logs and fix."
cover:
  image: "/images/og/rails-oauth-provider-uid-column-mismatch.png"
  alt: "Rails Oauth Provider Uid Column Mismatch"
  hidden: true
---


After integrating Apple Sign-In / Google Sign-In, the client only shows a 500 error, but looking at the server logs reveals the actual cause is different. Here is a case I encountered today.

In the early stages of SSO integration, it is not easy to distinguish whether it is a client-side (Flutter) configuration problem or a server-side problem. This post covers how to quickly diagnose and fix a `PG::UndefinedColumn` error caused by a server DB column name mismatch.

---

## Error

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 ...
```

On the client (Flutter) side, it appears as `401 Unauthorized`.

---

## Cause

The controller code for finding OAuth users referenced the `uid` column, but in the actual DB schema, there was no `uid` column -- it was defined as `provider_uid`.

```ruby
# Wrong code
user = User.find_by(provider: provider, uid: uid)
user.uid = uid
```

```ruby
# Correct code
user = User.find_by(provider: provider, provider_uid: uid)
user.provider_uid = uid
```

---

## Why This Mistake Happens

When first designing OAuth, you might think of the Devise-style `uid` and write code before deciding on the column name.

Or when copying code from another project, that project's column name (`uid`) may differ from the current project (`provider_uid`), and pasting it as-is causes this problem.

---

## How to Verify

### 1. Check Column Names in schema.rb

```ruby
# db/schema.rb
create_table "users", force: :cascade do |t|
  t.string "provider"
  t.string "provider_uid"   # not uid
  # ...
end
```

### 2. Direct Query Check

```bash
bundle exec rails c
User.column_names.grep(/uid|provider/)
# => ["provider", "provider_uid"]
```

---

## Fix

Align both `find_by` and attribute assignments to the actual column names.

```ruby
def create_or_update_oauth_user!(provider:, uid:, email:, name:, avatar_url:)
  user = User.find_by(provider: provider, provider_uid: uid) ||
         User.find_by(email: email.downcase)
  user ||= User.new

  user.provider     = provider
  user.provider_uid = uid      # uid -> provider_uid
  user.email        = email.downcase
  # ...
  user.save!
  user
end
```

---

## Lessons Learned

When SSO errors occur on the client side, the instinct is to suspect the client (tokens, configuration files). But checking the server logs first often reveals DB errors like `PG::UndefinedColumn` right away.

When social login fails, checking **server logs first** rather than client logs is faster.

---

## Similar Column Mismatch Patterns

The same type of mistake can occur with other columns.

| Wrong Column Name | Actual Column Name | Situation |
|---|---|---|
| `uid` | `provider_uid` | OAuth user identifier |
| `name` | `display_name` | User display name |
| `image` | `avatar_url` | Profile image |
| `token` | `access_token` | OAuth access token |

Always check whether column names differ when copying code from another project.

---

## Quickly Checking Column Names in Rails

```bash
# Check in console
bundle exec rails c
User.column_names
# => ["id", "email", "provider", "provider_uid", "display_name", ...]

# Check schema.rb directly
grep -A 20 'create_table "users"' db/schema.rb
```

---

## Prevention: Check schema.rb Before Writing Controllers

Building a habit of checking actual column names in `db/schema.rb` before writing OAuth controllers can reduce these mistakes.

Alternatively, defining explicit aliases in the model provides flexible handling.

```ruby
# app/models/user.rb
alias_attribute :uid, :provider_uid
```

However, overusing aliases can cause more confusion, so use them judiciously.
