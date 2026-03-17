---
title: "Rails 8 + Hotwire Native iOS — Real-time Notification Badge & Side Menu Navigation"
date: 2026-03-17
draft: false
tags: ["iOS", "Rails", "HotwireNative", "TurboStreams", "Swift", "Stimulus", "BridgeComponent", "ActionCable"]
description: "End-to-end implementation of real-time notification badge updates using Rails 8 Turbo Streams and Hotwire Native Bridge for iOS app icon and bell button. Also covers the dynamic URL navigation problem in native side menus."
---

Two problems solved while building a Rails 8 + Hotwire Native iOS app.

1. **Real-time notification badge** — instantly update the app icon badge and bell button the moment a notification is created on the server
2. **Side menu navigation failure** — correctly navigate to URLs that require dynamic parameters like a resource ID

---

## 1. Background

### Notification Badge

Without setting the `badge` field in APNs push notifications, no number appears on the iOS app icon. And even when notifications are read, the badge doesn't clear.

The deeper issue: **when the app is in the foreground**, no APNs push is delivered at all. That means we need Turbo Streams to push real-time DOM updates and relay them to native iOS.

### Side Menu

Native side menu items use hardcoded path strings (`String`) in Swift. But some pages require URLs with **dynamic IDs**, like `/resources/123/detail`.

If the ID isn't known when the menu is created, the path is set to `nil`, and `guard let path = path else { return }` silently does nothing.

---

## 2. Notification Badge Implementation

### End-to-End Flow

```
[Server: Notification created]
        ↓  after_create_commit
[Turbo::StreamsChannel.broadcast_update_to "notifications:#{user.id}"]
        ↓  ActionCable WebSocket
[Web: #notification-badge-count DOM update]
        ↓  MutationObserver (Stimulus badge controller)
[Bridge: this.send("update", { count })]
        ↓  HotwireNative BridgeComponent
[iOS: UNUserNotificationCenter.setBadgeCount(count)]
```

### Rails — Notification Model

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

Handling broadcasts at the model level means the notification count always stays in sync, regardless of where notifications are created or updated. `after_create_commit` / `after_update_commit` callbacks run after the transaction commits, so they're safe.

### Rails — Set badge in APNs payload

```ruby
def send_apns_notification(device_token, title, body, data = {})
  unread_count = device_token.user&.notifications&.unread&.count.to_i + 1

  notification = Rpush::Apns2::Notification.new
  notification.app    = app
  notification.device_token = device_token.token
  notification.alert  = { title: title, body: body }
  notification.data   = data
  notification.sound  = "default"
  notification.badge  = unread_count  # ← Without this, the app icon badge never updates
  notification.save!
end
```

The `+ 1` accounts for a potential timing race where the `unread.count` query might not yet include the newly created record when this method is called.

### Rails — Clear badge on read

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
    n.content_available = true  # silent push — no banner, no sound
    n.save!
  rescue => e
    Rails.logger.warn("[Push/APNs] Badge clear failed: #{e.message}")
  end
end
```

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

### Layout — Subscribe to Turbo Stream

```erb
<% if user_signed_in? %>
  <%= turbo_stream_from "notifications:#{current_user.id}" %>
  <span
    id="notification-badge-count"
    data-controller="badge"
    data-badge-count-value="<%= current_user.notifications.unread.count %>"
    class="hidden"
  ><%= current_user.notifications.unread.count %></span>
<% end %>
```

### Stimulus — badge_controller.js (without Bridge gem)

```javascript
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

  disconnect() { this._observer?.disconnect() }

  _sendBadge(count) {
    if (window.webkit?.messageHandlers?.badge) {
      window.webkit.messageHandlers.badge.postMessage({ count })
    }
  }
}
```

### Stimulus — bridge/badge_controller.js (with `@hotwired/hotwire-native-bridge`)

```javascript
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
    this._observer.observe(this.element, { childList: true, subtree: true, characterData: true })
  }

  disconnect() { this._observer?.disconnect(); super.disconnect() }

  _sendBadge(count) {
    this.send("update", { count }, () => {})
  }
}
```

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
        UNUserNotificationCenter.current().setBadgeCount(count)
        NotificationCenter.default.post(
            name: BadgeComponent.didUpdateNotification,
            object: nil,
            userInfo: ["count": count]
        )
    }

    static let didUpdateNotification = Notification.Name("BadgeComponentDidUpdate")

    private struct Payload: Decodable { let count: Int }
}
```

Register in `AppDelegate`:

```swift
Hotwire.registerBridgeComponents([
    FormComponent.self,
    ShareComponent.self,
    BadgeComponent.self,
])
```

---

## 3. Side Menu Dynamic URL

### Root Cause

```swift
// The path is nil because the resource ID isn't known at compile time
MenuItem(label: "Detail", path: nil)

// Delegate silently exits
func sideMenuDidSelect(path: String?) {
    guard let path = path else { return }  // ← exits here
    navigator?.route(...)
}
```

### Solution — Extract ID from the current URL

Parse the current page URL right before presenting the side menu:

```swift
@objc private func hamburgerTapped() {
    let sideMenu = SideMenuViewController()
    sideMenu.delegate = self
    sideMenu.resourceId = extractResourceId(from: currentVisitableURL)
    present(sideMenu, animated: false)
}

private func extractResourceId(from url: URL) -> String? {
    let components = url.pathComponents
    if let idx = components.firstIndex(of: "resources"), idx + 1 < components.count {
        let id = components[idx + 1]
        return Int(id) != nil ? id : nil
    }
    return nil
}
```

Use a computed `menuItems` property so it always reads the latest `resourceId`:

```swift
var resourceId: String?

private var menuItems: [MenuItem] {
    let detailPath = resourceId.map { "resources/\($0)/detail" }
    return [
        MenuItem(label: "Home",   path: "dashboard"),
        MenuItem(label: "Detail", path: detailPath),
    ]
}
```

---

## 4. Summary

| Concern | Technology | Key Point |
|---------|-----------|-----------|
| Server → Web realtime | Turbo Streams + ActionCable | `broadcast_update_to` updates DOM directly |
| Web → iOS relay | Hotwire Native Bridge | `BridgeComponent.onReceive` |
| App icon badge | `UNUserNotificationCenter.setBadgeCount` | Required API on iOS 17+ |
| APNs badge | `Rpush::Apns2::Notification.badge` | Must be set explicitly in payload |
| Foreground badge clear | Silent push (`content_available: true`) | Clears badge without a banner |
| Dynamic URL menus | Computed `menuItems` + URL parsing | `currentVisitableURL.pathComponents` |

Rails 8's Turbo Streams let you update a specific DOM element with a single `broadcast_update_to` call — no custom ActionCable channel management needed. Combined with Hotwire Native Bridge, you can seamlessly propagate server events all the way to native iOS UI.
