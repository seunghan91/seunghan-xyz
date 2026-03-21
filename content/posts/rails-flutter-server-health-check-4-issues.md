---
title: "Rails + Flutter 앱 서버 점검기: 한 번에 터진 4가지 문제와 해결"
date: 2025-10-15
draft: false
tags: ["Rails", "Flutter", "OAuth", "OpenAI", "PostgreSQL", "디버깅", "Seed Data"]
description: "Google SSO 실패, AI 일정 생성 엉뚱한 결과, 알림 페이지 크래시, 시드 데이터 부재 — 앱 빌드 하나에서 동시에 터진 4가지 문제를 진단하고 수정한 기록."
cover:
  image: "/images/og/rails-flutter-server-health-check-4-issues.png"
  alt: "Rails Flutter Server Health Check 4 Issues"
  hidden: true
categories: ["Rails"]
---

앱 테스트 빌드를 올리고 직접 돌려보니 한꺼번에 4가지가 안 됐다. Google 로그인 실패, AI 일정 생성이 엉뚱한 결과, 알림 버튼 누르면 크래시, 인기 여행지 섹션이 텅 비어있음. 하나씩 원인을 찾고 고친 과정을 정리한다.

---

## 1. Google SSO는 실패하는데 Apple 로그인은 성공

### 증상

Apple Sign-In은 정상 동작하지만 Google Sign-In만 500 에러. 클라이언트에서는 로그인 실패 토스트만 보인다.

### 원인

**컨트롤러는 이전 커밋에서 수정했지만, Model의 `from_omniauth` 메서드는 그대로였다.**

```ruby
# User 모델 — 마이그레이션 후에도 옛날 컬럼명 참조
def self.from_omniauth(auth)
  user = find_or_initialize_by(provider: auth.provider, uid: auth.uid)  # uid 컬럼 없음
  user.image = auth.info.image  # image 컬럼도 없음
end
```

DB 스키마에서는 `uid` → `provider_uid`, `image` → `avatar_url`로 마이그레이션된 상태. 컨트롤러 쿼리는 수정했지만 **모델 내부 메서드가 여전히 옛 컬럼을 참조**하고 있었다.

Apple 로그인은 `from_omniauth`를 타지 않는 별도 경로(`verify_apple_identity_token!` → 직접 `create_or_update_oauth_user!`)를 사용해서 영향이 없었다.

### 수정

```ruby
def self.from_omniauth(auth)
  user = find_or_initialize_by(provider: auth.provider, provider_uid: auth.uid)
  user.avatar_url = auth.info.image
  # ...
end

def set_uid_from_email
  self.provider_uid = email if self.provider_uid.blank?
end
```

### 교훈

DB 컬럼명 변경 시 **컨트롤러만 고치면 안 된다**. `grep -r "old_column_name" app/` 으로 모델, 서비스, 시리얼라이저까지 전부 확인해야 한다. 특히 OAuth 관련 코드는 로그인 경로가 여러 개(Google, Apple, 이메일)라서 한 경로만 테스트하면 다른 경로의 버그를 놓친다.

---

## 2. AI 일정 생성이 엉뚱한 결과를 반환

### 증상

"스위스" 키워드 + "가족여행" 테마로 AI 일정 생성을 요청했는데, 한국 국내 여행 일정이 나옴.

### 원인

**라우트는 정의되어 있지만 컨트롤러 파일 자체가 없었다.**

```ruby
# routes.rb
post "ai/generate_itinerary", to: "ai_itinerary#generate"
```

```
app/controllers/api/v1/ai_itinerary_controller.rb → 존재하지 않음 (404)
```

Flutter 앱은 API 호출 실패 시 **silent catch** 후 프리셋 데이터로 폴백하는 구조였는데, "스위스" 프리셋이 없어서 기본값(한국)이 표시된 것.

