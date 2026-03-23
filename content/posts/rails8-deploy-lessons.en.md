---
title: "5 Issues from First Rails 8 Deployment: Security, Migration, Compatibility"
date: 2025-11-11
draft: false
tags: ["Rails 8", "Render", "Solid Queue", "Sentry", "Deployment", "Security", "Debugging"]
description: "5 issues from first cloud deployment of a Rails 8 project: security file leak, database.yml removal mistake, Solid Suite multi-DB migration omission, Sentry compatibility error, and image_processing warning."
cover:
  image: "/images/og/rails8-deploy-lessons.png"
  alt: "Rails8 Deploy Lessons"
  hidden: true
categories: ["Rails"]
---

During the first cloud deployment of a Rails 8 project, I ran into five separate problems in a single day. Each one looked independent at the time, but the pattern was clear: fix one issue and the next one surfaces. Rails 8's newly introduced Solid Suite with its multi-database structure added extra unfamiliarity even for seasoned Rails developers. Here is a chronological account of what went wrong and how each issue was resolved.

---

## 1. Sensitive Files Committed to a Public Repository

### Symptoms

While doing a pre-deployment security check, I found sensitive files buried in the git history. Even if they are absent from the current HEAD, they remain accessible to anyone who can browse past commits.

```bash
# Check whether sensitive files exist anywhere in history
git log --all --full-history -- config/secrets.yml
git log --all --full-history -- "*.keystore"
git log --all --full-history -- "*.pem"
```

In this case, an old commit contained a `config/secrets.yml` file with a hardcoded `secret_key_base`, as well as an Android release keystore. Deleting the file from HEAD does nothing to remove it from history — the entire history must be rewritten.

### Solution: Purge from History with git filter-repo

`git filter-branch` is outdated and slow. The currently recommended tool is `git-filter-repo`.

```bash
pip install git-filter-repo

# Remove specific files from the entire git history
git filter-repo --path config/secrets.yml --invert-paths
git filter-repo --path app-release.keystore --invert-paths

# Force push the rewritten history
git push origin main --force
```

> **Warning**: `--force` on a shared repository requires advance notice to the whole team. Since history is rewritten, every team member must re-clone the repository. For public repos, GitHub may cache old tree views — consider filing a GitHub Support request to purge the cache as well.

### Additional Step: Rotate Any Exposed Secrets

Rewriting history prevents future exposure but does nothing about secrets already seen. Any value that was committed must be treated as compromised and rotated immediately.

```bash
# Generate a new secret_key_base inside Rails encrypted credentials
EDITOR="vim" bundle exec rails credentials:edit
```

```yaml
# config/credentials.yml.enc
secret_key_base: [newly generated 64-character hex string]
```

Using Rails encrypted credentials means `config/credentials.yml.enc` is safe to commit — it is encrypted and useless without the key. The one file that must never be committed is `config/master.key`. Double-check that `.gitignore` contains `config/master.key`.

---

## 2. Deployment Failure After Adding database.yml to .gitignore

### Symptoms

```
could not load config file: /app/config/database.yml
```

Everything works locally, but the deployment server throws this error on startup. The cause is that `database.yml` was removed from git tracking and is therefore absent from the deployed build.

### Cause

While hardening security as part of issue #1 above, it is tempting to think "all config files should be hidden" and add `/config/database.yml` to `.gitignore`, or run `git rm --cached config/database.yml` to stop tracking it.

The mistake here is conflating "contains secrets" with "is a config file." A `database.yml` that only references environment variables contains no secrets at all and is perfectly safe to commit:

```yaml
# config/database.yml — safe to commit because it only references ENV vars
default: &default
  adapter: postgresql
  encoding: unicode
  pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>

production:
  <<: *default
  url: <%= ENV["DATABASE_URL"] %>
```

In this structure, all actual connection details (host, port, credentials) live in the `DATABASE_URL` environment variable, which is injected at runtime by the hosting platform (Render, Heroku, Fly.io, etc.). The file itself is harmless.

