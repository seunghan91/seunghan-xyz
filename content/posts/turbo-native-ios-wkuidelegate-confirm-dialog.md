---
title: "Turbo Native iOS에서 data-turbo-confirm이 동작하지 않는 이유 — WKUIDelegate 누락 문제"
date: 2026-03-22
draft: false
tags: ["rails", "turbo-native", "ios", "hotwire", "wkwebview"]
categories: ["Hotwire Native", "iOS"]
description: "Rails의 data-turbo-confirm이 iOS 네이티브 앱에서 아무 반응이 없는 문제. WKWebView가 JavaScript confirm()을 기본 차단하는 보안 모델과 WKUIDelegate 해결법을 정리한다."
faq:
  - q: "WKUIDelegate를 구현했는데도 iOS 앱에서 confirm 창이 뜨지 않습니다. 확인해야 할 것은?"
    a: "가장 먼저 JSDialogHandler 인스턴스가 ARC에 의해 해제되지 않았는지 확인하세요. WKWebView의 uiDelegate는 weak 참조이므로, 지역 변수로 생성한 핸들러는 클로저 종료 후 즉시 해제됩니다. AppDelegate의 인스턴스 프로퍼티로 선언해서 앱 전체 생명주기 동안 strong reference를 유지해야 합니다."
  - q: "button_to와 link_to에서 turbo_confirm을 쓸 때 넣는 위치가 다른 이유는 무엇인가요?"
    a: "button_to는 내부적으로 form 태그를 생성하며, Turbo는 form 태그의 data-turbo-confirm 속성을 읽습니다. 따라서 button_to에서는 form: { data: { turbo_confirm: '...' } } 형태로 form에 넣어야 합니다. 반면 link_to에서는 a 태그 자체에 data: { turbo_confirm: '...' }로 넣어야 합니다. 웹 브라우저에서는 두 방식 모두 동작하는 경우가 있어 혼동하기 쉽습니다."
  - q: "Safari Web Inspector로 WKWebView 내 JavaScript를 디버깅하는 방법은?"
    a: "먼저 Swift 코드에서 webView.isInspectable = true를 설정합니다. 그 다음 Mac의 Safari 설정 > 고급 > '웹 개발자용 기능 표시'를 활성화합니다. iOS Simulator에서 앱을 실행한 뒤 Safari의 개발자 메뉴 > Simulator > 해당 WebView를 선택하면 됩니다. 콘솔에서 confirm('test')를 직접 입력해 아무 반응이 없으면 WKUIDelegate가 구현되지 않은 것입니다."
  - q: "turbo_confirm 대신 커스텀 모달로 확인 다이얼로그를 구현하고 싶을 때 어떻게 하나요?"
    a: "Turbo는 Turbo.config.confirmMethod를 재정의해서 기본 confirm() 대신 커스텀 함수를 사용하도록 설정할 수 있습니다. 예를 들어 Turbo.config.confirmMethod = (message, element) => new Promise((resolve) => { /* 커스텀 모달 표시 후 resolve(true/false) */ }) 형태로 구현하면 됩니다. 이 경우 WKUIDelegate의 confirm 메서드는 호출되지 않으므로 네이티브 앱에서도 별도 처리가 필요합니다."
---

## 버튼을 눌러도 아무 일도 일어나지 않는다

Rails 8 + Hotwire Native으로 iOS 앱을 만들고 있었다. 웹에서는 잘 동작하는 삭제 버튼이 네이티브 앱에서는 완전히 먹통이었다.

```erb
<%= button_to "삭제", tournament_path(@tournament),
    method: :delete,
    form: { data: { turbo_confirm: "정말 삭제하시겠습니까?" } } %>
```

웹 브라우저에서 클릭하면 "정말 삭제하시겠습니까?" 확인 다이얼로그가 뜨고, 확인하면 삭제가 진행된다. 그런데 iOS 앱에서는 버튼을 탭해도 **아무 반응이 없다**. 에러도 없고, 로그도 없고, 그냥 조용히 무시된다.

