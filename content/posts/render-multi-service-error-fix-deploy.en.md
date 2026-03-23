---
title: "Render 6 Service Error Bulk Fix — Stoplight, FK Constraints, Puma 7, Solid Stack Debugging"
date: 2026-02-24
draft: false
tags: ["Rails", "Render", "Stoplight", "Telegram", "Puma", "PostgreSQL", "SolidCache", "SolidQueue", "Debugging", "Deployment"]
description: "Bulk log inspection of 6 Rails 8 services on Render, fixing Stoplight 5.x compatibility, Telegram parse_mode, solid_cache schema, FK constraint violations, Puma 7 deprecated API, and more."
cover:
  image: "/images/og/render-multi-service-error-fix-deploy.png"
  alt: "Render Multi Service Error Fix Deploy"
  hidden: true
categories: ["Rails", "DevOps"]
---

Six Rails services deployed on Render were all throwing different errors at the same time. Going through the logs one by one revealed both common patterns and service-specific issues. This post documents how all of them were fixed and deployed within a single session.

---

## Overview

Instead of SSH-ing into each service individually, I used the Render API to pull logs from all six services at once via a local script. The results:

| Service | Primary Error |
|---------|---------------|
| Service A | ERB syntax error causing 500s (code was committed but never deployed) |
| Service B | Stoplight `Light#run` block error + Telegram parsing error |
| Service C | `solid_cache_entries` table missing |
| Service D | `PG::UndefinedColumn` + solid_cache table missing |
| Service E | `PG::DuplicateTable` on sessions + Sentry initialization error |
| Service F | `TaskCleanupJob` FK violation + Puma deprecated callback warnings |

**Common pattern**: Rails 8's Solid Stack (SolidCache, SolidQueue, SolidCable) initial setup was broken across multiple projects. The root cause was using a single PostgreSQL instance on Render's free/starter plan while Solid Stack's install generator assumes a multi-database configuration.

---

## Problem 1: Stoplight 5.x API Change — Block Passing in `Light#run`

### Symptom

```
BizRouter API Error: nothing to run. Please, pass a block into `Light#run`
```

Occurring every 5 minutes. Every external API call was failing, taking down all endpoints that communicate with third-party services.

### Cause

Stoplight is a circuit breaker library for Ruby. When external API calls fail repeatedly, it opens the circuit and stops attempting calls for a cooldown period, then allows a probe request to test recovery. In Stoplight 5.x, the way you pass a block changed. The old pattern no longer works:

```ruby
# Stoplight 4.x (old pattern) — no longer works
Stoplight('api-call') {
  HTTParty.get(url)
}.run

# Stoplight 5.x (new pattern) — block goes to .run
Stoplight('api-call').run {
  HTTParty.get(url)
}
```

The difference is subtle. In 5.x, a block passed to `Stoplight()` is silently ignored, and the block must be passed to `.run` instead. The error message spells this out exactly, but when you're looking at it for the first time it's confusing — you passed a block, so why is it complaining? If you updated the gem without checking the changelog, this is exactly the kind of breaking change you'd miss.

### Fix

```ruby
# Before
def call_api(path, params = {})
  Stoplight("biz-router-#{path}") {
    connection.get(path, params)
  }.run
end

# After
def call_api(path, params = {})
  Stoplight("biz-router-#{path}").run {
    connection.get(path, params)
  }
end
```

This single change brought all external API calls back to normal. One line of code, wide blast radius.

**Takeaway**: Whenever you update a circuit breaker library, always check whether the block-passing convention changed. Stoplight 5.x documents this in the CHANGELOG, but it's easy to miss until something breaks in production.

---

## Problem 2: Telegram Bot MarkdownV2 Parsing Hell

### Symptom

```
Telegram API error: Bad Request: can't parse entities:
Can't find end of the entity starting at byte offset 395
```

Every time a notification job ran, Telegram message delivery failed. The `byte offset` number in the error changed with each occurrence because it depends on the content of the message — specifically, whatever the user had typed into a task title or note.

### Cause

The code was using `parse_mode: 'Markdown'` (Telegram's legacy Markdown mode), and any message containing characters like `_`, `.`, `(`, or `)` would cause a parse failure. Since these characters appear naturally in user-generated content, the failure was essentially unavoidable.

Switching to MarkdownV2 makes things worse, not better. MarkdownV2 requires escaping 18 characters: `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, and `!`. Reliably escaping all of these in dynamically assembled messages is nearly impossible in practice.

### Fix: Switch to HTML parse_mode

The correct solution is to **use HTML parse_mode**. Only three characters need escaping: `&`, `<`, and `>`.

