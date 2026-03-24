---
title: "Flutter 노트 앱 디자인 리뉴얼 — Bear 스타일 에디터와 Glassmorphism 알림 적용기"
date: 2026-03-24
draft: false
tags: ["Flutter", "UI/UX", "Glassmorphism", "Bear", "디자인시스템"]
description: "Flutter 노트 앱에 Bear 스타일 에디터 타이포그래피와 Glassmorphism 알림 카드를 적용한 과정. BackdropFilter 성능 최적화, colorScheme 마이그레이션, 마크다운 포맷 툴바 구현까지."
---

Flutter로 노트 앱을 만들다 보면 어느 순간 기능은 다 있는데 "네이티브 앱 같지 않다"는 느낌이 든다. 버튼은 Glass 디자인 시스템으로 마이그레이션했는데, 정작 에디터 화면과 알림 히스토리는 초기 Material3 코드 그대로 방치돼 있었다. `const Divider()`, `Colors.blue.shade50`, `OutlineInputBorder()` — 이런 것들이 앱 전체 톤을 깨고 있었다.

Bear 앱의 에디터 UX를 참고하고, iOS 26 Liquid Glass에서 영감 받은 Glassmorphism을 알림 카드에 적용해봤다. 이 글에서는 실제 삽질 과정과 구현 코드를 정리한다.

---

## Bear 앱은 왜 글쓰기가 편한가

Bear는 Apple Design Award를 받은 마크다운 노트 앱이다. "도구가 방해하지 않는다(Tools stay out of your way)"가 핵심 철학이다. 실제로 Bear 에디터를 열면 눈에 띄는 UI 요소가 거의 없다. 제목, 날짜, 본문 — 이 세 가지만 보인다.

Bear의 타이포그래피 설정을 뜯어보면 이런 요소들을 제어할 수 있다:

| 설정 항목 | Bear 기본값 | 효과 |
|-----------|------------|------|
| Font | Avenir Next | 깔끔한 산세리프, 본문 가독성 우수 |
| Line Height | 1.5~1.6 | 장문 읽기 피로도 감소 |
| Line Width | 제한 있음 | iPad에서 한 줄이 너무 길어지는 것 방지 |
| Paragraph Spacing | 적당한 여백 | 문단 간 시각적 구분 |

Bear 2에서는 마크다운 문법이 편집 중인 줄에서만 보이고, 나머지는 렌더링된 상태로 표시된다. 사용자가 마크다운을 몰라도 쓸 수 있게 만든 거다. 하단에는 포맷팅 바가 있어서 텍스트 스타일, 테이블, 링크를 빠르게 삽입할 수 있다.

---

## 기존 에디터 코드: 뭐가 문제였나

기존 Flutter 노트 에디터 코드를 보자:

```dart
// 기존 코드 — 전형적인 초기 Material3 스타일
body: SingleChildScrollView(
  padding: const EdgeInsets.all(16),
  child: Column(
    children: [
      TextField(
        style: theme.textTheme.headlineSmall?.copyWith(
          fontWeight: FontWeight.bold,
        ),
        decoration: InputDecoration(
          border: InputBorder.none,
        ),
      ),
      const Divider(),  // 굵은 구분선
      TextField(
        style: theme.textTheme.bodyLarge,  // 시스템 기본 본문 스타일
        minLines: 20,
      ),
    ],
  ),
),
```

문제점 세 가지:

1. **`const Divider()`** — 1px 검은 선이 제목과 본문 사이를 강하게 끊는다. Bear는 이런 하드한 구분선을 쓰지 않는다.
2. **`theme.textTheme.bodyLarge`** — 시스템 기본 폰트 사이즈와 line height. 장문 노트에서 읽기 불편하다.
3. **메타 정보 없음** — 날짜, 단어 수 같은 정보가 전혀 없다. 글을 쓰는 사람 입장에서 진행도를 가늠할 수 없다.

---

## Bear 스타일 에디터 구현

### 메타 정보 줄 추가

제목 바로 아래에 날짜, 단어 수, 글자 수를 작게 표시한다. Bear에서 노트를 열면 비슷한 메타 정보가 보인다.

```dart
Widget _buildMetaInfoRow(ThemeData theme, ColorScheme colorScheme) {
  final date = _currentPaper?.updatedAt ?? DateTime.now();
  final text = _contentController.text.trim();
  final wordCount = text.isEmpty ? 0 : text.split(RegExp(r'\s+')).length;
  final charCount = _contentController.text.length;
  final dateStr = '${date.year}년 ${date.month}월 ${date.day}일';

  final metaStyle = theme.textTheme.bodySmall?.copyWith(
    color: colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
    fontSize: 12,
  );
  final divider = Padding(
    padding: const EdgeInsets.symmetric(horizontal: 8),
    child: Container(width: 1, height: 10, color: colorScheme.outlineVariant),
  );

  return Row(
    children: [
      Text(dateStr, style: metaStyle),
      divider,
      Text('$wordCount 단어', style: metaStyle),
      divider,
      Text('$charCount 자', style: metaStyle),
    ],
  );
}
```

