---
title: "Rails raw SQL 컬럼명 typo로 OAuth userinfo가 다 500 — 4중 보호막이 동시에 뚫린 이야기"
date: 2026-05-11T11:45:01+09:00
draft: false
tags: ["Rails", "ActiveRecord", "OAuth", "OIDC", "포스트모템", "운영"]
description: "OIDC IdP 서버 /oauth/userinfo가 모든 RP에서 500을 뱉었다. 표면 증상은 RP 측 401. 진짜 원인은 ActiveRecord raw SQL의 컬럼명 typo 한 줄이었고, spec/CI/auto-deploy/알림 4중 보호막이 동시에 뚫린 결과였다."
---

운영하던 OIDC IdP 서버에서 어느 날 갑자기 모든 RP(Relying Party) 로그인이 깨졌다. 사용자가 보는 화면은 평범한 401 "로그인 실패". 클라이언트 로그를 봐도 그냥 RP Rails 백엔드가 401을 응답했을 뿐이다. 처음엔 핸드오프(Universal Link / Custom Tabs) 문제로 의심했다 — 표면 증상만 보면 그게 가장 자연스러우니까.

그런데 진단을 깊이 파보니 4중으로 깔려있어야 할 안전망이 단 하나도 작동 안 한 상태였고, 그 결과 raw SQL 한 줄의 컬럼명 오타가 며칠을 살아서 모든 사용자 인증을 깨놓고 있었다. 사고 자체보다 **왜 이게 prod까지 도달했는지**가 본질이라 정리해둔다.

---

## TL;DR

- 표면: RP 앱에서 logi 푸시 승인까지 정상 → 그 직후 401
- 진짜: IdP 서버 `/oauth/userinfo`가 모든 호출에 **500 (PG::UndefinedColumn)** 반환 중
- 코드: `User#linked_user_ids`의 raw SQL string에서 `oauth_access_grants.application_id` 라고 적었는데 실제 컬럼명은 `oauth_application_id`
- 같은 테이블을 참조하는 다른 9곳은 다 올바르게 썼음. **딱 한 줄**이 raw SQL이었고 그 한 줄만 틀림
- 안전망이 다 뚫림: 모델 unit spec 없음 + CI 빨강 방치 + Render `autoDeploy:true`가 CI 결과 무시 + Sentry 미설치

---

## 진단 흐름 — 표면 증상이 진짜 원인을 가린다

RP 앱에서 사용자가 로그인을 누르면 OIDC authorization code flow가 돈다:

1. RP 앱 → IdP `/oauth/authorize` 호출 (브라우저)
2. IdP에서 사용자 인증 (이 환경에선 푸시 승인)
3. IdP → RP 앱 callback URL (`code` 파라미터 전달)
4. RP 앱 → IdP `/oauth/token` (code 교환 → access_token)
5. RP 앱 → **자기 백엔드**에 access_token POST
6. RP 백엔드 → IdP `/oauth/userinfo` (서버 간 호출, access_token으로 사용자 정보 조회)
7. RP 백엔드 → 자기 DB에 사용자 upsert + 세션 발급

사용자가 보는 화면은 7단계 결과지만, 실패는 6단계에서 일어나고 있었다. RP 백엔드 입장에선 IdP가 500을 뱉으니 access_token이 유효한지 검증할 수 없어서 안전하게 401로 떨어뜨린 거다.

그래서 RP 쪽 로그만 보면 "IdP가 거부함"으로 보이지만, IdP 쪽 로그를 봐야 진실이 나온다. Render 로그 grep:

```bash
# 사용자 신고 시각 ±5분
status=500, path=/oauth/userinfo
```

한 줄짜리 결정타가 떴다:

```
ActiveRecord::StatementInvalid (PG::UndefinedColumn:
  ERROR: column oauth_access_grants.application_id does not exist
LINE 1: ...rants.user_id = identity_links.linked_user_id AND oauth_acce...
                                                             ^
```

`/oauth/userinfo` 응답 시퀀스 추적해보니 직전 단계는 다 200으로 멀쩡했다:

