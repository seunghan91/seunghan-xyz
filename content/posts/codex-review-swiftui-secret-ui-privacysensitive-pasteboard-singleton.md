---
title: "AI 흔적 지우기 스킬 vs AI한테 리뷰받기 — Codex가 짚어준 SwiftUI 보안 구멍 8개"
date: 2026-05-13T10:43:41+09:00
draft: false
tags: ["SwiftUI", "iOS Security", "Codex", "Code Review", "UIPasteboard"]
description: "한국어 AI 흔적 지우는 휴머나이저 스킬을 보다가 생각했다. 진짜 저자 행위는 흔적 지우기가 아니라 검증이다. Codex가 SwiftUI 시크릿 UI에서 잡아낸 privacySensitive 누락, 싱글톤 stale state, UIPasteboard 자동만료까지 8개 실전 구멍."
---

GitHub 둘러보다가 `im-not-ai`라는 Claude Code 스킬을 봤다. 한국어로 AI가 쓴 글의 흔적을 지우는 도구다. 영어 기반 AI 탐지기는 한국어를 잘 못 잡는다는 문제 의식에서 출발해서, "번역체 흔적" — 수동태 남발, 문장 첫머리 접속사, 1·2·3 병렬 구조 — 같은 10개 카테고리 40+개 서브패턴을 분류하고 S1/S2/S3 심각도로 매겨서 다듬어주는 식이다. 페이지 하단에 명시적으로 "이건 탐지 회피 도구가 아니라 글 품질 개선 유틸리티다"라고 박혀 있는 점이 인상적이었다.

흥미로운 도구긴 한데 보다가 좀 다른 생각이 들었다. AI 흔적을 지운다고 그 글이 사람 글이 되는 건 아니지 않나. 진짜 사람 저자성이라는 게 있다면 그건 표면의 문체가 아니라 검증하고 판단하는 행위 쪽일 텐데. 글 영역은 일단 옆에 두고, 코드 영역에서는 그게 더 명확하다. AI가 짠 코드인지 들키지 않으려고 변수명 바꾸고 주석 다는 시간보다, AI한테 한 번 더 리뷰시켜서 내가 못 본 구멍을 메꾸는 시간이 훨씬 author 행위에 가깝다.

마침 오늘 작업한 게 그 좋은 예시가 됐다. 운영 중인 OAuth IdP 앱의 iOS 클라이언트에 Personal API Key(PAK) 관리 화면을 새로 붙이는 일이었는데, 1차 구현 후에 Codex(`/review` 모드)한테 던졌더니 8개 항목을 잡아냈다. 그중 절반은 SwiftUI 보안 패턴이라 다른 iOS 개발자도 자주 빠뜨릴 함정이라 정리해둔다.

---

## 시작 상황 — 키는 발급됐는데 사용자가 못 본다

서버 쪽에는 PAK 관리 API가 이미 다 있었다. `GET/POST/DELETE /api/v1/me/api_keys` 세트로 발급·조회·회수가 가능했고, 발급 응답에만 plaintext가 한 번 포함되고 그 이후엔 prefix만 보여주는 표준적인 시크릿 핸들링 패턴이었다.

문제는 iOS 앱이었다. 부트스트랩 단계에서 익명 PAK이 한 번 발급돼서 Keychain에 묻혀 있는데, 사용자가 그 존재를 모른다. 폰 분실이나 토큰 유출 의심 상황에서 회수할 셀프서비스 경로가 없어서 "계정 자체를 deactivate해주세요" CS로만 풀 수 있었다. 멀티 디바이스로 쓰는 사용자는 어느 기기가 어떤 토큰을 들고 있는지 가시성이 0이었다.

본격 작업 전에 코드베이스를 훑어보니 비슷한 시크릿 관리 화면이 이미 있었다. MCP 서버 인증용 토큰 발급·조회·폐기 화면이 `MCPTokenStore` + `MCPTokenSettingsView` 쌍으로 구현돼 있었고, plaintext 1회 표시 카드와 destructive alert 패턴까지 다 있었다. 이걸 그대로 복제하면 PAK용으로 1시간 안에 끝날 일이었다.

