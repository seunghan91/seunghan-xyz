---
title: "Flutter GoRouter ShellRoute로 바텀 네비게이션 전역 유지하기 — 삽질부터 Liquid Glass 인터랙션까지"
date: 2026-03-24
draft: false
tags: ["Flutter", "GoRouter", "ShellRoute", "iOS", "BLoC"]
categories: ["iOS", "Flutter"]
description: "Flutter GoRouter에서 context.push 시 바텀 네비게이션이 사라지는 문제를 ShellRoute로 해결한 과정. BLoC one-shot 네비게이션 트리거 버그 패턴과 iOS Liquid Glass 인터랙션 구현까지."
---

## 바텀 네비가 사라지는 순간

Flutter 앱을 만들다 보면 어느 순간 이런 상황을 만난다. 메인 화면에 탭 5개짜리 바텀 네비게이션 바가 있고, 할일 수정이나 새 메모 생성 버튼을 누르면 `context.push('/tasks/new')`로 화면을 전환한다. 그런데 화면이 전환되는 순간 바텀 네비가 통째로 사라진다.

iOS 네이티브 앱에서는 탭 안에서 push 하면 탭 바가 유지된다. Apple의 메모 앱에서 메모를 열어도, 미리 알림에서 항목을 수정해도 하단 탭 바는 그대로 있다. 그런데 Flutter에서는 기본적으로 이렇게 동작하지 않는다.

원인을 찾아보니 라우터 구조 자체의 문제였다.

---

## 원인: flat GoRoute 구조의 한계

GoRouter를 사용하면 보통 이런 식으로 라우트를 정의한다:

```dart
GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, __) => SplashScreen()),
    GoRoute(path: '/home', builder: (_, __) => MainScaffold()),
    GoRoute(path: '/tasks/new', builder: (_, __) => TaskEditScreen()),
    GoRoute(path: '/tasks/:id', builder: (_, state) => TaskEditScreen(taskId: state.pathParameters['id'])),
    GoRoute(path: '/settings', builder: (_, __) => SettingsScreen()),
    // ... 수십 개의 라우트가 같은 레벨에 나열
  ],
)
```

모든 라우트가 flat하게 나열되어 있다. 이 구조에서 `context.push('/tasks/new')`를 호출하면 GoRouter의 root Navigator가 **전체 화면을 교체**한다. `MainScaffold`(바텀 네비 포함)가 통째로 가려지고, `TaskEditScreen`만 화면에 남는다.

이건 Flutter의 Navigator 동작 방식 때문이다. `push`는 새 화면을 Navigator 스택 위에 올리는데, flat 구조에서는 모든 라우트가 root Navigator에 속하므로 MainScaffold 전체가 아래에 깔리게 된다.

---

## 해결법 비교: 3가지 접근법

| 접근법 | 난이도 | 탭 상태 보존 | 바텀 네비 유지 | 단점 |
|--------|--------|-------------|---------------|------|
| 각 화면에 nav 복사 | 낮음 | X | O (깜빡임) | 해킹적, 전환 애니메이션 부자연스러움 |
| `ShellRoute` | 중간 | △ | O | 탭 전환 시 내부 상태 초기화 가능 |
| `StatefulShellRoute.indexedStack` | 높음 | O | O | 라우터 전체 재설계 필요 |

각각의 특징을 자세히 보자.

### 1. 각 화면에 바텀 네비를 복사하는 방법

가장 단순하다. `TaskEditScreen`의 Scaffold에 동일한 `BottomNavigationBar`를 넣는 것이다. 하지만 화면 전환 시 기존 네비가 사라졌다가 새 네비가 나타나면서 깜빡임이 생긴다. 네비의 선택 상태도 별도로 관리해야 한다.

### 2. ShellRoute

GoRouter가 제공하는 `ShellRoute`는 "UI 껍데기"를 유지하면서 내부 컨텐츠만 교체하는 구조다:

```dart
ShellRoute(
  navigatorKey: _shellNavigatorKey,
  builder: (context, state, child) => AppShell(child: child),
  routes: [
    GoRoute(path: '/home', builder: ...),
    GoRoute(path: '/tasks/new', builder: ...),
    GoRoute(path: '/tasks/:id', builder: ...),
  ],
)
```

