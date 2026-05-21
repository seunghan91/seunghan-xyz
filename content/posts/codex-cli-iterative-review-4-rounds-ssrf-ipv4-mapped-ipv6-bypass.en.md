---
title: "Codex CLI Iterative Code Review — Why Every Round Found a New P1"
date: 2026-05-22T09:00:00+09:00
draft: false
tags: ["codex-cli", "code-review", "ssrf", "claude-code", "skill"]
description: "I ran Codex CLI review on a single PR four times. Each round surfaced a fresh P1. My first SSRF guard fell to IPv4-mapped IPv6, the second fix fell to a robots.txt side-channel. Here is why one-shot review is not enough, plus the six traps I baked into an automation skill."
---

A large PR landed. 8 commits, 73 files, +4484 / −239 lines. An external LLM had produced it as a branch-style gap analysis, so much of it touched code I had not written. Merging blind felt reckless, so I sent it through Codex CLI for review first.

Round 1 returned two `[P1]` findings. I fixed them, pushed, and assumed it was done. Then I ran round 2 — two more `[P1]`s appeared. Then round 3. Then round 4. New P1s every single round.

At first I assumed it was coincidence. After looking around, it turns out this is the expected pattern. So the journey to merge ended up being four rounds and eleven fix commits. But if I had stopped at round one, two SSRF bypasses would have shipped to production.

This post walks through those four rounds commit by commit, and the six traps I codified into a reusable skill afterward.

---

## What Codex CLI review actually does

Codex CLI is OpenAI's command-line code reviewer (`npm install -g @openai/codex`). The core invocation:

```bash
codex review --base main -c 'model_reasoning_effort="high"' --enable web_search_cached
```

It diffs the working branch against `--base`, reads the changes, and emits findings tagged `[P1]` (block merge), `[P2]` (follow-up), `[P3]` (suggestion). There is a running joke that Codex behaves like "a 200 IQ autistic developer doing review" — terse, technically dead-on, brutally specific about file and line.

I run it as a background job inside Claude Code:

```bash
codex review --base main -c 'model_reasoning_effort="high"' \
  --enable web_search_cached 2>/tmp/codex-err.txt > /tmp/codex-out.txt &
```

It takes about five minutes. Claude works on something else in parallel. When the job notifies, I parse the findings, fix the P1s, push.

---

## Round 1 — the obvious stuff

Two P1s and one P2 in the first pass:

| Severity | Location | Issue |
|---|---|---|
| P1 | `user_url_imports_controller.rb:64` | Any logged-in user submits an arbitrary URL, server fetches it — SSRF |
| P1 | `config/environments/production.rb:86-88` | Production defaults ActiveStorage to the r2 (S3-compatible) service, but `aws-sdk-s3` is not in the Gemfile — LoadError on first upload |
| P2 | `Show.svelte:40-43` | Svelte 5 `$derived.by` reads `Date.now()` but not the `_cooldownTick` state — reactivity never fires |

Both P1s are merge-blockers. SSRF is a textbook security hole. The missing gem would crash on the first production PDF upload.

### SSRF fix (round 1 attempt)

I added `app/lib/safe_url.rb`:

```ruby
require "ipaddr"
require "resolv"

module SafeUrl
  PRIVATE_RANGES = [
    IPAddr.new("0.0.0.0/8"),
    IPAddr.new("10.0.0.0/8"),
    IPAddr.new("100.64.0.0/10"),     # carrier-grade NAT
    IPAddr.new("127.0.0.0/8"),       # loopback
    IPAddr.new("169.254.0.0/16"),    # link-local incl. cloud metadata IP
    IPAddr.new("172.16.0.0/12"),     # RFC1918
    IPAddr.new("192.168.0.0/16"),
    IPAddr.new("::1/128"),
    IPAddr.new("fc00::/7"),          # IPv6 unique local
    IPAddr.new("fe80::/10")          # IPv6 link-local
  ].freeze

  def public!(url)
    uri = URI.parse(url.to_s)
    raise BlockedError, "scheme not allowed" unless %w[http https].include?(uri.scheme)
    addrs = Resolv.getaddresses(uri.host)
    addrs.each do |a|
      ip = IPAddr.new(a)
      blocked = PRIVATE_RANGES.any? { |range| range.include?(ip) }
      raise BlockedError, "private address not allowed: #{a}" if blocked
    end
    uri
  end
end
```

