---
title: "Godot 4 다마고치 미니게임 개발기 — 줌아웃 좌표계, Tween 루프, WarioWare 설계"
date: 2026-03-23
draft: false
tags: ["godot", "gamedev", "gdscript", "tween", "minigame"]
description: "Godot 4에서 다마고치 미니게임을 만들며 겪은 삽질. Tween set_loops 에러, 부모 씬 줌아웃 시 자식 좌표 보정, _process에서 meta 값 덮어쓰기 문제까지 실전 해결 과정을 정리했다."
---

다마고치 스타일 펫 게임을 Godot 4로 만들고 있다. 밥 주고, 쓰다듬고, 산책시키는 기본 기능은 어렵지 않았는데, 미니게임을 추가하면서 예상 못한 문제가 쏟아졌다. 똥 피하기 게임 하나 만드는데 좌표계 문제로 반나절을 날렸다.

이 글에서는 Godot 4의 Tween 루프 문법, 부모 노드 스케일 변경 시 자식 좌표 보정, 그리고 `_process()`에서 값이 매 프레임 덮어써지는 함정까지 실제로 겪은 삽질을 정리한다.

---

## Godot 4 Tween의 set_loops() 함정

### 에러 상황

똥이 하늘에서 떨어지면서 회전하는 애니메이션을 넣으려고 이렇게 작성했다:

```gdscript
# 이렇게 쓰면 에러!
var tw := create_tween()
tw.tween_property(item, "rotation", TAU, 1.0).set_loops()
```

실행하면 에러가 뜬다. `set_loops()`는 `PropertyTweener`의 메서드가 아니라 `Tween`의 메서드다.

### 올바른 방법

```gdscript
# set_loops()는 Tween 자체에 호출해야 한다
var tw := create_tween().set_loops()
tw.tween_property(item, "rotation", TAU, 1.0)
```

Godot 4의 Tween API에서 체이닝할 때 혼동하기 쉬운 부분이다. `tween_property()`가 반환하는 건 `PropertyTweener`이고, `set_loops()`는 `Tween` 클래스에만 존재한다. 체이닝 순서가 중요하다.

### Tween vs PropertyTweener 메서드 정리

| 메서드 | 소속 클래스 | 용도 |
|--------|------------|------|
| `set_loops()` | Tween | 전체 시퀀스 반복 |
| `set_parallel()` | Tween | 동시 실행 모드 |
| `set_speed_scale()` | Tween | 속도 배율 |
| `set_trans()` | Tween / PropertyTweener | 전환 곡선 |
| `set_ease()` | Tween / PropertyTweener | 이징 방향 |
| `as_relative()` | PropertyTweener | 상대값 기준 |
| `set_delay()` | PropertyTweener | 개별 딜레이 |

`set_trans()`와 `set_ease()`는 양쪽 다 있어서 어디서 호출해도 동작한다. 하지만 `set_loops()`는 Tween 전용이니까 반드시 `create_tween()` 직후에 체이닝해야 한다.

### 왜 이런 구조인가

Godot 4에서 Tween 시스템이 완전히 재설계됐다. Godot 3에서는 Tween이 노드였고 `interpolate_property()`로 설정하는 방식이었다. Godot 4에서는 `create_tween()`으로 가볍게 생성하고 체이닝하는 빌더 패턴으로 바뀌었다.

```gdscript
# Godot 3 (옛날 방식)
var tween = Tween.new()
add_child(tween)
tween.interpolate_property(sprite, "transform/scale",
    sprite.get_scale(), Vector2(2.0, 2.0), 0.3,
    Tween.TRANS_QUAD, Tween.EASE_OUT)
tween.start()

# Godot 4 (현재)
var tween = create_tween()
tween.tween_property(sprite, "scale", Vector2(2.0, 2.0), 0.3) \
    .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
```

빌더 패턴으로 바뀌면서 코드가 훨씬 깔끔해졌지만, 어떤 메서드가 `Tween`에 속하고 어떤 메서드가 `PropertyTweener`에 속하는지 구분을 잘 해야 한다.

---

