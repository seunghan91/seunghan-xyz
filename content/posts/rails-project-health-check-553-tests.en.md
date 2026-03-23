---
title: "Rails Project Deep Inspection — From 16 Tests to 553, Finding 8 Hidden Bugs"
date: 2026-02-03
draft: false
tags: ["Rails", "RSpec", "Debugging", "Refactoring", "Pundit", "Testing"]
description: "Inspecting a Rails project with 3% test coverage revealed 8 hidden issues including Dockerfile version mismatch, missing Serializers, and Policy bugs. Writing 553 tests to fix them all."
cover:
  image: "/images/og/rails-project-health-check-553-tests.png"
  alt: "Rails Project Health Check 553 Tests"
  hidden: true
categories: ["Rails"]
---

I decided to do a thorough inspection of a production Rails 8 API server. Most features appeared to be working, but test coverage sat at a mere 3%. This was an exercise in finding out just how dangerous the assumption "it works, so it's fine" really is.

When a project reaches a certain level of maturity, stability becomes more important than shipping new features. In a codebase without tests, every refactor, every dependency upgrade, and every new team member onboarding becomes a gamble. This inspection was not just about raising a coverage number — it was about taking an honest look at the actual state of the codebase.

---

## State Before the Inspection

- Rails 8 + PostgreSQL (UUID PK) + JWT authentication + Pundit authorization
- RSpec tests: **16** (basic scaffold level)
- 20+ models, 15+ controllers, 5+ services
- A Dockerfile written for deployment, but no CI pipeline

Those 16 tests were essentially auto-generated routing tests from scaffold. Core business logic, authorization checks, and the service layer had zero coverage. Running a production service for months while continuously adding features on top of that foundation was genuinely unsettling in hindsight.

The inspection approach was straightforward: start with models, work through controllers, services, and Policies, and treat every failing test as a signal pointing to a real problem in the production code.

---

## Problems Found

### 1. Dockerfile Ruby Version Mismatch

```dockerfile
# Dockerfile
FROM ruby:3.2-slim AS builder  # ← version is 3.2

# Gemfile.lock
RUBY VERSION
   ruby 3.4.4p34                # ← actual version is 3.4
```

Locally everything was fine because `rbenv` was pinned to 3.4, but this was a ticking time bomb. Ruby 3.2 and 3.4 have gem C extension compatibility differences, and native gem builds can fail unexpectedly. Without a CI pipeline, this would have gone unnoticed until it caused an actual deployment failure.

**Fix**: `ruby:3.2-slim` → `ruby:3.4-slim`

This kind of drift is easy to accumulate when there is no single source of truth for the Ruby version. A good practice is to define the version once — in a GitHub Actions workflow matrix or a shared environment variable — and have `.ruby-version`, the `Gemfile`, and the `Dockerfile` all reference it.

---

### 2. Missing Serializer — 500 Error on an Endpoint

There was a public community travel listing API, but the corresponding Serializer class simply did not exist.

```ruby
# controller
def community
  trips = Trip.completed_public
  render_success(trips.map { |t| CommunityTripSerializer.new(t).serializable_hash })
  # ↑ NameError: uninitialized constant CommunityTripSerializer
end
```

Because this was a public API requiring no authentication, it was easy to skip in QA. Authentication-gated endpoints naturally get exercised during development, but public endpoints exist outside the auth flow and can slip through unnoticed. The missing class was created following the existing Serializer pattern, and the endpoint was covered with a Request spec.

---

### 3. Missing Policy Methods

The controller called `authorize @trip, :update_exchange_rates?`, but the corresponding method was not defined in the Policy.

```
Pundit::NotDefinedError: unable to find policy method :update_exchange_rates?
```

A similar case: `generate_invite?` was also missing. Both were added with owner or member access.

This type of bug appears frequently when controllers and Policies are written at different times. If you write the controller first and add the Policy later, the methods the controller references and the methods the Policy actually defines tend to drift apart. Writing Policy specs makes these mismatches surface at test time rather than in production.

