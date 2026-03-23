---
title: "Android AGP 9.0 + Hotwire Native 1.2.5 빌드 오류 모음"
date: 2025-11-29
draft: true
tags: ["Android", "Hotwire Native", "Kotlin", "AGP", "Gradle", "빌드 오류"]
description: "AGP 9.0으로 올라가면서 kotlin-android 플러그인, kotlinOptions, HotwireWebBridgeFragment 등 줄줄이 터지는 빌드 오류 해결 기록"
cover:
  image: "/images/og/android-agp9-hotwire-native-build-errors.png"
  alt: "Android Agp9 Hotwire Native Build Errors"
  hidden: true
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

Rails + Hotwire Native 앱을 Android로 빌드하다가 AGP(Android Gradle Plugin) 9.0과 Hotwire Native 1.2.5 조합에서 오류가 쏟아졌다. 하나씩 해결한 기록을 남긴다.

AGP 9.0은 꽤 큰 변경이었다. 몇 년간 deprecated 상태였던 API들이 이번 버전에서 완전히 제거됐고, Kotlin 통합 방식도 바뀌었다. 오래된 튜토리얼이나 스타터 템플릿을 기반으로 만든 프로젝트라면 한 번에 여러 오류가 터지는 상황을 마주하게 된다. 게다가 Hotwire Native 1.2.5도 독자적인 API 변경을 가져왔기 때문에, 두 업그레이드가 겹치면 오류가 연쇄적으로 발생한다. 이 글은 그 연쇄를 짧게 끊어주기 위해 작성했다.

---

## 배경: 프로젝트 구성

백엔드는 Rails, 프론트는 Turbo Drive로 네비게이션을 처리하는 구조다. Android 앱은 Hotwire Native로 만든 얇은 네이티브 셸로, Rails가 렌더링한 화면을 WebView 안에서 표시하고, 탭바나 푸시 알림, 딥링크처럼 네이티브 처리가 필요한 부분만 Kotlin으로 구현한다. 빌드 시스템은 Kotlin DSL(`build.gradle.kts`)을 사용하며, compileSdk 36, minSdk 28을 기준으로 한다.

업그레이드 경로는 대략 이렇다: 기존 AGP 8.x 프로젝트 → AGP 9.0으로 버전 올리기 → Hotwire Native 1.2.5도 공개 API가 바뀐 것 확인 → 오류를 순서대로 해결.

---

## 오류 1: `kotlin-android` plugin is no longer required

**전체 오류 메시지:**
```
Plugin 'kotlin-android' is no longer required for Kotlin support since AGP 9.0
```

**무슨 일이 일어난 건가:** AGP 9.0부터 Kotlin 지원이 Android Gradle Plugin 안에 기본 내장됐다. 별도의 `kotlin-android` 플러그인 선언은 이제 중복일 뿐 아니라 하드 에러가 된다. 해당 라인이 있으면 빌드 자체가 시작되지 않는다.

**수정 방법:**

```kotlin
// build.gradle.kts — 수정 전
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)   // 이 줄 삭제
}

// build.gradle.kts — 수정 후
plugins {
    alias(libs.plugins.android.application)
}
```

`kotlin.serialization`이나 `google.services`는 AGP 자체와 무관한 별도 플러그인이므로 그대로 남긴다. `kotlin.android` 항목만 제거하면 된다.

---

## 오류 2: `kotlinOptions` unresolved reference

**전체 오류 메시지:**
```
Unresolved reference: kotlinOptions
```

**무슨 일이 일어난 건가:** `kotlinOptions` DSL 블록이 AGP 9.0에서 완전히 제거됐다. 더 이상 컴파일되지 않는다. `jvmTarget`을 `kotlinOptions`로 설정하던 프로젝트는 모두 `kotlin {}` 블록으로 마이그레이션해야 한다.

**왜 `jvmToolchain`이 더 나은가:** 단순히 타겟 바이트코드 버전을 지정하는 것 이상이다. Gradle에게 컴파일에 사용할 JDK 툴체인을 프로비저닝하고 사용하도록 지시하기 때문에, 개발자 머신과 CI 환경 사이의 JDK 버전 차이로 인한 재현 불가능한 빌드 문제를 방지할 수 있다. `jvmToolchain(17)` 하나로 `sourceCompatibility`, `targetCompatibility`, Kotlin의 `jvmTarget`이 모두 커버된다.

**수정 방법:**

```kotlin
// 수정 전 — 두 개의 분리된 블록
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlinOptions {
    jvmTarget = "17"
}

// 수정 후 — 통합된 툴체인 선언
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    jvmToolchain(17)
}
```

Java 상호운용성을 위해 `compileOptions` 블록은 그대로 유지한다. 두 블록 모두 남긴다.

---

## 오류 3: `HotwireWebBridgeFragment` unresolved reference

**전체 오류 메시지:**
```
Unresolved reference: HotwireWebBridgeFragment
```

