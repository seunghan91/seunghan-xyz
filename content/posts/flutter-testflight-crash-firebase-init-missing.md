---
title: "Flutter TestFlight 크래시 - Firebase.initializeApp() 누락"
date: 2025-08-16
draft: true
tags: ["Flutter", "Firebase", "iOS", "TestFlight", "크래시"]
description: "firebase_core를 추가했는데 Firebase.initializeApp()을 호출하지 않으면 릴리즈 빌드에서 크래시가 난다. 디버그에서는 괜찮다가 TestFlight에서만 터지는 이유와 해결법."
cover:
  image: "/images/og/flutter-testflight-crash-firebase-init-missing.png"
  alt: "Flutter Testflight Crash Firebase Init Missing"
  hidden: true
---

TestFlight 빌드를 올렸는데 앱을 열자마자 즉시 종료됐다. 시뮬레이터와 디버그 빌드에서는 멀쩡했다. 원인은 `Firebase.initializeApp()` 호출 누락이었다.

Flutter 개발을 하다 보면 디버그 환경에서 완벽하게 동작하던 앱이 TestFlight나 App Store 릴리즈 빌드에서 갑자기 크래시를 일으키는 경우가 있다. 특히 Firebase를 처음 연동할 때 이 함정에 빠지는 경우가 많다. 이 글에서는 그 원인을 깊이 파고들고, 안전하게 초기화하는 패턴과 재발 방지 방법을 정리한다.

---

## 왜 디버그에서는 괜찮고 릴리즈에서만 터지나

`firebase_core`를 추가하면 iOS native Firebase SDK가 CocoaPods를 통해 앱 바이너리에 포함된다. 앱이 실행되면 iOS 런타임이 `GoogleService-Info.plist`를 감지하고 native SDK 내부 초기화를 시작한다.

Flutter Dart 레이어에서 `Firebase.initializeApp()`을 호출하지 않으면 **native SDK ↔ Dart 브리지 사이의 동기화가 깨진다.** 디버그 빌드에서는 실행 속도가 느리고 타이밍 여유가 있어 어물쩡 넘어가는 경우가 있지만, 릴리즈 빌드는 AOT 컴파일로 실행 속도가 빨라지면서 타이밍 차이가 드러나 크래시로 이어진다.

### 더 깊은 원인: JIT vs AOT 컴파일의 차이

Flutter 디버그 빌드는 **JIT(Just-In-Time) 컴파일** 방식으로 동작한다. 코드가 실행되면서 컴파일되기 때문에 각 단계 사이에 자연스러운 지연이 생긴다. native SDK가 초기화를 완료할 시간이 충분하고, 설령 순서가 약간 어긋나도 타이밍이 맞아 넘어가는 경우가 많다.

릴리즈 빌드는 **AOT(Ahead-Of-Time) 컴파일** 방식이다. 배포 전에 이미 기계어로 컴파일이 완료되어 있어서 앱 실행 속도가 훨씬 빠르다. `main()` 함수부터 `runApp()`까지의 흐름이 순식간에 처리된다. 이때 Dart 레이어가 Firebase 서비스에 접근하려 하는데 native 브리지가 아직 준비되지 않은 상태라면, 즉시 `PlatformException` 또는 null dereference로 인한 크래시가 발생한다.

### native 레이어에서 무슨 일이 벌어지나

`GoogleService-Info.plist`가 있으면 Firebase iOS SDK는 앱 실행 시 `+[FIRApp configure]`를 자동으로 호출하려 한다. 하지만 Flutter는 이 초기화가 Dart 코드와 완전히 연동되기를 기대한다. 구체적으로 `Firebase.initializeApp()`이 호출되어야만:

1. Flutter의 MethodChannel이 Firebase native 모듈과 연결된다.
2. `FirebaseApp` 인스턴스가 Dart 레이어에서 접근 가능한 상태가 된다.
3. Firestore, Auth, Crashlytics 등 다른 Firebase 플러그인들이 이 인스턴스를 참조할 수 있다.

이 단계를 건너뛰면 이후에 `FirebaseFirestore.instance` 같은 코드를 실행하는 순간 "No Firebase App '[DEFAULT]' has been created" 오류와 함께 크래시가 난다.

### 왜 TestFlight에서만 발견되나

많은 팀이 이 버그를 TestFlight 단계에서야 발견하는 이유가 있다. 로컬 디버그 빌드에서는 JIT 특성상 타이밍 문제가 숨겨지고, `flutter run` 명령은 여러 초기화 단계를 거쳐 실행되기 때문에 여유 시간이 충분하다. `flutter run --release`로 로컬 릴리즈 빌드를 테스트하면 재현할 수 있지만, 많은 개발자가 이 단계를 생략하고 바로 TestFlight에 올리는 경향이 있다.

