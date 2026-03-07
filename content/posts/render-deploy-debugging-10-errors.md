---
title: "Render 배포 실패 디버깅 — DB 업그레이드부터 Gemfile 누락까지 10개 에러 연속 격파"
date: 2026-03-07
draft: false
tags: ["Rails", "Render", "PostgreSQL", "배포", "디버깅", "DevOps"]
description: "Render DB 업그레이드 중 서비스 재개로 촉발된 배포 실패를 10단계에 걸쳐 수정한 실전 디버깅 기록"
cover:
  image: "/images/og/render-deploy-debugging-10-errors.png"
  alt: "Render Deploy Debugging"
  hidden: true
---

오늘 Rails 앱 배포가 `build_failed`로 떨어졌다. 처음엔 단순한 에러 하나겠지 싶었는데, 고칠 때마다 새 에러가 튀어나왔다. 결국 10개의 에러를 순서대로 해결하고 나서야 `live` 상태가 됐다. 연속 디버깅의 기록을 남긴다.

---

## 배경

Render에서 Rails 8 + Inertia.js + Svelte 5 조합 웹 서비스를 운영 중이다. 어느 날 대시보드를 보니 최신 배포가 `build_failed` 상태. 로그를 열었다.

---

## 에러 1: DB 연결 실패 — `ActiveRecord::ConnectionNotEstablished`

```
bin/rails aborted!
ActiveRecord::ConnectionNotEstablished: connection to server at "10.x.x.x", 
port 5432 failed: Connection refused
Tasks: TOP => db:migrate
```

빌드 스크립트에서 `db:migrate`를 실행하는 순간 PostgreSQL 연결이 거부됐다. 트리거를 보니 `service_resumed` — 서비스가 재개(resume)된 것이었다.

**원인:** Render DB가 업그레이드 중이었다. DB 상태를 확인하니 `upgrade_in_progress`. 서비스 재개와 DB 업그레이드가 타이밍이 겹쳐버린 것.

**해결:** DB 상태가 `available`이 될 때까지 대기 후 수동으로 재배포를 트리거했다.

```bash
# render CLI로 DB 상태 확인
render services list --output json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data:
    if 'postgres' in item:
        print(item['postgres']['status'])
"
# upgrade_in_progress → unavailable → available 순으로 변경됨 (약 10분 소요)

# DB 준비 확인 후 재배포
render deploys create <service-id> --confirm
```

---

## 에러 2: 모델 클래스 없음 — `NameError: Missing model class`

```
NameError: Missing model class TransportationBooking for the 
Trip#transportation_bookings association.
/server/db/seeds.rb:51:in 'block in <main>'
```

`seeds.rb` 51번째 줄은 `u.trips.destroy_all`이다. Rails가 `Trip` 모델의 `dependent: :destroy` 연관을 처리하려다 `TransportationBooking` 클래스를 찾지 못했다.

**원인:** 모델 파일이 git에 추가되지 않았다 (`??` untracked 상태). `trip.rb`에 `has_many :transportation_bookings` 선언은 있는데, 정작 `transportation_booking.rb` 파일이 원격 저장소에 없었던 것.

비슷한 상황의 파일이 여럿이었다:

```
?? server/app/models/transportation_booking.rb
?? server/app/models/blog_post.rb
?? server/app/models/shopping_item.rb
?? server/app/models/local_transport.rb
?? server/app/models/trip_album.rb
?? server/app/models/trip_photo.rb
```

**해결:** 모델 파일들과 대응하는 마이그레이션을 일괄 생성·커밋했다.

```bash
git add server/app/models/transportation_booking.rb \
        server/app/models/blog_post.rb \
        ... (이하 생략)
```

---

## 에러 3: UUID / bigint 타입 불일치 — `PG::DatatypeMismatch`

```
PG::DatatypeMismatch: ERROR: foreign key constraint cannot be implemented
DETAIL: Key columns "trip_id" of the referencing table and "id" of the 
referenced table are of incompatible types: bigint and uuid.
```

마이그레이션을 이렇게 작성했는데:

```ruby
create_table :transportation_bookings do |t|
  t.references :trip, null: false, foreign_key: true  # ← 문제
```

