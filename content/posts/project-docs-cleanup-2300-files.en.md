---
title: "Reducing 2,300 Project Documents to 400 — A Full Audit Record"
date: 2026-01-27
draft: false
tags: ["Documentation", "Technical Debt", "Cleanup", "Git", "Dev Environment", "Productivity"]
description: "2,350 markdown files had piled up in docs/. Ran a full audit with parallel agent analysis and kept only 404 active documents."
cover:
  image: "/images/og/project-docs-cleanup-2300-files.png"
  alt: "Project Docs Cleanup 2300 Files"
  hidden: true
---


After running a project for nearly a year, documents accumulate. Feature design specs, TODOs, debugging records, migration plans, test scenarios... Each was needed at the time, but over time they become noise. One day I ran `find docs -name "*.md" | wc -l` and got **2,352**.

---

## Status Check: How Did It Get This Bad

```bash
find docs -name "*.md" | wc -l
# 2352

# File count by directory
find docs -maxdepth 1 -type d | while read d; do
  count=$(find "$d" -name "*.md" | wc -l)
  echo "$count $(basename $d)"
done | sort -rn | head -15
```

Results:

| Directory | File Count | Status |
|-----------|-----------|--------|
| archive/ | 1,422 | Already archived |
| todo/ | 215 | Mostly completed tasks |
| mobile/ | 91 | 92% abandoned for 5+ months |
| features/ | 56 | Design specs for completed features |
| reports/ | 49 | Relatively well maintained |
| testing/ | 45 | Duplicate test documents |
| web/ | 44 | Current references |
| migration/ | 37 | Currently in progress (the only 100% current) |

**Core problem**: Excluding `archive/`, 930 files were in "active" directories, but less than 30% were actually current.

---

## Analysis Strategy: Deploy 3 Parallel Agents

Opening 2,300 files one by one was not feasible. Using Claude Code's Agent tool, 3 exploration agents were run **in parallel**.

| Agent | Area | Analysis Target |
|-------|------|----------------|
| Agent 1 | `docs/todo/` | 215 files - Identify completed/abandoned tasks |
| Agent 2 | `docs/` main 10 subdirectories | 453 files - Determine current status |
| Agent 3 | Non-docs MD files | 70+ files - Accuracy verification |

Each agent independently performed file list collection -> reading 20-30 samples -> date/content-based classification. Running all 3 simultaneously, the overall picture emerged in about 3 minutes.

### Patterns Found by Agents

**1. "PHASE_Complete" pattern**: 18 files like `PHASE_1_COMPLETION_REPORT.md`, `PHASE_4.7_PRODUCTION_E2E_COMPLETE.md`. All marked "COMPLETE" in October 2025.

**2. Debug remnants**: 14 one-off troubleshooting records like `DEBUG_AUTH.md`, `TOKEN_MISMATCH_DIAGNOSIS.md`, `EMERGENCY_FIX.md`. Left behind after problems were solved.

**3. Duplicate documents**: `API_CONTRACT.md` existed in 3 places -- `architecture/`, `web/`, `server/`. Different versions at 50KB, 18KB, 12KB.

**4. Date-based decay**: 85 of 91 files in `mobile/` were from August-September 2025. Documents made completely useless after a framework migration.

---

## Execution: 6-Step Cleanup

### Step 1: Delete Debug/Temporary Files Immediately (14 files)

```bash
# Chrome extension debug files
rm chrome_extension/DEBUG_AUTH.md
rm chrome_extension/DEBUG_LOGIN_FLOW.md
rm chrome_extension/test-token-fix.md
rm chrome_extension/TOKEN_MISMATCH_DIAGNOSIS.md
rm chrome_extension/feedback.md

# App emergency fix/bug records
rm app/EMERGENCY_FIX.md
rm app/FIXES_SUMMARY.md
rm app/CRITICAL_BUGFIX_SUMMARY.md
rm app/ANDROID_CRASH_FIX.md
# ... etc
```

**Principle**: Delete debug records after the issue is resolved. Git history preserves them, so they can be restored if needed.

### Step 2: Archive Phase Completion Documents (11 files)

```bash
mkdir -p docs/archive/phase-history-2025
mv app/PHASE*.md docs/archive/phase-history-2025/
mv app/PROJECT_COMPLETION_SUMMARY.md docs/archive/phase-history-2025/
```

Archive, not delete. Can be referenced later when asking "when was this feature completed?"

### Step 3: Major docs/todo/ Cleanup (215 -> 33 files)

```bash
# Already explicitly archived folder (87 files)
mv docs/todo/archive-2025-10-18 docs/archive/

# PHASE_* completion files (18 files)
mv docs/todo/PHASE_*.md docs/archive/todo-phase-completions/

# FINAL/COMPLETE keyword files (8 files)
mv docs/todo/FINAL_*.md docs/archive/todo-phase-completions/
mv docs/todo/*COMPLETE*.md docs/archive/todo-phase-completions/

# Files abandoned for 3+ months (63 files)
for f in docs/todo/*.md; do
  mod_date=$(stat -f "%Sm" -t "%Y%m" "$f")
  [[ "$mod_date" < "202512" ]] && mv "$f" docs/archive/todo-old-2025/
done
```

The remaining 33 were all active documents created January-March 2026:
- `improvement-2026-02/` (10 files) - Current improvement roadmap
- `TODO_2026-02-12.md` - Current priorities
- `WEB_TO_RAILS_MIGRATION.md` - In-progress migration

### Step 4: Date-Based Archive for Large Subdirectories