### Solution

```bash
# Remove the database.yml entry from .gitignore, then re-add and commit the file
git add config/database.yml
git commit -m "restore: track database.yml (uses ENV vars only)"
```

The files that genuinely deserve `.gitignore` treatment are those that contain literal secret values: `config/master.key`, `config/credentials/*.key`, `.env` files, and similar. Keep the rule simple — if a file contains actual secret values, exclude it; if it only references environment variable names, commit it.

---

## 3. Missing Solid Suite Multi-Database Migrations

### Symptoms

Rails 8's Solid Queue, Solid Cache, and Solid Cable each use a separate database. If the deployment script only runs `db:migrate`, those tables are never created and the app fails immediately after startup:

```
PG::UndefinedTable: ERROR: relation "solid_queue_jobs" does not exist
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

This causes 500 errors across the entire application as soon as background jobs are enqueued or the cache is accessed.

### Cause

Rails 8's Solid Suite is designed around separate database connections, each with its own migration path in the project:

- `db/migrate/` — primary database (handled by the standard `db:migrate`)
- `db/queue_migrate/` — Solid Queue (`db:migrate:queue`)
- `db/cache_migrate/` — Solid Cache (`db:migrate:cache`)
- `db/cable_migrate/` — Solid Cable (`db:migrate:cable`)

In Rails 5 through 7, a single `db:migrate` command handled everything. Rails 8 with Solid Suite requires a separate migrate command for each database. This is the most significant operational change that surprises developers upgrading from earlier versions.

The `config/database.yml` section for Solid Suite looks something like this:

```yaml
queue: &queue
  primary:
    <<: *default
    url: <%= ENV["DATABASE_URL"] %>
  queue:
    <<: *default
    url: <%= ENV["QUEUE_DATABASE_URL"].presence || ENV["DATABASE_URL"] %>
    migrations_paths: db/queue_migrate
```

If no separate database URL is provided, all tables are created in the same PostgreSQL instance. On Render, it is common to use a single PostgreSQL instance with multiple table namespaces rather than separate database services.

### Solution: Add All Migration Commands to the Build Script

```bash
#!/usr/bin/env bash
# bin/render-build.sh

set -o errexit

bundle install
bundle exec rails assets:precompile
bundle exec rails assets:clean

echo "Running primary database migrations..."
bundle exec rails db:migrate

echo "Running Solid Queue migrations..."
bundle exec rails db:migrate:queue || echo "Queue migrate failed (may already exist)"

echo "Running Solid Cache migrations..."
bundle exec rails db:migrate:cache || echo "Cache migrate failed (may already exist)"

