---
title: "Godot 4 미니게임 모드 전환 — 상태 저장/복원 패턴과 _process() 함정"
date: 2026-03-26
draft: false
tags: ["godot", "gamedev", "gdscript", "minigame", "상태관리", "아키텍처"]
description: "Godot 4에서 미니게임 모드를 만들 때 씬 상태를 저장하고 복원하는 패턴. _process()가 매 프레임 값을 덮어쓰는 함정, 게임 모드 전환 시 체크리스트, 그리고 실전에서 터진 버그들을 정리했다."
---

다마고치 게임에 미니게임 3종을 넣었다. 게임 자체보다 어려웠던 건 **게임 모드 전환**이다. 미니게임을 시작하면 씬이 줌아웃되고 캐릭터가 축소되고 이동 범위가 바뀌고 배경이 교체된다. 게임이 끝나면 이 모든 게 원래대로 돌아와야 한다.

하나라도 복원을 빠뜨리면 버그가 된다. 캐릭터가 작은 채로 남아있거나, 배경이 확장된 채로 유지되거나, 이동 범위가 좁아진 채로 고정된다. 유저는 "게임이 망가졌다"고 느낀다.

이 글에서는 미니게임 모드 전환 시 상태 관리 패턴과, 실제로 터진 버그들의 원인과 해결을 정리한다.

---

## 문제의 본질: 임시 상태 vs 영구 상태

미니게임 모드는 **임시 상태**다. 잠깐 동안만 다른 설정을 쓰고, 끝나면 원래대로 돌아간다. 이게 간단해 보이는데 실제로는 복잡하다.

왜 복잡한가:
1. **변경해야 할 것이 많다**: scale, position, 이동 범위, 배경, UI 표시, 입력 모드...
2. **각 값의 복원 시점이 다르다**: UI는 즉시, 줌은 Tween으로 부드럽게, 배경은 줌 복원 후에
3. **다른 시스템이 값을 덮어쓸 수 있다**: `_process()`의 방어적 초기화가 대표적

---

## 패턴 1: Snapshot-Restore (스냅샷 저장/복원)

가장 기본적인 패턴. 게임 시작 시 모든 관련 값을 저장하고, 종료 시 복원한다.

```gdscript
# dodge_game_mode.gd

# 저장할 원본 값들
var _original_main_scale: Vector2
var _original_main_pos: Vector2
var _original_pet_scale: Vector2
var _original_wander_left: float
var _original_wander_right: float
var _original_bg_texture: Texture2D
var _original_bg_pos: Vector2

func start(pet_display: Node2D, main_scene: Node2D, vp_size: Vector2) -> void:
    # === SNAPSHOT ===
    _original_main_scale = main_scene.scale
    _original_main_pos = main_scene.position
    _original_pet_scale = pet_display.sprite.scale
    _original_wander_left = pet_display.WANDER_LEFT
    _original_wander_right = pet_display.WANDER_RIGHT

    var bg: Sprite2D = main_scene.get_node("Background")
    _original_bg_texture = bg.texture
    _original_bg_pos = bg.position

    # === MODIFY ===
    _apply_game_mode_settings()

func end_game() -> void:
    # === RESTORE ===
    _restore_all_originals()
```

단순하지만 강력하다. 규칙은 하나:

> **수정하는 모든 값은 반드시 수정 전에 저장한다.**

이걸 어기면 복원할 수 없다. "나중에 저장하지 뭐" 하다가 수정 후에 저장하면 이미 바뀐 값이 "원본"이 된다.

### 체크리스트

미니게임 모드에서 저장/복원해야 하는 항목:

| 카테고리 | 항목 | 수정 내용 |
|---------|------|----------|
| 트랜스폼 | 메인 씬 scale | 1.0 → 0.55 |
| 트랜스폼 | 메인 씬 position | (0,0) → 줌아웃 위치 |
| 트랜스폼 | 캐릭터 scale | 원본 → 축소 |
| 이동 | WANDER_LEFT/RIGHT | ±150 → ±364 |
| 이동 | meta("floor_left/right") | ±150 → ±364 |
| 비주얼 | 배경 텍스처 | 기본 → 확장(하늘) |
| 비주얼 | 배경 위치 | 원본 → 오프셋 |
| UI | ActionBar 표시 | visible → hidden |
| UI | HUD (HP, 점수) | hidden → visible |
| 행동 | 캐릭터 AI 모드 | 자동 산책 → 플레이어 조작 |