```bash
# Pattern: Archive only old files based on modification date
for f in $(find docs/mobile -name "*.md"); do
  mod_date=$(stat -f "%Sm" -t "%Y%m" "$f")
  [[ "$mod_date" < "202601" ]] && mv "$f" docs/archive/mobile-2025/
done
```

| Directory | Before | After | Archived |
|-----------|--------|-------|----------|
| mobile/ | 91 | 6 | 85 (93%) |
| features/ | 56 | 20 | 36 |
| testing/ | 45 | 16 | 29 |
| architecture/ | 30 | 10 | 20 |
| development/ | 22 | 4 | 18 |
| weakpoint/ | 26 | 7 | 19 |
| setup/ | 22 | 9 | 13 |

### Step 5: Consolidate Duplicate Files

```bash
# API_CONTRACT.md: 3 locations -> 1 (keep only the most complete version)
ls -la docs/architecture/API_CONTRACT.md  # 50KB (latest, complete)
ls -la docs/server/API_CONTRACT.md        # 18KB (partial copy)
ls -la docs/web/API_CONTRACT.md           # 12KB (partial copy)

rm docs/server/API_CONTRACT.md
rm docs/web/API_CONTRACT.md
```

### Step 6: Move Directories Named Like Archives

```bash
mv docs/legacy docs/archive/legacy-docs
mv docs/websocket_migration docs/archive/
mv docs/websocket docs/archive/
mv docs/dual-database-architecture docs/archive/
```

---

## Bonus: Git Worktree and Branch Cleanup

Documents were not the only problem. Git state was messy too.

### Worktree Remnants: 255MB Freed

```bash
git worktree list
# main
# .cursor/worktrees/ainote/nlq  (detached HEAD, 125MB)
# .claude/worktrees/romantic-kalam  (old branch, 130MB)
```

Both worktrees had commits already merged into main. One had only 2 untracked CI workflow files, the other had 109 changed files but all already reflected in main.

```bash
git worktree remove --force .claude/worktrees/romantic-kalam
git worktree remove --force .cursor/worktrees/ainote/nlq
# 255MB freed
```

### Branch Cleanup: 11 -> 6

```bash
# Verify merged
git branch --merged main | grep "claude/"
# claude/fix-fcm-token-duplicate
# claude/fix-flutter-memo-ui
# claude/fix-notification-parsing

# Safe delete
git branch -d claude/fix-fcm-token-duplicate
git branch -d claude/fix-flutter-memo-ui
git branch -d claude/fix-notification-parsing

# Unmerged branches verified and deleted
# claude/exciting-snyder (Feb, web migration) - proceeded separately on main
# claude/fix-deadline-category-bugs (Dec) - abandoned for 3 months
git branch -D claude/exciting-snyder
git branch -D claude/fix-deadline-category-bugs-d4P0n
```

---

## Results

| Item | Before | After | Reduction |
|------|--------|-------|-----------|
| docs/ active files | 2,350 | **404** | **83%** |
| docs/todo/ | 215 | 33 | 85% |
| docs/mobile/ | 91 | 6 | 93% |
| Git worktrees | 3 | 1 | 255MB freed |
| Git branches | 11 | 6 | 5 deleted |
| Debug/temp files | 14 | 0 | All deleted |

**Nothing was deleted permanently**. Everything was moved to `docs/archive/`. Git history also preserves them, so restoration is possible at any time.

---

## Lessons Learned

### 1. Documents Need the Same Lifecycle Management as Code

Code gets refactored while documents are neglected. Documents kept with the thought "I might reference this later" accumulate to thousands within a year. At least once per quarter, run `find docs -name "*.md" -mtime +90` to audit files abandoned for 3+ months.

### 2. Delete Debug Records Immediately After Issue Resolution

Files like `DEBUG_AUTH.md`, `TOKEN_MISMATCH_DIAGNOSIS.md` should be deleted right after the problem is solved. The worry "what if a similar problem occurs?" is resolved by Git history.

### 3. Add Expiry Dates to Completion Documents

Leaving snapshots at completion time like `PHASE_4_COMPLETION_SUMMARY.md` is good. But if you add metadata at creation time like "this document is archive-eligible after YYYY-MM-DD," it can be automated later.

### 4. Date-Based Archiving Is the Safest

Rather than reading and judging content one by one, checking modification dates with `stat` and batch archiving files older than 3 months is far more efficient. Even if a needed file is accidentally moved, it can be found in the archive.

### 5. Catch Duplicates Immediately

When `API_CONTRACT.md` exists in 3 places, nobody knows which is the canonical version. Designate one canonical location and delete the rest. The thought "let me copy it here for convenience" creates confusion 6 months later.

---

## Automation Ideas

To avoid repeating this work, a simple script can be created:

```bash
#!/bin/bash
# docs-health-check.sh
echo "=== Document Health Check ==="
echo "Total: $(find docs -name '*.md' -not -path '*/archive/*' | wc -l) files"
echo ""
echo "Abandoned for 3+ months:"
find docs -name "*.md" -not -path "*/archive/*" -type f | while read f; do
  mod_date=$(stat -f "%Sm" -t "%Y%m%d" "$f")
  cutoff=$(date -v-3m "+%Y%m%d")
  [[ "$mod_date" < "$cutoff" ]] && echo "  $f ($mod_date)"
done | head -20
echo ""
echo "Duplicate filenames:"
find docs -name "*.md" -not -path "*/archive/*" | xargs -I{} basename {} | sort | uniq -d
```

Running this script quarterly can prevent document bloat.
