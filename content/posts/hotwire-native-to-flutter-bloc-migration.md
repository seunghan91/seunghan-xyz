---
title: "Hotwire Native에서 Flutter BLoC으로 — 네이티브 앱 전환 실전기"
date: 2026-03-31
draft: false
tags: ["flutter", "bloc", "hotwire-native", "rails", "clean-architecture"]
description: "Hotwire Native iOS 앱이 심사에서 반복 반려되어 Flutter BLoC으로 전환한 실전 기록. Clean Architecture 설계, Rails API 구축, Firebase 시뮬레이터 행 이슈 해결까지."
---

Rails 웹앱에 Hotwire Native로 iOS 앱을 감싸서 출시했는데, 접속 오류로 심사가 반복 반려됐다. WebView 기반의 한계를 느끼고 Flutter + BLoC 패턴으로 순수 네이티브 전환을 결정했다.

이 글은 실제로 웹앱을 Flutter 앱으로 전환하면서 겪은 설계, 삽질, 해결 과정을 정리한 것이다.

---

## Hotwire Native가 안 된 이유

Hotwire Native는 WKWebView 위에 얇은 네이티브 셸을 씌우는 구조다. Turbo Navigator가 URL 기반으로 네비게이션을 처리하고, Bridge Component로 네이티브 UI를 부분적으로 제어한다. 웹 개발자 입장에서는 최소 비용으로 앱을 만들 수 있어서 매력적이다.

문제는 App Store 심사였다. 앱이 서버에 완전히 의존하기 때문에, Render 서버가 cold start로 느려지면 사용자에게 흰 화면이나 접속 오류가 뜬다. 심사 담당자가 보기엔 "앱이 동작하지 않음"이다. 15초 타임아웃도 넣고, 로딩 스피너도 추가했지만 근본적으로 WebView가 서버 응답을 기다리는 구조를 벗어날 수 없었다.

반려 사유는 매번 같았다:

> We were unable to review your app as it crashed on launch.

cold start 문제를 해결하려면 서버를 상시 가동하거나, 앱 자체를 네이티브로 만들어야 했다. 비용 대비 효과를 따져보면 Flutter 전환이 맞았다.

---

## 왜 Flutter + BLoC인가

크로스 플랫폼 선택지를 비교했다:

| 프레임워크 | 장점 | 단점 | 선택 이유 |
|-----------|------|------|----------|
| React Native | 웹 개발자 친화적, 큰 커뮤니티 | 브릿지 오버헤드, 네이티브 모듈 관리 복잡 | - |
| Flutter | 고성능 렌더링, 단일 코드베이스, BLoC 생태계 성숙 | Dart 학습 필요 | **채택** |
| SwiftUI (네이티브) | 최고 성능, 애플 생태계 최적 | iOS 전용, Android 별도 개발 | - |
| Kotlin Multiplatform | 로직 공유 가능 | UI 레이어 별도 | - |

Flutter를 택한 결정적 이유는 기존에 운영하던 다른 프로젝트가 이미 Flutter + BLoC을 쓰고 있어서 아키텍처 패턴을 그대로 가져올 수 있었기 때문이다. 2026년 기준 Flutter는 iOS 신규 무료 앱의 약 30%를 차지하고, Impeller 렌더러가 기본 탑재되면서 성능 문제도 사실상 해소됐다.

상태 관리는 BLoC(Business Logic Component) 패턴을 선택했다. 복잡한 이벤트 흐름(인증, 채팅 WebSocket)에는 Event → BLoC → State 구조가 적합하고, 단순한 상태(대시보드 로딩, 필터 변경)에는 Cubit으로 간결하게 처리할 수 있다.

---

## Clean Architecture 설계

디렉토리 구조는 3레이어 Clean Architecture를 따랐다:

```
lib/
├── core/                 # 공통 인프라
│   ├── config/           #   환경설정 (API URL)
│   ├── design_system/    #   디자인 토큰 + 컴포넌트
│   ├── errors/           #   예외 계층
│   └── services/         #   푸시알림 등
├── data/                 # 데이터 레이어
│   ├── datasources/
│   │   ├── local/        #   SecureStorage
│   │   └── remote/       #   DioClient, WebSocket
│   ├── models/           #   DTO
│   └── repositories/     #   Repository 구현체
├── domain/               # 도메인 레이어
│   ├── entities/         #   순수 도메인 모델
│   └── repositories/     #   Repository 인터페이스
└── presentation/         # UI 레이어
    ├── blocs/            #   BLoC/Cubit
    ├── router/           #   GoRouter
    ├── screens/          #   화면
    └── widgets/          #   재사용 위젯
```

핵심 원칙은 **의존성 방향이 항상 안쪽(domain)으로 흐른다**는 것이다. Presentation은 Domain을 알고, Data는 Domain의 인터페이스를 구현하지만, Domain은 외부를 모른다. 이렇게 해두면 나중에 API 서버를 바꾸거나 로컬 DB를 추가해도 Domain과 UI는 건드릴 필요가 없다.

---

## Rails API 레이어 구축

기존 웹앱은 세션 쿠키 기반 인증에 HTML 응답이었다. Flutter에서 쓰려면 JSON API가 필요했다. Rails에 `/api/v1/` 네임스페이스를 추가하고 JWT 인증을 구현했다.

### JWT 인증 (외부 gem 없이)

```ruby
# app/services/api/v1/json_web_token.rb
module Api
  module V1
    class JsonWebToken
      ALGORITHM = 'HS256'
      ACCESS_TTL = 15.minutes
      REFRESH_TTL = 30.days

      def self.encode(payload, ttl = ACCESS_TTL)
        payload[:exp] = ttl.from_now.to_i
        header = Base64.urlsafe_encode64({ alg: ALGORITHM, typ: 'JWT' }.to_json)
        body = Base64.urlsafe_encode64(payload.to_json)
        signature = sign("#{header}.#{body}")
        "#{header}.#{body}.#{signature}"
      end
    end
  end
end
```

`jwt` gem을 쓸 수도 있었지만, 의존성을 최소화하고 싶어서 OpenSSL HMAC으로 직접 구현했다. access token은 15분, refresh token은 30일로 설정했다.

### Base Controller 패턴

```ruby
# app/controllers/api/v1/base_controller.rb
class Api::V1::BaseController < ActionController::Base
  before_action :authenticate_api_user!
  
  private
  
  def authenticate_api_user!
    token = request.headers['Authorization']&.split(' ')&.last
    payload = Api::V1::JsonWebToken.decode(token)
    @current_api_session = Session.find(payload[:session_id])
    @current_api_user = @current_api_session.user
  rescue
    render json: { error: { message: '인증이 필요합니다' } }, status: :unauthorized
  end
end
```

기존 컨트롤러의 서비스 로직을 재사용하면서 JSON 시리얼라이즈만 추가하는 방식으로, 총 18개 API 컨트롤러를 하루 만에 만들 수 있었다.

---

## Flutter DioClient 인터셉터 체인

API 호출은 Dio + 4단 인터셉터 체인으로 구성했다:

```dart
// 인터셉터 순서가 중요하다
dio.interceptors.addAll([
  _authInterceptor(),         // 1. Bearer 토큰 자동 첨부
  _tokenRefreshInterceptor(), // 2. 401 시 토큰 갱신 + 원래 요청 재시도
  _errorInterceptor(),        // 3. DioException → AppException 변환
  if (kDebugMode) PrettyDioLogger(), // 4. 개발 시 로그
]);
```

특히 `_tokenRefreshInterceptor`가 중요하다. 401이 오면 refresh token으로 새 access token을 발급받고, 실패했던 원래 요청을 자동으로 재시도한다. 사용자는 토큰 만료를 전혀 인지하지 못한다.

```dart
InterceptorsWrapper _tokenRefreshInterceptor() {
  bool isRefreshing = false;
  return InterceptorsWrapper(
    onError: (error, handler) async {
      if (error.response?.statusCode != 401 || isRefreshing) {
        return handler.next(error);
      }
      isRefreshing = true;
      try {
        final newToken = await _refreshToken();
        // 원래 요청을 새 토큰으로 재시도
        final retryResponse = await dio.fetch(
          error.requestOptions..headers['Authorization'] = 'Bearer $newToken',
        );
        handler.resolve(retryResponse);
      } catch (_) {
        handler.next(error);
      } finally {
        isRefreshing = false;
      }
    },
  );
}
```

