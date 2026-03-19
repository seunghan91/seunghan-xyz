---
title: "[개발일기] Rails 8로 AI 에이전트 리뷰 시스템 만들면서 삽질한 이야기"
date: 2026-03-12
draft: false
tags: ["Rails 8", "AI", "바이브코딩", "LLM", "아키텍처", "삽질기"]
description: "Rails 8로 AI 멀티 에이전트 리뷰 시스템을 만들면서 겪은 삽질들. 에이전트 톤 설계, JSONB 활용 패턴, 보조 에이전트 아키텍처, Knowledge Graph 시점별 필터링, 인터랙티브 가이드 페이지까지."
cover:
  image: "https://images.unsplash.com/photo-1555949963-aa79dcee981c?w=800&h=600&fit=crop"
  alt: "AI 에이전트 개발 과정"
  hidden: true
slug: "rails-ai-agent-dev-diary"
---

AI가 글을 검수해주는 시스템을 Rails 8로 만들고 있다. 4개의 AI 에이전트가 각자 관점에서 원고를 분석하고, 스토리 데이터베이스와 연동해서 일관성까지 체크하는 구조.

만들면서 꽤 많이 삽질했는데, 기록 안 해두면 까먹을 것 같아서 정리해본다.

---

## 1. AI 에이전트의 "톤"이 이렇게 중요할 줄이야

처음엔 에이전트 프롬프트를 이렇게 썼다:

```
당신은 편집 보조자입니다. 원고를 분석하고 문제점을 지적하세요.
```

테스트 유저한테 피드백을 받았는데, **"이건 도움이 아니라 채점이다"**라는 반응이 돌아왔다.

창작하는 사람 입장에서 "지적" 톤은 부담스럽다는 거였다. 업계 리서치를 해보니까 Sudowrite, NovelAI 같은 도구들도 **"동료"** 톤이 압도적으로 선호된다고 한다.

그래서 4개 에이전트 전부 톤을 바꿨다:

```ruby
# Before
SYSTEM_PROMPT = "당신은 편집 보조자입니다."

# After
SYSTEM_PROMPT = "당신은 함께 원고를 검토하는 동료 작가입니다."
```

프롬프트에도 구체적인 톤 가이드를 추가했다:

```
- "~해야 합니다" 대신 "~하면 어떨까요? 왜냐하면..." 식으로 제안하세요
- 대담한 해석도 시도하되 근거를 함께 제시하세요
```

UI에서도 점수를 **"내부 참고 지표"**로 격하시키고, 서브타이틀을 "동료 작가 4명이 각자 관점에서 관찰하고 제안한 내용입니다"로 바꿨다.

**교훈**: AI 톤은 기능이 아니라 UX다. 같은 내용이라도 톤에 따라 사용자가 받아들이는 방식이 완전히 달라진다.

---

## 2. JSONB 하나로 마이그레이션 없이 기능 추가하기

캐릭터에 "능력", "현재 목표", "약점", "성격" 필드를 추가해야 했다. 보통이면 마이그레이션 파일 만들고 컬럼 추가하겠지만, 이미 `properties`라는 JSONB 컬럼이 있었다.

```ruby
# 새 마이그레이션 없이 기존 JSONB 활용
TRAIT_KEYS = %w[abilities current_goal weakness personality].freeze

TRAIT_KEYS.each do |key|
  define_method(key) { properties&.dig(key) }
  define_method(:"#{key}=") { |val| self.properties = (properties || {}).merge(key => val) }
end

def traits_present?
  TRAIT_KEYS.any? { |k| properties&.dig(k).present? }
end
```

이 패턴의 장점:
- **마이그레이션 제로**: DB 스키마 변경 없음
- **확장 용이**: `TRAIT_KEYS`에 문자열 하나 추가하면 끝
- **하위 호환**: 기존 데이터에 영향 없음

**단점도 있다**:
- DB 레벨 인덱싱이 안 됨 (성능 이슈 가능)
- 타입 검증이 애플리케이션 레벨에서만 가능