서버 컨트롤러 응답 형식을 한 번 더 확인한 다음 Store와 View를 짰다. `id`는 Int(Rails ActiveRecord 기본), 날짜는 ISO8601 문자열, DELETE는 `{status: "revoked"}` 봉투를 돌려준다는 점만 MCP 화면과 달랐다. 사이드바 진입점은 `MainTabView`의 MCP 토큰 NavigationLink 바로 다음에 한 줄 추가했다.

```swift
NavigationLink { APIKeysSettingsView() } label: {
    Label("API 키", systemImage: "key.horizontal")
}
.buttonStyle(GlassButtonStyle(variant: .secondary))
```

`swift build` 통과, 끝. 이 단계에서 그냥 PR 던졌으면 빠른 칭찬을 받고 머지됐을 거다. 그런데 마음 한구석이 찜찜해서 Codex `/review`를 돌렸다.

---

## Codex가 짚어준 8개 — 보안 4개, 구조 2개, 위생 2개

Codex CLI의 `/review` 모드는 현재 브랜치 diff를 베이스 브랜치와 비교해서 우선순위 매긴 findings를 돌려준다. 직접 코드는 안 건드리고 진단만 한다. 8개가 나왔다.

| 분류 | 항목 | 심각도 |
|------|------|--------|
| 보안 | `issuedPlaintext`가 싱글톤에 살아남아서 화면 재진입 시 재노출 | Blocker |
| 보안 | `issue()` 시작 시 이전 plaintext가 안 비워짐 | Should fix |
| 보안 | revoke 동작에 biometric step-up 없음 | Should fix |
| 보안 | UIPasteboard에 평문 그대로 — Universal Clipboard로 다른 기기에 동기화됨 | Should fix |
| 구조 | scopes / expires_at UI가 없어서 서버 기본값에 무조건 의존 | Should fix |
| 구조 | 싱글톤이 session 전환 시 stale state 유지 | Nice-to-have |
| 위생 | 테스트 0개 — 보안 민감 DTO인데 round-trip 검증 부재 | Should fix |
| 위생 | VoiceOver 힌트 부재 | Nice-to-have |

이 중 보안 4개가 흥미롭다. 하나씩 들어간다.

---

## 1. 싱글톤 stale state — `.onDisappear`만으로는 부족하다

처음 발견한 게 가장 아팠다. 코드를 보자:

```swift
@MainActor
public final class APIKeysStore: ObservableObject {
    public static let shared = APIKeysStore()
    @Published public private(set) var issuedPlaintext: String?
    // ...
}
```

View는 `@StateObject private var store = APIKeysStore.shared`로 싱글톤을 구독한다. 발급 직후엔 `store.issuedPlaintext`가 채워져서 카드가 뜬다. 사용자가 "숨기기" 버튼 안 누르고 그냥 뒤로 가면? 싱글톤이라 plaintext가 살아있다. 다시 화면 들어오면 그대로 보인다. UI 카피에는 "한 번만 표시됩니다"라고 박혀있는데 거짓말이 된다.

처음엔 `.onDisappear` 한 줄로 해결하려 했다.

```swift
.onDisappear { store.clearIssuedPlaintext() }
```

이걸로 사용자가 뒤로 가는 경우는 막힌다. 그런데 다른 경로가 더 있었다. 사용자가 "발급 후 화면 켠 채로 백그라운드 → 5분 후 세션 만료 → 폰 들어옴" 시나리오에서, 만료된 세션의 plaintext가 그대로 떠 있다. 해결책은 `APIClient`가 401 받았을 때 쏘는 `.logiSessionExpired` 노티피케이션을 Store도 구독하는 거였다.

```swift
private var sessionExpiredObserver: NSObjectProtocol?

public init() {
    sessionExpiredObserver = NotificationCenter.default.addObserver(
        forName: .logiSessionExpired,
        object: nil,
        queue: .main
    ) { [weak self] _ in
        Task { @MainActor in self?.resetAll() }
    }
}
```

