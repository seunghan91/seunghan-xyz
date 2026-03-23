---
title: "OpenAI Symphony에서 배운 7가지 패턴을 Rails ITSM에 적용한 이야기"
date: 2026-01-16
draft: false
tags: ["Rails", "자동화", "ITSM", "Symphony", "SolidQueue", "아키텍처"]
description: "이슈 트래커 자동화 오케스트레이터 Symphony의 핵심 패턴 7가지를 Rails 기반 티켓 시스템에 실제로 적용해본 기록"
cover:
  image: "/images/og/symphony-patterns-itsm-automation.png"
  alt: "Symphony Patterns Itsm Automation"
  hidden: true
---

AI 에이전트가 티켓을 잡고 방치하는 문제를 겪고 나서, OpenAI의 Symphony 프로젝트를 분석했다. Symphony는 GitHub 이슈 트래커를 폴링하고 코딩 에이전트(Codex, Claude 등)를 자동으로 실행시키는 오케스트레이터인데, 핵심 철학이 인상적이었다:

> **"에이전트를 관리하지 말고, 일(Work)을 관리해라."**

이 철학에서 7가지 패턴을 추출하고, Rails 8 + SolidQueue 기반 ITSM 시스템에 모두 적용했다. 각 패턴이 왜 필요했는지, 어떻게 구현했는지를 실제 코드와 함께 정리한다.

---

## 배경: AI 에이전트 방치 사고

문제의 발단은 단순했다. ITSM 시스템에서 티켓을 AI 에이전트에게 배정했는데, 에이전트가 분석을 시작하고 중간에 타임아웃이 났다. 타임아웃 처리 코드가 없었기 때문에 티켓 상태는 `assigned`로 남았고, 시스템 어디에도 경보가 울리지 않았다.

결국 담당자가 수동으로 확인하기 전까지 2시간 동안 방치됐다. 이런 사고가 반복될 것을 알면서도 "나중에 고쳐야지"라고 미뤄둔 것을 이 기회에 전면적으로 개선했다.

---

## 1. Reconciliation Loop (상태 동기화 루프)

**문제**: 티켓이 배정된 채 방치되어도 아무도 모른다. 에스컬레이션 후에도 조치가 없으면 그냥 묻힌다. 사람이 눈으로 대시보드를 확인해야만 발견할 수 있다.

**Symphony의 접근**: Symphony는 메인 루프에서 전체 이슈 목록을 주기적으로 재검토하여 처리되지 않은 이슈를 발견한다. 단순히 이벤트에만 반응하는 것이 아니라, 주기적으로 현실과 기대 상태를 비교(reconcile)한다.

**해결**: 5분마다 돌면서 전체 티켓 상태를 점검하는 크론잡.

```ruby
class TicketReconciliationJob < ApplicationJob
  queue_as :default

  def perform
    reconcile_ai_agent_tickets    # AI 10분 무활동 -> 에스컬레이션
    reconcile_stale_escalations   # 에스컬레이션 30분 방치 -> 관리자 재알림
    reconcile_stale_assignments   # 인간 4시간 무활동 -> 재배정
    reconcile_in_progress_stalls  # 진행중 24시간 무활동 -> SLA 경고
  end

  private

  def reconcile_ai_agent_tickets
    stale_cutoff = 10.minutes.ago
    Ticket.where(orchestration_state: "agent_working")
          .where(agent_type: :ai)
          .where("orchestration_changed_at < ?", stale_cutoff)
          .find_each do |ticket|
      EscalationService.escalate(ticket, reason: :ai_agent_stalled)
    end
  end

  def reconcile_stale_assignments
    stale_cutoff = 4.hours.ago
    Ticket.where(orchestration_state: "agent_working")
          .where(agent_type: :human)
          .where("orchestration_changed_at < ?", stale_cutoff)
          .find_each do |ticket|
      AutoAssignmentJob.perform_later(ticket.id)
    end
  end
end
```

SolidQueue의 recurring task로 등록:

```yaml
# config/recurring.yml
ticket_reconciliation:
  class: TicketReconciliationJob
  schedule: every 5 minutes
```