작은 프로젝트에서는 이게 훨씬 빠르다. 나중에 스케일 이슈 생기면 그때 정규 컬럼으로 옮기면 된다.

---

## 3. 5번째 에이전트를 추가할 때 — "보조 에이전트" 패턴

4개 에이전트가 이미 점수 가중치를 나눠갖고 있는 상태에서, 5번째 에이전트를 추가해야 했다. 복선/인과관계를 감지하는 에이전트.

문제는 이 에이전트가 실패해도 기존 4개 에이전트의 점수에 영향을 주면 안 된다는 것.

```ruby
# 핵심 에이전트 (점수에 반영)
AGENTS = {
  commercial: Agents::CommercialAgent,
  storytelling: Agents::StorytellingAgent,
  consistency: Agents::ConsistencyAgent,
  fact_check: Agents::FactCheckAgent
}.freeze

# 보조 에이전트 (실패해도 핵심 결과에 영향 없음)
SUPPLEMENTARY_AGENTS = {
  plot_thread_detection: Agents::PlotThreadDetectionAgent
}.freeze
```

보조 에이전트는 별도 메서드에서 실행하고, 실패 시 `nil`을 반환한다 (핵심 에이전트는 `FAILED_RESULT`를 반환):

```ruby
def run_supplementary_agents(bible, agent_metadata)
  SUPPLEMENTARY_AGENTS.to_h do |key, klass|
    # ... 실행 로직
    if outcome.success?
      [key, outcome.value!]
    else
      [key, nil]  # nil이지 FAILED_RESULT가 아님
    end
  rescue StandardError => e
    [key, nil]  # 예외도 조용히 처리
  end
end
```

이 패턴 덕분에:
- 보조 에이전트를 얼마든지 추가 가능
- 기존 점수 계산 로직 변경 불필요
- 보조 에이전트 실패가 전체 리뷰를 망치지 않음

**교훈**: 새 기능이 기존 시스템의 안정성을 위협할 때, "보조" 레이어로 분리하는 게 가장 안전하다.

---

## 4. Dry::Validation으로 AI 응답 검증하기

AI가 항상 기대한 JSON 구조를 반환하는 건 아니다. Claude든 GPT든 가끔 필드를 빼먹거나 타입을 틀린다.

각 에이전트마다 Contract를 만들어서 응답을 검증한다:

```ruby
class PlotThreadResponseContract < Dry::Validation::Contract
  json do
    required(:detected_threads).array(:hash) do
      required(:type).filled(:string)
      required(:source_entity).filled(:string)
      required(:target_entity).filled(:string)
      required(:confidence).filled(:float, gteq?: 0.0, lteq?: 1.0)
      required(:thread_scope).filled(:string, included_in?: %w[short_term mid_term long_term])
    end
    optional(:resolution_candidates).array(:hash)
    optional(:density_warning).maybe(:string)
  end
end
```

BaseAgent에서 공통으로 처리:

```ruby
def evaluate(content, context: {})
  raw = call_llm(content, context)
  parsed = JSON.parse(raw)
  result = contract.call(parsed)

  if result.success?
    Success(result.to_h)
  else
    Failure(errors: result.errors.to_h)
  end
end
```

**교훈**: AI 응답은 외부 입력이다. 사용자 입력을 검증하듯이 AI 응답도 반드시 검증해야 한다. Dry::Validation이 이 용도로 딱 맞는다.

---

## 5. Knowledge Graph에서 "시점별 관계도" 구현

스토리 데이터베이스의 관계도를 시각화하는데, 단순히 전체 관계를 보여주는 건 의미가 없었다. "3화 시점에서 주인공이 알고 있는 관계"를 보여줘야 했다.

핵심은 `valid_from_chapter`와 `valid_until_chapter` 필터링:

```ruby
# 특정 시점까지의 관계만 조회
edges = LoreEdge
  .where(source_node_id: node_ids)
  .where("valid_from_chapter <= ?", chapter_position)
  .where("valid_until_chapter IS NULL OR valid_until_chapter >= ?", chapter_position)
```

