---
title: "MCP·WebMCP 오픈소스 기여 두 달 — 프로덕션 근거가 이슈를 통과시킨다"
date: 2026-10-06T09:22:00+09:00
draft: false
tags: ["MCP", "WebMCP", "오픈소스", "Ruby", "Model Context Protocol"]
description: "MCP 공식 Ruby SDK에 PR 1건 머지, 이슈 2건이 v1.3.0에 반영됐고 W3C WebMCP 스펙 논의에도 참여했다. 프로덕션 Rails 서버 이전 중 발견한 문제를 어떻게 이슈로 만들었는지, 틀린 주장을 어떻게 정정했는지 정리했다."
---

8월 초에 직접 운영하던 Rails MCP 서버를 손으로 짠 구현에서 공식 Ruby SDK(`mcp` gem)로 옮겼다. 이전 작업 자체는 며칠이면 끝날 줄 알았다. 실제로는 옮기는 도중에 SDK가 우리 서버 모양을 다 받아주지 못하는 지점이 하나씩 나왔고, 그걸 우회 코드로 덮을지 업스트림에 올릴지 매번 고민해야 했다.

결과만 보면 두 달 동안 이렇게 됐다.

| 저장소 | 번호 | 종류 | 결과 |
|---|---|---|---|
| modelcontextprotocol/ruby-sdk | #493 | PR | 머지 (8/9) |
| modelcontextprotocol/ruby-sdk | #507 | 이슈 | 메인테이너가 #509로 구현, v1.3.0 |
| modelcontextprotocol/ruby-sdk | #508 | 이슈 | 다른 결함으로 재정의돼 #510으로 수정, v1.3.0 |
| modelcontextprotocol/ruby-sdk | #489, #491 | 리뷰 코멘트 | 머지 순서·에러 모양 결정에 반영 |
| webmachinelearning/awesome-webmcp | #19, #20 | PR | 머지 (webmcp-django, webmcp-go 등재) |
| webmachinelearning/webmcp | #234, #331 | 스펙 논의 | 진행 중 |

숫자보다 남기고 싶은 건 과정이다. 같은 "SDK가 이상하다"는 관찰도 어떤 근거를 붙이느냐에 따라 메인테이너 반응이 완전히 달랐다. 그리고 두 번은 공개 스레드에서 내가 틀렸다는 걸 스스로 정정해야 했다.

---

## MCP와 WebMCP는 다른 트랙이다

헷갈리기 쉬워서 먼저 정리한다.

**MCP(Model Context Protocol)**는 서버형 프로토콜이다. Claude Desktop, Claude Code, ChatGPT 같은 클라이언트가 JSON-RPC로 서버의 도구를 부른다. Ruby 쪽 공식 구현이 `modelcontextprotocol/ruby-sdk`이고, gem 이름은 `mcp`다. 2026-07-28 리비전부터 `initialize` 핸드셰이크가 사라지고 매 요청이 `_meta` 봉투를 들고 오는 스테이트리스 모델로 바뀌었다. 이 전환의 배경은 [MCP 스펙이 세 리비전 앞서가 있었다](/posts/mcp-spec-revisions-2026-07-28-stateless-migration/)에 따로 정리했다.

**WebMCP**는 브라우저 API다. 웹 페이지가 `document.modelContext.registerTool()`로 자바스크립트 함수를 도구로 등록하면, 브라우저 안에 있는 에이전트가 그 도구를 찾아 부른다. W3C Web Machine Learning Community Group이 스펙을 인큐베이팅하고 있고, Chrome은 149~156 버전에서 origin trial을 돌리는 중이다. 정식 표준이 아니라 Draft Community Group Report 단계다.

| 구분 | MCP | WebMCP |
|---|---|---|
| 실행 위치 | 서버 프로세스 | 브라우저 탭 |
| 호출자 | 데스크톱·CLI 에이전트 | 페이지를 띄운 브라우저 에이전트 |
| 전송 | stdio, Streamable HTTP | 페이지 내 JS 호출 |
| 표준화 | 프로토콜 리비전 (2026-07-28 최신) | W3C CG 초안, Chrome origin trial |
| 서버가 할 일 | 도구 구현 전부 | Origin-Trial 헤더, 도구가 부를 API |

