---
title: "Hotwire Native에서 Flutter로 — Rails 앱의 모바일 네이티브 전환 실전기"
date: 2026-03-31
draft: false
tags: ["Flutter", "Rails", "Hotwire Native", "JWT", "모바일"]
categories: ["Hotwire Native", "Flutter"]
description: "Hotwire Native(WebView 래퍼) 앱을 Flutter 풀 네이티브로 마이그레이션한 과정. Rails JSON API 설계, JWT 인증, SSE 스트리밍, Firebase 설정, 프로덕션 배포까지 삽질 기록."
---

Rails 8 + Hotwire로 웹을 만들고, Hotwire Native로 iOS/Android를 감싸면 꽤 그럴듯한 앱이 나온다. WebView가 서버 렌더링 HTML을 그대로 보여주니 코드 한 벌로 3플랫폼을 커버할 수 있다. 실제로 이 방식으로 프로덕션에서 잘 돌아가는 앱을 운영하고 있었다.

그런데 점점 한계가 보이기 시작했다. 오프라인 지원이 안 되고, 네이티브 애니메이션도 못 쓰고, WebView 특유의 뚝뚝 끊기는 느낌이 있었다. 결국 Flutter로 풀 네이티브 전환을 결정했고, 설계부터 프로덕션 배포까지 약 2주 만에 끝냈다. 그 과정을 정리한다.

---

## 기존 구조: Hotwire Native는 어떻게 동작하는가

Hotwire Native(구 Turbo Native)는 기본적으로 **WebView 래퍼**다. 네이티브 쉘이 탭바와 네비게이션만 담당하고, 실제 화면은 전부 서버에서 렌더링한 HTML을 WebView로 보여준다.

```
┌─ Native Shell (Swift/Kotlin) ─┐
│  탭바 (5탭)                    │
│  ┌─ WebView ────────────────┐ │
│  │  서버 렌더링 HTML          │ │
│  │  Turbo Streams로 실시간    │ │
│  └──────────────────────────┘ │
│  Bridge: Haptic, Share, FCM   │
└───────────────────────────────┘
```

네이티브 코드는 놀라울 정도로 적다. iOS는 Swift 파일 11개, Android는 Kotlin 10개. 대부분이 Bridge 컴포넌트(진동, 공유, FCM 토큰 전달)와 탭 설정 코드다.

### Bridge 컴포넌트란

Hotwire Native의 핵심 개념이다. WebView 안의 JavaScript와 네이티브 코드가 메시지를 주고받는 채널이다.

```swift
// iOS Bridge — NotificationTokenComponent.swift
class NotificationTokenComponent: BridgeComponent {
    override class var name: String { "notification-token" }
    
    override func onReceive(message: Message) {
        // 웹에서 "connect" 이벤트 → APNs 토큰 전달
        let token = UserDefaults.standard.string(forKey: "apns_token")
        reply(to: "connect", with: ["token": token, "granted": true])
    }
}
```

이 구조의 장점은 명확하다 — 서버 코드 한 번 수정하면 웹, iOS, Android가 동시에 바뀐다. 하지만 단점도 명확하다.

---

## 왜 Flutter로 전환했나

| 문제 | Hotwire Native | Flutter |
|------|---------------|---------|
| 오프라인 | 불가능 (서버 렌더링 의존) | 로컬 캐싱 가능 |
| 애니메이션 | WebView 안에서만 | 네이티브 60fps |
| 성능 | HTML 파싱 + 렌더링 오버헤드 | 네이티브 위젯 직접 렌더링 |
| UX | 웹 느낌 (탭 전환 시 흰 화면 깜빡임) | 네이티브 전환 |
| 코드베이스 | Swift 11개 + Kotlin 10개 = 2벌 | Dart 1벌 |
| 커스텀 UI | Bridge 추가해야 함 (복잡) | 위젯으로 자유롭게 |

