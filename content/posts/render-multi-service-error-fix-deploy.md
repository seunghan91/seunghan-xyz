---
title: "Render 6개 서비스 에러 일괄 점검 & 수정 — Stoplight, FK 제약, Puma 7, Solid Stack 삽질 기록"
date: 2026-02-24
draft: false
tags: ["Rails", "Render", "Stoplight", "Telegram", "Puma", "PostgreSQL", "SolidCache", "SolidQueue", "디버깅", "배포"]
description: "Render에 배포된 Rails 8 서비스 6개를 한꺼번에 로그 점검하고, Stoplight 5.x 호환성, Telegram parse_mode, solid_cache 스키마, FK 제약 위반, Puma 7 deprecated API 등 다양한 에러를 수정한 기록."
cover:
  image: "/images/og/render-multi-service-error-fix-deploy.png"
  alt: "Render Multi Service Error Fix Deploy"
  hidden: true
categories: ["Rails", "DevOps"]
---

Render에 올려둔 Rails 서비스 6개가 전부 각자 다른 에러를 토해내고 있었다. 하나씩 로그를 까보니 공통 패턴도 있고, 프로젝트마다 고유한 문제도 있었다. 한 세션에서 전부 수정하고 배포까지 마친 과정을 정리한다.

---

## 전체 상황

Render API로 서비스 6개의 로그를 일괄 조회했다. 각 서비스에 SSH로 하나씩 들어가서 로그를 보는 대신, Render의 REST API를 활용하면 로컬 터미널에서 모든 서비스의 로그를 한꺼번에 스크립트로 수집할 수 있다. 이번 점검에서 확인된 결과는 다음과 같았다:

| 서비스 | 주요 에러 |
|--------|-----------|
| 서비스 A | ERB 문법 에러로 500 (이미 커밋됐지만 미배포) |
| 서비스 B | Stoplight `Light#run` 블록 에러 + Telegram 파싱 에러 |
| 서비스 C | `solid_cache_entries` 테이블 누락 |
| 서비스 D | `PG::UndefinedColumn` + solid_cache 누락 |
| 서비스 E | `PG::DuplicateTable` sessions + Sentry 초기화 에러 |
| 서비스 F | `TaskCleanupJob` FK 위반 + Puma deprecated 경고 |

**공통 패턴**: Rails 8의 Solid Stack (SolidCache, SolidQueue, SolidCable) 초기 설정 문제가 여러 프로젝트에서 반복됐다. Render의 무료/스타터 플랜에서 단일 PostgreSQL 인스턴스를 여러 Rails 컴포넌트가 함께 사용하는 구성이 원인이었다.

---

## 문제 1: Stoplight 5.x API 변경 — `Light#run` 블록 전달

### 현상

```
BizRouter API Error: nothing to run. Please, pass a block into `Light#run`
```

5분마다 반복 발생. API 호출이 전부 실패. 외부 서비스와 통신하는 모든 엔드포인트가 영향을 받았다.

### 원인

Stoplight는 Ruby용 서킷 브레이커(circuit breaker) 라이브러리로, 외부 API 호출이 반복 실패할 때 자동으로 차단(open)하고 일정 시간 후 재시도(half-open)하는 패턴을 구현해준다. 그런데 Stoplight 5.x에서 블록 전달 방식이 바뀌었다. 기존 패턴이 더 이상 작동하지 않는다:

```ruby
# Stoplight 4.x (구 패턴) - 작동 안 함
Stoplight('api-call') {
  HTTParty.get(url)
}.run

# Stoplight 5.x (신 패턴) - 이렇게 바꿔야 함
Stoplight('api-call').run {
  HTTParty.get(url)
}
```

차이는 미묘하다. `Stoplight()` 에 전달한 블록은 5.x에서 무시되고, `.run`에 블록을 전달해야 한다. 에러 메시지가 정확히 이 상황을 설명하는데, 처음 보면 "블록을 넘겼는데 왜?" 싶다. `Gemfile.lock`을 확인하지 않고 gem을 업데이트하면 이런 breaking change를 놓치기 쉽다.

### 해결

```ruby
# 수정 전
def call_api(path, params = {})
  Stoplight("biz-router-#{path}") {
    connection.get(path, params)
  }.run
end

# 수정 후
def call_api(path, params = {})
  Stoplight("biz-router-#{path}").run {
    connection.get(path, params)
  }
