---
title: "WarioWare에서 훔친 미니게임 설계 원칙 — Godot 4로 3종 구현까지"
date: 2026-03-24
draft: false
tags: ["godot", "gamedev", "minigame", "게임디자인", "WarioWare"]
categories: ["Dev"]
description: "닌텐도 WarioWare의 마이크로게임 설계 원칙을 분석하고, Godot 4 다마고치 프로젝트에 3종의 미니게임을 실제로 구현한 과정. 즉각적 이해, 단순 입력, 점진적 난이도의 실전 적용기."
---

미니게임을 만들다 보면 욕심이 생긴다. 조작을 추가하고, 규칙을 복잡하게 만들고, 스코어 시스템을 정교하게 다듬고. 그런데 막상 플레이하면 재미없다. 5초 안에 "이게 뭐하는 게임이지?"가 파악이 안 되면 이미 실패다.

닌텐도 R&D1 팀이 2003년에 만든 WarioWare(미니게임천국)는 이 문제를 정면으로 해결한 게임이다. 5초짜리 게임 200개를 쏟아내면서도 하나하나가 직관적이다. 이 글에서는 WarioWare의 설계 원칙을 분석하고, 내 다마고치 프로젝트에 적용한 과정을 기록한다.

---

## WarioWare가 20년째 연구 대상인 이유

WarioWare 시리즈는 게임 디자인 수업에서 단골 교재다. "마이크로게임"이라는 장르를 사실상 창조했기 때문이다.

핵심 숫자:
- 게임당 **3~5초**
- 조작: **방향키 + 버튼 1개**
- 설명: **단어 1~2개** ("피해!", "잡아!", "날아!")
- 난이도: **3단계** 자동 순환

수석 디렉터 Goro Abe가 GDC에서 밝힌 4대 원칙:

### 1. 즉각적 이해 (Instant Comprehension)

플레이어가 게임 시작 2초 안에 "뭘 해야 하는지" 파악해야 한다. 튜토리얼이 필요하면 이미 실패다. WarioWare의 모든 게임은 화면에 뜨는 단어 하나로 규칙을 전달한다.

나도 처음에 미니게임마다 설명 화면을 넣으려고 했다. "좌우로 움직여서 똥을 피하세요. 3번 맞으면 게임 오버입니다." 이런 거. 근데 WarioWare를 보고 깨달았다. 그냥 **"피해!"** 한 마디면 된다.

### 2. 보편적 테마 (Universal Theme)

코를 후비거나, 벌레를 잡거나, 빵을 자른다. 누구나 아는 행동이다. 다마고치 맥락에서는 "똥 피하기", "밥 잡기"가 이에 해당한다. 펫을 키우는 사람이면 즉시 이해한다.

### 3. 단순 입력 (Simple Input)

방향키와 버튼 1개. 이게 전부다. 복잡한 콤보나 동시 입력 없다. 내 미니게임도 **좌/우 이동만** 사용한다. 점프도 없고, 공격도 없다.

### 4. 점진적 난이도 (Progressive Difficulty)

WarioWare는 같은 게임이 3단계로 변한다. 속도가 빨라지거나, 장애물이 늘거나, 시간이 줄어든다. **규칙은 안 바뀌고 파라미터만 바뀐다**. 이게 핵심이다.

---

## 3종 미니게임 설계서

WarioWare 원칙을 적용해서 다마고치 프로젝트에 3종의 미니게임을 만들었다.

### Left or Right (방향 맞추기)

가장 단순한 형태. WarioWare의 "원샷" 카테고리에 해당한다.

```
프롬프트: "어디?" (화살표 방향 표시)
입력: 좌 또는 우 (1회)
시간: 2초
성공: 펫 경험치 +10
실패: 아무 일도 안 일어남
```

구현이 단순해 보이지만 이 게임의 진짜 가치는 **전환 테스트**에 있다. 게임 모드 진입 → 입력 처리 → 결과 → 복귀까지의 전체 사이클을 가장 적은 코드로 검증할 수 있다. 나는 이걸 먼저 만들어서 게임 모드 프레임워크를 잡았다.

