---
title: "Flutter + Web 디자인 토큰 동기화 — Storybook 기반 디자인 시스템 구축기"
date: 2026-03-08
draft: false
tags: ["Flutter", "Svelte", "Storybook", "디자인시스템", "토큰", "CSS"]
description: "모바일 앱(Flutter)과 웹 디자인 키트(Svelte+Storybook)의 디자인 토큰을 하나의 소스로 맞추는 작업. 색상·라디우스·그림자를 CSS 변수와 Dart 상수로 동기화하고, 카테고리 카드 overflow까지 고친 과정."
---

Flutter 앱을 개발하다 보면 항상 부딪히는 문제가 있다. 디자이너는 Figma나 웹 기반 도구로 작업하는데, 개발자는 Dart 코드에 색상을 하드코딩한다. `Color(0xFF10B981)` 같은 값이 `app_colors.dart`에만 있고, 웹 쪽 CSS에는 `#10B981`로 따로 있다. 두 곳을 따로 관리하다 보면 어느 순간 서로 달라져 있다.

이번에 Svelte+Storybook 기반 웹 디자인 키트와 Flutter 앱의 토큰을 하나의 기준으로 맞추는 작업을 했다. 삽질한 내용 위주로 정리한다.

---

## 문제: 두 곳에 사는 디자인 토큰

기존 상태는 이랬다.

**웹 (CSS)**
```css
:root {
  --color-primary: #0000FF;  /* 기본값 그대로 */
  --radius: 0px;
}
```

**Flutter (Dart)**
```dart
class AppColors {
  static const primary = Color(0xFF10B981);  /* 실제 색상 */
}
```

CSS 쪽은 스타터 키트 기본값이 그대로 남아 있고, Flutter는 실제 브랜드 색상이 들어가 있다. Storybook으로 컴포넌트를 띄우면 파란색 버튼이 나오는데 앱에서는 초록색이다.

---

## 해결 방향: CSS가 Single Source of Truth

토큰 체계를 잡는 방향을 이렇게 정했다.

1. **CSS 변수** → 웹 Storybook의 기준
2. **Dart 상수** → Flutter의 기준
3. 두 곳을 **수동으로 동기화** (자동화는 나중에)

자동화(Style Dictionary 같은 툴)를 쓰면 이상적이지만, 프로젝트 규모가 크지 않으면 오버엔지니어링이다. 지금은 토큰 파일을 잘 정리해두고 한 곳에서 같이 관리하는 걸로 충분하다.

---

## tokens.css 정리

기존 파일에서 브랜드에 맞게 전면 교체했다.

```css
:root {
  /* Primary */
  --color-primary:       #10B981;
  --color-primary-dark:  #059669;
  --color-primary-light: rgba(16, 185, 129, 0.08);

  /* Border Radius */
  --radius:      12px;   /* 기본값 */
  --radius-sm:   8px;
  --radius-md:   12px;
  --radius-lg:   16px;
  --radius-xl:   20px;
  --radius-2xl:  24px;
  --radius-pill: 9999px;

  /* Shadow (Showcase 앱 참조, 미니멀) */
  --shadow-1: 0 1px 3px rgba(0, 0, 0, 0.06);
  --shadow-2: 0 2px 8px rgba(0, 0, 0, 0.08);
  --shadow-3: 0 4px 20px rgba(0, 0, 0, 0.10);
  --shadow-4: 0 8px 40px rgba(0, 0, 0, 0.14);

  /* Motion */
  --duration-fast:   150ms;
  --duration-normal: 300ms;
  --ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

포인트는 `--radius: 0px` 기본값을 `12px`로 바꾼 것이다. 스타터 키트가 라디우스를 0으로 두고 있었는데, 모바일 앱 느낌을 내려면 기본 12px가 맞다.

---

## Flutter 토큰 파일 분리

기존에는 `app_colors.dart` 하나에 모든 게 들어가 있었다. 이번에 역할별로 파일을 나눴다.

### app_radius.dart (신규)

```dart
class AppRadius {
  static const double sm   = 8;
  static const double md   = 12;
  static const double lg   = 16;
  static const double xl   = 20;
  static const double xxl  = 24;
  static const double pill = 9999;

  static final BorderRadius borderMd  = BorderRadius.circular(md);
  static final BorderRadius borderXl  = BorderRadius.circular(xl);
  static final BorderRadius borderXxl = BorderRadius.circular(xxl);
  // ...
}
```

`BorderRadius.circular(20)` 같은 매직 넘버를 코드 곳곳에 쓰는 대신, `AppRadius.borderXl` 하나로 통일된다. 나중에 라디우스를 바꾸고 싶으면 한 곳만 수정하면 된다.

### app_shadows.dart (신규)

```dart
class AppShadows {
  static const List<BoxShadow> xs = [
    BoxShadow(
      offset: Offset(0, 1),
      blurRadius: 3,
      color: Color.fromRGBO(0, 0, 0, 0.06),
    ),
  ];

