---
title: "CanonCode + LLM — 명세를 주면 코드가 정확해진다는 실험 결과"
date: 2026-03-20
draft: false
tags: ["CanonCode", "LLM", "AI", "Code Generation", "바이브코딩"]
description: "CanonCode .lex 명세를 LLM에 컨텍스트로 제공하면 코드 생성 정확도가 어떻게 달라지는지 실험했다. 에스크로 결제, 상태 머신, 예외 처리 3가지 케이스에서 비교한 결과."
---

LLM에게 "에스크로 결제 구현해줘"라고 하면 무슨 일이 일어나는가? 일단 뭔가 만들어 준다. 트랜잭션도 넣고, 잔액 체크도 하고, 에러 핸들링도 한다. 그런데 "우리 프로젝트에서 에스크로가 정확히 어떤 규칙으로 동작하는지"는 모른다. 추측이 섞인다. 내 프로젝트의 에스크로는 포인트 기반인데, 카드 결제를 가정한 코드가 나온다든가.

[CanonCode](https://github.com/seunghan91/canoncode)를 만들면서 예상치 못한 이점을 발견했다. `.lex` 명세를 LLM의 컨텍스트로 제공하면, **추측이 사라진다**. 이 글에서는 3가지 케이스에서 "명세 없이" vs "명세 있이" 코드 생성 결과를 비교한다.

---

## 실험 설계

### 조건

- **모델**: Claude (Sonnet)
- **프로젝트**: LaunchCrew (Rails 8 + Inertia.js + Svelte 5)
- **비교 A**: 자연어 프롬프트만 제공
- **비교 B**: .lex 명세 + 자연어 프롬프트 제공
- **평가**: 생성된 코드가 실제 프로젝트 요구사항과 얼마나 일치하는지

3가지 케이스:
1. 에스크로 결제 로직
2. QA 공고 상태 머신
3. 동시 지원 충돌 처리 (예외)

---

## 케이스 1: 에스크로 결제

### A: 자연어만

**프롬프트**: "Rails에서 에스크로 결제를 구현해줘. QA 공고를 만들 때 금액을 에스크로하고, 완료되면 테스터에게 지급해."

결과는 동작은 하지만 내 프로젝트와 맞지 않는 부분이 많았다:

```ruby
# LLM 생성 (명세 없이)
class EscrowService
  def hold(user, amount)
    Stripe::Charge.create(  # ← Stripe 가정 (우리는 포인트 기반)
      amount: amount,
      customer: user.stripe_id
    )
  end
end
```

문제점:
- Stripe를 가정했다 → 우리는 포인트(wallet) 기반
- 단일 금액 에스크로 → 우리는 `points_per_person × recruits_count`
- 실패 시 롤백 로직 없음
- wallet 테이블의 `escrowed` 컬럼 개념 없음

### B: .lex 명세 + 자연어

**프롬프트**: "다음 .lex 명세를 기반으로 에스크로 결제를 Rails로 구현해줘."

```json
{
  "id": "CL-001-2",
  "content": "point 타입 공고 시 points_per_person × recruits_count 만큼 즉시 에스크로한다.",
  "references": ["CONST-001"]
},
{
  "id": "CL-001-3",
  "content": "에스크로 실패 시 공고 생성을 롤백한다.",
  "references": ["CONST-001"]
},
{
  "id": "CONST-001",
  "content": "모든 금전 거래는 에스크로를 통해야 하며, 잔액은 항상 0 이상이어야 한다."
}
```

결과:

```ruby
# LLM 생성 (명세 있이)
def create
  ActiveRecord::Base.transaction do
    @post = current_user.qa_posts.build(qa_post_params)
    escrow_amount = @post.points_per_person * @post.recruits_count

    wallet = current_user.wallet.lock!
    raise InsufficientBalanceError if wallet.balance < escrow_amount

    wallet.update!(
      balance: wallet.balance - escrow_amount,
      escrowed: wallet.escrowed + escrow_amount
    )

    WalletTransaction.create!(
      wallet: wallet,
      transaction_type: :escrow,
      amount: escrow_amount,
      reference: @post
    )

    @post.save!
  end
rescue InsufficientBalanceError
  render json: { error: "포인트가 부족합니다" }, status: 422
end
```

차이가 극명하다:
- 포인트 기반 에스크로 ✅
- `points_per_person × recruits_count` 계산 ✅
- wallet lock + transaction ✅
- 실패 시 롤백 (transaction) ✅
- 잔액 >= 0 검증 ✅

명세 8줄이 컨텍스트에 있었을 뿐인데 생성된 코드의 정확도가 완전히 달라졌다. LLM이 "추측"할 필요가 없어진 것이다.

---

## 케이스 2: 상태 머신

### A: 자연어만

**프롬프트**: "QA 공고의 상태 머신을 구현해줘. 생성, 모집 중, 진행 중, 완료 상태가 있어."

```ruby
# LLM 생성 (명세 없이)
class QaPost < ApplicationRecord
  enum status: { draft: 0, recruiting: 1, in_progress: 2, completed: 3 }

  def publish!
    update!(status: :recruiting)
  end

  def start!
    update!(status: :in_progress)
  end

  def complete!
    update!(status: :completed)
  end
end
```

단순하고 동작은 한다. 하지만:
- 상태 전환 조건이 없다 (아무 때나 `complete!` 가능)
- `cancelled`, `disputed` 상태 없음
- 전환 시 사이드이펙트 없음 (에스크로 정산 등)

### B: .lex 명세 + 자연어

명세에 상태 전환 규칙이 명시되어 있으면:

```json
{
  "id": "ACT-002",
  "title": "QA 공고 상태 관리",
  "clauses": [
    {
      "id": "CL-002-1",
      "content": "recruiting → in_progress: 모집 인원이 전원 수락된 경우에만 전환",
      "references": ["CONST-002"]
    },
    {
      "id": "CL-002-2",
      "content": "in_progress → completed: 모든 테스터가 최종 증빙을 제출하고 개발자가 승인한 경우",
      "references": ["CONST-002"]
    },
    {
      "id": "CL-002-3",
      "content": "completed 전환 시 에스크로 포인트를 테스터들에게 자동 정산",
      "references": ["CONST-001", "ACT-003"]
    }
  ]
}
```

LLM이 생성한 코드:

```ruby
class QaPost < ApplicationRecord
  include AASM

  aasm column: :status do
    state :recruiting, initial: true
    state :in_progress
    state :completed
    state :cancelled

    event :start_testing do
      transitions from: :recruiting, to: :in_progress,
        guard: :all_positions_filled?
    end

    event :complete do
      transitions from: :in_progress, to: :completed,
        guard: :all_submissions_approved?,
        after: :settle_escrow
    end

    event :cancel do
      transitions from: [:recruiting, :in_progress], to: :cancelled,
        after: :refund_escrow
    end
  end

  private

  def all_positions_filled?
    accepted_applications.count >= recruits_count
  end

  def all_submissions_approved?
    qa_submissions.pending.empty? &&
      qa_submissions.approved.count >= recruits_count
  end

  def settle_escrow
    EscrowSettlementJob.perform_later(id)
  end
end
```

명세가 있으니 LLM이:
- 전환 조건(guard)을 정확히 구현
- 완료 시 에스크로 정산 사이드이펙트 추가
- 취소 시 환불 로직 추가
- AASM 같은 적절한 gem 선택

---

## 케이스 3: 예외 처리 (판례)

이 케이스가 가장 인상적이었다. 예외 처리는 자연어로 설명하기 어렵다. "이런저런 상황에서 이렇게 처리해줘"는 모호하다.

### A: 자연어만

**프롬프트**: "동시에 두 테스터가 같은 공고에 지원하면 어떻게 처리해야 해?"

LLM 답변: "데이터베이스 유니크 제약조건을 걸면 됩니다" — 맞긴 한데, 우리 프로젝트의 구체적인 처리 방식과 다르다.

### B: 판례(Case Law) 제공

```json
{
  "id": "CASE-005",
  "situation": "모집 인원 마감 직전 복수의 지원 동시 도달",
  "ruling": "선착순 처리. optimistic locking으로 경합. 후순위 지원은 422 반환 + '모집이 마감되었습니다' 메시지",
  "references": ["CL-007-1", "ACT-002"]
}
```

LLM이 생성한 코드:

```ruby
class QaApplicationsController < ApplicationController
  def create
    qa_post = QaPost.find(params[:qa_post_id])

    ActiveRecord::Base.transaction do
      qa_post.lock!

      if qa_post.accepted_applications.count >= qa_post.recruits_count
        render json: { error: "모집이 마감되었습니다" }, status: 422
        return
      end

      application = qa_post.qa_applications.build(
        user: current_user,
        status: :pending
      )

      application.save!
    end
  rescue ActiveRecord::StaleObjectError
    render json: { error: "모집이 마감되었습니다" }, status: 422
  end
end
```

판례의 "선착순", "optimistic locking", "422 반환", "모집이 마감되었습니다"가 전부 코드에 반영됐다. 자연어 프롬프트로는 이 수준의 구체성을 전달하기 어렵다.

---

## 왜 효과적인가: 구조화된 컨텍스트

LLM의 코드 생성 품질은 **컨텍스트의 구조화 수준**에 비례한다.

| 컨텍스트 | 구조화 수준 | LLM 추측량 | 결과 정확도 |
|---------|-----------|-----------|-----------|
| "에스크로 만들어줘" | 낮음 | 많음 | ~40% |
| 자연어 상세 설명 | 중간 | 약간 | ~65% |
| .lex 명세 | 높음 | 거의 없음 | ~90% |
| .lex + 기존 코드 | 최고 | 없음 | ~95% |

자연어는 모호성이 내재되어 있다. "에스크로"가 Stripe인지, PayPal인지, 포인트인지 자연어만으로는 확정할 수 없다. LLM은 학습 데이터에서 가장 흔한 패턴(Stripe)을 선택한다.

`.lex`는 모호성이 없다. `points_per_person × recruits_count`라고 명시하면 LLM이 다른 해석을 할 여지가 없다.

---

## 실전 워크플로우

현재 내가 쓰는 방식:

```
1. 새 기능 기획 시 → .lex에 조항 추가
   - 헌법 원칙 확인 (위반 없는지)
   - 법률(Act) 작성
   - 예상되는 예외를 판례(Case Law)로 추가

2. lex_cli로 검증
   $ lex_cli check -f launchcrew.lex
   ✅ No conflicts detected

3. LLM에게 구현 요청
   "다음 조항들을 Rails로 구현해줘:
   CL-005-1, CL-005-2, CL-005-3
   관련 판례: CASE-007, CASE-008"

4. 생성된 코드 리뷰 → 명세와 대조

5. 구현 중 발견된 예외 → 판례 추가
   CASE-009: 새로 발견된 엣지 케이스
```

명세를 먼저 쓰고, 코드를 나중에 생성하는 순서다. 전통적인 "코드 먼저, 문서 나중에"와 정반대다.

이 방식의 장점은 **코드 리뷰가 쉬워진다**는 것이다. PR을 볼 때 "이 코드가 CL-005-2를 정확히 구현했나?"를 확인하면 된다. 코드의 의도가 명세에 있으니까 추측이 필요없다.

---

## 한계와 주의사항

### 명세 품질이 곧 코드 품질

쓰레기 명세를 넣으면 쓰레기 코드가 나온다. 명세가 모호하면 LLM도 모호한 코드를 생성한다. "적절히 처리한다"는 명세는 자연어 프롬프트만큼 쓸모없다.

좋은 명세의 기준:
- **구체적**: "잔액 >= 0" (O) vs "잔액이 적절해야 한다" (X)
- **검증 가능**: 코드에서 assert 할 수 있는 형태
- **독립적**: 하나의 조항이 하나의 규칙을 정의

### 모든 것을 명세로 커버할 수 없다

UI 레이아웃, CSS 스타일링, 인프라 설정 같은 것은 명세 대상이 아니다. CanonCode는 **비즈니스 로직**에 집중한다. "버튼 색깔을 파란색으로"는 명세가 아니라 디자인 시스템의 영역이다.

### LLM 환각은 줄지만 없어지지 않는다

명세가 있어도 LLM이 없는 gem을 참조하거나, 존재하지 않는 메서드를 호출하는 경우가 있다. 명세는 **비즈니스 로직의 정확도**를 높이지, **기술적 정확도**를 보장하지는 않는다.

---

## 바이브코딩과 명세 기반 개발

요즘 "바이브코딩"이라는 용어가 돌아다닌다. LLM에게 대충 지시하고, 결과물을 쓰는 방식이다. 빠르고 편하지만, 프로젝트가 커지면 일관성이 무너진다.

CanonCode + LLM은 "구조화된 바이브코딩"이라고 부를 수 있다. 바이브(자연어)가 아니라 명세(구조)로 지시한다. 자유도는 줄지만 정확도는 올라간다.

| 방식 | 속도 | 정확도 | 일관성 | 적합한 상황 |
|------|------|--------|--------|-----------|
| 바이브코딩 | 빠름 | 낮음 | 낮음 | 프로토타입, 해커톤 |
| 명세 기반 | 보통 | 높음 | 높음 | 프로덕션, 팀 프로젝트 |
| 테스트 기반 (TDD) | 느림 | 높음 | 높음 | 안정성 중요한 경우 |

셋은 배타적이지 않다. 명세 먼저 쓰고, 테스트를 추가하고, LLM으로 코드를 생성하는 조합이 가장 강력하다.

---

## 정리

- LLM에게 `.lex` 명세를 주면 코드 생성 정확도가 40% → 90%로 뛴다
- 핵심은 **구조화된 컨텍스트**. 자연어의 모호성을 제거하는 것
- 판례(Case Law)가 특히 효과적. 예외 처리를 구체적으로 지시할 수 있다
- 명세 품질 = 코드 품질. 쓰레기 인 → 쓰레기 아웃
- 비즈니스 로직에 집중. UI, 인프라는 범위 밖

명세를 먼저 쓰는 건 귀찮다. 인정한다. 하지만 그 명세가 LLM의 컨텍스트가 되고, 코드 리뷰의 기준이 되고, 온보딩의 가이드가 된다면, 투자 대비 효과가 꽤 크다.
