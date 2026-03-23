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
categories: ["Rails", "Hotwire"]
---

Rails 앱 간 SSO(Single Sign-On)를 HMAC 기반으로 구현하던 중 예상치 못한 두 가지 버그를 만났다. 둘 다 Turbo Drive와 ERB의 동작 방식에서 비롯된 문제였다. 에러 메시지는 동일하게 "state mismatch"였지만 원인은 전혀 달랐고, 첫 번째 버그를 고쳐도 두 번째가 남아 있어 디버깅이 꽤 번거로웠다.

---

## 구현 개요

### 구조

두 개의 독립적인 Rails 앱이 SSO로 연결된다.

- **IdP (Identity Provider)**: 사용자 인증을 담당하는 Rails 앱. OTP 로그인을 처리하고 One-Time Token을 발급한다.
- **SP (Service Provider)**: IdP에서 발급받은 토큰으로 로그인하는 Rails 앱. 직접 사용자 자격증명을 다루지 않고 IdP를 신뢰한다.

이 구조는 소규모 멀티 앱 환경에서 공통 인증을 구현할 때 자주 쓰이는 패턴이다. OAuth 2.0보다 단순하지만 CSRF 방지와 토큰 검증은 동일하게 필요하다.

### 플로우

```
SP 로그인 버튼 클릭
  → SP: state 생성 후 세션 저장, IdP /authorize로 리다이렉트
  → IdP: 로그인 확인 후 One-Time Token 발급
  → IdP: authorize_complete 페이지 표시 (2초 후 SP callback으로 자동 리다이렉트)
  → SP callback: state 검증 + token 검증 → 로그인 완료
```

`state`는 UUID 형태의 랜덤 문자열로, SP가 생성해서 세션에 저장한다. callback이 돌아왔을 때 세션의 `state`와 파라미터의 `state`가 일치하면 정상 플로우로 인정한다. 이게 어긋나면 "state mismatch" 에러로 처리한다.

### 핵심 보안 요소

- **CSRF 방지**: SP에서 생성한 `state`를 세션에 저장하고 callback에서 검증. 제3자가 callback URL을 임의로 호출해도 세션에 state가 없으면 차단된다.
- **HMAC 서명**: SP가 IdP의 `/verify` 엔드포인트에 서명된 요청으로 token 검증. 토큰 위조나 중간자 공격을 방지한다.
- **One-Time Token**: 한 번 사용하면 무효화되는 토큰. 재사용 공격을 방지한다.

---

## 버그 1: "state mismatch" — Turbo Drive prefetch가 세션을 덮어쓴다

### 증상

SP의 "SSO 로그인" 버튼을 클릭하면 IdP에서 인증 완료 페이지까지 잘 가는데, SP callback에서 항상 **state mismatch** 에러가 발생했다. 로컬에서는 재현이 안 되고 Render 배포 환경에서만 발생하는 것도 수상했다.

Render 서버 로그를 보니 `/auth/sso/initiate` 요청이 **0.77초 간격으로 두 번** 찍혀 있었다.

```
05:09:23.205 - [req_A] Initiating SSO ... state=wvOVbkLL...
05:09:23.978 - [req_B] Initiating SSO ... state=fhnVtQr2...
05:09:26.748 - [callback] state mismatch
```

두 요청이 서로 다른 `state`를 생성하고 있었다. 사용자가 버튼을 한 번 클릭했는데 서버 요청이 두 번 들어온 것이다.

### 원인

Turbo Drive의 **prefetch** 기능 때문이었다.

Turbo Drive는 Hotwire의 핵심 기능으로, 페이지 전환을 SPA처럼 빠르게 만들어준다. 그 과정에서 성능 최적화를 위해 링크를 미리 fetch하는 동작이 있다. 사용자가 링크에 호버하거나, 특정 조건에서는 페이지 로드 시점에 가시 영역의 링크를 미리 fetch하기도 한다.

SSO 시작 링크(`/auth/sso/initiate`)도 prefetch 대상이 된 것이다.

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

여기서 타이밍 문제가 발생한다. prefetch 요청이 state_A를 세션에 쓰고, 실제 클릭이 state_B로 덮어쓴다. IdP로부터 돌아오는 callback은 B가 들어갈 수도 있고, 드문 경우 A가 남아있을 수도 있다. 타이밍에 따라 결과가 달라지는 레이스 컨디션이다.

더 중요한 문제는, 두 요청이 **같은 브라우저 세션**으로 들어오기 때문에 서버 측에서는 정상 요청과 prefetch를 구별할 방법이 없다는 것이다. `User-Agent`도 동일하고, 쿠키도 동일하다. `Sec-Purpose: prefetch` 헤더가 붙는 경우도 있지만, 브라우저나 Turbo Drive 버전에 따라 신뢰하기 어렵다.

로컬에서 재현되지 않았던 이유도 이 때문이다. 로컬에서는 페이지 로드가 빠르고 prefetch가 트리거되지 않는 조건이었지만, Render 환경에서는 네트워크 레이턴시로 인해 prefetch가 발동했다.

### 해결