여기서 또 함정 하나. 싱글톤은 deinit이 안 불려서 `removeObserver` 코드가 dead code인 줄 알고 지울 뻔했다. 그런데 테스트는 `APIKeysStore()`로 non-shared 인스턴스를 만든다. 그 인스턴스들은 deinit 시 observer 해제가 필요하다. dead code가 아니라 방어 코드였다. 싱글톤 가정만 보고 cleanup 코드를 지우면 테스트가 NotificationCenter observer를 누수한다.

---

## 2. `UIPasteboard.setItems(_:options:)` — 클립보드 자동 만료의 정석

`UIPasteboard.general.string = value`로 끝내면 안 된다는 건 알고 있었지만, 어떤 API를 써야 하는지는 흐릿했다. Codex가 짚어준 뒤 다시 찾아봤다.

iOS 10부터 Universal Clipboard가 기본 활성이다. 사용자가 iCloud에 로그인돼 있으면 폰에서 복사한 텍스트가 근처 맥북·아이패드에 자동으로 동기화된다. 발급된 API 키 평문이 이 채널 타고 다른 기기에 뜨는 건 명백한 보안 사고다.

해결 API는 두 개 옵션이 있다. `localOnly: true`는 Universal Clipboard 배제, `expirationDate`는 클립보드에서 자동 삭제 시각 설정. 같이 쓸 수 있다.

```swift
let expiry = Date().addingTimeInterval(60)
UIPasteboard.general.setItems(
    [[UIPasteboard.typeAutomatic: value]],
    options: [
        .expirationDate: expiry,
        .localOnly: true
    ]
)
```

여기서 자체 의심 사건이 하나 있었다. 코드 짜고 나서 `UIPasteboard.typeAutomatic`이 진짜 존재하는 심볼인지 의심이 들었다. `swift build`는 통과했는데, 이게 macOS 타깃으로만 빌드된 거고 해당 코드는 `#if canImport(UIKit)` 안에 있어서 컴파일된 적이 없었다. SDK 헤더를 grep해봐도 `UIPasteboard.h`에서 `typeAutomatic`이 안 보였다.

근데 자체 의심이라는 게 가끔 틀린다. 30초짜리 swiftc 단일 파일 타입체크가 진실이다.

```bash
cat > /tmp/pb_check.swift <<'EOF'
import UIKit
func test(value: String) {
    UIPasteboard.general.setItems(
        [[UIPasteboard.typeAutomatic: value]],
        options: [.expirationDate: Date().addingTimeInterval(60), .localOnly: true]
    )
}
EOF
xcrun -sdk iphonesimulator swiftc -typecheck \
    -target arm64-apple-ios26.0-simulator /tmp/pb_check.swift
```

에러 출력 0줄. 멀쩡한 심볼이다. 헤더 grep으로는 안 잡혔지만 Swift overlay나 extension 어딘가에 정의돼 있는 거였다. 컴파일러가 헤더 검색보다 항상 한 수 위다.

추가로 알게 된 가시 함정: Apple Discussions 글 보니까 `expirationDate`가 로컬 클립보드에선 시간 맞춰 비워지는데, **Universal Clipboard 쪽에서는 expirationDate가 무시되는** 버그성 동작이 보고됐다. 그래서 `localOnly: true`를 같이 박는 게 안전한 조합이다. 두 옵션을 동시에 거는 건 zero-trust 자세에 가깝다 — 어느 한쪽이 OS 버그로 실패해도 다른 쪽이 막아준다.

---

## 3. `.privacySensitive()` — App Switcher 스냅샷 redact

이게 가장 한국 iOS 블로그에 덜 알려진 패턴 같다. Codex가 "screenshot retention is a hypothesis"라고 짚어준 부분인데, 그 가설이 사실 정확히 들어맞는다.

iOS는 앱이 백그라운드로 빠질 때 앱 스위처 카드용 스냅샷을 자동으로 찍어둔다. 그 스냅샷은 다음 사용자가 멀티태스킹 제스처로 카드를 열 때 보인다. 발급된 API 키 평문이 화면에 떠 있을 때 사용자가 홈으로 빠지면? 키가 스냅샷에 캡쳐돼서 카드에 계속 보인다. 손가락만 까딱하면 누가 봐도 보이는 위치다.