---

### 4. Pundit Class-Level Authorize Bug

There was an interesting bug in the Accommodation listing endpoint.

```ruby
# controller
def index
  authorize Accommodation  # ← passing the class itself
  # ...
end

# policy
def trip
  record.is_a?(Class) ? Trip.find_by(id: @trip_id) : record.trip
  # ↑ @trip_id is not passed to the Policy → nil → authorization fails
end
```

The controller's `@trip_id` instance variable is not available inside the Policy object. Pundit constructs a new Policy instance with only `initialize(user, record)`, so there is no way to access controller-level instance variables from inside a Policy.

The code attempted to handle this with an `is_a?(Class)` branch, but `@trip_id` inside the Policy is nil, so `Trip.find_by(id: nil)` returns nil, causing authorization to always fail or raise an exception.

**Fix**: Replace `authorize Accommodation` with `authorize @trip.accommodations.build`, so the Policy can always reach the parent resource through `record.trip`.

```ruby
# controller (after fix)
def index
  authorize @trip.accommodations.build
  accommodations = @trip.accommodations
  # ...
end

# policy (simplified)
def index?
  trip_member?
end

private

def trip
  record.trip  # always accessible from the record
end
```

Using `build` creates an unsaved in-memory instance. The Policy receives that instance as `record` and can traverse the `trip` association on it without ever needing access to controller instance variables.

---

### 5. Positional vs Keyword Argument Mismatch in render_error

```ruby
# called in controller
render_error(message, :unprocessable_entity)  # positional argument

# defined in BaseController
def render_error(errors, status: :unprocessable_entity)  # keyword argument
```

In Ruby, calling `render_error("msg", :unprocessable_entity)` passes the second argument as a positional parameter, not as the `status` keyword — resulting in an `ArgumentError`. Since Ruby 3.0 drew a hard line between positional and keyword arguments, any code that carried over the old calling convention is at risk.

There is also a subtler variant: if the status keyword has a default value, Ruby may silently ignore the extra positional argument and use the default instead. The wrong HTTP status gets returned without any error, which is far harder to track down than an explicit `ArgumentError`.

**Fix**: `render_error(message, status: :unprocessable_entity)`

---

### 6. Serializer Referencing a Non-Existent Method

```ruby
class UserSerializer < ApplicationSerializer
  def serializable_hash
    {
      image: object.image,  # ← User model has no `image` method
      # avatar_url exists instead
    }
  end
end
```

The User model had an `avatar_url` method, not `image`. OAuth providers such as Google and GitHub include an `image` field in their user info payloads. The model column was named `avatar_url` when it was saved, but the Serializer was written using the OAuth provider's original field name.

This bug would raise `NoMethodError` on every API response that serializes a User — a critical failure that was never caught because there were no tests for those endpoints.

---

### 7. Missing Model File (Table Exists)

The `chat_messages` table had been created via migration, but `app/models/chat_message.rb` did not exist. The User model declared `has_many :chat_messages`, meaning any call to that association would raise an error.

This situation typically arises when a migration and its model file are written separately, or when a file gets deleted without rolling back the migration. Rails loads associations lazily, so the error only surfaces when `user.chat_messages` is actually called — not at boot time.

---

### 8. Calling a Private Method from a Controller

```ruby
class Trip < ApplicationRecord
  private

  def generate_invite_code!(expires_in: 7.days)
    # ...
  end
end
```

The controller called `@trip.generate_invite_code!`, but the method was inside a `private` block, causing a `NoMethodError`. Other methods in the same file were explicitly re-opened with `public :method_name`, but this one was missed.

What makes this bug interesting is that the `public :method_name` pattern was already in use in the same file. The developer clearly intended to selectively expose private methods, but `generate_invite_code!` was simply overlooked. Without code review, this kind of omission accumulates quietly.

