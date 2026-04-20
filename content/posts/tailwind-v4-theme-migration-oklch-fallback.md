---
title: "Tailwind v4로 올렸는데 tailwind.config.js가 무시되고 있었다 — @theme 함정과 Chrome DevTools MCP로 검증한 과정"
date: 2026-04-21T09:00:00+09:00
draft: false
tags: ["tailwindcss", "svelte", "chrome-devtools-mcp", "css", "oklch"]
description: "Tailwind v4 프로젝트에서 브랜드 컬러가 푸르스름하게 보였다. tailwind.config.js의 커스텀 토큰이 전혀 반영되지 않고 v4 기본 OKLCH blue-600으로 폴백되던 것. @theme로 포팅하고 Chrome DevTools MCP로 픽셀 단위 검증한 기록."
---

디자인 시스템 문서에는 Primary #3182F6 Toss Blue라고 분명히 적혀 있었다. 그런데 Submit 버튼은 어쩐지 다른 파란색이었다. 기분 탓이 아니라 조금 더 보라끼가 돌고 푸르스름했다. 처음엔 모니터 캘리브레이션 문제인가 싶었는데, DevTools로 computed style을 찍어보니 `background-color: oklch(0.546 0.245 262.881)`. 예상한 `rgb(49, 130, 246)` 하고는 확실히 다른 값이었다.

원인을 찾아보니 **Tailwind CSS v4에서 `tailwind.config.js`를 완전히 무시하고 있었다**. 프로젝트는 `tailwindcss@4.1.18` 로 올라가 있는데 설정은 v3 문법(JavaScript object) 그대로였고, `@theme` 블록에는 주요 컬러 스케일이 일부만 포팅돼 있었다. 결과적으로 커스텀 토큰은 전혀 적용이 안 되고 v4 기본 OKLCH 팔레트로 렌더되던 상태.

같은 함정에 빠진 사람이 검색해서 찾아오길 바라며, 오늘 겪은 과정과 Chrome DevTools MCP로 픽셀 단위 검증한 방식까지 정리한다.

## Tailwind v4의 CSS-first 설정 구조

Tailwind v4가 v3와 가장 크게 달라진 건 **설정이 JavaScript에서 CSS로 이동**했다는 점이다. v3에서는 `tailwind.config.js`에 JavaScript object로 팔레트, spacing, radius를 정의했다:

```javascript
// tailwind.config.js — v3 문법
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#3182F6',
        gray: {
          100: '#F2F4F6',
          200: '#E5E8EB',
        },
      },
      borderRadius: {
        xl: '12px',
      },
    },
  },
}
```

v4에서는 이 파일이 **기본적으로 무시된다**. 공식 마이그레이션 가이드에 따르면, `@config` 지시어를 명시적으로 쓰지 않는 한 v4는 CSS 내부의 `@theme` 블록만 참조한다. 같은 설정을 v4로 옮기면 이렇게 된다:

```css
/* application.css — v4 문법 */
@import "tailwindcss";

@theme {
  --color-primary: #3182F6;
  --color-gray-100: #F2F4F6;
  --color-gray-200: #E5E8EB;
  --radius-xl: 12px;
}
```

CSS 커스텀 프로퍼티 형태로 선언하면 Tailwind가 자동으로 `bg-primary`, `bg-gray-100`, `rounded-xl` 같은 유틸리티 클래스를 만들어준다. v3 대비 두 가지 이점이 있다:

1. **네이티브 CSS에 노출됨** — `@theme` 블록의 모든 값은 `:root`의 커스텀 프로퍼티로 선언되므로 CSS Modules, `<style>` 블록, 서드파티 라이브러리에서도 `var(--color-primary)` 로 바로 쓸 수 있다
2. **빌드 파이프라인 단순화** — PostCSS 플러그인 체인을 거치지 않고 Lightning CSS 내부 파서가 직접 처리