10개 항목이다. 미니게임 3종이면 각각 이 목록을 관리해야 한다. 공통 부분이 많으니 베이스 클래스로 뽑았다.

---

## 패턴 2: BaseGameMode 추상화

3종의 미니게임이 공통으로 쓰는 시작/종료 로직을 베이스 클래스로 분리했다.

```gdscript
# base_game_mode.gd
class_name BaseGameMode
extends CanvasLayer

var _main_scene: Node2D
var _pet_display: Node2D
var _vp_size: Vector2
var _game_active: bool = false

# 스냅샷 저장소
var _snapshots: Dictionary = {}

func _save_snapshot(key: String, value: Variant) -> void:
    _snapshots[key] = value

func _get_snapshot(key: String) -> Variant:
    return _snapshots.get(key)

func _base_start(pet_display: Node2D, main_scene: Node2D, vp_size: Vector2) -> void:
    _pet_display = pet_display
    _main_scene = main_scene
    _vp_size = vp_size

    # 공통 스냅샷
    _save_snapshot("main_scale", main_scene.scale)
    _save_snapshot("main_pos", main_scene.position)
    _save_snapshot("wander_left", pet_display.WANDER_LEFT)
    _save_snapshot("wander_right", pet_display.WANDER_RIGHT)
    _save_snapshot("floor_left_meta", pet_display.get_meta("floor_left", -150.0))
    _save_snapshot("floor_right_meta", pet_display.get_meta("floor_right", 150.0))

    # 공통 줌아웃
    _zoom_out()
    # 공통 이동 범위 보정
    _adjust_wander_range()

func _base_end() -> void:
    _game_active = false

    # 공통 복원
    _restore_wander_range()
    _zoom_restore()

func _zoom_out() -> void:
    var zoom := 0.55
    var tw := create_tween().set_parallel(true)
    tw.tween_property(_main_scene, "scale", Vector2(zoom, zoom), 0.4) \
        .set_ease(Tween.EASE_OUT)

    var target_x: float = _vp_size.x * (1.0 - zoom) * 0.5
    var target_y: float = _vp_size.y * (1.0 - zoom) * 1.1
    tw.tween_property(_main_scene, "position", Vector2(target_x, target_y), 0.4)

func _zoom_restore() -> void:
    var tw := create_tween().set_parallel(true)
    tw.tween_property(_main_scene, "scale", _get_snapshot("main_scale"), 0.4)
    tw.tween_property(_main_scene, "position", _get_snapshot("main_pos"), 0.4)
    tw.chain().tween_interval(1.5)
    tw.chain().tween_callback(queue_free)

func _adjust_wander_range() -> void:
    var zoom: float = 0.55
    var half_range: float = (_vp_size.x / zoom / 2.0) - 20
    _pet_display.WANDER_LEFT = -half_range
    _pet_display.WANDER_RIGHT = half_range
    _pet_display.set_meta("floor_left", -half_range)
    _pet_display.set_meta("floor_right", half_range)

func _restore_wander_range() -> void:
    _pet_display.WANDER_LEFT = _get_snapshot("wander_left")
    _pet_display.WANDER_RIGHT = _get_snapshot("wander_right")
    _pet_display.set_meta("floor_left", _get_snapshot("floor_left_meta"))
    _pet_display.set_meta("floor_right", _get_snapshot("floor_right_meta"))
```

이제 개별 미니게임은 이렇게 된다:

```gdscript
# dodge_game_mode.gd
class_name DodgeGameMode
extends BaseGameMode

func start(pet_display: Node2D, main_scene: Node2D, vp_size: Vector2) -> void:
    _base_start(pet_display, main_scene, vp_size)

    # Dodge 전용: 확장 배경 교체
    _swap_background()

    # 게임 시작
    _game_active = true
    _start_spawning()

func end_game() -> void:
    _base_end()
    _restore_background()
```

