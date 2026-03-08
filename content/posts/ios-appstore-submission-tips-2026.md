---
title: "iOS 앱 배포 삽질 모음: Bundle ID 계정 이전, ITMS-90683, AI 아이콘/스크린샷 생성"
date: 2026-03-08
draft: false
tags: ["iOS", "Flutter", "App Store Connect", "TestFlight", "AI", "Gemini", "앱배포"]
description: "Apple Developer 계정 전환, Bundle ID 신규 등록, 권한 누락 에러 수정, BizRouter + Gemini 3 Pro로 앱 아이콘/스크린샷 자동 생성까지 — 실제로 겪은 삽질을 정리했다."
---

Flutter 앱을 TestFlight에 올리는 과정에서 겪은 삽질들을 기록한다. Apple Developer 계정 전환, Bundle ID 등록, 권한 누락 에러, 그리고 AI로 아이콘과 스크린샷을 자동 생성하는 방법까지.

---

## 1. Apple Developer 계정이 다를 때 — Bundle ID 이전은 불가

앱을 A 계정(Team A)에서 개발하다가 B 계정(Team B)으로 배포하려고 했다. 기존 Bundle ID가 A 계정에 이미 등록되어 있어서 B 계정으로 등록하려 하면 **409 Conflict** 에러가 난다.

```json
{
  "errors": [{
    "status": "409",
    "code": "ENTITY_ERROR.ATTRIBUTE.INVALID",
    "detail": "An App ID with Identifier 'com.xxx.yyy' is not available."
  }]
}
```

Bundle ID는 계정 간 이전이 불가능하다. 해결책은 두 가지다:

1. **새 Bundle ID를 만든다** — B 계정에 새 Bundle ID 등록 후 Xcode 프로젝트의 `PRODUCT_BUNDLE_IDENTIFIER`를 교체
2. **그냥 A 계정으로 배포한다**

새 Bundle ID를 API로 등록하는 방법:

```python
import jwt, time, requests

KEY_ID = "YOUR_KEY_ID"
ISSUER_ID = "YOUR_ISSUER_ID"
with open("AuthKey_XXXXX.p8") as f:
    private_key = f.read()

payload = {
    "iss": ISSUER_ID,
    "iat": int(time.time()),
    "exp": int(time.time()) + 1200,
    "aud": "appstoreconnect-v1"
}
token = jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": KEY_ID})
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

data = {
    "data": {
        "type": "bundleIds",
        "attributes": {
            "identifier": "com.new.bundleid",
            "name": "MyApp",
            "platform": "IOS"
        }
    }
}
r = requests.post("https://api.appstoreconnect.apple.com/v1/bundleIds", headers=headers, json=data)
print(r.status_code, r.json())
```

---

## 2. App Store Connect에 앱이 먼저 등록되어 있어야 `altool` 업로드 가능

`xcrun altool --upload-app`으로 TestFlight 업로드할 때 이런 에러가 나면:

```
Cannot determine the Apple ID from Bundle ID 'com.xxx.yyy' and platform 'IOS'
```

App Store Connect 웹에서 앱을 먼저 생성해야 한다. API로는 앱 생성이 안 되고 (403 Forbidden), 웹에서 직접 만들어야 한다.

앱 생성 후 업로드 명령:

```bash
xcrun altool --upload-app \
  -f ./build/ios/ipa/myapp.ipa \
  -t ios \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

---

## 3. ITMS-90683: NSPhotoLibraryUsageDescription 누락

업로드 후 Apple로부터 이런 메일이 온다:

> ITMS-90683: Missing purpose string in Info.plist — Your app's code references one or more APIs that access sensitive user data...

앱에서 사진 라이브러리를 직접 사용하지 않아도, 사용하는 외부 패키지가 참조하면 목적 문자열이 필요하다. `ios/Runner/Info.plist`에 추가:

```xml
<key>NSPhotoLibraryUsageDescription</key>
<string>파일을 저장하거나 공유할 때 사진 라이브러리에 접근합니다.</string>
<key>NSPhotoLibraryAddUsageDescription</key>
<string>이미지를 저장할 때 사진 라이브러리에 접근합니다.</string>
```

추가 후 빌드 번호 올리고 재업로드.

---

## 4. ExportOptions.plist에 API Key 추가하면 Xcode 계정 로그인 없이 배포 가능

Xcode에 Apple 계정이 로그인되어 있지 않으면 export 단계에서 이런 에러가 난다:

```
error: exportArchive No Account for Team "XXXXXXXXXX"
```

`ExportOptions.plist`에 API Key 정보를 넣으면 해결된다:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>authenticationKeyPath</key>
    <string>/Users/username/.appstoreconnect/private_keys/AuthKey_XXXXX.p8</string>
    <key>authenticationKeyID</key>
    <string>XXXXX</string>
    <key>authenticationKeyIssuerID</key>
    <string>xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</string>
    <key>ITSAppUsesNonExemptEncryption</key>
    <false/>
</dict>
</plist>
```