이 하나만 있었어도 AI 에이전트 방치 사고를 자동으로 잡았을 것이다. Reconciliation Loop의 핵심은 **능동적 탐지**다. 이벤트 기반 시스템만으로는 이벤트가 발생하지 않는 경우(=방치)를 감지할 수 없다.

---

## 2. Stall Detection (정체 감지)

Symphony는 `stall_timeout_ms`로 에이전트 무활동을 감지한다. 에이전트가 일정 시간 동안 어떤 액션도 취하지 않으면 stall로 판단하고 자동으로 처리한다.

같은 개념을 티켓 상태별로 세분화해서 적용했다:

| 상태 | 정체 기준 | 대응 |
|------|-----------|------|
| `assigned` | 1시간 | 에이전트 리마인더 |
| `assigned` | 4시간 | 자동 재배정 |
| `in_progress` | 24시간 | SLA 경고 |
| `escalated` | 30분 | 관리자 재알림 |
| AI 에이전트 담당 | 10분 | 자동 에스컬레이션 |

왜 상태별로 다른 기준을 두는가? 에이전트가 `assigned` 상태로 4시간 방치되는 것과 `in_progress`로 24시간 방치되는 것은 의미가 다르다. 전자는 시작조차 안 한 것이고, 후자는 진행 중에 막힌 것이다. 대응 방식도 달라야 한다.

이 임계값들은 YAML 설정 파일로 분리해서 코드 수정 없이 조정 가능하게 했다:

```yaml
# config/assignment_policy.yml
stall_thresholds:
  ai_agent_working_minutes: 10
  human_assigned_reminder_hours: 1
  human_assigned_reassign_hours: 4
  in_progress_sla_hours: 24
  escalated_admin_notify_minutes: 30
```

운영 중에 임계값 조정이 필요할 때 배포 없이 YAML만 수정하면 된다.

---

## 3. Retry with Exponential Backoff

**문제**: 자동 배정이 실패하면 끝. 재시도 없음. 에이전트가 30분 후에 available이 되어도 티켓은 여전히 미배정 상태다.

**Symphony의 접근**: 에이전트 실행 실패 시 즉시 재시도하지 않고, 점진적으로 늘어나는 대기 시간 후에 재시도한다. 외부 서비스 장애나 일시적 과부하 상황에서 효과적이다.

**해결**: 에스컬레이션된 티켓에 대해 점진적 재시도.

```ruby
class AutoAssignmentJob < ApplicationJob
  retry_on StandardError, wait: :polynomially_longer, attempts: 5

  def perform(ticket_id, attempt: 0)
    ticket = Ticket.find(ticket_id)
    result = SmartAssignmentService.assign(ticket)

    if result[:success]
      ticket.update_orchestration!("agent_working")
    elsif result[:action] == :escalated && attempt < max_attempts
      delay = [10.seconds * (2 ** attempt), 5.minutes].min
      Rails.logger.info "[AutoAssignment] No agent available for ticket #{ticket_id}, retry in #{delay}s (attempt #{attempt + 1})"
      self.class.set(wait: delay).perform_later(ticket_id, attempt: attempt + 1)
    else
      ticket.update_orchestration!("stalled")
      AdminNotificationService.notify_unassignable(ticket)
    end
  end

  private

  def max_attempts
    5
  end
end
```

대기 시간 시퀀스: 10초 → 20초 → 40초 → 80초 → 160초. 5분 cap.

이 사이에 에이전트가 하나라도 업무를 완료하고 available 상태가 되면 다음 재시도 시 자동 배정된다. 특히 점심시간이나 회의 중처럼 에이전트가 일시적으로 모두 바쁜 상황에서 효과적이다.

`polynomially_longer`는 SolidQueue/ActiveJob의 내장 backoff 전략이다. 별도 구현 없이 `retry_on` 선언 하나로 사용할 수 있다.

---

## 4. WORKFLOW.md 패턴 (정책 파일 in-repo)

