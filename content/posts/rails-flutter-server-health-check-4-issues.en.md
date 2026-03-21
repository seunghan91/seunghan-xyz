---
title: "Rails + Flutter App Server Health Check: 4 Issues Found and Fixed at Once"
date: 2025-10-15
draft: false
tags: ["Rails", "Flutter", "OAuth", "OpenAI", "PostgreSQL", "Debugging", "Seed Data"]
description: "Google SSO failure, AI schedule generation wrong results, notification page crash, missing seed data — diagnosing and fixing 4 issues from a single app build."
cover:
  image: "/images/og/rails-flutter-server-health-check-4-issues.png"
  alt: "Rails Flutter Server Health Check 4 Issues"
  hidden: true
categories: ["Rails"]
---


After uploading a test build of the app and running it myself, 4 things broke simultaneously. Google login failure, AI itinerary generation returning wrong results, app crash on tapping the notification button, and the popular destinations section completely empty. Here is the process of finding and fixing each cause.

---

## 1. Google SSO Fails While Apple Login Succeeds

### Symptoms

Apple Sign-In works normally but Google Sign-In returns a 500 error. The client only shows a login failure toast.

### Cause

**The controller was fixed in a previous commit, but the Model's `from_omniauth` method was left unchanged.**

```ruby
# User model — still references old column names after migration
def self.from_omniauth(auth)
  user = find_or_initialize_by(provider: auth.provider, uid: auth.uid)  # uid column doesn't exist
  user.image = auth.info.image  # image column doesn't exist either
end
```

In the DB schema, `uid` had been migrated to `provider_uid` and `image` to `avatar_url`. The controller queries were fixed but **the model's internal method was still referencing old columns**.

Apple login was unaffected because it uses a separate path (`verify_apple_identity_token!` -> direct `create_or_update_oauth_user!`) that does not go through `from_omniauth`.

### Fix

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

### Lessons Learned

When changing DB column names, **fixing only the controller is not enough**. Use `grep -r "old_column_name" app/` to check models, services, and serializers as well. OAuth code is especially tricky because there are multiple login paths (Google, Apple, email), and testing only one path misses bugs in the others.

---

## 2. AI Itinerary Generation Returns Wrong Results

### Symptoms

Requested AI itinerary generation with "Switzerland" keyword + "family trip" theme, but a domestic Korea trip itinerary appeared.

### Cause

**The route was defined but the controller file itself did not exist.**

```ruby
# routes.rb
post "ai/generate_itinerary", to: "ai_itinerary#generate"
```

```
app/controllers/api/v1/ai_itinerary_controller.rb -> does not exist (404)
```

The Flutter app had a **silent catch** that fell back to preset data on API call failure, and since there was no "Switzerland" preset, the default (Korea) was displayed.

```dart
try {
  final response = await apiClient.post('/ai/generate_itinerary', data: {...});
  // ...
} catch (e) {
  // silent — no error logs either
}
```

### Fix

1. **Create AI controller**: OpenAI GPT-4o integration + preset fallback structure
2. **Expand presets**: 10 cities including Switzerland, Bangkok, London, Hawaii
3. **Add Flutter-side presets too**: Switzerland added to the app's own fallback data

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

### Lessons Learned

1. **Defining a route does not equal completing the feature**. You need to actually curl the endpoint to see if it returns 200 OK or 404
2. Flutter's **silent catch pattern is the enemy of debugging**. At minimum, add `debugPrint`
3. Features depending on AI APIs **must have a fallback strategy**. Even when API keys are missing or the service is down, basic results should be provided

---

## 3. App Crashes When Tapping Notification Button

### Symptoms

Top-right bell icon tap -> app crash (or blank screen)

### Cause

**The notification feature directory itself did not exist.**

```
lib/features/notification/  -> directory does not exist
```

GoRouter tried to import a non-existent file for the `/notifications` route. Not caught at compile time (conditional import or lazy route), crashes at runtime.

### Fix

Created a placeholder page:

```dart
class NotificationsPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Notifications')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.notifications_none, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('No notifications yet'),
          ],
        ),
      ),
    );
  }
}
```

