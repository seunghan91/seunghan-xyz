---
title: "Flutter UI 전수조사 — GlassAppBar TabBar overflow와 Colors.white 라이트모드 버그"
date: 2025-09-24
draft: false
tags: ["Flutter", "UI", "GlassAppBar", "TabBar", "overflow", "다크모드", "라이트모드"]
description: "앱 전체 화면을 대상으로 bottom overflow와 Colors.white 텍스트 버그를 전수조사한 과정. preferredSize 메커니즘과 라이트모드에서 흰 텍스트가 사라지는 원인을 정리했다."
cover:
  image: "/images/og/flutter-glassappbar-tabbar-overflow-colors-white-lightmode.png"
  alt: "Flutter Glassappbar Tabbar Overflow Colors White Lightmode"
  hidden: true
---

Flutter 앱을 어느 정도 만들다 보면 꼭 한 번씩 마주치는 두 가지 버그가 있다.

하나는 `bottom overflowed by N pixels` 에러, 다른 하나는 라이트모드에서 텍스트가 배경에 묻혀 보이지 않는 현상이다.

둘 다 원인은 단순한데, 전체 화면을 대상으로 전수조사하기 전까지는 "일부 화면에서 이상하다" 수준으로만 인식하기 쉽다. 이번에 앱 전체 50개 페이지를 한 번 훑어보고 나서야 패턴이 보였다.

---

## GlassAppBar + TabBar overflow의 진짜 원인

커스텀 `GlassAppBar`를 만들어서 쓰고 있었다. `bottom: TabBar(...)` 를 붙이면 AppBar 아래에 탭이 생기는 구조다.

```dart
GlassAppBar(
  title: '모니터링',
  bottom: TabBar(
    tabs: [
      Tab(icon: Icon(Icons.list), text: '목록'),
      Tab(icon: Icon(Icons.bar_chart), text: '현황'),
    ],
  ),
)
```

이게 특정 화면에서만 `bottom overflowed` 에러를 냈다. 다른 화면의 TabBar는 정상이었다.

차이를 찾아보니 GlassAppBar 내부의 `preferredSize` 구현에 있었다.

```dart
class GlassAppBar extends StatelessWidget implements PreferredSizeWidget {
  final double bottomHeight;

  const GlassAppBar({
    this.bottomHeight = 0,  // 기본값이 0
    ...
  });

  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + bottomHeight);
}
```

`preferredSize`는 Scaffold가 AppBar에게 "이 높이만큼 공간을 줄게"라고 알려주는 계약이다. 실제 렌더링된 높이와 달라지면 넘친다.

**TabBar 높이별 필요한 bottomHeight:**
- 텍스트만 있는 탭 (Tab(text: ...)): **48px**
- 아이콘+텍스트 탭 (Tab(icon: ..., text: ...)): **80px** (아이콘 24 + 텍스트 + 패딩)

```dart
GlassAppBar(
  title: '모니터링',
  bottomHeight: 80,  // icon+text 탭
  bottom: TabBar(...),
)
```

이걸 명시하지 않으면 `preferredSize`가 `kToolbarHeight`(56px)로만 잡히고, 실제 렌더링은 그보다 높아서 overflow가 발생한다.

---

## TabBar가 있으면 ListView padding도 같이 고쳐야 한다

AppBar에 TabBar가 붙으면 body의 실제 시작 위치도 달라진다. `extendBodyBehindAppBar: true` 를 쓰는 경우 특히 그렇다.

기존 코드에 이런 식의 하드코딩이 있었다.

```dart
ListView(
  padding: const EdgeInsets.fromLTRB(16, 100, 16, 24),
  // top: 100 = 대충 AppBar 높이겠지...
```

이건 당장은 동작하지만 TabBar 높이가 바뀌거나 기기 상단 안전영역이 달라지면 틀어진다.

MediaQuery 기반으로 계산하는 게 맞다.

```dart
ListView(
  padding: EdgeInsets.fromLTRB(
    16,
    MediaQuery.paddingOf(context).top + kToolbarHeight + 80, // statusBar + toolbar + tabBar
    16,
    24,
  ),
```

