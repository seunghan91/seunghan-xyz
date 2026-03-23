---
title: "Flutter TestFlight 빌드 번호 불일치: pubspec.yaml +9인데 TestFlight에서 빌드 11로 표시되는 이유"
date: 2025-08-13
draft: true
tags: ["Flutter", "iOS", "TestFlight", "Xcode", "빌드번호", "CFBundleVersion"]
description: "pubspec.yaml에 +9로 설정했는데 TestFlight에서 빌드 11로 표시되는 이유와, 이후 빌드 번호 관리를 일치시키는 방법을 정리한다."
cover:
  image: "/images/og/flutter-testflight-build-number-mismatch.png"
  alt: "Flutter Testflight Build Number Mismatch"
  hidden: true
---

Flutter iOS 앱을 TestFlight에 업로드했을 때 `pubspec.yaml`에 설정한 빌드 번호와 TestFlight에 표시되는 빌드 번호가 다른 경우가 있다. 예를 들어 `version: 1.0.1+9`로 설정했는데 TestFlight에서는 빌드 11로 표시된다. 처음 마주치면 당황스럽지만, 원인을 이해하고 나면 간단히 대응할 수 있다. 이 글에서는 왜 이런 현상이 발생하는지, 어떻게 디버깅하는지, 그리고 앞으로 빌드 번호를 일관되게 관리하는 방법을 정리한다.

---

## 배경: Flutter의 iOS 빌드 번호 구조

Flutter 프로젝트에서 버전 정보는 `pubspec.yaml`의 `version` 필드 하나로 관리한다.

```yaml
version: 1.0.1+9
```

여기서 `1.0.1`은 마케팅 버전(CFBundleShortVersionString)이고, `+9` 뒤의 숫자가 빌드 번호(CFBundleVersion)다. `flutter build ios` 명령을 실행하면 Flutter 빌드 시스템이 이 값을 읽어서 Xcode 프로젝트의 `Info.plist`에 자동으로 주입한다.

iOS 앱 배포에서 빌드 번호는 App Store Connect가 빌드를 식별하는 핵심 키다. 같은 마케팅 버전(예: 1.0.1) 내에서 빌드 번호는 반드시 이전 업로드보다 커야 한다. 이 규칙을 어기면 업로드 자체가 거부된다.

---

## 왜 빌드 번호가 달라지는가

문제의 핵심은 `-allowProvisioningUpdates` 옵션과 Xcode의 자동 서명(Automatic Signing) 메커니즘이다.

Flutter의 빌드 번호 흐름을 단계별로 보면:

```
pubspec.yaml version: 1.0.1+9
        ↓
flutter build ios --no-codesign
        ↓
CFBundleVersion = 9 (Runner.app)
        ↓
xcodebuild archive -allowProvisioningUpdates
        ↓
Xcode 자동 서명 과정에서 App Store Connect 최신 빌드 번호 조회
        ↓
최신 빌드가 10이면 → CFBundleVersion을 11로 덮어씀
        ↓
TestFlight에는 빌드 11로 업로드됨
```

`xcodebuild`에 `-allowProvisioningUpdates` 옵션을 주면 Xcode가 App Store Connect API를 통해 자동 서명을 처리한다. 이 과정에서 Xcode는 App Store Connect에 이미 업로드된 가장 최신 빌드 번호를 조회한다. 만약 현재 설정된 CFBundleVersion(9)이 이미 업로드된 빌드(10)보다 작거나 같으면, **충돌을 피하기 위해 CFBundleVersion을 자동으로 최신 번호 + 1로 덮어쓴다.**

Apple은 같은 버전(CFBundleShortVersionString) 내에서 빌드 번호가 이전보다 커야 업로드를 허용하기 때문에, Xcode가 안전하게 최신 번호 + 1(즉, 11)로 설정한다. 이 동작은 Xcode의 자동 서명 흐름에 내장되어 있으며, Apple이 서버 측에서 변경하는 것이 아니다.

### 언제 이 문제가 발생하는가

이 불일치는 다음 상황에서 자주 발생한다.

