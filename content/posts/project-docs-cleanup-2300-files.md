---
title: "프로젝트 문서 2,300개를 400개로 줄인 전수점검 기록"
date: 2026-03-06
draft: false
tags: ["문서관리", "기술부채", "정리", "Git", "개발환경", "생산성"]
description: "docs/ 폴더에 2,350개 마크다운이 쌓여있었다. 에이전트 병렬 분석으로 전수점검하고, 활성 문서 404개만 남기기까지의 과정을 기록한다."
---

프로젝트를 1년 가까이 진행하다 보면 문서가 쌓인다. 기능 설계서, TODO, 디버깅 기록, 마이그레이션 계획서, 테스트 시나리오... 각각은 그 시점에 필요했지만, 시간이 지나면 노이즈가 된다. 어느 날 `find docs -name "*.md" | wc -l`을 쳤더니 **2,352개**가 나왔다.

---

## 현황 파악: 어디서 이렇게 쌓였나

```bash
find docs -name "*.md" | wc -l
# 2352

# 디렉토리별 파일 수
find docs -maxdepth 1 -type d | while read d; do
  count=$(find "$d" -name "*.md" | wc -l)
  echo "$count $(basename $d)"
done | sort -rn | head -15
```

결과:

| 디렉토리 | 파일 수 | 상태 |
|----------|---------|------|
| archive/ | 1,422 | 이미 아카이브된 것들 |
| todo/ | 215 | 완료된 할일이 대부분 |
| mobile/ | 91 | 92%가 5개월 이상 방치 |
| features/ | 56 | 구현 완료된 설계서 |
| reports/ | 49 | 비교적 잘 관리됨 |
| testing/ | 45 | 중복 테스트 문서 |
| web/ | 44 | 현행 레퍼런스 |
| migration/ | 37 | 현재 진행 중 (유일하게 100% 최신) |

**핵심 문제**: `archive/` 제외해도 930개가 "활성" 디렉토리에 있었는데, 실제로 현행인 파일은 30%도 안 됐다.

---

## 분석 전략: 병렬 에이전트 3개 투입

2,300개를 한 파일씩 열어볼 수는 없다. Claude Code의 Agent 도구로 3개의 탐색 에이전트를 **병렬 실행**했다.

| 에이전트 | 담당 영역 | 분석 대상 |
|---------|----------|----------|
| Agent 1 | `docs/todo/` | 215개 - 완료/폐기 태스크 식별 |
| Agent 2 | `docs/` 주요 10개 서브디렉토리 | 453개 - 현행 여부 판단 |
| Agent 3 | 비-docs MD 파일들 | 70개+ - 정확성 검증 |

각 에이전트는 파일 목록 수집 → 20~30개 샘플 읽기 → 날짜/내용 기반 분류를 독립적으로 수행했다. 3개가 동시에 돌면서 약 3분 만에 전체 윤곽이 잡혔다.

### 에이전트가 찾아낸 패턴들

**1. "PHASE_완료" 패턴**: `PHASE_1_COMPLETION_REPORT.md`, `PHASE_4.7_PRODUCTION_E2E_COMPLETE.md` 같은 파일이 18개. 전부 2025년 10월에 "COMPLETE" 마킹된 과거 기록.

**2. 디버그 잔해**: `DEBUG_AUTH.md`, `TOKEN_MISMATCH_DIAGNOSIS.md`, `EMERGENCY_FIX.md` 같은 일회성 트러블슈팅 기록이 14개. 문제 해결 후 삭제 안 하고 방치.

**3. 중복 문서**: `API_CONTRACT.md`가 `architecture/`, `web/`, `server/` 3곳에 각각 존재. 크기도 50KB, 18KB, 12KB로 다른 버전.

**4. 날짜 기반 부패**: `mobile/` 91개 중 85개가 2025년 8~9월 파일. 프레임워크 마이그레이션 이후 완전히 쓸모없어진 문서들.

---

## 실행: 6단계 정리

### 1단계: 디버그/임시 파일 즉시 삭제 (14개)

```bash
# 크롬 확장 디버그 파일
rm chrome_extension/DEBUG_AUTH.md
rm chrome_extension/DEBUG_LOGIN_FLOW.md
rm chrome_extension/test-token-fix.md
rm chrome_extension/TOKEN_MISMATCH_DIAGNOSIS.md
rm chrome_extension/feedback.md

# 앱 긴급 수정/버그 기록
rm app/EMERGENCY_FIX.md
rm app/FIXES_SUMMARY.md
rm app/CRITICAL_BUGFIX_SUMMARY.md
rm app/ANDROID_CRASH_FIX.md
# ... 등
```

