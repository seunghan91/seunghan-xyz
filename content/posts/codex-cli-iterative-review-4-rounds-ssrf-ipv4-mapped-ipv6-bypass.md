---
title: "Codex CLI 4 라운드 코드 리뷰 — 매 라운드마다 새 P1이 나온 이유"
date: 2026-05-21T14:38:01+09:00
draft: false
tags: ["codex-cli", "code-review", "ssrf", "claude-code", "skill"]
description: "Codex CLI로 PR 한 개를 4 라운드 리뷰했더니 매 라운드 새 P1 finding이 나왔다. SSRF guard 첫 fix는 IPv4-mapped IPv6에 뚫리고, 그 fix는 robots.txt 별도 fetch에 뚫렸다. 1 라운드 통과로 머지하면 안 되는 이유 + 자동화 스킬로 박은 6가지 함정."
---

큰 PR을 받았다. 8 commits, 73 files, +4484 / -239 lines. 외부 LLM이 만든 가지 분석용 브랜치라 내가 모르는 영역이 많았다. 그냥 머지 버튼 누르긴 무서워서 Codex CLI로 리뷰부터 돌렸다.

1 라운드 끝나니까 `[P1]` 2 건이 나왔다. 고쳤다. "이제 끝났겠지" 하고 푸시했다. 2 라운드를 또 돌렸다. 새 `[P1]` 2 건이 나왔다. 또 고쳤다. 3 라운드. 또 `[P1]`. 4 라운드도 마찬가지.

매 라운드 새 P1이 나오는 게 우연일 수도 있다고 생각했는데, 검색해보니까 이게 정상 패턴이었다. 그래서 머지까지 가는 길이 4 라운드 + 11 fix commit로 길어졌지만, 만약 1 라운드에서 멈췄으면 production에 SSRF 우회 2 개가 그대로 흘러갔을 거다.

이 포스트는 그 4 라운드를 commit by commit으로 풀어쓴 기록이다. 그리고 이 워크플로를 자동화 스킬로 박으면서 발견한 6 가지 함정도 같이.

---

## Codex CLI 코드 리뷰가 뭐길래

Codex CLI는 OpenAI의 코드 리뷰 도구다 (`npm install -g @openai/codex`). 핵심 명령어 하나:

```bash
codex review --base main -c 'model_reasoning_effort="high"' --enable web_search_cached
```

브랜치를 base와 비교해서 diff를 읽고, 보안 / correctness / policy 이슈를 `[P1]` (즉시 차단), `[P2]` (follow-up), `[P3]` (suggestion) 등급으로 출력한다. "200 IQ autistic developer가 review한다"는 농담이 있는데, 실제로 써보면 그 비유가 정확하다.

내가 쓰는 패턴은 Claude Code 안에서 background job으로 띄우는 거다:

```bash
codex review --base main -c 'model_reasoning_effort="high"' \
  --enable web_search_cached 2>/tmp/codex-err.txt > /tmp/codex-out.txt &
```

5 분 쯤 걸린다. 그 사이에 Claude는 다른 거 한다. 끝나면 결과 읽고 P1만 골라서 고치고 push.

---

## Round 1 — 가장 명백한 것들

첫 라운드에서 나온 P1 2 건과 P2 1 건:

| 등급 | 위치 | 이슈 |
|---|---|---|
| P1 | `user_url_imports_controller.rb:64` | 로그인 사용자가 임의 URL 입력 → 서버가 fetch → SSRF |
| P1 | `config/environments/production.rb:86-88` | Production이 r2 (S3-compatible) 서비스로 default 설정인데 Gemfile에 `aws-sdk-s3` 없음 → ActiveStorage가 LoadError |
| P2 | `Show.svelte:40-43` | Svelte 5 `$derived.by`가 `Date.now()` 를 읽지만 `_cooldownTick` state는 안 읽음 → 반응성 미발동 |

P1 두 개 다 머지 차단급. SSRF는 명백한 보안 hole이고, missing gem은 production 첫 PDF 업로드 시점에 런타임 크래시.

### SSRF fix (round 1 시도)

`app/lib/safe_url.rb` 모듈을 만들었다. 핵심:

```ruby
require "ipaddr"
require "resolv"

module SafeUrl
  PRIVATE_RANGES = [
    IPAddr.new("0.0.0.0/8"),
    IPAddr.new("10.0.0.0/8"),
    IPAddr.new("100.64.0.0/10"),     # carrier-grade NAT
    IPAddr.new("127.0.0.0/8"),       # loopback
    IPAddr.new("169.254.0.0/16"),    # link-local incl. cloud metadata IP
    IPAddr.new("172.16.0.0/12"),     # RFC1918
    IPAddr.new("192.168.0.0/16"),
    IPAddr.new("::1/128"),
    IPAddr.new("fc00::/7"),          # IPv6 unique local
    IPAddr.new("fe80::/10")          # IPv6 link-local
  ].freeze

  def public!(url)
    uri = URI.parse(url.to_s)
    raise BlockedError, "scheme not allowed" unless %w[http https].include?(uri.scheme)
    addrs = Resolv.getaddresses(uri.host)
    addrs.each do |a|
      ip = IPAddr.new(a)
      blocked = PRIVATE_RANGES.any? { |range| range.include?(ip) }
      raise BlockedError, "private address not allowed: #{a}" if blocked
    end
    uri
  end
end
```

Crawl 모듈의 `get` 안에 `SafeUrl.public!(current)` 를 매 redirect hop마다 호출. 깔끔해 보였다. 8 가지 케이스 (loopback, RFC1918, metadata IP, IPv6 loopback, 등) 테스트 다 통과.

푸시하고 2 라운드 돌렸다.

---

## Round 2 — IPv4-mapped IPv6 우회

```
[P1] Block IPv4-mapped private IPv6 URLs — app/lib/safe_url.rb:26-28
For user-submitted URL imports, an IPv4-mapped IPv6 literal such as
http://[::ffff:127.0.0.1]/ or http://[::ffff:169.254.169.254]/ passes
this range list: IPAddr treats it as IPv6, so it is not included in
the IPv4 loopback/link-local ranges and no mapped-address handling
is present.
```

이게 가능한가 했는데 실제로 가능했다. `IPAddr.new("::ffff:127.0.0.1")` 는 IPv6 객체로 만들어지고, 내 `PRIVATE_RANGES`의 `127.0.0.0/8` (IPv4) 는 IPv6 객체를 contain한다고 판단하지 않는다. 그러면 우회 성공.

검색해봤더니 이 패턴은 흔한 CVE 카테고리였다.

- **CVE-2026-42449** (n8n-mcp, 2026-04-30): "SDK embedder path의 synchronous URL validator에 IPv6 검증이 없음. `http://[::ffff:169.254.169.254]` 가 cloud-metadata, localhost, private-IP range check를 모두 우회"
- **CVE-2026-26324** (OpenClaw, 2026-02-20): "SSRF protection이 full-form IPv4-mapped IPv6 literal `0:0:0:0:0:ffff:7f00:1` (= 127.0.0.1) 으로 우회됨"

내가 만든 SafeUrl과 정확히 같은 결함이었다. 다행히 Codex가 production 전에 잡았다.

### Round 2 fix

```ruby
addrs.each do |a|
  ip = IPAddr.new(a)
  # An IPv4-mapped IPv6 literal like ::ffff:127.0.0.1 lands outside the
  # IPv4 ranges as-is. Unwrap it to its embedded IPv4 form so the
  # private-range check actually catches loopback / metadata IPs.
  ip = ip.native if ip.ipv6? && ip.ipv4_mapped?
  blocked = PRIVATE_RANGES.any? { |range| range.include?(ip) }
  raise BlockedError, "private address not allowed: #{a}" if blocked
end
```

`IPAddr#ipv4_mapped?` + `IPAddr#native` 가 mapped IPv6를 embedded IPv4로 풀어준다. 거기서 다시 range check.

부수적으로 `uri.host` 가 IPv6 literal에서 brackets (`[]`)를 그대로 들고 있어서 `IPAddr.new` 에 실패하는 문제도 있었다. `uri.hostname` 으로 바꿔야 brackets가 빠진다. 이 두 가지 함정은 코드만 봐서는 안 보이는데, codex가 정확히 line 26-28을 짚어줬다.

테스트 2 개 추가 (mapped loopback + mapped metadata) 까지 해서 push. 3 라운드.

---

## Round 3 — Robots.txt가 SSRF guard를 우회

