---
title: "Flutter 싱글톤에서 iOS 플러그인 인스턴스를 즉시 생성하면 크래시가 난다"
date: 2025-08-10
draft: false
tags: ["Flutter", "iOS", "플러그인", "싱글톤", "크래시", "초기화"]
description: "싱글톤 클래스 필드에서 네이티브 플러그인 인스턴스를 즉시 생성하면, Flutter 엔진 초기화 이전에 플러그인 채널이 열려서 크래시가 발생한다. Lazy initialization으로 해결한다."
cover:
  image: "/images/og/flutter-singleton-plugin-eager-init-crash.png"
  alt: "Flutter Singleton Plugin Eager Init Crash"
  hidden: true
---

iOS 네이티브 플러그인을 사용하는 Flutter 앱에서 싱글톤 패턴을 쓸 때 흔히 저지르는 실수가 있다. 플러그인 인스턴스를 클래스 필드에서 즉시 생성하는 것이다.

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

`static final instance = CloudSyncService._()` 는 Dart에서 클래스가 **처음 참조되는 시점**에 실행된다. `main.dart` 상단에 `import`만 해도 static field initializer가 돌 수 있다.

이 시점은 `WidgetsFlutterBinding.ensureInitialized()` 이전일 수 있고, Flutter 엔진의 플러그인 채널 등록이 완료되기 전이다. 이 상태에서 `IcloudStorageSync()` 같은 네이티브 플러그인 인스턴스를 생성하면 **플랫폼 채널을 찾지 못해 크래시**가 발생한다.

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

`main()`에서 `WidgetsFlutterBinding.ensureInitialized()`가 완료된 이후에 `upload()`가 호출되므로, 그 시점에는 플러그인 채널이 이미 등록된 상태다.

---

## 왜 디버그에서는 안 터지나

디버그 빌드는 JIT 컴파일 + 느린 실행 속도 때문에 Flutter 엔진 초기화와 싱글톤 생성 사이에 시간 여유가 생긴다. 릴리즈 빌드(AOT)는 실행이 빠르기 때문에 타이밍 충돌이 드러난다.

TestFlight 빌드에서만 크래시가 나고 시뮬레이터에서는 정상이라면 이 패턴을 의심해볼 것.

---

## 적용 범위

이 문제는 `icloud_storage_sync` 외에 **iOS 네이티브 플러그인을 래핑하는 모든 패키지**에 해당한다.

- `local_auth`
- `flutter_secure_storage`
- `permission_handler`
- `sign_in_with_apple`
- 기타 플랫폼 채널을 사용하는 패키지

싱글톤 서비스에서 이런 패키지를 쓴다면 모두 lazy init으로 바꾸는 것이 안전하다.