echo "Running Solid Cable migrations..."
bundle exec rails db:migrate:cable || echo "Cable migrate failed (may already exist)"
```

The `|| echo "..."` fallback is a safety guard for the case where tables already exist. After the initial deployment, subsequent runs of these commands produce "nothing to migrate" output and exit cleanly anyway, so the fallback is mainly defensive. Still, it is worth keeping to avoid a failed build if something unexpected happens.

---

## 4. Sentry Compatibility Error on Rails 8

### Symptoms

```
NameError: uninitialized constant ActionController::ClientDisconnectedError
```

The app fails to start after deployment. In the build logs, Puma worker processes can be seen crashing at startup with this error during Sentry initialization.

### Cause

`sentry-rails` version 6.3.x and below references `ActionController::ClientDisconnectedError` internally. This constant was **removed in Rails 8**. The Sentry team addressed this in version 6.4.0.

When upgrading a project from Rails 7 to Rails 8, if the Gemfile pins sentry gems with a constraint like `~> 6.3`, the gems will not update to 6.4 automatically and this crash will occur on the first Rails 8 deployment.

> Note: there is no sentry-rails 7.x. As of 2024, the latest release series is 6.4.x.

### Solution: Update the Gemfile Constraint

```ruby
# Gemfile
gem "sentry-rails", "~> 6.4"
gem "sentry-ruby", "~> 6.4"
```

```bash
bundle update sentry-rails sentry-ruby
git add Gemfile Gemfile.lock
git commit -m "fix: upgrade sentry-rails to 6.4 for Rails 8 compatibility"
```

Running `bundle update sentry-rails sentry-ruby` updates only these two gems and their direct dependencies, which is safer than a bare `bundle update` that would update everything.

---

## 5. image_processing Gem Warning

### Symptoms

In deployment logs or when running `bundle exec rails s` locally:

```
WARN: Could not load 'mini_magick'. Please add gem 'image_processing' to your Gemfile.
```

Alternatively, Active Storage image variant features (resizing, format conversion) silently fail and the original, unprocessed image is served instead.

### Cause

When the following configuration is present in `config/application.rb` or an initializer:

```ruby
config.active_storage.variant_processor = :mini_magick
```

...but the `image_processing` gem is absent from the Gemfile, Rails cannot load `mini_magick` and raises this warning. In the default Rails application template, `image_processing` is included but commented out. Developers who use Active Storage for file uploads often miss this and only discover it when variant processing is actually exercised in production.

The `image_processing` gem provides image transformation capabilities (resize, crop, format conversion, watermarking) on top of either MiniMagick (an ImageMagick wrapper) or libvips. Active Storage's `variant` method depends on this gem.

### Solution

```ruby
# Gemfile
gem "image_processing", "~> 1.2"
```

```bash
bundle install
git add Gemfile Gemfile.lock
git commit -m "feat: add image_processing gem for Active Storage variants"
```

Also verify that ImageMagick is available on the deployment server. Render's default build environment includes ImageMagick, but custom Docker images require an explicit installation:

```dockerfile
RUN apt-get update && apt-get install -y imagemagick libvips
```

If performance is a concern, consider switching to libvips as the variant processor. It uses significantly less memory than ImageMagick and is generally faster for common image operations:

```ruby
config.active_storage.variant_processor = :vips
```

---

## Summary

| Issue | Root Cause | Fix |
|---|---|---|
| Sensitive file leak | Security files included in early commits | git filter-repo + rotate secrets |
| Deployment failure due to missing database.yml | Wrong .gitignore policy | ENV-only config files are safe to commit |
| Missing Solid Suite tables | Multi-DB migrations not run | Add db:migrate:queue/cache/cable to build script |
| Sentry crash on Rails 8 | ActionController constant removed | Upgrade sentry-rails to 6.4 |
| image_processing warning | Gem not in Gemfile | Add image_processing ~> 1.2 |

The Solid Suite multi-database migration requirement was the most unexpected change when moving to Rails 8. The assumption that `db:migrate` handles everything no longer holds — Queue, Cache, and Cable each need their own migration command. The remaining issues were mostly side effects of a security hardening pass done in a hurry before the first deployment.

---

## Key Takeaways

- **If sensitive files are in git history, deletion is not enough.** Use `git-filter-repo` to rewrite history, then immediately rotate any exposed secret values. Treating it as "already safe" after deletion is a false sense of security.
- **Do not add database.yml to .gitignore unless it contains literal secret values.** A config file that only references environment variable names is safe to commit. Excluding it breaks deployments silently.
- **Rails 8 with Solid Suite requires four migration commands, not one.** The build script must include `db:migrate:queue`, `db:migrate:cache`, and `db:migrate:cable` in addition to the standard `db:migrate`.
- **sentry-rails 6.4+ is required for Rails 8 compatibility.** The `ActionController::ClientDisconnectedError` constant was removed in Rails 8; the fix landed in sentry-rails 6.4.0.
- **Active Storage image variants require the image_processing gem.** It is commented out in the default Rails template — if you use file upload variants, add it explicitly and confirm ImageMagick or libvips is installed on the server.
