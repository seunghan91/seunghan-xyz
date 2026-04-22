---
title: "Godot 4 Tween 실전 레시피 — 미니게임에서 써먹은 12가지 애니메이션 패턴"
date: 2026-03-25
draft: false
tags: ["godot", "gamedev", "gdscript", "tween", "minigame", "애니메이션"]
categories: ["Dev"]
description: "Godot 4의 Tween 시스템으로 미니게임 UI 애니메이션을 만든 실전 레시피 12가지. 체이닝 함정, 병렬/순차 실행, 콜백 타이밍까지 코드와 함께 정리했다."
---

Godot 4에서 Tween API가 완전히 바뀌었다. Godot 3에서 노드 기반이던 게 빌더 패턴으로 재설계됐다. 코드는 깔끔해졌는데 API 경계가 헷갈린다. `set_loops()`를 `PropertyTweener`에 호출해서 에러 나고, `set_parallel()`을 `tween_property()` 뒤에 붙여서 동작 안 하고.

다마고치 미니게임을 만들면서 12가지 Tween 패턴을 정리했다. 삽질 한 번 할 때마다 하나씩 추가된 목록이다.

---

## 기본: Tween vs PropertyTweener

이게 모든 혼란의 원흉이다. `create_tween()`은 `Tween`을 반환하고, `tween_property()`는 `PropertyTweener`를 반환한다. 두 클래스의 메서드가 다르다.

```gdscript
var tween: Tween = create_tween()          # Tween 반환
var pt: PropertyTweener = tween.tween_property(...)  # PropertyTweener 반환
```

| 메서드 | Tween | PropertyTweener |
|--------|-------|-----------------|
| `set_loops()` | ✅ | ❌ |
| `set_parallel()` | ✅ | ❌ |
| `set_speed_scale()` | ✅ | ❌ |
| `set_trans()` | ✅ | ✅ |
| `set_ease()` | ✅ | ✅ |
| `as_relative()` | ❌ | ✅ |
| `set_delay()` | ❌ | ✅ |
| `from()` | ❌ | ✅ |
| `from_current()` | ❌ | ✅ |

체이닝할 때 **반환 타입**을 항상 의식해야 한다. 이걸 모르면 컴파일은 되는데 런타임에 터진다.

---

## 레시피 1: 루프 애니메이션 (회전)

떨어지는 아이템이 빙글빙글 도는 애니메이션. 가장 먼저 만들었고, 가장 먼저 에러났다.

```gdscript
# ❌ 잘못된 코드 — set_loops()는 PropertyTweener에 없다
var tw := create_tween()
tw.tween_property(item, "rotation", TAU, 1.0).set_loops()

# ✅ 올바른 코드 — Tween에 set_loops() 호출
var tw := create_tween().set_loops()
tw.tween_property(item, "rotation", TAU, 1.0).as_relative()
```

`as_relative()`도 중요하다. 없으면 `rotation`이 절대값 `TAU`(≈6.28)로 설정되고 끝이다. `as_relative()`를 붙이면 매 루프마다 현재 값에서 TAU만큼 추가 회전한다.

---

## 레시피 2: 병렬 실행 (줌아웃 + 이동)

미니게임 시작 시 메인 씬을 줌아웃하면서 동시에 위치도 옮겨야 한다. `set_parallel()`을 쓴다.

```gdscript
var tw := create_tween()
tw.set_parallel(true)

# 이 두 프로퍼티가 동시에 변한다
tw.tween_property(_main_scene, "scale", Vector2(0.55, 0.55), 0.4) \
    .set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_QUAD)
tw.tween_property(_main_scene, "position", target_pos, 0.4) \
    .set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_QUAD)
```

`set_parallel(true)` 없이 두 개를 추가하면 **순차 실행**된다. scale이 먼저 바뀌고, 그 다음 position이 바뀐다. 이건 어색하다.

---

## 레시피 3: 순차 → 병렬 → 순차 (복합 시퀀스)

게임 종료 시 이런 시퀀스를 원했다:
1. 결과 텍스트 페이드인 (순차)
2. 메인 씬 줌복원 + 위치복원 (병렬)
3. 1.5초 대기 후 정리 (순차)

```gdscript
var tw := create_tween()

# Step 1: 결과 텍스트 (순차 — 기본값)
tw.tween_property(_result_label, "modulate:a", 1.0, 0.3)

# Step 2: 줌복원 (병렬)
tw.set_parallel(true)
tw.tween_property(_main_scene, "scale", _original_scale, 0.4)
tw.tween_property(_main_scene, "position", _original_pos, 0.4)

# Step 3: 대기 후 정리 (순차로 돌아감)
tw.set_parallel(false)
tw.tween_interval(1.5)
tw.tween_callback(queue_free)
```

