---
title: "Chrome 확장 프로그램에서 iframe OACX 자동입력이 안 되는 문제 — 타이밍과 한글 IME"
date: 2026-01-23
draft: false
tags: ["Chrome Extension", "Manifest V3", "iframe", "OACX", "Korean IME", "디버깅", "MutationObserver"]
description: "정부 사이트 간편인증(OACX) 자동입력 확장을 만들었는데, 특정 사이트에서만 이름이 안 들어가는 버그. iframe 비동기 렌더링 타이밍과 한글 IME composition 이벤트가 원인이었다."
cover:
  image: "/images/og/chrome-extension-oacx-iframe-korean-ime-fix.png"
  alt: "Chrome Extension Oacx Iframe Korean Ime Fix"
  hidden: true
---

Chrome 확장 프로그램으로 정부 사이트 간편인증(OACX) 폼을 자동입력하는 기능을 만들었다. 대부분의 사이트에서 잘 동작하는데, 특정 대형 사이트에서 "이름 입력이 안 됩니다"라는 피드백이 들어왔다.

---

## 증상

- 간편인증 팝업이 열리면 이름, 생년월일, 휴대폰번호를 자동입력하는 확장
- 대부분의 정부 사이트(정부24, 건강보험 등)에서는 정상 동작
- **특정 사이트에서만 이름 필드가 비어있음** — 생년월일, 전화번호도 안 채워짐

---

## 조사: Playwright로 실제 DOM 구조 확인

사용자가 알려준 페이지를 Playwright MCP로 직접 열어서 확인했다.

### 1단계: 메인 페이지 스냅샷

메인 페이지에서 "간편인증" 버튼을 클릭하면 **레이어 팝업 + iframe**이 열린다.

```yaml
- heading "레이어 팝업"
  - iframe [ref=e214]   # <-- 여기에 OACX가 로드됨
```

### 2단계: iframe 내부 확인

iframe 안에서 JavaScript를 실행하여 실제 DOM을 확인:

```js
// iframe 내부에서 evaluate
const inputs = document.querySelectorAll('input, select');
```

결과:

```json
{
  "inputCount": 11,
  "hasOacxContainer": true,
  "url": "https://example.go.kr/oacx/index.jsp",
  "inputs": [
    { "id": "oacx_name",  "dataId": "oacx_name",  "type": "text",     "placeholder": "홍길동" },
    { "id": "oacx_birth", "dataId": "oacx_birth", "type": "text",     "placeholder": "19900101" },
    { "id": "oacx_phone2","dataId": "oacx_phone2","type": "text",     "placeholder": "12341234" },
    { "dataId": "oacx_phone0", "type": "select-one", "title": "통신사 선택" },
    { "dataId": "oacx_phone1", "type": "select-one", "title": "휴대폰번호 앞자리 선택" },
    { "id": "totalAgree", "type": "checkbox" }
  ]
}
```

**OACX 표준 구조(`data-id="oacx_name"` 등)를 그대로 쓰고 있었다.** 그런데 왜 안 되는 걸까?

---

## 원인 1: iframe 비동기 렌더링 타이밍

### 문제 구조

이 사이트는 OACX를 **같은 도메인의 iframe**에 로드한다:

```
부모 페이지 (*.go.kr)
  └─ iframe (src="about:blank" → JS로 oacx/index.jsp 네비게이션)
       └─ #oacxEmbededContents  ← 컨테이너
            └─ input[data-id="oacx_name"]  ← 폼 필드 (비동기 생성)
```

content script는 `all_frames: true`로 iframe 안에서도 실행된다. 문제는 **실행 순서**:

1. iframe이 `oacx/index.jsp`로 네비게이션
2. content script가 `document_idle`에 실행됨
3. `detectOACX()` → `#oacxEmbededContents` 발견 → `autoFill()` 즉시 호출
4. **하지만 `input[data-id="oacx_name"]`은 아직 렌더링 안 됨** (OACX JS가 비동기로 생성)
5. `document.querySelector('input[data-id="oacx_name"]')` → **null 반환**
6. `setInputValue(null, name)` → 아무 일도 안 함 (silent fail)
7. `filled = true` 설정됨 → **재시도 없음**

### 기존 코드의 문제

```js
async function autoFill() {
    // ... 인증 체크 ...
    filled = true;  // 여기서 바로 true 설정

    // 이름 필드가 아직 없으면 null → 조용히 실패
    setInputValue(
      document.querySelector('input[data-id="oacx_name"]'),
      info.name
    );
}
```

`filled = true`가 설정되면 MutationObserver가 다시 `autoFill()`을 호출하지 않는다.

### 수정: waitForEl — 필드가 나타날 때까지 대기

```js
// MutationObserver 기반 요소 대기
function waitForEl(selector, timeout = 3000) {
    return new Promise(resolve => {
        const el = document.querySelector(selector);
        if (el) return resolve(el);

        const t = setTimeout(() => {
            obs.disconnect();
            resolve(null);
        }, timeout);

        const obs = new MutationObserver(() => {
            const found = document.querySelector(selector);
            if (found) {
                clearTimeout(t);
                obs.disconnect();
                resolve(found);
            }
        });

        obs.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true
        });
    });
}
```

