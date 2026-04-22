---
title: "Flutter iOS TestFlight 업로드 실패: objective_c.framework 시뮬레이터 슬라이스 오류"
date: 2026-03-09
draft: false
tags: ["Flutter", "iOS", "Xcode", "TestFlight", "Makefile", "빌드 오류"]
categories: ["iOS", "Flutter"]
description: "flutter build ipa 후 TestFlight 업로드 시 IOSSIMULATOR 플랫폼 태그, x86_64 슬라이스 오류가 발생하는 원인과 Makefile 자동화 해결책"
---

Flutter 앱을 `flutter build ipa --release`로 빌드하고 TestFlight에 업로드했더니 altool이 거절했다.
원인, 삽질 과정, Makefile 자동화까지 정리한다.

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

`flutter build ipa`는 성공했고 IPA 파일도 정상 생성됐다. 문제는 빌드 단계가 아니라 업로드 단계에서 발생했다. 즉, Xcode 설정이나 Flutter 프로젝트 구성 자체의 문제가 아니라 Flutter가 조용히 임베드하는 서드파티 프레임워크 바이너리 안에 문제가 있다는 뜻이다.

---

## 원인

Flutter의 Dart FFI 패키지 `objective_c`는 개발 편의를 위해 iOS 기기(arm64)와 시뮬레이터(x86_64, arm64-simulator)를 모두 지원하는 **fat binary(universal binary)** 로 빌드된다.

Apple의 App Store 검증 파이프라인은 시뮬레이터 코드나 시뮬레이터 플랫폼 태그가 포함된 바이너리를 모두 거절한다. 두 가지 독립적인 문제가 세 개의 검증 오류를 만들어낸다.

**문제 1: x86_64 슬라이스 포함**

시뮬레이터 전용 x86_64 아키텍처가 App Store 제출용 IPA에 그대로 들어간다. Apple은 App Store 빌드에서 시뮬레이터 아키텍처를 허용하지 않는다. 이 오류가 가장 눈에 띄어서 보통 여기만 고치려 하는데, 그걸로는 부족하다.

**문제 2: arm64 슬라이스의 플랫폼 태그가 IOSSIMULATOR**

`lipo`로 x86_64 슬라이스를 제거해도 남아 있는 arm64 슬라이스 자체에 `LC_BUILD_VERSION` Mach-O 로드 커맨드가 박혀 있고, 거기 기록된 플랫폼이 `IOSSIMULATOR`다. Apple 검증기는 이 로드 커맨드를 독립적으로 검사해서 두 번째로 거절한다.

```bash
# 확인 방법
vtool -show-build Runner.app/Frameworks/objective_c.framework/objective_c

# 문제 있는 출력
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform IOSSIMULATOR   <- 이게 문제
    minos 14.0
    sdk 17.0
```

`LC_BUILD_VERSION` 로드 커맨드는 컴파일 타임에 바이너리에 기록된다. `objective_c` 패키지가 시뮬레이터 지원을 포함해서 컴파일되면 결과 바이너리는 타겟 플랫폼으로 `IOSSIMULATOR`를 기록한다. x86_64 슬라이스를 제거해도 arm64 슬라이스의 메타데이터 헤더는 그대로다. 두 문제를 모두 해결해야 Apple 검증기를 통과할 수 있다.

---

## 도구 이해: lipo vs vtool

수정 방법을 설명하기 전에 각 도구가 하는 일을 이해해두면 왜 이 순서가 맞는지 납득하기 쉽다.

**`lipo`** — 멀티 아키텍처 바이너리 도구. fat binary를 생성, 검사, 수정한다. fat binary는 여러 아키텍처 슬라이스를 하나의 파일에 이어 붙인 것이다. `lipo -archs`로 어떤 슬라이스가 들어있는지 확인하고, `lipo -remove`로 특정 슬라이스를 제거한다.

**`vtool`** — Mach-O 로드 커맨드 편집기. Mach-O 바이너리 내부의 메타데이터 헤더를 읽고 수정한다. `LC_BUILD_VERSION` 로드 커맨드에는 플랫폼(iOS, macOS, IOSSIMULATOR 등)과 최소 OS 버전이 기록되어 있다. `vtool -set-build-version`으로 이 값을 덮어쓸 수 있다.

