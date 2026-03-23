---
title: "Firefox 확장 프로그램 AMO 제출 시 data_collection_permissions 오류 해결"
date: 2025-09-17
draft: true
tags: ["Firefox", "Browser Extension", "AMO", "Manifest V3", "Chrome Extension"]
description: "Firefox Add-ons(AMO)에 확장 프로그램을 제출할 때 data_collection_permissions 필수 오류와 manifest.json 설정 방법 정리"
cover:
  image: "/images/og/firefox-addon-manifest-data-collection-permissions.png"
  alt: "Firefox Addon Manifest Data Collection Permissions"
  hidden: true
---

Chrome 확장 프로그램을 Firefox로 포팅해서 [AMO(addons.mozilla.org)](https://addons.mozilla.org)에 제출하면, Chrome Web Store에서는 없던 오류들을 만난다. 특히 2025년 11월부터 필수가 된 `data_collection_permissions` 때문에 삽질하기 쉽다. 이 글은 그 삽질 과정과 최종 해결책, 그리고 Chrome → Firefox 포팅 시 주의해야 할 manifest.json 차이점을 정리한 것이다.

---

## 배경: Chrome 확장 프로그램을 Firefox로 포팅하게 된 이유

Chrome Web Store에 이미 배포된 확장 프로그램을 Firefox 사용자들도 쓸 수 있게 하려면 AMO에 별도로 제출해야 한다. 겉으로 보기엔 간단해 보이지만, 두 브라우저의 확장 프로그램 API와 manifest 스펙이 세부적으로 다르다. Chrome에서 멀쩡하게 동작하던 코드가 Firefox에서 오류를 내거나, AMO 검사기가 Chrome 전용 필드를 오류로 처리한다.

특히 Manifest V3(MV3)로 작성된 확장 프로그램을 Firefox로 포팅할 때는 몇 가지 필수 변경사항이 있다. 그리고 2025년 11월부터는 `data_collection_permissions` 필드가 추가로 필수가 되면서, 기존에 잘 통과되던 확장 프로그램도 재제출 시 오류를 만날 수 있게 됐다.

---

## 증상 1: QR 이미지가 안 보인다?

확장 프로그램 팝업에서 이미지가 깨져 보이는 문제가 있었다. 처음에는 Content Security Policy(CSP) 문제인가 싶었지만, 원인은 훨씬 단순했다 — **패키징된 zip에 이미지 파일이 누락**된 것이었다. 로컬 개발 환경에서는 파일이 있지만, 스토어에 업로드한 빌드에는 빠져있었다.

### 원인 분석

macOS 환경에서 단순히 `zip -r extension.zip .` 명령을 쓰면 다음과 같은 불필요한 파일들이 포함된다:

- `__MACOSX/` 폴더: macOS의 리소스 포크(resource fork) 데이터
- `.DS_Store`: 디렉터리 메타데이터
- `._` 접두사 파일: 확장 속성(extended attributes)

이 파일들은 확장 프로그램 동작에 영향을 주지 않지만, zip 구조를 복잡하게 만들고 AMO 검사에서 의도치 않은 경고를 유발할 수 있다. 반대로 `store_assets/` 같이 마켓플레이스 업로드용으로 따로 관리하는 스크린샷, 배너 이미지 폴더가 실수로 포함되기도 한다.

### 해결: 깔끔한 zip 패키징

```bash
cd my_extension && zip -r ../extension.zip . \
  -x ".*" "__MACOSX/*" "*.DS_Store" "store_assets/*"
```

패키징 후 반드시 확인:

```bash
unzip -l extension.zip | grep "이미지파일"
```

`unzip -l`로 zip 내부 파일 목록을 출력해서 필요한 이미지 파일이 실제로 들어있는지, 불필요한 파일이 포함되지 않았는지 눈으로 확인하는 습관을 들여야 한다. 배포 전 체크리스트에 이 단계를 넣어두는 것을 강력히 권장한다.

---

## Chrome → Firefox 포팅 시 manifest.json 차이점

### 1. background 설정: service_worker vs scripts

이것이 가장 많이 마주치는 차이점이다. Chrome MV3는 background script를 Service Worker로 실행하지만, Firefox MV3는 아직 완전한 Service Worker를 지원하지 않고 `scripts` 배열 방식을 사용한다.

```json
// 잘못된 방식 — Chrome 전용 (Firefox에서 오류)
"background": {
  "service_worker": "background.js"
}

// 올바른 방식 — Firefox
"background": {
  "scripts": ["background.js"]
}

// 절대 하면 안 되는 방식 — 둘 다 포함 (오류 원인)
"background": {
  "service_worker": "background.js",
  "scripts": ["background.js"]
}
```

Chrome과 Firefox 양쪽을 모두 지원해야 한다면, 빌드 스크립트에서 브라우저 타깃에 따라 manifest.json을 다르게 생성하는 방식이 일반적이다. 단일 manifest로 두 브라우저를 동시에 지원하는 것은 불가능하다.

실질적인 동작 차이도 있다. Chrome의 Service Worker는 이벤트가 없으면 비활성화(idle)되어 메모리를 절약하지만, Firefox의 background script는 브라우저가 실행 중인 동안 계속 살아있다. 이 차이가 메모리 사용량이나 상태 관리 방식에 영향을 줄 수 있으므로 포팅 시 염두에 두어야 한다.

### 2. browser_specific_settings 필수

Firefox는 확장 프로그램을 식별하고 업데이트를 관리하기 위해 `gecko` 설정을 요구한다. Chrome에는 없는 필드다.

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0"
  }
}
```

`id` 필드는 이메일 형식이거나 `{uuid}` 형식이어야 한다. `strict_min_version`은 확장 프로그램이 지원하는 최소 Firefox 버전을 지정한다. MV3 지원은 Firefox 109부터 시작되었고, 128은 2024년 중반 LTS 기준이다. 사용하는 API에 따라 최솟값을 조정하면 된다.

`id`를 지정하지 않으면 AMO가 자동으로 UUID를 할당하지만, 자동 업데이트나 다른 확장 프로그램과의 통신이 필요한 경우 고정된 ID를 직접 지정하는 것이 좋다.

### 3. windows 권한 미지원

Firefox에서 `"permissions": ["windows"]`는 유효하지 않은 권한으로 처리되며 경고가 발생한다.

```json
// 잘못된 방식 — Firefox에서 경고 발생
"permissions": ["storage", "activeTab", "windows", "tabs"]

