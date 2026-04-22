---
title: "Rails 8 Hotwire 실전 삽질기 — DnD 배정, N+1 자동 감지, 테마별 Favicon"
date: 2026-03-21
draft: false
tags: ["Rails 8", "Hotwire", "Turbo Stream", "Stimulus", "N+1", "Prosopite", "DnD", "Favicon", "iOS"]
description: "Turbo Stream + Stimulus로 드래그앤드롭 선수 배정을 구현하면서 겪은 DOM 교체 후 이벤트 소실, 121 쿼리 N+1 문제 발견과 Prosopite 도입, 그리고 테마별 동적 Favicon/앱 아이콘 연동까지의 기록"
categories: ["iOS", "Rails"]
---

Rails 8 + Hotwire로 실시간 토너먼트 대시보드를 만들면서 하루 동안 겪은 3가지 삽질과 해결 과정. 이 문제들은 엣지 케이스가 아니라, Hotwire 프로그래밍 모델이 런타임에서 드러내는 자연스러운 마찰 지점들이다.

---

## 1. Turbo Stream + Stimulus DnD: DOM 교체 후 이벤트가 사라진다

### 문제

선수 칩을 코트 카드에 드래그하면 서버에 POST → Turbo Stream으로 코트 카드와 선수 목록을 교체하는 구조를 만들었다.

첫 번째 드래그는 잘 된다. **두 번째부터 아무 반응이 없다.** 이벤트도, 요청도, 응답도 없다.

Hotwire에서 가장 당혹스러운 버그 유형 중 하나다. DOM에는 모든 요소가 있고, `data-controller` 속성도 붙어 있고, Stimulus 컨트롤러도 등록돼 있다. 그런데 아무것도 실행되지 않는다.

### 원인

Stimulus 컨트롤러는 `connect()`에서 이벤트 리스너를 등록한다. Turbo Stream이 DOM 일부를 교체하면, 기존 요소와 그에 달린 리스너가 함께 버려진다. 서버가 새로 렌더링한 요소는 초기 상태 — `dragstart`, `dragover`, `drop` 핸들러가 전혀 없는 상태 — 로 시작한다.

잘못된 패턴:

```javascript
// DOM 교체 후 리스너 소실 — 두 번째 드래그 불가
connect() {
  this.chipTargets.forEach(chip => {
    chip.addEventListener("dragstart", this.dragStart.bind(this))
  })
}
```

Turbo Stream이 실행된 뒤 `this.chipTargets`는 여전히 새 DOM 노드를 반환한다. 하지만 그 노드들에는 핸들러가 없다.

### 해결: targetConnected 라이프사이클 + 이중 방어

Stimulus 3.x는 타겟 라이프사이클 콜백을 제공한다. `[target]TargetConnected(element)`는 해당 타겟이 DOM에 추가될 때마다 호출된다 — Turbo Stream 교체 이후도 포함해서. 이 훅이 핵심이다.

다만 일부 환경(Safari, 구버전 Hotwire)에서는 `targetConnected`가 초기 `connect()` 시점에 신뢰성 있게 발화하지 않는다. 안전한 방법은 두 곳 모두에서 셋업 함수를 호출하는 것이다:

```javascript
connect() {
  this._boundDragStart = this.dragStart.bind(this)
  this._boundDragOver  = this.dragOver.bind(this)
  this._boundDrop      = this.drop.bind(this)
  // 이미 DOM에 있는 타겟 직접 셋업 (fallback)
  this.chipTargets.forEach(chip => this._setupChip(chip))
}

// 새 타겟이 DOM에 추가될 때 자동 호출
chipTargetConnected(chip) {
  this._setupChip(chip)
}

chipTargetDisconnected(chip) {
  this._teardownChip(chip)
}

_setupChip(chip) {
  if (chip.dataset.dragBound) return  // 중복 바인딩 방지
  chip.dataset.dragBound = "1"
  chip.setAttribute("draggable", "true")
  chip.addEventListener("dragstart", this._boundDragStart)
}

_teardownChip(chip) {
  chip.removeEventListener("dragstart", this._boundDragStart)
  delete chip.dataset.dragBound
}
```

