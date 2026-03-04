---
title: "Flutter 미구현 UI 컴포넌트 연결 + Xcode 26 베타 WidgetKit 설치 버그 우회"
date: 2026-02-25
draft: false
tags: ["Flutter", "iOS", "Xcode", "WidgetKit", "LiveActivity", "Simulator"]
description: "Flutter 앱에서 onTap: () {} 로 방치된 UI 컴포넌트들을 연결하고, Xcode 26.2 베타에서 발생하는 WidgetKit 익스텐션 시뮬레이터 설치 버그를 우회하는 방법 정리"
---

Flutter 앱 작업 중 두 가지 문제를 연달아 처리했다.
하나는 UI 차원의 문제 — `onTap: () {}` 로 껍데기만 있는 컴포넌트들을 실제로 연결하는 작업.
다른 하나는 Xcode 26.2 베타에서 시뮬레이터에 앱을 설치하면 익스텐션 때문에 앱 자체가 설치되지 않는 문제다.

---

## 1. 동작하지 않는 UI 컴포넌트 연결

Flutter 개발 중 흔히 발생하는 상황: 화면은 다 만들어졌는데 버튼에 `onPressed: () {}`, 카드에 `onTap: () {}`만 달려 있고 실제 동작이 없는 상태.

### 패턴별 정리

**알림 벨 아이콘**

UI는 있는데 `GestureDetector`가 없어서 탭 자체가 불가한 케이스.

```dart
// 수정 전 — 그냥 Container
Container(
  child: Icon(Icons.notifications_outlined),
)

// 수정 후 — GestureDetector로 감싸서 라우팅
GestureDetector(
  onTap: () => context.push('/notifications'),
  child: Container(
    child: Icon(Icons.notifications_outlined),
  ),
)
```

**"전체보기" 텍스트버튼**

```dart
// 수정 전
TextButton(onPressed: () {}, child: Text('전체보기'))

// 수정 후
TextButton(
  onPressed: () => context.push('/list-page'),
  child: Text('전체보기'),
)
```

**카드 탭 → 바텀시트**

카드를 탭하면 상세 정보 + 액션 버튼을 담은 바텀시트를 보여주는 패턴.

```dart
GestureDetector(
  onTap: () => _showDetailSheet(context, item),
  child: Card(...),
)

void _showDetailSheet(BuildContext context, Item item) {
  showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (_) => Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(item.title),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              context.push('/create');
            },
            child: Text('새로 만들기'),
          ),
        ],
      ),
    ),
  );
}
```

### 알림 페이지 구조

앱에 알림 페이지가 아예 없어서 새로 만들었다.
더미 데이터 기반이지만 이후 API 연동으로 교체할 수 있게 구조를 잡았다.

```dart
class _NotificationItem {
  final String id;
  final _NotifType type;
  final String title;
  final String body;
  final String? tripId;   // 연결할 대상 ID
  final DateTime time;
  bool isRead;
}
```

`Dismissible`로 스와이프 삭제, `BlocConsumer`에서 읽음 처리.

```dart
Dismissible(
  key: Key(notif.id),
  direction: DismissDirection.endToStart,
  onDismissed: (_) => _dismiss(notif.id),
  child: InkWell(
    onTap: () {
      _markRead(notif.id);
      if (notif.relatedId != null) {
        context.push('/detail/${notif.relatedId}');
      }
    },
    child: NotificationTile(notif: notif),
  ),
)
```

### 기존 코드 버그 수정

작업 중 발견한 기존 버그 3개:

**1) BlocConsumer `listener` 누락**

```dart
// 에러: Required named parameter 'listener' must be provided
BlocConsumer<SomeBloc, SomeState>(
  builder: (context, state) { ... },
  // listener 빠져있음
)

// 수정
BlocConsumer<SomeBloc, SomeState>(
  listener: (context, state) {},
  builder: (context, state) { ... },
)
```

**2) `maybeMap` orElse 누락 → dynamic 반환**