end
```

이 변경 하나로 해당 서비스의 모든 외부 API 호출이 정상화됐다. 코드 한 줄의 차이지만 영향 범위가 컸다.

**교훈**: 서킷 브레이커 라이브러리를 업데이트했으면 블록 전달 방식이 바뀌었는지 반드시 확인할 것. Stoplight 5.x는 CHANGELOG에 이 변경을 명시하고 있으나, 에러가 나기 전까지는 눈에 띄지 않는다.

---

## 문제 2: Telegram Bot MarkdownV2 파싱 지옥

### 현상

```
Telegram API error: Bad Request: can't parse entities:
Can't find end of the entity starting at byte offset 395
```

알림 Job이 실행될 때마다 Telegram 메시지 발송이 실패했다. 로그를 보면 `byte offset` 번호가 매번 달랐는데, 이는 메시지 내용(사용자 입력 데이터)에 따라 파싱 실패 위치가 달라지기 때문이다.

### 원인

Telegram의 `parse_mode: 'Markdown'` (legacy)을 사용하면서 메시지 본문에 `_`, `.`, `(`, `)` 같은 특수문자가 포함되면 파싱이 깨진다. 사용자가 입력한 태스크 제목이나 메모에 이런 문자가 들어가면 무조건 실패하는 구조였다.

MarkdownV2로 바꾸면 이스케이프해야 할 문자가 더 많아진다. Telegram MarkdownV2는 `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!` 등 18개 문자를 모두 이스케이프해야 한다. 동적으로 생성되는 메시지에서 이 모든 경우를 처리하는 건 사실상 불가능에 가깝다.

### 해결: HTML parse_mode로 전환

근본적으로 **HTML parse_mode를 쓰는 게 정답**이다. 이스케이프할 문자가 `&`, `<`, `>` 세 개뿐이다:

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
      .gsub(/\\([_*\[\]()~`>#+=|{}.!\-])/, '\1')  # MD 이스케이프 제거
      .gsub(/\*([^*]+?)\*/, '<b>\1</b>')
      .gsub(/`([^`]+?)`/, '<code>\1</code>')
end
```

그리고 모든 `send_message` 호출에서:

```ruby
bot.api.send_message(
  chat_id: chat_id,
  text: markdown_to_html(message),
  parse_mode: 'HTML'  # Markdown → HTML
)
```

HTML 모드에서는 Telegram이 `<b>`, `<i>`, `<code>`, `<pre>`, `<a>` 태그만 파싱하고 나머지는 그대로 출력한다. 사용자 입력이 아무리 복잡해도 세 문자만 치환하면 안전하게 전송할 수 있다.

**교훈**: Telegram Bot에서 Markdown/MarkdownV2 파싱은 삽질의 원천이다. 처음부터 HTML을 쓰자. 이스케이프 규칙이 훨씬 단순하고, 동적 콘텐츠에 훨씬 안전하다.

---

## 문제 3: Solid Stack 테이블 누락 — 여러 프로젝트 공통

### 현상

```
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

이게 3개 프로젝트에서 동시에 발생했다. 서비스 C, D, E 모두 Rails 8로 새로 세팅한 프로젝트들이었다.

### 원인

Rails 8의 `solid_cache` (1.0.x)는 **마이그레이션 파일이 아니라 스키마 파일** (`db/cache_schema.rb`)로 테이블을 관리한다. `rails solid_cache:install`을 실행하면 `config/cache.yml`과 `db/cache_schema.rb`만 생성하고, `db/cache_migrate/` 디렉토리는 만들지 않는다.

```
# solid_cache:install이 생성하는 것
config/cache.yml
db/cache_schema.rb       ← 스키마 정의

# 생성하지 않는 것
db/cache_migrate/        ← 이게 없다!
```

그래서 `bin/render-build.sh`에서 `bundle exec rails db:migrate:cache`를 실행해봐야 마이그레이션 파일이 없으니 아무것도 안 된다. 빌드 로그에서는 에러가 없지만, 런타임에 테이블이 없어서 요청마다 500 에러가 발생한다.

이 설계는 Solid Stack이 별도 데이터베이스를 사용하는 멀티 DB 구성을 전제하기 때문이다. 별도 DB 연결(예: `connects_to database: { writing: :cache }`)을 사용하면 `db:schema:load`가 해당 DB에만 적용되어 안전하다. 그러나 Render 무료/스타터 플랜처럼 DB가 하나뿐인 환경에서는 이 구분이 의미가 없어진다.

### 해결 (방법 2가지)

**방법 1**: `render-build.sh`에서 스키마 로드 사용

```bash
# 수정 전 (작동 안 함)
bundle exec rails db:migrate:cache || true
bundle exec rails db:migrate:queue || true