SwiftUI는 이걸 위해 두 개 modifier 조합을 제공한다. `.privacySensitive()`로 "이 뷰는 민감"이라는 marking을 하고, 상위 뷰 어딘가에 `.redacted(reason: .privacy)`를 걸면 자동 redact된다. 다만 OS가 자체적으로 privacy redaction을 거는 컨텍스트(잠금화면 위젯, Always-On 디스플레이, App Switcher 스냅샷 등)에서는 `.privacySensitive()`만 있어도 충분하다 — 시스템이 알아서 redaction reason을 주입한다.

내가 추가한 건 한 줄이다.

```swift
Text(token)
    .font(.system(.footnote, design: .monospaced))
    .textSelection(.enabled)
    // ...
    .privacySensitive()
```

원리는 환경 변수 `\.redactionReasons`다. 평소엔 비어 있고, 시스템이 privacy 컨텍스트라고 판단하면 `.privacy`가 채워진다. `.privacySensitive()` modifier는 그 컨텍스트 안에서 자동으로 회색 박스로 가린다. 커스텀 redact 표현을 쓰고 싶으면:

```swift
@Environment(\.redactionReasons) var reasons

var body: some View {
    if reasons.contains(.privacy) {
        Text("[HIDDEN]")
    } else {
        Text(plaintext)
    }
}
```

이런 식으로 분기할 수도 있다. 내 케이스는 기본 회색 박스로 충분해서 한 줄로 끝냈다.

추가로 직접 컨트롤이 필요한 시나리오(예: blur 효과를 쓰고 싶거나 OS가 자동 적용하지 않는 컨텍스트)에서는 `@Environment(\.scenePhase)`를 직접 구독해서 `.blur(radius:)` 같은 modifier로 손수 처리하는 패턴도 있다. SwiftUI Vincent 블로그에 깔끔한 예제가 있는데, 같은 ViewModifier로 추출해두면 앱 전역에서 재사용된다. 다만 그 경우 OS의 자동 redaction 시스템과 별도로 동작하므로 둘 다 거는 게 안전하다.

---

## 4. Biometric gate는 발급뿐 아니라 폐기에도

처음엔 발급 동작만 Face ID로 막았다. Codex가 "destructive action도 step-up 대상"이라고 짚었다. 맞는 말이다. 폰 잠금이 풀린 상태에서 누가 잠깐 빌려갔을 때, 그 사람이 사용자 API 키를 폐기하면 그것도 공격이다. 발급보다 폐기가 더 즉시적이고 되돌릴 수 없다.

코드는 단순하다. destructive alert 버튼 액션을 Task로 감싸고, 그 안에서 `BiometricGate.require`를 먼저 통과시킨다.

```swift
.alert("API 키를 폐기할까요?", isPresented: ...) {
    Button("취소", role: .cancel) { revokeTarget = nil }
    Button("폐기", role: .destructive) {
        if let target = revokeTarget {
            Task {
                let allowed = await BiometricGate.require(reason: "API 키 폐기")
                guard allowed else {
                    revokeTarget = nil
                    return
                }
                await store.revoke(target)
                revokeTarget = nil
            }
        }
    }
}
```

alert 버튼 액션은 동기 클로저라 await을 직접 못 쓴다. Task로 감싸야 한다. 그 사이 alert는 이미 닫혔는데 그건 문제 없다 — `revokeTarget = nil`을 두 경로(취소·완료) 모두에서 명시적으로 해주면 상태가 깨지지 않는다.

---

## 5. scopes / expiry 직접 선택 vs 서버 기본값

내 첫 구현은 POST body에 `name`만 보냈다. 서버가 사용자 역할에 따라 기본 scope를 채워주고, `expires_at`이 없으면 무기한으로 처리한다. 빠르고 간단했다.

Codex 의견은 분명했다. "I disagree with shipping Personal API Keys without at least an expiry choice or visibly constrained defaults." 보안 IdP가 만료 옵션조차 보여주지 않는 건 권장 안 한다는 거다.

타협안은 두 가지:

- **만료**: 5단계 segmented picker로 7일/30일/90일/1년/무기한, 기본값 90일. 사용자가 명시적으로 "무기한"을 골라야 무기한이 된다. 권장값을 라벨에 박았다 ("90일 (권장)").
- **scopes**: 14개나 돼서 기본 화면에 깔면 노이즈가 너무 크다. `DisclosureGroup` "고급" 아래에 14개 토글로 숨기고, 도입부에 "비워두면 서버 기본값이 적용됩니다" 안내문을 박았다.

POST body 빌드 로직은 조건부로 키를 추가한다.

```swift
var body: [String: Any] = ["name": trimmed]
if !scopes.isEmpty {
    body["scopes"] = scopes
}
if let expiresAt {
    body["expires_at"] = ISO8601DateFormatter().string(from: expiresAt)
}
```

빈 scopes 셋은 body에서 생략 → 서버 default가 적용. 명시한 경우만 전송. 이렇게 두면 단순 사용자는 안전한 default(90일+역할 기본 scope)를 받고, CLI나 머신용 키가 필요한 고급 사용자는 "고급" 펼쳐서 세밀하게 고르면 된다.

---

## 환경 함정 — `swift build`와 `xcodebuild`의 검증 갭

이건 코드 문제가 아니라 검증 절차 문제다. `swift build --package-path Packages/LogiCore`가 통과했다고 iOS 타깃이 무사한 게 아니다. `swift build`는 호스트 플랫폼(macOS) 타깃만 빌드한다. `#if canImport(UIKit)` 블록 안의 코드는 컴파일된 적이 없다. 위 `typeAutomatic` 의심도 이 갭에서 출발했다.

이상적으론 xcodebuild로 iOS 시뮬레이터 빌드를 한 번 더 돌려야 한다. 시도해봤다.

```bash
xcodebuild -project ios/myapp.xcodeproj \
  -scheme myapp \
  -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  build CODE_SIGNING_ALLOWED=NO
```

결과: swift-syntax 매크로 의존성 해결 실패가 우수수 떨어졌다.

```
error: unable to resolve module dependency: 'SwiftSyntax'
error: unable to resolve module dependency: 'SwiftDiagnostics'
error: unable to resolve module dependency: 'SwiftSyntaxMacros'
error: unable to resolve module dependency: 'SwiftCompilerPlugin'
```

swift-perception, swift-dependencies, swift-composable-architecture 같은 매크로 플러그인이 swift-syntax 서브모듈을 못 불러온다. DerivedData 청소 후 재시도해도 동일. Xcode GUI에서 빌드하면 정상 동작하는데, CLI에서만 매크로 플러그인 의존성 해결이 깨진다. SwiftPM의 plugin resolution과 xcodebuild의 build system이 잘 안 맞는 케이스다.

결국 단일 파일 swiftc 타입체크로 핵심 pasteboard 부분만 검증하고 마무리했다. iOS 타깃 end-to-end 빌드는 Xcode GUI 또는 CI 잡에서 한 번 더 돌려야 한다고 PR 노트에 남겼다. 모든 걸 CLI에서 검증하려는 욕심을 접고 검증 갭을 명시적으로 인정하는 게 더 정직한 선택이었다.

---

## 테스트 — 보안 민감 DTO엔 round-trip이 최저선

마지막 should-fix는 테스트였다. MCP 토큰 화면도 테스트가 없어서 "기존 코드도 없으니까 안 써도 되겠지" 합리화했었는데, Codex가 "PAK는 더 민감하다, decode round-trip만이라도 깔아라"라고 했다. 옳다.

추가한 6개 테스트:

```
testDecodesListResponseWithMixedNullFields  // null 섞인 list
testDecodesCreateResponseIncludingPlaintext // plaintext 1회 노출 확인
testClearIssuedPlaintextNilsBothFields      // clear 동작
testResetAllWipesEverything                 // resetAll 동작
testSessionExpiredNotificationResetsStore   // notification 구독 동작
testKnownScopesMatchesServerList            // server scope 미러 검증
```

