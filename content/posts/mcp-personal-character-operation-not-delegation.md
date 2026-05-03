---
title: "MCP는 내 전용 캐릭터다 — 위임이 아니라 운용으로"
date: 2026-05-03T09:00:00+09:00
draft: false
tags: ["MCP", "AI Agent", "Digital Identity", "AX", "DT"]
description: "MCP를 SaaS 도구로만 쓰지 말고 내 전용 캐릭터로 운용하는 관점. GitHub MCP 17,600 토큰의 함정부터 위임이 아닌 운용 패턴, Hashimoto 공식 확장까지."
---

<style>
article p, article li, article td, article th, article blockquote {
  word-break: keep-all;
  overflow-wrap: break-word;
}
</style>

[ MCP, 너 내 도도독… 아니, 내 전용 캐릭터가 돼라! ]

MCP 100개 깔지 마세요. 한 개 잘 만드세요.
CLI는 서비스에 MCP는 나에게 양보하세요.

GitHub MCP 하나 깔면 Claude 컨텍스트 17,600 토큰. AI가 사용자 질문을 보기도 전에 컨텍스트 절반이 도구 설명으로 사라집니다.

MCP(Model Context Protocol)
'M' - '나', 'C' - '맥락', 'P' - '의사소통'
=> RPC(Real Player Character),
과거의 바보 같은 NPC(Non-Player Character)가 아닙니다.

사람은 24시간 7일 계속해서 일을 할 수 없습니다. 근데 잘 때도, 회의 중에도, 휴가 중에도 필요에 따라서는 일을 진행해야 합니다. 비서를 고용한다고 해결될 문제가 아닙니다. 비서도 잡니다.

그래서 노션·옵시디언·캘린더·슬랙에 나눠져 있는 데이터들을 한 곳에 모아 MCP라는 캐릭터를 만들어 AI가 붙어서 인터넷에서 활동한다면, 그게 곧 나를 대신해 살아있는 내 캐릭터가 됩니다.

MCP는 쉽게 말해 AI 세계의 USB-C입니다. 예전에는 Claude에서 노션 붙이려면 Claude용 코드를, ChatGPT에서 노션 붙이려면 ChatGPT용 코드를 따로 짰습니다. MCP가 표준이 되고 나서는 MCP 서버 한 번 만들면 Claude·ChatGPT·Codex 어디서든 같은 도구를 씁니다.

여기까지가 일반적인 설명입니다. 그런데 '내 캐릭터'로 쓰려면, 이 표준이 어떻게 동작하는지부터 그려야 합니다.

---

## 1) 내 캐릭터는 어떻게 일하나

작동 원리를 단순하게 그리면 이렇습니다.

```
내 로컬 데이터 (Ainote, 옵시디언, 캐시 DB, 메모)
     ↓ read
내 PC에 띄운 MCP 서버
     ↓ 호출할 때마다 권한 게이트
LLM (Claude / ChatGPT / Codex)
```

데이터는 둘 중 하나로 둡니다.

- **패턴 A**: 로컬 파일·DB는 원래 자리에 두고, MCP가 읽으러 가서 가져옴 (예: notion, 옵시디언 로컬 노트 폴더)
- **패턴 B**: 데이터를 아예 MCP 서버 안에 보관하고, MCP가 자기 내부에서 사용 (예: Ainote 로컬 mirror, 자체 캐시 DB)

어느 쪽이든 데이터가 내 영역 밖으로 나가지 않습니다. 외부로 나가는 건 LLM에 보내는 그 순간의 컨텍스트. 동기화 클라우드, OAuth 위임된 SaaS — 그런 매개가 없습니다.

그리고 LLM이 어떤 도구를 호출하려 할 때마다, 위험도에 따라 게이트가 작동합니다.

| 액션 분류 | 처리 |
|----------|------|
| 조회 / read-only | 자동 통과 |
| 쓰기 / 추가 | 5분 타임윈도우 자동 승인 |
| 삭제 / 메일 발송 / 결재 / 송금 | PASS·생체인증으로 매번 확인 |

