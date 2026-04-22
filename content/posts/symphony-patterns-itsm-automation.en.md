---
title: "7 Patterns Learned from OpenAI Symphony Applied to Rails ITSM"
date: 2026-01-16
draft: false
tags: ["Rails", "Automation", "ITSM", "Symphony", "SolidQueue", "Architecture"]
categories: ["AI Engineering", "Rails"]
description: "Applying 7 core patterns from the issue tracker automation orchestrator Symphony to a Rails-based ticket system."
cover:
  image: "/images/og/symphony-patterns-itsm-automation.png"
  alt: "Symphony Patterns Itsm Automation"
  hidden: true
---

After running into a problem where an AI agent grabbed a ticket and abandoned it, I dug into OpenAI's Symphony project. Symphony is an orchestrator that polls a GitHub issue tracker and automatically runs coding agents (Codex, Claude, etc.). Its core philosophy stuck with me:

> **"Don't manage agents — manage the Work."**

I extracted 7 patterns from that philosophy and applied all of them to a Rails 8 + SolidQueue based ITSM system. Here's what each pattern solves, how it's implemented, and why it matters.

---

## Background: The AI Agent Abandonment Incident

The root cause was straightforward. A ticket was assigned to an AI agent, the agent started its analysis, and then timed out midway. There was no timeout-handling code, so the ticket status remained `assigned` and no alerts fired anywhere in the system.

The ticket sat abandoned for two hours until a human manually checked the dashboard. This kind of silent failure was going to keep happening, so I took the opportunity to overhaul the entire automation architecture.

---

## 1. Reconciliation Loop

**Problem**: When a ticket is assigned and then abandoned, nobody knows. Even after escalation, if nobody acts, the ticket just gets buried. The only way to discover it is for a human to manually check a dashboard.

**Symphony's approach**: Symphony's main loop periodically re-examines the full list of open issues to find ones that haven't been handled. Rather than reacting only to events, it regularly compares actual state against expected state — this is the reconcile step.

**Solution**: A cron job that runs every 5 minutes and inspects the entire ticket state.

```ruby
class TicketReconciliationJob < ApplicationJob
  queue_as :default

  def perform
    reconcile_ai_agent_tickets    # AI idle 10 min -> escalate
    reconcile_stale_escalations   # Escalated 30 min idle -> re-alert admin
    reconcile_stale_assignments   # Human 4 hr idle -> reassign
    reconcile_in_progress_stalls  # In-progress 24 hr idle -> SLA warning
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

Register it as a SolidQueue recurring task:

```yaml
# config/recurring.yml
ticket_reconciliation:
  class: TicketReconciliationJob
  schedule: every 5 minutes
```

This single job would have caught the AI agent abandonment incident automatically. The key insight behind a Reconciliation Loop is **active detection**. An event-driven system alone cannot detect the absence of events — which is exactly what abandonment is.

---

## 2. Stall Detection

Symphony uses `stall_timeout_ms` to detect agent inactivity. If an agent goes a certain amount of time without taking any action, Symphony classifies it as stalled and handles it automatically.

I applied the same concept per ticket state, with different thresholds for each:

| State | Stall Threshold | Action |
|-------|----------------|--------|
| `assigned` | 1 hour | Send agent reminder |
| `assigned` | 4 hours | Auto-reassign |
| `in_progress` | 24 hours | SLA warning |
| `escalated` | 30 minutes | Re-alert admin |
| AI agent handling | 10 minutes | Auto-escalate |

Why different thresholds per state? A ticket stuck in `assigned` for 4 hours and a ticket stuck in `in_progress` for 24 hours have different meanings. The former means work hasn't started at all; the latter means work started but stalled. The appropriate response differs accordingly.

All thresholds are externalized into a YAML config file so they can be tuned without touching code:

```yaml
# config/assignment_policy.yml
stall_thresholds:
  ai_agent_working_minutes: 10
  human_assigned_reminder_hours: 1
  human_assigned_reassign_hours: 4
  in_progress_sla_hours: 24
  escalated_admin_notify_minutes: 30