단어 수가 실시간으로 업데이트되려면 `_onTextChanged`에서 `setState`를 호출해야 한다. 기존에는 `_hasUnsavedChanges = true`만 했는데, `setState`로 감싸면 메타 줄이 타이핑할 때마다 갱신된다:

```dart
void _onTextChanged() {
  setState(() {
    _hasUnsavedChanges = true;
  });
  // Debounce auto-save는 그대로 유지
  _autoSaveTimer?.cancel();
  _autoSaveTimer = Timer(const Duration(milliseconds: 500), () {
    if (_hasUnsavedChanges && mounted) _savePaper();
  });
}
```

### 구분선과 본문 타이포그래피

`const Divider()`를 0.5px 높이의 반투명 선으로 교체하고, 본문 TextField의 line-height를 1.72로 올렸다:

```dart
// 극도로 얇은 구분선
Container(
  height: 0.5,
  color: colorScheme.outlineVariant.withValues(alpha: 0.4),
),

// Bear 스타일 본문
TextField(
  controller: _contentController,
  style: TextStyle(
    fontSize: 16,
    height: 1.72,        // Bear의 여유로운 line-height
    letterSpacing: 0.1,  // 미세한 자간
    color: colorScheme.onSurface,
  ),
  decoration: InputDecoration(
    border: InputBorder.none,
    contentPadding: EdgeInsets.zero,
  ),
  maxLines: null,
  minLines: 20,
),
```

`height: 1.72`는 한글과 영문이 섞인 텍스트에서 가독성이 좋은 값이다. Bear 기본값인 1.5~1.6보다 약간 높게 잡은 이유는, 한글이 영문보다 글리프 높이가 커서 같은 line-height에서도 더 빡빡해 보이기 때문이다.

### 마크다운 포맷 툴바

Bear 하단에 있는 포맷팅 바를 Flutter로 구현했다. Scaffold body를 Column으로 감싸고 아래에 44px 높이 툴바를 배치한다:

```dart
Widget _buildFormattingBar(BuildContext context, ThemeData theme,
    ColorScheme colorScheme, PaperState state) {
  return Container(
    decoration: BoxDecoration(
      color: colorScheme.surface,
      border: Border(
        top: BorderSide(
          color: colorScheme.outlineVariant.withValues(alpha: 0.4),
          width: 0.5,
        ),
      ),
    ),
    child: SafeArea(
      top: false,
      child: SizedBox(
        height: 44,
        child: Row(
          children: [
            _fmtBtn('H', () => _insertFormat('## ', ''), colorScheme),
            _fmtBtn('B', () => _insertFormat('**', '**'), colorScheme,
                bold: true),
            _fmtBtn('I', () => _insertFormat('*', '*'), colorScheme,
                italic: true),
            _fmtBtn('S', () => _insertFormat('~~', '~~'), colorScheme,
                strikethrough: true),
            Container(width: 0.5, height: 22,
                color: colorScheme.outlineVariant),
            _fmtBtn('•', () => _insertFormat('- ', ''), colorScheme),
            _fmtBtn('☐', () => _insertFormat('- [ ] ', ''), colorScheme),
            const Spacer(),
            IconButton(
              icon: Icon(Icons.auto_awesome, size: 18,
                  color: colorScheme.primary),
              onPressed: () => _showAiToolSheet(context, state),
            ),
          ],
        ),
      ),
    ),
  );
}
```

`_insertFormat` 메서드는 선택된 텍스트가 있으면 래핑하고, 없으면 커서 위치에 삽입한 뒤 prefix 뒤로 커서를 이동시킨다:

```dart
void _insertFormat(String prefix, String suffix) {
  final controller = _contentFocusNode.hasFocus
      ? _contentController : _titleController;
  final text = controller.text;
  final sel = controller.selection;

  if (!sel.isValid || sel.start == sel.end) {
    // 커서 위치에 삽입
    final pos = sel.isValid ? sel.start : text.length;
    final newText = text.replaceRange(pos, pos, '$prefix$suffix');
    controller.value = controller.value.copyWith(
      text: newText,
      selection: TextSelection.collapsed(offset: pos + prefix.length),
    );
  } else {
    // 선택 텍스트 래핑
    final selected = sel.textInside(text);
    final newText = text.replaceRange(
        sel.start, sel.end, '$prefix$selected$suffix');
    controller.value = controller.value.copyWith(
      text: newText,
      selection: TextSelection.collapsed(
        offset: sel.start + prefix.length + selected.length + suffix.length,
      ),
    );
  }
}
```

