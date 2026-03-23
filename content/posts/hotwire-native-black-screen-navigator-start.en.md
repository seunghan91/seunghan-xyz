---
title: "HotwireNative iOS Black Screen Debug — What Happens When You Forget navigator.start()"
date: 2026-03-16
draft: true
tags: ["iOS", "HotwireNative", "Swift", "Turbo Native", "Debugging"]
description: "Launched a HotwireNative iOS app on the simulator and got a completely black screen. Network was fine, Rails server was responding — so why was nothing showing? The culprit was one missing line."
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

While developing an iOS app with HotwireNative, I ran into a completely black screen on the simulator. No crash, no error — just black. This post documents the full debugging process, the actual root cause, and why HotwireNative is designed this way. If you've hit the same wall, you'll find the answer quickly here. If you haven't yet, consider this a heads-up that will save you an hour.

---

## Symptoms

- Launch app on iOS Simulator → Only the status bar visible, entire screen is **black**
- Rails server responding normally (`curl http://localhost:3000` → HTTP 200)
- No crash logs, no build errors
- Xcode console shows no obvious errors
- App appears to launch successfully from Xcode's perspective

The absence of any error is what makes this particularly disorienting. Everything looks fine on the surface. The app builds, installs, and launches — but the screen stays black.

---

## The Debug Journey

### Step 1: Suspected ATS

Since the app uses `http://localhost:3000`, my first thought was that iOS App Transport Security (ATS) was blocking plain HTTP. By default, iOS enforces HTTPS for all network traffic. The `Info.plist` didn't have any ATS exception, so I added one:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
    <key>NSExceptionDomains</key>
    <dict>
        <key>localhost</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

Also reflected in `project.yml` (XcodeGen-based project):

```yaml
targets:
  MyApp:
    info:
      properties:
        NSAppTransportSecurity:
          NSAllowsLocalNetworking: true
          NSExceptionDomains:
            localhost:
              NSExceptionAllowsInsecureHTTPLoads: true
```

But the **black screen remained**. So ATS was not the culprit — or at minimum, it wasn't the only issue.

### Step 2: Log Analysis

Rather than guessing further, I streamed app logs directly via `xcrun simctl` to see what the app was actually doing at runtime:

```bash
xcrun simctl spawn <SIM_ID> log show \
  --predicate 'processImagePath CONTAINS "MyApp"' \
  --last 15s
```

To find your simulator ID, run:

```bash
xcrun simctl list devices | grep Booted
```

What the logs showed:

```
[com.apple.CFNetwork:Summary] Task ... response_status=304,
protocol="http/1.1", ... response_bytes=866
```

The `/api/v1/path_configurations` endpoint was responding with 304 (from local cache). This is the HotwireNative path configuration request — the framework was alive, making network calls, and getting valid responses. **Network was completely fine.**

WebKit processes were initializing normally too:

```
[com.apple.WebKit:Process] WebProcessPool::createWebPage: Not delaying WebProcess launch
[com.apple.WebKit:Loading] WebPageProxy::constructor
```

But here is the critical detail: after the path configuration loaded and WebKit initialized — **there was no network request for the main URL (`http://localhost:3000`) whatsoever.** The framework loaded its configuration, set up WebKit, and then... stopped. It never attempted to load the actual page.

This pattern is the key diagnostic signal. If the path configuration request appears in your logs but no main page request follows, the navigation stack was never started.

### Step 3: Reading the Navigator Source

With the evidence pointing to navigation never starting, I opened `Navigator.swift` from the HotwireNative Swift package directly in Xcode (via the package dependencies pane):

```swift
// Navigator.swift (HotwireNative)

/// Routes to the start location provided in the `Navigator.Configuration`.
public func start() {
    guard rootViewController.viewControllers.isEmpty,
    modalRootViewController.viewControllers.isEmpty else {
        logger.warning("Start can only be run when there are no view controllers on the stack.")
        return
    }

    route(configuration.startLocation)
}
```

There it was. A separate `start()` method exists explicitly for triggering the first navigation. The `Navigator(configuration:)` initializer **does not automatically navigate to `startLocation`.** It sets everything up but waits for you to explicitly call `start()`.

---

## Root Cause

`start()` was never called after creating the Navigator in `AppDelegate`.

```swift
// Wrong — missing start()
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()
// That's it. Navigator holds an empty UINavigationController with nothing pushed onto it.
```

`rootViewController` is an empty `UINavigationController`. With no view controllers pushed onto it, UIKit has nothing to render — so it displays black, which is the default background color for a window with no visible content.

The app is technically running fine. The window is key and visible. The root view controller is assigned. But that root view controller has an empty stack, so the screen is empty — and empty means black.

---

## The Fix

```swift
// Correct — explicitly call start()
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()

// start() must be called explicitly.
// Navigator does NOT automatically navigate to startLocation on init.
// Without this call, nothing gets pushed onto the rootViewController,
// resulting in a completely black screen.
navigator?.start()
```

One line. That is the entire fix.

---

## Why Is It Designed This Way?

