---
title: "Role-Based UI Separation and Mobile Optimization in a Rails 8 + Hotwire Native App"
date: 2026-03-17
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "WKWebView", "Tailwind", "i18n", "RBAC", "Stimulus"]
description: "From fixing distorted layouts in a mobile WebView to designing a per-tournament staff permission system — a day of cascading fixes"
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

Running an iOS app built with Rails 8 + Hotwire Native, I hit a series of issues in a single day. What started as a small UI distortion spiraled into a full permission system redesign. Here is the complete record.

The central appeal of Hotwire Native is being able to serve both a web browser and a native iOS or Android shell from a single Rails application. But that architecture quietly encourages a dangerous assumption: if it looks right in the browser, it will look right in the app. In practice, the WKWebView rendering context, the presence of a native navigation bar, and role-based UI branching introduce concerns that have no equivalent in a standard web browser. This post walks through seven of those issues and the patterns that resolved them.

---

## 1. Card Badges Distorted in the Mobile WebView

### Symptom

Tournament discovery cards looked perfectly fine in a desktop browser. Inside the iOS app's WKWebView (375px viewport), badges and icons were squished and overlapping.

### Root Cause

The deployed view used a **desktop-first layout** with `max-w-[1400px]` and a responsive grid. The WKWebView respects the `viewport` meta tag (`width=device-width, initial-scale=1`), so it renders the entire layout at 375px. Critically, Tailwind's `sm:` breakpoint at 640px never fires. The layout that assumed 1400px of horizontal space was being forced into less than a third of that.

```erb
<!-- Problem: desktop container -->
<div class="mx-auto min-h-screen max-w-[1400px] px-4 py-6">
  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
```

### Fix

Rewrote the container to be mobile-first with a hard 390px cap.

```erb
<!-- Fixed: mobile-first -->
<div class="w-full mx-auto" style="max-width: min(390px, 100%);">
  <div class="space-y-3">
```

Inside the cards, the banner height was reduced (`h-28` to `h-24`), badge font size was scaled down (`text-xs` to `text-[11px]`), and overflow was controlled with `min-w-0 truncate`. The `min-w-0` is non-obvious but important: a flex child defaults to `min-width: auto`, which means its content can push the container wider than intended. Setting `min-w-0` explicitly opts the element into proper truncation.

```erb
<div class="flex items-center min-w-0 gap-1">
  <span class="truncate text-[11px] font-medium">Badge text</span>
</div>
```

**Lesson**: With Hotwire Native, design every shared view for the mobile viewport first. Responsive breakpoints (`sm:`, `lg:`) are irrelevant inside WKWebView. If a view needs to work on both desktop browsers and the native app, design for mobile and use padding or max-width centering to make it tolerable on larger screens — not the other way around.

---

## 2. Cryptic W/L Badges

The dashboard stats strip displayed `0W` and `0L` badges. For users unfamiliar with English sports notation, neither abbreviation was self-explanatory.

### Attempt: Title Tooltips

```erb
<span title="Wins">0W</span>
```

Title attribute tooltips appear on desktop via mouse hover, but they do not work in a mobile WebView. Neither iOS Safari nor WKWebView supports tooltip display on tap or long-press — those gestures are reserved for text selection and the system context menu.

### Fix: Locale-Aware Labels

```erb
<span><%= wins %><%= t('stats.win_label') %></span>
```

With locale files defining `win_label: "W"` (English) and the appropriate localized equivalent, Rails `I18n.locale` selects the correct string automatically. The display adapts to the user's language without any view-layer conditionals.

This fix also introduced a discipline worth keeping: no hardcoded UI strings in templates. The moment a label goes through `t()`, the project gains free multi-language support for that string, and the locale file becomes a single source of truth for copy.

---

## 3. Role-Based Sidebar Navigation

The sidebar displayed "Tournament Management" and "Operations Workspace" sections to every user, including regular players who had no operational responsibilities.

### Implementation

Navigation items were moved into a constant array with an `admin_only` metadata flag. The rendering method filters the array before passing it to the view.

```ruby
SECONDARY_ITEMS = [
  { label_key: "nav.tournaments", path_helper: :tournaments_path,
    icon: :trophy, admin_only: true },
  { label_key: "nav.settings", path_helper: :app_settings_path,
    icon: :settings, admin_only: false }
].freeze

def secondary_navigation_items
  SECONDARY_ITEMS
    .reject { |item| item[:admin_only] && !admin_user? }
    .map { ... }
end
```

Declaring nav items as a constant array has two concrete advantages over scattered ERB conditionals. First, the complete list of navigation items is visible in one place — adding or removing an item does not require hunting through partial templates. Second, metadata like `admin_only` attaches naturally to each item definition rather than being encoded in a conditional wrapping the rendered HTML.

