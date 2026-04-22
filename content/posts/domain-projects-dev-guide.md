---
title: "멀티 도메인 정적 사이트 운영 개발 가이드"
date: 2025-09-13
draft: false
tags: ["Hugo", "Netlify", "Static Site", "DevOps", "Deployment"]
categories: ["DevOps"]
description: "Hugo + Netlify 기반 멀티 사이트 정적 호스팅 아키텍처와 배포 워크플로우 정리"
cover:
  image: "/images/og/domain-projects-dev-guide.png"
  alt: "Domain Projects Dev Guide"
  hidden: true
---

## 개요

여러 개의 정적 사이트(랜딩 페이지 + 블로그)를 단일 디렉토리에서 관리하는 구조와 배포 워크플로우를 정리한 문서입니다. 개인 블로그, 앱별 랜딩 페이지, 다국어 블로그 등 성격이 다른 여러 사이트를 운영할 때 발생하는 실무적인 문제들과 그 해결책을 다룹니다.

정적 사이트는 서버 부담이 없고, 배포가 빠르며, CDN 캐싱 효율이 높아 소규모 개인 프로젝트와 앱 마케팅 페이지에 이상적입니다. 그러나 여러 사이트를 동시에 운영하면 배포 방식이 사이트마다 달라져 혼란이 생기기 쉽습니다. 이 가이드는 각 사이트 유형별 배포 전략을 명확히 구분하고, 반복 작업을 자동화하는 방법을 설명합니다.

---

## 디렉토리 구조

```
~/domain/
├── dcode/
│   └── landing/          # Static HTML 랜딩 페이지 모음
│       ├── index.html    # 메인 페이지
│       ├── app-a/        # 앱별 서브 디렉토리
│       │   ├── index.html
│       │   ├── privacy/
│       │   └── terms/
│       ├── app-b/
│       └── Makefile
│
├── seunghan-xyz/         # 개인 블로그 (Hugo)
│   ├── content/
│   │   ├── posts/        # 기술 블로그 포스트
│   │   ├── projects/     # 프로젝트 소개
│   │   └── about/
│   ├── hugo.toml
│   └── public/           # 빌드 결과물 (git 제외)
│
└── blogs/
    └── blog_richdada/    # Hugo 블로그 컬렉션
        ├── site-a/       # 사이트 A (한국어/영어)
        └── site-b/       # 사이트 B
```

### 구조 설계 원칙

이 디렉토리 구조는 세 가지 원칙을 따릅니다.

**역할 분리**: `dcode/landing`은 앱 마케팅 페이지 전용입니다. Hugo가 필요 없는 단순한 HTML 파일로 구성되어 있어 디자이너나 외부 협업자도 쉽게 편집할 수 있습니다. `seunghan-xyz`는 기술 블로그로 Hugo의 마크다운 파이프라인을 활용합니다.

**독립적인 Git 저장소**: 각 사이트는 별도 Git 저장소로 관리됩니다. 블로그 포스트 하나를 추가할 때 랜딩 페이지 이력이 오염되지 않습니다. 충돌 없이 각 사이트를 독립적으로 버전 관리할 수 있습니다.

**배포 전략 명시화**: 사이트마다 배포 전략이 다릅니다. 어느 사이트가 자동 배포이고 어느 사이트가 수동 배포인지 디렉토리 구조와 Makefile로 명확하게 표현합니다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 개인 블로그 | Hugo + PaperMod Theme |
| 앱 블로그 | Hugo + Stack Theme v3 |
| 랜딩 페이지 | Static HTML + Tailwind CSS (CDN) |
| 호스팅 | Netlify |
| 도메인 관리 | Namecheap |

### Hugo를 선택한 이유

Hugo는 Go로 작성된 정적 사이트 생성기로, 빌드 속도가 경쟁 도구 중 가장 빠릅니다. 수백 개의 마크다운 파일을 수 초 안에 HTML로 변환합니다. 별도 런타임이 필요 없고, 단일 바이너리로 동작하기 때문에 로컬 환경 설정이 간단합니다.