**무슨 일이 일어난 건가:** Hotwire Native Android 1.2.5에서 공개 API가 재편됐다. `HotwireWebBridgeFragment` 클래스가 더 이상 존재하지 않는다. 올바른 기반 클래스는 `HotwireWebFragment`다.

클래스 이름 변경 외에도 Bridge 컴포넌트 등록 방식 자체가 바뀌었다. 이전 버전에서는 각 Fragment 안에서 `bridgeComponentFactories`를 오버라이드했다. 1.2.5에서는 Bridge 컴포넌트 등록이 Application 클래스로 중앙화되어 앱 시작 시 한 번만 실행된다.

**수정 방법 — Fragment:**

```kotlin
// 수정 전
class MainFragment : HotwireWebBridgeFragment() {
    override val bridgeComponentFactories = listOf(
        BridgeComponentFactory("my-component", ::MyBridgeComponent)
    )
}

// 수정 후
@HotwireDestinationDeepLink(uri = "myapp://fragment/web")
class MainFragment : HotwireWebFragment()
```

`@HotwireDestinationDeepLink` 어노테이션은 해당 Fragment를 유효한 네비게이션 목적지로 등록하기 위해 필수다. 없으면 Hotwire Navigator가 이 Fragment로 라우팅하지 못한다.

**수정 방법 — Application 클래스:**

```kotlin
class MainApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        Hotwire.registerBridgeComponents(
            BridgeComponentFactory("my-component", ::MyBridgeComponent)
        )
    }
}
```

모든 Bridge 컴포넌트 팩토리를 여기서 등록한다. `Hotwire.registerBridgeComponents()`는 vararg를 받으므로, 여러 컴포넌트를 단일 호출로 나열할 수 있다.

---

## 오류 4: `binding?.webView` null

**무슨 일이 일어난 건가:** 이건 컴파일 오류가 아니라 런타임 크래시다. Fragment 마이그레이션 이후 뷰 바인딩 객체로 WebView에 접근하면 null이 반환된다. `onViewCreated` 시점에도 마찬가지다. WebView가 그 시점에는 Fragment의 뷰 계층에 아직 붙지 않았기 때문이다.

Hotwire Native는 WebView 생명주기를 Fragment 생명주기와 분리해서 관리한다. WebView는 Fragment의 뷰가 생성된 후 비동기적으로 생성되고 붙는다. 붙기 전에 접근하면 null이 반환된다.

**올바른 패턴:**

```kotlin
// 수정 전 — 런타임 크래시
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    super.onViewCreated(view, savedInstanceState)
    binding?.webView?.settings?.javaScriptEnabled = true  // 여기서 null
}

// 수정 후 — 살아있는 WebView 참조 보장
override fun onWebViewAttached(webView: HotwireWebView) {
    super.onWebViewAttached(webView)
    webView.settings.javaScriptEnabled = true
}
```

`onWebViewAttached()`가 WebView 설정을 위한 올바른 생명주기 훅이다. JavaScript 활성화, DOM 스토리지, 파일 접근, 사용자 에이전트 등 WebView 관련 설정은 모두 `onViewCreated`가 아닌 여기에 넣어야 한다.

---

## 오류 5: `navigator?.navigateUp()` unresolved reference

**전체 오류 메시지:**
```
Unresolved reference: navigateUp
```

**무슨 일이 일어난 건가:** `navigateUp()` 메서드가 Hotwire Native 1.2.5의 Navigator API에서 제거됐다. 대체재는 `navigator.pop()`이다.

동작 차이는 미묘하지만 의도적이다. `navigateUp()`은 Android Navigation Component의 "위로" 네비게이션 개념(네비게이션 그래프의 부모 목적지로 이동)과 연결되어 있었다. `pop()`은 더 단순하다: Hotwire 백스택에서 현재 목적지를 꺼낸다. 네비게이션이 서버에 의해 구동되는 대부분의 Hotwire Native 앱에서는 `pop()`이 올바른 기본 연산이다.

**수정 방법:**

```kotlin
// 수정 전
navigator?.navigateUp()

// 수정 후
navigator.pop()
```

1.2.5에서는 `HotwireWebFragment` 내부에서 접근하는 `navigator`가 더 이상 nullable이 아니다. 안전 호출 연산자(`?.`)가 불필요하며 린터가 경고를 낸다.

---

## 오류 6: Firebase 패키지명 불일치

**무슨 일이 일어난 건가:** 이 오류는 빌드 실패를 만들지 않는다. 빌드는 성공하지만 debug 빌드에서 FCM 푸시 알림이 조용히 동작을 멈춘다. 원인은 debug buildType에 `applicationIdSuffix = ".debug"`를 추가하면 설치되는 패키지명이 `com.myapp.app`에서 `com.myapp.app.debug`로 바뀌기 때문이다. Firebase는 콘솔에 등록된 패키지명만 인식한다.

이 오류는 놓치기 쉽다. 개발 중에는 모든 게 정상으로 보이기 때문이다. 앱이 설치되고, WebView가 로드되고, 인증도 동작한다. 푸시 알림은 나중에 테스트되고, 근본 원인(suffix)이 즉각적으로 명확하지 않다.