One important caveat: hiding UI elements based on role is not security. The same authorization check must exist at the controller or policy layer. A determined user can still request the URL directly regardless of what the sidebar shows.

---

## 4. Three-Tier Settings Page

The original settings page displayed an onboarding completion checklist to all users, including those who had completed their setup weeks earlier. The page was redesigned around three distinct tiers.

| Tier | Content |
|------|---------|
| **Guest** (unauthenticated) | Sign up / login CTA and contact info |
| **Player** | Profile editing (name, phone, NTRP rating), per-type notification toggles, beta info, sign out |
| **Admin** | All player features + statistics dashboard + admin shortcuts |

Notification preferences were split into individual, labeled toggles rather than a single on/off switch:

```erb
<% [
  [:push_match_reminder, "Match start alert", "When your match is about to begin"],
  [:push_court_assignment, "Court assignment alert", "When a court is assigned or changed"],
  [:push_match_result, "Match result alert", "When a result is confirmed"],
  [:push_score_entry, "Score entry request", "When you need to enter a score"]
].each do |field, label, desc| %>
  <label class="flex items-center justify-between py-3">
    <div>
      <p class="text-sm font-medium"><%= label %></p>
      <p class="text-xs text-gray-400"><%= desc %></p>
    </div>
    <%= form.check_box field, onchange: "this.form.requestSubmit()" %>
  </label>
<% end %>
```

`requestSubmit()` — rather than `submit()` — triggers the browser's native form submission event, which Turbo intercepts and converts into an AJAX request. The toggle saves instantly. A Turbo Stream response can update just the toggle's state without a full page reload.

The three-tier design reflects a genuine insight about settings pages: each user tier has a fundamentally different goal when they open settings. A guest wants to get started. A player wants to tune their notifications. An admin wants operational visibility. A single page trying to serve all three goals without any structure ends up serving none of them well.

---

## 5. Organizer Role as a Boolean Feature Flag

### The Problem

The application had exactly two roles: `player` and `admin`. There was no way to represent a user who creates and manages tournaments without granting them full platform admin access.

### Design Decision: Enum vs. Boolean

The most natural instinct is to add an `organizer` value to the existing enum. But organizers frequently **participate as players in their own tournaments**. An enum forces a choice between the two identities. A boolean flag allows both simultaneously.

```ruby
# Platform-level role — unchanged
enum :role, { player: 0, admin: 1 }

# Feature flag — additive, independent
add_column :users, :organizer, :boolean, default: false, null: false
```

The conceptual distinction is important: `admin` represents a level of platform-wide access, while `organizer` is a capability switch — it answers "can this user create tournaments?" rather than "who is this user on the platform?" Conflating the two into a single enum eventually creates cases that the enum cannot represent, such as a user who is both an organizer and a platform admin.

### Free Tier Limits

```ruby
module OrganizerLimits
  FREE_TIER = {
    max_players_per_tournament: 12,
    max_courts_per_tournament: 3,
    max_active_tournaments: 1
  }.freeze

  def can_create_tournament?
    return true if admin? || pro_access?
    return false unless organizer?
    active_tournament_count < FREE_TIER[:max_active_tournaments]
  end
end
```

Extracting limits into a concern keeps the constants in one place and makes the module independently testable. When a paid tier is added later, the change is isolated to this file.

### Registration Flow

The sign-up form now displays two selection cards (Player / Organizer) at the top. A Stimulus controller toggles a hidden field value and updates the card highlight state.

```javascript
// role_select_controller.js
select(event) {
  const value = event.currentTarget.dataset.value
  this.fieldTargets.forEach((f) => (f.value = value))
  this.cardTargets.forEach((card) => {
    card.classList.toggle("ring-2 ring-blue-500", card === event.currentTarget)
  })
}
```

Stimulus's `data-action` and `data-target` pattern decouples the controller from the HTML structure. The card layout can be restyled or restructured without touching the JavaScript, as long as the `data-role-select-target="card"` attribute is preserved.

---

## 6. Per-Tournament Staff Permissions

### The Problem

The `organizer` flag is account-level: it says "this user can create tournaments," but it says nothing about which tournaments they can manage. If organizer A invites user B to help run a specific tournament, the account-level flag would grant B unauthorized access to all of A's other tournaments.

### Solution: TournamentStaff Join Table

```ruby
create_table :tournament_staffs do |t|
  t.references :tournament, null: false
  t.references :user, null: false
  t.integer :role, null: false, default: 0  # owner(0) / manager(1) / referee(2)
  t.references :invited_by, null: true
  t.integer :status, null: false, default: 0  # active(0) / revoked(1)
end
```

