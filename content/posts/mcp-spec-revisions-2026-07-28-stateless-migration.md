---
title: "MCP 스펙이 세 리비전 앞서가 있었다 — 2026-07-28 스테이트리스 전환의 전말"
date: 2026-08-07T16:39:39+09:00
draft: false
tags: ["MCP", "Model Context Protocol", "프로토콜", "아키텍처", "스테이트리스"]
description: "규격을 지키는 MCP 클라이언트일수록 서버가 실패하는 버그를 쫓다가 스펙이 세 리비전 앞서 있었다는 걸 발견했다. 2024-11-05부터 2026-07-28 스테이트리스 전환까지 각 변경의 배경과 대가를 정리했다."
---

직접 만든 MCP 서버가 이상하게 굴었다. 어떤 클라이언트에서는 잘 붙는데, 어떤 클라이언트에서는 인증이 통째로 날아가고 데모 데이터만 돌아왔다. 처음엔 클라이언트 쪽 문제라고 생각했다.

원인을 좁혀보니 정반대였다. `MCP-Protocol-Version` 헤더가 **오면** 서버가 인증 컨텍스트를 버리고 데모 모드로 강등하고 있었다. 헤더가 **없을 때만** 정상 동작했다. 그런데 스펙은 2025-06-18 부터 클라이언트가 이 헤더를 반드시 보내라고 요구한다. 즉 **규격을 제대로 지키는 클라이언트일수록 반드시 실패하는 구조**였다.

버그 자체는 몇 줄이면 고쳐진다. 문제는 그다음이었다. 고치려고 스펙을 열어보니 서버가 협상하던 `2025-03-26` 은 이미 **세 리비전 뒤처진** 버전이었다. 그사이 MCP 는 `initialize` 핸드셰이크를 없애고, 세션 헤더를 없애고, 서버가 클라이언트에게 요청을 되쏘는 모델 자체를 폐기했다. 단순 버그 수정이 아니라 **어느 리비전을 타깃할지부터 정해야 하는 상황**이었다.

그래서 리비전 다섯 개를 처음부터 훑었다. 각 변경이 왜 생겼고, 무엇을 얻고 무엇을 대가로 냈는지 정리한 기록이다.

---

## 삽질 기록 — 헤더 처리가 반대로 박혀 있었다

증상부터. 서버 로그에서 같은 사용자가 두 갈래로 갈렸다.

```
# 정상 (헤더 없음)
POST /mcp  auth=user:1234  tools=17

# 비정상 (헤더 있음)
POST /mcp  MCP-Protocol-Version: 2025-06-18
           auth=demo  tools=3
```

코드는 대략 이런 모양이었다. 프로토콜 버전 분기를 인증 경로 안에 끼워 넣은 게 화근이었다.

```ruby
def resolve_context(request)
  version = request.headers["MCP-Protocol-Version"]

  # 의도: 모르는 버전이면 안전하게 제한된 컨텍스트로
  # 실제: 아는 버전조차 여기로 떨어짐
  return demo_context unless version.nil? || SUPPORTED == version

  authenticated_context(request)
end
```

`SUPPORTED` 에 박혀 있던 값이 `"2025-03-26"` 이었다. 서버를 처음 만들던 시점의 최신 리비전이 그대로 굳어 있었던 거다. 그사이 클라이언트들은 `2025-06-18`, `2025-11-25` 를 보내기 시작했고, 전부 `demo_context` 로 떨어졌다.

여기서 진짜 문제는 **실패 방식**이었다. 스펙은 지원하지 않는 버전을 받으면 서버가 `400 Bad Request` 를 반환해야 한다고 못 박는다. 그런데 이 서버는 `200 OK` 에 데모 데이터를 실어 보냈다. 클라이언트 입장에서는 "성공했는데 도구가 3개뿐"인 상태라, 어디가 잘못됐는지 알 방법이 없다. **조용히 잘못된 성공**이 가장 나쁜 실패다.

그리고 하위호환 규칙도 정확히 반대로 알고 있었다. 스펙 원문은 이렇다.

> A server that supports clients implementing protocol versions earlier than `2025-06-18` (which did not define the `MCP-Protocol-Version` header) **MAY** treat a request that omits the header as protocol version `2025-03-26`.

