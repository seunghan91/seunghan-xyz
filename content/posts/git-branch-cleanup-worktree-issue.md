---
title: "Git 브랜치 정리 — worktree 에러 포함 완전 클린업 가이드"
date: 2026-03-31
draft: false
tags: ["git", "worktree", "브랜치관리", "github", "개발환경"]
categories: ["Dev"]
description: "머지된 브랜치 한 번에 정리하다 'cannot delete branch used by worktree' 에러 만났을 때 해결법. 로컬·원격 브랜치, dependabot 브랜치까지 전부 정리하는 방법 정리."
---

프로젝트를 어느 정도 운영하다 보면 브랜치가 쌓인다. feature 브랜치, claude가 만든 자동 브랜치, dependabot 브랜치까지 정리 안 하면 `git branch -a` 결과가 화면 가득 찬다.

오늘 작업하다 머지된 브랜치들 싹 정리했는데, `feature/link-in-bio` 삭제하려고 하니까 이런 에러가 났다.

```
error: cannot delete branch 'feature/link-in-bio' used by worktree at '/path/to/.worktrees/link-in-bio'
```

처음엔 그냥 `-D` 옵션으로 강제 삭제하면 되지 않나 싶었는데, 그게 올바른 방법이 아니다. worktree를 먼저 제거하는 게 맞다.

---

## PR이 이미 머지됐는지 확인하는 법

브랜치 정리 전에 먼저 해야 할 게 있다. 각 브랜치가 main에 이미 포함됐는지 확인하는 것.

```bash
# 브랜치 목록 전체 보기
git branch -a

# main보다 앞선 커밋이 있는지 확인
git log --oneline main..feature/some-branch

# 커밋 수로 확인
ahead=$(git log --oneline main..feature/some-branch | wc -l | tr -d ' ')
behind=$(git log --oneline feature/some-branch..main | wc -l | tr -d ' ')
echo "ahead: $ahead, behind: $behind"
```

`ahead: 0`이면 해당 브랜치의 모든 커밋이 main에 포함됐다는 뜻이다. 삭제해도 코드 손실 없음.

머지된 브랜치만 한 번에 뽑는 명령어도 있다.

```bash
# main에 머지된 로컬 브랜치 목록
git branch --merged main | grep -v "^\*\|main"

# 원격 브랜치 중 머지된 것
git branch -r --merged origin/main | grep -v "main\|HEAD"
```

---

## git worktree가 뭔지

`git worktree`는 같은 저장소에서 여러 브랜치를 동시에 다른 디렉토리에 체크아웃할 수 있는 기능이다.

```bash
# 새 worktree 생성 (feature/link-in-bio를 .worktrees/link-in-bio 폴더에)
git worktree add .worktrees/link-in-bio feature/link-in-bio

# 현재 worktree 목록
git worktree list
```

결과가 이런 식으로 나온다.

```
~/ax_admin               af35873 [main]
~/ax_admin/.worktrees/link-in-bio  a628943 [feature/link-in-bio]
```

메인 작업 디렉토리를 건드리지 않고 다른 브랜치를 병렬로 확인할 때 유용하다. Claude Code 같은 AI 에이전트들이 자동으로 worktree를 만들어서 작업하는 경우도 많다.

문제는 worktree가 브랜치를 "점유"하고 있으면 그 브랜치를 삭제할 수 없다는 것이다.

---

## 'cannot delete branch used by worktree' 에러 해결

### 상황 1: worktree 폴더를 그냥 지워버린 경우

Finder나 `rm -rf`로 폴더를 직접 지웠는데 Git은 여전히 worktree가 존재한다고 생각한다. 이 경우 `prune`으로 정리한다.

```bash
git worktree prune
git branch -d feature/link-in-bio
```

`prune`은 Git의 worktree 목록을 순회하면서 실제로 존재하지 않는 폴더에 연결된 항목을 제거한다.

### 상황 2: worktree 폴더가 아직 살아있는 경우 (정상 제거)

```bash
# 1. worktree 목록 확인
git worktree list

# 2. 상태 확인 (미커밋 변경사항 없는지)
git -C /path/to/worktree status

# 3. worktree 제거
git worktree remove /path/to/worktree

# 4. 브랜치 삭제
git branch -d feature/link-in-bio
```

`git worktree remove`는 클린 상태(미커밋 변경 없음)일 때만 작동한다. 수정 중인 파일이 있으면 `--force` 옵션이 필요하다. 단, 미저장 작업이 날아가므로 주의.

### 상황 3: 강제 삭제가 필요한 경우

작업을 포기하고 강제로 지우려면:

```bash
git worktree remove --force /path/to/worktree
git branch -D feature/link-in-bio  # 대문자 D = 강제 삭제
```

`-d`는 머지 여부를 확인하고 삭제, `-D`는 무조건 삭제다. 머지된 브랜치라면 `-d`로도 충분하다.

---

## 원격 브랜치 대량 삭제

로컬 정리가 끝나면 원격도 정리해야 한다. 특히 dependabot 브랜치가 여러 개 쌓인 경우.

### 개별 삭제

```bash
git push origin --delete feature/link-in-bio
```

### 여러 개 한 번에

```bash
git push origin --delete \
  feature/link-in-bio \
  refactor/old-design \
  claude/auto-branch-abc123
```

`--delete` 뒤에 공백으로 구분해서 여러 개 넣을 수 있다. 단, 존재하지 않는 브랜치가 하나라도 있으면 전체 명령이 실패한다.