```ruby
def self.escape(text)
  text.to_s
      .gsub('&', '&amp;')
      .gsub('<', '&lt;')
      .gsub('>', '&gt;')
end

def self.markdown_to_html(text)
  text.to_s
      .gsub('&', '&amp;').gsub('<', '&lt;').gsub('>', '&gt;')
      .gsub(/\\([_*\[\]()~`>#+=|{}.!\-])/, '\1')  # strip MD escape chars
      .gsub(/\*([^*]+?)\*/, '<b>\1</b>')
      .gsub(/`([^`]+?)`/, '<code>\1</code>')
end
```

And update every `send_message` call:

```ruby
bot.api.send_message(
  chat_id: chat_id,
  text: markdown_to_html(message),
  parse_mode: 'HTML'  # Markdown → HTML
)
```

In HTML mode, Telegram only interprets `<b>`, `<i>`, `<code>`, `<pre>`, and `<a>` tags. Everything else is treated as plain text. No matter how complex the user's input is, three substitutions are all it takes to make it safe.

**Takeaway**: Markdown and MarkdownV2 in Telegram bots are a maintenance trap when dealing with dynamic content. Start with HTML parse mode. The escaping rules are far simpler, and it handles user-generated text safely.

---

## Problem 3: Solid Stack Missing Tables — Multiple Projects

### Symptom

```
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

This hit three projects simultaneously. Services C, D, and E were all recently set up with Rails 8.

### Cause

Rails 8's `solid_cache` (1.0.x) manages its tables through a **schema file** (`db/cache_schema.rb`) rather than standard migration files. When you run `rails solid_cache:install`, it generates `config/cache.yml` and `db/cache_schema.rb`, but it does **not** create a `db/cache_migrate/` directory.

```
# What solid_cache:install creates
config/cache.yml
db/cache_schema.rb       ← schema definition

# What it does NOT create
db/cache_migrate/        ← does not exist
```

So running `bundle exec rails db:migrate:cache` in `bin/render-build.sh` does nothing — there are no migration files to run. The build succeeds without errors, but the table is never created. Every request then hits a 500 at runtime.

This design reflects Solid Stack's assumption of a multi-database configuration, where each component (cache, queue, cable) connects to a dedicated database. With a dedicated DB, loading the schema file is safe because it targets only that database. On Render's free/starter plan with a single shared PostgreSQL instance, this separation breaks down.

### Fix (two options)

**Option 1**: Use schema load in `render-build.sh`

```bash
# Before (does nothing)
bundle exec rails db:migrate:cache || true
bundle exec rails db:migrate:queue || true

# After (actually creates the tables)
SCHEMA=db/cache_schema.rb bundle exec rails db:schema:load || true
SCHEMA=db/queue_schema.rb bundle exec rails db:schema:load || true
```

**Option 2**: Manually create a migration in `db/cache_migrate/`

```ruby
# db/cache_migrate/20260306_create_solid_cache_entries.rb
class CreateSolidCacheEntries < ActiveRecord::Migration[8.0]
  def change
    create_table :solid_cache_entries, if_not_exists: true do |t|
      t.binary :key, null: false, limit: 1024
      t.binary :value, null: false, limit: 536870912
      t.datetime :created_at, null: false
      t.integer :key_hash, null: false, limit: 8
      t.integer :byte_size, null: false, limit: 4
      t.index :byte_size
      t.index :key_hash, unique: true
    end
  end
end
```

**When cache/queue/cable share the same DB as primary** (Render free/starter plan), Option 2 is safer. `db:schema:load` drops and recreates tables, which could wipe existing data. Option 2 uses `if_not_exists: true`, making it safe to run even when the table already exists.

**Takeaway**: Solid Stack is designed for multi-database setups. When using a single database, you need to create migration files manually. The official documentation only covers the multi-DB case, so this trip-up is common on budget hosting plans.

---

## Problem 4: TaskCleanupJob FK Constraint Violation

### Symptom

```
PG::ForeignKeyViolation: ERROR: update or delete on table "tasks"
violates foreign key constraint "fk_rails_d8a07e5092" on table "notifications"
```

This occurred in a job that permanently deletes soft-deleted tasks older than 30 days. Every run failed, and SolidQueue kept retrying, filling the error logs.

### Cause

The `Notification` model had `belongs_to :task` with a direct foreign key, but the `Task` model had no corresponding `has_many :notifications`. When the cleanup job tried to delete a task, PostgreSQL rejected it because `notifications` records still referenced that task via the FK.

Rails cascades dependent deletions based on declared associations. Without the `has_many` on `Task`, Rails had no instruction to clean up notifications first, so PostgreSQL's FK constraint enforcement stepped in and blocked the delete.

```ruby
# Task model (before) — missing notifications association
has_many :notification_schedules, as: :notifiable, dependent: :destroy
# has_many :notifications is absent
```

### Fix

```ruby
# Task model (after)
has_many :notifications, dependent: :destroy  # added
has_many :notification_schedules, as: :notifiable, dependent: :destroy
```

And change `destroy_all` to `delete_all` in the cleanup job:

```ruby
# Before: triggers callbacks, loads each record into memory
Notification.where(task_id: task.id).destroy_all

