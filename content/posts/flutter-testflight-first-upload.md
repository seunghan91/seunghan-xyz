---
title: "Flutter 앱 TestFlight 첫 업로드 — 삽질 모음"
date: 2026-03-09
draft: true
tags: ["Flutter", "iOS", "TestFlight", "AppStoreConnect", "Xcode"]
description: "Flutter 앱을 TestFlight에 처음 올리면서 마주친 DEVELOPMENT_TEAM 오류, ASC REST API 제한, 수출 규정 경고, 빌드 번호 중복 문제를 정리한다."
---

Flutter 앱을 TestFlight에 첫 업로드할 때는 의외로 작은 설정 하나 때문에 막히는 경우가 많다. Xcode GUI 없이 CLI만으로 진행하거나, 여러 Apple 계정을 동시에 관리하는 경우에는 더욱 그렇다. 겪은 삽질을 순서대로 정리했다.

---

## 1. DEVELOPMENT_TEAM 오류

### 문제

Flutter 프로젝트를 여러 Apple 계정에서 작업하다 보면 `project.pbxproj`의 `DEVELOPMENT_TEAM`이 의도한 팀 ID와 다른 경우가 있다. 특히 다른 앱의 ios 디렉토리를 복사해서 시작했거나, Xcode에서 다른 계정으로 한 번이라도 열었다면 자동으로 덮어쓰여 있을 수 있다.

```bash
# 현재 설정 확인
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj
```

App Store 배포용 팀 ID와 다르게 설정되어 있으면 아카이브는 성공해도 업로드 시 다음과 같은 사이닝 오류가 난다.

```
error: exportArchive: No signing certificate "iOS Distribution" found
```

또는 업로드 단계에서 아래 메시지가 나타난다.

```
The bundle identifier "com.example.app" is not registered for the selected team.
```

### 원인

`project.pbxproj`에는 `DEVELOPMENT_TEAM` 항목이 여러 곳(Debug/Release 각 설정별)에 분산되어 있다. Xcode가 자동으로 설정하는 과정에서 여러 팀 ID가 섞이는 경우가 생긴다.

### 해결

```bash
# 일괄 교체
sed -i '' 's/DEVELOPMENT_TEAM = OLD_TEAM_ID/DEVELOPMENT_TEAM = NEW_TEAM_ID/g' \
  ios/Runner.xcodeproj/project.pbxproj

# 교체 결과 확인
grep "DEVELOPMENT_TEAM" ios/Runner.xcodeproj/project.pbxproj
```

교체 후 `flutter clean && flutter build ipa` 로 다시 빌드한다. 빈 문자열(`DEVELOPMENT_TEAM = ""`)이 섞여 있다면 해당 라인도 함께 교체해야 한다.

### 예방

`ios/` 디렉토리를 버전 관리하는 경우 `project.pbxproj`를 커밋할 때 `DEVELOPMENT_TEAM` 값을 확인하는 습관을 들이는 것이 좋다. CI 환경에서는 빌드 스크립트에서 `sed`로 교체하는 단계를 명시적으로 추가해 두면 실수를 방지할 수 있다.

---

## 2. App Store Connect REST API로 앱 생성 불가

### 문제

스크립트로 자동화하려고 ASC REST API를 통해 앱을 생성하면 **403 FORBIDDEN**이 반환된다.

```json
{
  "status": "403",
  "title": "You do not have access to this resource",
  "detail": "You do not have access to the resource"
}
```

역할을 Admin으로 설정하고 API 키를 발급받아도 동일하다.

### 원인

`apps` 리소스는 GET(목록/상세 조회)과 PATCH(수정)만 허용되고, POST(신규 생성)는 API 스펙 자체에서 막혀 있다. Apple 공식 문서에도 "You cannot create an app using the API" 라고 명시되어 있다. 이는 앱 생성 시 개발자 계약 동의 확인, 번들 ID 등록, 콘텐츠 권한 설정 등 법적·정책적 절차가 포함되기 때문으로 보인다.

### 해결

**앱 생성은 반드시 ASC 웹 포털에서만 가능하다.**

