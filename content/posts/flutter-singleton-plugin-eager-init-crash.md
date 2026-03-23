---
title: "Flutter 싱글톤에서 iOS 플러그인 인스턴스를 즉시 생성하면 크래시가 난다"
date: 2025-08-10
draft: true
tags: ["Flutter", "iOS", "플러그인", "싱글톤", "크래시", "초기화"]
description: "싱글톤 클래스 필드에서 네이티브 플러그인 인스턴스를 즉시 생성하면, Flutter 엔진 초기화 이전에 플러그인 채널이 열려서 크래시가 발생한다. Lazy initialization으로 해결한다."
cover:
  image: "/images/og/flutter-singleton-plugin-eager-init-crash.png"
  alt: "Flutter Singleton Plugin Eager Init Crash"
  hidden: true
---

iOS 네이티브 플러그인을 사용하는 Flutter 앱에서 싱글톤 패턴을 쓸 때 흔히 저지르는 실수가 있다. 플러그인 인스턴스를 클래스 필드에서 즉시 생성하는 것이다. 로컬에서는 멀쩡하게 돌아가고, 시뮬레이터에서도 문제없이 작동한다. 그런데 TestFlight에 올린 릴리즈 빌드를 설치하면 앱이 시작과 동시에 뻗는다. 이 글에서는 이 크래시의 정확한 원인과 재현 조건, 그리고 안전하게 수정하는 방법을 설명한다.

---

## 문제가 되는 패턴

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  // ❌ 클래스 필드에서 즉시 생성
  final _iCloudSync = IcloudStorageSync();
}
```

언뜻 보면 자연스러운 코드다. `CloudSyncService`는 전형적인 Dart 싱글톤이고, `_iCloudSync`는 서비스가 필요로 하는 플러그인 인스턴스다. 클래스가 생성될 때 플러그인도 함께 생성되는 것이 당연해 보인다.

그런데 이 코드는 타이밍 문제를 내포하고 있다.

`static final instance = CloudSyncService._()` 는 Dart에서 클래스가 **처음 참조되는 시점**에 실행된다. `main.dart` 상단에 `import`만 해도 static field initializer가 돌 수 있다. 더 구체적으로는, 아래와 같은 상황에서 클래스가 참조된다.

- 다른 파일에서 `CloudSyncService.instance`를 import한 파일이 평가될 때
- `main()` 함수 안에서 `CloudSyncService.instance`를 직접 호출할 때
- `WidgetsApp`이나 `MaterialApp`의 빌드 과정에서 간접 참조될 때

이 시점은 `WidgetsFlutterBinding.ensureInitialized()` 이전일 수 있다. Flutter 엔진의 플러그인 채널 등록이 완료되기 전에 `IcloudStorageSync()` 생성자가 호출되면, 플랫폼 채널(MethodChannel)을 바인딩할 대상이 없다. 결과적으로 **플랫폼 채널을 찾지 못해 크래시**가 발생한다.

---

## Flutter 엔진 초기화 순서 이해하기

크래시의 원인을 정확히 이해하려면 Flutter 앱이 어떤 순서로 시작되는지 알아야 한다.

```
앱 프로세스 시작
  └─ main() 진입
       └─ (선택) WidgetsFlutterBinding.ensureInitialized()
            └─ Flutter 엔진 초기화 완료
                 └─ 플랫폼 채널(MethodChannel) 등록 완료
                      └─ runApp() 호출
                           └─ 위젯 트리 빌드 시작
