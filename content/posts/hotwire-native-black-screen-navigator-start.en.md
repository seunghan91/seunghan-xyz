---
title: "HotwireNative iOS Black Screen Debug — What Happens When You Forget navigator.start()"
date: 2026-03-16
draft: true
tags: ["iOS", "HotwireNative", "Swift", "Turbo Native", "Debugging"]
description: "Launched a HotwireNative iOS app on the simulator and got a completely black screen. Network was fine, Rails server was responding — so why was nothing showing? The culprit was one missing line."
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

While developing an iOS app with HotwireNative, I ran into a completely black screen on the simulator. No crash, no error — just black.

---

## Symptoms

- Launch app on iOS Simulator → Only the status bar visible, entire screen is **black**
- Rails server responding normally (`curl http://localhost:3000` → HTTP 200)
- No crash logs, no build errors

---

## The Debug Journey

### Step 1: Suspected ATS

Since the app uses `http://localhost:3000`, my first thought was that iOS App Transport Security was blocking plain HTTP. The `Info.plist` didn't have any ATS exception, so I added one:

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

Also reflected in `project.yml` (XcodeGen-based project). But the **black screen remained**.

### Step 2: Log Analysis

Streamed app logs via `xcrun simctl`:

```bash
xcrun simctl spawn <SIM_ID> log show \
  --predicate 'processImagePath CONTAINS "MyApp"' \
  --last 15s
```

What I found:

```
[com.apple.CFNetwork:Summary] Task ... response_status=304,
protocol="http/1.1", ... response_bytes=866
```

The `/api/v1/path_configurations` endpoint was responding with 304 (from cache). **Network was completely fine.**

WebKit processes were initializing normally too:

```
[com.apple.WebKit:Process] WebProcessPool::createWebPage: Not delaying WebProcess launch
[com.apple.WebKit:Loading] WebPageProxy::constructor
```

But after this — **no network request for the main URL (`http://localhost:3000`) whatsoever.**

### Step 3: Reading the Navigator Source

I opened `Navigator.swift` from the HotwireNative package:

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

There was a separate `start()` method. And the `Navigator(configuration:)` initializer **does not automatically navigate to `startLocation`.**

---

## Root Cause

`start()` was never called after creating the Navigator in `AppDelegate`.

```swift
// ❌ Wrong — missing start()
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()
// Done. Navigator holds an empty UINavigationController with nothing pushed.
```

`rootViewController` was an empty `UINavigationController` with no view controllers pushed onto it — hence the black screen.

---

## The Fix

```swift
// ✅ Correct — explicitly call start()
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()

// ⚠️ start() must be called explicitly.
// Navigator does NOT automatically navigate to startLocation on init.
// Without this call, nothing gets pushed onto the rootViewController,
// resulting in a completely black screen.
navigator?.start()
```

---

## Why Is It Designed This Way?

This is intentional. The reason `start()` is separate:

1. Gives you time to configure the Navigator (set delegate, register bridge components, etc.) before the first visit
2. Lets the developer control exactly when navigation starts, after the view hierarchy is fully ready
3. The `viewControllers.isEmpty` guard prevents duplicate calls if something is already on the stack

`Hotwire.config` setup (`loadPathConfiguration`, `registerBridgeComponents`, etc.) also needs to complete before `start()`, so this ordering matters.

---

## Correct Initialization Order

```swift
func application(_ application: UIApplication, didFinishLaunchingWithOptions ...) -> Bool {
    window = UIWindow(frame: UIScreen.main.bounds)

    // 1. Configure Hotwire globals first
    configureHotwire()

    // 2. Create Navigator + set delegate
    let configuration = Navigator.Configuration(name: "main", startLocation: startURL)
    navigator = Navigator(configuration: configuration)
    navigator?.delegate = self

    // 3. Set up the window
    window?.rootViewController = navigator?.rootViewController
    window?.makeKeyAndVisible()

    // 4. Call start() last
    navigator?.start()

    return true
}
```

---

## Summary

| Item | Detail |
|------|--------|
| Symptom | Completely black screen on launch |
| Initial suspect | ATS blocking HTTP on localhost |
| Actual cause | `navigator?.start()` not called |
| Fix | Add `navigator?.start()` after `window?.makeKeyAndVisible()` |
| Debug clue | No network request for the main URL appeared in logs at all |

I thought I had copied the official HotwireNative example code exactly — but missed one line. Next time you see a black screen with no crash, check whether the main URL is being requested at all in the logs. If it isn't, the navigation stack was probably never started.
