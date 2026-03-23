---
title: "Claude Code Channels 완전 가이드 — Telegram으로 로컬 AI 세션 원격 조종하기"
date: 2026-03-22
draft: false
tags: ["Claude Code", "Telegram", "AI", "개발환경", "자동화", "MCP", "원격개발"]
description: "Claude Code Channels로 Telegram 봇을 통해 로컬 Mac의 Claude Code 세션을 원격 제어하는 방법. 설치 과정에서 만난 에러, 올바른 명령어, tmux 영구 실행, macOS 재부팅 자동시작, OpenClaw 비교까지 삽질 기록을 전부 담았다."
faq:
  - q: "Claude Code Channels 실행 후 Telegram 메시지를 보내도 응답이 없습니다. 원인은?"
    a: "--channels 플래그 없이 실행했을 가능성이 높습니다. 환경변수에 토큰만 설정하고 일반 claude로 실행하면 Bun 서브프로세스가 뜨더라도 채널 이벤트가 비활성화됩니다. 반드시 claude --channels plugin:telegram@claude-plugins-official 명령어로 실행해야 하며, 시작 화면에 'Listening for channel messages from:' 메시지가 있는지 확인하세요."
  - q: "--dangerously-skip-permissions 플래그는 얼마나 위험한가요?"
    a: "이 플래그를 사용하면 Telegram으로 받은 메시지가 로컬 머신에서 파일 읽기/쓰기, 쉘 명령 실행 등 거의 모든 작업을 승인 없이 수행할 수 있습니다. 3계층 보안의 발신자 allowlist로 '누가 보낼 수 있는가'는 통제하지만, '무엇을 실행하는가'는 통제하지 않습니다. 개인 개발 머신에서 혼자 사용한다면 관리 가능한 위험이지만, 프로덕션 서버나 민감한 자격증명이 있는 머신에서는 사용하지 않는 것이 좋습니다."
  - q: "여러 Mac에서 같은 Telegram 봇을 쓸 수 있나요?"
    a: "봇 토큰은 하나지만 여러 머신에서 동시에 같은 토큰으로 Claude Code Channels를 실행할 수 있습니다. 단, 메시지는 가장 최근에 poll을 시작한 인스턴스가 받게 되며, 여러 인스턴스가 동시에 폴링하면 메시지가 분산되어 혼동이 생길 수 있습니다. 머신별로 별도 봇을 만들어 구분하거나, 하나의 머신만 활성화하는 것을 권장합니다."
---

2026년 3월 20일, Anthropic이 **Claude Code Channels** 리서치 프리뷰를 공개했다. 한마디로 요약하면, Telegram이나 Discord에서 메시지를 보내면 집에 있는 내 Mac의 Claude Code가 코드를 짜고 파일을 수정한 뒤 결과를 답장으로 보내주는 기능이다.

폰에서 "auth.py 버그 고쳐줘" 보내면 → 맥미니 Claude가 코드 파일 열고 수정하고 → "완료했습니다, 커밋했어요" 답장이 오는 식이다.

설정하면서 꽤 삽질을 했다. 이 글은 그 과정을 그대로 기록한 문서다.

---

## Claude Code Channels가 뭔가

### 기본 아키텍처

Claude Code Channels는 **MCP(Model Context Protocol) 기반 플러그인**이다. Claude Code 세션 안에 Telegram 또는 Discord와 연결된 MCP 서버를 서브프로세스로 띄우고, 외부 메시지를 세션 안으로 밀어넣는(push) 구조다.

```
폰 Telegram DM
      ↓
Telegram Bot API 폴링 (Bun 스크립트)
      ↓
MCP 서버 → Claude Code 세션에 이벤트 push
      ↓
Claude가 로컬 파일/Git/MCP 도구로 작업
      ↓
결과를 Telegram으로 reply
```

핵심은 **코드가 로컬에서 실행된다**는 점이다. 클라우드 서버가 아니라 내 맥미니의 파일시스템, Git, MCP 설정을 그대로 쓴다. Telegram은 그냥 입력창 역할만 한다.

### 기존 도구들과 뭐가 다른가

Anthropic이 공식 문서에서 직접 비교한 내용을 보면:

| 도구 | 특징 |
|------|------|
| Claude.ai 웹 세션 | stateless, 매번 새 대화 |
| Slack 통합 | 팀 채팅 안에서 Claude |
| MCP 서버 | Claude가 도구를 호출 |
| Remote Control | 다른 기기에서 같은 세션 접속 |
| **Channels** | **외부 소스의 이벤트를 실행 중인 세션으로 push** |

