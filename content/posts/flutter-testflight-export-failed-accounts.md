---
title: "Flutter TestFlight 업로드 삽질 — exportArchive Failed to Use Accounts 해결"
date: 2026-03-31
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "CI/CD"]
description: "flutter build ipa에서 exportArchive Failed to Use Accounts 에러가 날 때 해결법. altool 빌드번호 충돌, ExportOptions.plist 설정, API Key 인증까지 실전 삽질 기록."
---

Flutter로 앱을 만들고 TestFlight에 올리려는데, 아카이브 빌드는 성공하고 IPA export에서 멈췄다. `exportArchive Failed to Use Accounts`라는 에러가 뜨는데, 구글링해도 명쾌한 답이 없었다. 결국 3가지 다른 에러를 연달아 만나면서 해결했고, 그 과정을 정리한다.

---

## 에러 1: exportArchive Failed to Use Accounts

```bash
flutter build ipa --release --dart-define=ENV=prod --export-options-plist=ios/ExportOptions.plist
```

아카이브 빌드는 잘 된다:

```
✓ Built build/ios/archive/Runner.xcarchive (197.5MB)

[✓] App Settings Validation
    • Version Number: 1.0.1
    • Build Number: 9
    • Display Name: My App
    • Bundle Identifier: com.example.app
```

근데 바로 다음 줄에서:

```
Building App Store IPA...
Encountered error while creating the IPA:
error: exportArchive Failed to Use Accounts
```

### 원인

`flutter build ipa`는 내부적으로 `xcodebuild -exportArchive`를 호출한다. 이때 Xcode에 등록된 Apple 계정 정보를 사용하는데, **CLI 환경에서는 계정 인증이 제대로 안 되는 경우**가 있다. 특히 API Key 인증을 쓰는 CI/CD 환경에서 자주 발생한다.

Xcode GUI에서 로그인해놓으면 되는 경우도 있지만, 자동화 파이프라인에서는 그게 불가능하다.

### 해결: xcodebuild에 API Key를 직접 전달

`flutter build ipa` 대신, 2단계로 나눠서 실행한다.

**Step 1**: 아카이브만 빌드 (flutter가 처리)

```bash
flutter build ipa --release --dart-define=ENV=prod
# IPA export는 실패해도 아카이브는 build/ios/archive/Runner.xcarchive에 남아있다
```

**Step 2**: xcodebuild로 직접 export (API Key 전달)

```bash
xcodebuild -exportArchive \
  -archivePath build/ios/archive/Runner.xcarchive \
  -exportPath build/ios/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath /path/to/AuthKey_XXXXXX.p8 \
  -authenticationKeyID XXXXXX \
  -authenticationKeyIssuerID xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

이렇게 하면 Xcode 계정 없이도 API Key로 인증이 된다.

---

## ExportOptions.plist 설정

이 파일이 없거나 잘못 설정되어 있으면 export가 실패한다. TestFlight(App Store) 업로드용 최소 설정:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>uploadSymbols</key>
    <true/>
    <key>compileBitcode</key>
    <false/>
    <key>destination</key>
    <string>upload</string>
</dict>
</plist>
```

`method`가 `app-store`면 `destination: upload`를 함께 넣으면 export와 동시에 App Store Connect로 업로드까지 해준다. 이걸 모르고 export 후에 `altool`로 따로 업로드하면 2번 일하는 거다.

---

## 에러 2: Redundant Binary Upload

export가 성공하고 업로드까지 갔는데 이번엔 이 에러:

```
Redundant Binary Upload. You've already uploaded a build with
build number '9' for version number '1.0.1'.
```

같은 버전+빌드번호 조합으로 이미 올라가 있다는 뜻이다. `pubspec.yaml`에서 빌드번호를 올려야 한다.

```yaml
# 수정 전
version: 1.0.1+9

# 수정 후
version: 1.0.2+10
```

`+` 뒤의 숫자가 CFBundleVersion(빌드번호)이 된다. App Store Connect에서 이미 올라간 번호보다 **반드시 높아야** 한다.

### 함정: 몇 번까지 올라가 있는지 모른다

문제는 여러 번 시도하다 보면 App Store Connect에 이미 올라간 빌드번호를 추적하기 어렵다는 거다. 실제로 10으로 올렸는데 이런 에러가 났다:

```
The bundle version must be higher than the previously uploaded version: '11'.
```