`isRefreshing` 가드가 없으면 동시에 여러 요청이 401을 받았을 때 refresh가 중복 실행되는 문제가 생긴다.

---

## Firebase 초기화에서 시뮬레이터 행 이슈

가장 크게 삽질한 부분이다. Firebase + FCM을 붙인 후 iOS 시뮬레이터에서 앱이 영원히 빈 화면이었다.

### 원인 분석

```dart
// 이 코드가 시뮬레이터에서 무한 대기한다
await pushNotificationService.initialize();
// ↑ 내부에서 FirebaseMessaging.instance.requestPermission()을 호출하는데,
//   시뮬레이터에는 APNs가 없어서 응답이 안 온다
```

Firebase 공식 문서에 이렇게 적혀있다:

> FCM via APNs does not work on iOS Simulators. To receive messages & notifications a real device is required.

문제는 `requestPermission()`이 에러를 던지는 게 아니라 **영원히 완료되지 않는다**는 것이다. `await`를 걸어두면 `runApp()`에 도달하지 못해서 빈 화면이 된다.

### 해결: await를 제거하고 fire-and-forget

```dart
// Before (행 걸림)
await pushNotificationService.initialize();
runApp(...);

// After (non-blocking)
pushNotificationService.initialize().catchError((e) {
  debugPrint('Push init failed: $e');
});
runApp(...); // 즉시 실행됨
```

push 초기화를 `await` 없이 실행하고, 에러는 `catchError`로 조용히 잡는다. 실기기에서는 정상 동작하고, 시뮬레이터에서도 앱이 즉시 뜬다. 인증 완료 후 토큰 등록은 BLoC 리스너에서 처리한다:

```dart
BlocListener<AuthBloc, AuthState>(
  listener: (context, state) {
    if (state is AuthAuthenticated) {
      pushNotificationService.registerWithServer();
    }
    if (state is AuthUnauthenticated) {
      pushNotificationService.unregisterFromServer();
    }
  },
)
```

---

## 디자인 시스템: 웹 → Flutter 1:1 매핑

웹에서 쓰던 `tokens.css`의 디자인 토큰을 Flutter로 그대로 가져왔다:

```dart
class GwColors {
  static const primary500 = Color(0xFFFF6B2C);  // --color-primary-500
  static const surfacePrimary = Color(0xFFFFFFFF);
  static const surfaceSecondary = Color(0xFFFAFAF9);
  static const textPrimary = Color(0xFF1C1917);
  static const textSecondary = Color(0xFF78716C);
  static const borderDefault = Color(0xFFE7E5E4);
  // ... 50+ 토큰
}
```

| CSS 토큰 | Flutter 토큰 | 값 |
|----------|------------|-----|
| `--color-primary-500` | `GwColors.primary500` | `#FF6B2C` |
| `--spacing-2` | `GwSpacing.base` | `16.0` |
| `--radius-md` | `GwRadius.md` | `12.0` |
| `--shadow-xs` | `GwShadows.xs` | `blur: 3, opacity: 4%` |
| `--glass-bg` | `GwColors.liquidGlassBg` | `white 70%` |

이렇게 하면 웹과 앱의 디자인이 자동으로 일치한다. 디자이너가 웹 토큰을 바꾸면 Flutter 토큰만 같이 바꾸면 된다.

추가로 iOS 26 디자인 시스템의 Liquid Glass 재질 색상도 참조용으로 가져왔다. 사이드바의 반투명 카드나 글래스모피즘 효과에 활용했다:

```dart
// 사이드바 유저 카드 — Liquid Glass 스타일
ClipRRect(
  borderRadius: GwRadius.lgAll,
  child: BackdropFilter(
    filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
    child: Container(
      decoration: BoxDecoration(
        color: Colors.white.withAlpha(18),  // 7% white
        border: Border.all(color: Colors.white.withAlpha(31)),
      ),
      child: // 유저 프로필 정보
    ),
  ),
)
```

