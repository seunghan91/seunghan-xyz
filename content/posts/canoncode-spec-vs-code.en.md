---
title: "2,800 Lines of Code → 160 Lines of Spec — Converting a Real Project with CanonCode"
date: 2026-03-18
draft: false
tags: ["CanonCode", "Specification", "Architecture", "Code-as-Law", "LaunchCrew"]
description: "I converted the core business logic of a real QA matching platform (LaunchCrew) into a .lex specification. 2,800 lines became 160. An experiment in maintaining laws instead of code."
cover:
  image: ""
  alt: "CanonCode Spec vs Code"
  hidden: true
---

The bigger your codebase gets, the harder it is to answer "why does this feature work like this?" You end up opening 5 files. The design doc was written 3 months ago and nobody knows if it still matches the code. Comments are stale, Slack threads are gone, and the original designer left the company.

**What if the design doc itself was executable, and you maintained that instead of the code?**

I experimented with this idea in a side project called [CanonCode](https://github.com/seunghan91/canoncode). This post documents what happened when I applied it to a real production-level codebase — including the unexpected debugging wins and the honest limitations I ran into.

---

## The Idea: Govern Software Like Law

Inspired by legal systems:

| Legal System | Software |
|-------------|----------|
| Constitution | Project principles (mobile-first, offline support) |
| Acts | Feature architecture (QA posting, payment flow) |
| Rules | Interaction logic (validation, state transitions) |
| Appendices | Data schemas, API specs |
| Case Law | Exception handling (insufficient balance, race conditions) |

Lower-level laws cannot contradict higher-level ones. CanonCode's linter detects violations automatically.

The reason this idea feels fresh is straightforward. The gap between design and implementation is a problem almost every team experiences, but most solutions amount to "write better docs." CanonCode doesn't try to sync documents to code — it attempts to place **the spec structurally above the code**, making the spec the source of truth that code must conform to.

---

## The Subject: LaunchCrew

[LaunchCrew](https://github.com/seunghan91/launchcrew) is a C2C QA matching platform I'm building:

- Developers (Makers) post QA testing needs
- Testers (Hunters) apply, get accepted, and submit daily proof of work
- On completion, escrowed points are automatically released to testers

Stack: Rails 8 + Inertia.js + Svelte 5 + Flutter

I chose this project because the business logic is genuinely complex. Escrow payments, a state machine for job posts, proof verification, point settlement, and exception handling across multiple domains all interact with each other. The core business logic spans **40+ files, 2,800+ lines** across models, controllers, services, and UI components.

If a new developer joined, where would they start reading? `qa_posts_controller.rb`? `wallet.rb`? `escrow_service.rb`? It's not even clear which file is the "truth."

---

## Results

### Overall Comparison

| Section | .lex Spec | Actual Code | Ratio |
|---------|-----------|-------------|-------|
| Constitution (Principles) | 30 lines | ~450 lines | 15x |
| Acts (Feature Logic) | 50 lines | ~1,230 lines | 24.6x |
| Rules (Validation) | 12 lines | ~145 lines | 12x |
| Appendices (Reference) | 40 lines | ~200 lines | 5x |
| Case Law (Exceptions) | 25 lines | ~150 lines | 6x |
| **Total** | **~160 lines** | **~2,800+ lines** | **17.5x** |

The 17.5x compression ratio is less interesting than what it implies: **160 lines carry the "intent" behind 2,800 lines**. Code captures how something is implemented. The spec captures why it has to work that way at all.

### Escrow Payment: Spec vs Code

The escrow payment logic is the clearest illustration of this distinction.

**.lex spec (2 clauses):**

```json
{
  "id": "CL-001-2",
  "content": "point type posts must escrow points_per_person × recruits_count immediately upon creation"
},
{
  "id": "CL-001-3",
  "content": "On escrow failure, roll back post creation entirely"
}
```

**Actual code (~200 lines across 4 files):**

```ruby
# qa_posts_controller.rb
def create
  ActiveRecord::Base.transaction do
    @post = current_user.qa_posts.build(qa_post_params)
    escrow_amount = @post.points_per_person * @post.recruits_count
    wallet = current_user.wallet.lock!
    raise InsufficientBalanceError if wallet.balance < escrow_amount
    wallet.update!(balance: wallet.balance - escrow_amount,
                   escrowed: wallet.escrowed + escrow_amount)
    WalletTransaction.create!(wallet: wallet, transaction_type: :escrow,
                              amount: escrow_amount, ...)
    @post.save!
    QaProject.create!(qa_post: @post, developer: current_user, ...)
  end
rescue InsufficientBalanceError
  render json: { error: "Insufficient balance" }, status: 422
end
```

**2 clauses govern 200 lines** scattered across controller, service, model, and migration. Reading the code, you see `wallet.lock!`, `ActiveRecord::Base.transaction`, and error rescue branches — but you find no explanation of *why escrow exists at all*. That answer lives only in the spec.

---

## What Worked

### 1. Onboarding Speed

Reading one .lex file gives you the entire business logic in 10 minutes. Reading the codebase takes days.

After reading the spec, questions like "where is the escrow settlement logic handled?" disappear. The spec has `CL-001-2`, which references `ACT-003`, whose section 5 defines the settlement flow. The hierarchy is explicit and navigable.

### 2. Exception Traceability

In code, exception handling hides inside `catch` blocks. Answering "why does this logic exist?" requires an archaeological expedition: git blame → Slack history → original requirements doc (if it still exists).

In .lex, every exception is a **case law entry** linked to the specific clause it relates to:

```
CASE-002: Tester drops out mid-testing
  Situation: Tester abandons work before completion
  Ruling: Return only that tester's escrowed amount to the developer
  Related clauses: ACT-003 CL-005-3
```

The key element here is the "Ruling." It records not just what happens, but **why that outcome was chosen**. It's a letter to your future self — and to anyone who maintains the codebase six months from now.

### 3. Architecture Violation Detection

If the constitution clause says "balance >= 0", the linter catches code changes that could violate it. You no longer need a human to catch "wait, can this go negative?" during code review.

The `lex_engine`, written in Rust, handles this role. It builds a dependency graph across clauses and runs static analysis to detect when a new clause conflicts with existing constitutional principles. It's not complete yet, but the direction is clear.

### 4. Synergy with AI Code Generation

This benefit was unexpected. Prompting an LLM with "implement the escrow payment flow" produces far less accurate results than "implement clauses CL-001-2 and CL-001-3 in Rails." When the context is structured as a spec, the AI has no ambiguity to fill in with guesses.

---

## Debugging in Practice: The Concurrent Payment Race Condition

Shortly after adopting CanonCode, I hit a real bug. When two testers applied to the same job post simultaneously, escrow was being deducted twice.

Without the spec, the debugging path would have been:
1. Check `wallet.rb`'s `deduct_escrow` method
2. Search for all call sites (`grep -r "deduct_escrow"`)
3. Trace transaction boundaries
4. Identify the locking strategy

Because the spec existed, I checked it first:

```
CASE-005: Concurrent application collision
  Situation: Multiple applications arrive simultaneously as recruits_count fills
  Ruling: First-come-first-served; later applications return 422
  Related clauses: ACT-003 CL-007-1
```

The case law referenced `CL-007-1`, which specified `optimistic locking`. Checking the code immediately revealed that `lock_version` was missing from the relevant model. The spec was the map; the code was the territory. I found the bug by reading the map first.

This experience is what turned CanonCode from a documentation experiment into something I actually want to keep building. The spec is not just a record of intent — it is a **debugging tool that operates at the design level**, before bugs become runtime failures.

---

## Honest Limitations

1. **It does not replace code**: .lex defines "what", not "how". You still write all the implementation yourself. "Just write the spec and get code for free" is still a distant goal.
2. **JSON is verbose**: Markdown or YAML would be more concise for human authoring. The current format was chosen for parsing convenience, but it is not pleasant to write by hand.
3. **No automatic code generation yet**: Unlike tools like CodeSpeak, .lex-to-code generation is still in planning. LLM integration experiments are ongoing, but not yet reliable enough to ship.
4. **Overkill for small projects**: For prototypes and hackathons, the overhead is not justified. The benefits scale with business logic complexity and team size.
5. **Requires team-wide buy-in**: Used by one person, it is just another document. If `.lex` changes are not part of the code review process, the spec will drift from the code just like every other design doc before it.

---

## Who Benefits

- **Regulated industries** (finance, healthcare): Every design decision is a numbered, traceable article — audit logs become trivial
- **Teams of 5+**: Design docs that stay in sync with code because they are structurally required to
- **Enterprise and SI projects**: Hard traceability from requirements to implementation
- **Long-term products**: Prevent architecture erosion as engineers rotate and business rules accumulate

Conversely, if you are in the early MVP validation stage or the team is two or three people, the return on investment is low. The value of this approach is **proportional to time and complexity**.

---

## Try It

```bash
git clone https://github.com/seunghan91/canoncode.git
cd canoncode

# Check the LaunchCrew example
cat examples/launchcrew-qa-matching.lex | python3 -m json.tool | head -50

# Build the Rust engine and validate
cd lib/lex_engine && cargo build --release
./target/release/lex_cli info -f ../../examples/launchcrew-qa-matching.lex
```

Full source: [github.com/seunghan91/canoncode](https://github.com/seunghan91/canoncode)

---

## What's Next

1. `.lex → code generation` via LLM integration
2. `code → .lex reverse engineering` automation
3. Side-by-side spec vs code comparison view in the web UI
4. npm package release (`npx canoncode init my-project`)

---

## Key Takeaways

- 2,800 lines of code and 160 lines of spec describe the same system, but they carry different kinds of information. Code captures *how*. The spec captures *why*.
- The Case Law format is one of the most effective ways to preserve the context behind exception-handling decisions — the kind of context that normally lives in a Slack thread that gets deleted.
- The most immediate benefits of spec-driven development are onboarding speed and debugging clarity. Architecture violation detection comes after that.
- The tool's value only emerges when the whole team treats spec changes as a required part of the development workflow. A spec maintained by one person becomes just another abandoned document.

**Maintain laws, not code.** Still experimental, but the potential is real.