  static const List<BoxShadow> md = [
    BoxShadow(
      offset: Offset(0, 4),
      blurRadius: 20,
      color: Color.fromRGBO(0, 0, 0, 0.10),
    ),
  ];
  // ...
}
```

`BoxDecoration(boxShadow: AppShadows.sm)` 형태로 쓴다. CSS의 `--shadow-2`와 숫자를 맞춰뒀다.

### app_colors.dart 확장

카테고리별 색상을 추가했다. 기능 카테고리마다 색상이 다른 앱이라 필요했다.

```dart
// 카테고리별 색상
static const catParking     = Color(0xFF3B82F6);  // 파랑
static const catNoise       = Color(0xFF8B5CF6);  // 보라
static const catTrash       = Color(0xFFF59E0B);  // 노랑
static const catRoad        = Color(0xFFEF4444);  // 빨강
static const catStreetlight = Color(0xFF06B6D4);  // 하늘
static const catOther       = Color(0xFF6B7280);  // 회색
```

---

## app_theme.dart 매직 넘버 제거

기존에 하드코딩된 숫자를 전부 토큰으로 교체했다.

**Before**
```dart
shape: RoundedRectangleBorder(
  borderRadius: BorderRadius.circular(24),
),
```

**After**
```dart
shape: RoundedRectangleBorder(
  borderRadius: AppRadius.borderXxl,
),
```

버튼은 `AppRadius.borderXl(20)`, 카드는 `AppRadius.borderXxl(24)`, 인풋은 `AppRadius.borderMd(12)`. Tailwind에서 `rounded-xl` 쓰듯이 Flutter에서도 같은 감각으로 쓸 수 있게 됐다.

---

## Storybook tailwind.config.js 확장

CSS 변수를 Tailwind 클래스로 쓰려면 config에 바인딩이 필요하다.

```js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: 'var(--color-primary)',
          dark: 'var(--color-primary-dark)',
          light: 'var(--color-primary-light)',
        },
        cat: {
          parking:     'var(--color-cat-parking)',
          noise:       'var(--color-cat-noise)',
          trash:       'var(--color-cat-trash)',
          road:        'var(--color-cat-road)',
          streetlight: 'var(--color-cat-streetlight)',
          other:       'var(--color-cat-other)',
        },
      },
      borderRadius: {
        md:   'var(--radius-md)',
        xl:   'var(--radius-xl)',
        pill: 'var(--radius-pill)',
      },
    },
  },
};
```

이렇게 하면 Svelte 컴포넌트에서 `class="bg-primary rounded-xl"` 형태로 쓸 수 있고, 색상을 바꾸고 싶을 때 `tokens.css`의 변수 하나만 수정하면 Storybook 전체에 반영된다.

---

## 삽질: ReportCategoryCard overflow

시뮬레이터에 올리자마자 노란 줄무늬 경고가 떴다.

```
A RenderFlex overflowed by 3.6 pixels on the bottom.
  Column Column:file:///…/report_category_card.dart:38
  constraints: BoxConstraints(w=75.7, h=70.4)
```

카드 높이 70.4px에 내용이 3.6px 넘친 것이다. 구조를 보면 이유가 명확하다.

```
padding(16) + 아이콘(44) + spacing(10) + 텍스트(약 20) + padding(16) = 106px
```

컨테이너 높이가 70px인데 내용이 106px. 당연히 넘친다.

```dart
// Before
padding: const EdgeInsets.all(16),
const SizedBox(height: 10),

// After
padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
const SizedBox(height: 6),
```

padding을 줄이고 간격을 조금 좁혔더니 해결됐다. 카드 크기를 키우는 방법도 있지만, 그리드 레이아웃 전체를 건드려야 해서 이 쪽이 더 빠르다.

---

## 디렉토리 구조

최종적으로 정리된 구조다.

```
project/
├── design_guide/           # 디자인 가이드 문서 (6개)
│   ├── 00-overview.md
│   ├── 01-reference-analysis.md
│   ├── 02-design-tokens.md
│   ├── 03-component-plan.md
│   ├── 04-page-plan.md
│   └── 05-implementation-roadmap.md
│
├── design_kit/             # Svelte + Storybook
│   ├── styles/tokens.css   # 브랜드 토큰 (Single Source of Truth)
│   ├── tailwind.config.js  # 토큰 바인딩
│   └── components/         # 53개 컴포넌트
│
└── mobile/lib/theme/       # Flutter 토큰 동기화
    ├── app_colors.dart
    ├── app_radius.dart     # 신규
    ├── app_shadows.dart    # 신규
    └── app_theme.dart
```

---

## 정리

**디자인 토큰 동기화의 핵심은 구조화다.** 색상 하나만 있어도 `primary`, `primary-dark`, `primary-light`로 나눠두면 나중에 쓰는 사람이 의도를 이해할 수 있다. 매직 넘버 `BorderRadius.circular(20)` 하나를 없애는 게 사소해 보여도, 프로젝트 전체에 통일성을 만든다.

Flutter와 Web 토큰을 완전히 자동화하려면 Style Dictionary 같은 툴이 필요하다. 하지만 소규모 프로젝트에서는 파일 두 개(`tokens.css`, `app_*.dart`)를 잘 관리하는 것만으로도 충분하다. 오버엔지니어링보다 지금 작동하는 단순한 구조가 낫다.