---

## Glassmorphism 알림 히스토리 구현

### 글래스모피즘이란

Glassmorphism은 반투명 유리 느낌의 UI 스타일이다. Apple이 iOS 26에서 "Liquid Glass"라는 이름으로 전면 도입하면서 트렌드가 됐다. 핵심 요소 네 가지:

| 요소 | 구현 방법 | 역할 |
|------|----------|------|
| Blur | `BackdropFilter` + `ImageFilter.blur` | 뒤 콘텐츠를 흐리게 |
| Transparency | `color.withValues(alpha: 0.7)` | 반투명 배경 |
| Border | 얇은 반투명 테두리 | 유리 경계선 표현 |
| Rounded corners | `BorderRadius.circular(16)` | 부드러운 카드 형태 |

### Flutter에서의 현실

2026년 3월 기준, Flutter는 아직 iOS 26 Liquid Glass를 공식 지원하지 않는다. flutter/flutter#170310 이슈에서 논의가 진행 중이고, Material과 Cupertino 라이브러리를 분리해서 더 빠르게 대응하겠다는 방향이 잡혔다.

현재 사용 가능한 방법:

- **`BackdropFilter`** — Flutter 내장. 기본적인 blur 효과
- **`liquid_glass_renderer` 패키지** — Impeller 엔진 기반 커스텀 셰이더
- **`oc_liquid_glass` 패키지** — 유사한 접근, 초기 개발 단계
- **`cupertino_native` 패키지** — 네이티브 iOS 컴포넌트 직접 사용

프로덕션에서는 `BackdropFilter`가 가장 안정적이다. 다만 성능 주의가 필요하다.

### 기존 알림 리스트의 문제

기존 코드를 보면 디자인 문제가 명확하다:

```dart
// 기존: 왼쪽 4px 색 border만 있는 민밋한 리스트
child: Container(
  decoration: BoxDecoration(
    border: Border(
      left: BorderSide(
        color: notification.isRead
            ? Colors.grey.shade300    // 하드코딩
            : AppColors.primary,
        width: 4,
      ),
    ),
  ),
  child: // 텍스트만 나열...
),
```

더 심각한 건 `_getNotificationIcon()`과 `_getNotificationColor()` 메서드가 정의돼 있는데 리스트 아이템에서 전혀 호출하지 않고 있었다는 거다. 아이콘 없이 텍스트만 나열하고 있었다.

### Glass 카드 리스트로 교체

`ClipRRect` → `BackdropFilter` → 반투명 `Container` 순서로 감싸면 글래스 효과가 나온다:

```dart
child: ClipRRect(
  borderRadius: BorderRadius.circular(16),
  child: BackdropFilter(
    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
    child: Container(
      decoration: BoxDecoration(
        // 읽음/안읽음 상태에 따라 배경색 차별화
        color: notification.isRead
            ? cs.surface.withValues(alpha: 0.7)
            : cs.primaryContainer.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: notification.isRead
              ? cs.outlineVariant.withValues(alpha: 0.3)
              : cs.primary.withValues(alpha: 0.3),
          width: 0.5,
        ),
      ),
      child: // 아이콘 + 텍스트 Row
    ),
  ),
),
```

`ClipRRect`가 반드시 `BackdropFilter` 바깥에 있어야 한다. 안 그러면 blur가 카드 영역 밖으로 새어나간다.

알림 타입별 아이콘도 드디어 리스트에 연결했다:

```dart
// 알림 타입에 따른 아이콘 + 컬러 원형 배경
Container(
  width: 40,
  height: 40,
  decoration: BoxDecoration(
    color: iconColor.withValues(alpha: 0.15),
    shape: BoxShape.circle,
  ),
  child: Icon(iconData, size: 20, color: iconColor),
),
```

읽지 않은 알림은 제목 옆에 작은 파란 dot(8px)을 추가했다. iOS 메일 앱에서 볼 수 있는 패턴이다.

---

## BackdropFilter 성능 최적화

`BackdropFilter`는 매 프레임마다 뒤의 콘텐츠를 blur 처리하기 때문에 비용이 높다. Flutter GitHub 이슈 #32804에서도 오랫동안 논의된 문제다.

### 지켜야 할 규칙

| 규칙 | 이유 |
|------|------|
| `ClipRRect`로 영역 제한 | 전체 화면 blur 방지, repaint 영역 최소화 |
| sigma 값 6~12 유지 | 너무 높으면 GPU 부담 급증 |
| 중첩 `BackdropFilter` 금지 | 기하급수적 비용 증가 |
| `RepaintBoundary` 활용 | 정적 blur 영역 캐싱 |
| Impeller 엔진 사용 | Skia 대비 셰이더 성능 우수 |

