---
title: "Rails OOM on Render 512MB Starter — render.yaml Was the Culprit"
date: 2026-01-13
draft: true
tags: ["Rails", "Render", "Solid Queue", "Puma", "Deployment", "Memory"]
description: "Why OOM wasn't fixed no matter how much puma.rb was tuned — render.yaml environment variables were overriding code defaults."
cover:
  image: "/images/og/render-512mb-oom-rails-solid-queue.png"
  alt: "Render 512Mb Oom Rails Solid Queue"
  hidden: true
categories: ["Rails"]
---

After deploying a Rails 8 app to Render's Starter plan (512MB), the service kept going down with periodic out-of-memory crashes. I reduced thread counts in puma.rb, tuned queue.yml, and redeployed multiple times — nothing helped. It took a couple of frustrating hours before I found the real cause.

---

## Symptoms

OOM (Out of Memory) events were repeating in the Render dashboard. Memory usage would exceed 512MB, the process would get force-killed, Render would automatically restart it, and then a few minutes later the exact same pattern would play out again. Even with no traffic, memory would climb steadily over time until the process crashed.

Looking at Render's metrics view, you could see the classic OOM graph: memory rising gradually, then dropping vertically right before 512MB — the process dying and restarting.

---

## First Attempt — Editing puma.rb

The first thing I suspected was the Puma configuration. More threads means more memory per worker, so reducing thread counts is the standard first move.

```ruby
# config/puma.rb
threads_count = ENV.fetch("RAILS_MAX_THREADS", 2)  # reduced from 3 to 2
threads threads_count, threads_count
workers ENV.fetch("WEB_CONCURRENCY", 1)
```

Deployed. OOM still happening. The code had clearly changed, but nothing was different in production — which made it even more confusing.

Next I looked at the Solid Queue configuration, reduced thread counts there too, and increased the polling interval. Still no effect.

---

## The Real Cause — render.yaml Overrides Code Defaults

After two hours of fruitless debugging, I finally opened render.yaml — a file I had set up early in the project and completely forgotten about.

```yaml
envVars:
  - key: WEB_CONCURRENCY
    value: "2"
  - key: RAILS_MAX_THREADS
    value: "5"
```

That was the problem.

**Environment variable priority: render.yaml (externally injected) > code defaults**

`ENV.fetch("RAILS_MAX_THREADS", 2)` only falls back to `2` when the environment variable is absent. When render.yaml injects `RAILS_MAX_THREADS=5`, the code default is completely ignored. No matter how many times I edited puma.rb, those changes were irrelevant as long as render.yaml was setting the values.

This isn't a quirk of Rails or Puma — it's the 12-Factor App configuration principle. Processes read configuration from the environment, not from code. Render injects environment variables into the container this way, so values declared in render.yaml always take precedence over code-level defaults.

### Actual Memory Breakdown

With `WEB_CONCURRENCY=2` and `RAILS_MAX_THREADS=5`, here's what was running:

| Component | Estimated Memory |
|-----------|-----------------|
| Puma master | ~50MB |
| Puma worker × 2 | ~300MB |
| Solid Queue dispatcher | ~50MB |
| Solid Queue worker | ~100MB |
| **Total** | **~500MB+** |

At idle, the app was already sitting at 500MB. Any single memory spike — an ActiveRecord query loading a large dataset, rendering a complex email, processing a file upload — would push it over 512MB and kill the process. That explains why it was crashing periodically even under light traffic.

---

## Fix — Updating render.yaml

```yaml
envVars:
  - key: WEB_CONCURRENCY
    value: "1"
  - key: RAILS_MAX_THREADS
    value: "2"
  - key: MALLOC_ARENA_MAX
    value: "2"
```

`MALLOC_ARENA_MAX=2` is an environment variable that reduces glibc memory fragmentation without any code changes. By default, glibc creates multiple memory arenas proportional to the number of CPU cores — in a container environment, this can cause memory that is effectively used by a single process to become scattered across arenas and never returned to the OS. Setting `MALLOC_ARENA_MAX=2` limits this behavior, visibly reducing real memory usage in constrained environments like Render's Starter plan.

### Memory After Optimization

| Component | Estimated Memory |
|-----------|-----------------|
| Puma master | ~50MB |
| Puma worker × 1 | ~150MB |
| Solid Queue dispatcher | ~40MB |
| Solid Queue worker (threads=1) | ~60MB |
| **Total** | **~300MB** |

