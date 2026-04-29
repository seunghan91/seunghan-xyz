---
title: "Android Clean Arch + MVI 7-phase 리팩토링하면서 깨진 8가지 — iOS 스택과 다른 Android만의 함정들"
date: 2026-05-02T09:00:00+09:00
draft: false
tags: ["android", "clean-architecture", "mvi", "kotlin", "hilt"]
description: "iOS는 SwiftUI+TCA로 거의 마쳤고 Android를 single-module에서 multi-module Clean Arch+MVI로 옮기면서 7개 phase 동안 만난 실제 함정 8가지. KDoc nesting, viewModelScope leak, App Link host, Retrofit converter까지."
---

iOS 네이티브 앱은 SwiftUI + TCA(The Composable Architecture)로 거의 끝나가는 상태였다. Android는 single-module Compose 스캐폴드만 있는 상태에서 같은 수준의 production 품질로 끌어올리는 작업을 시작했다. iOS와 동일한 멘탈 모델 — Clean Architecture + 단방향 데이터 흐름 + DI — 을 Android idiom으로 번역하는 게 목표였다.

7개 phase로 끊어서 진행하면서 매 phase 마다 코드 리뷰를 돌렸는데, **거의 모든 phase 에서 진짜 production 버그가 잡혔다**. 운영 중인 앱이었으면 사용자가 실제로 깨졌을 것들이다. 이 글은 그 8가지를 정리한다. 같은 마이그레이션 하는 사람이 같은 함정 안 밟게.

## 1. Kotlin 블록 코멘트는 nest 된다 — `/api/v1/*` 가 KDoc 을 깨먹는다

가장 황당했던 건 첫번째 함정이었다. 모듈 split 후 :app 컴파일을 처음 돌렸는데:

```
e: SessionStore.kt:14:9 Unresolved reference 'FILE_NAME'
e: SessionStore.kt:36:78 Syntax error: Missing '}'.
e: SessionStore.kt:68:1 Syntax error: Unclosed comment.
```

근데 SessionStore.kt 는 67줄짜리 멀쩡한 파일이었다. `companion object` 안에 `private const val FILE_NAME = "..."` 가 있었고 module split 전에는 동작했었다. "Unclosed comment" 는 line 68 — 파일 EOF 를 1줄 넘긴 곳을 가리키고 있었다.

원인을 찾아보니 KDoc 안에 이런 줄이 있었다:

```kotlin
/**
 * Personal API Key issued by POST /api/v1/devices. Used as the Bearer
 * for /api/v1/* endpoints (Api::V1::BaseController#authenticate_pak!).
 */
var pakToken: String? = ...
```

