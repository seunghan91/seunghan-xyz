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
categories: ["AI Engineering", "Rails"]
---

While deploying a Rails 8-based ITSM system to Render today, I ran into three consecutive issues that each had different root causes but were connected like links in a chain. I'm documenting the process of reading deployment logs, debugging, patching code, and discovering the next problem.

The stack covered in this post: Rails 8.1, SolidQueue 1.3.1, Puma, PostgreSQL, deployed on Render.com.

---

## Issue 1 — `Application exited early` with SolidQueue

### Symptoms

The build succeeds in the Render deployment log, but the application dies immediately on startup.

```
==> Build successful 🎉
==> Deploying...
==> Running 'bundle exec puma -C config/puma.rb'
[87] Puma starting in cluster mode...
[87] * Preloading application
==> Application exited early
```

The `Build successful` message means the build phase is fine. The problem is in the run phase. The Puma process terminates before it even finishes starting.

### Finding the Root Cause

Looking more carefully at the Render logs reveals a stack trace:

```
from solid_queue-1.3.1/lib/solid_queue/configuration.rb in 'recurring_tasks'
from solid_queue-1.3.1/lib/solid_queue/supervisor.rb:15 in 'start'
from solid_queue-1.3.1/lib/puma/plugin/solid_queue.rb:81 in 'start_solid_queue'
...
[69] Detected Solid Queue has gone away, stopping Puma...
```

Inside `SolidQueue::RecurringTask.from_configuration`, `load_schema!` is called, and it blows up at `SchemaCache#columns`. In other words, **the `solid_queue_recurring_tasks` table does not exist in the database**.

When SolidQueue runs as a Puma plugin, it checks the DB schema during application boot. If the required tables are missing at that point, the SolidQueue supervisor exits immediately, the Puma plugin detects this and shuts down Puma itself. That is what produces `Application exited early`.

### Why Are the Tables Missing?

The Solid family of gems introduced in Rails 8 — SolidQueue, SolidCache, SolidCable — package their migration files inside the gem itself. You have to explicitly copy those migrations into your project's `db/migrate/` folder using a separate install command:

```bash
rails solid_queue:install:migrations
rails solid_cache:install:migrations
rails solid_cable:install:migrations
rails db:migrate
```

If you skip this step, no SolidQueue-related migration files exist in `db/migrate/`. No matter how many times `db:prepare` or `db:schema:load` runs, those tables will never be created. Rails' standard migration mechanism only processes files that are actually present inside `db/migrate/`.

SolidQueue requires a total of 10 tables:
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

### Fix — Manual CREATE in render-build.sh

We were already manually creating `solid_cache` and `solid_cable` tables inside `render-build.sh`. This pattern is common when you need to manage DB schema within a single service on Render, particularly on plans without a separate release command phase. We applied the same approach to add all 10 SolidQueue tables.

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
  # ... remaining 8 tables
].each { |sql| ActiveRecord::Base.connection.execute(sql) rescue nil }
"
```

The `CREATE TABLE IF NOT EXISTS` pattern makes this safe: if the table already exists, the statement is silently ignored. This script runs on every redeploy but causes no harm when tables are already in place.

There is a trade-off worth noting with this approach. Because you are stepping outside Rails' standard migration version tracking, if SolidQueue releases an upgrade that changes the schema, you must manually update `render-build.sh` to match. The proper long-term solution is to run `rails solid_queue:install:migrations` and commit those migration files to the repository.

Also verify the SolidQueue plugin configuration in `puma.rb`:

```ruby
# config/puma.rb
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]
```

When the `SOLID_QUEUE_IN_PUMA` environment variable is set, Puma starts SolidQueue together during boot. Running this without the tables in place produces exactly the crash described above. Because `SOLID_QUEUE_IN_PUMA=1` was set in Render's environment variables, the tables had to exist before Puma could start.

---

## Issue 2 — OpenClaw (AI Agent) Becomes Ticket Assignee

### Symptoms

When a ticket is created, it is automatically assigned to the AI agent account, and escalation occurs from that state.

```
Assignee: OpenClaw
Activity: Work started → Escalation
```

A ticket that should go to a human agent is being held by the AI agent. The AI agent accepts tickets up to its WIP limit, but since it cannot actually resolve them, it eventually triggers escalation. The manager notification fires, but the ticket ends up in limbo.

### Root Cause

The agent lookup query inside `SmartAssignmentService` was the problem.

```ruby
# Problematic code
def find_best_skilled_agent
  available_agents = User.where(role: [:agent, :ai_agent], status: :available)
                         .select { |u| u.wip_count < u.max_wip }
  # ...
end
```

`role: [:agent, :ai_agent]` — human agents (`agent`) and AI agents (`ai_agent`) are placed in the same pool. If no human agent is available or all are offline, an AI agent is automatically selected.

The intended architecture was:
- AI agents handle only tickets coming from bot channels
- Regular tickets are assigned exclusively to human agents

But the code did not behave that way. `SmartAssignmentService` always ran the same query regardless of the ticket's source channel (bot vs. regular). As a result, during hours when all human agents were offline — overnight, during lunch — every incoming ticket went to OpenClaw.

This bug was initially invisible because the development environment always had human agents seeded in an `available` state. The condition that causes AI agent selection was never exercised in tests.

### Fix

Exclude `ai_agent` from the standard assignment pool.

```ruby
def find_best_skilled_agent
  # role: :agent only — AI agents excluded
  available_agents = User.where(role: :agent, status: :available)
                         .select { |u| u.wip_count < u.max_wip }

  scored_available = score_candidates(available_agents)
  best_available = select_best_agent(scored_available)
  return best_available[:agent] if best_available

  busy_agents = User.where(role: :agent, status: :busy)
  scored_busy = score_candidates(busy_agents, include_busy: true)
  best_busy = select_best_agent(scored_busy)
  return best_busy[:agent] if best_busy

  nil  # If none found, escalate_to_manager is called upstream