결정적 계기는 AI 채팅 기능이었다. Turbo Streams로 스트리밍 응답을 보여주고 있었는데, WebView 안에서의 실시간 업데이트가 불안정했다. Flutter의 `Stream`과 `setState`가 훨씬 자연스럽다.

---

## 아키텍처 설계: 가장 먼저 결정할 것

### 핵심 원칙: Rails 서버는 건드리지 않는다

기존 웹 앱이 잘 돌아가고 있으므로, HTML 응답을 건드리면 안 된다. **JSON API를 추가**하는 방식으로 간다.

```
Rails 8.1 Server
├── /* HTML 응답 (기존 웹, Hotwire) → 그대로 유지
└── /api/v1/* JSON 응답 (Flutter용) → 신규 추가
```

이렇게 하면 기존 웹 사용자에게 영향 없이 모바일 앱만 전환할 수 있다.

### 인증 전환: 세션 쿠키 → JWT

여기서 첫 번째 큰 결정이 필요했다. 기존 웹은 세션 쿠키(`cookies.signed[:session_token]`) 기반이다. Flutter에서 쿠키를 관리하는 방법도 있지만, 모바일에서 쿠키는 불안정하다.

- 백그라운드/포그라운드 전환 시 쿠키 유실 가능
- CSRF 보호가 모바일에서 제대로 동작하지 않음
- 세션 무효화 범위가 불명확 (웹 로그아웃이 모바일에 영향?)

결국 **JWT**로 갔다. `jwt` gem 하나 추가하면 된다.

```ruby
# Gemfile
gem "jwt"

# app/services/jwt_service.rb
class JwtService
  ALGORITHM = "HS256"

  def self.encode(user)
    payload = {
      sub: user.id,
      email: user.email,
      role: user.role,
      exp: 1.hour.from_now.to_i,
      iat: Time.current.to_i
    }
    JWT.encode(payload, Rails.application.secret_key_base, ALGORITHM)
  end

  def self.decode(token)
    JWT.decode(token, Rails.application.secret_key_base, true, algorithm: ALGORITHM).first
  end
end
```

기존 OTP 로그인 플로우를 그대로 재활용하되, 마지막 단계에서 쿠키 대신 JWT를 발급한다.

```
[기존 웹]  OTP 검증 → Session 레코드 생성 → 세션 쿠키
[Flutter]  OTP 검증 → Session 레코드 생성 → JWT + refresh_token
                      ↑ 동일한 OTP 로직 공유
```

---

## Rails API 컨트롤러 설계

### BaseController — JWT 인증 공통

```ruby
module Api
  module V1
    class BaseController < ActionController::API
      before_action :authenticate_jwt!

      private

      def authenticate_jwt!
        token = request.headers["Authorization"]&.split(" ")&.last
        return render_unauthorized unless token

        payload = JwtService.decode(token)
        @current_user = User.find(payload["sub"])
      rescue JWT::ExpiredSignature
        render_unauthorized("Token expired")
      rescue JWT::DecodeError, ActiveRecord::RecordNotFound
        render_unauthorized
      end

      def render_unauthorized(msg = "Unauthorized")
        render json: { error: msg }, status: :unauthorized
      end
    end
  end
end
```

`ActionController::API`를 상속받으면 CSRF 보호, 쿠키, 세션 미들웨어가 모두 빠진다. API 전용으로 깔끔하다.

### AuthController — OTP + JWT 발급

가장 많이 삽질한 부분이다. 기존 `EmailVerificationCode` 모델의 메서드명이 API 컨트롤러에서 호출할 때 미묘하게 달랐다.

```ruby
# 잘못된 코드 — 존재하지 않는 메서드
verification = EmailVerificationCode.latest_for(user.email, purpose: "login")
verification.verify!(code)

# 올바른 코드 — 기존 scope 활용
verification = EmailVerificationCode.valid_for(user.email, "login").first
result = verification.verify!(code)
```

