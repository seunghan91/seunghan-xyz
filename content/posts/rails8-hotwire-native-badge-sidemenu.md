---
title: "Rails 8 + Hotwire Native iOS — 실시간 알림 뱃지 & 사이드 메뉴 네비게이션 구현"
date: 2026-03-17
draft: false
tags: ["iOS", "Rails", "HotwireNative", "TurboStreams", "Swift", "Stimulus", "BridgeComponent", "ActionCable"]
description: "Rails 8 Turbo Streams로 알림 뱃지를 실시간 브로드캐스트하고, Hotwire Native Bridge로 iOS 앱 아이콘 뱃지와 벨 버튼을 갱신하는 end-to-end 구현. 그리고 사이드 메뉴에서 동적 URL이 필요한 항목의 네비게이션 문제 해결."
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

Rails 8 기반 Hotwire Native iOS 앱에서 두 가지 문제를 해결한 기록이다.

1. **알림 뱃지 실시간 갱신** — 서버에서 알림이 생성되는 순간 앱 아이콘 뱃지와 내비게이션 벨 버튼을 즉시 업데이트
2. **사이드 메뉴 네비게이션 누락** — tournament ID 같은 동적 파라미터가 필요한 URL을 사이드 메뉴에서 올바르게 이동

---

## 1. 문제 배경

### 알림 뱃지

APNs 푸시 알림의 `badge` 필드를 설정하지 않으면 iOS 앱 아이콘에 숫자가 표시되지 않는다. 또한 알림을 읽어도 뱃지가 초기화되지 않는 문제가 있었다.

더 근본적인 문제는 **앱이 포그라운드에 있을 때** 알림을 받으면 APNs 푸시 자체가 오지 않으므로, Turbo Streams로 실시간 DOM 업데이트를 받아 이를 iOS 네이티브로 중계해야 한다는 점이다.

### 사이드 메뉴

네이티브 사이드 메뉴의 메뉴 항목은 Swift 코드에 하드코딩된 경로(`String`)를 사용한다. 그런데 일부 페이지는 `/resources/123/detail` 처럼 **동적 ID**가 포함된 URL이 필요하다.

이 ID를 메뉴 생성 시점에 모르면 경로를 `nil`로 두게 되고, `guard let path = path else { return }` 에서 조용히 무시된다.

---

## 2. 알림 뱃지 구현

### 전체 흐름

```
[서버: Notification 생성]
        ↓  after_create_commit
[Turbo::StreamsChannel.broadcast_update_to "notifications:#{user.id}"]
        ↓  ActionCable WebSocket
[Web: #notification-badge-count DOM 업데이트]
        ↓  MutationObserver (Stimulus badge controller)
[Bridge: this.send("update", { count })]
        ↓  HotwireNative BridgeComponent
[iOS: UNUserNotificationCenter.setBadgeCount(count)]
```

### Rails — Notification 모델

```ruby
class Notification < ApplicationRecord
  belongs_to :user

  after_create_commit :broadcast_badge_count
  after_update_commit :broadcast_badge_count

  private

  def broadcast_badge_count
    count = user.notifications.unread.count
    Turbo::StreamsChannel.broadcast_update_to(
      "notifications:#{user.id}",
      target: "notification-badge-count",
      html: count.to_s
    )
  end
end
```

모델 레벨에서 브로드캐스트를 처리하면 컨트롤러나 Job에서 직접 호출하는 것보다 누락될 가능성이 낮다. `after_create_commit` / `after_update_commit` 콜백은 트랜잭션이 커밋된 후에 실행되므로 안전하다.

### Rails — APNs 발송 시 badge 설정

```ruby
def send_apns_notification(device_token, title, body, data = {})
  unread_count = device_token.user&.notifications&.unread&.count.to_i + 1

  notification = Rpush::Apns2::Notification.new
  notification.app    = app
  notification.device_token = device_token.token
  notification.alert  = { title: title, body: body }
  notification.data   = data
  notification.sound  = "default"
  notification.badge  = unread_count  # ← 이 줄이 없으면 앱 아이콘 뱃지가 갱신되지 않음
  notification.save!
end
```

