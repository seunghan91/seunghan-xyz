---
title: "Rails 8 Hotwire 실전 삽질기 — DnD 배정, N+1 자동 감지, 테마별 Favicon"
date: 2026-03-21
draft: false
tags: ["Rails 8", "Hotwire", "Turbo Stream", "Stimulus", "N+1", "Prosopite", "DnD", "Favicon", "iOS"]
description: "Turbo Stream + Stimulus로 드래그앤드롭 선수 배정을 구현하면서 겪은 DOM 교체 후 이벤트 소실, 121 쿼리 N+1 문제 발견과 Prosopite 도입, 그리고 테마별 동적 Favicon/앱 아이콘 연동까지의 기록"
---

Rails 8 + Hotwire로 실시간 대시보드를 만들면서 하루 동안 겪은 3가지 삽질과 해결 과정.

---

## 1. Turbo Stream + Stimulus DnD: DOM 교체 후 이벤트가 사라진다

### 문제

선수 칩을 코트 카드에 드래그하면 서버에 POST → Turbo Stream으로 코트 카드와 선수 목록을 교체하는 구조를 만들었다.

첫 번째 드래그는 잘 되는데, **두 번째부터 드래그가 안 된다.**

### 원인

Stimulus 컨트롤러의 `connect()`에서 이벤트 리스너를 한 번만 등록했기 때문이다. Turbo Stream이 DOM을 교체하면 새 요소에는 리스너가 없다.

```javascript
// ❌ connect()에서만 등록 — 교체된 요소에는 적용 안 됨
connect() {
  this.chipTargets.forEach(chip => {
    chip.addEventListener("dragstart", this.dragStart.bind(this))
  })
}
```

### 해결: targetConnected 콜백 + 이중 방어

Stimulus 3.x의 `chipTargetConnected()` 콜백을 사용하면 새 타겟이 DOM에 추가될 때 자동으로 호출된다. 다만 일부 환경에서 이 콜백이 안 불리는 케이스가 있어서, `connect()`에서도 직접 세팅하는 이중 방어 방식을 적용했다.

```javascript
connect() {
  this._boundDragStart = this.dragStart.bind(this)
  // 기존 타겟도 직접 세팅 (fallback)
  this.chipTargets.forEach(chip => this._setupChip(chip))
}

// 새 타겟이 DOM에 추가될 때 자동 호출
chipTargetConnected(chip) { this._setupChip(chip) }
chipTargetDisconnected(chip) { this._teardownChip(chip) }

_setupChip(chip) {
  if (chip.dataset.dragBound) return  // 중복 방지
  chip.dataset.dragBound = "1"
  chip.setAttribute("draggable", "true")
  chip.addEventListener("dragstart", this._boundDragStart)
}
```

### 또 다른 함정: Turbo Stream replace 후 ID 소실

`turbo_stream.replace("player-list-container", partial: "player_list")`로 교체하는데, **partial 내부에 `id="player-list-container"`가 없으면** 두 번째 replace가 대상을 찾지 못한다.

```erb
<%# ❌ partial에 ID 없음 — 첫 replace 후 ID가 사라짐 %>
<div class="flex items-center ...">
  ...
</div>

<%# ✅ partial 안에 ID 포함 — replace 반복 가능 %>
<div id="player-list-container">
  <div class="flex items-center ...">
    ...
  </div>
</div>
```

**교훈**: Turbo Stream `replace`의 대상 ID는 **partial 내부**에 있어야 한다.

---

## 2. 121 쿼리 N+1: 사용자가 발견하기 전에 잡는 법

### 문제

대시보드 → 경기 탭으로 이동할 때 체감상 느리다는 피드백.

로그를 확인해보니:

```
Completed 200 OK in 340ms (Views: 165ms | ActiveRecord: 104ms (121 queries, 40 cached))
```

**121 쿼리.** 대시보드 한 페이지에서.

### 원인

서비스 객체에서 선수별 통계를 계산할 때, 각 선수마다 `completed_matches_count`, `wins_count` 등을 개별 쿼리로 조회하고 있었다.

```ruby
# ❌ N+1: 선수 11명 × 4쿼리 = 44 추가 쿼리
player_stats = players.map do |player|
  {
    matches_played: player.completed_matches_count,  # SELECT COUNT(*)...
    wins: player.wins_count,                          # each match_player...
    losses: player.losses_count,                      # count - wins
    win_rate: player.win_rate,                        # wins / count
  }
end
```

### 해결: 일괄 집계로 쿼리 0

이미 로드된 matches 데이터에서 메모리로 집계하면 추가 쿼리가 0이다.

```ruby
# ✅ 추가 쿼리 0: 이미 로드된 데이터에서 계산
player_match_counts = Hash.new(0)
player_win_counts = Hash.new(0)

completed_matches.each do |match|
  team_a_ids = match.match_players.select(&:team_a?).map(&:participant_id)
  team_b_ids = match.match_players.select(&:team_b?).map(&:participant_id)

  (team_a_ids + team_b_ids).each { |pid| player_match_counts[pid] += 1 }

  winner_ids = match.winner_team == "team_a" ? team_a_ids : team_b_ids
  winner_ids.each { |pid| player_win_counts[pid] += 1 }
end
```

### 근본 해결: Prosopite로 자동 감지

