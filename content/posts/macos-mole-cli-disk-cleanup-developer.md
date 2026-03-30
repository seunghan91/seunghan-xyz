---
title: "Mole로 맥 190GB 정리한 후기 — 개발자 맥에 쌓인 캐시의 실체"
date: 2026-03-30
draft: false
tags: ["macOS", "Mole", "disk-cleanup", "developer-tools", "Docker"]
description: "macOS 개발자 머신에 쌓인 190GB 캐시를 Mole CLI로 정리한 실전 기록. npm, Flutter, Docker, Xcode 캐시 분석과 안전한 삭제 방법을 다룬다."
---

개발하다 보면 디스크가 어느 순간 꽉 찬다. Xcode 빌드하다 용량 부족 에러가 뜨고, Docker 이미지 pull이 실패하고, npm install이 ENOSPC를 뱉는다. 저장소 확인해보면 "시스템 데이터"가 수백 GB를 차지하고 있는데, 정작 뭐가 그렇게 큰지 알 수가 없다.

CleanMyMac 같은 도구가 있지만 연 9만원짜리 구독이고, 개발자 특화 캐시는 잘 못 잡는다. 그러다 GitHub에서 34K 스타를 받은 오픈소스 CLI 도구 **Mole**을 발견했다. 설치부터 190GB 정리까지의 실전 기록을 남긴다.

---

## Mole이 뭔가