// 올바른 방식 — windows 제거
"permissions": ["storage", "activeTab", "tabs"]
```

Firefox에서 창 관련 기능이 필요하다면 `browser.windows` API를 사용할 수 있지만, 해당 권한을 명시적으로 요청할 필요가 없다. `tabs` 권한만으로 창 정보에 접근할 수 있는 경우가 많다.

### 4. API 네임스페이스 차이

Chrome은 `chrome.*` 네임스페이스를, Firefox는 `browser.*` 네임스페이스를 권장한다. Firefox도 `chrome.*`을 지원하지만, Promise 기반 API는 `browser.*`에서만 제대로 동작한다. 크로스브라우저 확장 프로그램을 개발할 때는 `webextension-polyfill` 라이브러리를 사용해 통일된 Promise 기반 API를 쓰는 것이 좋다.

---

## data_collection_permissions 삽질 기록

2025년 11월부터 **모든 새 Firefox 확장 프로그램**은 `data_collection_permissions`을 manifest.json에 명시해야 한다. Mozilla가 사용자 프라이버시 투명성을 강화하면서 도입한 정책이다. 이 필드를 빠뜨리면 AMO 자동 검사에서 오류로 처리되어 제출이 차단된다.

오류 메시지만 보면 어떤 값을 넣어야 하는지 바로 알기 어렵다. 공식 문서를 꼼꼼히 읽지 않으면 직관과 다른 시행착오를 겪게 된다.

### 시도 1: `is_exempt` 사용

"데이터를 수집하지 않으면 exempt(면제)라는 필드가 있겠지"라고 생각하고 시도했다.

```json
"data_collection_permissions": {
  "is_exempt": true,
  "description": "데이터를 수집하지 않습니다."
}
```

> 오류: `must have required property 'required'`

`is_exempt`라는 속성은 스펙에 존재하지 않는다. AMO 검사기가 `required` 속성이 없다고 오류를 낸다.

### 시도 2: `required: false`

"데이터 수집이 필요하지 않으니 false겠지"라고 생각했다.

```json
"data_collection_permissions": {
  "required": false
}
```

> 오류: `"required" must be array`

`required`는 boolean이 아니라 배열(array) 타입이다.

### 시도 3: 빈 배열 `required: []`

"수집하는 데이터가 없으니 빈 배열이면 되지 않을까?"

```json
"data_collection_permissions": {
  "required": []
}
```

> 오류: 검사 통과 실패

JSON 스펙상으로는 배열이 맞지만, AMO 검사기는 빈 배열을 허용하지 않는다. 배열 안에 최소 하나의 유효한 값이 필요하다.

### 시도 4: `required: ["none"]` — 정답

```json
"data_collection_permissions": {
  "required": ["none"]
}
```

**이게 정답이다.** 데이터를 수집하지 않는 확장 프로그램은 `"none"`을 배열에 명시해야 한다. "데이터 수집 없음"을 명시적으로 선언하는 방식이다.

### data_collection_permissions의 다른 유효 값

데이터를 수집하는 확장 프로그램이라면 수집하는 데이터 종류를 명시해야 한다. Mozilla 공식 문서 기준으로 허용되는 값들은 다음과 같다:

- `"none"`: 데이터 수집 없음
- `"location"`: 위치 정보
- `"health"`: 건강 관련 데이터
- `"financial"`: 금융 정보
- `"credentials"`: 인증 정보 (비밀번호 등)
- `"usage_data"`: 사용 통계

여러 종류를 수집한다면 배열에 모두 포함하면 된다:

```json
"data_collection_permissions": {
  "required": ["usage_data"],
  "optional": ["location"]
}
```

`required`는 확장 프로그램 기능에 필수적으로 수집하는 데이터, `optional`은 사용자 동의 후 수집하는 데이터다.

---

## data_collection_permissions 위치: gecko 내부 vs 최상위

한 가지 더 헷갈리는 부분이 있다. `data_collection_permissions`를 `browser_specific_settings.gecko` 안에 넣어야 하는지, manifest.json 최상위에 넣어야 하는지다.

현재 Mozilla 스펙과 AMO 검사기 기준으로는 **`gecko` 내부**에 위치해야 한다:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0",
    "data_collection_permissions": {
      "required": ["none"]
    }
  }
}
```

