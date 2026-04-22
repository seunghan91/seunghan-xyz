---
title: "Hugo 블로그 3개를 하나의 폴더에서 관리하는 구조"
date: 2025-10-08
draft: false
tags: ["Hugo", "Netlify", "블로그", "정적사이트", "PaperMod", "Stack"]
categories: ["DevOps"]
description: "용도가 다른 Hugo 블로그 3개(개발 블로그, 앱 홈페이지, 개인 블로그)를 단일 디렉토리에서 운영하면서 각각 Netlify로 독립 배포하는 방법"
cover:
  image: "/images/og/hugo-blog-multi-site-management.png"
  alt: "Hugo Blog Multi Site Management"
  hidden: true
---

Hugo 블로그를 목적별로 3개 운영하고 있다.

1. **개발 블로그** — 개발 삽질 기록, 기술 문서 (이 블로그)
2. **[앱명] 홈페이지** — 앱 소개 + 업데이트 블로그, 다국어(ko/en)
3. **개인 블로그** — 비개발 글

각각 역할이 달라서 분리했지만, 관리는 한 곳에서 하고 싶었다. 처음엔 별도 저장소로 나눴다가 결국 단일 디렉토리 아래 모아두는 구조로 정착했다. 이 글은 그 구조와 각 블로그의 설정 방식을 정리한 것이다.

---

## 왜 Hugo인가

정적 사이트 생성기 중 Hugo를 선택한 이유는 단순하다. **빠르다**. 수백 개의 포스트도 1초 내에 빌드된다. Go 바이너리 하나로 동작하기 때문에 의존성 관리 부담도 없다. Node.js 기반 도구처럼 `node_modules`가 수백 MB씩 쌓이지 않는다.

다른 장점은:

- **테마 생태계**: PaperMod, Stack, Blowfish 등 완성도 높은 무료 테마가 많다
- **다국어 내장**: 별도 플러그인 없이 `i18n` 폴더와 `hugo.toml` 설정만으로 다국어를 처리한다
- **Hugo Modules**: Go Modules 방식으로 테마를 관리해 버전 고정과 업데이트가 깔끔하다
- **Netlify 공식 지원**: `netlify.toml`에 Hugo 버전을 명시하면 빌드 환경이 보장된다

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

세 블로그가 같은 `~/domain/` 아래에 있지만 Hugo 프로젝트로서는 완전히 독립적이다. `hugo.toml`, `themes/`, `public/`이 각자 존재한다. 공유하는 파일은 아무것도 없다.

이 구조의 장점은 **경계가 명확하다**는 것이다. 한 블로그의 Hugo 버전을 올려도 다른 블로그에 영향을 주지 않는다. 테마 설정을 바꿔도 마찬가지다.

---

## 테마 선택

### 개발 블로그: PaperMod

```toml
# hugo.toml
theme = 'PaperMod'
```

미니멀하고 빠르다. 코드 하이라이팅이 깔끔하고, 다크모드를 기본 지원한다. 검색, 아카이브, 목차 기능이 내장되어 있어서 추가 설정이 거의 필요 없다.

코드 블록 스타일 설정:

```toml
[markup.highlight]
style = "github-dark"
noClasses = false
```

`noClasses = false`로 설정하면 Hugo가 인라인 스타일 대신 CSS 클래스를 출력한다. 이렇게 해야 커스텀 CSS로 코드 블록 스타일을 덮어쓸 수 있다.

PaperMod는 git submodule로 관리한다. Hugo Modules보다 직관적이고, GitHub에서 서브모듈 상태를 바로 확인할 수 있다는 것이 장점이다.

```bash
# 처음 클론할 때
git clone --recurse-submodules https://github.com/username/seunghan-xyz

# 이미 클론된 상태에서 submodule 초기화
git submodule update --init --recursive
```

### 앱 블로그: Hugo Stack v3

```toml
# hugo.toml
[module]
  [[module.imports]]
    path = "github.com/CaiJimmy/hugo-theme-stack/v3"
```

카드형 레이아웃. 앱 소개 페이지처럼 시각적 요소가 많을 때 어울린다. Hugo Modules로 설치해서 업데이트가 쉽다:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

Hugo Modules를 사용하면 `go.mod`와 `go.sum` 파일이 생성된다. 이 파일들이 테마 버전을 고정한다. `hugo mod get -u` 명령으로 최신 버전으로 올리고, `hugo mod tidy`로 불필요한 의존성을 정리한다.

### 테마 설치 방식 비교

| 방식 | 장점 | 단점 |
|------|------|------|
| git submodule | 직관적, GitHub에서 상태 확인 가능 | 클론 시 `--recurse-submodules` 필요 |
| Hugo Modules | 버전 고정 명확, 업데이트 간단 | `go.mod` 파일 관리 필요, Go 설치 필요 |
| 테마 직접 복사 | 가장 단순 | 업데이트 불편, 변경 추적 어려움 |

---

## 다국어 설정 (앱 블로그)

