---
title: "fetch() + PATCH + 302 Redirect = 보이지 않는 버그"
date: 2026-03-20
draft: false
tags: ["fetch API", "HTTP", "302 Redirect", "Stimulus", "Rails", "디버깅", "Turbo"]
description: "fetch()로 PATCH 요청을 보내고 302 redirect를 받으면, 브라우저는 PATCH를 유지한 채 redirect한다. POST만 GET으로 바뀐다. 이걸 몰라서 반나절을 날렸다."
---

Stimulus 컨트롤러에서 badge 선택 UI를 만들었다. 옵션을 클릭하면 `fetch()`로 PATCH를 보내고, 서버가 업데이트한 뒤 성공/실패를 표시하는 단순한 구조다.

그런데 **DB는 업데이트되는데 UI가 실패 표시를 하면서 원래 값으로 되돌아갔다.** 서버 로그를 열기 전까지는 원인을 전혀 짐작할 수 없었다.

---

## 증상

badge를 클릭하면:
1. 잠깐 선택 스타일이 바뀜
2. 곧바로 원래 값으로 revert
3. 에러 인디케이터(`X`) 표시

다른 필드(모드, 대진표 유형)는 정상 동작하는데, **특정 필드만 실패**했다. 모델 validation 문제도 아니고, 권한 문제도 아니었다.

---

## 서버 로그에서 본 진짜 원인

```
Started PATCH "/resources/54" for ::1
Processing by ResourcesController#update as TURBO_STREAM
  Parameters: {"resource"=>{"field_name"=>"new_value"}, "id"=>"54"}
  ...
  UPDATE "resources" SET "field_name" = 1 WHERE "id" = 54
  COMMIT
Redirected to http://localhost:3000/resources/54/dashboard
Completed 302 Found in 22ms

Started PATCH "/resources/54/dashboard" for ::1
ActionController::RoutingError (No route matches [PATCH] "/resources/54/dashboard"):
```

**DB 업데이트는 성공했다.** 그런데 서버가 `redirect_to dashboard`로 302를 보냈고, fetch가 그 redirect를 따라가면서 **PATCH method를 유지한 채** dashboard URL로 요청을 보냈다. Dashboard는 GET만 받으므로 RoutingError가 터졌다.

---

## 왜 PATCH가 유지되는가?

HTTP 스펙과 Fetch 스펙을 찾아봤다.

### Fetch 스펙 (whatwg/fetch)의 redirect 처리 규칙

```
302 상태코드 + POST method    → GET으로 변환
303 상태코드 + GET/HEAD 아닌  → GET으로 변환
302 상태코드 + PATCH method   → 변환 없음 (PATCH 유지!)
```

핵심은 이거다: **302 redirect에서 GET으로 변환되는 건 POST뿐이다.** PUT, PATCH, DELETE는 원래 method가 그대로 유지된다.

### 왜 POST만 특별한가?

역사적인 이유다. 1990년대 브라우저들이 302 응답에 대해 POST를 GET으로 바꾸는 관행이 퍼졌다. HTTP 스펙 원문(RFC 2616)은 "method를 바꾸면 안 된다"고 했지만, 대부분의 브라우저가 이미 POST→GET 변환을 하고 있었다.

결국 스펙이 현실에 맞춰졌다:
- **303 See Other**: 모든 method를 GET으로 변환 (명시적)
- **307 Temporary Redirect**: 모든 method를 유지 (명시적)
- **302 Found**: POST만 GET으로 변환, 나머지는 유지 (역사적 타협)

`fetch()` API는 이 스펙을 정확히 따른다. 전통적인 `<form>` submit은 GET/POST만 쓰니까 이 문제가 안 보이지만, **JavaScript에서 PATCH/PUT/DELETE를 쓰는 순간 이 함정에 빠진다.**

### Ben Nadel의 실험 결과 (2025)

```
fetch("./api.cfm", { method: "GET" })     → 302 redirect → GET    (변환)
fetch("./api.cfm", { method: "POST" })    → 302 redirect → GET    (변환)
fetch("./api.cfm", { method: "PUT" })     → 302 redirect → PUT    (유지!)
fetch("./api.cfm", { method: "PATCH" })   → 302 redirect → PATCH  (유지!)
fetch("./api.cfm", { method: "DELETE" })  → 302 redirect → DELETE (유지!)
```

---

## 문제의 코드

```javascript
// Stimulus controller - badge 선택 시 서버에 PATCH 전송
async save(newValue, previousValue) {
  const token = document.querySelector('meta[name="csrf-token"]')?.content
  const body = { "resource[field_name]": newValue }

  try {
    const response = await fetch(this.urlValue, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRF-Token": token,
        // 이 Accept 헤더가 문제의 시작점
        "Accept": "text/vnd.turbo-stream.html, text/html, application/json"
      },
      body: new URLSearchParams(body).toString()
    })

    if (response.ok) {
      this.showIndicator("success")
    } else {
      // redirect → PATCH dashboard → RoutingError → 여기로 옴
      this.revert(previousValue)
      this.showIndicator("error")
    }
  } catch (_e) {
    this.revert(previousValue)
    this.showIndicator("error")
  }
}
```

서버 쪽:

```ruby
# Rails controller
def update
  if @resource.update(resource_params)
    respond_to do |format|
      format.html { redirect_to dashboard_path }
      format.json { render json: { status: "ok" } }
      # Accept 헤더가 turbo_stream을 우선하므로 이 분기가 매칭됨
      # redirect_to는 302를 보냄 → fetch가 PATCH로 dashboard에 재요청 → 폭발
      format.turbo_stream { redirect_to dashboard_path }
    end
  end
end
```

**흐름 정리:**

1. `fetch()`가 `Accept: text/vnd.turbo-stream.html, ...`로 PATCH 전송
2. Rails가 `format.turbo_stream` 매칭 → `redirect_to dashboard` (302)
3. `fetch()`가 302를 따라감 → **PATCH method 유지**
4. `PATCH /resources/54/dashboard` → RoutingError (GET만 허용)
5. `response.ok` = false → UI가 revert → 사용자: "왜 안 돼?"

---

## 수정

```javascript
// Before (turbo_stream 우선 → redirect 302 발생)
//
// turbo_stream format이 매칭되면 서버가 redirect_to를 반환한다.
// fetch()는 302에 대해 PATCH method를 유지하므로,
// redirect된 URL(GET 전용)에 PATCH를 보내 RoutingError가 발생한다.
// 이는 Fetch 스펙상 302 + non-POST method는 변환하지 않기 때문이다.
// (POST만 GET으로 변환, PATCH/PUT/DELETE는 유지)
// See: https://fetch.spec.whatwg.org/#http-redirect-fetch
"Accept": "text/vnd.turbo-stream.html, text/html, application/json"

// After (JSON 직접 응답 → redirect 없음)
//
// format.json은 render json: {...}으로 응답하므로
// redirect가 발생하지 않고, response.ok로 성공 여부만 확인하면 된다.
"Accept": "application/json"
```

한 줄 수정이다. `Accept` 헤더를 `application/json`으로 바꾸면 서버가 `format.json { render json: ... }`으로 응답하고, redirect가 발생하지 않는다.

---

## 대안들

JSON 응답 외에도 몇 가지 방법이 있다:

### 1. 서버에서 303 반환

```ruby
format.turbo_stream { redirect_to dashboard_path, status: :see_other }
```

303은 모든 method를 GET으로 변환하므로 RoutingError가 안 난다. 하지만 inline PATCH에 redirect 자체가 불필요하다.

### 2. fetch에서 redirect: "manual" 사용

```javascript
const response = await fetch(url, {
  method: "PATCH",
  redirect: "manual"  // redirect를 따라가지 않음
})
// response.status === 0, response.type === "opaqueredirect"
// response.ok === false이므로 별도 처리 필요
```

redirect를 아예 따라가지 않는다. 하지만 `response.ok`가 false가 되어 성공/실패 구분이 어렵다.

### 3. Turbo Stream 응답 직접 렌더

```ruby
format.turbo_stream { head :ok }
```

redirect 대신 빈 200 응답을 보낸다. 가능하지만 클라이언트가 이미 JSON으로 성공 여부를 판단하고 있다면 굳이 turbo_stream을 유지할 이유가 없다.

---

## 영향 범위

이 버그는 **같은 패턴을 쓰는 모든 Stimulus 컨트롤러**에 영향을 줬다:

- badge 선택 컨트롤러 (enum 필드 변경)
- inline 편집 컨트롤러 (숫자/텍스트 필드 변경)
- 상태 확정 컨트롤러 (상태 전환)

공통점: `fetch()` + `PATCH` + `Accept: turbo_stream` + 서버의 `redirect_to`.

---

## 교훈

1. **302 redirect에서 method가 보존되는 건 POST 빼고 전부다.** fetch API를 쓸 때 PATCH/PUT/DELETE + redirect 조합은 항상 의심해야 한다.

2. **DB 업데이트 성공 ≠ HTTP 응답 성공.** 서버 로그를 안 봤으면 "모델 문제인가?" "권한 문제인가?"만 계속 파고 있었을 것이다. 로그에서 `PATCH /dashboard → RoutingError`를 보는 순간 바로 답이 나왔다.

3. **inline PATCH 요청에는 JSON 응답이 맞다.** Turbo Stream은 form submit이나 페이지 전환에 적합하다. JavaScript에서 직접 fetch를 호출하는 경우, redirect 없는 JSON 응답이 가장 예측 가능하다.

4. **`<form>` submit으로는 절대 발견할 수 없는 버그다.** HTML form은 GET/POST만 지원하고, POST + 302는 GET으로 변환되니까 문제가 안 생긴다. fetch()로 PATCH를 쓰는 순간부터 HTTP 스펙의 다른 영역에 들어간다.

---

## 참고

- [Fetch Standard - HTTP redirect fetch](https://fetch.spec.whatwg.org/#http-redirect-fetch)
- [MDN - 302 Found](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/302)
- [Ben Nadel - Fetch API Will Propagate Non-POST Methods Upon Redirect](https://www.bennadel.com/blog/4788-fetch-api-will-propagate-non-post-methods-upon-redirect.htm)
- [RFC 7231 Section 6.4.3 - 302 Found](https://tools.ietf.org/html/rfc7231#section-6.4.3)
