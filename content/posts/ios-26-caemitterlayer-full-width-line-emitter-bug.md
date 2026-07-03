---
title: "iOS 26에서 CAEmitterLayer 폭죽이 안 터진다 — 전체폭 line emitter 방출 드롭 회귀 디버깅기"
date: 2026-07-03T09:56:31+09:00
draft: false
tags: ["iOS", "CAEmitterLayer", "SwiftUI", "디버깅", "iOS26"]
description: "iOS 26에서 emitterSize가 화면 전체폭인 CAEmitterLayer .line emitter가 파티클을 전혀 방출하지 않는 회귀를 만났다. 시뮬레이터 스크린샷 기반 4라운드 A/B 판별로 원인을 격리하고 반폭 2-emitter 분할로 해결한 기록. SwiftUI @Observable Binding 추적 단절, zero-bounds 레이스, beginTime convertTime까지."
---

TestFlight 빌드를 받은 테스터에게서 피드백이 왔다. "축하 화면에서 폭죽이 안 터지는데?" NFC 태그 등록에 성공하면 전면 축하 화면과 함께 색종이(confetti)가 쏟아지게 만들어놨는데, 실기기에서 카드만 뜨고 파티클이 전혀 안 보인다는 거다.

코드를 보면 멀쩡하다. `CAEmitterLayer`를 `UIViewRepresentable`로 감싼 전형적인 confetti 구현이고, 시뮬레이터 프리뷰에서는 몇 달 전부터 잘 돌았다. 그런데 iOS 26 실기기에서는 빌드를 두 번 갈아엎어도 안 터졌다. 결론부터 말하면 **iOS 26에서 emitterSize가 화면 전체폭인 `.line` emitter는 셀 구성과 타이밍이 전부 정상이어도 방출 자체가 통째로 드롭되는 회귀**가 있었고, 검색해도 안 나오는 문제라 A/B 판별로 직접 격리해야 했다. 이 글은 그 4라운드 디버깅 기록이다. 가는 길에 SwiftUI `@Observable`의 수동 Binding 추적 단절, `updateUIView` zero-bounds 레이스 같은 다른 함정도 두 개 잡았다.

---

## CAEmitterLayer 기본 구조

디버깅 과정을 이해하려면 `CAEmitterLayer`의 구조를 먼저 짚어야 한다. NSHipster의 비유가 제일 명쾌하다:

- **`CAEmitterLayer`** = 색종이 대포. 어디서(`emitterPosition`), 어떤 모양의 영역에서(`emitterShape`, `emitterSize`), 어떻게(`emitterMode`) 파티클을 쏠지 정한다.
- **`CAEmitterCell`** = 대포에 장전된 색종이 종류. 색·이미지(`contents`), 초당 개수(`birthRate`), 수명(`lifetime`), 속도·중력(`velocity`, `yAcceleration`), 회전(`spin`) 등을 정한다.

성능 비결은 파티클을 개별 추적하지 않는다는 것. 한 번 생성된 파티클은 수정 불가능하고 서로 상호작용하지 않아서 GPU에서 병렬 렌더링된다. 대신 설정 API 표면적이 어마어마하게 넓고, **뭔가 잘못되면 그냥 조용히 아무것도 안 그린다.** 에러도, 로그도, 경고도 없다. 이번 삽질이 길어진 근본 이유다.

문제의 원본 코드는 이랬다. 화면 상단 전체 폭에서 색종이가 비처럼 내리는 구성:

```swift
let emitter = CAEmitterLayer()
emitter.emitterShape = .line
emitter.emitterMode = .outline
emitter.renderMode = .unordered
emitter.emitterPosition = CGPoint(x: bounds.midX, y: -12)
emitter.emitterSize = CGSize(width: bounds.width, height: 1)  // ← 화면 전체폭
emitter.frame = bounds
emitter.beginTime = CACurrentMediaTime()
emitter.emitterCells = palette.flatMap {
    [makeCell(color: $0, shape: .rectangle), makeCell(color: $0, shape: .circle)]
}  // 7색 × 2모양 = 14셀
layer.addSublayer(emitter)
```

