---
title: "맥미니 없이도 LLM 봇 만들기 — AWSKRUG 발표 미러로 만난 14가지 함정"
date: 2026-05-25T09:00:00+09:00
draft: false
tags: ["aws", "serverless", "lambda", "bedrock", "openclaw", "awskrug", "cdk", "docker"]
description: "AWSKRUG 이상현 님 발표 '맥미니 없이도 서버리스로 만드는 AI Cloud Agent' 를 처음부터 끝까지 미러 실습했다. 1시간 짜리 가이드를 따라했는데 14가지 함정에 14시간 걸렸다. Docker Desktop 28 OCI manifest, OpenClaw 2026.2.13 schema 변경, Anthropic use case 폼까지 — 진짜 만난 모든 함정과 자동화 스크립트, 그리고 14가지 함정을 12개로 자동화한 한국어 튜토리얼 레포 공개까지."
---

발표 한 편 보고 따라하면 1시간이면 끝날 줄 알았다. 결국 14시간 걸렸다.

AWSKRUG 의 이상현 님 ([AWS Serverless Hero](https://aws.amazon.com/developer/community/heroes/sanghyun-lee/)) 가 발표한 **"맥미니 없이도 서버리스로 만드는 AI Cloud Agent"** — 영상 시청 1시간이면 원리는 다 이해된다. 핵심 메시지가 명료하기 때문이다. **"LLM 에이전트를 24시간 켜놓는 맥미니/EC2 없이, AWS Lambda Container 로 호출당 1.35초만 돌리고 평소엔 $0 으로 운영하자."**

그래서 [원본 레포](https://github.com/serithemage/serverless-openclaw)를 클론해서 한 번 직접 띄워보기로 했다. 새 AWS 계정 만들고, 발표 자료 그대로 따라했다. 14시간 후에 봇이 답장을 보내왔다. 그 14시간 동안 발견한 함정 14가지가 이 글의 본문이다.

결과물은 [github.com/AI-Dico/aws-serverless-agent-ko](https://github.com/AI-Dico/aws-serverless-agent-ko) — 같은 길을 가려는 다음 사람이 함정 12개를 스크립트로 자동 회피하고, 사용자가 직접 처리해야 하는 건 2개만 남도록 정리한 한국어 빠른시작 가이드다.

## TL;DR

- 발표 미러 실습 = **AWS 새 계정 → Lambda Container 로 OpenClaw 띄우기 → Telegram 봇으로 Claude 응답 받기**
- 1시간 짜리 가이드인데 실제론 **14시간 + 함정 14가지** 통과해야 작동
- 가장 큰 함정 (4시간 소진): **Docker Desktop 28+ 가 OCI manifest 로 push 하는데 Lambda Container 는 Docker v2 만 받음**
- 두 번째 큰 함정: **Anthropic use case 폼** — AWS 가 모델 access 페이지를 deprecate 했지만 Anthropic 모델만은 별도 폼 제출 필수
- 결과 비용: **누적 $0.30** (AWS Free 6개월 $100 크레딧 내, 실 운영 ~$0.05/월)
- 정리된 [한국어 튜토리얼 레포](https://github.com/AI-Dico/aws-serverless-agent-ko)에 함정 12개 자동화 스크립트 + Claude Code skill

---

## 왜 맥미니가 아니라 서버리스인가

상시 가동되는 LLM 에이전트가 필요한 사람이 점점 늘고 있다. 카톡/Telegram 봇, MCP 도구를 가진 자동화, "OpenClaw 처럼 codex 류 코딩 에이전트를 클라우드 어디서나 호출" — 이런 시나리오가 다 그 부류다.

가장 단순한 답은 **맥미니나 EC2 t3.small 같은 작은 머신을 24시간 켜놓기**. 하지만:

- 맥미니 코로케이션: 월 $30~80
- EC2 t3.small: 월 $15 + 디스크 + 트래픽
- 둘 다 **유휴 시간에도 그대로 과금** — 메시지 하나도 안 보낸 새벽 6시간도 청구

이상현 님 발표의 핵심 아키텍처는 이 고정비를 **0** 으로 만든다:

```
사용자 → Telegram webhook → API Gateway → Lambda Container (OpenClaw 실행)
                                          ↓
                                          Bedrock Claude 호출 → 응답
                                          ↓
                                          S3 에 세션 저장
```

- Lambda Container 가 호출 시점에 컨테이너 부팅 (1.35초 콜드스타트, 0.12초 웜)
- 메시지 응답 후 자동 종료 → **$0 유휴**
- DynamoDB / S3 / API Gateway 다 PAY_PER_REQUEST → 안 쓰면 0원
- 듀얼 컴퓨트 옵션: 15분 넘는 작업은 Fargate Spot 으로 fallback

이론적으로 월 $1~2 면 충분하다. AWS Free 6개월 플랜의 $100 크레딧이면 약 200개월 — **16년치** 사용량이다.

이론은 그렇다. 실제는 좀 다르다.

---

## 함정 시작 — T1: KMS ≠ IAM Access Key

새 AWS 계정 만들고 가장 먼저 한 건 CLI 자격증명 발급이었다. AWS 콘솔 검색창에 "키 생성"이라고 치면 **KMS (Key Management Service) 키 생성 페이지가 뜬다**. 처음 보는 사람은 "AWS CLI 에서 쓸 키" 인 줄 알고 만들기 시작한다.

KMS 는 **데이터 암호화용** 키다. CDK 가 배포할 때 쓰는 건 **IAM Access Key** (Access Key ID + Secret) 인데, 이름이 비슷해서 30분 헤매기 좋다.

정답 경로:
1. AWS 콘솔 → **IAM** 검색
2. Users → 새 사용자 생성 (e.g. `cdk-deployer`)
3. **AdministratorAccess** 정책 첨부
4. 사용자 클릭 → **Security credentials** 탭
5. **Access keys** 섹션 → **Create access key** → **Command Line Interface (CLI)**
6. AKIA 로 시작하는 ID + 40자 Secret → **CSV 다운로드 (한 번만 보임)**

이게 `aws configure --profile dcode` 입력값이 된다. 안 받아두면 새로 만들어야 한다.

---

## T2: Bedrock model access 페이지는 deprecated

AWS Bedrock 콘솔의 "Model access" 페이지로 가서 Claude 모델 활성화하라는 안내가 여기저기 있다. 막상 가보면:

> "모델 접근 페이지는 더 이상 사용되지 않습니다. 이제 서버리스 파운데이션 모델은 계정에서 처음 실행될 때 모든 AWS 상용 리전에서 자동으로 활성화됩니다."

2025년 후반부터 AWS 가 정책 바꿨다. 그냥 `aws bedrock-runtime invoke-model` 한 번 호출하면 자동 활성화. 단, **Anthropic 모델은 사용 사례 폼 별도 제출 필요** (이게 T14 의 본질).

여기서 "그럼 폼은 어디서 내?" 라고 찾아헤매면 시간 또 빠진다. 답은: **모델 카탈로그에서 모델 카드 클릭 → "Available to request" 버튼**. 폼이 모달로 뜬다.

---

## T3: 신규 Claude 모델은 inference profile 만 지원

Bedrock 에 Haiku 4.5 호출 테스트하려고 모델 ID `anthropic.claude-haiku-4-5-20251001-v1:0` 로 invoke 했더니:

```
ValidationException: Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0
with on-demand throughput isn't supported.
Retry your request with the ID or ARN of an inference profile.
```

신규 모델 (Sonnet 4.5, Haiku 4.5, Opus 4.5+) 은 **cross-region inference profile** 만 지원. 모델 ID 에 prefix 가 붙어야 한다:

- ❌ `anthropic.claude-haiku-4-5-20251001-v1:0`
- ✅ `global.anthropic.claude-haiku-4-5-20251001-v1:0`

`global.` 외에도 지역별 `apac.`, `us.`, `eu.` prefix 가 있다. 한국에서는 `global.` 권장 (자동 라우팅).

확인 명령:
```bash
aws bedrock list-inference-profiles --region ap-northeast-2
```

---

## T4: SecretsStack 은 CFN Parameter 별도 주입 필수

CDK 배포 시작했다. `cdk deploy --all` 한 번에 6 stacks 다 올리려고 했다. 결과:

```
The following CloudFormation Parameters are missing a value:
BridgeAuthToken, OpenclawGatewayToken, TelegramBotToken, TelegramWebhookSecret
```

원본 코드의 `SecretsStack` 은 시크릿들을 **CFN parameter 로 주입받는다**. `cdk deploy` 그냥 돌리면 항상 실패. 다음과 같이 명시 주입 필요:

```bash
npx cdk deploy SecretsStack \
  --parameters "BridgeAuthToken=$(openssl rand -hex 32)" \
  --parameters "OpenclawGatewayToken=$(openssl rand -hex 32)" \
  --parameters "TelegramBotToken=$TELEGRAM_BOT_TOKEN" \
  --parameters "TelegramWebhookSecret=$(openssl rand -hex 32)" \
  --require-approval never
```

이후 `cdk deploy --all` 은 CloudFormation 이 parameter 자동 재사용 — 한 번만 명시하면 됨.

---

## T5: Lambda agent ECR repo 는 외부 자원 (chicken-and-egg)

SecretsStack 통과하고 다시 `cdk deploy --all`. 이번엔:

```
Source image 147885329473.dkr.ecr.ap-northeast-2.amazonaws.com/serverless-openclaw-lambda-agent:latest does not exist.
```

코드를 들여다보니 `lambda-agent-stack.ts` 가 ECR repo 를 `fromRepositoryName()` 으로 import — 즉 외부에서 미리 만들어져 있어야 한다. CDK 가 한 번에 ECR + Lambda 둘 다 만들려고 하면 chicken-and-egg.

해결:
1. ECR repo 수동 생성: `aws ecr create-repository --repository-name serverless-openclaw-lambda-agent --region ap-northeast-2`
2. Docker arm64 빌드 + ECR 푸시
3. 그 다음 `cdk deploy --all`

여기서 본격적인 함정이 시작된다.

---

## T11: Docker Desktop 28+ OCI manifest 문제 (4시간 소진한 본진)

`packages/lambda-agent/Dockerfile` 을 빌드하고 ECR 에 푸시했다. CDK deploy 다시 시도. 결과:

```
Resource handler returned message: "The image manifest, config or layer media type
for the source image ... is not supported.
(Service: Lambda, Status Code: 400)"
```

원인은 단순하지만 우회가 안 단순하다. **AWS Lambda Container 는 Docker manifest v2 schema 2 만 받는다**. OCI image manifest 는 거부한다. 그런데 Docker Desktop 28+ 의 containerd 기반 buildx 는 **무조건 OCI manifest 로 push 한다**.

AWS 공식 문서가 권장하는 회피책: `docker buildx build --provenance=false`. 그래서 시도했다:

```bash
docker buildx build --platform linux/arm64 --provenance=false --sbom=false \
  -f packages/lambda-agent/Dockerfile \
  -t $ECR_HOST/serverless-openclaw-lambda-agent:latest \
  --push .
```

ECR 확인:
```
imageManifestMediaType: application/vnd.oci.image.manifest.v1+json
```

여전히 OCI. `--provenance=false --sbom=false` 안 통함.

차례차례 시도한 것들:

1. **`--output type=image,oci-mediatypes=false`** — buildx 가 무시
2. **`default` driver + `--load` + `docker push`** — containerd 가 OCI 로 변환
3. **`DOCKER_BUILDKIT=0` legacy 빌더** — Docker 28 에서 무시됨
4. **`skopeo copy --format v2s2`** — `Unknown media type during manifest conversion` 에러
5. **`crane pull /tmp/img.tar` + `crane push`** — 타임아웃
6. **마지막: `regctl image mod --to-docker --replace`** — ✅ **성공**

```bash
brew install regclient
TOKEN=$(aws ecr get-login-password --region ap-northeast-2)
echo "$TOKEN" | regctl registry login $ECR_HOST --user AWS --pass-stdin
regctl image mod --to-docker --replace $ECR_HOST/serverless-openclaw-lambda-agent:latest
```

`regctl image mod --to-docker` 가 ECR 의 manifest 만 in-place 로 OCI → Docker v2 변환. 모든 layer 가 이미 docker mediatype 이라 in-place 가능. **이게 진짜 해결책**.

근본 해결 옵션도 있다 (옵션이 있다는 걸 알아내는 데 4시간 걸린 것):

> Docker Desktop → Settings → General → **"Use containerd for pulling and storing images" 체크 해제** → Apply & restart

이러면 buildx 가 처음부터 Docker v2 manifest 로 push. 단, Docker Desktop 의 일부 신기능 못 씀.

[튜토리얼 레포의 07-build-lambda-image.sh](https://github.com/AI-Dico/aws-serverless-agent-ko/blob/main/scripts/07-build-lambda-image.sh) 가 자동으로 manifest 검증 + 필요 시 regctl 변환 처리한다.

---

## T12 / T13: Lambda Container 의존성 충돌

T11 해결하고 Lambda 호출. 새 에러:

```
Error: Cannot find module '@smithy/smithy-client'
Require stack:
  /var/task/node_modules/@aws-sdk/lib-dynamodb/dist-cjs/index.js
```

Lambda runtime 은 `@aws-sdk/*` 만 제공하고 `@smithy/*` (그 transitive deps) 는 제공 안 한다. 원본 `Dockerfile` 이 `lib-dynamodb` 만 복사하고 `@smithy` 누락. (**T12**)

수정: builder 의 `@smithy/*` 도 같이 복사 → 빌드.

다음 에러:
```
Error [ERR_PACKAGE_PATH_NOT_EXPORTED]:
Package subpath './retry' is not defined by "exports"
in /var/task/node_modules/@smithy/core/package.json
```

이번엔 **OpenClaw 의 `@smithy/core`** 와 **`@aws-sdk/lib-dynamodb` 의 `@smithy/core`** 가 버전 충돌. Dockerfile 에서 두 패키지를 따로 설치하면 의존성 tree 가 어긋난다. (**T13**)

해결: 둘을 **하나의 `npm install` 로 묶기** → npm 이 dep tree 자동 정리.

```dockerfile
# ❌ 안 됨
RUN npm install openclaw@${OPENCLAW_VERSION}
COPY --from=builder /build/node_modules/@aws-sdk/lib-dynamodb/ ...
COPY --from=builder /build/node_modules/@smithy/ ...

# ✅ 됨
RUN npm install openclaw@${OPENCLAW_VERSION} @aws-sdk/lib-dynamodb
```

이렇게 nested 로 잘 들어가서 OpenClaw 의 `@smithy/core` 와 lib-dynamodb 의 다른 버전이 평화롭게 공존한다.

---

## T14: Anthropic Use case 폼 — 정작 마지막에 만나는 함정

빌드+배포 다 통과. 웹훅 등록. Telegram 봇한테 "안녕" 메시지 보냈다. **답장이 왔다.**

```
Model use case details have not been submitted for this account.
Fill out the Anthropic use case details form before using the model.
If you have already filled out the form, try again in 15 minutes.
```

응답이 오긴 왔다 — 그게 메시지 내용이었을 뿐이다. T2 에서 "Bedrock model access 페이지는 deprecated" 했지만, **Anthropic 모델만은 첫 호출 시 별도 use case 폼 제출**. AWS 가 그 정보를 Anthropic 에 전달하는 정책.

해결 (콘솔에서 5분):
1. https://ap-northeast-2.console.aws.amazon.com/bedrock/home?region=ap-northeast-2#/model-catalog
2. **Anthropic / Claude Haiku 4.5** 카드 클릭 → **"Available to request"**
3. 폼 입력:
   - Company name
   - Industry
   - Intended users (Internal / External)
   - Use case description (500자 이내)
4. **Submit** → 보통 즉시 활성화

이 폼만 마지막 줄에 추가하면 일반적인 가이드는 "T1 ~ T14 14가지 함정" 으로 종결된다. 1시간이면 따라할 수 있다.

---

## MCP 통합 시도 — 정직한 실패 보고 (T18 ~ T21)

여기까지가 "**Lambda 채팅 봇**" 까지 검증된 영역이다. 욕심이 더 났다. 봇이 **ainote MCP** (내가 만든 메모리/노트 MCP 서버) 를 호출해서 "메모리에 'AWS 관련' 검색해줘" 같은 명령을 처리하게 하고 싶었다.

OpenClaw 가 MCP 를 지원한다는 말은 docs 와 GitHub issue 에 가득하다. Perplexity 깊은 검색까지 돌려서 "MCP server 등록 방법" 까지 받았다.

> `openclaw.json` 의 `mcp.servers` 키에 `{ url, transport: "streamable-http", headers: { Authorization: "..." } }` 형태로 등록하면 됨.

그래서 `patch-config.ts` 에 mcp 키 추가하는 로직 넣고, ComputeStack 에 ainote MCP 환경변수 주입하고, AGENT_RUNTIME=both 로 Fargate Spot 띄우고… 빌드 + 배포. Fargate task 가 부팅하다가 죽었다:

```
Config invalid
File: ~/.openclaw/openclaw.json
Problem:
  - <root>: Unrecognized key: "mcp"
```

**T18: 우리가 가진 정보가 OpenClaw 2026.2.13 현재 schema 와 일치하지 않는다.** Perplexity 도, Anthropic Claude 도 알려준 답이 다 어긋난다. OpenClaw 가 빠르게 발전 중이라 docs 와 실제가 안 맞는 듯.

CLI 로 시도. `openclaw mcp set ainote '{...}'` → **T20**:

```
error: unknown command 'mcp'
(Did you mean acp?)
```

`mcp` subcommand 가 없다. `acp` (Agent Control Protocol) 라는 새로운 게 있는 모양인데, 그건 또 별개. 빠른 검증 단계에서 다음 함정도 동시에 만났다:

- **T19**: ComputeStack 의 Bridge 가 `CALLBACK_URL` env 누락으로 즉시 죽음 (ApiStack 의 WebSocket URL 을 동적 inject 해야)
- **T21**: OpenClaw 가 `TELEGRAM_BOT_TOKEN` 환경변수 감지해서 자기 채널로 attach → API GW telegram-webhook 과 충돌

4가지 함정이 동시에 막혀 있는 상태에서 우리는 멈췄다. 시간을 더 쓰는 것보다 **솔직하게 보고하기**를 택했다.

**[튜토리얼 레포의 README §6](https://github.com/AI-Dico/aws-serverless-agent-ko#6-후속-mcp-도구-통합-실패-사례--미해결)** 에는 시도한 경로와 발견한 함정 4가지 + 다음 도전자가 시도할 우회 전략 (Lambda 안 직접 fetch / Bedrock AgentCore Runtime) 까지 다 기록했다. 누가 이 길로 들어와도 같은 4시간을 또 쓰지 않게.

---

## 결과 정리

**검증 완료**: Lambda 채팅 봇이 Telegram 에서 Claude Haiku 4.5 응답을 받는다. 실측:

- Lambda Container 콜드스타트: **643ms** (init 포함)
- 웜 응답: **10~107ms**
- 전체 응답 시간 (Telegram 메시지 → 봇 응답): **~1.5초 (콜드)** / **~600ms (웜)**
- 누적 비용 (2일 진행 + 검증): **$0.30** (Free 크레딧 내)
- 월 운영 예상: **$0.05 + 사용량당** (Haiku 메시지당 $0.003)

**미해결**: ainote MCP 통합 — OpenClaw 2026 schema 재조사 필요.

**산출물**:
- 공개 튜토리얼 레포 [AI-Dico/aws-serverless-agent-ko](https://github.com/AI-Dico/aws-serverless-agent-ko)
- 9단계 자동화 스크립트 (`00-prereqs.sh` ~ `99-teardown.sh`)
- 머메이드 다이어그램 7개 + 함정 14가지 + 에러 메시지 → 해결 매핑 표
- Claude Code skill (`skills/aws-serverless-agent/SKILL.md`) — 다음에 다시 할 때 자동화
- 발견한 모든 함정 + 시도/실패 사례까지 정직 기록

다음 사람이 따라할 때 사용자 직접 해야 하는 건 **2가지** 뿐이다:
1. **T1**: AWS 콘솔에서 IAM Access Key 발급 (KMS 와 헷갈리지 말 것)
2. **T14**: Bedrock 콘솔에서 Anthropic Use case 폼 제출 (5분)

나머지 12개는 스크립트가 자동 회피한다.

---

## 회고 — 1시간 가이드가 14시간이 된 이유

1. **소프트웨어 정보의 빠른 진부화** — 발표 자료, 원본 README, Anthropic Claude 의 학습 데이터, Perplexity 검색 결과까지 4중으로 다 다른 시기의 정보. Docker Desktop 28, OpenClaw 2026.2.13, AWS Bedrock 정책 모두 최근 6개월 안에 바뀜.

2. **검색 결과의 신뢰도** — "MCP server 어떻게 등록?" 같은 구체적 질문에 대해 LLM 들이 자신 있게 틀린 답을 준다. 검증 안 하면 시간 빠진다.

3. **함정의 비독립성** — T11 (Docker manifest) 해결 후 T12 (smithy 누락) → T13 (version conflict) → T14 (Anthropic 폼). 각 함정이 다음 함정을 가리고 있어서 한 번에 다 안 보인다.

4. **그래도 진짜 가치 있는 것 — 정리된 산출물** — 14시간 쓴 게 **다음 사람의 1시간** 으로 압축됐다. 같은 길 또 가는 사람들에게 시간 13시간 + 4시간 OCI manifest 삽질 안 시킬 수 있다.

발표 자료가 좋아도, 코드가 공개되어 있어도, 6개월 지나면 함정이 새로 생긴다. 그래서 **실배포 후 함정 기록** 자체가 산출물이 된다.

[github.com/AI-Dico/aws-serverless-agent-ko](https://github.com/AI-Dico/aws-serverless-agent-ko) — Star/Fork 환영. 더 좋은 우회법 있으면 PR 환영. MCP 통합 성공하시면 알려주세요.

---

## 참고

- 원본 발표: [serithemage/serverless-openclaw](https://github.com/serithemage/serverless-openclaw) — 이상현 (AWSKRUG, AWS Serverless Hero)
- 한국어 튜토리얼: [AI-Dico/aws-serverless-agent-ko](https://github.com/AI-Dico/aws-serverless-agent-ko)
- AWS Lambda Container 가이드: [docs.aws.amazon.com — Working with Lambda container images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- Bedrock inference profiles: [docs.aws.amazon.com — Use a cross-region inference profile](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html)