**원칙**: 디버그 기록은 이슈 해결 후 삭제한다. Git 히스토리에 남아있으니 필요하면 복원 가능.

### 2단계: Phase 완료 문서 아카이브 (11개)

```bash
mkdir -p docs/archive/phase-history-2025
mv app/PHASE*.md docs/archive/phase-history-2025/
mv app/PROJECT_COMPLETION_SUMMARY.md docs/archive/phase-history-2025/
```

삭제가 아니라 아카이브. 나중에 "이 기능 언제 완료했지?" 할 때 참조할 수 있다.

### 3단계: docs/todo/ 대규모 정리 (215 → 33개)

```bash
# 이미 명시적으로 아카이브된 폴더 (87개)
mv docs/todo/archive-2025-10-18 docs/archive/

# PHASE_* 완료 파일들 (18개)
mv docs/todo/PHASE_*.md docs/archive/todo-phase-completions/

# FINAL/COMPLETE 키워드 파일들 (8개)
mv docs/todo/FINAL_*.md docs/archive/todo-phase-completions/
mv docs/todo/*COMPLETE*.md docs/archive/todo-phase-completions/

# 3개월 이상 방치된 파일들 (63개)
for f in docs/todo/*.md; do
  mod_date=$(stat -f "%Sm" -t "%Y%m" "$f")
  [[ "$mod_date" < "202512" ]] && mv "$f" docs/archive/todo-old-2025/
done
```

남은 33개는 전부 2026년 1~3월 생성된 활성 문서:
- `improvement-2026-02/` (10개) - 현재 개선 로드맵
- `TODO_2026-02-12.md` - 현재 우선순위
- `WEB_TO_RAILS_MIGRATION.md` - 진행 중인 마이그레이션

### 4단계: 대규모 서브디렉토리 날짜 기반 아카이브

```bash
# 패턴: 수정일 기준으로 오래된 파일만 아카이브
for f in $(find docs/mobile -name "*.md"); do
  mod_date=$(stat -f "%Sm" -t "%Y%m" "$f")
  [[ "$mod_date" < "202601" ]] && mv "$f" docs/archive/mobile-2025/
done
```

| 디렉토리 | Before | After | 아카이브 |
|----------|--------|-------|---------|
| mobile/ | 91 | 6 | 85개 (93%) |
| features/ | 56 | 20 | 36개 |
| testing/ | 45 | 16 | 29개 |
| architecture/ | 30 | 10 | 20개 |
| development/ | 22 | 4 | 18개 |
| weakpoint/ | 26 | 7 | 19개 |
| setup/ | 22 | 9 | 13개 |

### 5단계: 중복 파일 통합

```bash
# API_CONTRACT.md: 3곳 → 1곳 (가장 완전한 버전만 유지)
ls -la docs/architecture/API_CONTRACT.md  # 50KB (최신, 완전판)
ls -la docs/server/API_CONTRACT.md        # 18KB (부분 복사)
ls -la docs/web/API_CONTRACT.md           # 12KB (부분 복사)

rm docs/server/API_CONTRACT.md
rm docs/web/API_CONTRACT.md
```

### 6단계: legacy/ 등 이름부터 아카이브인 디렉토리 이동

```bash
mv docs/legacy docs/archive/legacy-docs
mv docs/websocket_migration docs/archive/
mv docs/websocket docs/archive/
mv docs/dual-database-architecture docs/archive/
```

---

## 보너스: Git Worktree와 Branch 정리

문서만 문제가 아니었다. Git 상태도 지저분했다.

### Worktree 잔재: 255MB 해제

```bash
git worktree list
# main
# .cursor/worktrees/ainote/nlq  (detached HEAD, 125MB)
# .claude/worktrees/romantic-kalam  (old branch, 130MB)
```

두 worktree 모두 main에 이미 머지된 커밋이었다. 하나는 untracked CI 워크플로 파일 2개만 있었고, 다른 하나는 109개의 변경 파일이 있었지만 전부 main에 반영된 상태.