수년간 인터넷에 돌아다닌 교과서 구성 그대로다. iOS 25까지는.

---

## 용의자 1: Reduce Motion — 시뮬레이터 재현으로 기각

첫 가설은 접근성 설정이었다. confetti 뷰가 `@Environment(\.accessibilityReduceMotion)`을 존중해서 동작 줄이기가 켜져 있으면 파티클을 안 그리게 돼 있었다. "카드는 뜨는데 파티클만 없다"는 증상과 정확히 일치한다.

그런데 사용자 기기 설정을 물어보기 전에 시뮬레이터에서 먼저 재현을 시도했다. 시뮬레이터는 동작 줄이기가 기본 OFF니까, 여기서도 안 터지면 접근성 문제가 아니다.

재현하려면 축하 화면을 강제로 띄울 방법이 필요했다. 실제 플로우는 로그인 + NFC 등록을 거쳐야 해서 스크립트로 돌리기 번거롭다. 그래서 DEBUG 전용 환경변수 훅을 하나 심었다:

```swift
#if DEBUG
if ProcessInfo.processInfo.environment["DEBUG_CELEBRATE"] == "1" {
    activationRecord = /* 더미 레코드 */
}
#endif
```

이러면 `simctl`로 전체 검증 루프를 자동화할 수 있다. 이 루프가 이번 디버깅의 핵심 도구였다:

```bash
xcodebuild -project App.xcodeproj -scheme App -configuration Debug \
  -destination "platform=iOS Simulator,id=$UDID" -derivedDataPath "$DD" build -quiet
xcrun simctl install "$UDID" "$APP"
SIMCTL_CHILD_DEBUG_CELEBRATE=1 xcrun simctl launch "$UDID" com.example.app
sleep 3.0
xcrun simctl io "$UDID" screenshot shot.png
```

`SIMCTL_CHILD_` 접두사를 붙이면 `simctl launch`가 그 환경변수를 앱 프로세스에 넘겨준다. 빌드→설치→실행→스크린샷까지 사람 손 없이 90초. 결과: **시뮬레이터에서도 파티클이 안 나왔다.** 접근성 가설 기각, 그리고 이제 재현 환경이 생겼다.

---

## 용의자 2: @Observable + 수동 Binding — 이건 진짜 버그였다 (다른 버그)

시뮬레이터 재현 전에 코드 리뷰에서 잡힌 별개의 버그가 하나 있다. 축하 화면을 띄우는 코드가 이런 모양이었다:

```swift
// ❌ @Observable 추적이 끊기는 패턴
.fullScreenCover(isPresented: Binding(
    get: { router.lastEnrolledRecord != nil },
    set: { if !$0 { router.clearLastEnrolled() } }
)) { ... }
```

`@Observable` 매크로의 의존성 추적은 **body 평가 중에 읽힌 프로퍼티만** 등록한다. 그런데 이 코드는 `lastEnrolledRecord`를 body 본문이 아니라 수동 `Binding`의 getter 클로저 안에서만 읽는다. getter가 언제 호출되느냐는 SwiftUI 내부 사정이라, 값이 바뀌어도 뷰 재평가가 누락될 수 있다. 시뮬레이터에서 "가끔 되는" 것처럼 보였던 건 다른 상태 변화가 우연히 리렌더를 유발해서였다.

수정은 신호를 `onChange`로 받아 `@State`로 presentation을 구동하는 것:

```swift
// ✅ onChange가 body 평가 중 값을 읽으므로 추적이 보장된다
@State private var activationRecord: KeyRecord?

.onChange(of: router.lastEnrolledRecord?.uid, initial: true) { _, _ in
    activationRecord = router.lastEnrolledRecord
}
.fullScreenCover(item: $activationRecord, onDismiss: {
    router.clearLastEnrolled()
}) { rec in ... }
```

`initial: true`는 콜드런치 딥링크처럼 뷰 등장 이전에 신호가 세팅된 경우까지 커버한다. 이 수정으로 "축하 카드 자체가 안 뜨는" 문제는 해결됐다. 하지만 파티클은 여전히 안 나왔다.

