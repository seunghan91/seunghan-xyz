---
title: "Flutter iOS TestFlight 업로드 실패: objective_c.framework 시뮬레이터 슬라이스 오류"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "Xcode", "TestFlight", "Makefile", "빌드 오류"]
description: "flutter build ipa 후 TestFlight 업로드 시 IOSSIMULATOR 플랫폼 태그, x86_64 슬라이스 오류가 발생하는 원인과 Makefile 자동화 해결책"
---

Flutter 앱을 `flutter build ipa --release`로 빌드하고 TestFlight에 업로드했더니 altool이 거절했다.
원인, 삽질 과정, 그리고 Makefile 자동화까지 정리한다.

---

## 오류 메시지

```
UPLOAD FAILED with 3 errors

Invalid executable. The "Runner.app/Frameworks/objective_c.framework/objective_c"
executable references an unsupported platform in the x86_64 slice.
Simulator platforms aren't permitted.

Invalid executable. The "Runner.app/Frameworks/objective_c.framework/objective_c"
executable references an unsupported platform in the arm64 slice.
Simulator platforms aren't permitted.

Unsupported Architectures. The executable for
Runner.app/Frameworks/objective_c.framework contains unsupported architectures '[x86_64]'.
```

`flutter build ipa`가 성공하고 IPA 파일도 정상 생성됐는데 업로드에서 막혔다.

---

## 원인

Flutter의 Dart FFI 패키지 `objective_c`는 개발 편의를 위해 iOS 기기(arm64)와 시뮬레이터(x86_64, arm64-simulator)를 모두 지원하는 **fat binary(universal binary)** 로 빌드된다.

문제는 두 가지다.

**1. x86_64 슬라이스 포함**

시뮬레이터용 x86_64 아키텍처가 App Store 제출용 IPA에 그대로 들어간다. Apple은 App Store 빌드에서 시뮬레이터 아키텍처를 허용하지 않는다.

**2. arm64 슬라이스의 플랫폼 태그가 IOSSIMULATOR**

`lipo`로 x86_64만 제거해도 arm64 슬라이스 자체에 박힌 `LC_BUILD_VERSION` 플랫폼 태그가 `IOSSIMULATOR`라 Apple 검증기가 또 거절한다.

```bash
# 확인 방법
vtool -show-build Runner.app/Frameworks/objective_c.framework/objective_c

# 문제 있는 출력
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform IOSSIMULATOR   ← 이게 문제
    minos 14.0
```

---

## 해결 순서

### 1단계: x86_64 슬라이스 제거

```bash
FW="Runner.xcarchive/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"
lipo -remove x86_64 "$FW" -output "$FW"
```

### 2단계: arm64 플랫폼 태그를 IOS로 교체

```bash
vtool -set-build-version ios 13.0 17.0 -replace \
  -output "$FW.tmp" "$FW"
mv "$FW.tmp" "$FW"
```

`vtool`은 코드 서명을 무효화하므로 반드시 **xcarchive 상태에서 수정**하고 이후 `xcodebuild -exportArchive`로 재서명해야 한다.

> **주의**: IPA를 unzip해서 바이너리를 직접 수정하면 서명이 깨져 `Missing or invalid signature` 오류가 난다. xcarchive에서 고쳐야 한다.

### 3단계: IPA 재생성 (재서명 포함)

```bash
xcodebuild -exportArchive \
  -archivePath "Runner.xcarchive" \
  -exportPath "build/ios/ipa" \
  -exportOptionsPlist "ios/ExportOptions.plist"
```

이 순서로 하면 Xcode가 수정된 바이너리를 배포 인증서로 다시 서명해서 IPA를 만들어준다.

---

## Makefile 자동화

매번 수동으로 하면 번거로우니 Makefile에 `fix-frameworks` 타겟을 만들어 `build-ipa`에 연결했다.

```makefile
ARCHIVE       = mobile/build/ios/archive/Runner.xcarchive
IPA_DIR       = mobile/build/ios/ipa
IOS_DIR       = mobile/ios
DEPLOY_TARGET = 13.0

build-ipa:
	cd mobile && flutter build ipa --release \
		--export-options-plist=ios/ExportOptions.plist
	$(MAKE) fix-frameworks
	@echo "=== IPA ready ==="

fix-frameworks:
	@ARCHIVE="$(ARCHIVE)"; \
	FW="$$ARCHIVE/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"; \
	if [ ! -f "$$FW" ]; then echo "objective_c.framework not found, skipping"; exit 0; fi; \
	echo "=== Fixing objective_c.framework ==="; \
	ARCHS=$$(lipo -archs "$$FW" 2>/dev/null); \
	if echo "$$ARCHS" | grep -q x86_64; then \
		lipo -remove x86_64 "$$FW" -output "$$FW.tmp" && mv "$$FW.tmp" "$$FW"; \
		echo "  ✓ Removed x86_64 slice"; \
	fi; \
	PLATFORM=$$(vtool -show-build "$$FW" 2>/dev/null | grep "platform " | awk '{print $$2}'); \
	if [ "$$PLATFORM" != "IOS" ]; then \
		vtool -set-build-version ios $(DEPLOY_TARGET) 17.0 -replace \
			-output "$$FW.tmp" "$$FW" 2>&1 | grep -v warning || true; \
		mv "$$FW.tmp" "$$FW"; \
		echo "  ✓ Fixed platform tag: $$PLATFORM → IOS"; \
	fi; \
	echo "=== Re-exporting IPA ==="; \
	xcodebuild -exportArchive \
		-archivePath "$$ARCHIVE" \
		-exportPath "$(IPA_DIR)" \
		-exportOptionsPlist "$(IOS_DIR)/ExportOptions.plist" 2>&1 | tail -3

testflight: bump-build build-ipa
	xcrun altool --upload-app \
		-f $(IPA_DIR)/*.ipa \
		-t ios \
		--apiKey $(ASC_API_KEY) \
		--apiIssuer $(ASC_ISSUER) 2>&1 | tail -5
```

이제 `make testflight` 하나로 빌드 번호 증가 → 빌드 → 프레임워크 수정 → TestFlight 업로드가 자동으로 된다.

---

## 삽질 포인트 정리

| 시도 | 결과 | 이유 |
|------|------|------|
| IPA unzip → lipo 제거 → zip 재압축 | ❌ `Missing or invalid signature` | 서명 무효화 후 재서명 없이 업로드 시도 |
| xcarchive에서 lipo만 제거 | ❌ `IOSSIMULATOR platform in arm64 slice` | x86_64만 없애도 arm64 플랫폼 태그가 살아있음 |
| xcarchive에서 lipo + vtool + 재익스포트 | ✅ 업로드 성공 | 올바른 순서 |

---

## 왜 이런 문제가 생기나

Flutter의 `objective_c` 패키지는 Dart FFI를 통해 Objective-C 런타임에 접근하는 패키지다. 개발 중 시뮬레이터에서도 실행할 수 있도록 universal binary로 배포되는데, 릴리스 빌드에서 시뮬레이터 슬라이스를 자동으로 제거하는 로직이 현재 Flutter 빌드 파이프라인에 빠져 있다.

React Native의 경우 `Podfile`에 `strip-frameworks.sh` 스크립트를 Xcode 빌드 페이즈에 추가해서 이 문제를 우회한다. Flutter도 비슷한 방식을 쓸 수 있지만, Makefile 레벨에서 후처리하는 게 더 간단하다.
