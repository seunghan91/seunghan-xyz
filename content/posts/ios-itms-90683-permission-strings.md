---
title: "App Store Connect ITMS-90683: Info.plist 권한 purpose string 누락 오류 해결"
date: 2025-08-27
draft: true
tags: ["Flutter", "iOS", "App Store Connect", "TestFlight", "Info.plist", "권한"]
description: "TestFlight 업로드 후 ITMS-90683 오류 메일이 오는 경우 해결 방법. NSPhotoLibraryUsageDescription, NSCameraUsageDescription 등 권한 설명 문자열 누락 시 처리."
cover:
  image: "/images/og/ios-itms-90683-permission-strings.png"
  alt: "Ios Itms 90683 Permission Strings"
  hidden: true
---

TestFlight에 IPA를 업로드하고 몇 분 후 App Store Connect에서 메일이 온다.

```
ITMS-90683: Missing purpose string in Info.plist
The app's Info.plist file is missing a required purpose string for
one or more of the following API categories: NSPhotoLibraryUsageDescription
```

업로드 자체는 성공했지만 Apple이 배포 전 자동으로 바이너리를 검사하고 이 메일을 보낸다. 수정하지 않으면 App Store 심사 제출 시 경고가 아닌 거절로 이어진다. 이 글에서는 오류가 왜 발생하는지, 어떻게 올바르게 수정하는지, 그리고 수정 후에도 심사에서 걸리는 흔한 실수를 피하는 방법을 다룬다.

---

## 왜 이 오류가 발생하는가

iOS는 카메라, 사진 라이브러리, 마이크, 위치 등 민감한 API에 접근할 때 사용자에게 권한 팝업을 보여준다. 이 팝업에 표시되는 설명 문구가 `Info.plist`에 없으면 Apple의 자동화 도구가 오류로 처리한다.

App Store Connect에 IPA를 업로드하면 Apple의 바이너리 분석 파이프라인이 즉시 동작한다. 이 파이프라인은 Mach-O 바이너리에 링크된 프레임워크를 분석하고 보호된 API 사용 여부를 감지한다. 코드에서 해당 API를 직접 호출하지 않아도 **의존 패키지가 해당 프레임워크를 링크하면** 오류가 발생한다.

Flutter 앱에서 이 오류가 특히 자주 나타나는 이유가 바로 여기에 있다. `image_picker`, `file_picker`, `photo_view`, `camera`, `geolocator`, `local_auth` 같은 패키지들은 내부적으로 iOS 네이티브 프레임워크를 사용한다. 예를 들어 `file_picker`로 PDF만 첨부하는 기능을 만들어도 패키지 네이티브 코드가 `PHPhotoLibrary`를 참조하기 때문에 `NSPhotoLibraryUsageDescription`이 반드시 필요하다.

---

## Apple이 위반을 감지하는 방식

업로드된 IPA는 다음 단계를 거쳐 검사된다.

1. Mach-O 바이너리 분해 후 링크된 프레임워크 목록 추출
2. 사진, 카메라, CoreLocation, Contacts 등 보호 API 사용 여부 감지
3. IPA 번들 내 `Info.plist` 항목과 교차 검증
4. 누락된 purpose string마다 자동 메일 발송

메일은 보통 업로드 후 5~10분 내에 도착한다. 빌드 자체는 TestFlight에 등록되지만 경고 상태로 표시되며, 모든 위반을 해결하기 전까지 App Store 제출로 넘길 수 없다.

---

## 수정: Info.plist에 purpose string 추가

`ios/Runner/Info.plist`에 해당 키와 설명 문자열을 추가한다. 문자열 값은 사용자가 읽을 수 있는 구체적인 설명이어야 한다. "앱 기능에 필요합니다" 같은 모호한 문구는 심사에서 Apple 가이드라인 5.1.1 위반으로 거절될 수 있다.

```xml
<!-- ios/Runner/Info.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <!-- 기존 설정들 ... -->

    <!-- 사진 라이브러리 읽기 권한 -->
    <key>NSPhotoLibraryUsageDescription</key>
    <string>서류 제출 및 프로필 사진 업로드를 위해 사진 라이브러리에 접근합니다.</string>

    <!-- 사진 라이브러리 저장 권한 (다운로드 기능이 있을 때) -->
    <key>NSPhotoLibraryAddUsageDescription</key>
    <string>다운로드한 파일을 사진 라이브러리에 저장하기 위해 접근합니다.</string>

    <!-- 카메라 권한 -->
    <key>NSCameraUsageDescription</key>
    <string>사진 촬영 및 문서 스캔을 위해 카메라에 접근합니다.</string>

    <!-- 마이크 권한 -->
    <key>NSMicrophoneUsageDescription</key>
    <string>음성 메시지 녹음을 위해 마이크에 접근합니다.</string>

</dict>
</plist>
```