**원인:** `trips` 테이블은 UUID primary key를 사용하는데, `t.references`의 기본 타입은 `bigint`다.

**해결:** 모든 references에 `type: :uuid`를 명시했다.

```ruby
create_table :transportation_bookings do |t|
  t.references :trip, type: :uuid, null: false, foreign_key: true
  t.references :user, type: :uuid, null: false, foreign_key: true
```

프로젝트에서 UUID primary key를 사용한다면, 외래키 참조 시 **반드시** `type: :uuid`를 지정해야 한다.

---

## 에러 4: 이미 실행된 마이그레이션에 컬럼 누락

```
NoMethodError: undefined method 'description=' for an instance of LocalTransport
```

`local_transports` 마이그레이션이 이미 DB에 반영됐는데, `description`, `purchased_at`, `balance_cents` 컬럼이 없었다. seeds.rb는 이 컬럼들을 사용하고 있었다.

**원인:** 마이그레이션 파일을 수정해서 커밋했는데, 이미 한 번 실행된 마이그레이션이었다. Rails는 `schema_migrations` 테이블에 기록된 버전은 다시 실행하지 않는다.

**해결:** 기존 마이그레이션을 수정하는 대신, 새 마이그레이션을 추가했다.

```ruby
# 20260307000008_add_missing_columns_to_local_transports.rb
class AddMissingColumnsToLocalTransports < ActiveRecord::Migration[8.0]
  def change
    add_column :local_transports, :description, :text unless column_exists?(:local_transports, :description)
    add_column :local_transports, :purchased_at, :datetime unless column_exists?(:local_transports, :purchased_at)
    add_column :local_transports, :balance_cents, :integer unless column_exists?(:local_transports, :balance_cents)
  end
end
```

`column_exists?` 가드를 쓴 이유: 혹시 로컬 개발 환경에서 이 마이그레이션을 실수로 두 번 실행하더라도 에러가 나지 않도록.

---

## 에러 5: 컬럼 이름 불일치 — `cover_image_url` vs `cover_photo_url`

```
NoMethodError: undefined method 'cover_photo_url=' for an instance of TripAlbum
```

마이그레이션에는 `cover_image_url`로 만들었는데, seeds.rb는 `cover_photo_url`을 사용하고 있었다. 마찬가지로 `trip_photos` 테이블의 `location_name`과 seeds의 `place_name`도 불일치.

**해결:** rename 마이그레이션을 추가했다.

```ruby
class FixTripAlbumsAndPhotosColumns < ActiveRecord::Migration[8.0]
  def change
    if column_exists?(:trip_albums, :cover_image_url)
      rename_column :trip_albums, :cover_image_url, :cover_photo_url
    elsif !column_exists?(:trip_albums, :cover_photo_url)
      add_column :trip_albums, :cover_photo_url, :string
    end
    # trip_photos도 동일하게 처리
  end
end
```

`if/elsif` 분기를 쓴 이유: 로컬 환경(컬럼이 처음부터 올바른 이름으로 존재)과 프로덕션(rename 필요)을 모두 대응하기 위해.

---

## 에러 6, 7: `posts`, `comments` 테이블에 `user_id` 없음

```
PG::UndefinedColumn: ERROR: column posts.user_id does not exist
HINT: Perhaps you meant to reference the column "posts.user".
```

오래된 마이그레이션을 보니:

```ruby
# ❌ 잘못된 마이그레이션
create_table :posts, id: :uuid do |t|
  t.text :user     # ← user 텍스트 컬럼으로 잘못 생성
  t.text :body
  ...
end
```

`t.references :user` 대신 `t.text :user`로 작성되어 있었다. `Post` 모델은 `belongs_to :user`를 선언하고 있어 Rails는 `user_id` UUID 컬럼을 기대하는데, 실제로는 `user`라는 text 컬럼만 있었다.

**해결:** 각각 추가 마이그레이션으로 `user_id` 컬럼을 붙였다.

```ruby
class AddUserIdToPosts < ActiveRecord::Migration[8.0]
  def change
    unless column_exists?(:posts, :user_id)
      add_reference :posts, :user, type: :uuid, foreign_key: true, null: true
    end
  end
end
```

---