```

When operations teams need to adjust thresholds during production, they edit the YAML — no deployment required.

---

## 3. Retry with Exponential Backoff

**Problem**: When auto-assignment fails, it's over. No retry. Even if an agent becomes available 30 minutes later, the ticket remains unassigned.

**Symphony's approach**: On agent execution failure, Symphony does not retry immediately. It waits progressively longer intervals before each retry. This is effective during external service outages or temporary overload.

**Solution**: Progressive retry for escalated tickets.

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

The delay sequence: 10s → 20s → 40s → 80s → 160s. Capped at 5 minutes.

If any agent finishes a task and becomes available during this window, the next retry will assign them automatically. This is especially effective during periods when all agents are temporarily busy — lunch breaks, meetings, incident response.

`polynomially_longer` is a built-in ActiveJob/SolidQueue backoff strategy. No custom implementation needed; a single `retry_on` declaration does the work.

---

## 4. The WORKFLOW.md Pattern (Policy Files In-Repo)

Symphony places a `WORKFLOW.md` file at the repository root to instruct AI agents on how to work. It uses YAML front matter for configuration values and Markdown body for prompts. Policy and instructions live in one file, versioned with the code.

I applied the same pattern to the ITSM assignment policy:

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

A service to parse the file:

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

The advantage of this approach is **version control**. AI prompt changes appear as Git commits. Policy changes go through PR review. Neither prompts nor assignment rules require a code deployment to modify.

---

## 5. Concurrency Control

Symphony enforces `max_concurrent_agents` and per-state limits. Running too many agents simultaneously causes interference or API rate limit exhaustion.

ITSM has the same problem. Without per-agent ticket limits, tickets pile onto specific agents, or critical tickets accumulate until none of them get handled properly.

```yaml
# config/assignment_policy.yml
concurrency:
  max_concurrent_ai_analysis: 5
  max_tickets_per_agent: 5
  max_critical_per_agent: 2
  max_concurrent_by_category:
    incident: 10
    change: 3        # Change requests: low concurrency limit
    problem: 5
    service_request: 15
```

The `AssignmentPolicy` service reads this config and validates it at assignment time:

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

The 2-critical-per-agent limit is particularly important. If an agent accumulates 3–4 critical tickets, none of them get proper attention. This is essentially the WIP (Work In Progress) limit principle from Kanban.

The `change` category is capped at 3 concurrent tickets because change requests involve complex review and approval processes. Handling too many simultaneously increases the chance of mistakes. Slower but more careful is the right tradeoff here.

---

## 6. Internal Orchestration States

**Problem**: The AASM states (`opened -> assigned -> in_progress -> resolved`) are what you show to users. But automation logic needs finer-grained state tracking. Mixing user-facing state with internal system state in the same column makes both sides complicated.

**Symphony's approach**: Symphony manages its own internal processing state separately from GitHub's issue state (open/closed). Even when a GitHub issue is open, Symphony internally tracks states like `processing`, `waiting_for_review`, or `completed`.

**Solution**: Add a dedicated `orchestration_state` column.

```
User-facing states (AASM):
  opened -> assigned -> in_progress -> resolved -> closed

Internal automation states (orchestration_state):
  unprocessed -> ai_analyzing -> awaiting_assignment
              -> agent_working -> stalled -> reassigning
```

Migration:

```ruby
add_column :tickets, :orchestration_state, :string, default: "unprocessed"
add_column :tickets, :orchestration_changed_at, :datetime
add_column :tickets, :assignment_attempts, :integer, default: 0
add_index :tickets, :orchestration_state
add_index :tickets, :orchestration_changed_at
```

Indexing `orchestration_changed_at` is critical. The Reconciliation Job queries this column every 5 minutes. Without an index, every reconciliation run becomes a full table scan.

Updating orchestration state at each processing step:

```ruby
# When AI analysis begins
ticket.update_orchestration!("ai_analyzing")

# Analysis complete, waiting for assignment
ticket.update_orchestration!("awaiting_assignment")