공통 로직은 베이스에, 게임별 특수 로직은 하위 클래스에. 표준적인 Template Method 패턴이다.

---

## 함정: `_process()`가 값을 덮어쓴다

이게 가장 오래 삽질한 버그다. 자세한 이야기는 [이전 글](/posts/godot4-tamagotchi-minigame-zoom-coordinate-tween/)에 있지만, 패턴 관점에서 다시 정리한다.

### 버그 상황

이동 범위를 `±364`로 넓혔는데, 다음 프레임에 `±150`으로 돌아간다.

### 원인

```gdscript
# pet_display.gd
func _process(delta: float) -> void:
    WANDER_LEFT = get_meta("floor_left", -150.0)   # 매 프레임!
    WANDER_RIGHT = get_meta("floor_right", 150.0)   # 매 프레임!
```

`_process()`에서 매 프레임 meta 값을 읽어와서 `WANDER_LEFT/RIGHT`를 초기화한다. 원래는 메인 씬에서 바닥 크기가 바뀔 때 자동으로 반영되라고 만든 코드다. 평상시에는 문제없다.

하지만 미니게임 모드에서 `WANDER_LEFT = -364`로 바꿔도, meta 값은 여전히 `-150`이니까 다음 프레임에 덮어써진다.

### 교훈: 방어적 초기화의 그림자

이 패턴은 "방어적 초기화"라고 불린다. 매 프레임 값을 리셋해서 일관성을 보장한다. 그런데 이게 **다른 시스템의 동적 변경을 무효화**하는 부작용이 있다.

해결 방법 3가지:

#### 방법 A: 소스(meta)도 함께 업데이트 (내가 쓴 방법)

```gdscript
# 게임 모드에서
_pet_display.WANDER_LEFT = -half_range
_pet_display.set_meta("floor_left", -half_range)  # 소스도 같이!
```

장점: 기존 `_process()` 코드 수정 불필요
단점: meta 의존성이 암묵적. "왜 meta를 바꿔야 하지?"가 직관적이지 않음

#### 방법 B: 게임 모드 플래그로 `_process()` 분기

```gdscript
# pet_display.gd
var in_game_mode: bool = false

func _process(delta: float) -> void:
    if not in_game_mode:  # 게임 모드가 아닐 때만
        WANDER_LEFT = get_meta("floor_left", -150.0)
        WANDER_RIGHT = get_meta("floor_right", 150.0)
```

장점: 의도가 명확. 게임 모드일 때 외부 값을 쓴다는 게 코드에 드러남
단점: `_process()` 복잡도 증가. 플래그 관리 필요

#### 방법 C: `_process()` 제거, 이벤트 기반으로 전환

```gdscript
# pet_display.gd
signal wander_range_changed(left: float, right: float)

func set_wander_range(left: float, right: float) -> void:
    WANDER_LEFT = left
    WANDER_RIGHT = right
    emit_signal("wander_range_changed", left, right)
```

장점: 가장 깔끔. 값이 바뀔 때만 실행
단점: 기존 코드 대폭 리팩토링 필요. 메인 씬에서 바닥 크기 변경 시 signal 연결 필요

나는 방법 A로 빠르게 해결하고 넘어갔다. 미니게임 3종이 전부라서 리팩토링 투자 대비 효과가 낮다고 판단했다. 미니게임이 10종으로 늘어나면 방법 B로 전환할 것 같다.

---

## 복원 순서가 중요하다

모든 값을 복원한다고 끝이 아니다. **순서**도 중요하다.

잘못된 순서:
```
1. 이동 범위 복원 (±150)
2. 줌 복원 (0.55 → 1.0)  ← 이 동안 캐릭터가 ±150 범위에서 움직이는데,
                            줌이 복원되면서 ±150이 화면 밖이 됨
```