```dart
try {
  final response = await apiClient.post('/ai/generate_itinerary', data: {...});
  // ...
} catch (e) {
  // silent — 에러 로그도 없음
}
```

### 수정

1. **AI 컨트롤러 생성**: OpenAI GPT-4o 연동 + 프리셋 폴백 구조
2. **프리셋 확충**: 스위스, 방콕, 런던, 하와이 등 10개 도시
3. **Flutter 측 프리셋도 추가**: 앱 자체의 폴백 데이터에도 스위스 추가

```ruby
class AiItineraryController < BaseController
  skip_before_action :authenticate_user!

  def generate
    if ENV['OPENAI_API_KEY'].present?
      result = call_openai(params)
    else
      result = find_preset(params[:destination])
    end
    render_success(result)
  end
end
```

### 교훈

1. **라우트 정의 ≠ 기능 완성**. `rails routes`에서 200 OK가 아니라 404가 나오는지 실제로 curl 해봐야 한다
2. Flutter의 **silent catch 패턴은 디버깅의 적**. 최소한 `debugPrint`라도 남겨야 한다
3. AI API 의존 기능은 **반드시 폴백 전략**이 필요. API 키가 없거나 서비스 장애 시에도 기본 결과를 제공해야 한다

---

## 3. 알림 버튼 누르면 앱 크래시

### 증상

우측 상단 벨 아이콘 탭 → 앱 크래시 (또는 빈 화면)

### 원인

**알림 기능 디렉토리 자체가 없었다.**

```
lib/features/notification/  → 디렉토리 없음
```

GoRouter에서 `/notifications` 경로가 존재하지 않는 파일을 import 하려다 실패. 컴파일 타임에는 잡히지 않고(조건부 import 또는 lazy route), 런타임에 터지는 케이스.

### 수정

플레이스홀더 페이지 생성:

```dart
class NotificationsPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('알림')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.notifications_none, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('아직 알림이 없습니다'),
          ],
        ),
      ),
    );
  }
}
```

### 교훈

**네비게이션 경로를 정의할 때는 대상 페이지가 최소한 빈 Scaffold라도 존재해야 한다.** CI에서 `flutter analyze` + 라우트 대상 파일 존재 여부 체크를 자동화하면 방지할 수 있다.

---

## 4. 인기 여행지 섹션이 텅 비어있음

### 증상

홈 화면 하단 "인기 여행지" 섹션에 데이터가 없거나 하드코딩된 5개만 표시.

### 원인

- DB 테이블 없음 (마이그레이션 안 됨)
- 모델 없음
- API 엔드포인트 없음
- Flutter 앱은 하드코딩된 5개 데이터만 보유

### 수정

풀스택으로 한 번에 구축:

**1) 마이그레이션**
```ruby
create_table :popular_destinations, id: :uuid do |t|
  t.string :name, null: false
  t.string :name_en
  t.string :country_code, null: false
  t.text :description
  t.string :image_url
  t.decimal :rating, precision: 2, scale: 1
  t.integer :trip_count, default: 0
  t.string :tags, array: true, default: []
  t.string :keywords, array: true, default: []
  t.string :season
  t.integer :position
  t.boolean :featured, default: false
  t.boolean :active, default: true
  t.timestamps
end
```

**2) 모델 + 스코프**
```ruby
class PopularDestination < ApplicationRecord
  scope :active, -> { where(active: true) }
  scope :featured, -> { where(featured: true) }
  scope :ordered, -> { order(:position) }
end
```

**3) Public API 엔드포인트**
```ruby
class PopularDestinationsController < BaseController
  skip_before_action :authenticate_user!

  def index
    destinations = PopularDestination.active.ordered
    destinations = destinations.featured if params[:featured].present?
    render_success(destinations)
  end
end
```

**4) 시드 데이터** — 교토, 발리, 뉴욕, 산토리니, 파리, 스위스 등 12개 도시

---

## 보너스: 시드 데이터로 E2E 플로우 검증