`v1/*` 의 `/*` 가 lexer 를 nested block comment 로 진입시킨 거다. **Java 와 다르게 Kotlin 블록 코멘트는 중첩**된다. [공식 문서에 명시](https://kotlinlang.org/docs/basic-syntax.html#comments)되어 있다:

> Block comments in Kotlin can be nested:
>
> ```
> /* The comment starts here
> /* contains a nested comment */
> and ends here.
> */
> ```

그래서 KDoc 안 `/api/v1/*` 가 nested comment 를 열고, 그 다음 `*/` 가 nested 만 닫고, 외곽 KDoc 은 영원히 unclosed 상태로 EOF 까지 swallow 된 거다. 그 결과 `FILE_NAME` 같이 그 아래 정의된 모든 식별자가 "comment 안의 텍스트" 로 인식되어 unresolved.

스캐폴드가 **첫 commit 부터 단 한번도 컴파일된 적 없었다**. Module split 이전에는 개발자가 `:app:compileDebugKotlin` 을 안 돌리고 IDE 만 보고 있었던 거다. IDE 는 partial compile 라 운 좋게 표시 안 됐을 수도 있다.

수정은 단순했다. KDoc 텍스트의 `/api/v1/*` 를 `/api/v1/` 로 바꿨다. 하지만 lesson 은 큰 거였다:

- **Java 출신 개발자가 Kotlin 으로 넘어올 때 가장 자주 헷갈리는 부분 중 하나**가 이 nesting 차이다
- KDoc 안에 와일드카드 `/*` 패턴 (URL 경로, regex, glob 등) 을 적을 때 무조건 escape 하거나 백틱 처리
- CI 에서 `compileDebugKotlin` 이 매 commit 마다 돌아야 한다. 스캐폴드도 예외 없음.

## 2. CustomTabsIntent 은 Activity context 가 필요하다

OAuth 흐름을 service-locator 패턴으로 정리하면서, `Application.onCreate()` 에서 `OAuthFlow` 를 미리 인스턴스화하고 그걸 모든 화면이 공유하게 만들었다. 코드가 깔끔해 보였는데 코드 리뷰에서 즉시 잡혔다:

> When the user taps "Continue with OAuth", this OAuthFlow now launches the Custom Tab with the Application context captured here. CustomTabsIntent.launchUrl ultimately calls startActivity, and using an application context without FLAG_ACTIVITY_NEW_TASK will throw AndroidRuntimeException.

진짜 운영에서 깨졌을 버그다. `startActivity()` 를 Application context 로 호출하면 Android 는 어느 task 에 활동을 붙일지 모르므로 `AndroidRuntimeException` 던진다. iOS 의 `ASWebAuthenticationSession` 은 Window 무관하게 동작해서 같은 함정이 없지만, Android 는 다르다.

수정은 context 를 생성자가 아니라 메서드 호출 시점에 받게 바꿨다:

```kotlin
class OAuthFlow(
    private val sessionStore: SessionStore,
    private val issuer: String,
    private val clientId: String,
) {
    // context 는 Composable의 LocalContext.current 에서 click 시점에 받는다
    fun start(context: Context) {
        // ... CustomTabsIntent.launchUrl(context, authorizeUri)
    }
}
```

Composable 에서:

```kotlin
val context = LocalContext.current  // 실제로는 Activity 인스턴스
TextButton(onClick = { app.oauthFlow.start(context) }) { Text("OAuth") }
```

LocalContext.current 가 일반적으로 Activity 를 반환하므로 자연스럽게 Activity context 가 흘러간다. 새 인스턴스를 매번 만들 필요도 없고, 설정값(issuer, clientId) 은 startup 에 한 번만 잡힌다.

## 3. viewModelScope 는 Activity 보다 오래 산다 — CredentialManager 가 stale Activity 호출

ViewModel 에 MVI 패턴으로 옮기면서, passkey 등록 흐름을 `viewModelScope.launch { ... }` 안에 통째로 넣었다. 1) 서버에서 옵션 받기 → 2) `CredentialManager.createCredential()` 로 사용자 prompt → 3) 결과 서버에 전송. 깔끔해 보였다. 또 잡혔다:

> When the user taps register and the screen is removed or the activity is recreated while the network call is still in flight, this viewModelScope coroutine survives and later calls passkey.register(context, ...) with the stale Activity context captured from the click.

이게 진짜 미묘하다. `viewModelScope` 는 ViewModel 의 lifecycle 에 묶여 있고, ViewModel 은 configuration change (rotate 등) 를 견디려고 Activity 보다 오래 산다. 그러면 1) 사용자가 버튼 클릭 → 2) 네트워크 요청 진행 중에 회면 회전 → 3) 옛 Activity destroy, 새 Activity 생성 → 4) 옛 viewModelScope 의 코루틴이 살아남아서 옛 Activity context 로 `CredentialManager` UI 를 띄우려 함 → crash.

