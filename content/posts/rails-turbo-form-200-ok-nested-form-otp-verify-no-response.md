---
title: "Rails Turbo form 함정 2종 — 검증 버튼 눌러도 반응 없던 이유"
date: 2026-05-27T11:30:00+09:00
draft: false
tags: ["Rails", "Turbo", "Hotwire", "Frontend", "Debugging"]
description: "Rails 7/8 Turbo Drive 가 form POST 의 200 OK 응답을 조용히 무시하는 함정과, button_to 를 form_with 안에 nesting 했을 때 발생하는 sev1 버그를 같은 날 두 번 만난 기록"
---

OTP 2단계 인증 enrollment 화면에서 사용자가 6자리 코드를 입력하고 "확인" 버튼을 눌렀는데 화면에 아무 반응이 없다는 제보를 받았다. 서버 로그에는 정상 처리됐다고 찍혀 있고, 응답 바디도 정상 크기였다. 그런데 브라우저는 그대로 멈춰 있었다.

같은 날 오전에는 다른 사용자가 같은 화면에서 코드를 입력하고 Enter 키를 쳤더니 "2단계 인증이 활성화되어 있지 않습니다" 라는 엉뚱한 alert 가 떴다고 했다. 서버 로그를 까보니 사용자가 누른 적 없는 DELETE 액션이 호출됐다.

두 사고 모두 Turbo Drive 가 원인이었다. Rails 7 부터 기본 활성화된 이 친구가 form 동작에 미묘하게 개입하면서 발생한, 알아두지 않으면 매번 새로 깨닫게 되는 함정 두 종이다. 같은 날 두 번 터진 김에 정리한다.

---

## 사고 1 — Enter 키 누르면 엉뚱한 액션이 호출된다

OTP enrollment 화면 구조는 단순했다. QR 코드 보여주고, 6자리 코드 입력 칸 두고, "확인" 버튼과 "취소" 버튼. 확인은 POST, 취소는 DELETE 였다.

ERB 코드는 이렇게 생겼었다.

```erb
<%= form_with url: enable_otp_path, method: :post, local: true do |f| %>
  <%= f.text_field :code, autocomplete: "one-time-code" %>
  <%= f.submit "확인" %>

  <%= button_to "취소",
                disable_otp_path,
                method: :delete,
                form: { data: { turbo: false }, style: "display:none" },
                class: "hidden" %>
<% end %>
```

취소 버튼은 일부 케이스에서만 보여주려고 hidden 처리해 뒀다. 평소엔 보이지 않으니 별문제 없을 줄 알았다.

그런데 사용자가 6자리 입력하고 Enter 를 친 순간 disable_otp 가 호출됐다. 사용자가 누른 적도 없는 DELETE 가 디스패치된 것이다. 처음엔 routing 이 잘못된 줄 알았는데 routes.rb 는 멀쩡했다.

원인은 `button_to` 가 Rails 에서 어떻게 렌더되는지에 있었다. `button_to` 는 단순한 `<button>` 이 아니라 **자체적인 `<form>` 으로 감싸진 element** 다. 즉 위 코드의 실제 DOM 은 이렇게 펼쳐진다.

```html
<form action="/security/otp" method="post"> <!-- enable_otp -->
  <input type="text" name="code" autocomplete="one-time-code">
  <input type="submit" value="확인">

  <form action="/security/otp" method="post"> <!-- 취소 (DELETE) -->
    <input type="hidden" name="_method" value="delete">
    <button type="submit" class="hidden">취소</button>
  </form>
</form>
```

HTML 스펙상 `<form>` 안에 또 다른 `<form>` 을 넣는 건 invalid 다. 브라우저는 이 케이스에서 자기 마음대로 파싱한다. 그리고 Enter 키가 눌리면 input 이 속한 가장 가까운 form 의 default submit button 을 찾아 트리거한다. hidden 처리된 nested 의 취소 버튼이 첫 번째로 발견됐고, 그것이 트리거됐다.

