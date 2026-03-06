---
title: "Rails 프로젝트 정밀 점검 — 16개 테스트에서 553개, 숨어있던 버그 8개"
date: 2026-03-06
draft: false
tags: ["Rails", "RSpec", "디버깅", "리팩토링", "Pundit", "테스트"]
description: "테스트 커버리지 3%짜리 Rails 프로젝트를 점검했더니 Dockerfile 버전 불일치, 누락된 Serializer, Policy 버그 등 8개의 숨은 문제가 나왔다. 553개 테스트를 작성하며 하나씩 잡아간 기록."
---

운영 중인 Rails 8 API 서버를 점검하기로 했다. 기능은 대부분 동작하고 있었지만, 테스트 커버리지가 3%밖에 안 되는 상태. "동작하니까 괜찮겠지"라는 생각이 얼마나 위험한지 확인하는 과정이었다.

---

## 점검 전 상태

- Rails 8 + PostgreSQL (UUID PK) + JWT 인증 + Pundit 권한
- RSpec 테스트: **16개** (기본 scaffold 수준)
- 모델 20개+, 컨트롤러 15개+, 서비스 5개+
- Dockerfile은 배포용으로 작성되어 있었고, CI는 없음

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

로컬에서는 `rbenv`로 3.4를 쓰고 있어서 문제 없었지만, Docker 빌드 시 gem 호환성 에러가 날 수 있는 시한폭탄이었다.

**수정**: `ruby:3.2-slim` → `ruby:3.4-slim`

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

인증 없이 접근하는 공개 API라 QA에서도 빠지기 쉬운 부분이었다. 기존 Serializer 패턴에 맞춰 생성.

---

### 3. Policy 메서드 누락

컨트롤러에서 `authorize @trip, :update_exchange_rates?`를 호출하는데, Policy에 해당 메서드가 없었다.

```
Pundit::NotDefinedError: unable to find policy method :update_exchange_rates?
```

비슷한 케이스로 `generate_invite?`도 누락. 둘 다 owner 또는 member 권한으로 추가.

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

컨트롤러의 `@trip_id`는 Policy 객체에 전달되지 않는다. Pundit의 `authorize`는 Policy 인스턴스를 새로 만들기 때문.

**수정**: `authorize Accommodation` 대신 `authorize @trip.accommodations.build`로 인스턴스를 넘겨서 Policy가 항상 `record.trip`을 통해 여행 정보에 접근하도록 변경.

---

### 5. render_error 호출 방식 불일치

```ruby
# 컨트롤러에서 호출
render_error(message, :unprocessable_entity)  # positional argument

# BaseController 정의
def render_error(errors, status: :unprocessable_entity)  # keyword argument
```

Ruby에서 `render_error("msg", :unprocessable_entity)`로 호출하면 두 번째 인자가 `status` 키워드가 아닌 positional로 들어가서 `ArgumentError`가 난다.

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

User 모델에는 `avatar_url` 메서드가 있고, `image`는 없었다. OAuth 인증 시 provider가 주는 필드명(`image`)을 그대로 쓴 것으로 보인다.

---

### 7. 모델 파일 누락 (테이블은 존재)

`chat_messages` 테이블은 마이그레이션으로 만들어져 있었지만, `app/models/chat_message.rb` 파일이 없었다. User 모델에서 `has_many :chat_messages`를 선언하고 있어서 association 호출 시 에러.

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

**수정**: 특정 참가자의 값을 검증하는 대신, 전체 분배 결과를 정렬해서 검증.

```ruby
shares = [ep1, ep2, ep3].map { |ep| ep.reload.share_amount_cents }.sort
expect(shares).to eq([3333, 3333, 3334])
expect(shares.sum).to eq(10_000)
```

---

## Shoulda Matchers + UUID 호환 문제

```ruby
it { should validate_uniqueness_of(:email).case_insensitive }
```

이 매처가 UUID PK 환경에서 실패했다. Shoulda가 내부적으로 레코드를 저장할 때 UUID 포맷 관련 비교에서 문제가 생긴다.

**수정**: 수동 테스트로 교체.

```ruby
it "이메일 중복을 허용하지 않는다" do
  create(:user, email: "test@example.com")
  duplicate = build(:user, email: "TEST@example.com")
  expect(duplicate).not_to be_valid
end
```

---

## 최종 결과

| 항목 | Before | After |
|------|--------|-------|
| 테스트 수 | 16 | **553** |
| 실패 | 0 (테스트가 없으니까) | **0** |
| Pending | 0 | **0** |
| 발견된 앱 버그 | 0 (몰랐음) | **8개 수정** |

테스트를 작성하는 과정에서 실제 버그 8개를 발견했다. "기능이 동작한다"와 "코드가 올바르다"는 다른 이야기다.

---

## 교훈

1. **Dockerfile과 로컬 환경의 버전을 동기화하라.** `.ruby-version`, `Gemfile.lock`, `Dockerfile`이 각각 다른 버전을 가리키고 있으면 어디선가 터진다.

2. **Pundit class-level authorize는 함정이다.** `authorize ModelClass` 대신 `authorize @parent.children.build`로 인스턴스를 넘겨라. Policy에서 부모 리소스에 접근할 수 있다.

3. **UUID PK를 쓴다면 `order(:id)`에 의존하지 마라.** 테스트에서 순서를 가정하면 간헐적 실패의 원인이 된다.

4. **Ruby의 keyword argument와 positional argument는 조용히 다르게 동작한다.** `method(a, b)` vs `method(a, key: b)` — 에러가 바로 나면 다행이지만, 예상과 다른 값이 들어가면 찾기 어렵다.

5. **테스트가 없는 코드는 "동작하는 코드"가 아니라 "아직 문제를 모르는 코드"다.**
