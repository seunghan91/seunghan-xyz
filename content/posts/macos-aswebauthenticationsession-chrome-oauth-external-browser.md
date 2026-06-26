---
title: "macOS 앱 Google 로그인이 Chrome에서 먹통 — ASWebAuthenticationSession 버그와 external browser 우회"
date: 2026-06-26T11:04:54+09:00
draft: false
tags: ["macOS", "ASWebAuthenticationSession", "OAuth", "SwiftUI", "Google SignIn"]
description: "iOS에서 멀쩡하던 Google SSO가 macOS에서만 안 됐다. 기본 브라우저가 Chrome일 때 ASWebAuthenticationSession이 OAuth 페이지를 안 띄우는 Apple 버그를 만나 external browser + custom scheme로 우회한 기록."
---

iOS/macOS 코드를 같은 Swift 패키지로 공유하는 앱을 만들고 있다. 로그인은 Apple/Google SSO를 쓴다. iOS에서는 Google 로그인이 잘 됐다. 그런데 macOS 빌드에서만 Google 로그인이 끝까지 완료가 안 됐다. 버튼을 눌러도 아무 반응이 없거나, 인증창이 떠도 "계속"을 누르면 OAuth 동의 페이지가 안 뜨고 브라우저 창만 덜렁 열렸다.

같은 코드인데 왜 한쪽 플랫폼에서만 깨지는가. 이게 며칠간 이어진 삽질의 시작이었다. 결론부터 말하면 범인은 `ASWebAuthenticationSession`이었고, macOS에서는 이 API를 쓰지 않고 외부 브라우저를 직접 여는 방식으로 바꿔서 해결했다. 이 글은 그 과정과, macOS 데스크톱 OAuth를 어떻게 구현해야 하는지에 대한 정리다.

<!--more-->

---

## ASWebAuthenticationSession이 뭔가

`ASWebAuthenticationSession`은 Apple이 제공하는 OAuth/OIDC용 인증 세션 API다. iOS 12 / macOS 10.15부터 들어왔다. 동작은 이렇다.

1. 앱이 authorization URL을 넘기면서 세션을 시작한다.
2. 시스템이 사용자에게 로그인 페이지를 보여준다.
3. 인증이 끝나면 custom scheme(또는 https) redirect로 결과를 앱에 돌려준다. 앱은 completion handler에서 그 callback URL을 받는다.

iOS에서는 이게 정말 깔끔하다. 화면 위에 **인앱 SafariViewController**(시스템이 관리하는 Safari 인스턴스)가 떠서 그 안에서 로그인이 끝나고, redirect가 오면 세션이 닫히면서 callback URL이 completion으로 넘어온다. 쿠키도 격리돼 있어서 보안 모델이 깔끔하고, 별도 브라우저로 튕겨 나가지도 않는다.

문제는 **macOS에서의 동작이 iOS와 근본적으로 다르다**는 점이다. macOS의 `ASWebAuthenticationSession`은 인앱 브라우저를 띄우는 게 아니라, **사용자의 "기본 브라우저"를 실행해서** 거기서 로그인을 시킨다. 여기서 모든 게 꼬이기 시작했다.

---

## 삽질 1 — 버튼을 눌러도 아무 반응이 없다

처음 증상은 무반응이었다. macOS에서 Google 버튼을 누르면 잠깐 로딩 상태가 됐다가, 아무 일도 안 일어나고 버튼이 영영 비활성 상태로 멈췄다. 에러도 없었다.

원인은 `session.start()`의 반환값을 무시한 코드였다. 대략 이런 모양이었다.

```swift
// 문제 코드 — start()의 Bool 반환값을 버린다
func presentSession(url: URL) async throws -> URL {
    try await withCheckedThrowingContinuation { continuation in
        let session = ASWebAuthenticationSession(
            url: url,
            callbackURLScheme: callbackScheme
        ) { callbackURL, error in
            // start()가 실패하면 이 completion이 아예 호출되지 않는다
            if let callbackURL { continuation.resume(returning: callbackURL) }
            else { continuation.resume(throwing: error ?? SomeError.unknown) }
        }
        session.presentationContextProvider = anchorProvider
        session.start()   // ← 반환값(Bool)을 안 본다
    }
}
```