문제는 마이그레이션 과정에서 v3 config를 **지우지 않고 그대로 둔 채** `@theme` 블록에 일부만 포팅한 상태가 만들어졌다는 것. Tailwind가 에러를 뱉지 않고 조용히 config 파일을 무시하기 때문에, 커스텀 토큰이 반영 안 된 상태로 빌드가 "성공"한다. 유틸리티 클래스 이름(`bg-primary`, `bg-gray-100`)은 여전히 v4가 생성하긴 하는데, 값이 **v4 기본 팔레트**에서 오게 된다.

## OKLCH 기본값이 문제가 되는 이유

Tailwind v4는 내부 기본 팔레트를 **OKLCH 색공간**으로 재정의했다. sRGB hex 대신 `oklch(L C H)` 문법을 쓴다. OKLCH는 인지적 균일성이 있는 색공간이어서, 같은 lightness 값이면 실제로 눈에 비슷한 밝기로 보인다. HSL이나 단순 sRGB에서는 blue-500과 yellow-500이 같은 50% lightness여도 노란색이 훨씬 밝게 보였는데, OKLCH는 그 불일치를 해결한다.

그런데 이 과정에서 **기본 팔레트의 실제 색상 값도 살짝 달라졌다**. v3에서 `bg-blue-600`은 `#2563EB`였는데, v4에서는 `oklch(0.546 0.245 262.881)`로 매핑된다. 이 둘을 sRGB로 변환해 비교하면:

| 항목 | v3 `bg-blue-600` | v4 `bg-blue-600` |
|---|---|---|
| 내부 표현 | `#2563EB` (sRGB hex) | `oklch(0.546 0.245 262.881)` |
| sRGB 근사값 | rgb(37, 99, 235) | rgb(38, 100, 240) |
| 체감 | 기존 Material blue | 약간 더 보라끼 있는 톤 |
| 눈에 띄는 차이 | - | 약간 차이 있음 |

같은 `bg-blue-600` 클래스인데 렌더되는 색이 바뀐 것. 브랜드 컬러가 Toss Blue(`#3182F6`)처럼 특정 hex에 맞춰져 있는 프로젝트라면, v4 기본 blue-600로 대체되는 게 눈에 띄게 달라 보인다. 특히 푸르스름한 느낌은 OKLCH의 H 값이 262.881로 살짝 보라 쪽으로 기울어서 생긴다.

브랜드 컬러가 필요하면 `@theme`에 명시적으로 선언해야 한다:

```css
@theme {
  --color-primary: #3182F6;
  --color-primary-dark: #1a6dd9;
  --color-primary-50: #ebf4ff;
  --color-primary-100: #d6e8ff;
  /* ... 50~900 전체 스케일 */
}
```

이렇게 선언하면 `bg-primary`, `hover:bg-primary-dark`, `bg-primary-50` 모두 자동 생성된다. 기본 팔레트의 blue 스케일은 그대로 살아있고, 브랜드 primary는 별도 키로 공존.

## 삽질 기록 — dead config가 살아있는 척할 때

문제를 진단하던 중 처음 의심한 건 빌드 캐시였다. Vite 재시작, `rm -rf public/vite/`, pnpm cache clear까지 다 시도했는데 증상이 그대로였다. 두 번째 의심은 CSS 특이도. `!important` 덮어쓰기가 있는지 보려고 DevTools Styles 패널을 열어봤는데 그냥 Tailwind utility가 깨끗하게 적용되고 있었다.

결정적 단서는 `grep`으로 찾았다:

```bash
grep -rn "primary" app/frontend/styles/application.css
# --color-primary: #3182f6;  ← @theme에 있음

grep -rn "primary" tailwind.config.js
# colors: { primary: '#3182F6', ... }  ← 여기도 있음

# 그런데 실제 렌더는 primary가 아니라 blue-600으로 동작
```

`@theme`에 primary는 있는데, **gray 스케일은 없었다**. 그리고 `.bg-gray-100`, `.border-gray-200` 같은 클래스가 프로젝트 전반에 8000건 넘게 쓰이고 있었다. v4 기본 gray 팔레트는 Tailwind 공식 스케일이라 Toss Gray(`#F2F4F6`)와 비슷하지만 동일하지 않다. 푸르스름함은 gray도 한몫한 거였다.