읽기는 알아서 하되, 돌이킬 수 없는 행동은 무조건 나(주인)에게 확인 후 다음 진행. 이게 위임이 아니라 운용의 코드 그림입니다.

여기서 한 가지 의문. *"그래서 그 MCP 서버라는 게 어디 있는 건데?"*

---

## 2) 'MCP 서버'에서 오해가 시작됩니다

이 얘기를 꺼내면 거의 매번 같은 질문이 돌아옵니다. *"그럼 그 서버 어디다 둠?"*

'MCP 서버'라는 단어 때문에 사람들은 메이플스토리 서버, 카카오 서버 같은 중앙 서비스를 떠올립니다. 그게 아닙니다.

여기서 말하는 서버는 내 PC, 내 노트북, 내 NAS(서버가 없다면 무료 클라우드)에서 직접 띄우는 작은 서비스입니다. 외부에 노출되지 않은 내 영역에서 도는 코드.

오히려 비유는 정확히 반대 방향입니다. 메이플 서버에 캐릭터를 만들 듯, 인터넷 상에 내 캐릭터를 만드는 것입니다. 다만 이번엔 그 서버를 남이 운영하지 않습니다. 내가 직접 합니다.

---

## 3) 캐릭터는 위임이 아니라 운용이다

위임 = 의사결정권 양도. 운용 = 정해진 룰 안에서의 실행.

위임은 *"이 결정 네가 해라"*입니다.
운용은 *"이 룰대로만 움직여라, 룰을 벗어난다면 항상 물어봐라"*입니다.

자율 에이전트가 *"나 대신"* 의사결정하고 행동하는 건 위험합니다. 거래처에 잘못 보낸 메일은 누구 책임인가요. 자동 결재 버튼은 누구 사인인가요. 이 질문에 답할 수 없는 상태에서 위임을 주면, 그건 캐릭터가 아니라 트롤입니다.

MCP가 좋은 인터페이스인 이유는 위임을 안전하게 통제할 수 있어서입니다. API 키 스코프, 2FA, 호출 감사 로그, 위험 액션 PASS 인증, HITL 게이트. 우리가 매일 쓰는 보안 패턴 그대로 적용 가능합니다.

자율을 주는 게 아니라 운용 권한만 주는 것. 그게 MCP 캐릭터의 정확한 정의여야 합니다.

---

## 4) Agent라는 단어에 너무 많은 의미가 실렸다

요즘 모두가 *"Agent, Agent"* 합니다. Anthropic이 `Agent = LLM + tools + loop`라 정의한 이래, 모든 LLM 래퍼가 자칭 agent가 됐습니다. Karpathy도 *"대부분의 자칭 agent는 그냥 for-loop가 달린 LLM"*이라 비판했습니다.

이런 단어 싸움보다, *"AI가 무엇을 어디까지 다루는가"*로 보는 게 본질이라고 생각합니다. 핵심은 AI가 내 데이터를 내 지시대로 운용하는가 입니다.

---

## 5) 개인 DT 없이는 개인 AX도 없다

회사 AX(AI Transformation)가 성공하려면 DT(Digital Transformation)가 선행되어야 한다는 말이 있습니다. 데이터가 흩어져있고 프로세스가 디지털화되지 않으면, 아무리 좋은 AI를 붙여도 운용할 게 없습니다.

개인 차원의 캐릭터도 똑같습니다.

자기 노션에 5년치 회의록·메모가 무질서하게 쌓인 상태에서 *"AI 에이전트로 자동화하겠다"*는 분들을 자주 봅니다. 그건 자동화가 아니라 환각의 자동화입니다.

순서는 이렇습니다.

1. 내 데이터를 한 곳에 모은다 (개인 DT)
2. LLM을 붙여 운용한다 (개인 AX)
3. MCP로 외부와 안전하게 소통한다 (캐릭터 활성화)

3번을 먼저 하면 무너집니다. 1번이 빠진 캐릭터는 텅 빈 외피이고, 2번이 빠진 MCP는 그냥 API 게이트웨이입니다.

---

## 6) 그래서 어디서 돌릴 거냐

