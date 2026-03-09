---
title: "Chrome 확장 개발 삽질 모음 — 도메인 화이트리스트, 이벤트 리스너 중복, 클로저 함정"
date: 2026-03-09
draft: false
tags: ["Chrome Extension", "Firefox Extension", "Manifest V3", "JavaScript", "디버깅"]
description: "Chrome/Firefox 확장 프로그램을 개발하면서 겪은 4가지 실수 — 도메인 감지 흐름 차단, 이벤트 리스너 중복 등록, 클로저 참조 누락, AMO 패키징 오류."
cover:
  image: ""
  alt: ""
  hidden: true
---

Chrome 확장을 유지보수하다 보면 "분명히 동작해야 하는데 왜 안 되지?"라는 상황을 꽤 자주 만난다. 이번에 짧은 시간 안에 4가지 실수를 연달아 저질렀고, 각각 원인이 달랐다. 기록해둔다.

---

## 1. 디스패치 블록의 `return`이 범용 감지를 막는다

Content script 끝부분에는 보통 이런 패턴이 있다.

```js
if (isSomeSpecificPage()) {
  doSomethingSpecific();
  return; // ← 여기서 끝
}

// 범용 DOM 감지 (MutationObserver 등)
const observer = new MutationObserver(() => { ... });
observer.observe(document.body, { childList: true, subtree: true });
```

특정 도메인에서만 동작하는 기능을 추가하면서 `return`으로 빠져나왔더니, 그 도메인의 팝업 창에서 범용 DOM 감지가 아예 실행되지 않았다.

문제가 된 흐름:
1. A 도메인에서 버튼 클릭 → B 도메인 팝업 오픈
2. B 도메인도 `isSomeSpecificPage()` 조건에 걸림 (`hostname.endsWith(...)` 방식이었음)
3. 팝업에서는 특정 기능이 필요 없고 범용 감지만 있으면 됐는데, `return`이 막아버림

**해결**: 특정 기능이 해당 팝업에서 실제로 필요 없다면 디스패치 블록 자체를 제거하거나, 조건을 더 좁게(`hostname === 'exact.domain.com'`) 잡아야 한다.

---

## 2. `<all_urls>` vs 구체적 도메인 나열 — Chrome Web Store 심사 관점

처음에는 `host_permissions`에 `<all_urls>`를 쓰면 편하다고 생각했다. 그런데 Chrome Web Store는 광범위한 권한에 대해 **별도 정당화(justification)** 를 요구하고, 심사가 길어지거나 반려될 수 있다.

반면 구체적인 도메인을 나열하면:
- 심사자가 각 도메인의 용도를 명확히 파악할 수 있다
- 불필요한 권한 없이 **최소 권한 원칙**을 만족한다
- 재심사 시 변경 의도가 분명하다

실무 팁: `manifest.json`의 `host_permissions`와 `content_scripts.matches`는 항상 **동일하게** 유지해야 한다. 한쪽만 바꾸면 권한은 있지만 스크립트가 주입 안 되거나, 반대로 스크립트는 주입되지만 API 호출이 막힌다.

새 도메인을 추가할 때 Chrome Web Store 심사 메모(Notes to reviewer)에 이유를 영문으로 적어두면 통과율이 높아진다.

```
Added *.example.go.kr to support [service name] which uses
[feature]. The extension only activates when specific DOM
elements are detected, and no data is sent to external servers.
```

---

## 3. 이벤트 리스너 중복 등록 — 뷰를 열 때마다 `addEventListener`

팝업 UI에서 편집 뷰를 열고 닫을 때마다 초기화 함수를 호출하는 패턴이 있었다.

```js
document.getElementById('btn-edit').addEventListener('click', () => {
  // 값 채우기...

  initTabBar('edit-tab-bar', 'edit');       // ← 매번 호출
  initCondSelect('edit-cp-sel', 'edit-cp'); // ← 매번 호출
  initSecToggles();                          // ← 매번 호출
});
```

`initCondSelect`는 내부에서 `select`에 `change` 리스너를 붙인다. 편집 뷰를 두 번 열면 리스너가 두 개 붙고, 세 번 열면 세 개가 붙는다. `select` 값이 바뀔 때 패널 show/hide가 N번 반복되어 결국 예상치 못한 상태가 된다.

**해결**: 이벤트 리스너 등록은 `DOMContentLoaded` 시점에 **한 번만** 한다. 값 채우기(`el.value = ...`)와 리스너 등록(`addEventListener`)을 분리하는 것이 핵심이다.

```js
// 한 번만 실행
initCondSelect('edit-cp-sel', 'edit-cp');

// btn-edit 클릭마다 실행 (값만 채우기)
document.getElementById('btn-edit').addEventListener('click', () => {
  cpSel.value = info.coupangLoginType || '';
  cpSel.dispatchEvent(new Event('change')); // 기존 리스너 재활용
});
```