헤더가 없을 때 `2025-03-26` 으로 가정하는 건 **MAY** 지 MUST 가 아니다. 구 클라이언트를 지원하지 않기로 한 서버는 헤더 없는 요청을 **거부해야 한다**. 이 서버는 정확히 거꾸로 — 헤더 없는 걸 우대하고 헤더 있는 걸 벌주고 있었다.

---

## 리비전 다섯 개를 관통하는 축

고치기 전에 전체 그림을 봤다. MCP 리비전 역사는 한 문장으로 요약된다.

**"한 사람의 랩톱에서 도는 프로토콜"로 설계된 것을 "수만 인스턴스가 로드밸런서 뒤에서 도는 프로토콜"로 개조하는 과정.**

| 리비전 | 해결한 질문 |
|---|---|
| 2024-11-05 | 공통 인터페이스가 어떻게 생겨야 하나 |
| 2025-03-26 | 원격 서버에 어떻게 안전하게 붙나 |
| 2025-06-18 | 인증을 어떻게 제대로 하고 출력을 어떻게 구조화하나 |
| 2025-11-25 | 1년 운영에서 드러난 마찰을 어떻게 없애나 |
| 2026-07-28 | 상태 자체를 어떻게 없애나 |

The Register 보도에 따르면 원 설계는 MCP 가 주로 랩톱에서 쓰이던 시절 만들어졌고, 다중 클라이언트 클라우드 배포에서 확장에 실패했다. 초기에 굳은 두 전제 — **연결이 곧 세션이고, 서버가 클라이언트에게 요청을 되쏠 수 있다** — 가 이후 모든 문제의 뿌리다. stdio 로컬 프로세스에서는 둘 다 자연스럽지만, HTTP 다중 인스턴스에서는 둘 다 성립하지 않는다.

---

## 2024-11-05 — 기반 정의

클라이언트-서버 아키텍처, JSON-RPC 2.0, 코어 프리미티브 3종(tools·resources·prompts), 전송 2종(stdio·HTTP+SSE). 2024-11-25 공개와 함께 Python·TypeScript SDK 와 Google Drive·Slack·GitHub·Git·Postgres 레퍼런스 서버가 나왔다.

풀려던 문제는 N개 모델 × M개 도구의 조합 폭발이었다. 그건 잘 풀었다. 다만 위에 적은 두 전제가 여기서 박혔다.

---

## 2025-03-26 — 원격 서버 시대

초기 채택 피드백이 한 방향을 가리켰다. 로컬 stdio 만으로는 부족하고, 남의 서버에 안전하게 붙어야 한다.

**OAuth 2.1 인가 프레임워크.** 각자 API 키를 굴리던 걸 표준 인가 흐름으로 통일했다. 원격 MCP 서버의 상업적 배포가 가능해진 지점이다.

**HTTP+SSE → Streamable HTTP.** 구 전송은 엔드포인트 2개(SSE용 GET + 메시지용 POST)를 요구했고 서버가 연결을 계속 열어둬야 했다. 서버리스·오토스케일과 궁합이 나빴다. 단일 MCP 엔드포인트에 POST 하고, 서버가 요청마다 단일 JSON 또는 SSE 스트림을 골라 응답하는 형태로 바꿨다.

여기서 절반만 고쳤다. 세션(`Mcp-Session-Id`)과 GET 스탠드얼론 스트림은 그대로 남았다. 이 잔재가 정확히 1년 4개월 뒤 제거된다.

그 외 tool annotations, audio content, argument completions, JSON-RPC 배칭이 들어갔다. Microsoft Copilot Studio 가 2025-03-19 에, 직후 OpenAI Agents SDK 가 붙었다.

---

## 2025-06-18 — 보안 경화

**JSON-RPC 배칭 제거.** 3개월 만에 도로 뺐다. 구현 복잡도 대비 실사용이 적었고, 배치 안의 개별 요청 실패·취소·스트리밍 처리가 애매했다. 넣었다 빼는 걸 주저하지 않는 이 태도는 이후 tasks(실험 → 확장 이동), `elicitationId`(도입 → 다음 리비전에서 제거)로 반복된다.

**MCP 서버 = OAuth Resource Server.** 그전에는 MCP 서버가 인가 서버 역할까지 겸하는 구현이 흔했고, 토큰 audience 검증이 느슨해 **토큰 대체(token substitution) 공격** 표면이 열려 있었다. Resource Server 로 명확히 분류하고, 토큰은 자기 audience 로 발급된 것만 수락하게 했다.

