---
title: "Hotwire Native 앱 대시보드 UX 삽질기 — CSP, Turbo 재선언, backdrop-filter 성능까지"
date: 2026-03-21
draft: false
tags: ["Rails 8", "Hotwire", "Turbo", "Stimulus", "CSP", "Content Security Policy", "backdrop-filter", "모바일 WebView", "성능 최적화", "Tailwind CSS", "WKWebView", "iOS", "Hotwire Native"]
description: "Rails 8 + Hotwire Native 모바일 앱의 대시보드 페이지에서 발생한 레이아웃 깨짐, CSP 차단, Turbo 변수 재선언 에러, 스크롤 성능 저하를 해결한 실전 디버깅 기록. 120개 backdrop-filter blur 레이어가 GPU를 죽이고, IIFE 패턴이 Turbo와 인라인 스크립트의 충돌을 해결한다."
cover:
  image: ""
  alt: "Hotwire Native Dashboard UX Optimization"
  hidden: true
---

Rails 8 + Hotwire Native으로 만든 모바일 앱의 대시보드 페이지를 Render에 배포한 뒤 실기기에서 점검하면서 만난 삽질 7가지를 정리했다. WKWebView 위에서 돌아가는 하이브리드 앱 특성상, 데스크톱 브라우저에서는 발견되지 않는 함정들이 많았다.

이 글에서 다루는 주요 키워드: **Hotwire Native 모바일 레이아웃**, **Content Security Policy CDN 차단**, **Turbo const/let 재선언 에러**, **backdrop-filter 성능**, **Stimulus 컨트롤러 자동 등록**, **CSS contain 최적화**.

---

## 프로젝트 환경

- **Backend**: Rails 8 + PostgreSQL
- **Frontend**: Hotwire (Turbo + Stimulus) + ERB + Tailwind CSS 4
- **Mobile**: Hotwire Native (iOS WKWebView)
- **Realtime**: ActionCable (WebSocket)
- **Deploy**: Render.com
- **Asset Pipeline**: importmap-rails (CDN pin 방식)

대시보드 페이지 구성: 코트 카드 grid (코트 수 x 라운드 수), 선수 DnD 리스트, 경기 목록, 교류 현황 통계. 코트 5개 x 8라운드 = 40장의 카드가 한 페이지에 렌더링되는 구조.

---

## 1. 모바일 WebView에서 가로 스크롤이 넘침

### 증상

Render에 배포 후 iOS 앱에서 대시보드를 열었더니:
- 헤더 버튼 영역(라운드, 선수, 전체경기, 설정)이 우측으로 넘쳐서 가로 스크롤 발생
- 코트 카드 내용(팀 이름, 스코어, 라운드명)이 세로로 잘림

데스크톱 크롬에서는 문제없었는데, WKWebView에서만 발생.

### 원인 분석

두 가지 원인이 복합적으로 작용했다:

**1) 버튼 영역 overflow**: 4개 버튼이 `flex` 컨테이너 안에 `whitespace-nowrap`으로 배치되어 있는데, `flex-wrap`이 없었다. 데스크톱에서는 공간이 충분해서 한 줄에 들어갔지만, 모바일 WebView(375px 이하)에서는 넘침.

**2) 코트 카드 `aspect-square`**: 코트 카드에 `aspect-ratio: 1/1`이 적용되어 있어서, 3열 grid(모바일 기본)에서 각 카드가 약 110px x 110px. 이 안에 코트번호, 팀 A 이름, VS, 팀 B 이름, 라운드명, 세트 스코어까지 들어가야 하는데 세로 공간이 부족.

### 해결

```erb
<%# 버튼 영역에 flex-wrap 추가 — 좁은 화면에서 줄바꿈 허용 %>
<div class="flex shrink-0 flex-wrap items-center gap-2">
  <%= yield %>
</div>
```

```erb
<%# 최상위 컨테이너에 overflow-x 방지 %>
<div class="theme-shell flex min-h-screen flex-col overflow-x-hidden">
```

```erb
<%# 코트 카드 비율을 세로로 긴 3:4로 변경 %>
<div class="relative overflow-hidden rounded-xl aspect-[3/4]" ...>
```

### 조사한 내용

Perplexity로 "Hotwire Native mobile webview CSS overflow prevention"을 검색해서 확인한 핵심 사항들:

- **iOS Safari/WKWebView에서는 `overflow-x: hidden`을 `<body>`에 설정해도 무시되는 버그**가 있다. 래퍼 div에 적용해야 안전.
- **`100vw` 대신 `100%`를 사용**해야 한다. Android Chrome에서 `100vw`는 스크롤바 너비를 포함해서 overflow를 유발.
- **flex 아이템에 `shrink-0` + `flex-wrap` 조합**이 모바일 WebView에서 가장 안정적인 레이아웃 패턴.

---

## 2. importmap CDN import가 Content Security Policy에 차단됨

### 증상

브라우저 콘솔에 3종류 에러가 연쇄 발생:

```
Loading the script 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm'
violates the following Content Security Policy directive:
"script-src 'self' 'unsafe-inline' https://us-assets.i.posthog.com"
```

```
Failed to register controller: dashboard-dnd (controllers/dashboard_dnd_controller)
TypeError: Failed to fetch dynamically imported module
```

```
Connecting to 'https://cdn.jsdelivr.net/sm/...' violates CSP "connect-src"
```

SortableJS를 CDN에서 동적 import하는 Stimulus 컨트롤러(`dashboard_dnd_controller`)가 로드 실패하면서, 드래그앤드롭 기능 전체가 작동하지 않음.

### 원인 분석

`config/importmap.rb`에 SortableJS가 CDN pin으로 등록되어 있었지만:

```ruby
# config/importmap.rb
pin "sortablejs", to: "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm"
```

`content_security_policy.rb`에는 `cdn.jsdelivr.net`이 허용 목록에 없었다:

```ruby
# 기존 — jsdelivr 없음
policy.script_src :self, :unsafe_inline, "https://us-assets.i.posthog.com"
policy.connect_src :self, "https://us.i.posthog.com", "https://us-assets.i.posthog.com"
```

importmap에 CDN pin을 추가할 때 CSP 업데이트를 깜빡한 것. 개발 환경에서는 CSP 위반이 콘솔 경고만 내고 실제로 차단하지 않는 경우가 있어서 놓치기 쉽다.

### 해결

```ruby
# config/initializers/content_security_policy.rb
Rails.application.configure do
  config.content_security_policy do |policy|
    policy.script_src  :self, :unsafe_inline,
                       "https://us-assets.i.posthog.com",
                       "https://cdn.jsdelivr.net"         # 추가
    policy.connect_src :self,
                       "https://us.i.posthog.com",
                       "https://us-assets.i.posthog.com",
                       "https://cdn.jsdelivr.net"         # 추가 (source map용)
  end
end
```

서버 재시작 필요 (`config/initializers` 변경).

### 교훈

importmap에서 CDN pin을 추가할 때는 반드시 CSP도 함께 업데이트해야 한다. 체크리스트:
1. `config/importmap.rb`에 pin 추가
2. `content_security_policy.rb`의 `script_src`에 CDN 도메인 추가
3. source map이 필요하면 `connect_src`에도 추가

---

## 3. Turbo 페이지 전환 시 `const`/`let` 재선언 에러

### 증상

대시보드에서 다른 페이지로 이동했다가 돌아오면, 또는 Turbo가 캐시된 스냅샷을 복원할 때:

```
Uncaught SyntaxError: Failed to execute 'replaceWith' on 'Element':
Identifier 'STORAGE_KEY' has already been declared
```

이 에러가 수십 번 반복 발생하면서 페이지의 모든 JS 기능(필터, 정렬, 매치 토글)이 작동 중단.

### 원인 분석

ERB 뷰 하단에 인라인 `<script>` 블록으로 상태 관리 코드를 작성했는데:

```html
<script>
  const STORAGE_KEY = 'friendly_dashboard_52'
  let currentMatchSort = 'round'
  let roundDescending = true
  // ...
</script>
```

Turbo의 페이지 전환 메커니즘:
1. 새 페이지를 fetch
2. `replaceWith`로 `<body>`를 교체
3. 교체된 body의 `<script>` 태그를 실행

문제는 3단계에서 **이전 페이지의 `const`/`let` 선언이 아직 스코프에 남아있는 상태에서** 새 스크립트가 같은 변수를 `const`/`let`으로 재선언하는 것. JavaScript 스펙상 `const`/`let`은 같은 스코프에서 재선언이 불가능하므로 SyntaxError가 발생한다.

