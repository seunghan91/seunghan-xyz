---
title: "Google One Tap 로그인 200인데 세션 유지 안 되는 버그"
date: 2026-03-08
draft: true
tags: ["Rails", "Devise", "Google One Tap", "OAuth", "세션", "디버깅"]
description: "Google One Tap 로그인이 200 OK를 반환하지만 대시보드로 이동하면 다시 로그인 페이지로 튕기는 버그. session[:user_id]와 Devise warden 세션의 차이가 원인이었다."
---

Google One Tap 로그인 버튼을 누르면 서버는 200 OK를 반환한다. 프론트엔드에서 리다이렉트까지 정상적으로 처리되는 것처럼 보인다. 그런데 대시보드 페이지로 이동하면 다시 로그인 페이지로 튕긴다.

처음엔 CORS 문제인가, 쿠키 SameSite 설정인가, 아니면 프론트엔드 JavaScript 로직 오류인가 — 여러 방향으로 의심했다. 결론은 훨씬 단순한 곳에 있었다. Devise의 세션 관리 방식을 잘못 이해하고 있었던 것이다.

---

## 증상

서버 로그를 보면:

```
POST /users/auth/google_one_tap → 200 OK (36ms)
GET  /dashboard                 → 302 Found
     Redirected to /users/sign_in
     Filter chain halted as :require_web_user! rendered or redirected
GET  /users/sign_in             → 200 OK
```

One Tap 엔드포인트는 성공했고, 리다이렉트도 됐고, 응답도 정상이다. 그런데 대시보드에서 인증 필터가 막아버린다.

더 당혹스러운 건, 로그인 직후 Rails 콘솔로 세션을 들여다보면 `session[:user_id]`에 값이 정상적으로 들어가 있다는 점이다. 서버도 성공이라고 말하고, 세션에도 값이 있는데, 왜 인증 필터는 실패라고 말하는 걸까?

---

## 배경: Google One Tap의 동작 방식

Google One Tap은 일반적인 OAuth 2.0 redirect flow와 다르다.

기존 OAuth 흐름은 이렇다: 사용자가 "구글로 로그인" 버튼을 누르면 → 구글 인증 페이지로 리다이렉트 → 사용자가 허용하면 → 구글이 서버의 콜백 URL로 리다이렉트 → 서버에서 OmniAuth가 콜백을 처리. 이 흐름에서 OmniAuth는 세션 처리를 포함한 많은 것을 대신 해준다.

One Tap은 다르다. 구글 SDK가 브라우저에서 직접 credential token(JWT)을 발급하고, 이것을 프론트엔드 JavaScript 코드가 받아 백엔드에 POST로 직접 전송한다. 서버 사이드 리다이렉트가 없다. OmniAuth 콜백이 없다. 처음부터 끝까지 커스텀 액션으로 처리해야 한다.

이 과정에서 "OmniAuth가 해주던 것"을 직접 구현하게 되는데, 거기서 실수가 나온다.

---

## 원인

컨트롤러 코드를 보면 문제가 바로 보인다.

**One Tap 액션 (문제 있는 코드):**

```ruby
def google_one_tap
  # ... 토큰 검증 및 유저 조회 ...

  reset_session
  session[:user_id] = user.id           # ← 여기가 문제
  session[:authenticated_at] = Time.current.iso8601

  render json: { success: true, redirect_to: dashboard_path }
end
```

**인증 필터:**

```ruby
def require_web_user!
  return if user_signed_in?  # Devise warden 세션을 확인
  redirect_to '/users/sign_in'
end
```

`session[:user_id]`에 값을 넣어도 `user_signed_in?`은 이걸 모른다.

### Devise와 warden의 관계

