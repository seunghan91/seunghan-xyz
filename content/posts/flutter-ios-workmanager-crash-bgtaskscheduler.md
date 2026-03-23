---
title: "Flutter iOS 크래시: workmanager의 BGTaskScheduler NSException이 Dart try-catch에 잡히지 않는 문제"
date: 2025-08-06
draft: true
tags: ["Flutter", "iOS", "workmanager", "BGTaskScheduler", "crash"]
description: "workmanager 패키지를 iOS에서 사용할 때 BGTaskScheduler가 던지는 ObjC NSException은 Dart try-catch로 잡을 수 없어 앱이 크래시된다. 원인 분석과 해결 방법을 정리한다."
cover:
  image: "/images/og/flutter-ios-workmanager-crash-bgtaskscheduler.png"
  alt: "Flutter Ios Workmanager Crash Bgtaskscheduler"
  hidden: true
---

Flutter 앱을 TestFlight에 올렸는데 앱 실행 즉시 크래시가 발생하는 경우가 있다. 코드에 try-catch를 감싸뒀는데도 크래시가 잡히지 않는다면 `workmanager` 패키지의 iOS BGTaskScheduler 문제일 가능성이 높다.

이 글은 실제 프로덕션 앱에서 겪은 크래시 분석 과정을 바탕으로, 원인부터 해결책, 그리고 재발 방지 방법까지 정리한다.

---

## 증상

- 앱을 켜자마자 즉시 크래시 (스플래시도 안 뜸)
- 시뮬레이터/실기기 모두 동일하게 재현
- `try-catch`로 감쌌는데도 앱이 죽음
- 로컬 debug 빌드에서는 정상 동작하다가 release 빌드에서만 크래시
- Xcode 콘솔에 출력이 없거나 매우 짧은 로그만 남음
- Firebase Crashlytics에 크래시가 기록되지 않는 경우도 있음 (초기화 전 크래시)

특히 마지막 증상이 혼란스럽다. Crashlytics는 앱 초기화 이후 크래시를 잡는데, BGTaskScheduler 예외는 앱이 완전히 뜨기도 전에 발생하기 때문에 리포트가 누락될 수 있다.

---

## 디버깅 과정

### 1단계: Xcode 직접 빌드로 확인

TestFlight에서만 크래시가 난다면 가장 먼저 Xcode에서 release 빌드로 직접 실행해본다.

```bash
# Xcode에서 Scheme을 Release로 변경 후 실행
# Product → Scheme → Edit Scheme → Run → Build Configuration: Release
```

Xcode 콘솔에서 NSException 메시지를 바로 확인할 수 있다.

### 2단계: 크래시 리포트 파일 확인

Xcode나 TestFlight 없이 크래시를 분석하려면 기기에 저장된 크래시 리포트를 확인한다. macOS 크래시 리포트는 `~/Library/Logs/DiagnosticReports/`에 `.ips` 파일로 저장된다.

```bash
ls ~/Library/Logs/DiagnosticReports/ | grep Runner
# Runner-2026-02-25-190740.ips
```

`.ips` 파일은 JSON 형식으로 파싱할 수 있다.

