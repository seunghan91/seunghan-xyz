---
title: "LLM이 지어낸 법령을 DB로 걸러내기 — 한국어 법률 인용 환각 방지 실전"
date: 2026-04-09T09:00:00+09:00
draft: false
tags: ["LLM", "Rails", "Postgres", "법률AI", "환각방지"]
description: "GPT-4가 법령을 인용하면 18-29%는 존재하지 않는다. 한국어 조/항/호/목 패턴을 정규식으로 뽑고 Postgres로 검증해서 환각을 막은 실전 기록."
---

법률 AI 서비스를 만들다 보면 이런 순간이 온다. LLM이 자신감 있게 "민법 제103조의2에 따라..." 라고 답변을 줬는데, 확인해보니 **제103조의2라는 조문은 존재하지 않는다**. 본조인 제103조만 있고 가지조문은 만들어진 것이다.

이게 얼마나 심각한 일인지는 이미 유명한 사건이 증명했다. 2023년 미국 Mata v. Avianca 소송에서 뉴욕의 한 변호사가 ChatGPT가 생성한 판례를 법원 제출서류에 인용했다가 **제재를 받았다**. 판례가 전부 지어낸 것이었던 거다. 법률 도메인에서 AI 환각은 그냥 버그가 아니라 법률 책임 문제로 번진다.

이번 작업에서 내가 만든 서비스도 같은 위험에 노출돼 있었다. 사용자가 법령 개정 diff를 보면서 "이 개정이 우리 회사에 어떤 영향?" 같은 후속 질문을 하면, LLM이 답변을 돌려주면서 근거 조문을 인용한다. 그 인용이 진짜인지 아닌지를 사용자에게 떠넘길 수는 없었다.

그래서 만든 게 `Legalize::CitationExtractor`다. 정규식으로 답변 텍스트에서 인용을 뽑고, Postgres에 실제로 그 조문이 있는지 검증한 뒤, **검증된 것과 그렇지 않은 것을 UI에서 분리해서 보여준다**. 이 포스트는 그 과정에서 배운 것과 삽질한 것의 기록이다.

---

## GPT-4 조차 조문의 20%는 지어낸다

먼저 문제 규모를 알고 시작해야 한다. 2024-2025년 여러 연구에서 측정한 LLM의 인용 환각률은 충격적이다.

| 모델 | 인용 환각률 | 조건 |
|---|---|---|
| GPT-3.5 | 39.6 ~ 55% | 기본 |
| GPT-4 | 18 ~ 28.6% | 기본 |
| GPT-5 | 7 ~ 8% | 웹 검색 통합 |
| 다층 검증 시스템(INRA) | 0.1% 미만 | 6-layer validation |

JMIR, Nature, Economics 저널에 실린 연구들이 공통적으로 말하는 건 하나다. **LLM 자체 능력만으로는 인용의 정확성을 보장할 수 없다**. 최신 GPT-5조차 100개의 인용을 주면 7-8개는 가짜다. 법률 전문 서비스에서 이 숫자는 용납되지 않는다.

Stanford가 2025년에 발표한 Legal RAG 벤치마크는 더 놀라운 결과를 보여줬다. **잘 설계된 RAG 파이프라인조차도 6번에 1번 꼴로 인용을 조작한다**. 단순히 관련 문서를 검색해서 프롬프트에 넣는 것만으로는 부족하다는 뜻이다.

그래서 현재 업계가 수렴하는 해결책은 세 단계다.

1. **Retrieval-Augmented Generation (RAG)** — 외부 소스에서 관련 문서 가져오기
2. **Span-level Verification** — 생성된 각 주장이 소스에 실제 뒷받침되는지 매칭
3. **Mechanical Citation Verification** — 인용된 파일/조문이 실제로 존재하는지 기계적 확인

내가 이번에 구현한 건 3번에 집중한 접근이다. 다른 두 단계는 기존 서비스에 이미 있었고, 빠져있던 마지막 검증 층을 채운 것이다.

---

## 삽질 1: 처음엔 LLM 응답을 그대로 믿었다

초기 버전의 채팅 서비스는 이렇게 생겼었다.

