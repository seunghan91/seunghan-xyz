---
title: "Flutter iOS Deployment Debugging Collection: 5 Build Errors + Dark Mode Hardcoding + Logout Bug"
date: 2025-11-01
draft: false
tags: ["Flutter", "iOS", "TestFlight", "Dart", "Retrofit", "Freezed", "build_runner", "Dark Mode", "Makefile"]
description: "Code generation failures (Retrofit syntax errors, Freezed sealed class), missing file restoration, TestFlight deployment without Xcode account, dark mode color hardcoding, and logout token deletion bug — all in one day."
cover:
  image: "/images/og/flutter-ios-build-dark-mode-logout-debugging.png"
  alt: "Flutter Ios Build Dark Mode Logout Debugging"
  hidden: true
---


I was trying to push a build when multiple issues hit at once. The code generator failed, files were missing, the build number got rejected, UI had hardcoded dark mode colors, and logout wasn't clearing tokens. Going through them one by one.

---

## 1. Retrofit Optional Parameter Syntax Error -> `.g.dart` Generation Failure

### Symptoms

When running `dart run build_runner build`, some API service files produce:

```
Expected to find ')'
```

### Cause

Wrong placement of optional parameters (`{}`) in Retrofit abstract methods.

```dart
// Wrong syntax — comma after closing brace
Future<Response> getItems(
  @Path('id') String id,
  {@Query('type') String? type},  // <- this is wrong
);

// Correct syntax — open { right after the last positional parameter
Future<Response> getItems(
  @Path('id') String id, {
  @Query('type') String? type,
});
```

In Dart syntax, optional parameters must open `{` right after the last positional parameter. Closing with `},` followed by a comma makes the parser try to recognize it as the next argument and fail.

### Solution

Fix all files with this pattern and re-run:

```bash
dart run build_runner build --delete-conflicting-outputs
```

---

## 2. Freezed 3.x + Dart 3.10: `sealed class` Required

### Symptoms

During `dart analyze`:

```
Missing concrete implementations of ...
```

### Cause

With Freezed 3.x and Dart 3.10+, classes annotated with `@freezed` must be declared as `sealed class`. Declaring them as regular `class` leaves `_$Mixin`'s abstract getters without implementations, causing errors.

```dart
// Old way
@freezed
class MyModel with _$MyModel { ... }

// Freezed 3.x + Dart 3.10
@freezed
sealed class MyModel with _$MyModel { ... }
```

`sealed class` is a keyword introduced in Dart 3.0 that also enables exhaustive checking in switch statements.

---

## 3. Deleted File Still Referenced in Generated Code Causes Build Failure

### Symptoms

During Flutter build:

```
Error when reading 'lib/core/services/place/place_service.dart': No such file or directory
Couldn't find constructor 'SomePage'
```

### Cause

The source file was deleted, but the code generator's `injection.config.dart` or router was still referencing it. Generated files (`.g.dart`, `.config.dart`) remain from the last successful build, creating a mismatch with actual source files.

### Solution

Backtrack the references and regenerate. The key steps:

1. Check import paths in `injection.config.dart` -> identify which classes are needed
2. Verify constructor signatures from usage sites (router, widgets)
3. Write a minimal stub or full implementation

For example, if used in a router as `const SomePage()`, only a default constructor is needed; if it's a service class, both interface and implementation are required.

---

## 4. TestFlight Deployment Without Xcode Account (`-allowProvisioningUpdates` + API Key)

### Symptoms

When running `flutter build ipa`:

```
No accounts found in Xcode
```

Auto-signing fails if no Apple account is logged into Xcode.

### Cause

`flutter build ipa` internally uses Xcode's auto-signing, which requires an account registered in Xcode.

### Solution

Compile only Dart with `flutter build ios --no-codesign`, then pass the App Store Connect API Key directly to `xcodebuild` for signing and distribution.

```makefile
build-ipa:
    # Step 1: Dart compile only (no signing)
    flutter build ios --release --no-codesign

    # Step 2: Xcode signs directly with API Key
    xcodebuild -workspace ios/Runner.xcworkspace \
        -scheme Runner -configuration Release \
        -archivePath build/ios/archive/Runner.xcarchive \
        archive \
        DEVELOPMENT_TEAM=XXXXXXXXXX \
        -allowProvisioningUpdates \
        -authenticationKeyID $(API_KEY) \
        -authenticationKeyIssuerID $(API_ISSUER) \
        -authenticationKeyPath $(API_KEY_PATH)

    # Step 3: IPA export
    xcodebuild -exportArchive \
        -archivePath build/ios/archive/Runner.xcarchive \
        -exportPath build/ios/ipa \
        -exportOptionsPlist ios/ExportOptions.plist \
        -allowProvisioningUpdates \
        -authenticationKeyID $(API_KEY) \
        -authenticationKeyIssuerID $(API_ISSUER) \
        -authenticationKeyPath $(API_KEY_PATH)
```

The API Key file (`AuthKey_XXXXXX.p8`) can be issued from App Store Connect -> Users and Access -> Keys and placed in `~/.appstoreconnect/private_keys/`.