단순히 버그만 고치고 끝내면 다음에 또 같은 문제가 생긴다. 시드 데이터로 **전체 여행 라이프사이클**을 재현해두면 개발/QA가 훨씬 편해진다.

### Flow 1: 여행 계획 전체 흐름

하나의 완료된 여행에 모든 관련 데이터를 연결:

```
Trip (completed, is_public: true)
├── Flights (왕복 2편, ICN↔JFK)
├── Schedules (7일 일정 + ScheduleFeedbacks)
├── Expenses (14건 + ExpenseParticipants 2인 분담)
├── Accommodation (호텔 1건)
├── TransportationBookings (공항 이동, 우버)
├── LocalTransports (MetroCard 7일권)
├── ShoppingItems (기념품, 패션, 뷰티 5건)
├── ScrapedLinks (위시리스트 4건)
├── Recommendations (맛집, 관광 4건)
├── ChecklistItems (여행 준비 체크리스트 8건)
├── TripAlbum + TripPhotos (앨범 1 + 사진 5장, GPS 포함)
└── Settlement (정산 완료, share_token 발급)
```

### Flow 2: 커뮤니티 뷰어 흐름

```
User C (viewer)
├── Follows: User A, User B
├── Browses: completed public trips
├── Posts: 여행 후기 5건 (A 2건, B 2건, C 1건)
├── Comments: 9건 (상호 댓글)
└── Likes: 8건 (상호 좋아요)
```

### 시드 실행 결과

```
Users: 3명
Trips: 11개 (completed 7, active 2, planning 2)
Flights: 4편 | Schedules: 44개 | Expenses: 68건
Posts: 5개 | Comments: 9개 | Likes: 8개 | Follows: 4개
ScheduleFeedbacks: 7개 | TripPhotos: 8장 | Settlements: 1건
```

---

## 발견한 추가 버그 (스키마-모델 불일치)

시드 데이터를 넣다가 발견한 문제:

### Post/Comment 모델에 user_id FK 누락

```ruby
# 모델
class Post < ApplicationRecord
  belongs_to :user  # user_id 컬럼을 기대
end
```

```ruby
# 실제 스키마 — user_id 없고 text 타입 user 필드만 있음
create_table "posts" do |t|
  t.text "user"     # JSON으로 유저 정보 저장용 (FK 아님)
  t.text "body"
end
```

`belongs_to :user`는 `user_id` FK를 기대하지만 실제 테이블에는 없었다. 마이그레이션 추가로 해결.

### Post 모델 validates :content — 실제 컬럼은 body

```ruby
validates :content, presence: true  # content 컬럼 없음, body가 맞음
```

이런 불일치는 마이그레이션과 모델을 다른 시점에 작성할 때 자주 발생한다. **시드 데이터를 짜면서 모든 모델을 한 번씩 건드려보면 이런 불일치를 조기에 발견할 수 있다.**

---

## 정리

| 문제 | 근본 원인 | 카테고리 |
|------|----------|----------|
| Google SSO 실패 | 컬럼명 변경 후 모델 메서드 미수정 | 스키마-코드 불일치 |
| AI 일정 엉뚱한 결과 | 컨트롤러 파일 미생성 + silent catch | 미완성 기능 + 에러 처리 |
| 알림 버튼 크래시 | 라우트 대상 페이지 파일 없음 | 미완성 기능 |
| 인기 여행지 빈 화면 | DB~API~클라이언트 전체 미구현 | 미완성 기능 |
| Post/Comment FK 누락 | 모델과 마이그레이션 시점 불일치 | 스키마-코드 불일치 |

**공통 교훈**: 기능을 추가할 때 "라우트 정의 → 컨트롤러 → 모델 → 마이그레이션 → 시드 → 클라이언트" 전체 체인을 한 번에 확인해야 한다. 시드 데이터로 E2E 플로우를 재현해두면 이런 빈틈을 빠르게 찾을 수 있다.