```

`WidgetsFlutterBinding.ensureInitialized()`는 Flutter 엔진과 Dart 런타임 사이의 다리를 초기화한다. 이 단계가 완료되어야 비로소 `MethodChannel`, `EventChannel` 등의 플랫폼 채널이 네이티브 코드와 통신할 수 있게 된다.

문제는 Dart의 static field initializer가 이 초기화 순서와 **무관하게 클래스가 처음 참조되는 즉시** 실행된다는 점이다. `main()` 함수가 시작되기도 전에, 또는 `ensureInitialized()` 호출 전에 싱글톤 클래스가 어딘가에서 참조되면, 플러그인 생성자가 준비되지 않은 엔진 위에서 실행된다.

iOS에서 `icloud_storage_sync`와 같은 플러그인은 생성자 내부에서 즉시 FlutterMethodChannel을 등록하려 시도한다. 엔진이 준비되지 않은 상태에서 이 작업이 실행되면 null 포인터 역참조 또는 채널 조회 실패로 크래시가 발생한다.

---

## 왜 디버그에서는 안 터지나

TestFlight 빌드에서만 크래시가 나고 시뮬레이터 또는 디버그 빌드에서는 정상이라면 이 패턴을 가장 먼저 의심해야 한다. 이유는 컴파일 방식의 차이다.

**디버그 빌드 (JIT, Just-In-Time)**
- Dart 코드를 런타임에 컴파일한다.
- 실행 속도가 느리다.
- Flutter 엔진 초기화와 싱글톤 생성 사이에 자연스럽게 시간 여유가 생긴다.
- 타이밍 충돌이 발생하지 않거나 발생해도 엔진이 이미 준비된 상태일 확률이 높다.

**릴리즈 빌드 (AOT, Ahead-Of-Time)**
- 빌드 타임에 네이티브 코드로 미리 컴파일된다.
- 실행 속도가 훨씬 빠르다.
- `main()` 진입과 동시에 static initializer들이 즉각 실행된다.
- 엔진 초기화가 완료되기 전에 플러그인 생성자가 호출될 가능성이 매우 높다.

즉, 디버그 환경의 느린 실행이 타이밍 버그를 숨기고 있었던 것이다. TestFlight나 App Store 빌드는 AOT 컴파일이므로 이 숨겨진 타이밍 문제가 수면 위로 드러난다.

시뮬레이터가 디버그 모드로 실행된다는 점도 중요하다. 시뮬레이터에서 `flutter run --release`로 실행하면 같은 크래시를 재현할 수 있다.

---

## 크래시 재현 방법

원인을 확인하고 싶다면 다음 방법으로 재현할 수 있다.

```bash
# 시뮬레이터에서 릴리즈 모드로 실행
flutter run --release

# 실기기에서 릴리즈 모드로 실행
flutter run --release -d <device-id>
```

Xcode Organizer 또는 Firebase Crashlytics에서 크래시 로그를 보면 보통 아래와 유사한 스택 트레이스를 볼 수 있다.

```
Thread 1: EXC_BAD_ACCESS (SIGSEGV)
  FlutterMethodChannel initWithName:binaryMessenger:codec:
  ...
  IcloudStorageSync.init()
  CloudSyncService._()
  CloudSyncService.$init (static field initializer)
  main
```

`static field initializer`가 `WidgetsFlutterBinding` 초기화 이전에 실행되었음을 스택에서 확인할 수 있다.

---

## 해결: Lazy Initialization

플러그인 인스턴스를 nullable로 선언하고, 실제로 사용하는 시점에 처음 생성한다.

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  // ✅ nullable로 선언, 처음 사용할 때 생성
  IcloudStorageSync? _iCloudSync;

  Future<void> upload(String filePath, String destination) async {
    // ??= 연산자로 lazy init
    _iCloudSync ??= IcloudStorageSync();

    await _iCloudSync!.upload(
      containerId: 'iCloud.com.example.myapp',
      filePath: filePath,
      destinationRelativePath: destination,
    );
  }
}
```

`main()`에서 `WidgetsFlutterBinding.ensureInitialized()`가 완료된 이후에 `upload()`가 호출되므로, 그 시점에는 플러그인 채널이 이미 등록된 상태다. `_iCloudSync ??= IcloudStorageSync()`는 null인 경우에만 생성하므로 중복 생성도 없다.

### main()에서의 올바른 초기화 순서

```dart
void main() async {
  // 반드시 가장 먼저 호출
  WidgetsFlutterBinding.ensureInitialized();

  // 이후 플러그인을 요구하는 초기화 작업
  await Firebase.initializeApp();
  // CloudSyncService.instance는 여기서 참조해도 안전
  // (단, 내부 플러그인은 사용 시점까지 생성하지 않음)

  runApp(const MyApp());
}
```

`ensureInitialized()`를 `main()` 최상단에 두는 것이 가장 안전하다. Flutter 팀도 이를 공식적으로 권장한다.

---

## 다른 해결 방법들

Lazy initialization 외에도 상황에 따라 선택할 수 있는 방법들이 있다.

