---
title: "Production DB Missing Table: schema.rb and Migration File Mismatch Incident"
date: 2025-10-18
draft: false
tags: ["Rails", "PostgreSQL", "DevOps", "CI/CD", "Debugging", "Migration"]
description: "Incident where a table existed in schema.rb but the migration file was missing, so the table was never created in production DB. Root cause analysis and building 3 defense layers."
cover:
  image: "/images/og/rails-missing-migration-sessions-table.png"
  alt: "Rails Missing Migration Sessions Table"
  hidden: true
categories: ["Rails"]
---


I received a report that sign-up and login were completely broken. The app just repeated "An unexpected error occurred."

---

## Symptoms

- Sign-up attempt -> 500 Internal Server Error
- Login attempt -> same 500
- Health check API -> 200 OK, DB connection normal

The server was alive and DB was connected, but all authentication features were dead.

---

## Investigation Process

### Step 1: Check Server Status

SSH in and check the Rails environment.

```bash
rails runner "puts Rails.env"
# => production

rails runner "puts User.count"
# => 13
```

Server normal, DB connection normal, user data exists.

### Step 2: Call API Directly

```bash
# Sign-up test
curl -X POST https://api.example.com/api/v1/auth/registrations \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"01088887777","password":"test1234",...}'

# => {"error":"An error occurred during registration."}
# => HTTP 500
```

But checking the DB:

```bash
rails runner "puts User.find(14).phone_number"
# => 01088887777
```

**User was created but still 500?** Something in the post-processing after user creation was blowing up.

### Step 3: Code Trace

Sign-up flow:

```ruby
# 1. User creation -> OK
user = create_user!

# 2. Wallet creation -> OK
@wallet_service.create_wallet_for_user(user)

# 3. Session creation -> FAILS here
session = user.sessions.create!(
  ip_address: request.remote_ip,
  user_agent: request.user_agent,
  last_active_at: Time.current
)
```

### Step 4: Root Cause Found

```bash
rails runner "puts Session.column_names"
```

```
PG::UndefinedTable: ERROR: relation "sessions" does not exist
```

**The `sessions` table did not exist in the DB.**

---

## Why This Happened

### Key: Test Environment and Production Have Different DB Creation Methods

| Aspect | Test (RSpec/CI) | Production |
|--------|-----------------|------------|
| DB creation method | Full load from `schema.rb` | Sequential execution via `db:migrate` |
| sessions table | Exists in `schema.rb` so OK | Missing if migration file absent |

`schema.rb` had the sessions table perfectly defined:

```ruby
# db/schema.rb
create_table "sessions", force: :cascade do |t|
  t.bigint "user_id", null: false
  t.string "token", null: false
  t.string "ip_address"
  t.string "user_agent"
  t.datetime "last_active_at"
  t.timestamps
  t.index ["token"], unique: true
  t.index ["user_id"]
end
```

But the `create_sessions.rb` migration file **was not deployed** to the `db/migrate/` directory.

Tests always pass because they load `schema.rb` in its entirety. Production runs `db:migrate`, so if the migration file is missing, the table is never created.

### Timeline

```
1. sessions migration file created (local)
2. schema.rb updated (local db:migrate executed)
3. Tests pass (schema.rb-based so no problem)
4. Migration file omitted during deployment
5. Production: db:migrate runs -> no sessions migration -> table not created
6. All authentication features die
```

---

## Immediate Fix

Directly create the table on the production DB:

```ruby
rails runner '
ActiveRecord::Base.connection.create_table :sessions do |t|
  t.references :user, null: false, foreign_key: true
  t.string :token, null: false
  t.string :ip_address
  t.string :user_agent
  t.datetime :last_active_at
  t.timestamps
end
ActiveRecord::Base.connection.add_index :sessions, :token, unique: true
'
```

Sign-up/login immediately restored.

---

## Preventing Recurrence: 3 Defense Layers