`tailwind.config.js`를 삭제하고 `@theme`에 전체 스케일을 포팅하자 즉시 해결됐다:

```css
@theme {
  /* Brand primary */
  --color-primary: #3182F6;
  --color-primary-light: #4d9bff;
  --color-primary-dark: #1a6dd9;

  /* Neutral Gray (Toss) */
  --color-gray-50: #f9fafb;
  --color-gray-100: #f2f4f6;
  --color-gray-200: #e5e8eb;
  --color-gray-300: #d1d6db;
  /* ... 900까지 */

  /* Radius */
  --radius-xl: 12px;
  --radius-2xl: 16px;

  /* Typography */
  --text-h1: 24px;
  --text-h1--line-height: 1.33;
  --text-h1--font-weight: 700;

  /* Font */
  --font-sans: Pretendard, -apple-system, sans-serif;
}
```

`tailwind.config.js` 자체를 삭제하니 v4에서 "설정이 하나뿐" 상태가 되면서 미스매치 가능성이 원천 차단됐다. v3 config를 남겨두면 나중에 누군가 "config가 있으니까 뭔가 하고 있겠지" 오해할 수 있는데, v4에서는 그냥 dead file이라 혼동만 유발한다.

## Chrome DevTools MCP로 픽셀 단위 검증

여기서부터는 검증 방식 이야기. Tailwind 마이그레이션이 제대로 됐는지 확인하려면 여러 페이지의 버튼 색상, padding, radius 를 픽셀 단위로 비교해야 하는데, 수십 페이지를 눈으로 일일이 비교하는 건 비효율적이다. 브라우저 자동화 툴로 computed style을 뽑아 Before/After 비교하는 게 정석.

원래 Playwright MCP를 쓰고 있었는데 Claude와 써보니 토큰 효율이 썩 좋지 않았다. 매 액션마다 페이지 전체의 accessibility snapshot을 15KB씩 실어 나르다 보니 10-step 워크플로우에 누적 100K 토큰 넘게 쓰이는 느낌이었다. 찾아보니 Chrome DevTools MCP라는 대안이 있었다.

**Playwright MCP vs Chrome DevTools MCP 체감 비교:**

| 항목 | Playwright MCP | Chrome DevTools MCP |
|---|---|---|
| Tool 정의 오버헤드 | ~13.7K tokens | ~17K tokens |
| 10-step 누적 | ~114K tokens | ~50K tokens |
| 페이지 snapshot 포함 | 매 step 전체 DOM (~15K) | 작업별 가변 |
| 브라우저 | Chromium/Firefox/WebKit | Chrome only |
| 강점 | 크로스 브라우저 | Lighthouse, performance trace, heap snapshot, 네트워크 모니터링 |
| 설치 | `npx @playwright/mcp` | `npx chrome-devtools-mcp@latest` |

로컬 개발 서버 확인, 스크린샷, 콘솔 체크가 주 용도였으므로 크로스 브라우저는 필요 없었다. DevTools급 프로파일링 기능이 덤으로 붙는 Chrome DevTools MCP로 갈아탔다. Claude Code 기준 설치 한 줄:

```bash
claude mcp add chrome-devtools -s user -- npx -y chrome-devtools-mcp@latest
```

유저 스코프에 설치해두면 모든 프로젝트에서 쓸 수 있다. 새 세션을 열면 툴 스키마가 로드된다.

## evaluate_script로 computed style 뽑기

Chrome DevTools MCP의 가장 실용적인 기능은 `evaluate_script`. 페이지에 JavaScript를 주입해서 반환값을 받을 수 있다. Before/After 비교를 위한 측정 스크립트는 이렇게 짰다:

```javascript
() => {
  const r = {};
  const btns = Array.from(document.querySelectorAll('button'));
  const find = (text) => btns.find(b => b.textContent.trim().includes(text));

  ['임시저장', '제출', '승인'].forEach(name => {
    const el = find(name);
    if (!el) { r[name] = null; return; }
    const rect = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    r[name] = {
      w: Math.round(rect.width),
      h: Math.round(rect.height),
      px: cs.paddingLeft + '/' + cs.paddingRight,
      py: cs.paddingTop + '/' + cs.paddingBottom,
      radius: cs.borderRadius,
      bg: cs.backgroundColor,
      color: cs.color,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
    };
  });
  return r;
}
```

마이그레이션 전후로 같은 스크립트를 돌리면 정확히 뭐가 바뀌었는지 JSON으로 떨어진다. 실제 결과:

**Before (v3 config 무시되던 상태):**
```json
{
  "제출": {
    "w": 70, "h": 32,
    "bg": "oklch(0.546 0.245 262.881)",
    "radius": "8px",
    "fontWeight": "500"
  }
}
```

**After (@theme에 포팅 후):**
```json
{
  "제출": {
    "w": 70, "h": 32,
    "bg": "rgb(49, 130, 246)",
    "radius": "8px",
    "fontWeight": "600"
  }
}
```

너비/높이/radius는 변화 없이 그대로. 핵심인 `bg`가 **v4 기본 OKLCH에서 Toss Blue `rgb(49, 130, 246)` = `#3182F6` 으로 정규화**된 게 확인된다. 눈으로 "뭔가 달라 보인다" 수준이 아니라 픽셀 단위 증거가 남는 게 실용적이다.

## 일괄 토큰 정규화할 때 안전한 sed 패턴

토큰은 잡았는데, raw 컬러 유틸(`bg-blue-600`, `hover:bg-blue-700`)이 `text-white`와 함께 직접 박혀있는 CTA 버튼이 프로젝트 전반에 86건 있었다. 하나씩 Find-Replace 하는 건 번거롭고, 전역 sed로 `bg-blue-600 → bg-primary` 치환하면 상태 뱃지(`bg-blue-100 text-blue-800`)같은 시맨틱 쓰임까지 오염된다. 상태 뱃지에서 blue는 "submitted" 상태를 시맨틱하게 나타내는 거라 브랜드 primary와 분리되어야 한다.

해결책은 **라인 스코프 조건 sed**:

```bash
grep -rln "text-white" app/frontend/ | \
  grep -v "\.stories\." | \
  xargs grep -l "bg-blue-600" 2>/dev/null | \
  xargs grep -l "hover:bg-blue-700" 2>/dev/null | \
  while read -r f; do
    sed -i '' '/text-white/{
      s/bg-blue-600/bg-primary/g
      s/hover:bg-blue-700/hover:bg-primary-dark/g
      s/disabled:bg-blue-400/disabled:bg-primary-400/g
    }' "$f"
  done
```

세 단계 필터:

1. **`text-white` 포함 파일만** — primary CTA 버튼은 거의 항상 흰 글자에 컬러 배경. 상태 뱃지는 보통 `text-blue-800` 같은 스케일을 쓰지 `text-white`를 안 쓴다
2. **`bg-blue-600` + `hover:bg-blue-700` 둘 다 있는 파일만** — 진짜 CTA 패턴 시그널
3. **`/text-white/{...}` sed 주소** — 파일 안에서도 `text-white`가 있는 라인만 치환 대상. 같은 파일 안에 상태 뱃지도 있으면 건너뜀

macOS sed는 `-i`에 빈 문자열 `''` 넣어줘야 한다 (GNU sed와 문법 차이). `while read -r f` 루프는 `for f in $files` 대신 쓰는 편이 안전한데, 파일명 리스트를 한 줄로 붙이는 버그를 피할 수 있다. `for` 루프 돌리다 "File name too long" 에러 봤다면 이 이유.

37개 파일이 대상이었고, 스크립트로 처리하니 수십 초 만에 끝났다. 검증 단계에서 남은 `bg-blue-600+text-white` 패턴을 다시 grep 해보니 DartMonitoring Index 한 건만 남아 있었는데, 그건 대시보드 job 상태 색상 매핑(`color: 'bg-blue-600 hover:bg-blue-700'` 문자열)이라 CTA와 무관해서 의도적으로 제외됐다. 라인 조건이 정확히 작동한 셈.

