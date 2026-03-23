---
title: "Rails 8 첫 배포에서 마주친 5가지 문제: 보안, 마이그레이션, 호환성"
date: 2025-11-11
draft: false
tags: ["Rails 8", "Render", "Solid Queue", "Sentry", "배포", "보안", "디버깅"]
description: "Rails 8 프로젝트를 처음 클라우드에 배포하면서 겪은 보안 파일 유출, database.yml 제거 실수, Solid Suite 멀티DB 마이그레이션 누락, Sentry 호환성 오류, image_processing 경고까지 5가지 삽질을 정리한다."
cover:
  image: "/images/og/rails8-deploy-lessons.png"
  alt: "Rails8 Deploy Lessons"
  hidden: true
categories: ["Rails"]
---

Rails 8 프로젝트를 처음 클라우드 서비스에 배포하면서 하루 동안 연속으로 5가지 문제를 만났다. 각각 독립적인 문제처럼 보였지만, 하나를 고치면 다음 문제가 드러나는 패턴이었다. 특히 Rails 8에서 새로 도입된 Solid Suite의 멀티 DB 구조는 기존 Rails 개발자에게도 낯선 부분이 많았다. 시간 순서대로 마주친 문제와 해결 과정을 기록한다.

---

## 1. 공개 저장소에 민감한 파일이 들어간 경우

### 증상

배포 전 보안 점검을 하다가 git 히스토리에 민감한 파일이 포함된 것을 발견했다. 현재 HEAD에는 없더라도 과거 커밋에 남아있으면 누구나 조회할 수 있다.

```bash
# 히스토리에서 민감한 파일 존재 여부 확인
git log --all --full-history -- config/secrets.yml
git log --all --full-history -- "*.keystore"
git log --all --full-history -- "*.pem"
```

이렇게 확인해보면 예전 커밋에 `secret_key_base`가 하드코딩된 파일, 앱 서명 키스토어 파일 등이 포함되어 있는 경우가 있다. 파일을 삭제해도 git 히스토리에는 영원히 남기 때문에 반드시 히스토리 자체를 재작성해야 한다.

### 해결: git filter-repo로 히스토리에서 완전 삭제

`git filter-branch`는 구식이고 느리다. `git-filter-repo`를 쓰는 것이 현재 권장 방법이다.

```bash
pip install git-filter-repo

# 특정 파일들을 히스토리 전체에서 제거
git filter-repo --path config/secrets.yml --invert-paths
git filter-repo --path app-release.keystore --invert-paths

# 강제 푸시
git push origin main --force
```

> **주의**: `--force` 는 팀 작업 중이라면 사전 공지 필수. 히스토리가 재작성되므로 모든 팀원이 re-clone해야 한다. 공개 저장소라면 GitHub에 캐시된 뷰도 있을 수 있으니 GitHub Support에 캐시 삭제를 요청하는 것도 고려한다.

### 추가 조치: 노출된 시크릿 반드시 교체

히스토리에서 지워도 이미 노출된 시크릿은 **반드시 교체**해야 한다. 히스토리 삭제는 "앞으로 더 이상 노출되지 않게" 하는 것이고, 이미 유출된 값은 공격자가 가지고 있을 수 있다.

```bash
# Rails credentials에 새로운 secret_key_base 생성 및 저장
EDITOR="vim" bundle exec rails credentials:edit
```

```yaml
# config/credentials.yml.enc
secret_key_base: [새로 생성한 64자리 hex 값]
```

Rails의 encrypted credentials를 사용하면 `config/credentials.yml.enc` 파일 자체는 git에 커밋해도 안전하다. `master.key`만 절대 커밋하지 않으면 된다. `.gitignore`에 `config/master.key`가 있는지 반드시 확인한다.

---

## 2. database.yml을 .gitignore에 추가했다가 배포 실패

### 증상

```
could not load config file: /app/config/database.yml
```

로컬에서는 정상 동작하는데 배포 서버에서만 이 오류가 발생한다면, `database.yml` 파일이 git에서 추적되지 않아 배포 빌드에 포함되지 않은 것이다.

### 원인

1번 문제를 해결하면서 보안 강화 작업을 하다 보면, "설정 파일은 다 숨기자"는 생각에 `.gitignore`에 `/config/database.yml`을 추가하거나 `git rm --cached config/database.yml`을 실행하는 실수를 저지르기 쉽다.

