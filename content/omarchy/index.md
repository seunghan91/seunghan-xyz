---
title: "Omarchy 오픈소스 기여 기록"
date: 2026-09-30
lastmod: 2026-09-30
draft: false
hidemeta: true
ShowBreadCrumbs: false
ShowPostNavLinks: false
ShowReadingTime: false
description: "Rails 창시자 DHH가 만든 리눅스 배포판 Omarchy와 Try Omarchy 프로젝트에 기여하는 과정을 기록합니다."
---

## Omarchy에 기여를 시작합니다

2026년 9월 30일, Omarchy 프로젝트에 오픈소스 기여를 시작했습니다.
이 페이지는 그 과정을 날짜순으로 남기는 기록장입니다.

> Omarchy를 처음 쓴다면 [Omarchy 창 다루기](/omarchy/manual/)부터 보세요.

---

## 플러그인

- [Glance Dock](/omarchy/glance-dock/) — 상단바에 마우스를 올리면 뜨는 독과 화면 가장자리 독을 더하는 셸 플러그인입니다.
- [Omarchy 창 다루기](/omarchy/manual/) — 처음 쓸 때 필요한 창 단축키를 정리했습니다.

---

## Omarchy는 무엇인가

Omarchy는 루비 온 레일즈(Ruby on Rails)를 만든
데이비드 하이네마이어 한손(DHH)이 시작한 리눅스 배포판입니다.
Arch Linux 위에 타일형 창 관리자 Hyprland를 얹고,
개발에 필요한 도구와 설정을 미리 맞춰 둔 구성입니다.
저장소 소개 문구는 "Beautiful, Modern & Opinionated Linux"입니다.

| 항목 | 내용 |
|------|------|
| 만든 사람 | DHH (Ruby on Rails 창시자) |
| 기반 | Arch Linux + Hyprland |
| 저장소 | [basecamp/omarchy](https://github.com/basecamp/omarchy) |
| 공개 시점 | 2025년 6월 |
| 라이선스 | MIT |

---

## 왜 Omarchy인가

2015년에 레일즈로 코딩을 처음 시작했습니다.
그 뒤로 여러 언어와 프레임워크를 거쳤지만 지금도 레일즈 스택을 가장 좋아합니다.
이 사이트에 올린 프로젝트 대부분이 Rails 8 위에서 돌아갑니다.

레일즈는 "설정보다 관례"라는 원칙으로 만든 프레임워크입니다.
Omarchy는 같은 사람이 같은 원칙을 운영체제에 적용한 결과물입니다.
10년 동안 그 원칙 덕을 봤으니 이번에는 돌려줄 차례입니다.

---

## 기여 대상 — Try Omarchy

Omarchy 본체는 리눅스 배포판이라 전용 기기가 있어야 제대로 쓸 수 있습니다.
Try Omarchy는 Omarchy를 가상머신에 담아 맥과 윈도우에서 앱처럼 실행하게 해 주는 프로젝트입니다.
평소 쓰는 맥에서 바로 돌려 볼 수 있어 첫 기여 대상으로 골랐습니다.

| 저장소 | 대상 환경 | 구성 |
|--------|-----------|------|
| [omacom/try-omarchy](https://github.com/omacom/try-omarchy) | Apple Silicon 맥, macOS 15 이상 | QEMU + Swift/AppKit 런처 |
| [omacom/try-omarchy-windows](https://github.com/omacom/try-omarchy-windows) | x86_64 Windows 10·11 | Go 런처 + 가상머신 이미지 |

두 저장소 모두 작은 수정과 문서 개선은 이슈 없이 바로 PR을 받습니다.
동작이나 구조를 크게 바꾸는 변경은 이슈에서 먼저 논의합니다.

---

## 현재 상태

- 맥판 Try Omarchy 설치 완료 (릴리스 v0.4.1)
- 두 저장소 소스 받아서 읽는 중
- 윈도우판은 ARM64 Windows를 지원하지 않아 x86 PC에서 확인 예정

---

## 살펴보는 기여 후보

### 1. 윈도우 런처 한국어 번역

윈도우 런처의 화면 문구는 `app/ui-locales/` 아래 JSON 파일로 관리합니다.
지금은 `en.json` 하나만 있습니다.
다국어 지원을 묻는 [이슈 #127](https://github.com/omacom/try-omarchy-windows/issues/127)이 열려 있어
`ko.json`을 추가하는 기여를 검토하고 있습니다.
번역은 실제 Windows 화면에서 확인한 뒤 올릴 계획입니다.

### 2. macOS에서 윈도우 저장소 테스트 실행

윈도우 저장소의 Go 테스트를 맥에서 돌리면 다수가 실패합니다.
대부분은 macOS 임시 폴더 경로(`/var`)가 심볼릭 링크라서 생기는 실패로 보입니다.
원인을 더 좁힌 뒤 고칠 가치가 있는지 판단할 예정입니다.

---

## 기여 기록

| 날짜 | 내용 |
|------|------|
| 2026-09-30 | 맥판 설치, 두 저장소 클론, 기여 후보 조사 |

PR이나 이슈를 올리면 이 표에 링크와 함께 추가합니다.