이런 실수는 기존 컨트롤러 코드를 제대로 안 읽어서 생긴다. 새 API를 만들 때는 반드시 기존 웹 컨트롤러의 실제 호출 패턴을 확인해야 한다.

---

## Flutter 프로젝트 구조

```
flutter/lib/
├── core/
│   ├── config/     (앱 설정, 테마)
│   ├── network/    (Dio, JWT 인터셉터)
│   ├── services/   (인증, FCM, 딥링크)
│   └── router/     (GoRouter)
├── features/
│   ├── auth/       (로그인, OTP, TOTP)
│   ├── dashboard/  (홈)
│   ├── conversation/ (AI 에이전트)
│   ├── service_request/ (서비스 요청)
│   ├── notification/
│   └── settings/
└── shared/widgets/ (공통 위젯)
```

상태관리는 **Riverpod 2.x**, HTTP는 **Dio**, 라우팅은 **GoRouter**를 선택했다. 이 조합이 2026년 기준으로 가장 안정적이다.

### Dio JWT 인터셉터 — 토큰 자동 갱신

```dart
class AuthInterceptor extends Interceptor {
  final Dio _dio;
  final Ref _ref;
  bool _isRefreshing = false;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    // 공개 엔드포인트는 토큰 생략
    final publicPaths = ['/api/v1/auth/sign_in', '/api/v1/auth/verify_otp'];
    if (publicPaths.contains(options.path)) return handler.next(options);

    final token = await _ref.read(authServiceProvider).getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401 || _isRefreshing) {
      return handler.next(err);
    }

    _isRefreshing = true;
    try {
      // refresh token으로 새 access token 발급
      final refreshToken = await _ref.read(authServiceProvider).getRefreshToken();
      final response = await _dio.post('/api/v1/auth/refresh',
        data: {'refresh_token': refreshToken});

      final newToken = response.data['access_token'];
      await _ref.read(authServiceProvider).saveAccessToken(newToken);

      // 원래 요청 재시도
      final opts = err.requestOptions;
      opts.headers['Authorization'] = 'Bearer $newToken';
      handler.resolve(await _dio.fetch(opts));
    } catch (_) {
      await _ref.read(authServiceProvider).clearTokens();
      handler.next(err);
    } finally {
      _isRefreshing = false;
    }
  }
}
```

이 패턴이 중요한 이유: 사용자가 앱을 1시간 이상 방치해도 refresh token으로 자동 갱신되기 때문에 재로그인 없이 계속 사용할 수 있다.

---

## AI 채팅 SSE 스트리밍 — 가장 복잡한 부분

기존 Hotwire에서는 ActionCable + Turbo Streams로 실시간 AI 응답을 보여줬다. Flutter에서는 **SSE(Server-Sent Events)**로 전환했다.

### Rails 서버 측

```ruby
# app/controllers/api/v1/messages_controller.rb
def create
  conversation = current_user.conversations.find(params[:conversation_id])
  user_message = conversation.messages.create!(
    role: "user", content: params[:content], status: "done"
  )

  if request.headers["Accept"]&.include?("text/event-stream")
    # SSE 스트리밍 응답
    assistant_message = conversation.messages.create!(
      role: "assistant", content: "", status: "streaming"
    )

    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"

    self.response_body = Enumerator.new do |yielder|
      AiService.stream_response(conversation) do |chunk|
        assistant_message.update_columns(
          content: assistant_message.content + chunk
        )
        yielder << "event: chunk\ndata: #{
          { content: chunk, done: false }.to_json
        }\n\n"
      end

      assistant_message.update!(status: "done")
      yielder << "event: done\ndata: #{
        { message_id: assistant_message.id, done: true }.to_json
      }\n\n"
    end
  end
end
```

여기서 삽질 포인트가 있었다. `Message` 모델에 `validates :content, presence: true`가 걸려 있어서, 스트리밍 시작 시 빈 content로 assistant 메시지를 생성할 수 없었다.

