---
title: "Android AGP 9.0 + Hotwire Native 1.2.5 Build Error Collection"
date: 2025-11-29
draft: true
tags: ["Android", "Hotwire Native", "Kotlin", "AGP", "Gradle", "Build Error"]
description: "A record of resolving cascading build errors from kotlin-android plugin, kotlinOptions, HotwireWebBridgeFragment, and more after upgrading to AGP 9.0"
cover:
  image: "/images/og/android-agp9-hotwire-native-build-errors.png"
  alt: "Android Agp9 Hotwire Native Build Errors"
  hidden: true
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---

While building a Rails + Hotwire Native app for Android, errors poured out from the AGP (Android Gradle Plugin) 9.0 and Hotwire Native 1.2.5 combination. Here's the record of fixing them one by one.

---

## Error 1: `kotlin-android` plugin is no longer required

```
Plugin 'kotlin-android' is no longer required for Kotlin support since AGP 9.0
```

Since AGP 9.0, Kotlin support is built-in and a separate plugin is no longer needed.

```kotlin
// build.gradle.kts — remove
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)   // ← delete
}

// keep only this
plugins {
    alias(libs.plugins.android.application)
}
```

---

## Error 2: `kotlinOptions` unresolved reference

```
Unresolved reference: kotlinOptions
```

`kotlinOptions` was removed in AGP 9.0. Replace with `kotlin { jvmToolchain() }`.

```kotlin
// wrong
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlinOptions {
    jvmTarget = "17"
}

// correct
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    jvmToolchain(17)
}
```

---

## Error 3: `HotwireWebBridgeFragment` unresolved reference

```
Unresolved reference: HotwireWebBridgeFragment
```

Hotwire Native Android 1.2.5 doesn't have `HotwireWebBridgeFragment`. Extend `HotwireWebFragment` instead.

```kotlin
// wrong
class MainFragment : HotwireWebBridgeFragment() {
    override val bridgeComponentFactories = listOf(...)
}

// correct
@HotwireDestinationDeepLink(uri = "myapp://fragment/web")
class MainFragment : HotwireWebFragment()
```

Bridge component registration should be done in the **Application class**, not in the Fragment.

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

## Error 4: `binding?.webView` null

Accessing the WebView via `binding?.webView` returns null. Hotwire Native provides a callback when the WebView is ready.

```kotlin
// wrong
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    super.onViewCreated(view, savedInstanceState)
    binding?.webView?.settings?.javaScriptEnabled = true
}

// correct
override fun onWebViewAttached(webView: HotwireWebView) {
    super.onWebViewAttached(webView)
    webView.settings.javaScriptEnabled = true
}
```

---

## Error 5: `navigator?.navigateUp()` unresolved

```
Unresolved reference: navigateUp
```

`navigateUp()` was removed. Replace with `navigator.pop()`.

```kotlin
// wrong
navigator?.navigateUp()

// correct
navigator.pop()
```

---

## Error 6: Firebase package name mismatch

Adding `applicationIdSuffix = ".debug"` to the `debug` buildType makes the package name (`com.myapp.app.debug`) different from what's registered in Firebase (`com.myapp.app`), causing FCM to stop working.

```kotlin
// This makes the debug build com.myapp.app.debug, which Firebase can't recognize
buildTypes {
    debug {
        applicationIdSuffix = ".debug"   // ← delete
    }
}
```

---

## Final build.gradle.kts

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

## Generating Release Signing Keystore

```bash
keytool -genkey -v \
  -keystore android/app/myapp.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias myapp \
  -storepass yourpassword \
  -keypass yourpassword
```

---

## Build Automation with Makefile

```makefile
apk-debug:
	cd android && ./gradlew assembleDebug

apk-release:
	cd android && ./gradlew assembleRelease

aab-release:
	cd android && ./gradlew bundleRelease
```

- Debug APK: Direct installation by partners (Settings > Security > Allow unknown apps)
- Release AAB: For Play Store submission
