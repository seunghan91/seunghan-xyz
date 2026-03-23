---
title: "Flutter SSO 로그인 실패 + Rails 서버 크래시 동시 디버깅 기록"
date: 2025-10-01
draft: true
tags: ["Flutter", "Rails", "TestFlight", "SSO", "Render", "디버깅"]
description: "TestFlight 앱에서 SSO 로그인이 localhost에 연결을 시도하며 실패하고, 동시에 Rails 서버가 uninitialized constant로 크래시되는 문제를 두 개 동시에 잡은 기록."
cover:
  image: "/images/og/flutter-sso-localhost-rails-uninitialized-constant-debug.png"
  alt: "Flutter Sso Localhost Rails Uninitialized Constant Debug"
  hidden: true
categories: ["Rails"]
---

TestFlight에서 소셜 로그인(Apple, Google)이 전부 실패하는 버그를 잡다가 서버도 크래시되고 있다는 걸 같이 발견했다. 각각 원인이 달랐고 둘 다 잡아야 앱이 정상 동작했다. 이 글은 두 버그의 발견 과정, 근본 원인, 수정 방법을 순서대로 기록한다.

---

## 증상

실기기(TestFlight)에서 Apple 로그인, Google 로그인 버튼을 누르면 다음 에러가 표시됐다:

```
Apple 로그인 실패: DioException [connection error]: The connection errored:
Connection refused This indicates an error which most likely cannot be solved
by the library.
Error: SocketException: Connection refused (OS Error: Connection refused, errno = 61),
address = localhost, port = 56837
```

```
Google 로그인 실패: DioException [connection error]: ...
address = localhost, port = 56839
```

두 가지가 이상했다:

1. `localhost`에 연결을 시도하고 있다 — 프로덕션 서버 URL이 아님
2. 포트가 56837, 56839처럼 랜덤 high port다 — baseUrl의 3000포트가 아님

첫 번째가 핵심이었다. TestFlight 빌드가 설치된 실기기에는 로컬 Rails 서버가 없다. 아이폰에서 `localhost`는 개발자의 맥이 아니라 아이폰 자기 자신을 가리킨다. 거기에는 아무 서버도 없으니 연결은 항상 거부될 수밖에 없다.

---

## 원인 1: Flutter API baseUrl 하드코딩

Flutter 코드를 확인했더니 `ApiService`에 이렇게 되어 있었다:

```dart
class ApiService {
  static const String baseUrl = 'http://localhost:3000';

  // ...
}
```

개발 중에 로컬 서버를 바라보도록 짜놓고 프로덕션 URL로 교체하지 않은 채 TestFlight 빌드를 올린 것.

개발 중에는 흔히 생기는 실수다. SSO 기능을 추가하고 로컬 Rails 서버 상대로 시뮬레이터에서 테스트하면 잘 동작한다. 그 상태로 빌드를 올리면 실기기에서는 자기 자신의 localhost에 연결을 시도하다 바로 실패한다.

### 포트 번호가 왜 56837이었냐

`baseUrl`이 `localhost:3000`인데 에러에는 56837이 찍혀서 혼란스러웠다. 실제로는 `api.post('/sso/apple', ...)` 호출이 localhost에 연결을 시도할 때, iOS가 OS 네트워킹 레이어에서 소켓의 출발지 포트(ephemeral source port)를 할당한다. `SocketException` 에러 메시지에 출력되는 것은 목적지 포트(3000)가 아니라 이 출발지 포트(56837)다. 소켓 레벨 에러 정보다.

실용적인 결론: `SocketException`에서 높은 임시 포트가 보이면 포트 번호는 무시하고 주소 필드를 봐야 한다. `localhost`가 찍혀 있다면 그게 버그다.

### 수정: 환경별 설정으로 분리

최소한의 수정은 문자열을 바꾸는 것이다:

```dart
class ApiService {
  static const String baseUrl = 'https://your-production-server.onrender.com';

  // ...
}
```

하지만 프로덕션 URL을 하드코딩하는 것도 결국 똑같은 문제를 다른 방식으로 반복하는 것이다. 올바른 해결은 환경 설정을 코드 밖으로 빼내는 것이다.

#### 방법 A: 빌드 시 `--dart-define` 사용