| 시각 | 단계 | 상태 |
|------|------|------|
| 23:47:04 | GET /oauth/authorize | 302 ✓ |
| 23:47:29 | POST /oauth/push/start | 200 ✓ |
| 23:47:39 | POST /api/v1/push_approvals/:id/approve | 200 ✓ |
| 23:47:39 | GET /oauth/push/:id/complete | 302 ✓ |
| 23:47:42 | POST /oauth/token | **200 ✓** |
| 23:47:43 | GET /oauth/userinfo | **500 ❌** |

토큰 발급까지 다 됐는데 userinfo만 깨진다는 건 토큰 자체가 아니라 그 다음 코드 경로에 버그가 있다는 뜻이다.

---

## 진짜 원인 — raw SQL 한 줄의 컬럼명 오타

`Oauth::UserinfoController#show` 안에서 호출되는 `User#linked_user_ids` 메서드가 범인이었다. 코드를 보자.

```ruby
# app/models/user.rb (수정 전)
def linked_user_ids(application_id: nil)
  cid = canonical_id
  scope = IdentityLink.where(primary_user_id: cid)
  if application_id.present?
    scope = scope.joins(<<~SQL.squish)
      INNER JOIN oauth_access_grants
        ON oauth_access_grants.user_id = identity_links.linked_user_id
       AND oauth_access_grants.application_id = #{ActiveRecord::Base.connection.quote(application_id)}
    SQL
    scope = scope.distinct
  end
  scope.pluck(:linked_user_id)
end
```

문제는 두 번째 JOIN 조건의 `oauth_access_grants.application_id`다. 스키마를 보면:

```ruby
# db/schema.rb
create_table "oauth_access_grants", force: :cascade do |t|
  t.string "code", null: false
  t.bigint "oauth_application_id", null: false      # ← 실제 컬럼명
  t.bigint "user_id", null: false
  # ...
  t.index ["oauth_application_id"], name: "..."
end
```

컬럼명은 `oauth_application_id`이지 `application_id`가 아니다. 같은 테이블을 참조하는 다른 9개 컨트롤러는 다 정확하게 썼다:

```ruby
# 다른 곳들: 다 정상
OauthAccessGrant.find_by(code: params[:code], oauth_application_id: app.id)
OauthAccessToken.find_by(jwt_jti: payload["jti"], oauth_application_id: app.id)
.where(oauth_application_id: app_id)
# ... 등등 9곳
```

딱 한 줄, raw SQL string으로 빠져나간 그 곳만 컬럼명을 빼먹었다.

---

## Doorkeeper 스타일 컨벤션 — 왜 `application_id`라고 생각했을까

이 컬럼명 혼란에는 역사적 배경이 있다. Doorkeeper gem의 upstream 스키마는 실제로 `application_id`를 쓴다:

```ruby
# Doorkeeper gem upstream schema
create_table "oauth_access_grants", force: :cascade do |t|
  t.integer "resource_owner_id", null: false
  t.integer "application_id", null: false          # ← upstream은 이것
  t.string "token", null: false
  # ...
end
```

이 프로젝트는 Doorkeeper를 그대로 안 쓰고 자체 OAuth 구현을 했는데, 마이그레이션 짤 때 `t.references :oauth_application` 으로 association을 잡아서 컬럼명이 `oauth_application_id`로 prefix됐다. 결과: Doorkeeper 가이드/Stack Overflow를 검색해서 코드를 적으면 `application_id`가 자연스럽게 떠오르고, 실제로는 그게 아니다. 사람 머리는 일반화하니까.

같은 마이그레이션을 작성한 사람이 다른 컨트롤러는 다 `.find_by(oauth_application_id: ...)` 형태로 썼다는 게 증거다 — AR hash form에서는 컬럼명을 직접 입력해야 하므로 스키마를 보면서 적었고, raw SQL string 한 군데에서만 기억으로 적다가 헛친 것.

---

## 왜 spec이 못 잡았나 — 안전망 ①

spec이 있긴 했다. `spec/requests/oauth/userinfo_spec.rb` 안에 28개 정도의 `it` 블록. 그런데 사고는 났다.

실험: fix를 다시 깨뜨리고 spec을 돌려봤다.

