---
title: "MDM — Markdown+Media"
date: 2026-03-13
lastmod: 2026-04-17
draft: false
tags: ["Rust", "Python", "JavaScript", "Markdown", "Parser", "Open Source"]
description: "이미지·비디오·오디오를 ![[]] 문법으로 직관적으로 제어하는 마크다운 슈퍼셋"
weight: 2
---

## MDM (Markdown+Media)

`![[name:preset | attr=val]]` 문법 하나로 이미지, 비디오, 오디오를 마크다운 문서에 자유롭게 임베드하고 제어하는 오픈소스 프로젝트입니다.

| 링크 | 주소 |
|------|------|
| **GitHub** | [seunghan91/markdown-media](https://github.com/seunghan91/markdown-media) · 최신 `v0.3.0` (2026-04-16) |
| **Playground** | [seunghan91.github.io/markdown-media/playground](https://seunghan91.github.io/markdown-media/playground/) |
| **npm (Native)** | [@markdown-media/core](https://www.npmjs.com/package/@markdown-media/core) `1.0.0` — napi Node.js 바인딩 |
| **npm (WASM)** | [@markdown-media/wasm](https://www.npmjs.com/package/@markdown-media/wasm) `0.1.0` — 브라우저/Node 공용 WASM (PDF 포함, 1.5 MB) |
| **PyPI** | [mdm-parser](https://pypi.org/project/mdm-parser/) `0.1.0` |
| **데스크톱 앱** | [mdm-desktop v0.1.1](https://github.com/seunghan91/mdm-desktop/releases) — macOS 코드사이닝 + 공증 완료 |
| **Chrome 확장** | MDM Converter (HWP/PDF/DOCX → Markdown) — 오프라인 WASM, 권한 0개 · 심사 중 |
| **MCP 서버** | [law-check.com/api/mcp](https://law-check.com) — `mdm_convert_document` · `mdm_extract_text` · `mdm_detect_format` |

---

## 1분 세팅 — 상황별 최단 경로

| 상황 | 명령어 / 링크 |
|------|---------------|
| **데스크톱 앱 (GUI)** | [mdm-desktop v0.1.1](https://github.com/seunghan91/mdm-desktop/releases) 에서 DMG 다운로드 → 드래그앤드롭 (공증 완료) |
| **Python** | `pip install mdm-parser` |
| **Node.js (Native)** | `npm install @markdown-media/core` |
| **브라우저 / WASM** | `npm install @markdown-media/wasm` (PDF 포함 1.5 MB) |
| **CLI 파이프** | `cat file.hwp \| hwp2mdm stream --ext hwp --mode body` |
| **AI Agent (MCP)** | law-check.com에서 MCP 키 발급 → `~/.claude.json`에 gateway 등록 |

### MCP 설정 (Claude Code 예시)

```json
{
  "mcpServers": {
    "korea-law-hub": {
      "url": "https://law-check.com/api/mcp",
      "headers": { "Authorization": "McpKey YOUR_KEY" }
    }
  }
}
```

설정 후 재시작하면 `mdm_convert_document`, `mdm_extract_text`, `mdm_detect_format` 3개 tool이 자동 로드된다.

전체 가이드: [GETTING-STARTED.md](https://github.com/seunghan91/markdown-media/blob/master/GETTING-STARTED.md)

---

## 최신 업데이트 — v0.3.0 (2026-04-16)

### HWPX 파서 추출 품질 상향

- **문자 스타일 정규화** — 취소선 / 밑줄 판정을 블랙리스트 → **화이트리스트**로 전환. 한컴 내보내기의 `shape="3D"` 같은 placeholder 값을 본문 전체 취소선으로 오해석하던 버그 제거.
- **강조점 (`<mark>`)** — OWPML `symMark` (`DOT`/`CIRCLE`/`TICK`/`TILDE`/`MIDDLE_DOT`/`COLON`) 를 `<mark>…</mark>` 로 보존. 공공문서 핵심 용어 신호가 살아남음.
- **루비 (덧말)** — `<hp:dutmal>` subText를 `한자(hanja)` 괄호 주석으로 보존.
- **각주 / 미주 / 머리말 / 꼬리말** — paragraph-level 컨트롤 4종을 `[각주: …]` · `[미주: …]` · `[머리말: …]` · `[꼬리말: …]` 로 인라인 확장.
- **수식 → LaTeX** — `<hp:equation>` 내용을 단일 라인 `$…$`, 다중 라인 `$$ … $$` 블록으로 출력. GitHub/Obsidian/LLM 바로 렌더.
- **Depth-aware paragraph scanner** — 중첩 `<hp:p>` 때문에 본문이 조기 종료되던 버그 수정.

### 데스크톱 뷰어 — 6개 액션 버튼 + 원본 충실도 뷰

| 버튼 | 동작 |
|---|---|
| 📋 복사 | 마크다운 클립보드 복사 |
| 📊 통계 | 9개 지표 모달 (문자·어절·문단·헤딩·표·이미지·강조·취소선·체크리스트) |
| 🔀 비교 | 두 번째 파일 선택 → 신구대조표 side-by-side |
| 📝 메모 | 사이드카(.mdm.json) 메모, 원본 HWP 불변 |
| ✨ AI에 묻기 | 4개 프리셋 × 4개 프로바이더 (Claude / ChatGPT / Gemini / Perplexity) |
| 💾 내보내기 | JSON · HTML · TXT |

**원본 모드** — 외부 HWP 에디터(iframe) 임베드로 픽셀-충실 렌더링을 MDM 안에서 바로 확인. 나란히 모드에선 렌더 ↔ 소스 판이 비율 기반으로 함께 스크롤.

### 보안 — ZIP 폭탄 방어

`MAX_HWPX_XML` · `MAX_HWPX_BINDATA` 디컴프레션 상한 도입. 악의적 HWPX의 메모리 폭탄 차단.

### 테스트 — Golden-file 회귀 스캐폴드

`core/tests/golden_hwpx.rs` 신설. `UPDATE_GOLDEN=1` 로 재생성, diff 리포트. 10개 초기 고정점(취소선/밑줄/강조/루비/각주/미주/수식 inline·block/머리말+꼬리말).

전체 릴리즈 노트: [v0.3.0 CHANGELOG](https://github.com/seunghan91/markdown-media/blob/master/CHANGELOG.md)

---

## 왜 만들었나

HWP, DOCX, PDF 같은 문서를 마크다운으로 변환하면 문서 안에 포함된 이미지나 미디어를 표현할 방법이 없습니다. 기존 마크다운 이미지 문법(`![alt](url)`)은 크기, 정렬, 캡션, 프리셋 같은 레이아웃 정보를 담을 수 없기 때문입니다.

MDM은 변환된 문서의 미디어 레이아웃 정보를 보존하기 위한 마크다운 확장 문법입니다.

```
HWP / DOCX / PDF
      ↓ 변환
MDM Markdown
  ![[chart.png | width=800 align=center caption="1분기 실적"]]
  ![[intro-video:inline]]
      ↓ MDM 파서
      HTML
```

---

## 문법

```markdown
# 기본 — 파일명만
![[hero.jpg]]

# 속성 지정
![[photo.jpg | width=800 align=center caption="서울 야경"]]

# 프리셋 사용 (.mdm 사이드카 파일)
![[logo:header]]
![[intro-video:inline]]

# 비디오
![[demo.mp4 | controls autoplay muted loop]]

# 오디오
![[podcast.mp3 | controls]]

# 유튜브 임베드
![[youtube-intro | width=720 height=405]]
```

`.mdm` 사이드카 파일(YAML)로 미디어 경로와 프리셋을 중앙 관리할 수 있습니다.

```yaml
version: "1.0"
media_root: "./assets/"
resources:
  logo:
    type: image
    src: logo.png
    alt: "MDM Logo"
    presets:
      header: { width: 200 }
      footer: { width: 120 }
  youtube-intro:
    type: embed
    provider: youtube
    id: dQw4w9WgXcQ
presets:
  inline: { width: 480, align: center }
```

---

## 기술 스택

| 구성 요소 | 기술 | 역할 |
|-----------|------|------|
| **Rust Core** | Rust + olefile/zip | HWP/HWPX/DOCX/PDF 파서 |
| **Native Node 바인딩** | `@markdown-media/core` (napi-rs) | Node.js 네이티브 연동 |
| **WASM 엔진** | `@markdown-media/wasm` (wasm-bindgen) | 브라우저 / Node 공용, PDF 포함 1.5 MB |
| **JS Viewer** | `@markdown-media/viewer` (Vanilla JS + Rollup) | Tokenizer → Renderer → HTML |
| **Python Parser** | `mdm-parser` (Python 3.8+) | 동일 API, 서버 사이드 변환 |
| **데스크톱 앱** | Tauri v2 + SvelteKit | macOS 코드사이닝 + 공증 |
| **Chrome 확장** | Manifest V3 + WASM | 완전 오프라인, 권한 0개 |
| **API Server** | FastAPI + Uvicorn | 문서 업로드 → MDM 변환 REST API |
| **Playground** | 순수 HTML/JS | 브라우저 라이브 데모 |
| **GitHub Pages** | Hugo + Actions | 랜딩·플레이그라운드 배포 |

---

## 주요 기능

### 파서 파이프라인

```
텍스트 입력
  └→ Tokenizer: ![[...]] 패턴 추출
       └→ Renderer: MDM 데이터(프리셋) + 속성 병합
            └→ HTML 출력 (XSS 이스케이핑 내장)
```

### 프리셋 우선순위

리소스별 프리셋 → 전역 MDM 프리셋 → 내장 크기 프리셋(thumb/small/medium/large/full) → 인라인 속성 순으로 병합됩니다.

### 문서 변환 API

HWP, DOCX, PDF 파일을 업로드하면 MDM 마크다운 + 추출 이미지(base64)를 반환합니다.

```bash
curl -X POST https://mdm-api.onrender.com/api/convert \
  -F "file=@document.hwp"
```

```json
{
  "filename": "document.hwp",
  "format": "hwp",
  "markdown": "# 제목\n\n본문...\n\n![[image_0.png | width=auto]]\n",
  "images": { "image_0.png": "base64..." },
  "stats": { "chars": 1234, "images": 2 }
}
```

---

## 테스트

- **Rust Core**: `cargo test` 260 passed (4개 스위트 합산, v0.3.0 기준)
- **JS Viewer**: Node.js built-in test runner
- **Python**: pytest
- **Golden-file 회귀**: `core/tests/golden_hwpx.rs` (취소선/밑줄/강조/루비/각주/미주/수식/머리말·꼬리말)
- **CI**: GitHub Actions (build + test + deploy)

---

## 링크

- [GitHub Repository](https://github.com/seunghan91/markdown-media)
- [Interactive Playground](https://seunghan91.github.io/markdown-media/playground/)
- [API 문서](https://mdm-api.onrender.com/docs)
- [npm @markdown-media/core](https://www.npmjs.com/package/@markdown-media/core) (native)
- [npm @markdown-media/wasm](https://www.npmjs.com/package/@markdown-media/wasm) (브라우저)
- [PyPI mdm-parser](https://pypi.org/project/mdm-parser/)
- [CHANGELOG](https://github.com/seunghan91/markdown-media/blob/master/CHANGELOG.md)