권한 설명은 실제 기능과 연결된 구체적인 문구로 작성한다. 심사관은 이 문구를 직접 확인하고, 앱에 해당 기능이 없거나 설명이 너무 막연하면 거절 사유가 된다.

---

## 자주 나오는 purpose string 전체 목록

| 키 | 보호 대상 | 주로 트리거되는 패키지 |
|----|----------|----------------------|
| `NSPhotoLibraryUsageDescription` | 사진 라이브러리 (읽기) | image_picker, file_picker, photo_view |
| `NSPhotoLibraryAddUsageDescription` | 사진 라이브러리 (저장) | image_gallery_saver, share_plus |
| `NSCameraUsageDescription` | 카메라 | image_picker, camera, qr_code_scanner |
| `NSMicrophoneUsageDescription` | 마이크 | audio_recorder, record, 동영상 촬영 |
| `NSLocationWhenInUseUsageDescription` | 위치 (앱 사용 중) | geolocator, google_maps, mapbox |
| `NSLocationAlwaysAndWhenInUseUsageDescription` | 위치 (백그라운드) | background_geolocation |
| `NSLocationAlwaysUsageDescription` | 위치 (구버전 백그라운드) | 이전 버전 geolocator |
| `NSContactsUsageDescription` | 연락처 | contacts_service, flutter_contacts |
| `NSCalendarsUsageDescription` | 캘린더 | add_2_calendar, device_calendar |
| `NSFaceIDUsageDescription` | Face ID / 생체인증 | local_auth |
| `NSBluetoothAlwaysUsageDescription` | 블루투스 | flutter_blue, flutter_reactive_ble |
| `NSBluetoothPeripheralUsageDescription` | 블루투스 peripheral | flutter_blue 구버전 (iOS 12) |
| `NSMotionUsageDescription` | 동작/가속도계 | sensors_plus |
| `NSHealthShareUsageDescription` | HealthKit (읽기) | health |
| `NSHealthUpdateUsageDescription` | HealthKit (쓰기) | health |
| `NSSpeechRecognitionUsageDescription` | 음성 인식 | speech_to_text |
| `NSRemindersUsageDescription` | 미리 알림 | flutter_local_notifications (일부 설정) |

---

## 어떤 권한이 필요한지 확인하는 방법

### 방법 1: 패키지 문서 확인

가장 빠른 방법이다. pub.dev에서 각 패키지의 README나 "iOS Setup" 섹션을 확인하면 필요한 `Info.plist` 키가 명시되어 있다. 잘 관리되는 패키지는 대부분 이 정보를 제공한다.

### 방법 2: Xcode 빌드 로그 검색

빌드 후 출력에서 권한 관련 경고를 검색한다.

```bash
# Xcode 빌드 로그에서 권한 관련 경고 검색
xcodebuild -workspace ios/Runner.xcworkspace \
  -scheme Runner \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  build 2>&1 | grep -i "usage description"
```

### 방법 3: 현재 Info.plist 키 확인

이미 선언된 키 목록을 확인해 누락된 항목을 파악한다.

```bash
# 현재 Info.plist에 있는 권한 키 확인
/usr/libexec/PlistBuddy -c "Print" ios/Runner/Info.plist | grep "UsageDescription"
```

### 방법 4: IPA 내 링크 프레임워크 직접 감사

더 정밀하게 확인하려면 IPA를 압축 해제하고 `otool`로 링크된 라이브러리를 검사한다.

```bash
unzip -o build/ios/ipa/YourApp.ipa -d /tmp/ipa_inspect
otool -L /tmp/ipa_inspect/Payload/Runner.app/Runner | grep -E "Photos|Camera|CoreLocation|Contacts|CoreMotion|HealthKit|CoreBluetooth|Speech"
```

결과에 등장하는 프레임워크가 보호 API와 매핑된다면 해당 purpose string이 필요하다.

---

## 업로드 후 경고 확인 방법

TestFlight 업로드 성공 후:

1. App Store Connect → 해당 앱 → TestFlight → 빌드 목록 진입
2. 노란색 경고 아이콘 또는 "Missing Compliance" 라벨 확인
3. 빌드를 클릭하면 위반 항목 전체 목록 확인 가능

메일보다 웹 UI에서 더 상세한 정보를 볼 수 있다. 여러 purpose string이 동시에 누락된 경우 전체 목록을 한 번에 파악할 수 있어 효율적이다.

