---
title: "Flutter image_picker 카메라/갤러리 바텀시트 + Riverpod 빈도 기반 카테고리 자동 정렬 삽질기"
date: 2026-03-09
draft: false
tags: ["Flutter", "Riverpod", "image_picker", "UX", "SharedPreferences", "DraggableScrollableSheet", "삽질"]
description: "Flutter 앱에서 image_picker 카메라/갤러리 분기 바텀시트, Riverpod AsyncNotifier로 사용 빈도 기반 카테고리 자동 정렬, 긴급 대상에 따른 버튼 색상 동적 변경까지 구현하면서 겪은 과정을 정리한다."
---

Flutter로 시민 신고 앱을 만들면서 세 가지 UX 문제를 연달아 만났다.

1. 사진 추가 버튼이 갤러리만 열어서 카메라 촬영이 불가능한 문제
2. 카테고리가 늘어날수록 그리드가 길어져서 스크롤이 많아지는 문제
3. 신고 대상(일반/긴급)이 바뀌어도 버튼 색상이 바뀌지 않아서 직관성이 떨어지는 문제

각각 어떻게 풀었는지 정리한다.

---

## 문제 1: image_picker가 갤러리만 열린다

### 현상

사진 추가 버튼이 `pickImage(source: ImageSource.gallery)`만 호출해서 카메라로 찍는 게 불가능했다. 앱 자체에 카메라 권한도 있고 `NSCameraUsageDescription`도 있는데 UI에서 선택지를 아예 안 줬던 것.

### Perplexity로 best practice 확인

`image_picker` 1.2+ best practice를 검색하니 결론은 명확했다.

> 카메라와 갤러리를 동시에 제공할 때는 **바텀시트에서 선택지를 보여주는 패턴**이 표준이다. 하나의 탭으로 합치면 사용자가 기대하는 동작과 어긋난다.

또 중요한 포인트:
- `async` 작업 후 `mounted` 체크 필수 — 이미지 피커가 열려있는 동안 위젯이 dispose될 수 있다
- 카메라와 갤러리 로직을 **별도 메서드로 분리**해야 각 케이스의 에러 처리가 깔끔해진다

### 해결: PhotoService에 takePhoto() 추가

```dart
// photo_service.dart
Future<PhotoAttachment?> takePhoto() async {
  try {
    final file = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (file == null) return null;
    final gps = await _extractGps(file);
    return PhotoAttachment(path: file.path, lat: gps.$1, lng: gps.$2);
  } catch (_) {
    return null;
  }
}
```

`imageQuality: 85`를 설정한 이유는 원본 그대로 올리면 SMS 첨부 흐름에서 불필요하게 크다.

### 해결: 바텀시트로 카메라/갤러리 분기

```dart
// photo_grid.dart (StatelessWidget 내부)
void _showPickerSheet(BuildContext context) {
  showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Container(
                width: 40, height: 40,
                decoration: BoxDecoration(
                  color: AppColors.info.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppColors.info),
              ),
              title: const Text('카메라로 촬영',
                style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: const Text('지금 바로 사진을 찍어 첨부합니다'),
              onTap: () {
                Navigator.pop(ctx);
                onAddFromCamera();
              },
            ),
            ListTile(
              leading: Container(
                width: 40, height: 40,
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.photo_library_rounded, color: AppColors.primary),
              ),
              title: const Text('갤러리에서 선택',
                style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: const Text('저장된 사진을 불러옵니다'),
              onTap: () {
                Navigator.pop(ctx);
                onAddFromGallery();
              },
            ),
          ],
        ),
      ),
    ),
  );
}
```

`StatelessWidget`에서 `showModalBottomSheet`를 직접 호출해도 된다. context만 있으면 충분하다.

### 호출부: mounted 체크 분리

```dart
// report_screen.dart
Future<void> _addPhotoFromCamera() async {
  if (_photosLimitReached) { /* snackbar */ return; }
  try {
    final photo = await ref.read(photoServiceProvider).takePhoto();
    if (photo == null) return;
    await _handlePickedPhotos([photo]);
  } catch (error) {
    if (mounted) {  // ← 핵심: async 후 mounted 체크
      messenger.showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }
}
```