## 용의자 3: updateUIView 시점의 zero-bounds 레이스

`UIViewRepresentable` 쪽에도 함정이 있었다:

```swift
func updateUIView(_ uiView: ConfettiEmitterView, context: Context) {
    uiView.startBurst()   // 내부에서 guard bounds.width > 0
}
```

`makeUIView` 직후 첫 `updateUIView`가 불리는 시점엔 아직 레이아웃 전이라 bounds가 0이다. guard에 걸려 발동이 스킵되는데, 문제는 **SwiftUI가 updateUIView를 다시 불러주는 건 부모 리렌더 타이밍이라는 우연에 달려 있다**는 것. Debug에서는 엔트런스 애니메이션 상태 변화가 리렌더를 유발해 우연히 살았고, Release 실기기에서는 영영 안 불릴 수 있다.

교과서적 수정은 레이아웃 확정 시점 재시도:

```swift
override func layoutSubviews() {
    super.layoutSubviews()
    if !didStart, bounds.width > 0 {
        startBurst()   // didStart 가드로 중복 발동 없음
    }
}
```

NSLog를 심어 확인하니 재시도는 정상 동작했다. bounds 402×874에서 emitter가 추가되고, 셀 14개, contents 전부 non-nil, hidden 아님, alpha 1. **레이어는 완벽하게 살아있는데 화면엔 아무것도 없었다.**

## 용의자 4: beginTime 시간공간 — delta 0.000으로 기각

`beginTime`은 `CAMediaTiming` 프로토콜 소속이고 **부모 레이어의 시간공간 기준**이다. `CACurrentMediaTime()`(호스트 절대시간)을 그대로 넣었는데 레이어 트리의 시간공간이 어긋나 있으면 beginTime이 미래 시각이 되어 방출이 영영 시작 안 될 수 있다. iOS 7 시절부터 유명한 함정이라(당시엔 반대로 "과거부터 방출된 것처럼 파티클이 쏟아지는" 문제였다) 정석대로 변환을 넣고 로그로 확인했다:

```swift
let hostNow = CACurrentMediaTime()
let layerNow = layer.convertTime(hostNow, from: nil)
NSLog("[confetti] delta=%.3f", hostNow - layerNow)
emitter.beginTime = layerNow
```

```
[confetti] time hostNow=170034.439 layerNow=170034.439 delta=0.000
```

delta 0. 시간공간은 일치했고 이 가설도 기각. 다만 `convertTime` 변환 자체는 정석이라 수정엔 남겨뒀다.

---

## A/B 판별: 진단 emitter 매트릭스

정적 분석으로 잡을 수 있는 건 다 기각됐다. 여기서부터는 empirical하게 갔다 — **설정이 다른 진단용 emitter 여러 개를 화면 좌/중/우에 색깔별로 깔고, 뭐가 그려지고 뭐가 안 그려지는지로 변수를 소거**하는 방식이다. 시뮬레이터 스크린샷 루프가 있으니 한 라운드에 90초면 된다.

| 라운드 | 변형 | 결과 | 소거된 가설 |
|---|---|---|---|
| 1 | `.point` shape × (기본/.volume/.outline 모드) 3종 | 🔴🟢🔵 전부 렌더 | CAEmitterLayer 자체는 정상. `.outline` 모드 무죄 |
| 2 | `.line` shape × (outline+y-12 / volume / y=+2) 3종, 폭 1/3 | 전부 렌더 | `.line`+`.outline` 조합 무죄, 화면 밖(y=-12) 스폰 무죄 |
| 3 | 원본 풀 구성 반폭 2종 — beginTime 유/무만 차이 | 둘 다 렌더 | beginTime 완전 무죄 |
| 4 | 반폭 × 팔레트 14셀 vs 7셀 | 둘 다 렌더 | 셀 개수(14) 무죄 |

4라운드가 끝나고 나니 소거법의 결론이 명확해졌다. 진단 emitter들과 원본의 남은 차이는 단 하나 — **`emitterSize`가 화면 전체폭(402pt)이냐, 그보다 좁으냐(~183pt)**. 그리고 매 라운드 스크린샷에서 원본 emitter의 7색 팔레트 파티클은 한 번도 보이지 않았다.