PaperMod 테마는 SEO 친화적이며, 다크 모드, 검색 기능, 소셜 공유 메타태그를 기본 제공합니다. Stack 테마는 사이드바 레이아웃과 카테고리 아카이브 기능이 강점으로, 콘텐츠가 많은 앱 블로그에 적합합니다.

### Netlify를 선택한 이유

Netlify는 정적 사이트 호스팅에 최적화된 플랫폼입니다. GitHub 연동 자동 배포, 글로벌 CDN, HTTPS 자동 발급, 미리보기 URL(preview deploy) 등 소규모 프로젝트에 필요한 기능을 무료 티어에서 모두 제공합니다. CLI 도구(`netlify-cli`)가 성숙해서 스크립트 기반 자동화도 용이합니다.

---

## 배포 방법

### 1. 개인 블로그 (Hugo → Netlify CLI)

빌드 후 Netlify CLI로 직접 배포합니다. GitHub push는 자동 배포와 연결되어 있지 **않습니다.**

```bash
cd ~/domain/seunghan-xyz

# Hugo 빌드
hugo

# Netlify 배포 (절대 경로 필수)
netlify deploy --prod \
  --dir /Users/[username]/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

> ⚠️ `--dir .` 또는 `--dir public` 같은 상대 경로는 실행 위치에 따라 엉뚱한 디렉토리가 배포될 수 있음. **절대 경로 사용 필수.**

개인 블로그는 GitHub 연동 자동 배포를 의도적으로 끊어놨습니다. 작성 중인 포스트가 실수로 배포되는 것을 방지하고, 빌드 결과물(`public/`)을 로컬에서 먼저 확인한 후 배포하는 워크플로우를 유지하기 위해서입니다. `public/` 디렉토리는 `.gitignore`에 포함되므로 Git 이력을 깔끔하게 유지할 수 있습니다.

### 2. 랜딩 페이지 (Static HTML → Netlify CLI)

```bash
cd ~/domain/dcode/landing

# Makefile 사용
make deploy

# 또는 직접 실행
netlify deploy --prod \
  --dir /Users/[username]/domain/dcode/landing \
  --site [SITE_ID]
```

`Makefile` 내용:
```makefile
NETLIFY_SITE_ID = [SITE_ID]

deploy:
	netlify deploy --prod --dir . --site $(NETLIFY_SITE_ID)
```

Makefile을 사용하면 사이트 ID를 매번 입력하지 않아도 됩니다. `make deploy` 한 줄로 배포가 완료됩니다. 팀원이 추가될 경우 배포 방법을 별도로 안내할 필요 없이 `make deploy` 명령만 전달하면 됩니다.

### 3. Hugo 블로그 (Netlify 자동 배포)

블로그 사이트들은 GitHub main 브랜치에 push하면 Netlify가 자동으로 빌드+배포합니다.

```bash
cd ~/domain/blogs/blog_richdada/site-a

# 개발 서버
hugo server -D

# 프로덕션 빌드 (확인용)
hugo --minify

# GitHub에 push → 자동 배포
git add . && git commit -m "update" && git push origin main
```

`netlify.toml`로 빌드 설정을 코드로 관리합니다:

```toml
[build]
  command = "hugo --minify"
  publish = "public"

[build.environment]
  HUGO_VERSION = "0.148.1"
```

Hugo 버전을 `netlify.toml`에 고정하면 Netlify 서버의 Hugo 버전 업데이트로 인한 빌드 깨짐을 방지할 수 있습니다. 실제로 Hugo 0.120 이후 버전에서 일부 테마의 템플릿 문법이 변경되어 빌드 오류가 발생한 사례가 있습니다.

---

## 로컬 개발

### 개인 블로그 개발 서버

```bash
cd ~/domain/seunghan-xyz
hugo server -D       # 드래프트 포함
# → http://localhost:1313
```

`-D` 플래그는 `draft: true`인 포스트도 로컬에서 렌더링합니다. 작성 중인 글을 미리 확인할 때 유용합니다. 배포 시에는 Hugo가 draft 포스트를 자동으로 제외하므로 별도로 신경 쓰지 않아도 됩니다.

### Hugo 블로그 개발 서버

```bash
cd ~/domain/blogs/blog_richdada/site-a
hugo server -D
# → http://localhost:1313