### Lessons Learned

**When defining navigation routes, the target page must exist as at least an empty Scaffold.** Automating `flutter analyze` + route target file existence checks in CI can prevent this.

---

## 4. Popular Destinations Section Is Completely Empty

### Symptoms

"Popular Destinations" section at the bottom of the home screen has no data or only shows 5 hardcoded entries.

### Cause

- No DB table (migration not run)
- No model
- No API endpoint
- Flutter app only has 5 hardcoded data entries

### Fix

Built the full stack at once:

**1) Migration**
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

**2) Model + Scopes**
```ruby
class PopularDestination < ApplicationRecord
  scope :active, -> { where(active: true) }
  scope :featured, -> { where(featured: true) }
  scope :ordered, -> { order(:position) }
end
```

**3) Public API Endpoint**
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

**4) Seed data** -- 12 cities including Kyoto, Bali, New York, Santorini, Paris, Switzerland

---

## Bonus: Verifying E2E Flow with Seed Data

Just fixing bugs and moving on means the same problems will recur. Reproducing the **entire trip lifecycle** with seed data makes development and QA much easier.

### Flow 1: Complete Trip Planning Flow

Connecting all related data to a single completed trip:

```
Trip (completed, is_public: true)
├── Flights (2 round-trip, ICN<->JFK)
├── Schedules (7-day itinerary + ScheduleFeedbacks)
├── Expenses (14 entries + ExpenseParticipants 2-person split)
├── Accommodation (1 hotel)
├── TransportationBookings (airport transfer, Uber)
├── LocalTransports (MetroCard 7-day pass)
├── ShoppingItems (souvenirs, fashion, beauty - 5 items)
├── ScrapedLinks (wishlist 4 items)
├── Recommendations (restaurants, attractions - 4 items)
├── ChecklistItems (trip prep checklist - 8 items)
├── TripAlbum + TripPhotos (1 album + 5 photos, with GPS)
└── Settlement (settlement complete, share_token issued)
```

### Flow 2: Community Viewer Flow

```
User C (viewer)
├── Follows: User A, User B
├── Browses: completed public trips
├── Posts: 5 trip reviews (A: 2, B: 2, C: 1)
├── Comments: 9 entries (mutual comments)
└── Likes: 8 entries (mutual likes)
```

### Seed Execution Results

```
Users: 3
Trips: 11 (completed 7, active 2, planning 2)
Flights: 4 | Schedules: 44 | Expenses: 68
Posts: 5 | Comments: 9 | Likes: 8 | Follows: 4
ScheduleFeedbacks: 7 | TripPhotos: 8 | Settlements: 1
```

---

## Additional Bugs Found (Schema-Model Mismatch)

Problems discovered while inserting seed data:

### Post/Comment Model Missing user_id FK

```ruby
# Model
class Post < ApplicationRecord
  belongs_to :user  # expects user_id column
end
```

```ruby
# Actual schema — no user_id, only a text-type user field
create_table "posts" do |t|
  t.text "user"     # For storing user info as JSON (not an FK)
  t.text "body"
end
```

`belongs_to :user` expects a `user_id` FK but the actual table did not have one. Resolved by adding a migration.

### Post Model validates :content -- Actual Column Is body

```ruby
validates :content, presence: true  # content column doesn't exist, body is correct
```

This kind of mismatch frequently occurs when migrations and models are written at different times. **Writing seed data that touches every model helps discover these mismatches early.**

---

## Summary

| Problem | Root Cause | Category |
|---------|-----------|----------|
| Google SSO failure | Model method not updated after column rename | Schema-code mismatch |
| AI itinerary wrong results | Controller file not created + silent catch | Incomplete feature + error handling |
| Notification button crash | Route target page file missing | Incomplete feature |
| Popular destinations empty screen | DB~API~client all unimplemented | Incomplete feature |
| Post/Comment FK missing | Model and migration written at different times | Schema-code mismatch |

**Common lesson**: When adding a feature, the entire chain of "route definition -> controller -> model -> migration -> seed -> client" must be verified at once. Reproducing E2E flows with seed data helps find these gaps quickly.