`autoFill()`에서 사용:

```js
filled = true;

// input 필드가 비동기 렌더링될 때까지 최대 3초 대기
const nameEl = await waitForEl('input[data-id="oacx_name"]', 3000);
if (!nameEl) {
    filled = false;  // 리셋 → MutationObserver가 재시도 가능
    return;
}

// 이후 정상 자동입력 진행
setInputValue(nameEl, info.name);
```

---

## 원인 2: 한글 이름과 IME Composition 이벤트

### 문제

기존 `setInputValue`는 이런 이벤트만 발생시켰다:

```js
function setInputValue(el, value) {
    nativeSetter.call(el, value);      // React 호환 값 설정
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
}
```

이름 필드(`홍길동`)는 **한글**이다. 한글은 브라우저에서 IME(Input Method Editor)를 통해 입력되는데, 이 과정에서 `compositionstart` → `compositionupdate` → `compositionend` 이벤트가 발생한다.

일부 웹 프레임워크는 **composition 이벤트가 없으면 한글 입력을 인식하지 않는다.** 생년월일(숫자)이나 전화번호(숫자)는 IME를 거치지 않으므로 이 문제가 없다.

### 수정: 한글 감지 시 composition 이벤트 추가

```js
function setInputValue(el, value) {
    if (!el) return;
    el.dispatchEvent(new Event('focus', { bubbles: true }));

    const nativeSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype, 'value'
    )?.set;
    if (nativeSetter) nativeSetter.call(el, value);
    else el.value = value;

    // 한글이 포함된 경우 IME composition 이벤트 발생
    if (/[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(value)) {
        el.dispatchEvent(new CompositionEvent('compositionstart', {
            bubbles: true
        }));
        el.dispatchEvent(new CompositionEvent('compositionend', {
            bubbles: true,
            data: value
        }));
    }

    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
}
```

한글 정규식 `/[ㄱ-ㅎㅏ-ㅣ가-힣]/`로 값에 한글이 포함되어 있는지 확인하고, 포함된 경우에만 composition 이벤트를 추가한다.

---

## 디버깅 과정에서 배운 것

### 1. Playwright MCP로 정부 사이트 DOM 분석

정부 사이트는 대부분 WebSquare 같은 SPA 프레임워크를 쓰고, 정적 스크랩으로는 빈 페이지만 나온다. Playwright를 사용하면:

```
navigate → wait → snapshot → click → snapshot → evaluate
```

이 흐름으로 실제 사용자 플로우를 재현하면서 DOM을 확인할 수 있다. 특히 `evaluate`로 iframe 내부의 JavaScript를 직접 실행할 수 있어서 정확한 속성값을 확인할 수 있었다.

### 2. iframe src="about:blank"의 함정

이 사이트는 iframe을 `src="about:blank"`으로 생성하고, JavaScript로 실제 URL을 네비게이션한다. 이 경우:

- Chrome은 네비게이션을 감지하고 content script를 주입함 (`all_frames: true` 필요)
- 하지만 iframe 내부 콘텐츠의 **렌더링 타이밍**이 부모 페이지와 다름
- `document_idle`에 실행되더라도 비동기로 생성되는 요소는 없을 수 있음

### 3. silent fail의 위험

```js
function setInputValue(el, value) {
    if (!el) return;  // el이 null이면 그냥 넘어감
    // ...
}
```

이 패턴은 방어적 코딩이지만, 디버깅을 어렵게 만든다. 요소를 못 찾았는데 에러도 없이 넘어가면 "왜 안 되는지" 찾기가 어렵다. 중요한 필드에 대해서는 **대기 → 재시도 → 실패 시 리셋** 패턴이 더 적합하다.

### 4. 한글 입력은 영문/숫자와 다르다

브라우저에서 한글을 입력하면 내부적으로:

```
keydown → compositionstart → compositionupdate(ㅎ) → compositionupdate(호)
→ compositionupdate(홍) → compositionend(홍) → input → keyup
```

프로그래밍으로 `el.value = '홍길동'`을 설정하면 이 과정이 전혀 발생하지 않는다. 프레임워크가 composition 이벤트에 의존하는 경우 값이 설정되었더라도 "입력됨"으로 인식하지 않을 수 있다.

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| 이름/생년월일/전화번호 전부 미입력 | OACX 컨테이너 감지 → 즉시 실행 → input 필드 아직 없음 | `waitForEl()`로 input 출현까지 대기 (3초 timeout) |
| 이름 필드만 프레임워크가 인식 못함 | 한글 IME composition 이벤트 누락 | 한글 감지 시 `compositionstart`/`compositionend` 추가 |
| 실패해도 재시도 안 됨 | `filled = true` 후 silent fail | 필드 미발견 시 `filled = false`로 리셋 |

iframe 안의 비동기 렌더링과 한글 IME — 둘 다 한국 웹 환경에서 흔히 마주치는 문제인데, 겹치니까 찾기 어려웠다.
