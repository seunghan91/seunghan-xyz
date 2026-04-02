---
title: "pnpm ERR_PNPM_OUTDATED_LOCKFILE — CI 배포 실패 진단과 해결"
date: 2026-04-02
draft: false
tags: ["pnpm", "CI/CD", "Render", "monorepo", "배포"]
description: "Render 배포에서 pnpm ERR_PNPM_OUTDATED_LOCKFILE 에러가 발생했다. CI 환경에서 frozen-lockfile이 기본 활성화되는 이유, 원인별 해결법, 재발 방지 방법을 정리했다."
---

Render에서 배포가 터졌다. 에러 메시지는 짧고 명확했지만 원인은 생각보다 다양했다.

```
ERR_PNPM_OUTDATED_LOCKFILE  Cannot install with "frozen-lockfile" because
pnpm-lock.yaml is not up to date with <ROOT>/apps/legal_audit_web/package.json

Note that in CI environments this setting is true by default.
If you still need to run install in such cases, use "pnpm install --no-frozen-lockfile"

Failure reason:
  specifiers in the lockfile don't match specifiers in package.json:
* 1 dependencies were added: @ios26_design_system/svelte-inertia@^1.0.0
```

로컬에서는 잘 됐는데 CI에서만 죽는 전형적인 패턴이다. 원인과 해결법을 기록해둔다.

---

## CI에서 frozen-lockfile이 자동 활성화되는 이유

`pnpm install`은 CI 환경을 자동 감지해서 `--frozen-lockfile`을 기본으로 켠다. CI 감지 로직은 `ci-info` 패키지 기반이다.

```js
// pnpm이 내부적으로 사용하는 CI 감지 코드
exports.isCI = !!(
  env.CI ||                    // Travis CI, CircleCI, GitLab CI, Appveyor
  env.CONTINUOUS_INTEGRATION || // Travis CI, Cirrus CI
  env.BUILD_NUMBER ||           // Jenkins, TeamCity
  env.RUN_ID ||                 // TaskCluster
  exports.name ||
  false
)
```

Render는 빌드 시 `CI=true` 환경변수를 설정하기 때문에 `pnpm install`이 자동으로 frozen 모드로 동작한다.

`--frozen-lockfile`이 켜지면 pnpm은 `pnpm-lock.yaml`과 `package.json`의 specifier가 완전히 일치해야만 설치를 진행한다. 불일치가 있으면 lockfile을 업데이트하지 않고 바로 에러로 종료한다.

| 환경 | frozen-lockfile 기본값 |
|------|----------------------|
| 로컬 개발 (`CI` 없음) | `false` — lockfile 자동 업데이트 |
| CI 환경 (`CI=true`) | `true` — 불일치 시 즉시 실패 |

로컬에서는 `pnpm install`이 알아서 lockfile을 갱신해주니까 문제를 못 느끼다가, CI에서 터지는 구조다.

---

## 원인 1: package.json에 패키지 추가했는데 lockfile 커밋 누락

이번에 겪은 케이스가 바로 이거다. `package.json`에 새 패키지를 추가하고 `pnpm install`까지 실행했지만, 업데이트된 `pnpm-lock.yaml`을 커밋에 포함시키지 않았다.

```bash
# 로컬에서 한 작업
$ pnpm add @ios26_design_system/svelte-inertia
# package.json 업데이트됨, pnpm-lock.yaml 업데이트됨

# 근데 커밋할 때
$ git add package.json
$ git commit -m "feat: add ios26 design system"
# pnpm-lock.yaml 누락!
```

GitHub에 올라간 상태: `package.json`은 새 패키지가 있는데 `pnpm-lock.yaml`은 예전 버전 그대로.

**해결**: lockfile 업데이트 후 함께 커밋한다.

```bash
$ pnpm install
$ git add pnpm-lock.yaml package.json
$ git commit -m "chore: update lockfile for @ios26_design_system/svelte-inertia"
```

---

## 원인 2: 로컬 pnpm 버전과 CI pnpm 버전 불일치

pnpm은 버전마다 lockfile 형식이 다르다. 로컬에서 pnpm v8로 생성한 lockfile을 CI가 pnpm v9로 읽으려 하면 에러가 난다.

```
ERR_PNPM_FROZEN_LOCKFILE_WITH_OUTDATED_LOCKFILE  Cannot perform a frozen
installation because the version of the lockfile is incompatible with this
version of pnpm
```

에러 메시지가 미묘하게 다르다. `OUTDATED_LOCKFILE`이 아니라 `FROZEN_LOCKFILE_WITH_OUTDATED_LOCKFILE`이면 버전 불일치 문제다.

**해결**: `package.json`의 `packageManager` 필드로 버전을 고정한다.

```json
{
  "packageManager": "pnpm@9.0.0"
}
```

이걸 설정하면 Corepack이 CI에서도 동일한 버전을 사용하도록 강제한다. 또는 CI 설정 파일에서 명시적으로 버전을 지정한다.

```yaml
# GitHub Actions 예시
- uses: pnpm/action-setup@v4
  with:
    version: 9.0.0
```

---