[Mole](https://github.com/tw93/Mole)은 대만 개발자 tw93이 만든 macOS 시스템 정리 CLI 도구다. Shell 79%와 Go 21%로 작성됐고, MIT 라이선스다.

핵심은 CleanMyMac + AppCleaner + DaisyDisk + iStat Menus를 **단일 바이너리**로 합쳤다는 점이다. GUI 없이 터미널에서 `mo` 한 줄로 실행된다. 백그라운드 프로세스도 없고, 실행할 때만 동작한다.

| 명령어 | 기능 | 구현 |
|--------|------|------|
| `mo clean` | 시스템/앱 캐시, 브라우저 잔여 파일 정리 | Shell |
| `mo uninstall` | 앱 + Launch Agent + 설정파일 완전 제거 | Shell + TUI |
| `mo optimize` | 시스템 DB 재빌드, DNS 플러시, Spotlight 재색인 | Shell |
| `mo analyze` | 디스크 사용량 시각화 탐색기 | Go (Bubble Tea) |
| `mo status` | CPU/GPU/메모리/디스크 실시간 대시보드 | Go (gopsutil) |
| `mo purge` | 프로젝트 빌드 아티팩트 정리 (node_modules 등) | Shell |

Go로 작성된 `analyze`와 `status`는 Charm의 [Bubble Tea](https://github.com/charmbracelet/bubbletea) TUI 프레임워크를 사용한다. 터미널 안에서 인터랙티브 UI가 돌아가는 구조다.

---

## 설치

Homebrew가 가장 깔끔하다.

```bash
brew install tw93/tap/mole
```

Homebrew에서 Command Line Tools 버전 이슈가 나는 경우가 있다. 그때는 설치 스크립트로 우회한다.

```bash
curl -fsSL https://raw.githubusercontent.com/tw93/mole/main/install.sh -o /tmp/mole-install.sh
bash /tmp/mole-install.sh
```

설치 스크립트는 `/usr/local/bin`에 설치하기 때문에 sudo 비밀번호가 필요하다. 설치 완료되면 `mo --version`으로 확인한다.

```
◎ Mole installed successfully, version 1.32.0
```

---

## 먼저 dry-run으로 뭘 지울지 확인한다

Mole의 가장 좋은 점은 `--dry-run` 플래그다. 실제로 아무것도 삭제하지 않고 삭제 대상만 보여준다.

```bash
sudo -v && mo clean --dry-run
```

`sudo -v`를 먼저 실행하는 이유는 시스템 캐시 스캔에 관리자 권한이 필요하기 때문이다. 이걸 안 하면 유저 캐시만 스캔된다.

내 맥미니(M4 Pro, 1TB)에서 실행한 결과:

```
Potential space: 190.26GB | Items: 12750 | Categories: 232
```

190GB. 1TB 디스크의 거의 20%가 캐시였다.

---

## 190GB의 실체: 카테고리별 분석

### User App Cache — 33GB

dry-run에서 "User app cache 276 items, 33.30GB"라고 나오면 무서워 보인다. 하지만 실체를 까보면 전부 재생성 가능한 캐시다.

```bash
du -sh ~/Library/Caches/* | sort -hr | head -10
```

```
7.6G  Google/Chrome
1.6G  BraveSoftware
1.1G  CocoaPods
641M  Chromium
143M  com.apple.amp.itmstransporter
98M   bun
96M   claude-cli-nodejs
```

Chrome 캐시만 7.6GB. 웹페이지 로딩 속도를 위해 브라우저가 저장해둔 이미지, JS, CSS 파일들이다. 삭제하면 웹사이트 첫 방문 시 약간 느려지지만, 다시 방문하면 캐시가 재생성된다.

CocoaPods 캐시 1.1GB는 `pod install` 시 다시 다운로드된다. Chromium 641MB는 Playwright 테스트용 브라우저 캐시다.

**결론: 전부 삭제해도 안전하다.**

### 브라우저 캐시 — 약 20GB

Chrome, Brave, Firefox, Comet 브라우저를 다 쓰고 있었는데, 각각 캐시가 GB 단위로 쌓여 있었다.

```
Chrome cache: 8.13GB
Chrome Service Worker: 총 4GB+
Brave cache: 1.71GB
Firefox cache: 567.5MB
Comet cache: 1.70GB
Puppeteer browser cache: 3.11GB
GoogleUpdater CRX cache: 726.7MB
```

Chrome Service Worker 캐시가 특히 심했다. 프로필별로 각각 수백 MB ~ 2.5GB씩 쌓여 있었다. Service Worker는 PWA나 오프라인 기능을 위해 브라우저가 로컬에 저장하는 데이터인데, 실제로 오프라인에서 쓸 일이 거의 없으니 삭제해도 문제없다.

### npm / pnpm / Bun 캐시 — 35GB

개발자 맥의 진짜 블랙홀이다.

```
npm cache directory: 10.21GB
npm npx cache: 5.89GB
pnpm store: 9.20GB
Bun cache: 9.72GB
```

npm은 패키지를 `.npm` 디렉토리에 캐싱해서 재설치 속도를 높인다. 문제는 이게 정리가 안 된다는 거다. 수년간 설치한 모든 패키지의 모든 버전이 쌓여 있다. `npm cache clean --force`로 수동 정리할 수도 있지만, Mole이 한 번에 처리해준다.

pnpm은 content-addressable store 방식이라 중복이 적다고 하지만, 그래도 9GB다. Bun도 마찬가지로 9.7GB.

삭제해도 다음 `npm install`이나 `pnpm install`에서 필요한 패키지만 다시 받는다. 첫 설치가 약간 느려지는 게 유일한 단점이다.

### Python uv 캐시 — 23GB

`uv`는 Rust로 작성된 Python 패키지 매니저인데, pip보다 10배 이상 빠른 대신 캐시를 공격적으로 한다. 23GB나 쌓여 있었다. pip, PyTorch 캐시까지 합치면 24GB.

### Flutter 빌드 캐시 — 약 50GB

이게 제일 충격이었다. Flutter 프로젝트가 20개 넘게 있는데, 각 프로젝트마다 `.dart_tool/`과 `build/` 디렉토리가 수 GB씩이었다.

```
unmask: build 7.20GB + .dart_tool 881MB
launchcrew/mobile: build 5.20GB + .dart_tool 844MB
120_fastpass/mobile: build 3.50GB + .dart_tool 858MB
ainote_flutter: build 3.30GB + .dart_tool 599MB
```

Flutter `build/` 디렉토리에는 컴파일된 앱 바이너리, 프레임워크 캐시, dSYM 파일 등이 들어간다. `flutter build`하면 다시 생성되니까 삭제해도 된다. `.dart_tool/`도 마찬가지로 패키지 resolution 캐시라 `flutter pub get`으로 복원된다.

### Xcode Derived Data + Archives — 9GB

```
Xcode derived data: 7.61GB
Xcode archives: 1.17GB
Xcode documentation cache: 542.8MB
```

Xcode DerivedData는 개발자 맥의 고전적인 용량 도둑이다. 프로젝트를 빌드할 때마다 중간 산출물이 쌓이는데, 자동 정리가 안 된다. `rm -rf ~/Library/Developer/Xcode/DerivedData`를 주기적으로 실행하는 개발자가 많은 이유다.

Archives는 TestFlight이나 App Store 제출용으로 만든 `.xcarchive` 파일이다. 과거 빌드 기록인데, 이미 제출 완료된 건 삭제해도 된다.

### Docker — 115GB (별도 정리)

이건 Mole `mo clean` 범위 밖이라 별도로 정리해야 한다.

```bash
docker system df -v
```

```
Images: 102.3GB, Reclaimable: 59.76GB (58%)
Containers: 572.6MB, Reclaimable: 572.6MB (99%)
Build Cache: 38.32GB, Reclaimable: 19.07GB
```

내 경우 Supabase 이미지만 5개 버전이 쌓여 있었다. postgres 이미지가 v15.6, v15.8, v17.6.054, v17.6.063, v17.6.064 — 5개로 약 20GB. studio, storage-api, edge-runtime도 각각 2~3개 버전씩 중복이었다.

```bash
docker system prune -f
```

`-f`는 확인 프롬프트 없이 바로 실행하는 플래그다. 이 명령으로 중지된 컨테이너, dangling 이미지, 빌드 캐시를 정리한다.

```
Deleted Containers: 42개
Deleted Images: 4개 (~8GB)
Deleted build cache objects: 82개 (~14GB)
Total reclaimed space: 22.71GB
```

더 공격적으로 정리하려면 `docker system prune -a`를 쓰면 된다. `-a` 플래그는 사용하지 않는 이미지도 전부 삭제한다. 단, 실행 중인 컨테이너의 이미지는 건드리지 않는다. 나중에 `docker compose up`하면 필요한 이미지를 다시 pull한다.

---

## 실제 정리 실행

### Step 1: mo clean

```bash
sudo -v && mo clean
```

Mole은 whitelist 시스템이 있어서 중요한 캐시는 자동으로 보호한다. 기본 whitelist에 21개 패턴이 포함되어 있다.

```
✓ Whitelist: 21 core patterns active
  ↳ /Users/seunghan/Library/Caches/ms-playwright*
  ↳ /Users/seunghan/.cache/huggingface*
  ↳ /Users/seunghan/.ollama/models/*
  ↳ /Users/seunghan/Library/Caches/JetBrains*
```

Playwright 브라우저, Hugging Face 모델, Ollama 모델, JetBrains IDE 캐시 등이 기본 보호 대상이다. 이걸 커스터마이징하려면:

```bash
mo clean --whitelist
```

### Step 2: Docker 정리

```bash
docker system prune -f
```

### Step 3: mo purge (프로젝트 빌드 아티팩트)

```bash
mo purge
```

이 명령을 실행하면 인터랙티브 TUI가 뜬다. 홈 디렉토리의 모든 프로젝트를 스캔해서 `node_modules`, `build/`, `.dart_tool/`, `target/`, `.next/`, `venv/` 등을 찾아준다.

```
Select Categories to Clean [1/2462], 127.72GB, 2402 selected
➤ ~/toy/servo                    14.36GB | target  | Recent
  ~/law_ontology/rust-api         9.20GB | target
  ~/unmask                        7.20GB | build
```

여기서 중요한 건 **Recent** 표시다. 최근 7일 이내에 수정된 프로젝트는 기본 선택에서 제외된다. 활발히 개발 중인 프로젝트의 빌드 캐시를 날리면 다음 빌드가 오래 걸리니까.

조작법은 간단하다:
- `A`: 전체 선택/해제
- `Space`: 개별 항목 토글
- `Enter`: 선택한 항목 삭제
- `Q`: 취소

---

## Mole vs CleanMyMac — 개발자 관점 비교

| 항목 | Mole | CleanMyMac |
|------|------|-----------|
| **가격** | 무료 (MIT) | 연 $89.95 |
| **인터페이스** | CLI (터미널) | GUI |
| **개발자 캐시** | npm, Flutter, Xcode, Docker, Rust 등 심층 스캔 | 기본적인 캐시만 |
| **dry-run** | `--dry-run`으로 미리보기 | Smart Scan 결과 확인 가능 |
| **whitelist** | 패턴 기반 보호 | UI에서 설정 |
| **백그라운드** | 실행할 때만 동작 | Menu Bar helper 상주 |
| **앱 제거** | Launch Agent, 설정, 캐시까지 완전 제거 | 동일 |
| **악성코드 검사** | 없음 | 있음 |
| **시스템 모니터링** | `mo status` (TUI 대시보드) | 있음 (GUI) |

CleanMyMac이 일반 사용자에게는 나을 수 있다. 하지만 개발자에게는 Mole이 압도적이다. npm, pnpm, Bun, Flutter, Rust target, Python venv, Docker — 이런 개발 도구 캐시를 카테고리별로 잡아주는 건 CleanMyMac에서 기대하기 어렵다.

---

## 주의사항과 알려진 함정

### optimize 명령은 신중하게

`mo optimize`는 Spotlight 재색인, DNS 플러시, Launch Services DB 재빌드 등을 수행한다. 대부분 안전하지만, 일부 macOS 환경에서 WindowServer 크래시나 그래픽 서브시스템 불안정이 보고된 적 있다. GitHub Issues에도 해당 내용이 있다. `mo clean`과 `mo purge`는 안정적이니 이 두 개를 주로 쓰면 된다.

### Docker.raw 파일은 prune로 줄어들지 않을 수 있다

macOS의 Docker Desktop은 Linux VM 위에서 돌아간다. 모든 이미지와 컨테이너가 `~/Library/Containers/com.docker.docker/Data/` 안의 가상 디스크 파일에 저장되는데, `docker system prune` 후에도 이 파일 크기가 안 줄어들 수 있다. Docker Desktop → Settings → Resources → Disk image size에서 수동으로 줄여야 한다.

### 활발히 개발 중인 프로젝트의 빌드 캐시

`mo purge`에서 Recent 표시된 프로젝트는 웬만하면 건드리지 않는 게 좋다. Flutter `build/` 디렉토리를 삭제하면 다음 `flutter build`가 처음부터 다시 컴파일해야 해서 시간이 꽤 걸린다. Xcode DerivedData도 마찬가지다.

### Spotify 오프라인 음악은 자동 보호

Mole은 Spotify 오프라인 캐시를 자동으로 감지해서 건드리지 않는다. dry-run에서도 이렇게 표시된다:

```
◎ Spotify cache protected · offline music detected
```

---

## 정리 결과

| 정리 수단 | 확보 용량 |
|-----------|----------|
| Docker system prune | 22.7GB |
| mo clean | ~75GB |
| mo purge (예상) | ~80GB |
| **총합** | **~178GB** |

147GB Free였던 맥미니가 300GB+ Free로 바뀌었다. 1TB 디스크의 30% 이상을 캐시가 먹고 있었던 셈이다.

---

## 정기 유지보수 루틴

한 번 정리하고 끝이 아니다. 개발하면 캐시는 다시 쌓인다. 월 1회 정도 이 루틴을 돌리면 된다.

```bash
# 1. 캐시 정리
sudo -v && mo clean

# 2. Docker 정리
docker system prune -f

# 3. 프로젝트 아티팩트 정리
mo purge

# 4. 시스템 상태 확인
mo status
```

`mo status`는 CPU, 메모리, 디스크, 배터리, 네트워크를 실시간 대시보드로 보여준다. iStat Menus 대체로 쓸 만하다.

```
Mole Status Health ● 92  MacBook Pro · M4 Pro · 32GB · macOS 15.x
⚙ CPU                    ▦ Memory
Total ████████░░░░░░ 45%  Used ████████░░░░░░ 58%
▤ Disk                    ⚡ Power
Used █████░░░░░░░░░ 35%  Level ██████████████ 100%
```

---

## 결론

개발자 맥은 일반 사용자 맥과 다르다. npm, Docker, Flutter, Xcode, Python — 각 도구가 독립적으로 캐시를 쌓고, 서로의 존재를 모른다. 시스템 설정의 "저장 공간"을 봐도 "시스템 데이터"라는 뭉뚱그려진 숫자만 보인다.

Mole은 이 문제를 CLI 한 줄로 해결한다. `--dry-run`으로 뭘 지울지 먼저 확인하고, whitelist로 중요한 건 보호하고, 인터랙티브 TUI로 프로젝트별 아티팩트를 선택적으로 정리한다. 무료이고 오픈소스다.

설치는 `brew install tw93/tap/mole`, 정리는 `mo clean`. 한 번 해보면 수십 GB가 돌아온다.
