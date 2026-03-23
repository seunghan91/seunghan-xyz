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

While building a Rails + Hotwire Native app for Android, errors poured out from the AGP (Android Gradle Plugin) 9.0 and Hotwire Native 1.2.5 combination. This post documents each error encountered and how it was resolved.

AGP 9.0 was a significant release. It removed several APIs and behaviors that had been deprecated for years, and it tightened Kotlin integration in ways that break projects which were following older tutorials or starter templates. Hotwire Native 1.2.5 made its own API changes on top of that. The result is a cascade of build errors that appear one after another as you fix each one — exactly the kind of situation this post tries to short-circuit.

---

## Background: The Stack

The project uses Rails as the backend server with Turbo Drive for navigation. The Android app is a thin native shell built with Hotwire Native — it renders the Rails views inside a WebView and only adds native UI where it makes sense (tab bars, push notifications, deep links). The build system is Gradle with Kotlin DSL (`build.gradle.kts`), targeting SDK 36 with a minimum of SDK 28.

The upgrade path was roughly: existing AGP 8.x project → AGP 9.0 → discover that Hotwire Native 1.2.5 also changed its public API → fix everything in sequence.

---

## Error 1: `kotlin-android` plugin is no longer required

**Full error message:**
```
Plugin 'kotlin-android' is no longer required for Kotlin support since AGP 9.0
```

**What happened:** Starting with AGP 9.0, Kotlin support is built directly into the Android Gradle Plugin. The separate `kotlin-android` plugin declaration became not just redundant but a hard error — the build will not proceed if it is present.

**The fix:**

```kotlin
// build.gradle.kts — before
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)   // remove this line
}

// build.gradle.kts — after
plugins {
    alias(libs.plugins.android.application)
}
```

Note that `kotlin.serialization` and `google.services` are still declared separately since they are not part of AGP itself. Only the `kotlin.android` plugin entry needs to be removed.

---

## Error 2: `kotlinOptions` unresolved reference

**Full error message:**
```
Unresolved reference: kotlinOptions
```

**What happened:** The `kotlinOptions` DSL block was deprecated in favor of the `kotlin {}` block and was fully removed in AGP 9.0. It no longer compiles. Any project that was setting `jvmTarget` via `kotlinOptions` needs to migrate to `jvmToolchain`.

**Why this matters:** `jvmToolchain` does more than just set the target bytecode version. It tells Gradle to provision and use a specific JDK toolchain for compilation, which makes the build more reproducible across different developer machines and CI environments. Setting `jvmToolchain(17)` covers both `sourceCompatibility`, `targetCompatibility`, and the Kotlin `jvmTarget` in one declaration.

**The fix:**

```kotlin
// before — two separate blocks
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlinOptions {
    jvmTarget = "17"
}

// after — unified toolchain declaration
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    jvmToolchain(17)
}
```

The `compileOptions` block is still needed for Java interop. Keep both.

---

## Error 3: `HotwireWebBridgeFragment` unresolved reference

**Full error message:**
```
Unresolved reference: HotwireWebBridgeFragment
```

**What happened:** Hotwire Native Android 1.2.5 reorganized its public API. The `HotwireWebBridgeFragment` class no longer exists. The correct base class is `HotwireWebFragment`.

Beyond the rename, the API for registering Bridge components changed fundamentally. In older versions you would override `bridgeComponentFactories` inside each Fragment. In 1.2.5, Bridge component registration is centralized in the Application class and happens once at startup.

**The fix — Fragment:**

```kotlin
// before
class MainFragment : HotwireWebBridgeFragment() {
    override val bridgeComponentFactories = listOf(
        BridgeComponentFactory("my-component", ::MyBridgeComponent)
    )
}

// after
@HotwireDestinationDeepLink(uri = "myapp://fragment/web")
class MainFragment : HotwireWebFragment()
```

The `@HotwireDestinationDeepLink` annotation is required for the fragment to be registered as a valid navigation destination. Without it, the Hotwire Navigator cannot route to this fragment.

**The fix — Application class:**

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

Register all Bridge component factories here. The `Hotwire.registerBridgeComponents()` call accepts vararg factories, so you can list multiple components in a single call.

---

## Error 4: `binding?.webView` returns null

**What happened:** This is not a compile error but a runtime crash. After the Fragment migration, attempts to access the WebView via the view binding object return null, even inside `onViewCreated`. The WebView is not yet attached to the Fragment's view hierarchy at that point in the lifecycle.

Hotwire Native manages the WebView lifecycle separately from the Fragment lifecycle. The WebView is created and attached asynchronously after the Fragment's view is created. Accessing it before attachment returns null.

**The correct pattern:**

```kotlin
// before — crashes at runtime
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    super.onViewCreated(view, savedInstanceState)
    binding?.webView?.settings?.javaScriptEnabled = true  // null here
}

// after — guaranteed to have a live WebView reference
override fun onWebViewAttached(webView: HotwireWebView) {
    super.onWebViewAttached(webView)
    webView.settings.javaScriptEnabled = true
}
```

