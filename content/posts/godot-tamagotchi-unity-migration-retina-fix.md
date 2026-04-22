---
title: "Godot 4로 다마고치 만들기 — Unity 포기하고 전환한 이유와 macOS에서 겪은 좌표 지옥"
date: 2026-03-23
draft: false
tags: ["godot", "game-dev", "tamagotchi", "macOS", "retina"]
categories: ["Dev"]
description: "Unity에서 Godot 4.6으로 다마고치 프로젝트를 전환한 이유, AI 바이브코딩에서 GDScript가 유리한 구조적 이유, macOS Retina + embedded editor에서 발생하는 좌표 불일치 문제 해결법까지 실전 삽질 기록."
---

## Unity로 다마고치를 만들다가 멈췄다

올해 초에 AI 생성형 다마고치 프로젝트를 시작했다. 프롬프트를 입력하면 AI가 펫 이미지를 생성해주고, 밥 주고 씻기고 놀아주면서 키우는 방치형 게임이다. 처음에는 당연히 Unity를 선택했다. 2D 게임이니까 Unity면 충분하다고 생각했고, WebGL export로 모바일 웹뷰에 임베딩하면 크로스 플랫폼도 해결될 거라고 봤다.

문제는 **바이브코딩**이었다. Claude Code로 게임 로직을 짜는데, Unity의 `.unity` 씬 파일은 직렬화된 YAML에 GUID 참조가 가득하다. AI가 씬 구조를 읽고 이해하기가 사실상 불가능했다. C# 코드는 그나마 낫지만, Unity는 하나의 기능을 구현하는 패턴이 너무 다양하다. MonoBehaviour 싱글톤, ScriptableObject 이벤트, 의존성 주입, ECS — AI가 프로젝트에서 어떤 패턴을 쓰는지 먼저 파악해야 코드를 짤 수 있다. 이건 느리다.

한 달 정도 Unity로 작업하다가 프로젝트를 멈췄다. 게임 로직보다 Unity 에디터와 싸우는 시간이 더 길었다.

---

## 왜 Godot인가 — AI 코딩에서 구조적으로 유리하다

두 달 후에 다시 프로젝트를 재개하면서 Godot을 선택했다. 핵심 이유는 **파일 포맷이 전부 텍스트**라는 점이다.

| 항목 | Unity | Godot |
|------|-------|-------|
| 씬 파일 | 직렬화 YAML + GUID | `.tscn` 텍스트 (사람이 읽을 수 있음) |
| 스크립트 | C# (넓은 API 표면) | GDScript (게임 전용, 작은 표면) |
| 프로젝트 설정 | 여러 meta 파일 | `project.godot` INI 하나 |
| 아키텍처 | 여러 패턴 중 선택 필요 | Signal + Scene Tree 하나 |
| VCS | force-text 모드 필요, diff 노이즈 많음 | 깔끔한 텍스트 diff |

Godot의 `.tscn` 파일을 열면 이런 식이다:

```
[node name="PetDisplay" parent="." instance=ExtResource("3_pet")]
position = Vector2(200, 319)

[node name="CanvasLayer" type="CanvasLayer" parent="."]

[node name="HUD" parent="CanvasLayer" instance=ExtResource("4_hud")]
```

AI가 이걸 읽으면 "PetDisplay가 (200, 319)에 있고, CanvasLayer 아래에 HUD가 있구나"를 바로 이해한다. Unity의 씬 파일에서 같은 정보를 추출하려면 GUID를 추적해야 한다.

GDScript는 Python과 비슷한 문법인데 게임 개발 전용이다. Signal 시스템, Export 변수, Node Tree 조작 등 게임에 필요한 것만 있다. AI가 GDScript를 짤 때 "웹 개발 패턴"이나 "서버 사이드 패턴"을 실수로 섞어넣을 일이 없다. 표면적이 작으니까 할루시네이션도 적다.

실제로 AI 어시스턴트와 함께 하루 만에 다마고치의 핵심 시스템을 전부 구현했다:

- 펫 상태머신 (IDLE → HUNGRY → DIRTY → SICK → SLEEPING)
- 오프라인 시간 계산 (접속 안 한 동안 배고픔/청결도 감소)
- 케어 액션 + 쿨다운 시스템
- 로컬 세이브
- 펫 행동 패턴 (걷기, 뛰기, 앉기, 두리번거리기)
- UI 테마

