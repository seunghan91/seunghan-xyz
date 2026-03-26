---
title: "Flutter AAB 빌드 서명 오류 해결 — Play Store 업로드 시 wrong key 에러 완벽 가이드"
date: 2026-03-26
draft: false
tags: ["Flutter", "Android", "Play Store", "keystore", "AAB"]
description: "Flutter 앱을 Google Play Store에 업로드할 때 발생하는 'Android App Bundle is signed with the wrong key' 에러의 원인과 해결법. key.properties 설정부터 build.gradle.kts 서명 구성까지 실전 삽질 기록."
---

## Flutter AAB를 Play Console에 드래그했더니 서명 에러

Flutter로 만든 앱을 Google Play Console에 업로드하려고 `flutter build appbundle --release`로 AAB 파일을 빌드했다. 빌드 자체는 성공했고, 51MB짜리 `app-release.aab`가 잘 생성됐다. 자신만만하게 Play Console에 드래그 앤 드롭했는데, 이런 에러가 떴다.

```
Android App Bundle이 잘못된 키로 서명되었습니다.
제대로 된 서명 키로 App Bundle에 서명한 다음 다시 시도해 보세요.

SHA1: 5A:2A:F8:A4:71:76:3B:CC:35:78:33:B1:98:65:8F:24:85:72:AB:87
지문이 포함된 인증서로 App Bundle에 서명해야 하지만,
업로드한 App Bundle 서명에 사용된 인증서의 지문은
SHA1: A8:E9:B6:3C:C6:9A:E9:FE:06:AA:BB:2E:E3:43:85:1A:74:96:16:48
입니다.
```

두 개의 SHA1 지문이 달랐다. Play Console이 기대하는 키와, 실제 AAB에 서명된 키가 다르다는 뜻이다.

---

## 왜 이런 에러가 발생하는가

Android 앱 서명 체계를 이해하면 원인이 바로 보인다.

### Android의 2단계 서명 구조

Google Play는 두 종류의 서명 키를 사용한다.

| 키 종류 | 역할 | 누가 관리하나 |
|---------|------|-------------|
| **Upload Key** (업로드 키) | 개발자가 AAB/APK를 Play Console에 올릴 때 사용 | 개발자 |
| **App Signing Key** (앱 서명 키) | 최종 사용자에게 배포될 APK에 서명 | Google (Play App Signing) |

개발자는 업로드 키로 AAB에 서명해서 Play Console에 올린다. Google이 이걸 검증한 뒤, 자체 앱 서명 키로 다시 서명해서 사용자에게 배포한다.

에러의 핵심은 이거다: **Play Console에 등록된 업로드 키의 SHA1과, 내가 빌드한 AAB의 서명 SHA1이 다르다.**

### Flutter 기본 빌드의 함정

Flutter 프로젝트를 처음 생성하면 `build.gradle.kts`의 release 빌드 타입이 이렇게 설정되어 있다.

```kotlin
buildTypes {
    release {
        // TODO: Add your own signing config for the release build.
        // Signing with the debug keys for now, so `flutter run --release` works.
        signingConfig = signingConfigs.getByName("debug")
    }
}
```

주석에도 대놓고 "지금은 debug 키로 서명 중"이라고 써있다. `flutter build appbundle --release`로 빌드해도 **debug 키**로 서명된 AAB가 나온다. 이게 첫 번째 함정이다.

---

## 에러 해결 과정: 삽질의 기록

### 1단계: 기존 keystore 찾기

이전에 네이티브 Android 프로젝트로 앱을 올린 적이 있었다면, 그때 사용한 keystore가 어딘가에 있을 거다. 파일 시스템을 검색했다.

```bash
find ~/project_directory -name "*.jks" -o -name "*.keystore" 2>/dev/null
```

프로젝트 내 `android/secrets/` 디렉토리에서 `release.keystore`를 찾았다. 이 keystore의 SHA1을 확인해봤다.

```bash
keytool -list -v -keystore android/secrets/release.keystore -alias easybracket
```

비밀번호를 모르면 SHA1을 볼 수 없다. 다행히 프로젝트 내 `keystore.properties` 파일에 비밀번호가 있었다.