### 저사양 기기 대응

Android 저사양 기기에서는 blur 셰이더가 느릴 수 있다. 플랫폼이나 기기 성능에 따라 fallback을 제공하는 것이 좋다:

```dart
// 저사양 기기에서 blur 없이 반투명 배경만 사용
final useBlur = !Platform.isAndroid || isHighEndDevice;

if (useBlur) {
  return ClipRRect(
    child: BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
      child: glassContainer,
    ),
  );
} else {
  return glassContainer; // blur 없이 반투명만
}
```

접근성도 고려해야 한다. iOS의 "투명도 줄이기(Reduce Transparency)" 설정이 켜져 있으면 blur 대신 불투명 배경을 써야 한다. Flutter에서 이 설정을 직접 감지하려면 Platform Channel이 필요한데, 대부분의 경우 `MediaQuery.of(context).highContrast` 체크로 충분하다.

---

## 하드코딩 컬러 마이그레이션

Bear 에디터와 Glassmorphism만큼 중요한 게 하드코딩된 색상을 `colorScheme` 토큰으로 교체하는 작업이다. 다크 모드에서 `Colors.blue.shade50`이 그대로 나오면 눈이 아프다.

### 변환 테이블

| Before (하드코딩) | After (colorScheme) | 용도 |
|-------------------|---------------------|------|
| `Colors.grey` | `cs.surfaceContainerHighest` | 기본 회색 배경 |
| `Colors.grey.shade300` | `cs.outlineVariant` | 비활성 보더 |
| `Colors.grey.shade600` | `cs.onSurfaceVariant` | 보조 텍스트 |
| `Colors.blue.shade50` | `cs.primaryContainer` | 강조 배경 |
| `Colors.blue.shade200` | `cs.primary.withValues(alpha: 0.3)` | 강조 보더 |
| `Colors.white` | `cs.onPrimary` | 강조 위 텍스트 |
| `Colors.red` | `cs.error` | 에러/삭제 |

`Colors.amber`(중요 표시), `Colors.green`(성공) 같은 시맨틱 컬러는 의도적으로 유지했다. 이런 색상은 의미를 전달하는 역할이라 테마에 따라 바뀌면 안 된다.

### InputDecoration도 네이티브로

`OutlineInputBorder()`는 웹 폼 느낌을 준다. 네이티브 앱에서는 filled 배경 + focus 시에만 테두리가 나타나는 패턴이 자연스럽다:

```dart
decoration: InputDecoration(
  border: InputBorder.none,
  filled: true,
  fillColor: cs.surfaceContainerHighest.withValues(alpha: 0.4),
  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
  enabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(12),
    borderSide: BorderSide.none,
  ),
  focusedBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(12),
    borderSide: BorderSide(color: cs.primary, width: 1),
  ),
),
```

---

## 마이그레이션 체크리스트

디자인 시스템 마이그레이션을 할 때 놓치기 쉬운 항목들이다:

1. **`const TextStyle` 하드코딩** — `theme.textTheme.bodyMedium`으로 교체
2. **`Colors.xxx` 직접 사용** — `colorScheme` 토큰으로 교체
3. **`OutlineInputBorder()`** — filled + borderless 패턴으로 교체
4. **정의만 있고 미사용 메서드** — 아이콘/컬러 헬퍼가 UI에 연결 안 된 경우
5. **`const` 위젯의 `TextStyle`** — `Theme.of(context)` 접근 불가라 `const` 제거 필요

특히 4번은 코드 리뷰에서도 잡기 어렵다. 메서드가 존재하니까 쓰는 줄 알았는데, 실제로는 리스트 빌더에서 호출하지 않고 있었다. IDE의 unused method 경고를 무시하지 말자.

---

## 결론

Bear 스타일 에디터의 핵심은 "안 보이는 것"에 있다. 굵은 구분선을 없애고, 메타 정보를 작게 넣고, line-height를 1.7 이상으로 여유롭게 잡는 것만으로도 체감 품질이 크게 올라간다.

Glassmorphism은 `BackdropFilter` + `ClipRRect` + 반투명 `Container` 세 가지 조합이면 충분하다. 다만 성능 비용이 있으니 blur 영역을 최소화하고, 저사양 기기 fallback을 준비해두는 게 좋다.

하드코딩된 `Colors.xxx`를 `colorScheme` 토큰으로 바꾸는 건 지루한 작업이지만, 다크 모드 대응과 디자인 일관성을 위해 반드시 해야 한다. "버튼만 마이그레이션하고 나머지는 나중에" 하면 결국 에디터 화면이 네이티브 같지 않다는 피드백을 받게 된다.