# After: single SQL DELETE, fast and reliable
Notification.where(notifiable_type: 'Task', notifiable_id: task.id)
            .or(Notification.where(task_id: task.id))
            .delete_all
```

For bulk deletion in a cleanup job, `destroy_all` is a bad choice even when it works. It instantiates each record as a Ruby object, runs all callbacks, and issues N individual `DELETE` queries. `delete_all` issues a single SQL statement — much faster and immune to FK timing issues.

**Takeaway**: If a model has `belongs_to :something`, always declare the inverse `has_many` on the other side with an appropriate `dependent:` option. Without it, FK violations will surface during deletion. For mass-delete jobs, prefer `delete_all` over `destroy_all` unless you specifically need callbacks to run.

---

## Problem 5: `find_each` Conflicts with `default_scope` Order

### Symptom

```
WARN: Scoped order is ignored, use :cursor with :order to configure custom order.
```

Logged every 5 minutes whenever the reminder job ran. Functionally it still worked, but the logs were noisy and the processing order was not what the code intended.

### Cause

The `Task` model had `default_scope { order(created_at: :desc) }`, but `find_each` internally forces `ORDER BY id ASC`. When the two conflict, Rails silently ignores the `default_scope` ordering and emits this warning.

`find_each` requires `id ASC` ordering because it uses cursor-based batching: each batch is fetched with `WHERE id > last_seen_id`. Any other ordering would break the pagination boundary logic. Rails cannot honor `default_scope`'s `ORDER BY` here, so it overrides it.

### Fix

```ruby
# Before
tasks_with_reminders.find_each do |task|

# After — explicitly reset the order
tasks_with_reminders.reorder(:id).find_each do |task|
```

`.reorder(:id)` discards all existing order clauses from the relation and applies `id ASC`. Calling it before `find_each` eliminates the warning and ensures correct batch iteration.

**Takeaway**: If a model has an `order` in `default_scope`, always add `.reorder(:id)` before `find_each` or `find_in_batches`. Better yet, avoid putting `order` in `default_scope` at all — it creates unpredictable behavior across many query contexts.

---

## Problem 6: Puma 7 Deprecated Callbacks

### Symptom

```
Use 'before_worker_boot', 'on_worker_boot' is deprecated and will be removed in v8
Use 'before_worker_shutdown', 'on_worker_shutdown' is deprecated and will be removed in v8
```

Logged on every server startup. Functionally fine now, but a ticking time bomb for when Puma 8 is adopted — the hooks would simply stop firing, breaking database connection pool management across workers.

### Background

Puma in clustered mode uses fork-based workers. Each worker needs to re-establish its own database connection after forking, and cleanly disconnect before shutting down. The lifecycle hooks that handle this were renamed in Puma 7.

### Fix

```ruby
# Before (Puma 6 and earlier)
on_worker_boot do
  ActiveRecord::Base.establish_connection
end
on_worker_shutdown do
  ActiveRecord::Base.connection_pool.disconnect!
end

# After (Puma 7+)
before_worker_boot do
  ActiveRecord::Base.establish_connection
end
before_worker_shutdown do
  ActiveRecord::Base.connection_pool.disconnect!
end
```

The behavior is identical — only the names changed. Fixing this before Puma 8 lands avoids a silent failure mode where workers share or lose database connections.

---

## Problem 7: Nested `<button>` Elements Are Invalid HTML

### Symptom (Vite build warning)

```
`<button>` cannot be a child of `<button>`.
When rendering this component on the server, the resulting HTML
will be modified by the browser, likely resulting in a hydration_mismatch warning
```

With Inertia.js SSR enabled, this warning can escalate into a hydration mismatch that breaks interactivity.

### Cause

In the notification list component, each list item was a `<button>` (clicking it navigated to the detail view), and inside each item there was a delete `<button>`. The HTML specification forbids nesting interactive elements this way.

When the browser encounters a `<button>` inside a `<button>`, it corrects the DOM by moving the inner button outside the outer one. This restructured DOM differs from the server-rendered HTML, causing Inertia's SSR hydration to detect a mismatch and potentially re-render the component from scratch on the client.

### Fix

Replace the inner button with a `<div role="button">` while preserving keyboard accessibility:

```svelte
<!-- Before -->
<button onclick={(e) => { e.stopPropagation(); onDelete(id); }}>
  Delete