내 서비스는 두 표면을 다 갖고 있다. 서버형 MCP 엔드포인트에 도구 40여 개가 있고, 웹 화면에는 WebMCP 읽기 도구 몇 개를 붙였다. 그래서 두 트랙에서 동시에 문제를 만났다.

---

## 첫 PR #493 — 누가 호출했는지 span에 안 찍혔다

SDK로 옮기고 나서 Sentry 트레이스를 보니 span에 사용자 정보가 없었다. 우리 서버는 인증된 사용자마다 보이는 도구가 달라서, 어떤 사용자의 호출이 느린지 모르면 디버깅이 안 된다.

SDK에는 `around_request` 훅이 있고, 여기서 `data`를 읽을 수 있다. 처음엔 이렇게 쓰면 될 줄 알았다.

```ruby
config.around_request = ->(data, &request_handler) {
  Sentry.set_user(id: data.dig(:server_context, :user_id))  # 항상 nil
  request_handler.call
}
```

`data[:server_context]`는 항상 비어 있었다. 코드를 따라가 보니 이름이 같은 값이 두 개 있었다.

- `Server.new(server_context: { user_id: ... })`로 넘기는 **사용자 정의 hash** — 누가 호출했는지
- `exception_reporter`가 받는 **reporter context** — `{ request: ... }`, `{ notification: "tools_list_changed" }`처럼 어디서 실패했는지

`instrument_call`은 reporter context만 받아서 `exception_reporter`로 넘기고 있었다. 사용자 정의 hash는 훅까지 오지 않았다.

PR에서는 `Configuration#instrument_server_context` 옵션을 추가했다. 기본값은 `false`다. 앱이 넣은 hash에 트레이싱 백엔드로 보내면 안 되는 값이 섞여 있을 수 있어서, 켜는 순간 기존 연동이 전송하는 데이터가 조용히 바뀌면 안 된다고 판단했다.

구현에서 한 줄이 중요했다.

```ruby
# instrument_call 안에서
data[:server_context] = self.server_context if instrument_server_context
```

`instrument_call`에는 이미 `server_context:` 키워드 인자가 있고, 이게 reader 메서드를 가린다. `self.`를 빼면 reporter context가 들어간다. PR 설명에 "the `self.` is load-bearing, not redundant"라고 적어 뒀다. 리뷰어가 정리 차원에서 지울 만한 코드였기 때문이다.

테스트는 10개를 붙였다. 기본값에서는 키가 없는지, 켰을 때 `around_request` 안에서 읽히는지, 호스트가 context를 안 줬을 때 키는 있고 값은 `nil`인지, reporter context가 사용자 값으로 새지 않는지 등이다. `rake conformance`는 기존 기준선과 같은 279 통과 / 1 실패였다. 실패 1건이 원래 있던 것이라는 것까지 PR에 적었다.

