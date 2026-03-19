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

---

## 왜 디버그에서는 괜찮고 릴리즈에서만 터지나

`firebase_core`를 추가하면 iOS native Firebase SDK가 CocoaPods를 통해 앱 바이너리에 포함된다. 앱이 실행되면 iOS 런타임이 `GoogleService-Info.plist`를 감지하고 native SDK 내부 초기화를 시작한다.

Flutter Dart 레이어에서 `Firebase.initializeApp()`을 호출하지 않으면 **native SDK ↔ Dart 브리지 사이의 동기화가 깨진다.** 디버그 빌드에서는 실행 속도가 느리고 타이밍 여유가 있어 어물쩍 넘어가는 경우가 있지만, 릴리즈 빌드는 AOT 컴파일로 실행 속도가 빨라지면서 타이밍 차이가 드러나 크래시로 이어진다.

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

---

## 체크리스트

- [ ] `Firebase.initializeApp()`이 `main()`에서 가장 먼저 호출되는가
- [ ] `GoogleService-Info.plist`가 `ios/Runner/`에 있는가
- [ ] `firebase_options.dart`가 프로젝트에 있는가
- [ ] `DefaultFirebaseOptions.currentPlatform`을 옵션으로 전달하는가