```bash
$ bundle exec rspec spec/requests/oauth/userinfo_spec.rb
...
Finished in 3.95 seconds
20 examples, 15 failures, 1 pending
```

**15/20 fail**. spec은 안전망으로서 완벽하게 작동했다. 즉 spec이 없어서 못 잡은 게 아니라, **누구도 spec을 안 돌렸다**. 정확히는 — CI가 돌긴 했는데 결과가 무시됐다 (뒤에 설명).

또 하나, 모델 단위 spec은 0건이었다. `User#linked_user_ids` 라는 메서드 자체에 대한 unit test가 없었다. request spec에서만 우연히 실행 경로에 걸쳐 있어서 같이 깨졌던 것뿐. 메서드 단독으로 검증하는 spec이 있었다면 의도 자체로 잡혔을 사고다.

---

## 왜 CI가 못 잡았나 — 안전망 ②

GitHub Actions로 CI는 돌고 있었다:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    services:
      postgres:
        image: postgres:16
    steps:
      - name: RSpec
        run: bundle exec rspec
```

Postgres도 정확하게 띄웠으니 `UndefinedColumn`은 실행만 되면 잡혔을 거다. 실제로 `gh run list` 해보니 최근 5개 run 중 4개가 FAIL 상태였다. CI는 정상적으로 빨강 신호를 내고 있었던 거다.

문제는 그 빨강 신호를 누구도 보지 않았다. 1인 운영 프로젝트라 코드리뷰 단계가 없었고, push 후 CI 결과를 확인하지 않은 채 다음 작업으로 넘어갔다.

---

## 왜 배포 게이트가 못 막았나 — 안전망 ③

여기가 진짜 시스템적 문제다. `render.yaml`을 보면:

```yaml
services:
  - type: web
    autoDeploy: true        # ← 이것
```

Render의 `autoDeploy: true` 기본 동작은 **git push 즉시 빌드 시작 (CI 결과 무관)**. CI가 fail이든 success든 상관없이 main에 push되면 prod에 올라간다.

조사해보니 Render는 2025년 후반에 "After CI Checks Pass" 옵션을 추가했다 ([Render Changelog](https://render.com/changelog/skip-auto-deploying-if-ci-checks-fail)). 대시보드에서 **Settings → Auto-Deploy → After CI Checks Pass**로 바꾸면 GitHub Checks API를 폴링해서 모든 체크가 통과해야 배포한다.

또는 더 명시적으로 `autoDeploy: no`로 두고 GitHub Actions에 deploy 단계를 명시적으로 추가하는 패턴도 흔하다:

```yaml
# .github/workflows/deploy.yml
deploy:
  needs: test        # test job이 통과해야만 실행
  runs-on: ubuntu-latest
  steps:
    - run: curl -X POST "$RENDER_DEPLOY_HOOK_URL"
      env:
        RENDER_DEPLOY_HOOK_URL: ${{ secrets.RENDER_DEPLOY_HOOK_URL }}