**vtool이 코드 서명을 무효화하는 이유**: iOS 코드 서명은 바이너리 내용 전체(Mach-O 헤더 포함)에 대한 암호화 해시를 계산하는 방식으로 작동한다. `vtool`이 로드 커맨드를 수정하면 헤더의 바이트가 바뀌고, 그러면 기존 서명 해시가 깨진다. 그래서 수정은 반드시 `xcodebuild -exportArchive`가 배포 인증서로 재서명하기 전에, xcarchive 상태에서 이루어져야 한다.

---

## 해결 순서

### 1단계: x86_64 슬라이스 제거

IPA가 아니라 xcarchive 안에서 작업한다. xcarchive에는 서명 전의 언패키지된 앱 번들이 들어있어서 수정이 가능하다.

```bash
FW="Runner.xcarchive/Products/Applications/Runner.app/Frameworks/objective_c.framework/objective_c"
lipo -remove x86_64 "$FW" -output "$FW.tmp" && mv "$FW.tmp" "$FW"
```

결과 확인:

```bash
lipo -archs "$FW"
# 출력: arm64
```

### 2단계: arm64 플랫폼 태그를 IOS로 교체

```bash
vtool -set-build-version ios 13.0 17.0 -replace \
  -output "$FW.tmp" "$FW"
mv "$FW.tmp" "$FW"
```

`-set-build-version` 인자는 순서대로 `플랫폼 최소OS SDK`다. `ios`(IOSSIMULATOR가 아님), 앱의 배포 타겟을 `minos`에, SDK 버전을 `sdk`에 넣는다. `-replace` 플래그는 기존 `LC_BUILD_VERSION`을 덮어쓰도록 지정한다(새로 추가하는 게 아니라).

결과 확인:

```bash
vtool -show-build "$FW"
# platform IOS 가 나와야 한다
```

`vtool`은 코드 서명을 무효화하므로 반드시 **xcarchive 상태에서 수정**하고 이후 `xcodebuild -exportArchive`로 재서명해야 한다.

> **주의**: IPA를 unzip해서 바이너리를 직접 수정하면 서명이 깨져 `Missing or invalid signature` 오류가 난다. 반드시 xcarchive에서 수정해야 한다. IPA는 서명이 완료된 결과물이고, xcarchive는 수정이 안전한 중간 작업 공간이다.

### 3단계: IPA 재생성 (재서명 포함)

```bash
xcodebuild -exportArchive \
  -archivePath "Runner.xcarchive" \
  -exportPath "build/ios/ipa" \
  -exportOptionsPlist "ios/ExportOptions.plist"
```

`xcodebuild -exportArchive`는 수정된 xcarchive를 읽어서 배포 인증서와 프로비저닝 프로파일로 전체 서명 파이프라인을 다시 실행하고, 새 IPA를 생성한다. 결과 바이너리는 수정된 로드 커맨드를 커버하는 유효한 서명을 갖게 된다.

---

## Makefile 자동화

매번 수동으로 하면 번거로우니 Makefile에 `fix-frameworks` 타겟을 만들어 `build-ipa`에 연결했다. 스크립트는 방어적으로 작성했다: 프레임워크가 존재하는지 먼저 확인하고, 이미 올바른 상태면 각 단계를 건너뛴다(향후 Flutter 버전에서 이 문제가 수정되었을 때도 안전하게 동작하도록).

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
		echo "  x86_64 슬라이스 제거 완료"; \
	fi; \
	PLATFORM=$$(vtool -show-build "$$FW" 2>/dev/null | grep "platform " | awk '{print $$2}'); \
	if [ "$$PLATFORM" != "IOS" ]; then \
		vtool -set-build-version ios $(DEPLOY_TARGET) 17.0 -replace \
			-output "$$FW.tmp" "$$FW" 2>&1 | grep -v warning || true; \
		mv "$$FW.tmp" "$$FW"; \
		echo "  플랫폼 태그 수정: $$PLATFORM -> IOS"; \
	fi; \
	echo "=== IPA 재생성 중 ==="; \
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

`fix-frameworks` 타겟은 멱등적이기도 하다. 프레임워크가 이미 올바른 상태거나 존재하지 않으면 아무 일도 하지 않고 종료한다. 그래서 `build-ipa`에 무조건 포함시켜도 안전하다.

---

## 삽질 포인트 정리

