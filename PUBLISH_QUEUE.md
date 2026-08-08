# Blog Publish Queue

매일 오전 9시 KST 자동 게시. 하루 1~2개 페이스 유지 (크롤 버짓 관리).

| 날짜 | 파일명 | 제목 요약 |
|------|--------|----------|
| 2026-04-08 | ai-design-system-vs-css-reskin-atomic-4-layer.md | AI로 디자인 시스템 마이그레이션했는데 사실 CSS 리스킨이었다 — 4-layer 재설계 회고 |
| 2026-04-09 | llm-citation-verification-korean-law.md | LLM이 지어낸 법령을 DB로 걸러내기 — 한국어 법률 인용 환각 방지 실전 |
| 2026-04-15 | mdm-mcp-gateway-integration.md | HWP 변환기를 MCP 툴로 만들기 — 기존 Gateway에 3줄 추가하는 법 |
| 2026-04-16 | flutter-rails-realtime-auth-fcm-actioncable-jwt.md | Flutter+Rails 실시간 인프라 4대 단절 고치기 — FCM 딥링크, ActionCable JWT, 익명→회원 연결 |
| 2026-04-17 | mdm-desktop-latex-mathml-pulldown-latex.md | Tauri 앱에 LaTeX 수식 달기 — KaTeX 버리고 pulldown-latex + MathML 선택 |
| 2026-04-20 | threads-api-oauth-token-reply-collection.md | Threads API OAuth 토큰 발급부터 내 게시물 댓글 151개 수집까지 실전 |
| 2026-04-21 | tailwind-v4-theme-migration-oklch-fallback.md | Tailwind v4 @theme 함정 — tailwind.config.js가 무시되고 기본 OKLCH로 폴백되던 문제 |
| 2026-04-25 | reinsman-paradigm-harness-engineering-next.md | 레인스맨(Reinsman) — 하네스 엔지니어링 다음에 오는 것 |
| 2026-04-26 | reinsman-paradigm-harness-engineering-next.en.md | Reinsman — What Comes After Harness Engineering (EN) |
| 2026-04-29 | render-rails-monorepo-ruby-version-solidqueue-puma.md | Render에 Rails 8 monorepo 처음 올릴 때 빌드 4번 깨먹은 이야기 — .ruby-version 함정과 SolidQueue web 통합 |
| 2026-05-02 | android-clean-architecture-mvi-7-phase-refactoring-pitfalls.md | Android Clean Arch + MVI 7-phase 리팩토링 함정 8가지 — iOS 스택과 다른 점 |
| 2026-05-03 | mcp-personal-character-operation-not-delegation.md | MCP는 내 전용 캐릭터다 — 위임이 아니라 운용으로 |
| 2026-05-11 | rails-raw-sql-column-typo-oauth-userinfo-500-defense-in-depth.md | Rails raw SQL 컬럼명 typo로 OAuth userinfo 전부 500 — 4중 보호막이 다 뚫린 이야기 (즉시 게시) |
| 2026-05-13 | codex-review-swiftui-secret-ui-privacysensitive-pasteboard-singleton.md | AI 흔적 지우기 스킬 vs Codex 리뷰 — SwiftUI 시크릿 UI 보안 8개 구멍 (즉시 게시) |
| 2026-05-16 | ruby-include-duck-typing-jsonb-oauth-redirect-uri-bypass.md | Ruby `.include?` 가 보안 hole 을 우연히 닫은 사건 — duck typing 과 jsonb `\|\|` 의 합작 |
| 2026-05-21 | codex-cli-iterative-review-4-rounds-ssrf-ipv4-mapped-ipv6-bypass.md | Codex CLI 4 라운드 코드 리뷰 — 매 라운드마다 새 P1이 나온 이유 (즉시 게시) |
| 2026-05-22 | codex-cli-iterative-review-4-rounds-ssrf-ipv4-mapped-ipv6-bypass.en.md | Codex CLI Iterative Code Review — Why Every Round Found a New P1 (EN) |

## 사용법
- 포스트 작성 시 `date: YYYY-MM-DDT09:00:00+09:00` 설정
- 큐의 마지막 날짜 + 1일로 배정
- 영문(.en.md)은 한국어 다음날 배정
- `git add PUBLISH_QUEUE.md` 함께 커밋
| 2026-05-25 | ai-parallel-agents-git-branch-pitfalls-worktree-pin.md | 병렬 AI 에이전트 6명 dispatch 중 만난 git branch 함정 3개 — worktree pin 패턴 (즉시 게시) |
| 2026-05-27 | rails-turbo-form-200-ok-nested-form-otp-verify-no-response.md | Rails Turbo form 함정 2종 — 200 OK 무시 + nested button_to, OTP 검증 sev1+sev2 (즉시 게시) |
| 2026-05-28 | imposter-syndrome-laing-false-self-sns-mask-2017-paper.md | 8년 전 학부 논문이 임포스터 신드롬이었다 — Laing 거짓 자기, SNS 가면, Clance 1978 (즉시 게시) |
| 2026-05-29 | ai-mask-creator-consumer-divide-tool-democratization-myth.md | AI가 가면 생산을 평등화해도 만드는/소비하는 사람은 갈라진다 — 90-9-1 법칙과 11% Expressing (예약) |
| 2026-06-26 | macos-aswebauthenticationsession-chrome-oauth-external-browser.md | macOS Google 로그인이 Chrome에서 먹통 — ASWebAuthenticationSession 버그와 external browser 우회 (즉시 게시) |
| 2026-06-27 | rust-binary128-libquadmath-bit-exact.md | 순수 Rust로 IEEE754 binary128을 libquadmath와 bit-exact 재현 — correctly-rounded 유일성·68K 퍼징·FFI ABI 함정 (즉시 게시) |
| 2026-07-03 | ios-26-caemitterlayer-full-width-line-emitter-bug.md | iOS 26 CAEmitterLayer 전체폭 line emitter 방출 드롭 회귀 — 4라운드 A/B 판별 디버깅기 (즉시 게시) |
| 2026-08-07 | mcp-spec-revisions-2026-07-28-stateless-migration.md | MCP 스펙이 세 리비전 앞서가 있었다 — 2026-07-28 스테이트리스 전환의 전말 (즉시 게시) |
| 2026-08-08 | ios-corebluetooth-autoreconnect-first-connect-cberror-1.md | iOS BLE 첫 연결만 실패 — auto-reconnect 옵션과 CBError Code=1, 실기 로그로 좁힌 디버깅기 (즉시 게시) |
