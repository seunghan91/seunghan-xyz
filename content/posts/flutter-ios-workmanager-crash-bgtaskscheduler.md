---
title: "Flutter iOS 크래시: workmanager의 BGTaskScheduler NSException이 Dart try-catch에 잡히지 않는 문제"
date: 2025-08-06
draft: false
tags: ["Flutter", "iOS", "workmanager", "BGTaskScheduler", "crash"]
description: "workmanager 패키지를 iOS에서 사용할 때 BGTaskScheduler가 던지는 ObjC NSException은 Dart try-catch로 잡을 수 없어 앱이 크래시된다. 원인 분석과 해결 방법을 정리한다."
cover:
  image: "/images/og/flutter-ios-workmanager-crash-bgtaskscheduler.png"
  alt: "Flutter Ios Workmanager Crash Bgtaskscheduler"
  hidden: true
---

Flutter 앱을 TestFlight에 올렸는데 앱 실행 즉시 크래시가 발생하는 경우가 있다. 코드에 try-catch를 감싸뒀는데도 크래시가 잡히지 않는다면 `workmanager` 패키지의 iOS BGTaskScheduler 문제일 가능성이 높다.

---

## 증상

- 앱을 켜자마자 즉시 크래시 (스플래시도 안 뜸)
- 시뮬레이터/실기기 모두 동일
- `try-catch`로 감쌌는데도 앱이 죽음
- 로컬 debug 빌드에서는 정상 동작하다가 release 빌드에서만 크래시

---

## 크래시 로그 분석

macOS 크래시 리포트는 `~/Library/Logs/DiagnosticReports/`에 `.ips` 파일로 저장된다.

```bash
ls ~/Library/Logs/DiagnosticReports/ | grep Runner
# Runner-2026-02-25-190740.ips
```

`.ips` 파일을 파싱하면 스택 트레이스를 확인할 수 있다.

```python
import json
with open('Runner-2026-02-25-190740.ips') as f:
    content = f.read()
lines = content.split('\n', 1)
data = json.loads(lines[1])

exc = data.get('exception', {})
print('Type:', exc.get('type'))   # EXC_BAD_ACCESS
print('Signal:', exc.get('signal'))  # SIGSEGV
```

실제 크래시 스택 트레이스:

```
-[NSAssertionHandler handleFailureInMethod:object:file:lineNumber:description:]
-[BGTaskScheduler _unsafe_submitTaskRequest:error:]
-[BGTaskScheduler submitTaskRequest:error:]
static WorkmanagerPlugin.schedulePeriodicTask(taskIdentifier:earliestBeginInSeconds:)
WorkmanagerPlugin.registerPeriodicTask(request:completion:)
...
UIApplicationMain
```

---

## 원인

`workmanager` 패키지는 iOS에서 `BGTaskScheduler`를 사용해 백그라운드 작업을 등록한다. `BGTaskScheduler`는 태스크 ID가 `Info.plist`의 `BGTaskSchedulerPermittedIdentifiers`에 없거나, 기타 조건을 충족하지 못하면 **Objective-C NSException**을 던진다.

문제는 Dart의 `try-catch`가 **ObjC NSException을 잡지 못한다**는 점이다.

```dart
// 이 코드는 동작하지 않는다
try {
  await Workmanager().initialize(callbackDispatcher);
  await Workmanager().registerPeriodicTask(...);
} catch (e) {
  // NSException은 여기서 잡히지 않음
  // 앱이 그냥 크래시됨
}
```

Swift의 `do-catch`도 ObjC `NSException`을 직접 잡지 못한다. ObjC 예외는 ARC 환경에서 undefined behavior로 이어져 앱이 즉시 종료된다.

---

## 해결 방법

### 방법 1: iOS에서는 workmanager 비활성화

workmanager의 iOS 지원은 공식적으로 **실험적(experimental)** 이다. Android 전용으로만 사용하는 것이 가장 안전하다.

```dart
import 'dart:io';
import 'package:workmanager/workmanager.dart';

Future<void> initialize() async {
  // iOS에서는 실행하지 않음
  if (Platform.isIOS) return;

  try {
    await Workmanager().initialize(callbackDispatcher);
    await Workmanager().registerPeriodicTask(
      'my_task',
      'my_task',
      frequency: const Duration(minutes: 15),
    );
  } catch (e) {
    print('Workmanager init failed: $e');
  }
}
```

### 방법 2: workmanager 완전 제거

iOS에서 백그라운드 주기 동기화가 꼭 필요하지 않다면 workmanager 자체를 제거하는 것이 깔끔하다.

**pubspec.yaml에서 제거:**

```yaml
dependencies:
  # 제거
  # workmanager: ^0.9.0
```

**Info.plist에서 관련 항목 제거:**

```xml
<!-- 이 부분 전체 제거 -->
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>my_task_identifier</string>
</array>
<key>UIBackgroundModes</key>
<array>
    <string>fetch</string>
    <string>processing</string>
</array>
```

---

## 주의사항

`BGTaskSchedulerPermittedIdentifiers`에 태스크 ID를 등록했더라도 시뮬레이터나 특정 iOS 버전에서는 BGTaskScheduler가 예외를 던질 수 있다. `Info.plist` 설정이 올바르더라도 크래시가 발생한다면 ObjC 예외 문제를 의심해야 한다.

workmanager iOS 지원 현황은 [공식 저장소 이슈](https://github.com/fluttercommunity/flutter_workmanager)에서 확인할 수 있다.