# 수정 후 (작동함)
SCHEMA=db/cache_schema.rb bundle exec rails db:schema:load || true
SCHEMA=db/queue_schema.rb bundle exec rails db:schema:load || true
```

**방법 2**: `db/cache_migrate/`에 직접 마이그레이션 생성

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

**production에서 cache/queue/cable DB가 primary DB와 같은 경우** (Render 무료/스타터 플랜), 방법 2가 더 안전하다. `db:schema:load`는 기존 테이블을 날릴 위험이 있기 때문이다. 방법 2는 `if_not_exists: true` 덕분에 이미 테이블이 있어도 안전하게 실행된다.

**교훈**: Solid Stack은 멀티 DB 구성을 전제로 설계됐다. 단일 DB에서 쓸 때는 마이그레이션 파일을 직접 만들어야 한다. 공식 문서에는 멀티 DB 구성만 설명하고, 단일 DB 케이스는 별도 언급이 없다.

---

## 문제 4: TaskCleanupJob FK 제약 위반

### 현상

```
PG::ForeignKeyViolation: ERROR: update or delete on table "tasks"
violates foreign key constraint "fk_rails_d8a07e5092" on table "notifications"
```

30일 지난 soft-delete 태스크를 영구 삭제하는 Job에서 발생. Job이 실행될 때마다 실패했고, SolidQueue에서 재시도를 반복하며 에러 로그가 쌓였다.

### 원인

`Notification` 모델에 `belongs_to :task` (직접 FK)가 있는데, `Task` 모델에는 `has_many :notifications`가 **없었다**. CleanupJob에서 Task를 삭제하려고 할 때 PostgreSQL이 FK 제약을 감지하고 거부한다.

Rails의 `dependent: :destroy`나 `dependent: :delete_all`은 모델에 명시된 연관관계를 기반으로 동작한다. 연관관계가 선언되지 않으면 Rails는 자식 레코드를 먼저 삭제하지 않고, PostgreSQL의 FK 제약이 작동하여 에러가 발생한다.

```ruby
# Task 모델 (수정 전) - notifications 연관관계 없음
has_many :notification_schedules, as: :notifiable, dependent: :destroy
# has_many :notifications 가 없다!
```

### 해결

```ruby
# Task 모델 (수정 후)
has_many :notifications, dependent: :destroy  # 추가
has_many :notification_schedules, as: :notifiable, dependent: :destroy
```

그리고 CleanupJob에서 `destroy_all` → `delete_all`로 변경:

```ruby
# 수정 전: 콜백까지 실행 (불필요 + 느림)
Notification.where(task_id: task.id).destroy_all

# 수정 후: SQL DELETE 직접 실행 (빠르고 확실)
Notification.where(notifiable_type: 'Task', notifiable_id: task.id)
            .or(Notification.where(task_id: task.id))
            .delete_all
```

CleanupJob처럼 대량 삭제를 수행하는 경우, `destroy_all`은 각 레코드를 Ruby 객체로 로드하고 콜백을 실행하기 때문에 N개의 레코드라면 N번의 `DELETE` 쿼리가 발생한다. `delete_all`은 단일 SQL로 처리하므로 훨씬 빠르고 FK 타이밍 문제도 없다.

**교훈**: `belongs_to :task`이 있으면 반드시 반대쪽에 `has_many :notifications`를 선언하고 `dependent` 옵션을 지정할 것. 안 그러면 레코드 삭제 시 FK 제약에 걸린다. 또한 대량 삭제 Job에서는 `destroy_all` 대신 `delete_all`을 기본으로 고려할 것.

---

## 문제 5: `find_each`와 default_scope `order` 충돌

### 현상

```
WARN: Scoped order is ignored, use :cursor with :order to configure custom order.
```

5분마다 리마인더 Job이 실행될 때마다 경고 발생. 기능은 동작하지만 로그가 지저분해지고, 배치 처리 순서가 의도와 다를 수 있다.

### 원인

`Task` 모델에 `default_scope { order(created_at: :desc) }`가 있는데, `find_each`는 내부적으로 `ORDER BY id ASC`를 강제한다. 두 order가 충돌하면 Rails가 default_scope의 order를 무시하고 경고를 낸다.

`find_each`가 `id` 기준 배치 처리를 강제하는 이유는 커서 기반 페이지네이션 때문이다. `WHERE id > last_id` 형태로 다음 배치를 가져오는 구조이므로 `id ASC` 정렬이 필수다. 다른 컬럼으로 정렬하면 배치 경계가 올바르게 동작하지 않는다.

### 해결

```ruby
# 수정 전
tasks_with_reminders.find_each do |task|

