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

The bigger your codebase gets, the harder it is to answer "why does this feature work like this?" You end up opening 5 files. The design doc was written 3 months ago and nobody knows if it still matches the code.

**What if the design doc itself was executable, and you maintained that instead of the code?**

I experimented with this idea in a side project called [CanonCode](https://github.com/seunghan91/canoncode).

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

---

## The Subject: LaunchCrew

[LaunchCrew](https://github.com/seunghan91/launchcrew) is a C2C QA matching platform I'm building:

- Developers (Makers) post QA testing needs
- Testers (Hunters) apply → get accepted → submit daily proof
- On completion, escrowed points are automatically released

Stack: Rails 8 + Inertia.js + Svelte 5 + Flutter

The core business logic spans **40+ files, 2,800+ lines** across models, controllers, services, and UI components.

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

### Escrow Payment Example

**.lex spec (2 clauses):**

```
"point type posts must escrow points_per_person × recruits_count immediately"
"On escrow failure, roll back post creation"
```

**Actual code (~200 lines across 4 files):** controller + service + model + migration with transaction locking, error handling, wallet updates, and transaction logging.

**2 clauses govern 200 lines** scattered across the codebase.

---

## What Worked

### 1. Onboarding
Reading one .lex file gives you the entire business logic in 10 minutes. Reading the codebase takes days.

### 2. Exception Traceability
Every exception is a **case law** entry linked to a specific article:

```
CASE-002: Tester drops out mid-testing
  Related: ACT-003 CL-005-3
  Ruling: Return only that tester's escrow to developer
```

No more hunting through catch blocks and git blame.

### 3. Architecture Violation Detection
If the constitution says "balance >= 0", the linter catches code changes that could violate it.

---

## Honest Limitations

1. **Doesn't replace code**: .lex defines "what", not "how". You still write code.
2. **JSON is verbose**: Markdown or YAML might be more concise.
3. **No auto code generation yet**: Unlike CodeSpeak, .lex → code generation is still planned.
4. **Overkill for small projects**: Not useful for prototypes or hackathons.

---

## Who Benefits

- **Regulated industries** (finance, healthcare): Every design decision is a numbered, traceable article
- **Teams of 5+**: Design docs that actually stay in sync with code
- **Enterprise/SI projects**: Requirements → implementation traceability
- **Long-term products**: Prevent architecture erosion over time

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

1. `.lex → code generation` (LLM integration)
2. `code → .lex reverse engineering` automation
3. Side-by-side spec vs code comparison in the web UI
4. npm package (`npx canoncode init my-project`)

**Maintain laws, not code.** Still experimental, but the potential is real.
