---
title: "Rails Turbo Stream 500 Error Triple Debugging — broadcast, SolidCable, Telegram Markdown"
date: 2026-01-09
draft: false
tags: ["Rails", "Turbo", "ActionCable", "SolidCable", "Telegram", "Debugging", "Ruby"]
description: "When broadcast_append_to 500 errors, SolidCable missing tables, and Telegram Markdown parsing errors all hit at once in Rails 8 + Turbo Stream — how to find and fix each cause."
cover:
  image: "/images/og/rails-turbo-actioncable-500-debug.png"
  alt: "Rails Turbo Actioncable 500 Debug"
  hidden: true
categories: ["Rails", "Hotwire"]
---

When running a Rails 8 + Hotwire (Turbo) application in production, `broadcast_append_to` callbacks can silently throw 500 errors. When that's compounded by a SolidCable setup issue and Telegram Bot message parsing errors, interpreting the logs becomes genuinely confusing. All three hit at the same time in a recent project — here's how each one was diagnosed and resolved.

These three problems are independent of each other, but in practice they tend to surface together in a freshly deployed Rails 8 app. The key is to isolate each problem and fix them one at a time.

---

## Problem 1: `No unique index found for id` — broadcast callback 500

### Symptoms

A 500 error fires from the controller when creating a message or notification. The log shows:

```
MessagesController#create error: No unique index found for id
```

The error message reads like an index problem, but that's misleading. What's actually happening is that an exception thrown inside an ActionCable broadcast is propagating all the way up to the controller. The record itself has already been saved to the database successfully.

### Cause

When `broadcast_append_to` is called inside an `after_create_commit` callback, it internally delivers a message through an ActionCable channel. If anything goes wrong during that delivery — especially when SolidCable is not fully configured — an exception is raised.

The critical issue is that **exceptions inside callbacks propagate up to the controller level**. The `create!` has already succeeded and the record is in the database, but the broadcast callback failure causes the controller to return a 500.

Rails' `after_create_commit` runs after the transaction commits. At that point, an exception cannot roll back the database record. However, Rails does not catch exceptions in the callback chain — it lets them propagate to the caller. The result is a user-visible 500 error even though the data was saved correctly. This is a confusing and misleading failure mode.

### Model code (before fix)

```ruby
class Message < ApplicationRecord
  after_create_commit :broadcast_message

  def broadcast_message
    broadcast_append_to(
      "conversation_#{conversation_id}",
      target: "messages",
      partial: "messages/message",
      locals: { message: self }
    )
  end
end
```

### Fix

Add a `rescue` block inside `broadcast_message`. A broadcast failure is not fatal — the record is already saved, and the client will receive the latest state on the next poll or page navigation.

```ruby
def broadcast_message
  broadcast_append_to(
    "conversation_#{conversation_id}",
    target: "messages",
    partial: "messages/message",
    locals: { message: self }
  )
rescue => e
  Rails.logger.error "[Message] broadcast_message failed: #{e.message}"
end
```

The `Notification` model's `broadcast_to_user` callback was fixed with the same pattern:

```ruby
def broadcast_to_user
  broadcast_append_to(...)
  broadcast_replace_to(...)
rescue => e
  Rails.logger.error "[Notification] broadcast_to_user failed: #{e.message}"
end
```

> **Core principle**: Broadcast callbacks inside `after_create_commit` are side effects. A failure must not roll back the transaction or return a 500. Always wrap them in a rescue.

### Going further: retries and monitoring

Simply swallowing the error with rescue is a start, but for production applications consider the following:

**Retry logic**: If failures are due to transient network issues or SolidCable queue delays, queuing a background job to retry the broadcast is a valid pattern.

```ruby
def broadcast_message
  broadcast_append_to(
    "conversation_#{conversation_id}",
    target: "messages",
    partial: "messages/message",
    locals: { message: self }
  )
rescue => e
  Rails.logger.error "[Message] broadcast_message failed: #{e.message}"
  # Queue a retry job if needed
  # BroadcastRetryJob.perform_later(self.class.name, id)
end
```

**Error monitoring**: If you use Sentry or a similar error tracking service, reporting broadcast failures at warning level lets you track trends. Frequent broadcast failures are an early signal of SolidCable configuration issues or database load problems.

---

## Problem 2: `PG::UndefinedTable — solid_cable_messages` table missing

### Symptoms

The following error appears repeatedly in the logs:

```
PG::UndefinedTable: ERROR: relation "solid_cable_messages" does not exist
```

ActionCable connections establish successfully, but message delivery fails and this error floods the logs.