---

## 주의: 실제로 사용하지 않는 권한 선언

purpose string만 추가하고 앱에서 해당 권한을 실제로 사용하지 않으면 심사에서 거절될 수 있다. Apple 가이드라인 5.1.1(데이터 수집 및 저장)에 따르면 앱에서 실제로 사용하는 권한만 선언해야 하며, 심사관이 이를 직접 테스트한다.

실제 예시: `file_picker`를 파일 첨부 기능에 사용하면 패키지 내부에서 `PHPhotoLibrary`에 접근하므로 `NSPhotoLibraryUsageDescription`은 정당하게 필요하다. 반면 앱 어디에도 카메라 UI가 없는데 "혹시 몰라서" `NSCameraUsageDescription`을 추가하면 심사에서 거절 사유가 된다.

각 패키지의 네이티브 구현이 실제로 해당 권한을 런타임에 요청하는지, 그리고 앱이 그 기능을 사용자에게 제공하는지를 먼저 확인한 뒤 키를 추가하는 것이 올바른 순서다.

---

## Flutter 전용: project.yml과 XcodeGen 사용 시 주의

Flutter 프로젝트에서 XcodeGen과 `project.yml`로 Xcode 프로젝트를 관리하는 경우 **`Info.plist`를 직접 수정하면 안 된다**. `make gen-ios` 또는 `xcodegen generate`를 실행할 때마다 `Info.plist`가 `project.yml`에서 재생성되어 직접 수정한 내용이 덮어씌워진다.

대신 `project.yml`의 타깃 `info` 블록에 purpose string을 선언한다.

```yaml
targets:
  Runner:
    info:
      path: ios/Runner/Info.plist
      properties:
        NSPhotoLibraryUsageDescription: "서류 제출 및 프로필 사진 업로드를 위해 사진 라이브러리에 접근합니다."
        NSCameraUsageDescription: "사진 촬영 및 문서 스캔을 위해 카메라에 접근합니다."
        NSMicrophoneUsageDescription: "음성 메시지 녹음을 위해 마이크에 접근합니다."
```

수정 후 반드시 재생성한다.

```bash
make gen-ios
# 또는: xcodegen generate
```

이렇게 해야 이후 `gen-ios`를 실행해도 purpose string이 유지된다.

---

## 수정 → 재업로드 흐름

```
1. ITMS-90683 메일에서 누락된 키 파악
          ↓
2. ios/Runner/Info.plist에 키 + 구체적인 설명 문자열 추가
   (XcodeGen 사용 시 project.yml에 추가 후 make gen-ios)
          ↓
3. 빌드 번호(CFBundleVersion) 증가
   (pubspec.yaml 또는 Info.plist에서 직접 수정)
          ↓
4. IPA 재빌드
   make testflight
   (또는: flutter build ipa --release && xcrun altool --upload-app ...)
          ↓
5. UPLOAD SUCCEEDED
          ↓
6. 5~10분 대기 — App Store Connect에서 메일 없으면 정상
```

중요한 점: 동일 빌드 번호로 재업로드하면 기존 빌드를 교체하는 것이 아니라 바로 거절된다. purpose string만 변경하는 경우에도 `CFBundleVersion`을 반드시 올려야 한다. `pubspec.yaml`의 `version` 필드에서 `+` 뒤 숫자가 빌드 번호에 해당한다.

---

## Key Takeaways

- ITMS-90683은 바이너리가 보호된 iOS API를 참조하지만 `Info.plist`에 해당 purpose string이 없을 때 발생한다. 내 코드에서 직접 호출하지 않아도 의존 패키지가 해당 프레임워크를 링크하면 트리거된다.
- Flutter 앱에서는 `pubspec.yaml` 의존성을 위 목록과 대조해 필요한 키를 미리 파악하는 것이 좋다.
- Purpose string은 사용자가 읽는 문구다. 실제 기능과 연결된 구체적인 설명을 작성해야 하며, 모호한 문구는 5.1.1 위반으로 거절될 수 있다.
- 앱에서 실제로 사용하지 않는 권한의 purpose string을 추가하지 않는다. 심사관이 테스트한다.
- Info.plist만 변경하는 경우에도 재업로드 전 빌드 번호를 반드시 올려야 한다.
- XcodeGen(`project.yml`) 사용 환경에서는 `Info.plist` 직접 수정 대신 `project.yml`에서 관리한다.
- 재업로드 후 5~10분 대기. App Store Connect에서 메일이 없으면 바이너리 자동 검사를 통과한 것이다.
