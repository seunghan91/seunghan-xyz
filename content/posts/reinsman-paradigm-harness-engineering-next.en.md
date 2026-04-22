---
title: "Reinsman — What Comes After Harness Engineering"
date: 2026-04-26T09:00:00+09:00
draft: false
tags: ["AI", "harness engineering", "agents", "Reinsman"]
description: "If harness engineering is about designing the tack, the person who holds the reins and steers through actual terrain also needs a name. I've started calling this role the Reinsman."
---

Since Mitchell Hashimoto named "harness engineering" in February 2026, the industry has adopted it remarkably fast. OpenAI, Anthropic, and LangChain picked it up within days. Every team running agents is now doing the same practice: every time an agent makes a mistake, add a rule, ship a tool, prevent the recurrence.

But I kept bumping into an unnamed position while following this arc.

No matter how well you design the harness, there's still a separate role in the field: someone who **holds and operates** that harness. Someone who catches context mismatches rather than rule violations. Someone who translates a practitioner's vague "this feels off" into a concrete rule. Someone who converts organizational anxiety into specific safeguards.

It struck me as strange that this role had no name. It differs from the harness engineer in timing, tools, and success metrics — yet the two were being lumped together.

---

English already has a word for it. The person who holds the reins of a horse: **Reinsman**. A driver.

OpenAI's harness engineering tagline — *"Humans steer. Agents execute."* — may not be accidental either. `Steer` comes from Old English `stēoran`, meaning both *to hold a ship's tiller* and *to hold the reins of a horse*. The answer was already inside the sentence, but most follow-up discussion fixated on the back half: *execute*.

So I've started giving a name to the practice implied by the front half — *Humans steer*.

**Reinsman**: the role of tuning agent behavior to real-world context on top of a harness, and translating between people and systems.

I'm not claiming we need to coin new terms. If another one already exists, I'll gladly switch. But right now the vocabulary for this role is missing, and the practice is invisible because of it.

---

The difference between a harness engineer and a Reinsman, in one line:

- **Harness Engineer**: ensures the agent doesn't do things it *shouldn't*.
- **Reinsman**: ensures the agent's allowed actions don't happen *out of context*.

The former can be codified into rules. The latter cannot. Context doesn't fit inside a harness.

What a Reinsman typically does falls into four shapes:

1. **Translation** — between practitioner language and agent language, both directions.
2. **Tuning** — moving harness parameters by season, situation, and stakes.
3. **Judgment** — detecting mistakes not yet codified, and feeding them back to the engineer.
4. **Persuasion** — converting organizational anxiety about AI into concrete safeguards people can see.

None of the four fits inside an `AGENTS.md` file.

---

I've been writing an extension to Hashimoto's formula like this:

```
Agent       = Model + Harness        (Hashimoto, 2026)
Production  = Agent + Reinsman       (2027-)
```

Anthropic and OpenAI make the models. HashiCorp-class vendors build the harnesses. But the reins need to be held by people in the field — us.

This isn't a new practice. Many teams already do it. It just didn't have a name yet.

---

**References**
- Mitchell Hashimoto, [Engineer the Harness (My AI Adoption Journey, Step 5)](https://mitchellh.com/writing/my-ai-adoption-journey), Feb 2026
- OpenAI, *Harness engineering: leveraging Codex in an agent-first world*, Feb 2026