### 방법 1: late 키워드 사용

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  // late: 처음 접근할 때 초기화 (단, non-nullable)
  late final IcloudStorageSync _iCloudSync = IcloudStorageSync();
}
```

`late`는 처음 접근할 때 초기화된다. 하지만 여전히 `ensureInitialized()` 이전에 접근하면 같은 문제가 생길 수 있으므로, 완전한 해결책이 아닐 수 있다.

### 방법 2: init() 메서드 패턴

```dart
class CloudSyncService {
  CloudSyncService._();
  static final CloudSyncService instance = CloudSyncService._();

  IcloudStorageSync? _iCloudSync;

  // main()에서 ensureInitialized() 이후 명시적으로 호출
  void init() {
    _iCloudSync = IcloudStorageSync();
  }
}

// main.dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  CloudSyncService.instance.init();
  runApp(const MyApp());
}
```

명시적인 `init()` 패턴은 초기화 시점을 코드에서 명확히 드러낸다는 장점이 있다.

### 방법 3: Provider / Riverpod 등 DI 컨테이너 활용

의존성 주입 프레임워크를 사용한다면 플러그인 인스턴스를 Provider나 Riverpod의 `Provider`로 등록하는 방법도 있다. 이 경우 Flutter 프레임워크가 생명주기를 관리하므로 타이밍 문제를 회피하기 쉽다.

---

## 적용 범위

이 문제는 `icloud_storage_sync` 외에 **iOS 네이티브 플러그인을 래핑하는 모든 패키지**에 해당한다. 플랫폼 채널(MethodChannel, EventChannel, BasicMessageChannel)을 생성자 내에서 초기화하는 모든 플러그인이 대상이다.

실제로 자주 문제가 되는 패키지들:

- `local_auth` — Face ID / Touch ID 인증
- `flutter_secure_storage` — iOS Keychain 연동
- `permission_handler` — 권한 요청
- `sign_in_with_apple` — Apple 로그인
- `in_app_purchase` — 앱 내 결제
- `camera` — 카메라 접근
- `geolocator` — 위치 정보
- 기타 플랫폼 채널을 사용하는 패키지

싱글톤 서비스에서 이런 패키지를 쓴다면 모두 lazy init으로 바꾸는 것이 안전하다.

---

## 예방 팁

이 문제를 미리 방지하기 위한 몇 가지 가이드라인이다.

**1. 싱글톤 필드에 플러그인 인스턴스를 직접 할당하지 않는다**
클래스 필드 선언부에서 플러그인 인스턴스를 생성하지 말고, 항상 메서드 내에서 lazy init 패턴으로 생성한다.

**2. `main()`에서 항상 `WidgetsFlutterBinding.ensureInitialized()`를 첫 줄에 둔다**
`async` `main()`을 사용할 때 특히 중요하다. `await`를 사용하기 전에 반드시 바인딩을 초기화해야 한다.

**3. 릴리즈 모드로 정기적으로 테스트한다**
시뮬레이터에서도 `flutter run --release`로 주기적으로 테스트하면 AOT 환경에서만 나타나는 버그를 TestFlight 전에 잡을 수 있다.

**4. Crashlytics 또는 Sentry를 초기에 붙인다**
TestFlight 빌드부터 크래시 리포팅 도구를 연결해두면 크래시 스택 트레이스를 즉시 확인할 수 있다.

**5. 코드 리뷰 시 static initializer를 주의 깊게 본다**
`static final` 필드가 플러그인 생성을 포함하고 있으면 코드 리뷰 단계에서 반드시 lazy init 여부를 확인한다.

---

## Key Takeaways

- Dart의 `static final` 필드 초기화는 `WidgetsFlutterBinding.ensureInitialized()` 이전에 실행될 수 있다.
- iOS 네이티브 플러그인 생성자는 Flutter 엔진이 초기화된 이후에만 호출해야 한다.
- 릴리즈(AOT) 빌드는 디버그(JIT) 빌드보다 훨씬 빠르게 실행되어 타이밍 버그를 드러낸다.
- 시뮬레이터 + 디버그에서 정상이고 TestFlight에서만 크래시가 난다면 이 패턴을 먼저 확인한다.
- 해결책은 단순하다: 플러그인 인스턴스를 nullable로 선언하고 `??=` 연산자로 lazy init한다.
- `main()` 최상단에 `WidgetsFlutterBinding.ensureInitialized()`를 두는 것이 가장 근본적인 예방책이다.