**구조화된 tool 출력.** 결과가 자유 텍스트라 클라이언트가 문자열 스크래핑을 해야 했다. `outputSchema` + `structuredContent` 로 스키마 검증 가능한 데이터를 반환하게 했다.

**elicitation 도입.** tool 실행 도중 사용자 입력이 필요하면(확인, 누락 파라미터) 방법이 없었다. 서버가 실패하고 "인자 채워서 다시 부르세요" 하거나 비표준 채널을 뚫어야 했다. 이걸 표준화했는데, 구현이 **서버발 JSON-RPC 요청을 열린 SSE 스트림에 실어 보내는** 방식이었다. 정확히 이 지점이 2026-07-28 에서 뒤집힌다.

---

## 2025-11-25 — 1주년, 마찰 제거

1년간의 실배포 피드백이 소재다. 새 기능보다 마찰 제거가 주제다.

### Client ID Metadata Documents

Dynamic Client Registration(DCR)이 생태계 규모에서 깨졌다.

- 인가 서버마다 공개 DCR 엔드포인트를 열고 레이트리밋을 걸어야 함
- 클라이언트는 서버 수천 개분의 credential 생명주기를 따로 관리
- 등록 실패 시 재등록을 반복하는 구현이 실제로 나옴

해법은 클라이언트가 자기가 통제하는 URL 을 `client_id` 로 쓰는 것이다.

```json
// https://example.com/client.json
{
  "client_id": "https://example.com/client.json",
  "client_name": "My MCP Client",
  "redirect_uris": ["https://example.com/callback"]
}
```

인가 서버가 OAuth 흐름 중에 이 JSON 을 가져다 쓴다. 신뢰 앵커가 DNS/HTTPS 로 분산되고, 사전 등록 마찰이 사라진다. 공개 엔드포인트와 보안 표면도 줄어든다.

### OIDC Discovery + 증분 스코프 동의

인가 서버 디스커버리가 MCP 전용 규약에 묶여 있어 기존 OIDC 인프라를 못 썼다. 그리고 스코프를 첫 동의에 몰아서 받아야 했다 — 아직 쓰지도 않을 권한까지 한 번에 승인시키는 구조. `WWW-Authenticate` 헤더로 필요한 시점에 스코프를 추가 요청하게 바꿔 최소권한 원칙이 실제로 성립하게 됐다.

### 실험적 tasks

요청-응답 주기를 넘는 작업(영상 렌더, 대형 빌드, 장시간 에이전트)을 표현할 방법이 없었다. 서버는 연결을 붙들거나 **가짜 진행률**을 흘려보내야 했다. "지금 호출, 나중에 수신" 패턴을 도입해 요청이 task handle 을 반환하고 `working`·`input_required`·`completed`·`failed` 상태를 추적하게 했다.

### 나머지

- **icons 메타데이터** — MCP 가 백엔드 배관에서 사용자에게 보이는 UI 로 올라온 결과
- **elicitation 표준화 + URL 모드** — 결제·복잡한 OAuth 처럼 프로토콜 안에서 못 끝내는 상호작용을 브라우저로 넘김
- **sampling 에 tool calling** — 서버 안에서 다단계 추론을 하려면 자체 에이전트 프레임워크가 필요했던 문제. 아이러니하게도 sampling 자체가 다음 리비전에서 폐기된다
- **로컬 서버 설치 보안 요구사항** — MCP 서버 설치는 임의 코드 실행이다. 원클릭 설치 UX 가 퍼지면서 사용자가 뭘 깔았는지 모르는 사례가 늘었다. 명시적 동의, 설치 내용 가시화, 백그라운드 설치 금지를 스펙 요구사항으로 못 박았다

---

## 2026-07-28 — 상태 제거

출범 이래 최대 개정. 개별 기능이 아니라 **아키텍처 전제 하나**를 바꾸는 게 목표다.

### 로드밸런서 뒤에서 실제로 무슨 일이 벌어지나

SEP-2322 가 든 시나리오가 문제를 정확히 보여준다. elicitation 이 필요한 tool 호출을 로드밸런서 뒤에서 처리하면 이렇게 된다.

