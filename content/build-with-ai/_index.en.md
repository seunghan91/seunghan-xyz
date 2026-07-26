---
title: "Build With AI — From Wherever You Are"
date: 2026-07-26
lastmod: 2026-07-26
draft: false
hidemeta: true
ShowBreadCrumbs: true
ShowPostNavLinks: false
ShowToc: true
TocOpen: false
description: "A Seoul-based engineer offering free, direct help to anyone building with AI — anywhere in the world. With observed AI-usage data for 121 countries, and why the gap was never about language."
keywords: ["build with AI", "AI mentorship", "AI adoption by country", "learn AI development", "AI for developers worldwide"]
---

## The language barrier is over. That was the easy part.

I'm Seunghan, an engineer in Seoul.

For most of my career, the distance between a developer in Seoul and a developer
in Kathmandu, Kigali, or Dhaka was made of language. Documentation was in English.
Stack Overflow was in English. The good conversations happened in rooms you
couldn't enter unless you had already spent years learning to enter them.

That is finished. Not improving — finished. You can now read any document, argue
with any codebase, and ship any idea in the language you think in.

So the question changed. It is no longer *can you access this*. It is **how badly
do you want to build something, and will you stay when it stops being fun.**

That is the only part AI did not solve for you. It is also the only part that
was ever interesting.

---

## I'd rather not guess about your country. Here's the data.

I don't want to write the sentence "developing countries are catching up." It's
lazy, it's condescending, and the data says it's wrong.

Anthropic publishes an [Economic Index](https://www.anthropic.com/economic-index)
measuring observed Claude usage across 121 countries. I pulled the snapshot for
2026-05-01 and compared every country against Korea, where I live and work.

Here is what I found, and it reorganized how I think about this entire page:

> **In Kenya, 15.83% of sampled conversations were matched to software development
> tasks. In Korea, that figure is 10.42%.**

Kenya is not trailing Korea on that measure. Kenya is ahead of it. So is Nepal
(16.29%). So is Rwanda (13.73%).

This pattern repeats. Of the 121 countries with published data, **120 lead Korea
on at least one dimension of how people actually use AI** — I checked all of
them. Not one or two exceptional countries. A hundred and twenty.

Korea has a higher overall usage index (3.78, rank 14). That measures volume
relative to working-age population. It does not measure hunger, and it says
nothing about what people do once they arrive.

I want to be careful about what this data can and cannot say. It is a single
snapshot of conversations matched to job tasks. It cannot tell you who those
people are, whether usage is rising or falling, or anything about employment.
What it does show is that the shape of use varies enormously between countries,
and that the variation does not line up neatly with wealth.

---

## What I do, and what I'm offering

### The work I've done

I've spent since 2018 at Korea Exchange, the national securities exchange, in IT
strategy. The part worth mentioning: I spent three years as lead designer on the
bond market systems inside EXTURE 3.0, the exchange's trading engine that went
live in January 2023 — C/C++, 50-microsecond latency, roughly 940 million
messages a day. Systems where being wrong is expensive and slow to undo.

Since 2025 I've also worked on AI strategy and internal AI education there.

Separately, and on my own time, I build and ship: iOS and Android apps in the
App Store and Google Play, Rails backends, an OAuth 2.1 / OIDC identity provider
I wrote from scratch, and a lot of agent tooling on top of the Claude API and MCP.
I've shipped enough to have made most of the mistakes personally.

### What I can actually help with

Concretely, the things I know well enough to be useful on:

- **Getting an app to a store and through review.** iOS and Android. Rejections,
  privacy declarations, the specific things reviewers stop you for.
- **AI agent and MCP tooling.** Claude API, Model Context Protocol, agent
  architectures, retrieval. What works and what only demos well.
- **Backend and infrastructure.** Rails, Postgres, deployment, auth. OAuth 2.1 /
  OIDC if you're implementing identity yourself.
- **Mobile.** Flutter, iOS native (SwiftUI + TCA), Android Compose.
- **Systems that can't fail quietly.** Financial-grade reliability thinking —
  how to design something when the cost of an error is real.
- **Reading your architecture and telling you what I'd worry about.** Often the
  most useful hour.

### The terms

Free. There is no engagement, no proposal, no invoice. I am not a consultancy
and this is not a business — everything here is under my own name, on my own
time, and non-commercial.

I'm not offering national strategy or enterprise transformation. I'm offering to
be a specific, experienced person you can ask a specific question, which is the
thing I most wanted and could not find when I started.

Write in English, Korean, or your own language — I'll manage. That is the whole
premise of this page.

### How to get a good answer out of me

The more specific you are, the more useful I can be. "Here's my repository and
here's what it does wrong" gets you something concrete. "How do I learn AI" gets
you something generic, because I don't yet know anything about you.

So tell me what you're working on, even roughly. An error message, a repository,
a design you're unsure about, a decision you keep going back and forth on. If
you're at the very beginning and don't have any of that yet, say that too — I'll
point you somewhere useful.

---

## Find your country

Each country page uses that country's own published usage data — what people
there actually build with AI, where it leads Korea, and where the interesting
gap sits. Not a template with the name swapped.

{{< country-index >}}

**If your country isn't listed:** the Economic Index publishes 121 countries,
so a good number aren't there — Bhutan, for one. That means the data wasn't
published, never that usage was measured at zero. It changes nothing about
whether I'll answer you. Write anyway.

---

## Get in touch

- **GitHub** — [github.com/seunghan91](https://github.com/seunghan91). Open an
  issue on any repository, or start a discussion.

Tell me what you're building and where you're stuck. Include the code if there
is code. I read everything; I answer as fast as I can, which is not always fast.

---

<small>

Usage figures throughout are from the [Anthropic Economic
Index](https://www.anthropic.com/economic-index), snapshot 2026-05-01. They
describe observed Claude conversations matched to job tasks — not who users are,
not employment, not the labour market. A country not appearing means data was
not published, never a measured zero.

This site is personal and non-commercial, written under my own name and not on
behalf of my employer.

</small>