### 안전하게: fetch --prune 먼저

원격에서 이미 삭제된 브랜치의 로컬 참조를 먼저 정리하고 삭제 작업을 한다.

```bash
# 원격 삭제된 브랜치의 로컬 참조 제거
git fetch --prune origin

# 이후 삭제 시도
git push origin --delete branch-name
```

`error: unable to delete 'xxx': remote ref does not exist` 에러가 나오면 이미 삭제됐거나 이름이 틀린 것이다. `git fetch --prune` 후 `git branch -a`로 실제 목록 확인 후 진행.

---

## 전체 클린업 순서

실제로 작업할 때 쓰는 순서다.

```bash
# 1. 원격과 동기화
git fetch --prune origin
git pull origin main

# 2. 브랜치 현황 파악
git branch -a

# 3. worktree 현황 파악
git worktree list

# 4. 각 브랜치의 ahead/behind 확인
for branch in $(git branch | grep -v main); do
  ahead=$(git log --oneline main..$branch 2>/dev/null | wc -l | tr -d ' ')
  behind=$(git log --oneline $branch..main 2>/dev/null | wc -l | tr -d ' ')
  echo "$branch — ahead: $ahead, behind: $behind"
done

# 5. worktree가 있는 브랜치는 worktree 먼저 제거
git worktree remove /path/to/worktree

# 6. 로컬 브랜치 삭제
git branch -d branch1 branch2 branch3

# 7. 원격 브랜치 삭제
git push origin --delete branch1 branch2 branch3
```

---

## dependabot 브랜치 처리

`dependabot/github_actions/actions/checkout-6` 같은 브랜치들이 쌓이는 건 GitHub Actions 의존성 업데이트 PR이 자동 생성됐기 때문이다. PR을 머지하거나 닫으면 브랜치도 자동 삭제되는 게 기본 동작인데, 설정에 따라 남는 경우가 있다.

일반 브랜치와 삭제 방법은 동일하다.

```bash
git push origin --delete dependabot/github_actions/actions/checkout-6
```

단, 이미 삭제된 경우 `remote ref does not exist` 에러가 나온다. `git fetch --prune` 먼저 실행하면 해결된다.

GitHub Settings → General → Pull Requests → "Automatically delete head branches" 옵션을 켜두면 PR 머지 직후 브랜치가 자동 삭제된다. 이게 기본으로 켜져 있으면 이런 정리 작업을 덜 해도 된다.

---

## 브랜치 관리 전략 비교

| 방식 | 장점 | 단점 |
|------|------|------|
| PR 머지 후 즉시 삭제 | 깔끔함 유지, 혼란 없음 | 수동 작업 필요 (자동화 안 하면) |
| GitHub 자동 삭제 설정 | 신경 안 써도 됨 | 원격만 삭제, 로컬은 수동 |
| 주기적 일괄 정리 | 자유로운 작업 흐름 | 가끔 쌓이면 정리가 번거로움 |
| git alias 자동화 | 명령 한 방에 해결 | 초기 설정 필요 |

git alias로 자동화하면 편하다. `~/.gitconfig`에 추가:

```ini
[alias]
  cleanup = "!git branch --merged | grep -v '\\*\\|main' | xargs -n 1 git branch -d"
  prune-all = "!git fetch --prune && git remote prune origin"
```

```bash
# 사용
git cleanup   # 머지된 로컬 브랜치 일괄 삭제
git prune-all # 원격 참조 정리
```

---

## 주의할 점

**`-D`와 `-d` 구분**: `-d`는 머지된 브랜치만 삭제하고, `-D`는 머지 여부 무관하게 강제 삭제다. 실수로 날리면 `git reflog`로 복구할 수 있지만, 번거롭다. 확실히 머지된 것만 `-d`로 지우는 습관을 들이는 게 낫다.

**worktree 폴더를 직접 삭제하지 말 것**: `rm -rf`로 지우면 Git 내부 상태와 어긋나서 나중에 `git worktree prune`을 따로 실행해야 한다. 항상 `git worktree remove`로 제거.

**원격 브랜치 대량 삭제 시 오타 주의**: 존재하지 않는 브랜치명이 하나라도 섞이면 전체 명령이 실패한다. `git branch -r | grep pattern`으로 실제 이름 확인 후 진행.

**공유 브랜치는 팀원 확인 후 삭제**: 혼자 쓰는 저장소면 상관없지만, 팀 저장소라면 `develop`이나 `staging` 같은 공유 브랜치는 절대 삭제하면 안 된다.

---

## 마무리

worktree 에러 만나면 당황하기 쉽지만 패턴은 단순하다. 폴더가 살아있으면 `git worktree remove`, 폴더가 이미 사라졌으면 `git worktree prune`. 그 다음에 `git branch -d`로 삭제.

원격 브랜치는 `git fetch --prune`으로 상태 동기화 후 `git push origin --delete`로 정리. dependabot 브랜치도 동일한 방법으로 처리된다.

브랜치를 자주 정리해두면 `git branch -a` 결과가 깔끔하고, 어떤 작업이 진행 중인지 한눈에 파악하기 쉽다. GitHub 설정에서 "Automatically delete head branches"도 켜두면 PR 머지 후 원격 브랜치는 자동으로 사라지니 참고.

관련 글: [git fetch와 git pull의 차이](/posts/git-fetch-vs-pull/)
