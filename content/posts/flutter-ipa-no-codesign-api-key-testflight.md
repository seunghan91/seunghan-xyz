---
title: "flutter build ipa 실패 원인과 --no-codesign + API Key로 TestFlight 배포하기"
date: 2026-02-27
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "Makefile", "코드서명", "배포자동화"]
description: "Development 인증서 없이 flutter build ipa가 실패하는 이유와, --no-codesign + App Store Connect API Key로 Xcode 계정 로그인 없이 TestFlight 배포하는 방법"
---

Flutter iOS 앱을 여러 Apple 계정으로 관리하다 보면 한 프로젝트에서는 `make testflight`가 잘 되는데 다른 프로젝트에서는 동일한 Makefile이 실패하는 상황이 생긴다. 오늘 겪은 케이스를 정리한다.

---

## 증상

```
❌ Error (Xcode): No signing certificate "iOS Development" found:
   No "iOS Development" signing certificate matching team ID "XXXXXXXX"
   with a private key was found.
```

`flutter build ipa` 실행 시 위 오류로 실패한다. Distribution 인증서는 키체인에 있는데 Development 인증서가 없다는 메시지다.

---

## 원인: `flutter build ipa` 내부에서 일어나는 일

`flutter build ipa`는 내부적으로 다음 순서로 동작한다.

```
flutter build ipa
  └─ flutter build ios --release        ← 여기서 문제 발생
       └─ xcodebuild -configuration Release
            └─ Xcode 자동 서명 파이프라인 실행
                 ├─ Xcode 계정 로그인 확인
                 ├─ iOS Development 인증서 체크  ← ❌ 없으면 실패
                 └─ 프로비저닝 프로파일 생성
```

TestFlight 업로드용이라 Distribution 인증서만 있으면 될 것 같지만, Xcode 자동 서명은 빌드 단계에서 **Development 인증서도 함께 요구**한다. 시뮬레이터나 실기기 디버그 빌드 지원을 위한 것이다.

**요약:**
- `flutter build ipa` → Xcode 계정 로그인 + Development cert 필요
- `flutter build ios --no-codesign` → 서명 과정 완전 건너뜀

---

## 왜 다른 프로젝트에서는 됐는가

두 프로젝트 비교:

| | 프로젝트 A (성공) | 프로젝트 B (실패) |
|---|---|---|
| Apple 팀 | Team 1 | Team 2 |
| Xcode 로그인 | ✅ 로그인됨 | ❌ 미로그인 |
| Development cert | ✅ 있음 | ❌ 없음 |
| Distribution cert | ✅ 있음 | ✅ 있음 |
| Makefile 방식 | `--no-codesign` + xcodebuild | `flutter build ipa` |

프로젝트 A는 이미 `--no-codesign` 방식을 쓰고 있어서 성공했고, 프로젝트 B는 `flutter build ipa`를 쓰고 있어서 실패했다.

Keychain에 Distribution 인증서만 있고, 해당 팀으로 Xcode에 로그인하지 않은 상황이라면 `flutter build ipa`는 무조건 실패한다.

---

## 해결: `--no-codesign` + xcodebuild API Key

### 전체 흐름

```
flutter build ios --release --no-codesign    ← 서명 없이 빌드
      ↓
xcodebuild archive                            ← API Key로 자동 서명 + 아카이브
      ↓
xcodebuild -exportArchive                     ← IPA 내보내기
      ↓
xcrun altool --upload-app                     ← TestFlight 업로드
```

`--no-codesign`으로 빌드하면 iOS 앱 바이너리만 생성되고 서명은 생략된다. 이후 `xcodebuild archive` 단계에서 App Store Connect API Key를 이용해 서명과 프로비저닝을 자동으로 처리한다. Xcode 계정 로그인이 전혀 필요 없다.

---

## 전체 Makefile

```makefile
# App Store Connect API 키
ASC_API_KEY_PATH ?= /path/to/AuthKey_XXXXXXXX.p8
ASC_API_KEY_ID ?= XXXXXXXX
ASC_API_ISSUER_ID ?= xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

FLUTTER := flutter
SCHEME := Runner
ARCHIVE_PATH := build/ios/xcarchive/Runner.xcarchive
IPA_DIR := build/ios/ipa

.PHONY: clean build-testflight testflight

clean:
	@rm -rf build/

build-testflight: clean
	@echo "▶ Flutter 빌드 (no-codesign)..."
	@$(FLUTTER) build ios --release --no-codesign

	@echo "▶ xcodebuild archive (API Key 서명)..."
	@xcodebuild \
		-workspace ios/Runner.xcworkspace \
		-scheme $(SCHEME) \
		-configuration Release \
		-destination "generic/platform=iOS" \
		-derivedDataPath build/derived_data \
		-archivePath $(ARCHIVE_PATH) \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		DEVELOPMENT_TEAM=YOUR_TEAM_ID \
		archive \
		-allowProvisioningUpdates

	@echo "▶ IPA 내보내기..."
	@xcodebuild -exportArchive \
		-archivePath $(ARCHIVE_PATH) \
		-exportPath $(IPA_DIR) \
		-exportOptionsPlist ios/ExportOptions.plist \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		-allowProvisioningUpdates

upload:
	@IPA_FILE=$$(ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1); \
	if [ -z "$$IPA_FILE" ]; then echo "❌ IPA 없음, make build-testflight 먼저"; exit 1; fi; \
	xcrun altool --upload-app \
		--type ios \
		--file "$$IPA_FILE" \
		--apiKey $(ASC_API_KEY_ID) \
		--apiIssuer $(ASC_API_ISSUER_ID)

testflight: build-testflight upload
	@echo "🎉 TestFlight 업로드 완료"
```

