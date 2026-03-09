---
title: "Flutter BottomSheet가 네비게이션 바를 가리는 문제: showDialog로 전환하기"
date: 2026-03-09
draft: false
tags: ["Flutter", "UI", "BottomSheet", "Dialog", "share_plus", "SQLite", "디버깅"]
description: "showModalBottomSheet가 하단 네비게이션 바를 가리는 문제를 showDialog 중앙 모달로 해결하고, TextButton 색상 가독성 문제와 SQLite 백업 PlatformException까지 함께 잡은 과정을 정리한다."
---

폼 입력이 필요한 화면에서 `showModalBottomSheet`를 쓰다 보면 자연스러운 UX처럼 느껴진다. 그런데 앱에 하단 네비게이션 바가 있으면 바텀시트가 올라오면서 네비게이션을 덮어버리는 문제가 생긴다. 기능적으로는 동작하지만, 시각적으로 답답하다.

세 가지 문제를 한 번에 해결했다.

1. 바텀시트 → 중앙 모달 전환
2. `TextButton` 취소 버튼이 노란색으로 렌더링되어 안 보이는 가독성 문제
3. `share_plus`로 SQLite 파일 공유 시 발생하는 `PlatformException`

---

## 문제 1: BottomSheet가 네비게이션 바를 가린다

### 현상

`showModalBottomSheet`로 만든 입력 폼이 올라올 때 하단 네비게이션 바와 겹친다. `isScrollControlled: true`를 써도 시트가 네비게이션 위까지 올라와 버린다.

### 원인

`showModalBottomSheet`는 `Scaffold` 위에 오버레이로 렌더링되는데, `bottomNavigationBar`와 Z축 레이어가 충돌한다. `SafeArea`나 `padding`으로 억지로 피할 수는 있지만 근본적으로 UX가 어색해진다.

### 해결: showDialog + Dialog 위젯

폼 입력 용도라면 중앙 모달이 더 자연스럽다. 키보드 인셋도 `Dialog`가 자동으로 처리해준다.

**Before (BottomSheet)**
```dart
await showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  backgroundColor: Colors.transparent,
  builder: (context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: StatefulBuilder(
        builder: (context, setModalState) {
          return Container(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(28),
              ),
            ),
            child: Form(/* ... */),
          );
        },
      ),
    );
  },
);
```

**After (Dialog)**
```dart
await showDialog<void>(
  context: context,
  builder: (dialogContext) {
    return StatefulBuilder(
      builder: (dialogContext, setModalState) {
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 24,
            vertical: 40,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(28),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
            child: SingleChildScrollView(
              child: Form(/* ... */),
            ),
          ),
        );
      },
    );
  },
);
```

### 바꿀 때 체크리스트

- **핸들바 제거**: 바텀시트 상단의 드래그 핸들 `Container(width: 44, height: 4, ...)` 삭제
- **borderRadius 변경**: `BorderRadius.vertical(top:)` → `BorderRadius.circular(28)` (네 모서리 모두)
- **키보드 패딩 제거**: `EdgeInsets.only(bottom: viewInsets.bottom)` 불필요, Dialog가 자동 처리
- **context 변수명 정리**: `sheetContext` → `dialogContext`로 명확하게
- **취소 버튼 추가**: 바텀시트는 스와이프로 닫을 수 있지만 Dialog는 명시적인 취소 버튼 필요
- **showDatePicker context**: 내부 `showDatePicker`도 `dialogContext`를 써야 올바른 레이어에 렌더링

### 리스트 피커처럼 높이가 필요한 경우

74~82% 높이를 쓰던 리스트 피커(`FractionallySizedBox(heightFactor: 0.74)`)는 `ConstrainedBox`로 대체한다.

```dart
Dialog(
  child: ConstrainedBox(
    constraints: BoxConstraints(
      maxHeight: MediaQuery.of(dialogContext).size.height * 0.72,
    ),
    child: MyListPickerWidget(/* ... */),
  ),
)
```

`MyListPickerWidget` 내부의 `Container` decoration도 같이 정리한다.

```dart
// Before
return Container(
  decoration: BoxDecoration(
    borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    color: colorScheme.surface,
  ),
  child: SafeArea(top: false, child: Column(...)),
);

// After
return Padding(
  padding: const EdgeInsets.all(20),
  child: Column(...),
);
```

