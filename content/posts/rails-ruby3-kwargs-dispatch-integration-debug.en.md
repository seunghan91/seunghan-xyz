---
title: "A Day of Debugging — Ruby 3.0 kwargs, Docker env, NAS Cron, SSH Special Characters"
date: 2026-01-02
draft: false
tags: ["Rails", "Ruby", "Docker", "Synology", "NAS", "Deployment", "Debugging", "Cron"]
description: "Bugs encountered while integrating AI agents with Rails API: Ruby 3.0 keyword argument separation, Docker env_file reload issues, Synology NAS cron setup, and SSH heredoc special character issues."
cover:
  image: "/images/og/rails-ruby3-kwargs-dispatch-integration-debug.png"
  alt: "Rails Ruby3 Kwargs Dispatch Integration Debug"
  hidden: true
categories: ["Rails"]
---

I was building a dispatcher that lets an AI agent call a Rails API server to automatically assign tickets. The logic itself was straightforward, but the integration kept hitting unexpected walls. Over the course of one day, I ran into seven distinct bugs — each small on its own, but exhausting in rapid succession. I'm writing them down in hopes they save someone else the same frustration.

---

## 1. Ruby 3.0 kwargs Separation — Why Does `render_success(key: val)` Blow Up?

This one cost the most time. In a Rails controller, I was calling a response helper like this:

```ruby
render_success(tickets: tickets_list, pagination: pagination_data)
```

The error in the server log:

```
ArgumentError - unknown keywords: :tickets, :pagination
```

The helper is defined as:

```ruby
def render_success(data, status: :ok)
  render json: { success: true, data: data }, status: status
end
```

### Why Did Ruby 3.0 Change This?

In **Ruby 2.x**, calling `render_success(tickets: ..., pagination: ...)` would implicitly coerce `{tickets: ..., pagination: ...}` into the `data` positional argument. This was called the "last hash argument as keyword parameters" implicit conversion. Ruby would helpfully say: "these look like keyword syntax, but there's a positional slot waiting — I'll pack them into a hash."

**Ruby 3.0 removed this behavior entirely** (Ruby 2.7 first introduced a deprecation warning to give developers time to migrate). Keyword arguments and positional arguments are now completely separate. When `tickets:` and `pagination:` are passed, Ruby 3.0 treats them as keyword arguments. But `render_success` only declares `status:` as a keyword parameter — so `tickets:` and `pagination:` are unknown keywords, resulting in `ArgumentError`.

The same applies to a single key:

```ruby
render_success(ticket: ticket_json(@ticket))
# → ArgumentError: wrong number of arguments (given 0, expected 1)
```

`ticket:` is parsed as a keyword argument, so the `data` positional parameter receives nothing (0 arguments), triggering the error.

### Fix

Wrap the hash explicitly with `{}`. This makes Ruby unambiguously treat it as a hash literal rather than keyword arguments.

```ruby
# All calls need to be updated to this form
render_success({ ticket: ticket_json(@ticket) })
render_success({ tickets: tickets_list, pagination: pagination_data })
```

I swept the entire project's controllers looking for any `render_success(` call not immediately followed by `{` and fixed them all. For single-line patterns, `sed` handled the bulk:

```bash
sed -i '' \
  -e 's/render_success(ticket: \(.*\))/render_success({ ticket: \1 })/g' \
  -e 's/render_success(message: "\(.*\)")/render_success({ message: "\1" })/g' \
  app/controllers/api/v1/tickets_controller.rb
```

### Prevention

If you're still on Ruby 2.7, search your logs for `warning: Using the last argument as keyword parameters is deprecated`. Fixing those warnings now means the Ruby 3.0 upgrade won't break anything.

---

## 2. Docker `restart` Does Not Reload env_file

I added a new environment variable to the `.env` file and restarted the container:

```bash
docker compose restart
```

But checking inside the container showed the new variable was absent:

```bash
docker exec mycontainer python3 -c "import os; print(os.environ.get('NEW_VAR', 'MISSING'))"
# → MISSING
```

### Why

`docker compose restart` sends SIGTERM to the running process and starts it again — but inside the **same container**. It does not recreate the container. The `env_file` configuration is read only at container creation time. Once a container exists, its environment variables are fixed regardless of how many times you restart it.

You can verify this with `docker inspect <container>` — the `Env` section shows the environment as it was when the container was created, and it does not change after a restart.

### Fix

Recreate the container:

```bash
docker compose up -d
```

`up -d` compares the current `docker-compose.yml` configuration with the running containers and recreates any service whose configuration has changed. This is what actually re-reads `env_file`.

```
Container mycontainer  Recreate
Container mycontainer  Recreated
Container mycontainer  Starting
Container mycontainer  Started
```