```
1. 클라이언트 → tool 호출          → LB가 인스턴스 A로 라우팅
2. A가 SSE 스트림 열고 elicitation 요청 전송
3. 클라이언트 → elicitation 응답    → LB가 인스턴스 B로 라우팅
4. A는 기다리는데 데이터는 B에 있음   ← 여기가 문제
5. A가 원래 스트림으로 결과를 보내야 함
```

4단계를 메우는 방법이 둘뿐이었다.

**(a) 공유 영속 스토리지.** Postgres·Redis·DynamoDB 를 인스턴스 전체가 공유. SEP 가 든 단점이 꽤 신랄하다.

- 날씨 조회 같은 ephemeral tool 에는 **극히 비쌈** — 원래 필요 없던 계층
- 단일 장애점이 됨 → HA·복제·백업이 강제됨
- 수평 확장의 병목. 지리적 분산은 글로벌 복제 아니면 sticky 라우팅
- 분산 락 또는 합의 프로토콜 필요
- GC 정책의 트레이드오프 — 공격적으로 지우면 사용자 응답 시간이 짧아지고, 느슨하게 지우면 저장 비용 증가
- SDK 에 이 스토리지 연동 훅이 없어 인라인 코드로 짜기가 매우 어려움

**(b) sticky 로드밸런싱.** 쿠키로 같은 인스턴스에 고정. 더 싸지만 LB 특수 설정이 필요하고 관리가 어렵다.

SEP 의 결론이 핵심이다. **MCP tool 의 절대다수는 ephemeral 인데, 소수의 persistent 케이스 때문에 전원에게 상태 비용을 물리고 있었다.**

프로덕션에서 세션이 물었던 방식도 구체적이다 — sticky 라우팅 강제, 배포할 때마다 세션 드롭, 그리고 서버리스가 사용자에게 질문을 던질 만큼 SSE 스트림을 오래 붙들지 못하는 문제.

### 스테이트리스 코어

`initialize`/`notifications/initialized` 핸드셰이크와 `Mcp-Session-Id` 를 제거했다. 프로토콜 버전·클라이언트 정체·capabilities 가 매 요청 `_meta` 에 실린다.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": { "location": "Seoul" },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": { "name": "ExampleClient", "version": "1.0.0" },
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

상태가 필요한 서버는 **서버가 발급한 handle 을 평범한 tool 인자로** 넘긴다. 발표 글의 표현대로 "전송 계층에 숨은 세션 상태보다, 애플리케이션 레벨의 명시적 handle 이 낫다". 상태가 있으면 보이게 하고, 없으면 값을 물리지 않는 구조다.

### MRTR — 서버발 요청 모델 폐기

위 시나리오의 2단계가 문제의 나머지 절반이다. 서버가 요청을 되쏘려면 스트림을 붙들어야 하고, 스트림을 붙들면 그 인스턴스가 상태를 갖는다.

이제 서버는 별도 요청을 보내지 않는다. `resultType: "input_required"` 인 결과에 `inputRequests` 를 담아 **반환**하고, 클라이언트가 원 요청을 `inputResponses` 와 함께 **새 request ID 로 재시도**한다.

```
Client → tools/call (id: 1)
Server → InputRequiredResult (inputRequests: elicitation/create, requestState)
Client → tools/call (id: 2, 원본 params + inputResponses + requestState)
Server → 최종 결과
```

`roots/list`·`sampling/createMessage`·`elicitation/create` 가 전부 이 패턴으로 흡수됐다. 서버는 아무것도 붙들지 않고, 재시도는 아무 인스턴스가 받아도 된다.

대가도 분명하다. persistent tool 은 `requestState` 로 스스로 상태를 인코딩해야 한다. 프로토콜이 대신 해주던 일이 애플리케이션 책임으로 이동했다.

### `requestState` — 새로 생긴 1번 보안 함정

이게 이번 개정에서 가장 조용하고 위험한 부분이다. `requestState` 는 **클라이언트를 왕복한다.** 즉 서버 입장에서 완전히 공격자 통제 입력이다.

스펙이 요구하는 것을 그대로 옮기면 이렇다.

