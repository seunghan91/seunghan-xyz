---
title: "Rails 8 + Hotwire Native 앱의 역할 기반 UI 분리와 모바일 최적화 삽질기"
date: 2026-03-17
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "WKWebView", "Tailwind", "i18n", "RBAC", "Stimulus"]
description: "데스크톱 레이아웃이 모바일 WebView에서 뭉개지는 문제부터, 역할 기반 네비게이션 분리, 운영진 권한 체계 설계까지 하루 동안의 삽질 기록"
categories: ["Hotwire Native", "iOS"]
series: ["Hotwire Native Mobile App"]
---

Rails 8 + Hotwire Native 조합으로 iOS 앱을 운영하는 중에, 하루 동안 발생한 여러 문제를 연쇄적으로 해결한 기록이다. 작은 UI 깨짐에서 시작해서 권한 체계 재설계까지 이어진 과정을 정리한다.

Hotwire Native의 핵심 매력은 하나의 Rails 앱으로 웹과 네이티브 iOS/Android를 동시에 지원한다는 점이다. 하지만 이 구조는 "웹에서 잘 보이면 앱에서도 잘 보인다"는 착각을 쉽게 심어준다. 실제로는 WKWebView의 렌더링 환경, 네이티브 네비게이션 바의 존재, 역할별 UI 분기 등 웹 브라우저와 전혀 다른 고려사항이 따라온다.

---

## 1. 모바일 WebView에서 카드 이미지가 뭉개지는 문제

### 증상

iOS 앱에서 대회 탐색 화면을 열면 카드의 배지/아이콘이 찌그러져 보였다. 웹 브라우저에서는 정상이었다.

### 원인

배포된 코드가 **데스크톱 레이아웃**(`max-w-[1400px]`, 반응형 그리드)으로 되어 있었는데, Hotwire Native의 WKWebView는 375px 폭이라 배너 영역의 뱃지들이 겹쳤다.

```erb
<!-- 문제: 데스크톱 기준 컨테이너 -->
<div class="mx-auto min-h-screen max-w-[1400px] px-4 py-6">
  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
```

WKWebView는 기본적으로 `viewport` 메타태그를 따르기 때문에 `width=device-width, initial-scale=1`로 설정되면 375px로 렌더링된다. 문제는 Tailwind의 `sm:` 브레이크포인트(640px)가 전혀 발동하지 않는다는 것이다. 결과적으로 최대 1400px을 가정한 레이아웃이 375px 안에 그대로 밀어 넣어진다.

### 해결

모바일 뷰포트 기준으로 재작성했다.

```erb
<!-- 수정: 390px 모바일 우선 -->
<div class="w-full mx-auto" style="max-width: min(390px, 100%);">
  <div class="space-y-3">
```

카드 내부도 배너 높이를 줄이고(`h-28` → `h-24`), 뱃지 폰트를 축소하고(`text-xs` → `text-[11px]`), `min-w-0` + `truncate`로 오버플로를 방지했다. `min-w-0`이 중요한 이유는, Flexbox 자식 요소는 기본값이 `min-width: auto`여서 내용물이 컨테이너를 밀어낼 수 있기 때문이다.

```erb
<div class="flex items-center min-w-0 gap-1">
  <span class="truncate text-[11px] font-medium">배지 텍스트</span>
</div>
```

**교훈**: Hotwire Native 앱이라면 뷰를 처음부터 모바일 뷰포트 기준으로 작성해야 한다. 반응형 그리드(`sm:grid-cols-2`)는 WKWebView 안에서 의미 없다. 웹과 앱 뷰를 공유한다면 처음부터 모바일 기준으로 설계하고, 데스크톱에서는 중앙 정렬 + 여백으로 대응하는 것이 낫다.

---

## 2. W/L 뱃지가 뭔지 모르겠는 문제

대시보드 상단 스탯 스트립에 `0W`, `0L`이라는 작은 뱃지가 있었는데, 한국 사용자 입장에서 의미를 바로 알 수 없었다.

### 시도 1: title tooltip

```erb
<span title="승리">0W</span>
```

