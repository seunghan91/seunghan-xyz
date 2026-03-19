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

Chrome 확장 프로그램을 Firefox로 포팅해서 [AMO(addons.mozilla.org)](https://addons.mozilla.org)에 제출하면, Chrome Web Store에서는 없던 오류들을 만난다. 특히 2025년 11월부터 필수가 된 `data_collection_permissions` 때문에 삽질하기 쉽다.

---

## 증상: QR 이미지가 안 보인다?

확장 프로그램 팝업에서 이미지가 깨져 보이는 문제가 있었다. 원인은 단순했다 — **패키징된 zip에 이미지 파일이 누락**된 것. 로컬 개발 환경에서는 파일이 있지만, 스토어에 업로드한 빌드에는 빠져있었다.

### 해결: 깔끔한 zip 패키징

```bash
cd my_extension && zip -r ../extension.zip . \
  -x ".*" "__MACOSX/*" "*.DS_Store" "store_assets/*"
```

macOS에서 zip 만들면 `__MACOSX/` 폴더와 `.DS_Store`가 들어가는데, 이걸 제외해야 한다. `store_assets/` 같은 스토어 에셋 폴더도 확장 프로그램 자체에는 불필요하다.

패키징 후 반드시 확인:
```bash
unzip -l extension.zip | grep "이미지파일"
```

---

## Chrome → Firefox 포팅 시 manifest.json 차이점

### 1. background 설정

Chrome은 `service_worker`, Firefox MV3는 `scripts`:

```json
// ❌ Chrome 방식 (Firefox에서 오류)
"background": {
  "service_worker": "background.js"
}

// ✅ Firefox 방식
"background": {
  "scripts": ["background.js"]
}

// ❌ 둘 다 넣기 (오류 원인)
"background": {
  "service_worker": "background.js",
  "scripts": ["background.js"]
}
```

### 2. browser_specific_settings 필수

Firefox는 `gecko` 설정이 필요하다:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "your-extension@example.com",
    "strict_min_version": "128.0"
  }
}
```

### 3. windows 권한 미지원

Firefox에서 `"permissions": ["windows"]`는 유효하지 않다. 경고가 뜨므로 제거해야 한다.

```json
// ❌ Firefox에서 경고
"permissions": ["storage", "activeTab", "windows", "tabs"]

// ✅ windows 제거
"permissions": ["storage", "activeTab", "tabs"]
```

---

## data_collection_permissions 삽질 기록

2025년 11월부터 **모든 새 Firefox 확장 프로그램**은 `data_collection_permissions`을 manifest.json에 명시해야 한다. 이걸 빠뜨리면 AMO 검사에서 오류로 제출이 차단된다.

### 시도 1: ❌ `is_exempt` 사용

```json
"data_collection_permissions": {
  "is_exempt": true,
  "description": "데이터를 수집하지 않습니다."
}
```
> 오류: `must have required property 'required'`

`is_exempt`라는 속성은 존재하지 않는다.

### 시도 2: ❌ `required: false`

```json
"data_collection_permissions": {
  "required": false
}
```
> 오류: `"required" must be array`

boolean이 아니라 배열이어야 한다.

### 시도 3: ❌ 빈 배열 `required: []`

```json
"data_collection_permissions": {
  "required": []
}
```
> 오류: 통과하지 못함

빈 배열도 안 된다.

### 시도 4: ✅ `required: ["none"]`

```json
"data_collection_permissions": {
  "required": ["none"]
}
```

**이게 정답이다.** 데이터를 수집하지 않는 확장 프로그램은 `"none"`을 배열에 명시해야 한다.

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

### innerHTML 경고

AMO 검사에서 `innerHTML` 사용 시 경고가 뜬다:

> Unsafe assignment to innerHTML

경고(warning)이므로 제출은 차단되지 않지만, 가능하면 `textContent`나 DOM API로 대체하는 것이 좋다.

### Firefox for Android

데스크탑 전용 확장 프로그램이라면 Android 호환성 테스트는 건너뛰어도 된다. AMO 제출 시 플랫폼 선택에서 데스크탑만 체크하면 된다.

---

## 참고 문서

- [Firefox built-in consent for data collection - Extension Workshop](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
- [Announcing data collection consent changes - Mozilla Add-ons Blog](https://blog.mozilla.org/addons/2025/10/23/data-collection-consent-changes-for-new-firefox-extensions/)
- [manifest.json - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json)
