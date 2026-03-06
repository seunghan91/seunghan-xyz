---
title: "Rails SSO 구현 중 Turbo Drive가 유발한 두 가지 버그 디버깅"
date: 2026-02-13
draft: false
tags: ["Rails", "SSO", "Turbo Drive", "디버깅", "Ruby", "보안"]
description: "HMAC 기반 SSO를 Rails에서 구현하면서 만난 두 가지 삽질 — Turbo Drive prefetch로 인한 세션 state 충돌과, ERB에서 j 헬퍼 사용 시 발생하는 이중 HTML 인코딩 문제"
cover:
  image: "/images/og/rails-sso-turbo-drive-debugging.png"
  alt: "Rails Sso Turbo Drive Debugging"
  hidden: true
---

Rails 앱 간 SSO(Single Sign-On)를 HMAC 기반으로 구현하던 중 예상치 못한 두 가지 버그를 만났다. 둘 다 Turbo Drive와 ERB의 동작 방식에서 비롯된 문제였다.

---

## 구현 개요

### 구조

- **IdP (Identity Provider)**: 사용자 인증을 담당하는 Rails 앱 (OTP 로그인)
- **SP (Service Provider)**: IdP에서 인증받아 로그인하는 Rails 앱

### 플로우

```
SP 로그인 버튼 클릭
  → SP: state 생성 후 세션 저장, IdP /authorize로 리다이렉트
  → IdP: 로그인 확인 후 One-Time Token 발급
  → IdP: authorize_complete 페이지 표시 (2초 후 SP callback으로 자동 리다이렉트)
  → SP callback: state 검증 + token 검증 → 로그인 완료
```

### 핵심 보안 요소

- **CSRF 방지**: SP에서 생성한 `state`를 세션에 저장하고 callback에서 검증
- **HMAC 서명**: SP가 IdP의 `/verify` 엔드포인트에 서명된 요청으로 token 검증
- **One-Time Token**: 한 번 사용하면 무효화되는 토큰

---

## 버그 1: "state mismatch" — Turbo Drive prefetch가 세션을 덮어쓴다

### 증상

SP의 "SSO 로그인" 버튼을 클릭하면 IdP에서 인증 완료 페이지까지 잘 가는데, SP callback에서 항상 **state mismatch** 에러가 발생했다.

Render 서버 로그를 보니 `/auth/sso/initiate` 요청이 **0.77초 간격으로 두 번** 찍혀 있었다.

```
05:09:23.205 - [req_A] Initiating SSO ... state=wvOVbkLL...
05:09:23.978 - [req_B] Initiating SSO ... state=fhnVtQr2...
05:09:26.748 - [callback] state mismatch
```

### 원인

Turbo Drive의 **prefetch** 기능 때문이었다.

Turbo Drive는 사용자가 링크에 호버하거나 페이지 로드 시점에 링크를 미리 fetch한다. SSO 시작 링크(`/auth/sso/initiate`)도 prefetch 대상이 된 것이다.

```
[페이지 로드] → Turbo가 /auth/sso/initiate 미리 fetch
                → 서버: state_A 생성, 세션에 저장
                → 302 redirect → IdP (CORS로 응답은 막히지만 세션 쿠키는 저장됨)

[사용자 클릭] → 실제 /auth/sso/initiate 요청
                → 서버: state_B 생성, 세션에 덮어씀
                → 302 redirect → IdP with state_B

[IdP callback] → SP에 state_B로 callback
                → 세션에는 state_B가 있어야 하는데...
```

문제는 두 요청이 **같은 브라우저 세션**으로 들어오기 때문에 서버 측에서는 정상 요청과 prefetch를 구별할 수 없다는 것이다. prefetch가 먼저 세션에 state_A를 쓰고, 실제 클릭이 state_B로 덮어쓴다. callback은 state_B로 오지만 세션에 무엇이 남아있을지 타이밍에 따라 달라진다.

### 해결

SP의 SSO 버튼 링크에 `data-turbo="false"` 추가:

```erb
<%= link_to sso_initiate_path, data: { turbo: false } do %>
  SSO로 로그인
<% end %>
```

`data-turbo="false"`는 Turbo Drive가 해당 링크를 완전히 무시하게 만든다. prefetch도, 캐싱도, 인터셉트도 없이 일반 브라우저 네비게이션으로 처리된다.

---

## 버그 2: `&amp;state=` — ERB + j 헬퍼의 이중 인코딩

### 증상