최상위에 넣으면 AMO 검사기가 인식하지 못하거나 다른 오류가 발생할 수 있다.

---

## 최종 Firefox manifest.json 템플릿

데이터 수집을 하지 않는 확장 프로그램의 최소 설정:

```json
{
  "manifest_version": 3,
  "name": "My Extension",
  "version": "1.0.0",
  "permissions": ["storage", "activeTab", "tabs"],
  "action": {
    "default_popup": "popup.html"
  },
  "content_scripts": [
    {
      "matches": ["https://example.com/*"],
      "js": ["content.js"],
      "all_frames": true,
      "run_at": "document_idle"
    }
  ],
  "background": {
    "scripts": ["background.js"]
  },
  "browser_specific_settings": {
    "gecko": {
      "id": "your-extension@example.com",
      "strict_min_version": "128.0",
      "data_collection_permissions": {
        "required": ["none"]
      }
    }
  }
}
```

---

## AMO 제출 시 참고사항

### 소스 코드 제출 여부

> "코드 생성기, 압축기, webpack 등을 사용합니까?"

빌드 도구 없이 순수 HTML/CSS/JS로 작성했다면 **"아니요"** 선택. 소스 코드 = 배포 코드이므로 별도 제출 불필요.

webpack, Vite, esbuild 등 번들러를 사용했다면 소스 코드를 별도로 제출해야 한다. AMO 리뷰어가 배포 코드와 소스 코드를 대조 검토하기 때문이다. 소스 코드 없이 난독화된 코드만 있으면 심사가 반려될 수 있다.