```gdscript
# left_or_right_mode.gd
func _on_input(direction: String) -> void:
    if _answered:
        return
    _answered = true

    if direction == _correct_direction:
        _show_result(true)
        _pet_display.add_exp(10)
    else:
        _show_result(false)

    # 1.5초 후 게임 모드 종료
    create_tween().tween_callback(end_game).set_delay(1.5)
```

### Dodge Poop (똥 피하기)

WarioWare의 "Dodge!" 계열. 시간 생존형이다.

```
프롬프트: "피해!"
입력: 좌/우 지속 이동
시간: 25초
HP: 3 (3번 맞으면 실패)
난이도 곡선: 시간이 지날수록 떨어지는 속도 증가
```

이 게임에서 가장 삽질한 건 좌표계 문제였다. 부모 씬을 줌아웃해서 빈 공간을 만드는데, 자식 노드의 이동 범위와 충돌 판정이 전부 틀어진다. [이전 글](/posts/godot4-tamagotchi-minigame-zoom-coordinate-tween/)에서 자세히 다뤘다.

난이도 곡선은 이렇게 구현했다:

```gdscript
# 시간에 따라 떨어지는 속도 증가
func _get_fall_speed() -> float:
    var base_speed := 200.0
    var time_bonus := _time_elapsed * 8.0  # 초당 8px/s 증가
    var max_speed := 500.0
    return min(base_speed + time_bonus, max_speed)

# 스폰 간격도 줄어듦
func _get_spawn_interval() -> float:
    var base_interval := 0.8
    var reduction := _time_elapsed * 0.015
    return max(base_interval - reduction, 0.3)
```

WarioWare 원칙대로 **규칙은 안 바뀐다**. 그냥 빨라질 뿐이다. 새로운 적이 나오거나 패턴이 바뀌는 건 없다. 그래도 25초 버티면 충분히 긴장감이 있다.

### Catch Food (음식 잡기)

WarioWare의 "잡아!" + "피해!" 복합형. 판단이 추가된다.

```
프롬프트: "잡아! (폭탄 주의)"
입력: 좌/우 지속 이동
시간: 15초
점수: 음식 +1점, 폭탄 -2점
난이도 곡선: 시간이 지날수록 폭탄 비율 증가
```

음식과 폭탄이 섞여서 떨어진다. 음식은 잡고 폭탄은 피해야 한다. WarioWare의 "일본 음식 잡기" 미니게임에서 직접 영감을 받았다.

```gdscript
func _spawn_item() -> void:
    # 폭탄 확률: 20%에서 시작, 시간에 따라 증가
    var bomb_chance: float = 0.2 + _time_elapsed * 0.015
    var is_bomb: bool = randf() < min(bomb_chance, 0.5)  # 최대 50%

    var item := Sprite2D.new()
    if is_bomb:
        item.texture = _bomb_texture
        item.set_meta("is_bomb", true)
        item.set_meta("points", -2)
    else:
        var food_idx := randi() % _food_textures.size()
        item.texture = _food_textures[food_idx]
        item.set_meta("is_bomb", false)
        item.set_meta("points", 1)

    # 화면 위 랜덤 위치에서 시작
    item.position = Vector2(
        randf_range(40, _vp_size.x - 40),
        -20
    )
    item.set_meta("speed", randf_range(150, 280))
    add_child(item)
```

여기서 중요한 디자인 결정이 있다. **폭탄을 맞아도 게임 오버가 아니다**. 점수만 깎인다. WarioWare의 "Dodge!" 계열에서 장애물에 맞으면 바로 실패인 것과 다르게 설계했다. 이유는 다마고치 유저가 하드코어 게이머가 아니기 때문이다. 펫 키우는 사람에게 미니게임은 부가 콘텐츠지 메인이 아니다. 실패가 너무 가혹하면 미니게임 자체를 안 하게 된다.

---

## 프롬프트 디자인: 단어 하나의 힘