`ASWebAuthenticationSession.start()`는 `Bool`을 돌려준다. 세션을 시작하지 못하면 `false`를 반환하고, **이 경우 completion handler는 절대 호출되지 않는다.** 그런데 위 코드는 `withCheckedThrowingContinuation` 안에서 completion만 기다린다. start가 false면 continuation은 resume될 일이 없으니 **영원히 hang**한다. 그 결과 `isLoading`이 영구 true가 되고 버튼이 죽는다.

iOS에서는 start가 거의 항상 성공하니 이 버그가 안 드러났다. macOS에서는 presentation anchor가 안 잡히거나 하는 이유로 start가 false가 될 수 있어서 무반응이 됐다. 1차 수정은 간단하다.

```swift
// start()의 반환값을 확인해서 실패를 throw로 전환
guard session.start() else {
    continuation.resume(throwing: AuthError.sessionStartFailed)
    return
}
```

이걸로 무반응은 사라졌다. 그런데 이제 진짜 벽이 드러났다.

---

## 삽질 2 — 인증창은 뜨는데 OAuth 페이지가 안 뜬다

start 수정 후, macOS에서 버튼을 누르면 "이 앱이 로그인하려고 한다"는 시스템 동의 다이얼로그가 떴다. "계속"을 눌렀다. 그러면 보통은 브라우저에 Google 로그인 페이지가 떠야 한다. 그런데 **Chrome 창만 하나 열리고 OAuth 페이지는 안 떴다.** 창은 그냥 빈 상태거나 직전 탭 상태 그대로였다. 에러도, 콜백도, 로그도 없었다.

처음엔 내 코드가 authorization URL을 잘못 만든 줄 알았다. URL을 출력해보니 멀쩡했다. PKCE, state, nonce 다 정상. 그래서 기본 브라우저를 잠깐 Safari로 바꿔봤다. **그랬더니 됐다.** Safari가 기본 브라우저일 때는 로그인 페이지가 뜨고 로그인까지 완료됐다.

여기서 확신했다. 코드 문제가 아니라 **"기본 브라우저가 Chrome일 때"** 특정해서 깨지는 거다. 검색해보니 Apple 개발자 포럼에 같은 증상이 수두룩했다.