## 미니게임을 위한 씬 줌아웃 — 배경과 캐릭터를 함께 축소하기

### 문제 정의

다마고치 화면 구성은 이렇다: 방 배경 + 바닥 + 캐릭터(펫). 여기서 "똥 피하기" 미니게임을 시작하면 하늘에서 똥이 떨어지는 공간이 필요하다.

처음에는 캐릭터만 작게 만들었다:

```gdscript
# 첫 번째 시도: 캐릭터만 축소
var small_scale := _original_pet_scale * 0.35
_pet_display.sprite.scale = small_scale
```

캐릭터는 작아졌는데 배경은 그대로라 어색했다. 캐릭터가 방 안에서 갑자기 혼자 쪼그라든 느낌이었다.

### 해결: 부모 씬 전체를 줌아웃

발상을 바꿨다. 캐릭터만 줄이는 게 아니라, 메인 씬 전체(배경 + 캐릭터 + 모든 요소)를 줌아웃하면 된다.

```gdscript
func start(pet_display: Node2D, main_scene: Node2D, viewport_size: Vector2) -> void:
    _main_scene = main_scene

    # 원래 상태 저장
    _original_main_scale = _main_scene.scale
    _original_main_pos = _main_scene.position

    # 전체 씬을 55%로 줌아웃
    var zoom_scale := 0.55
    var tw := create_tween()
    tw.set_parallel(true)
    tw.tween_property(_main_scene, "scale",
        Vector2(zoom_scale, zoom_scale), 0.4) \
        .set_ease(Tween.EASE_OUT)

    # 화면 하단에 배치
    var target_x: float = viewport_size.x * (1.0 - zoom_scale) * 0.5
    var target_y: float = viewport_size.y * (1.0 - zoom_scale) * 1.1
    tw.tween_property(_main_scene, "position",
        Vector2(target_x, target_y), 0.4)
```

줌아웃하면 화면 위쪽에 자연스럽게 빈 공간이 생기고, 여기서 똥이 떨어진다. 배경과 캐릭터가 동일한 비율로 줄어드니까 일관된 느낌이다.

### 빈 공간 문제 — 배경 이미지 확장

줌아웃하니까 원래 배경 위에 빈 공간이 노출됐다. 처음에는 파란색 `ColorRect`로 하늘을 채웠는데, 배경과 이질감이 심했다. 연속성이 없었다.

결국 배경 이미지 자체를 세로로 확장했다. 원래 400x600짜리 방 배경 위에 하늘+구름을 그려서 800x1000짜리 확장 배경을 만들었다.

```gdscript
# 게임 시작 시 확장 배경으로 교체
var ext_tex := load("res://assets/sprites/background_extended.png")
var bg_sprite: Sprite2D = _main_scene.get_node("Background")
if ext_tex and bg_sprite:
    _original_bg_texture = bg_sprite.texture
    bg_sprite.texture = ext_tex
    bg_sprite.position.y -= 100  # 위치 조정
```

게임이 끝나면 원래 배경으로 복원한다:

```gdscript
# 게임 종료 시 원래 배경 복원
var bg_sprite: Sprite2D = _main_scene.get_node_or_null("Background")
if bg_sprite and _original_bg_texture:
    bg_sprite.texture = _original_bg_texture
    bg_sprite.position = _original_bg_pos
```

---

## 좌표계 보정 — 줌아웃된 부모 안의 자식 이동 범위

이게 가장 오래 삽질한 부분이다. 씬을 55%로 줌아웃했는데 캐릭터가 화면 가장자리까지 이동하지 못했다.

### 왜 이동 범위가 좁아지는가

Godot에서 부모 노드의 `scale`을 줄이면 자식 노드의 로컬 좌표 → 화면 좌표 변환에 그 스케일이 곱해진다.

```
화면_X = 부모_position.x + (자식_로컬_X * 부모_scale.x)
```

부모 scale이 0.55이면:
- 자식이 로컬 좌표에서 ±200 이동해도
- 화면에서는 ±110만 이동한 것으로 보인다