```python
import json
with open('Runner-2026-02-25-190740.ips') as f:
    content = f.read()
lines = content.split('\n', 1)
data = json.loads(lines[1])

exc = data.get('exception', {})
print('Type:', exc.get('type'))    # EXC_BAD_ACCESS
print('Signal:', exc.get('signal')) # SIGSEGV
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

`NSAssertionHandler`와 `_unsafe_submitTaskRequest`가 스택 상단에 있다면 BGTaskScheduler가 NSException을 던진 것이다.

### 3단계: Xcode에서 NSException 브레이크포인트 설정

재현 환경이 있다면 Xcode의 Exception Breakpoint를 활용한다.

1. Xcode → Debug Navigator (⌘6)
2. 좌측 하단 `+` 버튼 클릭
3. `Exception Breakpoint` 선택
4. Exception: `Objective-C`, Break: `On Throw`

이 설정으로 NSException이 던져지는 정확한 시점과 콜스택을 확인할 수 있다.

---

## 원인

### BGTaskScheduler의 NSException 동작

`workmanager` 패키지는 iOS에서 `BGTaskScheduler`를 사용해 백그라운드 작업을 등록한다. `BGTaskScheduler`는 다음 조건 중 하나라도 충족되지 않으면 **Objective-C NSException**을 던진다.

1. **태스크 ID가 `Info.plist`에 없음**: `BGTaskSchedulerPermittedIdentifiers` 배열에 등록되지 않은 ID 사용
2. **앱이 실제 기기가 아닌 환경**: 시뮬레이터에서 BGProcessingTask 등록 시도
3. **iOS 13 미만**: BGTaskScheduler는 iOS 13+에서만 지원
4. **중복 등록**: 이미 등록된 태스크 ID를 다시 등록 시도

특히 1번 조건은 흔한 실수다. `pubspec.yaml`에 workmanager를 추가했지만 `Info.plist`에 태스크 ID를 등록하지 않은 경우다.

### Dart try-catch가 NSException을 잡지 못하는 이유

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

Dart의 예외 처리 시스템은 Dart VM 내에서만 동작한다. Dart 코드가 Flutter 플러그인을 통해 네이티브 메서드를 호출할 때, 네이티브 레이어(Objective-C/Swift)에서 던져지는 예외는 Dart VM 경계를 넘어오지 않는다.

정확한 메커니즘은 다음과 같다:

1. Dart가 `MethodChannel`을 통해 네이티브 코드 호출
2. 네이티브 코드(WorkmanagerPlugin)가 BGTaskScheduler 호출
3. BGTaskScheduler가 NSException throw
4. **ObjC 런타임이 스택을 unwind하며 ARC 환경에서 undefined behavior 발생**
5. 프로세스 강제 종료

Swift의 `do-catch`도 ObjC NSException을 직접 처리하지 못한다. Swift는 `Error` 프로토콜을 준수하는 Swift 에러만 catch할 수 있다. ObjC NSException을 catch하려면 Objective-C로 작성된 래퍼가 필요하다.

```objc
// NSException을 잡으려면 ObjC 코드가 필요
@try {
    [BGTaskScheduler.sharedScheduler submitTaskRequest:request error:&error];
} @catch (NSException *exception) {
    // 여기서만 잡힘
}
```

workmanager 플러그인 내부에 이런 처리가 없기 때문에 예외가 그대로 전파되어 앱이 죽는다.

---

## 해결 방법

### 방법 1: iOS에서는 workmanager 비활성화 (권장)

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

`Platform.isIOS` 체크를 최대한 이른 시점에, 가급적 `main()` 함수 내부나 앱 초기화 로직 최상단에 배치한다.

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

`flutter pub get` 후 `ios/` 디렉토리에서 `pod install`을 다시 실행해야 한다.

### 방법 3: iOS 백그라운드 작업 대안

iOS에서 백그라운드 처리가 필요하다면 workmanager 대신 다음 방법을 고려한다.

**`background_fetch` 패키지**: iOS BGAppRefreshTask를 지원하며 workmanager보다 iOS 지원이 안정적이다.

```dart
import 'package:background_fetch/background_fetch.dart';

BackgroundFetch.configure(
  BackgroundFetchConfig(
    minimumFetchInterval: 15,
    stopOnTerminate: false,
    enableHeadless: true,
  ),
  _onBackgroundFetch,
  _onBackgroundFetchTimeout,
);
```

**`flutter_background_service` 패키지**: 장기 실행 서비스가 필요한 경우 사용한다. 단, iOS는 백그라운드 실행 시간 제한이 있다.

**앱 포그라운드 시 동기화**: 백그라운드가 꼭 필요하지 않다면, 앱을 다시 열 때 동기화하는 방식이 iOS 제약에서 가장 자유롭다.

```dart
// AppLifecycleObserver를 활용
class _AppState extends State<App> with WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _syncData();
    }
  }
}
```

---

## 주의사항

`BGTaskSchedulerPermittedIdentifiers`에 태스크 ID를 등록했더라도 시뮬레이터나 특정 iOS 버전에서는 BGTaskScheduler가 예외를 던질 수 있다. `Info.plist` 설정이 올바르더라도 크래시가 발생한다면 ObjC 예외 문제를 의심해야 한다.

workmanager iOS 지원 현황은 [공식 저장소 이슈](https://github.com/fluttercommunity/flutter_workmanager)에서 확인할 수 있다.

---

## 재발 방지

### CI/CD에서 release 빌드 테스트

이 버그는 debug 빌드에서 재현되지 않는 경우가 많다. CI 파이프라인에 release 빌드 실행 단계를 추가한다.

```yaml
# GitHub Actions 예시
- name: Build iOS Release
  run: |
    flutter build ios --release --no-codesign
```

### Platform 분기 린트 규칙

팀 프로젝트라면 iOS에서 문제가 되는 패키지 사용 시 Platform 체크를 강제하는 린트 규칙이나 코드 리뷰 체크리스트를 만든다.

### workmanager 버전 고정

workmanager를 계속 사용해야 한다면 검증된 버전을 `pubspec.yaml`에 고정한다.

```yaml
dependencies:
  workmanager: 0.5.2  # ^0.5.2 대신 정확한 버전 고정
```

---

## Key Takeaways

- **Dart try-catch는 ObjC NSException을 잡지 못한다.** Flutter 플러그인이 네이티브 레이어에서 NSException을 던지면 앱이 즉시 종료된다.
- **BGTaskScheduler는 조건 미충족 시 NSException을 사용한다.** Info.plist 설정 누락, 시뮬레이터 환경, 중복 등록 등이 원인이 된다.
- **workmanager의 iOS 지원은 공식적으로 실험적이다.** 프로덕션 앱이라면 iOS에서는 `Platform.isIOS` 체크로 비활성화하는 것이 가장 안전하다.
- **크래시 리포트는 `.ips` 파일을 직접 파싱해 분석할 수 있다.** Xcode Exception Breakpoint를 함께 활용하면 원인 파악이 빠르다.
- **debug 빌드에서 재현되지 않아도 release 빌드에서 크래시가 날 수 있다.** CI에 release 빌드 테스트를 포함하는 것을 권장한다.
