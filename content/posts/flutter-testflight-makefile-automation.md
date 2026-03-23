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

Flutter iOS 앱을 TestFlight에 올리는 과정은 단계가 많다. `flutter build ipa`, Xcode 아카이브, altool 업로드... 매번 수동으로 반복하다 보면 실수가 생기기 마련이다. Makefile로 묶어두면 `make testflight` 한 줄로 끝난다. 이 글에서는 실제 운영 중인 프로젝트에서 사용하는 Makefile 구성부터 흔히 빠지는 함정, 빌드 번호 자동 관리, 클린 빌드가 필요한 시점까지 모두 다룬다.

---

## 왜 Makefile인가

Fastlane, GitHub Actions 같은 도구도 있지만, 로컬 개발에서 TestFlight 배포까지 빠르게 돌리기엔 Makefile이 가장 가볍다. 의존성 설치가 없고, 프로젝트 루트에 파일 하나만 두면 된다. `make testflight` 한 줄이 전체 파이프라인을 순서대로 실행한다.

CI/CD가 필요한 팀 프로젝트라면 Fastlane이나 GitHub Actions가 더 적합하지만, 1인 개발이나 프로토타입 단계에서는 Makefile의 단순함이 큰 장점이다. 새 맥에서 프로젝트를 클론하면 별도 설정 없이 `make testflight`만 치면 된다.

---

## 사전 준비: App Store Connect API 키

altool로 업로드하려면 App Store Connect API 키가 필요하다. 비밀번호 방식은 2023년부터 더 이상 권장되지 않으며, API 키 방식이 표준이다.