```ruby
def llm_answer(law:, diff:, question:)
  prompt = <<~PROMPT
    법령명: #{law.name}
    diff: #{diff}
    질문: #{question}

    아래 JSON 으로 답하라.
    { "answer": "...", "citations": ["민법 제103조"], "followups": [...] }
  PROMPT

  response = @client.chat_completion(MODEL, prompt)
  JSON.parse(response.dig("choices", 0, "message", "content"))
end
```

LLM에게 "citations 배열에 근거 조문을 적어줘"라고 요청하고, 그걸 그대로 프론트엔드에 넘긴다. 사용자 화면에 "「민법」 제103조" 같은 링크 뱃지가 뜬다.

이게 왜 위험한지는 직접 테스트해봤을 때 알았다. LLM이 답변 본문에서는 "민법 제103조의 남용 금지 조항"이라고 썼는데, citations 배열에는 엉뚱하게 "민사집행법 제235조"가 들어가 있었다. 본문과 구조화된 필드가 일치하지 않는 거다. 그리고 그 "민사집행법 제235조"는 확인해보니 존재하지 않는 조문이었다.

LLM이 **JSON 스키마 채우기 위해 아무거나 써넣는** 현상이다. 출력 형식 제약을 강하게 걸수록 환각이 늘어나는 역설이 있는데, 바로 그 케이스였다.

그래서 방향을 바꿨다. **LLM의 `citations` 필드를 믿지 말고, 답변 본문 전체를 내가 다시 파싱한다**. 본문에 실제로 등장한 조문만 추출하고, 그걸 DB로 존재 검증한다.

---

## 한국어 법령 인용 패턴은 생각보다 복잡하다

정규식을 짜기 전에 먼저 한국어 법령 인용 규칙을 정리해야 했다. 법제처 공식 표기법은 이렇다.

| 레벨 | 표기 | 예시 |
|---|---|---|
| 법령명 | 낫표 `「」` | 「민법」 |
| 편 | 제N편 | 제1편 |
| 장 | 제N장 | 제5장 |
| 절 | 제N절 | 제1절 |
| 관 | 제N관 | 제3관 |
| 조 | 제N조 | 제103조 |
| 가지조문 | 제N조의M | 제103조의2 |
| 항 | 제N항 | 제1항 |
| 호 | 제N호 | 제2호 |
| 목 | **가목** (제N목 아님!) | 가목, 나목, 다목 |

공식 표기는 공백 없이 붙여 쓴다. 예를 들어 민법의 가장 깊은 인용은 이런 식이다.

```
「민법」 제1편제5장제1절제103조제1항제2호가목
```

여기서 헷갈리는 게 몇 개 있다.

첫째, **목은 "제N목"이 아니라 "가목/나목/다목"** 이다. 한글 자음 순서다. 초보자는 "제1목"으로 쓰려다가 틀린다.

둘째, **가지조문**(枝條文)이다. 기존 조문 사이에 새 조문을 끼워넣을 때 번호를 밀지 않으려고 "제10조의2"처럼 쓴다. 제10조와 제11조 사이에 추가된 새 조문이라는 뜻이다. 이게 또 항/호/목을 가질 수 있다. "제10조의2제1항제3호"처럼.

셋째, 실제 문서에서는 낫표 없이 쓰는 경우도 많다. "민법 제103조" 이렇게. 이건 공식 규정은 낫표를 권장하지만 현실 관행상 생략이 흔하다.

정규식 설계할 때 이 모든 케이스를 커버해야 했다.

---

## 삽질 2: Ruby extended regex에서 한국어 주석이 폭탄이었다

첫 시도는 가독성을 위해 Ruby의 `/x` extended mode로 썼다.

```ruby
BRACKETED = /
  「([가-힣A-Za-z0-9\s·]+?)」     # 법령명
  \s*
  제(\d+)조                      # 조
  (?:의(\d+))?                   # 가지조문 (선택)
  (?:\s*제(\d+)항)?              # 항 (선택)
  (?:\s*제(\d+)호)?              # 호 (선택)
  (?:\s*([가-하])목)?            # 목 (선택)
/x
```

