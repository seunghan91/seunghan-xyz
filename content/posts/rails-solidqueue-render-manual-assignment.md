---
title: "Rails 8 + SolidQueue Render 배포 삽질 3연타 — 테이블 누락, AI 담당자, 수동 배정"
date: 2026-01-06
draft: false
tags: ["Rails", "Render", "Solid Queue", "배포", "ITSM", "자동배정"]
description: "SolidQueue 테이블이 없어서 Puma가 죽고, AI 에이전트가 티켓 담당자가 되고, 결국 수동 배정 기능을 만들기까지"
cover:
  image: "/images/og/rails-solidqueue-render-manual-assignment.png"
  alt: "Rails Solidqueue Render Manual Assignment"
  hidden: true
categories: ["Rails", "DevOps"]
---

오늘 Rails 8 기반 ITSM 시스템을 Render에 배포하면서 연속으로 삽질을 했다. 각각 원인이 달랐지만 사슬처럼 연결된 문제들이었다. 배포 로그를 보고 디버깅하고, 코드를 고치고, 새로운 문제를 발견하는 과정을 기록해 둔다.

이 글에서 다루는 스택은 Rails 8.1, SolidQueue 1.3.1, Puma, PostgreSQL이고 배포 환경은 Render.com이다.

---

## 삽질 1 — `Application exited early` with SolidQueue

### 증상

Render 배포 로그에 빌드는 성공인데 실행하자마자 죽는다.

```
==> Build successful 🎉
==> Deploying...
==> Running 'bundle exec puma -C config/puma.rb'
[87] Puma starting in cluster mode...
[87] * Preloading application
==> Application exited early
```

`Build successful` 메시지가 나왔으니 빌드 단계는 정상이다. 문제는 실행 단계다. Puma 프로세스가 시작조차 못 하고 종료된다.

### 원인 찾기

Render 로그를 자세히 보면 스택 트레이스가 있다.

```
from solid_queue-1.3.1/lib/solid_queue/configuration.rb in 'recurring_tasks'
from solid_queue-1.3.1/lib/solid_queue/supervisor.rb:15 in 'start'
from solid_queue-1.3.1/lib/puma/plugin/solid_queue.rb:81 in 'start_solid_queue'
...
[69] Detected Solid Queue has gone away, stopping Puma...
```

`SolidQueue::RecurringTask.from_configuration` 내부에서 `load_schema!`가 호출되고, `SchemaCache#columns`에서 터진다. 즉 **`solid_queue_recurring_tasks` 테이블이 DB에 없다**.

SolidQueue는 Puma 플러그인으로 실행될 때 애플리케이션 부팅 중에 DB 스키마를 확인한다. 이 시점에 필요한 테이블이 없으면 SolidQueue supervisor가 즉시 종료하고, Puma 플러그인이 이를 감지해 Puma 자체를 내려버린다. 그래서 `Application exited early`가 나오는 것이다.

### 왜 테이블이 없나?

Rails 8에서 도입된 Solid 계열 gem — SolidQueue, SolidCache, SolidCable — 은 gem 내부에 마이그레이션 파일이 패키징되어 있고, 이를 프로젝트 `db/migrate/` 폴더로 복사하는 설치 명령이 별도로 있다.

```bash
rails solid_queue:install:migrations
rails solid_cache:install:migrations
rails solid_cable:install:migrations
rails db:migrate
```

이 과정을 빠뜨리면 `db/migrate/` 폴더에 solid_queue 관련 마이그레이션 파일이 존재하지 않는다. `db:prepare`나 `db:schema:load`가 아무리 돌아도 해당 테이블이 생기지 않는다. Rails의 일반 마이그레이션 메커니즘은 `db/migrate/` 안에 있는 파일만 처리하기 때문이다.

SolidQueue가 필요로 하는 테이블은 총 10개다:
- `solid_queue_jobs`
- `solid_queue_recurring_tasks`
- `solid_queue_scheduled_executions`
- `solid_queue_ready_executions`
- `solid_queue_claimed_executions`
- `solid_queue_blocked_executions`
- `solid_queue_failed_executions`
- `solid_queue_pauses`
- `solid_queue_processes`
- `solid_queue_semaphores`

### 해결책 — render-build.sh에 수동 CREATE

이미 `solid_cache`와 `solid_cable` 테이블을 `render-build.sh`에서 수동으로 만들고 있었다. 이 패턴은 Render의 free tier처럼 단일 서비스로 DB 마이그레이션을 관리해야 할 때 흔히 쓰인다. 같은 방식으로 solid_queue 10개 테이블을 추가했다.

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

`CREATE TABLE IF NOT EXISTS` 패턴이라 이미 테이블이 있으면 무시한다. 안전하다. 재배포할 때마다 이 스크립트가 실행되지만 테이블이 이미 존재하면 아무 일도 일어나지 않는다.