WarioWare의 가장 과소평가된 요소가 프롬프트 디자인이다. "Dodge!", "Catch!", "Jump!" 같은 명령형 단어 하나가 3초짜리 게임의 규칙 전체를 전달한다.

내 미니게임에서도 이걸 적용했다:

| 게임 | 프롬프트 | 보조 텍스트 |
|------|---------|------------|
| Left or Right | "어디?" | (화살표 표시) |
| Dodge Poop | "피해!" | 없음 |
| Catch Food | "잡아!" | "💣 주의" |

프롬프트는 화면 중앙에 크게 0.8초 동안 표시된다:

```gdscript
func _show_prompt(text: String, sub_text: String = "") -> void:
    var label := Label.new()
    label.text = text
    label.add_theme_font_size_override("font_size", 64)
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    label.position = Vector2(_vp_size.x / 2, _vp_size.y / 3)
    add_child(label)

    if sub_text != "":
        var sub := Label.new()
        sub.text = sub_text
        sub.add_theme_font_size_override("font_size", 24)
        sub.position = label.position + Vector2(0, 60)
        add_child(sub)

    # 0.8초 후 페이드아웃
    var tw := create_tween()
    tw.tween_interval(0.5)
    tw.tween_property(label, "modulate:a", 0.0, 0.3)
    tw.tween_callback(label.queue_free)
```

0.8초가 절묘한 타이밍이다. 읽을 수 있을 만큼 길고, 게임 시작을 방해하지 않을 만큼 짧다. WarioWare는 이보다 더 짧다(약 0.5초). 하지만 내 게임은 25초짜리라 조금 여유를 줬다.

---

## 난이도 설계: 파라미터만 바꿔라

3종 미니게임의 난이도 곡선을 비교하면:

| 게임 | 변하는 것 | 변하지 않는 것 |
|------|----------|--------------|
| Left or Right | 제한 시간 (2초→1.5초→1초) | 좌/우 선택 |
| Dodge Poop | 낙하 속도, 스폰 간격 | 좌우 이동으로 피하기 |
| Catch Food | 폭탄 비율, 낙하 속도 | 음식 잡기 + 폭탄 피하기 |

공통점이 보인다. **규칙이 바뀌지 않는다**. 새로운 메커닉이 추가되지 않는다. 빨라지거나, 많아지거나, 비율이 바뀔 뿐이다.

이게 WarioWare의 핵심 교훈이다. 플레이어가 이미 이해한 규칙 위에서 난이도를 올려야 한다. 새 규칙을 추가하면 "즉각적 이해"가 깨진다.

게임학 연구자 Chaim Gingold가 분석한 WarioWare의 난이도 구조:

```
Round 1: Speed 1.0x → 5게임 후 보스
Round 2: Speed 1.3x → 10게임 후 보스
Round 3: Speed 1.6x → 15게임 후 보스
...반복, 속도만 증가
```

내 게임에서도 같은 원칙을 따랐다:

```gdscript
# dodge_game_mode.gd
const DIFFICULTY_TABLE := {
    # 경과 시간: {fall_speed, spawn_interval}
    0:  {"speed": 200, "interval": 0.8},
    8:  {"speed": 280, "interval": 0.6},
    16: {"speed": 360, "interval": 0.45},
    22: {"speed": 440, "interval": 0.35},
}

func _get_current_difficulty() -> Dictionary:
    var result := DIFFICULTY_TABLE[0]
    for threshold in DIFFICULTY_TABLE:
        if _time_elapsed >= threshold:
            result = DIFFICULTY_TABLE[threshold]
    return result
```

테이블 기반으로 관리하면 밸런싱이 쉽다. 플레이하면서 "16초 지점이 너무 급격하다" 싶으면 숫자만 바꾸면 된다.

---

## 전환 연출: 경계를 명확하게

WarioWare에서 게임 간 전환이 화려한 이유가 있다. **"지금 새 게임이 시작됐다"는 신호**를 확실하게 보내는 것이다.

내 다마고치에서도 미니게임 시작/종료 시 명확한 전환을 넣었다:

```gdscript
# 게임 시작 시퀀스
func _start_sequence() -> void:
    # 1. 씬 줌아웃 (0.4초)
    _zoom_out_main_scene()

    # 2. 프롬프트 표시 (0.8초)
    await get_tree().create_timer(0.5).timeout
    _show_prompt("피해!")

    # 3. 카운트다운 (선택적)
    await get_tree().create_timer(1.0).timeout

    # 4. 게임 시작
    _game_active = true
    _start_spawning()

# 게임 종료 시퀀스
func _end_sequence(success: bool) -> void:
    _game_active = false
    _clear_all_items()

    # 결과 표시
    if success:
        _show_result("성공! 🎉", Color.GREEN)
    else:
        _show_result("실패...", Color.RED)

    # 줌 복원
    await get_tree().create_timer(1.0).timeout
    _restore_main_scene()
```

줌아웃 → 프롬프트 → 게임 → 결과 → 줌복원. 이 5단계 시퀀스가 "지금 미니게임 중이다"는 명확한 경계를 만든다. WarioWare처럼 한 박자 쉬어가는 타이밍이 중요하다. 바로 시작하면 준비가 안 되고, 너무 느리면 템포가 죽는다.

---

## 피드백은 즉각적이고 과장되게

WarioWare의 성공/실패 피드백은 0.3초 안에 온다. 그리고 과장됐다. 성공하면 빠바밤! 실패하면 삐빅!

이걸 참고해서 넣은 피드백들:

```gdscript
# 똥에 맞았을 때
func _on_hit() -> void:
    _hp -= 1

    # 1. 화면 흔들기 (0.16초)
    _screen_shake()

    # 2. 캐릭터 빨갛게 (0.25초)
    _pet_display.sprite.modulate = Color(1, 0.2, 0.2)
    create_tween().tween_property(
        _pet_display.sprite, "modulate", Color.WHITE, 0.25)

    # 3. HP 표시 업데이트
    _update_hp_display()

    # 4. 진동 (모바일)
    if OS.has_feature("mobile"):
        Input.vibrate_handheld(100)

# 음식 잡았을 때
func _on_catch(points: int) -> void:
    _score += points

    # 점수 팝업 (위로 떠오르며 사라짐)
    var popup := Label.new()
    popup.text = "+%d" % points if points > 0 else "%d" % points
    popup.modulate = Color.GREEN if points > 0 else Color.RED

    var tw := create_tween()
    tw.set_parallel(true)
    tw.tween_property(popup, "position:y", popup.position.y - 40, 0.5)
    tw.tween_property(popup, "modulate:a", 0.0, 0.5)
    tw.chain().tween_callback(popup.queue_free)
```

화면 흔들기 + 색상 변경 + 진동. 세 가지 채널로 동시에 피드백을 준다. WarioWare도 시각(화면 효과) + 청각(효과음) + 촉각(컨트롤러 진동)을 항상 동시에 사용한다.

---

## 정리: WarioWare 체크리스트

미니게임을 만들 때마다 이 체크리스트를 확인한다:

| 원칙 | 체크 항목 | 통과 기준 |
|------|----------|----------|
| 즉각적 이해 | 프롬프트 1~2단어로 규칙 전달 가능? | 처음 보는 사람이 3초 안에 이해 |
| 단순 입력 | 방향키 + 버튼 1개로 충분? | 조작 설명이 필요하면 실패 |
| 점진적 난이도 | 파라미터만 변하고 규칙은 유지? | 새 메커닉 추가 = 위험 신호 |
| 즉각적 피드백 | 성공/실패를 0.3초 안에 전달? | 시각 + 모션 + 소리(진동) |
| 명확한 경계 | 시작/종료 전환이 명확? | 일반 모드와 혼동 없음 |

WarioWare가 20년 전 게임인데 아직도 참고할 게 이렇게 많다. 단순함의 깊이가 깊다.

다음은 이 미니게임들의 상태 관리 패턴을 정리할 예정이다. 게임 모드 진입/복귀 시 저장해야 할 것들이 생각보다 많고, 하나라도 빠지면 버그가 된다.
