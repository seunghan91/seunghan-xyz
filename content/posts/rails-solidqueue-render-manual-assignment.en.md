---
title: "Rails 8 + SolidQueue Render Deployment Triple Trouble — Missing Tables, AI Agent, Manual Assignment"
date: 2026-01-06
draft: false
tags: ["Rails", "Render", "Solid Queue", "Deployment", "ITSM", "Auto-Assignment"]
description: "Puma crashes because SolidQueue tables are missing, AI agent becomes ticket assignee, and ultimately building manual assignment functionality."
cover:
  image: "/images/og/rails-solidqueue-render-manual-assignment.png"
  alt: "Rails Solidqueue Render Manual Assignment"
  hidden: true
categories: ["Rails"]
---


오늘 Rails 8 기반 ITSM 시스템을 Render에 배포하면서 연속으로 삽질을 했다. 각각 원인이 달랐지만 사슬처럼 연결된 문제들이었다.

---

## 삽질 1 — `Application exited early` with SolidQueue

### Symptoms

Render 배포 로그에 빌드는 성공인데 실행하자마자 죽는다.

```
==> Build successful 🎉
==> Deploying...
==> Running 'bundle exec puma -C config/puma.rb'
[87] Puma starting in cluster mode...
[87] * Preloading application
==> Application exited early
```

### Cause 찾기

Render 로그를 자세히 보면 스택 트레이스가 있다.

```
from solid_queue-1.3.1/lib/solid_queue/configuration.rb in 'recurring_tasks'
from solid_queue-1.3.1/lib/solid_queue/supervisor.rb:15 in 'start'
from solid_queue-1.3.1/lib/puma/plugin/solid_queue.rb:81 in 'start_solid_queue'
...
[69] Detected Solid Queue has gone away, stopping Puma...
```

`SolidQueue::RecurringTask.from_configuration` 내부에서 `load_schema!`가 호출되고, `SchemaCache#columns`에서 터진다. 즉 **`solid_queue_recurring_tasks` 테이블이 DB에 없다**.

### 왜 테이블이 없나?

Rails 8의 SolidQueue, SolidCache, SolidCable은 gem에서 마이그레이션 파일을 복사해와야 한다.

```bash
rails solid_queue:install:migrations
rails db:migrate
```

이 과정을 빠뜨리면 `db/migrate/` 폴더에 solid_queue 관련 마이그레이션이 없다. `db:prepare`가 아무리 돌아도 테이블이 생기지 않는다.

### Solution책 — render-build.sh에 수동 CREATE

이미 `solid_cache`와 `solid_cable` 테이블을 `render-build.sh`에서 수동으로 만들고 있었다. 같은 방식으로 solid_queue 10개 테이블을 추가했다.

```bash
# render-build.sh
bundle exec rails runner "
[
  %q(CREATE TABLE IF NOT EXISTS solid_queue_jobs (
    id bigserial PRIMARY KEY,
    queue_name varchar NOT NULL,
    class_name varchar NOT NULL,
    arguments text,
    priority integer NOT NULL DEFAULT 0,
    active_job_id varchar,
    scheduled_at timestamp,
    finished_at timestamp,
    concurrency_key varchar,
    created_at timestamp NOT NULL,
    updated_at timestamp NOT NULL
  )),
  %q(CREATE TABLE IF NOT EXISTS solid_queue_recurring_tasks (
    id bigserial PRIMARY KEY,
    key varchar NOT NULL,
    schedule varchar NOT NULL,
    command varchar(2048),
    class_name varchar,
    arguments text,
    queue_name varchar,
    priority integer DEFAULT 0,
    static boolean NOT NULL DEFAULT true,
    description text,
    created_at timestamp NOT NULL,
    updated_at timestamp NOT NULL
  )),
  # ... 나머지 8개 테이블
].each { |sql| ActiveRecord::Base.connection.execute(sql) rescue nil }
"
```

`CREATE TABLE IF NOT EXISTS` 패턴이라 이미 테이블이 있으면 무시한다. 안전하다.

`puma.rb`에서 SolidQueue 플러그인 설정도 확인.

```ruby
# config/puma.rb
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]
```

`SOLID_QUEUE_IN_PUMA` 환경변수가 설정되어 있으면 Puma 부팅 시 SolidQueue를 같이 띄운다. 이게 테이블 없이 실행되면 위의 crash가 발생한다.

---

## 삽질 2 — OpenClaw(AI 에이전트)가 티켓 담당자가 됨

### Symptoms

티켓을 생성하면 담당자가 AI 에이전트 계정으로 자동 배정되고, 그 상태에서 에스컬레이션이 발생한다.

```
담당자: OpenClaw
활동: 작업 시작 → 에스컬레이션
```

인간 에이전트에게 가야 할 티켓이 AI 에이전트가 들고 있는 상황.

### Cause

