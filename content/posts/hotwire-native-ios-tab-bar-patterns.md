---
title: "Hotwire Native iOS 탭바 앱 구축 — HotwireTabBarController 적용기와 삽질 모음"
date: 2025-12-26
draft: false
tags: ["Rails", "Hotwire Native", "iOS", "Swift", "HotwireTabBarController", "WKWebView", "TestFlight", "Puma"]
description: "Rails + Hotwire Native로 네이티브 탭바 iOS 앱을 만들면서 겪은 문제들 — 백그라운드 WebView suspend, 수출 규정 누락, 뒤로가기 중복, Puma 스레드 부족까지 정리했다."
cover:
  image: "/images/og/hotwire-native-ios-tab-bar-patterns.png"
  alt: "Hotwire Native Ios Tab Bar Patterns"
  hidden: true
---

Rails 앱을 Hotwire Native로 래핑할 때 단일 Navigator 대신 **HotwireTabBarController** 패턴으로 전환하면서 생긴 문제들을 정리한다.
시뮬레이터에서는 안 보이던 버그가 TestFlight에서 터지고, 로컬 개발 환경 설정이 꼬이는 등 여러 지점에서 시간을 날렸다.

---

## 1. HotwireTabBarController 기본 구조

단일 Navigator 대신 탭별로 독립적인 Navigator와 WKWebView를 갖는 구조다.

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
// SceneController.swift 핵심 부분
private lazy var tabBarController: HotwireTabBarController = {
    let controller = HotwireTabBarController(navigatorDelegate: self)
    controller.load(AppTab.allCases.map(\.hotwireTab))

    // 탭 아이콘만 표시, 텍스트 제거
    controller.viewControllers?.forEach { vc in
        vc.tabBarItem.title = nil
        vc.tabBarItem.imageInsets = UIEdgeInsets(top: 6, left: 0, bottom: -6, right: 0)
        (vc as? UINavigationController)?.delegate = self
    }
    return controller
}()
```

탭 제목을 없애고 아이콘만 남기려면 `tabBarItem.title = nil`과 `imageInsets` 조정이 같이 필요하다.
title만 nil로 하면 아이콘 위치가 내려가지 않아서 어색하게 보인다.

---

## 2. 네비게이션 바에 알림 버튼 고정

모든 화면 전환 시마다 우측 상단에 벨 아이콘을 유지하려면 `UINavigationControllerDelegate`를 사용한다.

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

`didShow`는 push/pop/replace 모든 전환 후 호출되므로 어떤 화면이든 버튼이 유지된다.

---

## 3. 인증 화면 모달 처리

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

`presentedViewController != nil` 체크가 중요하다. 탭 3개가 동시에 `/sign_in`으로 리디렉트되면 모달이 3번 뜨려고 한다. 첫 번째만 허용하고 나머지는 reject.

---

## 4. 백그라운드 탭 WebView suspend → NSURLErrorCancelled (-999)

### 증상

앱을 처음 실행하면 "네트워크 오류가 발생했습니다" 다이얼로그가 뜬다. 서버는 정상이고 curl로도 200 응답이 오는데 앱에서만 에러가 난다.

### 원인

`HotwireTabBarController`는 모든 탭을 동시에 로드한다. 활성 탭(tab 1)의 WebView는 포그라운드에서 정상 로드되지만, 비활성 탭(tab 2, 3)의 WebProcess는 iOS가 즉시 suspend한다. 이때 진행 중이던 HTTP 요청이 취소되면서 `NSURLErrorCancelled (-999)`가 발생하고 `visitableDidFailRequest`가 호출된다.

시뮬레이터 로그로 확인:
```
WebProcessProxy::didChangeThrottleState(Foreground)
WebProcessProxy::didChangeThrottleState(Suspended)  ← 바로 suspend
```

### 수정

```swift
func visitableDidFailRequest(
    _ visitable: any Visitable,
    error: Error,
    retryHandler: RetryBlock?
) {
    let nsError = error as NSError
    // -999: 백그라운드 탭 WebView suspend로 인한 요청 취소
    // 탭 전환 시 HotwireTabBarController가 자동 재로드하므로 무시
    guard nsError.code != NSURLErrorCancelled else { return }

    let alert = UIAlertController(
        title: "연결 오류",
        message: "네트워크 오류가 발생했습니다. 다시 시도해주세요.",
        preferredStyle: .alert
    )
    if let retryHandler {
        alert.addAction(UIAlertAction(title: "재시도", style: .default) { _ in retryHandler() })
    }
    alert.addAction(UIAlertAction(title: "확인", style: .cancel))
    tabBarController.activeNavigator.rootViewController.present(alert, animated: true)
}
```

탭을 전환하면 HotwireTabBarController가 해당 탭의 페이지를 자동으로 다시 로드해주므로 그냥 무시해도 된다.

---

## 5. Debug/Release URL 분리

TestFlight 빌드에서 크래시가 났는데 로그는 `UINavigationController.init(rootViewController:)` 였다.
알고 보니 `baseURL`이 `localhost:3001`로 하드코딩되어 있어서 실기기에서 연결 실패 → 초기화 과정에서 crash가 났던 것.

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

`#if DEBUG` / `#else`로 Debug(시뮬레이터)와 Release(TestFlight/앱스토어)를 분리한다.
환경변수 주입도 가능하게 해두면 CI/CD에서 유연하게 쓸 수 있다.