1. [App Store Connect → 사용자 및 액세스 → 통합 → App Store Connect API](https://appstoreconnect.apple.com/access/integrations/api) 접속
2. 새 키 생성 (역할: App Manager 이상)
3. `.p8` 파일 다운로드 — **한 번만 다운로드 가능**하니 분실 주의
4. Key ID와 Issuer ID 메모

`.p8` 파일은 `~/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8` 위치에 두면 altool이 자동으로 찾는다. 이 경로를 쓰면 `ExportOptions.plist`에 절대 경로를 하드코딩하지 않아도 된다.

---

## 최종 Makefile

```makefile
.PHONY: build-ipa testflight clean

EXPORT_OPTIONS  = ios/ExportOptions.plist
API_KEY         = YOUR_API_KEY_ID
API_ISSUER      = YOUR_ISSUER_ID
IPA_DIR         = build/ios/ipa
IPA_FILE        = $(IPA_DIR)/Talkk.ipa  # <- 앱 Display Name과 반드시 일치해야 함

build-ipa:
	flutter build ipa --release --export-options-plist=$(EXPORT_OPTIONS)

testflight: build-ipa
	@echo "TestFlight 업로드 중..."
	xcrun altool --upload-app \
		--type ios \
		--file "$(IPA_FILE)" \
		--apiKey $(API_KEY) \
		--apiIssuer $(API_ISSUER) \
		--verbose
	@echo "TestFlight 업로드 완료!"

clean:
	flutter clean && flutter pub get
```

`testflight` 타겟은 `build-ipa`에 의존하기 때문에 `make testflight`만 입력해도 빌드 → 업로드가 순서대로 실행된다. `--verbose` 플래그는 업로드 진행 상황을 실시간으로 출력해준다. 업로드에 시간이 걸릴 때 아무 출력이 없으면 멈춘 것처럼 보이므로 꼭 붙여두는 게 낫다.

---

## ExportOptions.plist 설정

`flutter build ipa`는 내부적으로 Xcode 아카이브 후 IPA를 만든다. 이 과정에서 서명 방식, 팀 ID, App Store Connect API 키 등을 지정하는 파일이 필요하다. 이 파일이 없거나 경로가 잘못되면 빌드가 중간에 실패한다.

```xml
<!-- ios/ExportOptions.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
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

`signingStyle`을 `automatic`으로 설정하면 Xcode가 프로비저닝 프로파일을 자동으로 관리한다. 수동 관리(`manual`)를 쓰려면 `provisioningProfiles` 키에 번들 ID와 프로파일 UUID를 직접 지정해야 한다. 팀 내 여러 명이 빌드를 돌린다면 자동 서명이 훨씬 편하다.

`uploadSymbols`를 `true`로 설정하면 dSYM 파일도 함께 업로드된다. Crashlytics나 App Store Connect 크래시 로그에서 심볼이 풀려 스택 트레이스를 제대로 볼 수 있다.

주의할 점이 하나 있다. **iCloud를 사용하지 않는 앱에 `iCloudContainerEnvironment` 키를 넣으면 업로드가 실패한다.** 이 키는 iCloud 연동이 실제로 설정된 앱에서만 필요하다.

---

## 흔히 빠지는 함정: IPA 파일명

처음 Makefile을 세팅할 때 파일명을 `app_name.ipa`나 `Runner.ipa`로 설정하기 쉽다. 그런데 실제로 생성되는 IPA 파일명은 **앱의 Display Name**을 따른다. `Runner`가 아니다.

```bash
# 빌드 후 실제 파일명 확인
ls build/ios/ipa/
# DistributionSummary.plist
# ExportOptions.plist
# Packaging.log
# Talkk.ipa  <- Display Name 기준으로 생성됨
```

`Info.plist`의 `CFBundleDisplayName` 또는 Xcode의 Display Name 설정값이 파일명이 된다. 한국어 Display Name을 쓰는 경우 파일명도 한글이 된다 — `앱이름.ipa`. 이 경우 경로에 공백이나 특수문자가 있으면 altool이 파일을 못 찾는다. 가능하면 Display Name을 영문으로 쓰거나, `IPA_FILE` 변수에 정확한 파일명을 넣어야 한다.

Makefile의 `IPA_FILE` 변수가 실제 파일명과 다르면 다음 오류가 난다.

```
ERROR: File does not exist at path: build/ios/ipa/app.ipa
```

앱 이름을 바꾸면 Makefile의 `IPA_FILE`도 함께 수정해야 한다. 이걸 잊으면 빌드는 성공했는데 업로드에서 실패하는 상황이 벌어진다.

더 견고하게 만들려면 파일명을 하드코딩하지 않고 동적으로 찾을 수 있다.

```makefile
IPA_FILE = $(shell ls $(IPA_DIR)/*.ipa 2>/dev/null | head -1)
```

단, IPA 디렉토리에 이전 빌드 파일이 남아 있으면 잘못된 파일을 참조할 수 있다. 빌드 전에 디렉토리를 지우는 방법이 더 안전하다.

```makefile
build-ipa:
	rm -rf $(IPA_DIR)
	flutter build ipa --release --export-options-plist=$(EXPORT_OPTIONS)
```

---

## 빌드 번호 자동 관리

TestFlight는 동일 버전 내에서 빌드 번호가 증가해야 새 빌드를 받아들인다. 같은 빌드 번호로 다시 업로드하면 다음 오류가 난다.

```
ERROR ITMS-90189: "Redundant Binary Upload.
You've already uploaded a build with build number '3' for version number '1.0.1'."
```

Flutter 프로젝트는 `pubspec.yaml`에서 버전과 빌드 번호를 함께 관리한다.

```yaml
# pubspec.yaml
version: 1.0.1+3
#        ^     ^
#     버전    빌드번호
```

`flutter build ipa` 실행 시 빌드 결과에 버전/빌드 번호가 표시된다.

```
[✓] App Settings Validation
    • Version Number: 1.0.1
    • Build Number: 3
```

매 TestFlight 배포마다 빌드 번호를 올려줘야 한다. 스크립트로 자동화하면 이렇게 된다.

```bash
# pubspec.yaml의 빌드 번호 자동 증가
CURRENT=$(grep "^version:" pubspec.yaml | sed 's/.*+//')
NEXT=$((CURRENT + 1))
sed -i '' "s/+$CURRENT$/+$NEXT/" pubspec.yaml
```

Makefile에 통합하면 배포 전 자동으로 번호를 올릴 수 있다.

```makefile
bump:
	@CURRENT=$$(grep "^version:" pubspec.yaml | sed 's/.*+//'); \
	NEXT=$$((CURRENT + 1)); \
	sed -i '' "s/+$$CURRENT$$/+$$NEXT/" pubspec.yaml; \
	echo "빌드 번호: $$CURRENT -> $$NEXT"

testflight: bump build-ipa
	...
```

단, `bump`를 `testflight` 의존성에 넣으면 빌드가 실패해도 번호가 올라가 버린다는 단점이 있다. 번호를 올리는 시점을 업로드 성공 직후로 미루거나, 수동으로 `make bump`를 따로 실행하는 방식이 더 안전하다.

---

## 전체 배포 흐름

```
pubspec.yaml 빌드 번호 증가
        |
flutter clean && flutter pub get  (선택, 필요한 경우만)
        |
make testflight
   |-- flutter build ipa --release --export-options-plist=...
   |       |
   |   Xcode 아카이브 (~1분 30초)
   |       |
   |   IPA 생성 (~1분 50초)
   +-- xcrun altool --upload-app ...
           |
       UPLOAD SUCCEEDED
           |
App Store Connect 처리 (5~10분)
           |
TestFlight 테스터에게 배포
```

한 번 세팅해두면 이후 배포는 빌드 번호 올리고 `make testflight` 한 줄이다. 전체 시간은 빌드 3분 + 업로드 1~2분 + App Store Connect 처리 5~10분이다. 업로드가 완료된 직후 TestFlight에 빌드가 보이지 않는 건 정상이다. App Store Connect가 빌드를 처리하는 동안 "Processing" 상태로 표시되다가 완료되면 테스터에게 알림이 간다.

---

## clean 빌드가 필요한 경우

모든 빌드에 `flutter clean`을 넣으면 매번 3분씩 더 걸린다. 다음 상황에서만 선택적으로 클린 빌드를 실행하면 된다.

- `google-services.json` 교체 (Android Firebase 설정 변경)
- `GoogleService-Info.plist` 교체 (iOS Firebase 설정 변경)
- `pubspec.yaml` 패키지 버전 변경
- iOS `Podfile` 변경
- Xcode 또는 Flutter SDK 업그레이드 후

Firebase 설정 파일을 바꾸고 `flutter clean` 없이 빌드하면 이전 설정이 그대로 들어가는 경우가 있다. 증상이 이상하면 가장 먼저 클린 빌드를 의심해야 한다.

```bash
flutter clean
flutter pub get
cd ios && pod install && cd ..
make testflight
```

`pod install`까지 같이 해주면 확실하다. 특히 새 iOS 패키지를 추가하거나 기존 패키지 버전을 올린 경우엔 pod install이 필수다. pod install 없이 빌드하면 CocoaPods 의존성 불일치로 아카이브 단계에서 실패한다.

---

## 자주 겪는 오류와 해결책

**오류: `No signing certificate "iOS Distribution" found`**

자동 서명이 설정되어 있지만 Keychain에 배포 인증서가 없는 경우다. Xcode를 열어 Account 설정에서 인증서를 다운로드하거나, 새로 생성해야 한다.

**오류: `Unable to process request - PLA Update available`**

App Store Connect에서 새 계약 동의가 필요한 상태다. [App Store Connect](https://appstoreconnect.apple.com)에 직접 로그인해서 동의를 완료해야 한다.

**오류: `altool: command not found`**

Xcode Command Line Tools가 설치되지 않은 경우다. `xcode-select --install`로 설치한다.

**오류: 업로드 후 TestFlight에서 빌드가 "Missing Compliance" 상태**

암호화 관련 수출 규정 정보가 누락된 것이다. `Info.plist`에 `ITSAppUsesNonExemptEncryption = false`를 추가하면 해결된다. 암호화를 사용하지 않는 앱이라면 이 값을 `false`로 설정하면 된다.

---

## Key Takeaways

- `IPA_FILE` 변수는 `CFBundleDisplayName` 기준 파일명과 정확히 일치해야 한다. `Runner.ipa`가 아니다.
- `.p8` 키는 `~/.appstoreconnect/private_keys/`에 두면 altool이 자동으로 인식한다.
- `uploadSymbols: true`를 설정해야 Crashlytics 스택 트레이스가 심볼화된다.
- `iCloudContainerEnvironment`는 iCloud 미사용 앱에 넣으면 업로드 실패 원인이 된다.
- Firebase 설정 파일 교체, 패키지 버전 변경, Podfile 수정 후에는 반드시 `flutter clean` + `pod install` 후 빌드해야 한다.
- 빌드 번호 자동 증가는 편리하지만, 빌드 실패 시 번호가 낭비되지 않도록 실행 시점을 신중하게 설계해야 한다.
