---
title: "Firebase Phone Auth 플랫폼 설정 완전 정복 - Android SHA-1, iOS APNs"
date: 2025-06-29
draft: true
tags: ["Firebase", "Android", "iOS", "APNs", "SHA-1", "Phone Auth"]
description: "Firebase 전화 인증을 실기기에서 동작시키기 위한 Android SHA-1 지문 등록과 iOS APNs 키 설정 전체 과정"
cover:
  image: "/images/og/firebase-android-sha1-ios-apns-complete-setup.png"
  alt: "Firebase Android Sha1 Ios Apns Complete Setup"
  hidden: true
---

Firebase 전화 인증을 붙이고 에뮬레이터에서는 되는데 실기기에서 안 된다면, 대부분 플랫폼별 추가 설정이 빠진 것이다. Android와 iOS 각각 필요한 설정을 정리한다.

---

## 왜 에뮬레이터에서는 되고 실기기에서는 안 될까

Firebase Phone Auth는 플랫폼마다 인증 흐름이 다르다. 에뮬레이터에서는 Firebase가 별도의 보안 검증 없이 테스트 전화번호를 허용한다. 하지만 실기기에서는 두 가지 추가 보안 레이어가 작동한다.

**Android**: Firebase는 Play Integrity API를 통해 앱이 Google Play를 통해 올바르게 서명된 APK인지 검증한다. 이 과정에서 앱 서명 키의 SHA-1 지문이 일치해야 한다. 지문이 Firebase에 등록되지 않으면 Integrity 토큰 발급 자체가 실패하고, 전화번호 인증 요청도 거부된다.

**iOS**: Firebase는 APNs(Apple Push Notification service) silent push를 통해 인증 코드를 전달한다. SMS처럼 보이지만 내부적으로는 푸시 알림 경로를 이용한다. APNs 설정 없이는 코드가 기기까지 도달하지 못한다.

이 두 가지를 이해하면 설정 누락 시 왜 조용히 실패하는지 납득이 된다.

---

## Android: SHA-1 지문 등록

Firebase Phone Auth는 Android에서 **Play Integrity API**를 사용한다. 이 때문에 앱의 서명 키 지문(SHA-1)을 Firebase에 등록해야 한다. 없으면 인증 요청 자체가 실패한다.

### 1. 키스토어에서 SHA-1 추출

```bash
keytool -list -v \
  -keystore android/app/upload-keystore.jks \
  -alias upload \
  -storepass YOUR_STORE_PASSWORD
```

출력 예시:
```
SHA1: 64:60:03:0B:00:6F:E2:29:A4:40:DD:E3:44:3A:7D:32:39:2B:6A:42
SHA256: 24:83:18:41:D6:9A:E5:84:26:71:8E:A2:...
```

key.properties 파일이 있다면 비밀번호를 거기서 확인한다.

#### 디버그 키스토어도 등록해야 하는 경우

개발 중 실기기로 직접 빌드(`flutter run`)하는 경우, 릴리즈 키스토어가 아닌 **디버그 키스토어**로 서명된다. 이때는 디버그 키스토어의 SHA-1도 함께 등록해야 한다.

```bash
# macOS/Linux 기본 디버그 키스토어 경로
keytool -list -v \
  -keystore ~/.android/debug.keystore \
  -alias androiddebugkey \
  -storepass android
```

Firebase Console에는 디버그용 SHA-1과 릴리즈용 SHA-1을 **모두** 등록하는 것이 일반적이다. 그래야 개발 단계에서도 실기기 테스트가 가능하고, 배포 후에도 동작한다.

#### Google Play App Signing 사용 시

Google Play에 앱을 등록할 때 Play App Signing을 사용하면, 실제 기기에 설치된 APK의 서명 키는 **Play가 관리하는 키**다. 이 경우 개발자가 보유한 업로드 키스토어의 SHA-1이 아니라, Play Console에서 확인한 **앱 서명 키 인증서**의 SHA-1을 등록해야 한다.

Play Console → 해당 앱 → 릴리즈 → 앱 서명 → **앱 서명 키 인증서** 섹션에서 SHA-1을 확인한다.

### 2. Firebase Console에 등록

