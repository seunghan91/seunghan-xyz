---
title: "Flutter 앱 TestFlight 첫 업로드 — 삽질 모음"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "TestFlight", "AppStoreConnect", "Xcode"]
description: "Flutter 앱을 TestFlight에 처음 올리면서 마주친 DEVELOPMENT_TEAM 오류, ASC REST API 제한, 수출 규정 경고, 빌드 번호 중복 문제를 정리한다."
---

Flutter 앱을 TestFlight에 첫 업로드할 때는 의외로 작은 설정 하나 때문에 막히는 경우가 많다. 겪은 삽질을 순서대로 정리했다.

---

## 1. DEVELOPMENT_TEAM 오류

Flutter 프로젝트를 여러 Apple 계정에서 작업하다 보면 `project.pbxproj`의 `DEVELOPMENT_TEAM`이 의도한 팀 ID와 다른 경우가 있다.

```
# 현재 설정 확인
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj
```

App Store 배포용 팀 ID와 다르게 설정되어 있으면 아카이브는 성공해도 업로드 시 사이닝 오류가 난다.

```bash
# 일괄 교체
sed -i '' 's/DEVELOPMENT_TEAM = OLD_TEAM_ID/DEVELOPMENT_TEAM = NEW_TEAM_ID/g' \
  ios/Runner.xcodeproj/project.pbxproj
```

---

## 2. App Store Connect REST API로 앱 생성 불가

ASC REST API로 앱을 생성하려고 하면 **403 FORBIDDEN**이 반환된다.

```json
{
  "status": "403",
  "title": "You do not have access to this resource",
  "detail": "You do not have access to the resource"
}
```

`apps` 리소스는 GET/PATCH만 허용되고, POST(신규 생성)는 API에서 막혀 있다. **앱 생성은 반드시 ASC 웹 포털에서만 가능하다.**

---

## 3. ExportOptions.plist 생성

`flutter build ipa` 는 내부적으로 `xcodebuild -exportArchive`를 호출한다. App Store 배포용 IPA를 만들려면 `ios/ExportOptions.plist`가 필요하다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_TEAM_ID</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

> **주의**: iCloud를 사용하지 않는 앱에 `iCloudContainerEnvironment` 키를 넣으면 업로드 오류가 난다.

---

## 4. 수출 규정 경고 없애기

TestFlight 업로드 후 또는 App Store 심사 시 "이 앱이 암호화를 사용합니까?" 팝업이 뜬다. 앱에서 별도 암호화를 쓰지 않는다면 `Info.plist`에 한 줄을 추가하면 된다.

```xml
<!-- ios/Runner/Info.plist -->
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

이 키가 없으면 Transporter/altool 업로드 후 처리 단계에서 컴플라이언스 확인 요청이 추가된다.

---

## 5. xcrun altool로 업로드

ASC API 키를 사용하면 App Store Connect 로그인 없이 CLI에서 바로 업로드할 수 있다.

```bash
# IPA 빌드
flutter build ipa --release --build-number=1 --build-name=1.0.0

# 업로드
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

성공 시 출력:

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Transferred 27MB in 1.3 seconds
```

---

## 6. 빌드 번호 중복 오류

한 번 업로드한 빌드 번호를 재사용하면 409 오류가 발생한다.

```
Redundant Binary Upload. You've already uploaded a build
with build number '2' for version number '1.0.0'.
```

이전에 같은 번호로 업로드가 시작됐다가 중간에 끊겨도 ASC 서버에 등록된 것으로 처리된다. 빌드 번호를 하나 올려서 재빌드하면 된다.

```bash
flutter build ipa --release --build-number=3 --build-name=1.0.0
```

---

## 요약

| 문제 | 원인 | 해결 |
|------|------|------|
| 사이닝 오류 | `DEVELOPMENT_TEAM` 잘못된 팀 ID | `sed`로 pbxproj 일괄 교체 |
| 앱 생성 API 403 | REST API는 앱 생성 불가 | ASC 웹 포털에서 직접 생성 |
| 수출 규정 경고 | `ITSAppUsesNonExemptEncryption` 누락 | `Info.plist`에 `false` 추가 |
| 빌드 번호 중복 | 이전 업로드 잔류 | `--build-number` 증가 후 재빌드 |
