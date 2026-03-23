---
title: "Rails Turbo Stream 500 에러 3종 세트 디버깅 — broadcast, SolidCable, Telegram Markdown"
date: 2026-01-09
draft: false
tags: ["Rails", "Turbo", "ActionCable", "SolidCable", "Telegram", "디버깅", "Ruby"]
description: "Rails 8 + Turbo Stream 환경에서 broadcast_append_to 500 에러, SolidCable 테이블 누락, Telegram Markdown 파싱 오류가 한꺼번에 터졌을 때 각각 어떻게 원인을 찾고 해결했는지 기록한다."
cover:
  image: "/images/og/rails-turbo-actioncable-500-debug.png"
  alt: "Rails Turbo Actioncable 500 Debug"
  hidden: true
categories: ["Rails", "Hotwire"]
---

Rails 8 + Hotwire(Turbo) 기반 앱을 운영하다 보면 `broadcast_append_to` 계열 콜백이 조용히 500을 내뱉는 경우가 있다. 거기에 SolidCable 초기 설정 문제와 Telegram Bot 메시지 파싱 오류가 겹치면 로그 해석도 헷갈린다. 이번에 세 가지가 한꺼번에 터져서 순서대로 해결한 과정을 정리한다.

이 글에서 다루는 세 문제는 서로 독립적이지만, 실제 운영 환경에서는 이렇게 한꺼번에 맞닥뜨리는 경우가 많다. 각 문제를 격리해서 하나씩 해결하는 접근이 중요하다.

---

## 문제 1: `No unique index found for id` — broadcast 콜백 500

### 현상

메시지나 알림을 생성할 때 컨트롤러에서 500이 발생한다. 로그를 보면:

```
MessagesController#create error: No unique index found for id
```

에러 메시지만 보면 인덱스 문제처럼 읽히지만, 실제로는 ActionCable 브로드캐스트 과정에서 발생한 예외가 컨트롤러까지 전파된 것이다. 레코드 자체는 DB에 정상 저장된 상태다.

### 원인

Rails `after_create_commit` 콜백 안에서 `broadcast_append_to`를 호출할 때, 내부적으로 ActionCable 채널을 통해 메시지를 전달하는 과정에서 예외가 발생한다. SolidCable을 쓰는 경우 특히 초기 설정이 완전하지 않으면 이 에러가 자주 나온다.

문제는 콜백 내부의 예외가 **컨트롤러 레벨로 그대로 전파**된다는 점이다. `create!`는 이미 성공했고 DB에 레코드도 저장됐지만, 브로드캐스트 콜백 실패 때문에 500을 반환하게 된다.

Rails의 `after_create_commit`은 트랜잭션이 커밋된 뒤에 실행된다. 따라서 이 시점에서 예외가 발생하더라도 DB 레코드는 롤백되지 않는다. 그러나 Rails는 콜백 체인의 예외를 잡지 않고 그대로 상위로 던지기 때문에, 컨트롤러 액션이 500으로 응답하게 된다. 사용자는 에러 페이지를 보지만 실제 데이터는 정상적으로 저장돼 있는 혼란스러운 상황이 된다.

### 모델 코드 (수정 전)

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

### 수정

`broadcast_message` 메서드 안에 `rescue`를 추가한다. 브로드캐스트 실패는 치명적이지 않다 — 레코드는 이미 저장됐고, 클라이언트는 다음 폴링이나 페이지 이동 시 최신 상태를 받게 된다.

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

`Notification` 모델의 `broadcast_to_user` 콜백도 동일한 패턴으로 수정했다:

```ruby
def broadcast_to_user
  broadcast_append_to(...)
  broadcast_replace_to(...)
rescue => e
  Rails.logger.error "[Notification] broadcast_to_user failed: #{e.message}"
end
```

> **핵심 원칙**: `after_create_commit` 안의 브로드캐스트 콜백은 부수 효과(side effect)다. 실패해도 트랜잭션 자체가 롤백되어선 안 된다. 반드시 rescue로 감싸자.

### 더 나아가기: 재시도와 모니터링