---

## 증상 확인: 어떤 크래시 로그가 남나

Xcode Organizer 또는 Firebase Crashlytics에서 다음과 같은 패턴의 로그가 보인다면 이 문제일 가능성이 높다.

```
Fatal Exception: com.firebase.error
Failed to get FirebaseApp instance named '[DEFAULT]'.

Thread 1 Crashed:
0  libswiftCore.dylib           0x... swift_fatalError
1  firebase_core               0x... FlutterFirebaseCorePlugin...
2  Runner                      0x... main (main.m:xx)
```

또는 다음과 같이 더 간단한 형태로 나타나기도 한다.

```
[ERROR:flutter/runtime/dart_vm_initializer.cc] Unhandled Exception:
[core/no-app] No Firebase App '[DEFAULT]' has been created -
call Firebase.initializeApp()
```

이 로그가 보이면 수정 방법은 간단하다.

---

## 수정

```dart
// 잘못된 코드 - Firebase 초기화 없이 다른 서비스 먼저 실행
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SomeService.instance.initialize();
  runApp(const MyApp());
}
```

```dart
// 올바른 코드 - Firebase를 반드시 먼저 초기화
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  await SomeService.instance.initialize();
  runApp(const MyApp());
}
```

`firebase_options.dart`는 FlutterFire CLI로 생성한다.

```bash
dart pub global activate flutterfire_cli
flutterfire configure
```

### WidgetsFlutterBinding.ensureInitialized()는 왜 필요한가

`Firebase.initializeApp()`은 비동기 작업이다. 비동기 Flutter 코드를 `main()` 안에서 실행하려면 Flutter 엔진의 바인딩이 먼저 초기화되어 있어야 한다. `WidgetsFlutterBinding.ensureInitialized()`가 그 역할을 한다. 이 줄 없이 `await`를 사용하면 "Binding has not yet been initialized" 오류가 발생할 수 있다.

순서 요약:
1. `WidgetsFlutterBinding.ensureInitialized()` - Flutter 엔진 바인딩 초기화
2. `Firebase.initializeApp(...)` - Firebase native ↔ Dart 브리지 연결
3. 기타 서비스 초기화 (Crashlytics, Analytics 등)
4. `runApp(const MyApp())` - 앱 UI 시작

---

## 방어적으로 짜기

Firebase 초기화 실패가 앱 전체 크래시로 이어지지 않도록 try-catch로 감싸면 최소한 앱은 뜬다.

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } catch (e) {
    debugPrint('Firebase init failed: $e');
  }

  try {
    await SomeService.instance.initialize();
  } catch (e) {
    debugPrint('SomeService init failed: $e');
  }

  runApp(const MyApp());
}
```

Firebase가 실패해도 `runApp()`까지 도달하고, 크래시 리포트에도 더 의미 있는 스택 트레이스가 남는다.

### Firebase가 이미 초기화된 경우 처리

앱이 hot restart되거나 특정 환경에서 Firebase가 중복 초기화될 수 있다. 이 경우 `FirebaseException`이 발생할 수 있는데, 이미 초기화된 앱을 재사용하는 방식으로 처리할 수 있다.

```dart
Future<void> initializeFirebase() async {
  // 이미 초기화된 앱이 있으면 재사용
  if (Firebase.apps.isNotEmpty) {
    return;
  }

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
}
```

또는 에러 타입을 구분해서 처리할 수 있다.

```dart
try {
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
} on FirebaseException catch (e) {
  if (e.code != 'duplicate-app') {
    rethrow;
  }
  // duplicate-app은 이미 초기화됨 - 무시
}
```

---

## 디버깅 단계별 접근법

TestFlight에서 크래시가 발생했을 때 원인을 빠르게 좁히는 방법이다.

### 1단계: 로컬 릴리즈 빌드 재현 시도

```bash
flutter run --release
```

이 명령으로 로컬에서 릴리즈 빌드를 실행해 크래시가 재현되는지 확인한다. TestFlight까지 올리지 않아도 대부분의 초기화 관련 크래시는 이 단계에서 재현된다.

### 2단계: Xcode 콘솔 로그 확인

Xcode에서 기기를 연결하고 앱을 실행하면 콘솔에 native 레이어의 로그가 출력된다. Firebase 관련 오류 메시지를 여기서 가장 먼저 볼 수 있다.

```
Window → Devices and Simulators → 기기 선택 → Open Console
```

### 3단계: Firebase Crashlytics 확인

앱이 실행 직후 크래시나더라도 Crashlytics가 다음 실행 시 리포트를 전송한다. Firebase Console에서 크래시 로그와 스택 트레이스를 확인할 수 있다.

단, Crashlytics 자체도 Firebase 초기화 이후에 활성화된다. Firebase init이 실패하면 Crashlytics 로그도 남지 않을 수 있다. 이럴 때는 Xcode Organizer의 Crash Logs를 확인한다.

### 4단계: GoogleService-Info.plist 위치 확인

파일이 올바른 위치에 없으면 native SDK가 설정을 읽지 못한다.

```
ios/
  Runner/
    GoogleService-Info.plist  ← 반드시 여기에 있어야 함
    Info.plist
    AppDelegate.swift
