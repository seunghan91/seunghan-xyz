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

> ⚠️ `.p8` 파일은 **딱 한 번만 다운로드** 가능하다. 잃어버리면 재발급해야 한다.

화면에 표시된 **Key ID**와 계정의 **Team ID**를 기록해 둔다.

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

**`ios/Runner/Info.plist`**
```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
    <string>fetch</string>
    <string>remote-notification</string>  <!-- 이게 있어야 함 -->
</array>
```

Xcode에서 **Signing & Capabilities → Push Notifications** capability가 추가되어 있으면 entitlements 파일이 자동으로 관리된다.

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

---

## Firebase 테스트 전화번호 활용

실제 SMS를 받지 않고도 테스트하고 싶다면 Firebase Console에서 테스트 번호를 등록할 수 있다.

**Firebase Console → Authentication → Sign-in method → 전화 → 테스트용 전화번호**

| 전화번호 | 인증코드 |
|---------|---------|
| +82 10-1111-1111 | 111111 |

등록된 번호로 인증 요청을 보내면 실제 SMS 없이 지정한 코드로 인증이 통과된다. 개발/스테이징 환경에서 매우 유용하다.

---

## 설정 완료 체크리스트

```
Android
├── [ ] Firebase Console → Authentication → 전화 활성화
├── [ ] SHA-1 지문 등록
├── [ ] SHA-256 지문 등록 (권장)
└── [ ] google-services.json 재다운로드 후 교체

iOS
├── [ ] APNs 인증 키 발급 (Apple Developer)
├── [ ] Firebase Console → 클라우드 메시지에 APNs 키 업로드
├── [ ] Runner.entitlements에 aps-environment 설정
└── [ ] Info.plist에 remote-notification Background Mode 추가

공통
└── [ ] Firebase 테스트 전화번호 등록 (선택)
```

설정 하나라도 빠지면 실기기에서 동작하지 않는다. 체크리스트를 순서대로 확인하는 게 가장 빠른 방법이다.
