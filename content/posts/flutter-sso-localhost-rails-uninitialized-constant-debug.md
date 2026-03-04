---
title: "Flutter SSO 로그인 실패 + Rails 서버 크래시 동시 디버깅 기록"
date: 2026-02-26
draft: false
tags: ["Flutter", "Rails", "TestFlight", "SSO", "Render", "디버깅"]
description: "TestFlight 앱에서 SSO 로그인이 localhost에 연결을 시도하며 실패하고, 동시에 Rails 서버가 uninitialized constant로 크래시되는 문제를 두 개 동시에 잡은 기록."
---

TestFlight에서 소셜 로그인(Apple, Google)이 전부 실패하는 버그를 잡다가 서버도 크래시되고 있다는 걸 같이 발견했다. 각각 원인이 달랐고 둘 다 잡아야 앱이 정상 동작했다.

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

1. `localhost`에 연결을 시도하고 있다 → 프로덕션 서버 URL이 아님
2. 포트가 56837, 56839처럼 랜덤 high port다 → baseUrl의 3000포트가 아님

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

### 포트 번호가 왜 56837이었냐

`baseUrl`이 `localhost:3000`인데 에러에는 56837이 찍혀서 혼란스러웠다. 실제로는 `api.post('/sso/apple', ...)` 호출이 localhost에 연결을 시도할 때 iOS 내부적으로 ephemeral 소켓 포트가 에러 메시지에 출력된 것으로 보인다. 목적지 포트가 아니라 소켓 레벨 에러 정보다. 핵심은 `localhost`에 연결을 시도했다는 것 자체다.

### 수정

```dart
class ApiService {
  static const String baseUrl = 'https://your-production-server.onrender.com';

  // ...
}
```

---

## 원인 2: Rails 서버가 시작조차 안 되고 있었음

Flutter URL을 고친다고 끝이 아니었다. 서버 로그를 확인하니 서버 자체가 크래시되고 있었다:

```
[128353] ! Unable to start worker
[128353] uninitialized constant Admin::BaseController
/app/controllers/admin/blockchain_batches_controller.rb:2:in '<module:Admin>'
[128353] Early termination of worker
```

Rails의 eager loading 과정에서 `Admin::BlockchainBatchesController`가 `Admin::BaseController`를 상속하려는데, 해당 클래스가 존재하지 않아서 서버 자체가 뜨지 못하는 상황이었다.

즉 서버가 다운되어 있으니, Flutter URL을 아무리 맞게 고쳐도 503이었을 것이다.

### 원인

컨트롤러를 추가하면서 `Admin::BaseController`를 만들지 않고 여러 admin 컨트롤러가 이를 상속하도록 코드를 작성해둔 것. 개발 환경에서는 lazy loading이라 실제 해당 컨트롤러가 요청을 받기 전까지 에러가 안 나서 발견을 못 했던 것.

프로덕션 Rails는 기본적으로 eager loading(`config.eager_load = true`)이라 시작 시점에 모든 상수를 로딩하다가 바로 터진다.

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

---

## 서버 로그에서 크래시 찾는 방법

Render를 쓰는 경우 로그에서 핵심 에러만 빠르게 찾으려면:

- `type: ["app"]`로 필터링
- 메시지에서 `! Unable to start worker`, `uninitialized constant`, `Early termination` 키워드를 찾음

개발 환경에서 안 터지는 에러가 프로덕션에서 터지는 가장 흔한 패턴:

| 원인 | 개발 | 프로덕션 |
|------|------|----------|
| Eager loading | lazy (요청 시 로딩) | 시작 시 전체 로딩 |
| 상수 미정의 | 해당 컨트롤러 안 쓰면 모름 | 시작하자마자 크래시 |

---

## 최종 수정 순서

```
1. 서버 로그 확인 → Admin::BaseController 없음 발견
2. admin/base_controller.rb 생성 → push → Render 자동 배포
3. Flutter baseUrl 수정 → localhost:3000 → https://프로덕션URL
4. make build-testflight (빌드 번호 자동 증가 포함)
5. xcrun altool로 TestFlight 업로드
```

---

## TestFlight 업로드 명령어

```bash
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/app.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_UUID
```

API 키 파일은 `~/.appstoreconnect/private_keys/AuthKey_KEYID.p8`에 있어야 altool이 자동으로 찾는다.

---

## 교훈

- **Flutter API URL은 절대 하드코딩 금지** — `--dart-define`이나 환경별 설정 파일로 관리
- **Rails admin 컨트롤러 추가 시 BaseController부터 만들 것**
- **TestFlight 배포 전에 프로덕션 서버 로그를 먼저 확인하자** — 앱이 맞아도 서버가 죽어있으면 소용없다
- 에러 메시지의 포트 번호가 이상해도 `localhost`에 연결 시도 자체가 문제의 핵심이다