- `pubspec.yaml`의 빌드 번호를 수동으로 관리하다가 App Store Connect의 실제 번호와 동기화가 어긋났을 때
- 빌드를 여러 번 시도했다가 실패한 경우, 일부 빌드는 업로드되지 않았지만 App Store Connect에는 중간 번호가 기록된 경우
- CI/CD 파이프라인에서 자동 증분 스크립트가 pubspec.yaml만 업데이트하고 실제 업로드된 번호를 추적하지 않을 때
- 다른 팀원이 별도로 빌드를 업로드했을 때

---

## 내부 동작 상세: Xcode 자동 서명과 App Store Connect API

Xcode의 자동 서명이 활성화된 상태에서 `xcodebuild archive -allowProvisioningUpdates`를 실행하면 내부적으로 다음 과정이 일어난다.

1. **프로비저닝 프로파일 갱신**: Xcode가 Apple Developer Portal에 접속해서 팀 ID와 번들 ID에 맞는 프로비저닝 프로파일을 자동으로 갱신하거나 생성한다.

2. **App Store Connect 빌드 번호 조회**: 현재 `CFBundleShortVersionString`(예: 1.0.1)에 해당하는 가장 최근 업로드 빌드 번호를 App Store Connect API를 통해 조회한다.

3. **충돌 감지 및 번호 조정**: 현재 `CFBundleVersion`(9)이 최신 업로드 번호(10) 이하이면, `CFBundleVersion`을 `최신 번호 + 1`(11)로 덮어쓴다.

4. **아카이브 생성**: 조정된 번호로 `.xcarchive`를 생성한다.

5. **IPA 내보내기 및 업로드**: `xcrun altool` 또는 `xcodebuild -exportArchive`로 IPA를 만들어 TestFlight에 업로드한다.

이 과정에서 `pubspec.yaml`의 값은 변경되지 않는다. 빌드 아카이브와 업로드된 IPA의 CFBundleVersion만 바뀐다. 그래서 로컬 소스 코드와 TestFlight의 번호가 어긋나게 된다.

---

## 빌드 번호 확인 방법

업로드 후 실제 빌드 번호는 아래 방법으로 확인할 수 있다.

### 1. App Store Connect 활동 내역 확인

App Store Connect → 앱 선택 → TestFlight → 빌드 목록에서 실제 번호 확인

빌드 처리에는 보통 5~15분이 소요된다. 처리가 완료되면 목록에 실제 빌드 번호가 표시된다.

### 2. altool 업로드 로그 확인

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

업로드 성공 로그에서 Delivery UUID를 확인하고, App Store Connect의 활동(Activity) 탭에서 해당 UUID로 빌드를 찾을 수 있다.

### 3. App Store Connect API로 직접 조회

App Store Connect REST API를 사용하면 현재 최신 빌드 번호를 스크립트로 조회할 수 있다.

```bash
# JWT 토큰 생성 후 빌드 목록 조회
curl -H "Authorization: Bearer $JWT_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=$APP_ID&sort=-version&limit=1"
```

이 방법은 CI/CD 파이프라인에서 업로드 전 현재 최신 빌드 번호를 자동으로 파악할 때 유용하다.

### 4. xcrun altool로 빌드 목록 조회

```bash
xcrun altool --list-apps \
  --apiKey $ASC_KEY_ID \
  --apiIssuer $ASC_ISSUER_ID
```

---

## pubspec.yaml 번호 맞추기

TestFlight에서 빌드 11로 올라갔다면 `pubspec.yaml`도 `+11`로 맞춰야 다음 빌드가 정확히 `+12`로 증가한다.

```yaml
# 업로드 후 실제 TestFlight 번호로 맞춤
version: 1.0.1+11
```

### 자동 증분 스크립트

자동 증분 스크립트를 사용하는 경우:

```bash
#!/bin/bash
# increment-build-number.sh
PUBSPEC="$1"
VERSION_NAME=$(grep '^version:' "$PUBSPEC" | sed 's/version: *//;s/+.*//')
BUILD_NUMBER=$(grep '^version:' "$PUBSPEC" | sed 's/.*+//')
NEW_BUILD_NUMBER=$((BUILD_NUMBER + 1))
sed -i '' "s/^version: .*/version: ${VERSION_NAME}+${NEW_BUILD_NUMBER}/" "$PUBSPEC"
echo "Build: ${BUILD_NUMBER} -> ${NEW_BUILD_NUMBER}"
```

스크립트가 +9 → +10으로 올리더라도 Xcode가 또 덮어쓸 수 있으므로, **업로드 후 실제 TestFlight 번호를 확인하고 pubspec.yaml을 그 번호로 수동 동기화**하는 것이 안전하다.

