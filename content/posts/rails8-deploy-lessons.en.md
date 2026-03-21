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


Rails 8 프로젝트를 처음 클라우드 서비스에 배포하면서 하루 동안 연속으로 5가지 문제를 만났다. 각각 독립적인 문제처럼 보였지만, 하나를 고치면 다음 문제가 드러나는 패턴이었다. 기록으로 남긴다.

---

## 1. 공개 저장소에 민감한 파일이 들어간 경우

### Symptoms

`git log --all --full-history -- config/secrets.yml` 같은 명령으로 확인해보면, 예전 커밋에 `secret_key_base`가 하드코딩된 파일, 앱 서명 키스토어 파일 등이 포함되어 있다.

### Solution: git filter-repo로 히스토리에서 완전 삭제

```bash
pip install git-filter-repo

# 특정 파일들을 히스토리 전체에서 제거
git filter-repo --path config/secrets.yml --invert-paths
git filter-repo --path app-release.keystore --invert-paths

# 강제 푸시
git push origin main --force
```

> **주의**: `--force` 는 팀 작업 중이라면 사전 공지 필수. 모든 팀원이 re-clone해야 한다.

### 추가 조치

히스토리에서 지워도 이미 노출된 시크릿은 **반드시 교체**해야 한다.

```bash
# Rails credentials에 새로운 secret_key_base 추가
EDITOR="vim" bundle exec rails credentials:edit
```

```yaml
# config/credentials.yml.enc
secret_key_base: [새로 생성한 64자리 hex]
```

---

## 2. database.yml을 .gitignore에 추가했다가 배포 실패

### Symptoms

```
could not load config file: /app/config/database.yml
```

로컬에서는 잘 되는데 배포 서버에서만 이 오류가 난다면, `database.yml` 파일이 git에서 추적되지 않는 경우다.

### Cause

보안 강화 작업 중 `.gitignore`에 `/config/database.yml`을 추가하거나, `git rm --cached config/database.yml`을 실행해 추적을 중단한 경우 발생한다.

그런데 `database.yml`이 환경변수만 참조하는 구조라면 공개해도 무방하다:

```yaml
# config/database.yml - 환경변수만 사용하므로 커밋해도 안전
default: &default
  adapter: postgresql
  encoding: unicode
  pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>

production:
  <<: *default
  url: <%= ENV["DATABASE_URL"] %>
```

### Solution

```bash
# .gitignore에서 database.yml 제거
# 그 다음 다시 추적 시작
git add config/database.yml
git commit -m "restore: track database.yml (uses ENV vars only)"
```

---

## 3. Solid Suite 멀티 DB 마이그레이션 누락

### Symptoms

Rails 8의 Solid Queue, Solid Cache, Solid Cable은 별도 데이터베이스를 사용한다. 배포 스크립트에 `db:migrate`만 있으면 이 테이블들이 생성되지 않아 다음 오류가 발생한다:

```
PG::UndefinedTable: ERROR: relation "solid_queue_jobs" does not exist
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

### Cause

Rails 8의 Solid Suite는 `config/database.yml`에 별도 데이터베이스를 설정하고, 마이그레이션 경로도 분리되어 있다:

- `db/migrate/` → 기본 DB (기존 `db:migrate`)
- `db/queue_migrate/` → Solid Queue (`db:migrate:queue`)
- `db/cache_migrate/` → Solid Cache (`db:migrate:cache`)
- `db/cable_migrate/` → Solid Cable (`db:migrate:cable`)

### Solution: 빌드 스크립트에 모든 마이그레이션 추가

```bash
# bin/render-build.sh (또는 배포 빌드 스크립트)

echo "🗄️  Running primary database migrations..."
bundle exec rails db:migrate

echo "🗄️  Running Solid Queue migrations..."
bundle exec rails db:migrate:queue || echo "⚠️  Queue migrate failed (may already exist)"

echo "🗄️  Running Solid Cache migrations..."
bundle exec rails db:migrate:cache || echo "⚠️  Cache migrate failed (may already exist)"

echo "🗄️  Running Solid Cable migrations..."
bundle exec rails db:migrate:cable || echo "⚠️  Cable migrate failed (may already exist)"
```

`|| echo "..."` 처리는 테이블이 이미 존재하는 경우 오류로 배포가 중단되지 않도록 한다.

---

## 4. Sentry가 Rails 8에서 호환성 오류 발생

### Symptoms

```
NameError: uninitialized constant ActionController::ClientDisconnectedError
```

배포 직후 앱이 뜨지 않거나, Sentry 초기화 시점에 이 오류가 발생한다.

### Cause

`sentry-rails` 6.3.x 이하 버전은 `ActionController::ClientDisconnectedError`를 참조하는데, 이 상수가 **Rails 8에서 제거**되었다. 6.4.0에서 이 참조가 수정되었다.

> 참고: sentry-rails는 7.x 버전이 없다. 최신은 6.4.x다.

### Solution: Gemfile 업그레이드

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

---

## 5. image_processing gem 경고

### Symptoms

배포 로그 또는 `bundle exec rails s` 실행 시:

```
WARN: Could not load 'mini_magick'. Please add gem 'image_processing' to your Gemfile.
```

또는 Active Storage의 이미지 변환(리사이징 등) 기능이 동작하지 않는다.

### Cause

`config/application.rb` 또는 `config/initializers`에 다음 설정이 있는데:

```ruby
config.active_storage.variant_processor = :mini_magick
```

`image_processing` gem이 Gemfile에 없는 경우다. Rails 기본 앱 템플릿에는 주석 처리되어 있어 Active Storage를 실제로 사용할 때 직접 추가해야 한다.

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

---

## Summary

| 문제 | 원인 | 핵심 해결 |
|---|---|---|
| 민감한 파일 유출 | 초기 커밋 시 보안 파일 포함 | git filter-repo + 시크릿 교체 |
| database.yml 제거로 배포 실패 | 잘못된 .gitignore 적용 | ENV만 참조하면 커밋해도 안전 |
| Solid Suite 테이블 없음 | 멀티 DB 마이그레이션 누락 | db:migrate:queue/cache/cable 추가 |
| Sentry Rails 8 호환성 오류 | ActionController 상수 제거 | sentry-rails 6.4로 업그레이드 |
| image_processing 경고 | gem 누락 | image_processing ~> 1.2 추가 |

Rails 8로 오면서 Solid Suite의 멀티 DB 구조가 가장 낯설었다. `db:migrate` 하나로 다 된다는 생각을 바꿔야 했다. 나머지 문제들은 대부분 초기 보안 강화 작업 중 생긴 부작용이었다.
