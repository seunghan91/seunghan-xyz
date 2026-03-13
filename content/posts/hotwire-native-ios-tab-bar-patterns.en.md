---
title: "Hotwire Native iOS Tab Bar App — HotwireTabBarController Implementation and Debugging"
date: 2025-12-26
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "Swift", "HotwireTabBarController", "WKWebView", "TestFlight", "Puma"]
description: "Problems encountered building a native tab bar iOS app with Rails + Hotwire Native — background WebView suspend, missing export compliance, duplicate back navigation, and Puma thread exhaustion."
cover:
  image: "/images/og/hotwire-native-ios-tab-bar-patterns.png"
  alt: "Hotwire Native Ios Tab Bar Patterns"
  hidden: true
---


Here are the problems encountered when switching from a single Navigator to the **HotwireTabBarController** pattern while wrapping a Rails app with Hotwire Native. Bugs that were invisible in the simulator surfaced on TestFlight, and local dev environment settings got tangled -- multiple points where time was wasted.

---

## 1. HotwireTabBarController Basic Structure

Instead of a single Navigator, each tab has its own independent Navigator and WKWebView.

```swift
// AppTab.swift
enum AppTab: String, CaseIterable {
    case home, ai, request

    var systemImage: String {
        switch self {
        case .home:    return "house"
        case .ai:      return "message"
        case .request: return "checkmark.circle"
        }
    }

    var selectedSystemImage: String {
        switch self {
        case .home:    return "house.fill"
        case .ai:      return "message.fill"
        case .request: return "checkmark.circle.fill"
        }
    }

    var url: URL {
        let base = AppDelegate.baseURL
        switch self {
        case .home:    return base.appendingPathComponent("dashboard")
        case .ai:      return base.appendingPathComponent("conversations")
        case .request: return base.appendingPathComponent("service_requests")
        }
    }

    var hotwireTab: HotwireTab {
        HotwireTab(
            title: "",
            image: UIImage(systemName: systemImage)!,
            selectedImage: UIImage(systemName: selectedSystemImage)!,
            url: url
        )
    }
}
```

```swift
// SceneController.swift core part
private lazy var tabBarController: HotwireTabBarController = {
    let controller = HotwireTabBarController(navigatorDelegate: self)
    controller.load(AppTab.allCases.map(\.hotwireTab))

    // Show only tab icons, remove text
    controller.viewControllers?.forEach { vc in
        vc.tabBarItem.title = nil
        vc.tabBarItem.imageInsets = UIEdgeInsets(top: 6, left: 0, bottom: -6, right: 0)
        (vc as? UINavigationController)?.delegate = self
    }
    return controller
}()
```

To remove tab titles and keep only icons, both `tabBarItem.title = nil` and `imageInsets` adjustment are needed. Setting only title to nil leaves the icon position unchanged, looking awkward.

---

## 2. Pinning a Notification Button to the Navigation Bar

To maintain a bell icon in the top right on every screen transition, use `UINavigationControllerDelegate`.

```swift
extension SceneController: UINavigationControllerDelegate {
    func navigationController(
        _ navigationController: UINavigationController,
        didShow viewController: UIViewController,
        animated: Bool
    ) {
        addNavBarButtons(to: viewController)
    }

    private func addNavBarButtons(to viewController: UIViewController) {
        viewController.navigationItem.title = ""

        let notificationButton = UIBarButtonItem(
            image: UIImage(systemName: "bell"),
            style: .plain,
            target: self,
            action: #selector(openNotifications)
        )
        notificationButton.tintColor = UIColor.secondaryLabel
        viewController.navigationItem.rightBarButtonItem = notificationButton
    }

    @objc private func openNotifications() {
        tabBarController.activeNavigator.route(
            AppDelegate.baseURL.appendingPathComponent("notifications")
        )
    }
}
```

`didShow` is called after all transitions (push/pop/replace), so the button persists on every screen.

