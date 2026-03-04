---
title: "Flutter iOS 배포 삽질 모음: 빌드 오류 5종 + 다크모드 하드코딩 + 로그아웃 버그"
date: 2026-02-27
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Dart", "Retrofit", "Freezed", "build_runner", "다크모드", "Makefile"]
description: "코드 생성 실패(Retrofit 문법 오류, Freezed sealed class), 누락된 파일 복원, Xcode 계정 없이 TestFlight 배포, 다크모드 색상 하드코딩, 로그아웃 토큰 미삭제 버그까지 — 하루에 터진 문제들을 정리한다."
---

빌드를 올리려는데 한꺼번에 여러 문제가 터졌다. 코드 생성기가 실패하고, 없어진 파일이 있고, 빌드 번호 규칙을 몰라서 거절당하고, UI는 다크모드가 하드코딩되어 있고, 로그아웃은 토큰을 안 지웠다. 하나씩 정리한다.

---

## 1. Retrofit 옵션 파라미터 문법 오류 → `.g.dart` 생성 실패

### 증상

`dart run build_runner build` 실행 시 일부 API 서비스 파일에서:

```
Expected to find ')'
```

### 원인

Retrofit의 추상 메서드에서 옵션 파라미터(`{}`) 위치를 잘못 씀.

```dart
// ❌ 잘못된 문법 — 닫는 중괄호 뒤에 쉼표
Future<Response> getItems(
  @Path('id') String id,
  {@Query('type') String? type},  // ← 이렇게 쓰면 안 됨
);

// ✅ 올바른 문법 — 포지셔널 파라미터 뒤에 { 바로 열기
Future<Response> getItems(
  @Path('id') String id, {
  @Query('type') String? type,
});
```

Dart 문법에서 옵션 파라미터는 마지막 포지셔널 파라미터 바로 뒤에 `{`를 열어야 한다. `},`로 닫은 뒤 쉼표를 찍으면 파서가 다음 인자로 인식하려다 실패한다.

### 해결

해당 패턴이 있는 모든 파일을 수정하고 재실행:

```bash
dart run build_runner build --delete-conflicting-outputs
```

---

## 2. Freezed 3.x + Dart 3.10: `sealed class` 필수

### 증상

`dart analyze` 시:

```
Missing concrete implementations of ...
```

### 원인

Freezed 3.x와 Dart 3.10 이상에서는 `@freezed` 어노테이션 대상 클래스를 `sealed class`로 선언해야 한다. 기존 `class`로 선언하면 `_$Mixin`의 추상 getter들이 구현체 없이 남아 에러가 난다.

```dart
// ❌ 예전 방식
@freezed
class MyModel with _$MyModel { ... }

// ✅ Freezed 3.x + Dart 3.10
@freezed
sealed class MyModel with _$MyModel { ... }
```

`sealed class`는 Dart 3.0에서 도입된 키워드로, switch 문에서 exhaustive 체크도 가능해진다.

---

## 3. 삭제된 파일이 생성 코드에 참조되어 빌드 실패

### 증상

Flutter 빌드 시:

```
Error when reading 'lib/core/services/place/place_service.dart': No such file or directory
Couldn't find constructor 'SomePage'
```

### 원인

소스 파일은 삭제되었는데, 코드 생성기가 만든 `injection.config.dart`나 라우터에서 여전히 참조하고 있었다. 생성된 파일(`.g.dart`, `.config.dart`)은 마지막 성공한 빌드 기준으로 남아있기 때문에 실제 소스와 불일치가 생긴다.

### 해결

참조되는 파일을 역추적해서 재생성. 핵심은:

1. `injection.config.dart`에서 import 경로 확인 → 어떤 클래스가 필요한지 파악
2. 해당 파일의 사용처(라우터, 위젯)에서 생성자 시그니처 확인
3. 최소한의 stub 또는 완전한 구현체 작성

예를 들어 라우터에서 `const SomePage()` 형태로 쓰이면 기본 생성자만 있으면 되고, 서비스 클래스면 인터페이스와 구현체 모두 필요하다.

---

## 4. Xcode 계정 없이 TestFlight 배포 (`-allowProvisioningUpdates` + API Key)

