---
title: "MDM — Markdown+Media"
date: 2026-03-13
draft: false
tags: ["Rust", "Python", "JavaScript", "Markdown", "Parser", "Open Source"]
description: "이미지·비디오·오디오를 ![[]] 문법으로 직관적으로 제어하는 마크다운 슈퍼셋"
weight: 2
---

## MDM (Markdown+Media)

`![[name:preset | attr=val]]` 문법 하나로 이미지, 비디오, 오디오를 마크다운 문서에 자유롭게 임베드하고 제어하는 오픈소스 프로젝트입니다.

**GitHub** → [seunghan91/markdown-media](https://github.com/seunghan91/markdown-media)
**Playground** → [seunghan91.github.io/markdown-media/playground](https://seunghan91.github.io/markdown-media/playground/)
**npm** → [@mdm/parser](https://www.npmjs.com/package/@mdm/parser)

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
| **JS Parser** | Vanilla JS + Rollup | Tokenizer → Renderer → HTML |
| **Python Parser** | Python 3.8+ | 동일 API, 서버 사이드 변환 |
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

- **JS**: Node.js built-in test runner, 85개 테스트 통과
- **Python**: pytest, 84개 테스트 통과
- **CI**: GitHub Actions (build + test + deploy)

---

## 링크

- [GitHub Repository](https://github.com/seunghan91/markdown-media)
- [Interactive Playground](https://seunghan91.github.io/markdown-media/playground/)
- [API 문서](https://mdm-api.onrender.com/docs)
- [npm @mdm/parser](https://www.npmjs.com/package/@mdm/parser)