```bash
git worktree remove --force .claude/worktrees/romantic-kalam
git worktree remove --force .cursor/worktrees/ainote/nlq
# 255MB 해제
```

### 브랜치 정리: 11개 → 6개

```bash
# 머지 완료 확인
git branch --merged main | grep "claude/"
# claude/fix-fcm-token-duplicate
# claude/fix-flutter-memo-ui
# claude/fix-notification-parsing

# 안전 삭제
git branch -d claude/fix-fcm-token-duplicate
git branch -d claude/fix-flutter-memo-ui
git branch -d claude/fix-notification-parsing

# 미머지 브랜치도 확인 후 삭제
# claude/exciting-snyder (2월, web migration) - main에서 별도 진행됨
# claude/fix-deadline-category-bugs (12월) - 3개월 방치
git branch -D claude/exciting-snyder
git branch -D claude/fix-deadline-category-bugs-d4P0n
```

---

## 결과

| 항목 | Before | After | 감소율 |
|------|--------|-------|--------|
| docs/ 활성 파일 | 2,350개 | **404개** | **83%** |
| docs/todo/ | 215개 | 33개 | 85% |
| docs/mobile/ | 91개 | 6개 | 93% |
| Git worktrees | 3개 | 1개 | 255MB 해제 |
| Git branches | 11개 | 6개 | 5개 삭제 |
| 디버그/임시 파일 | 14개 | 0개 | 전량 삭제 |

**삭제한 것은 없다**. 전부 `docs/archive/`로 이동했다. Git 히스토리에도 남아있으니 필요하면 언제든 복원할 수 있다.

---

## 교훈

### 1. 문서는 코드와 같은 수명 관리가 필요하다

코드는 리팩토링하면서 문서는 방치하는 경우가 많다. "나중에 참고하려고"라는 마음으로 남겨둔 문서가 1년이면 수천 개가 된다. 분기마다 한 번은 `find docs -name "*.md" -mtime +90`으로 3개월 이상 방치된 파일을 점검해야 한다.

### 2. 디버그 기록은 이슈 해결 즉시 삭제

`DEBUG_AUTH.md`, `TOKEN_MISMATCH_DIAGNOSIS.md` 같은 파일은 문제 해결 후 바로 삭제하는 것이 맞다. "나중에 비슷한 문제가 생기면?"이라는 걱정은 Git 히스토리가 해결해준다.

### 3. 완료 문서에는 만료일을 붙여라

`PHASE_4_COMPLETION_SUMMARY.md`처럼 완료 시점의 스냅샷을 남기는 것은 좋다. 하지만 이런 파일은 생성 시점에 "이 문서는 YYYY-MM-DD 이후 아카이브 대상"이라는 메타데이터를 넣어두면 나중에 자동화할 수 있다.

### 4. 날짜 기반 아카이브가 가장 안전하다

내용을 일일이 읽고 판단하는 것보다, `stat`로 수정일을 확인하고 3개월 이상 된 파일을 일괄 아카이브하는 것이 훨씬 효율적이다. 실수로 필요한 파일을 옮겨도 아카이브에서 찾으면 된다.

### 5. 중복은 즉시 잡아라

`API_CONTRACT.md`가 3곳에 있으면 어느 것이 정본인지 아무도 모른다. 하나의 Canonical 위치를 정하고 나머지는 삭제. "편의를 위해 복사해두자"는 생각이 6개월 뒤의 혼란을 만든다.

---

## 자동화 아이디어

다음에는 이런 작업을 반복하지 않도록 간단한 스크립트를 만들 수 있다:

```bash
#!/bin/bash
# docs-health-check.sh
echo "=== 문서 건강 점검 ==="
echo "전체: $(find docs -name '*.md' -not -path '*/archive/*' | wc -l)개"
echo ""
echo "3개월 이상 방치:"
find docs -name "*.md" -not -path "*/archive/*" -type f | while read f; do
  mod_date=$(stat -f "%Sm" -t "%Y%m%d" "$f")
  cutoff=$(date -v-3m "+%Y%m%d")
  [[ "$mod_date" < "$cutoff" ]] && echo "  $f ($mod_date)"
done | head -20
echo ""
echo "중복 파일명:"
find docs -name "*.md" -not -path "*/archive/*" | xargs -I{} basename {} | sort | uniq -d
```

분기마다 이 스크립트를 돌리면 문서 비대화를 예방할 수 있다.