```bash
keytool -list -v -keystore android/secrets/release.keystore \
  -storepass 'MyPassword123!' -alias easybracket 2>&1 | grep "SHA1"
```

결과:

```
SHA1: 5A:2A:F8:A4:71:76:3B:CC:35:78:33:B1:98:65:8F:24:85:72:AB:87
```

Play Console이 기대하는 SHA1과 정확히 일치했다. 이 keystore로 서명하면 된다.

### 2단계: key.properties 생성

Flutter 공식 문서에서 권장하는 방식은 `android/key.properties` 파일에 keystore 정보를 분리하는 것이다.

```properties
storePassword=MyPassword123!
keyPassword=MyPassword123!
keyAlias=easybracket
storeFile=/absolute/path/to/release.keystore
```

`storeFile`에는 **절대 경로**를 쓰는 게 안전하다. 상대 경로를 쓰면 Gradle의 working directory 기준이라 빌드 환경에 따라 경로가 틀어질 수 있다.

> **주의**: `key.properties`에는 비밀번호가 들어가므로 `.gitignore`에 추가해서 소스 컨트롤에 올리지 않아야 한다.

### 3단계: build.gradle.kts 수정

`android/app/build.gradle.kts`를 수정해야 한다. Flutter의 최신 프로젝트는 Groovy(`.gradle`) 대신 Kotlin DSL(`.gradle.kts`)을 사용한다. 문법이 약간 다르니 주의가 필요하다.

**수정 전 (기본 상태):**

```kotlin
plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    // ...
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")  // ← 문제의 원인
        }
    }
}
```

**수정 후:**

```kotlin
import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    // ...

    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String
            keyPassword = keystoreProperties["keyPassword"] as String
            storeFile = file(keystoreProperties["storeFile"] as String)
            storePassword = keystoreProperties["storePassword"] as String
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}
```

핵심 변경점 세 가지:

1. 파일 상단에 `import java.util.Properties`와 `import java.io.FileInputStream` 추가
2. `android` 블록 바깥에서 `keystoreProperties` 로드
3. `signingConfigs`에 `release` 설정 추가하고, `buildTypes.release`에서 참조

### 4단계: 클린 빌드 (중요!)

여기서 한 번 더 삽질했다. `build.gradle.kts`를 수정한 뒤 바로 `flutter build appbundle`을 실행했는데, **여전히 debug 키로 서명된 AAB**가 나왔다.

원인은 Gradle 빌드 캐시다. 이전 빌드의 서명 정보가 캐시에 남아있어서, 설정을 바꿔도 반영이 안 된 것이다.

```bash
flutter clean
flutter pub get
flutter build appbundle --release
```

`flutter clean`이 핵심이다. 빌드 디렉토리와 캐시를 완전히 제거한 뒤 새로 빌드해야 한다.

### 5단계: 서명 검증

빌드가 끝나면 업로드 전에 서명이 제대로 됐는지 확인하는 게 좋다.

```bash
jarsigner -verify -verbose -certs app-release.aab 2>&1 | grep "CN="
```

출력에서 release keystore의 CN(Common Name)이 보이면 성공이다.

```
X.509, CN=EasyBracket, OU=Mobile, O=EasyBracket, L=Seoul, ST=Seoul, C=KR
```

debug 키로 서명됐다면 `CN=Android Debug` 같은 이름이 나온다.

---

## 패키지명 불일치: 두 번째 함정

서명 문제를 해결하고 다시 업로드했더니 또 다른 에러가 추가로 나왔다.

```
APK 또는 Android App Bundle의 패키지 이름에는
com.easybracket.android이(가) 있어야 합니다.
```

Flutter 프로젝트의 `applicationId`와 Play Console에 등록된 패키지명이 달랐다. Flutter 프로젝트를 새로 만들면서 자동 생성된 패키지명을 그대로 사용한 것이다.

| 위치 | 패키지명 |
|------|---------|
| Play Console (기존 앱) | `com.easybracket.android` |
| Flutter build.gradle.kts | `com.easybracket.easy_bracket_flutter` |