단순히 rescue로 에러를 삼키는 것에서 한 발 더 나아가, 실제 프로덕션에서는 다음을 고려할 수 있다.

**재시도 로직**: 일시적인 네트워크 문제나 SolidCable 큐 지연으로 인한 실패라면, 백그라운드 잡으로 재시도하는 패턴이 유효하다.

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
  # 필요하면 재시도 잡 큐잉
  # BroadcastRetryJob.perform_later(self.class.name, id)
end
```

**에러 모니터링**: Sentry 등 에러 트래킹 서비스를 쓴다면, 브로드캐스트 실패를 경고 레벨로 리포트해 추세를 파악하면 좋다. 잦은 브로드캐스트 실패는 SolidCable 설정 문제나 DB 부하의 조기 신호일 수 있다.

---

## 문제 2: `PG::UndefinedTable — solid_cable_messages` 테이블 누락

### 현상

로그에 아래 에러가 섞여 나온다:

```
PG::UndefinedTable: ERROR: relation "solid_cable_messages" does not exist
```

ActionCable 연결 자체는 되지만 메시지 전달이 실패하고, 위 에러가 반복적으로 로그에 쌓인다.

### SolidCable이란?

Rails 8에서 새로 도입된 SolidCable은 Redis 없이 PostgreSQL(또는 다른 관계형 DB)을 ActionCable 어댑터로 사용할 수 있게 해주는 라이브러리다. Redis 의존성을 줄이고 인프라를 단순화하는 것이 목적이다.

SolidCable은 `solid_cable_messages`라는 전용 테이블에 메시지를 저장하고 폴링 방식으로 구독자에게 전달한다. 이 테이블이 없으면 ActionCable 브로드캐스트 전체가 동작하지 않는다.

### 원인

Rails 8에서 SolidCable은 별도 migration path(`db/cable_migrate/`)를 사용한다. `database.yml` 설정을 보면:

```yaml
production:
  primary:
    url: <%= ENV["DATABASE_URL"] %>
  cable:
    <<: *primary_production
    migrations_paths: db/cable_migrate
```

`cable` 데이터베이스가 primary와 같은 URL을 가리키더라도, `db/cable_migrate/` 안의 마이그레이션은 일반 `rails db:migrate`로는 실행이 안 될 수 있다. Render 같은 PaaS에서 deploy hook이 `rails db:migrate`만 실행하도록 설정되어 있다면 cable migrate는 빠진다.

Rails의 multi-database 마이그레이션 처리 방식 때문에 이 문제가 발생한다. `db:migrate`는 기본적으로 `db/migrate/` 경로만 바라보며, `migrations_paths`로 별도 경로가 지정된 데이터베이스는 별도로 마이그레이션을 실행해야 한다.

### 확인 방법

```bash
rails db:migrate:status
```

출력에서 `solid_cable_messages` 관련 마이그레이션이 `down` 상태인지 확인한다. 아래처럼 보이면 문제다:

```
down    20241001000000  CreateSolidCableMessages
```

### 해결

```bash
rails db:migrate RAILS_ENV=production
```

Rails 7+ 에서는 `db:migrate`가 multi-database 환경의 모든 데이터베이스를 마이그레이션해야 하는데, 실제로는 `db/cable_migrate` 안의 파일이 `up` 처리되는지 확인이 필요하다. 안 되면:

```bash
rails db:migrate:cable RAILS_ENV=production
# 또는
rails db:migrate DATABASE=cable RAILS_ENV=production
```

### Deploy 스크립트 수정

Render, Fly.io, Heroku 등 PaaS를 사용한다면 deploy 명령을 명시적으로 수정해야 한다.

**Render의 경우** (`render.yaml`):

```yaml
services:
  - type: web
    name: myapp
    buildCommand: bundle install && bundle exec rails assets:precompile
    startCommand: bundle exec rails db:migrate && bundle exec rails db:migrate DATABASE=cable && bundle exec rails server
```

또는 `bin/render-build.sh` 스크립트를 만들어:

```bash
#!/usr/bin/env bash
set -o errexit

