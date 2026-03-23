---
title: "Rails API Token Creation: Errors from Missing NOT NULL Columns"
date: 2025-06-22
draft: true
tags: ["Rails", "API", "Authentication", "Debugging"]
description: "Errors that occur when creating API tokens directly with create! in Rails while missing NOT NULL columns, and why you should use Service objects."
cover:
  image: "/images/og/rails-api-token-not-null-constraint.png"
  alt: "Rails Api Token Not Null Constraint"
  hidden: true
categories: ["Rails"]
---

This documents a problem encountered while writing token issuance logic after social login (SSO) on a Rails API server.

---

## Situation

After Apple Sign In / Google Sign In, the server needs to issue access tokens and refresh tokens and return them to the client. This is a common flow when implementing social login in a mobile app or SPA:

1. The client receives an identity token (or authorization code) from Apple or Google and sends it to the server.
2. The server verifies the token, then finds or creates an internal user record.
3. The server issues its own access token and refresh token and returns them to the client.
4. Subsequent API requests include this access token as an `Authorization: Bearer <token>` header.

At step 3 — issuing the token directly — I wrote the following in the controller:

```ruby
token = user.api_tokens.create!(
  token_type: "bearer",
  expires_at: 1.hour.from_now
)
```

Simple-looking code, but it immediately threw an error.

---

## Error

```
ActiveRecord::NotNullViolation:
PG::NotNullViolation: ERROR: null value in column "token_digest"
violates not-null constraint
```

PostgreSQL detected a NOT NULL constraint violation and rejected the INSERT entirely. Rails' `ActiveRecord::NotNullViolation` is the exception that wraps this database-level error.

A subsequent attempt also produced this error:

```
ActiveRecord::UnknownAttributeError:
unknown attribute 'token_type' for ApiToken.
```

Both errors stem from the same root cause: attempting to interact with the model directly without understanding the actual table schema.

---

## Root Cause Analysis

Inspecting the actual schema of the `api_tokens` table revealed these columns were defined as `NOT NULL`:

```ruby
# db/schema.rb
create_table "api_tokens" do |t|
  t.string   "token_digest",         null: false  # SHA-256 hash value
  t.string   "refresh_token_digest", null: false  # refresh token hash value
  t.datetime "refresh_expires_at",   null: false  # refresh expiration timestamp
  t.string   "jti",                  null: false  # JWT ID (prevents replay)
  t.integer  "user_id",              null: false
  t.datetime "expires_at",           null: false
  t.datetime "created_at",           null: false
  t.datetime "updated_at",           null: false
end
```

The `create!` call only passed two parameters — `token_type` and `expires_at` — so two problems surfaced at once.

**Problem 1: NOT NULL columns received no values**

`token_digest`, `refresh_token_digest`, `refresh_expires_at`, and `jti` are all NOT NULL, yet the code supplied no values for them. ActiveRecord attempted the INSERT with these columns set to `nil`, and PostgreSQL rejected it with a constraint violation.

**Problem 2: A non-existent column was specified**

`token_type` does not exist in the schema. This was a case of confusing column names from another framework or library (such as Doorkeeper). Rails raises `UnknownAttributeError` when you pass an attribute name that has no corresponding column.

**The deeper problem**

Even if the schema had been read correctly, calling `create!` directly would still be wrong. The value stored in `token_digest` is not a plain string — it is a SHA-256 hash of the raw token. Writing that hashing logic inline in every controller that issues tokens leads to code duplication, security inconsistencies, and maintenance headaches.

---

## Debugging Steps

Here is the debugging sequence for when you hit this kind of error.

**Step 1: Check the schema**

The first thing to do is look at `db/schema.rb` or the relevant migration file.

```bash
# Find the table definition in schema.rb
grep -A 20 'create_table "api_tokens"' db/schema.rb
```

Identify which columns are NOT NULL and which columns actually exist.

**Step 2: Search for existing Service or helper code**

Search the project for existing code related to `api_token` or `token`.

```bash
grep -r "ApiToken" app/services/
grep -r "generate.*token\|token.*generate" app/
```

In most Rails projects, complex logic like token issuance is already implemented in a Service object or a Model class method. The fix is often just finding and using what already exists.

**Step 3: Read the error message literally**

`PG::NotNullViolation: ERROR: null value in column "token_digest"` names `"token_digest"` as the problem column. Tracing what value belongs there — through the schema and existing code — reveals the solution.

---

## Solution: Use a Service Object

A Service object (`ApiTokenService`) containing the token creation logic had already been implemented. The controller should go through the service rather than manipulating the model directly.

```ruby
# Wrong approach
token = user.api_tokens.create!(token_type: "bearer", expires_at: 1.hour.from_now)

# Correct approach
token_pair = ApiTokenService.generate(user, request)

# Using the return value
render json: {
  access_token:  token_pair[:access_token],
  refresh_token: token_pair[:refresh_token],
  expires_at:    token_pair[:expires_at].iso8601
}
```

`ApiTokenService.generate` internally handles all of the following:

- Generates a raw token string (e.g., `SecureRandom.hex(32)`) to be delivered to the client
- Computes `Digest::SHA256.hexdigest(raw_token)` and stores the result in `token_digest` — only the hash goes into the database
- Generates and hashes the refresh token in the same manner
- Generates a `jti` using `SecureRandom.uuid`
- Automatically sets `expires_at` and `refresh_expires_at`

The controller's only job is to call the service and render the result as JSON.

---

## Why Not Store Raw Tokens in the Database

If raw tokens are stored directly in the database, every user's token is exposed the moment the database is compromised. An attacker gains immediate access to all accounts.

Storing SHA-256 hashes instead means:

- When a client sends a token, the server hashes it and compares the hash against the database.
- If the database is compromised, the original tokens cannot be reverse-engineered from the hash values.
- This is the same principle as password hashing — though with API tokens, a fast hash like SHA-256 is appropriate because the tokens already have sufficient entropy (256 bits), unlike passwords where a slow hash (bcrypt, argon2) is necessary to resist brute force.

```ruby
# Token verification
def authenticate_token(raw_token)
  digest = Digest::SHA256.hexdigest(raw_token)
  ApiToken.find_by(token_digest: digest)
end
```

The verification flow is straightforward: extract the raw token from the request header, hash it, and check whether that hash exists in the database. The raw token lives briefly in server memory and is never persisted anywhere.

---

## Why jti (JWT ID) Is Necessary

`jti` is the unique identifier for a token record. It serves two main purposes.

**Replay attack prevention**

If a refresh token is stolen, it could be replayed to obtain new access tokens indefinitely. When the server invalidates the `jti` upon use — treating it as a one-time value — the same refresh token cannot be used twice. If an attacker and the legitimate user both try to use the same refresh token, the server can detect the conflict.

**Selective token revocation**

When only a specific session needs to be invalidated (for example, "log out this device"), the server can delete the `api_tokens` row with that particular `jti` without affecting other sessions. A "log out all devices" feature deletes all `api_tokens` rows for a user.

---

## Prevention: Patterns to Avoid Similar Errors

This class of error comes from the habit of reaching directly for `Model.create!` without understanding the schema or the existing codebase. A few patterns prevent it.

**Pattern 1: Encapsulate complex creation logic in a Service object or class method**

```ruby
# Model class method approach
class ApiToken < ApplicationRecord
  def self.generate_for(user, request)
    raw_token = SecureRandom.hex(32)
    raw_refresh = SecureRandom.hex(32)
    token = create!(
      user: user,
      token_digest: Digest::SHA256.hexdigest(raw_token),
      refresh_token_digest: Digest::SHA256.hexdigest(raw_refresh),
      jti: SecureRandom.uuid,
      expires_at: 1.hour.from_now,
      refresh_expires_at: 30.days.from_now
    )
    { access_token: raw_token, refresh_token: raw_refresh, expires_at: token.expires_at }
  end
end
```

**Pattern 2: Use `before_validation` callbacks for auto-generated NOT NULL columns**

If a NOT NULL column is always auto-generated rather than user-supplied, a model callback can fill it in automatically.

```ruby
class ApiToken < ApplicationRecord
  before_validation :set_jti, on: :create

  private

  def set_jti
    self.jti ||= SecureRandom.uuid
  end
end
```

This means a forgotten `jti` in a `create!` call will not blow up — the callback fills it in. That said, security-sensitive fields like token digests are better kept inside a Service object rather than scattered across callbacks.

**Pattern 3: Always check the schema before working with a new model**

```bash
# Keep schema.rb current
rails db:schema:dump

# Inspect a specific table
grep -A 30 'create_table "api_tokens"' db/schema.rb
```

Reading the schema first takes under a minute and prevents the entire class of errors described here.

---

## Conclusion

In Rails, models that require complex creation logic — hash computation, setting multiple columns simultaneously, enforcing business rules — should be wrapped in Service objects or Model class methods. Calling `create!` directly from a controller leads to missing required columns, bypassed business logic, and security gaps.

The lesson from this case is straightforward: check the schema before touching a model, and search for existing Service objects or helper methods before writing new creation logic. Most Rails projects already encapsulate complex domain logic somewhere. Finding and using it is faster than reinventing it, and safer than bypassing it.

When multiple controllers need to issue the same kind of token, a shared Service also guarantees consistency. If the token expiry policy or hashing algorithm ever changes, there is exactly one place to update.

---

## Key Takeaways

- `ActiveRecord::NotNullViolation` is raised when a database NOT NULL constraint is violated. The column name in the error message points directly to the problem — trace it in `db/schema.rb` to understand what value is expected.
- `ActiveRecord::UnknownAttributeError` is raised when a column name passed to `create!` does not exist in the schema. It is easy to confuse column names from other frameworks; always verify against the actual schema.
- Token creation logic that involves hash computation and multiple interdependent columns belongs in a Service object or Model class method — not in the controller. The controller should only call the service and render the result.
- Store SHA-256 hashes of tokens in the database, not the raw token strings. A compromised database cannot be used to reconstruct original tokens.
- `jti` (JWT ID) is a unique identifier per token record, enabling replay attack prevention and selective token revocation per session.
- Before working with any model, read the schema and search for existing Service objects. The fix is usually already written.