앱 스토어 심사에서 앱 홈페이지 URL을 요구할 때 영문 페이지도 필요하다. Apple App Store 심사 가이드라인은 앱 지원 URL과 마케팅 URL을 요구하는데, 영문 심사를 받을 경우 영문 페이지가 없으면 반려될 수 있다.

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

i18n 문자열은 `i18n/` 폴더에서 관리한다:

```yaml
# i18n/ko.yaml
- id: home
  translation: "홈"

- id: readMore
  translation: "더 보기"
```

```yaml
# i18n/en.yaml
- id: home
  translation: "Home"

- id: readMore
  translation: "Read More"
```

번역이 없는 페이지는 기본 언어(ko)로 폴백된다. 완전한 번역보다 핵심 페이지만 영문화하는 게 현실적이다. 앱 설명 페이지, 개인정보처리방침, 이용약관 정도만 영문으로 준비해두면 심사 통과에 충분하다.

### URL 구조

다국어 설정 후 URL 구조가 바뀐다:

- 한국어: `https://example.com/posts/feature-update/`
- 영어: `https://example.com/en/posts/feature-update/`

`DefaultContentLanguage = "ko"`로 설정하면 한국어 페이지에는 언어 접두사가 붙지 않는다. 영어 페이지에만 `/en/` 접두사가 붙는다. 이 설정이 없으면 한국어 페이지도 `/ko/` 접두사를 갖게 되므로 기존 URL이 깨질 수 있다.

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

`HUGO_VERSION`을 명시하는 게 중요하다. 명시하지 않으면 Netlify가 오래된 Hugo 버전을 사용해 빌드가 실패하거나 예상과 다른 결과가 나온다. 현재 사용 중인 버전을 그대로 고정해두는 것이 안전하다.

`hugo --minify` 플래그는 HTML, CSS, JS를 모두 압축한다. 용량을 줄이고 로딩 속도를 개선한다. 개발 중에는 minify 없이 빌드해서 결과물을 확인하고, 배포 시에만 적용된다.

### 자동 배포 (GitHub 연동)

GitHub 저장소와 Netlify를 연결하면 `main` 브랜치 push시 자동 빌드. 설정 방법:

1. Netlify 대시보드 → "Add new site" → "Import an existing project"
2. GitHub 저장소 선택
3. Build settings: `hugo --minify`, Publish directory: `public`
4. `netlify.toml`이 있으면 자동으로 읽어들인다

주의: `netlify.toml`의 설정과 Netlify 대시보드의 설정이 충돌하면 `netlify.toml`이 우선한다.

### 수동 배포 (개발 블로그)

```bash
cd ~/domain/seunghan-xyz
hugo && netlify deploy --prod \
  --dir ~/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

`--dir`에 **절대경로** 필수. 상대경로 쓰면 현재 작업 디렉토리 기준으로 배포되어 엉뚱한 파일이 올라간다. 이걸 한 번 실수하면 빈 디렉토리나 다른 프로젝트의 파일이 배포된다.

`SITE_ID`는 Netlify 대시보드의 "Site settings" → "Site details"에서 확인할 수 있다. 또는 `.netlify/state.json` 파일에 저장되어 있다.

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

`-D` 플래그는 `draft: true`인 포스트도 포함해서 미리보기 서버를 띄운다. 작성 중인 글을 확인할 때 유용하다. 배포 시에는 이 플래그 없이 `hugo` 명령만 실행하면 draft가 제외된다.

`hugo server`는 파일 변경을 감지하고 자동으로 브라우저를 새로고침(LiveReload)한다. 포스트를 작성하면서 결과를 실시간으로 확인할 수 있다.

---

## 포스트 작성 패턴

### Front Matter 템플릿

```markdown
---
title: "제목"
date: 2025-10-08
draft: false
tags: ["태그1", "태그2"]
description: "SEO용 한 줄 설명"
---
```

`draft: true`로 작성해두고 완성되면 `false`로 바꾼다. 초안이 실수로 배포되는 걸 막을 수 있다.

`description`은 검색 결과에 표시되는 메타 설명이다. 120~160자 안에 핵심 내용을 담는다. 비워두면 Hugo가 본문 앞부분을 잘라서 사용하는데, 문맥이 이상하게 잘릴 수 있으므로 직접 작성하는 게 낫다.

### 파일명 규칙

```
posts/flutter-testflight-makefile-automation.md
posts/rails-dart-api-integration.md
posts/hugo-blog-multi-site-management.md
```

모두 소문자, 하이픈 구분. URL이 그대로 파일명이 된다.

URL이 파일명과 동일하게 유지되므로 SEO 측면에서도 일관성이 있다. 나중에 파일명을 바꾸면 URL이 바뀌어 기존 링크가 깨지므로 처음에 신중하게 정하는 게 좋다.

### OG 이미지

소셜 공유 시 표시되는 이미지는 front matter의 `cover.image`로 지정한다:

```markdown
cover:
  image: "/images/og/hugo-blog-multi-site-management.png"
  alt: "Hugo Blog Multi Site Management"
  hidden: true