처음에는 `turbo_confirm`을 `form:` 옵션에 넣느냐 `data:` 옵션에 넣느냐의 문제인 줄 알았다. `button_to`의 `turbo_confirm`은 form 태그의 `data` 속성으로 전달해야 하기 때문이다. 하지만 코드는 정확했다. 웹에서 되는데 네이티브에서만 안 되니까 iOS 쪽 문제가 확실했다.

---

## WKWebView의 JavaScript 보안 모델

원인은 WKWebView의 보안 모델에 있었다. iOS의 WKWebView는 Safari와 달리 JavaScript의 `alert()`, `confirm()`, `prompt()` 다이얼로그를 **기본적으로 차단**한다.

| 환경 | `confirm("삭제?")` 호출 시 | 결과 |
|------|--------------------------|------|
| Safari / Chrome | 브라우저가 자동으로 다이얼로그 표시 | 사용자 선택에 따라 true/false |
| WKWebView (기본) | **아무 일도 안 일어남** | 자동으로 `false` 리턴 |
| WKWebView + WKUIDelegate | 개발자가 구현한 네이티브 다이얼로그 표시 | 정상 동작 |

이것은 버그가 아니라 **의도된 설계**다. WKWebView는 앱 내에 삽입되는 웹뷰이므로, 웹 페이지가 임의로 팝업을 띄우는 것을 막기 위해 기본적으로 모든 JavaScript UI 다이얼로그를 무시한다. 개발자가 명시적으로 "이 다이얼로그를 이렇게 처리하겠다"고 `WKUIDelegate`를 구현해야만 동작한다.

Apple 공식 문서에서도 이 프로토콜을 구현하지 않으면 JavaScript의 `window.alert()`, `window.confirm()`, `window.prompt()`가 모두 무시된다고 명시하고 있다.

---

## Turbo의 data-turbo-confirm이 내부적으로 하는 일

Turbo(Hotwire)의 `data-turbo-confirm`이 어떻게 동작하는지 이해하면 왜 문제가 되는지 명확해진다.

```html
<!-- Rails가 생성하는 HTML -->
<form data-turbo-confirm="정말 삭제하시겠습니까?" method="post" action="/tournaments/1">
  <input type="hidden" name="_method" value="delete">
  <button type="submit">삭제</button>
</form>
```

Turbo는 이 폼이 제출될 때 `data-turbo-confirm` 속성을 감지하고, **폼 제출 전에 JavaScript `confirm()` 함수를 호출**한다. `confirm()`이 `true`를 리턴하면 폼을 제출하고, `false`이면 제출을 취소한다.

```javascript
// Turbo 내부 로직 (simplified)
if (element.dataset.turboConfirm) {
  const message = element.dataset.turboConfirm
  if (!confirm(message)) {  // ← 여기서 JS confirm() 호출
    event.preventDefault()   // false이면 폼 제출 취소
    return
  }
}
```

WKWebView에서 `confirm()`은 WKUIDelegate가 없으면 자동으로 `false`를 리턴한다. 따라서 Turbo는 "사용자가 취소했다"고 판단하고 폼 제출을 막는다. **그래서 버튼을 눌러도 아무 일도 일어나지 않는 것이다.**

이 문제가 특히 질이 나쁜 이유는 **에러가 전혀 발생하지 않기** 때문이다. 크래시도 없고, 콘솔 로그도 없고, 네트워크 요청도 발생하지 않는다. 그냥 "안 됨"이다. 디버깅 시 원인을 찾기가 매우 어렵다.

---

## 영향 범위: 생각보다 광범위하다

`data-turbo-confirm`은 Rails 앱에서 매우 흔하게 사용된다. 내 프로젝트들에서 검색해보니:

| 프로젝트 | `turbo_confirm` 사용 횟수 | 영향받는 기능 |
|---------|-------------------------|-------------|
| 프로젝트 A | 41곳 | 삭제, 상태변경, 초기화, 라운드 추가/삭제 |
| 프로젝트 B | 5곳 | 설정 삭제, 감시목록 제거 |
| 프로젝트 C | 4곳 | 커뮤니티 글 삭제, 투표 |
| 프로젝트 D | 미확인 | 동일 구조 |