스펙을 돌렸더니 `SyntaxError` 폭탄이 떨어졌다.

```
citation_extractor.rb:33: syntax errors found (SyntaxError)
  31 |     PLAIN = /
  32 |       (?<![가-힣A-Za-z])             # 단어 경계 시작
> 33 | ... 끝이 법/령/규칙/규정)
     |     ^~~~ end pattern with unmatched parenthesis
     |          ^ unexpected local variable or method, expecting end-of-input
```

원인을 찾는데 한참 걸렸다. `/x` extended mode는 공백과 `#` 뒤를 주석으로 처리한다. 그런데 내 한국어 주석에 `)` 문자가 들어가 있었다. `"끝이 법/령/규칙/규정)"` 이 부분. Ruby 파서는 이 `)` 를 **정규식 종료 문자**로 해석했다. `/` 도 마찬가지 문제를 일으킨다.

해결은 단순했다. extended mode를 버리고 한 줄 정규식으로 바꿨다. 가독성은 떨어지지만 한국어 주석과 충돌하지 않는다.

```ruby
BRACKETED = /「([가-힣A-Za-z0-9\s·]+?)」\s*제(\d+)조(?:의(\d+))?(?:\s*제(\d+)항)?(?:\s*제(\d+)호)?(?:\s*([가-하])목)?/

PLAIN = /(?<![가-힣A-Za-z])([가-힣]{1,18}(?:법|령|규칙|규정))\s*제(\d+)조(?:의(\d+))?(?:\s*제(\d+)항)?(?:\s*제(\d+)호)?(?:\s*([가-하])목)?/
```

한국어 다루는 프로젝트에서 정규식 쓸 때 주의할 점이다. **한국어 주석 안에 정규식 메타 문자가 있으면 extended mode는 피하라.**

---

## 삽질 3: 그리디 백트래킹 실패

낫표 없는 인용 패턴 `PLAIN` 을 짤 때 또 걸렸다. 처음엔 이렇게 썼다.

```ruby
PLAIN = /...([가-힣]{2,20}(?:법|령|규칙|규정))\s*제(\d+)조.../
```

의도는 "한글 2-20자로 끝이 법/령/규칙/규정으로 끝나는 단어"였다. "민법", "상법", "국세기본법", "시행령" 같은 거.

테스트: `"민법 제103조에 따라"` → 매치 실패. 왜?

디버깅하면서 깨달았다. `[가-힣]{2,20}`는 greedy다. "민법"은 2글자인데 greedy로 "민법" 전체를 소비해버린다. 그 다음 `(?:법|령|규칙|규정)`이 와야 하는데 이미 "법"을 앞에서 먹어치웠으니 **뒤에 매칭할 게 없다**. Ruby regex는 백트래킹해서 `[가-힣]{2,20}`를 1글자로 줄이려고 하지만 `{2,20}` 최소가 2라서 줄일 수 없다. 매치 실패.

수정:

```ruby
PLAIN = /(?<![가-힣A-Za-z])([가-힣]{1,18}(?:법|령|규칙|규정))\s*제(\d+)조.../
```

`{1,18}`로 바꿨다. prefix를 1글자까지 줄일 수 있으니 "민" 1글자 + "법" 1글자 = "민법" 으로 매칭된다. 총 2-19 글자까지 법령명 허용.

**정규식에서 greedy 수량자와 그 뒤의 required 패턴을 설계할 때는 항상 백트래킹 여유를 남겨야 한다.** 이 실수는 정규식 짜는 사람이면 누구나 한번씩 겪는다.

---

## DB 검증: path_label `ends_with` 매칭

정규식으로 추출한 인용을 DB로 검증하는 단계다. 내가 Postgres에 저장한 `legalize_articles` 테이블 구조는 이렇다.

```ruby
# schema
legalize_articles:
  - level (enum: book/chapter/section/subsection/article/paragraph/item/subitem)
  - number (예: "103", "1", "가")
  - branch (예: 2 for 제10조의2)
  - path (예: "1/5/1/103/1/2/가") — 정렬/prefix 검색용
  - path_label (예: "제1편제5장제1절제103조제1항제2호가목") — 공식 인용 표기
```