관계 종류도 4가지로 분류했다:

```ruby
EDGE_TYPES = %w[relationship foreshadowing resolution cause_effect].freeze

# 한국어 라벨
EDGE_TYPE_LABELS = {
  "relationship" => "관계",
  "foreshadowing" => "복선",
  "resolution" => "회수",
  "cause_effect" => "인과"
}.freeze
```

타임라인 뷰에서는 복선/회수를 별도 섹션으로 분리해서 보여준다. 미회수 복선은 AI 컨텍스트에도 포함시켜서 "이 복선 아직 안 풀렸는데요?"라고 알려줄 수 있게 했다.

**교훈**: 시점(temporal) 필터링은 단순해 보이지만, "어디까지가 이 시점의 정보인가"를 정의하는 게 까다롭다. `valid_from`/`valid_until` 패턴이 가장 직관적이었다.

---

## 6. 스토리 데이터 중요도 정렬 알고리즘

스토리 데이터베이스에 항목이 쌓이면, AI한테 전부 넘기면 토큰 낭비다. 중요한 것부터 정렬해서 컨텍스트 한도 내에서 전달해야 한다.

```ruby
def importance_score(node)
  base = node.lore_edges.count * 12                    # 관계 많을수록 중요
  base += category_bonus(node.category)                  # 캐릭터 > 사건 > 장소
  base += recency_bonus(node, @chapter_position)         # 최근 등장 보너스
  base
end
```

중요도 등급도 만들었다:

| 점수 | 등급 | 의미 |
|------|------|------|
| 40+ | 핵심 | 스토리의 중심 요소 |
| 28+ | 주요 | 자주 등장하는 요소 |
| 16+ | 보조 | 가끔 등장 |
| 0+ | 기록 | 언급만 된 수준 |

이걸 AI 컨텍스트에도 동일하게 적용해서, 2500자 한도 내에서 핵심부터 채운다.

**교훈**: AI한테 "다 알려주기"보다 "중요한 것부터 알려주기"가 훨씬 결과가 좋다. 사람도 마찬가지 아닌가.

---

## 7. 글자수 색상 구간 — 사소하지만 중요한 UX

웹소설 플랫폼마다 권장 글자수가 다르다. 카카오페이지는 4,500자, 문피아는 5,000자 정도.

글자수에 따라 색상을 바꿔주는 헬퍼를 만들었다:

```ruby
def word_count_color_class(count)
  case count
  when 0...4500    then "error"      # 빨강 — 너무 짧음
  when 4500...5000 then "warning"    # 주황 — 조금 더
  when 5000...5500 then "success"    # 초록 — 적정
  when 5500...6000 then "info"       # 남색 — 충분
  else                  "overflow"   # 노랑 — 길 수 있음
  end
end
```

사소해 보이지만 실제 사용자는 이런 시각적 피드백에 가장 먼저 반응했다. "글자수가 색으로 바뀌니까 직관적이다"라는 피드백.

**교훈**: 화려한 AI 기능보다 색상 하나가 더 체감될 수 있다.

---

## 8. localStorage로 인터랙티브 가이드 만들기

첫 사용자가 기능을 이해할 수 있도록 10단계 워크스루 가이드를 만들었다. 서버사이드 변경 없이 Stimulus.js + localStorage만으로 구현.

```javascript
// Stimulus 컨트롤러
export default class extends Controller {
  static targets = ["step", "sidebar", "progress"]

  connect() {
    this.currentStep = parseInt(localStorage.getItem("guide_step") || "0")
    this.maxVisited = parseInt(localStorage.getItem("guide_max") || "0")
    this.showStep(this.currentStep)
  }

  next() {
    if (this.currentStep < this.totalSteps - 1) {
      this.currentStep++
      this.maxVisited = Math.max(this.maxVisited, this.currentStep)
      this.persist()
      this.showStep(this.currentStep)
    }
  }

  persist() {
    localStorage.setItem("guide_step", this.currentStep)
    localStorage.setItem("guide_max", this.maxVisited)
  }
}
```