4개 프로젝트 모두 동일한 구조(Rails 8 + HotwireNative iOS)로 되어 있었고, **전부 같은 문제를 갖고 있었다**. 단지 발견이 늦었을 뿐이다.

---

## 해결: JSDialogHandler 구현

해결 방법은 `WKUIDelegate` 프로토콜을 구현하는 클래스를 만들고, WKWebView에 할당하는 것이다.

### 1. JSDialogHandler.swift 생성

```swift
import UIKit
import WebKit

final class JSDialogHandler: NSObject, WKUIDelegate {

    // JS alert() → 네이티브 "확인" 버튼 1개짜리 다이얼로그
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

    // JS confirm() → 네이티브 "확인"/"취소" 다이얼로그
    // data-turbo-confirm이 이것을 사용한다
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

    // JS prompt() → 네이티브 텍스트 입력 다이얼로그
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

    // 현재 화면 최상단의 ViewController를 찾는다
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

### 2. AppDelegate에서 연결

```swift
// AppDelegate.swift

// strong reference 필수! uiDelegate는 weak 참조이므로
private let jsDialogHandler = JSDialogHandler()

private func configureHotwire() {
    // ... 기존 설정 ...

    let handler = jsDialogHandler
    Hotwire.config.makeCustomWebView = { config in
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.uiDelegate = handler  // 이 한 줄이 핵심
        return webView
    }
}
```

HotwireNative는 `Hotwire.config.makeCustomWebView` 클로저를 통해 WebView를 커스터마이즈할 수 있다. 이 클로저에서 생성된 WebView에 `uiDelegate`를 할당하면, 앱 전체에서 생성되는 모든 WebView에 자동으로 적용된다.

---

## 반드시 지켜야 할 3가지 주의사항

### 1. strong reference 유지

```swift
// ❌ 이렇게 하면 안 된다 — 클로저 실행 후 handler가 ARC에 의해 해제됨
Hotwire.config.makeCustomWebView = { config in
    let handler = JSDialogHandler()  // 지역 변수 → 클로저 종료 후 해제
    let webView = WKWebView(frame: .zero, configuration: config)
    webView.uiDelegate = handler     // weak 참조 → 바로 nil이 됨
    return webView
}

// ✅ 올바른 방법 — AppDelegate의 프로퍼티로 유지
private let jsDialogHandler = JSDialogHandler()  // strong reference
```

WKWebView의 `uiDelegate`는 **weak 참조**이다. 따라서 `JSDialogHandler` 인스턴스를 지역 변수로 만들면 클로저가 끝난 후 ARC에 의해 해제되고, `uiDelegate`가 `nil`이 되어 다시 동작하지 않는다.

반드시 `AppDelegate`의 인스턴스 프로퍼티로 선언하여 앱 생명주기 동안 유지해야 한다.

### 2. completionHandler 필수 호출

```swift
// ❌ completionHandler를 호출하지 않으면 앱이 크래시한다
func webView(_ webView: WKWebView,
             runJavaScriptConfirmPanelWithMessage message: String,
             initiatedByFrame frame: WKFrameInfo,
             completionHandler: @escaping (Bool) -> Void) {
    // completionHandler를 호출하지 않고 리턴하면 크래시!
}