SP의 SSO 버튼 링크에 `data-turbo="false"` 추가:

```erb
<%= link_to sso_initiate_path, data: { turbo: false } do %>
  SSO로 로그인
<% end %>
```

`data-turbo="false"`는 Turbo Drive가 해당 링크를 완전히 무시하게 만든다. prefetch도, 캐싱도, 인터셉트도 없이 일반 브라우저 네비게이션으로 처리된다. 리다이렉트를 포함한 전체 HTTP 플로우가 브라우저 기본 동작으로 이루어진다.

이 방법의 장점은 구현이 단순하고 명확하다는 것이다. SSO처럼 서버 사이드 세션 상태를 변경하는 엔드포인트는 Turbo Drive의 최적화 대상에서 제외하는 것이 올바른 설계다.

대안으로 `data-turbo-prefetch="false"`를 사용하면 prefetch만 차단하고 Turbo Drive의 다른 기능은 유지할 수 있다. 하지만 SSO initiate는 어차피 전체 페이지 이동이기 때문에 `data-turbo="false"`가 더 명확한 의도를 표현한다.

---

## 버그 2: `&amp;state=` — ERB + j 헬퍼의 이중 인코딩

### 증상

버그 1을 수정했는데도 state mismatch가 계속됐다. 이번에는 서버 로그에 요청이 한 번만 찍히는데도 실패했다. 로그를 더 자세히 보니 callback URL 자체가 이상했다:

```
GET /auth/sso/callback?token=abc123&amp;state=xyz789
```

`&state=`가 아니라 **`&amp;state=`** 그대로 서버에 도달하고 있었다. Rails의 쿼리 파라미터 파싱은 `&amp;`를 구분자가 아닌 일반 문자로 처리한다. 따라서 `params[:state]`는 `nil`이 되고, `params[:"amp;state"]`에 값이 들어간다.

### 원인

IdP의 `authorize_complete` 페이지에서 자동 리다이렉트를 위한 JavaScript가 문제였다:

```erb
<script>
  setTimeout(function() {
    window.location.href = "<%= j @callback_url %>";
  }, 2000);
</script>
```

`@callback_url`은 컨트롤러에서 생성한 순수 Ruby 문자열이다:

```ruby
# IdP 컨트롤러
@callback_url = "https://sp.example.com/auth/sso/callback?token=#{token}&state=#{state}"
```

`<%= j @callback_url %>`의 처리 과정을 단계별로 분해하면:

**1단계: `j` 헬퍼 (`escape_javascript`) 처리**

`j`는 JavaScript 문자열 안에서 문법 오류를 일으키는 문자들을 이스케이프한다:
- `\` → `\\`
- `"` → `\"`
- `'` → `\'`
- 개행 → `\n`
- `</` → `<\/` (스크립트 태그 조기 종료 방지)

**`&`는 JS 문법에서 특수문자가 아니므로 건드리지 않는다.**

**2단계: ERB `<%= %>` 출력 처리**

ERB의 `<%= %>` 태그는 출력 전에 `html_safe?` 여부를 확인한다. `html_safe?`가 아니면 HTML 이스케이프를 적용한다. 이 과정에서 `&` → `&amp;` 변환이 일어난다.

Rails의 `escape_javascript` 소스를 보면 이 동작을 이해할 수 있다:

```ruby
def escape_javascript(javascript)
  javascript = javascript.to_s
  if javascript.empty?
    result = ""
  else
    result = javascript.gsub(/(\\|<\/|\r\n|\342\200\250|\342\200\251|[\n\r"'])/u, JS_ESCAPE_MAP)
  end
  # html_safe 전파: 입력이 html_safe여야 결과도 html_safe
  javascript.html_safe? ? result.html_safe : result
end
```

평범한 Ruby 문자열(`@callback_url`)은 `html_safe?`가 `false`다. 따라서 `j`의 반환값도 `html_safe?`가 `false`다. 그러면 ERB의 `<%= %>`가 HTML 이스케이프를 추가로 적용한다.

결과적으로 HTML에 렌더링되는 JS는:

```javascript
// 실제로 HTML에 박히는 내용
window.location.href = "https://sp.example.com/callback?token=abc&amp;state=xyz";
```

여기서 중요한 점은 **`<script>` 태그는 HTML 파싱 컨텍스트가 아니다**. HTML 스펙에서 `<script>`는 "raw text element"로, 내용을 HTML로 파싱하지 않는다. 브라우저는 `<script>` 내부에서 HTML 엔티티를 디코딩하지 않는다.

따라서:
- `<a href="...&amp;state=xyz">` → 브라우저가 `&amp;`를 `&`로 디코딩 → 정상 동작
- `<script>... "&amp;state=xyz" ...</script>` → 브라우저가 그대로 JS 문자열로 사용 → `&amp;`가 URL에 포함됨

JS 코드가 `window.location.href = "...&amp;state=xyz"`로 실행되면, 브라우저는 그대로 `&amp;state=xyz`를 쿼리 파라미터로 취급해서 서버에 전송한다.

### 해결

`raw`와 `to_json` 조합 사용:

```erb
<script>
  setTimeout(function() {
    window.location.href = <%= raw @callback_url.to_json %>;
  }, 2000);
</script>
```

동작 원리:

- `@callback_url.to_json`: Ruby 문자열을 JSON 문자열로 변환한다. 출력은 큰따옴표로 감싸진 형태 (`"https://sp.example.com/..."`)이고, `&`는 그대로 유지된다. JSON 이스케이프는 `"`, `\`, 제어문자만 처리한다.
- `raw`: ERB의 HTML 이스케이프를 건너뛴다. `html_safe`를 명시적으로 선언하는 것과 같다.

`j`를 사용하지 않아도 되는 이유: `to_json`이 이미 JS 문자열 리터럴로서 안전한 형태를 만들어주기 때문이다. 큰따옴표를 포함해서 JS 리터럴로 바로 쓸 수 있다.

렌더링 결과:

```javascript
// HTML에 박히는 실제 내용
window.location.href = "https://sp.example.com/callback?token=abc&state=xyz";
```

`&`가 그대로 유지되어 올바른 URL로 이동한다.

---

## 참고: `<a href>`와 `<script>` 인코딩 차이

같은 URL을 두 곳에서 사용할 때 적용되는 인코딩 규칙이 다르다:

```erb
<%# href 속성: HTML 이스케이프 필요. 브라우저가 &amp; → & 디코딩해서 사용 %>
<a href="<%= @callback_url %>">링크</a>

<%# script 태그: HTML 이스케이프 불필요. 브라우저가 디코딩하지 않음 %>
<script>
  window.location.href = <%= raw @callback_url.to_json %>;
</script>
```

`href` 속성에서는 `<%= @callback_url %>`이 `&amp;`로 인코딩되어도 괜찮다. 브라우저는 HTML 속성 값을 파싱할 때 HTML 엔티티를 자동으로 디코딩하기 때문이다. 화면에 렌더링되거나 실제 URL 이동 시에는 `&`로 처리된다.

반면 `<script>` 태그 내부는 HTML 파싱 컨텍스트가 아니라 JavaScript 파싱 컨텍스트다. HTML 스펙상 raw text element로, 브라우저가 엔티티를 디코딩하지 않는다. `&amp;`는 그대로 JS 문자열에 포함된다.

이 차이는 HTML 파서의 동작 방식 차이에서 온다. 속성 값 파싱 시에는 character reference 처리가 적용되지만, raw text element 내부에서는 적용되지 않는다.

같은 실수가 발생할 수 있는 다른 패턴들:

```erb
<%# 잘못된 예시들 %>
<script>var url = "<%= @url %>";</script>               <!-- & → &amp; -->
<script>var url = "<%= j @url %>";</script>              <!-- & → &amp; (동일 문제) -->
<script>var data = <%= @hash.to_json %>;</script>        <!-- 해시는 OK, html_safe 아님에 주의 -->

<%# 올바른 예시들 %>
<script>var url = <%= raw @url.to_json %>;</script>      <!-- & 유지 -->
<script>var data = <%= raw @hash.to_json %>;</script>    <!-- 해시도 동일 패턴 사용 %>
```

---

## 정리

| 버그 | 원인 | 수정 |
|------|------|------|
| state mismatch (세션 덮어쓰기) | Turbo Drive prefetch가 `/initiate`를 미리 호출 | SSO 링크에 `data-turbo="false"` |
| state mismatch (`&amp;state=`) | `<%= j url %>` 이중 인코딩으로 JS에 `&amp;` 포함 | `<%= raw url.to_json %>` 사용 |

---

## 핵심 교훈

**Turbo Drive와 상태 변이 엔드포인트**

Turbo Drive를 사용하는 Rails 앱에서 SSO나 CSRF 보호가 필요한 상태 변이 엔드포인트는 반드시 `data-turbo="false"`로 prefetch를 차단해야 한다. 특히 `/auth/*`, `/session/*`, CSRF state를 생성하는 모든 엔드포인트가 해당된다. 이런 엔드포인트는 "멱등하지 않다" — 호출할 때마다 새로운 상태를 만들기 때문에 prefetch가 부작용을 일으킨다.

**ERB에서 URL을 JavaScript에 삽입할 때**

`<script>` 태그 안에 Ruby 변수를 출력할 때는 `<%= raw variable.to_json %>`를 기본 패턴으로 사용해야 한다. `j` 헬퍼는 JavaScript 문자열의 특수문자를 이스케이프하지만, ERB의 HTML 이스케이프는 별도로 적용된다. `<script>` 컨텍스트에서는 HTML 이스케이프가 필요하지 않고, 오히려 `&amp;`처럼 URL을 손상시키는 결과를 낳는다.

**디버깅 전략**

두 버그 모두 증상이 같았지만("state mismatch") 원인은 완전히 달랐다. 첫 번째 버그를 수정한 후 두 번째를 발견한 것처럼, 에러 메시지만 보고 원인을 하나로 단정짓지 않는 것이 중요하다. 서버 로그에서 요청 횟수, 실제 파라미터 값, URL 인코딩 상태를 각각 확인하는 단계별 접근이 효과적이었다.