```ruby
# 수정 전 — 에러 발생
validates :content, presence: true  # 빈 문자열이면 validation 실패

# 수정 후 — 스트리밍 assistant만 예외 허용
validates :content, presence: true, unless: :streaming_assistant?

def streaming_assistant?
  role == "assistant" && status == "streaming"
end
```

### Flutter 클라이언트 측

```dart
Stream<String> sendMessageStream(int conversationId, String content) async* {
  final response = await _dio.post(
    '/api/v1/conversations/$conversationId/messages',
    data: {'content': content},
    options: Options(
      responseType: ResponseType.stream,
      headers: {'Accept': 'text/event-stream'},
    ),
  );

  final stream = response.data.stream as Stream<List<int>>;
  String buffer = '';

  await for (final chunk in stream) {
    buffer += utf8.decode(chunk);

    while (buffer.contains('\n\n')) {
      final eventEnd = buffer.indexOf('\n\n');
      final eventBlock = buffer.substring(0, eventEnd);
      buffer = buffer.substring(eventEnd + 2);

      for (final line in eventBlock.split('\n')) {
        if (line.startsWith('data: ')) {
          final data = jsonDecode(line.substring(6));
          if (data['done'] == true) return;
          yield data['content'] as String;
        }
      }
    }
  }
}
```

Dio의 `ResponseType.stream`이 핵심이다. 일반적인 `ResponseType.json`이나 `ResponseType.plain`은 전체 응답을 기다리지만, `stream`은 청크 단위로 받을 수 있다.

SSE 프로토콜은 `event: 이벤트명\ndata: JSON\n\n` 형식이라 직접 파싱해야 한다. `flutter_client_sse` 같은 패키지도 있지만, 이 정도는 직접 구현하는 게 의존성이 줄어서 낫다.

---

## Firebase 설정 — 예상 외의 난관

Firebase 설정에서 시간을 많이 뺏겼다. 핵심: **FlutterFire CLI로 `firebase_options.dart`를 생성**해야 한다. `GoogleService-Info.plist`만 복사해서 넣으면 안 된다.

```dart
// lib/firebase_options.dart
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      default:
        throw UnsupportedError('Platform not supported');
    }
  }

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSy...',
    appId: '1:981186249046:ios:...',
    messagingSenderId: '981186249046',
    projectId: 'my-project',
    iosBundleId: 'com.example.app',
  );
  // ...
}
```

그리고 iOS에서 `GoogleService-Info.plist`을 Xcode 프로젝트의 **Copy Bundle Resources**에 등록하지 않으면 런타임에 크래시한다.

```
FirebaseApp.configure() could not find a valid GoogleService-Info.plist
```

이 에러를 만나면 `project.pbxproj`에 파일 참조를 수동으로 추가해야 한다. Xcode GUI에서 Runner 그룹에 드래그앤드롭하는 게 가장 확실하다.

---

## 프로덕션 배포에서 만난 에러

Render에 배포할 때 앱이 시작하자마자 크래시했다.

```
/app/models/user.rb:2: uninitialized constant User::AuditLoggable (NameError)
```

원인: `AuditLoggable` concern 파일이 커밋에 포함되지 않았다. 로컬에서는 잘 동작하지만 프로덕션에서만 터지는 전형적인 패턴이다.

**교훈**: 대규모 마이그레이션 후에는 반드시 `git status`로 미추적 파일을 확인하고, 프로덕션에 필요한 모든 파일이 커밋됐는지 검증해야 한다.

```bash
# 미추적 파일 중 프로덕션 필수 파일 확인
git status --porcelain | grep "^??" | grep -E "model|concern|service|controller"
```

또 하나: `encrypts :totp_secret`을 User 모델에 선언했는데, 프로덕션에 Active Record Encryption 키가 설정되지 않아서 앱 로드 자체가 실패했다. `encrypts` 선언은 키 없이도 마이그레이션은 통과하지만, eager loading 시점에서 터진다.

---

## BizRouter AI 연동 — 모델명 주의

