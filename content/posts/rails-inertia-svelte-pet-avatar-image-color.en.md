---
title: "Rails + Inertia + Svelte 5: Avatar Image/Color Selection Feature Implementation Struggles"
date: 2025-11-15
draft: false
tags: ["Rails", "Inertia.js", "Svelte 5", "ActiveRecord", "Migration", "Seeds", "Debugging"]
description: "Fixing logic that calculated colors from indices instead of storing them in DB, separating API and Web controllers, seed update patterns, and preset image handling."
cover:
  image: "/images/og/rails-inertia-svelte-pet-avatar-image-color.png"
  alt: "Rails Inertia Svelte Pet Avatar Image Color"
  hidden: true
categories: ["Rails"]
---


This documents the problems encountered while implementing a pet profile avatar selection feature (image or color) on a Rails 8 + Inertia.js + Svelte 5 stack.

---

## Problem 1: Colors Were Not Stored in the DB

### Symptoms

Looking at the initial code, pet card colors were displayed like this:

```typescript
const PET_COLORS = ['#f3caa1', '#b7ddf9', '#d3c8ff', '#c5d5f4', '#ffd9aa']

function petColor(index: number): string {
  return PET_COLORS[index % PET_COLORS.length]
}
```

Colors were determined by the **order (index) in which pets were created**. Since colors were not stored in the DB at all, even if a user changed a color, it would revert to the original on refresh.

### Solution

Added an `avatar_color` column via migration with a default value.

```ruby
# db/migrate/..._add_avatar_color_to_pets.rb
class AddAvatarColorToPets < ActiveRecord::Migration[8.0]
  def change
    add_column :pets, :avatar_color, :string, default: '#f3caa1', null: false
  end
end
```

Also added allowed color value validation to the model.

```ruby
# app/models/pet.rb
AVATAR_COLORS = %w[#f3caa1 #b7ddf9 #d3c8ff #c5d5f4 #ffd9aa].freeze

validates :avatar_color, inclusion: { in: AVATAR_COLORS }, allow_blank: true
validates :avatar_url, length: { maximum: 500 }, allow_blank: true
```

---

## Problem 2: Cannot Call API Controller Directly from Web UI

### Situation

An `Api::V1::PetsController` already existed. Initially I thought "I can just use this," but was immediately blocked.

### Cause

```ruby
# app/controllers/api/v1/base_controller.rb
class Api::V1::BaseController < ApplicationController
  include Authenticatable  # JWT Bearer token verification

  before_action :authenticate_api_user!
end
```

The API controller uses `Authorization: Bearer <jwt>` header-based authentication. However, the Inertia.js-based web UI authenticates via **cookie sessions**. Calling Inertia's `router.patch()` / `router.delete()` from a web page returns 401 since there is no Bearer token.

### Solution

Instead of using API routes, added separate web-specific pet CRUD actions to `mypage_controller`.

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

**Key point**: Even when using the same Pet model, **two controllers with different authentication methods** coexist. API (JWT) vs Web (session) must be completely separated.

---

## Problem 3: Immediate Reflection with Inertia router.patch in Svelte 5

When clicking an image or color in the avatar selection panel, it needed to save to the server immediately and reflect in the UI. Using Inertia's `router.patch` updates only the props without a page reload.

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
    onSuccess: () => { pickerPetId = null }  // close panel
  })
}
```

Note that without `preserveScroll: true`, the scroll jumps to the top after a patch.

---

## Problem 4: Seed Updates Not Being Applied

### Symptoms

Running `db:seed` again did not update `avatar_color` and `avatar_url` on existing records.

### Cause

The existing code used this pattern:

```ruby
Pet.find_or_create_by!(user: user, name: "Kongi") do |pet|
  pet.breed = "Pomeranian"
  pet.avatar_color = "#f3caa1"
  # ...
end
```

The block in `find_or_create_by!` is **only executed when creating a new record**. For already existing records, the block is never executed at all.

### Solution

Changed to the `find_or_initialize_by` + `assign_attributes` + `save!` pattern.

```ruby
pet = Pet.find_or_initialize_by(user: user, name: "Kongi")
pet.assign_attributes(
  breed:        "Pomeranian",
  avatar_color: "#f3caa1",
  avatar_url:   "/images/pets/pomeranian.jpg",
  gender:       "female",
  weight_g:     2800,
)
pet.save!
```

`find_or_initialize_by` returns the existing object if found, or a new object if not. Then `assign_attributes` overwrites the attributes and `save!` handles both creation and update. This is the basic pattern for **writing idempotent seeds**.

---

## Problem 5: Where to Get Preset Images

Chose to store preset images as DB URLs without a separate image upload feature. Images can be obtained for free by breed from the [Dog CEO API](https://dog.ceo/dog-api/).

```bash
# Example: fetching a Pomeranian image
curl "https://dog.ceo/api/breed/pomeranian/images/random" | jq -r .message
# -> https://images.dog.ceo/breeds/pomeranian/n02112018_4099.jpg

curl -o public/images/pets/pomeranian.jpg \
  "https://images.dog.ceo/breeds/pomeranian/n02112018_4099.jpg"
```

Saving images to `public/images/pets/` lets Rails serve them as static files. On the Svelte side, just use the `/images/pets/pomeranian.jpg` path.

One gotcha: the `shih-tzu` breed is written as `shihtzu` (no hyphen) in the Dog CEO API.

```bash
curl "https://dog.ceo/api/breed/shihtzu/images/random"   # OK
curl "https://dog.ceo/api/breed/shih-tzu/images/random"  # 404
```

---

## Complete Flow Summary

```
[DB Migration]
  -> avatar_color (string, default: '#f3caa1', not null)
  -> avatar_url   (string, nullable)

[Model]
  -> AVATAR_COLORS constant + inclusion validation

[Routes / Controller]
  -> API (JWT) and Web (session) fully separated
  -> Web pet CRUD in mypage_controller

[Frontend - Svelte 5]
  -> PetSettings: avatar click -> picker panel -> router.patch instant save
  -> PetForm: useForm + $form.patch / $form.post

[Seeds]
  -> find_or_initialize_by + assign_attributes + save! pattern
```

---

## Takeaways

- **API controllers and Web controllers must be separated when authentication methods differ**. Even when using the same model, do not mix them.
- The "only executes on create" behavior of `find_or_create_by!` blocks is a common mistake. For seeds that need updates, use the `find_or_initialize_by` pattern.
- Inertia.js's `router.patch` + `preserveScroll: true` combination delivers SPA-level UX without any extra state management, and it is quite pleasant to work with.
