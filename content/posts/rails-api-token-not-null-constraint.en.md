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

After Apple Sign In / Google Sign In, the server needs to issue access tokens and refresh tokens and return them to the client. I tried creating them directly in the controller:

```ruby
token = user.api_tokens.create!(
  token_type: "bearer",
  expires_at: 1.hour.from_now
)
```

---

## Error

```
ActiveRecord::NotNullViolation:
PG::NotNullViolation: ERROR: null value in column "token_digest"
violates not-null constraint
```

---

## Cause

Checking the actual schema of the `api_tokens` table revealed these columns were defined as `NOT NULL`:

```ruby
# db/schema.rb
create_table "api_tokens" do |t|
  t.string   "token_digest",         null: false  # SHA-256 hash value
  t.string   "refresh_token_digest", null: false  # refresh token hash value
  t.datetime "refresh_expires_at",   null: false  # refresh expiration time
  t.string   "jti",                  null: false  # JWT ID (duplicate prevention)
  # ...
end
```

Calling `create!` directly does not automatically populate these columns.

Additionally, the `token_type` column did not exist in the schema, causing an `unknown attribute 'token_type'` error as well.

---

## Solution: Use a Service Object

A Service object (`ApiTokenService`) containing the token creation logic had already been implemented. The controller should go through the service rather than directly manipulating the model.

```ruby
# Wrong approach
token = user.api_tokens.create!(token_type: "bearer", ...)

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
- Generating the raw token string (delivered to the client)
- Computing the SHA-256 hash and storing it in `token_digest` (only the hash is stored in DB)
- Processing the refresh token in the same manner
- Automatically setting required columns like `jti`, `expires_at`, `refresh_expires_at`

---

## Why Not Store Raw Tokens in the Database

If raw tokens are stored directly in the database, all user tokens are exposed when the DB is compromised.

Storing SHA-256 hashes means:
- When a client sends a token, the server hashes it and compares against the DB
- If the DB is compromised, original tokens cannot be reverse-engineered from hash values
- Same principle as password hashing (though using SHA-256 instead of bcrypt)

```ruby
# During verification
digest = Digest::SHA256.hexdigest(raw_token)
token = ApiToken.find_by(token_digest: digest)
```

---

## Conclusion

In Rails, models that require complex creation logic (hash computation, setting multiple columns simultaneously, etc.) should be wrapped in Service objects or Model class methods. Directly calling `create!` from controllers leads to problems like missing required columns or bypassing business logic.

When other controllers need to issue the same tokens, reusing the Service guarantees consistency.