display:none 인 버튼도 form 의 default submit 후보가 될 수 있다. 시각적으로 안 보일 뿐 DOM 에는 존재하니까.

### 해결

`button_to` 를 outer form_with 블록 **밖**으로 빼는 게 정답이다. nested form 자체를 만들지 않는다.

```erb
<%= form_with url: enable_otp_path, method: :post, local: true do |f| %>
  <%= f.text_field :code %>
  <%= f.submit "확인" %>
<% end %>

<%# form 밖에 위치 — 자체 form 이지만 nested 가 아니라 sibling %>
<%= button_to "취소",
              disable_otp_path,
              method: :delete,
              form: { data: { turbo: false } },
              class: "hidden" %>
```

배포하고 다시 테스트했다. Enter 눌렀더니 정상적으로 enable_otp 가 호출됐다.

이때까지만 해도 사고는 끝났다고 생각했다.

---

## 사고 2 — 확인 버튼 눌렀는데 화면이 그대로다

같은 날 오후, 다른 사용자가 다른 제보를 했다. "코드 입력하고 확인 버튼 눌렀는데 아무 반응이 없어요."

이번엔 nested form 도 아니고 routing 도 정상이었다. Render 로그를 까보니 POST 가 정상 처리됐다.

```
POST /console/account/security/otp
status=200 responseTimeMS=659 responseBytes=4926
```

응답 200, 바디 4.9KB. 백업 코드 acknowledgement 페이지를 정상 렌더한 거였다. 그런데 브라우저 화면은 그대로다.

처음엔 사용자 환경 탓이라고 생각했다. 그런데 다른 브라우저, 다른 OS, 다른 네트워크에서도 모두 동일했다. 서버는 정상인데 클라이언트가 응답을 무시하고 있었다.

키워드는 "form POST 응답 4.9KB" 다. Turbo Drive 가 form 응답을 어떻게 처리하는지 다시 찾아봤다.

### Turbo Drive 의 form submission 정책

Rails 7 이상부터 `form_with` 는 기본적으로 Turbo Drive 가 가로챈다. fetch API 로 비동기 POST 한 다음 응답을 받아서 직접 DOM 에 반영한다. 그런데 응답 상태 코드별로 처리 방식이 완전히 다르다.

| 응답 status | Turbo Drive 동작 |
|------------|---------------|
| 3xx redirect | Location 헤더 따라가 navigate |
| 422 Unprocessable Entity | 응답 HTML 을 in-place 렌더 (validation error 표시용) |
| 4xx/5xx (422 외) | 응답 HTML 을 in-place 렌더 |
| **200 OK** | **응답 무시. 콘솔에 에러만 찍힘** |

200 OK 가 무시되는 건 의도된 동작이다. 공식 문서에는 이렇게 적혀 있다.

> After a stateful request from a form submission, Turbo Drive expects the server to return an HTTP 303 redirect response, which it will then follow and use to navigate and update the page without reloading. The exception to this rule is when the response is rendered with either a 4xx or 5xx status code.

이유는 브라우저의 form resubmission 동작 때문이다. POST 후 페이지가 어떤 URL 에 머무는지 모호한 상황에서, 브라우저는 새로고침 시 "form 을 다시 제출하시겠습니까?" alert 를 띄운다. Turbo 가 이 동작을 흉내낼 수 없으니, 명시적으로 redirect 를 요구함으로써 URL 을 확정시키려는 디자인이다.

크롬 콘솔을 열어 보니 정말 에러가 찍혀 있었다.

```
Error: Form responses must redirect to another location
```

서버는 정상 응답했는데 클라이언트가 의도적으로 무시한 거다.

### 그런데 왜 200 으로 응답했나

내 코드의 controller 액션은 이런 모양이었다.