[Google 의 공식 codelab](https://codelabs.developers.google.com/credential-manager-api-for-android) 에도 명시되어 있다:

> Credential manager objects require an Activity to be passed in, which is associated with a Screen. However, Credential manager operations are usually triggered in View Models, and it's not recommended to reference Activities within View Models.

해결 패턴은 **VM 에서 UI 트리거를 분리**하는 것이다:

```kotlin
// VM
fun onEvent(event: PasskeyEvent.RegisterClicked) {
    viewModelScope.launch {
        val options = api.registrationOptions()  // 네트워크는 VM scope OK
        _effects.send(Effect.PromptCredentialManager(options.json))  // UI 작업은 위임
    }
}

fun onCredentialCreated(json: String) { /* 결과 받아서 서버에 POST */ }

// Composable
val composableScope = rememberCoroutineScope()  // 화면과 함께 죽음
LaunchedEffect(Unit) {
    viewModel.effects.collect { effect ->
        when (effect) {
            is Effect.PromptCredentialManager -> composableScope.launch {
                runCatching {
                    PasskeyManager(context).register(context, effect.json)
                }.onSuccess { viewModel.onCredentialCreated(it.responseJson) }
                 .onFailure { viewModel.onCredentialError(it.message) }
            }
        }
    }
}
```

네트워크 호출은 viewModelScope (config change 견딤), UI prompt 는 rememberCoroutineScope (화면과 함께 cancel). Google 가이드와 정확히 일치한다.

iOS TCA 에서는 `Effect.run { ... }` 가 Reducer 의 lifecycle 에 묶이지 않고 `Action` 으로 결과를 다시 던지는 단방향이라 같은 문제가 생기기 어렵다. Android 에서는 ViewModel scope vs UI scope 를 명시적으로 구분해야 한다.

## 4. ViewModel state 가 sign-in 사이클에 누적된다 — privacy 회귀

또 다른 미묘한 함정. SignIn 화면을 `remember { mutableStateOf("") }` 에서 ViewModel 의 `StateFlow<UiState>` 로 옮겼다. 코드 리뷰가 또 잡았다:

> Because viewModel() is scoped to the Activity here, this SignInViewModel survives after onAuthenticated() removes SignInScreen from composition. If the user signs in and later signs out from HomeScreen, returning to this screen reuses the same uiState, so the previous email/password remain populated and can be submitted again.

`remember` 는 Composable 이 composition 에서 빠지면 같이 사라진다. 하지만 ViewModel 은 Activity 가 살아있는 한 유지된다. 그래서 사용자가 로그인 → 사용 → 로그아웃 → 다시 로그인 화면 → 이메일/비번이 그대로 보인다. 다른 사람이 폰 빌려 쓴다면 직전 사용자의 자격증명이 노출된다.

수정은 한 줄이었다:

```kotlin
}.onSuccess { res ->
    sessionStore.accessToken = res.accessToken
    // 인증 성공 직후 state 초기화 — 재진입 시 잔존 방지
    _uiState.value = SignInUiState()
    _effects.send(SignInEffect.Authenticated)
}
```

ViewModel 패턴에 익숙한 개발자도 Composable 의 `remember` semantics 를 무의식적으로 가정하면 이런 회귀가 생긴다. **State 의 lifetime 을 명시적으로 설계해야 한다**:

| 위치 | Lifetime | 적합한 데이터 |
|---|---|---|
| `remember` | Composition | 임시 UI 상태, 토글 등 |
| `rememberSaveable` | Process death 까지 | 폼 입력 (재시작 시 복원) |
| `ViewModel + StateFlow` | Activity (config change 견딤) | 비즈니스 상태, 진행 중인 요청 |
| `SavedStateHandle` | Activity death | 프로세스 재시작 시 복원할 ID 등 |
| `DataStore / Room` | App 라이프타임 | 설정, 캐시 |

자격증명 같은 민감 입력은 ViewModel 에 두면 명시적으로 clear 해야 한다.

## 5. App Link host 는 API host 와 매칭해야 한다 — apex 가 아니다

마케팅 도메인 (`example.com`) 과 API 도메인 (`api.example.com`) 을 분리한 셋업에서, AndroidManifest 의 App Link `<intent-filter>` host 를 그냥 apex 로 박았다. 이런 식:

```kotlin
manifestPlaceholders["appLinkHost"] = "example.com"
buildConfigField("String", "APP_LINK_HOST", "\"example.com\"")
```

코드 리뷰가 잡았다:

> When production OAuth login links are https://api.example.com/oauth/authorize?..., this placeholder makes the manifest claim only https://example.com/..., so Android will not route those authorize/callback links to the app.

App Link 는 정확한 host 매칭이다. RP (Relying Party) 들이 `api.example.com/oauth/authorize` 로 callback 보내면 Android 는 `https://example.com/*` 만 claim 하는 앱에 라우팅 안 한다. AASA 파일 (`/.well-known/apple-app-site-association`) 과 Android assetlinks (`/.well-known/assetlinks.json`) 도 결국 그 호스트 (`api.example.com`) 에서 서빙되고 있어서 일관성도 깨진다.

수정은 단순한 문자열 치환이었지만, 이 함정은 **iOS 와 Android 둘 다 같은 패턴**이라는 점이 중요하다:

- iOS Universal Link 에서도 `applinks:api.example.com` 가 entitlement 에 들어가야 한다
- Android assetlinks 도 마찬가지로 `api.example.com` 에 호스팅
- "마케팅 도메인" 과 "OAuth callback 도메인" 을 의도적으로 분리하면, 양쪽 OS 의 deep link 시스템도 후자에 맞춰야 한다

## 6. Retrofit kotlinx-serialization converter Maven coordinates 가 바뀌었다

Module split 후 `import retrofit2.converter.kotlinx.serialization.asConverterFactory` 가 unresolved 로 떴다. 의존성은 명시되어 있었는데 `asConverterFactory` 확장 함수가 없다는 거였다.

조사해 보니 이 라이브러리는 Square 가 직접 흡수했다:

| 시점 | 좌표 | 비고 |
|---|---|---|
| 과거 | `com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter:1.0.0` | Jake Wharton 개인 라이브러리 |
| Retrofit 2.11.0+ | `com.squareup.retrofit2:converter-kotlinx-serialization:2.11.0` | Square 공식 흡수 |

JakeWharton 의 1.0.0 은 더 이상 업데이트 안 되고, `Json.asConverterFactory(MediaType)` 확장 함수가 거기엔 빠져있었다. Square 버전으로 옮기자 즉시 해결.

이런 라이브러리 마이그레이션은 공식 발표가 조용히 지나가는 경우가 많다. `libs.versions.toml` 의 알 수 없는 버전을 발견하면 "이 좌표가 아직 active 한가" 부터 확인하는 습관이 필요하다.

## 7. 모듈 split — 직관 vs 정답

Clean Architecture 모듈 분리에서 가장 헷갈렸던 건 **`:core:network` 에 무엇이 들어가야 하는가** 였다. 처음엔 직관적으로 모든 네트워크 관련 코드를 다 넣었다:

- DTOs (`@Serializable` data class)
- Retrofit 인터페이스 (`AuthApi`, `OAuthApi`)
- `ApiClient` (OkHttpClient + 인증 인터셉터)

근데 `ApiClient` 가 `SessionStore` (encrypted prefs 래퍼) 에 의존했다. `SessionStore` 는 어느 모듈에 둬야 하나? 만약 `:core:network` 에 두면 stateless 와 stateful 이 섞이고, 만약 `:core:data` 에 두면 `:core:network → :core:data` 의존이 생긴다 (역방향, Clean Arch 위반).

해답은 **모듈 분리를 stateful/stateless 로 자르는 것**:

```
:core:network    — 100% stateless
                   - DTOs (@Serializable)
                   - Retrofit interfaces
                   - 다른 모듈 의존성 0

:core:data       — stateful 인프라
                   - SessionStore (EncryptedSharedPreferences)
                   - ApiClient (interceptor + Retrofit 빌드)
                   - DeviceBootstrap (PAK 발급/갱신)
                   - OAuthFlow (Custom Tabs 런처)
                   - Hilt @Module 도 여기에
                   - 의존: :core:network, :core:domain, :core:auth
```

`:core:network` 가 어느 모듈에도 의존하지 않으니 컴파일 캐시가 가장 잘 보존되고 (서버 응답 스키마 변경 빈도 낮음), `:core:data` 만 Hilt 와 secure storage 같은 무거운 SDK 를 끌어온다. 인터페이스/구현 분리가 자연스럽게 따라온다.

iOS Swift Package 구조와도 1:1 매칭된다:

| iOS Package | Android Module |
|---|---|
| `LogiCore/Networking` (Codable + URLSession protocol) | `:core:network` |
| `LogiCore/Stores` (Keychain wrapper) | `:core:data` (SessionStore) |
| `LogiCore/Auth` (OAuth orchestration) | `:core:data` + `:core:auth` |
| `LogiCore/Design` (theme primitives) | `:core:designsystem` |
| `FeatureAuth` (TCA Reducer) | `:feature:auth` (HiltViewModel + StateFlow) |
| `LogiAuth` (RP-facing public SDK) | `:logi-auth-sdk` (plain Kotlin, no Hilt/Compose) |

플랫폼 idiom 은 다르지만 **레이어 분리는 동일**하게 유지할 수 있다는 게 핵심이었다.

## 8. 코드 리뷰 자동화가 매 phase 마다 진짜 버그를 잡았다

위 8개 함정 중 6개가 **코드 리뷰에서 잡혔다**. 내가 돌리고 있던 건 OpenAI Codex CLI 의 `codex review --commit <sha>` 였는데, 사람보다 빠르고 무료(API 비용만)라서 매 phase commit 직후 한 번씩 돌렸다.

명확한 P1/P2 마킹 + 정확한 file:line + 영향 분석 (왜 production 에서 깨지는지) 까지 줬다. 예시:

> [P2] Use an Activity context to launch OAuth Custom Tabs — LogiApplication.kt:26-28
> When the user taps "Continue with OAuth", this OAuthFlow now launches the Custom Tab with the Application context captured here. CustomTabsIntent.launchUrl ultimately calls startActivity, and using an application context without FLAG_ACTIVITY_NEW_TASK will throw AndroidRuntimeException instead of opening the OAuth page; previously the flow was constructed with the composable's Activity context.

이게 제일 valuable 한 부분이었다. AI 코드 생성보다 AI 코드 리뷰가 ROI 가 훨씬 높다는 걸 7-phase 동안 매번 확인했다. 사람이 PR 리뷰할 때 미묘한 lifetime 이슈 (viewModelScope vs Composable scope, Activity vs Application context) 를 일관되게 잡기는 어렵다. AI 는 안정적으로 잡았다.

## iOS TCA → Android 멘탈 모델 매핑

마지막으로, iOS TCA 에 익숙한 사람이 Android 로 넘어올 때 멘탈 모델 매핑:

| TCA 개념 | Android 등가물 |
|---|---|
| `State` | `data class UiState` (StateFlow 에 wrap) |
| `Action` | `sealed interface Event` |
| `Effect.run { ... }` | `viewModelScope.launch { ... }` |
| `Effect.send(Action)` | `_effects.send(Effect)` (Channel) + UI 가 Event 로 다시 dispatch |
| `Reducer` | ViewModel 의 `onEvent(event)` 분기 |
| `@Dependency` | Hilt `@Inject` |
| `WithViewStore` | `collectAsStateWithLifecycle()` |

핵심 차이는:
- TCA 는 reducer 가 pure function (State → State + Effect). Android 의 ViewModel 은 mutable state 머신
- TCA Effect 는 Reducer scope. Android viewModelScope 는 Activity scope (UI prompt 분리 필요)
- TCA 는 dependency injection 이 protocol-based. Android 는 Hilt (KSP 기반 컴파일타임)

mvikotlin, orbit-mvi 같은 라이브러리도 있지만 결국 같은 primitive 들을 wrapping 한 것뿐이라, **Google 자체 NowInAndroid 샘플 패턴 (StateFlow + Channel + sealed Event/Effect)** 가 가장 무난하고 외부 의존성 없이 production 에 갈 수 있다.

## 결론

7개 phase 를 거치면서:

1. 매 phase 끝마다 컴파일 검증 + 코드 리뷰 (사람 또는 AI)
2. P1/P2 발견 시 별도 commit 으로 즉시 수정
3. 다음 phase 진입은 이전 phase 가 깨끗할 때만

이 cycle 만 지키면 single-module → multi-module Clean Arch 마이그레이션이 안전하다. 8가지 함정 모두 production 에 가기 전에 잡혔고, 사용자가 깨지는 일은 없었다. 같은 작업 하시는 분들이 이 글로 같은 함정 한 번이라도 덜 밟으셨으면 좋겠다.

특히 **KDoc 안의 `/api/v1/*` 같은 와일드카드 텍스트** 는 진짜 안 보이는 함정이라, 검색 유입으로 들어오신 분이 있다면 5분 절약하셨을 거라 생각한다.