</button>

<!-- After -->
<div
  role="button"
  tabindex="0"
  onclick={(e) => { e.stopPropagation(); onDelete(id); }}
  onkeydown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.stopPropagation();
      e.preventDefault();
      onDelete(id);
    }
  }}
>
  Delete
</div>
```

Adding `role="button"` makes the element semantically equivalent to a button for screen readers. `tabindex="0"` ensures it receives keyboard focus. Handling `Enter` and `Space` in `onkeydown` matches standard button behavior.

---

## Triggering Deployments via Render API

After committing and pushing all fixes, deployments were triggered through the Render API rather than clicking through the dashboard one service at a time:

```bash
curl -X POST "https://api.render.com/v1/services/${SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'
```

Services configured with `autoDeploy: no` do not deploy on push — they require an explicit API trigger. The `clearCache: "do_not_clear"` option reuses Docker layer cache, significantly reducing build time when only application code changed and dependencies are unchanged.

To verify each deployment succeeded:

```bash
curl -s "https://api.render.com/v1/services/${SERVICE_ID}/deploys?limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY"
```

The response includes a `status` field. When it reads `live`, the deploy is complete. The `build_started_at` and `finished_at` timestamps tell you the exact build duration.

---

## Summary

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Stoplight `Light#run` | Block passing position changed in 5.x | Use `Stoplight().run { }` pattern |
| Telegram parse error | MarkdownV2 escaping too complex for dynamic content | Switch to HTML parse_mode |
| solid_cache table missing | Schema-file based install, no migrations generated | Create migration manually or load schema |
| FK constraint violation | `has_many :notifications` not declared on Task | Add association + use `delete_all` |
| Scoped order warning | `default_scope` order conflicts with `find_each` | Add `.reorder(:id)` before `find_each` |
| Puma deprecated callbacks | Callback names changed in Puma 7 | Rename to `before_worker_boot/shutdown` |
| Nested buttons | HTML spec violation | Replace inner button with `div[role=button]` |

All seven errors across six services were fixed and deployed in a single session. The key enabler was **using the Render API to fetch logs in bulk** before touching any code. Getting a complete picture of every service's error state at once makes it possible to batch related fixes and avoid context-switching one service at a time.

---

## Key Takeaways

Several patterns emerged from this session that are worth applying across any Rails deployment on managed hosting.

**1. Read the CHANGELOG before upgrading gems**
Stoplight 5.x's block-passing change is a textbook breaking change — syntactically valid code silently stops working. One `bundle update stoplight` without reading the changelog can take down every external API call in production. Make CHANGELOG review a required step in any gem upgrade.

**2. Avoid Markdown in Telegram messages with dynamic content**
Whether Telegram, Slack, or any other messaging platform, if messages contain user-generated text, avoid parse modes with complex escaping rules. HTML mode in Telegram requires escaping only three characters and handles any content safely. Markdown-based failures tend to be invisible in test environments and only surface in production with specific user inputs.

**3. Solid Stack on a single database requires manual migration files**
Rails 8's Solid Stack defaults assume a multi-database configuration. On budget hosting plans like Render's free tier where all components share one database, the install generator's output is incomplete. After running `solid_cache:install` or `solid_queue:install`, verify that the tables actually get created during the build step — not just that the build command exits without error.

**4. Always declare both sides of an association**
If `Notification` has `belongs_to :task`, then `Task` must have `has_many :notifications` with a `dependent:` option. Missing the inverse declaration leaves Rails unable to manage child records during deletion, and the database's FK constraint enforcement becomes your runtime error reporter. This is a standard Rails convention that is easy to skip and painful to debug.

**5. For bulk deletion jobs, default to `delete_all` over `destroy_all`**
`destroy_all` loads every record, runs callbacks, and issues N SQL statements. For cleanup jobs that delete potentially hundreds or thousands of old records, this is both slow and fragile. `delete_all` issues a single SQL statement, skips callbacks, and sidesteps FK timing issues that can occur when callbacks trigger additional queries mid-transaction.

**6. Use the Render API to manage multiple services at scale**
Once you have more than two or three services on Render, the dashboard becomes a bottleneck. Log fetching, deploy triggering, and environment variable updates are all available through the Render REST API. Scripting these operations pays off quickly, especially when operating services with `autoDeploy: no` that require explicit deploy triggers for each release.