문제는 **사용자가 "느리다"고 말해야 발견한다**는 것이다. 자동 감지 도구를 설치했다.

```ruby
# Gemfile
group :development do
  gem "prosopite"
end

# config/environments/development.rb
config.after_initialize do
  Prosopite.rails_logger = true  # 로그에 N+1 경고
  Prosopite.raise = false        # true면 에러 발생
  Prosopite.min_n_queries = 2
end

# application_controller.rb
around_action :prosopite_scan, if: -> { Rails.env.development? }

def prosopite_scan
  Prosopite.scan
  yield
ensure
  Prosopite.finish
end
```

이제 모든 요청에서 N+1이 자동 감지되어 로그에 경고가 출력된다.

```
# 로그 확인
grep 'Prosopite' log/development.log
```

Prosopite는 Bullet과 달리 **false positive가 없다** — 같은 call stack + 같은 쿼리 fingerprint가 2회 이상 반복되는 패턴만 잡는다.

---

## 3. 테마별 동적 Favicon + iOS 앱 아이콘

### 문제

앱 내에서 테마를 바꾸면 CSS 색상은 바뀌는데 브라우저 탭의 favicon은 그대로다. iOS 앱 아이콘도 마찬가지.

### 해결 1: SVG Favicon 동적 생성

SVG favicon은 CSS 변수를 쓸 수 없다 (별도 렌더링 컨텍스트). JavaScript로 Blob URL을 만들어 교체한다.

```javascript
// theme_controller.js
const THEME_COLORS = {
  "default":       { bg: "#047857", stroke: "#ecfdf5" },
  "wimbledon":     { bg: "#522398", stroke: "#f5f0ff" },
  "us-open":       { bg: "#003DA5", stroke: "#eef3ff" },
  // ...
}

_updateFavicon(theme) {
  const colors = THEME_COLORS[theme] || THEME_COLORS["default"]
  const svg = `<svg xmlns="..." width="512" height="512" viewBox="0 0 512 512">
    <rect width="512" height="512" rx="96" fill="${colors.bg}"/>
    <g stroke="${colors.stroke}" ...>...</g>
  </svg>`

  const blob = new Blob([svg], { type: "image/svg+xml" })
  const url = URL.createObjectURL(blob)

  let link = document.querySelector('link[rel="icon"][type="image/svg+xml"]')
  if (link) {
    if (link.dataset.blobUrl) URL.revokeObjectURL(link.dataset.blobUrl)
    link.href = url
    link.dataset.blobUrl = url
  }
}
```

초기 로딩 시 깜빡임 방지를 위해 `<head>` 인라인 스크립트에서도 동일한 로직을 실행한다.

### 해결 2: iOS 앱 아이콘 — Alternate Icons + Bridge Component

iOS에서는 `UIApplication.setAlternateIconName()`으로 앱 아이콘을 런타임에 변경할 수 있다 (iOS 10.3+).

**1) Asset Catalog에 테마별 아이콘 등록:**
```
Assets.xcassets/
├── AppIcon.appiconset/          (기본)
├── AppIcon-Wimbledon.appiconset/
├── AppIcon-USOpen.appiconset/
└── ...
```

**2) Info.plist에 Alternate Icons 선언:**
```xml
<key>CFBundleIcons</key>
<dict>
  <key>CFBundleAlternateIcons</key>
  <dict>
    <key>AppIcon-Wimbledon</key>
    <dict>
      <key>CFBundleIconFiles</key>
      <array><string>AppIcon-Wimbledon</string></array>
    </dict>
    ...
  </dict>
</dict>
```

**3) Hotwire Native Bridge Component:**
```swift
class AppIconComponent: BridgeComponent {
    override class var name: String { "app-icon" }

    override func onReceive(message: Message) {
        guard let data: Payload = message.data() else { return }
        let iconName = themeToIconName[data.theme]
        UIApplication.shared.setAlternateIconName(iconName)
        reply(to: message.id)
    }
}
```

**4) 웹에서 Bridge 호출:**
```javascript
_updateAppIcon(theme) {
  if (window.webkit?.messageHandlers?.["app-icon"]) {
    window.webkit.messageHandlers["app-icon"].postMessage({ theme })
  }
}
```

테마 선택 → favicon 즉시 변경 + iOS 앱 아이콘 변경까지 한 번에 처리된다.

---

## 정리

| 삽질 | 원인 | 해결 | 교훈 |
|------|------|------|------|
| DnD 두 번째부터 안 됨 | Turbo Stream DOM 교체 후 이벤트 소실 | `targetConnected` + 이중 방어 | Turbo Stream과 Stimulus는 lifecycle을 맞춰야 한다 |
| 대시보드 121 쿼리 | 서비스 객체 내 N+1 | 메모리 집계 + Prosopite 도입 | 자동 감지 도구 없이는 사용자가 발견한다 |
| 테마 변경 시 favicon 안 바뀜 | SVG favicon은 CSS 변수 불가 | Blob URL 동적 생성 | 브라우저 favicon은 별도 렌더링 컨텍스트 |

Rails 8 + Hotwire의 "서버가 HTML을 보내면 끝" 모델은 단순하지만, **DOM 라이프사이클과 쿼리 성능은 여전히 개발자 몫**이다.