### App Store Connect API 기반 자동 동기화

더 견고한 방법은 업로드 전에 App Store Connect에서 현재 최신 빌드 번호를 조회하고, 그보다 큰 번호를 직접 설정하는 것이다.

```bash
#!/bin/bash
# sync-build-number.sh
# App Store Connect에서 최신 빌드 번호를 조회하고 pubspec.yaml 업데이트

PUBSPEC="pubspec.yaml"
APP_ID="your_app_id"
JWT_TOKEN=$(python3 generate_jwt.py)  # App Store Connect JWT 생성 스크립트

LATEST_BUILD=$(curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=$APP_ID&sort=-version&limit=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['attributes']['version'])")

NEXT_BUILD=$((LATEST_BUILD + 1))
VERSION_NAME=$(grep '^version:' "$PUBSPEC" | sed 's/version: *//;s/+.*//')
sed -i '' "s/^version: .*/version: ${VERSION_NAME}+${NEXT_BUILD}/" "$PUBSPEC"
echo "Set build number to $NEXT_BUILD (latest was $LATEST_BUILD)"
```

---

## 근본 원인 요약 및 예방 팁

### 근본 원인 정리

| 항목 | 값 |
|------|-----|
| pubspec.yaml | `version: 1.0.1+9` |
| Flutter 빌드 후 CFBundleVersion | `9` |
| App Store Connect 최신 빌드 | `10` |
| Xcode 자동 조정 후 CFBundleVersion | `11` |
| TestFlight 표시 빌드 번호 | **11** |

Apple이 빌드 번호를 자동 변경하는 것이 아니라, **`-allowProvisioningUpdates` 옵션과 함께 xcodebuild가 자동 서명하는 과정에서 충돌 방지를 위해 번호를 올린다.**

### 예방 팁

**1. 업로드 후 반드시 번호를 확인하고 동기화한다.**

매 배포 직후 TestFlight의 실제 빌드 번호를 확인하고 `pubspec.yaml`을 해당 번호로 업데이트하는 습관을 들인다. 팀 작업이라면 이 업데이트를 커밋으로 남긴다.

**2. `-allowProvisioningUpdates` 없이 수동 서명한다.**

프로비저닝 프로파일과 인증서를 직접 관리한다면 `-allowProvisioningUpdates` 없이 빌드할 수 있다. 이 경우 Xcode가 App Store Connect를 조회하지 않으므로 번호 덮어쓰기가 발생하지 않는다. 단, 프로비저닝 프로파일 만료 관리를 직접 해야 한다.

**3. CI/CD에서 빌드 번호 소스를 App Store Connect로 통일한다.**

CI/CD 파이프라인이 있다면 빌드 번호의 소스를 `pubspec.yaml`이 아닌 App Store Connect API로 삼는다. 빌드 전에 API로 최신 번호를 조회하고, 그 번호 + 1을 `pubspec.yaml`에 쓴 뒤 빌드한다.

**4. 빌드 번호를 git 태그로 추적한다.**

```bash
git tag "build-11" -m "TestFlight build 11 (1.0.1)"
git push origin "build-11"
```

TestFlight 번호와 git 커밋을 연결해두면 어떤 코드가 어떤 빌드로 배포되었는지 추적하기 쉽다.

---

## Key Takeaways

- Flutter의 `pubspec.yaml` 빌드 번호(`+N`)는 `flutter build ios` 시점에 `CFBundleVersion`으로 주입되지만, `xcodebuild -allowProvisioningUpdates`가 이를 덮어쓸 수 있다.
- 덮어쓰기는 Xcode가 App Store Connect에서 최신 빌드 번호를 조회하고, 현재 번호가 그보다 작거나 같을 때 `최신 번호 + 1`로 자동 조정하기 때문에 발생한다.
- 이는 Apple 서버의 동작이 아니라 Xcode 자동 서명 과정의 로컬 동작이다.
- 해결책은 업로드 후 TestFlight의 실제 번호를 확인하고 `pubspec.yaml`을 그 번호로 수동 동기화하는 것이다.
- 장기적으로는 App Store Connect API를 빌드 번호의 단일 소스로 삼는 CI/CD 구성이 가장 안정적이다.
