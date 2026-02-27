---
title: "크롬 확장 content script — 한국 보험사 자동입력, HTML 목업 스크린샷, MOV→GIF"
date: 2026-02-27
draft: false
tags: ["Chrome Extension", "Browser Extension", "Playwright", "ffmpeg", "JavaScript", "content script"]
description: "다이렉트 자동차보험 10개사 JS 렌더링 대응 자동입력, React/Vue Native Setter trick, HTML+Playwright 스토어 스크린샷, ffmpeg 2-pass GIF 변환까지 하루 삽질 기록"
---

브라우저 확장 프로그램에서 form 자동입력 기능을 확장하면서 삽질한 내용들을 정리한다.

---

## 1. 다이렉트 자동차보험 사이트 content script 자동입력

### 문제: JS 렌더링 사이트는 WebFetch로 form 구조를 못 읽는다

한국 보험사 다이렉트 사이트들은 대부분 SPA/RIA 구조다.

- 삼성화재: SFMI 자체 RIA 프레임워크
- 현대해상, DB손보: Spring MVC `.do` URL 패턴
- KB손보, 메리츠: 모바일/PC 별도 도메인

`WebFetch`로 URL을 긁어봤자 form 필드 구조가 나오지 않는다. 직접 접속해서 DevTools로 확인하거나, 업계 공통 패턴으로 커버하는 방법 중 **후자**를 선택했다.

### 업계 공통 필드명 패턴

여러 보험사 HTML을 분석하면 필드 ID/name이 꽤 규칙적이다:

```javascript
// 이름
const NAME_SELECTORS = [
  'input[id*="custNm" i]',     // 고객명
  'input[id*="insCustNm" i]',  // 피보험자명
  'input[id*="contrNm" i]',    // 계약자명
  'input[id*="appcntNm" i]',   // 신청인명
  'input[placeholder*="이름"]',
];

// 주민번호 앞자리 (생년월일 6자리)
const BIRTH_SELECTORS = [
  'input[id*="rrnFront" i]',
  'input[id*="jumin1" i]',
  'input[id*="resno1" i]',
  'input[placeholder*="앞 6자리"]',
];

// 연락처
const PHONE_SELECTORS = [
  'input[id*="mobileNo" i]',
  'input[id*="hpNo" i]',
  'select[id*="mobileNo1" i]',  // 분할 입력 prefix
];
```

### 보안 키패드 건너뛰기

주민번호 뒷자리는 보안 키패드라 자동입력 불가다. 감지 로직:

```javascript
function isEncryptedInput(el) {
  if (!el) return true;
  if (el.readOnly || el.disabled) return true;
  const cls = (el.className || '').toLowerCase();
  if (/keypad|encrypt|security|virtual|seckey/.test(cls)) return true;
  if (el.dataset.encrypt === 'Y' || el.dataset.security === 'true') return true;
  return false;
}
```

### React/Vue에서 input.value = x 가 안 먹히는 이유

React와 Vue는 synthetic event system 때문에 `el.value = x`만으로는 상태 변경을 감지하지 못한다. **Native Setter**를 통해야 한다:

```javascript
function setInputValue(el, val) {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
  )?.set;
  if (nativeSetter) nativeSetter.call(el, val);
  else el.value = val;

  ['input', 'change', 'keyup'].forEach(ev =>
    el.dispatchEvent(new Event(ev, { bubbles: true }))
  );
}
```

`HTMLInputElement.prototype`의 `value` setter를 직접 호출한 뒤 `input`/`change` 이벤트를 dispatch하면 React/Vue도 상태를 갱신한다.

### 전화번호 분할 입력 처리

보험사 사이트는 `010 | 1234 | 5678` 세 칸 분리 또는 `01012345678` 통합 입력 둘 다 있다:

```javascript
const splitPrefix = document.querySelector('select[id*="mobileNo1" i]');

if (splitPrefix) {
  setInputValue(splitPrefix, '010');
  setInputValue(mid4El, phone.slice(0, 4));
  setInputValue(last4El, phone.slice(4));
} else {
  setInputValue(unifiedEl, fullPhone);
}
```

### MutationObserver로 SPA 폼 렌더링 대응

폼이 클릭 후 비동기로 렌더링되는 경우를 위해 `MutationObserver`를 사용한다:

```javascript
let filled = false;

const obs = new MutationObserver(() => {
  if (!filled) tryFillForm();
});

obs.observe(document.body, {
  childList: true, subtree: true,
  attributes: true,
  attributeFilter: ['style', 'class', 'disabled', 'readonly'],
});

setTimeout(() => obs.disconnect(), 120_000); // 2분 후 해제
```

### manifest.json 도메인 추가 패턴

새 보험사 도메인 추가 시 `host_permissions`와 `content_scripts.matches` **두 군데** 모두 추가해야 한다:

```json
"host_permissions": [
  "https://*.samsungfire.com/*",
  "https://*.directanycar.co.kr/*",
  "https://*.hanwhadirect.com/*"
],
"content_scripts": [{
  "matches": [
    "https://*.samsungfire.com/*",
    "https://*.directanycar.co.kr/*",
    "https://*.hanwhadirect.com/*"
  ],
  "js": ["content.js"]
}]
```

같은 보험사인데 도메인이 두 개인 경우도 있다 (예: 삼성화재 일반 다이렉트 vs 애니카 다이렉트). 스토어 페이지나 광고 링크를 직접 확인해봐야 알 수 있다.

---

## 2. SVG 아이콘 → PNG 재생성 (rsvg-convert)