메인테이너 koic이 리뷰 코멘트 없이 이틀 만에 머지했다. 기존 `tool_arguments`(#218), `client`(#221)가 같은 hash에 추가된 방식을 그대로 따랐다고 적은 게 판단을 쉽게 한 것 같다.

---

## 이슈 #507 — resources/list에만 훅이 없었다

다음 문제는 리소스 목록이었다. 우리 서버는 요청마다 보여줄 리소스가 다르다.

- 로그인 세션은 실제 리소스, 익명 세션은 데모 리소스
- OAuth 커넥터 세션은 허용된 scope만큼 걸러진 목록

`resources/read`에는 `resources_read_handler`가 있는데 `resources/list`는 생성자에 넘긴 고정 배열을 페이지네이션할 뿐이었다. 우회책은 두 가지였다.

1. 요청마다 `MCP::Server`를 새로 만든다 — 지금 하는 방식. 동작하지만 서버를 재사용할 수 없다.
2. 서브클래스에서 private `list_resources`를 덮는다 — 내부 구현에 기대서 업그레이드마다 깨질 수 있다.

이슈에는 문제, 두 우회책, 제안(`resources_read_handler`와 대칭인 `resources_list_handler`, `server_context:` 지원, 기본 동작 불변)을 적고 "방향이 괜찮으면 PR을 내겠다"고 썼다.

다음 날 koic이 직접 #509를 열어 구현했다. v1.3.0 문서에는 이렇게 들어갔다.

```ruby
server.resources_list_handler do |params, server_context:|
  server_context[:authenticated] ? real_resources : demo_resources
end
```

내가 생각 못 한 부분도 있었다. 블록이 **페이지마다 한 번씩** 호출되고 커서가 배열 위치 오프셋이라서, 블록은 한 쿼리의 페이지들 사이에서 순서를 안정적으로 유지해야 한다. 이 제약이 문서에 명시됐다.

---

## 이슈 #508 — 제기한 문제는 틀렸고, 진짜 결함은 따로 있었다

이 이슈가 가장 많이 배운 건이다.

손으로 짠 예전 서버는 `resources/subscribe` 응답에 `subscriptionId`를 넣어 줬다. SDK로 옮기니 핸들러가 무엇을 반환하든 응답이 `{}`였다. 코드는 이랬다.

```ruby
when Methods::RESOURCES_SUBSCRIBE, Methods::RESOURCES_UNSUBSCRIBE
  validate_resource_subscription_params!(params)
  dispatch_optional_context_handler(@handlers[method], params, ...)
  {}
```

그래서 "핸들러 반환값이 버려진다, 의도라면 문서에 적어 달라"고 이슈를 올렸다.

koic의 답은 두 부분이었다.

첫째, 문서 문구는 처음부터 있었다. "The return value is ignored; the response is always an empty result `{}` per the MCP specification." 내가 못 본 거다.

둘째, **그 문구가 틀렸고 그게 진짜 결함**이었다. `resources/subscribe` 결과는 `EmptyResult`인데, 스펙상 모든 Result는 `_meta`를 가질 수 있다. `{}`를 하드코딩하면서 스펙이 허용하는 유일한 필드인 `_meta`까지 버리고 있었다.

내가 원한 최상위 `subscriptionId`는 안 된다는 답도 같이 왔다. TypeScript SDK는 이 결과를 `ResultSchema.strict()`로 검증해서 `_meta` 외 필드를 거부한다. Python SDK는 `_meta`를 통과시킨다. 세 SDK가 동의하는 동작은 `_meta` 통과뿐이다. 그래서 수정은 이렇게 됐다.

```ruby
server.resources_subscribe_handler do |params|
  {
    _meta: {
      "myapp.example/subscriptionId" => subscriptions.create(params[:uri].to_s),
    },
  }
end
```

네임스페이스 키 아래에 넣는 게 상호운용 가능한 대안이다. 덧붙여 `resources/subscribe` 자체가 2026-07-28 리비전에서 빠지고 `subscriptions/listen`으로 대체됐으니, 이 수정은 2025-11-25 이하 프로토콜에만 해당한다는 범위 설명까지 받았다.

내 이슈는 "필드를 하나 더 실어 달라"였고, 결과는 "스펙 위반을 고치되 네 요구는 이 모양으로만 가능하다"였다. 메인테이너가 세 SDK의 스키마를 대조해서 문제를 다시 정의해 준 셈이다. 이슈를 올릴 때 내 해석까지 정답일 필요는 없다는 걸 배웠다. 관찰과 재현이 정확하면 메인테이너가 올바른 문제를 찾는다.

---

## 리뷰 코멘트 #491·#489 — 겹치는 PR 두 개를 나란히 읽었다

2026-07-28 리비전 대응 PR 두 개가 동시에 열려 있었다. #489(lifecycle admission 규칙)와 #491(봉투 검증 정렬)이다. 우리 서버가 바로 이 경로를 타서 둘을 같이 읽어 봤는데, `lib/mcp/request_envelope.rb`에서 같은 변경 세 개를 각자 하고 있었다.

| 변경 | #489 | #491 |
|---|---|---|
| `REQUIRED_META_KEYS`에서 `clientInfo` 제거 | ✅ | ✅ |
| `modern?` 판정을 `protocolVersion` 하나로 | ✅ | ✅ |
| `client_info == nil` 허용 | ✅ | ✅ |

더 중요한 차이는 와이어에 나가는 에러였다. #491은 `error_code`까지 세팅해서 어떤 키가 잘못됐는지 메시지에 실었고, #489는 그렇지 않았다. 어느 쪽이 먼저 머지되든 충돌이 나고, 에러 모양이 두 가지가 될 수 있다는 걸 코멘트로 남겼다.

koic은 #491을 먼저 머지하고 그 모양(`-32602` + 문제 키 명시)을 정본으로 삼은 뒤, #489를 그 위로 리베이스하겠다고 정리했다.

리베이스된 #489 브랜치는 실제 배포에서 돌려 봤다. 레거시 `2025-03-26` 클라이언트와 `2026-07-28` 클라이언트를 한 엔드포인트에서 받는 이중 시대(dual-era) 구성이다. 가장 눈에 띈 건 이 차이였다.

```text
main       400  -32600  "Invalid Request: the session already negotiated the legacy lifecycle via `initialize`"
d34fb74    404  -32601  "Method not found: initialize is not part of the modern lifecycle (SEP-2575)"
```

`main`에서는 새 연결의 **첫 요청**인데도 "이미 레거시로 협상했다"는 에러가 났다. 한 요청 안에서 `initialize`가 세션을 레거시로 잠그고, 같은 요청의 modern 봉투가 그 잠금에 걸리는 구조였다. 클라이언트 입장에선 원인을 알 수 없는 메시지다. PR 브랜치는 이 경로를 없애고 "modern 시대에 없는 메서드"로 답한다.

그 외 29개 요청 스펙은 두 브랜치에서 결과가 같았다. 둘 다 실패한 2건은 우리 클라이언트가 `Accept: application/json`만 보내서였다. modern 경로는 `application/json, text/event-stream`을 요구한다. SDK 문제가 아니라고 명시했다.

---

## 틀린 원인을 공개 스레드에서 정정했다

같은 코멘트에 관찰을 하나 더 붙였다. modern 요청 뒤에 `initialize`를 보내도 200이 난다, 즉 era-lock 방어가 `stateless: true`에서는 도달 불가능하다는 내용이었다.

머지 다음 날 내 스펙을 리뷰하다가 이 원인이 틀렸다는 걸 알았다. 우리 컨트롤러는 POST마다 `MCP::Server`와 transport를 새로 만든다. `stateless` 설정과 무관하게 요청 사이에 잠금이 살아남을 수가 없다. 그 스펙은 `stateless: true`를 지워도 초록불이었을 거다.

그래서 정정 코멘트를 달았다.

> The observation stands … but I attributed it to `stateless: true`, and that is not the cause. Our controller constructs a fresh `MCP::Server` and transport on every POST …

스펙도 응답 코드로 원인을 추론하던 걸 생성자 호출 횟수를 직접 검증하도록 바꿨다. 응답 코드 하나로 원인을 단정하면, 원인이 바뀌어도 테스트가 초록으로 남는다.

WebMCP 쪽에서도 같은 일이 있었다. 스펙 이슈 #234는 `registerTool()`이 `undefined` 대신 등록된 도구를 반환하자는 제안이다. 8월에 나는 "등록 확인 신호가 없어서 같은 이름으로 다시 등록해 중복 throw를 확인하는 수밖에 없었다"고 썼다. 스펙 에디터들이 `getTools()`나 `toolchange` 이벤트로 되지 않느냐고 물었고, 10월에 Chrome 154에서 다시 테스트해 보니 그 말이 맞았다. "유일한 신호"라는 내 주장이 틀렸다고 먼저 인정했다.

다시 테스트하다가 새로 찾은 것도 같이 적었다.

```js
// top frame과 same-origin iframe이 둘 다 { name: 'search' }를 등록
const tools = await document.modelContext.getTools();
// → [{ name: 'search', origin: 'http://localhost:…', window: <top> },
//    { name: 'search', origin: 'http://localhost:…', window: <iframe> }]
```

이름 중복 검사는 프레임 단위라서 same-origin iframe이 같은 이름을 등록할 수 있다. 그러면 `const [tool] = await getTools()`나 `tool.name` 비교가 iframe 도구를 집을 수 있다. `t.window === window`로 거르면 구분되지만 직관적이지 않다. `toolchange`는 detail 없는 평범한 `Event`이고 iframe 등록에도 발생한다. "반환값이 필요한가"라는 설계 질문에 쓸 만한 실측 근거다.

틀린 걸 정정하는 코멘트가 신뢰를 깎을까 걱정했는데 반대였다. 실측 근거로 주장하는 사람이 근거가 틀렸을 때도 실측으로 정정하면, 다음 코멘트를 읽는 사람이 그 실측을 믿는다.

---

## WebMCP #331 — 민감한 읽기 도구를 표현할 힌트가 없다

현재 WebMCP 스펙의 도구 어노테이션은 네 개다.

| 어노테이션 | 의미 |
|---|---|
| `readOnlyHint` | 상태를 바꾸지 않는다 |
| `untrustedContentHint` | 출력에 신뢰할 수 없는 데이터(UGC, 외부 데이터)가 있다 |
| `consequentialHint` | 실행 결과가 중대하거나 되돌릴 수 없다 (항공권 예약, 송금) |
| `debugging` | 개발 도구용이다 (Chrome 156부터) |

#331은 `consequentialHint`가 쓰기 작업만 다루고, 민감한 데이터를 **읽는** 도구는 모호하다는 문제 제기다. 스펙 에디터와 브라우저 쪽 참여자들이 `consequentialHint`를 넓히기보다 별도 힌트(`sensitiveHint` 같은)가 낫다는 쪽으로 기울어 있었고, "웹 개발자 쪽 실제 수요가 있느냐"를 묻고 있었다.

마침 정확히 그 사례가 있었다. 노트·할일 앱에 붙인 `search_notes`는 노트 제목과 짧은 미리보기를, `get_calendar_events`는 일정 제목을 돌려준다. 둘 다 `readOnlyHint: true`, `untrustedContentHint: true`다. 그런데 이 정도 출력에도 사적인 정보가 들어 있고, 그걸 말할 어노테이션이 없다.

따로 만들고 있는 페이지 내 에이전트 프로토타입은 이 규칙으로 확인 단계를 띄운다.

```js
const needsConfirm =
  tool.annotations?.readOnlyHint !== true ||
  tool.annotations?.consequentialHint === true ||
  tool.annotations?.destructiveHint === true;
```

현재 어노테이션으로는 두 읽기 도구가 확인 없이 실행된다. 코멘트에는 이게 우리 프로토타입의 정책일 뿐 다른 에이전트가 `readOnlyHint`를 이렇게 읽는다는 주장이 아니라고 범위를 그었다. 그리고 별도 힌트를 선호하는 이유를 적었다. 변경 여부와 무관하게 출력 민감도를 표현할 수 있으면, 확인 UI가 "무언가를 **한다**"와 "민감한 것을 **읽는다**"를 다르게 말할 수 있다.

---

## awesome-webmcp — 작지만 생태계 지도에 올라가는 일

WebMCP를 붙이면서 Origin-Trial 헤더 미들웨어와 선언형 폼 속성 헬퍼를 Django, Go로도 뽑아 냈다. `webmachinelearning/awesome-webmcp`의 Frameworks 섹션에 두 패키지를 한 줄씩 추가하는 PR을 냈고, 9월 2일에 머지됐다.

이건 코드 기여가 아니라 큐레이션 목록 등재다. 패키지 코드를 리뷰받은 것도, 공식 인증을 받은 것도 아니다. 그래도 WebMCP를 인큐베이팅하는 조직의 목록이라 생태계를 훑는 사람이 찾을 수 있다. 지금 이 목록에는 "내 사이트 추가" PR이 몇 달째 열려 있는데, 머지되는 쪽은 개발자가 재사용할 수 있는 도구 위주로 보인다.

---

## 메인테이너가 빨리 움직인 이슈의 공통점

두 달 동안 돌아보면 반응이 빨랐던 이슈와 코멘트는 모양이 비슷했다.

| 요소 | 실제로 적은 것 |
|---|---|
| 출처 | "프로덕션 Rails MCP 서버를 이 gem으로 이전하다 발견" |
| 정확한 위치 | `lib/mcp/server.rb:622-625 at ref f0c9665` |
| 시도한 우회책 | 서버 per-request 생성, private 메서드 오버라이드 — 각각의 비용 |
| 제안의 경계 | 기본 동작 불변, opt-in, 기존 추가 사례(#218, #221)와 같은 모양 |
| 범위 한정 | "SDK 결함이 아니라 우리 배포 구조 때문" "우리 프로토타입 정책일 뿐" |
| 재현 | before/after 응답 원문, 동일 요청 세트 비교 |

커밋 해시까지 붙인 줄 번호는 사소해 보여도 효과가 컸다. 메인테이너가 내가 본 코드를 그대로 열 수 있다. 우회책과 그 비용을 적으면 "그냥 이렇게 쓰세요"라는 답을 미리 막는다. 범위를 좁게 쓰면 과장된 주장을 반박하는 데 메인테이너 시간을 쓰지 않게 된다.

반대로 실패한 것도 있다. #508에서 문서를 끝까지 안 읽고 "문서에 적어 달라"고 했다. #234에서는 대안 API를 충분히 시험하지 않고 "유일한 신호"라고 했다. 둘 다 결과적으로 더 좋은 결론에 도달했지만, 처음부터 제대로 확인했으면 메인테이너의 한 턴을 아낄 수 있었다.

---

## 주의할 점

- **이슈의 해법은 메인테이너가 다시 쓸 수 있다.** #508처럼 내 제안이 거절되고 다른 수정이 들어가는 게 정상이다. 원래 요구가 스펙상 가능한지 다른 SDK와 대조해 보면 덜 헤맨다.
- **"PR 내겠다"는 말은 지킬 수 있을 때만 한다.** #507은 메인테이너가 먼저 구현했지만, 방향 합의 없이 큰 PR을 먼저 던졌으면 버려졌을 가능성이 크다.
- **스펙이 움직이는 영역은 범위를 꼭 적는다.** `resources/subscribe`는 2026-07-28에서 사라졌다. WebMCP는 `navigator.modelContext`에서 `document.modelContext`로 이미 한 번 옮겨 갔다. 어느 버전 기준의 관찰인지 없으면 몇 달 뒤 코멘트가 틀린 정보가 된다.
- **응답 코드로 원인을 추론하는 테스트는 위험하다.** 원인이 바뀌어도 초록불이 남는다. 원인을 직접 관찰하는 단언(생성자 호출 횟수 등)으로 바꾸자.
- **origin trial 토큰에는 만료일이 있다.** Chrome WebMCP 트라이얼은 156에서 끝난다. 토큰 갱신 날짜를 일정에 넣어 두지 않으면 어느 날 도구가 조용히 사라진다.

---

## 마치며

처음엔 "SDK가 우리 서버를 못 받아준다"는 불편함에서 시작했다. 우회 코드로 덮었으면 우리 저장소에만 남았을 문제들이, 근거를 붙여 올리니 v1.3.0에 들어갔고 다른 Rails 서버도 같은 코드를 안 짜도 된다.

가장 큰 수확은 기능이 아니라 방식이다. 실사용에서 부딪힌 지점, 정확한 코드 위치, 시도한 우회책, 좁게 그은 범위. 이 네 가지를 갖추면 처음 보는 메인테이너도 하루 이틀 안에 움직였다. 틀렸을 때 실측으로 정정하는 것도 같은 방식의 일부다.

다음은 WebMCP 스펙 쪽이다. #331에서 별도 민감도 힌트 논의가 어떻게 정리되는지 지켜보면서, 프로토타입 에이전트로 실측할 수 있는 질문을 계속 가져갈 생각이다.