`set_parallel()`은 토글이다. `true`로 바꾸면 이후 추가되는 tween들이 동시 실행되고, `false`로 돌리면 다시 순차가 된다. 중간에 바꿀 수 있다는 걸 몰라서 한참 삽질했다.

---

## 레시피 4: chain()으로 시퀀스 잇기

`set_parallel()` 토글보다 `chain()`이 더 직관적인 경우가 있다.

```gdscript
var tw := create_tween().set_parallel(true)

# 병렬 실행
tw.tween_property(node, "scale", Vector2(1.2, 1.2), 0.2)
tw.tween_property(node, "modulate", Color.YELLOW, 0.2)

# chain()으로 이후 순차 실행
tw.chain().tween_property(node, "scale", Vector2.ONE, 0.15)
tw.chain().tween_property(node, "modulate", Color.WHITE, 0.15)
```

`chain()`은 "지금까지 병렬로 등록된 것들이 다 끝난 뒤에 실행해줘"라는 의미다. 순서가 보장된다.

---

## 레시피 5: 화면 흔들기 (Screen Shake)

피격 시 카메라 대신 씬 자체를 흔든다. 줌아웃 상태에서는 이게 더 임팩트 있다.

```gdscript
func _screen_shake(intensity: float = 5.0, shakes: int = 4) -> void:
    var orig := _main_scene.position
    var tw := create_tween()

    for i in range(shakes):
        var offset := Vector2(
            randf_range(-intensity, intensity),
            randf_range(-intensity * 0.8, intensity * 0.8)
        )
        tw.tween_property(_main_scene, "position", orig + offset, 0.04)

    # 마지막에 반드시 원위치
    tw.tween_property(_main_scene, "position", orig, 0.04)
```

주의점: 흔들기 도중에 다른 Tween이 position을 건드리면 원위치 복귀가 어긋난다. 흔들기 전에 `orig`을 캡처하는 게 핵심이다.

---

## 레시피 6: 점수 팝업 (떠오르며 사라짐)

음식을 잡으면 "+1"이 위로 떠오르면서 페이드아웃된다. 심플하지만 게임 느낌을 확 살린다.

```gdscript
func _show_score_popup(pos: Vector2, points: int) -> void:
    var label := Label.new()
    label.text = "+%d" % points if points > 0 else "%d" % points
    label.position = pos
    label.modulate = Color.GREEN if points > 0 else Color.RED
    label.add_theme_font_size_override("font_size", 28)
    add_child(label)

    var tw := create_tween().set_parallel(true)
    tw.tween_property(label, "position:y", pos.y - 50, 0.6) \
        .set_ease(Tween.EASE_OUT)
    tw.tween_property(label, "modulate:a", 0.0, 0.6) \
        .set_delay(0.2)  # 0.2초 후부터 페이드 시작
    tw.chain().tween_callback(label.queue_free)
```

`set_delay(0.2)`가 포인트다. 위로 올라가기 시작하고 0.2초 후에 페이드가 시작된다. 동시에 시작하면 텍스트가 읽히기도 전에 사라진다.

---

## 레시피 7: 펄스(맥박) 애니메이션

HP가 1일 때 하트 아이콘이 두근두근 뛰는 효과.

```gdscript
func _start_pulse(node: Node2D) -> void:
    var tw := create_tween().set_loops()
    tw.tween_property(node, "scale", Vector2(1.15, 1.15), 0.3) \
        .set_trans(Tween.TRANS_SINE)
    tw.tween_property(node, "scale", Vector2.ONE, 0.3) \
        .set_trans(Tween.TRANS_SINE)
```

`TRANS_SINE`을 쓰면 시작과 끝이 부드럽다. `TRANS_LINEAR`이면 기계적으로 보인다. 심장 박동은 사인파가 맞다.

---

## 레시피 8: 프롬프트 텍스트 등장/퇴장

"피해!" 같은 프롬프트가 커지면서 나타나고, 잠깐 머물렀다가 사라진다.

```gdscript
func _show_prompt(text: String) -> void:
    var label := Label.new()
    label.text = text
    label.scale = Vector2(0.3, 0.3)
    label.modulate.a = 0
    add_child(label)

    var tw := create_tween()

    # 등장: 커지면서 페이드인
    tw.set_parallel(true)
    tw.tween_property(label, "scale", Vector2.ONE, 0.25) \
        .set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
    tw.tween_property(label, "modulate:a", 1.0, 0.15)

    # 머무름
    tw.chain().tween_interval(0.5)

    # 퇴장: 페이드아웃
    tw.chain().tween_property(label, "modulate:a", 0.0, 0.2)
    tw.chain().tween_callback(label.queue_free)
```

`TRANS_BACK`이 핵심. 목표 크기를 살짝 넘었다가 돌아오는 "탄성" 효과다. 텍스트가 "뿅" 하고 나타나는 느낌을 준다.

---

