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
categories: ["Rails"]
---

After integrating Apple Sign-In or Google Sign-In, the client shows a generic 500 error, but the actual cause lives somewhere completely different. This post documents a case I ran into recently and how I tracked it down.

In the early stages of SSO integration, it is genuinely difficult to distinguish between a client-side configuration problem (Flutter app, Apple/Google console settings, Bundle ID mismatch) and a server-side problem. The natural instinct is to start with the client — check the token generation logic, verify the client ID, compare the bundle identifier against what was registered in the Apple Developer portal. All of that takes time. Checking the server logs first would have saved me twenty minutes. This post covers how to quickly diagnose and fix a `PG::UndefinedColumn` error caused by a DB column name mismatch in a Rails OAuth controller.

---

## Environment

- Rails 8.x + PostgreSQL
- Flutter client sending Apple / Google ID tokens to a Rails API server
- Server verifies the token and upserts a `User` record
- New project reusing an OAuth controller copied from an older project

In this setup, the migration defined the column as `provider_uid`, but the copied controller code still referenced `uid`. The two files were written independently and never cross-checked against each other.

---

## The Error

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 ...
```

Rails prints this PostgreSQL error in full, along with a complete stack trace. The client, however, sees only a vague HTTP response:

```json
{
  "error": "Internal server error"
}
```

On a Flutter client this surfaces as `401 Unauthorized` or `500 Internal Server Error`. There is no way to tell from the client response alone whether the problem is a bad token, a misconfigured OAuth app, or a broken database query. **The server log is the only place where the real cause is visible.**

---

## Root Cause

The OAuth controller looked up users using the `uid` column, but the actual database schema defined that column as `provider_uid`. There was no `uid` column in the table at all.

```ruby
# Broken code — uid column does not exist in the database
user = User.find_by(provider: provider, uid: uid)
user.uid = uid
```

ActiveRecord translates `find_by(uid: ...)` directly into SQL. When PostgreSQL encounters a column that does not exist, it raises `PG::UndefinedColumn`. Rails catches this and returns a 500 response, and the original error message never reaches the client.

```ruby
# Correct code — uses the actual column name
user = User.find_by(provider: provider, provider_uid: uid)
user.provider_uid = uid
```

The fix is mechanical: replace the incorrect column name with the real one wherever it appears.

---

## Why This Mistake Happens

### 1. Confusion from Devise OmniAuth conventions

Projects built with [devise](https://github.com/heartcombo/devise) and [omniauth](https://github.com/omniauth/omniauth) typically use a column named `uid`. The official Devise OmniAuth documentation shows examples built around that name:

```ruby
# Standard Devise OmniAuth pattern
def self.from_omniauth(auth)
  where(provider: auth.provider, uid: auth.uid).first_or_create do |user|
    user.email = auth.info.email
    user.password = Devise.friendly_token[0, 20]
  end
end
```

When you build a custom OAuth implementation without Devise but name the column `provider_uid` in your migration, reusing this pattern without updating the column reference breaks things immediately.

### 2. Copy-pasting controllers across projects

Starting a new project by copying an existing OAuth controller is a common shortcut. If the source project used `uid` and the new project's migration uses `provider_uid`, the controller code will fail the moment it runs a query against the database. The tests might even pass if test fixtures happen to be empty or if the model is never exercised directly.

### 3. Writing the controller before the migration is finalized

Sometimes the controller is written first as a rough draft, with the migration added afterward. If the developer chose a different column name in the migration than what was already in the controller, the mismatch sits silently until the code path is hit at runtime.

---

## How to Verify

### 1. Check column names in schema.rb

`db/schema.rb` is the authoritative source for the current database structure. Read it before writing any query.

```ruby
# db/schema.rb
create_table "users", force: :cascade do |t|
  t.string "email",        null: false
  t.string "provider"
  t.string "provider_uid"   # not uid — this is the name the controller must use
  t.string "display_name"
  t.string "avatar_url"
  t.timestamps
end
```

### 2. Query column names in the Rails console

```bash
bundle exec rails c

User.column_names
# => ["id", "email", "provider", "provider_uid", "display_name", "avatar_url", "created_at", "updated_at"]

# Filter for uid or provider related columns
User.column_names.grep(/uid|provider/)
# => ["provider", "provider_uid"]
```

### 3. Grep schema.rb from the terminal

```bash
grep -A 20 'create_table "users"' db/schema.rb
```

### 4. Read the SQL in the server log

In development, Rails logs every SQL query it executes. The `PG::UndefinedColumn` error includes the exact SQL line that failed:

```
PG::UndefinedColumn: ERROR: column users.uid does not exist
LINE 1: SELECT "users".* FROM "users" WHERE "users"."uid" = $1 AND ...
                                                    ^^^
                                            wrong column name right here
