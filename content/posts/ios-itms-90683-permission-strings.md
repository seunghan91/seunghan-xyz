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

업로드 자체는 성공했지만 앱 배포 전 Apple이 자동으로 검사해서 이 메일을 보낸다. 수정하지 않으면 App Store 심사 제출 시 거절된다.

---

## 왜 이 오류가 발생하는가

iOS는 카메라, 사진 라이브러리, 마이크 등 민감한 API에 접근할 때 사용자에게 권한 팝업을 보여준다. 이 팝업에 표시되는 설명 문구가 Info.plist에 없으면 Apple이 오류로 처리한다.

앱에서 직접 권한을 요청하지 않더라도 **의존 패키지가 해당 API를 사용**하면 purpose string이 필요하다. `file_picker`, `image_picker`, `photo_view` 같은 패키지를 쓰면 실제 호출 여부와 무관하게 선언이 필요하다.

---

## 수정: Info.plist에 purpose string 추가

`ios/Runner/Info.plist`에 해당 키와 설명 문자열을 추가한다.

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
    <string>사진 촬영 및 파일 업로드를 위해 카메라에 접근합니다.</string>

</dict>
</plist>
```

---

## 자주 나오는 purpose string 목록

| 키 | 설명 | 관련 패키지 |
|----|------|------------|
| `NSPhotoLibraryUsageDescription` | 사진 라이브러리 읽기 | image_picker, file_picker, photo_view |
| `NSPhotoLibraryAddUsageDescription` | 사진 라이브러리 저장 | image_gallery_saver 등 |
| `NSCameraUsageDescription` | 카메라 | image_picker, camera |
| `NSMicrophoneUsageDescription` | 마이크 | audio_recorder, video 촬영 |
| `NSLocationWhenInUseUsageDescription` | 위치 (앱 사용 중) | geolocator, google_maps |
| `NSLocationAlwaysUsageDescription` | 위치 (백그라운드) | background_location |
| `NSContactsUsageDescription` | 연락처 | contacts_service |
| `NSCalendarsUsageDescription` | 캘린더 | add_2_calendar 등 |
| `NSFaceIDUsageDescription` | Face ID | local_auth |
| `NSBluetoothAlwaysUsageDescription` | 블루투스 | flutter_blue 등 |

---

## 어떤 권한이 필요한지 확인하는 방법

패키지 README나 pub.dev 페이지의 "iOS permissions" 섹션을 확인하는 게 가장 빠르다. 아니면 빌드 후 나오는 경고로 파악할 수 있다.

```bash
# Xcode 빌드 로그에서 권한 관련 경고 검색
xcodebuild ... 2>&1 | grep -i "usage description"
```

또는 Info.plist를 열어 이미 추가된 키 목록과 비교하는 방법도 있다.

```bash
# 현재 Info.plist에 있는 권한 키 확인
/usr/libexec/PlistBuddy -c "Print" ios/Runner/Info.plist | grep "UsageDescription"
```

---

## 업로드 후 경고 확인 방법

TestFlight 업로드 성공 후 App Store Connect → 앱 → TestFlight → 빌드 목록에서 "Missing Compliance" 또는 경고 아이콘이 있는지 확인한다.

메일로도 오지만 App Store Connect 웹에서 더 자세한 정보를 확인할 수 있다.

---

## 주의: 앱에서 실제로 사용하지 않는 권한

purpose string만 추가하고 앱에서 실제로 해당 권한을 요청하지 않으면 심사에서 거절될 수 있다. Apple 가이드라인 5.1.1에 따르면 실제로 사용하는 권한만 선언해야 한다.

파일 업로드 기능을 `file_picker`로 구현하면 내부적으로 사진 라이브러리에 접근하므로 `NSPhotoLibraryUsageDescription`은 정당하게 필요하다. 반면 앱 어디에도 카메라를 쓰지 않는데 `NSCameraUsageDescription`만 추가하면 심사에서 걸릴 수 있다.

---

## 수정 → 재업로드 흐름

```
Info.plist 권한 키 추가
        ↓
make testflight  (또는 flutter build ipa → xcrun altool)
        ↓
UPLOAD SUCCEEDED
        ↓
App Store Connect에서 메일 없으면 정상
```

권한 문자열만 바꾸는 경우라면 빌드 번호를 올릴 필요 없이 바로 재업로드한다. 단, 동일 빌드 번호로 재업로드하면 기존 빌드를 교체하는 게 아니라 거절된다. 빌드 번호를 올려야 한다.
