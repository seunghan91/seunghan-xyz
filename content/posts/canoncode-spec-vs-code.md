---
title: "코드 2,800줄을 명세 160줄로 — CanonCode로 실제 프로젝트를 변환해본 결과"
date: 2026-03-18
draft: false
tags: ["CanonCode", "Specification", "Architecture", "Code-as-Law", "LaunchCrew"]
description: "실제 운영 중인 QA 매칭 플랫폼(LaunchCrew)의 핵심 비즈니스 로직을 .lex 명세로 변환해보니, 2,800줄이 160줄로 줄었다. 코드 대신 법률을 유지보수하는 개발 방식에 대한 실험 기록."
cover:
  image: ""
  alt: "CanonCode Spec vs Code"
  hidden: true
---

코드가 커질수록 "이 기능이 왜 이렇게 동작하지?"를 알려면 파일 5개를 열어봐야 한다. 설계 문서는 3개월 전에 작성된 채로 방치되어 있고, 실제 코드와 일치하는지 아무도 모른다.

**만약 설계 문서 자체가 실행 가능하고, 코드 대신 그 문서를 유지보수한다면?**

[CanonCode](https://github.com/seunghan91/canoncode)라는 사이드 프로젝트에서 이 아이디어를 실험해봤다.

---

## 아이디어: 법률 체계로 소프트웨어를 거버넌스한다

법률 시스템에서 영감을 받았다:

| 법률 | 소프트웨어 |
|------|-----------|
| 헌법 | 프로젝트 원칙 (모바일 퍼스트, 오프라인 지원 등) |
| 법률(Acts) | 기능 아키텍처 (QA 공고 생성, 결제 플로우) |
| 규칙(Rules) | 상호작용 로직 (유효성 검사, 상태 전환) |
| 부칙(Appendices) | 데이터 스키마, API 명세 |
| 판례(Case Law) | 예외 처리 (잔액 부족, 동시 결제 충돌) |

하위 법률은 상위 법률과 모순될 수 없다. CanonCode의 린터가 자동으로 위반을 감지한다.

---

## 실험 대상: LaunchCrew

[LaunchCrew](https://github.com/seunghan91/launchcrew)는 내가 만들고 있는 C2C QA 매칭 플랫폼이다:

- 개발자(Maker)가 QA 공고를 올림
- 테스터(Hunter)가 지원 → 수락 → 매일 테스팅 증빙 제출
- 완료 시 에스크로된 포인트가 자동 지급

기술 스택: Rails 8 + Inertia.js + Svelte 5 + Flutter

핵심 비즈니스 로직이 모델, 컨트롤러, 서비스, UI 컴포넌트에 걸쳐 **40개 이상의 파일, 2,800줄 이상**에 분산되어 있다.

---

## 변환 결과

### 전체 비교

| 구분 | .lex 명세 | 실제 코드 | 비율 |
|------|----------|----------|------|
| 헌법 (프로젝트 원칙) | 30줄 | ~450줄 | 15x |
| 법률 (기능 로직) | 50줄 | ~1,230줄 | 24.6x |
| 규칙 (유효성 검사) | 12줄 | ~145줄 | 12x |
| 부칙 (참조 데이터) | 40줄 | ~200줄 | 5x |
| 판례 (예외 처리) | 25줄 | ~150줄 | 6x |
| **합계** | **~160줄** | **~2,800줄** | **17.5x** |

### 에스크로 결제 예시

**.lex 명세 (8줄):**

```json
{
  "id": "CL-001-2",
  "content": "point 타입 공고 시 points_per_person × recruits_count 만큼 즉시 에스크로한다."
},
{
  "id": "CL-001-3",
  "content": "에스크로 실패 시 공고 생성을 롤백한다."
}
```

**실제 코드 (4개 파일에 걸쳐 ~200줄):**

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
  render json: { error: "포인트 충전이 필요합니다" }, status: 422
end
```

2줄의 명세가 컨트롤러, 서비스, 모델, 마이그레이션에 걸친 200줄을 **거버넌스**한다.

---

## 어떤 점이 좋았나

### 1. 새 팀원 온보딩

.lex 파일 하나를 읽으면 LaunchCrew의 전체 비즈니스 로직을 10분 안에 파악할 수 있다. 코드베이스를 읽으려면 며칠이 걸린다.

### 2. 예외 처리의 추적성

코드에서 예외 처리는 `catch` 블록에 숨어 있다. "왜 이 로직이 있지?" → git blame → 슬랙 히스토리 → 원래 기획서...

.lex에서는 모든 예외가 **판례(Case Law)**로 기록되고, 어떤 조항과 연결되는지 명시한다:

```
CASE-002: 테스터 중도 포기
  상황: 테스터가 테스팅 도중 포기
  판결: 해당 테스터 에스크로만 개발자에게 반환
  관련조항: ACT-003 CL-005-3
```

### 3. 아키텍처 위반 감지

헌법 제3조에 "balance >= 0"이 명시되어 있다면, 이를 위반하는 코드 변경은 린터가 잡을 수 있다. 코드 리뷰에서 "이거 잔액 마이너스 될 수 있는데요?"를 사람이 잡을 필요가 없다.

---

## 솔직한 한계

1. **코드를 대체하지 않는다**: .lex는 "무엇을"을 정의하지, "어떻게"를 정의하지 않는다. 여전히 코드를 작성해야 한다.
2. **JSON이 장황하다**: 마크다운이나 YAML이 더 간결할 수 있다. 형식 개선 필요.
3. **자동 코드 생성은 아직**: CodeSpeak처럼 명세에서 코드를 자동 생성하는 기능은 아직 계획 단계다.
4. **작은 프로젝트에는 오버킬**: 프로토타입이나 해커톤 프로젝트에는 불필요하다.

---

## 누구에게 유용한가

- **규제 산업** (금융, 의료): 감사 추적이 필요한 곳. 모든 설계 결정이 번호 매겨진 조항으로 추적 가능.
- **5인 이상 팀**: 설계 문서가 코드와 괴리되는 문제를 해결.
- **SI 프로젝트**: 요구사항 → 구현 매핑이 필수인 곳.
- **장기 프로덕트**: 아키텍처가 시간이 지나면서 침식되는 것을 방지.

---

## 직접 해보기

```bash
git clone https://github.com/seunghan91/canoncode.git
cd canoncode

# LaunchCrew 예제 확인
cat examples/launchcrew-qa-matching.lex | python3 -m json.tool | head -50

# Rust 엔진 빌드 후 검증
cd lib/lex_engine && cargo build --release
./target/release/lex_cli info -f ../../examples/launchcrew-qa-matching.lex
```

전체 코드: [github.com/seunghan91/canoncode](https://github.com/seunghan91/canoncode)

---

## 다음 단계

1. `.lex → 코드 자동 생성` (LLM 연동)
2. `코드 → .lex 역공학` 자동화
3. 웹 UI에서 코드와 명세 나란히 비교 뷰
4. npm 패키지 배포 (`npx canoncode init my-project`)

**코드를 유지보수하는 게 아니라, 법률을 유지보수하는 개발.** 아직 실험 단계지만, 가능성은 느껴진다.
