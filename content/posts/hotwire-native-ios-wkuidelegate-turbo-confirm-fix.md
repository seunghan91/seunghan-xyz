---
title: "Hotwire Native iOS에서 삭제 버튼이 안 눌리는 이유 — WKUIDelegate와 turbo_confirm의 함정"
date: 2026-03-22
draft: false
tags: ["hotwire-native", "ios", "wkwebview", "turbo", "rails"]
description: "Hotwire Native iOS 앱에서 data-turbo-confirm이 붙은 버튼이 동작하지 않는 원인과 WKUIDelegate 구현으로 해결하는 방법. WKWebView의 JavaScript confirm() 보안 모델부터 실전 코드까지."
faq:
  - q: "WKUIDelegate를 구현했는데도 confirm 다이얼로그가 안 뜹니다. 원인이 뭔가요?"
    a: "가장 흔한 원인은 JSDialogHandler 인스턴스가 ARC에 의해 해제된 경우입니다. WKWebView의 uiDelegate는 weak 참조이므로, JSDialogHandler를 클로저 안에서 지역 변수로 생성하면 클로저 종료 후 즉시 해제됩니다. AppDelegate의 인스턴스 프로퍼티(private let jsDialogHandler = JSDialogHandler())로 선언해서 strong reference를 유지해야 합니다."
  - q: "completionHandler를 호출하지 않으면 어떻게 되나요?"
    a: "앱이 크래시합니다. WKWebView는 내부적으로 completionHandler가 반드시 호출될 것을 기대하며, 호출되지 않으면 'Completion handler passed to ... was not called' NSInternalInconsistencyException 예외가 발생합니다. topViewController를 찾지 못하는 예외 경로에서도 반드시 completionHandler(false)를 호출해야 합니다."
  - q: "Hotwire Native 없이 WKWebView만 쓰는 앱에서도 같은 방법으로 적용할 수 있나요?"
    a: "네, 완전히 동일하게 적용할 수 있습니다. WKWebView 인스턴스를 생성할 때 webView.uiDelegate = jsDialogHandler를 설정하면 됩니다. Hotwire Native의 makeCustomWebView 클로저는 Hotwire 전용 진입점일 뿐이며, 핵심 원리는 WKWebView + WKUIDelegate 프로토콜 구현 자체에 있습니다."
  - q: "iOS 앱에서 turbo_confirm 메시지를 한국어로 바꾸고 싶은데, UIAlertAction 버튼 텍스트를 커스터마이즈할 수 있나요?"
    a: "네, JSDialogHandler 내의 UIAlertAction 타이틀을 원하는 언어로 수정하면 됩니다. 파괴적인 동작(삭제 등)에는 style: .destructive를 사용하면 빨간색으로 표시되어 사용자에게 경고를 줄 수 있습니다. data-turbo-confirm에 넘기는 message 문자열 자체는 Rails 뷰에서 I18n.t()로 다국어 처리하면 됩니다."
---

## 삭제 버튼을 눌렀는데 아무 일도 일어나지 않는다

Rails + Hotwire로 웹앱을 만들고, Hotwire Native(구 Turbo Native)로 iOS 앱을 감싸서 배포하는 구조를 쓰고 있었다. 웹에서는 모든 것이 잘 동작했다. 삭제 버튼을 누르면 "정말 삭제하시겠습니까?" 확인 다이얼로그가 뜨고, 확인을 누르면 삭제가 진행됐다.

그런데 iOS 네이티브 앱에서 같은 버튼을 누르면 **아무 반응이 없었다**. 에러도 없고, 크래시도 없고, 그냥 조용히 무시됐다. 상태 변경 버튼, 라운드 추가/삭제 버튼, 토너먼트 삭제 버튼 — `turbo_confirm`이 붙은 모든 버튼이 죽어있었다.

Rails ERB 코드는 이렇게 생겼다:

```erb
<%= button_to tournament_path(@tournament),
    method: :delete,
    data: { turbo_confirm: "정말 삭제하시겠습니까?" } %>
```

