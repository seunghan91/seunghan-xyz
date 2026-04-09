# Blog Publish Queue

매일 오전 9시 KST 자동 게시. 하루 1~2개 페이스 유지 (크롤 버짓 관리).

| 날짜 | 파일명 | 제목 요약 |
|------|--------|----------|
| 2026-04-08 | ai-design-system-vs-css-reskin-atomic-4-layer.md | AI로 디자인 시스템 마이그레이션했는데 사실 CSS 리스킨이었다 — 4-layer 재설계 회고 |
| 2026-04-09 | llm-citation-verification-korean-law.md | LLM이 지어낸 법령을 DB로 걸러내기 — 한국어 법률 인용 환각 방지 실전 |

## 사용법
- 포스트 작성 시 `date: YYYY-MM-DDT09:00:00+09:00` 설정
- 큐의 마지막 날짜 + 1일로 배정
- 영문(.en.md)은 한국어 다음날 배정
- `git add PUBLISH_QUEUE.md` 함께 커밋