이 방식의 트레이드오프도 있다. Rails 마이그레이션 버전 관리에서 벗어나기 때문에, SolidQueue가 업그레이드되어 스키마가 바뀌면 `render-build.sh`도 수동으로 업데이트해야 한다. 장기적으로는 마이그레이션 파일을 정상적으로 복사해두는 편이 낫다.

`puma.rb`에서 SolidQueue 플러그인 설정도 확인.

```ruby
# config/puma.rb
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]
```

`SOLID_QUEUE_IN_PUMA` 환경변수가 설정되어 있으면 Puma 부팅 시 SolidQueue를 같이 띄운다. 이게 테이블 없이 실행되면 위의 crash가 발생한다. Render 환경변수에 `SOLID_QUEUE_IN_PUMA=1`이 설정되어 있었기 때문에 반드시 테이블이 존재해야 했다.

---

## 삽질 2 — OpenClaw(AI 에이전트)가 티켓 담당자가 됨

### 증상

티켓을 생성하면 담당자가 AI 에이전트 계정으로 자동 배정되고, 그 상태에서 에스컬레이션이 발생한다.

```
담당자: OpenClaw
활동: 작업 시작 → 에스컬레이션
```

인간 에이전트에게 가야 할 티켓이 AI 에이전트가 들고 있는 상황이다. AI 에이전트는 WIP 한도를 채울 때까지 티켓을 받지만, 실제로 처리하지 못하면 결국 에스컬레이션을 트리거한다. 이러면 관리자 알림은 가지만 티켓은 limbo 상태에 빠진다.

### 원인

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

하지만 코드가 그렇게 동작하지 않았다. `SmartAssignmentService`는 티켓 소스(봇 채널인지 일반 채널인지)를 따지지 않고 항상 같은 쿼리를 실행했다. 그 결과 야간이나 점심처럼 인간 에이전트가 모두 offline인 시간대에 들어온 티켓이 전부 OpenClaw에게 배정됐다.

이 버그가 처음에 잘 보이지 않았던 이유는 개발 환경에 항상 인간 에이전트가 available 상태로 시드돼 있었기 때문이다. AI 에이전트가 선택되는 조건 자체가 테스트되지 않았다.

### 해결

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

같은 이유로 `find_alternative_available_agent`도 수정했다. 이 메서드는 주 배정 대상 에이전트가 갑자기 offline이 될 때 대체 에이전트를 찾는 역할을 하는데, 여기서도 `ai_agent`가 포함되면 같은 문제가 반복된다.

`score_candidates` 내부 로직은 에이전트의 스킬 매칭 점수, 현재 WIP 비율, 평균 응답 시간 등을 고려해 점수를 산출한다. 에이전트 풀 자체가 잘못 구성되면 아무리 점수 계산이 정교해도 의미가 없다.

#### 배정 흐름 정리

| 상황 | 동작 |
|------|------|
| 인간 에이전트 available | 즉시 배정 |
| 인간 에이전트 모두 busy | 큐에 추가 (Case B/C/D) |
| 인간 에이전트 없음 | escalate_to_manager → 관리자 알림 |
| 봇 소스 티켓 | AI 에이전트에 round-robin 배정 (별도 로직) |

봇 소스 티켓의 AI 에이전트 배정은 별도 서비스(`BotTicketAssignmentService`)가 담당하도록 분리되어 있다. 두 서비스가 같은 에이전트 풀을 공유하지 않는 구조가 명확한 아키텍처다.

---

## 삽질 3 — 수동 배정 기능 필요성

### 문제

인간 에이전트가 없거나 모두 offline이면 에스컬레이션만 되고 티켓이 방치된다. 관리자가 직접 배정할 방법이 없다.

`escalate_to_manager`는 관리자에게 알림을 보내는 것까지만 한다. 관리자가 알림을 받아도 시스템 안에서 할 수 있는 게 없으면 결국 Slack이나 이메일로 수동 지시를 내려야 한다. 이건 ITSM의 목적에 어긋난다.

자동화 시스템이 실패할 때를 위한 탈출구가 반드시 필요하다.

### 설계

**사이드바 버튼 (관리자 전용)**
```
AI 티켓 접수
수동 배정  [3]  ← 대기 중 티켓 수 뱃지
```

**`/admin/manual_assignments` 페이지**

- AI 에이전트가 담당인 미해결 티켓 + escalated 상태 티켓 목록
- 각 행에 에이전트 드롭다운 + 배정 버튼

뱃지의 숫자가 0이 아니면 관리자가 즉시 개입이 필요한 상황임을 인식할 수 있다. "3개 있다"는 것만 보여줘도 관리자가 페이지를 열어볼 동기가 생긴다.

### 구현

컨트롤러는 두 가지 역할을 한다. `index`에서 stuck 티켓 목록을 보여주고, `assign`에서 실제 배정을 처리한다.

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

