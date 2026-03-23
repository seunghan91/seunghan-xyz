---
title: "Rails 프로젝트 정밀 점검 — 16개 테스트에서 553개, 숨어있던 버그 8개"
date: 2026-02-03
draft: false
tags: ["Rails", "RSpec", "디버깅", "리팩토링", "Pundit", "테스트"]
description: "테스트 커버리지 3%짜리 Rails 프로젝트를 점검했더니 Dockerfile 버전 불일치, 누락된 Serializer, Policy 버그 등 8개의 숨은 문제가 나왔다. 553개 테스트를 작성하며 하나씩 잡아간 기록."
cover:
  image: "/images/og/rails-project-health-check-553-tests.png"
  alt: "Rails Project Health Check 553 Tests"
  hidden: true
categories: ["Rails"]
---

운영 중인 Rails 8 API 서버를 점검하기로 했다. 기능은 대부분 동작하고 있었지만, 테스트 커버리지가 3%밖에 안 되는 상태. "동작하니까 괜찮겠지"라는 생각이 얼마나 위험한지 확인하는 과정이었다.

프로젝트가 어느 정도 성숙기에 접어들면 기능 개발보다 안정화가 더 중요해진다. 테스트가 없는 코드베이스에서는 리팩토링도, 의존성 업그레이드도, 팀원 온보딩도 전부 도박이 된다. 이번 점검은 단순히 테스트 커버리지 수치를 올리는 작업이 아니라, 현재 코드베이스의 실제 상태를 정직하게 들여다보는 과정이었다.

---

## 점검 전 상태

- Rails 8 + PostgreSQL (UUID PK) + JWT 인증 + Pundit 권한
- RSpec 테스트: **16개** (기본 scaffold 수준)
- 모델 20개+, 컨트롤러 15개+, 서비스 5개+
- Dockerfile은 배포용으로 작성되어 있었고, CI는 없음

테스트 16개가 있다고는 하지만, 실제로는 scaffold 생성 시 자동으로 만들어진 기본 라우팅 테스트 수준이었다. 핵심 비즈니스 로직, 권한 체크, 서비스 레이어는 전혀 커버되지 않은 상태. 이 상태로 몇 달을 운영하면서 기능을 계속 추가해왔다는 게 솔직히 불안했다.

점검 방법은 단순했다. 모델부터 시작해서 컨트롤러, 서비스, Policy 순서로 테스트를 작성해 나가면서 실패하는 테스트가 생기면 그 원인을 추적했다.

---

## 발견된 문제들

### 1. Dockerfile Ruby 버전 불일치

```dockerfile
# Dockerfile
FROM ruby:3.2-slim AS builder  # ← 여기가 3.2

# Gemfile.lock
RUBY VERSION
   ruby 3.4.4p34                # ← 실제는 3.4
```

로컬에서는 `rbenv`로 3.4를 쓰고 있어서 문제 없었지만, Docker 빌드 시 gem 호환성 에러가 날 수 있는 시한폭탄이었다. Ruby 3.2와 3.4 사이에는 gem C extension 호환성 이슈가 있을 수 있고, native gem 빌드 시 예상치 못한 에러가 발생한다. CI/CD 파이프라인이 없어서 이 문제가 실제 배포 장애로 이어지기 전까지 발견되지 않았을 것이다.

**수정**: `ruby:3.2-slim` → `ruby:3.4-slim`

이런 불일치는 `.ruby-version`, `Gemfile`, `Gemfile.lock`의 `RUBY VERSION` 섹션, 그리고 `Dockerfile`을 동시에 확인하는 습관이 없으면 쌓이기 쉽다. GitHub Actions에서 Ruby 버전을 한 곳에서 관리하고 다른 곳에서 참조하는 방식으로 단일 소스를 유지하는 것이 좋다.

---

### 2. 누락된 Serializer — 엔드포인트 500 에러

커뮤니티 공개 여행 목록 API가 있었는데, 해당 Serializer 클래스가 아예 없었다.