### 증상

`flutter build ipa` 실행 시:

```
No accounts found in Xcode
```

Xcode에 Apple 계정이 로그인되어 있지 않으면 자동 서명을 못 한다.

### 원인

`flutter build ipa`는 내부적으로 Xcode의 자동 서명을 사용하는데, 이때 Xcode에 계정이 등록되어 있어야 한다.

### 해결

`flutter build ios --no-codesign`으로 Dart만 컴파일하고, `xcodebuild`에 App Store Connect API Key를 직접 넘겨 서명과 배포를 처리한다.

```makefile
build-ipa:
    # 1단계: Dart 컴파일만 (서명 없이)
    flutter build ios --release --no-codesign

    # 2단계: Xcode가 API Key로 직접 서명
    xcodebuild -workspace ios/Runner.xcworkspace \
        -scheme Runner -configuration Release \
        -archivePath build/ios/archive/Runner.xcarchive \
        archive \
        DEVELOPMENT_TEAM=XXXXXXXXXX \
        -allowProvisioningUpdates \
        -authenticationKeyID $(API_KEY) \
        -authenticationKeyIssuerID $(API_ISSUER) \
        -authenticationKeyPath $(API_KEY_PATH)

    # 3단계: IPA export
    xcodebuild -exportArchive \
        -archivePath build/ios/archive/Runner.xcarchive \
        -exportPath build/ios/ipa \
        -exportOptionsPlist ios/ExportOptions.plist \
        -allowProvisioningUpdates \
        -authenticationKeyID $(API_KEY) \
        -authenticationKeyIssuerID $(API_ISSUER) \
        -authenticationKeyPath $(API_KEY_PATH)
```

API Key 파일(`AuthKey_XXXXXX.p8`)은 App Store Connect → Users and Access → Keys에서 발급받아 `~/.appstoreconnect/private_keys/`에 두면 된다.

---

## 5. TestFlight 빌드 번호 규칙

### 증상

두 번째 업로드 시:

```
The bundle version must be higher than the previously uploaded version: '5'
```

### 규칙

- **같은 버전 내 재업로드**: 빌드 번호를 올린다 (`1.0.1+1` → `1.0.1+2`)
- **버전 자체를 올릴 때**: 빌드 번호를 1로 리셋 (`1.0.2+1`)
- 같은 short version string(`CFBundleShortVersionString`) 안에서는 빌드 번호가 단조 증가해야 한다
- short version string이 바뀌면 빌드 번호를 1부터 다시 시작해도 된다

Flutter에서는 `pubspec.yaml`의 `version: 1.0.1+2`가 `CFBundleShortVersionString=1.0.1`, `CFBundleVersion=2`로 매핑된다.

### Makefile 자동화

매번 수동으로 번호를 올리면 실수하기 쉬우므로 Makefile에서 자동 증가:

```makefile
PUBSPEC      = pubspec.yaml
CURRENT_VER  := $(shell grep '^version:' $(PUBSPEC) | sed 's/version: //')
VERSION_NAME := $(shell echo $(CURRENT_VER) | cut -d'+' -f1)
BUILD_NUMBER := $(shell echo $(CURRENT_VER) | cut -d'+' -f2)
NEXT_BUILD   := $(shell echo $$(($(BUILD_NUMBER) + 1)))

bump-build:
    @echo "빌드번호 업: $(CURRENT_VER) → $(VERSION_NAME)+$(NEXT_BUILD)"
    @sed -i '' 's/^version: .*/version: $(VERSION_NAME)+$(NEXT_BUILD)/' $(PUBSPEC)

build-ipa: bump-build
    # ... 빌드 명령
```

`make build-testflight` 한 번으로 빌드번호 증가 → 빌드 → 업로드가 자동으로 이어진다.

---

## 6. 다크모드 색상 하드코딩 → 라이트모드에서 텍스트 안 보임

### 증상

특정 탭의 카드가 검정 배경인데 텍스트도 검정색 → 글씨가 안 보임.

### 원인

색상을 라이트/다크 모드 무관하게 고정값으로 사용했다:

```dart
// ❌ 다크 전용 색상을 항상 사용
color: AppColors.surfaceDark,    // Color(0xFF1A1A1A) — 거의 검정
style: TextStyle(color: AppColors.textPrimary), // Color(0xFF1C1C1E) — 거의 검정
```

`surfaceDark`(검정 카드) 위에 `textPrimary`(거의 검정 텍스트)를 올리면 둘 다 어두워서 안 보인다.

동시에 `main.dart`에서 `ThemeMode.light`가 하드코딩되어 있어 시스템 다크모드를 무시했다:

```dart
// ❌ 항상 라이트모드 강제
themeMode: ThemeMode.light,
```

### 해결

**① ThemeMode를 시스템 따르도록 변경:**

```dart
// ✅ 시스템 설정 반영
themeMode: ThemeMode.system,
```

**② 색상을 adaptive 메서드로 교체:**

```dart
// ✅ 현재 테마에 맞는 색상 반환
color: AppColors.surfaceOf(context),
style: TextStyle(color: AppColors.textPrimaryOf(context)),
border: Border.all(color: AppColors.borderOf(context)),
```

`context`를 받는 helper 메서드들은 내부적으로 `Theme.of(context).brightness`를 보고 다크/라이트 버전을 선택한다:

```dart
static Color surfaceOf(BuildContext context) {
  return isDarkMode(context) ? surfaceDark : surfaceLight;
}

static bool isDarkMode(BuildContext context) {
  return Theme.of(context).brightness == Brightness.dark;
}
```

---

## 7. 로그아웃 버튼이 토큰을 안 지움

### 증상

로그아웃 후 앱을 재시작하거나 로그인 화면으로 이동하면 자동으로 다시 메인으로 튕겨 들어간다.

### 원인

로그아웃 버튼이 화면 이동만 했고, 토큰 삭제와 소셜 로그인 해제가 없었다:

```dart
// ❌ 화면만 이동, 토큰은 그대로
onPressed: () {
  Navigator.pop(ctx);
  context.go('/login');
},
```

라우터는 `TokenStorage.hasToken()`으로 인증 여부를 판단한다. 토큰이 남아있으면 로그인 화면에서 다시 메인으로 리다이렉트된다.

### 해결

`AuthBloc`에 `logout` 이벤트를 발행해야 한다. `AuthRepository.logout()`이 API 호출 → 소셜 로그아웃(Google/Apple) → 토큰 삭제를 순서대로 처리한다:

```dart
// ✅ 토큰 삭제 + 소셜 로그아웃 처리 후 화면 이동
onPressed: () {
  Navigator.pop(ctx);
  context.read<AuthBloc>().add(const AuthEvent.logout());
  context.go('/login');
},
```

Bloc의 logout 핸들러:

```dart
logout: (e) async {
  emit(const AuthState.loading());
  try {
    await _authRepository.logout(); // API + 소셜 + 토큰 삭제
    emit(const AuthState.unauthenticated());
  } catch (e) {
    emit(AuthState.error(e.toString()));
  }
},
```

---

## 정리

| 문제 | 원인 | 핵심 해결 |
|------|------|----------|
| `build_runner` 실패 | Retrofit 옵션 파라미터 `},` 문법 오류 | `id, {` + `param,` + `}` 순서 |
| `Missing concrete implementations` | Freezed 3.x에서 `class` → `sealed class` | `sealed class` 키워드 |
| 파일 없음 빌드 실패 | 소스 삭제 후 생성 코드에 참조 잔존 | 참조 역추적 후 파일 재생성 |
| Xcode 계정 없음 | `flutter build ipa`는 Xcode 계정 필요 | `--no-codesign` + `xcodebuild` + API Key |
| 빌드번호 중복 거절 | 같은 번호 재업로드 | 버전 올리면 빌드번호 1 리셋 가능 |
| 텍스트 안 보임 | 다크 색상 하드코딩 + `ThemeMode.light` 고정 | `ThemeMode.system` + adaptive 색상 |
| 로그아웃 무효 | 화면 이동만, 토큰 미삭제 | `AuthBloc.logout()` 발행 필수 |