## 레시피 9: 아이템 수집 효과 (빨려 들어감)

음식이 캐릭터에게 빨려 들어가는 효과.

```gdscript
func _collect_item(item: Node2D, target_pos: Vector2) -> void:
    var tw := create_tween().set_parallel(true)
    tw.tween_property(item, "position", target_pos, 0.2) \
        .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
    tw.tween_property(item, "scale", Vector2.ZERO, 0.2)
    tw.tween_property(item, "modulate:a", 0.0, 0.15)
    tw.chain().tween_callback(item.queue_free)
```

`EASE_IN`을 쓰면 처음에 천천히 움직이다가 점점 빨라진다. 빨려 들어가는 느낌에 딱이다. `EASE_OUT`이면 처음에 빠르고 끝에 느린데, 이건 "날아가는" 느낌이 더 강하다.

---

## 레시피 10: 카운트다운 (3, 2, 1)

```gdscript
func _countdown() -> void:
    for i in range(3, 0, -1):
        var label := Label.new()
        label.text = str(i)
        label.add_theme_font_size_override("font_size", 80)
        label.position = _vp_size / 2
        add_child(label)

        var tw := create_tween()
        tw.set_parallel(true)
        tw.tween_property(label, "scale", Vector2(1.5, 1.5), 0.7)
        tw.tween_property(label, "modulate:a", 0.0, 0.7) \
            .set_delay(0.3)
        tw.chain().tween_callback(label.queue_free)

        await get_tree().create_timer(1.0).timeout

    _game_active = true
```

`await`과 Tween을 조합한다. 각 숫자가 1초 간격으로 등장하되, 등장 자체는 Tween으로 애니메이션된다.

---

## 레시피 11: 게임 오버 슬로모션

HP가 0이 되면 전체 씬이 느려지는 연출.

```gdscript
func _game_over_slowmo() -> void:
    # 씬 전체 속도를 30%로
    Engine.time_scale = 0.3

    # 2초(체감 0.6초) 후 복원
    await get_tree().create_timer(0.6).timeout

    var tw := create_tween()
    tw.tween_method(
        func(val: float): Engine.time_scale = val,
        0.3, 1.0, 0.5
    )
```

`Engine.time_scale`을 직접 건드리는 거라 조심해야 한다. 복원을 까먹으면 게임 전체가 슬로모션이 된다. `tween_method()`로 부드럽게 원래 속도로 돌아오게 했다.

---

## 레시피 12: 기존 Tween 정리

새 Tween을 시작하기 전에 기존 것을 정리해야 할 때가 있다. 안 그러면 같은 프로퍼티를 두 Tween이 동시에 건드려서 떨린다.

```gdscript
var _active_tween: Tween

func _start_animation() -> void:
    # 기존 Tween이 있으면 중지
    if _active_tween and _active_tween.is_valid():
        _active_tween.kill()

    _active_tween = create_tween()
    _active_tween.tween_property(...)
```

특히 `_process()`에서 조건부로 Tween을 생성할 때 이 패턴이 필수다. 안 그러면 매 프레임 새 Tween이 생기면서 메모리가 터진다.

---

## 이징/트랜지션 치트시트

미니게임에서 자주 쓴 조합:

| 용도 | Trans | Ease | 느낌 |
|------|-------|------|------|
| UI 등장 | BACK | OUT | 뿅! 탄성 |
| UI 퇴장 | QUAD | IN | 부드럽게 사라짐 |
| 이동 | QUAD | OUT | 자연스러운 감속 |
| 빨려듦 | QUAD | IN | 점점 빨라짐 |
| 심장 박동 | SINE | IN_OUT | 부드러운 반복 |
| 화면 흔들기 | LINEAR | - | 즉각적 |
| 줌아웃 | QUAD | OUT | 부드러운 감속 |

`TRANS_BACK`과 `TRANS_ELASTIC`은 극적인 효과에 좋지만, 남용하면 산만하다. 게임 중 반복 애니메이션에는 `SINE`이나 `QUAD`가 안전하다.

---

## 정리

| 패턴 | 핵심 | 주의점 |
|------|------|--------|
| 루프 | `create_tween().set_loops()` | Tween에서 호출 |
| 병렬 | `set_parallel(true)` | 중간에 토글 가능 |
| 시퀀스 | `chain()` | 병렬 완료 후 순차 |
| 흔들기 | 원위치 캡처 필수 | 다른 Tween과 충돌 조심 |
| 슬로모션 | `Engine.time_scale` | 반드시 복원 |
| 정리 | `kill()` 후 새로 생성 | `_process()` 내 생성 주의 |

Godot 4 Tween은 강력한데, API 경계(Tween vs PropertyTweener)만 잘 구분하면 거의 모든 애니메이션을 코드로 만들 수 있다. AnimationPlayer 없이도 미니게임 수준의 연출은 충분하다.