마지막이 좀 재밌다. 서버 `PersonalApiKey::KNOWN_SCOPES` 14개를 클라이언트에 미러로 두고 있는데, 서버가 새 scope 추가하면 클라이언트 미러가 드리프트한다. 그래서 expected set과 비교하는 테스트를 박아두면 서버 추가가 일어났을 때 클라이언트 테스트가 빨갛게 떨어진다 — 사실상 contract drift detector다. 정확히 같은 패턴이 OpenAPI 스펙 누락을 잡아내는 데도 쓸 수 있다.

테스트 헬퍼는 `#if DEBUG`로 가뒀다.

```swift
#if DEBUG
@MainActor
func _setIssuedForTest(plaintext: String, id: Int) {
    issuedPlaintext = plaintext
    issuedKeyId = id
}
#endif
```

`@testable import`는 internal 가시성에 접근하지만 release 빌드에서는 DEBUG 매크로가 정의되지 않으므로 이 메서드 자체가 컴파일되지 않는다. 테스트 인프라가 production 바이너리에 새어나가는 걸 막는 표준 패턴이다.

---

## 다시 도입으로 — 흔적 지우기 vs 검증

처음 본 `im-not-ai` 스킬 이야기로 돌아간다. 그 스킬은 정직하게 "탐지 회피용이 아니라 품질 개선용"이라고 밝힌다. 좋은 명시다. 다만 한국어 글 영역에서 AI 흔적을 지운다는 행위 자체가, 코드 영역에서 "AI한테 한 번 더 리뷰시켜 내가 못 본 8개 구멍을 메꾸는" 행위와 어느 쪽이 더 author 행위인가는 답이 분명하다고 느낀다.

오늘 1차 구현만 했으면 PAK 발급 직후 사용자가 홈 누른 순간 App Switcher 카드에 평문이 그대로 떴을 거다. 복사한 순간 사용자 맥북에도 같이 동기화됐을 거다. 사용자가 화면 다시 들어왔을 때 "한 번만 표시됩니다" 카피와 모순되게 plaintext가 재노출됐을 거다. 폰 잠깐 빌려준 사이에 누가 키를 폐기했어도 막을 방법이 없었을 거다.

이 네 가지를 메꾼 30분짜리 작업이 본질이고, 그 작업의 출발이 Codex의 8줄짜리 진단이었다. 진단을 그대로 받아들이지 않고 — 예를 들어 deinit이 dead code라는 한 항목은 재검토 후 거절했고, `typeAutomatic` 자체 의심은 swiftc 한 줄로 뒤집었다 — 사례별로 채택·반려·검증한 게 author 행위였다.

흔적을 지운다고 사람 글이 되지 않는다. 흔적이 있어도 검증된 결과가 사람의 결과다. AI 시대 코딩의 차별화는 위장이 아니라 검증 루프 안에서 일어난다.

---

## 정리 — 다른 iOS 시크릿 UI에 그대로 가져갈 체크리스트

다른 프로젝트에서 비슷한 "토큰·키·OTP 1회 노출 화면" 만들 때 그대로 가져갈 것:

1. **plaintext Text에 `.privacySensitive()`** — App Switcher 스냅샷 자동 redact
2. **`UIPasteboard.setItems` + `.expirationDate` + `.localOnly: true`** — 자동 만료 + Universal Clipboard 차단
3. **싱글톤 Store면 `.onDisappear` clear + `.logiSessionExpired`(또는 sign-out 시그널) 구독** — stale state 양방향 방어
4. **issue() 시작 시점에 이전 plaintext 즉시 clear** — 검증/실패 경로에서도 깨끗
5. **Destructive action에도 BiometricGate** — 발급뿐 아니라 폐기·회전·이전도
6. **scopes/expiry 선택지를 UI에 노출** — default를 안전하게, 명시는 가능하게
7. **decode round-trip 테스트 + KNOWN 상수 미러 테스트** — 서버 contract drift 자동 감지
8. **테스트 헬퍼는 `#if DEBUG`** — release 바이너리에 누수 금지

여기에 더해서, Codex `/review` 같은 페어 리뷰어를 PR 직전 루틴에 박아두는 것. 8개 항목 중 절반 이상이 한국어 SwiftUI 블로그에서도 흔히 빠뜨리는 항목이라, 사람 리뷰어 한 명만 보는 것보다 통계적으로 catch rate가 확실히 올라간다.