`onWebViewAttached()` is the correct lifecycle hook for configuring WebView settings. Any WebView configuration — JavaScript, DOM storage, file access, user agent — should be placed here, not in `onViewCreated`.

---

## Error 5: `navigator?.navigateUp()` unresolved reference

**Full error message:**
```
Unresolved reference: navigateUp
```

**What happened:** The `navigateUp()` method was removed from the Navigator API in Hotwire Native 1.2.5. The replacement is `navigator.pop()`.

The behavioral difference is subtle but intentional. `navigateUp()` was tied to the Android Navigation Component's concept of "up" navigation (going to the parent destination in the navigation graph). `pop()` is simpler: it pops the current destination off the Hotwire back stack. For most Hotwire Native apps where navigation is driven by the server, `pop()` is the correct primitive.

**The fix:**

```kotlin
// before
navigator?.navigateUp()

// after
navigator.pop()
```

Note that `navigator` is no longer nullable in 1.2.5 when accessed from within a `HotwireWebFragment`. The safe-call operator (`?.`) is unnecessary and the linter will warn about it.

---

## Error 6: Firebase package name mismatch after adding `applicationIdSuffix`

**What happened:** This error does not produce a build failure. The build succeeds, but FCM push notifications silently stop working on debug builds. The cause is that adding `applicationIdSuffix = ".debug"` to the debug buildType changes the installed package name from `com.myapp.app` to `com.myapp.app.debug`. Firebase only recognizes the package name that was registered in the Firebase console.

This error is easy to miss because everything looks fine during development — the app installs, the WebView loads, authentication works. Push notifications are only tested later, and the root cause (the suffix) is not obvious.

**The fix:**

```kotlin
// before — debug builds get com.myapp.app.debug, Firebase does not recognize it
buildTypes {
    debug {
        applicationIdSuffix = ".debug"   // remove this
        buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
    }
}

// after — package name stays consistent with Firebase registration
buildTypes {
    debug {
        buildConfigField("String", "BASE_URL", "\"https://my-server.com\"")
    }
}
```

If you genuinely need to install debug and release builds side by side on the same device, the correct approach is to register both `com.myapp.app` and `com.myapp.app.debug` as separate apps in Firebase and include both `google-services.json` configurations. For most projects this is unnecessary overhead — a single package name for all build types is simpler.

---

## Final build.gradle.kts

After all the fixes above, the complete `build.gradle.kts` looks like this:

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

Notable points: no `kotlin.android` plugin, no `kotlinOptions` block, no `applicationIdSuffix` on debug. The `buildConfig = true` feature flag is required to use `BuildConfig.BASE_URL` in Kotlin code — it is disabled by default in AGP 8+ and must be explicitly enabled.

---

## Generating a Release Signing Keystore

The release build requires a keystore file. Generate one with `keytool`:

```bash
keytool -genkey -v \
  -keystore android/app/myapp.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias myapp \
  -storepass yourpassword \
  -keypass yourpassword
```

Store the `.jks` file and its passwords securely. For CI/CD pipelines, the typical approach is to base64-encode the `.jks` file and store it as an environment secret, then decode it at build time. Never commit the raw keystore or its passwords to version control.

---

## Build Automation with Makefile

With the Gradle setup in place, a simple Makefile target set makes it easy to trigger the right build from the project root:

```makefile
apk-debug:
	cd android && ./gradlew assembleDebug

apk-release:
	cd android && ./gradlew assembleRelease

aab-release:
	cd android && ./gradlew bundleRelease
```

- **Debug APK** (`assembleDebug`): Produces an unsigned APK for direct installation. Share with testers via "Settings > Security > Install unknown apps".
- **Release APK** (`assembleRelease`): Produces a signed APK. Useful for ad-hoc distribution outside the Play Store.
- **Release AAB** (`bundleRelease`): Produces an Android App Bundle for Play Store submission. The Play Store requires AAB format for new apps.

For the Hotwire Native workflow, the debug APK is the primary artifact during development — install it on a physical device, point `BASE_URL` at your local Rails server (via ngrok or a local network address), and you have a live development loop.

---

## Key Takeaways

- **AGP 9.0 removes `kotlin-android` plugin** — delete the line entirely; Kotlin support is now built-in.
- **`kotlinOptions` is gone** — replace with `kotlin { jvmToolchain(17) }`, which also covers `compileOptions` semantically.
- **`HotwireWebBridgeFragment` no longer exists in 1.2.5** — use `HotwireWebFragment` and move Bridge component registration to the Application class.
- **`binding?.webView` is always null** — configure WebView settings inside `onWebViewAttached()`, not `onViewCreated()`.
- **`navigateUp()` is removed** — call `navigator.pop()` instead; `navigator` is non-nullable in 1.2.5.
- **`applicationIdSuffix` breaks Firebase FCM** — avoid it on debug builds unless you register the suffixed package name in Firebase separately.
- **Enable `buildConfig = true`** explicitly in `buildFeatures` or `BuildConfig` fields will not compile.
