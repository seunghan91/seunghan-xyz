---
title: "Render에 Rails 8 monorepo 처음 올릴 때 빌드 4번 깨먹은 이야기 — .ruby-version 함정과 SolidQueue web 통합"
date: 2026-04-29T09:00:00+09:00
draft: false
tags: ["Render", "Rails", "monorepo", "SolidQueue", "DevOps"]
description: "Render에 Rails 8 monorepo를 처음 배포하다 .ruby-version 위치와 lockfile RUBY VERSION 우선순위로 빌드를 4번 실패했다. SolidQueue worker를 web 프로세스에 통합해 MVP 비용 $7 절감한 과정도 같이."
---

새 OAuth/OIDC 서버를 Render에 처음 올리는 날이었다. Postgres 만들고 web service 만들고 환경변수 9개 박았다. 첫 deploy를 트리거하고 5분쯤 기다렸더니 빌드가 깨졌다. 그 뒤로 빌드를 3번 더 깨먹었다. 단순히 보이던 `.ruby-version` 함정이 사실은 4단 우선순위 게임이었던 것과, MVP 비용을 줄이려고 결정한 SolidQueue worker 통합까지 — 같은 길 가는 다른 사람이 빠르게 넘어가도록 정리한다.

본 포스트는 다음 상황을 가정한다.

- Rails 8 모노레포 (`server/` 안에 Rails 앱)
- Render Blueprint(`render.yaml`) 가 있지만 MCP 또는 API 로 서비스를 직접 생성하는 워크플로
- Postgres 1개 + Web 1개 가 MVP 인프라 목표

---

## 발단: 첫 빌드, 첫 실패

서비스 생성 직후 자동 시작된 첫 deploy 의 빌드 로그가 이렇게 끝났다.

```
==> Using Ruby version 3.4.4 (default)
==> Running build command 'cd server && ./bin/render-build'...
Bundler 2.7.2 is running, but your lockfile was generated with 4.0.8.
Installing Bundler 4.0.8 and restarting using that version.
Fetching gem metadata from https://rubygems.org/.
Your Ruby version is 3.4.4, but your Gemfile specified 3.4.2
==> Build failed 😞
```

두 줄이 핵심이다.

1. `Using Ruby version 3.4.4 (default)` — Render 기본값을 그대로 썼다. 내 `.ruby-version` 을 못 봤다.
2. `Your Ruby version is 3.4.4, but your Gemfile specified 3.4.2` — Bundler가 락파일(`RUBY VERSION ruby 3.4.2`) 과 실제 실행 환경(3.4.4) 불일치를 거부했다.

레포에 `server/.ruby-version` 은 분명 있었다. 내용은 `3.4.2`. Gemfile 도 `ruby file: ".ruby-version"` 이라고 정확히 지정해 둔 상태였다. 그런데 Render는 default 3.4.4 를 쓴다.

처음에는 환경변수를 의심했다.

## 첫 시도: `RUBY_VERSION` 환경변수 — 무시당함

Render 환경변수에 `RUBY_VERSION=3.4.2` 를 추가하면 그걸로 인식할 줄 알았다.

```bash
# MCP 또는 dashboard 로
RUBY_VERSION=3.4.2
```

env update 가 자동으로 redeploy 를 트리거했다. 두 번째 빌드 결과도 똑같았다.

```
==> Using Ruby version 3.4.4 (default)
...
Your Ruby version is 3.4.4, but your Gemfile specified 3.4.2
==> Build failed 😞
```

`RUBY_VERSION` 은 **Render Ruby 빌드에서 무시된다**. 검색해도 일부 환경에서만 동작한다는 모호한 글들만 보였다. 공식 문서에는 우선순위 목록만 있고 환경변수는 그 목록에 아예 없다. **이걸로 우회하려는 시도는 시간 낭비**다.

## 두 번째 시도: 루트에 `.ruby-version` 복제

Render 공식 문서를 다시 읽었다. Ruby 버전 결정 우선순위가 **내림차순으로 4단계**다.