### 1. Migration Integrity Verification in CI

Added a step to the CI pipeline that compares `db:migrate` results against `schema.rb`.

```yaml
# .github/workflows/ci.yml
- name: Verify migration integrity
  run: |
    # Dump schema from db:migrate
    bundle exec rails db:schema:dump
    cp db/schema.rb /tmp/schema_from_migrate.rb

    # Restore committed schema.rb
    git checkout db/schema.rb

    # Structural line comparison
    if diff <(grep -E '^\s+(create_table|add_foreign_key|t\.)' db/schema.rb | sort) \
             <(grep -E '^\s+(create_table|add_foreign_key|t\.)' /tmp/schema_from_migrate.rb | sort); then
      echo "Migration and schema.rb match"
    else
      echo "Mismatch detected!"
      exit 1
    fi
```

This catches tables that exist in schema.rb but cannot be created through migrations at the PR stage.

### 2. Post-Deployment Smoke Test

Automatically call critical API endpoints after deployment:

```yaml
# Runs automatically after deployment
- name: Smoke Test
  run: |
    # Health check
    curl -sf https://api.example.com/health | jq '.database_connected'

    # Registration API (fail on 500)
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST https://api.example.com/api/v1/auth/registrations \
      -H "Content-Type: application/json" \
      -d '{"phone_number":"01000009999","password":"test1234",...}')

    if [ "$STATUS" = "500" ]; then
      echo "Registration API 500 error - possible missing DB table"
      exit 1
    fi

    # Verify login API the same way
```

200/401/422 are all normal operation (regardless of success/failure). **Only 500 needs to be caught.**

### 3. Table Existence Verification Before Server Start

Create a Rake task to run before server startup:

```ruby
# lib/tasks/db_integrity.rake
namespace :db do
  task check_tables: :environment do
    schema_content = File.read(Rails.root.join("db", "schema.rb"))
    schema_tables = schema_content.scan(/create_table "(\w+)"/).flatten
    actual_tables = ActiveRecord::Base.connection.tables
    missing = schema_tables - actual_tables

    if missing.any?
      puts "Missing tables: #{missing.join(', ')}"
      exit 1  # Block server start
    end
  end
end
```

Run before puma starts in the deployment configuration:

```yaml
startCommand: >
  bundle exec rake db:migrate &&
  bundle exec rake db:check_tables &&
  bundle exec puma -C config/puma.rb
```

If even one table is missing, **the server does not start at all**. Better than receiving traffic in an incomplete state.

---

## Lessons Learned

### schema.rb Is "Current State," Migrations Are "Process"

- `schema.rb`: A snapshot of the current local DB state
- `db/migrate/`: Step-by-step instructions to reach the current state from an empty DB

If these two are not synchronized, ghost bugs appear that work fine locally/in tests but break only in production.

### Passing Tests Does Not Guarantee Safety

Rails' test DB setup (`maintain_test_schema!`) operates based on `schema.rb`. It does not verify whether migration files exist.

You must always be aware that **"the DB creation paths for test and production environments are different."**

### Defense in Depth

| Defense Layer | Timing | Role |
|---------------|--------|------|
| CI migration verification | PR/Push | Detect schema.rb <-> migration mismatch |
| Pre-start verification | Deployment | Block startup if tables are missing |
| Smoke test | Post-deployment | Verify actual API behavior |

Even if one layer is breached, another layer catches it.

---

## Local Verification Method

Creating a full consistency verification rake task is also convenient:

```bash
bundle exec rails db:verify_schema_consistency RAILS_ENV=test
```

Creates a temporary DB, builds the schema using only migrations, and compares against `schema.rb` at the table/column/FK level. Works the same in CI and locally.

```
=== Migration <-> schema.rb Consistency Verification ===
1. Create temporary database
2. Run all migrations
3. Compare schemas
Migration and schema.rb are fully consistent.
```