---

## 3. Authentication Screen Modal Handling

```swift
extension SceneController: NavigatorDelegate {
    func handle(proposal: VisitProposal) -> ProposalResult {
        let path = proposal.url.path()

        if path.hasPrefix("/sign_in") || path.hasPrefix("/sign_up") {
            guard tabBarController.presentedViewController == nil else {
                return .reject
            }
            let authVC = AuthViewController(url: proposal.url)
            tabBarController.present(authVC, animated: true)
            return .reject
        }

        if !isAppURL(proposal.url) {
            let safariVC = SFSafariViewController(url: proposal.url)
            tabBarController.activeNavigator.rootViewController.present(safariVC, animated: true)
            return .reject
        }

        return .accept
    }
}
```

The `presentedViewController != nil` check is important. If all 3 tabs redirect to `/sign_in` simultaneously, the modal tries to appear 3 times. Only allow the first and reject the rest.

---

## 4. Background Tab WebView Suspend -> NSURLErrorCancelled (-999)

### Symptoms

On first app launch, a "Network error occurred" dialog appears. The server is fine and curl returns 200, but only the app shows an error.

### Cause

`HotwireTabBarController` loads all tabs simultaneously. The active tab (tab 1) WebView loads normally in the foreground, but inactive tabs (tab 2, 3) have their WebProcess immediately suspended by iOS. HTTP requests in progress get cancelled, producing `NSURLErrorCancelled (-999)` and triggering `visitableDidFailRequest`.

Simulator log confirmation:
```
WebProcessProxy::didChangeThrottleState(Foreground)
WebProcessProxy::didChangeThrottleState(Suspended)  <- Immediately suspended
```

### Fix

```swift
func visitableDidFailRequest(
    _ visitable: any Visitable,
    error: Error,
    retryHandler: RetryBlock?
) {
    let nsError = error as NSError
    // -999: Request cancelled due to background tab WebView suspend
    // HotwireTabBarController auto-reloads on tab switch, so ignore
    guard nsError.code != NSURLErrorCancelled else { return }

    let alert = UIAlertController(
        title: "Connection Error",
        message: "A network error occurred. Please try again.",
        preferredStyle: .alert
    )
    if let retryHandler {
        alert.addAction(UIAlertAction(title: "Retry", style: .default) { _ in retryHandler() })
    }
    alert.addAction(UIAlertAction(title: "OK", style: .cancel))
    tabBarController.activeNavigator.rootViewController.present(alert, animated: true)
}
```

When the tab is switched, HotwireTabBarController automatically reloads that tab's page, so it is safe to simply ignore the error.

---

## 5. Debug/Release URL Separation

A TestFlight build crashed with a log pointing to `UINavigationController.init(rootViewController:)`. It turned out `baseURL` was hardcoded to `localhost:3001`, causing connection failure on real devices and a crash during initialization.

```swift
// AppDelegate.swift
static let baseURL: URL = {
    if let envURL = ProcessInfo.processInfo.environment["KRX_AI_BASE_URL"] {
        return URL(string: envURL)!
    }
    #if DEBUG
    return URL(string: "http://localhost:3001")!
    #else
    return URL(string: "https://your-production-server.com")!
    #endif
}()
```

Use `#if DEBUG` / `#else` to separate Debug (simulator) and Release (TestFlight/App Store). Making environment variable injection possible also adds flexibility for CI/CD.

---

## 6. Duplicate Back Button (Web + Native)

When a Rails view has a back link and the native navigation bar also has a back arrow, it causes user confusion.

### Solution -- A Combination of Approaches

**1. Hide web back button with CSS**

```css
/* application.css */
.native-app .native-back { display: none !important; }
```

**2. Add native-app class in Rails layout**

```erb
<%# application.html.erb %>
<% native_app = hotwire_native_app? %>
<body class="<%= 'native-app' if native_app %>">
```