| 우선순위 | 출처 | 위치 |
|--------|------|-----|
| 1 (최우선) | `Gemfile.lock` 또는 `gems.locked` 의 `RUBY VERSION` 섹션 | 레포 루트 |
| 2 | `.ruby-version` | 레포 루트 |
| 3 | `.tool-versions` | 레포 루트 |
| 4 | `Gemfile` 의 `ruby ""` 디렉티브 | 레포 루트 |

전부 다 **레포 루트**다. `cd server && ...` 가 buildCommand 라도 Render의 Ruby 버전 감지 단계는 buildCommand 실행 *전*에 일어나고, 레포 루트만 본다. 모노레포 함정 1번이다.

```bash
cd ~/toy/<project>
cp server/.ruby-version .ruby-version
git add .ruby-version
git commit -m "build(render): root .ruby-version"
git push origin main
```

세 번째 빌드. 결과는 또 실패였다.

```
==> Using Ruby version 3.4.4 (default)
...
Your Ruby version is 3.4.4, but your Gemfile specified 3.4.2
==> Build failed 😞
```

`Using Ruby version 3.4.4 (default)` 가 그대로다. 캐시 때문일 거라고 의심했다.

## 세 번째 시도: clear cache 빌드

Render dashboard 의 "Clear build cache & deploy" 버튼은 첫 빌드 후 캐시된 이전 결정을 무효화한다. API 로도 가능하다.

```bash
curl -X POST \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"clear"}' \
  https://api.render.com/v1/services/<SERVICE_ID>/deploys
```

네 번째 빌드. 한 줄이 바뀌었다.

```
==> Using Ruby version 3.4.2 via /opt/render/project/src/.ruby-version
==> Running build command 'cd server && ./bin/render-build'...
Bundler 2.7.2 is running, but your lockfile was generated with 4.0.8.
Installing Bundler 4.0.8 and restarting using that version.
Fetching gem metadata from https://rubygems.org/.
Your Ruby version is 3.4.4, but your Gemfile specified 3.4.2
==> Build failed 😞
```

이제 Render 의 detector 가 `.ruby-version` 을 정확히 읽는다 (`3.4.2 via /opt/render/project/src/.ruby-version`). 그런데도 Bundler 가 여전히 "3.4.4 vs 3.4.2 mismatch" 라고 거부한다. 무슨 일이지.

## 함정의 진짜 모양: 락파일 RUBY VERSION

