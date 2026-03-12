---
title: "XcodeGen이 Info.plist 버전을 매번 덮어쓰는 문제 — 근본 해결법"
date: 2026-03-12
draft: false
tags: ["iOS", "XcodeGen", "Xcode", "TestFlight", "WidgetKit", "CI/CD"]
description: "XcodeGen으로 프로젝트를 재생성할 때마다 Info.plist의 CFBundleVersion이 하드코딩 값으로 리셋되는 문제. project.yml에 변수 참조를 명시하면 영구적으로 해결된다."
---

XcodeGen 기반 iOS 프로젝트에서 TestFlight 빌드를 반복하다 보면 이상한 현상을 마주친다. `xcodegen generate`를 실행할 때마다 Info.plist의 `CFBundleVersion`과 `CFBundleShortVersionString`이 하드코딩된 `1`과 `1.0`으로 리셋된다.

매번 수동으로 고쳐야 해서 빌드 파이프라인이 불안정해지고, TestFlight에 같은 빌드 번호로 업로드하면 "Redundant Binary Upload" 에러가 발생한다.

---

## 증상

```
UPLOAD FAILED with 1 error
Redundant Binary Upload. You've already uploaded a build
with build number '6' for version number '1.0'.
```

`xcodegen generate` 후 Info.plist를 확인하면:

```xml
<key>CFBundleShortVersionString</key>
<string>1.0</string>      <!-- 하드코딩됨 -->
<key>CFBundleVersion</key>
<string>1</string>         <!-- 하드코딩됨 -->
```

`project.yml`에서 `CURRENT_PROJECT_VERSION: "7"`로 올려놔도, Info.plist에는 반영되지 않는다. Xcode가 빌드할 때 build settings의 값을 사용하긴 하지만, 다른 도구나 스크립트가 Info.plist를 직접 읽으면 잘못된 값을 가져간다.

---

## 원인

XcodeGen은 `info.properties`에 `CFBundleShortVersionString`과 `CFBundleVersion`을 **명시하지 않으면** 기본값을 하드코딩한다.

```yaml
# project.yml — 잘못된 예
targets:
  MyApp:
    info:
      path: MyApp/Info.plist
      properties:
        CFBundleDisplayName: My App
        # CFBundleVersion, CFBundleShortVersionString 미지정
        # → XcodeGen이 "1"과 "1.0"을 하드코딩
```

Xcode 11 이후로 Apple은 Info.plist에 변수 참조(`$(MARKETING_VERSION)`, `$(CURRENT_PROJECT_VERSION)`)를 사용하고, 실제 값은 `.pbxproj` build settings에 저장하는 방식으로 바꿨다. XcodeGen이 이 패턴을 자동으로 적용하지 않는 게 문제다.

---

## 해결: project.yml에 변수 참조 명시

`info.properties`에 변수 참조를 직접 지정하면 XcodeGen이 Info.plist에 올바른 값을 기록한다.

```yaml
# project.yml — 올바른 설정
settings:
  base:
    VERSIONING_SYSTEM: "apple-generic"
    MARKETING_VERSION: "1.0.0"
    CURRENT_PROJECT_VERSION: "8"

targets:
  MyApp:
    info:
      path: MyApp/Info.plist
      properties:
        CFBundleShortVersionString: $(MARKETING_VERSION)
        CFBundleVersion: $(CURRENT_PROJECT_VERSION)
        # ... 나머지 속성들
```

이렇게 하면 `xcodegen generate`를 몇 번을 실행해도 Info.plist에는 항상 변수 참조가 유지된다:

```xml
<key>CFBundleShortVersionString</key>
<string>$(MARKETING_VERSION)</string>
<key>CFBundleVersion</key>
<string>$(CURRENT_PROJECT_VERSION)</string>
```

### Widget Extension도 동일하게 적용

앱 본체와 Widget Extension이 있는 경우, **양쪽 타겟 모두** 동일한 설정이 필요하다:

```yaml
targets:
  MyApp:
    info:
      properties:
        CFBundleShortVersionString: $(MARKETING_VERSION)
        CFBundleVersion: $(CURRENT_PROJECT_VERSION)
    # ...

  MyWidgetExtension:
    info:
      properties:
        CFBundleShortVersionString: $(MARKETING_VERSION)
        CFBundleVersion: $(CURRENT_PROJECT_VERSION)
    # ...
```

App Store 검증 시 메인 앱과 Extension의 버전이 일치하지 않으면 업로드가 거절된다.

---

## 빌드 번호 자동 증가 Makefile

해결 후 Makefile에 빌드 번호 자동 증가를 추가하면 TestFlight 빌드가 완전 자동화된다:

```makefile
PROJECT_YML = $(PWD)/ios/project.yml

# 빌드 번호 자동 증가 (project.yml의 CURRENT_PROJECT_VERSION)
bump-build:
	@CURRENT=$$(grep 'CURRENT_PROJECT_VERSION:' $(PROJECT_YML) \
	  | awk '{print $$2}' | tr -d '"'); \
	NEXT=$$((CURRENT + 1)); \
	sed -i '' "s/CURRENT_PROJECT_VERSION: \"$$CURRENT\"/CURRENT_PROJECT_VERSION: \"$$NEXT\"/" \
	  $(PROJECT_YML); \
	echo "빌드 번호: $$CURRENT → $$NEXT"

# DerivedData 정리
clean-ios:
	rm -rf $(PWD)/ios/build \
	  ~/Library/Developer/Xcode/DerivedData/MyApp-*

# Archive 생성 (xcodegen 재생성 포함)
build-ios: gen-ios
	cd ios && xcodebuild archive \
	  -project MyApp.xcodeproj \
	  -scheme MyApp \
	  -archivePath $(ARCHIVE_PATH) \
	  -destination "generic/platform=iOS" \
	  -allowProvisioningUpdates

# TestFlight 전체 파이프라인
build-testflight: bump-build clean-ios build-ios build-ipa
	xcrun altool --upload-app --type ios \
	  -f $(IPA_DIR)/MyApp.ipa \
	  --apiKey $(ASC_API_KEY) \
	  --apiIssuer $(ASC_ISSUER)
```

`make build-testflight` 한 줄로:
1. `project.yml`에서 빌드 번호 자동 증가
2. DerivedData 캐시 정리
3. `xcodegen generate` → Archive → IPA 추출
4. TestFlight 업로드

---

## 핵심 포인트 정리

| 항목 | 잘못된 방법 | 올바른 방법 |
|------|-----------|-----------|
| Info.plist 버전 | 매번 수동으로 `$(MARKETING_VERSION)` 복원 | `project.yml`의 `info.properties`에 변수 참조 명시 |
| 빌드 번호 관리 | Info.plist에 직접 하드코딩 | `project.yml`의 `CURRENT_PROJECT_VERSION` 변경 |
| 빌드 캐시 | DerivedData 무시하고 빌드 | 빌드 번호 변경 시 DerivedData 삭제 |
| Extension 버전 | 메인 앱만 설정 | 메인 앱 + Extension 양쪽 모두 변수 참조 |

### 참고 자료

- [XcodeGen Issue #649 — CURRENT_PROJECT_VERSION 설정](https://github.com/yonaskolb/XcodeGen/issues/649)
- [Apple Developer — Build Settings Reference: Current Project Version](https://developer.apple.com/documentation/xcode/build-settings-reference#Current-Project-Version)
- [Apple Developer Forums — Xcode Project Versioning](https://developer.apple.com/forums/thread/709065)