3 라운드 결과:

```
[P1] Guard URLs before the robots.txt fetch
For a user-submitted URL such as http://169.254.169.254/..., this
call reaches Robotex.allowed? before the new SafeUrl guard in
Crawl.get runs, and Robotex fetches /robots.txt itself via
open-uri. That still allows SSRF against link-local/private services
(and robots redirects are also unguarded), so the robots check needs
to use the same public-address validation/guarded fetch path before
making any outbound request.
```

내 SafeUrl guard는 `Crawl.get` 안에 들어가 있었다. 그런데 controller가 호출하는 첫 outbound가 `Crawl.get` 이 아니라 `Crawl::RobotsChecker.allowed?` 였고, 그 안에서 `Robotex` 가 `open-uri` 로 `/robots.txt` 를 따로 fetch한다. **`Crawl.get` 을 거치지 않는 경로**.

이건 코드 한 줄 보고는 절대 못 잡는 결함이다. Robotex 내부까지 따라가야 보이는 sneak path. 1 라운드에서 controller가 ContentExtractor.extract → Crawl.get → SafeUrl 로 흘러가는 path만 보고 만족했었던 거.

### Round 3 fix

Defense in depth — controller의 trust boundary에서 SafeUrl을 한 번 더 부른다:

```ruby
# SSRF gate at the trust boundary. SafeUrl is also called inside
# Crawl.get, but Robotex fetches /robots.txt via open-uri which
# bypasses Crawl.get entirely — so a user-submitted URL pointing
# at 169.254.169.254 would still reach the metadata service during
# the robots check below if we didn't gate here first.
begin
  SafeUrl.public!(canonical)
rescue SafeUrl::BlockedError => e
  return redirect_to new_user_url_import_path,
                     alert: "외부 호스트만 허용해요: #{e.message}"
end

# robots.txt 체크
unless Crawl::RobotsChecker.allowed?(url: canonical)
  return redirect_to new_user_url_import_path,
                     alert: "robots.txt 가 허용하지 않아요."
end

extracted = Crawl::ContentExtractor.extract(url: canonical)
```

Crawl.get의 SafeUrl은 그대로 둔다 (redirect 시 매 hop마다 재검증). Controller의 SafeUrl은 trust boundary 진입 시 1차 방어.

같이 나온 P2 한 건도 짚어줄 만하다 — PDF 처리 job이 user에게 AI key가 없으면 `process_error: "no_api_key"` 저장하고 `processed_at` 도 같이 set. 그런데 job 첫 줄에 `return if pdf.processed_at.present?` 가 있어서 다음 run에서 그냥 skip. 즉, **user가 API key를 추가해도 PDF는 영원히 처리 안 됨**. processed_at만 안 set하면 retry 가능. 한 줄 fix.

---

## Round 4 — Policy 위반 + lifecycle 누락

```
[P1] Cap stored PDF paragraph excerpts at 500 chars
For text-extractable PDFs with long paragraphs, this stores up to
1000 characters per paragraph in user_pdfs.paragraphs, exceeding
the repository/legal storage cap for paragraph excerpts (≤500 chars
each).
```

이건 보안이 아니라 policy 위반. `legal/POLICY.md` 와 `Article::MAX_PARAGRAPH_LEN = 500` 이 둘 다 500 cap을 정해놨는데, PDF text extractor만 1000으로 박혀있었다. 1, 2, 3 라운드는 SSRF에 집중되어서 안 봤는데, 4 라운드에 와서야 codex가 policy 파일을 더 깊게 읽었다.

같이 나온 P2 두 건:

- 동일 PDF 재업로드 시 idempotent redirect만 하고 job 재enqueue 안 함 → no_api_key로 stuck 된 PDF는 재업로드해도 처리 안 됨
- PDF 삭제 시 `pdf.destroy!` 의 cascade가 polymorphic association (RecallDraft, TranslationSession) 에는 안 닿음 → user의 개인 텍스트가 DB에 남음

두 번째는 한국 개인정보보호법 관점에서 잠재 이슈. polymorphic + no FK 패턴은 cascade가 안 닿는 게 Rails ActiveRecord의 알려진 함정인데, 코드 리뷰로는 잘 안 보인다.

---

## 왜 매 라운드 새 P1이 나오는가

