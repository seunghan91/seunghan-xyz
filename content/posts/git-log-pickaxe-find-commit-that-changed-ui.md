---
title: "git log -S로 UI가 언제 바뀌었는지 추적하기 — pickaxe, blame, show 실전 조합"
date: 2026-03-25
draft: false
tags: ["git", "debugging", "pickaxe", "git-log", "code-archaeology"]
categories: ["Dev"]
description: "사이드바 타이틀이 언제 팀명으로 바뀌었는지 git log -S, git show, git blame을 조합해 원인 커밋을 추적한 실전 기록. pickaxe 옵션의 동작 원리와 -G 옵션과의 차이까지 정리했다."
---

## 사이드바 타이틀이 이상하다

Rails + Hotwire Native 기반 웹앱을 운영하고 있다. 어느 날 사이드바 상단에 원래 표시되던 앱 타이틀 대신 "리서치·정보분석" 같은 팀 이름이 들어가 있는 걸 발견했다. 분명 예전에는 앱 이름이 나왔는데 언제 바뀐 건지 모르겠다.

이런 상황, 개발하다 보면 꽤 자주 겪는다. "이거 원래 이랬나?" 싶은 순간이 오면, 코드를 뒤지기 전에 Git 히스토리를 먼저 파보는 게 훨씬 빠르다.

이번에 실제로 `git log -S`, `git show`, `git diff`를 조합해서 원인 커밋을 찾아낸 과정을 정리했다.

---

## 문제 상황: 뭐가 바뀌었는지는 안다

해당 코드는 ViewComponent 기반의 `AppShellComponent` 템플릿이었다. 사이드바 로고 영역에 이런 코드가 들어있었다:

```erb
<span class="font-bold text-lg truncate">
  <%= @team_name.present? ? @team_name : @title %>
</span>
```

`@team_name`이 있으면 팀명을, 없으면 앱 타이틀을 표시하는 로직이다. 원래는 `@title`만 표시했을 텐데, `@team_name` 분기가 언제 추가됐는지가 문제였다.

---

## 1단계: git log -S로 변수 도입 시점 찾기

`git log -S`는 Git에서 **pickaxe**라고 불리는 옵션이다. 특정 문자열이 추가되거나 삭제된 커밋만 필터링해서 보여준다. 단순히 해당 문자열이 diff에 포함된 커밋이 아니라, **해당 문자열의 출현 횟수가 변한 커밋**만 골라내는 게 핵심이다.

```bash
git log --oneline -S "@team_name" -- app/components/layout/app_shell_component.html.erb
```

결과:

```
2750ad4 feat: Mermaid UX Flow 자동 생성 + 과제 종료/공개 토글 + 전체화면 수정
d4ad940 feat: 모바일 반응형 네비게이션 레이아웃 구현
2a928b1 Refactor UI components with design token updates and layout improvements
```

3개 커밋이 나왔다. `@team_name`이라는 변수가 이 파일에서 추가/삭제/변경된 커밋들이다.

---

## 2단계: git show로 각 커밋 확인

가장 오래된 커밋부터 확인한다:

```bash
git show 2a928b1 --stat | head -20
```

```
commit 2a928b1
Author: seunghan Kim
Date:   Tue Mar 10 13:00:47 2026 +0900

    Refactor UI components with design token updates and layout improvements

 app/components/layout/app_shell_component.rb    |  57 +++++++-
 ...
```

`app_shell_component.rb`에 `team_name` 파라미터가 처음 추가된 커밋이었다. 하지만 이 커밋에서는 Ruby 파일(컴포넌트 클래스)만 수정했고, 템플릿에서는 아직 사용하지 않았다.

다음 커밋을 확인했다:

```bash
git show d4ad940 -- app/components/layout/app_shell_component.html.erb | head -40
```

```diff
+  <header class="md:hidden fixed top-0 left-0 right-0 z-50 ...">
+    <span class="font-bold text-base truncate">
+      <%= @team_name.present? ? @team_name : @title %>
+    </span>
+  </header>
```

여기다. `d4ad940` 커밋에서 **모바일 반응형 네비게이션**을 추가하면서, 모바일 상단 헤더에 `@team_name` 분기 로직을 처음 넣었다. 이후 `2750ad4`에서 데스크톱 사이드바에도 동일한 로직이 복사된 거였다.

---

## 3단계: 수정과 커밋

원인을 파악했으니 수정은 간단하다. 두 곳 모두 `@title`만 표시하도록 변경했다:

```erb
<%# 변경 전 %>
<%= @team_name.present? ? @team_name : @title %>

<%# 변경 후 %>
<%= @title %>
```

모바일 헤더와 데스크톱 사이드바 두 군데를 수정하고 커밋했다.

---

## pickaxe의 동작 원리

pickaxe(`-S`)가 정확히 어떻게 동작하는지 이해하면 활용 범위가 넓어진다.

### -S vs -G: 차이가 중요하다

| 옵션 | 동작 방식 | 용도 |
|------|----------|------|
| `-S "string"` | 문자열의 **출현 횟수가 변한** 커밋만 표시 | 변수/함수가 처음 도입되거나 삭제된 시점 찾기 |
| `-G "regex"` | diff에서 해당 **패턴이 포함된 줄이 변경된** 커밋 표시 | 특정 패턴이 수정된 모든 커밋 찾기 |

실질적인 차이를 예시로 보면:

```ruby
# 커밋 A: 줄 추가
team_name = "리서치팀"

# 커밋 B: 줄 이동 (같은 파일 내에서 위치만 변경)
# team_name = "리서치팀"  ← 삭제
team_name = "리서치팀"    # ← 다른 위치에 추가
```

- `-S "team_name"`: 커밋 A만 표시 (출현 횟수 변화 없는 B는 무시)
- `-G "team_name"`: 커밋 A, B 모두 표시 (diff에 해당 줄이 포함)

코드가 언제 **처음 도입**됐는지 찾을 때는 `-S`, 어떤 **수정이라도** 추적하고 싶을 때는 `-G`를 쓴다.

---

## 실전에서 자주 쓰는 pickaxe 패턴

### 특정 파일로 범위 제한

```bash
git log -S "team_name" -- app/components/layout/
```

`--` 뒤에 경로를 지정하면 해당 디렉토리 내 파일만 검색한다. 대규모 프로젝트에서 검색 속도를 크게 줄일 수 있다.

### diff까지 한번에 보기

```bash
git log -S "team_name" -p --pickaxe-all
```

`-p` 옵션을 추가하면 각 커밋의 diff를 함께 출력한다. `--pickaxe-all`은 해당 문자열이 변경된 파일뿐 아니라 **같은 커밋의 전체 diff**를 보여준다.

### 처음 도입된 커밋 바로 찾기

```bash
git log -S "team_name" --reverse
```

`--reverse`를 붙이면 시간순(오래된 것부터)으로 정렬되므로, 맨 첫 번째 결과가 해당 코드를 처음 도입한 커밋이다.

### 대소문자 무시 검색

```bash
git log -S "TeamName" -i
```

`-i` 옵션으로 대소문자를 무시할 수 있다. 변수명의 casing이 불확실할 때 유용하다.

### 정규표현식으로 검색

```bash
git log -G "team_name\s*=" -p
```

`-G`는 정규표현식을 지원한다. 변수 할당, 함수 호출 등 패턴이 복잡할 때 쓴다.

### 날짜 범위 제한

```bash
git log -S "deprecated_method" --since="2026-01-01" --until="2026-03-01"
```

특정 기간 내에서만 검색할 수 있다. "지난 달에 뭔가 바뀐 것 같은데" 같은 상황에서 유용하다.

---

## git blame vs git log -S vs git bisect: 언제 뭘 쓸까

셋 다 "코드 변경 추적"이라는 같은 목적이지만, 접근 방식이 다르다.

| 도구 | 질문 | 동작 방식 | 적합한 상황 |
|------|------|----------|------------|
| `git blame` | "이 줄을 마지막으로 누가 바꿨지?" | 파일의 각 줄에 마지막 수정 커밋을 매핑 | 특정 줄의 최근 변경자를 빠르게 확인 |
| `git log -S` | "이 코드가 언제 처음 생겼지?" | 문자열 출현 횟수 변화를 기준으로 커밋 필터링 | 변수/함수의 도입·삭제 시점 추적 |
| `git bisect` | "이 버그가 어느 커밋에서 시작됐지?" | 이진 탐색으로 good/bad 커밋 사이를 좁혀감 | 동작이 깨진 커밋을 찾을 때 (재현 가능한 버그) |

### 실전 사용 흐름

내가 자주 쓰는 조합 순서가 있다:

**1단계 — blame으로 빠르게 확인**

```bash
git blame app/components/layout/app_shell_component.html.erb
```

해당 줄의 마지막 수정 커밋이 바로 나온다. 이걸로 바로 원인이 보이면 끝이다.

**2단계 — blame으로 부족하면 pickaxe**