That leaves roughly 200MB of headroom within the 512MB limit — enough to absorb most memory spikes without crashing.

---

## Debugging Tips — How to Confirm Actual Memory Usage

Before touching render.yaml, it helps to understand what memory is actually being used.

**Render dashboard**: Go to your service → Metrics tab. The memory graph shows you when OOM events occur and whether usage grows over time (memory leak) or spikes suddenly.

**Rails console — check current process memory**:
```ruby
puts `ps -o rss= -p #{Process.pid}`.to_i / 1024
# => outputs memory in MB
```

**Render SSH (paid plans)**:
```bash
# See all Ruby processes and their memory
ps aux | grep ruby
```

**Verify which environment variable values are actually active** — do this after every deploy:
```ruby
# In Rails console
puts ENV["RAILS_MAX_THREADS"]
puts ENV["WEB_CONCURRENCY"]
puts ENV["MALLOC_ARENA_MAX"]
```

If you edited render.yaml, redeploy and confirm the values are correct before assuming the fix worked.

---

## Bonus — Solid Queue Crash Loop

On the same day, a different Rails app started returning `Bad Gateway`. The logs showed:

```
Solid Queue has gone away
Puma stopping...
```

When Solid Queue died, the Puma plugin detected it and shut Puma down as well.

The root cause was a structural error in `config/queue.yml`.

```yaml
# Wrong structure — dispatchers nested inside workers
production:
  workers:
    - queues: [default]
      dispatchers:
        polling_interval: 1

# Correct structure
production:
  dispatchers:
    - polling_interval: 1
      batch_size: 500
  workers:
    - queues: [default]
      threads: 1
```

`SolidQueue::Configuration#ensure_configured_processes` fails validation with this wrong nesting, causing Solid Queue to exit with code 1. The Puma plugin detects this and shuts Puma down too. Result: Bad Gateway.

### Decoupling the Puma Plugin Dependency

If Solid Queue configuration errors or brief queue outages shouldn't take down the web server, you can decouple them by disabling the Puma plugin and running Solid Queue as a separate process.

```ruby
# config/puma.rb
# plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]  # comment this out
```

Then add a separate worker service in render.yaml:

```yaml
services:
  - type: web
    name: myapp-web
    env: ruby
    buildCommand: bundle exec rails assets:precompile
    startCommand: bundle exec puma -C config/puma.rb

  - type: worker
    name: myapp-worker
    env: ruby
    startCommand: bundle exec rails solid_queue:start
    envVars:
      - key: RAILS_MAX_THREADS
        value: "1"
```

With this setup, if Solid Queue crashes, the web server stays up. The tradeoff is that a separate worker service costs extra on Render.

On the 512MB Starter plan, running a second service may not be feasible. In that case, keep the plugin approach but validate your queue.yml structure carefully before deploying.

---

## Summary

1. **render.yaml environment variables override code defaults.** Editing puma.rb defaults has no effect if render.yaml sets the same keys. Always verify which values are active in the deployed environment after a change.
2. **WEB_CONCURRENCY=2 is dangerous on 512MB.** One worker plus two threads is a realistic upper bound. Keeping the idle memory footprint under 300MB leaves enough headroom for traffic spikes.
3. **MALLOC_ARENA_MAX=2 is the easiest memory optimization with no code changes.** It reduces glibc memory fragmentation in Ruby/Puma environments with essentially no downside.
4. **queue.yml indentation and structure are validated at runtime.** Review it carefully before deploying. `dispatchers` must be at the same level as `workers`, not nested inside it.
5. **The Solid Queue + Puma plugin combination is convenient but has a single point of failure.** If Solid Queue crashes, Puma goes down with it. For higher reliability, run them as separate services.

---

## Key Takeaways

- When debugging Render deployments, check environment variables before touching code. A mismatch between your local `rails s` behavior and production almost always points to environment variable differences.
- For Rails + Solid Queue on the 512MB Starter plan, the proven starting point is: `WEB_CONCURRENCY=1`, `RAILS_MAX_THREADS=2`, `MALLOC_ARENA_MAX=2`.
- When editing environment variables on Render, check both the dashboard's Environment tab and render.yaml. If both are set, render.yaml takes precedence. After any change, confirm the deployed values with `ENV["KEY"]` in the Rails console.
- Memory fragmentation in Ruby processes running inside Linux containers is a known issue. `MALLOC_ARENA_MAX=2` is a widely used, low-risk mitigation that is worth adding to any memory-constrained deployment.