# 수정 후 — 명시적으로 order를 재지정
tasks_with_reminders.reorder(:id).find_each do |task|
```

`.reorder(:id)`는 기존 스코프의 모든 order를 덮어쓰고 `id ASC`만 적용한다. `find_each` 전에 명시적으로 호출하면 경고가 사라지고 배치 처리가 의도대로 동작한다.

**교훈**: `default_scope`에 `order`가 있으면 `find_each`/`find_in_batches` 사용 시 반드시 `.reorder(:id)`를 붙여줄 것. `default_scope`에 `order`를 넣는 것 자체를 피하는 것도 좋은 방법이다. 범위를 예측하기 어렵게 만든다.

---

## 문제 6: Puma 7 deprecated 콜백

### 현상

```
Use 'before_worker_boot', 'on_worker_boot' is deprecated and will be removed in v8
Use 'before_worker_shutdown', 'on_worker_shutdown' is deprecated and will be removed in v8
```

서버 시작 시마다 경고가 출력됐다. 기능은 동작하지만, Puma 8로 업그레이드하면 DB 커넥션 풀 관리가 무너질 수 있는 시한폭탄이다.

### 원인과 배경

Puma는 멀티 워커 모드에서 fork 기반으로 동작한다. 각 워커가 fork되기 전후로 DB 연결을 재설정해야 커넥션 풀이 제대로 동작한다. 예전에는 `on_worker_boot`/`on_worker_shutdown` 훅을 썼는데, Puma 7에서 훅 이름이 바뀌었다.

### 해결

```ruby
# 수정 전 (Puma 6 이하)
on_worker_boot do
  ActiveRecord::Base.establish_connection
end
on_worker_shutdown do
  ActiveRecord::Base.connection_pool.disconnect!
end

# 수정 후 (Puma 7+)
before_worker_boot do
  ActiveRecord::Base.establish_connection
end
before_worker_shutdown do
  ActiveRecord::Base.connection_pool.disconnect!
end
```

이름만 바뀐 것이지 동작은 동일하다. 조기에 수정하지 않으면 Puma 8 업그레이드 시 훅이 실행되지 않아 워커별로 DB 연결이 공유되거나 끊기는 문제가 발생할 수 있다.

---

## 문제 7: HTML에서 `<button>` 중첩 금지

### 현상 (Vite 빌드 경고)

```
`<button>` cannot be a child of `<button>`.
When rendering this component on the server, the resulting HTML
will be modified by the browser, likely resulting in a hydration_mismatch warning
```

SSR(Inertia.js)과 클라이언트 간 hydration 불일치로 이어질 수 있는 경고다.

### 원인

알림 목록에서 각 항목이 `<button>` (클릭 시 상세 이동)이고, 그 안에 삭제 버튼도 `<button>`이었다. HTML 스펙상 `<button>` 안에 `<button>`을 넣을 수 없다. 브라우저는 이 구조를 파싱할 때 내부 `<button>`을 외부로 끌어내어 DOM을 수정하는데, 이 과정에서 SSR로 렌더링된 HTML과 클라이언트가 파싱한 DOM이 달라지면서 hydration mismatch가 발생한다.

### 해결

내부 버튼을 `<div role="button">`으로 변경하고 키보드 접근성을 유지:

```svelte
<!-- 수정 전 -->
<button onclick={(e) => { e.stopPropagation(); onDelete(id); }}>
  삭제
</button>

<!-- 수정 후 -->
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
  삭제