`+ 1`을 하는 이유는 현재 알림이 `create!` 이후에 바로 여기에 도달하지만, `unread.count` 쿼리가 새 레코드를 포함하지 않을 수 있는 타이밍 이슈 때문이다.

### Rails — 알림 확인 시 뱃지 초기화

```ruby
# ApplicationController
def clear_apns_badge(user)
  return unless defined?(Rpush::Apns2::Notification)

  app = Rpush::Apns2::App.find_by(name: "ios_app")
  return unless app

  user.device_tokens.where(platform: "ios").each do |dt|
    n = Rpush::Apns2::Notification.new
    n.app          = app
    n.device_token = dt.token
    n.badge        = 0
    n.content_available = true  # silent push
    n.save!
  rescue => e
    Rails.logger.warn("[Push/APNs] Badge clear failed: #{e.message}")
  end
end
```

`content_available: true`는 silent push로, 배너나 소리 없이 뱃지만 초기화한다.

```ruby
# NotificationsController
def index
  @notifications = current_user.notifications.order(created_at: :desc).limit(50)
  clear_apns_badge(current_user) if native_app_request?
end

def mark_all_read
  current_user.notifications.unread.update_all(read_at: Time.current)
  clear_apns_badge(current_user)
  redirect_to notifications_path
end
```

### 레이아웃 — Turbo Stream 구독

```erb
<% if user_signed_in? %>
  <%# ActionCable을 통해 해당 유저의 알림 채널 구독 %>
  <%= turbo_stream_from "notifications:#{current_user.id}" %>

  <%# Turbo Stream이 이 요소의 내용을 갱신 → badge_controller가 감지 %>
  <span
    id="notification-badge-count"
    data-controller="badge"
    data-badge-count-value="<%= current_user.notifications.unread.count %>"
    class="hidden"
  ><%= current_user.notifications.unread.count %></span>
<% end %>
```

`turbo_stream_from`은 `Turbo::StreamsChannel`에 구독을 생성한다. 서버에서 `broadcast_update_to "notifications:#{user.id}"` 를 호출하면 이 채널로 Turbo Stream 메시지가 전달된다.

### Stimulus — badge_controller.js

#### 프로젝트에 `@hotwired/hotwire-native-bridge`가 없는 경우

```javascript
// app/javascript/controllers/badge_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { count: Number }

  connect() {
    this._sendBadge(this.countValue)
    this._observer = new MutationObserver(() => {
      const count = parseInt(this.element.textContent.trim(), 10) || 0
      this.countValue = count
      this._sendBadge(count)
    })
    this._observer.observe(this.element, {
      childList: true, subtree: true, characterData: true
    })
  }

  disconnect() {
    this._observer?.disconnect()
  }

  _sendBadge(count) {
    // iOS Hotwire Native Bridge
    if (window.webkit?.messageHandlers?.badge) {
      window.webkit.messageHandlers.badge.postMessage({ count })
    }
    // 웹 UI 뱃지 갱신 (data-notification-badge 속성을 가진 요소)
    document.querySelectorAll("[data-notification-badge]").forEach((el) => {
      if (count > 0) {
        el.textContent = count > 9 ? "9+" : String(count)
        el.classList.remove("hidden")
      } else {
        el.classList.add("hidden")
      }
    })
  }
}
```

#### `@hotwired/hotwire-native-bridge` gem/package를 사용하는 경우

```javascript
// app/javascript/controllers/bridge/badge_controller.js
import { BridgeComponent } from "@hotwired/hotwire-native-bridge"

export default class extends BridgeComponent {
  static component = "badge"
  static values = { count: Number }

  connect() {
    super.connect()
    this._sendBadge(this.countValue)
    this._observer = new MutationObserver(() => {
      const count = parseInt(this.element.textContent.trim(), 10) || 0
      this.countValue = count
      this._sendBadge(count)
    })
    this._observer.observe(this.element, {
      childList: true, subtree: true, characterData: true
    })
  }

  disconnect() {
    this._observer?.disconnect()
    super.disconnect()
  }

  _sendBadge(count) {
    this.send("update", { count }, () => {})
  }
}
```

