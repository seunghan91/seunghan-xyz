---
title: "Flutter 앱에 iOS 위젯 추가하기 — pbxproj 수동 편집부터 딥링크까지"
date: 2026-03-08
draft: false
tags: ["Flutter", "iOS", "WidgetKit", "Swift", "go_router", "딥링크"]
description: "Flutter 프로젝트에 iOS 위젯 익스텐션을 Xcode 없이 pbxproj 직접 수정으로 추가하고, App Group으로 데이터를 공유하고, go_router와 FlutterDeepLinkingEnabled로 딥링크까지 연결한 과정을 정리한다."
---

Flutter 앱에 iOS 홈 화면 위젯을 붙이는 작업을 했다. 처음엔 단순해 보였는데 생각보다 손댈 곳이 많았다. Xcode GUI를 쓰면 간단하지만 CLI 환경에서 `project.pbxproj`를 직접 수정해야 하는 경우를 위해 전 과정을 정리한다.

---

## 목표

- 홈 화면 위젯 2종: **2×2**(systemSmall), **2×1**(systemMedium)
- 위젯에서 앱의 미처리 항목 수를 실시간으로 표시
- 위젯 버튼 탭 → 앱 특정 화면으로 이동 (딥링크)

---

## 1. 위젯 익스텐션 파일 구성

```
ios/
├── Runner/
│   ├── AppDelegate.swift
│   ├── Info.plist
│   └── Runner.entitlements
└── ReceiptWidget/            ← 새로 추가
    ├── ReceiptWidget.swift
    ├── Info.plist
    └── ReceiptWidget.entitlements
```

`ReceiptWidget.swift` 하나에 Provider, View, Widget, Bundle을 모두 담았다. 사이즈별로 View를 분리하고 `@Environment(\.widgetFamily)`로 분기하는 패턴이 깔끔하다.

```swift
struct ReceiptWidgetEntryView: View {
    @Environment(\.widgetFamily) var widgetFamily
    var entry: ReceiptWidgetEntry

    var body: some View {
        switch widgetFamily {
        case .systemSmall:  SmallWidgetView(entry: entry)
        case .systemMedium: MediumWidgetView(entry: entry)
        default:            SmallWidgetView(entry: entry)
        }
    }
}
```

### Info.plist (위젯 익스텐션용)

```xml
<key>NSExtension</key>
<dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.widgetkit-extension</string>
</dict>
```

---

## 2. pbxproj 수동 편집

Flutter 프로젝트는 xcodegen을 쓰지 않아서 `project.pbxproj`를 직접 수정해야 했다. 추가해야 할 항목이 많아서 Python 스크립트로 처리했다.

### 추가해야 하는 섹션들

| 섹션 | 추가 항목 |
|------|-----------|
| `PBXBuildFile` | `.swift`, `.xcassets`, `.appex` (Embed) |
| `PBXFileReference` | 위젯 소스 파일들 + `.appex` product |
| `PBXGroup` | `ReceiptWidget` 그룹 |
| `PBXNativeTarget` | 위젯 타겟 |
| `PBXSourcesBuildPhase` | Swift 소스 컴파일 |
| `PBXFrameworksBuildPhase` | Frameworks (비어 있어도 필요) |
| `PBXResourcesBuildPhase` | Assets |
| `PBXCopyFilesBuildPhase` | Embed Foundation Extensions (Runner에 추가) |
| `PBXContainerItemProxy` + `PBXTargetDependency` | Runner → ReceiptWidget 의존성 |
| `XCBuildConfiguration` × 3 | Debug / Release / Profile |
| `XCConfigurationList` | 위젯 타겟 빌드 설정 목록 |

### UUID 관리 팁

pbxproj의 UUID는 24자리 16진수다. 직접 만들 때는 충돌을 피하기 위해 고정된 접두사를 쓰면 관리하기 편하다.

```
AA10000100000000000000AA  ← ReceiptWidget.swift in Sources
AA10000200000000000000AA  ← ReceiptWidget.swift (FileRef)
...
```

### 위젯 타겟 빌드 설정 최소 구성

```
IPHONEOS_DEPLOYMENT_TARGET = 16.0;   ← WidgetKit 최소 요건
PRODUCT_BUNDLE_IDENTIFIER = com.xxx.MyApp.ReceiptWidget;
SKIP_INSTALL = YES;                   ← 앱 익스텐션 필수
SWIFT_VERSION = 5.0;
```

### 주의: iOS 버전 분기

`containerBackground(_:for:)` 와 `#Preview(as:)` 매크로는 iOS 17+ 전용이다. 배포 타겟을 16으로 잡으면 컴파일 에러가 난다.

```swift
// ❌ iOS 16에서 에러
.containerBackground(.fill.tertiary, for: .widget)

// ✅ PreviewProvider 방식 사용
struct MyWidget_Previews: PreviewProvider {
    static var previews: some View {
        MyWidgetView(entry: entry)
            .previewContext(WidgetPreviewContext(family: .systemSmall))
    }
}
```

---

## 3. App Group으로 Flutter ↔ 위젯 데이터 공유

위젯은 앱의 SQLite에 직접 접근할 수 없다. **App Group UserDefaults**로 공유한다.

### 엔타이틀먼트 설정

`Runner.entitlements`와 `ReceiptWidget.entitlements` 양쪽 모두에 추가:

```xml
<key>com.apple.security.application-groups</key>
<array>
    <string>group.com.yourapp.appname</string>
</array>
```

### 위젯에서 읽기 (Swift)

```swift
private func loadEntry() -> MyEntry {
    let defaults = UserDefaults(suiteName: "group.com.yourapp.appname")
    let count = defaults?.integer(forKey: "pending_count") ?? 0
    return MyEntry(date: Date(), pendingCount: count)
}
```

