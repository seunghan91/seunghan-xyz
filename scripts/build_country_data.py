#!/usr/bin/env python3
"""
Anthropic Economic Index 국가별 원본 데이터 -> 페이지 생성용 파생 데이터.

각 국가 페이지가 템플릿 변수 치환이 아니라 '그 나라에만 해당하는 관찰'을 담도록,
글로벌 평균 및 한국 대비 델타를 계산해 country별 고유 사실(facts)을 뽑아낸다.

입력: raw_econ_index.json  (mcp econ_index_list_countries 원본)
출력: data/countries.json

표기 규율 (Anthropic Economic Index 방법론):
- 대화 내용을 직무 과업에 매칭한 값이다. 사용자를 직업에 매칭한 것이 아니다.
  -> "케냐 개발자들이" (X) / "소프트웨어 개발 과업에 매칭된 대화가" (O)
- 고용/일자리 대체에 대한 근거로 쓸 수 없다.
- null 은 미발행이지 측정된 0 이 아니다.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "scripts" / "raw_econ_index.json"
OUT = ROOT / "data" / "countries.json"

PERIOD = "2026-05-01"
SOURCE_URL = "https://www.anthropic.com/economic-index"

# econ_index_get_global_usage (2026-05-01) 기준선
GLOBAL = {
    "augmentation_pct": 51.38,
    "automation_pct": 48.62,
    "use_case_work_pct": 43.36,
    "use_case_personal_pct": 40.20,
    "use_case_coursework_pct": 16.45,
    "topics": {
        "Content Creation & Copywriting": 22.72,
        "Education & Learning": 13.23,
        "Software Development": 11.51,
        "Research & Intelligence": 10.94,
        "Hobbies & Lifestyle": 9.49,
        "Business Process & Operations": 4.70,
        "Document Processing & Extraction": 4.32,
        "Data Analysis & Business Intelligence": 3.83,
        "Knowledge Retrieval & Enterprise Search": 3.61,
        "Existential, Relational, and Emotional Support": 3.44,
        "Personal AI Assistant": 2.86,
        "DevOps & Infrastructure Operations": 2.82,
        "Companionship & General Conversation": 1.37,
        "Sales & Revenue Operations": 1.10,
        "Compliance & Regulatory": 1.06,
        "Customer Support & Service Operations": 0.60,
        "Cybersecurity & Threat Detection": 0.38,
        "Conversation & Meeting Intelligence": 0.26,
        "Trust & Safety / Platform Integrity": 0.07,
    },
    "jobs": {
        "Computer and Mathematical": 23.80,
        "Arts, Design, Entertainment, Sports, and Media": 13.55,
        "Educational Instruction and Library": 12.79,
        "Sales and Related": 9.14,
        "Office and Administrative Support": 7.89,
        "Management": 5.90,
        "Business and Financial Operations": 5.77,
        "Life, Physical, and Social Science": 4.51,
        "Architecture and Engineering": 3.56,
        "Healthcare Practitioners and Technical": 3.31,
    },
}

# 국가명 -> URL slug 예외 (기본은 소문자 + 하이픈)
SLUG_OVERRIDES = {
    "Côte d'Ivoire": "cote-divoire",
    "Türkiye": "turkiye",
    "Bosnia and Herzegovina": "bosnia-and-herzegovina",
    "Trinidad and Tobago": "trinidad-and-tobago",
    "Dominican Republic": "dominican-republic",
    "United Arab Emirates": "united-arab-emirates",
    "United Kingdom": "united-kingdom",
    "United States": "united-states",
    "South Korea": "south-korea",
    "South Africa": "south-africa",
    "New Zealand": "new-zealand",
    "Saudi Arabia": "saudi-arabia",
    "Sri Lanka": "sri-lanka",
    "Costa Rica": "costa-rica",
    "El Salvador": "el-salvador",
    "Hong Kong": "hong-kong",
    "North Macedonia": "north-macedonia",
    "Papua New Guinea": "papua-new-guinea",
}


def slugify(name: str) -> str:
    if name in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[name]
    s = name.lower()
    for a, b in [("'", ""), (".", ""), (",", ""), ("(", ""), (")", ""), (" ", "-"), ("&", "and")]:
        s = s.replace(a, b)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def as_map(rows):
    return {r["name"]: r["pct"] for r in (rows or [])}


def pct_delta(value, baseline):
    """baseline 대비 상대 변화율(%). baseline 이 0 이거나 없으면 None."""
    if baseline in (None, 0) or value is None:
        return None
    return round((value - baseline) / baseline * 100, 1)


def build_facts(c, kor):
    """이 나라에만 해당하는 관찰을 만든다. 각 항목은 페이지에서 한 문장이 된다."""
    facts = []
    topics = as_map(c.get("top_request_topics"))
    jobs = as_map(c.get("top_job_categories"))
    kor_topics = as_map(kor.get("top_request_topics"))

    # 1. 글로벌 평균 대비 가장 두드러진 요청 주제
    stand_out = []
    for name, pct in topics.items():
        base = GLOBAL["topics"].get(name)
        d = pct_delta(pct, base)
        if d is not None and abs(d) >= 15:
            stand_out.append({"name": name, "pct": pct, "baseline_pct": base, "delta_pct": d})
    stand_out.sort(key=lambda x: abs(x["delta_pct"]), reverse=True)
    facts_topics = stand_out[:3]

    # 2. 한국보다 높은 요청 주제 (시혜적 서술을 막는 핵심 근거)
    ahead_of_korea = []
    for name, pct in topics.items():
        kpct = kor_topics.get(name)
        if kpct is not None and pct > kpct:
            ahead_of_korea.append(
                {"name": name, "pct": pct, "korea_pct": kpct, "delta_pct": pct_delta(pct, kpct)}
            )
    ahead_of_korea.sort(key=lambda x: (x["delta_pct"] or 0), reverse=True)

    # 3. 자동화 / 증강 성향
    auto = c.get("automation_pct")
    automation_lean = None
    if auto is not None:
        d = round(auto - GLOBAL["automation_pct"], 2)
        automation_lean = {
            "automation_pct": auto,
            "augmentation_pct": c.get("augmentation_pct"),
            "vs_global_pp": d,
            "direction": "automation" if d > 1.5 else ("augmentation" if d < -1.5 else "balanced"),
        }

    # 4. 학습(coursework) 비중 — 제도가 아니라 개인이 밀어올리는 나라를 드러낸다
    cw = c.get("use_case_coursework_pct")
    coursework = None
    if cw is not None:
        coursework = {
            "pct": cw,
            "vs_global_pp": round(cw - GLOBAL["use_case_coursework_pct"], 2),
            "high": cw > GLOBAL["use_case_coursework_pct"] * 1.2,
        }

    # 5. 업무 비중
    work = c.get("use_case_work_pct")
    work_lean = None
    if work is not None:
        work_lean = {
            "pct": work,
            "vs_global_pp": round(work - GLOBAL["use_case_work_pct"], 2),
        }

    # 6. 직무 카테고리 중 글로벌 대비 두드러진 것
    job_stand_out = []
    for name, pct in jobs.items():
        base = GLOBAL["jobs"].get(name)
        d = pct_delta(pct, base)
        if d is not None and abs(d) >= 15:
            job_stand_out.append({"name": name, "pct": pct, "baseline_pct": base, "delta_pct": d})
    job_stand_out.sort(key=lambda x: abs(x["delta_pct"]), reverse=True)

    return {
        "distinct_topics": facts_topics,
        "ahead_of_korea": ahead_of_korea[:3],
        "automation_lean": automation_lean,
        "coursework": coursework,
        "work_lean": work_lean,
        "distinct_jobs": job_stand_out[:2],
    }


def main():
    if not RAW.exists():
        sys.exit(f"원본 데이터 없음: {RAW}")

    raw = json.loads(RAW.read_text())
    regions = raw["result"]["regions"]
    by_name = {r["name"]: r for r in regions}
    kor = by_name["South Korea"]
    kor_index = kor["anthropic_usage_index"]

    out = []
    for c in regions:
        idx = c.get("anthropic_usage_index")
        slug = slugify(c["name"])
        entry = {
            "name": c["name"],
            "slug": slug,
            "region_code": c.get("region_code"),
            "iso_numeric": c.get("iso_numeric"),
            "usage_index": idx,
            "usage_rank": c.get("usage_rank"),
            "usage_share_pct": c.get("usage_share_pct"),
            "augmentation_pct": c.get("augmentation_pct"),
            "automation_pct": c.get("automation_pct"),
            "work_pct": c.get("use_case_work_pct"),
            "personal_pct": c.get("use_case_personal_pct"),
            "coursework_pct": c.get("use_case_coursework_pct"),
            "top_job_categories": c.get("top_job_categories"),
            "top_request_topics": c.get("top_request_topics"),
            "artifacts": c.get("artifacts"),
            "korea_index": kor_index,
            "vs_korea_ratio": round(idx / kor_index, 3) if idx and kor_index else None,
            "facts": build_facts(c, kor),
        }
        out.append(entry)

    out.sort(key=lambda x: (x["usage_rank"] is None, x["usage_rank"] or 9999))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "period": PERIOD,
                "source_url": SOURCE_URL,
                "global": GLOBAL,
                "total": len(out),
                "countries": out,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    # 요약
    print(f"국가 {len(out)}개 -> {OUT}")
    ahead = [c for c in out if c["facts"]["ahead_of_korea"]]
    print(f"한국보다 높은 주제가 하나라도 있는 국가: {len(ahead)}개")
    no_facts = [c["name"] for c in out if not any(c["facts"].values())]
    if no_facts:
        print(f"고유 관찰 없음(페이지 생성 제외 대상): {no_facts}")


if __name__ == "__main__":
    main()