1. Firebase Console → 프로젝트 설정 (톱니바퀴)
2. **내 앱** 섹션 → Android 앱 클릭
3. **디지털 지문 추가** → SHA-1 붙여넣기 → 저장
4. SHA-256도 동일하게 추가 (권장)

### 3. google-services.json 재다운로드

지문 등록 후 `google-services.json`을 **반드시 새로 다운로드**해야 한다.

Firebase Console → Android 앱 → `google-services.json 다운로드`

기존 파일(`android/app/google-services.json`)을 교체하고 앱을 다시 빌드한다.

```bash
flutter clean
flutter pub get
flutter run
```

`flutter clean` 없이 빌드하면 캐시된 이전 설정 파일이 사용될 수 있다. 지문 등록 후에는 반드시 클린 빌드가 권장된다.

---

## iOS: APNs 키 등록

iOS에서 Firebase Phone Auth는 **APNs(Apple Push Notification service)** 를 통해 silent push로 인증 코드를 전달한다. APNs 설정이 없으면 실기기에서 SMS가 아예 오지 않는다.

> 시뮬레이터는 APNs 없이도 Firebase 테스트 번호로 동작한다. 실기기에만 필요하다.

### 1. APNs 인증 키 발급 (Apple Developer Console)

1. [developer.apple.com](https://developer.apple.com/account) 로그인
2. **Certificates, Identifiers & Profiles → Keys**
3. **+** 버튼 클릭
4. **Apple Push Notifications service (APNs)** 체크
5. 이름 입력 후 **Continue → Register**
6. **Download** 클릭 → `.p8` 파일 저장

> APNs 키는 특정 앱이 아닌 **개발자 계정 전체**에 연결된다. 하나의 키로 계정에 속한 모든 앱의 푸시 알림을 처리할 수 있다.

> ⚠️ `.p8` 파일은 **딱 한 번만 다운로드** 가능하다. 잃어버리면 재발급해야 한다.

화면에 표시된 **Key ID**와 계정의 **Team ID**를 기록해 둔다.

#### APNs Certificate vs APNs Key

Apple Developer Console에서 APNs 설정 방식은 두 가지다.

- **APNs Certificate** (구형): `.p12` 형식, 앱별로 발급, 1년마다 갱신 필요
- **APNs Key** (권장): `.p8` 형식, 계정 전체 적용, 만료 없음

Firebase는 두 가지 모두 지원하지만 **APNs Key(.p8)** 방식이 훨씬 간편하다. 갱신 걱정이 없고 하나의 키로 모든 앱을 커버한다.

### 2. Firebase Console에 APNs 키 업로드

1. Firebase Console → 프로젝트 설정
2. **클라우드 메시지** 탭
3. **Apple 앱 구성** 섹션 → iOS 앱 선택
4. **APNs 인증 키** → **업로드**
   - `.p8` 파일 선택
   - Key ID 입력
   - Team ID 입력

### 3. iOS 프로젝트 설정 확인

Flutter 프로젝트 기준으로 아래 두 파일이 올바르게 설정되어 있어야 한다.

**`ios/Runner/Runner.entitlements`**
```xml
<dict>
    <key>aps-environment</key>
    <string>production</string>
</dict>
```

개발 중(`flutter run`)에는 `development`, TestFlight/App Store 배포 시에는 `production`으로 설정한다. 환경이 맞지 않으면 silent push가 도달하지 않는다.

**`ios/Runner/Info.plist`**
```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
    <string>fetch</string>
    <string>remote-notification</string>  <!-- 이게 있어야 함 -->
</array>
```

`remote-notification`이 `UIBackgroundModes`에 포함되어 있어야 앱이 백그라운드 상태일 때도 Firebase의 silent push를 수신할 수 있다.

Xcode에서 **Signing & Capabilities → Push Notifications** capability가 추가되어 있으면 entitlements 파일이 자동으로 관리된다.

### 4. 자주 겪는 iOS 트러블슈팅

**증상**: 전화번호 입력 후 아무 반응 없음 (타임아웃)

원인 후보:
- `aps-environment`가 `development`인데 App Store 빌드를 테스트하는 경우 (또는 반대)
- Firebase Console의 Cloud Messaging 탭에서 APNs 키가 등록되지 않은 경우
- Push Notifications capability 미추가

**증상**: 시뮬레이터에서는 되는데 TestFlight 빌드에서 안 됨

원인:
- `aps-environment`가 `development`로 설정된 채 배포된 경우
- TestFlight와 App Store 빌드는 `production` APNs 채널을 사용한다

**증상**: 코드 입력 화면이 뜨지 않고 reCAPTCHA 웹뷰가 뜸

Firebase가 APNs silent push를 수신하지 못하면 자동으로 reCAPTCHA 방식으로 폴백한다. APNs 설정이 누락된 경우 이 증상이 나타난다.

---

## 키 파일 관리

APNs `.p8` 파일은 보안 민감 정보다. 프로젝트 내에 보관한다면 반드시 `.gitignore`에 추가한다.

```bash
# .gitignore
ios/secrets/
*.p8
.env
```

`.env` 파일에 키 정보를 기록해 두면 팀 내에서 공유하기 편하다.

```bash
# .env
APNS_KEY_ID=XXXXXXXXXX
APNS_KEY_PATH=ios/secrets/AuthKey_XXXXXXXXXX.p8
APPLE_TEAM_ID=XXXXXXXXXX
```

여러 프로젝트를 관리하는 경우, 키 파일을 프로젝트 외부의 안전한 위치(예: `~/.secrets/`)에 저장하고 경로만 `.env`에 기록하는 방법도 있다.

---

## Firebase 테스트 전화번호 활용

실제 SMS를 받지 않고도 테스트하고 싶다면 Firebase Console에서 테스트 번호를 등록할 수 있다.

**Firebase Console → Authentication → Sign-in method → 전화 → 테스트용 전화번호**

| 전화번호 | 인증코드 |
|---------|---------|
| +82 10-1111-1111 | 111111 |

등록된 번호로 인증 요청을 보내면 실제 SMS 없이 지정한 코드로 인증이 통과된다. 개발/스테이징 환경에서 매우 유용하다.

테스트 번호는 **APNs나 SHA-1 없이도 동작**한다는 점이 중요하다. 에뮬레이터에서 테스트 번호로 성공했다고 실기기에서도 동작한다고 가정하면 안 된다. 반드시 실기기에서 **실제 번호**로 전체 플로우를 검증해야 한다.

---

## 설정 완료 체크리스트

```
Android
├── [ ] Firebase Console → Authentication → 전화 활성화
├── [ ] 릴리즈 키스토어 SHA-1 등록
├── [ ] 디버그 키스토어 SHA-1 등록 (개발용 실기기 테스트)
├── [ ] Play App Signing 사용 시 Play Console에서 서명 키 SHA-1 확인
├── [ ] SHA-256 지문 등록 (권장)
└── [ ] google-services.json 재다운로드 후 교체 + flutter clean

iOS
├── [ ] APNs 인증 키 발급 (Apple Developer) - .p8 + Key ID + Team ID
├── [ ] Firebase Console → 클라우드 메시지에 APNs 키 업로드
├── [ ] Runner.entitlements에 aps-environment 설정 (dev/prod 환경 구분)
├── [ ] Info.plist에 remote-notification Background Mode 추가
└── [ ] Xcode Push Notifications capability 추가

공통
└── [ ] Firebase 테스트 전화번호 등록 (선택)
```

---

## Key Takeaways

- **에뮬레이터 성공 = 실기기 성공이 아니다.** 에뮬레이터는 보안 검증을 우회한다. 실기기에서는 SHA-1(Android)과 APNs(iOS) 두 가지가 반드시 필요하다.
- **google-services.json은 SHA-1 등록 후 반드시 새로 받아야 한다.** 파일 안에 지문 정보가 포함되기 때문이다. 파일 교체 후 `flutter clean`도 잊지 않는다.
- **iOS reCAPTCHA 폴백은 APNs 누락 신호다.** 인증 화면 대신 웹뷰 캡차가 뜬다면 APNs 설정을 먼저 점검한다.
- **APNs Key(.p8)는 계정 전체에 적용된다.** 앱마다 따로 발급할 필요 없고, 갱신 기간도 없다. Certificate(.p12) 방식보다 훨씬 관리가 편하다.
- **Google Play App Signing을 사용하면 SHA-1 출처가 달라진다.** 업로드 키스토어가 아닌 Play Console의 앱 서명 키 SHA-1을 등록해야 한다. 배포 후 갑자기 안 된다면 이 케이스를 먼저 의심한다.
