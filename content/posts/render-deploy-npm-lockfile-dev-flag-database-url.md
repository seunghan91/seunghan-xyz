---
title: "Render 배포 실패 두 가지 — npm lockfile dev 플래그와 DATABASE_URL 소켓 오류"
date: 2026-03-30
draft: false
tags: ["render", "npm", "rails", "postgresql", "devops"]
categories: ["Rails", "DevOps"]
description: "Render 빌드에서 Cannot find package 'vite-plugin-ruby' 에러와 PostgreSQL 소켓 연결 실패를 디버깅한 기록. npm package-lock.json의 dev 플래그 함정과 PG18 업그레이드 후 DATABASE_URL 문제를 다룬다."
---

Render에서 배포가 갑자기 안 되기 시작했다. 한 번도 아니고 두 번 연속으로, 서로 다른 이유로. 첫 번째는 Vite 빌드에서 패키지를 못 찾는다는 에러, 두 번째는 Rails 서버가 PostgreSQL에 소켓으로 연결하려다 죽는 오류였다. 둘 다 원인을 찾기까지 상당히 헤맸다.

---

## 첫 번째 오류: `Cannot find package 'vite-plugin-ruby'`

빌드 로그에 이런 에러가 찍혔다.

```
failed to load config from /opt/render/project/src/.../vite.config.ts
error during build:
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'vite-plugin-ruby' imported from vite.config.ts
```

`vite-plugin-ruby`는 분명히 `package.json`의 `dependencies`에 들어있었다. `devDependencies`가 아니라 `dependencies`에.

```json
"dependencies": {
  "vite": "^5.4.21",
  "vite-plugin-ruby": "^5.1.3",
  "@sveltejs/vite-plugin-svelte": "^4.0.4",
  ...
}
```

그런데 `npm install --omit=dev`를 쓰면 이 패키지가 설치가 안 된다. 왜?

---

## npm lockfile의 `dev` 플래그 문제

`package-lock.json`을 직접 열어서 해당 항목을 확인했다.

```json
"node_modules/vite-plugin-ruby": {
  "version": "5.1.3",
  "resolved": "...",
  "integrity": "...",
  "dev": true,
  ...
}
```

`dev: true`가 박혀있었다.

`package.json`에는 `dependencies`에 있지만, `package-lock.json`에는 `"dev": true`로 마킹된 것이다. 이게 왜 발생하냐면, 과거에 이 패키지가 `devDependencies`에 있다가 나중에 `dependencies`로 옮겨졌는데, lockfile이 제대로 재생성되지 않았기 때문이다.

**핵심은 `--omit=dev`가 `package.json`이 아닌 `package-lock.json`의 `dev` 플래그를 기준으로 패키지를 제외한다는 것이다.**

즉:
- `package.json`: `dependencies`에 있음 → "프로덕션 패키지"
- `package-lock.json`: `"dev": true` → "이건 dev 패키지임"
- `npm install --omit=dev`: lockfile 기준으로 건너뜀 → 설치 안 됨

이 두 파일이 불일치할 때 lockfile이 우선된다.

---

## 왜 이런 불일치가 생기나

npm은 lockfile을 생성할 때 각 패키지가 어떤 경로로 요구되는지 추적해서 `dev` 플래그를 결정한다. `package.json`에서 `devDependencies → dependencies`로 패키지를 옮겨도, lockfile을 명시적으로 재생성하지 않으면 기존 `dev: true` 플래그가 그대로 남는다.

`npm install`을 그냥 실행하면 되지 않냐고 할 수 있는데, 이 프로젝트는 로컬에서 pnpm을 쓰고 있었다 (`pnpm-lock.yaml`이 존재). npm으로 install을 시도하면 arborist 내부에서 에러가 난다.

```
npm error Cannot read properties of null (reading 'matches')
npm error A complete log of this run can be found in: ~/.npm/_logs/...
```

pnpm이 관리하는 `node_modules`의 심링크 구조와 npm의 dependency tree 계산이 충돌하는 것이다. 이 상태에서 `npm install --package-lock-only`도 같은 이유로 실패했다.

---

## 해결 방법

가장 빠른 수정은 빌드 스크립트에서 `--omit=dev`를 `--include=dev`로 바꾸는 것이다.

```bash
# 변경 전
npm install --omit=dev

# 변경 후
npm install --include=dev
```