## 주의해야 할 함정

같은 작업 다시 할 사람들을 위해 몇 가지 짚어둘 것:

- **`tailwind.config.js`는 `@config` 지시어로 살려둘 수 있다** — 하지만 v4 공식 권장은 삭제. 마이그레이션 툴(`npx @tailwindcss/upgrade@next`)이 `@theme`에 자동 포팅해준다. 복잡한 플러그인만 `@config`로 남겨두는 게 맞다
- **Svelte 같은 scoped CSS는 `@reference` 필요** — `<style>` 블록 안에서 `@apply bg-primary` 쓰려면 `@reference "../path/to/main.css"` 선언해야 `@theme` 변수가 가시권에 들어온다
- **Preprocessor(Sass/Less) 쓰면 안 된다** — v4는 Lightning CSS 내부 파서를 쓰는데, PostCSS + 프리프로세서 조합이 깨질 수 있다. v4 자체의 nesting, color-mix, calc()로 대부분 대체 가능
- **Storybook 같은 별도 빌드 경로는 따로 확인** — 메인 앱은 `@theme` 잘 먹어도 Storybook 빌드 파이프라인이 다른 CSS를 물고 있을 수 있다. Storybook 스토리에 `tailwind.config.js`가 깔려있는 경우 주의
- **`hover:bg-primary-dark`가 없으면 `primary-dark` 토큰부터 선언** — 기본 팔레트에는 `primary-50/100/200/.../900` 전체 스케일이 자동 생성 안 된다. 필요한 shade는 모두 `@theme`에 넣어야 한다
- **shadow-* 유틸도 v4가 재설계** — `shadow`가 `shadow-sm`으로, `shadow-sm`이 `shadow-xs`로 리네이밍됐다. 커스텀 shadow를 넣으려면 `@theme`에 `--shadow-sm`, `--shadow-md` 등을 선언해야 v4 기본값과 분리된다

## 검증이 쉬워지니 리팩터 속도가 붙는다

Before/After를 픽셀 단위로 뽑을 수 있다는 건 생각보다 큰 차이다. "뭔가 이상하다"에서 멈추는 게 아니라 "`oklch(0.546 0.245 262.881)` 이게 왜 여기 있지?" 같은 구체적 질문이 가능해진다. 이 질문은 grep으로 소스 추적이 되고, 소스는 토큰 정의로 이어진다.

지금까지는 Playwright 쪽에 쌓인 자료가 많아 자동으로 Playwright MCP를 골랐는데, Chrome DevTools MCP 쪽이 Lighthouse 감사와 퍼포먼스 트레이스까지 덤으로 붙어있어서 디자인 검증 + 성능 점검을 한 툴에서 끝낼 수 있다. 디자인 리팩터를 실제 프로덕션 지표로 연결하려면 이쪽이 낫다고 본다.

요약:

1. Tailwind v4 썼으면 `tailwind.config.js`를 완전히 삭제하고 `@theme`만 유지한다. config가 남아있으면 조용히 무시되면서 "어디가 소스인지" 혼동이 생긴다
2. 기본 팔레트가 OKLCH로 바뀐 걸 인지하고, 브랜드 컬러는 명시적으로 `@theme`에 선언한다. 특히 gray 스케일은 레거시 hex와 느낌이 다르다
3. 검증은 `evaluate_script`로 computed style을 JSON으로 뽑으면 눈 비교를 우회할 수 있다
4. 일괄 치환은 라인 스코프 sed로 시맨틱 컬러와 브랜드 컬러를 분리한다. `text-white` + `bg-blue-600` + `hover:bg-blue-700` 세 조건 교집합이 주 CTA 패턴

이제 v3 config 하나 지우는 PR에 이유를 한 줄로 쓸 수 있다: "v4에서는 이 파일이 무시된다."