모바일 Safari에서는 정상. 데스크톱 Chrome에서도 정상. 오직 Hotwire Native iOS 앱에서만 동작하지 않았다. 5개 프로젝트에서 총 68곳이 넘는 `turbo_confirm` 사용처가 전부 먹통이었는데, 아무도 몰랐다.

---

## 원인: WKWebView는 JavaScript confirm()을 무시한다

### Safari와 WKWebView는 다르다

이 문제를 이해하려면 Safari 브라우저와 WKWebView의 차이를 알아야 한다.

**Safari** (또는 Chrome, Firefox 같은 일반 브라우저)에서 JavaScript의 `confirm("삭제하시겠습니까?")`을 호출하면, 브라우저가 자동으로 확인/취소 다이얼로그를 표시한다. 개발자가 별도로 할 일이 없다.

**WKWebView** (iOS 앱 내 웹뷰)에서는 완전히 다르다. Apple은 보안상의 이유로 WKWebView에서 JavaScript의 `alert()`, `confirm()`, `prompt()` 다이얼로그를 **기본적으로 차단**한다. `confirm()`을 호출하면 다이얼로그가 표시되지 않고 **자동으로 `false`를 리턴**한다.

```
[Safari/Chrome]
  confirm("삭제?") → 브라우저가 다이얼로그 표시 → 사용자 선택 → true/false

[WKWebView - 기본 동작]
  confirm("삭제?") → 무시됨 → 자동으로 false 리턴 → 폼 제출 취소
```

### Turbo의 data-turbo-confirm 동작 원리

Turbo 프레임워크에서 `data-turbo-confirm`이 어떻게 동작하는지 보면:

1. 사용자가 버튼을 클릭한다
2. Turbo가 `data-turbo-confirm` 속성값을 읽는다
3. **JavaScript의 `confirm()` 함수를 호출**한다
4. `confirm()`이 `true`를 리턴하면 → 폼 제출 진행
5. `confirm()`이 `false`를 리턴하면 → 폼 제출 취소

WKWebView에서는 3번 단계에서 `confirm()`이 자동으로 `false`를 리턴하니까, Turbo는 "사용자가 취소를 눌렀구나"라고 판단하고 폼 제출을 취소한다. **에러도, 경고도, 크래시도 없다.** 그냥 조용히 아무 일도 일어나지 않는다.

이것이 디버깅을 어렵게 만드는 핵심이다. 에러가 있으면 찾을 수 있지만, "정상적으로 취소된 것"은 버그처럼 보이지 않는다.

---

## WKUIDelegate란 무엇인가

### iOS WebKit의 Delegate 패턴

WKWebView는 두 가지 주요 delegate 프로토콜을 제공한다:

| Delegate | 역할 | 주요 메서드 |
|----------|------|------------|
| `WKNavigationDelegate` | 페이지 로딩, URL 결정, 에러 처리 | `decidePolicyFor`, `didFinish` |
| `WKUIDelegate` | JavaScript UI 다이얼로그 처리 | `runJavaScriptAlertPanel`, `runJavaScriptConfirmPanel`, `runJavaScriptTextInputPanel` |

대부분의 Hotwire Native 튜토리얼과 공식 문서에서는 `WKNavigationDelegate`에 대해 자세히 설명하지만, **`WKUIDelegate`는 거의 언급하지 않는다**. Hotwire Native 프레임워크 자체도 WKUIDelegate를 기본으로 구현하지 않는다.

이것이 바로 함정이다. 개발자가 직접 `WKUIDelegate`를 구현해서 webView에 할당하지 않으면, JavaScript의 `alert()`, `confirm()`, `prompt()`는 영원히 동작하지 않는다.

### Apple이 이렇게 설계한 이유

Apple의 WKWebView 보안 모델을 이해하면 이 설계가 합리적이라는 것을 알 수 있다:

1. **악성 웹페이지 방어**: 앱 내 웹뷰에서 무한 `alert()` 루프로 앱을 먹통으로 만드는 공격을 방지
2. **UX 일관성**: 네이티브 앱에서 웹 스타일의 다이얼로그가 뜨면 사용자 경험이 깨진다. 개발자가 직접 네이티브 UIAlertController로 구현하도록 강제
3. **보안 제어**: 어떤 다이얼로그를 언제 표시할지 앱 개발자가 완전히 제어할 수 있어야 한다
4. **프로세스 격리**: WKWebView는 별도 프로세스에서 웹 콘텐츠를 렌더링하므로, UI 표시 결정은 앱 프로세스에서 해야 한다

---

## 해결 방법: JSDialogHandler 구현

### 핵심 구현 코드

별도의 `JSDialogHandler` 클래스를 만들어서 WKUIDelegate를 구현한다. 이 클래스는 JavaScript의 alert/confirm/prompt를 iOS 네이티브 `UIAlertController`로 변환한다.

```swift
import UIKit
import WebKit

final class JSDialogHandler: NSObject, WKUIDelegate {

    // JavaScript alert() → 네이티브 알림 다이얼로그
    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        guard let vc = topViewController() else {
            completionHandler()
            return
        }
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "확인", style: .default) { _ in
            completionHandler()
        })
        vc.present(alert, animated: true)
    }

    // JavaScript confirm() → 네이티브 확인/취소 다이얼로그
    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        guard let vc = topViewController() else {
            completionHandler(false)
            return
        }
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "확인", style: .destructive) { _ in
            completionHandler(true)
        })
        alert.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in
            completionHandler(false)
        })
        vc.present(alert, animated: true)
    }

    // JavaScript prompt() → 네이티브 텍스트 입력 다이얼로그
    func webView(
        _ webView: WKWebView,
        runJavaScriptTextInputPanelWithPrompt prompt: String,
        defaultText: String?,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (String?) -> Void
    ) {
        guard let vc = topViewController() else {
            completionHandler(nil)
            return
        }
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "확인", style: .default) { _ in
            completionHandler(alert.textFields?.first?.text)
        })
        alert.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in
            completionHandler(nil)
        })
        vc.present(alert, animated: true)
    }

    // 현재 화면의 최상위 ViewController 탐색
    private func topViewController() -> UIViewController? {
        guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController
        else { return nil }
        return findTop(from: root)
    }

    private func findTop(from vc: UIViewController) -> UIViewController {
        if let p = vc.presentedViewController { return findTop(from: p) }
        if let n = vc as? UINavigationController, let t = n.topViewController { return findTop(from: t) }
        if let t = vc as? UITabBarController, let s = t.selectedViewController { return findTop(from: s) }
        return vc
    }
}
```

### AppDelegate에서 webView에 연결

Hotwire Native 1.x에서는 `Hotwire.config.makeCustomWebView`를 통해 webView를 커스터마이즈할 수 있다. 여기서 `uiDelegate`를 설정한다.

```swift
import UIKit
import WebKit
import HotwireNative

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {

    // strong reference 필수!
    // WKWebView의 uiDelegate는 weak 참조이므로,
    // 지역 변수로 만들면 ARC에 의해 해제된다.
    private let jsDialogHandler = JSDialogHandler()

    private func configureHotwire() {
        // ... 기존 설정 ...

        let handler = jsDialogHandler
        Hotwire.config.makeCustomWebView = { config in
            let webView = WKWebView(frame: .zero, configuration: config)
            webView.uiDelegate = handler
            return webView
        }
    }
}
```

---

## 반드시 주의할 3가지 함정

### 함정 1: completionHandler를 반드시 호출해야 한다

WKUIDelegate의 세 메서드 모두 `completionHandler`를 파라미터로 받는다. 이 핸들러를 호출하지 않으면 **앱이 크래시**한다.