```

Xcode에서도 이 파일이 Runner 타겟의 Copy Bundle Resources에 포함되어 있는지 확인해야 한다. 파일이 디렉토리에는 있어도 Xcode 타겟에 추가되지 않은 경우 빌드에 포함되지 않는다.

---

## 예방: CI/CD에서 릴리즈 빌드 자동 검증

이 버그를 TestFlight 이전에 잡으려면 CI 파이프라인에 릴리즈 빌드 스텝을 추가하는 것이 가장 효과적이다.

### GitHub Actions 예시

```yaml
- name: Flutter Release Build (iOS)
  run: |
    flutter build ios --release --no-codesign
  # 빌드 성공 여부만 확인해도 초기화 코드 누락 같은 컴파일/런타임 오류를 잡을 수 있다
```

### flutter_test에서 Firebase 초기화 검증

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/firebase_core_platform_interface.dart';
import 'package:flutter/services.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    // 테스트 환경에서 Firebase mock 설정
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  test('Firebase is initialized before app starts', () async {
    expect(Firebase.apps, isNotEmpty);
  });
}
```

---

## 재발 방지 팁

### 1. main.dart 초기화 순서를 주석으로 문서화

```dart
Future<void> main() async {
  // Step 1: Flutter 엔진 바인딩 초기화 (항상 가장 먼저)
  WidgetsFlutterBinding.ensureInitialized();

  // Step 2: Firebase 초기화 (다른 Firebase 플러그인보다 먼저)
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  // Step 3: Firebase 기반 서비스들
  await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(true);

  // Step 4: 앱 실행
  runApp(const MyApp());
}
```

### 2. 새 Firebase 패키지 추가 시 체크

`pubspec.yaml`에 `firebase_analytics`, `firebase_auth`, `cloud_firestore` 등을 추가할 때마다 반드시 `main()` 초기화 순서를 검토한다. 각 패키지는 `firebase_core`의 초기화가 완료된 상태를 전제로 동작한다.

### 3. 릴리즈 빌드를 TestFlight 올리기 전에 로컬에서 먼저 실행

```bash
# 매 TestFlight 업로드 전 로컬 릴리즈 빌드 확인 루틴
flutter clean
flutter pub get
flutter run --release -d <device-id>
```

---

## 체크리스트

- [ ] `Firebase.initializeApp()`이 `main()`에서 가장 먼저 호출되는가
- [ ] `WidgetsFlutterBinding.ensureInitialized()`가 `Firebase.initializeApp()` 앞에 있는가
- [ ] `GoogleService-Info.plist`가 `ios/Runner/`에 있는가
- [ ] `GoogleService-Info.plist`가 Xcode 타겟의 Copy Bundle Resources에 포함되어 있는가
- [ ] `firebase_options.dart`가 프로젝트에 있는가
- [ ] `DefaultFirebaseOptions.currentPlatform`을 옵션으로 전달하는가
- [ ] `flutter run --release`로 로컬 릴리즈 빌드에서 확인했는가

---

## Key Takeaways

- **디버그 빌드는 거짓말한다.** JIT 컴파일의 느린 실행 속도가 타이밍 버그를 숨긴다. 릴리즈 전 반드시 `flutter run --release`로 검증하라.
- **Firebase.initializeApp()은 선택이 아니다.** `firebase_core`를 pubspec에 추가하는 순간 이 초기화는 필수가 된다. 다른 어떤 서비스보다 먼저 호출되어야 한다.
- **try-catch는 보험이다.** Firebase 초기화를 try-catch로 감싸면 최악의 경우에도 앱이 뜨고, 의미 있는 에러 로그가 남는다.
- **초기화 순서가 아키텍처다.** `main()`의 초기화 순서는 앱 전체 의존성 그래프의 축약판이다. 문서화하고 팀과 공유하라.
- **CI에 릴리즈 빌드 스텝을 추가하라.** TestFlight는 QA 단계가 아니다. 릴리즈 빌드 검증은 CI에서 자동화되어야 한다.
