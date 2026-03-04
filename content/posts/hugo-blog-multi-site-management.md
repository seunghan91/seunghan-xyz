---
title: "Hugo 블로그 3개를 하나의 폴더에서 관리하는 구조"
date: 2026-02-26
draft: false
tags: ["Hugo", "Netlify", "블로그", "정적사이트", "PaperMod", "Stack"]
description: "용도가 다른 Hugo 블로그 3개(개발 블로그, 앱 홈페이지, 개인 블로그)를 단일 디렉토리에서 운영하면서 각각 Netlify로 독립 배포하는 방법"
---

Hugo 블로그를 목적별로 3개 운영하고 있다.

1. **개발 블로그** — 개발 삽질 기록, 기술 문서 (이 블로그)
2. **[앱명] 홈페이지** — 앱 소개 + 업데이트 블로그, 다국어(ko/en)
3. **개인 블로그** — 비개발 글

각각 역할이 달라서 분리했지만, 관리는 한 곳에서 하고 싶었다.

---

## 디렉토리 구조

```
~/domain/
├── seunghan-xyz/           # 개발 블로그
│   ├── content/
│   │   ├── posts/          # 기술 포스트
│   │   ├── projects/       # 프로젝트 소개
│   │   └── about/
│   ├── themes/
│   │   └── PaperMod/       # git submodule
│   ├── hugo.toml
│   └── public/             # 빌드 결과물
│
├── blogs/
│   └── blog_richdada/
│       ├── [앱명]-blog/    # 앱 홈페이지 겸 블로그
│       │   ├── content/
│       │   │   ├── posts/
│       │   │   ├── features/
│       │   │   ├── legal/
│       │   │   └── mcp/
│       │   ├── i18n/       # ko.yaml, en.yaml
│       │   ├── hugo.toml
│       │   └── netlify.toml
│       │
│       └── personal-blog/  # 개인 블로그
│           ├── content/
│           │   └── posts/
│           └── hugo.toml
│
└── dcode/
    └── landing/            # 정적 랜딩 페이지들
```

---

## 테마 선택

### 개발 블로그: PaperMod

```toml
# hugo.toml
theme = 'PaperMod'
```

미니멀하고 빠르다. 코드 하이라이팅이 깔끔하고, 다크모드를 기본 지원한다.
검색, 아카이브, 목차 기능이 내장되어 있어서 추가 설정이 거의 필요 없다.

```toml
[markup.highlight]
style = "github-dark"
noClasses = false
```

### 앱 블로그: Hugo Stack v3

```toml
# hugo.toml
[module]
  [[module.imports]]
    path = "github.com/CaiJimmy/hugo-theme-stack/v3"
```

카드형 레이아웃. 앱 소개 페이지처럼 시각적 요소가 많을 때 어울린다.
Hugo Modules로 설치해서 업데이트가 쉽다:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

---

## 다국어 설정 (앱 블로그)

앱 스토어 심사에서 앱 홈페이지 URL을 요구할 때 영문 페이지도 필요하다.

```toml
# hugo.toml
DefaultContentLanguage = "ko"

[languages]
  [languages.ko]
    languageName = "Korean"
    weight = 1
  [languages.en]
    languageName = "English"
    weight = 2
```

콘텐츠 파일 구조:

```
content/
├── posts/
│   ├── ko/
│   │   └── feature-update.md
│   └── en/
│       └── feature-update.md
├── features/
│   └── _index.ko.md
│   └── _index.en.md
```

번역이 없는 페이지는 기본 언어(ko)로 폴백된다. 완전한 번역보다 핵심 페이지만 영문화하는 게 현실적이다.

---

## Netlify 배포

각 블로그마다 `netlify.toml`이 있고, Netlify 사이트도 별도다.

```toml
# netlify.toml
[build]
  publish = "public"
  command = "hugo --minify"

[build.environment]
  HUGO_VERSION = "0.141.0"

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
```

자동 배포: GitHub 저장소와 Netlify를 연결하면 `main` 브랜치 push시 자동 빌드.

수동 배포 (개발 블로그):
```bash
cd ~/domain/seunghan-xyz
hugo && netlify deploy --prod \
  --dir ~/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

`--dir`에 **절대경로** 필수. 상대경로 쓰면 현재 작업 디렉토리 기준으로 배포되어 엉뚱한 파일이 올라간다.

---

## 로컬 개발

```bash
# 개발 블로그
cd ~/domain/seunghan-xyz
hugo server -D          # draft 포함 미리보기
hugo server --port 1314 # 포트 충돌 방지

# 앱 블로그
cd ~/domain/blogs/blog_richdada/[앱명]-blog
hugo server -D --port 1315

# 개인 블로그
cd ~/domain/blogs/blog_richdada/personal-blog
hugo server -D --port 1316
```

세 서버를 동시에 띄울 수 있다. 포트만 다르게.

---

## 포스트 작성 패턴

### Front Matter 템플릿

```markdown
---
title: "제목"
date: 2026-02-26
draft: false
tags: ["태그1", "태그2"]
description: "SEO용 한 줄 설명"
---
```

`draft: true`로 작성해두고 완성되면 `false`로 바꾼다. 초안이 실수로 배포되는 걸 막을 수 있다.

### 파일명 규칙

```
posts/flutter-testflight-makefile-automation.md
posts/rails-dart-api-integration.md
posts/hugo-blog-multi-site-management.md
```

모두 소문자, 하이픈 구분. URL이 그대로 파일명이 된다.

---

## 테마 업데이트

### PaperMod (git submodule)

```bash
cd ~/domain/seunghan-xyz
git submodule update --remote --merge
git add themes/PaperMod
git commit -m "chore: update PaperMod theme"
```

### Stack v3 (Hugo Modules)

```bash
cd ~/domain/blogs/blog_richdada/[앱명]-blog
hugo mod get -u
hugo mod tidy
```

---

## SEO 설정

```toml
# hugo.toml
enableRobotsTXT = true

[outputs]
home = ["HTML", "RSS", "JSON"]

[params]
  description = "..."
  keywords = ["개발", "Flutter", "iOS", "Rails"]
```

JSON 출력은 Fuse.js 검색에 필요하다. PaperMod에서 검색 기능을 켜면 자동으로 사용된다.

---

## 정리

| 용도 | 테마 | 배포 방식 | 특이사항 |
|------|------|----------|---------|
| 개발 블로그 | PaperMod | Netlify CLI (수동) | 이 블로그 |
| 앱 홈페이지 | Stack v3 | Netlify (자동, GitHub 연동) | ko/en 다국어 |
| 개인 블로그 | Stack v3 | Netlify (자동, GitHub 연동) | — |

세 블로그가 서로 독립적으로 빌드/배포된다.
공통 설정을 공유하고 싶은 욕심이 있었지만, 각각 Hugo 버전도 다르고 요구사항도 달라서 그냥 독립적으로 두는 게 낫다는 결론이다.