```
Terminating app due to uncaught exception 'NSInternalInconsistencyException',
reason: 'Completion handler passed to
-[YourApp.JSDialogHandler webView:runJavaScriptConfirmPanelWithMessage:
initiatedByFrame:completionHandler:] was not called'
```

topViewController를 찾지 못하는 경우에도 반드시 completionHandler를 호출해야 한다. 그래서 `guard let vc = topViewController() else { completionHandler(false); return }` 패턴을 사용한다.

### 함정 2: strong reference를 유지해야 한다

WKWebView의 `uiDelegate` 프로퍼티는 **weak 참조**다. 이것은 Apple의 delegate 패턴 표준이지만, 별도 클래스로 핸들러를 만들 때 치명적인 함정이 된다.

```swift
// 잘못된 코드 - handler가 즉시 해제된다
Hotwire.config.makeCustomWebView = { config in
    let handler = JSDialogHandler() // 이 줄에서 생성되고...
    let webView = WKWebView(frame: .zero, configuration: config)
    webView.uiDelegate = handler   // weak 참조로 할당
    return webView
    // 클로저 종료 → handler가 ARC에 의해 해제 → uiDelegate가 nil이 됨
}
```

```swift
// 올바른 코드 - AppDelegate에서 strong reference 유지
private let jsDialogHandler = JSDialogHandler() // AppDelegate 프로퍼티

private func configureHotwire() {
    let handler = jsDialogHandler  // 클로저에서 캡처할 로컬 변수
    Hotwire.config.makeCustomWebView = { config in
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.uiDelegate = handler  // AppDelegate가 살아있는 한 유효
        return webView
    }
}
```

### 함정 3: topViewController 탐색이 필수다

`UIAlertController`를 표시하려면 `present(_:animated:completion:)`을 호출해야 하는데, 이것은 `UIViewController` 인스턴스에서만 호출할 수 있다. JSDialogHandler는 `NSObject`이지 ViewController가 아니므로, 현재 화면에 표시중인 최상위 ViewController를 찾아야 한다.

탐색 체인은 다음과 같다:

```
UIWindowScene
  └─ keyWindow
       └─ rootViewController
            └─ presentedViewController? (모달이 떠있으면)
                 └─ UINavigationController? → topViewController
                      └─ UITabBarController? → selectedViewController
```

Hotwire Native 앱은 보통 `UITabBarController` > `UINavigationController` > `VisitableViewController` 구조를 사용하므로, 세 가지 케이스를 모두 처리해야 한다.

---

## Hotwire Native 버전별 적용 방법 비교

Hotwire Native의 버전에 따라 webView에 접근하는 방법이 다르다.

| 버전 | webView 접근 방법 | 권장 방식 |
|------|-------------------|-----------|
| turbo-ios 7.x (구버전) | `Session(webView:)` 생성자에 직접 전달 | Session 생성 시 webView.uiDelegate 설정 |
| hotwire-native-ios 1.0-1.2 | `Hotwire.config.makeCustomWebView` 클로저 | 클로저 내에서 webView.uiDelegate 설정 |
| 향후 버전 | 변경 가능 | 공식 문서 확인 |

turbo-ios 7.x (Turbo Native) 시절에는 Session을 직접 생성하면서 webView를 전달했기 때문에, SceneDelegate를 WKUIDelegate로 확장하는 방식이 일반적이었다:

```swift
// turbo-ios 7.x 방식
private lazy var session: Session = {
    let config = WKWebViewConfiguration()
    let webView = WKWebView(frame: .zero, configuration: config)
    webView.uiDelegate = self  // SceneDelegate가 직접 구현
    let session = Session(webView: webView)
    session.delegate = self
    return session
}()
```

hotwire-native-ios 1.x에서는 Session을 직접 생성하지 않고 Navigator가 관리하므로, `makeCustomWebView` 클로저를 사용하는 것이 올바른 방법이다.

---

## 실전 영향 범위: Rails에서 turbo_confirm이 쓰이는 곳들