Symphony는 레포 루트에 `WORKFLOW.md` 파일을 두어 AI 에이전트에게 어떻게 일해야 하는지 지시한다. YAML front matter로 설정값을 넣고, Markdown 본문으로 프롬프트를 작성한다. 하나의 파일에 정책과 지시가 모두 들어간다.

이 패턴을 ITSM 배정 정책에 그대로 적용했다:

```markdown
---
assignment:
  auto_assign: true
  prefer_human_agents: true
  ai_agent_fallback: false
  max_reassign_attempts: 3

analysis:
  confidence_threshold: 0.75
  auto_apply_category: true
---

## Ticket Analysis Prompt

You are an ITSM ticket analysis AI.
Analyze the given ticket to determine:
- Category: incident / service_request / problem / change
- Priority: critical / high / medium / low
- Required Skills: [array]
- Estimated Resolution Time: [minutes]

Be conservative with priority assignments. Default to medium unless
there is clear evidence of business impact.
...
```

파일을 파싱하는 서비스:

```ruby
class WorkflowPolicyLoader
  def self.load(path = Rails.root.join("config/ticket_workflow.md"))
    content = File.read(path)
    front_matter, prompt = content.split("---\n", 3)[1..2]
    policy = YAML.safe_load(front_matter)
    { policy: policy, prompt: prompt.strip }
  end
end
```

이 방식의 장점은 **버전 관리**다. AI 프롬프트 변경이 Git 커밋으로 추적된다. 배정 정책을 바꿀 때 PR을 통해 리뷰할 수 있다. 코드를 건드리지 않고 정책과 프롬프트를 수정할 수 있다.

---

## 5. Concurrency Control (동시성 제어)

Symphony는 `max_concurrent_agents`와 상태별 제한을 둔다. 동시에 너무 많은 에이전트가 실행되면 서로 간섭하거나 API 한도를 초과한다.

ITSM에서도 같은 문제가 있다. 에이전트당 티켓 수 제한이 없으면 특정 에이전트에게만 티켓이 몰리거나, critical 티켓이 쌓여서 아무것도 제때 처리되지 않는다.

```yaml
# config/assignment_policy.yml
concurrency:
  max_concurrent_ai_analysis: 5
  max_tickets_per_agent: 5
  max_critical_per_agent: 2
  max_concurrent_by_category:
    incident: 10
    change: 3        # 변경 요청은 동시 처리를 낮게 제한
    problem: 5
    service_request: 15
```

이 설정을 `AssignmentPolicy` 서비스가 읽어서 배정 시 검증한다:

```ruby
class AssignmentPolicy
  def self.can_accept_ticket?(agent, ticket)
    return false if agent.wip_count >= max_tickets_per_agent

    if ticket.critical?
      critical_count = agent.assigned_tickets.where(priority: :critical).active.count
      return false if critical_count >= max_critical_per_agent
    end

    category_limit = max_concurrent_by_category[ticket.category]
    if category_limit
      team_category_count = Ticket.where(category: ticket.category)
                                   .where(orchestration_state: "agent_working")
                                   .count
      return false if team_category_count >= category_limit
    end

    true
  end

  private

  def self.policy
    @policy ||= YAML.safe_load_file(Rails.root.join("config/assignment_policy.yml"))
  end

  def self.max_tickets_per_agent
    policy.dig("concurrency", "max_tickets_per_agent") || 5
  end

  def self.max_critical_per_agent
    policy.dig("concurrency", "max_critical_per_agent") || 2
  end

  def self.max_concurrent_by_category
    policy.dig("concurrency", "max_concurrent_by_category") || {}
  end
end
```

에이전트당 critical 2개 제한이 특히 중요하다. critical만 3-4개 쌓이면 어느 것도 제대로 처리하지 못한다. WIP 제한은 칸반의 핵심 원칙이기도 하다.

`change` 카테고리를 3으로 낮게 설정한 이유: 변경 요청은 검토와 승인 프로세스가 복잡해서 동시에 많이 처리하면 실수가 늘어난다. 느리더라도 신중하게 처리하는 것이 낫다.

---