화면 전체(400px)를 커버하려면 로컬 좌표에서 `400 / 0.55 / 2 = ±364` 범위가 필요하다.

### 이동 속도도 보정 필요

같은 이유로 이동 속도도 느려 보인다. 로컬 좌표에서 500px/s로 이동해도 화면에서는 275px/s로 보인다.

```gdscript
# 줌 보정 적용
var half_range: float = (viewport_size.x / zoom_scale / 2.0) - 20
_pet_display.WANDER_LEFT = -half_range
_pet_display.WANDER_RIGHT = half_range

# 속도도 줌 보정
var zoom: float = _main_scene.scale.x
var speed: float = 500.0 / zoom  # 0.55 줌이면 ~909
```

### 충돌 판정도 화면 좌표 기준으로

떨어지는 똥은 CanvasLayer 위에서 화면 좌표로 떨어진다. 캐릭터는 줌아웃된 씬 안에 있다. 충돌 판정을 하려면 캐릭터의 화면 좌표를 직접 계산해야 한다.

```gdscript
# 캐릭터의 화면 좌표 계산
var pet_screen_x: float = _main_scene.position.x + \
    (_pet_display.global_position.x + _pet_display._offset_x) * \
    _main_scene.scale.x

var pet_screen_y: float = _main_scene.position.y + \
    _pet_display.global_position.y * _main_scene.scale.y

# 충돌 반경도 줌에 맞게
var hit_radius: float = 18.0 * _main_scene.scale.x
```

부모-자식 좌표 변환은 Godot뿐 아니라 모든 2D/3D 엔진에서 기본 개념이다. 하지만 "게임 모드 전환" 같은 동적 스케일 변경 상황에서는 놓치기 쉽다.

---

## _process()에서 매 프레임 값이 덮어써지는 함정

### 가장 찾기 어려웠던 버그

줌 보정을 적용하고, 이동 범위를 ±364로 넓혔는데... 여전히 이동이 안 됐다. 값을 500으로 올려도 안 됐다. `print()`로 찍어보면 설정 직후에는 맞는데 다음 프레임에 ±150으로 돌아가 있었다.

범인은 `pet_display.gd`의 `_process()` 함수였다:

```gdscript
# pet_display.gd의 _process()
func _process(delta: float) -> void:
    WANDER_LEFT = get_meta("floor_left", -150.0)   # 매 프레임 실행!
    WANDER_RIGHT = get_meta("floor_right", 150.0)   # 매 프레임 실행!
    # ...
```

메인 씬에서 바닥 크기에 맞춰 meta 값을 설정하고, `_process()`에서 매 프레임 읽어오는 구조였다. 게임 모드에서 `WANDER_LEFT = -364`로 바꿔도 다음 프레임에 meta 값(-150)으로 리셋되는 거다.

### 해결: meta 값 자체를 업데이트

```gdscript
# dodge_game_mode.gd에서 meta도 함께 업데이트
var half_range: float = (viewport_size.x / zoom_scale / 2.0) - 20
_pet_display.WANDER_LEFT = -half_range
_pet_display.WANDER_RIGHT = half_range
# 핵심! meta 값도 같이 바꿔야 _process()가 덮어쓰지 않는다
_pet_display.set_meta("floor_left", -half_range)
_pet_display.set_meta("floor_right", half_range)
```

게임이 끝나면 원래 값으로 복원:

```gdscript
# 게임 종료 시 원래 범위 복원
_pet_display.WANDER_LEFT = _original_wander_left
_pet_display.WANDER_RIGHT = _original_wander_right
_pet_display.set_meta("floor_left", _original_wander_left)
_pet_display.set_meta("floor_right", _original_wander_right)
```

### 교훈: _process() 안의 값 초기화를 조심하라

이 패턴은 "방어적 초기화"로 만든 코드가 다른 시스템의 동적 설정을 방해하는 전형적인 케이스다. 일반 상태에서는 문제없지만, 게임 모드처럼 일시적으로 다른 값을 써야 할 때 충돌한다.

해결 방법은 여러 가지가 있다:

| 방법 | 장점 | 단점 |
|------|------|------|
| meta 값 업데이트 (위 방법) | 기존 코드 수정 불필요 | meta 의존성 증가 |
| 게임 모드 플래그로 _process() 분기 | 명확한 의도 표현 | _process() 복잡도 증가 |
| 값 소스를 signal로 전환 | 느슨한 결합 | 구조 변경 필요 |
| _process() 대신 setter 사용 | 변경 시점 제어 가능 | 리팩토링 범위 큼 |

빠르게 해결하려면 meta 값 업데이트가 최선이었다. 장기적으로는 게임 모드 플래그를 두고 `_process()`에서 체크하는 게 깔끔하다.

---

## WarioWare에서 배운 마이크로게임 설계 원칙

미니게임을 더 추가하려고 WarioWare(미니게임천국) 디자인을 조사했다. 닌텐도 R&D1 팀이 2003년에 만든 이 게임은 "마이크로게임" 장르의 교과서다.

### WarioWare의 핵심 설계 원칙

WarioWare의 수석 디렉터 Goro Abe가 인터뷰에서 밝힌 원칙:

1. **즉각적 이해**: 조작과 규칙이 직관적이어야 한다. 2~3번째 시도에 클리어할 수 있는 밸런스
2. **보편적 테마**: 넓은 연령대와 배경에 공감되는 주제
3. **다양한 비주얼**: 각 마이크로게임마다 다른 아트 스타일. 개발자마다 자기 그래픽을 직접 그렸다
4. **단순 입력**: 방향키 + 버튼 1개. 복잡한 조작 금지

게임학 연구자 Chaim Gingold의 분석에 따르면, WarioWare가 "혼돈 속에서도 플레이 가능한" 이유는:

- **원자적 단순함**: 각 게임이 최소한의 요소만 포함
- **명확한 경계**: 게임 간 전환을 화려한 애니메이션으로 명확히 표시
- **점진적 난이도**: 속도 증가 + 난이도 3단계 순환
- **즉각적 피드백**: 성공/실패가 바로 전달

### 다마고치 미니게임에 적용한 것

이 원칙을 따라 다마고치 게임에 3종의 미니게임을 만들었다:

```
미니게임 목록:
├── Left or Right (방향 맞추기) — 2초 안에 방향 선택
├── Dodge Poop (똥 피하기) — 25초 생존, 좌우 이동
└── Catch Food (음식 잡기) — 15초, 좌우 이동 + 폭탄 회피
```

| 게임 | 입력 | 시간 | 난이도 곡선 | WarioWare 원칙 |
|------|------|------|-----------|---------------|
| Left or Right | 좌/우 키 1회 | 2초 | 없음 (원샷) | 즉각적 이해 |
| Dodge Poop | 좌/우 지속 | 25초 | 시간↑ 속도↑ | 점진적 난이도 |
| Catch Food | 좌/우 지속 | 15초 | 폭탄 비율↑ | 다중 판단 |

### Catch Food 구현 — WarioWare 스타일

WarioWare의 "Dodge!" 계열 마이크로게임을 참고해서 만든 음식 잡기 게임:

```gdscript
func _spawn_item() -> void:
    var is_bomb: bool = randf() < (0.2 + _time_elapsed * 0.01)
    var item := Sprite2D.new()

    if is_bomb:
        item.texture = _bomb_texture
        item.scale = Vector2(2.5, 2.5)
    else:
        item.texture = _food_texture
        item.scale = Vector2(2.0, 2.0)

    item.position = Vector2(
        randf_range(40, _vp_size.x - 40),
        -20  # 화면 위에서 시작
    )
    item.set_meta("is_bomb", is_bomb)
    item.set_meta("speed", randf_range(150, 250))
    add_child(item)
```

WarioWare처럼 "Catch!"라는 간단한 프롬프트 하나로 규칙을 전달하고, 음식은 잡고 폭탄(X)은 피하는 직관적 구조다.

---

## 게임 모드 전환의 상태 관리 패턴