- [Apple Forums thread 725547](https://developer.apple.com/forums/thread/725547) — "Chrome이 기본 브라우저면 세션 시작 시 Chrome 창이 떴다가 즉시 닫히고, 로그인 페이지가 안 뜬다. 핸들러는 에러도 콜백도 못 받는다."
- [thread 721765](https://developer.apple.com/forums/thread/721765) — "Chrome이 기본일 때 앱이 크래시한다. Firefox나 Safari가 기본이면 정상 동작한다."
- [thread 689046](https://developer.apple.com/forums/thread/689046) — "ASWebAuthenticationSession을 쓰면 Chrome의 모든 탭이 종료되고 'Chrome이 올바르게 종료되지 않았습니다' 팝업이 뜬다."
- [thread 726888](https://developer.apple.com/forums/thread/726888) — "같은 머신, 같은 설정인데 어떤 때는 Chrome이, 어떤 때는 Safari가 열린다." (비결정적)
- [thread 814054](https://developer.apple.com/forums/thread/814054) — 최신 macOS에서도 "브라우저 앱은 dock에 뜨는데 인증 URL 창이 안 뜨는 silent failure"가 보고됐다.

증상이 토씨 하나까지 똑같았다. 그리고 thread 726888의 "어떤 때는 되고 어떤 때는 안 된다"는 관찰이 중요했다. 나도 테스트하면서 "원래 되던 게 왜 안 되지?" 싶은 순간이 있었는데, 그게 착각이 아니라 **실제로 비결정적**이었던 거다. 기본 브라우저 선택 자체가 들쭉날쭉했다.

정리하면 이건 내 버그가 아니라 **macOS의 `ASWebAuthenticationSession` + Chrome 조합에서 발생하는 Apple/Chrome 레벨의 알려진 버그**다. `prefersEphemeralWebBrowserSession = true`로 시크릿 세션을 강제해도 해결되지 않았다(포럼들에서도 동일). iOS는 항상 인앱 Safari를 쓰니까 이 문제 자체가 존재하지 않는다. 오직 macOS만, 그것도 외부 기본 브라우저를 띄우는 설계 때문에 터진다.

---

## 그럼 macOS 데스크톱 OAuth는 어떻게 해야 하나

여기서 한 발 물러서서 "원래 native app OAuth는 어떻게 하는 게 맞는가"를 봤다. 표준은 **RFC 8252 — OAuth 2.0 for Native Apps**다. 핵심 원칙은 이렇다.

> To conform to this best practice, native apps MUST use an external user-agent to perform OAuth authorization requests.

즉 native 앱은 웹뷰(embedded user-agent)가 아니라 **외부 브라우저(external user-agent)**로 로그인을 시켜야 한다. 이걸 흔히 **AppAuth 패턴**이라고 부른다. 그리고 결과를 앱으로 돌려받는 redirect 방식으로 RFC 8252는 세 가지를 제시한다.

| Redirect 방식 | 형태 | 적합한 곳 |
|---|---|---|
| Private-use URI scheme (custom scheme) | `com.example.app:/callback` | iOS/macOS 모두. RFC B.4가 macOS에 "good choice"로 명시 |
| Claimed "https" scheme (Universal Links) | `https://example.com/callback` | iOS 17.4 / macOS 14.4+에서 `ASWebAuthenticationSession.Callback`로 가능 |
| Loopback redirect | `http://127.0.0.1:{port}/cb` | 데스크톱 표준. RFC가 desktop OS에 권장 |

RFC 8252 부록 B.4(macOS Implementation Details)는 이렇게 쓰여 있다.

> Apps can initiate an authorization request in the user's default browser using platform APIs for opening URIs in the browser. To receive the authorization response, private-use URI schemes are a good redirect URI choice on macOS... Loopback IP redirects are another viable option.

핵심은 **"platform APIs for opening URIs in the browser"** 즉 `ASWebAuthenticationSession`을 거치지 말고, **내가 직접 브라우저를 열라**는 거다. `ASWebAuthenticationSession`은 Apple이 만든 편의 래퍼일 뿐이고, RFC가 요구하는 건 "외부 브라우저로 열고 redirect로 돌려받기"지 특정 API가 아니다. macOS에서 그 래퍼가 Chrome과 안 맞으면, 래퍼를 버리고 원칙대로 직접 하면 된다.

---

## 해결 — external browser + custom scheme

방향이 정해졌다. **macOS에서만** `ASWebAuthenticationSession`을 버리고, `NSWorkspace.open`으로 기본 브라우저에 authorization URL을 직접 열고, custom scheme redirect를 `onOpenURL`에서 받는다. iOS는 잘 되고 있으니 그대로 둔다.

플랫폼 분기부터.

```swift
func signIn() async throws -> URL {
    #if os(macOS)
    return try await presentExternalBrowser(url: authURL)
    #else
    return try await presentSession(url: authURL)   // iOS: ASWebAuthenticationSession 유지
    #endif
}
```

macOS 경로는 직접 브라우저를 연다. 핵심은 callback을 받을 continuation을 어딘가 저장해두고, `onOpenURL`이 그걸 깨우는 구조다.

```swift
#if os(macOS)
private var pendingCallback: CheckedContinuation<URL, Error>?
private var pendingCallbackScheme: String?

func presentExternalBrowser(url: URL) async throws -> URL {
    try await withCheckedThrowingContinuation { continuation in
        self.pendingCallback = continuation
        self.pendingCallbackScheme = self.callbackScheme

        // 사용자가 브라우저에서 취소하고 앱으로 그냥 돌아온 케이스를 잡기 위한 옵저버
        registerReturnObserver()

        if !NSWorkspace.shared.open(url) {
            finishPending(throwing: AuthError.sessionStartFailed)
        }
    }
}

// onOpenURL에서 호출. 우리 scheme이면 continuation을 깨우고 true를 반환
func handleCallback(_ url: URL) -> Bool {
    guard url.scheme == pendingCallbackScheme else { return false }
    finishPending(returning: url)
    return true
}

private func finishPending(returning url: URL) {
    pendingCallback?.resume(returning: url)
    clearPending()
}
private func finishPending(throwing error: Error) {
    pendingCallback?.resume(throwing: error)
    clearPending()
}
#endif
```

앱 진입점에서 `onOpenURL`이 이걸 가장 먼저 가로채게 한다. custom scheme redirect는 OS가 앱을 깨우면서 `onOpenURL`로 들어온다.

```swift
WindowGroup {
    RootView()
        .onOpenURL { url in
            // OAuth 콜백이면 여기서 처리하고 끝낸다
            if GoogleSignInService.shared.handleCallback(url) { return }
            // 그 외 딥링크는 기존 라우터로
            IncomingOAuthRouter.handle(url)
        }
}
```

여기까지가 정상 흐름이다. 그런데 한 가지 빈틈이 있다. **사용자가 브라우저에서 로그인을 안 하고 그냥 앱으로 돌아오면?** callback이 영영 안 오고 continuation이 또 hang한다(삽질 1의 재발). 이걸 막으려고 앱이 다시 활성화되는 시점을 감지하는 옵저버를 달았다.

```swift
private func registerReturnObserver() {
    let work = DispatchWorkItem { [weak self] in
        // 앱이 포그라운드로 돌아왔는데 일정 시간 내 콜백이 안 오면 취소로 간주
        self?.finishPending(throwing: AuthError.userCancelled)
    }
    NotificationCenter.default.addObserver(
        forName: NSApplication.didBecomeActiveNotification,
        object: nil, queue: .main
    ) { _ in
        // 1.5초 grace를 주고, 그 안에 콜백이 오면 work를 cancel
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: work)
    }
    self.pendingCancelWork = work
}
```

콜백이 grace 시간 안에 도착하면 `finishPending(returning:)`이 먼저 불리면서 `pendingCancelWork`를 cancel해버리니 취소 경로는 안 탄다. 이 grace 윈도우가 있어야 "redirect로 앱이 활성화 → 곧이어 콜백 도착" 순서에서 오탐(앱 활성화를 취소로 오인)을 막을 수 있다.

빌드해서 실기기에서 Chrome을 기본 브라우저로 둔 채 테스트했다. 이번엔 Chrome에 Google 로그인 페이지가 제대로 떴고, 로그인 후 custom scheme redirect로 앱이 깨어나 로그인이 완료됐다. macOS만 별도 경로로 갈라낸 게 정답이었다.

---

## Google Sign-In SDK를 쓰면 되지 않나

당연히 떠오르는 대안이 "공식 Google Sign-In SDK를 쓰자"였다. SDK가 알아서 잘 처리해줄 것 같았다. 그런데 확인해보니 **GoogleSignIn-iOS SDK도 macOS에서는 내부적으로 `ASWebAuthenticationSession`을 쓴다**([GoogleSignIn-iOS#388](https://github.com/google/GoogleSignIn-iOS/issues/388)). 즉 SDK를 도입해도 같은 Chrome 버그를 그대로 만난다. 편의 래퍼를 더 두꺼운 편의 래퍼로 바꾸는 것일 뿐, 근본 원인(외부 기본 브라우저 호출)은 동일하다.

그래서 SDK를 채택하지 않고 외부 브라우저를 직접 제어하는 쪽을 유지했다. 결국 RFC 8252가 말하는 "platform API로 직접 브라우저 열기"가 가장 통제 가능한 방법이었다.

---

## iOS vs macOS — 같은 OAuth, 다른 경로

이번 일을 겪고 나서 정리한 멘탈 모델은 이렇다.

| 항목 | iOS | macOS |
|---|---|---|
| `ASWebAuthenticationSession` | 인앱 Safari, 안정적 → **그대로 사용** | 외부 기본 브라우저 호출, Chrome과 충돌 → **사용 금지** |
| 권장 방식 | ASWebAuthenticationSession + custom scheme | `NSWorkspace.open` + custom scheme, 또는 loopback redirect |
| redirect 수신 | 세션 completion handler | `onOpenURL` (custom scheme) / 로컬 HTTP 서버 (loopback) |
| 취소 처리 | 세션이 알아서 에러 전달 | `didBecomeActive` 옵저버로 직접 감지 |

핵심 교훈: **"코드를 공유한다"가 "동작이 같다"를 보장하지 않는다.** 같은 `ASWebAuthenticationSession` 호출이 iOS에서는 인앱 브라우저, macOS에서는 외부 브라우저라는 전혀 다른 동작으로 갈린다. 플랫폼 API 문서에서 "동작이 플랫폼마다 다르다"는 한 줄을 흘려보내면 이런 데서 며칠을 태운다.

---

## 알려진 함정 정리

- **`session.start()`의 Bool을 반드시 확인하라.** false면 completion이 안 불린다. continuation 패턴과 만나면 영구 hang이다.
- **macOS에서 `ASWebAuthenticationSession`을 신뢰하지 마라.** 기본 브라우저가 Chrome이면 OAuth 페이지가 안 뜨거나 비결정적으로 깨진다. `prefersEphemeralWebBrowserSession`으로도 안 고쳐진다.
- **`onOpenURL`은 OAuth 콜백을 다른 딥링크보다 먼저 가로채야 한다.** 순서가 밀리면 콜백이 엉뚱한 라우터로 새서 세션이 안 닫힌다.
- **취소 경로를 명시적으로 처리하라.** 사용자가 브라우저에서 그냥 돌아오면 콜백이 영영 안 온다. 앱 재활성화 + grace timeout으로 취소를 만들어줘야 한다.
- **iOS 17.4 / macOS 14.4 이상만 타깃이면** `ASWebAuthenticationSession.Callback`으로 custom scheme 대신 claimed https URL을 쓸 수도 있다([Apple Forums 750051](https://developer.apple.com/forums/thread/750051)). 다만 macOS의 외부 브라우저 호출 자체가 문제라면 이것도 근본 해결은 아니다.
- **데스크톱이라면 loopback redirect(RFC 8252 §7.3)도 적극 고려하라.** 로컬에 임시 포트를 열어 `http://127.0.0.1:{port}/cb`로 받는 방식이다. 데스크톱 firewall이 기본 허용이고, Google/GitHub/Microsoft 등 대부분의 provider가 지원한다. custom scheme보다 "앱으로 다시 튕겨주는" 단계에 덜 의존해서 더 견고할 때가 많다.

---

## 결론

문제는 "Google 로그인이 macOS에서 안 된다"였지만, 진짜 원인은 "`ASWebAuthenticationSession`이 macOS에서는 외부 기본 브라우저를 띄우는데, 그 기본 브라우저가 Chrome이면 Apple/Chrome 레벨에서 깨진다"는 데 있었다. 편의 API 하나가 플랫폼에 따라 전혀 다르게 동작한다는 사실을 몰랐던 게 본질이었다.

해결은 표준으로 돌아가는 거였다. RFC 8252가 말하는 대로 macOS에서는 외부 브라우저를 직접 열고(custom scheme 또는 loopback) redirect를 직접 받았다. iOS는 인앱 Safari 기반의 `ASWebAuthenticationSession`이 여전히 정답이라 그대로 뒀다. 한 코드베이스 안에서 플랫폼별로 OAuth 경로를 갈라낸 것이다.

비슷한 macOS/SwiftUI 보안·인증 삽질은 [SwiftUI 시크릿 UI 보안 구멍 정리](/posts/codex-review-swiftui-secret-ui-privacysensitive-pasteboard-singleton/)에도 더 적어뒀다. 같은 에러를 검색하다 들어온 사람에게 이 글이 며칠을 아껴주면 좋겠다.