차이는 메시지 전송 방식이다. 전자는 `window.webkit.messageHandlers`를 직접 호출하고, 후자는 Hotwire Native Bridge 프로토콜을 통해 `onReceive(message:)`로 전달한다.

### iOS — BadgeComponent.swift

```swift
import HotwireNative
import UIKit
import UserNotifications

final class BadgeComponent: BridgeComponent {
    override class var name: String { "badge" }

    override func onReceive(message: Message) {
        guard message.event == "update",
              let data: Payload = message.data() else { return }
        apply(count: data.count)
        try? reply(to: "update")
    }

    private func apply(count: Int) {
        // 앱 아이콘 뱃지
        UNUserNotificationCenter.current().setBadgeCount(count)
        // 다른 UI 컴포넌트(탭바, 벨 버튼 등)에 변화 전파
        NotificationCenter.default.post(
            name: BadgeComponent.didUpdateNotification,
            object: nil,
            userInfo: ["count": count]
        )
    }

    static let didUpdateNotification = Notification.Name("BadgeComponentDidUpdate")

    private struct Payload: Decodable {
        let count: Int
    }
}
```

`AppDelegate`에 등록:

```swift
Hotwire.registerBridgeComponents([
    NotificationTokenComponent.self,
    FormComponent.self,
    ShareComponent.self,
    BadgeComponent.self,  // ← 추가
])
```

### iOS — 벨 버튼 뱃지 표시

```swift
// AppViewController.swift

override func viewDidLoad() {
    super.viewDidLoad()
    setupNavigationBarButtons()
    observeBadgeChanges()
}

private func observeBadgeChanges() {
    NotificationCenter.default.addObserver(
        forName: BadgeComponent.badgeDidChangeNotification,
        object: nil,
        queue: .main
    ) { [weak self] _ in
        self?.setupNavigationBarButtons()
    }
}

private func makeBellBarButton() -> UIBarButtonItem {
    let badgeCount = UIApplication.shared.applicationIconBadgeNumber
    let bellImage = UIImage(systemName: badgeCount > 0 ? "bell.badge" : "bell")
    let button = UIButton(type: .system)
    button.setImage(bellImage, for: .normal)
    button.tintColor = badgeCount > 0 ? .systemRed : .label
    button.addTarget(self, action: #selector(bellTapped), for: .touchUpInside)
    button.frame = CGRect(x: 0, y: 0, width: 36, height: 36)
    return UIBarButtonItem(customView: button)
}
```

`applicationIconBadgeNumber`는 `setBadgeCount()` 이후 즉시 반영되므로, `BadgeComponent`가 뱃지를 설정한 뒤 `NotificationCenter`로 알리면 `setupNavigationBarButtons()`가 재호출되어 `bell.badge` 아이콘으로 바뀐다.

---

## 3. 사이드 메뉴 동적 URL 문제

### 문제

```swift
// 기존 — path가 nil이면 아무 일도 일어나지 않음
MenuItem(icon: "square.grid.3x3", label: "대진표", path: nil)
```

```swift
// AppViewController의 delegate
func sideMenuDidSelect(path: String?) {
    guard let path = path else { return }  // nil이면 여기서 탈출
    navigator?.route(...)
}
```

### 해결 — 현재 URL에서 ID 추출

사이드 메뉴를 열기 직전에 현재 페이지 URL을 분석해 필요한 ID를 추출하는 방식이다.

```swift
// AppViewController.swift
@objc private func hamburgerTapped() {
    let sideMenu = SideMenuViewController()
    sideMenu.delegate = self
    // 현재 URL에서 resource ID 추출 후 전달
    sideMenu.resourceId = extractResourceId(from: currentVisitableURL)
    present(sideMenu, animated: false)
}

private func extractResourceId(from url: URL) -> String? {
    let components = url.pathComponents
    // URL 패턴: /resources/123/detail
    if let idx = components.firstIndex(of: "resources"), idx + 1 < components.count {
        let id = components[idx + 1]
        return Int(id) != nil ? id : nil  // 숫자 ID만 허용
    }
    return nil
}
```