| 시도 | 결과 | 이유 |
|------|------|------|
| IPA unzip → lipo 제거 → zip 재압축 | `Missing or invalid signature` | 서명 무효화 후 재서명 없이 업로드 시도 |
| xcarchive에서 lipo만 제거 | `IOSSIMULATOR platform in arm64 slice` | x86_64만 없애도 arm64 플랫폼 태그가 살아있음 |
| xcarchive에서 lipo + vtool + 재익스포트 | 업로드 성공 | 올바른 순서: 수정 후 재서명 |

첫 번째 시도는 가장 직관적이지만 틀렸다. 두 번째 시도는 올바른 위치에서 작업했지만 두 번째 오류를 놓쳤다. 세 번째 시도만이 두 문제를 올바른 순서로 해결한다.

---

## 왜 이런 문제가 생기나

Flutter의 `objective_c` 패키지는 Dart FFI를 통해 Objective-C 런타임에 접근하는 패키지다. 개발 중 시뮬레이터에서도 실행할 수 있도록 universal binary로 배포되는데, Flutter 빌드 파이프라인이 현재 App Store IPA를 패키징하기 전에 이 FFI 프레임워크에서 시뮬레이터 슬라이스를 자동으로 제거하지 않는다.

이것은 Flutter iOS 릴리스 툴체인의 알려진 공백이다. `flutter build ipa` 명령은 아카이빙, 기본 검증, 초기 익스포트 등 많은 것을 처리하지만 임베디드 프레임워크에서 시뮬레이터 아티팩트를 후처리하지는 않는다. `xcodebuild` 스트리핑이 이를 처리한다고 가정하는 것으로 보이지만, Xcode 의존성 그래프 밖에서 빌드된 Dart FFI 프레임워크는 그 처리 대상이 아니다.

React Native는 `Podfile`의 `post_install` 훅에 `strip-frameworks.sh` 스크립트를 Xcode 빌드 페이즈로 추가해서 이 문제를 우회한다. 스크립트는 임베디드 프레임워크를 순회하며 비기기 아키텍처를 아카이브 생성 전에 제거한다. Flutter 프로젝트에서도 비슷한 방식을 Xcode 프로젝트에 커스텀 빌드 페이즈로 추가할 수 있지만, `project.pbxproj`를 직접 편집하거나 `post_install` 훅을 관리해야 해서 관리 부담이 있다. 아카이브 후 Makefile 타겟에서 후처리하는 방식이 더 단순하고 모든 릴리스 로직을 한 곳에서 관리할 수 있다.

프로젝트에 Dart FFI 패키지가 여러 개 있다면(예: C나 Objective-C 라이브러리를 래핑하는 패키지), 다른 프레임워크에도 같은 문제가 있는지 확인해볼 필요가 있다.

```bash
find Runner.xcarchive -name "*.framework" | while read fw; do
  bin="$fw/$(basename $fw .framework)"
  [ -f "$bin" ] && echo "$bin: $(lipo -archs "$bin" 2>/dev/null)"
done
```

위 명령으로 xcarchive 내 모든 프레임워크 바이너리의 아키텍처를 확인할 수 있다. `objective_c` 외에 `x86_64`가 포함된 프레임워크가 있으면 `fix-frameworks` 타겟을 확장해야 한다.

---

## 핵심 정리

- `flutter build ipa`는 Dart FFI 프레임워크에서 시뮬레이터 슬라이스를 제거하지 않는다. 결과 IPA는 TestFlight의 altool 검증기에서 거절된다.
- 두 가지 문제를 모두 해결해야 한다: x86_64 아키텍처 슬라이스(`lipo -remove`)와 arm64 슬라이스의 `IOSSIMULATOR` 플랫폼 태그(`vtool -set-build-version`).
- 두 수정 모두 IPA가 아닌 xcarchive에서 이루어져야 한다. IPA는 서명이 완료된 결과물이고 수정하면 서명이 깨진다. xcarchive가 서명 전 작업 공간이다.
- 바이너리 수정 후 `xcodebuild -exportArchive`로 배포 인증서를 사용해 재서명하고 새 IPA를 생성한다.
- Makefile의 `fix-frameworks` 타겟으로 이 과정을 자동화하면 `make testflight` 하나로 모든 것이 처리된다.
- C나 Objective-C 라이브러리를 래핑하는 패키지를 사용 중이라면 다른 Dart FFI 프레임워크도 같은 문제가 있는지 확인한다.