</div>
```

`role="button"`과 `tabindex="0"`을 함께 지정하면 스크린 리더와 키보드 사용자 모두 접근할 수 있다. `onkeydown`에서 `Enter`와 `Space` 키를 처리하는 것도 버튼 동작의 표준이다.

---

## Render API로 일괄 배포

모든 수정을 커밋 & 푸시한 뒤, Render API로 수동 배포를 트리거했다. Render 대시보드에서 하나씩 클릭하는 대신 스크립트로 자동화할 수 있다:

```bash
curl -X POST "https://api.render.com/v1/services/${SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'
```

`autoDeploy: no`로 설정된 서비스들은 push해도 자동으로 배포되지 않으므로, 이렇게 API 호출로 배포를 직접 트리거해야 한다. `clearCache: "do_not_clear"` 옵션을 쓰면 Docker 레이어 캐시를 재활용하여 빌드 시간을 단축할 수 있다. 의존성이 바뀌지 않은 경우 항상 이 옵션을 사용한다.

6개 서비스를 순서대로 트리거하고, 배포 상태를 확인:

```bash
curl -s "https://api.render.com/v1/services/${SERVICE_ID}/deploys?limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY"
```

반환된 JSON에서 `status` 필드가 `live`가 되면 배포 완료다. `build_started_at`과 `finished_at`으로 배포 소요 시간도 확인할 수 있다.

---

## 정리

| 문제 | 핵심 원인 | 해결 |
|------|-----------|------|
| Stoplight `Light#run` | 5.x에서 블록 전달 위치 변경 | `Stoplight().run { }` 패턴 사용 |
| Telegram 파싱 에러 | MarkdownV2 이스케이프 복잡도 | HTML parse_mode로 전환 |
| solid_cache 테이블 누락 | 스키마 기반이라 migrate가 안 됨 | 마이그레이션 직접 생성 or 스키마 로드 |
| FK 제약 위반 | `has_many :notifications` 누락 | 연관관계 추가 + `delete_all` |
| Scoped order 경고 | default_scope order vs find_each | `.reorder(:id)` 명시 |
| Puma deprecated | 7.x에서 콜백명 변경 | `before_worker_boot/shutdown` |
| button 중첩 | HTML 스펙 위반 | `div[role=button]` |

한 세션에서 6개 서비스의 에러를 전부 수정하고 배포까지 마쳤다. 핵심은 **Render API로 로그를 일괄 조회**해서 전체 상황을 먼저 파악한 것이다. 하나씩 SSH 접속해서 보는 것보다 훨씬 빠르다.

---

## 교훈 정리 (Key Takeaways)

이번 작업에서 반복적으로 느낀 점들을 정리한다.

**1. gem 업데이트는 CHANGELOG를 먼저 읽어라**
Stoplight 5.x의 블록 전달 방식 변경처럼, 메이저 버전 업데이트에는 반드시 breaking change가 있다. `bundle update stoplight` 한 줄이 모든 외부 API 호출을 중단시킬 수 있다. 업데이트 전에 CHANGELOG와 GitHub Releases를 확인하는 습관이 필요하다.

**2. 동적 콘텐츠가 포함된 메시지에는 Markdown을 쓰지 마라**
Telegram이든 Slack이든, 사용자 입력을 그대로 포함하는 메시지라면 이스케이프 규칙이 복잡한 Markdown/MarkdownV2보다 HTML이나 plain text가 안전하다. 파싱 에러는 테스트 환경에서는 잘 나타나지 않고 프로덕션에서 특정 사용자의 입력에만 발생하는 경우가 많다.

**3. Solid Stack은 단일 DB 환경에서 추가 설정이 필요하다**
Rails 8의 기본 설정이 멀티 DB를 전제한다는 점을 인식하고 있어야 한다. Render, Heroku 등의 호스팅 환경에서 비용 절감을 위해 단일 DB를 쓰는 경우, Solid Stack 설치 후 반드시 마이그레이션이 실제로 실행됐는지 확인해야 한다.

**4. 연관관계는 양쪽 모두 선언하라**
`belongs_to :task`가 있으면 반대쪽에 `has_many`를 반드시 선언하는 것이 Rails 컨벤션이다. 연관관계를 빠트리면 FK 제약 위반처럼 예상치 못한 런타임 에러가 발생한다. 모델 코드 리뷰 시 양방향 연관관계 선언 여부를 체크하는 것이 좋다.

**5. Render API를 활용하면 다중 서비스 관리가 훨씬 편해진다**
서비스가 많아질수록 대시보드보다 API 스크립팅이 효율적이다. 로그 조회, 배포 트리거, 환경변수 업데이트 모두 Render REST API로 자동화할 수 있다. 특히 `autoDeploy: no`로 운영하는 서비스가 많을 때 일괄 배포 스크립트는 필수다.