- 요청에 `requestState` 가 있으면 서버는 **MUST** 그 상태를 검증한다. 클라이언트는 신뢰할 수 없는 중개자다
- 변조가 우려되면 **SHOULD** 암호화한다 (AES-GCM, 서명된 JWT 등) — 기밀성과 무결성 둘 다
- **재생·하이재킹 위험이 따로 있다.** 인증된 공격자가 원래 다른 사용자에게 발급된 상태를 재전송할 수 있다. 따라서 사용자별 데이터가 들어 있으면 서버는 **MUST** 그 데이터를 원 사용자에게 암호학적으로 바인딩하고, 현재 인증된 사용자와 일치하는지 **MUST** 검증한다
- 평문 상태를 쓰는 서버는 디코딩한 값을 **다른 클라이언트 입력과 똑같이** 검증해야 한다

클라이언트 쪽에도 규칙이 있다. `requestState` 를 **MUST** 그대로 에코백하고, 내용을 들여다보거나 파싱하거나 수정해서는 **안 된다**. 없으면 재시도에 넣어서도 안 된다.

실수하기 딱 좋은 모양이다. base64 JSON 으로 대충 인코딩해두면 "암호화한 것처럼" 보이는데 실제로는 그냥 인코딩이다.

```python
# 위험 — 인코딩은 암호화가 아니다
state = base64.b64encode(json.dumps({"user_id": 42, "step": 2}).encode())

# 최소한 이렇게 — 서명 + 사용자 바인딩 + 만료
state = jwt.encode(
    {"sub": current_user.id, "step": 2, "exp": now + 600},
    SECRET, algorithm="HS256"
)
# 검증 시 sub 가 현재 인증 사용자와 같은지 반드시 확인
```

세션이 사라진 자리에 생긴 새 공격면이다. 세션 ID 는 서버가 들고 있었지만, `requestState` 는 클라이언트가 들고 있다.

### 헤더 기반 라우팅

게이트웨이·WAF·레이트리미터가 "이 요청이 어느 tool 호출인가"를 알려면 JSON 본문을 파싱해야 했다. 인프라 계층에서 본문 파싱은 비싸고, 스트리밍 요청에서는 아예 어렵다.

| 헤더 | 소스 | 필수 대상 |
|---|---|---|
| `MCP-Protocol-Version` | `_meta` 의 protocolVersion | 모든 POST |
| `Mcp-Method` | `method` | 모든 요청 |
| `Mcp-Name` | `params.name` 또는 `params.uri` | `tools/call`·`resources/read`·`prompts/get` |

```http
POST /mcp HTTP/1.1
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: get_weather
```

보안 설계가 흥미롭다. 헤더와 본문이 어긋나면 **MUST** `400` + `HeaderMismatch`(`-32020`). 이유가 스펙에 명시돼 있다 — LB 는 헤더로 라우팅하고 서버는 본문으로 실행하면 **서로 다른 진실의 원천**을 보게 되어 취약점이 된다. 헤더에 `region: us-west1` 을 쓰고 본문에 `eu-central1` 을 넣는 식의 우회를 원천 차단한다.

중간 계층에도 지침이 붙는다. 미러링된 헤더로 정책을 거는 중개자는 `MCP-Protocol-Version` 이 헤더-본문 검증을 요구하는 버전인지 먼저 확인하고, 아니면 요청을 거부해야 한다. 구 버전에서는 헤더가 검증되지 않으므로 믿으면 안 된다는 뜻이다.

### 캐시 가능한 list 결과

재연결마다 `tools/list` 를 다시 부르면 네트워크 낭비이자 **상류 프롬프트 캐시 무효화**다. tool 목록은 시스템 프롬프트에 들어가므로, 목록이 흔들리면 LLM 프롬프트 캐시가 통째로 깨지고 비용과 지연이 뛴다.

list·read 계열 결과에 `ttlMs`(신선도 힌트) + `cacheScope`(`public`/`private`)를 필수로 넣었다. 더불어 `tools/list` 는 **결정적 순서**로 반환해야 한다(SHOULD). 순서 결정성은 캐시 히트율을 직접 올린다.

이건 스테이트리스 없이는 불가능하다. list 결과가 연결마다 달라지면 애초에 캐시할 수 없다. 그래서 "list 는 연결별로 달라지지 않는다"가 같은 SEP 에 들어 있다.

### 제거된 것들과 그 이유

