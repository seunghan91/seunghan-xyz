---
title: "Rails Turbo Stream 500 Error Triple Debugging — broadcast, SolidCable, Telegram Markdown"
date: 2026-01-09
draft: false
tags: ["Rails", "Turbo", "ActionCable", "SolidCable", "Telegram", "Debugging", "Ruby"]
description: "When broadcast_append_to 500 errors, SolidCable missing tables, and Telegram Markdown parsing errors all hit at once in Rails 8 + Turbo Stream — how to find and fix each cause."
cover:
  image: "/images/og/rails-turbo-actioncable-500-debug.png"
  alt: "Rails Turbo Actioncable 500 Debug"
  hidden: true
---


Rails 8 + Hotwire(Turbo) 기반 앱을 운영하다 보면 `broadcast_append_to` 계열 콜백이 조용히 500을 내뱉는 경우가 있다. 거기에 SolidCable 초기 설정 문제와 Telegram Bot 메시지 파싱 오류가 겹치면 로그 해석도 헷갈린다. 이번에 세 가지가 한꺼번에 터져서 순서대로 해결한 과정을 정리한다.

---

## Problem 1: `No unique index found for id` — broadcast 콜백 500

### 현상

메시지나 알림을 생성할 때 컨트롤러에서 500이 발생한다. 로그를 보면:

```
MessagesController#create error: No unique index found for id
```

### Cause

Rails `after_create_commit` 콜백 안에서 `broadcast_append_to` 를 호출할 때, 내부적으로 ActionCable 채널을 통해 메시지를 전달하는 과정에서 예외가 발생한다. SolidCable을 쓰는 경우 특히 초기 설정이 완전하지 않으면 이 에러가 자주 나온다.

문제는 콜백 내부의 예외가 **컨트롤러 레벨로 그대로 전파**된다는 점이다. `create!` 는 이미 성공했고 DB에 레코드도 저장됐지만, 브로드캐스트 콜백 실패 때문에 500을 반환하게 된다.

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

### Fix

`broadcast_message` 메서드 안에 `rescue` 를 추가한다. 브로드캐스트 실패는 치명적이지 않다 — 레코드는 이미 저장됐고, 클라이언트는 다음 폴링이나 페이지 이동 시 최신 상태를 받게 된다.

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

---

## Problem 2: `PG::UndefinedTable — solid_cable_messages` 테이블 누락

### 현상

로그에 아래 에러가 섞여 나온다:

```
PG::UndefinedTable: ERROR: relation "solid_cable_messages" does not exist
```

### Cause

Rails 8에서 SolidCable은 별도 migration path(`db/cable_migrate/`)를 사용한다. `database.yml` 설정을 보면:

```yaml
production:
  primary:
    url: <%= ENV["DATABASE_URL"] %>
  cable:
    <<: *primary_production
    migrations_paths: db/cable_migrate
```

`cable` 데이터베이스가 primary와 같은 URL을 가리키더라도, `db/cable_migrate/` 안의 마이그레이션은 일반 `rails db:migrate` 로는 실행이 안 될 수 있다. Render 같은 PaaS에서 deploy hook이 `rails db:migrate` 만 실행하도록 설정되어 있다면 cable migrate는 빠진다.

### 확인 방법

```bash
rails db:migrate:status
```

출력에서 `solid_cable_messages` 관련 마이그레이션이 `down` 상태인지 확인.

### Solution

```bash
rails db:migrate RAILS_ENV=production
```

Rails 7+ 에서는 `db:migrate` 가 multi-database 환경의 모든 데이터베이스를 마이그레이션해야 하는데, 실제로는 `db/cable_migrate` 안의 파일이 `up` 처리되는지 확인이 필요하다. 안 되면:

```bash
rails db:migrate:cable RAILS_ENV=production
# 또는
rails db:migrate DATABASE=cable RAILS_ENV=production
```

`db/cable_migrate/` 에 마이그레이션 파일이 있는지, deploy 스크립트에서 실행되는지 체크하는 게 중요하다.

---

## Problem 3: Telegram 메시지에 `\(`, `\.`, `\-` 이스케이프 문자가 그대로 출력

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

### Cause

앱 내부적으로 description을 **MarkdownV2 형식**으로 빌드하고 있었는데 (`\(`, `\.` 등으로 이스케이프), 이걸 Telegram 메시지에 그대로 넣을 때 `parse_mode: 'Markdown'`(v1)을 사용했다.

Markdown v1은 `\(` 같은 문자를 이스케이프 시퀀스로 인식하지 않는다. 그러므로 백슬래시가 그대로 보이게 된다. `parse_mode: 'MarkdownV2'` 로 바꾸면 되지만, description 내용이 완전히 MarkdownV2 스펙에 맞지 않으면 또 파싱 오류(400)가 발생한다.

### Solution: plain_text 헬퍼로 마크다운 완전 제거

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

### Solution: 메타데이터 키 한글 레이블 + 금액 포매팅

`desired_amount: 20000` 같이 raw key가 출력되는 문제는 description 빌드 단계에서 키 매핑을 추가해 해결했다:

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

`20000` → `20,000원` 으로 출력된다.

---

## 총정리

| 문제 | 원인 | 해결 |
|------|------|------|
| `No unique index found for id` 500 | `after_create_commit` 브로드캐스트 예외가 컨트롤러로 전파 | 콜백 안에 `rescue` 추가 |
| `solid_cable_messages` 테이블 없음 | deploy 시 `db/cable_migrate` 실행 안 됨 | `rails db:migrate` 또는 cable 전용 migrate 명령 실행 |
| Telegram 이스케이프 문자 노출 | MarkdownV2 이스케이프가 Markdown v1 parse_mode에서 그대로 출력 | `plain_text` 헬퍼로 마크다운 전체 제거 후 전송 |
| 메타데이터 raw key 노출 | key name이 그대로 출력 | `METADATA_LABELS` 매핑 + `format_amount` 포매팅 |

Rails + Turbo 조합에서 브로드캐스트 콜백 에러는 예상보다 자주 발생한다. 특히 ActionCable/SolidCable 초기 설정이 완전하지 않거나 다중 DB 마이그레이션이 누락된 경우가 많다. `after_create_commit` 안의 부수 효과는 항상 rescue로 격리하는 습관을 들이자.