```ruby
def enable_otp
  user = Current.user
  code = params[:code].to_s

  unless user.verify_otp(code)
    redirect_to security_path, alert: "잘못된 코드" and return
  end

  backup_codes = user.regenerate_backup_codes!
  user.update!(
    otp_pending_at: Time.current,
    backup_codes_issued_at: Time.current
  )

  @backup_codes = backup_codes
  render template: "account/security/codes_ack"
end
```

`render` 가 기본적으로 200 OK 를 돌려준다. 실패 케이스는 모두 `redirect_to` 라서 OK 였는데, 성공 케이스가 redirect 가 아니라 codes_ack 페이지를 직접 렌더하고 있었다.

왜 redirect 가 아니냐면, 백업 코드는 일회성으로 화면에 표시하고 두 번 다시 보여주지 않는 정책이라서다. flash 에 담아 redirect 하면 cookie 에 평문으로 잠시 들어가는데 그게 싫었다. session 에 담는 것도 모바일 환경에서 새로고침되면 사라질 위험이 있고. 그래서 액션 응답 바디에 직접 렌더하는 패턴을 골랐던 거다.

### 해결책 3가지

같은 문제를 푸는 방법이 여러 개 있다.

**(1) controller 에서 redirect 강제**

```ruby
def enable_otp
  # ...
  session[:pending_backup_codes] = backup_codes
  redirect_to codes_ack_path
end
```

가장 정공법이지만, 위에서 말한 일회성 코드 정책과 충돌한다. session 에 담아 다음 GET 에서 꺼내는 패턴은 cookie store 면 cookie 에 담기고, redis store 면 별로 위험하지 않다. 정책에 따라 선택.

**(2) `status: :unprocessable_entity` 로 응답 (422)**

```ruby
render template: "account/security/codes_ack", status: :unprocessable_entity
```

가장 빠른 fix 지만 의미 오염이다. 422 는 "처리할 수 없는 entity" 라는 뜻인데 성공 응답을 422 로 보내는 건 코드를 읽는 사람을 혼란시킨다. 안 권장.

**(3) 해당 form 만 Turbo 비활성화**

```erb
<%= form_with url: enable_otp_path,
              method: :post,
              local: true,
              data: { turbo: false } do |f| %>
  <%# ... %>
<% end %>
```

`data: { turbo: false }` 를 추가하면 Turbo 가 이 form 을 가로채지 않는다. 브라우저 native form submission 으로 동작하고, 200 응답 바디는 그대로 새 페이지로 렌더된다.

내 케이스는 일회성 코드 정책 때문에 (3) 을 골랐다. 한 줄 추가로 끝.

### `local: true` 와의 관계

여기서 또 하나 헷갈리는 게 있다. `form_with` 에는 `local: true` 옵션이 있다. 이름만 보면 "비동기 처리 끄고 native form 으로 동작" 같은 느낌이다. 그런데 실제로는 다르다.

`local: true` 가 끄는 건 **Rails UJS** 의 `data-remote="true"` (XHR) 다. Rails 5~6 시절의 비동기 form 처리 기능이다. Rails 7 부터 UJS 는 사실상 deprecated 상태고 Turbo 가 그 자리를 대체한다.

Turbo 는 `local: true` 와 별개로 form 을 가로챈다. 진짜로 Turbo 까지 끄려면 `data: { turbo: false }` 가 필요하다. 두 옵션을 같이 써야 비로소 옛날 Rails 의 "그냥 form" 처럼 동작한다.

이걸 모르고 `local: true` 만 붙여놨다가 "분명히 동기 form 인데 왜 Turbo 가 동작하지?" 라고 한참 헤매는 게 흔한 코스다. 나도 처음엔 그렇게 의심했다.

---

## Turbo 가 왜 이렇게 동작하는가

찾아보니 Turbo 의 form 정책에는 나름의 이유가 있다.

기존 브라우저 form 동작에서 POST 후 새로고침 시 "다시 제출하시겠습니까?" alert 가 뜨는 건 사용자 경험상 별로다. 그래서 PRG (Post-Redirect-Get) 패턴이 web 의 사실상 표준이 됐다. 성공이면 redirect 로 GET URL 을 만들고, 실패면 form 페이지를 다시 보여준다. Turbo 는 이 패턴을 강제하는 방향으로 디자인됐다.