`AppShell`이 바텀 네비를 가지고 있고, `child`에 현재 라우트의 화면이 들어온다. 화면이 전환되어도 `AppShell`은 유지되므로 바텀 네비가 사라지지 않는다.

### 3. StatefulShellRoute.indexedStack

이게 iOS 네이티브와 가장 유사한 패턴이다. 각 탭이 독립된 Navigator를 가지고, 탭 전환 시 이전 탭의 상태가 보존된다:

```dart
StatefulShellRoute.indexedStack(
  builder: (context, state, navigationShell) {
    return ScaffoldWithNavBar(navigationShell: navigationShell);
  },
  branches: [
    StatefulShellBranch(routes: [
      GoRoute(path: '/search', builder: ..., routes: [
        GoRoute(path: 'detail/:id', builder: ...),
      ]),
    ]),
    StatefulShellBranch(routes: [
      GoRoute(path: '/notes', builder: ..., routes: [
        GoRoute(path: ':id', builder: ...),
      ]),
    ]),
    // ... 더 많은 탭
  ],
)
```

Code With Andrea의 [가이드](https://codewithandrea.com/articles/flutter-bottom-navigation-bar-nested-routes-gorouter/)에서 이 패턴을 상세히 다루고 있다. 핵심은 `StatefulShellBranch`마다 별도의 `navigatorKey`를 두어 탭 간 네비게이션 스택이 독립적으로 유지된다는 점이다.

다만 기존 앱이 이미 `MainScaffold` 내부에서 탭을 `_screens[_currentIndex]`로 관리하고 있다면, 이 방식으로 마이그레이션하려면 라우터 전체를 재설계해야 한다. 현실적으로 ShellRoute가 적절한 중간 지점이었다.

---

## ShellRoute 적용 구현

### Navigator Key 분리

핵심은 root navigator와 shell navigator를 분리하는 것이다:

```dart
final _rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');
final _shellNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'shell');

GoRouter createAppRouter(BuildContext context) => GoRouter(
  navigatorKey: _rootNavigatorKey,
  routes: [
    // 인증/스플래시: root navigator (바텀 네비 없음)
    GoRoute(
      path: '/',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (_, __) => const SplashScreen(),
    ),
    GoRoute(
      path: '/auth/sign-in',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (_, __) => const SignInScreen(),
    ),

    // ShellRoute: 바텀 네비 유지 영역
    ShellRoute(
      navigatorKey: _shellNavigatorKey,
      builder: (context, state, child) => AppShell(child: child),
      routes: [
        GoRoute(path: '/home', builder: ...),
        GoRoute(path: '/tasks/new', builder: ...),
        GoRoute(path: '/tasks/:id', builder: ...),
        GoRoute(path: '/notes/:id', builder: ...),
        GoRoute(path: '/settings', builder: ...),
        // 바텀 네비가 보여야 하는 모든 라우트
      ],
    ),
  ],
);
```

`parentNavigatorKey: _rootNavigatorKey`를 명시한 라우트는 ShellRoute 바깥에서 렌더링된다. 로그인, 스플래시, 온보딩 같은 화면은 바텀 네비 없이 전체 화면으로 표시된다.

### AppShell 위젯

```dart
class AppShell extends StatefulWidget {
  const AppShell({super.key, required this.child});
  final Widget child;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _tabNotifier = TabStateNotifier();

  void _onTabTapped(int index) {
    _tabNotifier.setIndex(index);
    final location = GoRouterState.of(context).uri.toString();
    if (!location.startsWith('/home')) {
      context.go('/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return TabStateProvider(
      notifier: _tabNotifier,
      child: Stack(
        children: [
          Positioned.fill(child: widget.child),
          Positioned(
            left: 0, right: 0, bottom: 0,
            child: ListenableBuilder(
              listenable: _tabNotifier,
              builder: (context, _) => GlassBottomBar(
                currentIndex: _tabNotifier.currentIndex,
                onTap: _onTabTapped,
                items: [...],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
```

Stack 구조를 쓴 이유가 있다. Scaffold로 감싸면 `MainScaffold`가 이미 자체 Scaffold를 가지고 있어서 nested Scaffold 문제가 생긴다. Stack으로 바텀 네비를 overlay하면 자식 화면이 어떤 Scaffold 구조든 상관없이 동작한다.

### 탭 상태 동기화

Shell의 바텀 네비와 MainScaffold의 탭 상태를 동기화해야 한다. `ChangeNotifier` + `InheritedWidget` 패턴을 사용했다:

```dart
class TabStateNotifier extends ChangeNotifier {
  int _currentIndex = 0;
  int get currentIndex => _currentIndex;

  void setIndex(int index) {
    if (_currentIndex != index) {
      _currentIndex = index;
      notifyListeners();
    }
  }
}

class TabStateProvider extends InheritedNotifier<TabStateNotifier> {
  const TabStateProvider({
    super.key,
    required TabStateNotifier notifier,
    required super.child,
  }) : super(notifier: notifier);

  static TabStateNotifier of(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<TabStateProvider>()!
        .notifier!;
  }
}
```

MainScaffold는 initState에서 이 notifier를 구독하고, 탭 변경 시 양방향으로 동기화한다:

```dart
@override
void initState() {
  super.initState();
  WidgetsBinding.instance.addPostFrameCallback((_) {
    final tabNotifier = TabStateProvider.maybeOf(context);
    tabNotifier?.setIndex(_currentIndex);
    tabNotifier?.addListener(_onShellTabChanged);
  });
}

void _onShellTabChanged() {
  final tabNotifier = TabStateProvider.maybeOf(context);
  if (tabNotifier != null && tabNotifier.currentIndex != _currentIndex) {
    setState(() => _currentIndex = tabNotifier.currentIndex);
  }
}
```

---

## 번외: BLoC one-shot 네비게이션 트리거 함정

ShellRoute 작업 중에 발견한 별도 버그가 있다. BLoC에서 "아이템 생성 후 자동으로 상세 화면으로 이동"하는 패턴인데, 이게 잘못 구현되면 화면이 두 번 열린다.

### 문제 패턴

```dart
// State에 one-shot 네비게이션 트리거
class ItemState {
  final Item? lastCreatedItem;  // 생성 후 네비게이션용
  // ...
}

// BlocConsumer listener에서 네비게이션
BlocConsumer<ItemBloc, ItemState>(
  listenWhen: (prev, curr) =>
    prev.errorMessage != curr.errorMessage ||
    (prev.lastCreatedItem != curr.lastCreatedItem &&
     curr.lastCreatedItem != null),
  listener: (context, state) {
    if (state.errorMessage != null) {
      showError(state.errorMessage!);
      bloc.add(ErrorCleared());
    }
    if (state.lastCreatedItem != null) {
      context.push('/items/${state.lastCreatedItem!.id}');
    }
  },
)
```

이 코드에는 함정이 세 개 있다.

**함정 1: lastCreatedItem이 소비 후 클리어되지 않는다.**

`lastCreatedItem`이 한번 설정되면 그 값이 계속 남아있다. `copyWith`가 기본적으로 이전 값을 보존하기 때문이다. 나중에 `errorMessage` 변경으로 `listenWhen`이 트리거되면, listener 안의 두 번째 조건 `state.lastCreatedItem != null`도 여전히 true이므로 재네비게이션이 발생한다.

**함정 2: listenWhen의 OR 조건과 listener의 독립 체크가 불일치한다.**

`listenWhen`은 "errorMessage 변경 OR lastCreatedItem 변경"으로 트리거한다. 하지만 listener는 두 조건을 독립적으로 체크한다. `listenWhen`이 errorMessage 때문에 트리거되어도, listener는 lastCreatedItem을 다시 확인하고 네비게이션을 시도한다.

**함정 3: 빠른 더블 탭 방어가 없다.**

생성 버튼을 빠르게 두 번 누르면 두 개의 `CreateRequested` 이벤트가 BLoC 큐에 들어간다. 둘 다 순차 처리되면서 각각 `lastCreatedItem`을 설정하고, 각각 네비게이션을 트리거한다.

### 해결

```dart
// 1. 네비게이션 후 즉시 클리어 이벤트 발행
listener: (context, state) {
  if (state.lastCreatedItem != null) {
    bloc.add(const NavigationCompleted());  // 소비 후 클리어
    context.push('/items/${state.lastCreatedItem!.id}');
  }
},

// 2. BLoC에서 클리어 핸들러
Future<void> _onNavigationCompleted(event, emit) async {
  emit(state.copyWith(clearLastCreatedItem: true));
}

// 3. 생성 버튼에 가드 추가
bool _isCreating = false;

void _createItem() {
  if (_isCreating) return;
  _isCreating = true;
  bloc.add(CreateRequested(item));
}
```

이 패턴의 핵심: **BLoC에서 one-shot 네비게이션 트리거를 사용할 때는 반드시 "소비 후 초기화"해야 한다.** 상태가 immutable이라 이전 값이 계속 남기 때문이다.

felangel/bloc의 [Issue #201](https://github.com/felangel/bloc/issues/201)에서도 이 문제가 오래전부터 논의되어왔다. 해결 방법으로 `BlocListener`를 한 곳에만 두거나, 상태를 즉시 리셋하거나, `listenWhen`에서 정확히 해당 조건만 체크하는 방식이 제안되었다.

---

## iOS Liquid Glass 인터랙션을 Flutter에서 구현하기

바텀 네비의 구조를 바꾸면서 탭 인터랙션도 개선했다. iOS 26에서 도입된 Liquid Glass 디자인은 `.interactive()` 수식어를 통해 세 가지 터치 피드백을 제공한다:

1. **Press scale**: 누르면 0.85배로 축소, 놓으면 spring bounce로 복귀
2. **Touch-point illumination**: 터치 지점에서 빛이 방사형으로 퍼져나감
3. **Sliding indicator**: 탭 전환 시 인디케이터가 spring 물리로 슬라이딩

Flutter에서 네이티브 Liquid Glass를 쓰려면 `cupertino_native_plus` 패키지(iOS 26+ 필요)나 `liquid_glass_renderer` 패키지를 쓸 수 있지만, 바텀 네비 하나에 외부 패키지를 추가하기는 과하다. `AnimationController`로 직접 구현했다.

### Press Scale + Radial Ripple

```dart
class _GlassTabItemState extends State<_GlassTabItem>
    with TickerProviderStateMixin {
  late final AnimationController _pressController;
  late final Animation<double> _scaleAnimation;
  late final AnimationController _rippleController;
  late final Animation<double> _rippleScale;
  late final Animation<double> _rippleOpacity;

  @override
  void initState() {
    super.initState();
    // Press: 120ms down, 300ms spring back
    _pressController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 120),
      reverseDuration: const Duration(milliseconds: 300),
    );
    _scaleAnimation = Tween<double>(begin: 1.0, end: 0.85).animate(
      CurvedAnimation(
        parent: _pressController,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.elasticOut,
      ),
    );

    // Ripple: 500ms expand + fade
    _rippleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    _rippleScale = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _rippleController, curve: Curves.easeOutCubic),
    );
    _rippleOpacity = Tween<double>(begin: 0.5, end: 0.0).animate(
      CurvedAnimation(parent: _rippleController, curve: Curves.easeOut),
    );
  }

  void _onTapDown(TapDownDetails details) => _pressController.forward();
  void _onTapUp(TapUpDetails details) {
    _pressController.reverse();
    _rippleController.forward(from: 0.0);
    widget.onTap();
  }
  void _onTapCancel() => _pressController.reverse();
}
```

`Curves.elasticOut`이 핵심이다. 목표값을 살짝 넘었다가 돌아오는 bounce 효과로, iOS의 spring animation과 유사한 느낌을 준다. `Curves.easeOutBack`도 비슷하지만 bounce 폭이 다르다.

### Spring Sliding Indicator

탭 전환 시 인디케이터가 따라 움직이는 효과:

```dart
AnimatedAlign(
  duration: const Duration(milliseconds: 400),
  curve: Curves.easeOutBack,
  alignment: Alignment(
    tabCount > 1
        ? -1.0 + (2.0 * currentIndex / (tabCount - 1))
        : 0.0,
    0.0,
  ),
  child: Container(
    width: 52, height: 34,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(17),
      gradient: LinearGradient(
        colors: [
          primaryColor.withValues(alpha: 0.18),
          primaryColor.withValues(alpha: 0.08),
        ],
      ),
    ),
  ),
)
```

`Alignment`의 x값을 -1.0(첫 번째 탭)부터 1.0(마지막 탭)까지 매핑하면, `AnimatedAlign`이 자동으로 spring 느낌의 애니메이션을 적용한다.

---

## 현재 Flutter의 Liquid Glass 생태계

2025년 기준으로 Flutter에서 iOS 26 Liquid Glass를 구현하는 방법은 세 가지다:

| 접근법 | 패키지 | iOS 26 필수 | 성능 | 특징 |
|--------|--------|------------|------|------|
| 네이티브 임베드 | `cupertino_native_plus` | O | 최상 | 실제 UIKit 컴포넌트 임베드 |
| Pure Flutter 렌더러 | `liquid_glass_renderer` | X | 중상 | Impeller 기반 커스텀 셰이더 |
| 직접 구현 | 없음 | X | 최상 | AnimationController + BackdropFilter |

Flutter 공식 팀은 [Issue #170310](https://github.com/flutter/flutter/issues/170310)에서 Liquid Glass 지원을 논의 중이지만, Cupertino 라이브러리가 독립 패키지로 분리되는 작업이 선행되어야 해서 당장은 공식 지원이 없다. `liquid_glass_renderer`는 Impeller 렌더링 엔진을 활용해 refraction(굴절), chromatic aberration(색수차), glow 등을 구현하지만, 바텀 네비 하나에 쓰기엔 의존성이 크다.

바텀 네비 정도의 인터랙션이라면 `AnimationController` + `BackdropFilter` 조합으로 충분하다. glass 배경은 `BackdropFilter`로, 터치 반응은 `AnimationController`로, 인디케이터 슬라이딩은 `AnimatedAlign`으로 처리하면 외부 의존성 없이도 iOS 네이티브에 가까운 느낌을 만들 수 있다.

---

## 주의사항과 알려진 함정

### ShellRoute에서 뒤로 가기

Shell 안에서 `context.push`로 화면을 올리면, 뒤로 가기(Android back button, iOS swipe back)로 이전 화면에 돌아간다. 이때 Shell은 유지되므로 바텀 네비도 그대로 있다. 하지만 `context.go`를 쓰면 히스토리가 교체되므로 뒤로 가기가 동작하지 않는다. push와 go의 차이를 명확히 구분해서 써야 한다.

### nested Scaffold 문제

ShellRoute의 builder가 Scaffold를 쓰고, 자식 화면도 Scaffold를 쓰면 nested Scaffold가 된다. AppBar가 두 개 나타나거나, safe area가 이중으로 적용될 수 있다. Stack 기반으로 overlay하면 이 문제를 피할 수 있다.

### StatefulShellRoute로의 마이그레이션

ShellRoute는 탭 전환 시 이전 탭의 상태를 보존하지 않는다. 할일 탭에서 스크롤을 내리다가 캘린더 탭으로 갔다 오면 스크롤이 초기화된다. 이게 문제라면 `StatefulShellRoute.indexedStack`으로 마이그레이션해야 한다. 다만 라우터 전체를 재설계해야 하므로 점진적으로 진행하는 게 현실적이다.

### BLoC listener에서의 context.push

ShellRoute 안에서 `BlocConsumer`의 listener가 `context.push`를 호출할 때, 해당 context가 Shell의 navigator에 속하는지 확인해야 한다. 잘못된 context를 쓰면 root navigator에서 push가 일어나 바텀 네비가 사라질 수 있다.

---

## 결론

바텀 네비게이션이 사라지는 문제의 근본 원인은 GoRouter의 flat route 구조였다. `ShellRoute`로 인증 화면과 앱 화면을 분리하고, Shell이 바텀 네비를 overlay하는 구조로 변경하면 해결된다.

동시에 BLoC의 one-shot 네비게이션 트리거는 "소비 후 즉시 클리어" 패턴을 반드시 적용해야 한다. 그리고 바텀 네비의 터치 피드백은 외부 패키지 없이 `AnimationController` + `Curves.elasticOut`으로 iOS Liquid Glass와 유사한 느낌을 만들 수 있다.

궁극적으로는 `StatefulShellRoute.indexedStack`이 iOS UITabBarController의 동작과 가장 일치하지만, 기존 앱 구조에 따라 ShellRoute부터 시작해서 점진적으로 마이그레이션하는 전략이 현실적이다.