## 6. Internal Orchestration States (내부 상태 머신)

**문제**: AASM 상태(`opened -> assigned -> in_progress -> resolved`)는 사용자에게 보여주는 것이다. 하지만 자동화 로직에서는 더 세밀한 상태 추적이 필요하다. 사용자 상태와 시스템 내부 상태를 같은 컬럼에 넣으면 양쪽 다 복잡해진다.

**Symphony의 접근**: Symphony는 이슈의 GitHub 상태(open/closed)와는 별개로 내부 처리 상태를 관리한다. 이슈가 GitHub에서 열려 있어도 Symphony 내부에서는 `processing`, `waiting_for_review`, `completed` 등 다른 상태를 가진다.

**해결**: `orchestration_state` 컬럼을 별도로 추가.

```
사용자에게 보이는 상태 (AASM):
  opened -> assigned -> in_progress -> resolved -> closed

내부 자동화 상태 (orchestration_state):
  unprocessed -> ai_analyzing -> awaiting_assignment
              -> agent_working -> stalled -> reassigning
```

마이그레이션:

```ruby
add_column :tickets, :orchestration_state, :string, default: "unprocessed"
add_column :tickets, :orchestration_changed_at, :datetime
add_column :tickets, :assignment_attempts, :integer, default: 0
add_index :tickets, :orchestration_state
add_index :tickets, :orchestration_changed_at
```

`orchestration_changed_at`에 인덱스를 거는 것이 중요하다. Reconciliation Job이 매 5분마다 이 컬럼으로 쿼리하기 때문에 인덱스 없이는 풀 테이블 스캔이 발생한다.

각 처리 단계에서 orchestration state를 업데이트:

```ruby
# AI 분석 시작 시
ticket.update_orchestration!("ai_analyzing")

# 분석 완료, 배정 대기
ticket.update_orchestration!("awaiting_assignment")

# 에이전트 배정 완료
ticket.update_orchestration!("agent_working")

# 배정 실패
ticket.update_orchestration!("stalled")
```

`update_orchestration!` 헬퍼:

```ruby
def update_orchestration!(state)
  update!(
    orchestration_state: state,
    orchestration_changed_at: Time.current
  )
end
```

Reconciliation Job이 `orchestration_changed_at`을 기준으로 stuck 티켓을 정확히 집어낸다.

---

## 7. Workspace Isolation (격리 실행)

Symphony는 이슈마다 별도 디렉토리에서 에이전트를 실행한다. 크로스 컨타미네이션 방지가 목적이다. 에이전트 A가 이슈 #123을 처리하면서 남긴 파일이나 상태가 에이전트 B의 이슈 #456 처리에 영향을 주지 않는다.

AI 분석에서 같은 원리를 적용했다. 티켓마다 고유 세션 ID를 생성:

```ruby
class TicketAnalyzer
  def initialize(ticket)
    @ticket = ticket
    @session_id = "ticket-#{ticket.id}-#{SecureRandom.hex(4)}"
    @client = BizRouter::Client.new
  end

  def analyze
    Rails.logger.info "[TicketAnalyzer] Starting analysis for ticket #{@ticket.id} (session: #{@session_id})"

    response = @client.analyze_ticket(
      build_ticket_payload.merge(session_id: @session_id)
    )

    parse_and_apply_analysis(response)
  rescue => e
    Rails.logger.error "[TicketAnalyzer] Analysis failed for ticket #{@ticket.id} (session: #{@session_id}): #{e.message}"
    raise
  end

  private

  def build_ticket_payload
    {
      ticket_id: @ticket.id,
      title: @ticket.title,
      description: @ticket.description,
      reporter: @ticket.reporter.name,
      created_at: @ticket.created_at.iso8601
    }
  end
end
```

단순해 보이지만 효과적이다. AI API가 대화 컨텍스트를 유지하는 경우, 다른 티켓의 분석 맥락이 섞이지 않는다. 로그에서도 `session_id`로 특정 티켓의 전체 처리 과정을 추적할 수 있어서 디버깅이 편해진다.

---

## 전체 적용 후 아키텍처