문제는 PRG 가 모든 상황에 fit 하지 않다는 거다. 일회성 데이터 표시 (백업 코드, OTP secret, 다운로드 토큰 등), modal 안에서의 폼 처리, 외부 시스템과의 callback 처리 등은 redirect 모델이 부자연스럽다.

이런 케이스를 위해 Turbo 는 두 가지 이스케이프 해치를 제공한다.

- **422 응답**: validation error 용이지만 실제로는 "이 응답을 그대로 렌더해라" 의 의미로 쓰인다. Hotwire 0.7.0 에서 도입됐고 Rails 7 의 `responders` gem 도 이에 맞춰 기본 422 응답으로 바뀌었다.
- **`data: { turbo: false }`**: 이 form 만 Turbo 의 손길에서 분리

두 방법 다 의도가 명확해야 한다. 422 는 진짜 validation error 일 때만, `turbo: false` 는 진짜 Turbo 없이 동작해야 하는 케이스만.

### content-type 함정 추가

심층 조사하면서 발견한 추가 함정이 있다. Turbo 가 form 을 가로챌 때 Accept 헤더에 `text/vnd.turbo-stream.html` 을 포함시킨다. 그래서 controller 의 응답 mime type 이 그쪽으로 가버릴 수 있다.

`render :new` 할 때 view 파일이 `new.html.erb` 가 아니라 그냥 `new.erb` 라면 Rails 가 mime type 을 추론하지 못해서 응답 content-type 이 `text/vnd.turbo-stream.html` 로 설정된다. 이러면 Turbo 가 응답을 turbo-stream 으로 처리하려다가 실패한다.

```ruby
# 안 되는 케이스
render :new, status: :unprocessable_entity
# content-type: text/vnd.turbo-stream.html (Turbo confused)

# 되는 케이스
respond_to do |format|
  format.html { render :new, status: :unprocessable_entity }
end
# content-type: text/html ✓
```

view 파일 확장자를 `.html.erb` 로 두거나 `respond_to do |format|` 로 명시적으로 format 을 지정하면 해결된다. 이건 내가 직접 겪지는 않았지만 같이 알아두면 좋다.

---

## 디버깅 패턴 — "form 눌러도 반응 없음" 신고 받았을 때

같은 사고를 또 겪지 않으려고 신고-원인 매핑을 정리해 뒀다. "버튼 눌러도 반응 없음" 같은 신고가 들어왔을 때 다음 순서로 보면 빠르게 좁힐 수 있다.

| 신고 패턴 | 1차 확인 | 가능성 |
|---------|---------|------|
| 버튼 눌렀는데 아무 반응 없음 | 서버 로그 status 코드 | 200 OK + 큰 body → Turbo swallow |
| 엉뚱한 액션 alert 나옴 | 같은 path 다른 method 호출 흔적 | nested form, button_to inside form_with |
| validation error 표시 안 됨 | 응답 status 코드 | render :new + 200 → 422 로 바꿔야 함 |
| Form 동기로 동작해야 하는데 안 됨 | `local: true` 만 있는지 | `data: { turbo: false }` 도 필요 |
| Turbo 가 응답 못 받음 | response content-type | text/vnd.turbo-stream.html → respond_to 로 fix |

Render 같은 cloud 환경에서는 request 로그에 status 코드, responseTimeMS, responseBytes 가 깔끔하게 나온다. 사용자 신고 받고 시간 좁혀서 그 시점의 로그만 뽑아 보면 1차 진단이 거의 끝난다.

```bash
# Render MCP / dashboard 에서 path 와 시간 범위 좁혀 조회
path=/console/account/security/otp
time=2026-05-27T01:30~02:30
```

