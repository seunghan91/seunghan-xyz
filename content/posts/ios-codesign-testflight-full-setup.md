---
title: "iOS 배포 인증서 전체 세팅: Distribution Cert → APNs → Provisioning Profile → TestFlight"
date: 2025-06-18
draft: false
tags: ["iOS", "Flutter", "Xcode", "TestFlight", "Provisioning", "배포"]
description: "Distribution 인증서부터 APNs 인증서, Provisioning Profile 생성, xcodebuild API Key 빌드까지 iOS 배포 전체 흐름 정리"
cover:
  image: "/images/og/ios-codesign-testflight-full-setup.png"
  alt: "Ios Codesign Testflight Full Setup"
  hidden: true
---

Flutter 앱을 TestFlight에 올리는 과정에서 코드 서명 관련 설정을 처음부터 다시 잡으면서 정리한 내용이다. Xcode 자동 서명이 아닌 수동 + App Store Connect API Key 방식으로 진행했다.

---

## 전체 흐름

```
[1] Distribution Certificate 발급
[2] APNs Certificate 발급 (CSR 생성 필요)
[3] App ID에 Push Notifications 활성화
[4] Provisioning Profile 생성 (App Store, Push 포함)
[5] xcodebuild archive + export (API Key 인증)
[6] xcrun altool로 TestFlight 업로드
```

---

## 1. Distribution Certificate

Apple Developer → Certificates → + → **Apple Distribution** 선택.

이미 팀에 배포 인증서가 있다면 `.cer` 파일을 다운로드해서 더블클릭하면 Keychain에 설치된다.

설치 확인:

```bash
security find-identity -v -p codesigning | grep "Apple Distribution"
# 3) B5B332... "Apple Distribution: Your Name (TEAMID)"
```

---

## 2. APNs Certificate (Push 알림용)

Push Notifications를 쓰려면 APNs 인증서가 별도로 필요하다. 서버에서 푸시를 보낼 때 사용한다.

### CSR 파일 생성

Keychain Access GUI 대신 터미널로 바로 만드는 게 편하다.

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout ~/Desktop/push.key \
  -out ~/Desktop/push.csr \
  -subj "/emailAddress=your@email.com/CN=App Push/C=KR"
```

### Apple Developer에서 발급

Certificates → + → **Apple Push Notification service SSL (Sandbox & Production)** 선택 → `push.csr` 업로드 → `aps.cer` 다운로드.

이 `.cer` 파일은 **서버 측 푸시 발송**에 사용한다. iOS 앱 빌드에는 직접 사용하지 않는다.

---

## 3. App ID에 Push Notifications 활성화

Identifiers → 해당 App ID → **Push Notifications** 체크 → Save.

이 단계를 먼저 해야 Push Notifications가 포함된 Provisioning Profile을 만들 수 있다. 순서가 바뀌면 프로파일 생성 시 Push 항목이 비활성화 상태로 나온다.

---

## 4. Provisioning Profile 생성

Profiles → + → **Distribution → App Store Connect** → App ID 선택 → Distribution Certificate 선택 → 이름 입력 → Generate → Download.

다운로드한 `.mobileprovision` 파일 설치:

```bash
cp ~/Downloads/myapp.mobileprovision \
  ~/Library/MobileDevice/Provisioning\ Profiles/myapp.mobileprovision
```

더블클릭으로 설치하면 UUID 기반 파일명으로 저장된다. 직접 복사하면 원하는 이름으로 관리할 수 있다.

Push Notifications 포함 여부 확인:

```bash
strings ~/Library/MobileDevice/Provisioning\ Profiles/myapp.mobileprovision \
  | grep "aps-environment"
# <key>aps-environment</key> 가 나오면 Push 포함
```

---

## 5. xcodebuild로 아카이브 + Export

`flutter build ipa` 는 내부적으로 xcodebuild를 호출하는데, Xcode에 Apple 계정이 로그인되어 있지 않으면 Automatic 서명이 Wildcard 프로파일을 선택해버린다. Wildcard는 Push Notifications를 지원하지 않아서 아카이브 단계에서 실패한다.

### App Store Connect API Key 방식

계정 로그인 없이 API Key로 인증하면 `-allowProvisioningUpdates` 플래그와 함께 자동으로 적합한 프로파일을 찾아서 처리한다.

```bash
xcodebuild archive \
  -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -archivePath /tmp/myapp.xcarchive \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_KEYID.p8 \
  -authenticationKeyID KEYID \
  -authenticationKeyIssuerID your-issuer-uuid \
  FLUTTER_BUILD_NUMBER=4 \
  FLUTTER_BUILD_NAME=1.0.0