```ruby
# controller
def community
  trips = Trip.completed_public
  render_success(trips.map { |t| CommunityTripSerializer.new(t).serializable_hash })
  # ↑ NameError: uninitialized constant CommunityTripSerializer
end
```

인증 없이 접근하는 공개 API라 QA에서도 빠지기 쉬운 부분이었다. 이 API를 호출하는 테스트가 없었으니 당연히 발견되지 않았다. 로그인이 필요한 엔드포인트는 개발 중에 자연스럽게 테스트하게 되지만, 공개 API는 인증 흐름 밖에 있어서 의도치 않게 건너뛰는 경우가 많다.

기존 Serializer 패턴에 맞춰 생성하고, 해당 엔드포인트의 요청/응답 구조를 Request spec으로 커버했다.

---

### 3. Policy 메서드 누락

컨트롤러에서 `authorize @trip, :update_exchange_rates?`를 호출하는데, Policy에 해당 메서드가 없었다.

```
Pundit::NotDefinedError: unable to find policy method :update_exchange_rates?
```

비슷한 케이스로 `generate_invite?`도 누락. 둘 다 owner 또는 member 권한으로 추가했다.

이 유형의 버그는 컨트롤러와 Policy를 각각 다른 시점에 작성할 때 자주 발생한다. 컨트롤러를 먼저 작성하고 Policy를 나중에 추가하다 보면, 컨트롤러가 참조하는 Policy 메서드 목록과 실제 Policy에 정의된 메서드가 어긋나게 된다. Policy spec을 작성하면 이런 불일치를 컴파일 타임이 아닌 테스트 실행 시점에 잡을 수 있다.

---

### 4. Pundit class-level authorize 문제

숙소(Accommodation) 목록 조회에서 흥미로운 버그가 있었다.

```ruby
# controller
def index
  authorize Accommodation  # ← 클래스를 넘김
  # ...
end

# policy
def trip
  record.is_a?(Class) ? Trip.find_by(id: @trip_id) : record.trip
  # ↑ @trip_id가 Policy에는 전달되지 않음 → nil → 권한 체크 실패
end
```

컨트롤러의 `@trip_id`는 Policy 객체에 전달되지 않는다. Pundit의 `authorize`는 Policy 인스턴스를 새로 만들기 때문이다. Policy 생성자는 `initialize(user, record)` 형태로만 호출되므로, 컨트롤러의 인스턴스 변수에는 접근할 방법이 없다.

`record.is_a?(Class)` 분기로 이 상황을 처리하려 했지만, `@trip_id`가 nil이 되어 `Trip.find_by(id: nil)`을 호출하게 되고, 결과적으로 nil을 반환해 권한 체크가 항상 실패하거나 예외가 발생한다.

**수정**: `authorize Accommodation` 대신 `authorize @trip.accommodations.build`로 인스턴스를 넘겨서 Policy가 항상 `record.trip`을 통해 여행 정보에 접근하도록 변경.

```ruby
# controller (수정 후)
def index
  authorize @trip.accommodations.build
  accommodations = @trip.accommodations
  # ...
end

# policy (단순화)
def index?
  trip_member?
end

private

def trip
  record.trip  # 항상 record에서 접근 가능
end
```

`build`를 쓰면 DB에 저장되지 않는 임시 인스턴스가 만들어지면서, Policy는 그 인스턴스의 `trip` 관계를 통해 부모 리소스에 접근할 수 있다.

---

### 5. render_error 호출 방식 불일치

```ruby
# 컨트롤러에서 호출
render_error(message, :unprocessable_entity)  # positional argument

# BaseController 정의
def render_error(errors, status: :unprocessable_entity)  # keyword argument
```

Ruby에서 `render_error("msg", :unprocessable_entity)`로 호출하면 두 번째 인자가 `status` 키워드가 아닌 positional로 들어가서 `ArgumentError`가 난다. Ruby 3.0부터 positional argument와 keyword argument를 명확히 분리했기 때문에 이전 코드에서 넘어온 패턴이라면 특히 주의해야 한다.