**수정 방법:**

```kotlin
// 수정 전 — debug 빌드가 com.myapp.app.debug가 되어 Firebase가 인식하지 못함
buildTypes {
    debug {
        applicationIdSuffix = ".debug"   // 삭제
        buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
    }
}

// 수정 후 — Firebase 등록 패키지명과 일치
buildTypes {
    debug {
        buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
    }
}
```

같은 기기에 debug와 release 빌드를 동시에 설치해야 하는 경우라면, Firebase에 `com.myapp.app`과 `com.myapp.app.debug` 두 앱을 각각 등록하고 두 개의 `google-services.json` 구성을 포함하는 것이 올바른 접근이다. 대부분의 프로젝트에서는 이게 불필요한 복잡도이므로, 모든 빌드 타입에 단일 패키지명을 사용하는 게 더 단순하다.

---

## 최종 build.gradle.kts

위의 수정을 모두 반영한 완전한 `build.gradle.kts`는 다음과 같다:

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.google.services)
}

android {
    namespace = "com.myapp.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.myapp.app"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        create("release") {
            storeFile = file("myapp.jks")
            storePassword = "password"
            keyAlias = "myapp"
            keyPassword = "password"
        }
    }

    buildTypes {
        debug {
            buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        jvmToolchain(17)
    }

    buildFeatures {
        buildConfig = true
    }
}
```

주요 포인트: `kotlin.android` 플러그인 없음, `kotlinOptions` 블록 없음, debug에 `applicationIdSuffix` 없음. `buildConfig = true` 피처 플래그는 Kotlin 코드에서 `BuildConfig.BASE_URL`을 사용하기 위해 필수다. AGP 8+에서 기본 비활성화로 바뀌었으므로 명시적으로 활성화해야 한다.

---

## 릴리즈 서명 키스토어 생성

릴리즈 빌드에는 키스토어 파일이 필요하다. `keytool`로 생성한다:

```bash
keytool -genkey -v \
  -keystore android/app/myapp.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias myapp \
  -storepass yourpassword \
  -keypass yourpassword
```

`.jks` 파일과 비밀번호는 안전하게 보관한다. CI/CD 파이프라인에서는 `.jks` 파일을 base64로 인코딩해서 환경 시크릿으로 저장하고, 빌드 시점에 디코딩하는 방식이 일반적이다. 키스토어 파일이나 비밀번호를 버전 관리에 커밋하면 절대 안 된다.

---

## Makefile로 빌드 자동화

Gradle 설정이 완료되면, 프로젝트 루트에서 간단한 Makefile 타겟으로 필요한 빌드를 트리거할 수 있다:

```makefile
apk-debug:
	cd android && ./gradlew assembleDebug

apk-release:
	cd android && ./gradlew assembleRelease

aab-release:
	cd android && ./gradlew bundleRelease
```

- **Debug APK** (`assembleDebug`): 서명되지 않은 APK를 생성한다. 테스터에게 직접 배포할 수 있다. "설정 > 보안 > 알 수 없는 앱 허용"으로 설치.
- **Release APK** (`assembleRelease`): 서명된 APK를 생성한다. Play Store 외부의 애드혹 배포에 유용하다.
- **Release AAB** (`bundleRelease`): Play Store 제출용 Android App Bundle을 생성한다. Play Store는 신규 앱에 AAB 형식을 요구한다.

Hotwire Native 개발 워크플로우에서는 debug APK가 핵심 산출물이다. 실기기에 설치하고 `BASE_URL`을 ngrok이나 로컬 네트워크 주소로 설정하면, 로컬 Rails 서버에 연결된 라이브 개발 루프를 만들 수 있다.

---

## 핵심 정리

- **AGP 9.0은 `kotlin-android` 플러그인을 제거한다** — 해당 라인 자체를 삭제한다. Kotlin 지원은 이제 내장이다.
- **`kotlinOptions`가 사라졌다** — `kotlin { jvmToolchain(17) }`으로 교체한다. `compileOptions`의 역할도 의미상 커버된다.
- **`HotwireWebBridgeFragment`는 1.2.5에 더 이상 없다** — `HotwireWebFragment`를 사용하고, Bridge 컴포넌트 등록은 Application 클래스로 옮긴다.
- **`binding?.webView`는 항상 null이다** — WebView 설정은 `onViewCreated()`가 아닌 `onWebViewAttached()` 안에서 한다.
- **`navigateUp()`이 제거됐다** — `navigator.pop()`을 호출한다. 1.2.5에서 `navigator`는 non-nullable이다.
- **`applicationIdSuffix`는 Firebase FCM을 망가뜨린다** — debug 빌드에는 사용하지 않는다. 필요하다면 Firebase에 suffix 포함 패키지명을 별도 앱으로 등록한다.
- **`buildConfig = true`를 명시적으로 활성화한다** — 없으면 `BuildConfig` 필드가 컴파일되지 않는다.