```dart
// maybeMap에 orElse 없으면 반환 타입이 dynamic
// shouldShow가 dynamic이면 삼항 연산자 컴파일 에러
final shouldShow = state.maybeMap(
  loaded: (data) => data.items.length >= 10,
  // orElse 없음 → dynamic 반환
);

// 수정
final shouldShow = state.maybeMap(
  loaded: (data) => data.items.length >= 10,
  orElse: () => false,  // bool로 고정
);
```

**3) import 경로 오타**

```dart
// 잘못된 경로 (디렉토리 depth 하나 더 들어감)
import '../../bloc/some_bloc.dart';

// 올바른 경로
import '../bloc/some_bloc.dart';
```

---

## 2. Xcode 26.2 베타 WidgetKit 익스텐션 시뮬레이터 설치 버그

`flutter run`으로 시뮬레이터에서 실행하면 빌드는 성공하는데 설치 단계에서 터진다.

```
Unable to install Runner.app
Invalid placeholder attributes.
Failed to create app extension placeholder for PlugIns/SomeWidgetExtension.appex
Failed to create promise.
```

iOS 18.x 시뮬레이터, iOS 26.x 시뮬레이터 가리지 않고 동일하게 발생했다.

### 원인

Xcode 26.2 베타에서 `xcrun simctl install`이 WidgetKit/ActivityKit 익스텐션의 placeholder를 생성할 때 실패한다. "Failed to create promise"는 App Extension이 시뮬레이터에 등록되는 과정에서 내부적으로 사용하는 promise 객체 생성 실패.

Xcode 26이 베타라서 생긴 회귀(regression)로 보이고, 실기기에서는 문제없다.

### 우회 방법

빌드는 정상이므로 익스텐션만 제거하고 직접 설치하면 된다.

```bash
# 1. 시뮬레이터용 빌드 (익스텐션 포함해서 빌드됨)
flutter build ios --simulator --debug

# 2. 문제 익스텐션만 제거
rm -rf build/ios/iphonesimulator/Runner.app/PlugIns/YourWidgetExtension.appex

# 3. simctl로 직접 설치
xcrun simctl install <DEVICE_UUID> build/ios/iphonesimulator/Runner.app

# 4. 실행
xcrun simctl launch <DEVICE_UUID> com.your.bundleid
```

Makefile로 묶어두면 편하다:

```makefile
SIM_DEVICE_ID = <device-uuid>
BUNDLE_ID     = com.your.app.bundleid
WIDGET_EXT    = YourWidgetExtension.appex

run-sim:
	flutter build ios --simulator --debug
	rm -rf build/ios/iphonesimulator/Runner.app/PlugIns/$(WIDGET_EXT)
	xcrun simctl install $(SIM_DEVICE_ID) build/ios/iphonesimulator/Runner.app
	xcrun simctl launch $(SIM_DEVICE_ID) $(BUNDLE_ID)
```

이후엔 `make run-sim` 한 번으로 끝난다.

### 부팅된 시뮬레이터 확인

```bash
xcrun simctl list devices | grep Booted
```

설치하려는 시뮬레이터가 `Booted` 상태여야 한다. `Shutdown` 상태에서 install하면 `Unable to lookup in current state: Shutdown` 에러.

```bash
# 시뮬레이터 직접 부팅
xcrun simctl boot <DEVICE_UUID>
open -a Simulator
```

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| 탭 이벤트 없음 | `GestureDetector` 누락 | 래핑 + `context.push()` 연결 |
| 전체보기 빈 함수 | `onPressed: () {}` | 라우트 또는 바텀시트 연결 |
| BlocConsumer 컴파일 에러 | `listener` 파라미터 누락 | 빈 listener라도 명시 |
| maybeMap 타입 에러 | `orElse` 누락 → dynamic | `orElse: () => false` 추가 |
| 시뮬레이터 설치 실패 | Xcode 26 베타 버그 | 익스텐션 제거 후 simctl install |

Xcode 26 베타 버그는 정식 릴리즈 이후 자연히 해결될 예정이다.
그 전까지는 `make run-sim` 워크어라운드로 개발 진행.