`var`는 재선언이 허용되므로 이 문제가 없지만, 모던 JS 습관적으로 `const`/`let`을 쓰면 Turbo 환경에서 함정에 빠진다.

### 해결

전체 스크립트를 **IIFE(Immediately Invoked Function Expression)**으로 감싸서 변수 스코프를 격리한다:

```html
<script>
;(function() {
  var STORAGE_KEY = 'friendly_dashboard_<%= @tournament.id %>'
  var currentMatchSort = 'round'
  var roundDescending = true

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        roundFilter: currentRoundFilter,
        roundDescending: roundDescending,
        matchSort: currentMatchSort
      }))
    } catch(e) {}
  }

  // onclick="filterRounds('all')" 같은 인라인 핸들러에서 접근해야 하므로 window에 등록
  window.filterRounds = function(filter) {
    currentRoundFilter = filter
    // DOM 조작...
    saveState()
  }

  window.toggleRoundOrder = function() {
    roundDescending = !roundDescending
    // DOM 조작...
    saveState()
  }

  // 페이지 로드 시 localStorage에서 상태 복원
  var saved = loadState()
  if (saved) {
    if (saved.roundFilter !== 'all') window.filterRounds(saved.roundFilter)
    if (saved.roundDescending === false) window.toggleRoundOrder()
    if (saved.matchSort !== 'round') window.switchMatchSort(saved.matchSort)
  }
})()
</script>
```

### 핵심 패턴

```
Turbo + 인라인 <script> = IIFE + var + window.함수명
```

| 패턴 | Turbo 호환 | 이유 |
|------|-----------|------|
| `const x = 1` | X | 재선언 불가 |
| `let x = 1` | X | 재선언 불가 |
| `var x = 1` (전역) | 세미 O | 재선언은 되지만 이전 값이 남아 상태 오염 |
| IIFE + `var` | O | 함수 스코프로 격리, 재실행해도 안전 |
| Stimulus 컨트롤러 | O | 가장 이상적. connect/disconnect 생명주기 활용 |

### 교훈

- Turbo 환경에서 인라인 `<script>`에 `const`/`let`은 **절대 사용하지 않는다**
- 간단한 토글 로직이라도 IIFE로 감싸는 습관을 들이자
- 장기적으로는 Stimulus 컨트롤러로 옮기는 게 정석

---

## 4. Turbo Stream 토스트 알림이 사라지지 않음

### 증상

자동 배치 버튼을 클릭하면 "3경기 자동 배정 완료" 토스트가 화면 하단에 나타나는데, 이 토스트가 **영원히** 사라지지 않고 계속 화면에 남아있음.

### 원인 분석

Turbo Stream으로 토스트 HTML을 동적 삽입할 때 `data-controller='auto-dismiss'`를 지정했지만:

```ruby
# 컨트롤러에서 turbo_stream으로 토스트 삽입
turbo_stream.append("toast-container",
  "<div data-controller='auto-dismiss' data-auto-dismiss-delay-value='3000'>
    #{notice}
  </div>".html_safe)
```

**`auto_dismiss_controller.js` 파일이 존재하지 않았다.** importmap 기반 eager loading에서는 `app/javascript/controllers/` 디렉토리에 파일만 만들면 자동 등록되지만, 파일 자체가 없으니 Stimulus가 컨트롤러를 찾지 못해서 아무 동작도 하지 않은 것.

### 해결

```javascript
// app/javascript/controllers/auto_dismiss_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { delay: { type: Number, default: 3000 } }

  connect() {
    this.timeout = setTimeout(() => {
      this.element.style.transition = "opacity 0.3s ease-out"
      this.element.style.opacity = "0"
      setTimeout(() => this.element.remove(), 300)
    }, this.delayValue)
  }

  disconnect() {
    if (this.timeout) clearTimeout(this.timeout)
  }
}
```

### 교훈

Turbo Stream으로 동적 삽입하는 요소에 Stimulus 컨트롤러를 지정할 때:
1. 해당 컨트롤러 파일이 **실제로 존재하는지** 확인
2. `disconnect()`에서 타이머를 정리해야 메모리 누수 방지
3. `remove()` 전에 fade-out 애니메이션을 주면 UX가 자연스러움