`Crawl.get` now calls `SafeUrl.public!(current)` on every redirect hop. Looked clean. Eight test cases covered (loopback, RFC1918, metadata IP, IPv6 loopback, etc.) and all passed.

I pushed and triggered round 2.

---

## Round 2 — the IPv4-mapped IPv6 bypass

```
[P1] Block IPv4-mapped private IPv6 URLs — app/lib/safe_url.rb:26-28
For user-submitted URL imports, an IPv4-mapped IPv6 literal such as
http://[::ffff:127.0.0.1]/ or http://[::ffff:169.254.169.254]/ passes
this range list: IPAddr treats it as IPv6, so it is not included in
the IPv4 loopback/link-local ranges and no mapped-address handling
is present.
```

I thought this could not actually work. It did. `IPAddr.new("::ffff:127.0.0.1")` becomes an IPv6 object, and my `PRIVATE_RANGES`'s `127.0.0.0/8` (IPv4) does not consider an IPv6 object to fall inside it. Filter bypassed.

A quick search turned up this is a well-known CVE category:

- **CVE-2026-42449** (n8n-mcp, 2026-04-30): "Synchronous URL validator in SDK embedder path lacks IPv6 validation. `http://[::ffff:169.254.169.254]` bypasses cloud-metadata, localhost, and private-IP range checks."
- **CVE-2026-26324** (OpenClaw, 2026-02-20): "SSRF protection bypassed using full-form IPv4-mapped IPv6 literals such as `0:0:0:0:0:ffff:7f00:1` (= 127.0.0.1)."

My SafeUrl had the exact same defect. Lucky that Codex caught it before production.

### Round 2 fix

```ruby
addrs.each do |a|
  ip = IPAddr.new(a)
  # An IPv4-mapped IPv6 literal like ::ffff:127.0.0.1 lands outside the
  # IPv4 ranges as-is. Unwrap it to its embedded IPv4 form so the
  # private-range check actually catches loopback / metadata IPs.
  ip = ip.native if ip.ipv6? && ip.ipv4_mapped?
  blocked = PRIVATE_RANGES.any? { |range| range.include?(ip) }
  raise BlockedError, "private address not allowed: #{a}" if blocked
end
```

`IPAddr#ipv4_mapped?` plus `IPAddr#native` unwraps the mapped IPv6 into its embedded IPv4 representation, and the range check works again.

There was a secondary trap: `uri.host` keeps the brackets (`[]`) around IPv6 literals, which makes `IPAddr.new` reject the input. Switching to `uri.hostname` strips them. You cannot see either of these defects from reading the code in isolation — Codex pointed me right at line 26-28.

I added two more tests (mapped loopback + mapped metadata IP) and pushed. Round 3.

---

## Round 3 — robots.txt sneaks around the SSRF guard

Round 3 result:

```
[P1] Guard URLs before the robots.txt fetch
For a user-submitted URL such as http://169.254.169.254/..., this
call reaches Robotex.allowed? before the new SafeUrl guard in
Crawl.get runs, and Robotex fetches /robots.txt itself via
open-uri. That still allows SSRF against link-local/private services
(and robots redirects are also unguarded), so the robots check needs
to use the same public-address validation/guarded fetch path before
making any outbound request.
```

My SafeUrl guard lived inside `Crawl.get`. But the first outbound request from the controller was not `Crawl.get` — it was `Crawl::RobotsChecker.allowed?`, which calls `Robotex` internally, which fetches `/robots.txt` through `open-uri`. **A path that never goes through `Crawl.get`**.

No amount of staring at the controller would catch this. You have to follow Robotex's internals to see the sneak path. In round 1 I had only validated the controller → `ContentExtractor.extract` → `Crawl.get` → `SafeUrl` flow and called it done.

### Round 3 fix

Defense in depth — call SafeUrl again at the controller's trust boundary:

```ruby
# SSRF gate at the trust boundary. SafeUrl is also called inside
# Crawl.get, but Robotex fetches /robots.txt via open-uri which
# bypasses Crawl.get entirely — so a user-submitted URL pointing
# at 169.254.169.254 would still reach the metadata service during
# the robots check below if we didn't gate here first.
begin
  SafeUrl.public!(canonical)
rescue SafeUrl::BlockedError => e
  return redirect_to new_user_url_import_path,
                     alert: "Only public hosts allowed: #{e.message}"
end

# robots.txt check
unless Crawl::RobotsChecker.allowed?(url: canonical)
  return redirect_to new_user_url_import_path,
                     alert: "robots.txt disallows this path."
end

extracted = Crawl::ContentExtractor.extract(url: canonical)
```