DB 테이블 안 만들고도 진행 상태를 추적할 수 있다. 물론 기기 간 동기화는 안 되지만, 가이드 진행 상태 정도는 이걸로 충분하다.

---

## 9. AI 자동 추출 — 이중 안전장치 패턴

AI가 원고에서 캐릭터 특성 변화를 자동 추출하는 기능을 만들었다. 핵심은 **이 기능이 실패해도 다른 기능에 영향을 주면 안 된다**는 것.

```ruby
# Job 레벨 — 첫 번째 안전장치
class ExtractLoreJob < ApplicationJob
  def perform(chapter)
    # 1. 핵심 추출 (실패하면 전체 실패)
    extraction = LoreExtractionService.new(chapter).extract!

    # 2. 특성 추출 (실패해도 핵심 추출은 보존)
    begin
      traits = TraitExtractionService.new(chapter, chapter.project).extract
      extraction.payload["trait_updates"] = traits if traits.any?
      extraction.save!
    rescue => e
      Rails.logger.error("[TraitExtraction] #{e.message}")
      # 조용히 넘어감 — 핵심 추출은 이미 완료
    end
  end
end
```

```ruby
# Service 레벨 — 두 번째 안전장치
class TraitExtractionService
  def extract
    return [] if @characters.empty?
    # ... AI 호출
  rescue StandardError => e
    Rails.logger.error("[TraitExtractionService] #{e.message}")
    []  # 빈 배열 반환, 절대 예외를 던지지 않음
  end
end
```

승인 단계에서도 confidence threshold(0.5)로 한 번 더 필터링:

```ruby
def apply_trait_updates!
  trait_updates.each do |update|
    next if update["confidence"].to_f < 0.5  # 확신도 낮으면 스킵
    # ...
  end
end
```

**교훈**: AI 기반 자동화 기능은 3중 안전장치가 기본이다. 서비스 레벨 rescue → Job 레벨 rescue → 승인 시 threshold.

---

## 10. 전체 아키텍처 회고

```
사용자 원고 입력
    ↓
ReviewOrchestrator
    ├── 핵심 에이전트 4개 (병렬 실행, 점수 반영)
    │   ├── 상업성 에이전트
    │   ├── 스토리텔링 에이전트
    │   ├── 개연성 에이전트 ← StoryBibleContext 주입
    │   └── 고증 에이전트
    ├── 보조 에이전트 (실패 허용)
    │   └── 복선 감지 에이전트
    └── 결과 집계 + 메타데이터

별도 파이프라인:
    원고 → LoreExtractionService → 엔티티/관계 추출
         → TraitExtractionService → 캐릭터 특성 변화 추출
         → 사용자 승인 → StoryBible 반영
```

Rails 8이 이런 시스템에 잘 맞는 이유:
- **ActiveJob**: 비동기 AI 호출에 딱
- **JSONB**: 유연한 스키마로 빠른 반복
- **Convention over Configuration**: 보일러플레이트 최소화
- **ViewComponent + Stimulus**: 서버 사이드 렌더링 + 필요한 곳만 인터랙티브

가장 큰 배움은 **AI 기능은 "실패 허용"이 기본**이어야 한다는 것. AI 응답은 불확실하고, 네트워크는 불안정하고, 비용도 든다. 핵심 흐름이 AI 실패 때문에 멈추면 안 된다.

---

## 마무리

한 줄 요약하면: **AI를 쓰는 시스템은 "AI가 실패해도 괜찮은" 구조를 먼저 만들어야 한다.**

기능을 하나씩 쌓으면서 느낀 건, 화려한 AI 기능보다 "어떤 톤으로 말하느냐", "글자수 색상이 바뀌느냐" 같은 사소한 UX가 실제 사용자 반응에 더 큰 영향을 준다는 것.

다음엔 AI가 자동으로 복선을 감지하고 회수 시점을 제안하는 기능을 만들 예정이다. 데이터가 쌓이면 가능해질 것 같다.