---

## 6. 뒤로가기 버튼 중복 (웹 + 네이티브)

Rails 뷰에 뒤로가기 링크가 있고 네이티브 네비게이션 바에도 뒤로가기 화살표가 있으면 사용자 혼란이 생긴다.

### 해결 방법 — 3가지 조합

**① CSS로 웹 뒤로가기 숨기기**

```css
/* application.css */
.native-app .native-back { display: none !important; }
```

**② Rails 레이아웃에서 native-app 클래스 추가**

```erb
<%# application.html.erb %>
<% native_app = hotwire_native_app? %>
<body class="<%= 'native-app' if native_app %>">
```

`hotwire_native_app?`는 turbo-rails가 제공하는 헬퍼. User-Agent에 "Turbo Native"가 포함되어 있으면 true.

**③ 각 뷰의 뒤로가기 버튼에 클래스 추가**

```erb
<%= link_to "← 돌아가기", some_path, class: "native-back" %>
```

**④ path-configuration.json에서 탭 루트는 replace**

```json
{
  "patterns": ["^/dashboard$", "^/conversations$", "^/service_requests$"],
  "properties": {
    "context": "default",
    "presentation": "replace"
  }
}
```

탭 루트 URL은 `presentation: replace`로 설정해서 내비게이션 스택에 쌓이지 않게 한다. 그러면 탭 루트에서는 네이티브 뒤로가기 화살표 자체가 안 보인다.

**⑤ 뒤로가기 버튼 텍스트 제거**

```swift
// AppDelegate.swift
Hotwire.config.backButtonDisplayMode = .minimal
```

화살표만 표시하고 이전 페이지 제목 텍스트는 숨긴다.

---

## 7. Puma 스레드 설정 — 탭 동시 로드 대비

`HotwireTabBarController`는 탭 수만큼 요청을 동시에 보낸다. 기본 Puma 스레드(2개)가 부족하면 요청이 큐에 밀린다.

```ruby
# config/puma.rb
threads_count = ENV.fetch("RAILS_MAX_THREADS", 5)
threads threads_count, threads_count
```

탭이 3개면 최소 3개 이상, 여유를 두고 5개로 설정한다.

로컬 개발용 포트도 명시적으로 지정해두면 iOS 앱의 baseURL과 일치시키기 편하다:

```ruby
port ENV.fetch("PORT", 3001)
```

```
# Procfile.dev
web: bin/rails server -p 3001
```

---

## 8. 수출 규정 관련 문서 누락 (ITSAppUsesNonExemptEncryption)

TestFlight/앱스토어 빌드를 올리면 "수출 규정 관련 문서 누락" 경고가 계속 뜬다.
HTTPS만 사용하고 별도 암호화를 구현하지 않은 앱이라면 `Info.plist`에 아래를 추가하면 해결된다.

XcodeGen을 쓴다면 `project.yml`에:

```yaml
info:
  properties:
    ITSAppUsesNonExemptEncryption: false
```

직접 `Info.plist`에 추가한다면:
```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

매 빌드마다 App Store Connect에서 수동으로 답변해야 하는 번거로움을 없앨 수 있다.

---

## 9. make sim — 로컬 시뮬레이터 빌드 자동화

`make testflight`는 항상 Release 빌드라서 로컬 서버 없이도 프로덕션 서버로 붙는다.
시뮬레이터에서 Debug 빌드로 로컬 개발하려면 별도 타겟이 필요하다.

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

로컬 워크플로:
```bash
# 터미널 1
make dev       # Rails 서버 (localhost:3001)

# 터미널 2
make sim       # 시뮬레이터 Debug 빌드 + 실행
```

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| 앱 실행 시 "연결 오류" | 백그라운드 탭 WebView suspend → NSURLErrorCancelled | `-999` 에러 무시 처리 |
| TestFlight 크래시 | localhost가 Release 빌드에 하드코딩 | `#if DEBUG` / `#else` 분기 |
| 뒤로가기 버튼 중복 | 웹 뒤로가기 + 네이티브 내비게이션 바 | CSS `.native-back` 숨김 + path-config `replace` |
| 수출 규정 경고 | `ITSAppUsesNonExemptEncryption` 미선언 | `project.yml`에 `false` 추가 |
| 시뮬레이터 연결 실패 | Procfile 포트 미지정 (3000) + 앱은 3001 | `bin/rails server -p 3001` |
| 동시 요청 실패 | Puma 스레드 2개 < 탭 3개 동시 로드 | 스레드 5개로 증가 |
