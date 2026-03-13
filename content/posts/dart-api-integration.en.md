---
title: "DART Open API Integration Journey (Rails + Flutter)"
date: 2025-06-01
draft: false
tags: ["Rails", "Flutter", "DART", "PostgreSQL", "ActiveJob"]
description: "Migration errors, field name mismatches, and permission structure design while integrating Korea FSS DART Open API with a Rails backend."
cover:
  image: "/images/og/dart-api-integration.png"
  alt: "Dart Api Integration"
  hidden: true
---

Notes on integrating the [DART Open API](https://opendart.fss.or.kr) (Korea's Financial Supervisory Service disclosure system) with a Rails backend. Implemented 5 areas: disclosure monitoring, audit opinions, governance, financial indexes, and equity reports -- each step came with its own struggles.

---

## Implementation Structure

Created a model and ActiveJob for each data type. Each job calls the DART API and inserts data using `upsert_all` -- simple structure.

```
DartCorpCodeSyncJob     -> dart_companies      (company master)
DartDisclosureSyncJob   -> dart_disclosures    (disclosure list)
DartMajorEventSyncJob   -> dart_major_events   (delisting trigger events -- DS001)
DartAuditOpinionSyncJob -> dart_audit_opinions (audit opinions -- DS002/DS003)
DartGovernanceSyncJob   -> dart_executives / dart_major_shareholders (DS004/DS005)
DartFinancialIndexSyncJob -> dart_financial_indexes (fnlttSinglAcntAll)
DartEquityReportSyncJob -> dart_equity_reports (equity disclosures)
```

---

## Struggle 1: `upsert_all` + `update_only` + `updated_at` Duplication

The first error to hit.

```
PG::SyntaxError: ERROR: multiple assignments to same column "updated_at"
```

Rails 8's `upsert_all` **automatically adds** `updated_at` to the ON CONFLICT DO UPDATE clause beyond the columns specified in `update_only:`. If you also include `updated_at` in `update_only:`, the same column gets assigned twice, causing PostgreSQL to throw a syntax error.

```ruby
# Wrong - causes error
upsert_all rows, unique_by: :corp_code, update_only: [
  :corp_name, :stock_code, :updated_at   # <- here
]

# Correct - Rails handles updated_at automatically, don't specify it
upsert_all rows, unique_by: :corp_code, update_only: [
  :corp_name, :stock_code
]
```

This same mistake existed in 4 Jobs. When you find it in one place, always do a full audit of the rest.

---

## Struggle 2: API Response Fields Differ from Documentation

There were cases where the field names/formats in the DART API documentation didn't match the actual response.

### Executive Information -- Date and Category Fields

The docs showed short code values, but the actual response returned Korean text.

| Field | Expected | Actual API Response |
|-------|----------|-------------------|
| `birth_ym` | `"196203"` (6 chars) | `"1962년 03월"` (10 chars) |
| `rgit_exctv_at` | 1-char code | `"사내이사"` (inside director) |
| `fte_at` | 1-char code | `"상근"` / `"비상근"` (full-time/part-time) |

DB columns were set to `limit: 6`, which caused `PG::StringDataRightTruncation`.

```ruby
# Migration to fix column sizes
change_column :dart_executives, :birth_ym,      :string, limit: 20
change_column :dart_executives, :rgit_exctv_at, :string, limit: 20
change_column :dart_executives, :fte_at,        :string, limit: 10
```

There was also a key name typo in the Job code.

```ruby
# Wrong - typo
item["rgit_exctv_at"]

# Correct - actual API key
item["rgist_exctv_at"]
```

### Equity Reports -- Complete Field Name Mismatch

The equity report API had three keys that were all wrong compared to what I assumed.

| Key I Used | Actual API Key |
|-----------|---------------|
| `repror_nm` | `repror` |
| `stkqy_irds_rt` | `stkrt_irds` |
| `posesn_stock_qota_rt` | `stkrt` |

The `rcept_dt` column was also assumed to be `"20240101"` format (8 chars) with `limit: 8`, but the actual format was `"2024-03-22"` (10 chars). Extended to `limit: 12` and corrected column names with `rename_column`.

**Lesson**: With the DART API, always `curl` the actual response first to verify field names and data lengths before designing the schema.

---

## Struggle 3: Test Company Selection

Chose Samsung Electronics (`corp_code: 00126380`) for testing since it has rich data to help find errors.

```
dart_major_events       ->    6 records
dart_audit_opinions     ->   32 records
dart_major_shareholders ->  117 records
dart_executives         ->  134 records
dart_financial_indexes  ->  704 records
dart_equity_reports     -> 2713 records
```

DART API has a daily limit of 10,000 requests, so you need to consider rate limits when testing with high-volume data.

---

## Permission Structure Design -- Which Roles Should Have Access?

Initially placed everything under the admin namespace. During operation, realized that regular reviewers also need to check disclosures routinely, so restructured.

### Before

```ruby
# Inside Admin namespace, admin-only access
namespace :admin do
  resources :dart_monitoring, only: [:index, :show] do
    collection { post :sync }
  end
end
```

### After

```ruby
# Moved to root level, only sync remains admin-only
resources :dart_monitoring, only: [:index, :show] do
  collection { post :sync }
end
```

```ruby
class DartMonitoringController < ApplicationController
  before_action :ensure_staff!              # reviewer + admin: read access
  before_action :ensure_admin!, only: :sync # admin only: run sync

  def ensure_staff!
    return if current_user&.admin? || current_user&.reviewer?
    redirect_to root_path
  end
end
```

The Svelte pages were also moved from `Admin/DartMonitoring/` to `DartMonitoring/`.

### Sidebar Role-Based Branching

Since sidebar items differ by role, each case was handled explicitly. For "unassigned specialty" reviewers, there's logic to merge listing review + delisting review menus -- but simply concatenating arrays causes common items (DART, Calendar, Notifications) to appear twice.

```typescript
// Wrong - causes duplicates
return [...baseItems, ...listingItems, ...delistingItems, ...commonItems];

// Correct - extract common items and include only once
const dartItem = { name: 'DART Monitoring', href: '/dart_monitoring', ... };
const calendarItem = { ... };
const notifItem = { ... };

// For the unassigned case, compose directly
return [
  ...baseItems,
  { name: 'My Review List', ... },
  { name: 'Delisting Review', ... },
  { name: 'Review History & Stats', ... },
  dartItem,      // once only
  calendarItem,  // once only
  notifItem,     // once only
  ...commonItems,
];
```

---

## Flutter App Integration

Since the web controller uses Inertia rendering, it can't be used directly from mobile. Created a separate `Api::V1::DartMonitoringController` that returns the same data as JSON.

```ruby
# routes.rb
namespace :api do
  namespace :v1 do
    resources :dart_monitoring, only: [:index, :show]
  end
end
```

The Flutter page was kept simple with a `StatefulWidget + ApiClient(Dio)` pattern without BLoC. Tab switching re-fetches the tab data, and infinite scroll uses pagination.

```dart
Future<void> _loadTab(String tab, {bool loadMore = false}) async {
  final resp = await _api.get<Map<String, dynamic>>(
    '/api/v1/dart_monitoring',
    queryParameters: {'tab': tab, 'page': loadMore ? _currentPage : 1},
  );
  // ...
}
```

### Gotcha: Custom Widget Parameter Check

The project's `GlassCard` widget didn't have a `margin` parameter. Assumed it would and used it directly, which caused an analysis error.

```dart
// Wrong - parameter doesn't exist
GlassCard(
  margin: const EdgeInsets.only(bottom: 8),
  child: ...,
)

// Correct - wrap with Padding
Padding(
  padding: const EdgeInsets.only(bottom: 8),
  child: GlassCard(child: ...),
)
```

Latest Flutter also gave many `withOpacity` deprecated warnings. Need to use `withAlpha(38)` (= `0.15 * 255`) or `.withValues(alpha: 0.15)`.

---

## Overall Data Flow

```
[DART Open API]
     | (ActiveJob, periodic or manual sync)
[PostgreSQL]
  dart_companies, dart_disclosures, dart_financials,
  dart_major_events, dart_audit_opinions,
  dart_major_shareholders, dart_executives, dart_equity_reports
     |
[Rails Controllers]
  Web:    DartMonitoringController       -> Inertia/Svelte (reviewers + admin)
  Mobile: Api::V1::DartMonitoringController -> JSON
     |
[Frontend]
  Web:    Index.svelte  (tabbed dashboard: overview/disclosures/events/audit opinions/company status/equity)
          Show.svelte   (company detail: disclosures, financials, governance, etc.)
  Mobile: DartMonitoringPage       (tab list)
          DartMonitoringDetailPage (company detail)
```

---

## Summary

- Never include `updated_at` in the `update_only:` array of `upsert_all`
- Trust actual DART API responses over documentation (verify with curl first)
- Set generous `limit` for date/category columns (Korean text may come instead of short codes)
- When changing permissions, update routes, controllers, frontend, and sidebar all at once
- Check custom widget parameter definitions before using them