### Force Recreate When Config Hasn't Changed

If the compose file itself hasn't changed but you still want to force a recreate:

```bash
docker compose up -d --force-recreate
```

Verify the variable is now present:

```bash
docker exec mycontainer env | grep NEW_VAR
```

---

## 3. Synology NAS Has No `crontab` Command

I wanted to run a Python script every 5 minutes on the NAS:

```bash
ssh user@nas "crontab -e"
# → crontab: command not found
```

### Why

Synology DSM is not a standard Linux distribution. The `crond` daemon is present and running, but the `crontab` user-space utility is not included. There is no per-user crontab management interface.

### Fix: Edit /etc/crontab Directly

You need to edit `/etc/crontab` directly. This is a system-level crontab file. Unlike per-user crontab files, it includes a "run-as user" column in each entry:

```bash
# /etc/crontab format: minute hour day month weekday user command
*/5    *    *    *    *    root    /usr/local/bin/docker exec mycontainer python3 /home/node/script.py >> /path/to/logs/script.log 2>&1
```

Points to watch:
- Field separator is technically a **tab**, but spaces work too
- The **user column** (`root`) is required — standard per-user crontabs omit this
- Editing requires **sudo** access
- `/etc/crontab` **may be overwritten by DSM updates**. For anything mission-critical, back it up separately or use DSM's built-in Task Scheduler (Control Panel > Task Scheduler), which survives updates.

### Reload After Editing

In many cases `crond` auto-detects changes to `/etc/crontab`, but to be sure:

```bash
sudo synoservicectl --restart crond
```

---

## 4. `!` Characters Break SSH Heredocs

I wanted to run a short Ruby snippet on the server via Rails runner:

```bash
ssh user@server 'bundle exec rails runner "record.update!(key: value)"'
```

This kept failing. The `!` in `update!` is the culprit — in interactive bash, `!` triggers history expansion.

### Why It Happens Even Inside Single Quotes

In normal interactive bash, single quotes prevent most special character interpretation. But when passing commands through SSH, you're effectively dealing with two layers of shell parsing: the local shell that builds the command string, and the remote shell that receives and executes it. In interactive shells with history expansion enabled (`set -H`, which is the default), `!` can be misinterpreted even inside quoted strings depending on context.

With heredocs it gets worse:

```bash
# heredoc turns update! into update\! which is a Ruby syntax error
ssh user@server << 'EOF'
  record.update!(key: value)
EOF
```

### Fix 1: Avoid Bang Methods

Replace bang methods with their non-bang equivalents. Rails provides alternatives for all common bang operations:

```ruby
record.update_columns(key: value)   # instead of update!
record.save(validate: false)        # instead of save!
```

`update_columns` bypasses callbacks and validations and issues a direct `UPDATE` SQL statement. For one-off data fix scripts, this is often exactly what you want.

### Fix 2: Write the Script to a File First

For complex snippets, use Python to write the Ruby code to a temp file on the server, then execute it:

```bash
# Write the file via Python (handles ! without issue)
ssh user@server "python3 -c \"
with open('/tmp/fix.rb', 'w') as f:
    f.write('''
k = Model.find_by(token: \\\"TOKEN\\\")
k.update_columns(permissions: k.permissions | [\\\"new_perm\\\"])
puts k.reload.permissions.inspect
''')
\""

# Then run it
ssh user@server 'bundle exec rails runner /tmp/fix.rb'
```

### Fix 3: bash -s Pattern

Another option is piping the script via stdin:

```bash
ssh user@server bash -s << 'SCRIPT'
cd /app && bundle exec rails runner - << 'RUBY'
puts "Hello from Rails"
RUBY
SCRIPT
```

---

## 5. SCP/SFTP Blocked by Permissions — base64 Workaround

Trying to upload a file to the NAS:

```bash
scp script.py user@nas:/path/to/dir/
# → scp: /path/to/dir/script.py: Permission denied
```

The directory was owned by root, so the regular SSH account had no write access via SCP. Running `chmod` in a separate SSH session didn't take effect immediately.

### Why SCP Can't Use sudo

SCP and SFTP operate through a separate subsystem (`sftp-server`). Unlike a regular SSH shell session, this subsystem does not support privilege escalation via `sudo`. If the destination directory is not writable by your user, there is no way to use SCP or SFTP to write there — regardless of what `sudo` permissions your account has.

### Workaround: SSH + base64

Send the file using only SSH shell commands, which do support `sudo`:

```bash
base64 script.py | ssh user@nas "base64 -d | sudo tee /path/to/dir/script.py > /dev/null"
```

Or capture the base64 content first and echo it:

```bash
CONTENT=$(base64 < script.py)
ssh user@nas "echo '$CONTENT' | base64 -d | sudo tee /path/to/dir/script.py"
```

