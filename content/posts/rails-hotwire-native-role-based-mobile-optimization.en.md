---
title: "Role-Based UI Separation and Mobile Optimization in a Rails 8 + Hotwire Native App"
date: 2026-03-17
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "WKWebView", "Tailwind", "i18n", "RBAC", "Stimulus"]
description: "From fixing distorted layouts in a mobile WebView to designing a per-tournament staff permission system — a day of cascading fixes"
---

Running an iOS app built with Rails 8 + Hotwire Native, I hit a series of issues in a single day. What started as a small UI distortion spiraled into a full permission system redesign. Here's the record.

---

## 1. Card Images Distorted in Mobile WebView

### Symptom

Tournament discovery cards looked fine in a desktop browser, but badges and icons were squished inside the iOS app's WKWebView (375px viewport).

### Root Cause

The deployed view used a **desktop-first layout** (`max-w-[1400px]`, responsive grid). The WKWebView rendered all of it in 375px, causing badge overlap.

```erb
<!-- Problem: desktop container -->
<div class="mx-auto min-h-screen max-w-[1400px] px-4 py-6">
  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
```

### Fix

Rewrote to mobile-first with a 390px max-width, single column, and reduced badge sizes.

```erb
<!-- Fixed: mobile-first -->
<div class="w-full mx-auto" style="max-width: min(390px, 100%);">
  <div class="space-y-3">
```

**Lesson**: With Hotwire Native, always design views for the mobile viewport first. Responsive grid breakpoints (`sm:`, `lg:`) are meaningless inside WKWebView.

---

## 2. Cryptic W/L Badges

The dashboard stats strip showed `0W` / `0L` badges — meaningless to Korean-speaking users.

Title tooltips (`title="Wins"`) don't work on mobile WebView. The fix was locale-aware labels:

```erb
<span><%= wins %><%= t('stats.win_label') %></span>
<!-- ko: "1승", en: "1W" -->
```

---

## 3. Role-Based Sidebar Navigation

The sidebar showed "Tournament Management" and "Operations Workspace" to all users, including regular players who had no use for them.

Added `admin_only` flags to navigation items and a conditional `admin?` check on the sidebar component:

```ruby
SECONDARY_ITEMS = [
  { label_key: "nav.tournaments", admin_only: true },
  { label_key: "nav.settings", admin_only: false }
]

def secondary_navigation_items
  SECONDARY_ITEMS
    .reject { |item| item[:admin_only] && !admin_user? }
    .map { ... }
end
```

---

## 4. Three-Tier Settings Page

Redesigned the settings page into three layers instead of a one-size-fits-all onboarding checklist:

| Tier | Content |
|------|---------|
| **Guest** | Sign up/login CTA + contact |
| **Player** | Profile editing, per-type notification toggles, sign out |
| **Admin** | All player features + stats dashboard + admin shortcuts |

Notification preferences were split into individual toggles (match start, court assignment, result, score entry) with instant save via `requestSubmit()`.

---

## 5. Organizer Role as Boolean Flag

### The Problem

Only two roles existed: `player` and `admin`. No way to distinguish tournament organizers from regular players.

### Design Decision

Since organizers frequently **play in their own tournaments**, a separate enum value would force choosing one or the other. A boolean flag allows both:

```ruby
enum :role, { player: 0, admin: 1 }  # platform level (unchanged)
add_column :users, :organizer, :boolean, default: false  # feature flag
```

Free tier limits enforced via a model concern:

```ruby
module OrganizerLimits
  FREE_TIER = {
    max_players_per_tournament: 12,
    max_courts_per_tournament: 3,
    max_active_tournaments: 1
  }.freeze
end
```

Registration form now shows two cards (Player / Organizer) with a Stimulus controller toggling a hidden field.

---

## 6. Per-Tournament Staff Permissions

### The Problem

The `organizer` flag is account-level. If organizer A invites user B to help manage a tournament, B shouldn't gain access to A's other tournaments.

### Solution: TournamentStaff Join Table

```ruby
create_table :tournament_staffs do |t|
  t.references :tournament
  t.references :user
  t.integer :role  # owner(0), manager(1), referee(2)
  t.references :invited_by, null: true
  t.integer :status  # active(0), revoked(1)
end
```

| Role | Permissions |
|------|-------------|
| **Owner** | Everything + staff management + delete |
| **Manager** | Players, brackets, courts, matches |
| **Referee** | Score entry, match status changes |

The policy checks staff permissions first, then falls back to the existing `club_admin?` path:

```ruby
def update?
  return true if admin?
  return true if staff_can?(:can_edit_tournament_settings?)
  tournament_organizer?  # legacy club_admin? fallback
end
```

---

## 7. Native App Button Deduplication

The iOS app has a native bell button in the navigation bar (via Hotwire Native's `VisitableViewController`). The web dashboard navbar also had a bell button — resulting in two bells in the app.

```erb
<% unless helpers.native_app_request? %>
  <%= link_to notification_path, ... %>
<% end %>
```

The `native_app_request?` helper checks the User-Agent for `"Turbo Native"` or app-specific identifiers.

---

## Takeaways

A single UI distortion cascaded into a full day of fixes spanning layout, localization, navigation, permissions, and native/web deduplication. Three key patterns emerged:

1. **Hotwire Native = mobile-first views**: Don't rely on responsive breakpoints inside WKWebView
2. **Separate account-level and resource-level roles**: `user.organizer?` (can create tournaments) vs `TournamentStaff` (can manage this specific tournament)
3. **Check for native/web overlap**: Use `native_app_request?` to hide web UI elements that duplicate native components