`Crawl.get`'s SafeUrl call stays where it is (re-validates each redirect hop). The controller's SafeUrl is first-line defense at the trust boundary.

The same round also caught a P2 worth mentioning: when a user uploads a PDF without an AI key, the processing job stores `process_error: "no_api_key"` *and* sets `processed_at`. Because the job's first line is `return if pdf.processed_at.present?`, the next run skips the PDF entirely. The user can never make it process, even after adding a key. Dropping the `processed_at` assignment in that branch fixes it.

---

## Round 4 — policy violation + lifecycle gaps

```
[P1] Cap stored PDF paragraph excerpts at 500 chars
For text-extractable PDFs with long paragraphs, this stores up to
1000 characters per paragraph in user_pdfs.paragraphs, exceeding
the repository/legal storage cap for paragraph excerpts (≤500 chars
each).
```

This one is not a security hole, it is a policy violation. `legal/POLICY.md` and `Article::MAX_PARAGRAPH_LEN = 500` both stipulate 500 as the cap on stored paragraph excerpts, but the PDF text extractor was hardcoded to 1000. Rounds 1-3 had been so focused on SSRF that nobody checked policy files. Round 4 widened Codex's gaze.

Two more P2s came with it:

- Re-uploading the same PDF after adding an AI key triggers the idempotency branch, which only redirects — it never re-enqueues the job. PDFs stuck in the no_api_key state stay stuck forever.
- `pdf.destroy!`'s association cascade does not reach polymorphic rows (RecallDraft, TranslationSession). The user's personal text remains in the database after deletion.

The second one is a latent personal-information-leak issue. Polymorphic + no FK is a known Rails ActiveRecord trap. It does not show up in casual code review.

---

## Why every round finds new P1s

I started suspecting Codex was deliberately rationing findings. It isn't. **Each round looks at a different surface.**

- Round 1: the most obvious line-level defects in the diff (direct SSRF, missing gem)
- Round 2: defects in *my own fix* (mapped IPv6 bypass — an edge case in newly-added code)
- Round 3: side paths around my fix (Robotex sidesteps SafeUrl) — Codex's view broadens to the whole controller
- Round 4: business / policy / lifecycle layer (paragraph cap, polymorphic cleanup) — Codex's view broadens further to the codebase

The [zylos.ai Multi-Model AI Code Review research](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence) describes the same dynamic.

> The actor-critic literature consistently reports **3-5 rounds** as the practical convergence window. From our own experience running Claude Code (fixer) + OpenAI Codex (reviewer) in an 8-round convergence loop on an SDK codebase: findings decreased monotonically from 7 in round 3 to 4 in round 4, 2 in rounds 5-6, 1 in round 7, and 0 (CLEAN) in round 8.

3 to 8 rounds is the normal range. Cursor's BugBot reportedly does 8 parallel review passes with randomized file ordering, on the theory that any single ordering misses findings that a different ordering would surface. Same idea, different shape: **what you see on the first read and what you see on the second read are genuinely different.**