---

## 5. TestFlight Build Number Rules

### Symptoms

On second upload:

```
The bundle version must be higher than the previously uploaded version: '5'
```

### Rules

- **Re-uploading within the same version**: Increment the build number (`1.0.1+1` -> `1.0.1+2`)
- **Bumping the version itself**: Build number can reset to 1 (`1.0.2+1`)
- Within the same short version string (`CFBundleShortVersionString`), build numbers must monotonically increase
- When the short version string changes, build numbers can restart from 1

In Flutter, `version: 1.0.1+2` in `pubspec.yaml` maps to `CFBundleShortVersionString=1.0.1`, `CFBundleVersion=2`.

### Makefile Automation

Manually incrementing is error-prone, so automate it in the Makefile:

```makefile
PUBSPEC      = pubspec.yaml
CURRENT_VER  := $(shell grep '^version:' $(PUBSPEC) | sed 's/version: //')
VERSION_NAME := $(shell echo $(CURRENT_VER) | cut -d'+' -f1)
BUILD_NUMBER := $(shell echo $(CURRENT_VER) | cut -d'+' -f2)
NEXT_BUILD   := $(shell echo $$(($(BUILD_NUMBER) + 1)))

bump-build:
    @echo "Build number up: $(CURRENT_VER) -> $(VERSION_NAME)+$(NEXT_BUILD)"
    @sed -i '' 's/^version: .*/version: $(VERSION_NAME)+$(NEXT_BUILD)/' $(PUBSPEC)

build-ipa: bump-build
    # ... build commands
```

A single `make build-testflight` chains build number increment -> build -> upload automatically.

---

## 6. Dark Mode Color Hardcoding -> Text Invisible in Light Mode

### Symptoms

Cards on a certain tab have a black background with black text -> text is invisible.

### Cause

Colors were used as fixed values regardless of light/dark mode:

```dart
// Dark-only colors always used
color: AppColors.surfaceDark,    // Color(0xFF1A1A1A) — nearly black
style: TextStyle(color: AppColors.textPrimary), // Color(0xFF1C1C1E) — nearly black
```

Placing `textPrimary` (nearly black text) on `surfaceDark` (black card) makes both dark and unreadable.

Simultaneously, `ThemeMode.light` was hardcoded in `main.dart`, ignoring system dark mode:

```dart
// Always forced light mode
themeMode: ThemeMode.light,
```

### Solution

**1. Change ThemeMode to follow system:**

```dart
// Reflect system settings
themeMode: ThemeMode.system,
```

**2. Replace colors with adaptive methods:**

```dart
// Return colors matching current theme
color: AppColors.surfaceOf(context),
style: TextStyle(color: AppColors.textPrimaryOf(context)),
border: Border.all(color: AppColors.borderOf(context)),
```

The helper methods that take `context` internally check `Theme.of(context).brightness` to select dark/light versions:

```dart
static Color surfaceOf(BuildContext context) {
  return isDarkMode(context) ? surfaceDark : surfaceLight;
}

static bool isDarkMode(BuildContext context) {
  return Theme.of(context).brightness == Brightness.dark;
}
```

---

## 7. Logout Button Not Clearing Tokens

### Symptoms

After logout, restarting the app or navigating to the login screen automatically bounces back to the main screen.

### Cause

The logout button only navigated screens without clearing tokens or signing out of social logins:

```dart
// Only screen navigation, tokens remain
onPressed: () {
  Navigator.pop(ctx);
  context.go('/login');
},
```

The router checks auth status with `TokenStorage.hasToken()`. If the token remains, it redirects from the login screen back to main.

### Solution

A `logout` event must be dispatched to `AuthBloc`. `AuthRepository.logout()` handles API call -> social logout (Google/Apple) -> token deletion in sequence:

```dart
// Token deletion + social logout processed before screen navigation
onPressed: () {
  Navigator.pop(ctx);
  context.read<AuthBloc>().add(const AuthEvent.logout());
  context.go('/login');
},
```

BLoC logout handler:

```dart
logout: (e) async {
  emit(const AuthState.loading());
  try {
    await _authRepository.logout(); // API + social + token deletion
    emit(const AuthState.unauthenticated());
  } catch (e) {
    emit(AuthState.error(e.toString()));
  }
},
```

---

## Summary

| Problem | Cause | Key Solution |
|------|------|----------|
| `build_runner` failure | Retrofit optional parameter `},` syntax error | `id, {` + `param,` + `}` order |
| `Missing concrete implementations` | Freezed 3.x requires `class` -> `sealed class` | `sealed class` keyword |
| Missing file build failure | Source deleted but generated code still references it | Backtrack references and regenerate file |
| No Xcode account | `flutter build ipa` requires Xcode account | `--no-codesign` + `xcodebuild` + API Key |
| Build number rejection | Same number re-uploaded | Build number can reset to 1 on version bump |
| Text invisible | Dark color hardcoding + `ThemeMode.light` forced | `ThemeMode.system` + adaptive colors |
| Logout ineffective | Only screen navigation, tokens not cleared | Dispatching `AuthBloc.logout()` is required |