툴바 아이콘을 SVG로 교체하고 rsvg-convert로 PNG를 뽑았다:

```bash
brew install librsvg   # 없으면 설치

rsvg-convert -w 16  -h 16  icon.svg -o icon16.png
rsvg-convert -w 48  -h 48  icon.svg -o icon48.png
rsvg-convert -w 128 -h 128 icon.svg -o icon128.png
```

Chrome용 아이콘을 Firefox에도 동기화:

```bash
cp icons/icon*.png ../firefox_extension/icons/
```

---

## 3. 크롬 웹스토어 스크린샷 — HTML 목업 + Playwright

### 웹스토어 스크린샷 요건
- 1280×800 또는 640×400
- JPEG 또는 **24비트 PNG (알파 없음)**
- 최대 5개

실제 화면 캡처는 개인정보 노출 위험이 있어서 **HTML로 목업**을 만들고 Playwright로 픽셀 단위 캡처하는 방식을 선택했다.

### HTML 목업 핵심: 뷰포트 고정

```html
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1280px;
    height: 800px;
    overflow: hidden;   /* 이게 핵심 */
  }
</style>
```

`overflow: hidden`을 걸어두면 Playwright 캡처 시 정확히 1280×800으로 잘린다.

### Playwright 캡처 스크립트

```javascript
// capture.js
const { chromium } = require('playwright');
const path = require('path');

const files = [
  '01_hero.html', '02_autofill.html', '03_setup.html',
  '04_insurance.html', '05_security.html',
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  for (const f of files) {
    await page.goto(`file://${path.join(__dirname, f)}`);
    await page.waitForTimeout(600);   // 폰트/이미지 로드 대기
    await page.screenshot({
      path: f.replace('.html', '.png'),
      fullPage: false,   // 뷰포트 크기만 캡처
    });
    console.log(`✓ ${f}`);
  }

  await browser.close();
})();
```

```bash
node capture.js
# ✓ 01_hero.html
# ✓ 02_autofill.html
# ...
```

`fullPage: false`가 중요하다. `true`로 하면 HTML 내용 전체 높이로 캡처돼서 1280×800 고정이 깨진다.

---

## 4. MOV → GIF 변환 (ffmpeg 2-pass)

화면 녹화 `.mov`를 GIF로 만들 때 품질을 높이려면 **팔레트 생성 → GIF 변환** 2단계를 거쳐야 한다.

### 기본 2-pass 명령

```bash
# 1단계: 팔레트 생성
ffmpeg -ss 0 -t 15 -i input.mov \
  -vf "fps=12,scale=716:-1,palettegen=stats_mode=diff" \
  palette.png

# 2단계: GIF 생성
ffmpeg -ss 0 -t 15 -i input.mov -i palette.png \
  -lavfi "fps=12,scale=716:-1 [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  output.gif
```

`stats_mode=diff`는 장면 변화가 많을 때 팔레트를 더 잘 최적화한다.
`dither=bayer:bayer_scale=5:diff_mode=rectangle`는 파일 크기 대비 품질이 가장 좋은 조합이다.

### 속도 조절: setpts

| 목적 | 필터 | 설명 |
|------|------|------|
| 슬로우 (0.75x) | `setpts=1.35*PTS` | PTS 값 늘리기 = 느리게 |
| 빠르게 (1.5x) | `setpts=0.655*PTS` | PTS 값 줄이기 = 빠르게 |
| 전체를 15초로 압축 | `setpts=(15/원본초)*PTS` | 원본 길이에서 계산 |

원본이 22.9초일 때 15초로 압축:

```bash
PTS=$(echo "scale=3; 15/22.9" | bc)   # → 0.655
ffmpeg ... -vf "setpts=${PTS}*PTS,fps=15,scale=716:-1" ...
```

### 5개 시안 패턴

| 시안 | ss | t | 필터 |
|------|----|---|------|
| 풀샷 원속 | 0 | 15 | `fps=12,scale=716:-1` |
| 풀샷 슬로우 (0.75x) | 0 | 11 | `setpts=1.35*PTS,fps=10,scale=716:-1` |
| 핵심 크롭 | 0 | 15 | `crop=850:680:291:231,fps=12,scale=716:-1` |
| 전체 빠르게 | 0 | 원본길이 | `setpts=0.655*PTS,fps=15,scale=716:-1` |
| 임팩트 루프 | 6 | 7 | `fps=15,scale=640:-1` |

`-ss` 옵션은 `-i` **앞에** 놓는 것이 훨씬 빠르다 (입력 demuxing 전에 seek).

---

## 오늘의 교훈

1. **한국 보험사 SPA 사이트는 WebFetch로 form을 읽을 수 없다** — 업계 공통 필드명 패턴으로 커버하는 게 낫다.

2. **React/Vue input 자동입력은 Native Setter + Event dispatch** — `el.value = x`만으론 상태가 변경되지 않는다.

3. **같은 회사인데 도메인이 두 개인 경우가 있다** — manifest에 하나만 넣으면 다른 채널 사이트에서 동작하지 않는다.

4. **스토어 스크린샷은 HTML 목업이 최선** — 실제 앱보다 깔끔하고 개인정보 노출도 없다. `overflow: hidden` + `fullPage: false`로 픽셀 정확하게 캡처.

5. **GIF는 2-pass 팔레트 방식** — 파일 크기 대비 품질이 훨씬 낫다. `dither=bayer:bayer_scale=5:diff_mode=rectangle` 추천.