`build.gradle.kts`에서 `applicationId`를 수정해야 한다.

```kotlin
defaultConfig {
    applicationId = "com.easybracket.android"  // Play Console과 일치시킨다
    minSdk = 26
    targetSdk = flutter.targetSdkVersion
    versionCode = flutter.versionCode
    versionName = flutter.versionName
}
```

`applicationId`는 `namespace`와 다르다는 점에 주의하자.

| 속성 | 역할 | 변경 가능 |
|------|------|----------|
| `namespace` | 코드 내 R 클래스, BuildConfig 등의 패키지 | 앱 내부 참조용 |
| `applicationId` | Play Store에서 앱을 식별하는 고유 ID | Play Console 등록과 일치해야 함 |

`namespace`는 Flutter가 자동 생성한 값을 유지하고, `applicationId`만 Play Console과 맞추면 된다.

---

## Groovy vs Kotlin DSL: 문법 차이 정리

인터넷에서 Flutter 서명 설정을 검색하면 Groovy 문법과 Kotlin DSL 문법이 섞여서 나온다. 프로젝트 파일 확장자를 먼저 확인하자.

| 항목 | Groovy (`.gradle`) | Kotlin DSL (`.gradle.kts`) |
|------|--------------------|-----------------------------|
| Properties 로드 | `def keystoreProperties = new Properties()` | `val keystoreProperties = Properties()` |
| 파일 존재 확인 | `if (keystorePropertiesFile.exists())` | 동일 |
| FileInputStream | `new FileInputStream(file)` | `FileInputStream(file)` |
| signingConfig 생성 | `release { keyAlias ... }` | `create("release") { keyAlias = ... }` |
| 값 참조 | `keystoreProperties['keyAlias']` | `keystoreProperties["keyAlias"] as String` |
| storeFile | `file(keystoreProperties['storeFile'])` | `file(keystoreProperties["storeFile"] as String)` |

Kotlin DSL에서는 `as String` 캐스팅이 필요하다. 이걸 빠뜨리면 타입 에러가 난다.

---

## keystore 관련 유용한 keytool 명령어

keystore 문제를 디버깅할 때 자주 쓰는 명령어를 정리했다.

### keystore의 alias와 SHA1 확인

```bash
keytool -list -v -keystore release.keystore -storepass MyPassword
```

`-v` 옵션을 주면 SHA1, SHA256, MD5 지문이 모두 나온다.

### 특정 alias의 인증서만 확인

```bash
keytool -list -v -keystore release.keystore -alias myalias -storepass MyPassword
```

### AAB/APK의 서명 정보 확인

```bash
# AAB 서명 검증
jarsigner -verify -verbose -certs app-release.aab

# APK 서명 검증
apksigner verify --print-certs app-release.apk
```

### 새 keystore 생성 (처음 만드는 경우)

