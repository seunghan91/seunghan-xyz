---
title: "Flutter TestFlight 업로드 자동화 - Makefile로 한 줄에 끝내기"
date: 2025-08-20
draft: true
tags: ["Flutter", "TestFlight", "iOS", "Makefile", "자동화", "배포"]
description: "flutter build ipa부터 xcrun altool 업로드까지 Makefile 한 줄로 처리하는 방법과 흔히 빠지는 IPA 파일명 함정"
cover:
  image: "/images/og/flutter-testflight-makefile-automation.png"
  alt: "Flutter Testflight Makefile Automation"
  hidden: true
---

Flutter iOS 앱을 TestFlight에 올리는 과정은 단계가 많다. `flutter build ipa`, Xcode 아카이브, altool 업로드... Makefile로 묶어두면 `make testflight` 한 줄로 끝난다.

---

## 최종 Makefile

```makefile
.PHONY: build-ipa testflight clean

EXPORT_OPTIONS  = ios/ExportOptions.plist
API_KEY         = YOUR_API_KEY_ID
API_ISSUER      = YOUR_ISSUER_ID
IPA_DIR         = build/ios/ipa
IPA_FILE        = $(IPA_DIR)/Talkk.ipa  # ← 앱 Display Name과 일치해야 함

build-ipa:
	flutter build ipa --release --export-options-plist=$(EXPORT_OPTIONS)

testflight: build-ipa
	@echo "📦 TestFlight 업로드 중..."
	xcrun altool --upload-app \
		--type ios \
		--file "$(IPA_FILE)" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER) \
		--verbose
	@echo "✅ TestFlight 업로드 완료!"

clean:
	flutter clean && flutter pub get
```

---

## ExportOptions.plist 설정

`flutter build ipa`는 내부적으로 Xcode 아카이브 후 IPA를 만든다. 이 과정에서 서명 방식, 팀 ID, App Store Connect API 키 등을 지정하는 파일이 필요하다.

```xml
<!-- ios/ExportOptions.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>stripSwiftSymbols</key>
    <true/>
    <key>uploadSymbols</key>
    <true/>
    <key>authenticationKeyID</key>
    <string>YOUR_API_KEY_ID</string>
    <key>authenticationKeyIssuerID</key>
    <string>YOUR_ISSUER_ID</string>
    <key>authenticationKeyPath</key>
    <string>/Users/yourname/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8</string>
</dict>
</plist>
```

App Store Connect API 키는 [App Store Connect → 사용자 및 액세스 → 키](https://appstoreconnect.apple.com/access/integrations/api)에서 발급한다. API 키 `.p8` 파일은 `~/.appstoreconnect/private_keys/`에 두면 altool이 자동으로 찾는다.

---

## 흔히 빠지는 함정: IPA 파일명

처음 이 Makefile을 세팅할 때 파일명을 `app_name.ipa`나 `Runner.ipa`로 설정하기 쉽다. 그런데 실제로 생성되는 IPA 파일명은 **앱의 Display Name**을 따른다.

```bash
# 빌드 후 실제 파일명 확인
ls build/ios/ipa/
# DistributionSummary.plist
# ExportOptions.plist
# Packaging.log
# Talkk.ipa  ← Display Name 기준
```

`Info.plist`의 `CFBundleDisplayName` 또는 Xcode의 Display Name 설정값이 파일명이 된다. Makefile의 `IPA_FILE` 변수가 실제 파일명과 다르면 다음 오류가 난다.

```
ERROR: File does not exist at path: build/ios/ipa/app.ipa
```

앱 이름을 바꾸면 Makefile도 같이 수정해야 한다.

---

## 빌드 번호 자동 관리

TestFlight는 동일 버전 내에서 빌드 번호가 증가해야 새 빌드를 받아들인다. Flutter 프로젝트의 `pubspec.yaml`에서 관리한다.

```yaml
# pubspec.yaml
version: 1.0.1+3
#        ↑     ↑
#     버전    빌드번호
```

`flutter build ipa` 실행 시 빌드 결과에 버전/빌드 번호가 표시된다.

```
[✓] App Settings Validation
    • Version Number: 1.0.1
    • Build Number: 3
```

매 TestFlight 배포마다 빌드 번호를 올려줘야 한다. 스크립트로 자동화하고 싶다면 이렇게.

```bash
# pubspec.yaml의 빌드 번호 자동 증가
CURRENT=$(grep "^version:" pubspec.yaml | sed 's/.*+//')
NEXT=$((CURRENT + 1))
sed -i '' "s/+$CURRENT$/+$NEXT/" pubspec.yaml
```

---

## 전체 배포 흐름

```
pubspec.yaml 빌드 번호 증가
        ↓
flutter clean && flutter pub get
        ↓
make testflight
   ├── flutter build ipa --release --export-options-plist=...
   │       ↓
   │   Xcode 아카이브 (~1분 30초)
   │       ↓
   │   IPA 생성 (~1분 50초)
   └── xcrun altool --upload-app ...
           ↓
       UPLOAD SUCCEEDED
           ↓
App Store Connect 처리 (5~10분)
           ↓
TestFlight 테스터에게 배포
```

한 번 세팅해두면 이후 배포는 빌드 번호 올리고 `make testflight` 한 줄이다.

---

## clean 빌드가 필요한 경우

다음 상황에서는 반드시 `flutter clean` 후 재빌드해야 한다.

- `google-services.json` 교체 (Android Firebase 설정 변경)
- `GoogleService-Info.plist` 교체 (iOS Firebase 설정 변경)
- `pubspec.yaml` 패키지 버전 변경
- iOS `Podfile` 변경

Firebase 설정 파일을 바꾸고 `flutter clean` 없이 빌드하면 이전 설정이 그대로 들어가는 경우가 있다.

```bash
flutter clean
flutter pub get
cd ios && pod install && cd ..
make testflight
```

pod install까지 같이 해주면 확실하다.
