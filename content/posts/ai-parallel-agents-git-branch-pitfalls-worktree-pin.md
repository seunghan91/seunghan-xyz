---
title: "병렬 AI 에이전트 6명을 dispatch 했더니 git branch 함정 3개를 만났다 — worktree pin 패턴"
date: 2026-05-25T14:40:00+09:00
draft: false
tags: ["claude-code", "git", "ai-agent", "rails", "postgresql"]
description: "Claude Code Agent tool 로 병렬 dispatch 하다 만난 P11 baseline 부재 / 사용자 병행 세션 branch switching / Agent worktree stale base 함정 3개와 worktree pin + update-ref 해결 패턴."
---

새 feature 를 6개 트랙으로 쪼개서 AI 에이전트 6명에게 병렬로 던지는 게 요즘 일과다. plan-level codex review 2 round 통과한 깔끔한 plan 을 들고 자신만만하게 Wave 1 (2개 에이전트 병렬) dispatch 했는데, 첫 번째 에이전트가 5분 만에 **"STOP — schema 가 없습니다"** 라고 돌아왔다. 두 번째 dispatch 도 STOP. 세 번째에서야 통과.

그 사이 git branch 가 어디로 가있는지 reflog 를 5번 들여다봐야 했고, P11 merge 커밋이 엉뚱한 branch 위에 올라가서 reset 했다가, 결국 detached worktree + `git update-ref` 조합으로 우회해서 land 시켰다. 같은 함정에 또 안 빠지려고 정리한다.

---

## 배경: codex-collab 6 트랙 병렬 패턴

큰 기능을 작은 단위로 자르는 건 모두 한다. 차이는 **얼마나 잘게**, **얼마나 독립적으로** 자르냐. 이번 케이스는:

- Track A: Rails 데이터 모델 + 마이그레이션 (8 migrations, 5 신규 테이블)
- Track B: 매칭 알고리즘 (2 신규 서비스 + 16 테스트)
- Track C: cron jobs + 라운드 종료 detector
- Track D: API controllers + contract doc
- Track E: iOS feature 모듈
- Track F: Android feature 모듈

각 트랙은 plan 문서의 ownership matrix 로 책임 경계가 잡혀있고, 충돌 가능한 공유 자원 (`config/routes.rb`, `db/schema.rb`, `docs/api_v2_contract.md`) 은 단일 owner 명시. Wave 1 = A+B 병렬, Wave 2 = C+D 병렬 (A 의존), Wave 3 = E+F 병렬 (D 의존).

Claude Code 의 `Agent` tool 은 `isolation: "worktree"` 옵션이 있어서 서브 에이전트 각자 별도 worktree 에서 작업한다. 이론상 충돌 0. 실제로는 그렇게 호락호락하지 않았다.

---

## 함정 1: 의존 작업 미머지 시 baseline 부재

새 feature branch 를 main 에서 cut 했다.

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feat/p12-recurring-group
git cherry-pick 96934c42   # plan 커밋만 가져옴
```

plan 문서가 "기존 adhoc_matches 테이블의 status 컬럼에 `cancelled` 값을 추가" 라고 명시. Wave 1 Track A 에이전트가 schema 검사부터 시작:

```bash
grep -c "adhoc_" easy_bracket_web/db/schema.rb
# → 0
ls easy_bracket_web/app/models/adhoc/
# → No such file or directory
```

에이전트가 STOP and report 의무를 지키면서 정확하게 진단했다:

> The plan §2.1 + §4.1.5 + migration 006/007/008 all assume the P11 adhoc baseline (`adhoc_matches`, `adhoc_venues`, `app/models/adhoc/match.rb`, etc.) already exists on the branch. **It does not.**

원인이 뭐였냐면, 직전 작업 (P11 = adhoc QR 트랙) 이 `feat/adhoc-qr-foundation` 위에서 50+ 커밋 누적된 채로 **main 에 머지되지 않은 상태**였다. plan 작성 시점에는 P11 가 main 에 들어있을 줄 알고 썼던 거고, 실제 dispatch 시점에는 안 들어가 있었다.

이게 만약 STOP 의무가 안 박혔으면? 에이전트는 미존재 테이블에 `add_reference :adhoc_matches, :round` 마이그레이션을 신나게 적었을 거다. `bin/rails db:migrate` 단계에서야 `PG::UndefinedTable` 나고, 그 시점엔 이미 7개 다른 마이그레이션이 같이 적혀있어서 정리가 지옥.

### 해결: pre-flight 검증 + STOP 의무

이번 세션 이후로 모든 Wave dispatch prompt 에 박는 블록:

```text
# Pre-flight verification (FIRST — must pass before writing anything)