[Render 공식 문서](https://render.com/docs/ruby-version)를 다시 정독했다. 중요한 줄을 흘렸다.

> **Set a different Ruby version in *any* of the following ways (in descending order of precedence)**

내림차순 — 즉 락파일이 먼저다. `.ruby-version` 이 없을 때만 `Gemfile.lock` 의 `RUBY VERSION` 섹션으로 폴백되는 게 아니라, **둘 다 있으면 락파일이 이긴다**. 락파일을 보고 Render 가 Ruby 3.4.2 binary 를 다운로드하려고 하는데 — 여기서 또 다른 함정이 있다. Render 의 Ruby 풀에 **모든 patch 버전이 있는 건 아니다**. 3.4.x 시리즈에서 일부 patch 만 빌드해 둔다. 3.4.2 가 풀에 없으면 가장 가까운 사용 가능 버전(3.4.4)을 fallback 으로 설치한다. 그 결과:

- `.ruby-version` 은 정확히 3.4.2 를 가리키고
- Render 빌더는 "3.4.2 요청됨" 을 표시하지만
- 실제 설치된 binary 는 3.4.4 이고
- Bundler 가 그 mismatch 를 거부한다

해결법은 둘 중 하나다.

### A) 락파일/`.ruby-version` 을 Render 가 가진 버전에 맞춘다

가장 빠르고 안전한 길. Render 가 3.4.4 를 갖고 있다면 거기 맞춘다.

```bash
# .ruby-version 만 수정해도 락파일 RUBY VERSION 섹션과 어긋나면 또 깨진다
# 둘 다 동기화해야 한다

# 1) 로컬에서 rbenv install 3.4.4
rbenv install 3.4.4

# 2) .ruby-version 들 동기화
echo 3.4.4 > .ruby-version
echo 3.4.4 > server/.ruby-version

# 3) bundle install 로 락파일 RUBY VERSION 섹션 갱신
cd server && bundle install
git add ../.ruby-version .ruby-version Gemfile.lock
git commit -m "chore: bump Ruby to 3.4.4 to match Render pool"
git push
```

### B) `Gemfile` 의 `ruby` 디렉티브 + 락파일 `RUBY VERSION` 섹션을 모두 제거한다

Bundler enforcement 자체를 끈다. 단점은 로컬과 프로덕션 환경 차이를 더 이상 자동으로 잡아주지 않는다. 단일 환경 MVP 라면 허용 가능.

```ruby
# server/Gemfile
# 아래 줄 제거:
# ruby file: ".ruby-version"
```

```
# server/Gemfile.lock
# 아래 섹션 통째로 제거:
RUBY VERSION
   ruby 3.4.2
```

내 경우는 A 로 갔다. 로컬과 프로덕션 차이를 명시적으로 보고 싶었기 때문이다.

다섯 번째 빌드는 통과했다.

---

## 우선순위 정리: 다른 사람이 빠르게 넘어가도록

같은 함정에 빠지지 않도록 한 번 더 정리한다.

| 단계 | 확인할 것 | 흔한 실수 |
|-----|---------|---------|
| 1 | `Gemfile.lock` 의 `RUBY VERSION` 섹션 — **레포 루트** 또는 buildCommand cwd 둘 다 일치해야 함 | 모노레포에서 락파일이 sub-dir 에만 있으면 Render 가 못 찾을 수 있음 |
| 2 | `.ruby-version` — **레포 루트** | server/, app/ 같은 sub-dir 에만 두는 것 |
| 3 | Render 가 **해당 patch 버전을 빌드해 둔 게 맞는지** | 새 patch 출시 직후엔 풀에 없을 수 있음 |
| 4 | `RUBY_VERSION` env var — **무시됨** | "환경변수로 우회" 시도 |
| 5 | Build cache — Ruby 버전 결정은 캐시되니 버전 변경 후 **clear cache deploy** | 변경했는데 이전 결정 그대로 |

추가로, `.tool-versions` 사용자(asdf, mise) 는 다음을 주의한다. Render 는 `ruby file: ".tool-versions"` 같은 Gemfile 디렉티브의 file 참조를 **파싱하지 못한다**. 즉 Gemfile 안에 `ruby file: ".ruby-version"` 또는 `ruby file: ".tool-versions"` 라고 써 두면 Render 빌더가 해당 파일명을 그대로 *버전 번호로* 해석해서 깨진다. Render 의 detector 와 Bundler 는 다른 코드 경로다.

---

## 다른 절반: SolidQueue worker 를 web 에 통합해 MVP 비용 $7/mo 절감

같은 배포 작업에서 결정한 다른 트레이드오프다. Rails 8 의 SolidQueue 는 기본 Active Job 백엔드다. 보통은 web 서비스와 별도의 worker 프로세스(예: `bundle exec rake solid_queue:start`)로 띄운다. 하지만 MVP 단계에서는 **Puma 안에 통합**해서 web 1대로 끝낼 수 있다.

### 작동 원리

[SolidQueue README](https://github.com/rails/solid_queue) 와 [Honeybadger 가이드](https://www.honeybadger.io/blog/deploy-solid-queue-rails/) 둘 다 명시한다. `config/puma.rb` 에 한 줄 추가하면 Puma 프로세스가 dispatcher + worker + recurring scheduler 를 같은 프로세스 안에서 띄운다.

```ruby
# config/puma.rb
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]
```

Render 환경변수에 `SOLID_QUEUE_IN_PUMA=1` 만 추가하면 web service 1대 안에서 백그라운드 잡이 처리된다. 별도 worker 서비스 불필요.

### MVP 비용 비교

Render Singapore 기준 starter plan:

| 구성 | 월 비용 |
|-----|--------|
| Postgres basic-256mb + Web starter + Worker starter | $6 + $7 + $7 = **$20/mo** |
| Postgres basic-256mb + Web starter (`SOLID_QUEUE_IN_PUMA=1`) | $6 + $7 = **$13/mo** |

**$7/mo 절감**. 1년이면 $84.

### 언제 worker 를 분리해야 하는가

[SolidQueue issue #281](https://github.com/rails/solid_queue/issues/281) 에서 DHH 도 명시했다. Puma plugin 은 single-server 배포를 위해 유지되지만, 트래픽이 늘면 분리하는 게 맞다. 분리 신호 3가지.

1. **web 메모리/CPU 압박**: 잡이 무거워지면 web request latency 가 같이 망가진다.
2. **분당 100+ 잡**: dispatcher polling 이 web HTTP loop 와 자원 경합한다.
3. **잡 백로그**: 푸시 알림 같은 critical-path 잡이 밀리기 시작하면 dedicated worker 가 필요하다.

지금 MVP 단계에서는 가입자 0명이고 SP 도 0개다. webhook job, back-channel logout job, push notification job 모두 호출 빈도 분당 1회 이하다. log purge 는 일 1회. 합쳐도 web 의 1% 부하도 안 된다.

### 함정 한 가지: Puma worker 수

[GoRails 토론](https://gorails.com/forum/how-to-use-solid-queue-in-rails-with-active-job-discussion) 과 issue #281 에서 공통적으로 지적한다. Puma 의 `WEB_CONCURRENCY` (워커 프로세스 수) 가 1인 환경에서는 SolidQueue plugin 이 가끔 시작에 실패한다. 최소 2 이상 권장.

```bash
# Render env vars
WEB_CONCURRENCY=2
SOLID_QUEUE_IN_PUMA=1
```

starter plan 의 메모리(512MB)에서 worker 2 + threads 5 면 Rails 8 + SolidQueue 가 안정적으로 돈다.

### 단일 DB vs 분리 DB

SolidQueue 는 보통 별도 `queue:` 데이터베이스를 권장한다. 하지만 [공식 README의 "Single database configuration" 섹션](https://github.com/rails/solid_queue#single-database-configuration) 처럼 같은 Postgres 인스턴스에 `solid_queue_*` 테이블을 두는 것도 정식 옵션이다. `config/database.yml` 의 production 블록에서 `queue:` 와 `cache:` 가 모두 `<<: *primary_production` 을 상속받게 만들면, 한 인스턴스 안에서 schema namespace 만 분리된다.

```yaml
# config/database.yml
production:
  primary: &primary_production
    <<: *default
    url: <%= ENV["DATABASE_URL"] %>
    sslmode: require
  queue:
    <<: *primary_production
    migrations_paths: db/queue_migrate
  cache:
    <<: *primary_production
    migrations_paths: db/cache_migrate
  cable:
    <<: *primary_production
    migrations_paths: db/cable_migrate
```

이러면 `bin/rails db:prepare` 가 4개 DB connection 모두 같은 Postgres 에 마이그레이션을 적용한다. Postgres 인스턴스 1개로 끝.

---

## Render API 로 monorepo Web service 만들 때 알아둘 것

번외. Render MCP 또는 REST API 로 자동화할 때 dashboard 와 다른 제약이 있다.

### `rootDir` 미지원

API/MCP 로 web service 를 만들 때 `rootDir` 파라미터는 노출되지 않는다. 그래서 buildCommand / startCommand 에 `cd server && ...` 를 직접 inline 으로 박는다.

```yaml
# render.yaml (Blueprint) 에서는 가능
services:
  - type: web
    rootDir: server
    buildCommand: ./bin/render-build
```

```bash
# API/MCP 로 직접 만들 때는 cd 로 우회
buildCommand: cd server && ./bin/render-build
startCommand: cd server && bundle exec rails server -b 0.0.0.0 -p $PORT
```

이 차이가 위에서 말한 `.ruby-version` 함정의 원인이기도 하다. Blueprint 면 `rootDir: server` 라서 server/.ruby-version 이 정확히 인식될 가능성이 있지만, API 로 생성한 monorepo 서비스는 root 가 빈 문자열이라 레포 루트만 본다.

### `fromDatabase` 미지원 — connection string 직접 가져와야 함

Blueprint 의 `fromDatabase: { name: db, property: connectionString }` 도 API 에서는 불가. Postgres 가 available 상태가 된 다음 connection string 을 별도로 가져와 web service env 에 직접 박아야 한다. REST 엔드포인트는 `/v1/postgres/{id}/connection-info`.

```bash
curl -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/postgres/<POSTGRES_ID>/connection-info
```

응답에 `internalConnectionString` (같은 region 내부) 과 `externalConnectionString` (외부 psql 접속용) 둘이 있다. web service 에는 internal 을 쓴다.

```
postgresql://<user>:<password>@<postgres-id>/<dbname>
```

호스트 부분이 `dpg-xxxxxxxxxxxxxxxxxxxx-a` 같은 Render 내부 식별자다. 이 값이 같은 region 내부 DNS 로만 풀린다.

---

## 실전 점검표

같은 작업을 처음부터 다시 한다면 다음 순서로 한다.

1. 레포 루트에 `.ruby-version` 을 둔다 (sub-dir 의 `.ruby-version` 만으론 부족).
2. `Gemfile.lock` 의 `RUBY VERSION` 섹션 버전 ≡ `.ruby-version` ≡ Render 가 가진 patch 버전. 셋이 모두 일치해야 한다.
3. Render 가 해당 patch 버전을 갖고 있는지 의심된다면 [Render Ruby 문서](https://render.com/docs/ruby-version) 의 default 버전(현재 3.4.4)에 맞춘다.
4. `SOLID_QUEUE_IN_PUMA=1` + `WEB_CONCURRENCY=2` 로 web 1대 통합. worker 트래픽 늘면 그때 분리.
5. `config/database.yml` 의 production 에서 `queue:`/`cache:`/`cable:` 모두 primary 를 상속하게 해서 Postgres 인스턴스 1개로 끝.
6. API/MCP 로 만들면 buildCommand/startCommand 에 `cd <subdir> && ...` 를 inline.
7. Postgres 가 available 된 후 `/connection-info` 로 internal URL 받아서 web env 에 직접 주입.
8. Ruby 버전 변경 후엔 반드시 **Clear build cache & deploy**. 캐시된 detector 결과가 새 변경을 무시한다.

---

## 결론

Render 에 Rails 8 monorepo 를 처음 올리는 작업 자체는 5분이면 끝난다. 하지만 4가지 이상의 우선순위 규칙이 사일런트하게 충돌하면 4번 빌드를 깨먹게 된다. 락파일 > `.ruby-version` > `.tool-versions` > Gemfile directive 순서 + Render 가 가진 patch 풀 + clear cache 까지 합쳐 5단 게임이다. 이 글을 같은 길에서 시간 날린 사람이 발견했다면 바로 5번째 빌드부터 시도해 볼 수 있을 것이다.

SolidQueue 의 Puma 통합은 별 얘기 아닌 것 같지만, MVP 12개월이면 $84 차이고 무엇보다 운영 surface 가 줄어든다. 2개 서비스보다 1개 서비스가 모니터링·디버깅·로그·배포 모두 단순하다. 트래픽 지표가 분명히 worker 분리를 요구할 때 그때 분리하면 된다 — 미리 분리하지 않는다.

같은 함정 정리: `seunghan.xyz` 의 [Tailwind v4 @theme 함정](/posts/tailwind-v4-theme-migration-oklch-fallback) 도 비슷한 패턴이다. "공식 문서대로 했는데 왜 안 돼" 의 70% 는 우선순위 규칙을 흘려 읽었기 때문이다.
