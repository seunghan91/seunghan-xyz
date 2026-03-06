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

AI 에이전트가 티켓을 잡고 방치하는 문제를 겪고 나서, OpenAI의 Symphony 프로젝트를 분석했다. Symphony는 이슈 트래커를 폴링하고 코딩 에이전트를 자동으로 실행시키는 오케스트레이터인데, 핵심 철학이 인상적이었다:

> **"에이전트를 관리하지 말고, 일(Work)을 관리해라."**

이 철학에서 7가지 패턴을 추출하고, Rails 8 + SolidQueue 기반 ITSM 시스템에 모두 적용했다.

---

## 1. Reconciliation Loop (상태 동기화 루프)

**문제**: 티켓이 배정된 채 방치되어도 아무도 모른다. 에스컬레이션 후에도 조치 없으면 그냥 묻힌다.

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
end
```

SolidQueue의 recurring task로 등록:

```yaml
# config/recurring.yml
ticket_reconciliation:
  class: TicketReconciliationJob
  schedule: every 5 minutes
```

이 하나만 있었어도 어제 AI 에이전트 방치 사고를 자동으로 잡았을 것이다.

---

## 2. Stall Detection (정체 감지)

Symphony는 `stall_timeout_ms`로 에이전트 무활동을 감지한다. 같은 개념을 티켓 상태별로 적용:

| 상태 | 정체 기준 | 대응 |
|------|-----------|------|
| `assigned` | 1시간 | 에이전트 리마인더 |
| `assigned` | 4시간 | 자동 재배정 |
| `in_progress` | 24시간 | SLA 경고 |
| `escalated` | 30분 | 관리자 재알림 |
| AI 에이전트 담당 | 10분 | 자동 에스컬레이션 |

이 임계값들은 YAML 설정 파일로 빼서 코드 수정 없이 조정 가능하게 했다.

---

## 3. Retry with Exponential Backoff

**문제**: 자동 배정이 실패하면 끝. 재시도 없음. 에이전트가 30분 후에 available이 되어도 티켓은 여전히 미배정.

**해결**: 에스컬레이션된 티켓에 대해 점진적 재시도.

```ruby
class AutoAssignmentJob < ApplicationJob
  retry_on StandardError, wait: :polynomially_longer, attempts: 5

  def perform(ticket_id, attempt: 0)
    result = SmartAssignmentService.assign(ticket)

    if !result[:success] && result[:action] == :escalated && attempt < max_attempts
      delay = [10.seconds * (2 ** attempt), 5.minutes].min
      self.class.set(wait: delay).perform_later(ticket_id, attempt: attempt + 1)
    end
  end
end
```

10초 -> 20초 -> 40초 -> 80초 -> 160초. 5분 cap. 이 사이에 에이전트가 하나라도 비면 자동 배정된다.

---

## 4. WORKFLOW.md 패턴 (정책 파일 in-repo)

Symphony는 YAML front matter + Markdown 프롬프트를 하나의 파일에 넣어 버전 관리한다. 같은 방식을 적용:

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
...
```

AI 프롬프트와 배정 규칙이 코드에서 분리되니까, 정책 변경을 PR 리뷰로 추적할 수 있다.

---

## 5. Concurrency Control (동시성 제어)

Symphony는 `max_concurrent_agents`와 상태별 제한을 둔다. ITSM에서는:

```yaml
# config/assignment_policy.yml
concurrency:
  max_concurrent_ai_analysis: 5
  max_tickets_per_agent: 5
  max_critical_per_agent: 2
  max_concurrent_by_category:
    incident: 10
    change: 3        # 변경 요청은 동시 처리 제한
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

    true
  end
end
```

에이전트당 critical 2개 제한은 중요하다. critical만 3-4개 쌓이면 어느 것도 제대로 처리 못한다.

---

## 6. Internal Orchestration States (내부 상태 머신)

**문제**: AASM 상태(`opened -> assigned -> in_progress -> resolved`)는 사용자에게 보여주는 것. 하지만 자동화 로직에서는 더 세밀한 상태 추적이 필요하다.

**해결**: `orchestration_state` 컬럼을 별도로 추가.

```
사용자에게 보이는 상태 (AASM):
  opened -> assigned -> in_progress -> resolved -> closed

내부 자동화 상태 (orchestration_state):
  unprocessed -> ai_analyzing -> awaiting_assignment -> agent_working -> stalled -> reassigning
```

마이그레이션:

```ruby
add_column :tickets, :orchestration_state, :string, default: "unprocessed"
add_column :tickets, :orchestration_changed_at, :datetime
add_column :tickets, :assignment_attempts, :integer, default: 0
```

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

Reconciliation Job이 이 상태를 보고 stuck 티켓을 정확히 집어낸다.

---

## 7. Workspace Isolation (격리 실행)

Symphony는 이슈마다 별도 디렉토리에서 에이전트를 실행한다. 크로스 컨타미네이션 방지.

AI 분석에서 같은 원리를 적용 -- 티켓마다 고유 세션 ID를 생성:

```ruby
class TicketAnalyzer
  def initialize(ticket)
    @ticket = ticket
    @session_id = "ticket-#{ticket.id}-#{SecureRandom.hex(4)}"
    @client = BizRouter::Client.new
  end

  def analyze
    response = @client.analyze_ticket(
      build_ticket_payload.merge(session_id: @session_id)
    )
    # ...
  end
end
```

단순하지만 효과적이다. AI API가 대화 컨텍스트를 유지하는 경우, 다른 티켓의 분석 맥락이 섞이지 않는다.

---

## 전체 적용 후 아키텍처

```
티켓 생성
  |
  v
[TicketAnalysisJob] -- orchestration: ai_analyzing
  |                     session_id: ticket-123-a1b2
  v
AI 분석 완료 -- orchestration: awaiting_assignment
  |
  v
[AutoAssignmentJob] -- AssignmentPolicy 검증
  |                    retry with backoff (최대 5회)
  |-- 성공 --> orchestration: agent_working
  |-- 실패 --> orchestration: stalled, escalate
  v
[TicketReconciliationJob] (매 5분)
  |-- AI 10분 방치 --> 에스컬레이션
  |-- 인간 4시간 방치 --> 재배정
  |-- 에스컬레이션 30분 --> 관리자 재알림
  v
모든 임계값은 config/assignment_policy.yml에서 조정
```

---

## 핵심 교훈

1. **한 번 배정하고 끝이 아니다.** 주기적으로 reconcile해서 방치를 자동 감지해야 한다. 이게 가장 효과 크다.

2. **실패를 당연시하라.** 자동 배정은 실패할 수 있다. 재시도 + backoff가 있으면 에이전트가 available이 되는 순간 자동 복구된다.

3. **사용자 상태와 시스템 상태를 분리하라.** AASM은 사람한테 보여주는 것, orchestration_state는 자동화가 쓰는 것. 섞으면 양쪽 다 복잡해진다.

4. **정책은 코드 밖으로.** YAML 설정 파일 하나로 임계값과 제한을 관리하면 배포 없이 운영 튜닝이 가능하다.

5. **격리는 단순해도 효과적이다.** `session_id` 한 줄이면 AI 분석 간 컨텍스트 오염을 막을 수 있다.

Symphony의 코드가 아니라 **철학**을 가져온 것이 핵심이다. "에이전트를 관리하지 말고, 일을 관리해라" -- 이 한 문장이 전체 설계를 바꿨다.