bundle install
bundle exec rails assets:precompile
bundle exec rails assets:clean
bundle exec rails db:migrate
bundle exec rails db:migrate DATABASE=cable
```

`db/cable_migrate/` 에 마이그레이션 파일이 있는지, deploy 스크립트에서 실행되는지 체크하는 게 중요하다.

### SolidQueue와의 혼동 주의

Rails 8에는 SolidCable 외에도 SolidQueue(백그라운드 잡), SolidCache(캐시)가 있다. 각각 별도의 migration path를 가진다:

- SolidCable: `db/cable_migrate/`
- SolidQueue: `db/queue_migrate/`
- SolidCache: `db/cache_migrate/`

전부 사용한다면 deploy 스크립트에 세 가지를 모두 포함시켜야 한다.

---

## 문제 3: Telegram 메시지에 `\(`, `\.`, `\-` 이스케이프 문자가 그대로 출력

### 현상

Telegram Bot으로 받은 메시지에 이런 식으로 raw 이스케이프 문자가 노출된다:

```
신청자: seunghan \(seunghan@example\.co\.kr\)
요청 금액: 20000
```

기대했던 출력:
```
신청자: seunghan (seunghan@example.co.kr)
요청 금액: 20,000원
```

두 가지 문제가 있었다:
1. `\(`, `\.`, `\-` 등 MarkdownV2 이스케이프 문자가 Telegram에 그대로 노출됨
2. `desired_amount: 20000` 같이 raw 키 이름이 숫자 그대로 출력됨

### Telegram Markdown 버전 차이 이해하기

Telegram Bot API는 두 가지 Markdown 파싱 모드를 지원한다:

**Markdown (v1)**: 오래된 방식. `*bold*`, `_italic_`, `` `code` `` 등을 지원하지만 이스케이프 문법이 없다. `\(`는 이스케이프 시퀀스로 인식하지 않고 백슬래시를 그대로 출력한다.

**MarkdownV2**: 현재 권장 방식. 특수문자(`. ( ) [ ] { } ~ > # + - = | ! \`)를 모두 백슬래시로 이스케이프해야 한다. 이스케이프 안 된 특수문자가 있으면 400 에러가 발생한다.

### 원인

앱 내부적으로 description을 **MarkdownV2 형식**으로 빌드하고 있었는데(`\(`, `\.` 등으로 이스케이프), 이걸 Telegram 메시지에 그대로 넣을 때 `parse_mode: 'Markdown'`(v1)을 사용했다.

Markdown v1은 `\(`같은 문자를 이스케이프 시퀀스로 인식하지 않는다. 그러므로 백슬래시가 그대로 보이게 된다. `parse_mode: 'MarkdownV2'`로 바꾸면 되지만, description 내용이 완전히 MarkdownV2 스펙에 맞지 않으면 또 파싱 오류(400)가 발생한다.

즉 세 가지 선택지가 있다:
1. `parse_mode` 없이 plain text로 전송 → 마크다운 렌더링 없음
2. `parse_mode: 'MarkdownV2'`로 바꾸고 내용을 완전히 MarkdownV2 스펙에 맞춤
3. 마크다운을 전부 제거하고 plain text로 전송

Telegram 알림 메시지는 굵은 글씨나 링크가 굳이 필요 없는 경우가 많으므로, 세 번째 방법이 가장 단순하고 안전하다.

### 해결: plain_text 헬퍼로 마크다운 완전 제거

Telegram 알림 메시지에는 굳이 마크다운 포매팅이 필요 없으므로, 전송 전에 모든 마크다운을 벗겨내는 `plain_text` 헬퍼를 만들었다:

```ruby
def self.plain_text(text)
  text.to_s
      .gsub(/\*\*(.*?)\*\*/m, '\1')   # **bold** 제거
      .gsub(/\*(.*?)\*/m, '\1')        # *italic* 제거
      .gsub(/\\([_*\[\]()~`>#+=|{}.!\-])/, '\1')  # MarkdownV2 이스케이프 제거
      .strip
end
```

그리고 알림 전송 시:

```ruby
# Before
desc = escape(ticket.description.to_s.truncate(200))

# After
desc = plain_text(ticket.description.to_s.truncate(300))
```

`parse_mode` 옵션도 제거하거나 명시적으로 빼는 것이 좋다. `parse_mode`를 전달하지 않으면 Telegram은 plain text로 처리한다.

### 해결: 메타데이터 키 한글 레이블 + 금액 포매팅

`desired_amount: 20000`같이 raw key가 출력되는 문제는 description 빌드 단계에서 키 매핑을 추가해 해결했다:

```ruby
METADATA_LABELS = {
  "desired_amount" => "요청 금액",
  "current_amount" => "현재 금액",
  "target_amount"  => "목표 금액",
  "quota"          => "할당량",
  "target_date"    => "목표 일자",
  "department"     => "부서",
  "system"         => "대상 시스템",
  "priority"       => "우선순위"
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
  "#{num.to_s.reverse.gsub(/(\d{3})(?=\d)/, '\1,').reverse}원"
end
```

`20000` → `20,000원`으로 출력된다.

### Telegram 메시지 길이 제한 주의

Telegram Bot API의 메시지 길이 제한은 4096자다. `truncate(300)`은 안전한 범위지만, 메타데이터가 많거나 description이 긴 경우에는 전체 메시지가 4096자를 초과하지 않도록 주의해야 한다. 초과하면 400 에러(`Bad Request: message is too long`)가 발생한다.

---

## 총정리

| 문제 | 원인 | 해결 |
|------|------|------|
| `No unique index found for id` 500 | `after_create_commit` 브로드캐스트 예외가 컨트롤러로 전파 | 콜백 안에 `rescue` 추가 |
| `solid_cable_messages` 테이블 없음 | deploy 시 `db/cable_migrate` 실행 안 됨 | `rails db:migrate` 또는 cable 전용 migrate 명령 실행 |
| Telegram 이스케이프 문자 노출 | MarkdownV2 이스케이프가 Markdown v1 parse_mode에서 그대로 출력 | `plain_text` 헬퍼로 마크다운 전체 제거 후 전송 |
| 메타데이터 raw key 노출 | key name이 그대로 출력 | `METADATA_LABELS` 매핑 + `format_amount` 포매팅 |

Rails + Turbo 조합에서 브로드캐스트 콜백 에러는 예상보다 자주 발생한다. 특히 ActionCable/SolidCable 초기 설정이 완전하지 않거나 다중 DB 마이그레이션이 누락된 경우가 많다. `after_create_commit` 안의 부수 효과는 항상 rescue로 격리하는 습관을 들이자.

---

## Key Takeaways

1. **`after_create_commit` 콜백의 브로드캐스트는 항상 `rescue`로 감싸라.** 브로드캐스트는 부수 효과다. 실패해도 메인 트랜잭션이 롤백되거나 500을 반환해서는 안 된다.

2. **SolidCable(SolidQueue, SolidCache)은 별도 migration path를 가진다.** `db/cable_migrate/`는 `rails db:migrate`만으로는 실행되지 않을 수 있다. PaaS deploy 스크립트에 `rails db:migrate DATABASE=cable`을 명시적으로 추가하자.

3. **Telegram MarkdownV2와 Markdown v1은 완전히 다른 파싱 규칙을 따른다.** 내부 포매팅과 전송 parse_mode를 혼용하면 이스케이프 문자가 그대로 노출된다. 알림 메시지에는 마크다운을 완전히 제거한 plain text 전송이 가장 안전하다.

4. **에러 메시지를 액면 그대로 믿지 마라.** `No unique index found for id`는 인덱스 문제가 아니라 ActionCable 내부 예외가 전파된 것이었다. 스택 트레이스 전체를 봐야 진짜 원인을 알 수 있다.

5. **Rails 8의 Solid 삼총사(SolidCable, SolidQueue, SolidCache)를 같이 쓴다면 deploy 스크립트에 세 가지 migrate를 모두 포함시켜라.** 각각 `db/cable_migrate/`, `db/queue_migrate/`, `db/cache_migrate/`를 바라본다.