- 전체폭 단일 `.line` emitter → ❌ 항상 빈 화면
- 반폭 `.line` emitter 2개 (동일 셀 배열·모드·beginTime) → ✅ 정상 방출

iOS 26 시뮬레이터(26.5)와 실기기 양쪽에서 재현됐고, 같은 코드가 이전 OS에서는 수년간 잘 돌았다. 공개된 버그 리포트나 StackOverflow 글은 아직 못 찾았다 — iOS 26의 렌더링 파이프라인 개편(Liquid Glass) 과정에서 생긴 회귀로 추정할 뿐이다.

## 수정: 반폭 2-emitter 분할

원인을 알면 수정은 간단하다. 전체폭 emitter 1개를 반폭 2개(좌 0.25w / 우 0.75w)로 쪼개면 시각적으로 동일한 "상단 전폭 색종이 라인"이 나온다:

```swift
emitterLayers = (0..<2).map { _ in
    let emitter = CAEmitterLayer()
    emitter.emitterShape = .line
    emitter.emitterMode = .outline
    emitter.renderMode = .unordered
    emitter.beginTime = layer.convertTime(CACurrentMediaTime(), from: nil)
    emitter.emitterCells = palette.flatMap {
        [makeCell(color: $0, shape: .rectangle), makeCell(color: $0, shape: .circle)]
    }
    layer.addSublayer(emitter)
    return emitter
}

private func layoutEmitters() {
    for (i, emitter) in emitterLayers.enumerated() {
        emitter.emitterPosition = CGPoint(x: bounds.width * (i == 0 ? 0.25 : 0.75), y: -12)
        emitter.emitterSize = CGSize(width: bounds.width / 2, height: 1)
        emitter.frame = bounds
    }
}
```

한 가지 놓치기 쉬운 건 **파티클 총량 보정**이다. 셀의 birthRate 공식이 `intensity / (색 수 × 모양 수)`였다면, emitter가 2개가 됐으니 분모에 ×2를 해줘야 초당 총 파티클 수가 유지된다. 안 하면 폭죽이 두 배로 쏟아진다(그것대로 축제 같긴 하다).

수정 빌드의 시뮬레이터 스크린샷에서 의도한 디자인 그대로 전폭 색종이가 확인됐고, 실기기 TestFlight 빌드에서도 재현됐다.

---

## 그냥 라이브러리 쓰면 안 되나?

디버깅이 길어지니 당연히 이 생각이 든다. 조사해본 현재 시점 선택지:

| 라이브러리 | 렌더링 | 특징 | 이번 회귀 영향 |
|---|---|---|---|
| [Vortex](https://github.com/twostraws/Vortex) (twostraws) | SwiftUI 네이티브 | 고성능 파티클 시스템, `.confetti`/`.fireworks` 프리셋, 전 Apple 플랫폼 | 없음 (CAEmitterLayer 미사용) |
| [ConfettiSwiftUI](https://github.com/simibac/ConfettiSwiftUI) | SwiftUI 네이티브 | 사실상 표준. 포인트 대포(burst) 스타일 | 없음 |
| [EffectsLibrary](https://github.com/GetStream/effects-library) (GetStream) | **내부적으로 CAEmitterLayer/SKEmitterNode** | 6종 프리셋 (snow/rain/fire/fireworks/smoke/confetti) | **있을 수 있음** — 내부 구현이 CAEmitterLayer면 같은 회귀를 밟는다 |
| swiftui-particles (benlmyers) | SwiftUI 네이티브 | 선언형 문법 | 없음 |

교훈이 하나 있다면: **"라이브러리를 쓰면 안전하다"가 아니라 "렌더링 백엔드가 뭔지 봐야 안전하다"**. EffectsLibrary처럼 내부가 CAEmitterLayer인 래퍼는 이번 회귀를 그대로 물려받는다.

우리는 자체 구현을 유지했다. 이유는 셋 — ① 반폭 분할 수정이 이미 검증됐고 의존성이 0이다 ② 원하는 비주얼이 "상단 전폭 비"인데 ConfettiSwiftUI는 포인트 대포 스타일이라 다르다 ③ Android 쪽에 같은 디자인의 Compose 미러 구현이 있어 파리티를 유지하고 싶었다. 하지만 신규 프로젝트라면 Vortex부터 검토하는 게 맞다고 본다. CAEmitterLayer는 이번 건 말고도 백그라운드 전환 후 방출이 멈추는 고질병 등 세월에 걸친 잔버그가 많은 API다.

## 이번에 챙긴 디버깅 패턴

버그 자체보다 이쪽이 재사용 가치가 크다.

**1. DEBUG 환경변수 훅으로 UI 상태 강제.** 로그인·하드웨어(NFC)가 필요한 화면도 `ProcessInfo.processInfo.environment` 체크 하나면 시뮬레이터에서 즉시 띄울 수 있다. `#if DEBUG` 게이트라 Release엔 컴파일 자체가 안 된다. 한 번 심어두면 QA 하니스로 계속 쓴다.

**2. simctl 스크린샷 루프.** `SIMCTL_CHILD_*` env 전달 + `simctl io screenshot`으로 "빌드→실행→육안 확인"을 완전 자동화. 렌더링 버그는 로그로 안 잡히니 스크린샷이 곧 assert다.

**3. 색깔로 구분한 진단 emitter 매트릭스.** 렌더링처럼 조용히 실패하는 시스템은 로그 대신 **변형들을 한 화면에 동시에 깔고 시각적으로 소거**하는 게 빠르다. 라운드당 변수 하나가 아니라, 위치·색으로 구분되는 변형 3개씩을 병렬로 검증했다.

**4. 로그는 "어디까지 살아있는지"를 자르는 용도.** `startBurst 호출됨 → bounds 정상 → 레이어 추가됨 → 셀 contents 정상`까지 확인되면, 남는 건 렌더링 계층뿐이라는 걸 알고 전략을 바꿀 수 있었다.

## 주의사항

- 이 회귀의 정확한 경계(전체폭의 몇 %부터 드롭되는지, bounds와의 관계인지 절대 폭인지)까지는 파지 않았다. 반폭(50%)은 확실히 동작하고 전체폭(100%)은 확실히 실패한다는 것만 검증했다. 여유를 두고 싶으면 3분할도 방법이다.
- `emitterShape = .line`은 원래도 emitterSize의 height를 무시한다(수직 라인을 원하면 transform 회전이 정석). 이번 건과 별개의 오래된 스펙.
- iOS 26에서 멀쩡히 도는 CAEmitterLayer 코드도 있다 — `.point` shape나 좁은 `.line`은 전부 정상이었다. 전수 실패가 아니라서 오히려 발견이 늦어지는 유형의 회귀다.
- Reduce Motion 대응은 유지하는 게 맞다. 접근성 설정 사용자가 파티클 없이 카드만 보는 건 의도된 동작이다.

## 결론

"폭죽이 안 터져요"라는 한 줄 제보의 뒤에는 버그가 세 겹 있었다. `@Observable` 수동 Binding 추적 단절(카드가 안 뜸), `updateUIView` zero-bounds 레이스(발동이 우연에 의존), 그리고 iOS 26의 전체폭 line emitter 방출 드롭 회귀(진범). 앞의 둘은 코드 리뷰와 로그로 잡혔지만, 마지막은 문서도 선례도 없어서 시뮬레이터 스크린샷 루프 + 진단 emitter 매트릭스라는 물리적인 소거법으로만 잡을 수 있었다.

조용히 실패하는 API를 디버깅할 때는 "왜 안 되지"를 오래 고민하는 것보다 재현 루프를 90초로 줄이는 데 먼저 투자하는 게 결과적으로 빨랐다. 재현이 싸지면 가설 하나 기각하는 비용도 싸진다.

관련 글: [XcodeGen이 Info.plist 버전을 덮어쓰는 문제](/posts/xcodegen-infoplist-version-overwrite-fix/)