```bash
# 개발
flutter run --dart-define=API_BASE_URL=http://localhost:3000

# 프로덕션 / TestFlight
flutter build ipa --dart-define=API_BASE_URL=https://your-production-server.onrender.com
```

```dart
class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:3000',
  );
}
```

#### 방법 B: Flavor별 설정 파일 분리

Flutter flavor(`--flavor development`, `--flavor production`)를 `--dart-define-from-file`과 함께 사용하면 환경별 차이를 환경별 JSON 파일 하나로 관리할 수 있다. Dart 코드에는 URL이 직접 들어가지 않는다.

어느 방법을 쓰든 TestFlight나 App Store 빌드가 실수로 localhost를 바라볼 수 없게 된다.

---

## 원인 2: Rails 서버가 시작조차 안 되고 있었음

Flutter URL을 고친다고 끝이 아니었다. 서버 로그를 확인하니 서버 자체가 시작 시점에 크래시되고 있었다:

```
[128353] ! Unable to start worker
[128353] uninitialized constant Admin::BaseController
/app/controllers/admin/blockchain_batches_controller.rb:2:in '<module:Admin>'
[128353] Early termination of worker
```

Rails의 eager loading 과정에서 `Admin::BlockchainBatchesController`가 `Admin::BaseController`를 상속하려는데, 해당 클래스가 코드베이스 어디에도 존재하지 않아서 서버 자체가 뜨지 못하는 상황이었다. 워커 프로세스가 요청을 하나도 받기 전에 종료된다.

즉 서버가 완전히 다운되어 있으니, Flutter URL을 아무리 맞게 고쳐도 503이었을 것이다.

### 개발 환경에서는 왜 안 터졌냐

Rails의 "개발 환경에서는 되는데 프로덕션에서 터지는" 가장 흔한 패턴이다: lazy loading과 eager loading의 차이.

| 환경 | 로딩 전략 | 상수 해석 시점 |
|------|-----------|--------------|
| 개발 | Lazy loading | 해당 라우트에 첫 요청이 들어오는 순간 |
| 프로덕션 | Eager loading (`config.eager_load = true`) | 서버 시작 시 전체 일괄 로딩 |

개발 환경에서는 admin 라우트에 요청이 한 번도 안 들어오면 `Admin::BlockchainBatchesController`가 로딩되지 않고, 따라서 `Admin::BaseController`가 없다는 사실도 드러나지 않는다. 배포 전까지 버그가 완벽하게 숨어 있는다.

프로덕션에서는 Rails가 시작 시 전체 애플리케이션을 로딩한다. 모든 클래스, 모든 모듈, 모든 상수 참조가 즉시 해석된다. 없는 기반 클래스가 시작하자마자 표면으로 드러난다.

### 수정

`app/controllers/admin/base_controller.rb` 생성:

```ruby
module Admin
  class BaseController < ApplicationController
    include ApiResponse
    include Paginatable

    skip_before_action :verify_authenticity_token
    skip_before_action :require_authentication

    before_action :authenticate_api!
    before_action :set_current_attributes

    private

    def authenticate_api!
      token = request.headers["Authorization"]&.sub("Bearer ", "")
      api_token = ApiTokenService.authenticate(token)

      if api_token
        Current.api_token = api_token
      else
        render_unauthorized("인증이 필요합니다", error_code: "unauthorized")
      end
    end

    def set_current_attributes
      Current.user_agent = request.user_agent
      Current.ip_address = request.remote_ip
    end

    def current_user
      Current.user
    end
  end
end
```

base controller는 admin 컨트롤러 전체가 공유하는 관심사를 한 곳에 모은다: API 토큰 인증, current attributes 설정, `ApiResponse`와 `Paginatable` 같은 공통 concern. 이걸 상속받는 자식 컨트롤러는 자동으로 이 동작들을 갖게 되는데, 그래서 만들지 않으면 모든 게 망가진다.

### 로컬에서 Eager Load 에러 미리 잡기

프로덕션에 배포하기 전에 로컬에서 미리 잡을 수 있다:

```bash
bundle exec rails zeitwerk:check
```

`zeitwerk:check` 명령(Rails 6+)은 autoload 경로 안의 모든 파일이 에러 없이 로딩 가능한지 검증한다. 이걸 배포 전 체크리스트나 CI 단계에 포함시키면 누락된 상수가 프로덕션을 크래시내기 전에 잡힌다.

직접 프로덕션 eager loading을 시뮬레이션하려면:

```bash
RAILS_ENV=production bundle exec rails runner "puts 'Eager load OK'"
```

---

## 서버 로그에서 크래시 찾는 방법

Render를 쓰는 경우 로드 밸런서와 헬스 체크 노이즈가 많다. 시작 크래시 에러를 빠르게 찾으려면:

- `type: ["app"]`로 필터링해서 인프라 레벨 로그 제거
- 키워드 검색: `! Unable to start worker`, `uninitialized constant`, `Early termination`

시작 크래시는 보통 다음 순서로 나타난다:

```
Unable to start worker
<Ruby 예외 + 백트레이스>
Early termination of worker
```

`Early termination`은 보이는데 `Started GET`이나 요청 처리 로그가 하나도 없다면 서버가 아예 뜨지 못한 것이다.

---

## 시간을 아낀 디버깅 순서

독립적인 두 버그를 효율적으로 처리하려면 순서가 중요하다. 서버 사이드 문제가 항상 클라이언트 사이드 설정보다 우선순위가 높다. 서버가 죽어있으면 클라이언트를 아무리 고쳐도 의미가 없기 때문이다.

```
1. Render 서버 로그 확인
   → "uninitialized constant Admin::BaseController" 발견
2. app/controllers/admin/base_controller.rb 생성
   → git push → Render 자동 배포 → 서버 정상 기동 확인
3. 헬스 체크 또는 기본 요청으로 서버 응답 확인
4. 그 다음 Flutter 에러 조사
   → DioException에서 "address = localhost" 확인
5. Flutter baseUrl 수정 → localhost:3000 → https://프로덕션URL
6. --dart-define 기반 환경 설정으로 근본 해결
7. make build-testflight (빌드 번호 자동 증가 포함)
8. xcrun altool로 TestFlight 업로드
```

Flutter URL을 먼저 고치고 서버가 여전히 다운되어 있다는 걸 나중에 알게 되면 빌드 사이클과 TestFlight 제출 한 번이 낭비된다.

---

## TestFlight 업로드 명령어

```bash
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/app.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_UUID
```

API 키 파일은 `~/.appstoreconnect/private_keys/AuthKey_KEYID.p8`에 있어야 altool이 자동으로 찾는다. 파일이 다른 위치에 있으면 altool이 키 대신 비밀번호를 요구한다.

`xcrun altool`은 공증(notarization) 용도로는 deprecated되었지만 TestFlight 업로드는 Xcode 15 기준으로 여전히 동작한다. Deprecation 경고가 나온다면 Apple 릴리즈 노트에서 대체 명령을 확인할 것.

---

## Key Takeaways

- **Flutter API URL은 절대 하드코딩하지 말 것.** `--dart-define`이나 환경별 설정 파일로 관리한다. 하드코딩된 `localhost:3000`은 시뮬레이터 테스트에서는 보이지 않고 실기기에서 치명적으로 나타난다.
- **`SocketException`의 높은 임시 포트 번호는 노이즈다.** 주소 필드(`localhost`)가 버그를 나타낸다. 포트 번호가 이상해 보여도 localhost에 연결을 시도했다는 사실 자체가 문제다.
- **Rails eager loading은 기본적으로 프로덕션 전용 동작이다.** 누락된 상수, 미해석 autoload 경로, 순환 의존성으로 인한 에러는 프로덕션 시작 시점에만 나타난다. `bundle exec rails zeitwerk:check`를 로컬에서 실행해서 미리 잡아라.
- **Rails admin 컨트롤러 추가 시 BaseController부터 만들 것.** 존재하지 않는 클래스를 상속하는 컨트롤러는 개발 환경 테스트를 조용히 통과하고 프로덕션 배포 시 서버를 크래시낸다.
- **Flutter 에러를 조사하기 전에 프로덕션 서버 로그를 먼저 확인하라.** 죽어있는 서버는 클라이언트 사이드 디버깅을 전부 무효화한다. 서버가 살아있는지 먼저 확인한 다음 클라이언트를 본다.
- **독립적인 버그 두 개가 하나의 혼란스러운 증상으로 나타날 수 있다.** TestFlight에서 SSO 로그인 실패는 하나의 문제처럼 보였지만 실제로는 클라이언트 설정 오류와 서버 크래시가 동시에 일어나고 있었다. 둘 다 잡아야 한다.