```

이 프로젝트는 `autoDeploy: true` 그대로였고, CI는 빨강이었으며, 그래서 푸시 즉시 깨진 코드가 prod에 올라갔다.

---

## 왜 알림이 못 깨웠나 — 안전망 ④

prod 500이 며칠 살아있었는데도 발견이 늦은 건 알림이 없었기 때문이다. `Gemfile`을 grep해보니 `sentry-ruby`, `sentry-rails`, `bugsnag`, `rollbar` 어느 것도 없었다.

운영 패턴으로 따지면 1인 프로젝트라도 다음 두 가지는 깔아야 한다:

1. **Error tracking**: Sentry / Rollbar / Honeybadger 중 하나. 500이 발생하면 5분 안에 Slack/이메일로 알림.
2. **Uptime + endpoint monitoring**: 단순히 healthcheck 200만 보는 게 아니라, **핵심 비즈니스 엔드포인트**(`/oauth/userinfo`, `/oauth/token`)에 합성 트래픽을 정기적으로 쏘는 synthetic monitor.

이 둘이 있었으면 사용자가 신고하기 전에 잡혔을 거다.

---

## 4중 보호막을 표로 정리

| 안전망 | 상태 | 왜 못 잡았나 |
|---|---|---|
| 모델 unit spec | ❌ | `linked_user_ids` 호출하는 spec 0건 |
| Request spec | ⚠️ | 존재했고 깨지면 15/20 fail함. 단지 로컬에서 안 돌리고 push |
| CI (GitHub Actions) | ⚠️ | 정상 빨강 신호. 단지 사람이 안 봤음 |
| 배포 게이트 | ❌ | `autoDeploy: true` — CI 무관 즉시 배포 |
| 알림/모니터링 | ❌ | Sentry 미설치, synthetic 없음 |

**다섯 단계** 중 단 한 단계라도 작동했으면 prod까지 안 갔다. 한꺼번에 다 뚫린 게 사고의 본질.

---

## 수정 — 코드 레벨과 운영 레벨

### 코드: raw SQL → AR hash form

가장 간단한 픽스는 컬럼명 한 글자 바꾸기지만, 그건 같은 종류 사고가 또 날 여지를 남긴다. raw SQL string은 ActiveRecord의 reflection 검증을 우회하니까 컬럼명이 바뀌어도 호출되기 전까지는 못 잡는다.

리팩토 후:

```ruby
def linked_user_ids(application_id: nil)
  cid = canonical_id
  scope = IdentityLink.where(primary_user_id: cid)
  if application_id.present?
    scope = scope
      .joins("INNER JOIN oauth_access_grants ON oauth_access_grants.user_id = identity_links.linked_user_id")
      .where(oauth_access_grants: { oauth_application_id: application_id })
      .distinct
  end
  scope.pluck(:linked_user_id)
end
```

핵심은 `.where(oauth_access_grants: { oauth_application_id: application_id })` 형태다. 이 hash form은 ActiveRecord가 스키마 reflection을 통해 컬럼 존재 여부를 검증한다. 컬럼명이 틀리면 `ActiveRecord::StatementInvalid`가 raw SQL보다 훨씬 빠른 시점에 (모델 로드 또는 첫 호출 시점에) 떠서, spec이 없어도 첫 사용에서 폭발한다.

JOIN 자체는 여전히 문자열인데, 거기 적힌 컬럼들(`user_id`, `linked_user_id`)은 단순 FK 컨벤션이라 typo 가능성이 낮다. 가능하면 `IdentityLink`에 association을 추가해서 그것도 reflection-validated 형태로 가는 게 더 안전하지만, 그건 더 큰 리팩토라 일단 hash form까지로 막아뒀다.

### Spec: 모델 unit spec 추가

`spec/models/user_spec.rb`에 회귀 가드 4건을 박았다.

```ruby
describe "#linked_user_ids" do
  let(:primary)   { create(:user) }
  let(:absorbed)  { create(:user) }
  let(:app)       { create(:oauth_application, ...) }
  let(:other_app) { create(:oauth_application, ...) }

  def link!(primary:, linked:)
    IdentityLink.create!(
      primary_user: primary, linked_user: linked,
      merged_via: "explicit_user_merge_logi_app",
      idempotency_key: SecureRandom.uuid,
      occurred_at: Time.current
    )
  end

  it "returns empty when no links exist" do ... end
  it "without application_id returns every linked user" do ... end
  it "with application_id filters to RPs the linked user has grants with" do ... end
  it "excludes linked users with no grant to this app even if other links exist" do ... end
end
```

검증: 일부러 다시 컬럼명 깨뜨리면 3/4가 즉시 fail한다. 다음에 누가 비슷한 raw SQL 들어가도 한 번 더 잡힌다.

### 운영: Render Auto-Deploy CI 게이트

Render 대시보드에서 두 가지 옵션 중 선택:

**옵션 A (간단)**: Service Settings → Auto-Deploy → "After CI Checks Pass" 로 변경. GitHub Checks API가 자동으로 인식돼서 CI 통과 시에만 빌드 시작.

**옵션 B (명시적)**: `render.yaml`에서 `autoDeploy: no` + GitHub Actions에서 test 단계 → deploy 단계로 dependency 걸어서 deploy hook 호출.

```yaml
jobs:
  test:
    # ... bundle exec rspec ...
  deploy:
    needs: test                    # test 통과해야만 실행
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Render deploy
        run: curl -fsSL -X POST "$RENDER_DEPLOY_HOOK_URL"
        env:
          RENDER_DEPLOY_HOOK_URL: ${{ secrets.RENDER_DEPLOY_HOOK_URL }}