데스크톱에서는 마우스 호버로 보이지만, **모바일 WebView에서는 tooltip이 동작하지 않는다**. iOS Safari와 WKWebView 모두 마우스 기반 `title` 속성 툴팁을 지원하지 않는다. Long press 제스처는 기본적으로 다른 동작(텍스트 선택, 컨텍스트 메뉴)에 연결되어 있다.

### 최종: 한글 라벨로 변경

```erb
<span><%= wins %><%= t('stats.win_label') %></span>
<!-- ko: "1승", en: "1W" -->
```

locale 파일에서 `win_label: "승"`, `loss_label: "패"`로 분리하니 어디서든 바로 이해 가능. Rails의 `I18n.locale`이 자동으로 적절한 번역을 선택하므로 한국어 앱에서는 "3승 1패", 영어권 앱에서는 "3W 1L"로 렌더링된다.

이 패턴은 UI 텍스트를 하드코딩하는 습관을 없애는 부수 효과도 있다. 로케일 파일에 값을 추가하는 순간, 다국어 지원을 처음부터 고려한 구조가 된다.

---

## 3. 역할 기반 사이드바 분리

사이드바에 "토너먼트 관리"와 "운영 워크스페이스" 패널이 모든 유저에게 보이고 있었다. 일반 선수에게는 불필요한 항목이었다.

### 구현

`SECONDARY_ITEMS`에 `admin_only` 플래그를 추가하고, SidebarComponent에 `admin` 파라미터를 전달했다.

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

네비게이션 항목을 상수 배열로 선언하면 두 가지 이점이 있다. 첫째, 항목 추가/삭제가 배열에만 집중된다. 둘째, `admin_only` 같은 메타데이터를 각 항목에 자연스럽게 붙일 수 있다. ERB 뷰 안에서 `<% if admin? %>` 분기를 반복하는 것보다 훨씬 유지보수하기 좋다.

사이드바 하단의 "운영 워크스페이스" 정보 패널도 `<% if admin? %>` 조건으로 감쌌다. 다만, 권한 체크가 뷰 레이어에만 있으면 보안 취약점이 된다. 실제 데이터와 기능은 반드시 컨트롤러(또는 Policy)에서도 보호해야 한다. 뷰의 조건은 "보여주지 않는 것"이지, "접근을 막는 것"이 아니다.

---

## 4. 설정 페이지 3계층 재구성

기존 설정 페이지는 "계정 설정 완료도" 같은 온보딩 카드가 있었는데, 이미 설정을 다 한 유저에게도 계속 보였다. 3계층으로 재설계했다.

| 계층 | 보이는 것 |
|------|----------|
| **게스트** (미로그인) | 회원가입/로그인 유도 + 연락처 |
| **일반 유저** | 프로필 편집(이름, 전화, NTRP), 알림 유형별 토글, 베타 정보, 로그아웃 |
| **관리자** | 위 전부 + 통계 대시보드 + 관리 바로가기 |

알림 설정은 단순 ON/OFF가 아니라 **유형별 토글**로 세분화했다:

```erb
<% [
  [:push_match_reminder, "경기 시작 알림", "내 경기가 곧 시작될 때"],
  [:push_court_assignment, "코트 배정 알림", "코트가 배정/변경될 때"],
  [:push_match_result, "경기 결과 알림", "결과 확정 시"],
  [:push_score_entry, "점수 입력 요청", "점수 입력이 필요할 때"]
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

`requestSubmit()`으로 토글 즉시 저장. Turbo가 폼을 인라인으로 처리한다. `requestSubmit()`은 `submit()`과 달리 브라우저의 네이티브 폼 제출 이벤트를 발생시키므로, Turbo가 가로채서 AJAX 요청으로 바꾼다. Turbo Stream 응답을 사용하면 페이지 전체를 새로 고치지 않고 해당 토글 상태만 업데이트할 수 있다.

설정 페이지를 계층으로 나누는 것은 단순히 "다른 게 보이는 것"이 아니다. 각 계층의 유저가 이 페이지에서 달성하려는 목표가 다르다는 것을 인정하는 설계다. 게스트는 "시작하고 싶다", 일반 유저는 "알림을 조정하고 싶다", 관리자는 "운영 현황을 파악하고 싶다". 하나의 페이지가 모든 역할을 위한 것이 되면 결국 모두에게 최적화되지 않는다.

---

## 5. 운영진(Organizer) 역할 도입

### 문제

기존 `User.role`은 `player(0)` / `admin(1)` 뿐이었다. 대회를 만드는 "운영진"과 참가하는 "선수"가 구분되지 않았다.

### 설계 결정: enum 확장 vs boolean 플래그

운영진이 자기 대회에 **선수로도 참가**하는 경우가 흔하다. enum을 `player/organizer/admin`으로 바꾸면 둘 중 하나만 가능하지만, boolean이면 둘 다 된다.

```ruby
# role은 플랫폼 레벨 (기존 유지)
enum :role, { player: 0, admin: 1 }