Rails + Turbo 앱에서 `turbo_confirm`은 생각보다 많은 곳에 사용된다. 이 문제를 해결하지 않으면 다음 기능들이 전부 네이티브 앱에서 동작하지 않는다:

| Rails 코드 | 용도 | 영향 |
|------------|------|------|
| `button_to path, method: :delete, data: { turbo_confirm: "..." }` | 리소스 삭제 | 삭제 불가 |
| `link_to path, data: { turbo_method: :delete, turbo_confirm: "..." }` | 링크형 삭제 | 삭제 불가 |
| `button_to path, method: :patch, data: { turbo_confirm: "..." }` | 상태 변경 | 상태 변경 불가 |
| `form: { data: { turbo_confirm: "..." } }` | 폼 제출 전 확인 | 폼 제출 불가 |
| `data: { turbo_confirm: "..." }` on Turbo Frame | 프레임 내 확인 | 프레임 동작 불가 |

실제로 내가 운영하는 5개 프로젝트에서 확인한 turbo_confirm 사용 현황:

| 프로젝트 | turbo_confirm 사용처 | 주요 기능 |
|---------|---------------------|-----------|
| 프로젝트 A | 41곳 | 라운드 관리, 상태변경, 대회 삭제 |
| 프로젝트 B | 18곳 | 관리자 삭제, 채팅 삭제, 과제 상태변경 |
| 프로젝트 C | 5곳 | 설정 삭제, 감시목록 삭제 |
| 프로젝트 D | 4곳 | 커뮤니티 글 삭제 |
| 프로젝트 E | 3곳 | 결제 취소, 비밀번호 초기화 |

총 71곳에서 확인 다이얼로그가 동작하지 않고 있었다. 에러가 나지 않아서 아무도 인지하지 못했다.

---

## XcodeGen(project.yml) 프로젝트에서의 파일 포함

XcodeGen을 사용하는 프로젝트에서는 새로 만든 Swift 파일이 자동으로 빌드 대상에 포함되는지 확인해야 한다.

```yaml
# project.yml
targets:
  YourApp:
    type: application
    platform: iOS
    sources:
      - path: YourApp        # 이 폴더 하위의 모든 .swift 파일 자동 포함
        excludes:
          - "**/.DS_Store"
```

`sources`에 상위 폴더(`YourApp`)를 지정하면 하위의 모든 Swift 파일이 자동으로 포함된다. `Bridge/JSDialogHandler.swift`든 `Controllers/JSDialogHandler.swift`든 경로에 상관없이 빌드에 포함된다.

단, `.xcodeproj`를 직접 관리하는 경우에는 Xcode에서 파일을 프로젝트 트리에 수동으로 추가해야 한다. 파일시스템에 파일이 있어도 `.pbxproj`에 등록되지 않으면 컴파일되지 않는다.

---

## turbo_confirm 대신 Stimulus로 confirm을 구현하는 방법

WKUIDelegate를 구현하면 `turbo_confirm`이 동작하지만, 일부 개발자는 JavaScript `confirm()` 의존을 아예 피하고 싶어한다. 이런 경우 Stimulus 컨트롤러에서 직접 `confirm()`을 호출하고 fetch API로 서버 요청을 보내는 패턴을 사용할 수 있다.

```javascript
// round_count_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { addUrl: String, removeUrl: String }

  increment() {
    if (!confirm("빈 라운드를 추가하시겠습니까?")) return

    fetch(this.addUrlValue, {
      method: "POST",
      headers: {
        "X-CSRF-Token": document.querySelector("[name='csrf-token']").content,
        "Accept": "text/vnd.turbo-stream.html"
      }
    }).then(response => response.text())
      .then(html => Turbo.renderStreamMessage(html))
  }
}
```

이 방식은 `button_to`의 `<form>` 태그 대신 일반 `<button>`을 사용하므로, HTML이 깔끔해지고 `turbo_confirm`의 `<form>` 내 hidden input 문제도 피할 수 있다. 물론 WKUIDelegate가 구현되어 있어야 `confirm()` 다이얼로그가 표시된다는 점은 동일하다.