cd $WORKING_DIR
git log --oneline -3                              # expect specific tip
grep -c "adhoc_" easy_bracket_web/db/schema.rb    # expect 100+
ls easy_bracket_web/app/models/adhoc/             # expect existing files

If any check fails, STOP and report. Do not proceed.
```

그리고 plan 에 의존성이 있으면 dispatch 전에 main thread 가 baseline 흡수:

```bash
git checkout feat/p12-recurring-group
git merge feat/adhoc-qr-foundation --no-edit
# 충돌 resolve
git status --short
grep -c "adhoc_" easy_bracket_web/db/schema.rb    # → 113
```

머지 베이스가 깨끗하면 PR base 는 main, 두 트랙 (P11 + P12) 같이 land. PR review 가 커지는 트레이드오프는 있지만, baseline 동기화 함정보다 낫다.

---

## 함정 2: 사용자 병행 세션이 branch 를 switch 함

같은 머신에서 Claude Code 를 두 세션 띄워놓고 작업하는 게 점점 흔하다. 한 세션은 백엔드 마이그레이션, 다른 세션은 UI 인셋 손보기. 보통은 문제 없는데, **`git checkout` 이 main 워킹 트리에서 일어나면** 모든 세션이 동시에 영향받는다. worktree 가 공유되니까.

내가 P11 머지를 시작하기 직전 reflog:

```text
HEAD@{10}: checkout: moving from feat/adhoc-qr-foundation to main
HEAD@{9}:  checkout: moving from main to feat/p12-recurring-group
HEAD@{8}:  cherry-pick: docs(p12): post office-hours plan + codex review notes
HEAD@{7}:  checkout: moving from feat/p12-recurring-group to fix/ui-insets-safe-area   ← ⚠️
HEAD@{6}:  commit: web: add viewport-fit=cover to layouts for iOS safe-area support
HEAD@{5}:  commit: android(core/ui): add EbScreenScaffold helper for safe-inset wrapping
HEAD@{4}:  commit: android(auth): add safeDrawing inset + verticalScroll
HEAD@{3}:  commit: android(chat): apply safeDrawing(Bottom) to ComposeBar
HEAD@{2}:  commit: android(discovery): wrap with EbScreenScaffold
HEAD@{1}:  commit: android(auth): move verticalScroll to inner Column
HEAD@{0}:  commit (merge): merge: feat/adhoc-qr-foundation → feat/p12-recurring-group
```

`HEAD@{7}` 에서 다른 세션이 `fix/ui-insets-safe-area` 로 switch. 거기서 UI 작업 6개 커밋. 그 위에 `HEAD@{0}` 으로 내가 **fix/ui-insets-safe-area 위에 P11 머지를 올린 거**. 의도는 `feat/p12-recurring-group` 위에 올리는 거였는데, branch 가 바뀐 줄 모르고 `git merge` 친 결과.

```bash
git rev-parse feat/p12-recurring-group
# → d320bc13   (← 머지 전 상태, plan only)

git log --oneline -1
# → 29c32984 merge: feat/adhoc-qr-foundation → feat/p12-recurring-group (P11 baseline)

git branch --show-current
# → fix/ui-insets-safe-area   ← 머지가 여기 올라감
```

커밋 메시지에 `feat/p12-recurring-group` 라고 적었는데 실제로는 다른 branch 에 올라간, 완벽한 미스라벨.

### 해결: reset + 정확한 branch 에서 재merge

`fix/ui-insets-safe-area` 의 합법적인 6개 커밋은 살리고, 잘못 들어간 머지 1개만 떨궈야 한다:

```bash
# 잘못된 머지 직전 SHA 가 HEAD@{1} = 5f89e748
git reset --hard 5f89e748   # 머지 제거, UI 6개 커밋은 유지