Unity로 한 달 걸릴 작업이 Godot + AI 코딩으로 하루에 끝났다.

---

## 멀티 플랫폼 — 하나의 코드베이스로 어디든

다마고치 프로젝트의 목표는 **멀티디바이스**다. 웹에서든, 맥 바탕화면 위젯이든, 폰이든 어디서든 펫을 키울 수 있어야 한다. Godot 4.6은 단일 코드베이스에서 이 모든 플랫폼을 지원한다:

| 플랫폼 | Export 방식 | 비고 |
|--------|------------|------|
| Web/PWA | HTML5/WASM | 브라우저만 있으면 어디든 |
| macOS | Native .app | 위젯 모드 가능 |
| Windows | Native .exe | 위젯 모드 가능 |
| iOS | Xcode 빌드 | macOS 필요 |
| Android | APK/AAB | 직접 빌드 |

단, **Compatibility 렌더러(OpenGL)를 선택해야** 웹 export가 작동한다. Vulkan 기반인 Forward+ 렌더러는 브라우저에서 돌아가지 않는다. `project.godot`에서 이렇게 설정한다:

```ini
[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
renderer/rendering_method.web="gl_compatibility"
```

---

## 펫 상태 시스템 설계

다마고치의 핵심은 상태머신이다. 스탯 3개(hunger, hygiene, happiness)가 시간에 따라 감소하고, 임계치에 따라 상태가 바뀐다.

```gdscript
static func evaluate(stats: PetStats, is_night: bool, is_happy: bool) -> State:
    if stats.hunger <= 0 or stats.hygiene <= 0:
        return State.SICK
    if is_night:
        return State.SLEEPING
    if stats.hunger < 30:
        return State.HUNGRY
    if stats.hygiene < 30:
        return State.DIRTY
    if is_happy:
        return State.HAPPY
    return State.IDLE
```

순수 함수로 구현해서 테스트하기 쉽다. Godot의 headless 모드(`godot --headless -s test_runner.gd`)로 유닛테스트를 돌릴 수 있다. 다만 `-s` 플래그로 실행하는 스크립트는 `extends SceneTree`이어야 한다. `extends Node`를 쓰면 이런 에러가 난다:

```
ERROR: Can't load the script "tests/test_runner.gd" as it doesn't inherit
from SceneTree or MainLoop.
```

---

## .tscn 파일에 이모지를 쓰면 안 된다

Godot의 텍스트 파서는 이모지를 처리하지 못한다. 버튼 텍스트에 🍗, 🧹 같은 이모지를 넣으면 이런 에러가 쏟아진다:

```
ERROR: Unicode parsing error: Invalid unicode codepoint (1f357),
cannot represent as ASCII/Latin-1
```

`.tscn` 파일 안에서 이모지가 `\ud83c\udf57` 형태의 Unicode escape로 저장되는데, Godot의 파서가 이걸 처리하지 못한다. 해결은 간단하다 — ASCII 텍스트로 대체하면 된다:

```
# 이전 (에러)
text = "\ud83c\udf57 Feed"

# 수정 후
text = "Feed"
```

---

## macOS Retina에서 시작된 좌표 지옥

이 프로젝트에서 가장 오래 삽질한 부분이 **펫 좌표 문제**다. 뷰포트를 400x600으로 설정하고 펫을 (200, 319)에 배치했는데, 실행하면 펫이 좌측 상단 창문 위에 작게 나타났다. 바닥 위에 서 있어야 하는데.

디버그 로그를 찍어보니 두 가지 문제가 있었다.

### 문제 1: Godot 에디터의 embedded window

Godot 4.6에는 "embedded play window"라는 기능이 있다. 게임을 에디터 안의 작은 패널에서 실행하는 건데, 이때 윈도우 크기가 400x600이 아니라 에디터가 할당하는 크기(내 경우 275x413)로 줄어든다.

```
# 에디터에서 실행
Window size: (275, 413)

# CLI에서 실행
Window size: (400, 600)
```