더 조용한 형태의 버그도 있다. `status` 기본값이 `:unprocessable_entity`로 설정되어 있어서, 두 번째 positional 인자로 넘긴 심볼이 무시되고 기본값이 그대로 쓰이는 경우다. 에러가 나지 않으면서 잘못된 HTTP status가 반환되는 유형인데 이쪽이 더 찾기 어렵다.

**수정**: `render_error(message, status: :unprocessable_entity)`

---

### 6. Serializer에서 없는 메서드 참조

```ruby
class UserSerializer < ApplicationSerializer
  def serializable_hash
    {
      image: object.image,  # ← User 모델에 image 메서드 없음
      # avatar_url은 있음
    }
  end
end
```

User 모델에는 `avatar_url` 메서드가 있고, `image`는 없었다. OAuth 인증 시 provider(Google, GitHub 등)가 반환하는 사용자 정보에는 `image` 필드가 포함된다. 이 값을 저장할 때 `avatar_url`로 컬럼명을 정했는데, Serializer에서는 OAuth provider의 필드명을 그대로 쓴 것으로 보인다.

이 버그는 User 정보를 반환하는 모든 API 응답에서 `NoMethodError`를 발생시키는 치명적인 문제지만, 테스트가 없으니 발견되지 않았다.

---

### 7. 모델 파일 누락 (테이블은 존재)

`chat_messages` 테이블은 마이그레이션으로 만들어져 있었지만, `app/models/chat_message.rb` 파일이 없었다. User 모델에서 `has_many :chat_messages`를 선언하고 있어서 association 호출 시 에러가 발생한다.

이런 상황은 테이블 마이그레이션과 모델 파일을 따로 작성할 때, 또는 파일을 삭제했다가 마이그레이션 롤백을 빠뜨린 경우에 생긴다. Rails는 ActiveRecord에 등록된 association을 lazy하게 로드하기 때문에, 실제로 `user.chat_messages`를 호출하기 전까지는 에러가 드러나지 않는다.

---

### 8. private 메서드를 컨트롤러에서 호출

```ruby
class Trip < ApplicationRecord
  private

  def generate_invite_code!(expires_in: 7.days)
    # ...
  end
end
```

컨트롤러에서 `@trip.generate_invite_code!`를 호출하는데, private 블록 안에 있어서 `NoMethodError`. 같은 파일에 다른 메서드들은 `public :method_name`으로 명시적으로 공개하고 있었는데, 이것만 빠져 있었다.

이 버그가 흥미로운 이유는 같은 파일 안에 이미 `public :method_name` 패턴이 사용되고 있었다는 점이다. 즉, 개발자가 의도적으로 일부 메서드는 공개 선언을 했는데, `generate_invite_code!`만 빠진 것이다. 리뷰 없이 혼자 작업하는 환경에서 이런 실수가 쌓인다.

---

## UUID PK에서의 테스트 함정

PostgreSQL UUID를 PK로 쓰는 프로젝트에서 재미있는 문제를 만났다.

```ruby
# 이 테스트가 간헐적으로 실패
expense.recalculate_shares!
expect(ep1.reload.share_amount_cents).to eq(3334)  # 나머지 1원
expect(ep2.reload.share_amount_cents).to eq(3333)
expect(ep3.reload.share_amount_cents).to eq(3333)
```

`recalculate_shares!`는 `order(:id)`로 참가자를 정렬한 뒤 첫 번째에게 나머지를 준다. 그런데 UUID는 순차적이지 않다. `ep1`이 항상 첫 번째가 아닌 것이다.

UUID는 랜덤하게 생성되므로 `order(:id)`의 결과가 테스트 실행마다 달라질 수 있다. "간헐적으로 실패하는 테스트"는 가장 찾기 어려운 버그 중 하나다. 재현이 되지 않으면 그냥 넘어가기 쉬운데, 대부분 실행 순서나 타이밍 의존성에서 비롯된다.

**수정**: 특정 참가자의 값을 검증하는 대신, 전체 분배 결과를 정렬해서 검증.