```bash
keytool -genkey -v -keystore upload-keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

`-validity 10000`은 약 27년이다. keystore의 유효기간이 만료되면 앱 업데이트를 올릴 수 없으므로 충분히 길게 설정한다.

---

## 기존 네이티브 → Flutter 마이그레이션 시 체크리스트

기존에 네이티브(Java/Kotlin)로 만든 앱을 Flutter로 다시 만들어서 같은 Play Store 앱으로 업데이트하려는 경우, 다음 사항을 확인해야 한다.

| 항목 | 확인 사항 |
|------|----------|
| **applicationId** | 기존 앱과 동일해야 함 (`build.gradle.kts`의 `applicationId`) |
| **keystore** | 기존 앱 업로드에 사용했던 keystore 파일 |
| **alias** | keystore 내 alias 이름 일치 |
| **versionCode** | 기존 앱의 마지막 versionCode보다 높아야 함 |
| **서명 확인** | `jarsigner -verify`로 SHA1 대조 |

`applicationId`가 다르면 Play Console은 이것을 완전히 다른 앱으로 인식한다. 기존 앱 위에 업데이트를 올리려면 반드시 동일한 `applicationId`를 사용해야 한다.

---

## Play App Signing과 업로드 키 분리

2021년 8월 이후 Google Play에 신규 등록하는 앱은 **Play App Signing**이 자동 적용된다. 이 구조에서는 두 개의 키가 분리되어 운영된다.

```
개발자 PC                    Google Play Console              사용자 기기
┌──────────┐                ┌─────────────────┐              ┌──────────┐
│ AAB 빌드  │  ──업로드키──→ │ 업로드키 검증     │              │          │
│          │                │ 앱 서명키로 재서명 │ ──앱서명키──→ │ APK 설치  │
└──────────┘                └─────────────────┘              └──────────┘
```

업로드 키를 분실하면 Play Console에서 **업로드 키 재설정(Upload Key Reset)**을 요청할 수 있다. Google이 2-3 영업일 내에 처리해준다.

하지만 Play App Signing 이전에 등록된 앱이고 앱 서명 키를 직접 관리하는 경우, 그 키를 잃어버리면 해당 앱은 더 이상 업데이트할 수 없다. keystore 파일을 안전하게 백업해두는 것이 중요하다.

---

## key.properties 보안 관리

`key.properties`에는 keystore 비밀번호가 평문으로 들어간다. 이 파일을 소스 컨트롤에 올리면 안 된다.

### .gitignore 설정

```gitignore
# Android keystore
android/key.properties
android/secrets/
*.keystore
*.jks
```

### CI/CD에서의 처리

GitHub Actions 등 CI 환경에서는 keystore를 base64로 인코딩해서 Secret으로 저장하고, 빌드 시 복원하는 방식을 쓴다.

```yaml
- name: Decode keystore
  run: echo "${{ secrets.KEYSTORE_BASE64 }}" | base64 -d > android/app/release.keystore

- name: Create key.properties
  run: |
    cat > android/key.properties << EOF
    storePassword=${{ secrets.STORE_PASSWORD }}
    keyPassword=${{ secrets.KEY_PASSWORD }}
    keyAlias=${{ secrets.KEY_ALIAS }}
    storeFile=release.keystore
    EOF
```

로컬 개발 환경에서는 macOS Keychain이나 1Password 같은 비밀번호 관리자에 저장해두고, `key.properties`는 로컬에만 두는 게 안전하다.

---

## Makefile로 빌드 자동화

반복되는 빌드 과정은 Makefile로 자동화해두면 편하다.

```makefile
# 빌드 번호 자동 증가
bump:
	@CURRENT=$$(grep "^version:" pubspec.yaml | sed 's/.*+//'); \
	NEXT=$$((CURRENT + 1)); \
	VERSION_NAME=$$(grep "^version:" pubspec.yaml | sed 's/version: \([0-9.]*\)+.*/\1/'); \
	sed -i '' "s/^version: .*/version: $$VERSION_NAME+$$NEXT/" pubspec.yaml; \
	echo "$$VERSION_NAME+$$CURRENT -> $$VERSION_NAME+$$NEXT"

# Android AAB 빌드
build-android:
	flutter build appbundle --release

# Play Store 업로드용 빌드 (번호 증가 + 빌드)
playstore: bump build-android
	@echo "AAB: build/app/outputs/bundle/release/app-release.aab"
	@echo "Upload to: https://play.google.com/console"
```

`make playstore` 한 번이면 빌드 번호 증가 → AAB 빌드가 자동으로 진행된다.

---

## 결론

Flutter AAB 서명 에러는 원인만 알면 해결이 간단하다. 정리하면 이렇다.

1. Flutter 기본 설정은 debug 키로 release 빌드를 서명한다
2. Play Console에 등록된 업로드 키와 동일한 keystore로 서명해야 한다
3. `key.properties` + `build.gradle.kts` 설정으로 release keystore를 연결한다
4. 설정 변경 후 반드시 `flutter clean`으로 캐시를 제거하고 빌드한다
5. 업로드 전 `jarsigner -verify`로 서명을 확인하면 실수를 줄일 수 있다

기존 네이티브 앱을 Flutter로 마이그레이션하는 경우, `applicationId`와 keystore를 반드시 맞춰야 한다는 점도 잊지 말자.