200 OK + responseBytes 가 큰 (수 KB 단위) 응답을 본 순간 이 글의 함정을 떠올리면 된다. 302 + 작은 body (~1.5KB) 면 redirect 가 정상 동작 중이라는 뜻이고, 그 다음 페이지가 문제다. 4xx/5xx 면 in-place 렌더되니까 사용자가 알아챌 수 있다 — "응답 없음" 신고가 안 들어온다.

---

## 신규 Rails form 작성 체크리스트

같은 사고 재발 방지용으로 체크리스트 박아 두고 신규 form 만들 때마다 확인한다.

```
□ controller 액션이 success 시 redirect 하는가?
   - render 라면 Turbo opt-out 필요 (data: { turbo: false })
   - 또는 status: :unprocessable_entity (의미상 적절한 경우만)

□ form_with 블록 안에 button_to 가 없는가?
   - button_to 는 자체 form 으로 펼쳐짐 → nested 금지
   - cancel/secondary 액션은 outer 블록 밖에 위치

□ Turbo 진짜 끄려면 `data: { turbo: false }` 사용
   - `local: true` 만으로는 부족 (UJS 만 끔)

□ view 파일이 `.html.erb` 확장자인가?
   - `.erb` 만 두면 content-type 이 turbo-stream 으로 튐
   - 또는 controller 에서 respond_to do |format| 명시

□ render 의 layout 이 폼이 있던 페이지와 동일한가?
   - 다르면 422 응답이 새 GET 으로 떨어져서 폼 상태 잃음
```

---

## 같은 날 두 번 터진 이유

곰곰이 생각해 보면 두 사고 모두 "Turbo 가 form 동작에 끼어든다" 는 한 가지 사실의 두 측면이다. 사고 1 은 nested form 이라는 HTML invalid 가 Turbo 의 가로채기와 만나서 엉뚱한 form 의 default submit 을 트리거한 케이스고, 사고 2 는 Turbo 가 200 응답을 무시하는 정책이 my controller 의 render 패턴과 부딪힌 케이스다.

Turbo 자체가 나쁜 건 아니다. PRG 패턴 강제, fetch 기반 비동기 navigation, turbo-frame 으로 부분 갱신 같은 가치가 분명하다. 다만 form 의 기존 model 과 미묘하게 다른 정책 위에서 동작하기 때문에, 사용자가 명시적으로 그 차이를 알지 못하면 silent 한 버그가 만들어진다.

Rails 7 도입 시점에 Turbo 를 디폴트 켠 건 옳은 결정이라고 생각한다. 다만 form 작성 때마다 이런 함정을 의식적으로 점검하지 않으면 사고는 또 일어난다. 그래서 체크리스트로 박아 두는 게 안전하다.

---

## 결론

같은 날 OTP enrollment 화면에서 두 번의 form 사고를 만났다.

**사고 1** — button_to 를 form_with 안에 nesting 해 두면 HTML invalid 한 nested form 이 만들어진다. 사용자가 Enter 키만 쳐도 hidden 처리된 nested form 의 submit 이 트리거되어 의도치 않은 액션이 호출된다. button_to 는 항상 outer form 밖에 위치시켜야 한다.

**사고 2** — Turbo Drive 는 form POST 의 200 OK 응답을 의도적으로 무시한다. PRG 패턴을 강제하는 디자인 결정이다. 일회성 렌더가 필요하면 `data: { turbo: false }` 로 그 form 만 Turbo 에서 분리하거나, 422 응답으로 의도적으로 in-place 렌더를 트리거하거나, redirect + session 으로 우회한다.

`local: true` 는 UJS 만 끄지 Turbo 는 못 끈다는 사실도 같이 박아 두자. Rails 5~6 에서 Rails 7+ 로 넘어오면서 가장 자주 헤매는 지점 중 하나다.

같은 사고 한 번 더 겪지 않으려고 체크리스트로 정리해 둔다. 다음에 form 만들 때 5초만 쓰면 사고 한 건은 막을 수 있다.
