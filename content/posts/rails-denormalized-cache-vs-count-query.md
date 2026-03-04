---
title: "Rails 비정규화 캐시 컬럼과 COUNT 쿼리 불일치: 씨드 데이터가 0%를 만들었을 때"
date: 2026-03-04
draft: false
tags: ["Rails", "디버깅", "데이터베이스", "비정규화", "씨드 데이터", "PostgreSQL"]
description: "직접 컬럼을 업데이트한 씨드 데이터가 화면에서 0%로 표시된 이유. vote_count 캐시 컬럼과 votes.count() 쿼리 사이의 불일치를 파헤친 디버깅 기록."
---

Rails 앱에 데모용 씨드 데이터를 직접 삽입했는데, 화면에서 모든 퍼센트가 **0%** 로 표시되는 상황을 만났다.

서버 로그도 깨끗하고, 데이터는 DB에 분명히 들어가 있는데, 숫자만 안 나온다.

---

## 상황

투표 기능이 있는 Rails 앱이다. 선택지(Choice)마다 득표 수를 보여주는 화면이 있고, 전체 투표수 대비 퍼센트를 계산해서 프로그레스 바와 숫자로 표시한다.

데모를 보여줘야 해서 외부 API에서 실시간 데이터를 가져와 씨드 데이터로 넣었다. 방식은 간단했다.

```ruby
# 씨드 데이터: 컬럼을 직접 업데이트
choice.update_column(:vote_count, 4712)
pick.update_column(:total_votes, 6536)
```

DB를 직접 조회하면 숫자가 잘 들어가 있다. 그런데 화면에서는:

```
선택지A   0%
선택지B   0%
선택지C   0%
```

전부 0%다.

---

## 원인 분석

`Pick` 모델의 `results` 메서드를 열어봤다.

```ruby
# 문제가 된 코드
def results
  total = votes.count  # ← 실제 Vote 레코드를 COUNT
  ordered_choices = choices.order(:position).to_a

  ordered_choices.map.with_index do |choice, index|
    {
      choice_id: choice.id,
      label: choice.label,
      count: choice.vote_count,
      percentage: total.zero? ? 0 : (choice.vote_count.to_f / total * 100).round(1),
      color: result_color_for_choice(index, choice.color)
    }
  end
end
```

`total = votes.count` — 이게 문제였다.

이 코드는 `votes` 연관관계를 통해 실제 `Vote` 테이블의 레코드 수를 COUNT한다.
씨드 데이터는 `vote_count`와 `total_votes` **컬럼만** 업데이트했을 뿐,
`Vote` 테이블에는 단 한 건도 넣지 않았다.

결과적으로:

| 데이터 | 값 |
|--------|-----|
| `pick.total_votes` | 6,536 |
| `choice.vote_count` | 4,712 |
| `Vote.where(pick: pick).count` | **0** |

분모인 `total`이 0이 되니 `percentage`도 0이었다.

---

## 모델 구조: 두 가지 카운트

이 앱의 모델에는 투표 수를 추적하는 경로가 두 가지였다.

```
votes (테이블)          ← 사용자가 투표할 때 생성되는 실제 레코드
  - user_id
  - pick_id
  - choice_id

choices (테이블)
  - vote_count          ← 비정규화된 캐시 컬럼 (정수)

picks (테이블)
  - total_votes         ← 비정규화된 캐시 컬럼 (정수)
```

정상적인 투표 플로우에서는 둘이 동시에 업데이트된다.

```ruby
# 투표 시: Vote 레코드 생성 + 캐시 컬럼 증가
Vote.create!(user: user, pick: pick, choice: choice)
choice.increment!(:vote_count)
pick.increment!(:total_votes)
```

그러나 씨드 데이터는 이 플로우를 건너뛰고 캐시 컬럼만 건드렸기 때문에, `votes.count`를 기준으로 계산하는 `results` 메서드는 "투표가 하나도 없다"고 인식했다.

---

## 해결

`total_votes` 캐시 컬럼을 분모로 쓰도록 변경했다.