`dragBound` 데이터셋 플래그는 `connect()`와 `targetConnected`가 같은 요소에 대해 모두 발화하는 경우를 막는다. `_teardownChip`은 Turbo Stream이 요소를 제거할 때 메모리 누수를 방지한다.

### 또 다른 함정: Turbo Stream replace 후 ID 소실

테스트 중에 두 번째 버그가 발견됐다. 첫 번째 드래그는 성공하는데, 두 번째 드래그에서 Turbo Stream 응답이 교체할 요소를 찾지 못한다는 다른 오류가 발생했다.

원인: `turbo_stream.replace("player-list-container", partial: "player_list")`는 첫 번째 인자와 `id`가 일치하는 요소를 교체한다. 그런데 렌더링되는 partial의 루트 요소에 그 `id`가 없으면, 첫 번째 replace 이후 DOM에서 해당 `id`가 사라진다. 두 번째 replace는 타겟을 찾지 못한다.

```erb
<%# 잘못된 예: partial 루트에 id 없음 — 첫 교체 후 id 소멸 %>
<div class="flex items-center gap-2">
  <% @players.each do |p| %>
    ...
  <% end %>
</div>

<%# 올바른 예: partial이 타겟 요소 자체를 포함 %>
<div id="player-list-container">
  <div class="flex items-center gap-2">
    <% @players.each do |p| %>
      ...
    <% end %>
  </div>
</div>
```

**규칙:** `turbo_stream.replace`에 넘기는 `id`는 partial 내부의 최외곽 요소에 있어야 한다. Turbo Stream은 해당 id를 가진 요소를 렌더링된 partial로 교체한다. partial이 그 id를 다시 출력하지 않으면 DOM은 핸들을 영구적으로 잃는다.

### 왜 발견하기 어려운가

두 버그 모두 수동 smoke test를 통과한다. 첫 드래그가 성공하기 때문에 빠른 테스트는 통과 결과를 낸다. 두 번째 상호작용 — 또는 두 번의 드래그를 체이닝하는 자동화 테스트 — 에서야 문제가 드러난다. `targetConnected` 훅 추가와 partial ID 검증은 Hotwire DnD 구현 체크리스트에 반드시 포함돼야 한다.

---

## 2. 페이지 하나에서 121 쿼리: 사용자보다 먼저 N+1 잡는 법

### 문제

대시보드의 경기 탭으로 이동할 때 체감상 느리다는 피드백이 들어왔다. 에러도, 타임아웃도 아닌 그냥 눈에 띄는 지연. Rails 로그가 원인을 확인해줬다:

```
Completed 200 OK in 340ms (Views: 165ms | ActiveRecord: 104ms (121 queries, 40 cached))
```

단일 페이지 렌더링에 데이터베이스 쿼리 121개. 캐시된 40개를 제외해도 실제 왕복이 81회, ActiveRecord 시간만 104ms였다.

### 원인: 서비스 객체 내 선수별 개별 쿼리

대시보드는 서비스 객체를 사용해 선수별 통계를 계산했다. 구현은 각 선수 모델 객체의 인스턴스 메서드를 호출하는 방식이었다:

```ruby
# N+1: 각 메서드 호출이 선수마다 1개 이상의 SQL 쿼리 발생
player_stats = players.map do |player|
  {
    matches_played: player.completed_matches_count,  # SELECT COUNT(*)
    wins:           player.wins_count,               # match_players 로드 후 이터레이션
    losses:         player.losses_count,             # 별도 COUNT
    win_rate:       player.win_rate,                 # wins + matches 재호출
  }
end
```

선수 11명 × 4쿼리 = 44개 추가 쿼리. 페이지의 다른 부분에서 유사한 패턴이 반복되어 총 121개에 이르렀다.

### 즉각 해결: 이미 로드된 데이터로 메모리 집계

matches와 `match_players` 연관관계는 서비스 객체 앞부분에서 이미 로드돼 있었다. 선수마다 쿼리를 날리는 대신, 이미 로드된 데이터를 단일 패스로 순회하면 추가 쿼리 없이 모든 통계를 계산할 수 있다:

```ruby
player_match_counts = Hash.new(0)
player_win_counts   = Hash.new(0)

# 이미 로드된 completed_matches 순회 — 추가 쿼리 0
completed_matches.each do |match|
  team_a_ids = match.match_players.select(&:team_a?).map(&:participant_id)
  team_b_ids = match.match_players.select(&:team_b?).map(&:participant_id)

  (team_a_ids + team_b_ids).each { |pid| player_match_counts[pid] += 1 }

  winner_ids = match.winner_team == "team_a" ? team_a_ids : team_b_ids
  winner_ids.each { |pid| player_win_counts[pid] += 1 }
end

player_stats = players.map do |player|
  matches = player_match_counts[player.id]
  wins    = player_win_counts[player.id]
  {
    matches_played: matches,
    wins:           wins,
    losses:         matches - wins,
    win_rate:       matches > 0 ? (wins.to_f / matches * 100).round(1) : 0,
  }
end
```

결과: 선수별 44개 쿼리가 0으로 줄었다. 페이지 전체 쿼리가 121개에서 약 12개로 감소하고, 응답 시간은 340ms에서 80ms 이하로 떨어졌다.

### 근본 해결: Prosopite로 자동 감지

메모리 집계가 이번 N+1을 해결했다. 하지만 근본 문제는 그대로다. **N+1 버그는 누군가 "느리다"고 말해야 발견된다.** 개발 워크플로우에서 그건 용납하기 어렵다. 답은 모든 요청에서 자동 감지다.