---

## 4. Flutter → 위젯 데이터 동기화 (MethodChannel)

앱에서 데이터가 바뀔 때마다 App Group에 써주는 서비스를 만든다.

### Flutter 서비스

```dart
class WidgetSyncService {
  static const _channel = MethodChannel('myapp/widget');

  Future<void> sync(List<Item> items) async {
    if (!Platform.isIOS) return;

    final pending = items.where((i) => i.category == null).length;

    try {
      await _channel.invokeMethod('syncWidgetData', {
        'pending_count': pending,
        'total_count': items.length,
      });
    } on PlatformException {
      // 위젯 동기화 실패는 무시
    }
  }
}
```

### AppDelegate.swift

```swift
private func setupWidgetChannel(registry: FlutterPluginRegistry) {
    guard let controller = window?.rootViewController as? FlutterViewController else { return }
    let channel = FlutterMethodChannel(
        name: "myapp/widget",
        binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
        if call.method == "syncWidgetData" {
            self.syncWidgetData(args: call.arguments, result: result)
        }
    }
}

private func syncWidgetData(args: Any?, result: FlutterResult) {
    guard let data = args as? [String: Any],
          let defaults = UserDefaults(suiteName: "group.com.yourapp.appname")
    else { return }

    defaults.set(data["pending_count"] as? Int ?? 0, forKey: "pending_count")
    defaults.synchronize()

    if #available(iOS 14.0, *) {
        WidgetCenter.shared.reloadTimelines(ofKind: "MyWidget")
    }
    result(nil)
}
```

CRUD 작업 후 `_widgetSyncService.sync(allItems).ignore()` 한 줄씩 추가하면 위젯이 자동으로 최신 상태를 유지한다.

---

## 5. 딥링크: 위젯 버튼 → 앱 특정 화면

위젯에서는 `Link(destination: url)` 또는 `widgetURL()`로 딥링크를 열 수 있다.

```swift
// 위젯 버튼
if let url = URL(string: "myapp://pending") {
    Link(destination: url) {
        PendingButtonView()
    }
}
```

### go_router 딥링크 처리 — 베스트 프랙티스

Flutter 공식 문서와 커뮤니티 권장 패턴은 **Flutter 내장 딥링크 + go_router redirect normalizer** 조합이다. MethodChannel로 직접 `context.go()` 하는 방식보다 훨씬 깔끔하다.

**1단계: `Info.plist`에 `FlutterDeepLinkingEnabled` 추가**

```xml
<key>FlutterDeepLinkingEnabled</key>
<true/>
```

이 하나로 iOS가 URL scheme을 Flutter 라우터에 자동으로 전달한다. `AppDelegate`에서 `application(_:open:options:)`를 별도로 구현할 필요가 없다.

**2단계: go_router의 `redirect`에서 URI 정규화**

```dart
String? _normalizeDeepLink(String location) {
  final uri = Uri.tryParse(location);
  if (uri == null || uri.scheme != 'myapp') return null;

  switch (uri.host) {
    case 'camera':   return '/collect';
    case 'pending':  return '/pending-list';
    case 'list':     return '/pending-list';
    default:         return '/home';
  }
}

final router = GoRouter(
  redirect: (context, state) {
    // 딥링크 정규화 → 가드 로직보다 먼저
    final normalized = _normalizeDeepLink(state.uri.toString());
    if (normalized != null) return normalized;

    // 이후 로그인 가드 등 처리
    ...
    return null;
  },
  routes: [...],
);
```

**포인트:** 딥링크 정규화를 redirect 맨 앞에 놓아야 한다. 뒤에 놓으면 온보딩 가드 등에 걸려서 원하는 화면으로 이동하지 못한다.

---

## 전체 흐름 요약

```
위젯 버튼 탭
    │
    ▼
myapp://pending  (URL scheme)
    │
    ▼  FlutterDeepLinkingEnabled
Flutter go_router redirect
    │
    ▼  _normalizeDeepLink()
/pending-list  →  PendingListScreen()
```

```
앱에서 데이터 변경 (추가/수정/삭제)
    │
    ▼
WidgetSyncService.sync()
    │  MethodChannel "myapp/widget"
    ▼
AppDelegate.syncWidgetData()
    │  App Group UserDefaults
    ▼
WidgetKit Provider.loadEntry()
    │  WidgetCenter.reloadTimelines()
    ▼
위젯 UI 갱신
```

---

## 삽질 모음

**1. `containerBackground` iOS 17 전용**
배포 타겟 16으로 잡으면 컴파일 에러. 그냥 제거하고 View에서 직접 `.background()` 쓰면 된다.

**2. `WidgetCenter` iOS 14 전용**
`if #available(iOS 14.0, *) { ... }` 래핑 필요.

**3. pbxproj의 `PBXCopyFilesBuildPhase` `dstSubfolderSpec`**
Frameworks embed는 `10`, App Extension embed는 `13`. 틀리면 앱 빌드는 되는데 위젯이 번들에 포함되지 않는다.

**4. `FlutterDeepLinkingEnabled` 없으면 URL이 앱 진입 전에 삭제됨**
이 키 없이 `AppDelegate`에서 `open url` 처리해도 앱이 이미 실행 중일 때는 동작하지 않는 케이스가 있다. 공식 플래그를 쓰는 게 안전하다.

---

## 마치며

Flutter에 iOS 위젯을 붙이는 건 Xcode GUI를 쓰면 빠르지만, pbxproj 구조를 한 번 이해해두면 자동화나 CI 환경에서도 다룰 수 있다. 딥링크도 MethodChannel 없이 `FlutterDeepLinkingEnabled` + go_router redirect 조합이 가장 간결하다는 걸 이번에 확인했다.