7가지 패턴을 적용한 후 전체 흐름:

```
티켓 생성
  |
  v
[TicketAnalysisJob] -- orchestration: ai_analyzing
  |                     session_id: ticket-123-a1b2 (격리 실행)
  v
AI 분석 완료 -- orchestration: awaiting_assignment
  |
  v
[AutoAssignmentJob] -- AssignmentPolicy.can_accept_ticket? (동시성 제어)
  |                    retry with backoff (최대 5회, 10초~5분)
  |-- 성공 --> orchestration: agent_working
  |-- 실패 --> orchestration: stalled, escalate
  v
[TicketReconciliationJob] (매 5분, Reconciliation Loop)
  |-- AI 10분 방치 --> 에스컬레이션
  |-- 인간 4시간 방치 --> 재배정 (AutoAssignmentJob 재실행)
  |-- 에스컬레이션 30분 --> 관리자 재알림
  v
모든 임계값은 config/assignment_policy.yml에서 조정 (정책 외부화)
```

각 컴포넌트의 책임이 명확히 분리되어 있다. `TicketReconciliationJob`은 감지만 한다. 실제 배정은 `AutoAssignmentJob`이 한다. 정책 판단은 `AssignmentPolicy`가 한다.

---

## 핵심 교훈

1. **한 번 배정하고 끝이 아니다.** 주기적으로 reconcile해서 방치를 자동 감지해야 한다. 이벤트 기반 시스템만으로는 이벤트가 발생하지 않는 상황(방치)을 감지할 수 없다. Reconciliation Loop가 가장 임팩트가 크다.

2. **실패를 당연시하라.** 자동 배정은 실패할 수 있다. 재시도 + backoff가 있으면 에이전트가 available이 되는 순간 자동 복구된다. 실패를 예외 상황이 아니라 정상적인 케이스로 설계해야 한다.

3. **사용자 상태와 시스템 상태를 분리하라.** AASM은 사람한테 보여주는 것, `orchestration_state`는 자동화가 쓰는 것. 섞으면 양쪽 다 복잡해진다. 인덱스 위치도 달라진다.

4. **정책은 코드 밖으로.** YAML 설정 파일 하나로 임계값과 제한을 관리하면 배포 없이 운영 튜닝이 가능하다. 프롬프트도 마찬가지다.

5. **격리는 단순해도 효과적이다.** `session_id` 한 줄이면 AI 분석 간 컨텍스트 오염을 막을 수 있다. 부작용으로 로그 추적도 쉬워진다.

Symphony의 코드가 아니라 **철학**을 가져온 것이 핵심이다. "에이전트를 관리하지 말고, 일을 관리해라" — 이 한 문장이 전체 설계를 바꿨다. AI 에이전트가 몇 개이든, 어떤 종류이든 상관없이 시스템이 안정적으로 돌아가게 되었다.

---

## Key Takeaways

- **Reconciliation Loop**: 이벤트 기반만으로는 방치를 감지할 수 없다. 주기적으로 현실과 기대 상태를 비교하는 루프가 반드시 필요하다.
- **Stall Detection**: 상태별로 다른 정체 기준을 두어야 한다. `assigned` 1시간과 `in_progress` 24시간은 의미가 다르다.
- **Exponential Backoff**: 일시적 실패를 영구 실패로 만들지 마라. 점진적 재시도로 시스템이 자가 복구하게 하라.
- **Policy as Code**: AI 프롬프트와 배정 규칙을 Git으로 버전 관리하면 정책 변경이 PR 리뷰로 추적된다.
- **Concurrency Limits**: WIP 제한 없이는 특정 에이전트에게 티켓이 몰리거나 critical 티켓이 쌓인다. 카테고리별로 동시 처리 상한을 두어라.
- **Internal vs. External State**: 사용자용 상태와 자동화용 내부 상태는 분리해야 한다. 섞으면 양쪽 다 복잡해진다.
- **Workspace Isolation**: 세션 ID 하나로 AI 분석 간 컨텍스트 오염을 막고 로그 추적성도 확보할 수 있다.