```ruby
# 수정 후
def results
  total = total_votes.to_i  # ← 캐시 컬럼 사용
  ordered_choices = choices.order(:position).to_a

  ordered_choices.map.with_index do |choice, index|
    {
      choice_id: choice.id,
      label: choice.label,
      count: choice.vote_count,
      percentage: total.zero? ? 0 : (choice.vote_count.to_f / total * 100).round(1),
      color: result_color_for_choice(index, choice.color)
    }
  end
end
```

변경 포인트는 단 한 줄이다. `votes.count` → `total_votes.to_i`.

---

## 어떤 선택이 맞는가

둘 중 어느 쪽을 써야 할까. 상황에 따라 다르다.

### `votes.count` 를 쓰는 경우

- 실시간 정확도가 중요한 경우
- 캐시 컬럼 업데이트 로직을 신뢰하기 어려운 경우
- 소량 데이터라 N+1이 큰 문제가 아닌 경우

```sql
-- 매번 COUNT 쿼리 발생
SELECT COUNT(*) FROM votes WHERE pick_id = ?
```

### `total_votes` 캐시 컬럼을 쓰는 경우

- 표시용 숫자는 캐시 컬럼에서 읽는 것이 원칙
- 별도 쿼리 없이 컬럼 하나로 해결
- 씨드 데이터, 어드민 수동 조작 등 직접 업데이트와 호환됨

투표 집계처럼 **자주 읽히고 정확도가 중요한** 경우 비정규화는 일반적인 패턴이다.
`total_votes`가 존재하는 이유 자체가 "매번 COUNT 쿼리를 치지 않기 위해서"이므로,
화면 표시 로직은 이 컬럼을 기준으로 하는 것이 일관성 있다.

---

## 씨드 데이터 작성 시 주의점

이번 문제의 근본 원인은 씨드 데이터가 앱의 "비즈니스 플로우"를 따르지 않았기 때문이다.

앱의 정상 투표 플로우는:

```
Vote 레코드 생성 → vote_count 증가 → total_votes 증가
```

씨드 데이터는 캐시 컬럼만 건드렸다. 읽는 쪽이 Vote 레코드를 기대하면 문제가 생긴다.

씨드 데이터 전략은 두 가지다.

**방법 A: 서비스 오브젝트/메서드를 통해 삽입 (권장)**

```ruby
# 앱의 투표 로직을 그대로 타기 때문에 일관성 보장
VoteService.call(user: admin_user, pick: pick, choice: choice)
```

**방법 B: 캐시 컬럼만 직접 업데이트 (간편하지만 주의 필요)**

```ruby
# 읽는 쪽 로직이 캐시 컬럼 기반이어야 함
choice.update_column(:vote_count, 4712)
pick.update_column(:total_votes, 6536)
```

방법 B를 쓸 때는 해당 데이터를 소비하는 모든 메서드가 캐시 컬럼을 사용하는지 확인해야 한다.

---

## 디버깅 흐름 요약

```
0% 표시 확인
  → HTML에서 CSS 클래스 확인 (option-compact-prob)
  → 컴포넌트 코드 확인 → pick.results 호출 확인
  → pick.rb results 메서드 확인
  → votes.count 발견 → Vote 레코드 수 확인 → 0건
  → total_votes 컬럼 확인 → 값 있음
  → total = votes.count → total = total_votes 로 수정
```

원인을 찾는 데 걸린 시간보다 원인이 무엇인지 파악하는 게 더 중요했다.
"화면에 0%가 나온다"는 증상만 보고 뷰를 뒤지면 헤맨다. 데이터 흐름을 추적해야 한다.

---

## 마치며

비정규화 캐시 컬럼은 성능을 위해 자주 쓰이지만, **두 가지 진실의 원천**이 생긴다는 점을 항상 의식해야 한다.

- 소스: `Vote` 테이블 레코드
- 캐시: `total_votes`, `vote_count` 컬럼

읽는 코드와 쓰는 코드가 같은 원천을 바라보고 있는지, 씨드나 어드민 조작이 어느 원천을 업데이트하는지 항상 맞춰두는 것이 중요하다.