Channels만의 차별점은 "이미 열려있는 세션"에 이벤트를 주입한다는 것이다. 세션이 프로젝트 컨텍스트를 가지고 있고, MCP 서버도 연결된 상태에서 외부 메시지를 받는다.

---

## 삽질 기록 — 잘못된 명령어들

### 첫 번째 시도: 에러

```bash
claude --channel telegram
# error: unknown option '--channel'
```

`--channel`이 아니라 `--channels`(복수형)이고, 플러그인 전체 경로를 줘야 한다.

### 두 번째 시도: 작동하지만 채널 비활성화

```bash
TELEGRAM_BOT_TOKEN=xxx claude
```

실행은 되고 토큰도 저장되는데, Telegram 메시지가 세션으로 전달되지 않는다. `--channels` 플래그 없이 실행하면 플러그인은 연결되지만 채널 이벤트가 비활성화된 상태다.

**올바른 명령어:**

```bash
claude --channels plugin:telegram@claude-plugins-official
```

이것만 기억하면 된다.

---

## 전체 설치 과정

### 사전 요구사항 확인

```bash
claude --version  # 2.1.80 이상
bun --version     # Bun 런타임 필요 (없으면 설치)
```

Bun이 없다면:
```bash
curl -fsSL https://bun.sh/install | bash
```

**주의사항:**
- claude.ai Pro 또는 Max 구독 필요 (API Key 방식 불가)
- Team/Enterprise는 조직 관리자가 먼저 채널 활성화 필요

### 1단계: Telegram 봇 생성

Telegram에서 `@BotFather`를 찾아 `/newbot` 명령어를 보낸다. 봇 이름과 username(끝에 `bot`이 붙어야 함)을 설정하면 토큰이 발급된다.

```
봇 생성 완료
Token: 1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

이 토큰은 보안상 중요하다. 공개 저장소나 채팅에 올리지 말 것.

### 2단계: 플러그인 확인 및 설치

공식 마켓플레이스가 등록되어 있다면:

```bash
claude plugin list  # 설치된 플러그인 확인
claude plugin install telegram@claude-plugins-official
```

마켓플레이스가 없다면:
```
/plugin marketplace add anthropics/claude-plugins-official
```

설치 확인:
```bash
claude plugin list
# ❯ telegram@claude-plugins-official
#   Status: ✔ enabled
```

### 3단계: 봇 토큰 저장

토큰을 Claude 세션 안에서 설정하거나, 직접 파일로 저장한다.

**방법 A: Claude 세션 안에서**
```
/telegram:configure <봇토큰>
```

**방법 B: 직접 파일 생성**
```bash
mkdir -p ~/.claude/channels/telegram
echo "TELEGRAM_BOT_TOKEN=<봇토큰>" > ~/.claude/channels/telegram/.env
chmod 600 ~/.claude/channels/telegram/.env  # 권한 제한
```

### 4단계: 채널 활성화로 Claude 실행

```bash
claude --channels plugin:telegram@claude-plugins-official
```

실행하면 이런 메시지가 뜬다:
```
Listening for channel messages from: plugin:telegram@claude-plugins-official
Experimental · inbound messages will be pushed into this session
```

### 5단계: 페어링

1. Telegram에서 내 봇에 아무 메시지나 DM으로 보낸다
2. 봇이 6자리 페어링 코드를 응답한다: `Pairing required — run in Claude Code: /telegram:access pair ea27d7`
3. Claude Code 세션에서 승인한다:

```
/telegram:access pair ea27d7
```

코드가 승인되면 Telegram에 "Paired! Say hi to Claude."가 온다.

### 6단계: 보안 잠금

페어링 후 반드시 allowlist 모드로 전환한다:

```
/telegram:access policy allowlist
```

이렇게 하면 내 Telegram ID만 봇에 메시지를 보낼 수 있다. 다른 사람이 DM을 보내도 조용히 무시된다(에러 없이 drop).

---

## 삽질 기록 — 메시지 응답이 안 오는 문제

설치를 완료하고 페어링도 됐는데, 메시지를 보내도 응답이 없었다.

**원인:** `TELEGRAM_BOT_TOKEN=xxx claude`로 실행해서 `--channels` 플래그가 없었기 때문이다. 세션은 살아있고 Bun 서브프로세스도 실행되어 있는데, 채널 이벤트 수신이 비활성화된 상태였다.

확인 방법:
```bash
ps aux | grep bun  # Bun telegram 프로세스가 있어야 함
```

채널이 제대로 활성화됐을 때 Claude 시작 화면에 이 메시지가 있어야 한다:
```
Listening for channel messages from: plugin:telegram@claude-plugins-official
```

이 줄이 없으면 채널이 비활성화 상태다.

---

## 영구 실행 설정

### 문제: 터미널 닫으면 봇도 꺼진다

Claude Code Channels는 **세션이 열려있을 때만 작동**한다. 터미널을 닫거나 Claude 프로세스가 종료되면 Telegram 메시지를 받을 수 없다. 더 중요한 것은 **오프라인 중에 온 메시지는 영구 소실**된다. 메시지 큐가 없다.

### 해결책 1: tmux 영구 실행

```bash
tmux new -s claude-channel
# tmux 안에서:
while true; do claude --channels plugin:telegram@claude-plugins-official; sleep 5; done
```

세션이 충돌하거나 오류가 나도 5초 후 자동으로 재시작된다.

나중에 세션에 다시 붙으려면:
```bash
tmux attach -t claude-channel
```

detach는 `Ctrl+B, D`.

### 해결책 2: macOS 재부팅 후 자동시작 (Login Items)

Mac이 꺼졌다 켜져도 자동으로 시작되게 하려면 스크립트를 만들고 Login Items에 등록한다.

**스크립트 생성** (`~/scripts/start-claude-channel.sh`):

```bash
#!/bin/bash
sleep 10  # 로그인 직후 네트워크/keychain 준비 대기