# Agent assigned successfully
ticket.update_orchestration!("agent_working")

# Assignment failed
ticket.update_orchestration!("stalled")
```

The `update_orchestration!` helper:

```ruby
def update_orchestration!(state)
  update!(
    orchestration_state: state,
    orchestration_changed_at: Time.current
  )
end
```

The Reconciliation Job uses `orchestration_changed_at` to precisely identify stuck tickets.

---

## 7. Workspace Isolation

Symphony runs each agent in a separate directory per issue to prevent cross-contamination. Files or state left behind by agent A working on issue #123 cannot affect agent B's processing of issue #456.

I applied the same principle to AI analysis — generating a unique session ID per ticket:

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

Simple, but effective. When an AI API maintains conversational context, analysis context from one ticket cannot bleed into another. As a bonus, the `session_id` makes it easy to trace the full processing history of a specific ticket in the logs — just grep for the session ID.

---

## Full Architecture After Applying All 7 Patterns

```
Ticket Created
  |
  v
[TicketAnalysisJob] -- orchestration: ai_analyzing
  |                     session_id: ticket-123-a1b2 (workspace isolation)
  v
AI Analysis Complete -- orchestration: awaiting_assignment
  |
  v
[AutoAssignmentJob] -- AssignmentPolicy.can_accept_ticket? (concurrency control)
  |                    retry with backoff (up to 5 attempts, 10s to 5 min)
  |-- success --> orchestration: agent_working
  |-- failure --> orchestration: stalled, escalate
  v
[TicketReconciliationJob] (every 5 min, reconciliation loop)
  |-- AI idle 10 min --> escalate
  |-- Human idle 4 hr --> reassign (re-run AutoAssignmentJob)
  |-- Escalated 30 min --> re-alert admin
  v
All thresholds configurable in config/assignment_policy.yml (externalized policy)
```

Each component has a single, clear responsibility. `TicketReconciliationJob` only detects. `AutoAssignmentJob` assigns. `AssignmentPolicy` decides eligibility.

---

## Lessons Learned

1. **Assignment is not a one-time event.** Reconcile periodically to detect abandonment automatically. An event-driven system cannot detect the absence of events — which is exactly what abandonment looks like. The Reconciliation Loop has the highest impact of all 7 patterns.

2. **Design for failure.** Auto-assignment can and will fail. With retry + backoff, the system self-heals the moment an agent becomes available. Treat failure as a normal case in the design, not an exception.

3. **Separate user state from system state.** AASM is for humans; `orchestration_state` is for automation. Mixing them makes both sides more complex and harder to index correctly.

4. **Keep policy out of code.** Managing thresholds and limits in a YAML config file means operations teams can tune behavior without a deployment. The same goes for AI prompts.

5. **Isolation is cheap but effective.** A single `session_id` prevents context contamination between AI analyses. It also makes log tracing dramatically easier.

The key was borrowing Symphony's **philosophy**, not its code. "Don't manage agents — manage the Work." That one sentence changed the entire design. No matter how many AI agents are running or what kind they are, the system stays stable.

---

## Key Takeaways

- **Reconciliation Loop**: Event-driven alone cannot detect abandonment. A periodic loop comparing actual vs. expected state is essential.
- **Stall Detection**: Different states need different thresholds. A ticket `assigned` for 1 hour and `in_progress` for 24 hours mean very different things.
- **Exponential Backoff**: Don't let transient failures become permanent failures. Progressive retry lets the system self-heal when capacity becomes available.
- **Policy as Code**: Version-controlling AI prompts and assignment rules means policy changes go through PR review instead of ad-hoc edits.
- **Concurrency Limits**: Without WIP limits, tickets pile onto individual agents or critical tickets accumulate unresolved. Set per-category concurrency ceilings.
- **Internal vs. External State**: User-facing state and automation-internal state should be separate columns. Mixing them complicates both sides and leads to incorrect index placement.
- **Workspace Isolation**: A session ID per AI analysis prevents context contamination and unlocks per-ticket log traceability as a free side effect.
