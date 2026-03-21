---
title: "Rails + Inertia + Svelte 5: 아바타 이미지/색상 선택 기능 구현에서 삽질한 것들"
date: 2025-11-15
draft: false
tags: ["Rails", "Inertia.js", "Svelte 5", "ActiveRecord", "Migration", "Seeds", "디버깅"]
description: "DB에 색상을 저장하지 않고 인덱스로 계산하던 로직을 고치면서, API 컨트롤러와 Web 컨트롤러 분리, 시드 업데이트 패턴, 프리셋 이미지 처리까지 삽질한 내용을 정리한다."
cover:
  image: "/images/og/rails-inertia-svelte-pet-avatar-image-color.png"
  alt: "Rails Inertia Svelte Pet Avatar Image Color"
  hidden: true
categories: ["Rails"]
---

Rails 8 + Inertia.js + Svelte 5 스택으로 펫(반려동물) 프로필 아바타를 이미지 또는 색상으로 선택하는 기능을 구현하면서 겪은 문제들을 정리한다.

---

## 문제 1: 색상이 DB에 저장되지 않았다

### 증상

처음 코드를 보니 펫 카드에 색상을 표시할 때 이런 식으로 되어 있었다.

```typescript
const PET_COLORS = ['#f3caa1', '#b7ddf9', '#d3c8ff', '#c5d5f4', '#ffd9aa']

function petColor(index: number): string {
  return PET_COLORS[index % PET_COLORS.length]
}
```

**펫을 생성한 순서(인덱스)** 로 색상을 결정하는 구조였다. 색상을 DB에 아예 저장하지 않았으니, 사용자가 색상을 바꿔도 새로고침하면 원래 색상으로 돌아왔다.

### 해결

마이그레이션으로 `avatar_color` 컬럼을 추가하고 기본값을 지정했다.

```ruby
# db/migrate/..._add_avatar_color_to_pets.rb
class AddAvatarColorToPets < ActiveRecord::Migration[8.0]
  def change
    add_column :pets, :avatar_color, :string, default: '#f3caa1', null: false
  end
end
```

모델에는 허용 색상값 검증도 추가했다.

```ruby
# app/models/pet.rb
AVATAR_COLORS = %w[#f3caa1 #b7ddf9 #d3c8ff #c5d5f4 #ffd9aa].freeze

validates :avatar_color, inclusion: { in: AVATAR_COLORS }, allow_blank: true
validates :avatar_url, length: { maximum: 500 }, allow_blank: true
```

---

## 문제 2: API 컨트롤러를 Web UI에서 직접 호출할 수 없다

### 상황

기존에 `Api::V1::PetsController`가 이미 있었다. 처음에는 "그냥 이걸 쓰면 되겠다"고 생각했는데, 바로 막혔다.

### 원인

```ruby
# app/controllers/api/v1/base_controller.rb
class Api::V1::BaseController < ApplicationController
  include Authenticatable  # JWT Bearer 토큰 검증

  before_action :authenticate_api_user!
end
```

API 컨트롤러는 `Authorization: Bearer <jwt>` 헤더 기반 인증이다. 그런데 Inertia.js 기반 웹 UI는 **쿠키 세션** 으로 인증한다. 웹 페이지에서 Inertia의 `router.patch()` / `router.delete()` 를 호출하면 Bearer 토큰이 없으니 401이 반환된다.

### 해결

API 라우트를 쓰지 않고, `mypage_controller`에 별도로 웹용 pet CRUD 액션을 추가했다.

```ruby
# config/routes.rb
scope "mypage" do
  get    "pet-settings",      to: "mypage#pet_settings",  as: :mypage_pet_settings
  get    "pets/new",          to: "mypage#new_pet",       as: :mypage_new_pet
  post   "pets",              to: "mypage#create_pet",    as: :mypage_create_pet
  get    "pets/:id/edit",     to: "mypage#edit_pet",      as: :mypage_edit_pet
  patch  "pets/:id",          to: "mypage#update_pet",    as: :mypage_update_pet
  delete "pets/:id",          to: "mypage#destroy_pet",   as: :mypage_destroy_pet
end
```

```ruby
# app/controllers/mypage_controller.rb
def update_pet
  pet = current_user.pets.find(params[:id])
  pet.update!(web_pet_params)
  redirect_to mypage_pet_settings_path
end

private

def web_pet_params
  {
    name:           params[:name]&.strip,
    breed:          params[:breed]&.strip,
    gender:         params[:gender].presence || "unknown",
    weight_g:       params[:weight_kg].present? ? (params[:weight_kg].to_f * 1000).round : nil,
    neck_cm:        params[:neck_cm].presence,
    chest_cm:       params[:chest_cm].presence,
    back_length_cm: params[:back_length_cm].presence,
    waist_cm:       params[:waist_cm].presence,
    avatar_color:   params[:avatar_color].presence,
    avatar_url:     params[:avatar_url].presence,
  }.compact
end
```