[aseemshrey.in's writeup](https://aseemshrey.in/blog/claude-codex-iterative-plan-review/) frames it well:

> A one-shot review finds problems but doesn't verify fixes. The iterative loop means:
> 1. Codex finds issues
> 2. Claude fixes them
> 3. Codex verifies the fixes actually work
> 4. Repeat until clean
>
> This catches the "fixed one thing but broke another" class of problems.

In my run, round 2 caught a flaw in round 1's fix. Round 3 caught a bypass of round 2's fix. The "fixed one thing but broke another" class — exactly.

---

## Six traps I baked into the skill

Because I was going to repeat this workflow on every PR, I codified it as a Claude Code skill called `pr-merge-review`. The skill turned up six traps along the way.

### Trap #1 — unpushed commits on local main

Before sending another PR through Codex, run `git log --oneline origin/main..main`. If that output is non-empty, your PR base comparison is misleading. I lost an hour to this on a previous PR.

### Trap #2 — two PRs touching the same area with different intent

If two PRs modify the same files for different purposes, merging is a tiebreak decision, not an automatic union. Never auto-pick a side.

### Trap #3 — silent half-merge

When a cherry-pick conflicts, never apply `git checkout --theirs/--ours` wholesale. Read both sides' intent at every conflict and decide. Otherwise one side's intent silently disappears.

### Trap #4 — losing findings when closing obsolete PRs

After the merge, closing the older PRs with a bare `gh pr close` destroys the Codex findings recorded against them. Always leave a summary comment first.

### Trap #5 — dirty working tree before checkout (newly discovered)

Run `git status` before any cherry-pick or branch checkout. If there are uncommitted changes, stash first. After the merge, `git stash pop` may conflict — those are the user's in-progress edits, never auto-resolve.

### Trap #6 — the branch moves while Codex review is running (newly discovered)

A long Codex review (4-5 minutes) gives plenty of room for new commits to land on the PR branch — from a collaborator, from CI, from yourself in another session. Before pushing your fixes, always `git fetch origin <branch>` and check `git log HEAD..origin/<branch>`. If anything new arrived, rebase and re-run Codex (the new commits may have introduced their own P1s).

Traps #5 and #6 are first-run discoveries from this PR. I added them to the skill's incident log so the next invocation checks for them in step 0.

---

## Antipatterns (do not do these)

The "never" list, written down so I do not repeat them:

- ❌ Merging despite an open P1 finding ("I'll fix it later")
- ❌ Resolving conflicts in bulk with `git checkout --theirs/--ours`
- ❌ Skipping the build / test pass before cherry-picking
- ❌ Closing an obsolete PR without preserving the Codex findings
- ❌ Ignoring unpushed commits on local main
- ❌ Trying to merge two competing implementations of the same area
- ❌ **Merging after one Codex round passes** (round 2+ frequently surfaces new P1s)
- ❌ Pushing fixes after a long Codex review without fetching first (silent branch drift)
- ❌ Doing cherry-picks against a dirty working tree
- ❌ Auto-resolving stash-pop conflicts (silently loses the user's in-progress work)

The most dangerous of these is "merge after one round passes." If you stop early to save time, defects like the mapped-IPv6 SSRF bypass ship to production. This PR caught all of them only because round 4 happened.

---

## When to stop running rounds

You cannot loop forever. My stop criteria are three:

1. **Round result is zero P1s and remaining P2s are lifecycle / policy class** — merge, file the P2s as follow-ups.
2. **Round N+1 only surfaces the same findings as round N** — convergence reached. Merge.
3. **The user says "merge now"** — user judgment wins even with open P1s.

The [Multi-Model AI Code Review paper](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence) lists five termination criteria:

1. All findings resolved
2. Evaluation score above threshold
3. Retry limit reached
4. Hard timeout
5. Escalation (human judgment needed)

My case landed at criterion 1. After four rounds I was confident no SSRF or policy violation would reach production.

---

## Toolchain setup

If you want to reproduce this workflow, the pieces:

```bash
# 1. Codex CLI
npm install -g @openai/codex

# 2. Claude Code (Anthropic — claude.ai/code)
# 3. gh CLI (GitHub)
brew install gh && gh auth login
```

Codex CLI needs one `codex login` against your OpenAI account. It is bundled with the ChatGPT subscription.

Drop a SKILL.md into your Claude Code skill directory and you can drive the whole flow in natural language:

```
You: "merge PR #N"
Claude: (invokes pr-merge-review skill)
        → preflight: check all six traps
        → codex review (background)
        → analyze findings
        → apply fixes
        → re-review
        → ... (until P1 count is zero)
        → merge
```

---

## Takeaway

When you send a large PR through Codex, **one passing round does not mean safe**. New P1s on every round is the expected pattern, and three to five rounds is the standard convergence window. This PR took four rounds and eleven fix commits.

The most chilling moment was round 2's mapped-IPv6 finding. My SafeUrl module had exactly the same defect as CVE-2026-42449 and CVE-2026-26324. If I had stopped after round 1, that defect would have shipped.

The workflow itself is now a skill. Next time, "merge this PR" triggers all six trap checks and four review rounds without me having to drive each step manually.

```bash
codex review --base main -c 'model_reasoning_effort="high"' --enable web_search_cached
```

That single command kept two SSRF bypasses out of production. Five to ten extra minutes is a cheap price.