`SmartAssignmentService`의 에이전트 조회 쿼리가 문제였다.

```ruby
# 문제가 된 코드
def find_best_skilled_agent
  available_agents = User.where(role: [:agent, :ai_agent], status: :available)
                         .select { |u| u.wip_count < u.max_wip }
  # ...
end
```

`role: [:agent, :ai_agent]` — 인간 에이전트(`agent`)와 AI 에이전트(`ai_agent`)를 같은 풀에 넣어서 조회한다. 인간 에이전트가 없거나 모두 offline이면 AI 에이전트가 자동 선택된다.

아키텍처 의도는 이랬을 것이다:
- AI 에이전트는 봇 채널에서 들어온 티켓만 처리
- 일반 티켓은 인간 에이전트에게만 배정

하지만 코드가 그렇게 동작하지 않았다.

### Solution

일반 배정 풀에서 `ai_agent`를 제외한다.

```ruby
def find_best_skilled_agent
  # role: :agent 만 — AI 에이전트 제외
  available_agents = User.where(role: :agent, status: :available)
                         .select { |u| u.wip_count < u.max_wip }

  scored_available = score_candidates(available_agents)
  best_available = select_best_agent(scored_available)
  return best_available[:agent] if best_available

  busy_agents = User.where(role: :agent, status: :busy)
  scored_busy = score_candidates(busy_agents, include_busy: true)
  best_busy = select_best_agent(scored_busy)
  return best_busy[:agent] if best_busy

  nil  # 없으면 escalate_to_manager 호출
end
```

같은 이유로 `find_alternative_available_agent`도 수정.

#### 배정 흐름 정리

| 상황 | 동작 |
|------|------|
| 인간 에이전트 available | 즉시 배정 |
| 인간 에이전트 모두 busy | 큐에 추가 (Case B/C/D) |
| 인간 에이전트 없음 | escalate_to_manager → 관리자 알림 |
| 봇 소스 티켓 | AI 에이전트에 round-robin 배정 (별도 로직) |

---

## 삽질 3 — 수동 배정 기능 필요성

### Problem

인간 에이전트가 없거나 모두 offline이면 에스컬레이션만 되고 티켓이 방치된다. 관리자가 직접 배정할 방법이 없다.

### 설계

**사이드바 버튼 (관리자 전용)**
```
AI 티켓 접수
수동 배정  [3]  ← 대기 중 티켓 수 뱃지
```

**`/admin/manual_assignments` 페이지**

- AI 에이전트가 담당인 미해결 티켓 + escalated 상태 티켓 목록
- 각 행에 에이전트 드롭다운 + 배정 버튼

### 구현

```ruby
# app/controllers/admin/manual_assignments_controller.rb
module Admin
  class ManualAssignmentsController < BaseController
    def index
      @stuck_tickets = Ticket.includes(:assignee, :requester)
                             .where(
                               "(assignee_id IN (?) AND aasm_state NOT IN (?)) OR aasm_state = ?",
                               User.ai_agents.select(:id),
                               %w[resolved closed],
                               'escalated'
                             )
                             .order(created_at: :desc)

      @human_agents = User.where(role: :agent).order(:name)
    end

    def assign
      @ticket = Ticket.find(params[:id])
      @agent  = User.find(params[:assignee_id])

      ActiveRecord::Base.transaction do
        @ticket.update!(assignee: @agent)
        @ticket.assign! if @ticket.may_assign?
        TicketAssignment.create!(ticket: @ticket, user: @agent, queue_position: 0)
      end

      redirect_to admin_manual_assignments_path,
                  notice: "티켓 ##{@ticket.id}이(가) #{@agent.name}에게 배정되었습니다."
    end
  end
end
```

라우트.

```ruby
namespace :admin do
  resources :manual_assignments, only: [:index] do
    member do
      patch :assign
    end
  end
end
```

사이드바에서 뱃지 숫자는 매 요청마다 쿼리한다. 캐시를 도입할 수도 있지만 관리자 페이지 트래픽이 많지 않아 일단 이걸로 충분하다.

```erb
<% stuck_count = Ticket.where("...").count rescue 0 %>
<% if stuck_count > 0 %>
  <span class="..."><%= stuck_count %></span>
<% end %>
```

---

## Lessons Learned 요약

1. **Rails 8 Solid* 계열 gem은 마이그레이션 파일을 직접 복사해야 한다.** `db:prepare`가 자동으로 해주지 않는다.

2. **자동 배정 로직에서 role 필터링은 의도적으로 명시해야 한다.** `[:agent, :ai_agent]` 대신 `:agent`만 쓰는 것이 아키텍처 의도와 일치했다.

3. **자동화 로직이 실패할 때를 위한 수동 폴백이 반드시 필요하다.** escalate_to_manager 알림만으로는 부족하다. 관리자가 직접 개입할 수 있는 UI가 있어야 한다.