**핵심**: 같은 Pet 모델을 쓰더라도 **인증 방식이 다른 두 컨트롤러**가 공존한다. API(JWT) vs Web(세션)은 완전히 분리해야 한다.

---

## 문제 3: Svelte 5에서 Inertia router.patch 즉시 반영

아바타 선택 패널에서 이미지나 색상을 클릭하면 바로 서버에 저장되고 UI에 반영되어야 했다. Inertia의 `router.patch`를 쓰면 페이지 리로드 없이 props만 업데이트된다.

```typescript
// PetSettings.svelte
function selectImage(pet: Pet, url: string) {
  router.patch(`/mypage/pets/${pet.id}`, {
    avatar_url:   url,
    avatar_color: pet.avatar_color,
    name:         pet.name,
    breed:        pet.breed,
    gender:       pet.gender ?? 'unknown',
    weight_kg:    pet.weight_g ? (pet.weight_g / 1000).toString() : '',
  }, {
    preserveScroll: true,
    onSuccess: () => { pickerPetId = null }  // 패널 닫기
  })
}
```

`preserveScroll: true`를 쓰지 않으면 patch 후 스크롤이 맨 위로 올라가버리니 주의.

---

## 문제 4: Seeds 업데이트가 적용되지 않는다

### 증상

`db:seed`를 다시 실행해도 기존 레코드의 `avatar_color`, `avatar_url`이 업데이트되지 않았다.

### 원인

기존 코드가 이런 패턴이었다.

```ruby
Pet.find_or_create_by!(user: user, name: "콩이") do |pet|
  pet.breed = "포메라니안"
  pet.avatar_color = "#f3caa1"
  # ...
end
```

`find_or_create_by!`의 블록은 **레코드를 새로 생성할 때만** 실행된다. 이미 존재하는 레코드는 블록이 아예 실행되지 않는다.

### 해결

`find_or_initialize_by` + `assign_attributes` + `save!` 패턴으로 변경했다.

```ruby
pet = Pet.find_or_initialize_by(user: user, name: "콩이")
pet.assign_attributes(
  breed:        "포메라니안",
  avatar_color: "#f3caa1",
  avatar_url:   "/images/pets/pomeranian.jpg",
  gender:       "female",
  weight_g:     2800,
)
pet.save!
```

`find_or_initialize_by`는 찾으면 기존 객체를, 없으면 새 객체를 반환한다. 이후 `assign_attributes`로 속성을 덮어쓰고 `save!`하면 생성/업데이트 둘 다 처리된다. **멱등성 있는 seed 작성**의 기본 패턴이다.

---

## 문제 5: 프리셋 이미지를 어디서 구하나

별도 이미지 업로드 기능 없이 프리셋 이미지를 DB URL로 저장하는 방식을 택했다. 이미지는 [Dog CEO API](https://dog.ceo/dog-api/)에서 품종별로 무료로 가져올 수 있다.

```bash
# 예시: 포메라니안 이미지 가져오기
curl "https://dog.ceo/api/breed/pomeranian/images/random" | jq -r .message
# → https://images.dog.ceo/breeds/pomeranian/n02112018_4099.jpg

curl -o public/images/pets/pomeranian.jpg \
  "https://images.dog.ceo/breeds/pomeranian/n02112018_4099.jpg"
```

이미지를 `public/images/pets/` 에 저장하면 Rails가 정적 파일로 서빙한다. Svelte 쪽에서는 그냥 `/images/pets/pomeranian.jpg` 경로로 쓰면 된다.

한 가지 함정: `shih-tzu` 품종은 Dog CEO API에서 `shihtzu` (하이픈 없음)로 쓴다.

```bash
curl "https://dog.ceo/api/breed/shihtzu/images/random"   # ✅
curl "https://dog.ceo/api/breed/shih-tzu/images/random"  # ❌ 404
```

---

## 전체 흐름 정리

```
[DB 마이그레이션]
  → avatar_color (string, default: '#f3caa1', not null)
  → avatar_url   (string, nullable)

[모델]
  → AVATAR_COLORS 상수 + inclusion 검증

[라우트 / 컨트롤러]
  → API (JWT) 와 Web (세션) 완전 분리
  → Web용 pet CRUD는 mypage_controller에

[프론트엔드 - Svelte 5]
  → PetSettings: 아바타 클릭 → picker 패널 → router.patch 즉시 저장
  → PetForm: useForm + $form.patch / $form.post

[Seeds]
  → find_or_initialize_by + assign_attributes + save! 패턴
```

---

## 느낀 점

- **API 컨트롤러와 Web 컨트롤러는 인증 방식이 다르면 반드시 분리**. 같은 모델을 쓰더라도 섞으면 안 된다.
- `find_or_create_by!` 블록의 "create 시에만 실행" 동작은 자주 실수하는 지점이다. 업데이트가 필요한 seed라면 `find_or_initialize_by` 패턴을 쓰자.
- Inertia.js의 `router.patch` + `preserveScroll: true` 조합은 SPA 수준의 UX를 별다른 상태 관리 없이 구현할 수 있어서 꽤 쾌적하다.
