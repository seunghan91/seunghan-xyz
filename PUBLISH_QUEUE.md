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

## 사용법
- 포스트 작성 시 `date: YYYY-MM-DDT09:00:00+09:00` 설정
- 큐의 마지막 날짜 + 1일로 배정
- 영문(.en.md)은 한국어 다음날 배정
- `git add PUBLISH_QUEUE.md` 함께 커밋
