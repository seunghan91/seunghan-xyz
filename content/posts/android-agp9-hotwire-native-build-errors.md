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
---

Rails + Hotwire Native 앱을 Android로 빌드하다가 AGP(Android Gradle Plugin) 9.0과 Hotwire Native 1.2.5 조합에서 오류가 쏟아졌다. 하나씩 해결한 기록.

---

## 오류 1: `kotlin-android` plugin is no longer required

```
Plugin 'kotlin-android' is no longer required for Kotlin support since AGP 9.0
```

AGP 9.0부터 Kotlin 지원이 내장되어 별도 플러그인이 필요 없다.

```kotlin
// build.gradle.kts — 제거
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)   // ← 삭제
}

// 이것만 남김
plugins {
    alias(libs.plugins.android.application)
}
```

---

## 오류 2: `kotlinOptions` unresolved reference

```
Unresolved reference: kotlinOptions
```

AGP 9.0에서 `kotlinOptions`가 제거됐다. `kotlin { jvmToolchain() }`으로 교체.

```kotlin
// 잘못됨
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlinOptions {
    jvmTarget = "17"
}

// 올바름
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    jvmToolchain(17)
}
```

---

## 오류 3: `HotwireWebBridgeFragment` unresolved reference

```
Unresolved reference: HotwireWebBridgeFragment
```

Hotwire Native Android 1.2.5에는 `HotwireWebBridgeFragment`가 없다. `HotwireWebFragment`를 상속하면 된다.

```kotlin
// 잘못됨
class MainFragment : HotwireWebBridgeFragment() {
    override val bridgeComponentFactories = listOf(...)
}

// 올바름
@HotwireDestinationDeepLink(uri = "myapp://fragment/web")
class MainFragment : HotwireWebFragment()
```

Bridge 컴포넌트 등록은 Fragment가 아니라 **Application 클래스**에서 한다.

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

---

## 오류 4: `binding?.webView` null

WebView 접근을 `binding?.webView`로 하면 null이 떨어진다. Hotwire Native는 WebView 준비 완료 시 콜백을 제공한다.

```kotlin
// 잘못됨
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    super.onViewCreated(view, savedInstanceState)
    binding?.webView?.settings?.javaScriptEnabled = true
}

// 올바름
override fun onWebViewAttached(webView: HotwireWebView) {
    super.onWebViewAttached(webView)
    webView.settings.javaScriptEnabled = true
}
```

---

## 오류 5: `navigator?.navigateUp()` unresolved

```
Unresolved reference: navigateUp
```

`navigateUp()`이 제거됐다. `navigator.pop()`으로 교체.

```kotlin
// 잘못됨
navigator?.navigateUp()

// 올바름
navigator.pop()
```

---

## 오류 6: Firebase 패키지명 불일치

`debug` buildType에 `applicationIdSuffix = ".debug"`를 붙이면 Firebase에 등록한 패키지명(`com.myapp.app`)과 달라져서 FCM이 동작하지 않는다.

```kotlin
// 이렇게 하면 debug 빌드가 com.myapp.app.debug가 되어 Firebase 인식 못함
buildTypes {
    debug {
        applicationIdSuffix = ".debug"   // ← 삭제
    }
}
```

---

## 최종 build.gradle.kts

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

---

## 릴리즈 서명 키스토어 생성

```bash
keytool -genkey -v \
  -keystore android/app/myapp.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias myapp \
  -storepass yourpassword \
  -keypass yourpassword
```

---

## Makefile로 빌드 자동화

```makefile
apk-debug:
	cd android && ./gradlew assembleDebug

apk-release:
	cd android && ./gradlew assembleRelease

aab-release:
	cd android && ./gradlew bundleRelease
```

- Debug APK → 동업자 직접 설치 (설정 > 보안 > 알 수 없는 앱 허용)
- Release AAB → Play Store 제출용