`path_label`은 법제처 공식 표기법 그대로 저장돼 있다. 문제는, 사용자(또는 LLM)가 인용할 때는 최상위 계층을 생략한다는 점이다.

- LLM 출력: `"「민법」 제103조"`
- DB 저장: `"제1편제5장제1절제103조"` (편/장/절까지 풀로)

단순 equality로는 매칭 안 된다. 그래서 `ends_with` 매칭으로 풀었다.

```ruby
def verify_all(entries)
  law_names = entries.map { |e| e[:law_name] }.uniq
  laws_by_name = LegalizeLaw.where(name: law_names).index_by(&:name)

  entries.each do |entry|
    law = laws_by_name[entry[:law_name]]
    next unless law

    latest = law.legalize_versions.effective_order.first
    next unless latest

    # 중요: path_label LIKE '%제103조'
    article_rec = latest.legalize_articles
                        .where("path_label LIKE ?", "%#{entry[:path_label]}")
                        .limit(1)
                        .first

    if article_rec
      entry[:verified] = true
      entry[:legalize_article_id] = article_rec.id
      entry[:full_path_label] = article_rec.path_label
      entry[:law_slug] = law.slug
    end
  end
end
```

`LIKE '%<추출된 인용>'` — trailing match 만 확인한다. "제103조"로 추출됐으면 "제1편제5장제1절제103조"와 매칭된다. "제103조제1항제2호"로 추출됐으면 그 정확한 path만 매칭된다.

이 쿼리는 인덱스 스캔이 안 되는 게 약점이다. `path_label LIKE '%패턴'`은 leading wildcard라서 B-tree 인덱스가 못 쓴다. 하지만 우리의 경우 검증 대상이 latest version 안에서만, 한 번에 최대 10-20개 인용이라 성능 문제는 안 됐다. 만약 전체 테이블 스캔이 느려지면 `path_label` 컬럼에 `reverse()` 인덱스나 별도 역순 컬럼을 만들어 해결할 수 있다.

---

## ChatService 통합 — fallback 호환성을 유지하는 법

CitationExtractor를 ChatService에 끼워넣을 때 주의한 게 하나 있다. 기존 fallback 모드를 깨면 안 됐다.

LLM이 실패하거나 dev 환경에서는 ChatService가 이런 fallback 답변을 돌려준다.

```ruby
def fallback_answer(law:, diff:, ...)
  citations = diff.fetch(:entries, []).first(3).map { |e| e[:path_label] }
  {
    "answer" => "...",
    "citations" => citations  # ["제1조", "제2조", ...]
    # ← 법령명 없이 path_label만
  }
end
```

이 citations는 법령명이 붙어있지 않다. 그냥 `"제1조"` 이런 식. 내 CitationExtractor는 법령명이 필요하니까 이건 추출이 안 된다. 그대로 `enrich_citations`를 돌리면 citations 배열이 **빈 배열**로 대체돼버린다. Request spec이 즉시 깨졌다.

해결은 fallback 호환 로직 추가.

```ruby
def enrich_citations(payload)
  corpus = [payload["answer"], Array(payload["citations"]).join(" ")].compact.join(" ")
  extracted = Legalize::CitationExtractor.extract(corpus)

  citations_override =
    if extracted.any?
      extracted.map { |c| c[:display] }
    else
      Array(payload["citations"])  # ← 추출 실패 시 원본 유지
    end

  payload.merge(
    "citations" => citations_override,
    "verified_citations" => extracted.select { |c| c[:verified] }.map { ... },
    "unverified_citations" => extracted.reject { |c| c[:verified] }.map { ... }
  )
end
```

핵심은 **추출이 하나라도 성공하면 LLM citations를 덮어쓰고, 전부 실패하면 원본 유지**. 그리고 verified/unverified를 별도 필드로 분리해서 프론트가 다르게 렌더할 수 있게 했다.

프론트에서는 이렇게 쓸 수 있다.