```

This makes it trivial to identify exactly which column name the code is using versus what the database actually has.

---

## The Fix

Update both the `find_by` lookup and any attribute assignments to use the real column name. Keep the method parameter name (`uid`) as-is — it is a local variable name and has nothing to do with the database.

```ruby
def create_or_update_oauth_user!(provider:, uid:, email:, name:, avatar_url:)
  # Look up by provider + provider_uid first, fall back to email
  user = User.find_by(provider: provider, provider_uid: uid) ||
         User.find_by(email: email.downcase)
  user ||= User.new

  user.provider     = provider
  user.provider_uid = uid          # uid -> provider_uid
  user.email        = email.downcase
  user.display_name = name         # also check: name vs display_name
  user.avatar_url   = avatar_url   # also check: image vs avatar_url
  user.save!
  user
end
```

After making the change, verify directly in the Rails console before deploying:

```bash
bundle exec rails c

user = create_or_update_oauth_user!(
  provider: "apple",
  uid: "test.apple.uid.001",
  email: "test@example.com",
  name: "Test User",
  avatar_url: nil
)
puts user.persisted?    # => true
puts user.provider_uid  # => "test.apple.uid.001"
```

---

## Similar Column Mismatch Patterns

The same class of mistake affects other columns whenever Devise OmniAuth naming conventions collide with a custom schema. Common mismatches:

| Wrong Column Name | Actual Column Name | Context |
|---|---|---|
| `uid` | `provider_uid` | OAuth user identifier |
| `name` | `display_name` | User display name |
| `image` | `avatar_url` | Profile image URL |
| `token` | `access_token` | OAuth access token |
| `refresh_token` | `oauth_refresh_token` | Token refresh |
| `expires_at` | `token_expires_at` | Token expiry timestamp |

Any time you copy OAuth controller code from one project to another, compare the column names used in the code against what `db/schema.rb` actually defines. The five seconds this takes is cheaper than an hour of debugging a vague 500 error.

---

## Prevention

### 1. Check schema.rb before writing the controller

Make it a habit: before writing any `find_by` or attribute assignment in an OAuth controller, open `db/schema.rb` and confirm the exact column names. This single step eliminates the entire class of mismatch errors.

```bash
grep -A 30 'create_table "users"' db/schema.rb
```

### 2. Use alias_attribute for legacy compatibility (with caution)

If you need to maintain backward compatibility with an existing codebase that uses `uid`, you can define an alias in the model:

```ruby
# app/models/user.rb
alias_attribute :uid, :provider_uid
```

With this in place, both `user.uid` and `user.provider_uid` work. However, aliases add a layer of indirection that makes it harder to understand the actual schema at a glance. Use this approach only when compatibility with a legacy interface genuinely requires it. For a greenfield project, keep column names consistent and skip the alias.

### 3. Write migration and controller together, and code review for column alignment

Writing the migration and controller in the same pull request makes it much easier to catch mismatches during code review. Adding a checklist item — "DB column names match code references" — to your team's review template is a lightweight way to prevent this from slipping through.

### 4. Add a model spec to catch column name regressions

A minimal RSpec test can catch this during CI before it ever reaches production:

```ruby
# spec/models/user_spec.rb
RSpec.describe User, type: :model do
  it "has provider_uid column and not uid" do
    expect(User.column_names).to include("provider_uid")
    expect(User.column_names).not_to include("uid")
  end
end
```

This test fails immediately if someone adds a migration that renames the column or if the wrong schema is loaded in test setup.

---

## Key Takeaways

- **Start with the server log, not the client error.** A `401` or `500` on the client tells you nothing about the actual cause. The server log shows the raw `PG::UndefinedColumn` error with the exact SQL and column name involved.
- **The most common cause of `PG::UndefinedColumn` in OAuth code is copy-pasting from a project with different column names.** Devise OmniAuth conventions (`uid`, `name`, `image`) often conflict with a custom schema (`provider_uid`, `display_name`, `avatar_url`).
- **`db/schema.rb` is the ground truth.** It reflects the actual current state of the database. Use `User.column_names` in the Rails console when you need to check programmatically.
- **The fix is always the same: replace the wrong column name with the real one** in every `find_by` call and every attribute assignment.
- **`alias_attribute` is a compatibility tool, not a solution.** It can paper over the mismatch, but it adds hidden indirection. Prefer consistent column naming across the codebase.
- **A one-line model spec catches this before CI.** The cost of adding `expect(User.column_names).to include("provider_uid")` is negligible; the cost of debugging a silent 500 error in production is not.