---

## BLoC vs Cubit 판단 기준

모든 걸 BLoC으로 만들 필요는 없다. 기준을 정해뒀다:

| 상황 | 패턴 | 예시 |
|------|------|------|
| 복잡한 이벤트 흐름, WebSocket 연동 | **BLoC** | AuthBloc, ChatDetailBloc |
| 단순 API 호출 + 상태 갱신 | **Cubit** | DashboardCubit, AssignmentListCubit |

AuthBloc은 5종의 이벤트(AppStarted, LoginRequested, LogoutRequested, TokenRefresh, PasswordChange)를 처리하고, JWT 만료 전 자동 갱신 타이머까지 관리한다. ChatDetailBloc은 REST 메시지 로딩과 WebSocket 실시간 수신을 통합한다.

반면 DashboardCubit은 `loadDashboard()` 하나면 충분하다:

```dart
class DashboardCubit extends Cubit<DashboardState> {
  Future<void> loadDashboard() async {
    emit(state.copyWith(status: LoadStatus.loading));
    try {
      final data = await _repo.getDashboard();
      emit(state.copyWith(data: data, status: LoadStatus.success));
    } catch (e) {
      emit(state.copyWith(status: LoadStatus.failure));
    }
  }
}
```

이벤트 클래스를 별도로 만들 필요 없이 메서드 호출로 끝난다.

---

## 전역 vs 로컬 BLoC 제공 전략

모든 BLoC을 `MultiBlocProvider`에 넣으면 앱 시작 시 전부 초기화된다. 불필요한 메모리 사용이다.

```dart
// 전역: 앱 전체에서 항상 필요한 것만
MultiBlocProvider(
  providers: [
    BlocProvider(create: (_) => AuthBloc(...)..add(AuthAppStarted())),
    BlocProvider(create: (_) => NotificationCubit(...)),
  ],
  child: MaterialApp.router(...),
)

// 로컬: 화면 진입 시 생성, 이탈 시 자동 해제
GoRoute(
  path: '/chats/:id',
  builder: (context, state) => BlocProvider(
    create: (_) => ChatDetailBloc(...)..add(ChatLoadRequested(channelId)),
    child: ChatDetailScreen(),
  ),
)
```

ChatDetailBloc은 채팅방에 들어갈 때만 생성되고, WebSocket 구독도 그때 시작된다. 화면을 나가면 자동으로 `close()`가 호출되면서 구독이 해제된다.

---

## GoRouter 인증 가드

GoRouter의 `redirect`와 `refreshListenable`을 조합하면 인증 상태에 따른 자동 리다이렉트를 깔끔하게 구현할 수 있다:

```dart
GoRouter(
  initialLocation: '/splash',
  refreshListenable: GoRouterRefreshStream(authBloc.stream),
  redirect: (context, state) {
    final authState = authBloc.state;
    final location = state.matchedLocation;
    
    // 아직 초기화 중 → 스플래시 유지
    if (authState is AuthInitial || authState is AuthLoading) {
      return location == '/splash' ? null : '/splash';
    }
    // 미인증 → 로그인으로
    if (authState is AuthUnauthenticated) {
      return location == '/login' ? null : '/login';
    }
    // 인증됨 + 온보딩 필요 → 온보딩으로
    if (authState is AuthAuthenticated && authState.needsOnboarding) {
      return location == '/onboarding' ? null : '/onboarding';
    }
    // 인증 완료인데 스플래시/로그인에 있으면 → 대시보드로
    if (authState is AuthAuthenticated && 
        (location == '/splash' || location == '/login')) {
      return '/dashboard';
    }
    return null; // 리다이렉트 불필요
  },
)
```

`GoRouterRefreshStream`은 AuthBloc의 상태 변화를 `ChangeNotifier`로 변환해서, 상태가 바뀔 때마다 라우터가 `redirect`를 재평가한다.

---

## ActionCable WebSocket 연동

채팅 실시간 기능은 Rails의 ActionCable을 Flutter에서 직접 연결했다:

```dart
class ChatWebSocketService {
  Future<void> connect() async {
    final token = await _storage.getAccessToken();
    _channel = WebSocketChannel.connect(
      Uri.parse('wss://server.com/cable?token=$token'),
    );
  }

  Stream<ChatMessageDto> subscribeToChat(int channelId) {
    _channel?.sink.add(jsonEncode({
      'command': 'subscribe',
      'identifier': jsonEncode({
        'channel': 'ChatChannel',
        'chat_channel_id': channelId,
      }),
    }));
    // ActionCable 프로토콜: ping 메시지 필터링
    return _channel!.stream
      .map((data) => jsonDecode(data))
      .where((json) => json['type'] == null) // ping/confirm 제외
      .map((json) => ChatMessageDto.fromJson(json['message']));
  }
}
```

ActionCable은 WebSocket 위에 자체 프로토콜을 쓴다. `subscribe` 커맨드로 채널에 가입하고, 서버에서 오는 메시지 중 `type`이 null인 것만 실제 데이터다. `type: 'ping'`이나 `type: 'confirm_subscription'`은 무시해야 한다.

---

## 마크다운 렌더링 적용

과제 설명이나 커뮤니티 게시글에 `**굵게**`, `## 제목` 같은 마크다운 문법이 들어오는데, 처음에는 `Text()` 위젯으로 그대로 표시해서 마크다운 태그가 날것으로 보였다.

`flutter_markdown` 패키지로 교체했다:

```dart
MarkdownBody(
  data: content ?? '',
  selectable: true,
  onTapLink: (text, href, title) {
    if (href != null) launchUrl(Uri.parse(href));
  },
  styleSheet: MarkdownStyleSheet(
    p: TextStyle(fontSize: 14, height: 1.6, color: GwColors.textPrimary),
    strong: TextStyle(fontWeight: FontWeight.w600),
    code: TextStyle(backgroundColor: GwColors.surfaceTertiary),
  ),
)
```

목록 화면의 미리보기(150자 truncate)에서도 마크다운이 렌더링되도록 적용했다. 잘린 마크다운이 불완전할 수 있지만, `**굵게**` 같은 기본 서식은 문제없이 표시된다.

---

## 전환 결과

| 항목 | Before (Hotwire Native) | After (Flutter) |
|------|------------------------|-----------------|
| 앱 구조 | WebView (서버 의존) | 네이티브 렌더링 |
| 오프라인 | 완전 불가 | 캐시 가능 |
| 앱 시작 속도 | 서버 cold start 대기 (5~15초) | 즉시 (~1초) |
| 인증 | 세션 쿠키 | JWT + SecureStorage |
| 실시간 통신 | Turbo Stream (HTML) | WebSocket (JSON) |
| 빌드 타겟 | iOS만 | iOS + Android |
| 화면 수 | 웹 그대로 | 26개 네이티브 화면 |
| API 엔드포인트 | 0개 (HTML만) | 46개 JSON API |

Hotwire Native 접근법이 나쁜 건 아니다. 서버가 빠르게 응답하고, 앱 심사에서 접속 문제가 없다면 여전히 유효한 선택이다. 다만 서버 상태에 앱의 운명이 걸리는 구조는 프로덕션에서 리스크가 크다.

---

## 정리

웹앱을 Flutter로 전환하면서 배운 핵심:

1. **API 먼저** — Flutter UI 작업과 Rails API 작업을 병렬로 진행할 수 있다. API가 없어도 Mock 데이터로 UI를 먼저 만든다.
2. **Firebase 초기화는 non-blocking으로** — `await`를 걸면 시뮬레이터에서 앱이 안 뜬다. fire-and-forget 패턴으로 처리하고, 실제 토큰 등록은 인증 후에.
3. **디자인 토큰 1:1 매핑** — CSS 변수를 Dart 상수로 옮기면 웹-앱 디자인 일치가 자동으로 보장된다.
4. **BLoC은 필요한 곳에만** — 단순한 화면은 Cubit이 훨씬 가볍다. 이벤트 클래스를 만드는 오버헤드가 없다.
5. **Clean Architecture의 진가는 전환할 때** — Repository 인터페이스 덕분에 REST API든 WebSocket이든 교체가 쉽다.
