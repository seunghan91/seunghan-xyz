---
title: "HotwireNative iOS 검정 화면(Black Screen) 디버깅 — navigator.start()를 빠뜨리면 생기는 일"
date: 2026-03-16
draft: true
tags: ["iOS", "HotwireNative", "Swift", "Turbo Native", "Debugging"]
description: "HotwireNative iOS 앱을 시뮬레이터에서 실행했는데 완전한 검정 화면만 나왔다. 네트워크는 연결되고, Rails 서버도 정상인데 왜 아무것도 안 보이는 걸까. 원인은 단 한 줄의 누락이었다."
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

HotwireNative로 iOS 앱을 개발하던 중 시뮬레이터에서 앱을 실행했을 때 완전한 검정 화면만 보이는 현상을 만났다. 크래시도 없고, 빌드 에러도 없고, Xcode 콘솔에 뭔가 잘못됐다는 신호조차 없었다. 그냥 검정. 이 글은 그 디버깅 과정 전체와 실제 원인, 그리고 HotwireNative가 왜 이런 설계를 선택했는지를 정리한 기록이다. 같은 문제로 막혀 있다면 빠르게 답을 찾을 수 있을 것이고, 아직 만나지 않았다면 미리 알아두는 것이 한 시간을 아끼는 방법이다.

---

## 증상

- iOS 시뮬레이터 앱 실행 → 상단 status bar만 보이고 나머지 전부 **검정 화면**
- Rails 서버는 `curl http://localhost:3000` 으로 정상 응답 확인 (HTTP 200)
- 크래시 로그 없음, 빌드 에러 없음
- Xcode 콘솔에 명확한 에러 메시지 없음
- Xcode 입장에서는 앱이 정상 실행된 것처럼 보임

에러가 아무것도 없다는 것이 이 현상을 특히 혼란스럽게 만든다. 겉으로는 모든 것이 정상이다. 빌드되고, 설치되고, 실행된다. 그런데 화면은 검정이다.

---

## 삽질 과정

### 1단계: ATS 문제인 줄 알았다

`http://localhost:3000`을 사용하는데 iOS App Transport Security(ATS)가 평문 HTTP를 막고 있지 않을까 의심했다. iOS는 기본적으로 모든 네트워크 통신에 HTTPS를 강제한다. `Info.plist`에 ATS 예외 설정이 없었던 것도 사실이라 먼저 추가했다.

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

XcodeGen 기반 프로젝트라 `project.yml`에도 동일하게 반영했다:

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

그러나 **검정 화면은 그대로**였다. ATS가 원인이 아니거나, 적어도 유일한 원인은 아니었다.

### 2단계: 로그 분석

더 이상 추측하지 않고 `xcrun simctl`로 앱 로그를 직접 스트리밍해서 런타임에 실제로 무슨 일이 벌어지는지 확인했다:

```bash
xcrun simctl spawn <SIM_ID> log show \
  --predicate 'processImagePath CONTAINS "MyApp"' \
  --last 15s
```

시뮬레이터 ID를 모른다면:

```bash
xcrun simctl list devices | grep Booted
```

로그에서 발견한 것:

```
[com.apple.CFNetwork:Summary] Task ... response_status=304, connection=1,
protocol="http/1.1", ... response_bytes=866
```

`/api/v1/path_configurations` 엔드포인트에 304 응답(캐시에서)을 받고 있었다. 이것은 HotwireNative의 Path Configuration 요청이다. 프레임워크가 살아있고, 네트워크 요청을 만들고, 유효한 응답을 받고 있다는 뜻이다. **네트워크는 완전히 정상**이었다.

WebKit 프로세스도 정상 초기화되고 있었다:

```
[com.apple.WebKit:Process] WebProcessPool::createWebPage: Not delaying WebProcess launch
[com.apple.WebKit:Loading] WebPageProxy::constructor
```

그런데 여기서 결정적인 단서가 있었다. Path Configuration을 로드하고 WebKit이 초기화된 이후 — **메인 URL(`http://localhost:3000`)에 대한 네트워크 요청이 단 한 건도 없었다.** 프레임워크는 설정을 불러오고, WebKit을 준비하고, 그리고 멈췄다. 실제 페이지를 로드하려는 시도 자체가 없었던 것이다.

이 패턴이 핵심 진단 신호다. Path Configuration 요청은 로그에 나타나는데 그 뒤로 메인 페이지 요청이 없다면, 네비게이션 스택이 한 번도 시작되지 않은 것이다.