git checkout feat/p12-recurring-group
git merge feat/adhoc-qr-foundation --no-edit
# 이번엔 깨끗 (충돌 0)
```

이번에 충돌이 0건이었던 이유: `fix/ui-insets-safe-area` 에 있던 `application.html.erb` 변경이 충돌의 원인이었는데, `feat/p12-recurring-group` 은 main 직후라 그 변경이 없었음. 같은 머지인데 시작 branch 가 다르면 충돌 양상도 다르다.

### 일반화: branch 검증 의무

이 사고 후 박힌 규칙:

```bash
# 머지/cherry-pick 직전 의무 체크
git branch --show-current   # 예상 brunch 인지
git log --oneline -2        # 예상 tip 인지
git rev-parse HEAD          # SHA 명시
```

리뷰어 입장에서 이 3줄을 commit 메시지나 PR description 에 그대로 박아두면 나중에 reflog 안 봐도 의도된 base 가 보인다.

---

## 함정 3: Agent worktree 가 stale base 에서 fork

P11 머지 완료. 이제 Track A 재dispatch. `isolation: "worktree"` 옵션 켜고 보냈는데, 5초 만에 또 STOP:

```text
**P11 baseline is NOT present on `feat/p12-recurring-group`.**
- Current HEAD = 648ccc01 (chore(ios): add native ExportOptions.plist)
- on branch worktree-agent-ac989f6318f7d574a
- Expected: 41df4a51 (Merge feat/adhoc-qr-foundation)
```

방금 머지 잘 됐는데? `feat/p12-recurring-group` 도 41df4a51 이고? 근데 에이전트는 머지 전 SHA `648ccc01` 을 보고 있다.

이유: Agent tool 의 `isolation: "worktree"` 가 **에이전트 spawn 시점의 HEAD 에서 worktree 를 fork** 하는데, 그 spawn 이 (한참 전 첫 시도 때) `648ccc01` 에서 시작됐고, 그 후 내가 main worktree 에서 머지를 해도 이미 detach 된 agent worktree 의 base 는 안 따라온다. 또 머지 commit 을 `feat/p12-recurring-group` ref 아래에 직접 갱신해도 worktree HEAD 는 갱신 안 됨.

거기다 사용자가 또 main checkout 을 다른 branch 로 switch. 또 reflog 가 뒤집힘. 이 시점에 **명시적 commit-pinned worktree** 가 답이라는 결론.

### 해결: detached HEAD worktree + commit pin

매 dispatch 마다 명시적으로 commit SHA 를 박은 worktree 를 만든다. 이러면 사용자가 main checkout 을 어떻게 흔들어도 영향 없음.

```bash
# 1. Track B 산출물부터 atomic commit (worktree pin 의 base 가 안정적이도록)
git checkout feat/p12-recurring-group
git add easy_bracket_web/app/services/matching/{session_former,tier_bucketer}.rb
git add easy_bracket_web/test/services/matching/{session_former,tier_bucketer}_test.rb
git commit -m "feat(p12): Matching::SessionFormer + TierBucketer (Track B Wave 1)"
# → 968067a7

# 2. 그 commit 에 detached worktree pin
git worktree add --detach /tmp/wave1-track-a-wt 968067a7
cd /tmp/wave1-track-a-wt

# 3. Pre-flight 다시 (이번엔 통과)
grep -c "adhoc_" easy_bracket_web/db/schema.rb        # 113
ls easy_bracket_web/app/services/matching/session_former.rb   # Track B 산출물도 보임
```

agent prompt 에 `cwd` 를 박는다:

```text
Work in `/tmp/wave1-track-a-wt` (detached HEAD @ 968067a7). DO NOT cd elsewhere.
This worktree is pinned and isolated — the user's parallel work cannot affect you.
```

이번엔 에이전트가 22 테스트 0 fail 로 통과. 산출물을 worktree 안에서 commit:

```bash
cd /tmp/wave1-track-a-wt
git add -A easy_bracket_web/app/models/adhoc/ \
         easy_bracket_web/app/serializers/api/v2/adhoc/ \
         easy_bracket_web/db/migrate/2026052500000*_*.rb \
         easy_bracket_web/db/schema.rb \
         easy_bracket_web/test/models/adhoc/