```ruby
shares = [ep1, ep2, ep3].map { |ep| ep.reload.share_amount_cents }.sort
expect(shares).to eq([3333, 3333, 3334])
expect(shares.sum).to eq(10_000)
```

이 접근법은 "누가 나머지를 받는가"가 아니라 "전체 분배가 올바른가"를 검증한다. 비즈니스 요구사항 관점에서도 이쪽이 더 올바른 테스트다.

---

## Shoulda Matchers + UUID 호환 문제

```ruby
it { should validate_uniqueness_of(:email).case_insensitive }
```

이 매처가 UUID PK 환경에서 실패했다. Shoulda가 내부적으로 레코드를 저장할 때 UUID 포맷 관련 비교에서 문제가 생긴다. 구체적으로는 Shoulda Matchers가 테스트용 레코드를 만들 때 integer PK를 가정한 로직이 있어서, UUID PK 환경에서 예상치 못한 동작이 나온다.

**수정**: 수동 테스트로 교체.

```ruby
it "이메일 중복을 허용하지 않는다" do
  create(:user, email: "test@example.com")
  duplicate = build(:user, email: "TEST@example.com")
  expect(duplicate).not_to be_valid
end
```

수동 테스트가 더 길지만, 실제로 무엇을 검증하는지 코드에서 명확히 드러난다는 장점이 있다. `case_insensitive` 동작도 `TEST@example.com`처럼 케이스를 바꿔서 명시적으로 확인할 수 있다.

---

## 최종 결과

| 항목 | Before | After |
|------|--------|-------|
| 테스트 수 | 16 | **553** |
| 실패 | 0 (테스트가 없으니까) | **0** |
| Pending | 0 | **0** |
| 발견된 앱 버그 | 0 (몰랐음) | **8개 수정** |

테스트를 작성하는 과정에서 실제 버그 8개를 발견했다. "기능이 동작한다"와 "코드가 올바르다"는 다른 이야기다.

553개라는 숫자가 처음부터 목표였던 건 아니다. 모델 spec, 컨트롤러 spec, policy spec, request spec, service spec을 하나씩 채워나가다 보니 그렇게 됐다. 중간중간 테스트가 실패할 때마다 실제 코드를 고쳤고, 고칠 때마다 테스트가 존재한다는 것의 가치를 다시 실감했다.

---

## Key Takeaways

1. **Dockerfile과 로컬 환경의 버전을 동기화하라.** `.ruby-version`, `Gemfile.lock`, `Dockerfile`이 각각 다른 버전을 가리키고 있으면 어디선가 터진다. CI가 없는 환경일수록 이 불일치가 오래 숨어 있다.

2. **Pundit class-level authorize는 함정이다.** `authorize ModelClass` 대신 `authorize @parent.children.build`로 인스턴스를 넘겨라. Policy에서 부모 리소스에 접근할 수 있고, `is_a?(Class)` 분기 같은 복잡한 우회 로직이 필요 없어진다.

3. **UUID PK를 쓴다면 `order(:id)`에 의존하지 마라.** 테스트에서 순서를 가정하면 간헐적 실패의 원인이 된다. "간헐적으로 실패"는 랜덤한 UUID 순서 때문인 경우가 많다.

4. **Ruby의 keyword argument와 positional argument는 조용히 다르게 동작한다.** `method(a, b)` vs `method(a, key: b)` — 에러가 바로 나면 다행이지만, 기본값이 있으면 에러 없이 잘못된 값으로 실행된다.

5. **공개 API 엔드포인트는 QA에서 빠지기 쉽다.** 인증이 필요한 엔드포인트는 개발 중 자연스럽게 테스트되지만, 인증 없이 접근하는 공개 API는 의도치 않게 건너뛰는 경우가 많다. Request spec으로 명시적으로 커버해야 한다.

6. **테스트가 없는 코드는 "동작하는 코드"가 아니라 "아직 문제를 모르는 코드"다.** 이번 점검에서 발견된 8개 버그 중 어떤 것도 코드를 보는 것만으로는 쉽게 찾을 수 없었다. 테스트를 실행해야 드러났다.