`hotwire_native_app?` is a helper provided by turbo-rails. Returns true if "Turbo Native" is in the User-Agent.

**3. Add class to each view's back button**

```erb
<%= link_to "<- Back", some_path, class: "native-back" %>
```

**4. Set tab roots to replace in path-configuration.json**

```json
{
  "patterns": ["^/dashboard$", "^/conversations$", "^/service_requests$"],
  "properties": {
    "context": "default",
    "presentation": "replace"
  }
}
```

Setting tab root URLs to `presentation: replace` prevents them from stacking in the navigation stack. This means the native back arrow does not appear on tab roots.

**5. Remove back button text**

```swift
// AppDelegate.swift
Hotwire.config.backButtonDisplayMode = .minimal
```

Shows only the arrow and hides the previous page title text.

---

## 7. Puma Thread Settings -- Preparing for Simultaneous Tab Loading

`HotwireTabBarController` sends as many requests simultaneously as there are tabs. If the default Puma threads (2) are insufficient, requests queue up.

```ruby
# config/puma.rb
threads_count = ENV.fetch("RAILS_MAX_THREADS", 5)
threads threads_count, threads_count
```

With 3 tabs, set at least 3, with some margin at 5.

Explicitly specifying the local development port also makes it easy to match the iOS app's baseURL:

```ruby
port ENV.fetch("PORT", 3001)
```

```
# Procfile.dev
web: bin/rails server -p 3001
```

---

## 8. Missing Export Compliance Documentation (ITSAppUsesNonExemptEncryption)

When uploading TestFlight/App Store builds, the "Missing Export Compliance Documentation" warning keeps appearing. For apps that only use HTTPS without implementing separate encryption, add the following to `Info.plist`.

If using XcodeGen, in `project.yml`:

```yaml
info:
  properties:
    ITSAppUsesNonExemptEncryption: false
```

If adding directly to `Info.plist`:
```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

This eliminates the hassle of manually answering in App Store Connect for every build.

---

## 9. make sim -- Local Simulator Build Automation

`make testflight` always builds Release, connecting to the production server without a local server. For local development with Debug builds on the simulator, a separate target is needed.

```makefile
SIM_DEVICE_ID = <your-simulator-udid>

sim: gen-ios
	@echo "Building for Simulator (Debug)..."
	xcodebuild build \
		-project ios/$(SCHEME).xcodeproj \
		-scheme $(SCHEME) \
		-configuration Debug \
		-destination "platform=iOS Simulator,id=$(SIM_DEVICE_ID)" \
		-derivedDataPath ios/build/sim \
		| xcpretty 2>/dev/null || true
	xcrun simctl boot $(SIM_DEVICE_ID) 2>/dev/null || true
	xcrun simctl install $(SIM_DEVICE_ID) \
		"ios/build/sim/Build/Products/Debug-iphonesimulator/$(SCHEME).app"
	xcrun simctl launch --console-pty $(SIM_DEVICE_ID) com.your.bundle.id
	open -a Simulator
```

Local workflow:
```bash
# Terminal 1
make dev       # Rails server (localhost:3001)

# Terminal 2
make sim       # Simulator Debug build + launch
```

---

## Summary

| Problem | Cause | Solution |
|------|------|------|
| "Connection error" on app launch | Background tab WebView suspend -> NSURLErrorCancelled | Ignore `-999` error |
| TestFlight crash | localhost hardcoded in Release build | `#if DEBUG` / `#else` branching |
| Duplicate back button | Web back button + native navigation bar | CSS `.native-back` hide + path-config `replace` |
| Export compliance warning | `ITSAppUsesNonExemptEncryption` not declared | Add `false` to `project.yml` |
| Simulator connection failure | Procfile port not specified (3000) + app expects 3001 | `bin/rails server -p 3001` |
| Simultaneous request failure | Puma threads 2 < 3 tabs loading simultaneously | Increase threads to 5 |