### innerHTML 경고

AMO 검사에서 `innerHTML` 사용 시 경고가 뜬다:

> Unsafe assignment to innerHTML

경고(warning)이므로 제출 자체는 차단되지 않지만, 수동 리뷰 단계에서 추가 검토 대상이 될 수 있다. XSS 취약점의 원인이 될 수 있기 때문이다. 가능하면 `textContent`나 DOM API(`createElement`, `appendChild`)로 대체하는 것이 좋다.

사용자 입력을 그대로 innerHTML에 넣는 패턴은 반드시 피해야 하고, 정말 필요한 경우에는 DOMPurify 같은 sanitize 라이브러리를 사용해야 한다.

### eval 및 동적 코드 실행

`eval()`, `Function()` 생성자, `setTimeout`/`setInterval`에 문자열을 넘기는 패턴은 AMO에서 오류로 처리된다. MV3의 CSP는 이런 패턴을 명시적으로 금지한다. 동적으로 코드를 생성해야 하는 경우 다른 접근법을 찾아야 한다.

### Firefox for Android

데스크탑 전용 확장 프로그램이라면 Android 호환성 테스트는 건너뛰어도 된다. AMO 제출 시 플랫폼 선택에서 데스크탑만 체크하면 된다.

Firefox for Android(Fenix)는 별도의 확장 프로그램 API 지원 범위를 가지고 있어서, 데스크탑에서 잘 동작하는 확장 프로그램이 Android에서는 동작하지 않을 수 있다.

---

## Key Takeaways

1. **`data_collection_permissions`는 2025년 11월부터 필수다.** 데이터를 수집하지 않더라도 `"required": ["none"]`으로 명시해야 한다. 빈 배열이나 boolean은 유효하지 않다.

2. **`data_collection_permissions`는 `browser_specific_settings.gecko` 안에 위치해야 한다.** 최상위에 놓으면 AMO가 인식하지 못한다.

3. **`background.service_worker`는 Firefox에서 동작하지 않는다.** Firefox MV3는 `background.scripts` 배열을 사용한다.

4. **`browser_specific_settings.gecko.id`는 명시적으로 지정하는 것이 좋다.** 자동 할당 UUID는 나중에 문제가 생길 수 있다.

5. **macOS에서 zip 만들 때 `__MACOSX/`, `.DS_Store`를 반드시 제외해야 한다.** `-x ".*" "__MACOSX/*"` 옵션을 사용하자.

6. **Chrome과 Firefox용 manifest.json은 단일 파일로 통합할 수 없다.** 빌드 스크립트로 브라우저별 manifest를 생성하는 구조가 필요하다.

7. **innerHTML 경고는 수동 리뷰 대상이 될 수 있다.** 반드시 차단되진 않지만, `textContent`나 DOM API로 대체하는 것이 장기적으로 안전하다.

---

## 참고 문서

- [Firefox built-in consent for data collection - Extension Workshop](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Announcing data collection consent changes - Mozilla Add-ons Blog](https://blog.mozilla.org/addons/2025/10/23/data-collection-consent-changes-for-new-firefox-extensions/)
- [manifest.json - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json)
- [browser_specific_settings - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/browser_specific_settings)
- [Porting a Google Chrome extension - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Porting_a_Google_Chrome_extension)