처음엔 codex가 일부러 정보 숨겨서 차차 꺼내는 줄 알았다. 그게 아니라 **각 round가 다른 surface를 봄**.

- Round 1: diff의 가장 명백한 line-level 결함 (직접 SSRF 호출, missing gem)
- Round 2: 내 fix 자체의 결함 (mapped IPv6 우회 — 새로 추가된 코드의 edge case)
- Round 3: fix 적용 후의 side path (Robotex가 SafeUrl 우회) — 시야가 controller 전체로 넓어짐
- Round 4: business / policy / lifecycle 차원 (paragraph cap, polymorphic cleanup) — 시야가 다시 codebase 전체로

검색해보니까 [zylos.ai의 Multi-Model Review 연구](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence) 가 이걸 정확히 설명한다.

> The actor-critic literature consistently reports **3-5 rounds** as the practical convergence window. From our own experience running Claude Code (fixer) + OpenAI Codex (reviewer) in an 8-round convergence loop on an SDK codebase: findings decreased monotonically from 7 in round 3 to 4 in round 4, 2 in rounds 5-6, 1 in round 7, and 0 (CLEAN) in round 8.

3 ~ 8 round가 정상 범위. Cursor의 BugBot은 8 parallel review pass + randomized file ordering으로 single ordering이 못 보는 finding을 잡는다고도 한다. 즉, **한 번 본 것과 두 번 본 것의 차이**가 본질적으로 존재.