| Role | Permissions |
|------|-------------|
| **Owner** | Everything, including staff management and tournament deletion |
| **Manager** | Players, brackets, courts, and matches |
| **Referee** | Score entry and match status changes |

The `invited_by` column serves an audit purpose: knowing who invited whom allows the ownership chain to be reconstructed later. The `status: revoked` state retains the record for the same reason — hard-deleting staff records makes it impossible to audit historical access.

The Pundit policy checks staff permissions first and falls back to the legacy `club_admin?` path:

```ruby
def update?
  return true if admin?
  return true if staff_can?(:can_edit_tournament_settings?)
  tournament_organizer?  # legacy fallback
end

def staff_record
  @staff_record ||= record.staff_for(user)
end

def staff_can?(permission)
  staff_record&.public_send(permission) || false
end
```

The `@staff_record` memoization prevents repeated database queries when multiple policy methods are called in a single request cycle — a commonly overlooked optimization in Pundit-based applications. The fallback chain (`staff_can?` then `tournament_organizer?`) ensures existing organizers retain their permissions during the migration period. Once the new staff system is fully adopted, the fallback can be removed.

---

## 7. Deduplicating Native App Buttons

The iOS app's `VisitableViewController` renders a native navigation bar that includes a bell icon for notifications. The web dashboard's navbar also rendered a bell icon. Inside the app, both were visible simultaneously — two bells, one action.

```erb
<% unless helpers.native_app_request? %>
  <%= link_to notification_path, class: "..." do %>
    <%= icon :bell %>
  <% end %>
<% end %>
```

The `native_app_request?` helper inspects the `User-Agent` header. Hotwire Native's iOS SDK appends `Turbo Native iOS` to the User-Agent string automatically.

```ruby
def native_app_request?
  request.user_agent.to_s.include?("Turbo Native")
end
```

This pattern extends beyond button deduplication. The native app already provides a tab bar, a navigation bar with back/forward gestures, and swipe-to-go-back behavior. Web HTML elements that replicate these affordances look out of place inside a native shell and should be conditionally hidden. For example, since the app has a native bottom tab bar, the HTML sidebar can be omitted entirely in the native context, freeing up vertical space for content.

The underlying principle is respecting the boundary between the web layer and the native shell. Hotwire Native works best when the web view provides content and the native layer provides navigation chrome — not when both try to handle navigation simultaneously.

---

## Takeaways

One small UI distortion triggered a full day of cascading fixes spanning layout, localization, navigation, permissions, and native/web deduplication. The patterns that kept emerging:

1. **Hotwire Native requires mobile-first views**: Responsive breakpoints are irrelevant inside WKWebView. Design for 375-390px and scale up for the browser, not the other way around.
2. **Separate account-level roles from resource-level permissions**: `user.organizer?` answers "can this user create tournaments?" — `TournamentStaff` answers "can this user manage this specific tournament?" These are different questions and should not share the same data structure.
3. **Audit columns are worth the extra migration**: `invited_by`, `status: revoked`, and created timestamps on join tables cost almost nothing at write time and provide enormous value when something goes wrong.
4. **`native_app_request?` is essential for shared views**: Any view that renders inside both a browser and a native WebView needs an escape hatch for native-only vs. web-only UI elements.
5. **`requestSubmit()` + Turbo for instant-save toggles**: This combination handles settings toggles cleanly with no custom JavaScript and no full page reload.

Rails + Hotwire + Tailwind handles this kind of incremental, cascading change well. Each individual fix was small. The discipline that made them manageable was keeping concerns cleanly separated: layout in the template, authorization in the policy, role definitions in the model concern, and native detection in a helper.

---

## Key Takeaways

| Problem Type | Core Pattern | When to Apply |
|---|---|---|
| WKWebView layout distortion | `max-w` 390px, no responsive grids, `min-w-0 truncate` | Authoring any Hotwire Native view |
| Mobile tooltip failure | Rails i18n locale labels instead of `title` attributes | Any text-based UI in a WebView |
| Navigation role gating | Constant array + `admin_only` metadata flag | Multi-role navigation |
| Role design (combinable identities) | Enum (platform role) + boolean (feature flag) | When a user needs more than one identity |
| Resource-scoped permissions | Join table (`tournament_staffs`) + Policy fallback | Invitation-based collaboration |
| Native/web UI duplication | `native_app_request?` User-Agent helper | Any shared view with native chrome |
| Instant-save toggles | `requestSubmit()` + Turbo Stream response | Settings pages with per-field saves |