[Prosopite](https://github.com/charkost/prosopite)는 개발 환경에서 ActiveRecord를 계측해 N+1 패턴을 감지한다. [Bullet](https://github.com/flyerhzm/bullet)은 연관관계 로딩 휴리스틱 기반이라 false positive가 발생한다. Prosopite는 call stack당 쿼리 fingerprint를 추적하는 방식이다. 완전히 동일한 쿼리(같은 fingerprint)가 같은 call stack 위치에서 설정된 최솟값 이상 반복될 때만 보고한다. false positive가 없고 알림 피로도 없다.

설정은 4단계:

```ruby
# Gemfile
group :development do
  gem "prosopite"
end
```

```ruby
# config/environments/development.rb
config.after_initialize do
  Prosopite.rails_logger = true   # N+1 경고가 development.log에 출력
  Prosopite.raise = false         # true로 바꾸면 N+1 발생 시 요청 자체가 실패
  Prosopite.min_n_queries = 2     # 2회 이상 반복되면 플래그
end
```

```ruby
# app/controllers/application_controller.rb
around_action :prosopite_scan, if: -> { Rails.env.development? }

private

def prosopite_scan
  Prosopite.scan
  yield
ensure
  Prosopite.finish
end
```

이제 모든 컨트롤러 액션이 자동으로 스캔된다. N+1 패턴은 즉시 로그에 나타난다:

```
[Prosopite] N+1 queries detected:
  SELECT "match_players".* FROM "match_players" WHERE "match_players"."match_id" = $1
  ↳ app/models/match.rb:34:in `wins_count'
  Called 11 times from app/services/player_stats_service.rb:22
```

소스 파일과 라인 번호까지 명시된다. N+1 발견 과정이 "사용자가 느리다고 보고 → 수동 로그 조사 → 쿼리 이분법"에서 "로그 열기, 경고 읽기, 해당 줄 수정"으로 바뀐다.

```bash
# 세션 중 경고 확인
grep 'Prosopite' log/development.log
```

---

## 3. 테마별 동적 Favicon + iOS 앱 아이콘

### 문제

앱은 여러 비주얼 테마를 지원한다 — 각각 고유한 색상 팔레트를 가진다. CSS 변수는 테마 변경 즉시 업데이트된다. 그런데 브라우저 탭 favicon은 기본 아이콘 그대로다. iOS 앱(Hotwire Native)의 홈 화면 아이콘도 마찬가지다.

개별로는 낮은 우선순위 이슈지만, 합쳐지면 문제가 된다. UI는 바뀌는데 정체성 표식은 따라오지 않는다.

### 해결 1: JavaScript로 SVG Favicon 동적 생성

자연스러운 첫 시도는 SVG favicon에 CSS 변수를 쓰는 것이다. 이건 동작하지 않는다. SVG favicon은 별도 브라우저 컨텍스트에서 렌더링되며, 페이지의 CSS custom property에 접근할 수 없다. favicon SVG 안의 `var(--color-primary)`는 아무것도 아닌 것으로 resolve된다.

올바른 접근은 JavaScript에서 resolved 색상값으로 SVG 콘텐츠를 직접 생성하고, 그 문자열로 Blob을 만들고, favicon `<link>` 요소의 `href`를 Blob URL로 교체하는 것이다:

```javascript
// theme_controller.js (Stimulus)
const THEME_COLORS = {
  "default":   { bg: "#047857", stroke: "#ecfdf5" },
  "wimbledon": { bg: "#522398", stroke: "#f5f0ff" },
  "us-open":   { bg: "#003DA5", stroke: "#eef3ff" },
  "hardcourt": { bg: "#c05e1a", stroke: "#fff7ed" },
}

_updateFavicon(theme) {
  const colors = THEME_COLORS[theme] ?? THEME_COLORS["default"]

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
    <rect width="512" height="512" rx="96" fill="${colors.bg}"/>
    <circle cx="256" cy="256" r="120" fill="none" stroke="${colors.stroke}" stroke-width="24"/>
    <line x1="136" y1="256" x2="376" y2="256" stroke="${colors.stroke}" stroke-width="24"/>
    <line x1="256" y1="136" x2="256" y2="376" stroke="${colors.stroke}" stroke-width="24"/>
  </svg>`

  const blob = new Blob([svg], { type: "image/svg+xml" })
  const url  = URL.createObjectURL(blob)

  const link = document.querySelector('link[rel="icon"][type="image/svg+xml"]')
  if (!link) return

  // 이전 Blob URL 해제 — 메모리 누수 방지
  if (link.dataset.blobUrl) URL.revokeObjectURL(link.dataset.blobUrl)

  link.href = url
  link.dataset.blobUrl = url
}
```

초기 로딩 시 깜빡임 방지를 위해 `<head>` 인라인 스크립트에서도 동일한 로직을 실행한다. 페이지 렌더 전에 동기적으로 실행되므로 favicon 플래시가 없다:

```html
<head>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <script>
    // 페인트 전 동기 실행 — favicon 깜빡임 없음
    (function() {
      const theme = localStorage.getItem("theme") || "default"
      const colors = { default: { bg: "#047857", stroke: "#ecfdf5" } /* ... */ }
      const c = colors[theme] || colors.default
      const svg = `<svg ...><rect fill="${c.bg}"/>...</svg>`
      const blob = new Blob([svg], { type: "image/svg+xml" })
      document.querySelector('link[rel="icon"]').href = URL.createObjectURL(blob)
    })()
  </script>
</head>
```

### 해결 2: iOS 앱 아이콘 — Alternate Icons + Hotwire Native Bridge

iOS는 iOS 10.3부터 `UIApplication.shared.setAlternateIconName()`으로 런타임에 앱 아이콘을 변경할 수 있다. Hotwire Native의 Bridge Component 아키텍처를 사용하면 웹 레이어와 연결하기 쉽다.

**1단계: Asset Catalog에 Alternate Icons 등록**

테마별 `.appiconset`을 `Assets.xcassets`에 추가한다:

```
Assets.xcassets/
├── AppIcon.appiconset/           (기본, 필수)
├── AppIcon-Wimbledon.appiconset/
├── AppIcon-USOpen.appiconset/
└── AppIcon-Hardcourt.appiconset/
```

**2단계: Info.plist에 Alternate Icons 선언**

```xml
<key>CFBundleIcons</key>
<dict>
  <key>CFBundleAlternateIcons</key>
  <dict>
    <key>AppIcon-Wimbledon</key>
    <dict>
      <key>CFBundleIconFiles</key>
      <array><string>AppIcon-Wimbledon</string></array>
      <key>UIPrerenderedIcon</key>
      <false/>
    </dict>
    <key>AppIcon-USOpen</key>
    <dict>
      <key>CFBundleIconFiles</key>
      <array><string>AppIcon-USOpen</string></array>
      <key>UIPrerenderedIcon</key>
      <false/>
    </dict>
  </dict>
</dict>
```

**3단계: Swift Bridge Component 구현**

```swift
// AppIconComponent.swift
import HotwireNative
import UIKit

struct AppIconPayload: Decodable {
    let theme: String
}

class AppIconComponent: BridgeComponent {
    override class var name: String { "app-icon" }

    private let themeToIconName: [String: String?] = [
        "default":   nil,                    // nil로 기본 아이콘 복원
        "wimbledon": "AppIcon-Wimbledon",
        "us-open":   "AppIcon-USOpen",
        "hardcourt": "AppIcon-Hardcourt",
    ]

    override func onReceive(message: Message) {
        guard let data: AppIconPayload = message.data() else { return }
        let iconName = themeToIconName[data.theme] ?? nil

        UIApplication.shared.setAlternateIconName(iconName) { error in
            if let error { print("[AppIconComponent] error: \(error)") }
        }

        reply(to: message)
    }
}
```

**4단계: 웹 Stimulus 컨트롤러에서 Bridge 호출**

```javascript
// theme_controller.js
_updateAppIcon(theme) {
  // Hotwire Native iOS 내부에서만 발화 — 브라우저에서는 no-op
  window.webkit?.messageHandlers?.["app-icon"]?.postMessage({ theme })
}

themeChanged(theme) {
  this._applyTheme(theme)
  this._updateFavicon(theme)
  this._updateAppIcon(theme)
  localStorage.setItem("theme", theme)
}
```

결과: 테마 선택 하나로 브라우저 탭 favicon 변경 + iOS 홈 화면 앱 아이콘 변경 + UI CSS 변수 변경이 한 번에 처리된다.

**iOS 동작 주의사항:** `setAlternateIconName`은 처음 실행 시 시스템 알림("앱 아이콘을 변경했습니다...")을 표시한다. iOS 시스템 제약으로 억제할 수 없다. 아이콘 변경마다 한 번씩만 뜨므로 치명적인 UX 문제는 아니다.

---

## 정리

| 삽질 | 원인 | 해결 | 핵심 교훈 |
|------|------|------|---------|
| DnD 두 번째부터 안 됨 | Turbo Stream DOM 교체 후 이벤트 리스너 소실 | `targetConnected` 라이프사이클 콜백 + 멱등성 가드 | Stimulus와 Turbo Stream의 라이프사이클은 명시적으로 동기화해야 한다 |
| 페이지 121 쿼리 | 서비스 객체 내 선수별 N+1 | 이미 로드된 데이터로 메모리 집계 + Prosopite 도입 | 자동 감지 없이는 N+1이 개발 경고가 아닌 사용자 불만으로 드러난다 |
| 테마 변경 시 favicon 불변 | SVG favicon은 CSS 변수 접근 불가 (별도 렌더링 컨텍스트) | JavaScript로 Blob URL 생성 | 브라우저 favicon은 페이지 CSS 환경으로부터 격리돼 있다 |
| iOS 앱 아이콘 고정 | 웹 레이어에서 네이티브 훅 없음 | Hotwire Native Bridge Component + `setAlternateIconName` | Bridge Component는 웹→네이티브 기능 호출의 올바른 추상화다 |

Rails 8 + Hotwire의 모델 — "서버가 HTML을 보내면 브라우저가 적용한다" — 은 개념적으로 단순하다. 하지만 DOM 라이프사이클 관리, N+1 쿼리 규율, 브라우저 렌더링 컨텍스트 경계는 여전히 전적으로 개발자의 책임이다. 이 문제들은 튜토리얼에서 나오지 않는다. 사용자가 두 번째로 칩을 드래그하는 순간 프로덕션 대시보드에서 나온다.

여기서 설명한 3가지 해결은 합산해도 하루가 걸리지 않았다. 특히 Prosopite 설정은 지속적인 효과가 있다. 코드베이스 어디에서든 새 N+1이 도입되면 사용자가 지연을 인지하기 전에 즉시 로그 경고가 출력된다.
