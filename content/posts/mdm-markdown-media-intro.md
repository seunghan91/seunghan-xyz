---
title: "MDM: HWP·DOCX를 마크다운으로 변환할 때 미디어를 어떻게 표현할까"
date: 2026-03-13
draft: false
tags: ["Markdown", "Parser", "Rust", "Python", "JavaScript", "Open Source", "HWP"]
description: "![[]] 문법으로 이미지·비디오를 제어하는 마크다운 슈퍼셋 MDM을 만들게 된 이유와 구조"
cover:
  image: ""
  alt: "MDM Markdown+Media"
ShowToc: true
TocOpen: false
---

## 문제: 문서 변환 후 미디어가 사라진다

HWP, DOCX, PDF를 마크다운으로 변환하면 텍스트는 잘 나오는데 이미지나 미디어 레이아웃 정보가 유실됩니다.

기존 마크다운 이미지 문법은 이렇습니다:

```markdown
![대체 텍스트](image.jpg)
```

원본 문서에서 이미지가 `width: 800px`, `align: center`, `caption: "1분기 실적"` 이렇게 배치되어 있었다면? 마크다운으로 변환하는 순간 이 정보들이 모두 사라집니다.

단순 기술 블로그 글이라면 괜찮지만, 보고서·기획서·법률 문서처럼 레이아웃이 의미를 가지는 문서에서는 치명적입니다.

---

## 해결: 속성을 담을 수 있는 확장 문법

그래서 만든 게 MDM(Markdown+Media)입니다. `![[]]` 안에 속성을 직접 쓸 수 있습니다.

```markdown
![[photo.jpg | width=800 align=center caption="1분기 실적"]]
![[demo.mp4 | controls autoplay muted]]
![[podcast.mp3 | controls]]
```

비교하면 이렇습니다:

| | 기존 마크다운 | MDM |
|---|---|---|
| 이미지 크기 | ❌ | ✅ `width=800` |
| 정렬 | ❌ | ✅ `align=center` |
| 캡션 | ❌ | ✅ `caption="..."` |
| 비디오 | ❌ | ✅ `controls autoplay` |
| 오디오 | ❌ | ✅ |
| 프리셋 재사용 | ❌ | ✅ `![[logo:header]]` |

### 프리셋 시스템

같은 이미지를 여러 곳에서 다른 크기로 써야 할 때 `.mdm` 사이드카 파일로 관리합니다.

```yaml
# blog.mdm
version: "1.0"
resources:
  logo:
    type: image
    src: ./assets/logo.png
    presets:
      header: { width: 200 }
      footer: { width: 80 }
```

```markdown
![[logo:header]]   <!-- width=200 -->
![[logo:footer]]   <!-- width=80 -->
```

---

## 구현 구조

파서 파이프라인은 세 단계입니다.

```
입력 텍스트
  ↓
[Tokenizer]  ![[...]] 패턴을 찾아 토큰 배열로 분리
  ↓
[Renderer]   MDM 데이터(프리셋) + 인라인 속성 병합 → HTML 태그 생성
  ↓
HTML 출력
```

JavaScript로 구현한 Tokenizer 핵심은 정규식 하나입니다:

```js
const mdmPattern = /!\[\[([^\]]+)\]\]/g;
// 이름:프리셋 | 속성들 파싱
const refParts = /^([^:|]+)(?::([^|]+))?(?:\s*\|\s*(.+))?$/;
```

렌더러는 파일 확장자를 보고 img/video/audio/iframe 태그를 자동으로 선택합니다.

```js
renderDirectFile(filename, attrs) {
  const ext = filename.split('.').pop().toLowerCase();
  if (['jpg','jpeg','png','gif','webp','svg','avif'].includes(ext))
    return this.renderImage(filename, attrs);
  if (['mp4','webm','ogg','mov'].includes(ext))
    return this.renderVideo(filename, attrs);
  if (['mp3','wav','ogg','aac','flac'].includes(ext))
    return this.renderAudio(filename, attrs);
  return this.renderEmbed(filename, attrs);
}
```

---

## 다중 언어 구현

같은 스펙을 JS, Python, Rust 세 개 언어로 구현했습니다.

**JavaScript** (`@mdm/parser` npm)
```js
import { MDMParser } from '@mdm/parser';
const parser = new MDMParser();
await parser.loadMDM('./doc.mdm');
const html = await parser.parse(markdownText);
```

**Python** (`mdm-parser` PyPI)
```python
from mdm import MDMParser
parser = MDMParser()
parser.load_mdm('./doc.mdm')
html = parser.parse(markdown_text)
```

JS는 85개, Python은 84개 테스트가 통과합니다. 두 구현이 동일한 출력을 내도록 테스트 케이스를 미러링했습니다.

---

## 문서 변환 API

변환 흐름 전체를 묶은 REST API도 만들었습니다.

```
HWP / DOCX / PDF 업로드
  ↓ FastAPI (Render, Singapore)
  Python 변환기로 텍스트+이미지 추출
  ↓
MDM 마크다운 반환
  {
    "markdown": "# 제목\n\n![[image_0.png | width=auto]]\n",
    "images": { "image_0.png": "base64..." }
  }
```

Playground에서 파일을 직접 올려볼 수 있습니다 → [playground](https://seunghan91.github.io/markdown-media/playground/)

---

## 오픈소스

GitHub에 전체 코드가 공개되어 있습니다.

- [github.com/seunghan91/markdown-media](https://github.com/seunghan91/markdown-media)
- Playground: [seunghan91.github.io/markdown-media/playground](https://seunghan91.github.io/markdown-media/playground/)
- API 문서: [mdm-api.onrender.com/docs](https://mdm-api.onrender.com/docs)