```

ExportOptions.plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>teamID</key>
    <string>TEAMID</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
```

Export:

```bash
xcodebuild -exportArchive \
  -archivePath /tmp/myapp.xcarchive \
  -exportPath /tmp/myapp_ipa \
  -exportOptionsPlist ios/ExportOptions.plist \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/.appstoreconnect/private_keys/AuthKey_KEYID.p8 \
  -authenticationKeyID KEYID \
  -authenticationKeyIssuerID your-issuer-uuid
```

---

## 6. TestFlight 업로드

API Key 방식:

```bash
xcrun altool --upload-app \
  --type ios \
  -f /tmp/myapp_ipa/app.ipa \
  --apiKey KEYID \
  --apiIssuer your-issuer-uuid
```

성공하면:

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

App Store Connect API를 통해 빌드 상태 확인:

```python
import jwt, time, requests

key = open('AuthKey_KEYID.p8').read()
token = jwt.encode({
    'iss': 'your-issuer-uuid',
    'iat': int(time.time()),
    'exp': int(time.time()) + 1200,
    'aud': 'appstoreconnect-v1'
}, key, algorithm='ES256', headers={'kid': 'KEYID'})

# 앱 ID 조회
r = requests.get(
    'https://api.appstoreconnect.apple.com/v1/apps',
    params={'filter[bundleId]': 'com.example.myapp'},
    headers={'Authorization': f'Bearer {token}'}
)
app_id = r.json()['data'][0]['id']

# 빌드 목록
r = requests.get(
    f'https://api.appstoreconnect.apple.com/v1/builds',
    params={'filter[app]': app_id, 'sort': '-uploadedDate', 'limit': 5},
    headers={'Authorization': f'Bearer {token}'}
)
for b in r.json()['data']:
    attrs = b['attributes']
    print(attrs['version'], attrs['processingState'])
```

`processingState`가 `VALID`이면 TestFlight 배포 준비 완료.

---

## 여러 앱 프로비저닝 프로파일 일괄 관리

앱이 여러 개면 프로파일도 여러 개다. 한 번에 정리하는 스크립트:

```bash
# Push Notifications 포함 여부 일괄 확인
for f in ~/Library/MobileDevice/Provisioning\ Profiles/*.mobileprovision; do
  name=$(basename "$f")
  has_aps=$(strings "$f" 2>/dev/null | grep -c "aps-environment")
  bundle=$(strings "$f" 2>/dev/null | grep "com\." | grep -v "apple\|dtd" | head -1 | tr -d '<>string/')
  [ "$has_aps" -gt 0 ] && mark="✅" || mark="❌"
  echo "$mark $name | $bundle"
done
```

---

## 자주 만나는 오류

### Wildcard 프로파일 + Push 충돌

```
Provisioning profile "iOS Team Provisioning Profile: *"
doesn't include the Push Notifications capability.
```

원인: `Runner.entitlements`에 `aps-environment` 키가 있는데 Wildcard 프로파일 사용 중.

해결: 명시적 App ID 프로파일로 교체하거나, Push가 필요 없으면 entitlements에서 키 제거.

### 빌드 번호 중복

```
ERROR ITMS-90189: "Redundant Binary Upload"
```

업로드 전 `pubspec.yaml`의 `version: 1.0.0+N`에서 빌드 번호(+N)를 올려야 한다.

### No Accounts 경고

```
Error (Xcode): No Accounts: Add a new account in Accounts settings.
```

Xcode에 Apple 계정이 없어도 `-allowProvisioningUpdates` + API Key 방식이면 실제로는 빌드가 진행된다. 경고로 표시되지만 무시해도 된다.

---

## 정리

| 항목 | 용도 |
|---|---|
| `distribution.cer` | 앱 코드 서명 (빌드 시 필요) |
| `aps.cer` | 서버 → 기기 푸시 발송 (서버에 필요) |
| `.mobileprovision` | 앱 ID + 인증서 + 기능 묶음 (빌드 시 필요) |
| API Key `.p8` | App Store Connect 인증 (업로드, 프로비저닝 자동화) |

Xcode 자동 서명은 편리하지만 CI 환경이나 Push 같은 특수 기능이 있으면 수동 프로파일 관리가 더 안정적이다.