```

옵션 B는 deploy 시점 로그까지 GitHub Actions에서 통합 관리 가능해서 1인 운영 환경에서 추적이 쉽다.

### 알림: Sentry + Synthetic

```ruby
# Gemfile
gem "sentry-ruby"
gem "sentry-rails"
```

```ruby
# config/initializers/sentry.rb
Sentry.init do |config|
  config.dsn = ENV["SENTRY_DSN"]
  config.traces_sample_rate = 0.1
  config.environment = Rails.env
end
```

5xx가 나면 즉시 알림. Render의 health check만 보면 healthz는 200이라 깨진 줄 모른다 — 비즈니스 엔드포인트별 모니터링이 필수다.

---

## 실전 교훈

### Raw SQL을 쓸지 말지의 기준

raw SQL string이 무조건 나쁜 건 아니다. 복잡한 윈도우 함수나 CTE처럼 AR로 표현이 어색한 경우엔 raw가 더 명확하다. 하지만 일반적인 INNER JOIN + equality 조건이면 AR hash form이 거의 항상 가능하고, reflection 검증이 따라온다.

판단 기준:

- AR hash form으로 표현 가능 → AR로
- AR로 가능하지만 가독성이 떨어짐 → 일단 AR로 가고 주석으로 보충
- AR로 표현이 부자연스럽거나 성능 차이가 큼 → raw SQL, 단 **반드시 unit spec으로 컬럼명까지 검증**

### "안전망 다섯 개" 점검 체크리스트

새 Rails 프로젝트 셋업할 때 다음 다섯 가지가 다 켜져있는지 본다:

1. RSpec/Minitest + 모델/request spec 커버리지
2. CI (GitHub Actions, GitLab CI 등) — Postgres같이 prod와 같은 DB 엔진으로
3. **CI 빨강 → 자동 차단** (PR 머지 보호 + 배포 게이트)
4. 배포 시스템 (Render, Fly, Heroku 등)이 CI 결과를 명시적으로 확인하는 모드
5. Error tracking (Sentry급) + 핵심 엔드포인트 synthetic monitor

1인 운영이라도 다섯 개 다 깔아둬야 한다. 1인이라서 더 필요하다 — 다른 사람이 잡아줄 사람이 없으니까.

### 표면 증상으로 결론 내리지 말 것

이 사고의 가장 큰 시간 낭비는 "RP 측 401이니까 RP 핸드오프 코드 문제겠지"라고 추정하고 거기를 한참 팠다는 거다. OAuth flow는 단계가 많고, **단계마다 다른 컴포넌트가 다른 로그를 쓴다**. 사용자에게 보이는 마지막 에러 코드는 자주 거짓말한다.

진단 시작점은 항상 가장 깊은 레이어의 로그여야 한다. OIDC IdP 서버 → RP 백엔드 → RP 앱 순서로 흐르니까 IdP 로그를 먼저 본다. IdP가 200이면 그 다음 레이어로 내려간다.

---

## 결론

raw SQL 한 줄의 컬럼명 오타로 시작된 사고였지만, 진짜 문제는 그 한 줄이 prod까지 도달하는 동안 다섯 단계의 안전망이 모두 무력화돼있었던 거다. 코드 수정은 5분, 운영 파이프라인 보강은 그보다 훨씬 오래 걸린다. 사고 직후의 핫픽스보다 **다음 같은 종류 사고를 막는 시스템 조정**이 본질적인 산출물이다.

raw SQL이 필요할 때는 AR hash form으로 컬럼명을 한 번이라도 reflection 통과시키자. CI가 빨강이면 배포 자체를 막자. prod 500은 사람이 신고하기 전에 알림이 떠야 한다. 다 안다고 생각했던 기본기들이지만, 한 번에 다 풀어졌을 때 어떤 일이 일어나는지를 봤다.