---

## The UUID PK Test Trap

Working with PostgreSQL UUID primary keys surfaced a subtle but important testing problem.

```ruby
# This test failed intermittently
expense.recalculate_shares!
expect(ep1.reload.share_amount_cents).to eq(3334)  # gets the remainder penny
expect(ep2.reload.share_amount_cents).to eq(3333)
expect(ep3.reload.share_amount_cents).to eq(3333)
```

`recalculate_shares!` sorts participants by `order(:id)` and assigns the remainder to the first one. But UUIDs are not sequential. There is no guarantee that `ep1` is ever the first record in that ordering.

Because UUIDs are randomly generated, `order(:id)` can produce a different result on every test run. "Intermittently failing tests" are among the hardest bugs to track down — they rarely reproduce on demand, and teams often dismiss them as flaky CI. In most cases they stem from ordering assumptions or timing dependencies.

**Fix**: Instead of asserting a specific participant's value, sort all results and assert the distribution.

```ruby
shares = [ep1, ep2, ep3].map { |ep| ep.reload.share_amount_cents }.sort
expect(shares).to eq([3333, 3333, 3334])
expect(shares.sum).to eq(10_000)
```

This approach tests "is the total split correct?" rather than "who gets the remainder?" — which is also the more accurate expression of the actual business requirement.

---

## Shoulda Matchers + UUID Compatibility

```ruby
it { should validate_uniqueness_of(:email).case_insensitive }
```

This matcher failed in a UUID PK environment. Shoulda Matchers internally assumes integer primary keys in parts of its uniqueness validation logic, leading to unexpected behavior when UUIDs are used.

**Fix**: Replace with a manual test.

```ruby
it "does not allow duplicate emails" do
  create(:user, email: "test@example.com")
  duplicate = build(:user, email: "TEST@example.com")
  expect(duplicate).not_to be_valid
end
```

The manual test is longer, but it makes the intent explicit in the code. The `case_insensitive` behavior is also verified directly by using a different casing in the email, rather than relying on a matcher option.

---

## Final Results

| Metric | Before | After |
|--------|--------|-------|
| Test count | 16 | **553** |
| Failures | 0 (no tests to fail) | **0** |
| Pending | 0 | **0** |
| App bugs found | 0 (unknown) | **8 fixed** |

Writing tests surfaced 8 real bugs. "The feature works" and "the code is correct" are not the same statement.

The number 553 was never the goal. It accumulated by working through model specs, controller specs, policy specs, request specs, and service specs one layer at a time. Every time a test failed, the production code was fixed. Every fix reinforced why having the test there in the first place mattered.

---

## Key Takeaways

1. **Keep Ruby versions in sync across all files.** If `.ruby-version`, `Gemfile.lock`, and `Dockerfile` each point to a different version, something will eventually break. Without CI, this drift can hide for a long time.

2. **Pundit class-level authorize is a trap.** Use `authorize @parent.children.build` instead of `authorize ModelClass`. This gives the Policy clean access to the parent resource through `record.trip`, eliminating awkward `is_a?(Class)` workaround logic.

3. **Do not rely on `order(:id)` when using UUID primary keys.** Assuming a sort order in tests leads to intermittent failures. If you see a test that "randomly fails," UUID ordering is a likely culprit.

4. **Ruby keyword and positional arguments fail silently when default values are involved.** `method(a, b)` versus `method(a, key: b)` — if a default value is defined, the wrong value can be used without raising any error.

5. **Public endpoints are easy to miss in QA.** Auth-gated endpoints get exercised naturally during development. Endpoints that require no authentication sit outside the normal flow and can go untested for months. Cover them explicitly with Request specs.

6. **Code without tests is not "working code" — it is "code where the problems are not yet known."** None of the 8 bugs found during this inspection were obvious from reading the code alone. They only surfaced when the tests ran and forced the code to prove its correctness.