`mounted` 체크를 빠뜨리면 카메라 앱에서 돌아왔을 때 위젯이 이미 dispose된 경우 `setState called after dispose` 에러가 난다.

---

## 문제 2: 카테고리가 많아질수록 UI가 무거워진다

### 현상

신고 유형을 추가하다 보니 카테고리가 14개까지 늘었다. 3열 그리드로 보여주면 스크롤이 길어지고, 자주 쓰는 것과 거의 안 쓰는 것이 동등하게 나열된다.

### 아이디어: 상위 3개 빠른 선택 + 전체 모달

자주 쓰는 카테고리 3개를 메인 화면에 큰 버튼으로 띄우고, 나머지는 "전체 카테고리 ↓" 버튼으로 모달에서 고르게 하면 된다.

문제는 "자주 쓰는 것"을 어떻게 정하느냐인데, 두 가지 방법이 있다.
- **하드코딩**: 통계적으로 많은 유형을 고정
- **사용 빈도 추적**: 실제 사용자 선택 기록 기반 정렬

하드코딩은 유지보수가 불편하고, 사람마다 자주 쓰는 유형이 다르기 때문에 **SharedPreferences + 빈도 추적** 방식을 선택했다.

### Riverpod AsyncNotifier로 빈도 관리

```dart
// category_frequency_provider.dart

const _prefsKey = 'category_frequency_v1';

// 국내 민원 통계 기반 초기값 — 아무도 안 써도 이 순서가 기본
const _defaultFrequencies = <String, int>{
  'dasan120:불법주정차': 500,
  'dasan120:소음': 300,
  'dasan120:불법투기': 200,
  // ...
  'police112:범죄신고': 500,
  'fire119:구급': 500,
  'fire119:화재': 300,
};

class CategoryFrequencyNotifier extends AsyncNotifier<Map<String, int>> {
  @override
  Future<Map<String, int>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    if (raw == null) return Map.from(_defaultFrequencies);
    final stored = (jsonDecode(raw) as Map<String, dynamic>)
        .map((k, v) => MapEntry(k, (v as num).toInt()));
    // 신규 카테고리도 기본값이 적용되도록 merge
    return {..._defaultFrequencies, ...stored};
  }

  Future<void> increment(String label, ReportTarget target) async {
    final key = '${target.name}:$label';
    final current = await future;
    final updated = {...current, key: (current[key] ?? 0) + 100};
    state = AsyncValue.data(updated);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, jsonEncode(updated));
  }
}
```

선택할 때마다 +100씩 더한다. 기본값이 500이므로 5번 이상 쓰면 기본값보다 높아져서 상위 3위에 진입한다.

### 파생 Provider로 상위 N개 계산

```dart
final topCategoriesProvider =
    Provider.family<List<ReportCategory>, ReportTarget>((ref, target) {
  final freqsAsync = ref.watch(categoryFrequencyProvider);
  final freqs = switch (freqsAsync) {
    AsyncData(:final value) => value,
    _ => _defaultFrequencies,  // 로딩 중엔 기본값
  };

  return ReportCategory.forTarget(target)
      .where((c) => c.label != '기타')
      .toList()
    ..sort((a, b) {
        final ka = '${target.name}:${a.label}';
        final kb = '${target.name}:${b.label}';
        return (freqs[kb] ?? 0).compareTo(freqs[ka] ?? 0);
      });
});
```

`Provider.family`를 쓰면 `target`이 바뀔 때 자동으로 재계산된다. 다산120에서 경찰112로 스와이프하면 상위 3개가 즉시 바뀐다.

Riverpod 3.x에서는 `AsyncValue.valueOrNull`이 없어서 Dart 3 패턴 매칭으로 대응했다.

```dart
// ❌ Riverpod 3.x에서 컴파일 에러
final freqs = ref.watch(categoryFrequencyProvider).valueOrNull ?? defaults;

// ✅
final freqs = switch (ref.watch(categoryFrequencyProvider)) {
  AsyncData(:final value) => value,
  _ => defaults,
};
```

### DraggableScrollableSheet로 전체 카테고리 모달