```svelte
{#each response.verified_citations as cite}
  <a href="/legalize/{cite.law_slug}?path={cite.path}"
     class="badge-verified">
    ✓ {cite.display}
  </a>
{/each}

{#each response.unverified_citations as cite}
  <span class="badge-unverified" title="DB 에서 찾을 수 없음">
    ⚠ {cite.display}
  </span>
{/each}
```

verified된 건 클릭 가능한 링크로 실제 조문 뷰어로 이동한다. unverified는 회색 + 경고 아이콘으로 "확인 필요" 뱃지. 사용자가 **어떤 인용이 진짜이고 어떤 게 미검증인지 즉시 구분할 수 있다**.

---

## 업계는 어디까지 왔나 — 비교

내 접근은 업계 표준과 비교해서 어디쯤에 있을까. 2025년 논문들과 대조해봤다.

### SelfCheckGPT (EMNLP 2023)
LLM에게 같은 질문을 여러 번 물어보고 답변 간 일관성을 측정한다. 일관성이 낮으면 환각일 가능성 높다. 외부 DB 없이 돌릴 수 있는 black-box 방법이라 범용성이 높다. 하지만 한국어 법령처럼 **정확한 ground truth가 있는 도메인**에서는 과잉이다. 우리는 DB가 있으니 직접 조회하면 된다.

### REFIND (SemEval 2025)
Span-level verification. 생성된 각 주장을 retrieved evidence와 매칭한다. 매칭 안 되면 환각 플래그. 개념적으로는 내 방식과 동일하다. 차이는 REFIND가 일반 텍스트 대상이고 내 건 법령 전용이라는 점. **도메인 특화 덕에 정규식 기반으로도 높은 정확도**가 나온다.

### INRA.AI 6-layer validation
- Real-time source retrieval (PubMed, arXiv, Semantic Scholar)
- Context annotation
- LLM constraints ("cite only from these papers")
- Real-time validation during generation
- Post-generation cleaning
- Complete audit trails

이게 학술 문헌 검색 도구의 업계 최고 수준이다. 환각률 0.1% 미만. 내 접근은 이 중 4번(real-time validation)과 5번(post-generation cleaning)에 해당한다. 나머지 단계는 기존 서비스에 이미 있었다. 법률 도메인은 학술 문헌보다 훨씬 구조화된 편이어서 **정규식 기반 6번만 덧붙여도 유사한 효과**를 낸다.

### Citation-Grounded Code Comprehension (arxiv 2512.12117, 2025)
BM25 + BGE 임베딩 + Neo4j 그래프 + mechanical citation verification. 코드 레포지토리 대상. 여기서 재미있는 건 **"mechanical citation verification"**이라는 용어다. LLM이 `[file.py:100-110]` 식으로 인용하면 interval arithmetic으로 실제 retrieved chunk와 겹치는지 확인한다. 92% 인용 정확도, **0% 환각 달성**.

내 `path_label LIKE '%...'` 검증이 정확히 같은 철학이다. LLM 출력을 기계적으로 검증 가능한 형식으로 가두고, 검증 실패하는 건 플래그.

**공통 원칙**: "LLM이 citation을 지어낼 거라고 가정하고 시스템을 설계하라."

---

## 프로덕션 적용 전 체크리스트

이 패턴을 다른 도메인에 적용하려는 사람을 위한 체크리스트.

### 1. 인용 대상이 구조화되어 있는가
법령, 판례, 학술 논문, 코드 라인처럼 **명확한 식별자가 있는 대상**이어야 기계적 검증이 가능하다. "어제 뉴스 기사" 같은 애매한 대상은 안 된다.

### 2. 정확한 표기 규칙이 있는가
법령은 "제N조제N항제N호" 같은 공식 표기가 있다. 학술 논문은 DOI + 저자/연도. 코드는 파일:라인. 표기 규칙이 없으면 정규식으로 못 뽑는다.

### 3. DB/인덱스가 있는가
검증 단계에서 O(1) 또는 O(log n) 조회가 가능해야 한다. 전수 조회는 답변 지연을 악화시킨다. 내 경우 `path_label`이 `LIKE` 패턴이라 인덱스가 부분적으로만 먹는데, 법령당 수백-수천 노드 규모에서는 충분했다.

