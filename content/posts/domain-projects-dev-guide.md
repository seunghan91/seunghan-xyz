---
title: "멀티 도메인 정적 사이트 운영 개발 가이드"
date: 2025-09-13
draft: false
tags: ["Hugo", "Netlify", "Static Site", "DevOps", "Deployment"]
categories: ["Dev Guide"]
description: "Hugo + Netlify 기반 멀티 사이트 정적 호스팅 아키텍처와 배포 워크플로우 정리"
cover:
  image: "/images/og/domain-projects-dev-guide.png"
  alt: "Domain Projects Dev Guide"
  hidden: true
---

## 개요

여러 개의 정적 사이트(랜딩 페이지 + 블로그)를 단일 디렉토리에서 관리하는 구조와 배포 워크플로우를 정리한 문서입니다.

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

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 개인 블로그 | Hugo + PaperMod Theme |
| 앱 블로그 | Hugo + Stack Theme v3 |
| 랜딩 페이지 | Static HTML + Tailwind CSS (CDN) |
| 호스팅 | Netlify |
| 도메인 관리 | Namecheap |

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

---

## 로컬 개발

### 개인 블로그 개발 서버

```bash
cd ~/domain/seunghan-xyz
hugo server -D       # 드래프트 포함
# → http://localhost:1313
```

### Hugo 블로그 개발 서버

```bash
cd ~/domain/blogs/blog_richdada/site-a
hugo server -D
# → http://localhost:1313

# 멀티 언어 확인
hugo server --baseURL http://localhost:1313
```

### 랜딩 페이지 로컬 확인

별도 빌드 없이 브라우저에서 `index.html` 직접 열기, 또는 간단한 로컬 서버 사용:

```bash
cd ~/domain/dcode/landing
python3 -m http.server 8080
# → http://localhost:8080
```

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

---

## 도메인 & 배포 현황

| 사이트 | 배포 방식 | 자동배포 |
|--------|----------|---------|
| 개인 블로그 | Netlify CLI (수동) | ❌ |
| 랜딩 페이지 | Netlify CLI / make deploy | ❌ |
| 앱 블로그 A | Netlify (GitHub 연동) | ✅ |
| 앱 블로그 B | Netlify (GitHub 연동) | ✅ |

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
```

---

## 주의사항

1. **절대 경로 사용** — Netlify CLI `--dir` 옵션은 항상 절대 경로로 지정
2. **GitHub push ≠ 배포** — 개인 블로그와 랜딩 페이지는 GitHub push와 자동 배포 미연결, CLI 수동 배포 필요
3. **Hugo public/ 디렉토리** — `.gitignore`에 포함되어 있으므로 빌드 후 배포 전 존재 여부 확인
4. **다국어 Hugo 사이트** — `hugo server` 시 `DefaultContentLanguage` 확인, 루트 URL 리다이렉션 설정 필요할 수 있음
5. **Tailwind CSS CDN** — 랜딩 페이지는 CDN 방식이라 별도 빌드 과정 없음, 인터넷 연결 필요

---

## 참고

- [Hugo 공식 문서](https://gohugo.io/documentation/)
- [PaperMod 테마](https://github.com/adityatelange/hugo-PaperMod)
- [Hugo Stack 테마](https://github.com/CaiJimmy/hugo-theme-stack)
- [Netlify CLI 문서](https://docs.netlify.com/cli/get-started/)