미니게임 시작/종료 시 원래 상태를 정확히 복원하는 게 중요하다. 하나라도 빠지면 게임 끝나고 캐릭터가 이상해진다.

### 저장-복원 패턴

```gdscript
# 시작 시 저장
_original_main_scale = _main_scene.scale
_original_main_pos = _main_scene.position
_original_pet_scale = _pet_display.sprite.scale
_original_wander_left = _pet_display.WANDER_LEFT
_original_wander_right = _pet_display.WANDER_RIGHT
_original_bg_texture = bg_sprite.texture
_original_bg_pos = bg_sprite.position

# 종료 시 복원 (Tween으로 부드럽게)
var tw := create_tween()
tw.set_parallel(true)
tw.tween_property(_main_scene, "scale", _original_main_scale, 0.4)
tw.tween_property(_main_scene, "position", _original_main_pos, 0.4)
tw.chain().tween_interval(1.5)
tw.chain().tween_callback(queue_free)
```

복원할 때 Tween을 써서 부드럽게 돌아가게 한 게 포인트다. 갑자기 원래 크기로 돌아가면 어색하다.

### 체크리스트

미니게임 모드 구현 시 반드시 저장/복원해야 하는 항목:

- 부모 노드 scale, position
- 캐릭터 scale, position
- 이동 범위 (WANDER bounds + meta)
- 배경 텍스처, 위치
- UI 표시 상태 (HUD, ActionBar)
- 캐릭터 행동 모드 (AI 산책 ↔ 플레이어 조작)

---

## 화면 흔들림(Screen Shake)을 줌아웃 상태에서 구현하기

똥에 맞으면 화면이 흔들리는 피드백을 넣었다. 보통은 카메라를 흔들지만, 줌아웃 상태에서는 메인 씬 자체를 흔드는 게 효과적이다.

```gdscript
func _screen_shake() -> void:
    var orig := _main_scene.position
    var tw := create_tween()
    for i in range(4):
        tw.tween_property(_main_scene, "position",
            orig + Vector2(randf_range(-5, 5), randf_range(-4, 4)),
            0.04)
    tw.tween_property(_main_scene, "position", orig, 0.04)
```

4프레임 동안 랜덤 위치로 흔들리고 원래 자리로 복귀한다. 줌아웃 상태라 흔들림이 전체 화면에 걸쳐 보이니까 임팩트가 크다.

캐릭터 색상 변경도 함께 넣었다:

```gdscript
# 맞으면 빨간색 → 0.25초 후 복원
_pet_display.sprite.modulate = Color(1, 0.2, 0.2)
create_tween().tween_property(
    _pet_display.sprite, "modulate", Color.WHITE, 0.25)
```

시각 + 모션 피드백을 동시에 주면 "맞았다"는 느낌이 확실히 전달된다. WarioWare에서도 실패 시 짧고 강렬한 피드백을 주는 게 핵심 원칙 중 하나다.

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| `set_loops()` 에러 | PropertyTweener에 호출 | `create_tween().set_loops()` |
| 캐릭터만 작아짐 | 캐릭터 scale만 변경 | 부모 씬 전체 줌아웃 |
| 줌아웃 시 빈 공간 | 배경 부족 | 확장 배경(하늘) 교체 |
| 이동 범위 부족 | 줌으로 좌표 축소 | `range / zoom_scale` 보정 |
| 보정해도 이동 안 됨 | `_process()`가 meta 덮어씀 | meta 값도 함께 업데이트 |
| 충돌 판정 어긋남 | 좌표계 불일치 | 화면 좌표 직접 계산 |

Godot 4에서 미니게임 모드를 구현할 때 핵심은 좌표계 관리다. 부모 scale이 바뀌면 자식의 모든 위치, 속도, 충돌 판정을 그에 맞게 보정해야 한다. 그리고 `_process()`에서 방어적으로 초기화하는 코드가 있다면, 게임 모드 전환 시 반드시 그 소스(meta, config 등)까지 함께 업데이트해야 한다.

50개 커밋 넘게 쌓이면서 다마고치가 점점 게임다워지고 있다. 다음은 상점 시스템이다.