# 멀티 언어 확인
hugo server --baseURL http://localhost:1313
```

다국어 사이트에서 `--baseURL`을 지정하지 않으면 언어 전환 링크가 잘못된 URL을 가리킬 수 있습니다. 한국어/영어 양쪽을 동시에 개발할 때는 `--baseURL` 옵션을 명시하는 것이 좋습니다.

### 랜딩 페이지 로컬 확인

별도 빌드 없이 브라우저에서 `index.html` 직접 열기, 또는 간단한 로컬 서버 사용:

```bash
cd ~/domain/dcode/landing
python3 -m http.server 8080
# → http://localhost:8080
```

`file://` 프로토콜로 직접 열면 일부 상대 경로 참조나 fetch API 호출이 CORS 오류로 실패합니다. 로컬 서버를 사용하면 이런 문제를 방지할 수 있습니다.

---

## 콘텐츠 작성

### 블로그 포스트 추가 (seunghan-xyz)

```bash
cd ~/domain/seunghan-xyz
hugo new posts/my-new-post.md
```

생성되는 프론트매터:
```yaml
---
title: "Post Title"
date: 2025-09-13
draft: true          # 배포 시 false로 변경
tags: ["tag1"]
categories: ["Dev"]
description: "설명"
---
```

프론트매터의 `description` 필드는 SEO에 직접 영향을 줍니다. 검색 결과 미리보기에 표시되므로 120~160자 내외로 핵심 내용을 담는 것이 좋습니다. `tags`와 `categories`는 Hugo의 분류(taxonomy) 시스템에 연결되어 자동으로 목록 페이지를 생성합니다.

### 다국어 포스트 작성

한국어 포스트와 영어 포스트를 쌍으로 관리할 때는 파일명 규칙을 통일합니다:

```
posts/
├── my-post.md        # 한국어 (기본 언어)
└── my-post.en.md     # 영어
```

Hugo의 다국어 설정(`hugo.toml`)에서 기본 언어를 한국어로 지정하면 `.md` 파일이 한국어 버전, `.en.md`가 영어 버전으로 처리됩니다. 양쪽 파일의 프론트매터 `date`와 파일명 기반 경로는 동일하게 유지해야 언어 전환 링크가 정상 동작합니다.

### 랜딩 페이지 앱 추가

새 앱 디렉토리를 생성하고 기존 구조를 복사합니다:

```
app-new/
├── index.html      # 메인 랜딩
├── app_icon.png    # 앱 아이콘 (1024x1024)
├── privacy/
│   └── index.html  # 개인정보처리방침
└── terms/
    └── index.html  # 이용약관
```

앱 스토어 제출 시 개인정보처리방침(`/privacy/`)과 이용약관(`/terms/`) URL이 필수입니다. Netlify에서는 별도 설정 없이 `privacy/index.html`이 `/privacy/` URL로 서빙됩니다.

---

## 도메인 & 배포 현황

| 사이트 | 배포 방식 | 자동배포 |
|--------|----------|---------|
| 개인 블로그 | Netlify CLI (수동) | ❌ |
| 랜딩 페이지 | Netlify CLI / make deploy | ❌ |
| 앱 블로그 A | Netlify (GitHub 연동) | ✅ |
| 앱 블로그 B | Netlify (GitHub 연동) | ✅ |

자동 배포와 수동 배포를 혼용하는 이유는 사이트의 성격에 따라 배포 안정성 요구사항이 다르기 때문입니다. 자주 업데이트되는 블로그는 push-to-deploy 자동화가 편리합니다. 반면 개인 블로그나 랜딩 페이지는 빌드 결과물을 먼저 로컬에서 검토한 후 의도적으로 배포하는 것이 실수를 줄입니다.

---

## 자주 쓰는 명령어 모음

```bash
# 개인 블로그 빌드 + 배포 (한 번에)
cd ~/domain/seunghan-xyz && hugo && \
  netlify deploy --prod \
  --dir /Users/[username]/domain/seunghan-xyz/public \
  --site [SITE_ID]

# 랜딩 페이지 배포
cd ~/domain/dcode/landing && make deploy

# 전체 Git 상태 확인
for dir in seunghan-xyz dcode/landing; do
  echo "=== $dir ===" && cd ~/domain/$dir && git status --short && cd ~/domain
done

# Hugo 버전 확인
hugo version

# Netlify CLI 로그인 상태 확인
netlify status

# 새 포스트 생성 후 즉시 서버 시작
cd ~/domain/seunghan-xyz && \
  hugo new posts/new-post.md && \
  hugo server -D
```

