---
title: "Render에서 VitePress 빌드가 갑자기 죽었다 — puppeteer가 devDependencies에 박혀있었던 이야기"
date: 2026-05-14
draft: false
tags: ["Render", "VitePress", "pnpm", "puppeteer", "CI/CD", "docs"]
description: "Render static site 빌드가 pnpm install 직후 출력 없이 죽었다. 빌드 캐시 청소로 일단 살아났지만, 진짜 원인은 devDependencies에 들어있던 puppeteer 24.x였다."
---

docs 사이트(`docs.1pass.dev`, VitePress) 배포가 갑자기 실패했다. Render 대시보드에는 "Exited with status 1 while building your code." 한 줄만 떴다.

수동으로 "Clear build cache & deploy" 한 번 누르니 그대로 살아났다. 그런데 코드 자체는 한 줄도 안 바뀌었으니 찜찜했다. **무엇이 진짜 문제였는지** 확인하고 가야 다음에 같은 상황에서 헤매지 않는다.

---

## 증상

- Render static site (`pnpm install --frozen-lockfile && pnpm run build`)
- 새 커밋 push → 자동 빌드 시작 → 30초 만에 `build_failed`
- Render 로그 API에 잡힌 마지막 줄:

  ```
  [ERR_PNPM_IGNORED_BUILDS] Ignored build scripts:
    esbuild@0.21.5, puppeteer@24.42.0, vue-demi@0.14.10

  Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
  ```

- 그 뒤로 stdout/stderr가 **한 줄도 없음.** 빌드 프로세스가 무언의 종료.

---

## 1차 가설: pnpm의 빌드 스크립트 차단?

`ERR_PNPM_IGNORED_BUILDS`는 pnpm 9+가 보안상의 이유로 의존성의 postinstall 스크립트를 기본 차단한 결과다. 처음엔 이게 원인인 줄 알았다.

하지만 잘 읽어보면 **에러가 아니라 경고**다. 차단된 스크립트는:

- `esbuild` — 네이티브 바이너리 다운로드 (postinstall 안 돌아도 npm 패키지에 prebuilt 포함)
- `puppeteer` — Chromium 다운로드 (이게 핵심)
- `vue-demi` — Vue 2/3 듀얼 빌드 alias 세팅

VitePress가 esbuild의 prebuilt 바이너리를 못 찾으면 빌드가 죽긴 한다. 그런데 같은 lockfile로 다른 환경에서는 멀쩡히 돌았다. 이게 진짜 원인이라기엔 약하다.

---

## 2차 가설: 메모리 부족

진짜 의심스러운 건 `puppeteer@24.42.0`이다. puppeteer가 npm install 단계에서 Chromium(~170MB)을 받아 `node_modules/puppeteer/.local-chromium/`에 풀어놓는다. Render free static build worker는 메모리/디스크가 빠듯하다.

`puppeteer`가 정말 빌드에 필요한지 확인해보자:

```bash
$ grep -rn "puppeteer" docs-site/ --include="*.mjs" --include="*.js" -l
docs-site/scripts/render-og.mjs
docs-site/scripts/render-og-variants.mjs
```

`scripts/render-og.mjs`:

```js
import puppeteer from "puppeteer";
import { dirname, join } from "node:path";

const browser = await puppeteer.launch({ headless: "new" });
const page = await browser.newPage();
await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
await page.goto("file://" + htmlPath, { waitUntil: "networkidle0" });
await page.screenshot({ path: outPath, type: "png" });
await browser.close();
```

**OG 이미지(소셜 미디어 미리보기) 한 번 만들고 끝나는 일회성 스크립트.** 결과물(`public/og-image.png`)은 이미 정적 파일로 커밋되어 있다.

`package.json`의 `build` 스크립트를 보면:

```json
"build": "npm run build:llms && vitepress build"
```

`render-og`는 호출되지도 않는다. 즉 **puppeteer는 빌드 파이프라인에 1도 안 쓰임.**

---

## 진단

`pnpm install --frozen-lockfile` 단계에서 puppeteer가 Chromium을 받느라 디스크/메모리/네트워크 부하 → 그 와중에 다른 무언가가 죽음 (esbuild prebuilt 압축 해제 실패 같은) → 빌드 프로세스가 출력 없이 종료.

**왜 캐시 청소 후엔 성공했나?** stale `node_modules` 캐시에 깨진 puppeteer 설치본이 남아있다가 frozen-lockfile 모드에서 재구성 실패했을 가능성이 높다. clearCache로 처음부터 다시 받게 하니 정상화됐다.

---

## 해결책

puppeteer를 `devDependencies`에서 빼고, OG 이미지 생성은 별도 워크플로로 분리한다.

**Before** (`docs-site/package.json`):

```json
"devDependencies": {
  "@scalar/api-reference": "^1.25.0",
  "puppeteer": "^24.42.0",
  "vitepress": "^1.5.0",
  "vue": "^3.5.0"
}
```

**After**:

```json
"devDependencies": {
  "@scalar/api-reference": "^1.25.0",
  "vitepress": "^1.5.0",
  "vue": "^3.5.0"
}
```

OG 이미지를 갱신할 일이 생기면 그때만 ad-hoc으로:

```bash
npx puppeteer@24 node scripts/render-og.mjs
```

또는 GitHub Actions workflow를 따로 만들어서 OG 이미지 갱신 PR만 자동화한다 (`workflow_dispatch` 트리거).

---

## 교훈

1. **빌드 시점에 필요 없는 헤비 의존성은 devDependencies에서도 빼라.** 일회성 스크립트는 `npx`나 별도 워크플로로.
2. **`pnpm install`이 받는 패키지 중 postinstall이 큰 것**(puppeteer, playwright, sharp, canvas 등)은 항상 의심 대상. Render/Vercel 같은 ephemeral build worker에서는 더더욱.
3. **Render 로그가 출력 없이 끊기면 메모리/디스크 압박을 먼저 의심하라.** stderr가 안 잡힐 수 있다.
4. **build cache clear는 임시 처방.** 진짜 원인을 안 잡으면 다음 release 때 재발한다.

---

## 메타

- 진단: `curl https://api.render.com/v1/services/{id}/deploys` + `/v1/logs?ownerId=...&resource=...` 로 실패한 deploy의 build 로그 끝까지 받아봄
- Render REST API 토큰 한 개로 모든 서비스 로그 접근 가능 — 빌드 실패 디버깅은 대시보드보다 API가 훨씬 빠르다
