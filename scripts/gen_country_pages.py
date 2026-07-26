#!/usr/bin/env python3
"""
국가별 'Build With AI' 페이지 생성.

구조:
  - 수치·사실은 Python 이 data/countries.json 에서 정확히 조립한다 (LLM 이 숫자를 만지지 않는다).
  - 서사는 kimi k3 가 국가별로 따로 쓴다 (템플릿 변수 치환이 되지 않도록).

사용:
  python3 scripts/gen_country_pages.py --only Kenya Nepal Mongolia   # 파일럿
  python3 scripts/gen_country_pages.py --all                          # 전수
  python3 scripts/gen_country_pages.py --all --skip-existing          # 이어서
"""

import argparse
import concurrent.futures as cf
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "countries.json"
OUTDIR = ROOT / "content" / "build-with-ai"
CACHE = ROOT / "scripts" / ".narrative_cache"
KIMI = pathlib.Path.home() / ".local" / "bin" / "kimi"

SOURCE_URL = "https://www.anthropic.com/economic-index"

# 프롬프트 규칙이나 검증 로직을 바꾸면 이 값을 올린다 -> 캐시 전량 무효화
PROMPT_VERSION = "3"
RUN_DATE = "2026-07-26"


def fmt_pp(v):
    if v is None:
        return "n/a"
    return f"+{v}" if v > 0 else str(v)


def build_prompt(c, g):
    f = c["facts"]
    name = c["name"]

    lines = [
        f"COUNTRY: {name}",
        f"Anthropic Usage Index: {c['usage_index']} (rank {c['usage_rank']} of 121)",
        f"Korea's index for comparison: {c['korea_index']}",
        f"Share of conversations that are work: {c['work_pct']}% (global {g['use_case_work_pct']}%)",
        f"Share that are coursework/learning: {c['coursework_pct']}% (global {g['use_case_coursework_pct']}%)",
        f"Automation-leaning: {c['automation_pct']}% vs augmentation {c['augmentation_pct']}% "
        f"(global automation {g['automation_pct']}%)",
        "",
        "TOP REQUEST TOPICS (share of sampled conversations):",
    ]
    for t in c["top_request_topics"]:
        base = g["topics"].get(t["name"])
        extra = f" [global {base}%]" if base else ""
        lines.append(f"  - {t['name']}: {t['pct']}%{extra}")

    lines.append("")
    lines.append("WHERE THIS COUNTRY LEADS KOREA:")
    if f["ahead_of_korea"]:
        for t in f["ahead_of_korea"]:
            lines.append(
                f"  - {t['name']}: {t['pct']}% vs Korea's {t['korea_pct']}% ({t['delta_pct']}% higher)"
            )
    else:
        lines.append("  - (none in the top topics)")

    lines.append("")
    lines.append("MOST DISTINCTIVE VS GLOBAL AVERAGE:")
    for t in f["distinct_topics"]:
        lines.append(
            f"  - {t['name']}: {t['pct']}% vs global {t['baseline_pct']}% ({fmt_pp(t['delta_pct'])}%)"
        )
    for j in f["distinct_jobs"]:
        lines.append(
            f"  - job tasks '{j['name']}': {j['pct']}% vs global {j['baseline_pct']}% ({fmt_pp(j['delta_pct'])}%)"
        )

    facts_block = "\n".join(lines)

    return f"""You are helping write one page of a personal website. The author is Seunghan, \
a software engineer in Seoul who offers free, informal technical help to people building \
things with AI anywhere in the world. This page is for readers in {name}.

Write ONLY the body prose for the section titled "What the data says about {name}". \
Target 320-420 words. Output plain Markdown paragraphs. No headings, no bullet lists, \
no preamble, no sign-off, no code fences.

DATA (this is the only factual material you may use):
{facts_block}

HARD RULES — violating any of these makes the output unusable:
1. Do NOT invent any statistic, year, percentage, currency amount, company name, \
government programme, institution, or named person. If it is not in the DATA block above, \
you may not state it as fact. Qualitative context about {name} that any informed reader \
would accept as common knowledge (languages spoken, geography, time zone relative to Seoul, \
general economic character) is allowed, but keep it light and never numeric.
2. NEVER write that {name} is "catching up", "behind", "developing", "emerging", or would \
benefit from Korean guidance. The author explicitly rejects that framing. Where the data \
shows {name} ahead of Korea, say so plainly.
3. These figures describe CONVERSATIONS matched to job tasks — not people's actual jobs, and \
not who the users are. Write "conversations matched to software development tasks", never \
"developers in {name}". You may NOT say or imply who these people are: not "students", not \
"early-career builders", not "freelancers", not "professionals". A high coursework share means \
conversations looked like coursework — it does NOT mean the users are students. Never draw \
conclusions about employment, hiring, job loss, or the labour market.
3a. This is descriptive data with no significance testing. Never write "statistically", \
"significant", "margin of error", "correlated", or "indistinguishable from" — you cannot \
make claims about statistical confidence from these figures.
3b. This is ONE snapshot with no trend series. You may NOT claim anything is rising, falling, \
growing, accelerating, newly arrived, early or late in adoption. No years, no dates, no \
"increasingly". The data cannot support any statement about change over time.
4. No hype adjectives (revolutionary, groundbreaking, unprecedented, remarkable, exciting). \
No "In conclusion". No rhetorical questions to open.
5. Do not address the reader as though they are poor, remote, or disadvantaged. Address them \
as a peer who is already building.

WHAT TO ACTUALLY DO:
Lead with the single most interesting thing in this country's data — the number that would \
surprise someone who assumed a simple rich-country/poor-country ordering. Say what it plausibly \
reflects about how people there are using these tools (reasoning from the data, hedged where it \
is a guess). If the country leads Korea somewhere, make that concrete. Close by connecting it to \
what Seunghan can help with: shipping apps to stores, AI agent and MCP tooling, backend and auth, \
mobile development, and reliability engineering.

Produce the prose itself in THIS response. Do not describe what you wrote, do not summarise your compliance, do not refer to any earlier message — the raw prose is the entire expected output.\n\nDistinctiveness matters more than polish. Another page in this series covers a country with a \
similar profile, and the two must not read alike. Anchor every paragraph in {name}'s specific \
numbers."""


