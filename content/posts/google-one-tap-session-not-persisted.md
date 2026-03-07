---
title: "Google One Tap 로그인 200인데 세션 유지 안 되는 버그"
date: 2026-03-08
draft: false
tags: ["Rails", "Devise", "Google One Tap", "OAuth", "세션", "디버깅"]
description: "Google One Tap 로그인이 200 OK를 반환하지만 대시보드로 이동하면 다시 로그인 페이지로 튕기는 버그. session[:user_id]와 Devise warden 세션의 차이가 원인이었다."
---

Google One Tap 로그인 버튼을 누르면 서버는 200 OK를 반환한다. 프론트엔드에서 리다이렉트까지 정상적으로 처리되는 것처럼 보인다. 그런데 대시보드 페이지로 이동하면 다시 로그인 페이지로 튕긴다.

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

Devise는 warden이라는 인증 미들웨어를 통해 세션을 관리한다. warden의 세션 키는 `session[:user_id]`가 아니라 `warden.user.user.key` 같은 형식이다. `user_signed_in?`은 warden 세션을 확인하므로, 직접 `session[:user_id]`를 설정해도 인증된 것으로 인식하지 않는다.

즉, 서버 입장에서 One Tap은 성공했지만 **Devise 입장에서는 아무도 로그인하지 않은 상태**다.

### 일반 이메일/비밀번호 로그인과의 차이

일반 로그인 액션은 Devise의 `sign_in` 메서드를 사용한다:

```ruby
def create
  # ...
  sign_in(user, remember_me: remember_me)  # Devise가 warden 세션에 기록
  redirect_to dashboard_path
end
```

One Tap만 다른 방식을 쓰고 있었던 것이다.

---

## 수정

```ruby
def google_one_tap
  # ... 토큰 검증 및 유저 조회 ...

  # AS-IS
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

---

## 왜 이렇게 됐나

Google One Tap은 표준 폼 로그인이나 OmniAuth 콜백 방식과 다른 흐름이다. 프론트엔드에서 구글 토큰을 받아 직접 백엔드 API로 POST하는 방식이라, OmniAuth 콜백 컨트롤러와는 별도로 커스텀 액션을 만들게 된다.

이때 다른 JSON API 엔드포인트처럼 작성하다 보면 `session[:user_id] = user.id`처럼 손으로 세션을 다루게 된다. API 서버라면 이게 맞을 수 있지만, **세션 기반 웹 인증(Devise)을 사용하는 환경에서는 반드시 `sign_in`을 통해야 한다.**

---

## 교훈

1. **Devise 환경에서는 항상 `sign_in` 메서드를 사용하라** — `session[:user_id]`에 직접 쓰는 것은 Devise 세션과 무관하다
2. **200 OK가 성공을 의미하지 않는다** — 응답 코드가 아니라 이후 동작(세션 유지, 리다이렉트 성공)까지 확인해야 한다
3. **로그의 흐름을 순서대로 읽어라** — POST 성공 다음 GET에서 302가 뜬다면, POST에서 상태가 제대로 저장되지 않은 것
4. **기존에 동작하는 유사 액션과 비교하라** — 일반 로그인 액션과 One Tap 액션을 나란히 놓고 보니 차이가 바로 보였다

---

## Devise 세션 vs 직접 세션 비교

| 방식 | 코드 | user_signed_in? | 사용 시기 |
|------|------|-----------------|-----------|
| Devise sign_in | `sign_in(user)` | true | 웹 세션 기반 인증 |
| 직접 세션 | `session[:user_id] = user.id` | false | Devise 미사용 시 |
| warden 직접 | `warden.set_user(user)` | true | 저수준 접근 (비권장) |

Rails + Devise 조합에서는 `sign_in`이 정답이다.