[aseemshrey.in 블로그](https://aseemshrey.in/blog/claude-codex-iterative-plan-review/) 의 표현이 정확하다:

> A one-shot review finds problems but doesn't verify fixes. The iterative loop means:
> 1. Codex finds issues
> 2. Claude fixes them
> 3. Codex verifies the fixes actually work
> 4. Repeat until clean
>
> This catches the "fixed one thing but broke another" class of problems.

내 경우 round 2가 round 1 fix의 결함을 잡았고, round 3이 round 2 fix의 우회를 잡았다. 정확히 "fixed one thing but broke another" 클래스.

---

## 이걸 자동화 스킬로 박으면서 발견한 6 가지 함정

같은 워크플로를 다음 PR에도 쓸 거니까 Claude Code skill로 박았다. `pr-merge-review` 라는 이름의 스킬인데, 만드는 과정에서 함정 6 개를 마주쳤다.

### 함정 #1 — Local main에 unpushed commit

다른 PR을 codex로 리뷰하기 전에 `git log --oneline origin/main..main` 부터 봐야 한다. 안 그러면 PR base 비교가 misleading해진다. 첫 PR 마주쳤을 때 이거 빼먹어서 1 시간 헛돈 적 있다.

### 함정 #2 — 같은 영역 다른 구현의 PR 두 개

PR이 두 개고 같은 파일을 다른 의도로 만지면 머지 시 충돌. 어느 쪽 채택할지 사용자 결정 필요. 자동 union 절대 금지.

### 함정 #3 — Silent half-merge

충돌 발생 시 `git checkout --theirs/--ours` 일괄 적용 금지. 매 conflict마다 양쪽 의도 읽고 결정. 안 그러면 한쪽 의도가 silent하게 날아간다.

### 함정 #4 — Obsolete PR close 시 finding 같이 소실

머지 후 다른 PR 닫을 때 그냥 `gh pr close` 만 하면 그 PR에 대한 codex finding이 사라진다. 닫기 전에 finding 요약 comment로 보존.

### 함정 #5 — Dirty working tree 무시 (이번에 새로 발견)

cherry-pick / branch checkout 전에 `git status` 가 깨끗한지 확인. uncommitted 변경이 있으면 stash 후 진행. 머지 끝나고 `git stash pop` 시 충돌 가능 — 그건 user 본인의 미완 작업이라 자동 resolve 금지.

### 함정 #6 — Codex review 도는 동안 브랜치가 움직임 (이번에 새로 발견)

Long-running codex review (4-5 분) 중에 PR 브랜치에 새 commit이 push될 수 있다. 협업자가 push하거나, CI가 push하거나, 사용자 본인이 다른 세션에서 push하거나. 리뷰 끝나고 push 전에 반드시 `git fetch origin <branch>` + `git log HEAD..origin/<branch>` 로 확인. 새 commit 있으면 rebase + codex 재리뷰 (새 commit이 P1 가져왔을 수 있음).

이 두 함정 (#5, #6) 은 첫 운영에서 마주친 거라 스킬 SKILL.md에 사고 케이스로 박아뒀다. 다음번엔 첫 step에서 자동 체크.

---

## 안티패턴 (절대 금지)

운영하면서 깨달은 안 할 것들:

- ❌ P1 finding 보고도 "나중에 fix하지" 하고 머지
- ❌ `git checkout --theirs/--ours` 로 충돌 일괄 해결
- ❌ Cherry-pick 전 빌드/테스트 검증 생략
- ❌ Obsolete PR을 codex finding 보존 없이 그냥 close
- ❌ Local main의 unpushed commit 무시
- ❌ 같은 영역 다른 구현 두 PR을 둘 다 머지 시도 (한쪽은 반드시 택일)
- ❌ **Codex 1 라운드 통과 후 그대로 머지** (round 2+가 새 P1 잡는 경우 흔함)
- ❌ Long codex review 후 fetch 없이 push (브랜치 이동 silent miss)
- ❌ Dirty working tree 무시하고 cherry-pick / checkout
- ❌ Stash pop 충돌 시 자동 resolve (user의 미완 작업 의도 silent loss)

이 중에 가장 위험한 게 **1 라운드 통과 후 머지**. 시간 아끼려고 1 라운드만 보면 SSRF mapped IPv6 우회 같은 결함이 production으로 흘러간다. 이번 PR에서 그게 4 round 만에 다 잡혔다.

---

## 라운드 멈추는 시점

무한히 돌릴 순 없다. 내 기준은 3 가지:

1. **Round 결과가 P1 0 건이고 P2도 lifecycle / policy class 만 남았을 때** — main으로 머지하고 P2는 follow-up.
2. **Round N+1이 Round N과 같은 finding만 다시 짚을 때** — convergence 도달. 머지.
3. **사용자가 "그만 머지" 라고 명시할 때** — 진행 중 새 P1 있어도 user judgment 따름.

[Multi-Model AI Code Review 논문](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence) 의 termination 기준 5 개:

1. 모든 finding이 resolve됨
2. Evaluation score가 threshold 초과
3. Retry limit 도달
4. Hard timeout
5. Escalation (human input 필요)

내 경우는 1번. 4 라운드 후 sleep 들어가도 production에 SSRF / policy violation 없다는 확신이 들었다.

---

## 도구 setup

이 워크플로 그대로 따라하려면 필요한 것:

```bash
# 1. Codex CLI
npm install -g @openai/codex

# 2. Claude Code (Anthropic, claude.ai/code)
# 3. gh CLI (GitHub)
brew install gh && gh auth login
```

Codex CLI는 OpenAI 계정으로 `codex login` 한 번 하면 끝. ChatGPT subscription에 포함됨.

Claude Code에서 skill 폴더에 SKILL.md 박으면 자연어로 호출 가능:

```
사용자: "PR #N 머지해줘"
Claude: (자동으로 pr-merge-review skill 발동)
        → preflight 6 가지 함정 체크
        → codex review (background)
        → finding 분석
        → fix 적용
        → 재리뷰
        → ... (P1 0건 될 때까지)
        → 머지
```

---

## 정리

큰 PR을 codex로 리뷰할 때, 1 라운드 통과 ≠ 안전. 매 라운드 새 P1이 나오는 게 정상 패턴이고, 3 ~ 5 라운드가 일반적인 convergence window다. 이번 PR은 4 라운드 + 11 fix commit으로 끝났다.

가장 인상적이었던 건 round 2에서 mapped IPv6 우회. 내가 짠 SafeUrl이 정확히 CVE-2026-42449 + CVE-2026-26324 와 같은 결함을 가지고 있었다. 1 라운드에서 멈췄으면 production 갔다.

워크플로 자체는 자동화 스킬로 박았다. 다음 PR부턴 "머지해줘" 한 마디로 6 가지 함정 + 4 라운드 review까지 다 돈다.

```bash
codex review --base main -c 'model_reasoning_effort="high"' --enable web_search_cached
```

이 한 줄이 production에 흘러갈 뻔한 SSRF 우회 두 개를 막았다. 시간 5-10 분 더 쓰는 대가로는 싸다.