---

## Colors.white 텍스트 — 라이트모드에서 사라지는 버그

다크모드에서만 개발하다 보면 자주 생기는 패턴이다.

```dart
Text(
  document.name,
  style: const TextStyle(color: Colors.white),
)
```

다크모드 배경이 `#1A1A2E` 같은 어두운 색이니까 흰 텍스트가 잘 보인다. 근데 라이트모드로 전환하면 배경이 흰색에 가까워지고, 흰 텍스트가 완전히 사라진다.

해결은 간단하다. `ThemeExtension`으로 만들어 둔 `colors.text`를 쓰면 된다.

```dart
final colors = context.glassColors;

Text(
  document.name,
  style: TextStyle(color: colors.text),  // 다크: 흰색, 라이트: 어두운 색 자동 전환
)
```

`GlassColors`에서 `text` 색상은 이렇게 정의된다.

```dart
// 다크모드
static const GlassColors dark = GlassColors(
  text: Color(0xFFFFFFFF),  // 흰색
  ...
);

// 라이트모드
static const GlassColors light = GlassColors(
  text: Color(0xFF1A1A2E),  // 어두운 남색
  ...
);
```

한 번 쓰고 나면 모드에 관계없이 적절한 색이 자동으로 적용된다.

---

## 어떤 건 Colors.white를 그대로 써야 한다

전수조사 중에 모든 `Colors.white`를 고치면 안 된다는 걸 구분하는 게 중요했다.

**고쳐야 하는 것 — 배경이 투명/흰색인 위젯 위의 텍스트:**
```dart
// GlassCard 위
Text(title, style: const TextStyle(color: Colors.white))  // ❌

// AlertDialog title
Text('삭제', style: const TextStyle(color: Colors.white))  // ❌
```

**그대로 둬야 하는 것 — 진한 색 배경 위:**
```dart
// 그라디언트 버튼 위 아이콘
Icon(Icons.send, color: Colors.white)  // ✅

// 빨간 배경 뱃지 위 숫자
Text('$count', style: TextStyle(color: Colors.white))  // ✅ (color: colors.error 배경)

// 아바타 원형 배경 위 이니셜
Text(name[0], style: TextStyle(color: Colors.white))  // ✅ (accent 그라디언트 배경)
```

판단 기준은 단순하다. **부모 Container의 color/gradient를 확인하라.** 배경이 코드에서 직접 진한 색으로 지정된 경우엔 `Colors.white`를 유지한다. `GlassCard`, `AlertDialog`, `colors.surface` 같은 테마 기반 배경이면 `colors.text`로 교체해야 한다.

---

## 전수조사를 어떻게 했나

50개 파일을 수동으로 보기엔 너무 많으니 grep으로 패턴을 먼저 잡았다.

```bash
# TabBar가 있는 파일 찾기
grep -rn "bottom: TabBar" lib/ --include="*.dart"

# Colors.white 텍스트가 있는 파일 목록
grep -rn "color: Colors\.white" lib/ --include="*.dart"
```

이후 실제 파일을 읽어서 "이 `Colors.white`가 어떤 배경 위에 있는가"를 확인했다.

TabBar overflow는 결국 한 파일에서만 실제 버그였고, 나머지는 모두 `GlassDecoration.button` 같은 진한 배경 위라 정상이었다. 잘못 알람이 많이 뜨는 상황이라 하나하나 확인하는 수밖에 없었다.

---

## 핵심 체크리스트

커스텀 AppBar + TabBar를 만들 때:

- [ ] `preferredSize`에 TabBar 높이가 포함되어 있는가?
- [ ] text-only 탭이면 +48, icon+text 탭이면 +80
- [ ] body의 ListView/Column top padding이 AppBar + TabBar 높이를 반영했는가?

`Colors.white` 텍스트를 쓸 때:

- [ ] 부모의 배경색이 코드에서 직접 진한 색으로 고정되어 있는가?
- [ ] 아니라면 `colors.text`로 교체
- [ ] `const TextStyle(color: Colors.white)`에서 `const` 제거도 잊지 말 것