```swift
// SideMenuViewController.swift
var resourceId: String?

private var menuItems: [MenuItem] {
    let detailPath = resourceId.map { "resources/\($0)/detail" }
    return [
        MenuItem(icon: "house",         label: "홈",      path: "dashboard"),
        MenuItem(icon: "square.grid.3x3", label: "상세 보기", path: detailPath),
        // path가 nil이면 메뉴 탭 시 아무 일도 일어나지 않으므로
        // 필요하다면 비활성화 스타일을 적용하는 것이 좋다.
    ]
}
```

`menuItems`를 `let` 저장 프로퍼티에서 `var` computed property로 바꾸면, 메뉴를 열 때마다 최신 `resourceId`를 참조한다.

### path가 nil일 때 UI 처리

사용자가 탭했을 때 반응이 없으면 혼란스러울 수 있다. 두 가지 선택지:

**A. 비활성화 스타일 적용**

```swift
private func makeMenuButton(item: MenuItem, ...) -> UIButton {
    var config = UIButton.Configuration.plain()
    config.baseForegroundColor = item.path == nil ? .tertiaryLabel : .label
    let button = UIButton(configuration: config)
    button.isUserInteractionEnabled = item.path != nil
    return button
}
```

**B. fallback URL 사용**

```swift
let detailPath = resourceId.map { "resources/\($0)/detail" } ?? "dashboard"
```

---

## 4. HotwireTabBarController 사용 시 탭바 뱃지

`HotwireTabBarController`를 사용하는 경우 탭바 아이템의 뱃지는 다음과 같이 설정한다:

```swift
// SceneController.swift
private func observeBadgeUpdates() {
    NotificationCenter.default.addObserver(
        forName: BadgeComponent.didUpdateNotification,
        object: nil,
        queue: .main
    ) { [weak self] notification in
        guard let self,
              let count = notification.userInfo?["count"] as? Int else { return }
        self.updateNotificationsTabBadge(count: count)
    }
}

private func updateNotificationsTabBadge(count: Int) {
    guard let index = AppTab.allCases.firstIndex(of: .notifications) else { return }
    let tabItem = tabBarController.tabBar.items?[index]
    tabItem?.badgeValue = count > 0 ? (count > 99 ? "99+" : "\(count)") : nil
}
```

알림 탭으로 전환할 때 뱃지 초기화:

```swift
private func handleDeepLink(url: URL) {
    if url.path().hasPrefix("/notifications") {
        tabBarController.selectedIndex = notificationsTabIndex
        clearNotificationBadge()
    }
    tabBarController.activeNavigator.route(url)
}

private func clearNotificationBadge() {
    UNUserNotificationCenter.current().setBadgeCount(0)
    updateNotificationsTabBadge(count: 0)
}
```

---

## 5. 정리

| 항목 | 기술 | 핵심 포인트 |
|------|------|-------------|
| 서버 → 웹 실시간 업데이트 | Turbo Streams + ActionCable | `broadcast_update_to` 로 DOM 직접 갱신 |
| 웹 → iOS 중계 | Hotwire Native Bridge | `BridgeComponent.onReceive` |
| 앱 아이콘 뱃지 | `UNUserNotificationCenter.setBadgeCount` | iOS 17+ 필수 API |
| APNs 뱃지 | `Rpush::Apns2::Notification.badge` | 푸시 페이로드에 명시해야 반영됨 |
| 포그라운드 뱃지 초기화 | silent push (`content_available: true`) | 배너 없이 뱃지만 초기화 |
| 동적 URL 메뉴 | computed `menuItems` + 현재 URL 파싱 | `currentVisitableURL.pathComponents` |

Rails 8의 Turbo Streams는 WebSocket 채널 관리나 커스텀 ActionCable 채널 없이 `broadcast_update_to` 한 줄로 특정 DOM 요소를 갱신할 수 있어서 간결하다. Hotwire Native Bridge와 조합하면 서버 이벤트를 네이티브 UI까지 매끄럽게 전달할 수 있다.