# 기존 세션 정리
tmux kill-session -t claude-channel 2>/dev/null

# 새 tmux 세션 시작
tmux new-session -d -s claude-channel -x 220 -y 50

# Claude Channels 루프 실행
tmux send-keys -t claude-channel \
  "while true; do /opt/homebrew/bin/claude --dangerously-skip-permissions --channels plugin:telegram@claude-plugins-official; sleep 5; done" \
  Enter
```

```bash
chmod +x ~/scripts/start-claude-channel.sh
```

**Login Items 등록:**
```bash
osascript -e 'tell application "System Events" to make new login item at end with properties {path:"/Users/<username>/scripts/start-claude-channel.sh", hidden:true}'
```

또는 시스템 설정 → 일반 → 로그인 항목에서 수동으로 추가한다.

---

## 권한 문제와 현실적인 선택

### 권한 프롬프트 문제

Claude Code가 파일 쓰기, 쉘 실행, 빌드 같은 작업을 할 때 터미널에서 권한 확인 프롬프트가 뜬다. Telegram에서는 이 프롬프트에 응답할 수 없다. 세션이 멈춘다.

원격에서 실질적으로 무언가를 시키려면 대부분 이 플래그가 필요하다:

```bash
claude --dangerously-skip-permissions --channels plugin:telegram@claude-plugins-official
```

이름이 경고처럼 생겼는데, 실제로 경고다. 이 플래그를 쓰면 allowlist에 있는 발신자의 메시지가 Claude가 내 머신에서 무엇이든 실행할 수 있게 된다. 개인 프로젝트에서 혼자 쓴다면 관리 가능한 위험이지만, 프로덕션 인프라에 연결된 머신이라면 신중히 생각해야 한다.

### 현실적인 접근법

- **자리에 있을 때**: 일반 모드 실행 (권한 확인 있음, 보안 높음)
- **자리 비울 때**: `--dangerously-skip-permissions` (완전 자동화, 위험 감수)

---

## 보안 모델 3계층

Claude Code Channels의 보안은 3계층으로 구성된다.

**1계층: 발신자 allowlist**
페어링 플로우를 완료한 Telegram 사용자(숫자 user ID로 식별)만 메시지 전달 가능. 미승인 메시지는 에러 없이 조용히 drop된다.

**2계층: 세션별 opt-in**
`--channels` 플래그를 명시해야만 채널이 활성화된다. 플래그 없이 실행하면 MCP 서버는 연결되지만 채널 이벤트는 수신하지 않는다. 내 지식 없이 채널이 활성화되는 일이 없다.

**3계층: 플러그인 whitelist**
`--channels`는 Anthropic이 승인한 플러그인만 허용한다. 현재 Telegram, Discord, Fakechat(로컬 테스트용) 세 가지뿐이다. 직접 만든 채널을 테스트하려면 `--dangerously-load-development-channels` 플래그가 필요하고, 다른 사람에게 배포하려면 Anthropic 심사를 거쳐야 한다.

**아킬레스건:**
3계층이 "누가 메시지를 보낼 수 있는가"는 보호하지만, "Claude가 메시지를 받은 후 무엇을 하는가"는 보호하지 않는다. `--dangerously-skip-permissions`를 쓴 상태에서 allowlist에 있는 발신자의 모든 메시지는 로컬 머신에서 임의 작업을 실행할 수 있다.

---

## Claude Code Channels vs OpenClaw 비교

설치하면서 자연스럽게 기존 도구인 OpenClaw와 비교하게 됐다.

| 항목 | Claude Code Channels | OpenClaw |
|------|---------------------|----------|
| 개발 주체 | Anthropic (공식) | 커뮤니티 |
| 지원 플랫폼 | Telegram, Discord | Telegram, Discord, iMessage, WhatsApp, Slack 등 |
| 보안 모델 | 3계층 공식 설계 | 보안 우회 논란 있음 |
| 세션 지속성 | 세션 유지 필요 | 24/7 지속 세션 |
| 구독 필요 | claude.ai Pro/Max | 오픈소스, API Key |
| 설정 복잡도 | 중간 (CLI 몇 개) | 높음 (자체 서버 운영) |
| 프로젝트 컨텍스트 | Claude Code 세션 공유 | API 레이어, 별개 |
| 커스텀 채널 | 프리뷰 제한 | 자유로움 |

**어떤 걸 쓸까:**
- "가끔 폰에서 코딩 작업 시키고 싶다, 보안이 중요하다" → **Channels**. 공식 지원, 3계층 보안, 간단한 설정.
- "iMessage/WhatsApp 필수, 24/7 지속 세션, 다양한 AI 모델 쓰고 싶다" → **OpenClaw**. 플랫폼 지원이 넓고 모델 선택 자유도 높다.
- "Docker 컨테이너로 격리된 환경 원한다" → **NanoClaw**. 호스트 파일시스템을 AI가 직접 건드리지 않는다.

VentureBeat가 "OpenClaw killer"라고 표현했지만, 실제로는 대체보다 보완 관계에 가깝다.

---

## 알려진 함정들

### 1. Telegram vs Discord 차이

- **Telegram**: 히스토리 API 없음. 대화 기록이 없어서 긴 대화 맥락 유지가 약하다.
- **Discord**: 메시지 히스토리 있음, 설정이 더 복잡하지만 대화 연속성이 좋다.

빠른 단발성 요청은 Telegram, 맥락이 필요한 긴 작업은 Discord가 낫다.

### 2. DISABLE_TELEMETRY 설정 함정

Claude Code 설정에 `DISABLE_TELEMETRY`가 설정되어 있으면 값이 `0`이어도 채널이 차단된다. "비활성화를 비활성화"가 아니라 키 자체를 삭제해야 한다.

```bash
# 잘못된 수정 (여전히 차단됨)
DISABLE_TELEMETRY=0