`dispatchEvent(new Event('change'))`로 기존 리스너를 트리거하면 show/hide 로직을 중복 구현할 필요가 없다.

---

## 4. 클로저 안의 `data` 참조 — 저장 후 편집이 안 되는 이유

`DOMContentLoaded`에서 `data`를 불러와 여러 함수에 넘기는 구조였다.

```js
document.addEventListener('DOMContentLoaded', async () => {
  const data = await chrome.storage.local.get([...]);
  // data.userInfo === undefined (신규 사용자)

  initSignup(); // data 안 넘김
  initMain(data);
});
```

`initSignup` 안에서 저장을 완료해도, `initMain`에 넘어간 `data` 객체의 `userInfo`는 여전히 `undefined`다. 그래서 저장 직후 편집 버튼을 누르면 `if (!info) return`으로 조기 탈출한다.

**해결**: `data` 객체를 `initSignup`에도 넘기고, 저장 후 `data.userInfo`를 직접 업데이트한다.

```js
initSignup(data); // data 참조 전달

// initSignup 내부
async function save() {
  await chrome.storage.local.set({ userInfo });
  data.userInfo = userInfo; // 같은 객체를 업데이트 → initMain 클로저에서도 반영됨
}
```

JavaScript 객체는 참조로 전달되므로, 같은 `data` 객체의 프로퍼티를 업데이트하면 다른 함수의 클로저에서도 바로 반영된다.

---

## 5. Firefox AMO 패키징 — zip 구조 오류

Firefox Add-ons에 업로드할 때 이런 오류가 났다.

```
manifest.json was not found at the root of the extension.
The package file must be a ZIP of the extension's files themselves,
not of the containing directory.
```

원인은 간단했다. 상위 디렉토리에서 폴더째로 압축했기 때문이다.

```bash
# ❌ 틀린 방식 — firefox_extension/manifest.json 이 된다
zip -r output.zip firefox_extension/

# ✅ 맞는 방식 — manifest.json 이 루트에 위치한다
cd firefox_extension && zip -r ../output.zip .
```

Chrome Web Store도 동일하다. 언제나 **확장 폴더 안으로 들어가서** 압축해야 한다.

---

## 6. Firefox AMO innerHTML 경고

AMO 린터가 이런 경고를 냈다.

```
Unsafe assignment to innerHTML
firefox_extension/content.js 줄 401
```

해당 코드는 이렇게 생겼다.

```js
function showHint(messageHtml) {
  el.querySelector('#msg').innerHTML = messageHtml; // ← 경고
}

showHint('안내 메시지입니다.<br><b>굵은 텍스트</b>도 있어요.');
```

`messageHtml`은 코드 내 정적 문자열만 받지만, 린터는 변수명만 보고 동적 값일 수 있다고 판단한다.

**해결**: `<br>`과 `<b>` 태그만 허용하는 간단한 DOM 헬퍼를 만들었다.

```js
function renderSafeHtml(container, html) {
  container.textContent = '';
  html.split(/(<br\s*\/?>|<b>[^<]*<\/b>)/g).forEach(part => {
    if (/^<br/i.test(part)) {
      container.appendChild(document.createElement('br'));
    } else if (/^<b>/i.test(part)) {
      const b = document.createElement('b');
      b.textContent = part.replace(/<\/?b>/gi, '');
      container.appendChild(b);
    } else if (part) {
      container.appendChild(document.createTextNode(part));
    }
  });
}
```

정적 문자열이라도 AMO 심사를 통과하려면 DOM 조작 방식을 써야 한다.

---

## 정리

| 실수 | 원인 | 해결 |
|---|---|---|
| 팝업에서 범용 감지 안 됨 | 디스패치 블록 `return`이 흐름 차단 | 조건 좁히거나 블록 제거 |
| CWS 심사 지연 | `<all_urls>` 광범위 권한 | 구체적 도메인 나열 |
| 저장 버튼 동작 불안정 | 이벤트 리스너 중복 등록 | init은 한 번, 값 채우기만 반복 |
| 저장 후 편집 안 됨 | 클로저에 `data` 참조 누락 | `data` 객체 전달 후 직접 업데이트 |
| AMO 패키징 오류 | 폴더째 zip | 폴더 안에서 zip |
| AMO innerHTML 경고 | 변수에 HTML 문자열 할당 | DOM 헬퍼로 대체 |

삽질의 공통점은 "당연히 될 것 같았다"는 가정에서 시작한다는 거다. 확장 프로그램 개발에서는 도메인 매칭, 스크립트 주입 타이밍, 이벤트 등록 시점이 생각보다 훨씬 까다롭다.
