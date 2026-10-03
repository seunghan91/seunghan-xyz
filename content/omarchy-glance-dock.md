---
title: "Glance Dock — Omarchy 앱 독 플러그인"
date: 2026-10-02
lastmod: 2026-10-02
draft: false
url: "/omarchy/glance-dock/"
hidemeta: true
ShowBreadCrumbs: false
ShowPostNavLinks: false
ShowReadingTime: false
ShowToc: false
description: "Omarchy 상단 바에 마우스를 올리면 그 워크스페이스의 앱 아이콘이 내려오는 플러그인입니다. 화면 가장자리 독과 종료 메뉴도 함께 씁니다."
---

[Omarchy 기여 기록](/omarchy/) › Glance Dock

상단 바에 마우스를 올리면 열린 앱이 아이콘으로 내려옵니다.\
화면 가장자리에 맥 스타일 독도 함께 띄웁니다.

![데모 — 상단 바에 마우스를 올리면 독이 내려오고, 워크스페이스 번호를 따라 바뀐 뒤, 가장자리 독과 오른쪽 클릭 메뉴(Quit·Force Quit)가 열리는 모습](/images/omarchy/glance-dock-demo.gif)

![상단 바의 워크스페이스 번호 위에 마우스를 올리자 그 워크스페이스의 앱 아이콘이 한 줄로 내려온 모습](/images/omarchy/glance-dock-top.png)