올바른 순서:
```
1. 게임 중지 (스폰 정지, 판정 정지)
2. 아이템 정리 (떨어지던 것들 제거)
3. 결과 표시 (성공/실패)
4. 줌 복원 (Tween, 0.4초)
5. 줌 복원 완료 후 → 이동 범위 복원
6. 배경 복원
7. UI 복원
8. 게임 모드 노드 제거
```

줌이 복원된 **후에** 이동 범위를 복원해야 한다. 줌 복원 중에 이동 범위가 먼저 바뀌면, 캐릭터가 일시적으로 화면 밖으로 나갈 수 있다.

```gdscript
func _end_sequence() -> void:
    _game_active = false
    _clear_items()
    _show_result()

    # 줌 복원 Tween
    var tw := create_tween().set_parallel(true)
    tw.tween_property(_main_scene, "scale", _get_snapshot("main_scale"), 0.4)
    tw.tween_property(_main_scene, "position", _get_snapshot("main_pos"), 0.4)

    # 줌 복원 완료 후에 나머지 복원
    tw.chain().tween_callback(_restore_wander_range)
    tw.chain().tween_callback(_restore_background)
    tw.chain().tween_callback(_restore_ui)
    tw.chain().tween_interval(0.5)
    tw.chain().tween_callback(queue_free)
```

`chain().tween_callback()`으로 줌 복원 완료 시점에 콜백을 건다. Tween의 시퀀스 기능이 여기서 빛난다.

---

## 동시 실행 방지

미니게임이 실행 중인데 또 시작하면? 버그다. 스냅샷이 덮어써지고 복원이 불가능해진다.

```gdscript
# main_scene.gd
var _current_game_mode: BaseGameMode = null

func start_minigame(mode_scene: PackedScene) -> void:
    # 이미 게임 중이면 무시
    if _current_game_mode != null:
        return

    _current_game_mode = mode_scene.instantiate()
    _current_game_mode.tree_exiting.connect(
        func(): _current_game_mode = null
    )
    add_child(_current_game_mode)
    _current_game_mode.start(_pet_display, self, get_viewport_rect().size)
```

`tree_exiting` 시그널로 게임 모드가 정리될 때 자동으로 `null`로 돌린다. `queue_free()`가 호출되면 `tree_exiting`이 먼저 발생하니까 타이밍이 안전하다.

---

## 디버깅 팁: 복원 검증

개발 중에 복원이 제대로 됐는지 확인하는 헬퍼:

```gdscript
func _verify_restoration() -> void:
    for key in _snapshots:
        var expected = _snapshots[key]
        var actual: Variant

        match key:
            "main_scale": actual = _main_scene.scale
            "main_pos": actual = _main_scene.position
            "wander_left": actual = _pet_display.WANDER_LEFT
            "wander_right": actual = _pet_display.WANDER_RIGHT

        if actual != null and actual != expected:
            push_warning("Restore mismatch: %s expected=%s actual=%s" \
                % [key, expected, actual])
```

게임 종료 후에 이걸 돌리면 복원이 안 된 항목이 콘솔에 뜬다. 프로덕션에서는 빼지만 개발 중에는 항상 켜둔다.

---

## 정리

| 패턴 | 용도 | 핵심 규칙 |
|------|------|----------|
| Snapshot-Restore | 임시 상태 관리 | 수정 전에 반드시 저장 |
| BaseGameMode | 공통 로직 추상화 | Template Method |
| 소스 업데이트 | `_process()` 방어 우회 | meta/config도 함께 변경 |
| 순서 보장 | 복원 타이밍 관리 | Tween chain으로 시퀀싱 |
| 동시 실행 방지 | 다중 게임 방지 | null 체크 + 시그널 정리 |

게임 모드 전환은 "모든 걸 바꾸고 모든 걸 원래대로 돌리는" 작업이다. 바꿀 게 3개면 쉽지만 10개 넘으면 하나는 반드시 빠뜨린다. 체크리스트와 자동 검증이 유일한 방법이다.

미니게임을 더 추가할 계획이라 BaseGameMode를 좀 더 일반화할 예정이다. 각 게임이 "나는 이것만 추가로 바꾼다"를 선언하면 자동으로 저장/복원되는 구조를 목표로 하고 있다.
