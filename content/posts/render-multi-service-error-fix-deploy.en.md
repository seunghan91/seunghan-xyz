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


Render에 올려둔 Rails 서비스 6개가 전부 각자 다른 에러를 토해내고 있었다. 하나씩 로그를 까보니 공통 패턴도 있고, 프로젝트마다 고유한 문제도 있었다. 한 세션에서 전부 수정하고 배포까지 마친 과정을 정리한다.

---

## 전체 상황

Render API로 서비스 6개의 로그를 일괄 조회했다. 결과:

| 서비스 | 주요 에러 |
|--------|-----------|
| 서비스 A | ERB 문법 에러로 500 (이미 커밋됐지만 미배포) |
| 서비스 B | Stoplight `Light#run` 블록 에러 + Telegram 파싱 에러 |
| 서비스 C | `solid_cache_entries` 테이블 누락 |
| 서비스 D | `PG::UndefinedColumn` + solid_cache 누락 |
| 서비스 E | `PG::DuplicateTable` sessions + Sentry 초기화 에러 |
| 서비스 F | `TaskCleanupJob` FK 위반 + Puma deprecated 경고 |

**공통 패턴**: Rails 8의 Solid Stack (SolidCache, SolidQueue, SolidCable) 초기 설정 문제가 여러 프로젝트에서 반복됐다.

---

## Problem 1: Stoplight 5.x API 변경 — `Light#run` 블록 전달

### 현상

```
BizRouter API Error: nothing to run. Please, pass a block into `Light#run`
```

5분마다 반복 발생. API 호출이 전부 실패.

### Cause

Stoplight 5.x에서 API가 바뀌었다. 기존 패턴이 더 이상 작동하지 않는다:

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

차이는 미묘하다. `Stoplight()` 에 전달한 블록은 5.x에서 무시되고, `.run`에 블록을 전달해야 한다. 에러 메시지가 정확히 이 상황을 설명하는데, 처음 보면 "블록을 넘겼는데 왜?" 싶다.

### Solution

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

**교훈**: 서킷 브레이커 라이브러리를 업데이트했으면 블록 전달 방식이 바뀌었는지 반드시 확인할 것.

---

## Problem 2: Telegram Bot MarkdownV2 파싱 지옥

### 현상

```
Telegram API error: Bad Request: can't parse entities:
Can't find end of the entity starting at byte offset 395
```

### Cause

Telegram의 `parse_mode: 'Markdown'` (legacy)을 사용하면서 메시지 본문에 `_`, `.`, `(`, `)` 같은 특수문자가 포함되면 파싱이 깨진다. MarkdownV2로 바꾸면 이스케이프할 문자가 더 많아져서 오히려 복잡해진다.

### Solution: HTML parse_mode로 전환

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

**교훈**: Telegram Bot에서 Markdown/MarkdownV2 파싱은 삽질의 원천이다. 처음부터 HTML을 쓰자. 이스케이프 규칙이 훨씬 단순하다.

---

## Problem 3: Solid Stack 테이블 누락 — 여러 프로젝트 공통

### 현상

```
PG::UndefinedTable: ERROR: relation "solid_cache_entries" does not exist
```

이게 3개 프로젝트에서 동시에 발생했다.

### Cause

Rails 8의 `solid_cache` (1.0.x)는 **마이그레이션 파일이 아니라 스키마 파일** (`db/cache_schema.rb`)로 테이블을 관리한다. `rails solid_cache:install`을 실행하면 `config/cache.yml`과 `db/cache_schema.rb`만 생성하고, `db/cache_migrate/` 디렉토리는 만들지 않는다.

```
# solid_cache:install이 생성하는 것
config/cache.yml
db/cache_schema.rb       ← 스키마 정의