git commit -m "feat(p12): adhoc Group/Session/Round schema + models (Track A)"
# → e53af7c3
```

detached HEAD 에서 만든 commit 을 원래 branch 로 가져오기 위해 `update-ref` 로 ff:

```bash
NEW=$(git rev-parse HEAD)   # e53af7c3
git update-ref refs/heads/feat/p12-recurring-group $NEW
```

`968067a7` 은 `feat/p12-recurring-group` 의 ancestor 였으니 ff. 안전. 사용자 working tree 는 아예 안 건드림.

검증:

```bash
git log --oneline feat/p12-recurring-group -3
# e53af7c3 feat(p12): adhoc Group/Session/Round schema + models (Track A Wave 1)
# 968067a7 feat(p12): Matching::SessionFormer + TierBucketer (Track B Wave 1)
# 41df4a51 Merge branch 'feat/adhoc-qr-foundation' into feat/p12-recurring-group
```

---

## 부수 함정 모음

위 3개 말고 같은 세션에서 추가로 만난 것들.

### PostgreSQL CHECK 안에 subquery 금지

plan 이 이걸 적었다:

```sql
CHECK (
  array_length(weekdays, 1) >= 1
  AND weekdays <@ ARRAY[0,1,2,3,4,5,6]
  AND cardinality(weekdays) = (SELECT count(DISTINCT x) FROM unnest(weekdays) AS x)
)
```

요일 배열에 중복 없는지 검사하려고 subquery 를 썼는데:

```text
PG::FeatureNotSupported: ERROR: cannot use subquery in check constraint
```

[PostgreSQL 문서](https://www.postgresql.org/docs/current/ddl-constraints.html) 가 명시: "PostgreSQL does not support CHECK constraints that reference table data other than the new or updated row being checked."

이유: 다른 row 를 참조하면 dump/restore 가 깨지고, immutability 가정도 깨진다. CHECK 가 row-local 인 게 설계 원칙.

해결 옵션:

| 옵션 | 트레이드오프 |
|---|---|
| `UNIQUE`/`EXCLUDE` 제약으로 변환 | 적용 가능한 케이스만 (cross-row 만) |
| Custom function in CHECK | function 정의 변경 시 무방비, dump/restore 함정 |
| Model 레이어 validation | DB 보장 약화, 응용 우회 가능. 가장 흔한 선택 |
| `BEFORE INSERT` 트리거 | 복잡, dump/restore 안전 |

이번엔 model validation 으로 이관. DB 는 `cardinality(weekdays) >= 1 AND weekdays <@ ARRAY[0,1,2,3,4,5,6]` 만 enforce (둘 다 row-local).

```ruby
class Adhoc::Group < ApplicationRecord
  validate :weekdays_must_be_unique_and_in_range

  private

  def weekdays_must_be_unique_and_in_range
    return if weekdays.blank?
    errors.add(:weekdays, "must be unique") if weekdays.uniq.size != weekdays.size
    errors.add(:weekdays, "must be in 0..6") unless weekdays.all? { |w| (0..6).include?(w) }
  end
end
```

### strong_migrations 의 add_reference + concurrent index = 3-step FK

[strong_migrations](https://github.com/ankane/strong_migrations) 가 잡는 함정. `add_reference` 가 기본적으로 non-concurrent index 를 만들기 때문에 큰 테이블에서 writes 차단.

올바른 패턴은 3-step:

```ruby
# Migration 006: add_reference + concurrent index, FK 는 미설정
class AddRoundIdToAdhocMatches < ActiveRecord::Migration[8.1]
  disable_ddl_transaction!
  def change
    add_reference :adhoc_matches, :round,
      foreign_key: false,
      null: true,
      index: { algorithm: :concurrently, where: "round_id IS NOT NULL" }
  end
end

# Migration 007: FK 만 추가 (NOT VALID)
class AddRoundFkToAdhocMatches < ActiveRecord::Migration[8.1]
  def change
    add_foreign_key :adhoc_matches, :adhoc_rounds,
      column: :round_id, validate: false
  end
end

# Migration 008 (별도 deploy 후): FK validate
class ValidateRoundFkOnAdhocMatches < ActiveRecord::Migration[8.1]
  def change
    validate_foreign_key :adhoc_matches, :adhoc_rounds
  end
end
```

각 마이그레이션을 별도 deploy 로 보내면 lock acquisition window 가 짧고 운영 영향 최소. Render 의 Pre-Deploy 와 결합하면 expand → contract 패턴이 깨끗하게 떨어진다.

### Soft delete + unique index = partial unique

같은 사용자가 그룹에서 나간 뒤 다시 합류 가능해야 한다. 그런데 `unique` index 를 그냥 걸면 leave-then-rejoin 차단됨.

해결: status 컬럼 + partial unique.

```ruby
add_index :adhoc_group_members, [:group_id, :user_id],
  unique: true,
  where: "user_id IS NOT NULL AND status = 0",
  name: :idx_adhoc_group_members_active_user
