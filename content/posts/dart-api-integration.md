---
title: "DART Open API 연동 삽질기 (Rails + Flutter)"
date: 2026-02-24
draft: false
tags: ["Rails", "Flutter", "DART", "PostgreSQL", "ActiveJob"]
description: "금융감독원 DART Open API를 Rails 백엔드에 붙이면서 겪은 마이그레이션 오류, 필드명 불일치, 권한 구조 설계까지 정리"
---

[DART Open API](https://opendart.fss.or.kr)를 Rails 백엔드에 연동하면서 겪은 과정을 정리한다.
공시 모니터링, 감사의견, 지배구조, 재무지표, 지분공시 5개 영역을 구현했고 각 단계마다 삽질이 있었다.

---

## 구현 구조

각 데이터 유형마다 모델과 ActiveJob을 하나씩 만들었다.
Job은 DART API를 호출해서 `upsert_all`로 DB에 넣는 단순한 구조다.

```
DartCorpCodeSyncJob     → dart_companies      (기업 마스터)
DartDisclosureSyncJob   → dart_disclosures    (공시 목록)
DartMajorEventSyncJob   → dart_major_events   (상장폐지 트리거 이벤트 — DS001)
DartAuditOpinionSyncJob → dart_audit_opinions (감사의견 — DS002/DS003)
DartGovernanceSyncJob   → dart_executives / dart_major_shareholders (DS004/DS005)
DartFinancialIndexSyncJob → dart_financial_indexes (fnlttSinglAcntAll)
DartEquityReportSyncJob → dart_equity_reports (지분공시)
```

---

## 삽질 1: `upsert_all` + `update_only` + `updated_at` 중복

가장 먼저 터진 오류.

```
PG::SyntaxError: ERROR: multiple assignments to same column "updated_at"
```

Rails 8의 `upsert_all`은 `update_only:`에 명시한 컬럼 외에 `updated_at`을 ON CONFLICT DO UPDATE 절에 **자동으로 추가**한다.
`update_only:`에 `updated_at`을 같이 넣으면 같은 컬럼이 두 번 할당되어 PostgreSQL이 문법 오류로 뻗는다.

```ruby
# ❌ 오류 발생
upsert_all rows, unique_by: :corp_code, update_only: [
  :corp_name, :stock_code, :updated_at   # ← 여기
]

# ✅ updated_at은 Rails가 자동 처리, 명시하지 않아야 함
upsert_all rows, unique_by: :corp_code, update_only: [
  :corp_name, :stock_code
]
```

이 실수가 4개 Job에 동일하게 있었다. 한 곳에서 발견하면 나머지도 반드시 전수 확인해야 한다.

---

## 삽질 2: API 응답 필드가 문서와 다름

DART API 문서에 적힌 필드명/형식과 실제 응답이 다른 경우가 있었다.

### 임원 정보 — 날짜·구분 필드

문서에는 짧은 코드값처럼 나와 있지만 실제 응답은 한글 텍스트.

| 필드 | 예상 | 실제 API 응답 |
|------|------|--------------|
| `birth_ym` | `"196203"` (6자) | `"1962년 03월"` (10자) |
| `rgit_exctv_at` | 1자 코드 | `"사내이사"` |
| `fte_at` | 1자 코드 | `"상근"` / `"비상근"` |

DB 컬럼을 `limit: 6`으로 잡았다가 `PG::StringDataRightTruncation`이 터졌다.

```ruby
# 마이그레이션으로 컬럼 크기 수정
change_column :dart_executives, :birth_ym,      :string, limit: 20
change_column :dart_executives, :rgit_exctv_at, :string, limit: 20
change_column :dart_executives, :fte_at,        :string, limit: 10
```

Job 코드에 키 이름 오타도 있었다.

```ruby
# ❌ 오타
item["rgit_exctv_at"]

# ✅ 실제 API 키
item["rgist_exctv_at"]
```

### 지분공시 — 필드명 전면 불일치

지분공시 API는 내가 가정한 키와 실제 응답 키가 세 개 다 틀렸다.

| 내가 쓴 키 | 실제 API 키 |
|-----------|-----------|
| `repror_nm` | `repror` |
| `stkqy_irds_rt` | `stkrt_irds` |
| `posesn_stock_qota_rt` | `stkrt` |

`rcept_dt` 컬럼도 `"20240101"` 형식(8자)으로 생각하고 `limit: 8`로 잡았는데, 실제로는 `"2024-03-22"` 형식(10자)이 온다. `limit: 12`로 늘리고 컬럼명도 `rename_column`으로 정정했다.

**교훈**: DART API는 실제 응답을 `curl`로 먼저 찍어보고 필드명·데이터 길이를 확인한 뒤 스키마를 설계해야 한다.

---

## 삽질 3: 테스트 기업 선택

데이터가 풍부해야 오류를 찾기 좋아서 삼성전자(`corp_code: 00126380`)로 테스트했다.

```
dart_major_events       →    6건
dart_audit_opinions     →   32건
dart_major_shareholders →  117건
dart_executives         →  134건
dart_financial_indexes  →  704건
dart_equity_reports     → 2713건
```

DART API는 일 1만 건 제한이 있어서 건수가 많은 테스트는 Rate Limit을 고려해야 한다.

---

## 권한 구조 설계 — 어떤 역할이 볼 수 있어야 하나

처음엔 관리자 네임스페이스에 넣었다. 운영하면서 일반 심사역도 공시를 일상적으로 확인해야 한다는 걸 깨달아서 구조를 바꿨다.

### 변경 전

```ruby
# Admin 네임스페이스 안에서 admin만 접근
namespace :admin do
  resources :dart_monitoring, only: [:index, :show] do
    collection { post :sync }
  end
end
```

### 변경 후

```ruby
# 루트 레벨로 이동, 동기화만 admin 전용
resources :dart_monitoring, only: [:index, :show] do
  collection { post :sync }
end
```

```ruby
class DartMonitoringController < ApplicationController
  before_action :ensure_staff!              # reviewer + admin: 읽기
  before_action :ensure_admin!, only: :sync # admin만: 동기화 실행

  def ensure_staff!
    return if current_user&.admin? || current_user&.reviewer?
    redirect_to root_path
  end
end
```

Svelte 페이지도 `Admin/DartMonitoring/` 디렉토리에서 `DartMonitoring/`으로 이동했다.

### 사이드바 역할별 분기

역할에 따라 사이드바 항목이 달라지는 구조라 각 케이스를 명시적으로 처리했다.
"전문분야 미지정" 심사역의 경우 상장심사 메뉴 + 상폐심사 메뉴를 합치는 로직이 있는데,
그냥 배열을 concat하면 공통 항목(DART, 캘린더, 알림)이 두 번 나온다.

```typescript
// ❌ 중복 발생
return [...baseItems, ...listingItems, ...delistingItems, ...commonItems];

// ✅ 공통 항목 변수로 추출 후 명시적으로 1회만 포함
const dartItem = { name: 'DART 모니터링', href: '/dart_monitoring', ... };
const calendarItem = { ... };
const notifItem = { ... };

// listingItems, delistingItems 각각에 dartItem 포함시키되
// 미지정 케이스에서는 직접 조합
return [
  ...baseItems,
  { name: '내 검토 목록', ... },
  { name: '상장폐지 심사', ... },
  { name: '심사내역&통계', ... },
  dartItem,      // 1번만
  calendarItem,  // 1번만
  notifItem,     // 1번만
  ...commonItems,
];
```

---

## Flutter 앱 반영

웹 컨트롤러가 Inertia 렌더링이라 모바일에서 직접 쓸 수 없다.
`Api::V1::DartMonitoringController`를 별도로 만들고 동일한 데이터를 JSON으로 반환했다.

```ruby
# routes.rb
namespace :api do
  namespace :v1 do
    resources :dart_monitoring, only: [:index, :show]
  end
end
```

Flutter 페이지는 BLoC 없이 `StatefulWidget + ApiClient(Dio)` 패턴으로 단순하게 구성했다.
탭 전환 시 해당 탭 데이터를 다시 fetch하고, 무한 스크롤은 pagination으로 처리했다.

```dart
Future<void> _loadTab(String tab, {bool loadMore = false}) async {
  final resp = await _api.get<Map<String, dynamic>>(
    '/api/v1/dart_monitoring',
    queryParameters: {'tab': tab, 'page': loadMore ? _currentPage : 1},
  );
  // ...
}
```

### 삽질: 커스텀 위젯 파라미터 확인

프로젝트에서 쓰는 `GlassCard` 위젯에 `margin` 파라미터가 없었다.
당연히 있을 거라 생각하고 바로 썼다가 분석 오류가 떴다.

```dart
// ❌ 파라미터 없음
GlassCard(
  margin: const EdgeInsets.only(bottom: 8),
  child: ...,
)

// ✅ Padding으로 감싸기
Padding(
  padding: const EdgeInsets.only(bottom: 8),
  child: GlassCard(child: ...),
)
```

Flutter 최신 버전에서 `withOpacity` deprecated 경고도 많이 나왔다.
`withAlpha(38)` (= `0.15 * 255`) 또는 `.withValues(alpha: 0.15)`를 써야 한다.

---

## 전체 데이터 흐름

```
[DART Open API]
     ↓ (ActiveJob, 주기적 or 수동 sync)
[PostgreSQL]
  dart_companies, dart_disclosures, dart_financials,
  dart_major_events, dart_audit_opinions,
  dart_major_shareholders, dart_executives, dart_equity_reports
     ↓
[Rails Controllers]
  Web:    DartMonitoringController       → Inertia/Svelte (심사역+관리자)
  Mobile: Api::V1::DartMonitoringController → JSON
     ↓
[Frontend]
  Web:    Index.svelte  (탭 대시보드: 개요/공시/이벤트/감사의견/기업현황/지분공시)
          Show.svelte   (기업 상세: 공시·재무·지배구조 등)
  Mobile: DartMonitoringPage       (탭 목록)
          DartMonitoringDetailPage (기업 상세)
```

---

## 요약

- `upsert_all`의 `update_only:` 배열에 `updated_at` 절대 넣지 말 것
- DART API 필드명은 문서보다 실제 응답을 믿을 것 (curl로 먼저 확인)
- 날짜·구분 컬럼 `limit`은 넉넉하게 잡을 것 (코드값이 아니라 한글 텍스트가 올 수 있음)
- 권한 변경 시 라우트·컨트롤러·프론트엔드·사이드바를 전부 찾아서 일괄 수정할 것
- 커스텀 위젯 쓰기 전에 파라미터 정의를 먼저 확인할 것