| 항목 | 내용 |
|------|------|
| 이름 | Glance Dock |
| 버전 | 0.2.0 |
| 종류 | Omarchy 바 위젯 플러그인 (Quickshell/QML) |
| 환경 | Omarchy + Hyprland |
| 개발 | Seunghan ([@seunghan91](https://github.com/seunghan91)) |
| 마켓 | [omarchyplugins.com](https://omarchyplugins.com/plugin.html?id=io.github.seunghan91.glance-dock) (검증 완료) |
| 라이선스 | MIT |

---

## 무엇을 하나

### 바 위 호버 독

- 시계 왼쪽 바 위에 마우스를 잠깐 두면 독이 열립니다. 기본 지연은 250ms입니다.
- 독은 마우스 바로 아래에 내려옵니다.
- 워크스페이스 번호 위에서는 그 워크스페이스의 앱을 보여 줍니다.\
  다른 곳에서는 지금 워크스페이스의 앱을 보여 줍니다.
- 번호 사이를 옮겨 다니면 목록도 따라 바뀝니다.
- 앱 하나에 아이콘 하나입니다. 창이 여럿이면 개수 배지가 붙습니다.
- 클릭하면 그 앱으로 이동합니다.\
  다시 누를 때마다 그 앱의 창을 차례로 돕니다.
- 지금 쓰는 앱에는 밑줄이 표시됩니다. 아이콘에 올리면 앱 이름이 뜹니다.
- 앱이 많으면 가로로 스크롤되고 넘친 개수는 `+N`으로 보입니다.
- 아이콘 크기는 Omarchy 화면 배율을 따릅니다. 바 높이의 1.08배가 기준입니다.

### 화면 가장자리 독

![왼쪽 가장자리에 열린 앱 전체가 세로 독으로 떠 있고 아이콘 위에 앱 이름 툴팁이 보이는 전체 화면](/images/omarchy/glance-dock-edge.jpg)

- 열린 앱 전체를 화면 가장자리 독으로 보여 줍니다.
- 위치는 왼쪽(기본)·오른쪽·아래 중에서 고르고 끌 수도 있습니다.
- 자동 숨김(기본)은 마우스가 가장자리에 닿을 때 미끄러져 나옵니다.
- 고정은 독 자리를 비워 두고 타일 창을 옆으로 밀어 둡니다.

### 오른쪽 클릭 메뉴

![앱 아이콘을 오른쪽 클릭해 그 앱의 창 목록과 Quit 항목이 있는 메뉴가 열린 모습](/images/omarchy/glance-dock-menu.png)

- 아이콘을 오른쪽 클릭하면 macOS와 비슷한 메뉴가 열립니다.
- 위에는 그 앱의 창 목록이 있습니다. 누르면 그 창으로 이동합니다.
- 맨 아래 Quit은 목록의 창에 닫기를 요청합니다. `Super + W`와 같은 방식입니다.\
  상단 독에서는 그 워크스페이스의 창만, 가장자리 독에서는 모든 워크스페이스의 창이 대상입니다.
- 메뉴가 열린 상태에서 Alt(Option)를 누르면 Force Quit으로 바뀝니다.\
  Force Quit은 앱 프로세스를 강제로 끝냅니다.
- Esc를 누르거나 메뉴 밖을 클릭하면 닫힙니다.\
  모니터가 여러 대면 다른 모니터를 클릭해도 macOS처럼 닫힙니다.
- 창이 많으면 목록이 스크롤되고 Quit은 항상 보입니다.

비슷한 플러그인으로 워크스페이스 미리보기나 맥 스타일 가장자리 독이 있습니다.\
Glance Dock은 마우스 아래 내려오는 독, 가장자리 독, 종료 메뉴를 한 플러그인에 묶었습니다.

---

## 설치·업데이트·제거

Omarchy 공식 플러그인 마켓에 검증을 거쳐 올라가 있습니다.
[마켓 페이지](https://omarchyplugins.com/plugin.html?id=io.github.seunghan91.glance-dock)에서 설치 명령을 복사해도 되고, 아래 명령을 그대로 써도 됩니다.

설치하면서 바로 켭니다.

```bash
omarchy plugin add https://github.com/seunghan91/omarchy-glance-dock --enable
```

바에서 위치를 옮기려면 다음 명령을 씁니다.

```bash
omarchy bar move io.github.seunghan91.glance-dock --section left
```

업데이트와 제거는 플러그인 id로 합니다.

```bash
omarchy plugin update io.github.seunghan91.glance-dock
omarchy plugin remove io.github.seunghan91.glance-dock
```

Omarchy 메뉴의 플러그인 항목에서도 켜기·끄기·제거를 할 수 있습니다.

---

## 설정

바의 위젯 설정에서 바꾸거나, 터미널에서 `omarchy bar set`으로 바꿉니다.

```bash
# 가장자리 독을 오른쪽으로
omarchy bar set io.github.seunghan91.glance-dock edgeDock right
# 가장자리 독을 고정(창이 옆으로 비켜남)
omarchy bar set io.github.seunghan91.glance-dock edgeMode pinned
# 독이 열리기까지 기다리는 시간(숫자 설정은 --json)
omarchy bar set io.github.seunghan91.glance-dock hoverDelayMs 150 --json
```

- `iconScale` — 아이콘 크기.\
  `small`(0.85배) · `normal`(1배) · `large`(1.2배), 기본 `normal`
- `hoverDelayMs` — 독이 열리기까지 기다리는 시간.\
  0–1000ms, 기본 250
- `edgeDock` — 가장자리 독 위치.\
  `off` · `left` · `right` · `bottom`, 기본 `left`
- `edgeMode` — 가장자리 독 동작.\
  `autohide` · `pinned`, 기본 `autohide`

---

## 사용 팁과 한계

- 독이 너무 빨리 열리면 `hoverDelayMs`를 늘립니다.
- 가장자리 독이 창을 가리면 `pinned`로 바꿉니다.
- Alt를 누른 채 오른쪽 클릭하면 인식되지 않습니다.\
  독이 키보드 수식키를 받지 못하기 때문입니다.\
  메뉴를 연 뒤에 Alt를 누릅니다.

---

## 소스·라이선스

- 소스: [github.com/seunghan91/omarchy-glance-dock](https://github.com/seunghan91/omarchy-glance-dock)
- 설명서: [한국어](https://github.com/seunghan91/omarchy-glance-dock/blob/main/README.ko.md) 등 9개 언어 README
- 마켓: [omarchyplugins.com](https://omarchyplugins.com/plugin.html?id=io.github.seunghan91.glance-dock)
- 라이선스: MIT

[← Omarchy 기여 기록으로 돌아가기](/omarchy/)

<small>2026년 10월, Glance Dock 0.2.0 기준</small>