# organizer는 기능 플래그
add_column :users, :organizer, :boolean, default: false, null: false
```

이 결정의 핵심은 **"플랫폼 레벨 역할"과 "기능 플래그"를 분리**하는 것이다. `admin`은 플랫폼 전체에 대한 접근 권한을 의미하지만, `organizer`는 "대회를 만들 수 있는 기능을 활성화"하는 스위치다. 두 개념을 같은 enum에 섞으면 나중에 "운영진이면서 플랫폼 관리자"인 유저를 표현할 방법이 없어진다.

### 무료 티어 제한

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

제한 로직을 Concern으로 분리하면 여러 이점이 생긴다. 상수를 한 곳에서 관리할 수 있고, 테스트도 Concern 단독으로 작성할 수 있다. 나중에 Pro 티어가 추가될 때도 이 파일만 수정하면 된다.

### 회원가입 분기

가입 폼 상단에 역할 선택 카드 2개를 추가했다. Stimulus 컨트롤러로 hidden field 값을 토글한다.

```javascript
// role_select_controller.js
select(event) {
  const value = event.currentTarget.dataset.value
  this.fieldTargets.forEach((f) => (f.value = value))
  // 선택된 카드 하이라이트
  this.cardTargets.forEach((card) => {
    card.classList.toggle("ring-2 ring-blue-500", card === event.currentTarget)
  })
}
```

Stimulus의 `data-action`, `data-target` 패턴을 쓰면 JavaScript가 HTML 구조에 의존하지 않는다. 카드 레이아웃이 바뀌어도 `data-role-select-target="card"` 속성만 붙어 있으면 컨트롤러가 정상 작동한다.

---

## 6. 대회 단위 운영진 권한 (TournamentStaff)

### 문제

`user.organizer?`가 계정 레벨 플래그라서, A가 만든 대회에 초대된 B가 **다른 대회까지** 운영 권한을 갖는 문제가 생길 수 있었다.

### 해결: 대회별 스태프 테이블

```ruby
create_table :tournament_staffs do |t|
  t.references :tournament, null: false
  t.references :user, null: false
  t.integer :role, null: false, default: 0  # owner/manager/referee
  t.references :invited_by, null: true
  t.integer :status, null: false, default: 0  # active/revoked
end
```

| 역할 | 권한 |
|------|------|
| **Owner** | 전부 + 스태프 관리 + 대회 삭제 |
| **Manager** | 선수, 대진표, 코트, 경기 |
| **Referee** | 점수 입력, 경기 상태 변경 |

`invited_by` 컬럼은 감사(audit) 목적이다. 누가 누구를 초대했는지 추적할 수 있으면, 나중에 "왜 이 사람이 스태프인가?"를 재구성할 수 있다. `status: revoked` 상태도 레코드를 삭제하지 않고 유지하는 이유가 같다.

Policy에서 staff 권한을 먼저 체크하고, 없으면 기존 `club_admin?`으로 폴백한다:

```ruby
def update?
  return true if admin?
  return true if staff_can?(:can_edit_tournament_settings?)
  tournament_organizer?  # 기존 club_admin? 폴백
end

def staff_record
  @staff_record ||= record.staff_for(user)
end

def staff_can?(permission)
  staff_record&.public_send(permission) || false