### 4. UI가 verified/unverified를 분리 표시할 수 있는가
검증 기능을 만들어도 UI가 이 정보를 사용하지 않으면 무의미하다. 사용자에게 **명시적으로** "이건 검증됨, 저건 미검증" 뱃지를 보여줘야 한다. 숨기면 검증 자체를 왜 했는지 모르게 된다.

### 5. Fallback 호환성
LLM이 실패해도 동작해야 한다. 내 경우 정규식 추출 실패 시 원본 citations 배열 유지로 해결했다.

---

## 성능과 비용

이 검증을 매 응답에 추가하면 얼마나 느려지나? 내 환경 기준 측정값.

| 단계 | 시간 |
|---|---|
| 정규식 scan (응답 1-2KB) | < 1ms |
| DB 조회 (법령 5개 × `LIKE` 쿼리 1회씩) | 5-10ms |
| 전체 verify_all | ~15ms |

LLM 응답 자체가 1-5초 걸리는 것에 비하면 0.3% 미만 오버헤드다. 무시해도 된다.

비용 관점에서는 **비용 절감 효과**가 있다. 환각된 citation을 사용자가 클릭해서 404 맞는 순간 신뢰가 무너진다. 그 사용자를 다시 데려오는 비용이 검증 구현 비용보다 훨씬 크다. 법률 도메인에서는 환각 한 번이 법적 책임 문제로 번질 수 있으니 ROI는 사실상 무한대다.

---

## 남은 숙제

지금 버전에서 아직 해결 못 한 것들.

### 1. 크로스 법령 참조 검증
"이 민법 조항이 시행령 제N조와 충돌한다" 같은 답변에서 시행령 조문까지 검증하려면 별도 처리가 필요하다. 현재는 단일 법령 기준.

### 2. 삭제된 조문 대응
법령 개정 이력 중간에 삭제된 조문이 있을 수 있다. "제N조 삭제 <2024.12.31>" 같은 케이스. 현재는 latest version만 검증하므로 과거 시점 인용은 verified=false가 된다. 역사적 인용을 지원하려면 version별로 검증해야 한다.

### 3. 유사 표기 허용
"민법 103조" (제 생략) 같은 비공식 표기가 실제 사용자 질의에서 자주 나온다. 현재는 `제\d+조` 요구라서 놓친다. fuzzy matching 추가 고려 중.

### 4. LLM 프롬프트 개선
LLM에게 "인용할 때는 반드시 「」 낫표를 쓰고 공식 표기를 따르라"는 시스템 프롬프트 강화하면 추출 성공률이 올라간다. 현재는 이 부분 아직 반영 안 함.

---

## 결론: LLM을 믿지 말고 출력을 검증하라

이번 작업의 교훈을 한 줄로 요약하면 이거다.

**"LLM이 뭐라고 하든 출력의 사실성은 시스템이 보증해야 한다."**

GPT-5가 GPT-4보다 환각이 줄어든 건 맞지만, 7-8%는 여전히 프로덕션에서 용납할 수 없는 수치다. 그리고 이 비율은 **모델이 좋아져도 0으로 수렴하지 않는다**. 근본적으로 확률적 생성 모델의 한계다.

해결책은 모델을 더 기다리는 게 아니라 **아키텍처로 가두는** 것이다. 인용이 명확하게 식별 가능한 도메인이면 정규식 + DB 검증 같은 기계적 접근으로 충분히 0%에 가까운 환각률을 낼 수 있다. 구현 자체는 몇백 줄 코드다.

법률 AI를 만드는 사람은 이 부분을 절대 LLM에게 맡기지 말기를 바란다. Mata v. Avianca 변호사처럼 되지 않으려면 **자기 시스템이 사실을 보증해야 한다**.

작업 중 남긴 삽질 로그와 정규식 패턴은 공개 저장소에 올려둘 예정이고, 다른 도메인(학술 논문, 코드, 의료 가이드라인)에서도 동일한 패턴이 통한다고 생각한다. 시행착오 없이 건너뛰고 싶은 사람에게 도움이 되길.