### What is SolidCable?

SolidCable is a new library introduced in Rails 8 that allows PostgreSQL (or another relational database) to serve as the ActionCable adapter — eliminating the need for Redis. The goal is to simplify infrastructure by reducing the number of external services required.

SolidCable stores messages in a dedicated `solid_cable_messages` table and delivers them to subscribers via polling. If this table does not exist, ActionCable broadcasts fail entirely.

### Cause

In Rails 8, SolidCable uses a separate migration path (`db/cable_migrate/`). The `database.yml` configuration looks like this:

```yaml
production:
  primary:
    url: <%= ENV["DATABASE_URL"] %>
  cable:
    <<: *primary_production
    migrations_paths: db/cable_migrate
```

Even if the `cable` database points to the same URL as `primary`, migrations inside `db/cable_migrate/` may not run when you execute the standard `rails db:migrate`. On PaaS platforms like Render, if the deploy hook only runs `rails db:migrate`, the cable migrations are skipped.

This happens because of how Rails handles multi-database migrations. By default, `db:migrate` looks at `db/migrate/` only. Databases with a custom `migrations_paths` require a separate migration command to pick up their migrations.

### How to check

```bash
rails db:migrate:status
```

Look for the `solid_cable_messages` migration showing as `down`:

```
down    20241001000000  CreateSolidCableMessages
```

### Solution

```bash
rails db:migrate RAILS_ENV=production
```

In Rails 7+, `db:migrate` should migrate all databases in a multi-database setup, but in practice you need to verify that the files in `db/cable_migrate` are actually processed. If they are not, run:

```bash
rails db:migrate:cable RAILS_ENV=production
# or
rails db:migrate DATABASE=cable RAILS_ENV=production
```

### Updating the deploy script

On PaaS platforms such as Render, Fly.io, or Heroku, the deploy command needs to be updated explicitly.

**For Render** (`render.yaml`):

```yaml
services:
  - type: web
    name: myapp
    buildCommand: bundle install && bundle exec rails assets:precompile
    startCommand: bundle exec rails db:migrate && bundle exec rails db:migrate DATABASE=cable && bundle exec rails server
```

Or create a `bin/render-build.sh` script:

```bash
#!/usr/bin/env bash
set -o errexit

bundle install
bundle exec rails assets:precompile
bundle exec rails assets:clean
bundle exec rails db:migrate
bundle exec rails db:migrate DATABASE=cable
```

Always verify that the migration files exist in `db/cable_migrate/` and that the deploy script actually executes them.

### Watch out for confusion with SolidQueue

Rails 8 ships with three Solid libraries, each with its own migration path:

- SolidCable: `db/cable_migrate/`
- SolidQueue: `db/queue_migrate/`
- SolidCache: `db/cache_migrate/`

If you use all three, the deploy script must include all three migration commands.

---

## Problem 3: Raw escape characters `\(`, `\.`, `\-` appearing in Telegram messages

### Symptoms

Messages received via the Telegram Bot show raw escape characters like this:

```
Applicant: seunghan \(seunghan@example\.co\.kr\)
Requested amount: 20000
```

Expected output:
```
Applicant: seunghan (seunghan@example.co.kr)
Requested amount: 20,000 KRW
```

There were two separate issues:
1. MarkdownV2 escape sequences like `\(`, `\.`, `\-` were being rendered literally in Telegram
2. Raw metadata keys like `desired_amount: 20000` were appearing instead of human-readable labels with formatted numbers

### Understanding Telegram Markdown versions

The Telegram Bot API supports two Markdown parsing modes:

**Markdown (v1)**: The older format. Supports `*bold*`, `_italic_`, `` `code` ``, but has no escape syntax. The backslash in `\(` is not treated as an escape character — it is printed as-is.