내 노트북도 되고, 맥미니도 되고, NAS도 됩니다. 외부에 노출시키지 않고 Tailscale 같은 사설망으로만 접근하면 됩니다.

핵심은 위치가 아니라 소유권입니다. 외부 SaaS가 아닌 내 영역에서 돈다는 것. 그게 직접 운용과 무지성 위임을 가르는 선입니다.

다만 한 가지는 분명해질 것 같습니다. 내 캐릭터를 24시간 켜둘 작은 서버 한 대가 곧 모두에게 필요해진다는 것. 10년 전 노트북 한 대가 그랬듯이.

---

## 7) Hashimoto의 하네스에 이어서..

Mitchell Hashimoto가 26.1Q에 `Agent = Model + Harness`라는 공식을 세웠습니다. *'무엇으로 만들어졌는가'*에 대한 답이었죠.

저는 한 줄을 더해 봅니다.

```
Agent     = Model + Harness            (Hashimoto)
Character = Agent + (My Data ↔ MCP)    (← 이번 글)
```

Hashimoto의 공식은 *"에이전트가 무엇이냐"*의 답이고, 위 공식은 *"그 에이전트가 누구의 것이냐"*의 답입니다.

---

## 8) 업계도 같은 방향으로 정렬 중이다

1년 전이라면 가설이었지만 이제 다릅니다.

- **Kong (DevWeek 2026)**: *"Delegated OAuth gives AI agents scoped, short-lived tokens so they act on your behalf without roaming free with your credentials"* — 위임이 아니라 대리(delegate), 그것도 짧고 좁게.
- **MCP 공식 로드맵 (2026 Q2)**: Cross-App Access — 엔터프라이즈 ID provider와 MCP 서버 직결로 OAuth 플로우 자체를 매끄럽게.
- **Microsoft Foundry**: OAuth identity passthrough를 별도 명시 — *"개인 컨텍스트가 유지되도록 사용자별 위임"*.

다만 이 모든 발전이 향하는 종착점은 AI 자율 위임이 아니어야 합니다. 그 방향은 책임의 공백을 만듭니다. 종착점은 안전한 운용입니다. 내가 자는 동안 내 캐릭터가 빌런이 되지 않도록.

---

## 정리

- MCP 서버는 메이플 서버가 아니다. 내 PC가 띄우는 내 영역의 작은 서버 - 프로세스다
- 인터넷 상에 만드는 MCP 내 캐릭터는 운용이지 완전 위임이 아니다
- Agent라는 라벨에 묶이지 말고 AI가 운용하는 단위로 보자
- 개인 DT(데이터 정리) 없이는 개인 AX(캐릭터) 없다
- OpenClaw 같은 자율 위임 모델보다 MCP가 좋은 인터페이스인 이유는 보안 게이팅 때문이다

26년 남은 기간의 진짜 화두는 *"얼마나 자율적인 AI를 만드느냐"*가 아니라, *"얼마나 안전하게 운용 가능한 내 캐릭터를 만드느냐"*라고 봅니다.

시작은 단순합니다. 내 데이터 한 곳에 모으기. 그리고 그 위에 내 캐릭터 한 명 세우기. MCP는 그 캐릭터의 손과 발입니다.

---

## References

- GitHub MCP 17,600 토큰 측정 — Atlassian Labs (2026-04): [MCP Compression: Preventing tool bloat in AI agents](https://www.atlassian.com/blog/developer/mcp-compression-preventing-tool-bloat-in-ai-agents)
- Mitchell Hashimoto, *Harness Engineering* (26.1Q)
- Anthropic, [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) (2024-12)
- Andrej Karpathy, *for-loop가 달린 LLM* 비판 발언 (X, 2025)
- Kong, [DevWeek 2026 — MCP Servers & Delegated Auth](https://www.youtube.com/watch?v=mbZUq4nBFmw)
- [MCP Roadmap 2026 by David (MCP creator)](https://www.youtube.com/watch?v=kAVRFYgCPg0)
- Microsoft Foundry — [MCP Authentication](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/mcp-authentication)