```

`status = 0` (active) 만 unique. 떠난 row (`status = 1`) 는 무제한 누적 가능. 히스토리 보존 + rejoin 허용 둘 다 잡힘.

guest 도 같은 패턴:

```ruby
add_index :adhoc_group_members, [:group_id, :guest_token],
  unique: true,
  where: "guest_token IS NOT NULL AND status = 0",
  name: :idx_adhoc_group_members_active_guest
```

### CHECK 확장 시 single DROP+ADD 는 strong lock

`status IN ('open','playing','finished','abandoned')` 에 `'cancelled'` 를 추가하려고 했다. 첫 시도:

```ruby
safety_assured do
  execute <<~SQL
    ALTER TABLE adhoc_matches DROP CONSTRAINT chk_adhoc_matches_status;
    ALTER TABLE adhoc_matches ADD CONSTRAINT chk_adhoc_matches_status
      CHECK (status IN ('open','playing','finished','abandoned','cancelled'));
  SQL
end
```

codex 가 BLOCK: `ALTER TABLE ... ADD CONSTRAINT CHECK` 가 즉시 validation 을 수행해서 `AccessExclusiveLock` 을 모든 row 에 걸어버린다. 운영 중인 큰 테이블에서 위험.

NOT VALID + validate 2-step 패턴이 정답:

```ruby
# 1. 새 CHECK 를 NOT VALID 로 추가 (검증 안 함, lock 최소)
execute <<~SQL
  ALTER TABLE adhoc_matches
    ADD CONSTRAINT chk_adhoc_matches_status_v2
    CHECK (status IN ('open','playing','finished','abandoned','cancelled'))
    NOT VALID;
SQL

# 2. validate (SHARE UPDATE EXCLUSIVE lock 만, writes 허용)
execute "ALTER TABLE adhoc_matches VALIDATE CONSTRAINT chk_adhoc_matches_status_v2;"

# 3. 옛 CHECK 제거 + rename
execute "ALTER TABLE adhoc_matches DROP CONSTRAINT chk_adhoc_matches_status;"
execute "ALTER TABLE adhoc_matches RENAME CONSTRAINT chk_adhoc_matches_status_v2 TO chk_adhoc_matches_status;"
```

step 1-2 가 무지 짧은 lock window, step 3 도 metadata-only. 운영 중 안전.

### Agent 산출물이 untracked 라 main checkout 으로 leak

`isolation: "worktree"` 로 dispatch 한 에이전트가 worktree 안에서 untracked 파일을 만들고, "commit 은 main thread 가 한다" 패턴. worktree 안의 untracked 파일은 main checkout 의 working tree 와는 분리되어 있는데, **에이전트가 부수 효과로 main checkout 의 파일을 건드릴 수도 있다** (예: 일부 도구가 절대 경로로 main repo 의 lockfile 만짐).

이 세션에서 main checkout 에 untracked 가 쌓여있었고, branch switch 할 때 같이 끌려다녔다. 해결: agent 산출물은 명시적으로 `cp` 또는 worktree 안에서 commit 후 update-ref 로 가져오기. main checkout 의 working tree 는 사용자 영역으로 두기.

### codex CLI 가 긴 prompt 에서 hang

[codex CLI](https://github.com/openai/codex) 로 plan-level review 돌릴 때, prompt 가 200+ 라인이면 종종 응답이 안 옴. `pkill codex` 로 죽이고 prompt 를 잘라야 한다.

대처법:

```bash
codex exec \
  --sandbox read-only \
  --cd "$PWD" \
  "Review the diff vs origin/main. Files: ... Focus on: (1)..(2)..(3).. Under 80 lines." \
  < /dev/null