| 제거 대상 | 이유 |
|---|---|
| GET 스탠드얼론 스트림 | "서버가 아무 때나 뭔가 보낼 수 있는 채널" = 열려 있는 동안 상태. `subscriptions/listen` 으로 대체 |
| SSE 재개(`Last-Event-ID`) | 재개하려면 서버가 이벤트 버퍼를 보유 = 상태 |
| `ping` | 세션 생존 확인용. 세션이 없으면 의미 없음 |
| `logging/setLevel` | 세션 스코프 설정. 요청별 `_meta` 의 `logLevel` 로 이동 |
| `notifications/roots/list_changed` | 세션 전제 |
| `tasks/list` | 목록을 주려면 전역 task 레지스트리 유지 필요 |

`subscriptions/listen` 은 단일 long-lived POST 응답 스트림이다. 클라이언트가 원하는 알림 종류를 명시적으로 opt-in 하고 서버가 ack 한다. 알림 채널이 하나의 평범한 요청이 되면서 같은 인증·라우팅·미터링 경로를 타게 됐다.

스트림이 끊기면 in-flight 요청은 소실된다. 클라이언트가 새 request ID 로 재발행해야 한다(MUST). 재전송 보장을 프로토콜에서 빼고 재시도 책임을 클라이언트로 옮긴 것 — 멱등성 부담이 애플리케이션으로 가는 대신 서버 인스턴스는 완전히 대체 가능해진다.

### Roots·Sampling·Logging 폐기와 12개월 정책

sampling 은 실사용이 드물고 의미가 혼란스러웠고, roots 는 니치한 파일시스템 기능, logging 은 stderr/OpenTelemetry 로 충분했다. 셋 다 폐기됐다.

| 폐기 기능 | 권장 대체 |
|---|---|
| Roots | tool 파라미터, 리소스 URI, 서버 설정 |
| Sampling | LLM 제공자 API 직접 연동 |
| Logging | stderr(stdio) 또는 OpenTelemetry |

더 중요한 건 함께 들어온 거버넌스다. Active / Deprecated / Removed 세 상태와 **최소 12개월 폐기 유예**, 폐기 기능 레지스트리를 정책으로 못 박았다. "업그레이드에 반응하는 대신 계획할 수 있게" 하는 것. 프로토콜이 실험 단계를 벗어나 인프라로 취급되기 시작했다는 신호다.

### 에러코드 정리

`-32000~-32019` 는 구현 정의(기존 SDK 관행 grandfathering), `-32020~-32099` 는 스펙 예약으로 나눴다. 이 원칙에 맞춰 드래프트 단계에서 미리 재번호했다.

| 이름 | 변경 |
|---|---|
| `HeaderMismatch` | `-32001` → `-32020` |
| `MissingRequiredClientCapability` | `-32003` → `-32021` |
| `UnsupportedProtocolVersion` | `-32004` → `-32022` |
| 리소스 not found | `-32002` → `-32602` (JSON-RPC Invalid Params) |

배포 후에는 못 바꾸니 드래프트에서 정리한 것이다. 마지막 항목은 특정 코드를 catch 하던 에러 처리를 조용히 깨뜨리므로 마이그레이션 체크리스트에 반드시 넣어야 한다.

---

## era 모델 — 실무에서 진짜 봐야 할 표

스펙이 정의한 용어가 마이그레이션 판단의 기준이다.

- **Modern** = 요청별 메타데이터 (2026-07-28 이상)
- **Legacy** = `initialize` 핸드셰이크 (2025-11-25 이하)
- **Dual-era** = 둘 다 지원

| Client | Server | 결과 |
|---|---|---|
| Modern | Modern | 동작 |
| Modern | Legacy | **실패** |
| Dual-era | Modern | 동작 |
| Dual-era | Legacy | 동작 |
| Legacy | Modern | **실패** |
| Legacy | Dual-era | 동작 |

핵심은 대각선이 아니라 **Dual-era 행**이다. 지금 새로 만드는 건 dual-era 여야 안전하다. 판별 방법도 규정돼 있다.

- **HTTP**: modern 요청을 먼저 던지고 `400` 이 오면 **본문을 본다.** 인식 가능한 modern JSON-RPC 오류면 modern 서버 → 버전 바꿔 재시도. 본문이 비었거나 인식 불가면 legacy → `initialize` 폴백
- **stdio**: `server/discover` 로 probe. modern 오류가 아닌 무엇이든 오면 폴백
- era 는 **요청이 아니라 서버의 속성**이다. 프로세스(stdio)나 오리진(HTTP) 수명 동안 캐시해야 한다(SHOULD)