`canvas_items` stretch 모드에서 뷰포트 좌표 자체는 400x600이 유지되지만, `stretch/aspect` 설정이 빠져있으면 비율이 맞지 않아서 좌표가 어긋난다. 그런데 Godot 에디터는 **`stretch/aspect`가 기본값이면 project.godot에서 해당 줄을 삭제**해버린다. 에디터를 열 때마다 설정이 날아가는 거다.

해결법: 런타임에 코드로 강제 설정한다.

```gdscript
func _ready() -> void:
    get_tree().root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
    get_tree().root.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
    get_tree().root.content_scale_size = Vector2i(400, 600)
```

### 문제 2: 자식 노드가 부모의 position을 덮어씀

이게 진짜 원인이었다. `main.gd`의 `_layout()` 함수에서 펫 위치를 (200, 372)로 설정하는데, `pet_display.gd`에서 이걸 덮어쓰고 있었다:

```gdscript
# pet_display.gd _ready()에서:
position = Vector2(0, 0)    # _layout()이 설정한 값을 (0,0)으로 초기화

# pet_display.gd _process()에서 매 프레임:
position.y = 0              # Y좌표를 매 프레임 0으로 리셋
```

`_layout()`이 아무리 위치를 바꿔도 `pet_display.gd`가 다음 프레임에 (0, 0)으로 되돌렸다. 좌표 (0, 0)은 뷰포트 좌측 상단, 즉 창문 위다.

Godot의 스크린샷 기능으로 실제 렌더링 결과를 캡처해서 확인했다:

```gdscript
func _take_debug_screenshot() -> void:
    var img := get_viewport().get_texture().get_image()
    img.save_png("/tmp/prompet_debug.png")
    print("Pet global_pos: %s" % pet_display.global_position)
```

이걸로 `Pet global_pos: (79, 0)` — 확실히 (0, 0) 근처에 있는 걸 확인하고, position 덮어쓰기 코드를 제거해서 해결했다.

**교훈: position 제어권은 반드시 한 곳에서만 가져야 한다.**

```gdscript
# WARNING: Do NOT set position in this script.
# Position is controlled by main.gd _layout() only.
# Setting position here (in _ready or _process) will override _layout()
# and cause the pet to appear at (0,0) = top-left corner.
# Only modify sprite.position (local offset for animations), never self.position.
```

---

## AI로 펫 이미지 생성하기

프롬프트로 펫 외형을 생성하는 것도 구현했다. BizRouter API를 통해 Gemini 이미지 모델을 호출하고, 결과 이미지를 64x64로 리사이즈해서 스프라이트에 적용한다.

```gdscript
var full_prompt := "Create a cute pixel art virtual pet character, 64x64 pixels,
transparent background, tamagotchi style: %s" % user_prompt

var headers := PackedStringArray([
    "Content-Type: application/json",
    "Authorization: Bearer " + _api_key
])
var body := JSON.stringify({
    "model": "google/gemini-2.5-flash-image",
    "messages": [{"role": "user", "content": full_prompt}],
    "image_size": "1K",
    "aspect_ratio": "1:1"
})
```

응답에서 base64 이미지를 추출하고, 투명 배경 처리(격자 패턴 제거)까지 자동으로 한다. 이미지 생성 AI가 "투명 배경"을 요청해도 실제로는 격자 패턴 배경을 넣어주는 경우가 많기 때문이다.

```gdscript
static func _remove_background(img: Image) -> void:
    img.convert(Image.FORMAT_RGBA8)
    # 모서리 4곳의 색상을 감지해서 배경색으로 판단
    var corners := [
        img.get_pixel(0, 0),
        img.get_pixel(w - 1, 0),
        img.get_pixel(0, h - 1),
        img.get_pixel(w - 1, h - 1)
    ]
    # 비슷한 색상의 픽셀을 투명으로 처리
    for y in range(h):
        for x in range(w):
            var pixel := img.get_pixel(x, y)
            for bg in bg_colors:
                if _color_similar(pixel, bg, 0.12):
                    img.set_pixel(x, y, Color(0, 0, 0, 0))
                    break
```

---

## GDScript 타입 추론 함정

GDScript에서 `:=`로 변수 선언하면 우변에서 타입을 추론하는데, 함수 반환 타입이 명확하지 않으면 에러가 난다:

```gdscript
# 에러: Cannot infer the type of "success" variable
var success := game_manager.do_action(action_name)

# 해결: 명시적 타입 선언
var success: bool = game_manager.do_action(action_name)
```

`do_action()`이 `bool`을 반환하지만 GDScript 파서가 이를 추론하지 못하는 경우가 있다. 특히 동적 타입 함수나 복잡한 호출 체인에서 자주 발생한다. 습관적으로 타입을 명시하는 게 안전하다.

비슷한 예로 `hop_y`도 있었다:

```gdscript
# 에러
var hop_y := -abs(sin(_hop_phase * PI)) * 20.0

# 해결
var hop_y: float = -abs(sin(_hop_phase * PI)) * 20.0
```

---

## 펫 행동 패턴 — 날아다니지 않게 만들기

처음 펫 이동 로직을 만들었을 때, 펫이 방 안에서 "날아다니는" 느낌이었다. X축과 Y축 모두 랜덤으로 이동시켰기 때문이다. 다마고치나 시메지(데스크톱 펫) 같은 레퍼런스를 찾아보니 핵심은 **바닥에 붙어서 좌우로만 이동**하는 것이었다.

```gdscript
enum Behavior { IDLE_STAND, IDLE_LOOK, WALKING, SITTING, HOPPING }
```

각 행동별로 다른 움직임을 준다:

- **WALKING**: 좌우 뒤뚱뒤뚱 + 살짝 기울어짐
- **HOPPING**: 포물선 점프 + 착지 시 squash & stretch
- **SITTING**: 납작하게 앉아서 쉬기
- **IDLE_LOOK**: 제자리에서 좌우 두리번거리기

Squash & stretch는 캐릭터에 생동감을 주는 클래식 애니메이션 기법이다:

```gdscript
Behavior.HOPPING:
    var hop_y: float = -abs(sin(_hop_phase * PI)) * 20.0
    sprite.position.y = hop_y
    if hop_y > -3.0:
        _squash = Vector2(1.2, 0.8)   # 착지: 납작
    else:
        _squash = Vector2(0.85, 1.15)  # 공중: 길쭉
```

---

## 동적 레이아웃 — 어떤 윈도우 크기에서든 작동하게

에디터 embedded window, CLI 실행, 모바일 등 다양한 화면 크기에서 동작해야 하므로 절대 좌표 대신 뷰포트 비율로 배치한다:

```gdscript
func _layout() -> void:
    var vp := get_viewport().get_visible_rect().size

    # 배경: 뷰포트에 맞게 스케일
    var bg := $Background as Sprite2D
    var bg_scale := maxf(vp.x / bg.texture.get_size().x,
                         vp.y / bg.texture.get_size().y)
    bg.scale = Vector2(bg_scale, bg_scale)
    bg.position = vp / 2.0

    # 펫: 뷰포트 높이의 62% 위치 (바닥선)
    var floor_y := vp.y * 0.62
    pet_display.position = Vector2(vp.x / 2.0, floor_y)
```

---

## 정리

| 항목 | Unity | Godot |
|------|-------|-------|
| AI 코딩 호환성 | 낮음 (GUID, 다양한 패턴) | 높음 (텍스트 기반, 단일 패턴) |
| 2D 게임 개발 속도 | 보통 | 빠름 |
| 멀티플랫폼 | 강력 (콘솔 포함) | 좋음 (콘솔 제외) |
| 파일 포맷 | 바이너리/YAML 혼합 | 전부 텍스트 |
| 웹 export | WebGL (무거움) | WASM (15-25MB) |
| 학습 곡선 | 가파름 | 완만 |

Godot이 모든 면에서 낫다는 게 아니다. 3D 게임이나 콘솔 타겟이면 Unity가 여전히 강하다. 하지만 **2D 인디 게임 + AI 코딩 워크플로우**에서는 Godot의 텍스트 기반 구조가 압도적으로 유리하다.

macOS에서 개발한다면 Retina 스케일링과 에디터 embedded window 문제를 미리 알아두면 삽질을 크게 줄일 수 있다. `content_scale`을 코드에서 강제 설정하고, position 제어권은 반드시 한 곳에서만 관리하는 것. 이 두 가지가 핵심이었다.