### 3단계: Navigator 소스 코드 확인

네비게이션이 시작되지 않았다는 증거를 확보한 뒤, Xcode의 패키지 의존성 패널에서 HotwireNative Swift 패키지의 `Navigator.swift`를 직접 열어봤다.

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

`start()` 메서드가 따로 존재했다. 그리고 `Navigator(configuration:)` 생성자는 **자동으로 `startLocation`으로 이동하지 않는다.** 모든 것을 준비하지만, 명시적으로 `start()`를 호출할 때까지 기다린다.

---

## 원인

`AppDelegate`에서 Navigator를 생성한 뒤 `start()`를 호출하지 않았다.

```swift
// ❌ 잘못된 코드 — start() 누락
navigator = Navigator(configuration: configuration)
navigator?.delegate = self
window?.rootViewController = navigator?.rootViewController
window?.makeKeyAndVisible()
// 여기서 끝. Navigator는 아무것도 push되지 않은 빈 UINavigationController만 들고 있음
```

`rootViewController`는 빈 `UINavigationController`이고, 아무 ViewController도 push되지 않았기 때문에 UIKit은 렌더링할 것이 없다. 그 결과 화면 전체가 검정으로 보인다. 검정은 보여줄 콘텐츠가 없는 윈도우의 기본 배경색이다.

앱은 기술적으로 정상 실행 중이다. 윈도우는 key이고 visible이다. 루트 뷰 컨트롤러도 할당되어 있다. 그런데 그 루트 뷰 컨트롤러의 스택이 비어 있으니 화면이 비어 있고, 비어 있으면 검정이다.

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

한 줄. 이것이 전부다.

---

## 왜 이런 설계인가

의도적인 API 설계이지, 실수가 아니다. `start()`를 초기화와 분리한 이유를 하나씩 살펴보자.

**1. 초기화 이후 설정 시간 확보**

Navigator를 생성한 직후에는 첫 페이지가 로드되기 전에 설정해야 할 것들이 있다: delegate 지정, bridge component 등록, 특정 경로 패턴에 대한 커스텀 뷰 컨트롤러 설정 등. `init`이 즉시 네비게이션을 시작하면, 설정이 완료되기 전에 첫 페이지 로딩이 시작되는 경쟁 상태(race condition)가 생긴다.

**2. 개발자가 네비게이션 시작 시점을 제어**

뷰 계층이 준비됐을 때를 아는 것은 프레임워크가 아니라 개발자다. 네비게이션 시작을 개발자 손에 맡기면 `window?.makeKeyAndVisible()` 이후, 윈도우가 올바른 상태가 된 뒤에 `start()`를 호출할 수 있다.

**3. 중복 초기화 방지**

`start()` 내부의 `viewControllers.isEmpty` 체크는 안전 장치다. 딥링크 핸들러나 푸시 알림 처리 때문에 이미 스택에 뭔가 push된 상황이라면, `start()`를 다시 호출해도 경고 로그를 남기고 early return한다. 이미 구성된 네비게이션 스택을 실수로 리셋하는 것을 방지한다.

**4. `Hotwire.config` 설정과의 정렬**

`Hotwire.config` 설정 — `registerBridgeComponents`로 bridge component 등록, `loadPathConfiguration`으로 경로 설정 로드, 커스텀 User-Agent 설정 등 — 모두 네비게이션이 시작되기 전에 완료되어야 한다. `start()`를 명시적으로 호출하는 구조는 이 설정 완료 시점을 자연스럽게 체크포인트로 만든다.

---

## 올바른 초기화 순서

`AppDelegate`에서 권장하는 전체 순서:

```swift
func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

    window = UIWindow(frame: UIScreen.main.bounds)

    // 1. Hotwire 전역 설정 먼저
    //    Bridge component 등록, Path Configuration 로드 등을 여기서
    configureHotwire()

    // 2. Navigator 생성 + delegate 설정
    //    이 시점에서 Navigator는 존재하지만 아직 어디에도 이동하지 않은 상태
    let configuration = Navigator.Configuration(
        name: "main",
        startLocation: startURL
    )
    navigator = Navigator(configuration: configuration)
    navigator?.delegate = self

    // 3. 윈도우 설정
    //    Navigator의 rootViewController는 아직 비어 있는 UINavigationController
    window?.rootViewController = navigator?.rootViewController
    window?.makeKeyAndVisible()

    // 4. 마지막으로 start() 호출
    //    윈도우가 visible 상태이고 모든 설정이 끝난 뒤에만 호출
    navigator?.start()

    return true
}
```

