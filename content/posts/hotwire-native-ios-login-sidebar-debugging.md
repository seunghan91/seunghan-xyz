---
title: "Hotwire Native iOS — 로그인 모달 충돌, Tailwind 4 사이드바, path config 삽질 기록"
date: 2026-03-19
draft: false
tags: ["iOS", "HotwireNative", "Swift", "Tailwind", "CSS", "Rails", "Debugging"]
description: "Hotwire Native 멀티탭 앱에서 로그인 모달이 홈 탭에서만 뜨는 문제, Tailwind v4 CSS 속성 변경으로 사이드바가 안 열리는 버그, path_configuration의 tab_id 불일치로 네비게이션이 조용히 실패하는 세 가지 삽질을 해결한 기록."
---

Hotwire Native iOS 앱에서 하루 동안 세 가지 버그를 잡았다. 각각 원인이 다르지만 공통점이 있다: **겉으로 보이는 증상과 실제 원인이 전혀 다른 곳에 있었다.**

---

## 1. 로그인 페이지가 홈 탭에서만 보이는 문제

### 증상

4개 탭(홈, 과제, 알림, 마이)이 있는 앱에서, 비로그인 상태로 앱을 열면 **홈 탭에서만 로그인 페이지가 뜨고**, 나머지 탭을 누르면 빈 화면이나 에러가 표시된다.

Rails 서버는 4개 탭 모두 `/login`으로 정상 리다이렉트하고 있었다.

### 원인: path-configuration의 `context: "modal"`

Hotwire Native의 path-configuration에서 `/login`이 이렇게 설정되어 있었다:

```json
{
  "patterns": ["/login"],
  "properties": {
    "context": "modal",
    "presentation": "replace"
  }
}
```

`HotwireTabBarController`는 `load()` 호출 시 **모든 탭의 URL을 동시에 로드**한다. 각 탭의 Navigator가 독립적으로 `/login` 리다이렉트를 받으면:

1. **홈 탭 (active)**: `/dashboard` → `/login` 리다이렉트 → 모달 프레젠테이션 성공 ✅
2. **나머지 탭 (background)**: 각 URL → `/login` 리다이렉트 → 모달 프레젠테이션 **실패** ❌

백그라운드 탭의 Navigator는 view hierarchy에 없으므로 모달을 present할 수 없다. 이 탭들은 "방문 시도했지만 실패한" 상태로 남아서, 나중에 탭을 선택해도 재시도하지 않는다.

### 해결: `context: "default"`로 변경 + 탭바 숨김

```json
{
  "patterns": ["/login", "/onboarding"],
  "properties": {
    "context": "default",
    "presentation": "replace",
    "pull_to_refresh_enabled": false,
    "animated": false
  }
}
```

`context: "default"`로 바꾸면 로그인 페이지가 각 탭의 Navigator 내부에 **인라인**으로 렌더링된다. 모달이 아니므로 백그라운드 탭에서도 정상 동작한다.

단, 탭바가 로그인 화면 아래에 보이는 문제가 생긴다. `NavigatorDelegate`의 `requestDidFinish`에서 탭바를 숨기면 해결:

```swift
func requestDidFinish(at url: URL) {
    // 로그인/온보딩 페이지에서 탭바 숨김
    let isAuthPage = url.path == "/login" || url.path == "/onboarding"
    tabBarController.tabBar.isHidden = isAuthPage
}
```

로그인 성공 후 `/reset_app` → `resetTabs()`로 탭바 컨트롤러가 새로 생성되므로 탭바가 자동으로 다시 보인다.

**핵심**: Hotwire Native에서 멀티탭 + 모달 조합은 위험하다. 비활성 탭의 Navigator가 모달을 present하려 하면 조용히 실패한다.

---

## 2. 사이드바가 안 열리는 문제 — Tailwind v4의 CSS 속성 변경

### 증상

네이티브 앱에서 햄버거 버튼을 누르면 **반투명 오버레이(회색 배경)만 깔리고 사이드바가 슬라이드인되지 않는다.**

JS 코드가 실행되고 있다는 건 오버레이가 뜨는 것으로 확인됐다. CSS 문제다.

### 원인: Tailwind 3의 `transform` vs Tailwind 4의 `translate`

네이티브 전용 CSS에서 사이드바 위치를 이렇게 제어하고 있었다:

```css
/* ❌ Tailwind 3 시절 코드 */
body.native-app aside {
  transform: translateX(-100%) !important;
  transition: transform 0.25s ease !important;
}

body.native-app aside.native-sidebar-open {
  transform: translateX(0) !important;
}
```

문제는 **Tailwind v4가 `transform` shorthand 대신 개별 CSS 속성 `translate`를 사용**한다는 것이다.

```html
<!-- Tailwind v4가 생성하는 클래스 -->
<aside class="-translate-x-full md:translate-x-0 ...">
```

Tailwind v3에서 `-translate-x-full`은 이렇게 컴파일됐다:

```css
/* Tailwind v3 */
.-translate-x-full {
  transform: translateX(-100%);
}
```

Tailwind v4에서는:

```css
/* Tailwind v4 */
.-translate-x-full {
  translate: -100% 0;
}
```

**`transform`과 `translate`는 완전히 다른 CSS 속성**이다. `transform: translateX(0) !important`를 아무리 때려도 `translate: -100% 0`을 오버라이드할 수 없다. 서로 다른 속성이니까.

### 해결: `translate` 속성으로 변경