### Caveats

base64 encoding inflates file size by roughly 33%. This approach is fine for scripts and config files, but not for large binaries or media files. For large files, the right fix is to correct the directory permissions (`chmod`/`chown`) rather than working around them.

---

## 6. `update_column` vs `update_columns` — PostgreSQL Array Columns

During a data migration, I was trying to update a PostgreSQL array-type column:

```ruby
record.update_column(:permissions, record.permissions + ['new_perm'])
```

This caused problems.

### The Difference Between update_column and update_columns

`update_column` (singular) updates a single column directly in the database, skipping callbacks and validations. When you pass a Ruby `Array` to it, the `pg` driver has to serialize it to PostgreSQL's `text[]` format. In some versions and configurations, this serialization is unreliable for array values.

`update_columns` (plural) is more robust and the preferred approach:

```ruby
new_perms = (record.permissions || []) | ['new_perm']
record.update_columns(permissions: new_perms)
```

### Using `|` Instead of `+`

The `|` operator performs a set union — it merges two arrays without duplicates:

```ruby
['admin', 'read'] | ['read', 'write']  # → ['admin', 'read', 'write']
['admin', 'read'] + ['read', 'write']  # → ['admin', 'read', 'read', 'write']
```

For a permissions list, duplicates are meaningless or harmful, so `|` is the right operator.

### Guard Against nil

If the column might be `nil` for older records (e.g., `default: []` wasn't set in the migration):

```ruby
new_perms = (record.permissions || []) | ['new_perm']
```

Always guard with `|| []` to avoid `NoMethodError: undefined method '|' for nil`.

---

## 7. `wip_count` Was a Computed Field, Not a DB Column

The user model had a `wip_count` attribute, so I tried to reset it with `update_columns`:

```ruby
user.update_columns(wip_count: 0)
```

Error:

```
can't write unknown attribute 'wip_count'
```

### Why

It was not a database column at all — it was a Ruby method:

```ruby
def wip_count
  assigned_tickets.where(aasm_state: %w[assigned in_progress]).count
end
```

This is a computed (derived) field that counts the user's currently active tickets in real time. It only exists as a method on the model class, not as a column in the database. You cannot write to it with `update_columns` because there is no corresponding column in the `UPDATE` SQL statement.

### Fix

To change the effective value of `wip_count`, you need to change the underlying tickets' states, or adjust the related `max_wip` column that controls how many tickets the user is allowed to hold:

```ruby
# wip_count itself is read-only; increase max_wip to allow more tickets
user.update_columns(max_wip: 20)
```

### Quick Way to Check

When unsure whether an attribute is a DB column or a computed method:

```ruby
# In Rails console
User.column_names.include?('wip_count')  # false → it's a method, not a column
User.columns_hash['wip_count']            # nil → not in the database
```

Or just search `db/schema.rb` — if it's not there, it's not a column.

---

## Summary

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `render_success(key: val)` raises ArgumentError | Ruby 3.0 kwargs/positional separation | Wrap explicitly with `{}` |
| Docker env vars not updated after restart | `restart` does not recreate the container | Use `up -d` to recreate |
| NAS `crontab` command not found | Synology DSM doesn't ship `crontab` | Edit `/etc/crontab` directly |
| SSH heredoc `!` causes Ruby syntax error | bash history expansion | Use `update_columns` and other non-bang methods |
| SCP Permission denied | Root-owned directory, no sudo via SFTP | base64 encode and pipe through SSH + tee |
| PostgreSQL array column update fails | `update_column` serialization inconsistency | Use `update_columns` with `|` operator |
| `update_columns` fails on `wip_count` | Mistook a computed field for a DB column | Check schema.rb; adjust `max_wip` instead |

---

## Key Takeaways

- **Ruby 3.0 kwargs separation is a silent time bomb.** Any codebase upgraded from Ruby 2.x that uses `render_success(key: val)` or similar helper patterns will break without warning at runtime. Run a project-wide grep for `render_success(` not immediately followed by `{` before upgrading.
- **Docker environment variables are locked at container creation time.** `restart` keeps the old environment. `up -d` recreates and picks up the new values. This distinction also matters in CI/CD pipelines.
- **Synology NAS is not standard Linux.** Familiar tools like `crontab`, `apt`, and `systemctl` are absent or work differently. Always check DSM-specific documentation first.
- **SSH + `!` is always dangerous.** When executing Rails bang methods (`update!`, `save!`) via SSH, either switch to non-bang alternatives (`update_columns`, `save(validate: false)`) or write the code to a file first.
- **Always verify whether an attribute is a DB column or a computed field** before trying to write it. A quick check of `schema.rb` or `column_names` saves a confusing `can't write unknown attribute` error.