def cache_key(c, g):
    """서사 캐시 키. 입력 데이터나 프롬프트 규칙이 바뀌면 자동으로 달라진다."""
    payload = json.dumps(
        {"prompt": build_prompt(c, g), "v": PROMPT_VERSION}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def call_kimi(prompt, retries=2):
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                [str(KIMI), "--quiet", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=420,
                cwd="/tmp",
            )
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(5)
                continue
            return None

        out = r.stdout.strip()
        # kimi 부산물 제거
        out = re.sub(r"<choice>.*?</choice>", "", out, flags=re.S)
        out = re.sub(r"^To resume this session:.*$", "", out, flags=re.M)
        out = re.sub(r"^Shell cwd was reset to.*$", "", out, flags=re.M)
        out = re.sub(r"^```(?:markdown)?\s*$", "", out, flags=re.M)
        out = out.strip()

        if len(out.split()) >= 250:
            return out
        if attempt < retries:
            time.sleep(5)
    return None


def get_narrative(c, g, max_rounds=3):
    """kimi 호출 + 검증 + 위반 시 재교정. 통과한 서사 또는 (None, 사유) 반환."""
    prompt = build_prompt(c, g)
    last_problems = []
    for rnd in range(max_rounds):
        text = call_kimi(prompt)
        if not text:
            last_problems = ["kimi 응답 실패"]
            continue
        problems = validate(text, c)
        if not problems:
            return text, None
        last_problems = problems
        # 위반 내용을 명시해 재작성 요구
        prompt = (
            build_prompt(c, g)
            + "\n\nA previous attempt was REJECTED for these violations:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nRewrite from scratch. Do not use those words or constructions anywhere. "
            "Do not mention any year. Stay strictly within the DATA block for all facts."
        )
    return None, "; ".join(last_problems)


def validate(text, c):
    """kimi 산출물 검증. 반환: 위반 목록.

    표면 단어뿐 아니라 '데이터가 지지하지 않는 주장'까지 잡는다. 이 데이터는 대화를
    직무 과업에 매칭한 것이라, 사용자가 누구인지·고용이 어떻게 되는지는 말해주지 않는다.
    """
    bad = []
    low = text.lower()

    # 0. 형식 — kimi 가 서사 대신 자기 작업 요약(메타 응답)을 내는 경우가 있다.
    #    --final-message-only 가 마지막 턴만 잡기 때문에 구조적으로 발생한다.
    words = len(text.split())
    if words < 250:
        bad.append(f"분량 미달 {words}단어 (최소 250)")
    for meta in [
        "previous message", "previous turn", "delivered in my", "meets all requirements",
        "meets all constraints", "as requested above", "i have written", "the prose is complete",
        "was delivered", "in my earlier",
    ]:
        if meta in low:
            bad.append(f"메타 응답 '{meta}' — 서사가 아니라 작업 보고")
            break

    # 1. 시혜적 프레이밍
    for phrase in [
        "catching up", "catch up", "caught up", "falling behind", "fall behind",
        "lagging", "lags behind", "developing nation", "developing country",
        "developing world", "emerging market", "emerging economy", "third world",
        "less developed", "underdeveloped", "leapfrog",
    ]:
        if phrase in low:
            bad.append(f"시혜적 표현 '{phrase}'")

    # 2. AI 클리셰 / hype
    for phrase in [
        "in conclusion", "it is worth noting", "revolutionary", "groundbreaking",
        "unprecedented", "remarkable", "game-chang", "cutting-edge", "transformative",
    ]:
        if phrase in low:
            bad.append(f"클리셰/hype '{phrase}'")

    # 3. 사용자 정체 추론 — 이 데이터는 '누가 썼는지'를 말하지 않는다
    for phrase in [
        "students and", "are students", "students are", "student population",
        "early-career", "young professionals", "freelancers are", "developers in",
        "engineers in", "workers in", "professionals in", "user base is",
        "these users are", "people there are mostly", "predominantly students",
    ]:
        if phrase in low:
            bad.append(f"사용자 정체 추론 '{phrase}' (데이터는 대화지 사람이 아님)")

    # 4. 고용 / 노동시장 추론 — 출처 방법론이 명시적으로 금지
    for phrase in [
        "job market", "labour market", "labor market", "job loss", "job losses",
        "displac", "unemploy", "replace jobs", "replacing workers", "workforce is",
        "job security", "hiring", "employment rate",
    ]:
        if phrase in low:
            bad.append(f"고용/노동시장 추론 '{phrase}'")

    # 4b. 통계적 주장 — 유의성 검정을 한 데이터가 아니다
    for phrase in [
        "statistically", "significant difference", "margin of error", "confidence interval",
        "correlat", "causal", "p-value", "indistinguishable from",
    ]:
        if phrase in low:
            bad.append(f"통계 주장 '{phrase}' (유의성 검정 없는 데이터)")

    # 5. 데이터가 측정하지 않는 시간 축 (도입 시기·추세)
    for phrase in [
        "arrived late", "arrived early", "adopted late", "early adopter",
        "growing fast", "rapidly growing", "on the rise", "increasing share",
        "declining share", "trend toward", "year over year",
    ]:
        if phrase in low:
            bad.append(f"추세/시점 주장 '{phrase}' (스냅샷 1개라 추세 측정 불가)")

    # 6. 날조된 연도 — 그룹이 아닌 전체 매치를 로그에 남긴다
    for y in re.findall(r"\b(?:19|20)\d{2}\b", text):
        bad.append(f"연도 언급 '{y}' — 데이터에 없는 사실 주장 가능성")
        break

    return bad


def render_page(c, g, narrative, draft=False):
    name = c["name"]
    f = c["facts"]
    ahead = f["ahead_of_korea"]

    lead = ""
    if ahead:
        t = ahead[0]
        lead = (
            f"In {name}, {t['pct']}% of sampled conversations were matched to "
            f"{t['name'].lower()} tasks. In Korea that figure is {t['korea_pct']}%."
        )

    # description/keywords 를 국가별 실제 데이터로 구성한다.
    # (국가명만 치환하는 문자열은 doorway page 패턴으로 읽힌다)
    top = c["top_request_topics"][0] if c["top_request_topics"] else None
    if ahead:
        t0 = ahead[0]
        desc = (
            f"{t0['pct']}% of sampled Claude conversations in {name} were matched to "
            f"{t0['name'].lower()} tasks, against {t0['korea_pct']}% in Korea. "
            f"What that looks like up close, and free technical help from a Seoul engineer."
        )
    elif top:
        desc = (
            f"{name}'s Anthropic Usage Index is {c['usage_index']}, and {top['pct']}% of "
            f"sampled conversations were matched to {top['name'].lower()} tasks. "
            f"What that looks like up close, and free technical help from a Seoul engineer."
        )
    else:
        desc = (
            f"Observed AI usage in {name}, read against Korea's, plus free technical help "
            f"from a Seoul engineer."
        )

    kw = [f"AI usage in {name}", f"Anthropic Economic Index {name}"]
    for t in c["top_request_topics"][:2]:
        kw.append(f"{t['name']} {name}")
    kw.append("free developer mentoring")
    keywords = ", ".join(f'"{k}"' for k in kw)

    rows = []
    for t in c["top_request_topics"]:
        base = g["topics"].get(t["name"])
        vs = ""
        if base:
            d = round((t["pct"] - base) / base * 100)
            vs = f"{d:+d}%" if d else "0%"
        rows.append(f"| {t['name']} | {t['pct']}% | {base if base else '—'}% | {vs or '—'} |")
    topic_table = "\n".join(rows)

    job_rows = "\n".join(
        f"| {j['name']} | {j['pct']}% |" for j in (c["top_job_categories"] or [])
    )

    ahead_block = ""
    if ahead:
        items = "\n".join(
            f"- **{t['name']}** — {t['pct']}% here, {t['korea_pct']}% in Korea "
            f"({t['delta_pct']}% higher)"
            for t in ahead
        )
        ahead_block = f"""
## Where {name} is ahead of Korea

{items}
"""

    return f"""---
title: "Build With AI in {name}"
date: {RUN_DATE}
lastmod: {RUN_DATE}
draft: {"true" if draft else "false"}
ShowBreadCrumbs: true
ShowToc: true
TocOpen: false
description: "{desc}"
keywords: [{keywords}]
---

{lead}

## What the data says about {name}

{narrative}

## The numbers

| | {name} | Global |
|---|---|---|
| Anthropic Usage Index | **{c['usage_index']}** (rank {c['usage_rank']} of 121) | 1.00 baseline |
| Work conversations | {c['work_pct']}% | {g['use_case_work_pct']}% |
| Learning / coursework | {c['coursework_pct']}% | {g['use_case_coursework_pct']}% |
| Automation-leaning | {c['automation_pct']}% | {g['automation_pct']}% |
| Augmentation-leaning | {c['augmentation_pct']}% | {g['augmentation_pct']}% |

### Most common request topics

| Topic | {name} | Global | Difference |
|---|---|---|---|
{topic_table}

### Job-task categories these conversations matched

| Category | Share |
|---|---|
{job_rows}
{ahead_block}
## Ask me something

I'm Seunghan, an engineer in Seoul. I answer questions about shipping apps,
AI agent tooling, backends, and reliability — free, and for anyone.
[Here's what I can help with and why](/en/build-with-ai/).

[GitHub](https://github.com/seunghan91) &middot;
[KakaoTalk open chat](https://open.kakao.com/o/sYu2sj9h) &middot;
[All countries](/en/build-with-ai/)

---

<small>

Figures from the [Anthropic Economic Index]({SOURCE_URL}), snapshot {c.get('period', '2026-05-01')}.
They describe observed Claude conversations matched to job tasks — not who users are, not
employment, not the labour market. A country absent from the index means data was not
published, never a measured zero.

</small>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="국가명 (원문 표기)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--publish", nargs="*", default=None,
                    help="이 국가들만 draft:false. 나머지는 draft:true")
    args = ap.parse_args()

    d = json.loads(DATA.read_text())
    g = d["global"]
    period = d["period"]
    countries = d["countries"]

    if args.only:
        want = set(args.only)
        countries = [c for c in countries if c["name"] in want]
        missing = want - {c["name"] for c in countries}
        if missing:
            sys.exit(f"데이터에 없는 국가: {sorted(missing)}")
    elif not args.all:
        sys.exit("--only 또는 --all 필요")

    CACHE.mkdir(exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    todo = []
    skipped = 0
    for c in countries:
        c["period"] = period
        if args.skip_existing and (OUTDIR / f"{c['slug']}.en.md").exists():
            skipped += 1
            continue
        todo.append(c)

    if args.dry_run:
        for c in todo:
            print(f"dry-run: {c['name']} -> {c['slug']}.en.md")
        print(f"\n대상 {len(todo)} / 건너뜀 {skipped}")
        return

    total = len(todo)
    ok, failed = 0, []
    lock = threading.Lock()
    done = [0]

    def work(c):
        # 예외가 하나라도 새어나가면 ex.map 이 배치 전체를 버린다 -> 반드시 격리
        try:
            cache_f = CACHE / f"{c['slug']}-{cache_key(c, g)}.txt"
            if cache_f.exists():
                narrative = cache_f.read_text().strip()
                if validate(narrative, c):
                    cache_f.unlink()
                    narrative, err = get_narrative(c, g)
                    src = "kimi-redo"
                else:
                    err, src = None, "cache"
            else:
                narrative, err = get_narrative(c, g)
                src = "kimi"
                if narrative:
                    cache_f.write_text(narrative)
            return c, narrative, err, src
        except Exception as e:
            return c, None, f"{type(e).__name__}: {e}", "error"

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for c, narrative, err, src in ex.map(work, todo):
            with lock:
                done[0] += 1
                i = done[0]
            if not narrative:
                failed.append((c["name"], err))
                print(f"[{i}/{total}] {c['name']} — 실패: {err}", flush=True)
                continue
            is_draft = args.publish is not None and c["name"] not in set(args.publish)
            (OUTDIR / f"{c['slug']}.en.md").write_text(render_page(c, g, narrative, is_draft))
            ok += 1
            print(
                f"[{i}/{total}] {c['name']} — 생성 ({src}, {len(narrative.split())}단어)",
                flush=True,
            )

    print(f"\n생성 {ok} / 건너뜀 {skipped} / 실패 {len(failed)}")
    for n, why in failed:
        print(f"  실패: {n} — {why}")


if __name__ == "__main__":
    main()