**MarkdownV2**: The currently recommended format. All special characters (`. ( ) [ ] { } ~ > # + - = | ! \`) must be escaped with a backslash. Any unescaped special character causes a 400 error from the API.

### Cause

The application was internally building descriptions in **MarkdownV2 format** (with `\(`, `\.`, etc. as escapes), then sending those descriptions to Telegram using `parse_mode: 'Markdown'` (v1).

Since Markdown v1 does not recognize backslash escapes, the backslashes are printed literally. Switching to `parse_mode: 'MarkdownV2'` would fix the backslash issue, but only if the entire message content strictly conforms to MarkdownV2 spec — any non-escaped special character in the content will cause a 400 error.

Three options are available:
1. Send without `parse_mode` (plain text) — no Markdown rendering at all
2. Switch to `parse_mode: 'MarkdownV2'` and ensure the entire message content is properly escaped
3. Strip all Markdown before sending and use plain text

For notification messages that do not need bold text or links, option 3 is the simplest and most robust.

### Solution: strip Markdown with a plain_text helper

Since Telegram notification messages do not require Markdown formatting, a `plain_text` helper strips all Markdown before sending:

```ruby
def self.plain_text(text)
  text.to_s
      .gsub(/\*\*(.*?)\*\*/m, '\1')   # remove **bold**
      .gsub(/\*(.*?)\*/m, '\1')        # remove *italic*
      .gsub(/\\([_*\[\]()~`>#+=|{}.!\-])/, '\1')  # remove MarkdownV2 escapes
      .strip
end
```

Update the notification send call accordingly:

```ruby
# Before
desc = escape(ticket.description.to_s.truncate(200))

# After
desc = plain_text(ticket.description.to_s.truncate(300))
```

Remove the `parse_mode` option as well, or omit it entirely. Without `parse_mode`, Telegram treats the message as plain text.

### Solution: human-readable metadata labels and amount formatting

The problem of raw keys like `desired_amount: 20000` was fixed by adding a label mapping at the description-building stage:

```ruby
METADATA_LABELS = {
  "desired_amount" => "Requested amount",
  "current_amount" => "Current amount",
  "target_amount"  => "Target amount",
  "quota"          => "Quota",
  "target_date"    => "Target date",
  "department"     => "Department",
  "system"         => "Target system",
  "priority"       => "Priority"
}.freeze

def build_description
  lines = []
  # ...
  @sr.metadata.each do |k, v|
    label = METADATA_LABELS[k.to_s] || k.to_s.gsub("_", " ").capitalize
    value = k.to_s.include?("amount") ? format_amount(v) : v
    lines << "- #{label}: #{value}"
  end
  lines.join("\n")
end

def format_amount(v)
  num = v.to_s.gsub(/[^0-9]/, "").to_i
  "#{num.to_s.reverse.gsub(/(\d{3})(?=\d)/, '\1,').reverse} KRW"
end
```

`20000` becomes `20,000 KRW`.

### Mind the Telegram message length limit

The Telegram Bot API enforces a 4096-character limit per message. `truncate(300)` is well within range, but if metadata is extensive or descriptions are long, verify the total assembled message does not exceed 4096 characters. Exceeding it results in a `400 Bad Request: message is too long` error from the API.

---

## Summary

| Problem | Cause | Fix |
|---------|-------|-----|
| `No unique index found for id` 500 | Broadcast exception inside `after_create_commit` propagates to the controller | Add `rescue` inside the callback |
| `solid_cable_messages` table missing | `db/cable_migrate` not run during deploy | Run `rails db:migrate DATABASE=cable` explicitly |
| Telegram escape characters shown literally | MarkdownV2 escapes sent with `parse_mode: 'Markdown'` (v1) | Strip all Markdown with a `plain_text` helper before sending |
| Raw metadata keys in messages | Key names rendered without labels or formatting | Add `METADATA_LABELS` mapping and `format_amount` formatter |

Broadcast callback errors are more common than expected in Rails + Turbo setups. Incomplete ActionCable/SolidCable configuration and missing multi-database migrations are the most frequent culprits. Get into the habit of isolating side effects inside `after_create_commit` with a rescue block.

---

## Key Takeaways

1. **Always wrap broadcasts inside `after_create_commit` with `rescue`.** Broadcasts are side effects. A failure must not roll back the main transaction or cause a 500 response to the user.

2. **SolidCable (and SolidQueue, SolidCache) uses a separate migration path.** Migrations in `db/cable_migrate/` may not run with a plain `rails db:migrate`. Add `rails db:migrate DATABASE=cable` explicitly to your PaaS deploy script.

3. **Telegram MarkdownV2 and Markdown v1 follow completely different parsing rules.** Mixing internally-formatted MarkdownV2 content with a v1 `parse_mode` causes escape characters to appear literally. For notification messages, stripping all Markdown and sending plain text is the safest approach.

4. **Do not read error messages at face value.** `No unique index found for id` was not an index problem — it was an ActionCable internal exception propagating upward. You need the full stack trace to find the real cause.

5. **If you use all three Rails 8 Solid libraries (SolidCable, SolidQueue, SolidCache), include all three migration commands in your deploy script.** Each watches a different path: `db/cable_migrate/`, `db/queue_migrate/`, and `db/cache_migrate/`.