# 올바른 수정 (키 삭제)
# settings.json에서 해당 키를 완전히 제거
```

### 3. 오프라인 메시지 소실

메시지 큐가 없다. 세션이 닫혀있는 동안 온 메시지는 되돌릴 수 없다. tmux + while 루프로 다운타임을 최소화하는 것이 현실적인 대응이다.

### 4. 첨부파일 기본 차단

Telegram과 Discord 모두 첨부파일은 기본으로 차단된다. 이미지나 파일을 Claude에 전달하려면 추가 설정이 필요하다.

---

## 실전 활용 시나리오

### 모바일 코딩

맥미니에 tmux 세션을 상시 실행해두고, 외출 중 폰에서:
- "auth.py JWT 검증 버그 고쳐줘" → Claude가 파일 수정, 커밋, 결과 답장
- "test 돌리고 결과 알려줘" → Claude가 테스트 실행, 요약 답장

### CI 파이프라인 자동 대응

Sentry 알림이나 빌드 실패 webhook을 Claude Code 세션으로 연결하면 (커스텀 채널 기능, 현재 프리뷰 제한), 로그 분석부터 자동 수정 PR까지 자동화할 수 있다.

### 멀티 프로젝트 모니터링

여러 프로젝트의 알림을 하나의 Claude Code 세션으로 집중시켜, Claude가 우선순위를 판단하고 Telegram으로 요약 답장을 보내게 한다.

---

## 현재 한계와 로드맵

리서치 프리뷰 단계라 몇 가지 제한이 있다:

- **플랫폼 제한**: Telegram, Discord만 공식 지원. Slack, WhatsApp, iMessage는 없다.
- **커스텀 채널**: 프리뷰 중에는 개발 플래그 필요, 배포 불가.
- **인증**: API Key 불가, claude.ai 계정 필요.
- **세션 지속성**: 항상 세션 열어둬야 함, 영구 백그라운드 모드 없음.

API 안정화는 2026년 Q2~Q3 예정이라고 한다.

---

## 결론

Claude Code Channels는 완벽하지 않다. 세션을 계속 켜둬야 하고, 오프라인 메시지는 소실되며, 권한 프롬프트 문제로 실질적인 원격 작업에는 `--dangerously-skip-permissions`가 거의 필수다.

그럼에도 **공식 도구라는 점에서 오는 신뢰성**, **Claude Code 세션과 완전히 통합된 컨텍스트**, **5분이면 끝나는 설정**은 확실한 장점이다. OpenClaw처럼 별도 서버를 운영하거나 복잡한 설정을 할 필요 없이, 지금 쓰는 Claude Code에 플래그 하나 추가하는 것만으로 Telegram 원격 제어가 된다.

폰에서 Telegram 보내면 집 맥미니가 코딩한다는 게 신기하긴 하다.

---

## 자주 묻는 질문 (FAQ)

### Q: 설치 후 Telegram 메시지를 보내도 Claude가 응답하지 않습니다. 어떻게 디버깅하나요?

가장 먼저 Claude Code 시작 화면에 `Listening for channel messages from: plugin:telegram@claude-plugins-official` 메시지가 있는지 확인한다. 이 줄이 없으면 `--channels` 플래그 없이 실행된 것이다. 다음으로 `ps aux | grep bun`으로 Bun 서브프로세스가 실행 중인지 확인한다. Bun이 없으면 Telegram 폴링 자체가 되지 않는다. 마지막으로 페어링이 완료된 상태인지 확인한다. Telegram에서 봇에게 DM을 보내면 페어링 코드를 요구하는 메시지가 와야 하며, 그 코드를 `/telegram:access pair <코드>` 명령으로 승인해야 한다.

### Q: `--dangerously-skip-permissions`는 얼마나 위험한가요? 꼭 써야 하나요?

이 플래그를 사용하면 allowlist 발신자의 Telegram 메시지가 파일 쓰기, 쉘 실행, Git 커밋 등 거의 모든 로컬 작업을 권한 확인 없이 수행할 수 있다. 개인 개발 머신에서 혼자 사용한다면 관리 가능한 위험이다. 그러나 반드시 먼저 `/telegram:access policy allowlist`로 내 Telegram ID만 허용하도록 설정해야 한다. 민감한 API 키, SSH 키, 프로덕션 자격증명이 있는 머신이라면 권한 확인이 있는 일반 모드로 실행하되, 터미널에서 직접 응답할 수 있는 환경에서만 사용하는 것이 안전하다.

### Q: 여러 Mac에서 같은 Telegram 봇 토큰을 쓸 수 있나요?

기술적으로는 가능하지만 권장하지 않는다. 하나의 봇 토큰에 여러 인스턴스가 동시에 폴링하면 메시지가 인스턴스 사이에 무작위로 분산되어, 어느 머신에서 작업이 처리됐는지 파악하기 어렵다. 맥북과 맥미니 같이 여러 머신을 쓴다면 머신별로 별도 봇(`@mybot_macmini`, `@mybot_macbook`)을 만들거나, 한 번에 하나의 머신만 채널을 활성화하는 방식으로 운영하는 것이 깔끔하다.

---

## 관련 이슈 및 추가 팁

### 작업 지시 프롬프트 템플릿 패턴

Telegram에서 Claude에게 작업을 지시할 때 구체적인 컨텍스트를 함께 줄수록 결과가 좋다. 다음과 같은 템플릿을 만들어두면 유용하다:

```
[프로젝트]: tennis_bracket
[작업]: auth.rb에서 JWT 토큰 만료 처리 버그 수정
[확인]: 수정 후 bundle exec rspec spec/auth_spec.rb 실행해서 결과 알려줘
```

Claude Code 세션이 이미 특정 프로젝트 디렉토리에서 열려있다면 `[프로젝트]` 부분을 생략해도 된다. 세션이 가진 컨텍스트(`CLAUDE.md`, MCP 설정 등)가 자동으로 활성화된 상태에서 작업이 실행된다.

### Telegram vs Discord 선택 기준

간단한 단발성 요청(`"이 함수 리팩토링해줘"`, `"빌드 에러 원인 찾아줘"`)이라면 Telegram이 더 편리하다. 봇과의 DM 형식으로 빠르게 메시지를 주고받을 수 있다. 반면 여러 사람이 함께 Claude에게 요청을 보내거나 대화 히스토리를 참고하며 진행하는 긴 작업이라면 Discord가 낫다. Discord는 메시지 히스토리가 보존되어 Claude가 이전 대화 맥락을 이어받을 수 있고, 스레드 기능으로 작업 단위를 구분하기도 좋다.