# 생성하지 않는 것
db/cache_migrate/        ← 이게 없다!
```

그래서 `bin/render-build.sh`에서 `bundle exec rails db:migrate:cache`를 실행해봐야 마이그레이션 파일이 없으니 아무것도 안 된다.

### Solution (방법 2가지)

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

**production에서 cache/queue/cable DB가 primary DB와 같은 경우** (Render 무료/스타터 플랜), 방법 2가 더 안전하다. `db:schema:load`는 기존 테이블을 날릴 위험이 있다.

**교훈**: Solid Stack은 멀티 DB 구성을 전제로 설계됐다. 단일 DB에서 쓸 때는 마이그레이션 파일을 직접 만들어야 한다.

---

## Problem 4: TaskCleanupJob FK 제약 위반

### 현상

```
PG::ForeignKeyViolation: ERROR: update or delete on table "tasks"
violates foreign key constraint "fk_rails_d8a07e5092" on table "notifications"
```

30일 지난 soft-delete 태스크를 영구 삭제하는 Job에서 발생.

### Cause

`Notification` 모델에 `belongs_to :task` (직접 FK)가 있는데, `Task` 모델에는 `has_many :notifications`가 **없었다**. CleanupJob에서 notifications를 먼저 삭제하려고 시도하지만, `destroy_all`이 콜백을 거치면서 타이밍 이슈가 생길 수 있다.

```ruby
# Task 모델 (수정 전) - notifications 연관관계 없음
has_many :notification_schedules, as: :notifiable, dependent: :destroy
# has_many :notifications 가 없다!
```

### Solution

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

**교훈**: `belongs_to :task`이 있으면 반드시 반대쪽에 `has_many :notifications`를 선언하고 `dependent` 옵션을 지정할 것. 안 그러면 레코드 삭제 시 FK 제약에 걸린다.

---

## Problem 5: `find_each`와 default_scope `order` 충돌

### 현상

```
WARN: Scoped order is ignored, use :cursor with :order to configure custom order.
```

5분마다 리마인더 Job이 실행될 때마다 경고 발생.

### Cause

`Task` 모델에 `default_scope { order(created_at: :desc) }`가 있는데, `find_each`는 내부적으로 `order(:id)`를 강제한다. 두 order가 충돌하면 Rails가 default_scope의 order를 무시하고 경고를 낸다.

### Solution

```ruby
# 수정 전
tasks_with_reminders.find_each do |task|

# 수정 후 — 명시적으로 order를 재지정
tasks_with_reminders.reorder(:id).find_each do |task|
```

**교훈**: `default_scope`에 `order`가 있으면 `find_each`/`find_in_batches` 사용 시 반드시 `.reorder(:id)`를 붙여줄 것.

---

## Problem 6: Puma 7 deprecated 콜백

### 현상

```
Use 'before_worker_boot', 'on_worker_boot' is deprecated and will be removed in v8
Use 'before_worker_shutdown', 'on_worker_shutdown' is deprecated and will be removed in v8
```

### Solution

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

---

## Problem 7: HTML에서 `<button>` 중첩 금지

### 현상 (Vite 빌드 경고)

```
`<button>` cannot be a child of `<button>`.
When rendering this component on the server, the resulting HTML
will be modified by the browser, likely resulting in a hydration_mismatch warning
```

### Cause

알림 목록에서 각 항목이 `<button>`이고, 그 안에 삭제 버튼도 `<button>`이었다. HTML 스펙상 `<button>` 안에 `<button>`을 넣을 수 없다.

### Solution

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

---

## Render API로 일괄 배포

모든 수정을 커밋 & 푸시한 뒤, Render API로 수동 배포를 트리거했다:

```bash
curl -X POST "https://api.render.com/v1/services/${SERVICE_ID}/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'
```

`autoDeploy: no`로 설정된 서비스들은 이렇게 API 호출로 배포해야 한다. 6개 서비스를 순서대로 트리거하고, 배포 상태를 확인:

```bash
curl -s "https://api.render.com/v1/services/${SERVICE_ID}/deploys?limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY"
```

---

## Summary

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