This is intentional API design, not an oversight. The reason `start()` is decoupled from initialization:

**1. Post-initialization configuration window**

After creating a Navigator, you typically need to set up several things before the first page loads: the delegate, bridge component registrations, custom view controllers for specific path patterns, and so on. If `init` triggered navigation immediately, you would have a race condition where the first page starts loading before your configuration is complete.

**2. Developer-controlled navigation timing**

You know exactly when your view hierarchy is ready. The framework doesn't. Putting navigation initiation in your hands means you can defer `start()` until `window?.makeKeyAndVisible()` has been called and the window is in the correct state.

**3. Guard against duplicate initialization**

The `viewControllers.isEmpty` check inside `start()` is a safety valve. If something already pushed a view controller onto the stack (perhaps from a deep link handler or a push notification), calling `start()` again will log a warning and return early — preventing you from accidentally resetting a navigation stack that was already populated.

**4. Alignment with Hotwire.config setup**

`Hotwire.config` setup — registering bridge components with `registerBridgeComponents`, loading path configurations with `loadPathConfiguration`, setting custom user agents — all of this must complete before navigation begins. Explicitly calling `start()` after configuration gives you a natural checkpoint.

---

## Correct Initialization Order

Here is the full recommended sequence for `AppDelegate`:

```swift
func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

    window = UIWindow(frame: UIScreen.main.bounds)

    // 1. Configure Hotwire globals first.
    //    Register bridge components and path configuration here.
    configureHotwire()

    // 2. Create Navigator and set delegate.
    //    At this point, the navigator exists but hasn't navigated anywhere yet.
    let configuration = Navigator.Configuration(
        name: "main",
        startLocation: startURL
    )
    navigator = Navigator(configuration: configuration)
    navigator?.delegate = self

    // 3. Assign root view controller and make window visible.
    //    The navigator's rootViewController is an empty UINavigationController.
    window?.rootViewController = navigator?.rootViewController
    window?.makeKeyAndVisible()

    // 4. Call start() — this triggers the first navigation to startLocation.
    //    Only call this after the window is visible and all configuration is done.
    navigator?.start()

    return true
}
```

A typical `configureHotwire()` function looks like this:

```swift
private func configureHotwire() {
    Hotwire.config.logLevel = .debug
    Hotwire.config.userAgent += "; MyApp/1.0"

    // Register bridge components your app uses
    Hotwire.registerBridgeComponents([
        FormComponent.self,
        MenuComponent.self,
    ])

    // Load path configuration from a remote URL + local fallback
    Hotwire.loadPathConfiguration(from: [
        .file(Bundle.main.url(forResource: "path-configuration", withExtension: "json")!),
        .server(pathConfigURL),
    ])
}
```

All of this must complete before `navigator?.start()` is called.

---

## Debugging Checklist for Black Screen in HotwireNative

If you encounter a black screen with HotwireNative, work through this checklist in order:

1. **Check if `navigator?.start()` is called** — This is the most common cause by far.
2. **Confirm the call order** — `start()` must come after `window?.makeKeyAndVisible()`.
3. **Inspect logs for main URL requests** — Run `xcrun simctl spawn` log streaming and look for a network request to your `startLocation`. If it's absent, navigation never started.
4. **Check ATS configuration** — If using `http://` in development, ensure `NSAllowsLocalNetworking` and/or `NSExceptionDomains` are set correctly in `Info.plist`.
5. **Verify `startLocation` is reachable** — Confirm the URL is correct and the server is running. A 200 or 304 from `curl` is sufficient.
6. **Look for delegate errors** — If `NavigatorDelegate` methods are returning early due to unexpected conditions, navigation may be silently blocked.

---

## Summary

| Item | Detail |
|------|--------|
| Symptom | Completely black screen on launch |
| Initial suspect | ATS blocking HTTP on localhost |
| Actual cause | `navigator?.start()` not called |
| Fix | Add `navigator?.start()` after `window?.makeKeyAndVisible()` |
| Debug clue | No network request for the main URL appeared in logs |
| Why it's designed this way | Explicit start separates configuration from navigation, giving developers control over timing |

---

## Key Takeaways

- **`Navigator.init` does not navigate.** Initialization and navigation are intentionally separated in HotwireNative. Always call `navigator?.start()` explicitly.
- **The absence of a main URL request in logs is the definitive signal.** If path configuration loads but no page request follows, the navigation stack was never started.
- **Log streaming via `xcrun simctl` is the fastest diagnostic tool** for silent failures like this. `os_log` data exposes exactly what the framework is doing at the network layer.
- **Correct order: configure → create navigator → set window → call `start()`.** Deviating from this order can produce subtle bugs even when `start()` is present.
- **ATS is almost never the cause of a black screen by itself.** ATS failures produce explicit error logs. A silent black screen with no network activity points to navigation never starting.

I thought I had copied the official HotwireNative example code exactly — but missed one line. Next time you see a black screen with no crash in a HotwireNative app, your first move should be to check the logs for the main URL request. If it is not there, the fix is almost certainly `navigator?.start()`.