// ✅ 모든 경로에서 반드시 호출
func webView(_ webView: WKWebView, ...) {
    guard let vc = topViewController() else {
        completionHandler(false)  // vc를 못 찾아도 반드시 호출
        return
    }
    // ... alert 표시 ...
}
```

WKWebView는 내부적으로 `completionHandler`가 반드시 호출될 것을 기대한다. 어떤 경로에서든 호출하지 않으면 `"Completion handler was not called"` assertion 에러와 함께 앱이 크래시한다.

### 3. topViewController 탐색

`UIAlertController`를 `present`하려면 현재 화면에 보이는 ViewController가 필요하다. HotwireNative 앱은 보통 `UITabBarController` > `UINavigationController` > `VisitableViewController` 구조를 가지므로, 재귀적으로 최상위 VC를 탐색해야 한다.

---

## 이 문제를 빠르게 진단하는 방법

만약 iOS Turbo Native 앱에서 어떤 버튼이 동작하지 않는다면:

1. **웹 브라우저에서 같은 버튼을 테스트한다.** 웹에서 되는데 앱에서 안 되면 WKWebView 문제다.
2. **해당 버튼에 `data-turbo-confirm`이 있는지 확인한다.** Rails 뷰에서 `turbo_confirm`을 grep한다.
3. **Safari Web Inspector로 WebView를 디버깅한다.** JavaScript 콘솔에서 `confirm("test")`를 직접 호출해본다. 아무 반응이 없으면 WKUIDelegate 미구현이다.

```swift
// 디버깅용: Safari Web Inspector 활성화
webView.isInspectable = true
```

---

## HotwireNative 공식 지원은 없나?

HotwireNative 1.2.2 (2025년 7월 기준 최신)까지도 WKUIDelegate는 **내장 지원하지 않는다**. 이것은 의도적인 설계 결정으로 보인다. HotwireNative는 웹뷰의 네비게이션과 라우팅에 집중하고, JavaScript 다이얼로그 같은 UI 커스터마이징은 개발자에게 맡긴다.

Joe Masilotti(Turbo Native 커뮤니티의 핵심 기여자)도 [블로그](https://masilotti.com/javascript-alerts-in-turbo-native/)에서 이 문제를 다루며, WKUIDelegate 구현이 필수라고 설명하고 있다.

이 문제는 turbolinks-ios 시절(2017년)부터 존재했던 [오래된 이슈](https://github.com/turbolinks/turbolinks-ios/issues/88)이다. WKWebView의 근본적인 보안 모델에서 비롯된 것이므로, Apple이 WKWebView의 기본 동작을 바꾸지 않는 한 계속 존재할 것이다.

---

## button_to의 turbo_confirm은 form에 넣어야 한다

이 문제를 디버깅하면서 추가로 발견한 사실이 있다. `button_to`에서 `turbo_confirm`의 올바른 위치다.

```erb
<%# ❌ button의 data에 넣으면 동작 안 함 %>
<%= button_to "삭제", path, method: :delete,
    data: { turbo_confirm: "삭제하시겠습니까?" } %>

<%# ✅ form의 data에 넣어야 함 %>
<%= button_to "삭제", path, method: :delete,
    form: { data: { turbo_confirm: "삭제하시겠습니까?" } } %>
```

`button_to`는 내부적으로 `<form>` 태그를 생성한다. Turbo는 **폼 태그**에서 `data-turbo-confirm` 속성을 읽으므로, button이 아닌 form에 넣어야 한다. 이것은 [turbo-rails #302 이슈](https://github.com/hotwired/turbo-rails/issues/302)에서도 확인된 동작이다.

웹 브라우저에서는 두 방식 모두 동작하는 경우가 있어서 혼동하기 쉬운데, 공식적으로는 form에 넣는 것이 올바른 방법이다.

---

## 실전 활용: button_to 대신 Stimulus + JS confirm

또 하나 발견한 패턴이 있다. Rails의 `button_to`가 생성하는 `<form>` 태그는 CSRF hidden input, method hidden input 등을 포함하여 레이아웃이 복잡해질 수 있다. 특히 `-/+` 같은 작은 인라인 버튼에서는 form 태그가 레이아웃을 깨뜨리는 경우가 있다.

이런 경우에는 Stimulus 컨트롤러 + JavaScript `confirm()`을 직접 사용하는 것이 더 깔끔하다.

```javascript
// round_count_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { addUrl: String, removeUrl: String, count: Number }

  increment() {
    if (!confirm("빈 라운드를 추가하시겠습니까?")) return
    this.submitAction(this.addUrlValue, "POST")
  }

  decrement() {
    if (this.countValue <= 0) return
    if (!confirm("마지막 라운드를 삭제하시겠습니까?")) return
    this.submitAction(this.removeUrlValue, "DELETE")
  }

  async submitAction(url, method) {
    const response = await fetch(url, {
      method: method,
      headers: {
        "Accept": "text/vnd.turbo-stream.html, text/html",
        "X-CSRF-Token": document.querySelector("meta[name='csrf-token']")?.content
      },
      credentials: "same-origin"
    })
    // Turbo Stream 응답이면 자동 처리, 아니면 페이지 리로드
    if (response.headers.get("content-type")?.includes("turbo-stream")) {
      Turbo.renderStreamMessage(await response.text())
    } else {
      window.location.reload()
    }
  }
}
```

```erb
<%# form 태그 없이 깔끔한 인라인 버튼 %>
<div data-controller="round-count"
     data-round-count-add-url-value="<%= add_path %>"
     data-round-count-remove-url-value="<%= remove_path %>"
     data-round-count-count-value="<%= count %>">
  <button data-action="round-count#decrement">−</button>
  <span><%= count %></span>
  <button data-action="round-count#increment">+</button>