---

## 5. BizRouter + Gemini 3 Pro Image로 앱 아이콘 시안 10개 자동 생성

[BizRouter](https://bizrouter.ai) AI 게이트웨이를 통해 Gemini 3 Pro Image 모델(`google/gemini-3-pro-image-preview`)로 앱 아이콘 시안을 뽑았다.

Perplexity로 2025-2026 트렌드를 먼저 검색하고, 아래 스타일로 각각 프롬프트를 작성했다:

| # | 스타일 |
|---|--------|
| 1 | Liquid Glass (iOS 26) |
| 2 | Neo-Brutalism |
| 3 | 3D Clay Soft Render |
| 4 | Aurora Gradient |
| 5 | Glassmorphism 2.0 |
| 6 | Dynamic Minimalism |
| 7 | Tactile 3D |
| 8 | Dark Mode Neon |
| 9 | Retro Modern Fusion |
| 10 | AI Aesthetic / Surreal |

API 호출 예시:

```python
import requests, base64

API_KEY = "YOUR_BIZROUTER_API_KEY"
payload = {
    "model": "google/gemini-3-pro-image-preview",
    "messages": [{
        "role": "user",
        "content": "iOS app icon, 1024x1024. Style: Neo-Brutalism 2025..."
    }],
    "aspect_ratio": "1:1",
    "image_size": "1K"
}
r = requests.post(
    "https://api.bizrouter.ai/v1/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=120
)
content = r.json()["choices"][0]["message"]["content"]
for part in content:
    if part["type"] == "image_url":
        b64 = part["image_url"]["url"].split(",", 1)[1]
        with open("icon.png", "wb") as f:
            f.write(base64.b64decode(b64))
```

생성된 이미지를 Pillow로 전체 iOS 사이즈에 맞게 리사이즈:

```python
from PIL import Image

sizes = [
    ("Icon-App-20x20@2x.png", 40),
    ("Icon-App-60x60@2x.png", 120),
    ("Icon-App-60x60@3x.png", 180),
    ("Icon-App-1024x1024@1x.png", 1024),
    # ... 등 15개 사이즈
]
img = Image.open("icon.png").convert("RGBA")
for filename, px in sizes:
    img.resize((px, px), Image.LANCZOS).convert("RGB").save(filename)
```

---

## 6. App Store 스크린샷 사이즈와 비율 문제

App Store에서 요구하는 스크린샷 비율이 일반적인 9:16보다 훨씬 길다.

| 기기 | 해상도 | 비율 |
|------|--------|------|
| iPhone 6.5" | 1242 × 2688 | ≈ 1:2.16 |
| iPhone 6.9" | 1320 × 2868 | ≈ 1:2.17 |

Gemini가 지원하는 가장 긴 비율은 `9:16` (1:1.78). 그대로 크롭하면 내용이 잘린다.

**해결: 레터박스 방식** — 9:16 이미지를 너비 기준으로 맞추고 위아래를 검정으로 채운다. 검정 배경 디자인이면 자연스럽게 이어진다.

```python
from PIL import Image
from io import BytesIO

def letterbox_resize(img_bytes, target_w, target_h):
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h

    if src_ratio > tgt_ratio:
        new_w = target_w
        new_h = int(target_w / src_ratio)
    else:
        new_h = target_h
        new_w = int(target_h * src_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    canvas.paste(img, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas
```

---

## 정리

- Bundle ID는 계정 간 이전 불가 → 새로 등록
- `altool` 업로드 전에 App Store Connect 웹에서 앱 먼저 생성 필수
- 권한 목적 문자열 누락(ITMS-90683)은 사용하지 않아도 패키지가 참조하면 필요
- `ExportOptions.plist`에 API Key 넣으면 Xcode 로그인 없이 CI/CD 가능
- Gemini 3 Pro Image로 아이콘/스크린샷 자동 생성 가능 (레터박스로 비율 처리)
