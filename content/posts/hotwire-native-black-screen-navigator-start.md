---
title: "HotwireNative iOS 검정 화면(Black Screen) 디버깅 — navigator.start()를 빠뜨리면 생기는 일"
date: 2026-03-16
draft: true
tags: ["iOS", "HotwireNative", "Swift", "Turbo Native", "Debugging"]
description: "HotwireNative iOS 앱을 시뮬레이터에서 실행했는데 완전한 검정 화면만 나왔다. 네트워크는 연결되고, Rails 서버도 정상인데 왜 아무것도 안 보이는 걸까. 원인은 단 한 줄의 누락이었다."
---

HotwireNative로 iOS 앱을 개발하던 중 시뮬레이터에서 앱을 실행했을 때 완전한 검정 화면만 보이는 현상을 만났다.

---

## 증상

- iOS 시뮬레이터 앱 실행 → 상단 status bar만 보이고 나머지 전부 **검정 화면**
- Rails 서버는 `curl http://localhost:3000` 으로 정상 응답 확인 (HTTP 200)
- 크래시 로그 없음, 빌드 에러 없음

---

## 삽질 과정

### 1단계: ATS 문제인 줄 알았다

`http://localhost:3000`을 사용하는데 iOS App Transport Security가 HTTP를 막고 있지 않을까 의심했다. `Info.plist`에 ATS 예외 설정이 없었던 것도 사실이라 먼저 추가했다.

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

`project.yml`(XcodeGen 기반 프로젝트)에도 동일하게 반영했다. 그러나 **검정 화면은 그대로**였다.

### 2단계: 로그 분석

`xcrun simctl spawn` 으로 앱 로그를 스트리밍해서 확인했다.

```bash
xcrun simctl spawn <SIM_ID> log show \
  --predicate 'processImagePath CONTAINS "MyApp"' \
  --last 15s
```

로그에서 발견한 것:

```
[com.apple.CFNetwork:Summary] Task ... response_status=304, connection=1,
protocol="http/1.1", ... response_bytes=866
```

`/api/v1/path_configurations` 엔드포인트에 성공적으로 304 응답을 받고 있었다. **네트워크는 완전히 정상**이었다.

WebKit 프로세스도 정상 초기화되고 있었다:

```
[com.apple.WebKit:Process] WebProcessPool::createWebPage: Not delaying WebProcess launch
[com.apple.WebKit:Loading] WebPageProxy::constructor
```

그런데 그 이후로 **메인 URL(`http://localhost:3000`)에 대한 네트워크 요청이 전혀 없었다.**

### 3단계: Navigator 소스 코드 확인

HotwireNative 소스에서 `Navigator.swift`를 직접 열어봤다.

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

`start()` 메서드가 따로 존재했다. 그리고 `Navigator(configuration:)` 생성자는 **자동으로 `startLocation`으로 이동하지 않는다.**

---

## 원인

`AppDelegate`에서 Navigator를 생성한 뒤 `start()`를 호출하지 않았다.

```swift
// ❌ 잘못된 코드 — start() 누락
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()
// 여기서 끝. navigator는 빈 UINavigationController만 들고 있음
```

`rootViewController`는 빈 `UINavigationController`이고, 아무 ViewController도 push되지 않았기 때문에 화면 전체가 검정으로 보인 것이다.

---

## 해결

```swift
// ✅ 올바른 코드 — start() 명시 호출
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()

// ⚠️ 반드시 start()를 명시적으로 호출해야 합니다.
// Navigator는 init만으로 startLocation 로드를 시작하지 않습니다.
// 호출하지 않으면 rootViewController에 아무 ViewController도
// push되지 않아 앱 화면이 검정(black screen)으로 보입니다.
navigator?.start()
```

---

## 왜 이런 설계인가

의도적인 설계다. `start()`를 분리한 이유는:

1. Navigator 생성 직후 추가 설정(delegate, bridge components 등)을 할 시간을 준다
2. 뷰 계층이 완전히 준비된 뒤 첫 방문을 시작하도록 개발자가 제어권을 갖는다
3. `viewControllers.isEmpty` 체크로 이미 스택에 뭔가 있을 때 중복 호출을 방지한다

`Hotwire.config` 설정(`loadPathConfiguration`, `registerBridgeComponents` 등)도 `start()` 이전에 완료되어야 하므로, 이 순서가 중요하다.

---

## 올바른 초기화 순서

```swift
func application(_ application: UIApplication, didFinishLaunchingWithOptions ...) -> Bool {
    window = UIWindow(frame: UIScreen.main.bounds)

    // 1. Hotwire 전역 설정 먼저
    configureHotwire()

    // 2. Navigator 생성 + delegate 설정
    let configuration = Navigator.Configuration(name: "main", startLocation: startURL)
    navigator = Navigator(configuration: configuration)
    navigator?.delegate = self

    // 3. 윈도우 설정
    window?.rootViewController = navigator?.rootViewController
    window?.makeKeyAndVisible()

    // 4. 마지막으로 start() 호출
    navigator?.start()

    return true
}
```

---

## 정리

| 항목 | 내용 |
|------|------|
| 증상 | 앱 실행 시 완전한 검정 화면 |
| 착각한 원인 | ATS(App Transport Security) HTTP 차단 |
| 실제 원인 | `navigator?.start()` 미호출 |
| 해결 | `window?.makeKeyAndVisible()` 다음에 `navigator?.start()` 추가 |
| 디버깅 단서 | 로그에 메인 URL 네트워크 요청이 전혀 없었음 |

HotwireNative 공식 예제 코드를 그대로 옮겼다고 생각했는데, 한 줄을 빠뜨린 것이 원인이었다. 다음에 비슷한 현상을 만나면 "네트워크 요청 자체가 있는가"부터 로그로 확인하는 것이 빠른 진단법이다.