Devise는 인증 로직을 직접 구현하지 않는다. 내부적으로 [warden](https://github.com/wardencommunity/warden)이라는 Rack 미들웨어를 사용한다. warden은 세션을 독립적으로 관리하며, 자체적인 세션 키 구조를 갖는다.

Devise가 세션에 저장하는 키는 대략 이런 형태다:

```ruby
# warden이 실제로 사용하는 세션 구조
session["warden.user.user.key"] = [[user.id], user.authenticatable_salt]
```

`user_signed_in?`은 내부적으로 `warden.authenticated?(:user)`를 호출하고, 이것은 `session["warden.user.user.key"]`의 존재와 유효성을 확인한다.

`session[:user_id]`는 완전히 별개의 키다. Devise도, warden도 이 키를 전혀 참조하지 않는다.

즉, 서버 입장에서 One Tap은 성공했지만 **Devise 입장에서는 아무도 로그인하지 않은 상태**다. 세션에 `user_id`는 있지만, Devise가 "이 사람은 로그인했다"고 인식하는 warden 세션에는 아무것도 없다.

### 일반 이메일/비밀번호 로그인과의 차이

일반 로그인 액션은 Devise의 `sign_in` 메서드를 사용한다:

```ruby
def create
  # ...
  sign_in(user, remember_me: remember_me)  # Devise가 warden 세션에 기록
  redirect_to dashboard_path
end
```

`sign_in`이 내부적으로 `warden.set_user(user)` 를 호출하고, warden이 올바른 세션 키에 유저 정보를 저장한다. 이후 `user_signed_in?`은 `true`를 반환한다.

One Tap만 다른 방식을 쓰고 있었던 것이다.

---

## 수정

```ruby
def google_one_tap
  # ... 토큰 검증 및 유저 조회 ...

  # AS-IS (잘못된 코드)
  # reset_session
  # session[:user_id] = user.id
  # session[:authenticated_at] = Time.current.iso8601

  # TO-BE: 일반 로그인과 동일하게 Devise sign_in 사용
  clear_auth_bridge_session!
  reset_session
  sign_in(user, remember_me: true)

  render json: { success: true, redirect_to: dashboard_path }
end
```

`sign_in(user)`을 호출하면 Devise가 warden 세션에 유저 정보를 기록하고, 이후 `user_signed_in?`이 정상적으로 `true`를 반환한다.

`remember_me: true`는 선택사항이다. One Tap은 사용자가 명시적으로 로그인 버튼을 누른 게 아니라 One Tap 프롬프트에 응답한 것이므로, 장기 세션을 부여할지는 제품 정책에 따라 결정하면 된다.

---

## 왜 이렇게 됐나

Google One Tap은 표준 폼 로그인이나 OmniAuth 콜백 방식과 다른 흐름이다. 프론트엔드에서 구글 토큰을 받아 직접 백엔드 API로 POST하는 방식이라, OmniAuth 콜백 컨트롤러와는 별도로 커스텀 액션을 만들게 된다.

이때 다른 JSON API 엔드포인트처럼 작성하다 보면 `session[:user_id] = user.id`처럼 손으로 세션을 다루게 된다. API 서버라면 이게 맞을 수 있지만, **세션 기반 웹 인증(Devise)을 사용하는 환경에서는 반드시 `sign_in`을 통해야 한다.**

또 한 가지 함정이 있다. `reset_session` 다음에 `sign_in`을 호출하는 순서도 중요하다. `reset_session`은 현재 세션을 무효화하고 새 세션 ID를 발급하는데, `sign_in` 이전에 호출해야 세션 고정 공격(session fixation)을 방지할 수 있다. 순서를 바꾸면 `reset_session`이 방금 쓴 warden 세션을 날려버린다.

---

## 디버깅 과정

이 버그를 추적하면서 실제로 시도한 것들:

**1. 브라우저 개발자 도구 → Network 탭**
POST 응답의 Set-Cookie 헤더를 확인했다. 쿠키는 정상적으로 발급되고 있었다. 문제는 쿠키 자체가 아니었다.

**2. Rails 콘솔에서 세션 확인**
`ActionDispatch::Session::CookieStore`를 통해 세션 내용을 디코딩해보니 `user_id`는 잘 들어가 있었다. 하지만 `warden.user.user.key`가 없었다. 이 시점에서 방향이 잡혔다.

**3. `user_signed_in?` 메서드 소스 추적**
Devise 소스를 열어보니 `user_signed_in?` → `warden.authenticated?(:user)` → warden 내부 세션 키 확인 순서로 동작했다. `session[:user_id]`를 참조하는 곳은 없었다.

**4. 일반 로그인 액션과 나란히 비교**
기존 `sessions#create` 액션을 One Tap 액션과 나란히 놓고 보니 `sign_in` 호출 유무 차이가 즉시 눈에 들어왔다.

---

## Devise 세션 vs 직접 세션 비교

| 방식 | 코드 | user_signed_in? | 사용 시기 |
|------|------|-----------------|-----------|
| Devise sign_in | `sign_in(user)` | true | 웹 세션 기반 인증 |
| 직접 세션 | `session[:user_id] = user.id` | false | Devise 미사용 시 |
| warden 직접 | `warden.set_user(user)` | true | 저수준 접근 (비권장) |

`warden.set_user(user)`도 기술적으로는 동작하지만, Devise의 내부 콜백(로그인 시 실행되는 `after_sign_in_path_for`, 각종 hook 등)을 건너뛰기 때문에 권장하지 않는다. `sign_in`은 이 모든 것을 올바르게 처리한다.

Rails + Devise 조합에서는 `sign_in`이 정답이다.

---

## Key Takeaways

1. **Devise 환경에서는 항상 `sign_in` 메서드를 사용하라** — `session[:user_id]`에 직접 쓰는 것은 Devise 세션과 무관하다. Devise는 warden을 통해 세션을 관리하며, 두 세션 구조는 서로 독립적이다.

2. **200 OK가 성공을 의미하지 않는다** — 응답 코드가 아니라 이후 동작(세션 유지, 리다이렉트 성공)까지 확인해야 한다. "서버가 성공했다"와 "원하는 상태가 저장됐다"는 다른 질문이다.

3. **로그의 흐름을 순서대로 읽어라** — POST 성공 다음 GET에서 302가 뜬다면, POST에서 상태가 제대로 저장되지 않은 것이다. 각 요청이 독립적으로 성공한다는 사실에 속으면 안 된다.

4. **기존에 동작하는 유사 액션과 비교하라** — 일반 로그인 액션과 One Tap 액션을 나란히 놓고 보니 차이가 바로 보였다. 비슷한 기능을 새로 작성할 때는 기존 코드를 반드시 참조하라.

5. **`reset_session`과 `sign_in`의 순서를 지켜라** — 세션 고정 공격 방지를 위해 `reset_session`을 먼저 호출하고, 그 다음에 `sign_in`을 호출해야 한다. 순서가 바뀌면 방금 만든 세션이 날아간다.
