---
title: "Rails 앱을 Hotwire Native로 iOS 앱 만들어 TestFlight 올리기까지의 삽질 기록"
date: 2026-03-07
draft: false
tags: ["iOS", "Hotwire Native", "Rails", "TestFlight", "XcodeGen", "삽질"]
description: "Rails 8 웹앱을 Hotwire Native iOS로 감싸서 App Store Connect에 올리기까지 겪은 에러들과 해결법"
---

Rails 8로 만든 긴급 신고 웹앱 **바로신고**를 Hotwire Native으로 iOS 앱으로 감싸서 TestFlight에 올리기까지의 과정을 정리합니다.

---

## 기술 스택

- **Backend**: Rails 8 + Turbo
- **iOS**: Hotwire Native 1.2.2 + XcodeGen
- **빌드**: Makefile 자동화

## 프로젝트 구조

```
ios/
├── project.yml          # XcodeGen 설정
├── ExportOptions.plist  # App Store 내보내기
├── Makefile             # 빌드 자동화
└── BaroSingo/
    ├── AppDelegate.swift
    ├── SceneController.swift
    ├── AppTab.swift
    ├── Bridge/
    │   ├── FormComponent.swift
    │   ├── HapticComponent.swift
    │   └── ShareComponent.swift
    └── Resources/
        ├── Assets.xcassets/
        └── path-configuration.json
```

---

## 삽질 1: Hotwire Native API 변경

### `Hotwire.config.userAgent` — 읽기 전용

```swift
// ❌ 컴파일 에러: 'userAgent' is a get-only property
Hotwire.config.userAgent = "BaroSingo iOS"

// ✅ 해결: makeCustomWebView 사용
Hotwire.config.makeCustomWebView = { configuration in
    let webView = WKWebView(frame: .zero, configuration: configuration)
    webView.customUserAgent = "BaroSingo iOS/1.0 Turbo Native"
    return webView
}
```

### `Hotwire.loadPathConfiguration` — 존재하지 않는 API

```swift
// ❌ 컴파일 에러: no member 'loadPathConfiguration'
Hotwire.loadPathConfiguration(from: [source])

// ✅ 해결: config.pathConfiguration.sources 직접 설정
Hotwire.config.pathConfiguration.sources = [
    .file(Bundle.main.url(forResource: "path-configuration", withExtension: "json")!),
    .server(URL(string: "\(baseURL)/api/hotwire/path-configuration")!)
]
```

### Bridge Component에서 ViewController 접근

```swift
// ❌ 컴파일 에러: optional type must be unwrapped
delegate.webView?.findViewController()

// ✅ 해결: delegate?.destination 사용
guard let viewController = delegate?.destination as? UIViewController else { return }
```

**교훈**: Hotwire Native는 버전별 API 변경이 잦다. 공식 소스코드와 실제 동작하는 프로젝트를 참고하는 게 가장 확실하다.

---

## 삽질 2: TestFlight 업로드 — 4개 에러 한번에

IPA를 `xcrun altool`로 업로드했더니 4개 validation 에러가 한꺼번에 터졌다.

### 에러 1, 2: AppIcon 누락

```
Missing required icon file. The bundle does not contain an app icon
for iPhone of exactly '120x120' pixels
for iPad of exactly '152x152' pixels
```

**원인**: Asset Catalog에 AppIcon.appiconset이 없었다.

**해결**: 1024px 원본 아이콘 생성 후 `sips`로 13개 사이즈 일괄 생성.

```bash
for size in 20 29 40 58 60 76 80 87 120 152 167 180 1024; do
  sips -z $size $size appicon_1024.png --out "icon_${size}.png"
done
```

### 에러 3: iPad 방향 누락

```
you need to include all of the orientations to support iPad multitasking
```

**원인**: `project.yml`에서 iPad 방향에 `UIInterfaceOrientationPortraitUpsideDown`이 빠져있었다.

```yaml
# ❌ 부족
UISupportedInterfaceOrientations~ipad:
  - UIInterfaceOrientationPortrait
  - UIInterfaceOrientationLandscapeLeft
  - UIInterfaceOrientationLandscapeRight

# ✅ 수정 — PortraitUpsideDown 추가
UISupportedInterfaceOrientations~ipad:
  - UIInterfaceOrientationPortrait
  - UIInterfaceOrientationPortraitUpsideDown
  - UIInterfaceOrientationLandscapeLeft
  - UIInterfaceOrientationLandscapeRight
```

### 에러 4: CFBundleIconName 누락

```
A value for the Info.plist key 'CFBundleIconName' is missing
```

**해결**: `project.yml` Info.plist properties에 추가.

```yaml
CFBundleIconName: AppIcon
```

**교훈**: `altool` 업로드 전에 `xcrun altool --validate-app`으로 먼저 검증하면 업로드 시간을 아낄 수 있다.

---

## 삽질 3: ASC에서 앱 생성

```
ERROR: Cannot determine the Apple ID from Bundle ID
```

App Store Connect에 앱이 등록되지 않은 상태에서 업로드하면 발생한다. `fastlane produce`는 비대화형 셸에서 동작하지 않으므로, ASC REST API로 Bundle ID를 등록하거나 웹에서 직접 생성해야 한다.

---

## 스크린샷 사이즈

ASC가 요구하는 정확한 픽셀 사이즈:

| 디스플레이 | 사이즈 |
|-----------|--------|
| 6.9" | 1320×2868 또는 1290×2796 |
| 6.5" | 1242×2688 또는 1284×2778 |

AI로 생성한 이미지는 정확한 사이즈가 나오지 않으므로, 비율이 같은 큰 이미지를 생성한 뒤 `sips -z`로 정확한 사이즈로 리사이즈하는 방식이 효과적이다.

---

## 최종 빌드 명령어

```bash
# 1. Xcode 프로젝트 생성
xcodegen generate

# 2. Release 아카이브
xcodebuild -project BaroSingo.xcodeproj \
  -scheme BaroSingo -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/BaroSingo.xcarchive \
  -allowProvisioningUpdates archive

# 3. IPA 내보내기
xcodebuild -exportArchive \
  -archivePath build/BaroSingo.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/ipa

# 4. TestFlight 업로드
xcrun altool --upload-app \
  -f build/ipa/BaroSingo.ipa -t ios \
  --apiKey $ASC_API_KEY --apiIssuer $ASC_ISSUER
```

---

## 결론

Hotwire Native는 Rails 웹앱을 빠르게 네이티브 앱으로 감쌀 수 있는 훌륭한 도구다. 다만 API 변경이 잦고, TestFlight 업로드 시 Asset Catalog과 Info.plist 설정을 꼼꼼히 챙겨야 한다. 한번 패턴을 잡아두면 다음 프로젝트부터는 30분 안에 끝낼 수 있다.