### ExportOptions.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>destination</key>
    <string>upload</string>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
</dict>
</plist>
```

`manageAppVersionAndBuildNumber: false`로 설정해야 빌드 번호를 Makefile에서 직접 제어할 수 있다.

---

## 네이티브 Swift(Xcode) 프로젝트에도 동일 패턴 적용

Flutter 없이 순수 Xcode 프로젝트(Swift/SwiftUI)도 동일한 방식을 쓴다. `flutter build ios --no-codesign` 단계만 없으면 된다.

```makefile
# Swift/Xcode 프로젝트용

ASC_API_KEY_PATH ?= /path/to/AuthKey_XXXXXXXX.p8
ASC_API_KEY_ID ?= XXXXXXXX
ASC_API_ISSUER_ID ?= xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

XCPROJECT := MyApp/MyApp.xcodeproj
SCHEME := MyApp
ARCHIVE_PATH := build/MyApp.xcarchive
IPA_DIR := build/ipa

.PHONY: testflight increment-build archive export upload

increment-build:
	@cd $(dir $(XCPROJECT)) && agvtool next-version -all
	@echo "빌드 번호: $$(cd $(dir $(XCPROJECT)) && agvtool what-version -terse)"

archive:
	@mkdir -p build
	@xcodebuild \
		-project $(XCPROJECT) \
		-scheme $(SCHEME) \
		-configuration Release \
		-destination "generic/platform=iOS" \
		-derivedDataPath build/derived_data \
		-archivePath $(ARCHIVE_PATH) \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		DEVELOPMENT_TEAM=YOUR_TEAM_ID \
		-allowProvisioningUpdates \
		archive

export: archive
	@xcodebuild -exportArchive \
		-archivePath $(ARCHIVE_PATH) \
		-exportPath $(IPA_DIR) \
		-exportOptionsPlist MyApp/ExportOptions.plist \
		-authenticationKeyPath "$(ASC_API_KEY_PATH)" \
		-authenticationKeyID "$(ASC_API_KEY_ID)" \
		-authenticationKeyIssuerID "$(ASC_API_ISSUER_ID)" \
		-allowProvisioningUpdates

upload:
	@IPA_FILE=$$(ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1); \
	xcrun altool --upload-app --type ios --file "$$IPA_FILE" \
		--apiKey $(ASC_API_KEY_ID) --apiIssuer $(ASC_API_ISSUER_ID)

testflight: increment-build archive export upload
	@echo "🎉 TestFlight 업로드 완료"
```

`agvtool next-version -all`로 빌드 번호를 자동으로 증가시킨 뒤 배포한다. Info.plist를 직접 수정하는 것보다 안정적이다.

---

## App Store Connect API Key 발급

[App Store Connect](https://appstoreconnect.apple.com) → Users and Access → Integrations → App Store Connect API → + 버튼

- **Role**: Developer 이상 (App Manager 권장)
- **.p8 파일**: 발급 시 딱 한 번만 다운로드 가능, 잃어버리면 재발급 필요
- **Key ID / Issuer ID**: API Keys 탭 상단에 표시됨

발급한 `.p8` 파일을 `~/.appstoreconnect/private_keys/AuthKey_{KEY_ID}.p8` 위치에 두면 `xcrun altool`이 자동으로 찾는다.

```bash
mkdir -p ~/.appstoreconnect/private_keys
cp AuthKey_XXXXXXXX.p8 ~/.appstoreconnect/private_keys/
```

---

## 정리

| 방식 | Xcode 계정 로그인 | Development cert | 결과 |
|---|---|---|---|
| `flutter build ipa` | 필요 | 필요 | 없으면 실패 |
| `flutter build ios --no-codesign` + xcodebuild API Key | 불필요 | 불필요 | 항상 성공 |

여러 Apple 팀 계정을 관리하거나, CI/CD 환경처럼 Xcode 로그인이 어려운 상황이라면 `--no-codesign` + API Key 방식이 훨씬 안정적이다. Distribution 인증서만 키체인에 있어도 배포가 가능하다.