end
```

`find_alternative_available_agent` was updated for the same reason. This method finds a replacement agent when the primary assignee suddenly goes offline. If `ai_agent` is included here too, the same problem would repeat.

The `score_candidates` method internally computes a score based on skill matching, current WIP ratio, and average response time. No matter how sophisticated the scoring logic is, it is meaningless if the agent pool itself is incorrectly assembled.

#### Assignment Flow Summary

| Situation | Behavior |
|-----------|----------|
| Human agent available | Assign immediately |
| All human agents busy | Add to queue (Case B/C/D) |
| No human agents at all | escalate_to_manager → admin notification |
| Bot-sourced ticket | Round-robin to AI agent (separate logic) |

AI agent assignment for bot-sourced tickets is handled by a separate `BotTicketAssignmentService`. The two services do not share the same agent pool, which makes the architectural boundary explicit.

---

## Issue 3 — Need for a Manual Assignment Feature

### Problem

When no human agents are available or all are offline, tickets just escalate and sit unattended. There is no way for an admin to assign tickets directly.

`escalate_to_manager` only sends a notification to the manager. Receiving a notification without being able to take action inside the system means the manager has to issue manual instructions through Slack or email. That defeats the purpose of an ITSM tool.

Automation systems need a fallback escape hatch for when they fail.

### Design

**Sidebar button (admin only)**
```
AI Ticket Intake
Manual Assignment  [3]  ← badge showing waiting ticket count
```

**`/admin/manual_assignments` page**

- List of unresolved tickets assigned to AI agents + tickets in `escalated` state
- Each row has an agent dropdown and an assign button

When the badge number is non-zero, the admin immediately knows manual intervention is needed. Simply showing "3 pending" gives the admin enough context to open the page and act.

### Implementation

The controller handles two responsibilities: `index` renders the list of stuck tickets, and `assign` processes the actual assignment.

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
                  notice: "Ticket ##{@ticket.id} has been assigned to #{@agent.name}."
    end
  end
end
```

The reason `assign` uses a transaction is important. `@ticket.update!`, `@ticket.assign!` (AASM state transition), and `TicketAssignment.create!` must all succeed together or all fail together. If only one of them fails midway, you can end up in an inconsistent state — the assignee changed but the state did not, or the state changed but no assignment record was created. These partial-success bugs are among the hardest to debug.

Calling `may_assign?` before `assign!` is a safety guard. If the ticket is already `in_progress`, calling `assign!` would raise an AASM InvalidTransition error. Always checking whether a state transition is permitted before executing it makes the code more resilient.

Routes:

```ruby
namespace :admin do
  resources :manual_assignments, only: [:index] do
    member do
      patch :assign
    end
  end
end
```

Using `only: [:index]` and separating `assign` as a member action is intentional. Assignment is an action targeting a specific ticket ID, so `/admin/manual_assignments/:id/assign` is a clearer and more RESTful path than a generic collection endpoint.

The badge counter in the sidebar queries the database on every request. Caching could be introduced, but admin page traffic is low enough that a direct query is perfectly acceptable for now.

```erb
<% stuck_count = Ticket.where("...").count rescue 0 %>
<% if stuck_count > 0 %>
  <span class="..."><%= stuck_count %></span>
<% end %>
```

The `rescue 0` is intentional. This code runs in the layout on every request. If the DB connection flickers or the query fails, you do not want a minor counter query to take down the entire page with a 500 error. A secondary UI element should never be able to bring down the main interface.

---

## Lessons Learned

1. **Rails 8 Solid* gems require explicit migration file installation.** `db:prepare` will not do it automatically. `rails solid_queue:install:migrations` must be included explicitly in initial project setup. If you work around this with manual CREATE statements in `render-build.sh` as shown here, you are responsible for manually tracking schema changes whenever the gem is upgraded.

2. **Role filtering in auto-assignment logic must be explicit and deliberate.** Using only `:agent` instead of `[:agent, :ai_agent]` matched the architectural intent. This category of bug is difficult to spot when development seed data does not cover production-level scenarios. Add explicit test cases for "all human agents are offline" situations.

3. **Manual fallback is mandatory when automation fails.** An `escalate_to_manager` notification alone is not enough. Admins need a UI where they can intervene directly within the system. Every automated workflow should include a human escape hatch from the design phase onwards.

---

## Key Takeaways

- **Solid gem migrations**: Run `rails solid_queue:install:migrations` first. Skipping this step causes a crash at Puma startup due to missing tables. The stack trace is buried in the middle of the Render log, not at the very top — scroll carefully.
- **Puma + SolidQueue integration failure pattern**: When `SOLID_QUEUE_IN_PUMA=1`, a SolidQueue initialization failure takes down the entire Puma process. The build phase succeeds but the run phase crashes immediately. Always verify tables exist before enabling this env var.
- **Separating AI and human agents**: Putting both agent types in the same query pool causes AI agents to pick up human work when humans are unavailable. Role filters must be written defensively and explicitly — never rely on implicit exclusion.
- **Manual assignment UI is not optional**: No matter how sophisticated the auto-assignment logic, edge cases will occur. Without an in-system way to assign tickets manually, incident response cost goes up significantly.
- **Transaction integrity for assignment operations**: Updates spanning multiple tables (ticket record, AASM state, assignment log) must be wrapped in a transaction. Partial success creates inconsistent state that is notoriously hard to diagnose.
- **`rescue 0` pattern for layout counters**: Any query embedded in a layout that runs on every request should have exception handling. A transient DB error on a sidebar counter should never produce a 500 for the entire page.
