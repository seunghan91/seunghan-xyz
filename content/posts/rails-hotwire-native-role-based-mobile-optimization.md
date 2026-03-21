---
title: "Rails 8 + Hotwire Native 앱의 역할 기반 UI 분리와 모바일 최적화 삽질기"
date: 2026-03-17
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "WKWebView", "Tailwind", "i18n", "RBAC", "Stimulus"]
description: "데스크톱 레이아웃이 모바일 WebView에서 뭉개지는 문제부터, 역할 기반 네비게이션 분리, 운영진 권한 체계 설계까지 하루 동안의 삽질 기록"
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

Rails 8 + Hotwire Native 조합으로 iOS 앱을 운영하는 중에, 하루 동안 발생한 여러 문제를 연쇄적으로 해결한 기록이다. 작은 UI 깨짐에서 시작해서 권한 체계 재설계까지 이어진 과정을 정리한다.

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

### 해결

모바일 뷰포트 기준으로 재작성했다.

```erb
<!-- 수정: 390px 모바일 우선 -->
<div class="w-full mx-auto" style="max-width: min(390px, 100%);">
  <div class="space-y-3">
```

카드 내부도 배너 높이를 줄이고(`h-28` → `h-24`), 뱃지 폰트를 축소하고(`text-xs` → `text-[11px]`), `min-w-0` + `truncate`로 오버플로를 방지했다.

**교훈**: Hotwire Native 앱이라면 뷰를 처음부터 모바일 뷰포트 기준으로 작성해야 한다. 반응형 그리드(`sm:grid-cols-2`)는 WKWebView 안에서 의미 없다.

---

## 2. W/L 뱃지가 뭔지 모르겠는 문제

대시보드 상단 스탯 스트립에 `0W`, `0L`이라는 작은 뱃지가 있었는데, 한국 사용자 입장에서 의미를 바로 알 수 없었다.

### 시도 1: title tooltip

```erb
<span title="승리">0W</span>
```

데스크톱에서는 마우스 호버로 보이지만, **모바일 WebView에서는 tooltip이 동작하지 않는다**.

### 최종: 한글 라벨로 변경

```erb
<span><%= wins %><%= t('stats.win_label') %></span>
<!-- ko: "1승", en: "1W" -->
```

locale 파일에서 `win_label: "승"`, `loss_label: "패"`로 분리하니 어디서든 바로 이해 가능.

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

사이드바 하단의 "운영 워크스페이스" 정보 패널도 `<% if admin? %>` 조건으로 감쌌다.

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

`requestSubmit()`으로 토글 즉시 저장. Turbo가 폼을 인라인으로 처리한다.

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

### 회원가입 분기

가입 폼 상단에 역할 선택 카드 2개를 추가했다. Stimulus 컨트롤러로 hidden field 값을 토글한다.

```javascript
// role_select_controller.js
select(event) {
  const value = event.currentTarget.dataset.value
  this.fieldTargets.forEach((f) => (f.value = value))
  // 선택된 카드 하이라이트
}
```

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

---

## 7. 네이티브 앱 버튼 중복 방지

iOS 앱은 Hotwire Native의 네이티브 네비게이션 바에 알림 bell 버튼이 있다. 웹 대시보드 navbar에도 같은 알림 버튼이 있어서, 앱에서 보면 bell이 2개 나오는 문제가 있었다.

```erb
<% unless helpers.native_app_request? %>
  <%# 웹에서만 알림/설정 버튼 표시 %>
  <%= link_to notification_path, ... %>
<% end %>
```

`native_app_request?`는 User-Agent에 `"Turbo Native"` 또는 앱 식별자가 포함되어 있는지 확인하는 헬퍼다.

---

## 정리

하루 동안 작은 UI 깨짐에서 시작해서 권한 체계까지 리팩토링이 이어졌다. 돌아보면 핵심은 세 가지였다:

1. **Hotwire Native = 모바일 퍼스트**: 반응형이 아니라 모바일 뷰포트 기준으로 뷰를 작성해야 한다
2. **역할은 계층별로 분리**: 계정 레벨(organizer 플래그)과 리소스 레벨(tournament_staff)은 별개의 관심사
3. **네이티브/웹 중복 체크**: Hotwire Native 앱이 래핑하는 웹 뷰에서 네이티브 UI와 겹치는 요소를 `native_app_request?`로 분기

작업량 자체는 많았지만, Rails + Hotwire + Tailwind 조합이 이런 연쇄적 수정에 꽤 유연하게 대응한다는 걸 다시 느꼈다.