</div>
```

이 방식은 `button_to`의 form 태그 없이도 서버에 요청을 보내고, `confirm()` 다이얼로그도 정상적으로 표시된다. 물론 `JSDialogHandler`가 구현되어 있어야 네이티브 앱에서도 동작한다.

---

## 체크리스트: 새 프로젝트 시작 시

Rails + HotwireNative iOS 프로젝트를 시작할 때 반드시 확인해야 할 항목이다.

| # | 항목 | 확인 |
|---|------|------|
| 1 | `Bridge/JSDialogHandler.swift` 파일이 프로젝트에 추가되었는가? | |
| 2 | `AppDelegate`에서 `jsDialogHandler`를 인스턴스 프로퍼티로 유지하는가? | |
| 3 | `makeCustomWebView` 블록에서 `webView.uiDelegate = handler`를 설정하는가? | |
| 4 | 3개 delegate 메서드 모두에서 `completionHandler`를 반드시 호출하는가? | |
| 5 | 네이티브 앱에서 `data-turbo-confirm` 버튼 클릭 시 다이얼로그가 표시되는가? | |

---

## 결론

WKWebView가 JavaScript `confirm()`을 기본 차단하는 것은 iOS 개발에서 유명한 함정이지만, Rails + Turbo Native 맥락에서는 잘 언급되지 않는다. `data-turbo-confirm`이 내부적으로 `confirm()`을 호출한다는 것을 모르면, "왜 버튼이 안 되지?"라는 질문에서 시작해 몇 시간을 헤매게 된다.

해결 자체는 간단하다. `JSDialogHandler.swift` 파일 하나와 AppDelegate에서 `webView.uiDelegate = handler` 한 줄이면 된다. 하지만 이 문제를 **발견하는 것**이 어렵다. 에러도 없고 로그도 없으니까.

이 글을 읽는 사람이 같은 삽질을 하지 않기를 바란다. HotwireNative iOS 프로젝트를 시작한다면, 첫 번째로 할 일은 `JSDialogHandler`를 추가하는 것이다.

---

## 자주 묻는 질문 (FAQ)

### Q: WKUIDelegate를 구현했는데도 iOS 앱에서 confirm 창이 뜨지 않습니다. 확인해야 할 것은?

가장 먼저 `JSDialogHandler` 인스턴스가 ARC에 의해 해제되지 않았는지 확인해야 한다. `WKWebView`의 `uiDelegate`는 **weak 참조**이므로, `makeCustomWebView` 클로저 내부에서 `let handler = JSDialogHandler()`로 생성하면 클로저가 종료되는 순간 `uiDelegate`가 `nil`이 된다. `AppDelegate`에서 `private let jsDialogHandler = JSDialogHandler()`로 선언해 strong reference를 유지해야 한다. Safari Web Inspector 콘솔에서 `confirm("test")`를 직접 입력해 반응이 없으면 핸들러가 해제된 것이다.

### Q: `button_to`와 `link_to`에서 `turbo_confirm`을 넣는 위치가 다른 이유는 무엇인가요?

`button_to`는 내부적으로 `<form>` 태그를 생성하고, Turbo는 **폼 태그**에서 `data-turbo-confirm` 속성을 읽는다. 따라서 `button_to`에서는 반드시 `form: { data: { turbo_confirm: "..." } }` 형태로 form에 넣어야 한다. 반면 `link_to`는 `<a>` 태그에 직접 속성이 붙으므로 `data: { turbo_confirm: "..." }`를 쓴다. 웹 브라우저에서는 두 방식 모두 동작하는 경우가 있어 혼동하기 쉽지만, 공식 동작은 form 태그 기준이다.

### Q: Safari Web Inspector로 WKWebView 내 JavaScript를 디버깅하는 방법은?

Swift 코드에서 `webView.isInspectable = true`를 설정한 다음, Mac의 Safari 설정 > 고급 > "웹 개발자용 기능 표시"를 활성화한다. iOS Simulator에서 앱을 실행한 뒤 Safari 메뉴바에서 개발자 > Simulator > 해당 WebView를 선택하면 Elements, Console, Network 탭을 모두 사용할 수 있다. 콘솔에서 `confirm("test")`를 직접 입력해 다이얼로그가 표시되지 않으면 WKUIDelegate가 연결되지 않은 것이다.

### Q: `turbo_confirm` 대신 커스텀 모달로 확인 다이얼로그를 대체하고 싶을 때는 어떻게 하나요?

Turbo는 `Turbo.config.confirmMethod`를 재정의해서 기본 `window.confirm()` 대신 커스텀 함수를 사용할 수 있다. JavaScript에서 `Turbo.config.confirmMethod = (message, element, submitter) => new Promise(resolve => { /* 커스텀 모달 표시 후 resolve(true) 또는 resolve(false) */ })`처럼 Promise를 반환하는 형태로 구현한다. 이 방식을 선택하면 `window.confirm()`이 호출되지 않으므로 WKUIDelegate의 confirm 메서드는 사용되지 않는다. 다만 네이티브 앱 전용 커스텀 모달을 구현하려면 별도의 Turbo Bridge 이벤트 연동이 필요하다.

---

## 관련 이슈 및 추가 팁

### Turbo Native Bridge를 활용한 커스텀 확인 UI

WKUIDelegate가 표시하는 기본 `UIAlertController`는 iOS 네이티브 앱치고는 다소 밋밋하게 느껴질 수 있다. [Turbo Native Bridge](https://github.com/hotwired/hotwire-native-bridge)를 사용하면 웹 페이지에서 네이티브 커스텀 UI를 트리거하는 더 정교한 방법을 구현할 수 있다. 예를 들어, JavaScript에서 `BridgeElement`를 통해 iOS에 "이 삭제 작업은 커스텀 확인 화면을 보여줘"라고 요청하고, Swift 쪽에서 완전히 커스텀한 확인 화면을 표시한 뒤 결과를 다시 웹으로 돌려보내는 양방향 통신이 가능하다. 간단한 confirm 다이얼로그라면 WKUIDelegate가 충분하지만, 복잡한 확인 플로우가 필요하다면 Bridge가 더 적합하다.

### Android Turbo Native에서의 동일한 문제

iOS뿐 아니라 Android에서도 `Turbo Native` (또는 Hotwire Native Android)를 사용할 때 비슷한 문제가 발생한다. Android의 `WebView`도 기본적으로 JavaScript 다이얼로그를 차단하며, `WebChromeClient`를 구현하고 `onJsConfirm()` 메서드를 오버라이드해야 한다. Rails 앱이 iOS와 Android 모두를 네이티브 앱으로 감싸고 있다면 두 플랫폼 모두 동일한 처리가 필요하다는 점을 기억하자.