## 원인 3: pnpm v8 → v9 업그레이드로 lockfile 형식 변경

pnpm v9는 peer dependency 처리 방식이 바뀌면서 lockfile 형식 자체가 v9로 올라갔다. 기존 v6/v8 형식의 lockfile은 v9에서 frozen 모드로 읽을 수 없다.

```bash
# lockfile을 v9 형식으로 재생성
$ rm pnpm-lock.yaml
$ pnpm install
$ git add pnpm-lock.yaml
$ git commit -m "chore: regenerate lockfile for pnpm v9"
```

아니면 `--fix-lockfile` 옵션으로 기존 lockfile을 마이그레이션한다.

```bash
$ pnpm install --fix-lockfile
```

---

## 원인 4: monorepo에서 특정 workspace의 package.json만 변경

monorepo 구조에서는 루트 `pnpm-lock.yaml`이 모든 workspace의 의존성을 관리한다. `apps/web/package.json`을 바꿨는데 루트 lockfile을 업데이트 안 하면 같은 에러가 난다.

```
ERR_PNPM_OUTDATED_LOCKFILE  Cannot install with "frozen-lockfile" because
pnpm-lock.yaml is not up to date with <ROOT>/apps/web/package.json
```

이번 케이스도 monorepo(`apps/legal_audit_web/`) 구조였다. `apps/legal_audit_web/package.json`에 패키지를 추가했는데 루트의 `pnpm-lock.yaml`이 그걸 반영 안 하고 있었다.

루트에서 `pnpm install`을 실행해야 모든 workspace의 lockfile을 갱신한다.

```bash
# workspace 루트에서 실행
$ cd /path/to/monorepo-root
$ pnpm install
$ git add pnpm-lock.yaml
```

---

## Render 배포 로그에서 진단하는 방법

Render는 배포 실패 시 로그가 짧게 나온다. Render MCP나 대시보드에서 빌드 로그를 확인하면 정확한 실패 지점을 알 수 있다.

```
==> Running build command 'bundle config set deployment true &&
    bundle install &&
    pnpm install &&
    pnpm build &&
    bundle exec rails db:migrate RAILS_ENV=production'...

ERR_PNPM_OUTDATED_LOCKFILE  Cannot install with "frozen-lockfile"...

Failure reason:
  specifiers in the lockfile don't match specifiers in package.json:
* 1 dependencies were added: @ios26_design_system/svelte-inertia@^1.0.0

==> Build failed 😞
```

`Failure reason` 아래에 어떤 패키지가 불일치인지 정확히 나온다. pnpm 8.5.1 이후부터 이 메시지가 추가됐다.

---

## 빠른 해결법 vs 올바른 해결법

급할 때 `--no-frozen-lockfile`을 buildCommand에 넣고 싶은 유혹이 있다.

```yaml
# render.yaml — 임시방편 (권장 안 함)
buildCommand: >-
  pnpm install --no-frozen-lockfile &&
  pnpm build
```

이렇게 하면 CI가 매번 최신 버전으로 패키지를 resolve해서 재현 불가능한 빌드가 만들어진다. lockfile을 쓰는 이유가 없어진다.

**올바른 해결법**:
1. 로컬에서 `pnpm install` 실행
2. `pnpm-lock.yaml`을 반드시 커밋에 포함
3. PR 리뷰 시 `pnpm-lock.yaml` 변경 확인

---

## 재발 방지: pre-commit hook으로 lockfile 동기화 확인

`.husky/pre-commit`에 lockfile 검증을 추가하면 로컬에서 미리 잡을 수 있다.

```bash
#!/bin/sh
# .husky/pre-commit

# package.json 변경 시 pnpm-lock.yaml도 변경됐는지 확인
if git diff --cached --name-only | grep -q "package.json"; then
  if ! git diff --cached --name-only | grep -q "pnpm-lock.yaml"; then
    echo "⚠️  package.json이 변경됐는데 pnpm-lock.yaml이 스테이징되지 않았습니다."
    echo "   pnpm install 후 pnpm-lock.yaml을 커밋에 포함해주세요."
    exit 1
  fi
fi
```

---

## 정리

| 에러 메시지 | 원인 | 해결 |
|------------|------|------|
| `specifiers don't match` | package.json 변경 후 lockfile 커밋 누락 | `pnpm install` 후 lockfile 함께 커밋 |
| `lockfile is incompatible` | pnpm 버전 불일치 (로컬 vs CI) | `packageManager` 필드로 버전 고정 |
| `lockfile needs updates` | pnpm v8→v9 lockfile 형식 변경 | `pnpm install --fix-lockfile` 후 커밋 |
| monorepo workspace 에러 | workspace package.json 변경 후 루트 lockfile 미갱신 | 루트에서 `pnpm install` |

pnpm의 frozen-lockfile은 재현 가능한 빌드를 위한 장치다. 에러가 나면 lockfile을 bypass하는 게 아니라 lockfile을 올바른 상태로 만드는 게 맞다.

관련 포스트: [Rails + SolidQueue Render 배포 삽질](/posts/rails-solidqueue-render-manual-assignment/)