---

## 5. `backdrop-filter: blur()`가 스크롤 성능을 죽이다

### 증상

코트 5개 x 8라운드 = 40장 카드를 스크롤할 때 뚝뚝 끊기는 느낌. 데스크톱 크롬에서도 약간의 랙이 느껴졌고, 모바일 WKWebView에서는 더 심각.

### 원인 분석

각 코트 카드의 HTML을 살펴보니 `backdrop-filter: blur()`가 **카드 당 3곳**에 적용:

```html
<!-- 팀 A 이름 배경 -->
<div style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);">
  팀 A
</div>

<!-- VS 스코어 배경 -->
<div style="background: rgba(0,0,0,0.4); backdrop-filter: blur(8px);">
  vs
</div>

<!-- 팀 B 이름 배경 -->
<div style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);">
  팀 B
</div>
```

40장 카드 x 3곳 = **120개 blur 합성 레이어**. 매 스크롤 프레임마다 GPU가 120개 영역의 뒤 배경을 샘플링해서 blur 처리해야 한다.

`backdrop-filter`의 작동 원리:
1. 해당 요소 뒤에 있는 모든 콘텐츠를 오프스크린 버퍼에 렌더링
2. 그 버퍼에 Gaussian blur 적용
3. blur된 이미지 위에 요소를 합성

이 과정이 **매 프레임마다** (스크롤 시 초당 60번) 일어나므로, 120개가 동시에 돌면 GPU 메모리와 연산이 포화.

### 해결

`backdrop-filter: blur()`를 전부 제거하고 `background: rgba(...)` 반투명만 유지:

```diff
- style="background: rgba(255,255,255,0.15); backdrop-filter: blur(4px);"
+ style="background: rgba(255,255,255,0.15);"

- style="background: rgba(0,0,0,0.4); backdrop-filter: blur(8px);"
+ style="background: rgba(0,0,0,0.4);"
```

추가로 각 카드에 CSS `contain: content`를 적용해서 리페인트 범위를 격리:

```html
<div class="relative overflow-hidden rounded-xl aspect-square"
     style="background: linear-gradient(...); contain: content;">
```

### 성능 비교

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| GPU 합성 레이어 | ~120개 | 0개 |
| 스크롤 FPS | 30~45fps (랙 체감) | 60fps (부드러움) |
| 시각적 차이 | blur 효과 | 거의 동일 (반투명만) |
| GPU 메모리 | 높음 | 최소 |

### 교훈

- **`backdrop-filter: blur()`는 카드 1~2개에는 아름답지만, 수십 개가 반복되면 치명적**
- 특히 모바일 WebView에서는 GPU 메모리 제한(iOS는 보통 1/3)으로 더 심각
- 대안: `background: rgba()` 반투명만으로 충분히 가독성 확보 가능
- `CSS contain: content`는 저비용으로 리페인트 범위를 격리하는 최적화. `layout`, `paint`, `size` 격리를 한 번에 적용

---

## 6. DB 레거시 데이터가 뷰에 그대로 노출됨

### 증상

선수 목록 페이지에서 테니스 레벨이 "4.0", "3.5" 같은 NTRP 숫자로 표시됨. 설정 페이지에서는 이미 한국어 옵션(입문/초급/중급/상급/선수급)으로 변경했는데, 기존에 가입한 시드 유저들의 DB 값이 숫자 그대로.

### 원인 분석

```ruby
# DB에 저장된 값 확인
User.where.not(ntrp_level: [nil, '']).pluck(:ntrp_level).uniq
# => ["4.5", "4.0", "3.5", "3.0", "5.0", "2.5"]
```

설정 폼은 한국어 옵션으로 변경했지만, 기존 유저의 DB 값은 숫자. 뷰에서 `player.user.ntrp_level`을 직접 출력하니 숫자가 그대로 나옴.

### 해결

DB 마이그레이션 없이 뷰 레이어에서 하위호환 매핑:

```ruby
# app/helpers/application_helper.rb
module ApplicationHelper
  NTRP_TO_LEVEL = {
    "2.0" => "입문", "2.5" => "입문",
    "3.0" => "초급", "3.5" => "초급",
    "4.0" => "중급", "4.5" => "상급",
    "5.0" => "선수급", "5.5" => "선수급"
  }.freeze

  VALID_LEVELS = %w[입문 초급 중급 상급 선수급].freeze

  def display_tennis_level(raw_level)
    return nil if raw_level.blank?
    return raw_level if VALID_LEVELS.include?(raw_level)
    NTRP_TO_LEVEL[raw_level] || raw_level
  end
end
```

전수 조사해서 6개 뷰 파일에서 `player.user.ntrp_level`을 `display_tennis_level()`로 교체:

```erb
<%# 변경 전 %>
<%= player.user.ntrp_level %>

<%# 변경 후 %>
<%= display_tennis_level(player.user.ntrp_level) %>
```

### 교훈

- DB 컬럼 리네임이나 값 마이그레이션은 리스크가 크므로, **뷰 레이어에서 매핑하는 패턴**이 안전
- 이미 한국어로 저장된 신규 유저는 `VALID_LEVELS.include?` 체크로 그대로 통과
- `|| raw_level` fallback으로 매핑에 없는 미지의 값도 표시 (방어적 코딩)

---

## 7. 상태 변경 후 잘못된 페이지로 리다이렉트

### 증상

대시보드에서 "진행 → 준비"로 상태를 되돌리면 설정 페이지(`/settings`)로 이동. 사용자는 대시보드에 있었는데 갑자기 낯선 설정 페이지가 보여서 혼란.

### 원인

```ruby
# tournaments_controller.rb
def revert_to_registration
  if @tournament.revert_to_registration!
    redirect_to settings_tournament_path(@tournament),
      notice: "준비 단계로 변경되었습니다. 설정을 수정하세요."
  end
end
```

"설정을 수정하세요"라는 의도로 설정 페이지로 보낸 건데, 사용자 입장에서는 **대시보드에서 작업 중이었으므로 대시보드로 돌아가는 게 자연스럽다**.

### 해결

```ruby
redirect_to dashboard_path_for(@tournament),
  notice: "준비 단계로 변경되었습니다."
```

모드별 대시보드 경로를 반환하는 헬퍼:

```ruby
def dashboard_path_for(tournament)
  case tournament.mode.to_sym
  when :free_play   then tournament_free_play_dashboard_path(tournament)
  when :round_robin then tournament_round_robin_dashboard_path(tournament)
  when :friendly    then tournament_friendly_dashboard_path(tournament)
  else tournament_path(tournament)
  end
end
```

### 교훈

리다이렉트 대상은 **개발자의 의도**가 아니라 **사용자의 컨텍스트**에 맞춰야 한다.

---

## 정리: 7가지 이슈 요약

| # | 이슈 | 핵심 원인 | 카테고리 |
|---|------|-----------|----------|
| 1 | 가로 스크롤 넘침 | `flex-wrap` 누락 + `aspect-square` | 모바일 레이아웃 |
| 2 | CDN CSP 차단 | importmap pin 시 CSP 미갱신 | 보안 정책 |
| 3 | `const` 재선언 에러 | Turbo + 인라인 스크립트 충돌 | Turbo 호환성 |
| 4 | 토스트 안 사라짐 | Stimulus 컨트롤러 파일 미생성 | Stimulus |
| 5 | 스크롤 성능 저하 | `backdrop-filter: blur()` x 120개 | CSS 성능 |
| 6 | 레거시 데이터 노출 | DB 값 마이그레이션 누락 | 데이터 호환 |
| 7 | 잘못된 리다이렉트 | 하드코딩된 redirect 경로 | UX 동선 |

대부분 **"개발 환경에서는 동작하지만 운영 환경에서 문제가 드러나는"** 유형이었다. 특히 `backdrop-filter` 성능 이슈는 고사양 개발 머신에서는 눈치채기 어렵고, 실제 모바일 디바이스에서만 체감되므로 배포 후 실기기 테스트가 필수다.

Hotwire Native 앱은 웹 기술의 장점(빠른 배포, 코드 공유)을 살리면서도 네이티브 앱의 UX를 추구하는 아키텍처인데, 그만큼 웹과 네이티브 양쪽의 함정을 모두 신경 써야 한다. 이 글이 비슷한 스택으로 개발하는 분들에게 도움이 되길 바란다.