`assign` 액션에서 트랜잭션을 사용하는 이유가 중요하다. `@ticket.update!`, `@ticket.assign!`(AASM 상태 전이), `TicketAssignment.create!` 이 세 가지는 반드시 함께 성공하거나 함께 실패해야 한다. 중간에 하나만 실패하면 담당자는 바뀌었는데 상태는 그대로이거나, 상태는 바뀌었는데 assignment 기록이 없는 불일치 상태가 생길 수 있다.

`may_assign?`을 확인하는 이유는 티켓이 이미 `in_progress` 상태인 경우 `assign!`을 호출하면 AASM 예외가 발생하기 때문이다. 상태 전이 가능 여부를 먼저 확인하고 호출하는 것이 안전하다.

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

`only: [:index]`로 제한하고 `assign`은 member action으로 분리한 이유는 배정이 특정 티켓 ID에 대한 액션이기 때문이다. RESTful 설계 관점에서 `/admin/manual_assignments/:id/assign` 경로가 의미가 명확하다.

사이드바에서 뱃지 숫자는 매 요청마다 쿼리한다. 캐시를 도입할 수도 있지만 관리자 페이지 트래픽이 많지 않아 일단 이걸로 충분하다.

```erb
<% stuck_count = Ticket.where("...").count rescue 0 %>
<% if stuck_count > 0 %>
  <span class="..."><%= stuck_count %></span>
<% end %>
```

`rescue 0`을 붙인 이유는 레이아웃에서 매 요청마다 실행되는 코드이기 때문이다. DB 연결이 잠깐 끊기거나 쿼리가 실패할 때 사이드바 전체가 500 에러로 터지는 것을 방지한다. 관리자 UI의 부가적인 카운터 하나 때문에 페이지 전체가 죽으면 안 된다.

---

## 교훈 요약

1. **Rails 8 Solid* 계열 gem은 마이그레이션 파일을 직접 복사해야 한다.** `db:prepare`가 자동으로 해주지 않는다. `rails solid_queue:install:migrations`를 프로젝트 초기 설정에 명시적으로 포함시켜야 한다. Render처럼 마이그레이션 파일 없이 수동 CREATE로 우회할 경우, gem 업그레이드 시 스키마 변경을 반드시 수동으로 추적해야 한다.

2. **자동 배정 로직에서 role 필터링은 의도적으로 명시해야 한다.** `[:agent, :ai_agent]` 대신 `:agent`만 쓰는 것이 아키텍처 의도와 일치했다. 이 종류의 버그는 개발 환경 시드 데이터가 production 시나리오를 충분히 커버하지 않을 때 발견하기 어렵다. "인간 에이전트가 모두 offline인 상황"을 명시적으로 테스트하는 케이스를 추가해야 한다.

3. **자동화 로직이 실패할 때를 위한 수동 폴백이 반드시 필요하다.** escalate_to_manager 알림만으로는 부족하다. 관리자가 직접 개입할 수 있는 UI가 있어야 한다. 모든 자동화에는 인간이 개입할 수 있는 탈출구를 설계 단계부터 고려해야 한다.

---

## Key Takeaways

- **Solid 계열 gem 마이그레이션**: `rails solid_queue:install:migrations` 명령으로 마이그레이션 파일을 먼저 복사해야 한다. 이 단계를 건너뛰면 Puma 시작 시점에 테이블 부재로 crash가 발생한다.
- **Puma + SolidQueue 통합 실패 패턴**: `SOLID_QUEUE_IN_PUMA=1` 환경변수가 있을 때 SolidQueue 초기화 실패는 Puma 프로세스 전체를 종료시킨다. 스택 트레이스는 Render 로그 상단이 아닌 중간에 숨어있으니 주의 깊게 스크롤해야 한다.
- **AI 에이전트와 인간 에이전트 분리**: 자동 배정 서비스에서 두 종류의 에이전트를 같은 쿼리 풀에 넣으면 예상치 못한 상황에서 AI 에이전트가 인간 업무를 가로챈다. role 필터는 방어적으로, 명시적으로 작성해야 한다.
- **수동 배정 UI는 선택이 아니라 필수**: 자동 배정이 아무리 정교해도 edge case는 존재한다. 관리자가 시스템 안에서 직접 배정할 수 있는 화면이 없으면 장애 대응 비용이 급증한다.
- **트랜잭션으로 상태 일관성 보호**: 티켓 배정처럼 여러 테이블을 동시에 업데이트하는 작업은 반드시 트랜잭션으로 묶어야 한다. 부분 성공은 디버깅하기 가장 어려운 종류의 버그다.
- **`rescue 0` 패턴**: 레이아웃에 삽입되는 카운터 쿼리에는 예외 처리를 넣어야 한다. 사소한 DB 오류가 전체 페이지를 500으로 만들지 않도록.