11까지 이미 올라가 있었다. 이전에 xcodebuild의 `destination: upload` 옵션으로 export 시 자동 업로드된 것이었다. 12로 올리니 통과했다.

**교훈**: App Store Connect > 앱 > Activity에서 현재 최신 빌드번호를 확인하고, 그보다 높은 번호를 쓰자.

---

## 에러 3: altool deprecated (2025+)

```bash
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/MyApp.ipa \
  --apiKey XXXXXX \
  --apiIssuer xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

이 방법은 아직 동작하지만, Apple은 `altool`을 **deprecated**로 표시하고 `transporter`를 권장하고 있다. 2026년 현재 둘 다 작동하지만, 새 프로젝트라면 `transporter`를 쓰는 게 안전하다.

```bash
xcrun transporter -m upload \
  -f build/ios/ipa/MyApp.ipa \
  --apiKey XXXXXX \
  --apiIssuer xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## flutter build ipa vs xcodebuild 비교

| 항목 | `flutter build ipa` | `xcodebuild` 수동 |
|------|--------------------|--------------------|
| 명령어 수 | 1개 | 2개 (archive + export) |
| 계정 인증 | Xcode GUI 계정 필요 | API Key 직접 전달 가능 |
| 유연성 | 낮음 | 높음 (스킴, 설정 자유) |
| CI/CD 적합성 | 에러 발생 가능 | 안정적 |
| IPA 경로 | `build/ios/ipa/*.ipa` | `exportPath`에 지정 |

결론: 로컬 개발에서는 `flutter build ipa`가 편하고, CI/CD나 자동화에서는 `xcodebuild` 수동 조합이 더 안정적이다.

---

## 실전 워크플로우: Flutter TestFlight 업로드

최종적으로 안정적으로 동작한 플로우:

```bash
# 1. 빌드번호 확인/수정
# pubspec.yaml의 version: X.Y.Z+BUILD_NUMBER

# 2. IPA 빌드 (export 실패해도 아카이브는 남음)
flutter build ipa --release --dart-define=ENV=prod

# 3. 성공하면 바로 업로드
xcrun altool --upload-app --type ios \
  -f "build/ios/ipa/My App.ipa" \
  --apiKey YOUR_API_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID

# 3-alt. flutter build ipa가 실패하면 수동 export
xcodebuild -exportArchive \
  -archivePath build/ios/archive/Runner.xcarchive \
  -exportPath build/ios/ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_XXXX.p8 \
  -authenticationKeyID XXXX \
  -authenticationKeyIssuerID xxxx-xxxx-xxxx
```

### Makefile로 자동화

```makefile
ASC_API_KEY = YOUR_KEY_ID
ASC_ISSUER  = YOUR_ISSUER_ID

flutter-testflight:
	cd flutter && flutter build ipa --release --dart-define=ENV=prod
	xcrun altool --upload-app --type ios \
		-f "flutter/build/ios/ipa/*.ipa" \
		--apiKey $(ASC_API_KEY) \
		--apiIssuer $(ASC_ISSUER)
```

---

## 주의사항 정리

| 함정 | 증상 | 해결 |
|------|------|------|
| Xcode 계정 미등록 | `Failed to Use Accounts` | API Key로 직접 인증 |
| 빌드번호 중복 | `Redundant Binary Upload` | App Store Connect에서 최신 번호 확인 후 +1 |
| 빌드번호 미증가 | `must be higher than '11'` | `pubspec.yaml` version 수정 후 재빌드 |
| ExportOptions 누락 | export 단계에서 실패 | `method: app-store` + `teamID` 필수 |
| altool deprecated | 경고 메시지 | `transporter`로 전환 검토 |
| 아카이브 캐시 | 이전 빌드번호로 export | `rm -rf build/ios/` 후 재빌드 |

---

## 결론

`flutter build ipa`가 한 번에 되면 좋겠지만, 실제로는 계정 인증, 빌드번호, ExportOptions 설정에서 에러가 나는 경우가 많다. 핵심은:

1. **아카이브와 export를 분리**해서 생각하기 — 아카이브가 성공했으면 xcodebuild로 직접 export
2. **빌드번호는 항상 최신보다 높게** — App Store Connect Activity 탭 확인
3. **API Key 인증을 사용** — Xcode GUI 계정에 의존하지 않기

이 3가지만 기억하면 TestFlight 업로드에서 삽질하는 시간을 크게 줄일 수 있다.