---

## 트러블슈팅

### 배포 후 변경 사항이 반영되지 않는 경우

Netlify CDN 캐시가 남아있을 수 있습니다. Netlify 대시보드에서 "Clear cache and retry deploy"를 실행하거나, 다음 명령으로 강제 재배포합니다:

```bash
netlify deploy --prod --dir [absolute-path] --site [SITE_ID]
```

브라우저 측 캐시 문제라면 강제 새로고침(`Cmd+Shift+R` / `Ctrl+Shift+R`)을 시도합니다.

### Hugo 빌드 오류: 템플릿 파싱 실패

Hugo 버전 업데이트 후 일부 테마에서 `execute of template failed` 오류가 발생할 수 있습니다. `netlify.toml`의 `HUGO_VERSION`을 기존에 정상 동작하던 버전으로 고정하고, 테마 저장소에서 업데이트된 버전을 확인합니다:

```toml
[build.environment]
  HUGO_VERSION = "0.136.5"  # 안정 버전으로 고정
```

### Git push 후 Netlify 자동 배포가 트리거되지 않는 경우

Netlify 대시보드의 "Site configuration > Build & deploy > Continuous deployment"에서 GitHub 연동 상태를 확인합니다. GitHub App 권한이 만료되거나 저장소 접근 권한이 변경된 경우 재연동이 필요합니다.

---

## 주의사항

1. **절대 경로 사용** — Netlify CLI `--dir` 옵션은 항상 절대 경로로 지정
2. **GitHub push ≠ 배포** — 개인 블로그와 랜딩 페이지는 GitHub push와 자동 배포 미연결, CLI 수동 배포 필요
3. **Hugo public/ 디렉토리** — `.gitignore`에 포함되어 있으므로 빌드 후 배포 전 존재 여부 확인
4. **다국어 Hugo 사이트** — `hugo server` 시 `DefaultContentLanguage` 확인, 루트 URL 리다이렉션 설정 필요할 수 있음
5. **Tailwind CSS CDN** — 랜딩 페이지는 CDN 방식이라 별도 빌드 과정 없음, 인터넷 연결 필요
6. **파일 추적 확인** — 새 파일 생성 후 `git add`를 빠뜨리면 GitHub에 올라가지 않아 자동 배포에서 누락됨

---

## Key Takeaways

- **사이트 유형별 배포 전략을 분리하라**: 자동 배포는 편리하지만 모든 사이트에 적용이 정답은 아니다. 검토가 필요한 사이트는 수동 배포 워크플로우를 의도적으로 유지하는 것이 실수를 줄인다.
- **절대 경로 규칙을 지켜라**: Netlify CLI의 `--dir` 옵션에서 상대 경로 사용은 실행 위치에 따라 의도치 않은 디렉토리를 배포하는 치명적 실수로 이어진다.
- **Hugo 버전을 코드로 고정하라**: `netlify.toml`에 `HUGO_VERSION`을 명시하면 플랫폼 업데이트로 인한 빌드 깨짐을 예방한다.
- **Makefile로 반복 작업을 줄여라**: 복잡한 CLI 명령은 Makefile 타겟으로 감싸면 팀 전체의 배포 명령을 단순화할 수 있다.
- **`public/`은 Git에서 제외하라**: 빌드 결과물을 Git으로 추적하면 이력이 오염되고 저장소 크기가 불필요하게 커진다. Netlify가 빌드를 담당하게 하거나 CLI로 직접 업로드한다.

---

## 참고

- [Hugo 공식 문서](https://gohugo.io/documentation/)
- [PaperMod 테마](https://github.com/adityatelange/hugo-PaperMod)
- [Hugo Stack 테마](https://github.com/CaiJimmy/hugo-theme-stack)
- [Netlify CLI 문서](https://docs.netlify.com/cli/get-started/)