```

`hidden: true`는 본문에는 이미지를 표시하지 않고 OG 태그에만 사용하겠다는 설정이다. 포스트 상단에 커버 이미지가 자동으로 출력되는 것을 막는다.

---

## 테마 업데이트

### PaperMod (git submodule)

```bash
cd ~/domain/seunghan-xyz
git submodule update --remote --merge
git add themes/PaperMod
git commit -m "chore: update PaperMod theme"
```

`--remote` 플래그는 서브모듈의 원격 저장소에서 최신 커밋을 가져온다. `--merge`는 로컬 변경사항이 있을 경우 병합한다. 테마를 직접 수정하지 않았다면 충돌 없이 업데이트된다.

### Stack v3 (Hugo Modules)

```bash
cd ~/domain/blogs/blog_richdada/[앱명]-blog
hugo mod get -u
hugo mod tidy
```

`hugo mod get -u`는 모든 모듈을 최신 버전으로 업데이트한다. 특정 모듈만 업데이트하려면 경로를 지정한다:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

업데이트 후 로컬에서 반드시 확인한다. 테마 메이저 버전 업데이트 시 레이아웃이나 설정 방식이 바뀔 수 있다.

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

`enableRobotsTXT = true`로 설정하면 Hugo가 자동으로 `robots.txt`를 생성한다. 검색 엔진 크롤러가 이 파일을 읽어 사이트 구조를 파악한다. 기본 설정은 모든 크롤러를 허용한다.

### Sitemap

Hugo는 기본적으로 `sitemap.xml`을 생성한다. Google Search Console에 이 URL을 등록해두면 새 포스트가 더 빠르게 색인된다:

```
https://seunghan.xyz/sitemap.xml
```

sitemap 생성 설정을 커스터마이즈할 수 있다:

```toml
[sitemap]
  changefreq = "weekly"
  priority = 0.5
  filename = "sitemap.xml"
```

### Canonical URL

같은 콘텐츠가 여러 URL에서 접근 가능한 경우 canonical URL을 지정해야 중복 콘텐츠 패널티를 피할 수 있다. Hugo는 기본적으로 각 페이지에 canonical 태그를 추가한다. `baseURL`이 올바르게 설정되어 있는지 확인한다:

```toml
baseURL = "https://seunghan.xyz/"
```

---

## 실제 운영에서 겪은 문제들

### 1. git add를 잊으면 배포가 안 된다

`content/` 아래에 파일을 만들고 `git add` 없이 커밋하면 GitHub에 올라가지 않는다. Netlify 자동 배포는 GitHub 저장소 기준으로 동작하므로 로컬에서 파일이 존재해도 배포에 반영되지 않는다.

```bash
# 항상 확인하는 습관
git status
git add .
git commit -m "post: add new article"
git push
```

### 2. Hugo 버전 불일치

로컬에서 잘 빌드되던 게 Netlify에서 실패하는 경우, `netlify.toml`의 `HUGO_VERSION`이 로컬 버전과 다를 때 발생한다.

```bash
# 로컬 버전 확인
hugo version
```

출력된 버전을 `netlify.toml`에 그대로 적는다.

### 3. 수동 배포 시 상대경로 실수

```bash
# 잘못된 예
netlify deploy --prod --dir public

# 올바른 예
netlify deploy --prod --dir ~/domain/seunghan-xyz/public
```

현재 디렉토리가 `~/domain/seunghan-xyz/`가 아닌 상태에서 상대경로를 쓰면 다른 곳의 `public/` 폴더가 배포된다.

---

## 정리

| 용도 | 테마 | 배포 방식 | 특이사항 |
|------|------|----------|---------|
| 개발 블로그 | PaperMod | Netlify CLI (수동) | 이 블로그 |
| 앱 홈페이지 | Stack v3 | Netlify (자동, GitHub 연동) | ko/en 다국어 |
| 개인 블로그 | Stack v3 | Netlify (자동, GitHub 연동) | — |

세 블로그가 서로 독립적으로 빌드/배포된다. 공통 설정을 공유하고 싶은 욕심이 있었지만, 각각 Hugo 버전도 다르고 요구사항도 달라서 그냥 독립적으로 두는 게 낫다는 결론이다.

---

## Key Takeaways

- **단일 디렉토리, 독립 Hugo 프로젝트**: 파일 시스템상 한 곳에 두되, Hugo 프로젝트 경계는 명확히 분리한다
- **테마 방식은 목적에 맞게**: 기술 블로그는 PaperMod(git submodule), 시각적 콘텐츠는 Stack(Hugo Modules)
- **netlify.toml에 Hugo 버전 고정**: 빌드 재현성의 핵심, 버전 명시 없이는 환경이 보장되지 않는다
- **수동 배포 시 절대경로**: `--dir`에 상대경로를 쓰면 잘못된 파일이 배포된다
- **draft 워크플로우**: `draft: true`로 시작해서 완성 후 `false`로 전환, 실수 배포 방지
- **다국어는 핵심 페이지만**: 앱 심사 통과를 위한 최소 영문화(설명, 법적 페이지)로도 충분하다
- **git add 확인 습관**: 파일 생성 후 `git status`로 반드시 확인, untracked 파일은 배포되지 않는다