그런데 `database.yml`이 환경변수만 참조하는 구조라면 공개해도 전혀 문제없다. 파일 자체에는 접속 정보가 없고, 실제 값은 런타임에 환경변수에서 가져오기 때문이다.

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

위 구조에서 실제 데이터베이스 접속 정보(호스트, 포트, 사용자명, 비밀번호)는 `DATABASE_URL` 환경변수에 있다. 이 환경변수는 Render, Heroku 등의 플랫폼에서 자동으로 주입해준다.

### 해결

```bash
# .gitignore에서 database.yml 관련 항목 제거 후 다시 추적 시작
git add config/database.yml
git commit -m "restore: track database.yml (uses ENV vars only)"
```

반면 실제로 git에서 제외해야 하는 파일은 `config/master.key`, `config/credentials/*.key`, `.env` 파일 등이다. 값이 직접 담긴 파일만 제외하면 된다.

---

## 3. Solid Suite 멀티 DB 마이그레이션 누락

### 증상

Rails 8의 Solid Queue, Solid Cache, Solid Cable은 별도 데이터베이스를 사용한다. 배포 스크립트에 `db:migrate`만 있으면 이 테이블들이 생성되지 않아 다음 오류가 발생한다:

```
PG::UndefinedTable: ERROR: relation "solid_queue_jobs" does not exist
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

배포 직후 앱이 뜨자마자 백그라운드 잡을 실행하거나 캐시를 읽으려 할 때 발생하며, 앱 전체가 500 에러를 반환하는 원인이 된다.

### 원인

Rails 8에서 Solid Suite는 기본 DB와 분리된 별도 데이터베이스를 사용한다. `config/database.yml`에 각각의 데이터베이스가 설정되고, 마이그레이션 파일 경로도 분리되어 있다:

- `db/migrate/` → 기본 DB (기존 `db:migrate` 로 처리)
- `db/queue_migrate/` → Solid Queue (`db:migrate:queue`)
- `db/cache_migrate/` → Solid Cache (`db:migrate:cache`)
- `db/cable_migrate/` → Solid Cable (`db:migrate:cable`)

기존 Rails 5~7 프로젝트에서는 `db:migrate` 하나로 모든 마이그레이션이 처리됐지만, Rails 8의 Solid Suite는 각 데이터베이스에 대해 별도로 마이그레이션 명령을 실행해야 한다.

`config/database.yml`의 Solid Suite 관련 설정은 보통 다음과 같다:

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

별도 데이터베이스 URL을 지정하지 않으면 기본 DB와 같은 곳에 테이블을 생성한다. Render의 경우 하나의 PostgreSQL 인스턴스에서 여러 테이블 네임스페이스로 운영하는 것이 일반적이다.

### 해결: 빌드 스크립트에 모든 마이그레이션 추가

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

`|| echo "..."` 처리는 테이블이 이미 존재하는 경우 오류로 배포가 중단되지 않도록 하는 안전장치다. 첫 배포 이후에는 이미 테이블이 있어서 마이그레이션 명령이 "nothing to migrate" 상태가 되는데, 이때 오류 코드 없이 종료되므로 사실 `|| echo` 없이도 괜찮다. 다만 예기치 않은 상황을 대비한 방어 코드로 남겨두는 편이 낫다.

---

## 4. Sentry가 Rails 8에서 호환성 오류 발생

### 증상

```
NameError: uninitialized constant ActionController::ClientDisconnectedError
```

배포 직후 앱이 뜨지 않거나, Sentry 초기화 시점에 이 오류가 발생한다. 배포 로그에서는 Puma가 워커를 시작하려다 이 오류로 실패하는 것을 볼 수 있다.

### 원인

`sentry-rails` 6.3.x 이하 버전은 내부적으로 `ActionController::ClientDisconnectedError`를 참조하는데, 이 상수가 **Rails 8에서 제거**되었다. Sentry 측에서는 6.4.0에서 이 참조를 제거하고 Rails 8 호환성을 확보했다.

Rails 7에서 Rails 8로 업그레이드하면서 Gemfile의 sentry 버전을 그대로 두면 이 문제가 발생한다. 특히 `~> 6.3` 처럼 패치 버전만 올라가는 제약을 걸어뒀다면 자동 업데이트가 되지 않는다.

> 참고: sentry-rails는 7.x 버전이 없다. 2024년 기준 최신은 6.4.x다.

### 해결: Gemfile 업그레이드

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

`bundle update sentry-rails sentry-ruby`는 두 gem과 그 의존성만 업데이트한다. `bundle update` 만 실행하면 전체 의존성이 바뀔 수 있으니 대상을 명시하는 것이 안전하다.

---

## 5. image_processing gem 경고

### 증상

배포 로그 또는 `bundle exec rails s` 실행 시:

```
WARN: Could not load 'mini_magick'. Please add gem 'image_processing' to your Gemfile.
```

또는 Active Storage의 이미지 변환(리사이징, 포맷 변환 등) 기능이 동작하지 않고 원본 이미지가 그대로 서빙된다.

### 원인

`config/application.rb` 또는 `config/initializers/` 에 다음 설정이 있는 경우:

```ruby
config.active_storage.variant_processor = :mini_magick
```

`image_processing` gem이 Gemfile에 없으면 `mini_magick`을 로드할 수 없어 이 경고가 발생한다. Rails 기본 앱 템플릿에서는 이 gem이 주석 처리된 상태로 포함되어 있어서, Active Storage를 실제로 사용할 때 직접 주석을 해제하거나 추가해야 한다.

`image_processing` gem은 MiniMagick(ImageMagick 래퍼) 또는 libvips 기반으로 이미지 리사이징, 크롭, 포맷 변환, 워터마크 등의 기능을 제공한다. Active Storage의 `variant` 기능이 내부적으로 이 gem에 의존한다.

### 해결

```ruby
# Gemfile
gem "image_processing", "~> 1.2"
```

```bash
bundle install
git add Gemfile Gemfile.lock
git commit -m "feat: add image_processing gem for Active Storage variants"
```

배포 서버에 ImageMagick이 설치되어 있는지도 확인해야 한다. Render의 경우 기본 환경에 ImageMagick이 포함되어 있지만, 커스텀 Docker 이미지를 사용한다면 직접 설치해야 한다:

```dockerfile
RUN apt-get update && apt-get install -y imagemagick libvips
```

libvips를 사용한다면 `variant_processor`를 `:vips`로 변경하는 것도 고려할 수 있다. libvips는 ImageMagick보다 메모리 효율이 높고 빠르다.

---

## 정리

| 문제 | 원인 | 핵심 해결 |
|---|---|---|
| 민감한 파일 유출 | 초기 커밋 시 보안 파일 포함 | git filter-repo + 시크릿 교체 |
| database.yml 제거로 배포 실패 | 잘못된 .gitignore 적용 | ENV만 참조하면 커밋해도 안전 |
| Solid Suite 테이블 없음 | 멀티 DB 마이그레이션 누락 | db:migrate:queue/cache/cable 추가 |
| Sentry Rails 8 호환성 오류 | ActionController 상수 제거 | sentry-rails 6.4로 업그레이드 |
| image_processing 경고 | gem 누락 | image_processing ~> 1.2 추가 |

Rails 8로 오면서 Solid Suite의 멀티 DB 구조가 가장 낯설었다. 기존에는 `db:migrate` 하나로 모든 게 해결됐는데, 이제는 Queue, Cache, Cable 각각을 따로 마이그레이션해야 한다는 것을 처음 배포에서야 깨달았다. 나머지 문제들은 대부분 보안 강화 작업 중 생긴 부작용이었다.

---

## 핵심 정리

- **git 히스토리에 민감한 파일이 들어갔다면**: 파일 삭제만으로는 부족하다. `git-filter-repo`로 히스토리를 재작성하고, 노출된 시크릿 값은 반드시 새로 발급해야 한다.
- **database.yml을 gitignore에 넣지 않아야 한다**: 환경변수만 참조하는 구조라면 커밋해도 안전하다. 실제 접속 정보가 담긴 `.env`나 `master.key`만 제외하면 된다.
- **Rails 8 Solid Suite는 마이그레이션 명령이 4개다**: `db:migrate` 외에 `db:migrate:queue`, `db:migrate:cache`, `db:migrate:cable`을 빌드 스크립트에 추가해야 한다.
- **sentry-rails는 6.4 이상이어야 Rails 8과 호환된다**: `ActionController::ClientDisconnectedError` 상수가 Rails 8에서 제거되었고, 6.4.0에서 이 문제가 수정되었다.
- **Active Storage 이미지 변환 기능은 image_processing gem이 필요하다**: Rails 템플릿에 주석 처리된 상태로 있으니 Active Storage를 실제 사용한다면 반드시 추가해야 한다.