blame은 **마지막** 수정만 보여준다. 그 줄이 여러 번 수정됐거나, 다른 파일에서 복사돼 온 경우에는 소용없다. 이때 `git log -S`로 해당 코드의 전체 히스토리를 추적한다.

**3단계 — 동작 검증이 필요하면 bisect**

pickaxe는 텍스트 기반 검색이라, "이 코드가 있으면 버그가 발생하는가"까지는 알려주지 않는다. 특정 기능이 깨진 시점을 정확히 찾아야 할 때는 bisect가 낫다:

```bash
git bisect start
git bisect bad HEAD
git bisect good abc1234
# Git이 중간 커밋을 checkout → 테스트 → good/bad 반복
```

20,000개 커밋이 있어도 약 15번 테스트면 원인 커밋을 찾는다. O(log n)의 위력이다.

---

## blame의 한계: 왜 pickaxe가 필요한가

`git blame`은 만능이 아니다. 실제로 부딪히는 한계가 몇 가지 있다:

### 줄 이동/리팩토링에 취약하다

코드를 다른 파일로 옮기거나, 같은 파일 내에서 위치만 바꾸면 blame은 그 "이동" 커밋을 마지막 수정으로 표시한다. 원래 그 코드를 작성한 커밋은 묻혀버린다.

```bash
# blame은 이동 커밋만 보여줌
git blame app/components/layout/app_shell_component.html.erb -L 38,40
# → 2750ad4 (2026-03-15) 로 표시

# pickaxe는 원래 도입 커밋까지 보여줌
git log -S "@team_name" --reverse -- app/components/layout/
# → 2a928b1 (2026-03-10) 이 첫 번째로 나옴
```

### 여러 파일에 걸친 변경을 추적하기 어렵다

blame은 한 파일 단위로 동작한다. "이 변수가 프로젝트 전체에서 언제 처음 사용됐는지"는 pickaxe가 더 적합하다:

```bash
# 프로젝트 전체에서 team_name 변수의 히스토리
git log -S "team_name" --oneline --name-status
```

이 명령은 `team_name`이 추가/삭제된 모든 커밋과 관련 파일을 한번에 보여준다.

---

## 자동화: bisect run

수동으로 good/bad를 반복하기 귀찮다면, 테스트 스크립트를 만들어서 자동화할 수 있다:

```bash
git bisect start
git bisect bad HEAD
git bisect good v1.0
git bisect run ./test_sidebar_title.sh
```

`test_sidebar_title.sh`가 exit 0이면 good, non-zero면 bad로 자동 판정된다. CI 환경에서 회귀 테스트와 조합하면 강력하다.

---

## 알려진 함정과 주의사항

### pickaxe는 공백에 민감하다

```bash
# 이건 찾는다
git log -S "@team_name"

# 이건 못 찾을 수 있다 (앞뒤 공백 차이)
git log -S " @team_name "
```

검색 문자열이 코드에 있는 것과 정확히 일치해야 한다. 확실하지 않으면 `-G`로 정규표현식 검색을 쓰는 게 안전하다.

### 대규모 리포에서는 느릴 수 있다

pickaxe는 모든 커밋의 diff를 확인하기 때문에, 커밋이 수만 개인 리포에서는 시간이 걸린다. `--` 뒤에 파일 경로를 지정하거나 `--since`로 날짜를 제한하면 검색 범위를 줄일 수 있다.

### merge 커밋 주의

`-S`는 기본적으로 merge 커밋을 건너뛴다. merge 커밋까지 포함해서 검색하려면 `--full-history` 옵션을 추가한다:

```bash
git log -S "team_name" --full-history
```

---

## 정리

| 상황 | 추천 명령어 |
|------|------------|
| "이 줄 누가 바꿨지?" | `git blame <file>` |
| "이 변수가 언제 처음 생겼지?" | `git log -S "변수명" --reverse` |
| "이 패턴이 수정된 모든 커밋 보여줘" | `git log -G "패턴" -p` |
| "이 기능이 어디서 깨졌지?" | `git bisect start` + `good`/`bad` |
| "특정 파일 내에서만 추적" | `git log -S "문자열" -- path/to/file` |

"이거 원래 이랬나?" 싶은 순간이 오면, 코드를 뒤지기 전에 `git log -S`를 먼저 돌려보자. 대부분의 경우 30초 안에 원인 커밋을 찾을 수 있다. blame으로 부족하면 pickaxe, pickaxe로 부족하면 bisect — 이 순서만 기억하면 된다.