AI 응답 생성에 BizRouter(OpenAI 호환 API 게이트웨이)를 사용하고 있었다. 로컬에서 테스트할 때 404 에러가 났다.

```
Faraday::ResourceNotFound: 404 for POST https://api.bizrouter.ai/v1/chat/completions
```

원인은 모델명이었다. `bizrouter/claude-sonnet-4-6`이 아니라 `anthropic/claude-sonnet-4`가 올바른 모델명이었다. OpenAI 호환 API를 사용할 때는 제공자의 모델 목록을 반드시 확인해야 한다.

```ruby
# 잘못됨
DEFAULT_MODEL = "bizrouter/claude-sonnet-4-6"

# 올바름
DEFAULT_MODEL = "anthropic/claude-sonnet-4"
```

---

## Hotwire Native vs Flutter — 언제 전환해야 하는가

| 상황 | Hotwire Native 유지 | Flutter 전환 |
|------|---------------------|-------------|
| MVP / 프로토타입 | O | X |
| 웹과 100% 동일 UI | O | X |
| 오프라인 필수 | X | O |
| 커스텀 애니메이션 | X | O |
| 실시간 스트리밍 (AI 챗봇) | 가능하지만 불안정 | O |
| iOS + Android 동시 | 2벌 코드 | 1벌 코드 |
| 개발 속도 (초기) | 매우 빠름 | 느림 |
| 장기 유지보수 | 웹 코드와 결합 | 독립적 |

**Hotwire Native이 적합한 경우**: 웹 서비스의 모바일 래퍼가 필요하고, 네이티브 기능을 거의 안 쓰는 경우. 블로그, CMS, 관리자 도구 같은 CRUD 앱.

**Flutter 전환이 필요한 경우**: 실시간 기능(채팅, 스트리밍), 오프라인, 복잡한 인터랙션, 또는 두 플랫폼의 코드를 하나로 합치고 싶을 때.

---

## 마이그레이션 체크리스트

실제로 전환하면서 만든 체크리스트다. 빠뜨리면 프로덕션에서 터지는 것들 위주.

| # | 항목 | 삽질 포인트 |
|---|------|-----------|
| 1 | Bundle ID 동일하게 | 기존 앱 업데이트로 배포하려면 필수 |
| 2 | `firebase_options.dart` 생성 | `GoogleService-Info.plist`만으론 부족 |
| 3 | Xcode Bundle Resources에 plist 등록 | 안 하면 런타임 크래시 |
| 4 | JWT refresh interceptor | 없으면 1시간마다 로그아웃 |
| 5 | SSE 파싱 직접 구현 | Dio `ResponseType.stream` 사용 |
| 6 | Message validation 예외 | 스트리밍 빈 content 허용 필요 |
| 7 | 기존 모델 메서드명 확인 | `generate_for!` vs `generate_for` |
| 8 | `encrypts` 선언은 키 설정 후 | 키 없으면 프로덕션 앱 로드 실패 |
| 9 | 미커밋 파일 확인 | concern, service 파일 누락 주의 |
| 10 | Render env vars PUT 시 전체 포함 | 빠뜨리면 기존 변수 삭제됨 |

---

## 결론

Hotwire Native에서 Flutter로의 전환은 "WebView를 걷어내고 네이티브 UI를 입히는" 작업이다. Rails 서버는 JSON API만 추가하면 되고, 기존 웹은 건드리지 않는다.

가장 중요한 건 **기존 인증 플로우를 재활용**하는 것이다. OTP 검증 로직은 그대로 두고, 마지막 단계에서 쿠키 대신 JWT를 발급하는 식으로 하면 코드 중복 없이 깔끔하게 전환된다.

삽질은 대부분 "환경 설정"에서 발생했다. Firebase plist 등록, Active Record Encryption 키, Render 환경변수 관리. 코드 로직보다 인프라 설정에서 시간을 더 많이 쓴 것 같다.