```dart
// category_picker_sheet.dart
class CategoryPickerSheet extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final categories = ReportCategory.forTarget(target);

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.55,
      maxChildSize: 0.88,
      minChildSize: 0.35,
      builder: (ctx, scrollController) {
        return Column(
          children: [
            // 헤더
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
              child: Text('카테고리 선택', ...),
            ),
            // 전체 그리드 (스크롤 컨트롤러 연결 필수)
            Expanded(
              child: GridView.builder(
                controller: scrollController, // ← 이게 빠지면 드래그가 안 됨
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 3,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.1,
                ),
                itemBuilder: (_, i) => ReportCategoryCard(...),
                itemCount: categories.length,
              ),
            ),
          ],
        );
      },
    );
  }
}
```

`DraggableScrollableSheet` 안에 `GridView`를 넣을 때 `controller: scrollController`를 반드시 연결해야 한다. 빠뜨리면 시트 드래그와 그리드 스크롤이 충돌해서 둘 다 안 된다.

### 메인 화면: 상위 3개 칩 + 전체보기

```dart
// report_screen.dart
final topCategories = ref.watch(topCategoriesProvider(draft.target));

// ...

_QuickCategoryRow(
  topCategories: topCategories,
  selectedCategory: draft.category,
  onSelect: (cat) {
    ref.read(categoryFrequencyProvider.notifier)
        .increment(cat.label, draft.target); // 선택할 때마다 빈도 +100
    ref.read(reportControllerProvider.notifier)
        .updateCategory(cat.label);
    _scrollToContent();
  },
  onShowAll: () => _showCategoryPicker(draft), // 전체 모달 열기
),
```

---

## 문제 3: 긴급 대상으로 바꿔도 버튼 색상이 그대로다

### 현상

신고 대상을 스와이프로 전환할 수 있는데, 일반(다산120)이든 긴급(112, 119)이든 하단의 신고 제출 버튼이 항상 초록색이었다. 긴급 상황인데 초록 버튼을 보면 위급함이 전달되지 않는다.

### 해결: accentColor를 emergency에 따라 분기

```dart
// _FloatingSubmitButton.build()

final accentColor = emergency ? AppColors.error : AppColors.primary;
final accentDark  = emergency ? const Color(0xFFDC2626) : AppColors.primaryDark;

// 그라데이션
gradient: LinearGradient(
  colors: isReady
      ? [
          accentColor.withValues(alpha: 0.92),
          accentDark.withValues(alpha: 0.92),
        ]
      : hasStartedInput
      ? [
          Colors.white.withValues(alpha: 0.72),
          accentColor.withValues(alpha: 0.18), // 입력 시작하면 살짝 물드는 효과
        ]
      : [ /* 기본 흰/회색 */ ],
),

// 글로우 shadow도 동일하게
BoxShadow(
  color: statusColor.withValues(alpha: isReady ? 0.32 : 0.10),
  blurRadius: isReady ? 28 : 18,
),
```

ready 상태 뿐만 아니라 `hasStartedInput`(입력 시작) 상태에서도 accentColor가 살짝 물드는 효과를 줬다. 아직 제출 못 하더라도 긴급 느낌이 전달된다.

`TargetChip`(신고 대상 선택 칩)은 이미 emergency 여부로 색상을 구분하고 있었는데, 제출 버튼만 빠져 있었던 것이다. 앱 전체 컬러 톤이 일관성을 잃으면 사용자가 혼란스럽다.

---

## 정리

| 문제 | 해결 포인트 |
|------|-------------|
| 카메라 버튼 없음 | 바텀시트 2-option (카메라/갤러리), async 후 `mounted` 체크 |
| 카테고리 과다 노출 | 빈도 기반 상위 3개 + DraggableScrollableSheet 전체 모달 |
| 긴급 버튼 색상 일관성 | `accentColor`/`accentDark`를 emergency 여부로 분기 |

Riverpod 3.x에서 `valueOrNull` → Dart 3 패턴 매칭(`switch`/`AsyncData`)으로 교체하는 게 제일 당황스러웠다. 공식 마이그레이션 가이드에는 있는데 ChatGPT나 기존 예제들이 다 구버전 API를 쓰고 있어서 찾는 데 시간이 걸렸다.