## 에러 8: 사용하지 않는 `monetize` 선언

```
NoMethodError: undefined method 'amount_cents' for an instance of Post
```

Post 모델에 이런 코드가 있었다:

```ruby
class Post < ApplicationRecord
  belongs_to :user
  monetize :amount_cents  # ← DB 컬럼 없음
  ...
end
```

`money-rails` gem의 `monetize` 매크로는 해당 컬럼이 DB에 실제로 있어야 동작한다. `amount_cents` 컬럼은 마이그레이션에 없었고, seeds에서도 사용하지 않는 코드였다.

**해결:** 한 줄 삭제.

---

## 에러 9: 모델 클래스 누락 — `PopularDestination`

```
NameError: uninitialized constant PopularDestination
```

에러 2와 같은 패턴. 이번엔 `popular_destination.rb` 파일이 untracked 상태였다.

**해결:** 모델 파일과 마이그레이션을 함께 커밋.

---

## 에러 10 (최후의 보스): `apnotic` gem LoadError

```
cannot load such file -- apnotic (LoadError)
```

드디어 seeds.rb 오류는 다 잡았는데, 런타임 서버 시작 시 gem을 찾지 못했다.

**원인:** `Gemfile`과 `Gemfile.lock`이 git에 커밋되지 않았다. 최근에 APNS 푸시 알림 기능을 추가하면서 `gem "apnotic"` 을 Gemfile에 넣었는데, 모델·마이그레이션 파일들만 골라 커밋하다가 Gemfile 변경분이 빠져버린 것.

**해결:** `git status`로 확인하면 바로 보이는 문제였다.

```bash
git add server/Gemfile server/Gemfile.lock
git commit -m "fix: Add apnotic gem"
git push
```

이 커밋 후 드디어 `live`.

---

## 교훈 정리

### 1. 배포 전 `git status` 전체 확인은 필수

`git add` 없이 누락된 파일이 의외로 많다. 특히 새 기능을 만들며 파일을 여러 개 생성하다 보면 일부를 빠뜨리기 쉽다. 배포 전에 반드시:

```bash
git status  # untracked(??) 파일 없는지 확인
git diff HEAD -- Gemfile Gemfile.lock  # gem 변경사항 확인
```

### 2. UUID primary key 프로젝트에서 마이그레이션 템플릿

```ruby
# UUID primary key 테이블 참조 시 항상 type: :uuid 명시
t.references :trip, type: :uuid, null: false, foreign_key: true
t.references :user, type: :uuid, null: false, foreign_key: true
```

### 3. 이미 실행된 마이그레이션은 수정이 아닌 추가로

프로덕션에서 이미 실행된 마이그레이션 파일을 고쳐봐야 소용없다. Rails는 `schema_migrations`에 기록된 버전을 다시 실행하지 않는다. **항상 새 마이그레이션을 추가**하고, `column_exists?`로 방어 코드를 넣자.

### 4. DB 업그레이드 타이밍 주의

Render (또는 다른 PaaS)에서 DB 업그레이드가 진행 중일 때는 배포를 시도하지 않는 것이 좋다. 업그레이드 중에는 DB가 `unavailable` 상태를 거치므로, `db:migrate`가 연결 실패로 빌드 자체를 망가뜨릴 수 있다.

### 5. `t.text :user` vs `t.references :user`

```ruby
# ❌ 잘못된 패턴 — user라는 이름의 text 컬럼만 생성
t.text :user

# ✅ 올바른 패턴 — user_id (UUID) 외래키 컬럼 생성
t.references :user, type: :uuid, foreign_key: true
```

`belongs_to :user`가 있는 모델은 DB에 `user_id` 컬럼이 있어야 한다.

---

## 마치며

단순한 `build_failed` 하나가 연쇄 에러 10개로 이어졌다. 하나씩 로그 → 원인 파악 → 수정 → 재배포 사이클을 반복하는 과정이 지루하게 느껴질 수도 있지만, 각 에러가 명확한 원인과 해결책을 갖고 있어 오히려 깔끔했다.

배포 파이프라인을 견고하게 유지하려면 결국 **git 커밋 단위 관리**, **마이그레이션 불변 원칙**, **타입 일관성**이 핵심이다.
