---
title: "판례(Case Law)로 예외 처리 설계하기 — CanonCode에서 배운 패턴"
date: 2026-03-21
draft: false
tags: ["CanonCode", "Exception Handling", "Architecture", "Design Pattern", "LaunchCrew"]
description: "CanonCode의 판례(Case Law) 시스템을 활용한 예외 처리 설계 방법론. 실제 LaunchCrew 프로젝트에서 6가지 판례를 작성하고 코드에 적용한 과정을 정리했다."
---

코드에서 가장 무서운 건 `catch` 블록 안에 숨어있는 비즈니스 결정이다. "왜 여기서 422를 반환하지? 500이 아니라?" — 이유를 알려면 git blame → PR → 슬랙 스레드를 거슬러 올라가야 한다. 3개월 전 코드면 작성자 본인도 기억 못 한다.

[CanonCode](https://github.com/seunghan91/canoncode)의 판례(Case Law) 시스템은 이 문제를 정면으로 해결한다. 모든 예외 처리의 "왜"를 구조화된 형식으로 기록하는 것이다. 법원이 판례를 남기듯.

이 글에서는 LaunchCrew 프로젝트에서 작성한 6가지 판례와, 각각이 실제 코드에 어떻게 반영됐는지를 정리한다.

---

## 판례가 왜 필요한가

예외 처리 코드에는 3가지 정보가 필요하다:

1. **어떤 상황**에서 발생하는가 (situation)
2. **어떻게 처리**하는가 (ruling)
3. **왜 그렇게** 처리하는가 (rationale)

일반적인 코드는 2번만 담고 있다:

```ruby
rescue InsufficientBalanceError
  render json: { error: "포인트 충전이 필요합니다" }, status: 422
end
```

1번(어떤 상황)은 메서드 이름이나 주석에서 추측해야 하고, 3번(왜)은 아예 없다. 왜 500이 아니라 422인가? 왜 "충전이 필요합니다"라는 메시지인가? 코드만 봐서는 모른다.

CanonCode의 판례는 세 가지를 모두 기록한다:

```json
{
  "id": "CASE-001",
  "situation": "잔액 부족 상태에서 point 타입 공고 생성 시도",
  "ruling": "422 에러 반환. 공고 생성을 롤백하고 '포인트 충전이 필요합니다' 메시지를 표시한다.",
  "rationale": "500은 서버 오류를 의미하므로 부적절. 잔액 부족은 클라이언트가 해결할 수 있는 상황이므로 422(Unprocessable Entity)가 적합하다.",
  "references": ["CL-001-2", "CONST-001"]
}
```

6개월 뒤에 이 코드를 보는 사람은 판례를 읽으면 된다. git blame할 필요 없다.

---

## 판례 구조

CanonCode의 판례는 법률 시스템의 판결문에서 영감을 받았다.

| 필드 | 법률 비유 | 프로그래밍 비유 |
|------|---------|--------------|
| `id` | 판례 번호 | 고유 식별자 |
| `situation` | 사실 관계 | 예외 발생 조건 |
| `ruling` | 판결 | 예외 처리 방법 |
| `rationale` | 판결 이유 | 왜 이렇게 처리하는지 |
| `references` | 근거 법조문 | 관련 비즈니스 규칙 |

`references`가 중요하다. 판례가 어떤 법률(비즈니스 규칙)에 근거하는지 명시한다. 나중에 그 규칙이 바뀌면, 관련 판례도 업데이트해야 한다는 신호가 된다.

---

## LaunchCrew의 6가지 판례

### CASE-001: 잔액 부족

```json
{
  "id": "CASE-001",
  "situation": "잔액 부족 상태에서 point 타입 공고 생성 시도",
  "ruling": "422 반환. 공고 생성 롤백. '포인트 충전이 필요합니다' 메시지.",
  "rationale": "클라이언트 해결 가능 → 422. 서버 오류가 아님.",
  "references": ["CL-001-2", "CONST-001"]
}
```

코드:
```ruby
rescue InsufficientBalanceError
  render json: { error: "포인트 충전이 필요합니다" }, status: 422
end
```

이건 단순하다. 대부분의 개발자가 직관적으로 이렇게 구현한다. 하지만 판례로 남기면 "왜 422인가"가 영구 기록된다.

### CASE-002: 테스터 중도 포기

```json
{
  "id": "CASE-002",
  "situation": "테스팅 진행 중 테스터가 중도 포기 선언",
  "ruling": "해당 테스터의 에스크로 포인트만 개발자에게 반환. 다른 테스터의 진행에 영향 없음.",
  "rationale": "전체 프로젝트를 중단하면 다른 테스터에게 피해. 부분 반환으로 개발자 손해 최소화.",
  "references": ["ACT-003", "CL-005-3"]
}
```

이 판례가 없었다면 구현자가 결정해야 할 것들:
- 전체 에스크로를 반환할 것인가, 부분만 반환할 것인가?
- 다른 테스터의 진행을 중단할 것인가?
- 포기한 테스터에게 패널티가 있는가?

각각이 비즈니스 결정이다. 코드에서 즉흥적으로 결정하면 일관성이 깨진다.

코드:
```ruby
class QaApplications::WithdrawService
  def call(application)
    ActiveRecord::Base.transaction do
      application.update!(status: :withdrawn)

      # 해당 테스터 에스크로만 반환
      escrow_amount = application.qa_post.points_per_person
      developer_wallet = application.qa_post.user.wallet.lock!
      developer_wallet.update!(
        balance: developer_wallet.balance + escrow_amount,
        escrowed: developer_wallet.escrowed - escrow_amount
      )

      WalletTransaction.create!(
        wallet: developer_wallet,
        transaction_type: :escrow_refund,
        amount: escrow_amount,
        reference: application,
        note: "테스터 중도 포기로 인한 부분 환불"
      )

      # 다른 테스터는 영향 없음 — 아무것도 하지 않음
    end
  end
end
```

"다른 테스터는 영향 없음"이라는 결정이 판례에 있다. 코드에서는 "아무것도 하지 않음"으로 표현되는데, 이건 **의도적인 무행동**이다. 판례 없이는 "여기 뭔가 빠진 거 아닌가?"로 오해할 수 있다.

### CASE-003: 증빙 기한 초과

```json
{
  "id": "CASE-003",
  "situation": "테스터가 일일 증빙 제출 기한(23:59)을 초과",
  "ruling": "해당 일자는 미제출로 기록. 누적 3회 미제출 시 자동 탈락 경고. 5회 시 강제 탈락.",
  "rationale": "1회 초과는 실수일 수 있으므로 즉시 탈락은 가혹. 단 반복 시 프로젝트 품질 보호를 위해 단계적 제재.",
  "references": ["ACT-004", "CL-004-1"]
}
```

이 판례에는 **판결 이유(rationale)**가 핵심이다. "왜 1회 초과에 즉시 탈락이 아닌가?"에 대한 답이 있다. 나중에 정책을 바꾸려면 이 이유를 재검토하면 된다.

### CASE-004: 개발자의 부당한 증빙 거절

```json
{
  "id": "CASE-004",
  "situation": "개발자가 정당한 증빙을 반복적으로 거절하여 테스터가 이의 제기",
  "ruling": "운영팀 중재 프로세스 진입. 중재 기간 동안 에스크로 동결. 운영팀 판단에 따라 강제 승인 또는 분쟁 종결.",
  "rationale": "자동화로 해결할 수 없는 주관적 분쟁. 인간 판단이 필요한 영역.",
  "references": ["CONST-003", "ACT-005"]
}
```

이건 코드로 완전히 구현할 수 없는 판례다. "운영팀 중재"는 수동 프로세스이기 때문이다. 하지만 판례로 남기는 이유는 **시스템이 어디까지 자동화하고 어디서 인간에게 넘기는지**를 명시하기 위해서다.

```ruby
class DisputeService
  def create_dispute(application, reason)
    Dispute.create!(
      qa_application: application,
      reporter: application.user,
      reason: reason,
      status: :pending_mediation  # 운영팀 대기
    )

    # 에스크로 동결 플래그
    application.qa_post.update!(escrow_frozen: true)

    # 운영팀 알림
    AdminNotificationJob.perform_later(:dispute_created, application.id)
  end
end
```

### CASE-005: 동시 지원 충돌

```json
{
  "id": "CASE-005",
  "situation": "모집 인원 마감 직전 복수의 지원 동시 도달",
  "ruling": "선착순 처리. optimistic locking으로 경합. 후순위 지원은 422 반환 + '모집이 마감되었습니다'",
  "rationale": "추첨이나 심사 방식은 UX가 복잡해짐. 선착순이 가장 단순하고 공정함.",
  "references": ["CL-007-1", "ACT-002"]
}
```

이 판례가 실제 디버깅을 도와준 사례는 [이전 글](/posts/canoncode-spec-vs-code/)에서 다뤘다. `lock_version` 누락을 찾는 데 판례가 지도 역할을 했다.

### CASE-006: 결제 시스템 장애

```json
{
  "id": "CASE-006",
  "situation": "외부 결제 시스템(TossPayments) 장애로 카드 결제 실패",
  "ruling": "3회 자동 재시도(exponential backoff: 1초, 3초, 10초). 3회 실패 시 공고 생성 보류 상태로 전환. 사용자에게 '결제 시스템 일시 장애' 알림.",
  "rationale": "일시적 네트워크 장애가 대부분이므로 즉시 실패 처리는 UX 저하. 단 무한 재시도는 시스템 부하 유발.",
  "references": ["CL-001-4", "CONST-004"]
}
```

재시도 횟수, 간격, 실패 시 처리까지 전부 명시한다. 이런 결정은 코드 안에 상수로 박혀있으면 "왜 3회인가? 5회로 바꿔도 되나?"에 대한 답이 없다. 판례에 rationale이 있으면 판단 근거가 된다.

---

## 판례 작성 가이드라인

6개를 쓰면서 정리한 가이드라인:

### 1. situation은 재현 가능하게

나쁜 예: "결제가 안 될 때"
좋은 예: "잔액 부족 상태에서 point 타입 공고 생성 시도"

재현 조건이 명확해야 테스트 케이스로 변환할 수 있다.

### 2. ruling은 검증 가능하게

나쁜 예: "적절히 처리한다"
좋은 예: "422 에러 반환. 공고 생성 롤백. '포인트 충전이 필요합니다' 메시지."

HTTP 상태 코드, 사이드이펙트, 사용자 메시지까지 구체적으로.

### 3. rationale은 반드시 포함

이게 판례의 진짜 가치다. "왜"가 없으면 그냥 주석이다. 주석은 코드 옆에 써도 된다. 판례는 "왜"가 있어야 판례다.

나쁜 예: (rationale 없음)
좋은 예: "1회 초과는 실수일 수 있으므로 즉시 탈락은 가혹. 단 반복 시 프로젝트 품질 보호를 위해 단계적 제재."

### 4. references로 근거 법률을 명시

판례가 어떤 비즈니스 규칙에 기반하는지 연결한다. 나중에 규칙이 바뀌면 관련 판례를 자동으로 찾을 수 있다.

```bash
$ lex_cli tree -f launchcrew.lex --root CONST-001
CONST-001: 모든 금전 거래는 에스크로를 통해야 한다
├── CL-001-2: 즉시 에스크로
├── CASE-001: 잔액 부족 → 422
├── CASE-002: 중도 포기 → 부분 반환
└── CASE-006: 결제 장애 → 재시도 + 보류
```

"에스크로 규칙(CONST-001)을 바꾸면 판례 3개가 영향을 받는다"가 한눈에 보인다.

---

## 판례에서 테스트로

판례의 `situation`과 `ruling`은 사실상 **테스트 케이스의 설명**이다.

```ruby
# CASE-001에서 직접 파생된 테스트
RSpec.describe "CASE-001: 잔액 부족 시 공고 생성" do
  let(:user) { create(:user) }
  let!(:wallet) { create(:wallet, user: user, balance: 100) }

  it "422를 반환하고 공고가 생성되지 않는다" do
    # points_per_person(200) × recruits_count(3) = 600 > balance(100)
    post_params = { points_per_person: 200, recruits_count: 3 }

    expect {
      post "/api/qa_posts", params: post_params
    }.not_to change(QaPost, :count)

    expect(response).to have_http_status(422)
    expect(json_body["error"]).to include("포인트")
  end

  it "잔액이 변하지 않는다 (롤백)" do
    post_params = { points_per_person: 200, recruits_count: 3 }

    expect {
      post "/api/qa_posts", params: post_params
    }.not_to change { wallet.reload.balance }
  end
end
```

판례 → 테스트 변환이 기계적이다. situation이 given, ruling이 then이다. 자동화할 수도 있다.

---

## 판례는 언제 추가하는가

1. **처음부터 예상되는 예외**: 기획 단계에서 식별된 엣지 케이스
2. **실제 버그 발생 시**: 프로덕션에서 발견된 예외 상황
3. **코드 리뷰 중**: "이 경우는 어떻게 되나?"라는 질문이 나왔을 때
4. **정책 변경 시**: 기존 처리 방식을 변경할 때 (이전 판례를 폐기하고 새 판례 추가)

2번이 가장 중요하다. **버그는 판례가 된다**. 한 번 겪은 예외 상황은 다시 겪지 않도록 판례로 남긴다. 이건 법원이 선례를 축적하는 것과 같다.

---

## 정리

| 전통적 방식 | 판례 기반 방식 |
|-----------|-------------|
| 예외 처리가 코드에만 존재 | 판례 + 코드로 이중 기록 |
| "왜"는 git blame에 의존 | rationale이 판례에 명시 |
| 정책 변경 시 영향 범위 불명 | references로 추적 가능 |
| 테스트 케이스 설계 시 상상 | 판례에서 기계적 변환 |
| 온보딩 시 코드 전부 읽기 | 판례 6개 읽으면 핵심 파악 |

예외 처리는 "어떻게"보다 "왜"가 중요하다. `catch` 블록의 코드는 누구나 읽을 수 있다. 하지만 그 코드가 **왜 그런 형태인지**는 코드만 봐서 알 수 없다. 판례는 그 "왜"를 영구 보존하는 시스템이다.

CanonCode의 판례가 완벽한 시스템인 건 아니다. JSON이 장황하고, 관리 비용이 있고, 팀 전체가 써야 효과가 있다. 하지만 "예외 처리에 왜를 기록한다"는 아이디어 자체는 CanonCode 없이도 적용할 수 있다. 주석으로든, ADR(Architecture Decision Record)로든.

중요한 건 **6개월 뒤의 나 자신에게 편지를 쓰는 것**이다. "왜 여기서 422야?"라고 물었을 때 답이 있어야 한다.
