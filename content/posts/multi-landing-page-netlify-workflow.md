---
title: "앱 랜딩 페이지 8개를 하나의 저장소로 관리하는 법"
date: 2025-10-11
draft: false
tags: ["Netlify", "TailwindCSS", "정적사이트", "배포", "랜딩페이지", "워크플로우"]
description: "빌드 도구 없이 Pure HTML + Tailwind CDN으로 여러 앱의 랜딩 페이지를 단일 저장소에서 운영하고, Netlify CLI로 배포하는 실전 구조"
cover:
  image: "/images/og/multi-landing-page-netlify-workflow.png"
  alt: "Multi Landing Page Netlify Workflow"
  hidden: true
---

앱을 여러 개 만들다 보면 각각 랜딩 페이지가 필요해진다.
별도 저장소를 8개 만드는 건 관리 비용이 너무 크고, 하나로 묶으면 배포가 복잡해진다.
결국 단일 저장소 + Netlify 개별 사이트 전략으로 정착했다.

---

## 디렉토리 구조

```
landing/
├── index.html          # 회사 메인 페이지
├── [서비스-A]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [서비스-B]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [서비스-C]/
│   └── index.html
│ ...
└── Makefile
```

각 서비스는 독립 디렉토리. `privacy/`와 `terms/` 하위 페이지는 App Store / Google Play 심사 제출용으로 필수다.

---

## 기술 스택 선택 이유

### Pure HTML + Tailwind CDN

빌드 프로세스가 없다. `npm install`, `node_modules`, `package.json` 아무것도 없다.

```html
<script src="https://cdn.tailwindcss.com"></script>
```

랜딩 페이지는 기능이 단순하다. 스크롤 애니메이션, CTA 버튼, 스크린샷 몇 장.
이 정도에 webpack/vite 설정을 넣는 건 오버엔지니어링이다.

단점은 CSS 번들 크기 최적화가 불가능하다는 것. 하지만 CDN에서 내려오는 Tailwind는 브라우저 캐시에 올라가고, 페이지 자체 크기는 작아서 실제로 문제가 된 적이 없다.

### 각 페이지별 디자인 시스템

앱 성격에 맞게 다른 디자인을 적용했다:

| 서비스 유형 | 스타일 | 주요 색상 |
|------------|--------|----------|
| 회사 메인 | Trust & Authority | Black + Gold |
| 운세/엔터테인먼트 | Glassmorphism | Blue + Orange |
| 필름/레트로 | Motion-Driven | Black + White |
| 여행/라이프스타일 | Soft UI | Sky Blue + Orange |
| AI 서비스 | Tech Minimal | Gray + Accent |
| 부동산/문서 | Clean Professional | Navy + White |

같은 Tailwind를 쓰지만 컬러 팔레트와 컴포넌트 스타일이 다르면 전혀 다른 느낌이 난다.

---

## Netlify 배포 구조

각 서비스마다 Netlify 사이트를 하나씩 만든다. 저장소는 하나지만 배포는 독립적이다.

### Makefile

```makefile
NETLIFY := netlify
BASE := /Users/$(USER)/domain/[회사명]/landing

deploy-main:
	$(NETLIFY) deploy --prod \
		--dir $(BASE) \
		--site [SITE_ID_MAIN]

deploy-service-a:
	$(NETLIFY) deploy --prod \
		--dir $(BASE)/[서비스-A] \
		--site [SITE_ID_A]

deploy-service-b:
	$(NETLIFY) deploy --prod \
		--dir $(BASE)/[서비스-B] \
		--site [SITE_ID_B]

deploy-all:
	$(MAKE) deploy-main
	$(MAKE) deploy-service-a
	$(MAKE) deploy-service-b
```

`--dir`에 절대경로를 쓰는 게 중요하다. 상대경로(`--dir .`)를 쓰면 어디서 `make`를 실행하느냐에 따라 엉뚱한 디렉토리가 배포된다. 한 번 겪으면 절대경로 습관이 생긴다.

### Netlify CLI 설치

```bash
npm install -g netlify-cli
netlify login
```

처음 사이트를 만들 때는 Netlify 대시보드에서 수동으로 사이트를 생성하고 Site ID를 얻는다. 이후엔 `make deploy-*` 명령어 하나로 끝.

---

## 실제 배포 흐름

랜딩 페이지 하나를 수정하면:

```bash
# 1. HTML 수정
vim landing/[서비스-A]/index.html

# 2. 해당 사이트만 배포
make deploy-service-a

# 3. 확인
# → https://[서비스-a].netlify.app
```

전체 배포가 필요하면:
```bash
make deploy-all
```

평균 배포 시간은 10–15초. 빌드 과정이 없어서 빠르다.

---

## 커스텀 도메인 연결

Netlify 대시보드에서 각 사이트에 커스텀 도메인을 연결한다.

```
회사 메인      → [company-domain].com
서비스 A      → [서비스-A].[company-domain].com (서브도메인)
서비스 B      → 별도 도메인
```

DNS 설정:
```
A     @    75.2.60.5        (Netlify Load Balancer)
CNAME www  [netlify-site].netlify.app
```

SSL 인증서는 Netlify가 Let's Encrypt로 자동 발급. 도메인 연결 후 24시간 이내에 HTTPS가 된다.

---

## 유지보수 패턴

### 공통 컴포넌트 없이 운영하는 이유

헤더, 푸터를 공통화하고 싶은 유혹이 있지만 하지 않았다. 각 페이지가 독립적이고, 디자인이 다르고, 배포 시점도 다르다. 공통 컴포넌트를 만들면 하나를 바꿀 때 전체를 확인해야 한다.

"DRY 원칙을 지키자"는 생각이 오히려 복잡도를 높일 수 있다. 랜딩 페이지처럼 변경이 드문 정적 파일은 복붙이 낫다.

### 법적 페이지 관리

App Store / Google Play 심사에서 Privacy Policy와 Terms of Service URL을 요구한다.

```
[서비스-A]/
├── index.html
├── privacy/
│   └── index.html    # https://[domain]/[서비스-A]/privacy/
└── terms/
    └── index.html    # https://[domain]/[서비스-A]/terms/
```

각 페이지는 앱 특성에 맞게 내용이 다르다. 데이터 수집 항목, 제3자 SDK 목록이 서비스마다 다르기 때문.

---

## 배포 전 체크리스트

```
□ 스크린샷 최신 버전으로 교체
□ App Store / Play Store 링크 활성 여부 확인
□ 연락처 이메일 정확한지 확인
□ Privacy / Terms 페이지 접근 가능한지 확인
□ 모바일 반응형 확인 (375px 기준)
□ meta description, og:image 설정 확인
```

---

## 정리

- **저장소 1개**, **Netlify 사이트 N개** 구조가 관리 효율이 좋다
- **Pure HTML + Tailwind CDN**: 빌드 없이 즉시 배포 가능
- **Makefile**: `make deploy-[서비스명]` 한 줄로 배포
- **절대경로 필수**: `--dir` 옵션엔 항상 절대경로
- **독립 배포**: 각 서비스가 서로 영향 없이 배포됨

앱이 늘어나도 디렉토리 하나 추가하고 Makefile에 target 하나 추가하면 끝이다.