`SafeArea(top: false, ...)` 와 `Container` decoration은 Dialog 자체가 처리하므로 제거한다. 이때 닫는 괄호 수가 달라지므로 주의.

---

## 문제 2: TextButton 취소 버튼이 노란색으로 보인다

### 현상

`AlertDialog`나 커스텀 `Dialog` 안의 취소 `TextButton` 글씨가 앱 테마 primary 색상(노란색 계열)으로 렌더링된다. 흰 배경 다이얼로그 위에서 노란 글씨는 거의 안 보인다.

### 원인

`TextButton`의 기본 `foregroundColor`는 `Theme.of(context).colorScheme.primary`를 따른다. 앱 전체 seed color가 노란/앰버 계열이면 취소 버튼도 같은 색이 된다.

### 해결

취소 버튼에만 `onSurfaceVariant`를 명시한다. 이 색은 보통 중간 명도의 회색 계열이라 어떤 배경에서도 가독성이 보장된다.

```dart
TextButton(
  style: TextButton.styleFrom(
    foregroundColor: Theme.of(context).colorScheme.onSurfaceVariant,
  ),
  onPressed: () => Navigator.of(context).pop(false),
  child: const Text('취소'),
),
```

확인/저장/삭제 등 주요 액션 버튼은 `FilledButton`을 그대로 쓰면 된다. 취소만 톤을 낮춰주는 게 Material 3 가이드라인에도 맞다.

---

## 문제 3: SQLite 백업 파일 공유 시 PlatformException

### 현상

`share_plus`로 SQLite `.db` 파일을 공유할 때 iOS에서 `PlatformException`이 발생한다.

```dart
// 기존 코드
Future<void> exportBackup() async {
  final dbPath = p.join(await getDatabasesPath(), 'app.db');
  final tempDir = await getTemporaryDirectory();
  final backupPath = p.join(tempDir.path, 'app_backup.db');

  await File(dbPath).copy(backupPath);

  await SharePlus.instance.share(
    ShareParams(
      files: [XFile(backupPath, mimeType: 'application/octet-stream')],
      subject: '앱 데이터 백업',
    ),
  );
}
```

### 원인

SQLite는 기본적으로 **WAL(Write-Ahead Logging)** 모드를 사용하지 않더라도, DB 연결이 열려 있는 상태에서 파일을 복사하면 진행 중인 트랜잭션이나 캐시된 데이터가 반영되지 않을 수 있다. iOS에서는 이런 상태의 파일을 공유 시트에 넘길 때 플랫폼 레벨에서 검증 오류가 발생하기도 한다.

### 해결

복사 전에 DB 연결을 닫는다. `sqflite`의 `Database.close()`를 호출하면 캐시가 디스크에 플러시된다. Riverpod을 쓰는 경우 StorageService에 `closeAndReset()` 메서드를 두고, 백업 내보내기 전에 호출한다.

```dart
// StorageService
Future<void> closeAndReset() async {
  await _database?.close();
  _database = null;  // 다음 접근 시 자동으로 재연결
}
```

```dart
// 백업 내보내기 호출부
Future<void> _exportBackup(BuildContext context, WidgetRef ref) async {
  try {
    // DB 닫기 → WAL/캐시 플러시 보장
    await ref.read(storageServiceProvider).closeAndReset();
    await ref.read(backupServiceProvider).exportBackup();
  } catch (e) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('백업 내보내기 실패: $e')),
    );
  }
}
```

`closeAndReset()` 후 `_database = null`로 초기화해두면, 이후 DB 접근 시 자동으로 재연결되어 정상 동작한다. 앱을 재시작하거나 프로바이더를 invalidate할 필요 없다.

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| BottomSheet가 네비게이션 바를 가림 | Z축 레이어 충돌 | `showDialog` + `Dialog` 위젯으로 교체 |
| 취소 버튼 글씨가 안 보임 | `TextButton` 기본색이 theme primary | `onSurfaceVariant` 명시 |
| 백업 공유 PlatformException | DB 연결 열린 채로 파일 복사 | `closeAndReset()` 후 복사 |

세 문제 모두 Flutter나 SQLite의 버그가 아니라, 플랫폼/프레임워크가 어떻게 동작하는지 이해하면 자연스럽게 도출되는 해결책이다.