1. [App Store Connect](https://appstoreconnect.apple.com) 접속
2. My Apps → + 버튼 → New App
3. Bundle ID, 앱 이름, SKU 입력 후 생성
4. 이후 메타데이터 수정, 빌드 연결 등은 API로 자동화 가능

Bundle ID는 [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list) 에서 미리 등록해 두거나, ASC 포털에서 앱 생성 시 함께 생성할 수 있다.

### 예방

신규 앱 출시 워크플로우에서 "ASC 포털에서 앱 수동 생성" 단계를 명시적으로 문서화해 두면 자동화 스크립트 작성 시 빠뜨리지 않는다.

---

## 3. ExportOptions.plist 생성

### 문제

`flutter build ipa`를 실행하면 내부적으로 `xcodebuild -exportArchive`가 호출된다. 이 단계에서 익스포트 옵션 파일이 없거나 잘못 설정되어 있으면 빌드는 성공해도 IPA 생성에 실패하거나, 잘못된 배포 방식으로 패키징된다.

### 원인

`xcodebuild -exportArchive`는 `-exportOptionsPlist` 파라미터로 배포 방법, 팀 ID, 코드 서명 방식 등을 받는다. Flutter는 `ios/ExportOptions.plist`가 있으면 자동으로 이 파일을 사용한다.

### 해결

`ios/ExportOptions.plist`를 아래 내용으로 생성한다.

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
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

각 키의 의미:

| 키 | 설명 |
|----|------|
| `method` | `app-store`(배포용), `development`(개발용), `ad-hoc` 중 선택 |
| `teamID` | Apple Developer 팀 ID (10자리 영숫자) |
| `uploadBitcode` | Bitcode는 Xcode 14부터 deprecated. `false`로 설정 |
| `uploadSymbols` | 크래시 리포트를 위해 `true` 권장 |
| `signingStyle` | `automatic`(Xcode 자동 관리) 또는 `manual` |

> **주의**: iCloud를 사용하지 않는 앱에 `iCloudContainerEnvironment` 키를 넣으면 다음과 같은 업로드 오류가 난다.
>
> ```
> The value for key 'iCloudContainerEnvironment' in your ExportOptions.plist is not valid.
> ```

### 예방

이 파일은 팀마다, 앱마다 다를 수 있으므로 `ios/ExportOptions.plist`를 Git에 포함시키되, `teamID` 값이 올바른지 주기적으로 확인한다.

---

## 4. 수출 규정 경고 없애기

### 문제

TestFlight 업로드 후 또는 App Store 심사 시 "이 앱이 암호화를 사용합니까?" 컴플라이언스 확인 팝업이 나타나거나, altool 업로드 후 처리 단계에서 경고 메일이 온다.

```
ITMS-90725: SDK Encryption Usage — Your app uses encryption, but does not have the
required export compliance documentation.
```

### 원인

Apple은 미국 수출 규정(EAR)에 따라 암호화 기술을 사용하는 앱의 출처를 추적해야 한다. HTTPS 통신(TLS)도 암호화로 간주된다. `ITSAppUsesNonExemptEncryption` 키가 없으면 매번 수동으로 컴플라이언스를 확인해야 한다.

### 해결

`ios/Runner/Info.plist`에 아래 키를 추가한다.

```xml
<!-- ios/Runner/Info.plist -->
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

이 키를 `false`로 설정하면 "앱이 면제 암호화만 사용하거나 암호화를 전혀 사용하지 않는다"고 선언하는 것이다. HTTPS만 사용하는 일반적인 앱이라면 이것으로 충분하다.

만약 직접 구현한 암호화 알고리즘이나 VPN, 보안 통신 프로토콜이 포함된다면 `true`로 설정하고 별도의 ERN(Encryption Registration Number) 문서를 제출해야 한다.

### 예방

앱 프로젝트 생성 초기에 `Info.plist`에 이 키를 추가하는 것을 체크리스트에 넣어 두면 나중에 깜빡하지 않는다.

---

## 5. xcrun altool로 업로드

### 배경

App Store Connect에 직접 로그인하지 않고 CLI에서 업로드하는 방법은 크게 두 가지다.

- `xcrun altool`: 구형 방식이지만 여전히 동작하며, Apple ID 기반 또는 API 키 기반 인증 모두 지원
- `xcrun notarytool` + `xcrun stapler`: macOS 앱용 공증 도구 (iOS IPA에는 불필요)

API 키 방식을 사용하면 2FA 없이 CI/CD 파이프라인에서 자동화할 수 있다.

### ASC API 키 발급

1. App Store Connect → Users and Access → Keys 탭
2. + 버튼으로 새 키 생성 (Role: Admin 또는 App Manager)
3. `.p8` 파일 다운로드 (한 번만 가능, 분실 시 재발급 불가)
4. Key ID와 Issuer ID를 메모해 둔다

### 업로드 명령

```bash
# IPA 빌드
flutter build ipa --release --build-number=1 --build-name=1.0.0

# 업로드
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/*.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_ID
```

`.p8` 파일은 `~/.appstoreconnect/private_keys/AuthKey_YOUR_KEY_ID.p8` 경로에 있어야 한다. 다른 경로에 있다면 `--apiKey` 대신 `--apiKeyPath`로 직접 경로를 지정할 수 있다.

성공 시 출력:

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Transferred 27MB in 1.3 seconds
```

### 업로드 후 처리 시간

업로드가 성공해도 TestFlight에 빌드가 나타나기까지 보통 5~15분이 걸린다. ASC가 내부적으로 바이너리를 처리하고 암호화 컴플라이언스 등을 검사하는 시간이다. 처리 완료 시 등록된 이메일로 알림이 온다.

---

## 6. 빌드 번호 중복 오류

### 문제

한 번 업로드한 빌드 번호를 재사용하면 409 오류가 발생한다.

```
Redundant Binary Upload. You've already uploaded a build
with build number '2' for version number '1.0.0'.
```

### 원인

ASC는 `(버전 번호, 빌드 번호)` 쌍을 유일 키로 관리한다. 업로드가 중간에 끊겨도, 또는 업로드 직후 바로 삭제해도 해당 쌍은 ASC 서버에 이미 등록된 것으로 처리된다. 네트워크 오류로 업로드가 실패했다고 생각하고 같은 번호로 재시도하면 이 오류에 걸린다.

### 해결

빌드 번호를 하나 올려서 재빌드한다.

```bash
flutter build ipa --release --build-number=3 --build-name=1.0.0
```

현재 ASC에 어떤 빌드 번호까지 등록되어 있는지 확인하려면 ASC 포털의 TestFlight 탭에서 빌드 목록을 확인하거나, ASC REST API로 조회할 수 있다.

```bash
# ASC REST API로 최근 빌드 목록 조회 (jq 필요)
curl -s -H "Authorization: Bearer $ASC_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=APP_ID&sort=-uploadedDate&limit=5" \
  | jq '.data[].attributes | {version, buildAudienceType, uploadedDate}'
```

### 예방

빌드 번호를 `YYYYMMDDHHII` 형식의 타임스탬프로 자동 생성하면 중복 걱정 없이 관리할 수 있다.

```bash
BUILD_NUMBER=$(date +%Y%m%d%H%M)
flutter build ipa --release --build-number=$BUILD_NUMBER --build-name=1.0.0
```

---

## 요약

| 문제 | 원인 | 해결 |
|------|------|------|
| 사이닝 오류 | `DEVELOPMENT_TEAM` 잘못된 팀 ID | `sed`로 pbxproj 일괄 교체 |
| 앱 생성 API 403 | REST API는 앱 생성 불가 | ASC 웹 포털에서 직접 생성 |
| ExportOptions 누락 | IPA 익스포트 설정 파일 없음 | `ios/ExportOptions.plist` 생성 |
| 수출 규정 경고 | `ITSAppUsesNonExemptEncryption` 누락 | `Info.plist`에 `false` 추가 |
| 빌드 번호 중복 | 이전 업로드 잔류 | `--build-number` 증가 후 재빌드 |

---

## Key Takeaways

- **`DEVELOPMENT_TEAM`은 여러 곳에 분산되어 있다.** `grep`으로 전체를 확인하고, `sed`로 일괄 교체한 뒤 반드시 결과를 재확인한다.
- **앱 생성은 API로 불가능하다.** ASC REST API는 기존 앱 관리에만 사용할 수 있다. 신규 앱은 반드시 웹 포털에서 직접 생성해야 한다.
- **`ExportOptions.plist`의 `iCloudContainerEnvironment` 키는 iCloud를 사용하지 않는 앱에 넣지 않는다.** 불필요한 키 하나로 전체 업로드가 실패한다.
- **`ITSAppUsesNonExemptEncryption = false`는 프로젝트 생성 초기에 설정한다.** 나중에 TestFlight에서 처음 발견하면 재업로드가 필요해진다.
- **빌드 번호는 타임스탬프 기반으로 자동화한다.** 중단된 업로드도 ASC에 등록되므로, 수동으로 번호를 관리하면 반드시 충돌이 생긴다.
- **업로드 성공과 TestFlight 배포 준비는 다르다.** 업로드 후 5~15분의 처리 시간이 있으며, 이메일 알림으로 완료를 확인해야 한다.