`--include=dev`를 쓰면 lockfile의 `dev` 플래그와 무관하게 모든 패키지를 설치한다. 빌드 서버에서는 Vite, vite-plugin-ruby 같은 빌드 도구가 반드시 필요하므로 이 방식이 맞다.

근본적인 수정은 `package.json`을 올바르게 정리하고 lockfile을 재생성하는 것이다. 빌드 도구는 `dependencies`에 두는 게 맞다 (런타임이 아닌 빌드타임에 쓰이더라도, Render 같은 환경에서는 빌드 단계에 필요하므로).

| 패키지 | 올바른 위치 |
|--------|-------------|
| `vite`, `vite-plugin-ruby` | `dependencies` |
| `@sveltejs/vite-plugin-svelte` | `dependencies` |
| `@tailwindcss/vite` | `dependencies` |
| `vitest`, `jsdom` | `devDependencies` |
| `@playwright/test` | `devDependencies` |

---

## 두 번째 오류: PostgreSQL 소켓 연결 실패

빌드는 통과했는데 이번엔 배포 단계(`update_failed`)에서 죽었다. Rails 로그를 보니:

```
Unable to load application: ActiveRecord::ConnectionNotEstablished:
connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed:
No such file or directory
```

유닉스 소켓으로 PostgreSQL에 붙으려는 것이다. 이 에러는 `DATABASE_URL`이 없거나 호스트 없이 로컬 DB를 찾을 때 발생한다. Render에서는 반드시 TCP 연결로 외부 DB에 붙어야 한다.

---

## 왜 갑자기 DATABASE_URL이 없어졌나

PostgreSQL 16 → 18 업그레이드 유지보수가 있었다. Render는 이 과정에서 DB의 내부 호스트명을 변경하는 경우가 있다. 만약 `DATABASE_URL`이 Render의 "linked database" 기능으로 자동 주입되는 게 아니라, 수동으로 환경변수에 설정된 값이라면 업그레이드 후 예전 호스트명을 계속 가리킬 수 있다.

이 경우엔 환경변수가 아예 없어진 상태였다. 이전 DB 인스턴스에서 새 PG18 인스턴스로 마이그레이션되면서 서비스의 환경변수 연결이 끊어진 것으로 보인다.

---

## 해결 방법

Render 대시보드 → DB 서비스 → "Connect" 탭에서 **Internal Database URL**을 복사한다.

내부 URL 형식은 이렇다:

```
postgresql://user:password@dpg-xxxxxxxxxxxxxxxx-a/dbname
```

외부 URL과 다르게 호스트명에 `.render.com` 도메인이 없고, 같은 리전의 Render 서비스끼리만 이 주소로 통신할 수 있다. Render MCP가 있다면 직접 업데이트도 가능하다:

```
update_environment_variables(
  serviceId: "srv-...",
  envVars: [{ key: "DATABASE_URL", value: "postgresql://..." }],
  replace: false
)
```

`replace: false`를 쓰면 기존 환경변수는 유지하고 `DATABASE_URL`만 덮어쓴다. Render의 PUT API는 기본적으로 전체 교체(`replace: true`)가 되므로 조심해야 한다.

---

## 이번에 확인한 Render 배포 흐름

```
git push
  → build 단계 (render-build.sh 실행)
      → bundle install
      → npm install
      → vite build
  → pre-deploy 단계 (서버 네트워크 사용 가능)
      → rails db:migrate
  → update 단계 (새 인스턴스 기동)
      → puma 시작
      → DB 연결 확인
  → live (헬스체크 통과)
```

빌드 컨테이너에서는 내부 DB 호스트명을 못 쓰는 케이스가 있어서 `db:migrate`는 pre-deploy 단계로 옮겨야 한다는 것도 이번에 알았다. 빌드 컨테이너는 서비스 네트워크 외부에 있기 때문이다.

---

## 정리

오늘 배운 것 두 가지:

1. **npm lockfile의 `dev` 플래그는 `package.json`과 독립적으로 관리된다.** 패키지를 devDependencies에서 dependencies로 옮기면 lockfile도 재생성해야 한다. 그게 안 되는 환경이라면 `--include=dev`로 lockfile 플래그를 무시하고 전부 설치하는 게 낫다.

2. **Render DB 업그레이드 후에는 DATABASE_URL을 반드시 확인해야 한다.** 특히 수동으로 환경변수를 설정한 경우, 업그레이드 이후 내부 호스트명이 바뀌어서 연결이 끊길 수 있다. `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432"` 에러가 나면 DATABASE_URL 누락을 먼저 의심하면 된다.