버그 1을 수정했는데도 state mismatch가 계속됐다. 로그를 다시 보니 callback URL이 이상했다:

```
GET /auth/sso/callback?token=abc123&amp;state=xyz789
```

`&state=`가 아니라 **`&amp;state=`** 그대로 서버에 도달하고 있었다. Rails는 이걸 `amp;state=xyz789`라는 키로 파싱하므로 `params[:state]`는 `nil`이 된다.

### 원인

IdP의 authorize_complete 페이지에서 자동 리다이렉트를 위한 JavaScript:

```erb
<script>
  setTimeout(function() {
    window.location.href = "<%= j @callback_url %>";
  }, 2000);
</script>
```

`@callback_url`은 `"https://sp.example.com/callback?token=abc&state=xyz"` 같은 순수 Ruby 문자열이다.

여기서 `<%= j @callback_url %>`의 처리 과정:

1. `j` (alias for `escape_javascript`): `\`, `"`, `'`, 개행 등 JS 특수문자 이스케이프. **`&`는 건드리지 않는다.**
2. `<%= %>`: 결과가 `html_safe?`가 아니면 **HTML 이스케이프** 적용. `&` → `&amp;`

Rails의 `escape_javascript` 소스를 보면:

```ruby
def escape_javascript(javascript)
  # ...
  javascript.html_safe? ? result.html_safe : result
  #          ^^^^^ 입력이 html_safe가 아니면 결과도 html_safe 아님
end
```

평범한 Ruby 문자열인 `@callback_url`은 `html_safe?`가 false이므로, `j`의 반환값도 html_safe가 아니다. 그러면 `<%= %>` 가 다시 HTML 이스케이프를 적용한다.

결과적으로 HTML에 렌더링되는 JS는:

```javascript
window.location.href = "https://sp.example.com/callback?token=abc&amp;state=xyz";
```

`<script>` 태그 안의 내용은 브라우저가 HTML 엔티티를 디코딩하지 않는다 (raw text element). 그러므로 JS가 `&amp;`를 그대로 URL로 사용하고, 브라우저는 쿼리스트링에 `amp;state=xyz`를 포함해서 서버에 전송한다.

### 해결

`raw`와 `to_json` 조합 사용:

```erb
<script>
  setTimeout(function() {
    window.location.href = <%= raw @callback_url.to_json %>;
  }, 2000);
</script>
```

- `@callback_url.to_json`: Ruby 문자열을 JSON 문자열로 변환 (`"..."` 포함, `&`는 그대로)
- `raw`: ERB의 HTML 이스케이프를 건너뜀

렌더링 결과:

```javascript
window.location.href = "https://sp.example.com/callback?token=abc&state=xyz";
```

`&`가 그대로 유지되어 올바른 URL로 이동한다.

---

## 참고: `<a href>`와 `<script>` 인코딩 차이

같은 URL을 두 곳에서 사용할 때 규칙이 다르다:

```erb
<%# href 속성: html_escape 필요, 브라우저가 &amp; → & 디코딩해서 사용 %>
<a href="<%= @callback_url %>">링크</a>

<%# script 태그: html_escape 불필요, 브라우저가 디코딩하지 않음 %>
<script>
  window.location.href = <%= raw @callback_url.to_json %>;
</script>
```

`href` 속성에서는 `<%= @callback_url %>`이 `&amp;`로 인코딩되어도 괜찮다. 브라우저가 HTML 속성의 엔티티를 자동으로 디코딩해서 실제 URL 이동 시 `&`로 처리하기 때문이다.

반면 `<script>` 태그 안은 HTML 파싱 컨텍스트가 아니라 JavaScript 파싱 컨텍스트다. 브라우저가 엔티티를 디코딩하지 않으므로 `&amp;`는 그대로 JS 문자열에 포함된다.

---

## 정리

| 버그 | 원인 | 수정 |
|------|------|------|
| state mismatch (세션 덮어쓰기) | Turbo Drive prefetch가 `/initiate`를 미리 호출 | SSO 링크에 `data-turbo="false"` |
| state mismatch (`&amp;state=`) | `<%= j url %>` 이중 인코딩으로 JS에 `&amp;` 포함 | `<%= raw url.to_json %>` 사용 |

Turbo Drive를 사용하는 Rails 앱에서 SSO나 CSRF 보호가 필요한 상태 변이 엔드포인트는 반드시 `data-turbo="false"`로 prefetch를 차단해야 한다. 그리고 ERB에서 URL을 JS에 넣을 때는 인코딩 컨텍스트를 명확히 구분해야 한다.