---

## 결론

Hotwire Native iOS 앱을 만들 때 `WKUIDelegate`는 **선택이 아니라 필수**다. 이것이 없으면 `turbo_confirm`이 붙은 모든 버튼이 조용히 동작을 거부한다. 에러도 없고 크래시도 없어서 디버깅이 극도로 어렵다.

체크리스트:

- `JSDialogHandler.swift` 파일 생성 (alert, confirm, prompt 3종)
- `AppDelegate`에서 `private let jsDialogHandler = JSDialogHandler()` (strong reference)
- `makeCustomWebView` 클로저에서 `webView.uiDelegate = handler` 설정
- `completionHandler`를 모든 경로에서 반드시 호출

Hotwire Native 공식 문서에도, 37signals의 공식 가이드에도 이 내용이 빠져있다. Joe Masilotti의 블로그(masilotti.com)가 이 문제를 다룬 거의 유일한 영어 자료다. 이 글이 같은 문제로 삽질하는 개발자에게 도움이 되길 바란다.

---

## 자주 묻는 질문 (FAQ)

### Q: WKUIDelegate를 구현했는데도 confirm 다이얼로그가 안 뜹니다. 원인이 뭔가요?

가장 흔한 원인은 JSDialogHandler 인스턴스가 ARC에 의해 해제된 경우다. WKWebView의 `uiDelegate`는 **weak 참조**이므로, `JSDialogHandler`를 `makeCustomWebView` 클로저 안에서 지역 변수로 생성하면 클로저가 끝난 직후 인스턴스가 해제된다. 반드시 `AppDelegate`의 인스턴스 프로퍼티(`private let jsDialogHandler = JSDialogHandler()`)로 선언해서 strong reference를 앱 생명주기 내내 유지해야 한다.

### Q: completionHandler를 호출하지 않으면 어떻게 되나요?

앱이 크래시한다. WKWebView는 내부적으로 `completionHandler`가 반드시 호출될 것을 기대하며, 호출되지 않으면 `NSInternalInconsistencyException`이 발생한다. 메시지는 `'Completion handler passed to -[YourApp.JSDialogHandler webView:runJavaScriptConfirmPanelWithMessage:...] was not called'`와 같이 나타난다. `topViewController()`를 찾지 못하는 guard 분기에서도 반드시 `completionHandler(false)`를 호출해야 한다.

### Q: Hotwire Native 없이 WKWebView만 쓰는 앱에서도 같은 방법으로 적용할 수 있나요?

네, 완전히 동일하게 적용된다. `WKWebView` 인스턴스를 직접 생성할 때 `webView.uiDelegate = jsDialogHandler`를 설정하면 된다. `makeCustomWebView` 클로저는 Hotwire Native 전용 진입점일 뿐이며, 핵심은 `WKWebView`와 `WKUIDelegate` 구현 자체에 있다. 순수 `WKWebView` 기반 앱이라면 `ViewController`에 weak 참조 없이 핸들러를 프로퍼티로 유지하면 된다.

### Q: iOS 앱에서 확인/취소 버튼 텍스트를 한국어가 아닌 다른 언어로 바꿀 수 있나요?

`JSDialogHandler` 내 `UIAlertAction`의 타이틀 문자열을 직접 수정하면 된다. Rails 뷰에서 `data-turbo-confirm` 속성에 넘기는 메시지 자체는 `I18n.t(:confirm_delete)` 같은 방식으로 다국어 처리하면 되고, iOS 쪽의 "확인"/"취소" 버튼 텍스트는 `Localizable.strings` 또는 `String(localized:)` API를 통해 iOS 현지화 파일에서 관리하는 것이 좋다. 파괴적인 동작(삭제)에는 `style: .destructive`를 사용하면 버튼이 빨간색으로 표시되어 사용자에게 시각적 경고를 준다.