일반적인 `configureHotwire()` 함수는 다음과 같은 모습이다:

```swift
private func configureHotwire() {
    Hotwire.config.logLevel = .debug
    Hotwire.config.userAgent += "; MyApp/1.0"

    // 앱에서 사용하는 bridge component 등록
    Hotwire.registerBridgeComponents([
        FormComponent.self,
        MenuComponent.self,
    ])

    // 원격 URL + 로컬 fallback 방식으로 Path Configuration 로드
    Hotwire.loadPathConfiguration(from: [
        .file(Bundle.main.url(forResource: "path-configuration", withExtension: "json")!),
        .server(pathConfigURL),
    ])
}
```

이 모든 것이 `navigator?.start()` 호출 전에 완료되어야 한다.

---

## HotwireNative 검정 화면 디버깅 체크리스트

HotwireNative 앱에서 검정 화면을 만났다면 이 순서로 확인하자:

1. **`navigator?.start()` 호출 여부 확인** — 압도적으로 가장 흔한 원인이다.
2. **호출 순서 확인** — `start()`는 반드시 `window?.makeKeyAndVisible()` 이후에 호출해야 한다.
3. **로그에서 메인 URL 요청 확인** — `xcrun simctl spawn` 로그 스트리밍을 실행하고 `startLocation`으로의 네트워크 요청이 있는지 확인한다. 없다면 네비게이션이 시작되지 않은 것이다.
4. **ATS 설정 확인** — 개발 환경에서 `http://`를 사용한다면 `Info.plist`에 `NSAllowsLocalNetworking` 및/또는 `NSExceptionDomains` 설정이 올바른지 확인한다.
5. **`startLocation` 접근 가능 여부 확인** — URL이 올바른지, 서버가 실행 중인지 확인한다. `curl`로 200 또는 304가 나오면 충분하다.
6. **delegate 에러 확인** — `NavigatorDelegate` 메서드가 예상치 못한 조건으로 early return하고 있다면 네비게이션이 조용히 막힐 수 있다.

---

## 정리

| 항목 | 내용 |
|------|------|
| 증상 | 앱 실행 시 완전한 검정 화면 |
| 착각한 원인 | ATS(App Transport Security) HTTP 차단 |
| 실제 원인 | `navigator?.start()` 미호출 |
| 해결 | `window?.makeKeyAndVisible()` 다음에 `navigator?.start()` 추가 |
| 디버깅 단서 | 로그에 메인 URL 네트워크 요청이 전혀 없었음 |
| 이런 설계인 이유 | 설정과 네비게이션 분리로 개발자가 시작 시점을 제어하기 위해 |

---

## Key Takeaways

- **`Navigator.init`은 네비게이션을 시작하지 않는다.** 초기화와 네비게이션은 HotwireNative에서 의도적으로 분리되어 있다. `navigator?.start()`를 항상 명시적으로 호출해야 한다.
- **로그에 메인 URL 요청이 없다는 것이 결정적인 신호다.** Path Configuration 로드는 성공했는데 페이지 요청이 따라오지 않는다면, 네비게이션 스택이 시작되지 않은 것이다.
- **`xcrun simctl` 로그 스트리밍이 이런 침묵하는 장애의 가장 빠른 진단 도구다.** `os_log` 데이터는 프레임워크가 네트워크 레이어에서 정확히 무엇을 하는지 보여준다.
- **올바른 순서: 설정 → Navigator 생성 → 윈도우 설정 → `start()` 호출.** 이 순서를 벗어나면 `start()`가 있어도 미묘한 버그가 생길 수 있다.
- **ATS만으로는 검정 화면이 생기는 경우가 거의 없다.** ATS 실패는 명확한 에러 로그를 남긴다. 네트워크 활동 없이 조용히 검정 화면이 나타나는 것은 네비게이션이 한 번도 시작되지 않았다는 신호다.

HotwireNative 공식 예제 코드를 그대로 옮겼다고 생각했는데, 한 줄을 빠뜨린 것이 원인이었다. 다음에 HotwireNative 앱에서 크래시 없는 검정 화면을 만나면 첫 번째로 할 일은 로그에서 메인 URL 요청을 확인하는 것이다. 요청이 없다면 해결책은 거의 확실히 `navigator?.start()`다.