`server/discover` 는 서버가 반드시 구현해야 하지만(MUST), 클라이언트는 선택이다(MAY). 그냥 요청을 던지고 `UnsupportedProtocolVersionError` 를 받아 재시도해도 된다. 협상이 핸드셰이크(왕복 필수)에서 **낙관적 실행 + 오류 시 재협상**으로 바뀐 셈이라 정상 경로에서 왕복 1회를 아낀다.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32022,
    "message": "Unsupported protocol version",
    "data": {
      "supported": ["2026-07-28", "2025-11-25"],
      "requested": "1900-01-01"
    }
  }
}
```

modern 전용 서버라면 `initialize` 요청에 대한 오류 메시지에 지원 버전을 적어줘야 한다(SHOULD). legacy 클라이언트에게는 그게 유일한 진단 정보다.

---

## 실전 판단 — 무엇을 지금 하고 무엇을 미룰까

세 리비전 뒤처진 서버를 앞에 두고 내린 결론이다.

**지금 당장 고칠 것.** 프로토콜 버전 분기를 **인증 판단에서 완전히 분리**한다. 어느 리비전을 타깃하든 이건 버그다.

```ruby
SUPPORTED_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"].freeze

def negotiate_version(request)
  raw = request.headers["MCP-Protocol-Version"]
  # 헤더 없음 = 구 클라이언트. 지원하기로 했다면 2025-03-26 가정
  return "2025-03-26" if raw.nil?

  # 미지원 = 조용한 강등이 아니라 400
  unless SUPPORTED_VERSIONS.include?(raw)
    return render_unsupported_version(raw, SUPPORTED_VERSIONS)
  end
  raw
end

# 인증은 여기서 독립적으로. 버전과 엮지 않는다.
def authenticate(request) = resolve_token(request)
```

**타깃 리비전.** `2026-07-28` 로 바로 가면 서버 재작성에 가깝다 — MRTR 로 elicitation 경로 전환, 모든 결과에 `resultType`, list 결과에 `ttlMs`/`cacheScope`, 헤더 3종 검증, `server/discover` 구현, `subscriptions/listen`. 반면 `2025-11-25` 로 맞추면 현재 클라이언트 생태계와 붙고, 그 위에 dual-era 판별만 얹어두면 전환 시점을 선택할 수 있다.

**지금부터 미리 해둘 것.** 세션이나 연결에 매달린 상태가 있다면 handle 기반으로 빼두는 것. 어느 쪽 리비전에서도 손해가 아니고, modern 전환 비용의 대부분이 여기에 몰려 있다. `Mcp-Session-Id` 를 키로 뭔가 저장하고 있다면 그게 1순위 작업이다.

**SDK 상황도 봐야 한다.** TypeScript 는 `@modelcontextprotocol/client@2` / `@modelcontextprotocol/server@2` 두 패키지로 갈렸고, 2025 시대 서버는 기존 `@modelcontextprotocol/sdk` 1.x 라인에 남는다. 버전을 핀으로 고정해두지 않으면 의도치 않게 era 를 건너뛰게 된다.

MCP 를 위임이 아니라 운용의 관점으로 보는 이야기는 [MCP는 내 전용 캐릭터다](/posts/mcp-personal-character-operation-not-delegation/)에 따로 적어뒀다.

---

## 정리

세 줄로 줄이면 이렇다.

1. **`MCP-Protocol-Version` 을 인증 판단에 엮지 마라.** 미지원 버전은 조용한 강등이 아니라 `400` 이다. 조용히 잘못된 성공이 가장 나쁜 실패다.
2. **2026-07-28 의 본질은 기능 추가가 아니라 상태 제거다.** 없어진 것들(세션·핸드셰이크·GET 스트림·SSE 재개·ping)은 전부 "누군가 뭔가를 붙들고 있어야 하는" 것들이었다.
3. **세션이 사라진 자리에 `requestState` 가 들어왔다.** 서버가 들고 있던 상태가 클라이언트를 왕복하게 됐으니, 서명·사용자 바인딩·만료 없이 쓰면 재생 공격에 그대로 열린다.

버그 하나 고치려다 프로토콜 역사 1년 9개월을 읽게 된 케이스였다. 그런데 읽길 잘했다. 헤더 한 줄만 고쳤으면 다음 리비전에서 똑같은 자리에서 또 깨졌을 거다.