```

- prompt 100 라인 이내
- `< /dev/null` 로 stdin 차단 (interactive prompt 회피)
- `--sandbox read-only` 로 부수 효과 차단
- 200-300초 timeout 으로 wrap

그리고 review 를 **분할**한다. 27 파일을 한 번에 보내지 말고:

- Round 1: Track A + B 만 (스키마 + 알고리즘)
- Round 2: Track C + D (cron + API)
- Round 3: PR integration (cross-track)

분할이 한 번에 보내는 것보다 4배 BLOCK 잡았다. 컨텍스트 더 길어지면 codex 도 자세히 못 본다.

---

## 정리: AI 에이전트 병렬 dispatch 안전 패턴

이 세션 다 거치고 박은 규칙들.

| 규칙 | 이유 |
|---|---|
| 모든 agent prompt 에 pre-flight 블록 + STOP 의무 | hallucination 마이그레이션 작성 방지 |
| dispatch 전 baseline 검증 (`grep -c "<keyword>" schema.rb`) | 의존 작업 미머지 발견 |
| 명시적 `git worktree add --detach <path> <sha>` | 사용자 병행 세션 격리 |
| Agent 산출물은 worktree 안에서 commit, `git update-ref` 로 ff | main checkout working tree 안 건드림 |
| 매 dispatch 직전 `git branch --show-current` + `git log -2` | 잘못된 branch 에 commit 방지 |
| codex review 트랙별 분할 + prompt 100 라인 이내 | hang 회피 + BLOCK 더 잡음 |
| atomic commit per agent (track 별) | revert 단위 명확, PR review 부담 분산 |

### "STOP and report" 의무 prompt 의 실질 가치

이번 세션 두 번의 STOP 이 데이터 정합성을 살렸다. 첫 번째는 P11 baseline 부재, 두 번째는 worktree stale base. 두 번 다 에이전트가 진단을 정확히 했고, 어떤 파일도 안 만들었다. 만약 STOP 안 하고 추측으로 진행했다면 8개 마이그레이션이 깨진 상태로 main thread 까지 올라왔을 거고, 그걸 정리하는 데 더 오래 걸렸을 거다.

prompt 한 줄로 박는 가치:

```text
If the pre-flight does NOT show <expected baseline>, STOP and report — do not proceed.
Do not guess. Do not write any files.
```

이게 LLM agent 의 "확신 없으면 멈춘다" 행동을 강제한다. 단순한 문장이지만 실효성 큼.

### multi-Claude session 에서의 branch 위생

한 머신에서 두 Claude 세션 굴리는 게 흔해진 이상, branch state 가 세션 사이에 leaky 라는 사실을 받아들이고 가야 한다. main checkout 은 **언제든 다른 세션이 switch 할 수 있는 공유 자원**이고, 내 작업은 worktree 로 격리. 사용자 working tree 의 staged/unstaged 변경은 내 영역이 아님.

이번 사고 이후 worktree 사용 패턴이 바뀌었다: 짧은 작업도 worktree 만들고 들어가는 게 디폴트. `/tmp/<feature>-wt` 같은 명확한 경로 + detached HEAD + commit pin.

```bash
# 새 dispatch 시작 표준 절차
git worktree add --detach /tmp/feat-X-wt <base-sha>
cd /tmp/feat-X-wt
# ... agent dispatch with cwd=/tmp/feat-X-wt
# 완료 후
NEW=$(git -C /tmp/feat-X-wt rev-parse HEAD)
git update-ref refs/heads/<target-branch> $NEW
git worktree remove /tmp/feat-X-wt
```

5줄로 끝나는 패턴인데, 함정 3개 다 막힌다.

---

## 결론

병렬 AI 에이전트 dispatch 는 명목상 "충돌 없는 병렬화" 인데, 실제로는 git state 가 세션 사이에 leaky 라 함정이 많다. 이번 세션에서 만난 3개:

1. **의존 작업 미머지** → pre-flight + STOP 의무 + main thread 의 baseline 흡수
2. **사용자 병행 세션 branch switching** → 명시적 worktree pin + `update-ref` ff
3. **Agent worktree stale base** → detached HEAD + commit SHA 박힌 path 로 dispatch

부수적으로 PG CHECK subquery 금지, strong_migrations 3-step FK, partial unique soft delete, NOT VALID CHECK 확장, codex 분할 review 까지. 다 같은 세션에서 한 번씩 부딪혔다.

다음 세션부터는 worktree pin 이 디폴트. plan 에 baseline 의존성 명시. agent prompt 에 pre-flight 블록 박기. 같은 함정 또 만나면 그땐 시간 더 잃을 수밖에 없으니까.