end
```

`@staff_record` 메모이제이션이 중요하다. Policy 메서드가 여러 번 호출될 때마다 DB 쿼리가 발생하지 않도록 한다. Pundit 같은 Policy 라이브러리를 쓸 때 흔히 놓치는 최적화 포인트다.

폴백 구조(`staff_can? → tournament_organizer?`)는 마이그레이션 기간 동안 기존 유저들이 권한을 잃지 않도록 보장한다. 새 스태프 시스템으로 완전히 전환되면 폴백을 제거할 수 있다.

---

## 7. 네이티브 앱 버튼 중복 방지

iOS 앱은 Hotwire Native의 네이티브 네비게이션 바에 알림 bell 버튼이 있다. 웹 대시보드 navbar에도 같은 알림 버튼이 있어서, 앱에서 보면 bell이 2개 나오는 문제가 있었다.

```erb
<% unless helpers.native_app_request? %>
  <%# 웹에서만 알림/설정 버튼 표시 %>
  <%= link_to notification_path, ... %>
<% end %>
```

`native_app_request?`는 User-Agent에 `"Turbo Native"` 또는 앱 식별자가 포함되어 있는지 확인하는 헬퍼다. Hotwire Native iOS SDK는 기본적으로 User-Agent에 `Turbo Native iOS`를 추가한다.

```ruby
def native_app_request?
  request.user_agent.to_s.include?("Turbo Native")
end
```

이 패턴은 단순히 버튼을 숨기는 것 이상의 의미가 있다. Hotwire Native 앱에서는 네이티브 컴포넌트(탭 바, 네비게이션 바 버튼, 스와이프 제스처)를 활용하는 것이 앱스러운 경험을 만드는 핵심이다. 웹 뷰 안의 HTML 버튼과 네이티브 버튼이 중복되면 사용자는 혼란스럽고, 디자인도 어색해진다.

나아가 이 헬퍼로 모바일 앱에서만 다른 레이아웃을 적용할 수도 있다. 예를 들어 앱에서는 하단 네비게이션 바가 네이티브로 존재하므로, HTML 사이드바 자체를 숨기거나 축약할 수 있다.

---

## 정리

하루 동안 작은 UI 깨짐에서 시작해서 권한 체계까지 리팩토링이 이어졌다. 돌아보면 핵심은 세 가지였다:

1. **Hotwire Native = 모바일 퍼스트**: 반응형이 아니라 모바일 뷰포트 기준으로 뷰를 작성해야 한다
2. **역할은 계층별로 분리**: 계정 레벨(organizer 플래그)과 리소스 레벨(tournament_staff)은 별개의 관심사
3. **네이티브/웹 중복 체크**: Hotwire Native 앱이 래핑하는 웹 뷰에서 네이티브 UI와 겹치는 요소를 `native_app_request?`로 분기

작업량 자체는 많았지만, Rails + Hotwire + Tailwind 조합이 이런 연쇄적 수정에 꽤 유연하게 대응한다는 걸 다시 느꼈다.

---

## Key Takeaways

| 문제 유형 | 핵심 패턴 | 적용 시점 |
|-----------|-----------|-----------|
| WKWebView 레이아웃 깨짐 | `max-w` 390px, 반응형 그리드 제거, `min-w-0 truncate` | Hotwire Native 뷰 작성 시 |
| 모바일 tooltip 무효 | Rails i18n locale 라벨 분리 | 텍스트 UI 설계 시 |
| 네비게이션 권한 분기 | 상수 배열 + `admin_only` 플래그 패턴 | 다중 역할 앱 |
| 역할 설계 (조합 필요 시) | enum(플랫폼 역할) + boolean(기능 플래그) 분리 | 역할이 2개 이상 조합될 때 |
| 리소스 단위 권한 | TournamentStaff join table + Policy 폴백 | 초대 기반 협업 기능 |
| 네이티브/웹 UI 중복 | `native_app_request?` User-Agent 헬퍼 | Hotwire Native 공유 뷰 |
| 즉각 저장 토글 | `requestSubmit()` + Turbo Stream | 설정 페이지 UX |

Hotwire Native는 Rails 생태계 안에서 iOS/Android 앱을 빠르게 만들 수 있는 강력한 도구다. 단, 웹과 앱을 동시에 지원하는 구조인 만큼, 뷰와 권한 설계 단계에서 "이게 웹에서만 보이는가, 앱에서도 보이는가"를 항상 의식하는 것이 가장 중요하다.