```css
/* ✅ Tailwind v4 호환 */
body.native-app aside {
  translate: -100% 0 !important;
  transform: none !important;
  transition: translate 0.25s ease !important;
}

body.native-app aside.native-sidebar-open {
  translate: 0 0 !important;
}
```

세 가지를 바꿔야 한다:
1. **속성 이름**: `transform: translateX(...)` → `translate: ... 0`
2. **기존 transform 무력화**: `transform: none !important` 추가
3. **transition 대상**: `transition: transform` → `transition: translate`

**핵심**: Tailwind v3 → v4 마이그레이션 시 `transform`, `rotate`, `scale` 관련 커스텀 CSS가 있다면 반드시 확인해야 한다. v4는 개별 CSS 속성(`translate`, `rotate`, `scale`)을 사용한다.

---

## 3. 알림 버튼이 동작하지 않는 문제 — tab_id 불일치

### 증상

네이티브 앱 상단 벨 아이콘을 눌러도 알림 페이지로 이동하지 않는다. 아무 반응 없음.

### 원인: 존재하지 않는 `tab_id`로 탭 전환 시도

벨 버튼의 Swift 코드:

```swift
@objc private func didTapBell() {
    let url = baseURL.appending(path: "/notifications")
    tabBarController.activeNavigator.route(url)
}
```

서버의 path-configuration:

```ruby
{ patterns: ["/notifications$"],
  properties: { context: "default",
                presentation: "clear_all",
                tab_id: "notifications" } }
```

`NavigatorDelegate.handle(proposal:)`에서 `tab_id`가 있으면 해당 탭으로 전환을 시도한다:

```swift
if let tabId = proposal.properties["tab_id"] as? String {
    let currentTabs = AppTab.tabs(for: currentUserRole)
    if currentTab?.tabId != tabId {
        switchToTab(withId: tabId)
        return .reject  // ← 여기서 reject 후 종료
    }
}
```

`switchToTab(withId:)`는 내부적으로 `firstIndex(where: { $0.tabId == tabId })`를 호출한다. 그런데 탭 구조가 변경되어 `"notifications"` ID를 가진 탭이 더 이상 없었다. `firstIndex`가 `nil`을 반환하고, 탭 전환은 실패한다.

그런데 proposal은 이미 `.reject`되었으므로 **페이지 로드도 되지 않는다.** 결과: 아무 일도 안 일어남.

### 해결: tab_id 제거

```ruby
# 알림은 더 이상 탭이 아님 → tab_id 없이 push 네비게이션
{ patterns: ["/notifications$"],
  properties: { context: "default",
                presentation: "push" } }
```

`tab_id`를 제거하면 `handle(proposal:)`에서 탭 전환 분기를 타지 않고, 현재 활성 탭의 Navigator에 push된다.

**핵심**: Hotwire Native의 path-configuration에서 `tab_id`는 해당 ID의 탭이 실제로 존재할 때만 써야 한다. 존재하지 않는 `tab_id`로의 전환은 조용히 실패하고, proposal까지 reject해버려서 디버깅이 매우 어렵다. 에러 로그도 크래시도 없다.

---

## 보너스: 로그인 후 잘못된 탭으로 이동

### 증상

로그인 성공 후 홈 탭이 아닌 프로필 탭이 선택된 상태로 시작된다.

### 원인

`resetTabs(andRouteTo:)`에서 `return_to` 경로를 받아 해당 경로로 라우팅하는 로직이 있었다. 역할별 홈 경로(`/mentor/dashboard` 등)와 현재 역할의 홈 경로가 다를 때 추가 라우팅이 발생하고, 이 과정에서 `detectRoleAndRebuildIfNeeded()`가 탭을 재구성하면서 예상치 못한 탭이 선택됐다.

### 해결: 항상 tab 0에서 시작

```swift
private func resetTabs(andRouteTo path: String?) {
    let controller = makeTabBarController(role: currentUserRole)
    tabBarController = controller
    window?.rootViewController = controller

    // 항상 홈 탭에서 시작
    controller.selectedIndex = 0

    fetchWidgetToken()
}
```

`return_to` 경로를 추적하는 로직을 제거하고, 무조건 홈 탭(index 0)에서 시작하게 했다. `requestDidFinish`에서 `detectRoleAndRebuildIfNeeded()`가 역할을 감지하면 올바른 탭 구성으로 재구성된다.

---

## 교훈 정리

| 버그 | 겉으로 보이는 증상 | 실제 원인 |
|------|-------------------|----------|
| 로그인 홈 탭만 | 서버 리다이렉트 문제? | path-config `context: "modal"` + 비활성 탭의 모달 present 실패 |
| 사이드바 안 열림 | JS 토글 문제? | Tailwind v4가 `transform` → `translate` 개별 속성으로 변경 |
| 알림 버튼 무반응 | route() 호출 실패? | path-config의 `tab_id`가 존재하지 않는 탭 → 조용한 reject |
| 로그인 후 잘못된 탭 | 리다이렉트 경로 문제? | 역할 감지 + 탭 재구성 타이밍 |

공통 패턴: **Hotwire Native는 실패를 조용히 삼킨다.** 모달 present 실패, tab 전환 실패, CSS 속성 불일치 — 모두 에러 로그 없이 "아무 일도 안 일어나는" 형태로 나타난다. 디버깅할 때 크래시보다 "아무 반응 없음"이 더 어렵다.
