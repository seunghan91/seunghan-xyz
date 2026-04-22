---
title: "앱 랜딩 페이지 8개를 하나의 저장소로 관리하는 법"
date: 2025-10-11
draft: false
tags: ["Netlify", "TailwindCSS", "정적사이트", "배포", "랜딩페이지", "워크플로우"]
categories: ["Frontend", "DevOps"]
description: "빌드 도구 없이 Pure HTML + Tailwind CDN으로 여러 앱의 랜딩 페이지를 단일 저장소에서 운영하고, Netlify CLI로 배포하는 실전 구조"
cover:
  image: "/images/og/multi-landing-page-netlify-workflow.png"
  alt: "Multi Landing Page Netlify Workflow"
  hidden: true
---

앱을 여러 개 만들다 보면 각각 랜딩 페이지가 필요해진다. 저장소를 8개 따로 만들면 관리 비용이 8배가 된다. 반대로 하나로 완전히 묶으면 배포가 복잡해진다 — 어느 페이지 하나를 수정해도 전체가 재배포되고, 실수 하나가 전체를 망가뜨릴 수 있다.

두 극단 사이에서 찾은 구조가 **저장소 1개 + Netlify 사이트 N개**다. 코드 관리는 한 곳에서, 배포는 서비스별로 완전히 독립적으로. 이 글은 그 구조의 세부 사항, 각 결정의 이유, 그리고 규모가 커져도 유지보수할 수 있게 만드는 패턴들을 정리한 것이다.

---

## 디렉토리 구조

```
landing/
├── index.html          # 회사 메인 페이지
├── [서비스-A]/
│   ├── index.html
│   ├── privacy/
│   │   └── index.html
│   └── terms/
│       └── index.html
├── [서비스-B]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [서비스-C]/
│   └── index.html
│ ...
└── Makefile
```

각 서비스는 독립 디렉토리에 산다. `privacy/`와 `terms/` 하위 페이지는 선택 사항이 아니다 — App Store와 Google Play 모두 개인정보처리방침과 이용약관의 공개 URL이 있어야 심사를 통과시켜 준다.

구조가 평탄하고 예측 가능하기 때문에 어떤 개발자든 몇 초 만에 전체 레이아웃을 파악할 수 있다. 파싱해야 할 설정 파일도 없고, 프레임워크 지식도 필요 없다.

---

## 기술 스택 선택 이유

### Pure HTML + Tailwind CDN

빌드 의존성이 전혀 없다. `npm install`, `node_modules`, `package.json`, lockfile, 번들러 — 아무것도 없다.

```html
<script src="https://cdn.tailwindcss.com"></script>
```

랜딩 페이지의 기능 범위는 제한적이다: 히어로 섹션, 스크롤 애니메이션, CTA 버튼, 앱 스크린샷, 법적 페이지. 이 정도를 위해 webpack이나 Vite 파이프라인을 도입하는 건 오버엔지니어링이다. 빌드 설정을 유지 관리하는 인지 비용이 해결하려는 문제에 비해 정당화되지 않는다.

CDN 방식에는 실제 트레이드오프가 있다. 사용하지 않는 CSS 클래스를 제거(purge)할 수 없어서 전체 Tailwind 스타일시트(비압축 기준 약 350KB)가 매 방문마다 로드된다. 하지만 실제로 성능 문제가 된 적은 없다. CDN URL은 전 세계 모든 Tailwind 프로젝트에서 동일하기 때문에 방문자가 이전에 방문한 다른 사이트에서 이미 브라우저 캐시에 올라가 있는 경우가 대부분이다. 페이지 자체 HTML은 보통 20KB 미만이라 전체 페이로드는 충분히 수용 가능하다.

프로덕션급 성능 최적화가 필요하다면 Tailwind CLI + PurgeCSS로 전환하는 건 어렵지 않다. 하지만 상대적으로 트래픽이 적은 랜딩 페이지에서는 단순함 쪽이 낫다.

### 정적 사이트 생성기를 쓰지 않은 이유

Hugo, Eleventy, Astro 같은 도구들은 콘텐츠가 많은 사이트에 탁월한 선택이다. 하지만 빌드 단계가 생기고, 템플릿 언어를 배워야 하고, 의존성을 관리해야 한다. 여기서 각 랜딩 페이지는 콘텐츠만 다른 게 아니라 디자인 자체가 완전히 다르기 때문에 공유 템플릿이 주는 이점이 거의 없다. 페이지들은 데이터로부터 생성되는 게 아니라 각각 직접 제작된다.

판단 기준은 단순하다: 페이지들이 템플릿으로 묶을 만큼 충분한 구조를 공유한다면 생성기를 쓸 가치가 있다. 그렇지 않다면 순수 HTML이 이긴다.

### 각 페이지별 디자인 시스템

같은 Tailwind 유틸리티 클래스를 사용하면서도 각 서비스에 완전히 다른 시각적 정체성을 적용했다:

| 서비스 유형 | 스타일 | 주요 색상 |
|------------|--------|----------|
| 회사 메인 | Trust & Authority | Black + Gold |
| 운세/엔터테인먼트 | Glassmorphism | Blue + Orange |
| 필름/레트로 | Motion-Driven | Black + White |
| 여행/라이프스타일 | Soft UI | Sky Blue + Orange |
| AI 서비스 | Tech Minimal | Gray + Accent |
| 부동산/문서 | Clean Professional | Navy + White |

Glassmorphism — `backdrop-blur`, 반투명 `bg-white/10` 배경, 그라디언트 테두리 — 은 깔끔한 `bg-white` 전문가 레이아웃과 완전히 다른 느낌을 준다. 두 가지 모두 Tailwind로 작성됐는데도. 유틸리티 우선 접근법은 별도의 CSS 파일 없이 이런 발산적 디자인을 현실적으로 만들어 준다.

---

## Netlify 배포 구조

핵심 아키텍처는 저장소 하나를 여러 Netlify 사이트에 매핑하는 것이다. 각 사이트는 자체 Site ID, 자체 도메인, 자체 독립 배포 파이프라인을 가진다. 한 사이트의 변경이 다른 사이트에 영향을 줄 수 없다.

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

이 Makefile에서 설명이 필요한 설계 결정이 두 가지 있다.

**`--dir`에 절대경로를 쓰는 이유.** 이건 스타일 선호가 아니라 정확성 요구사항이다. `--dir` 플래그는 Netlify CLI에게 어떤 디렉토리를 업로드할지 알려준다. `--dir .`처럼 상대경로를 쓰면 `make`를 실행하는 작업 디렉토리에 따라 결과가 달라진다. 저장소 루트에서 실행하면 저장소 전체가 배포된다. 서비스 하위 디렉토리에서 실행하면 그 디렉토리만 배포된다. 다른 터미널 세션과 CI 환경에 걸쳐 동작이 예측 불가능하다. 절대경로를 쓰면 이 모호함이 완전히 사라진다. 한 번 이 실수를 겪으면 절대경로 습관이 생긴다.

**서비스별 Makefile 타겟을 명시적으로 쓰는 이유.** 루프나 함수로 DRY하게 만들 수도 있지만 하지 않았다. 명시성이 가치 있기 때문이다. 어떤 Site ID가 존재하는지, 어떤 서비스가 등록됐는지, 어떤 서비스가 자동화 파이프라인에 없는지를 한눈에 볼 수 있다. 새 서비스를 추가할 때 과정은 기계적이다: 디렉토리 추가, 타겟 추가, `deploy-all`에 추가.

### Netlify CLI 설치

```bash
npm install -g netlify-cli
netlify login
```

각 서비스의 첫 번째 사이트는 Netlify 대시보드에서 수동으로 생성해야 한다. 이건 의도적이다 — Netlify 대시보드는 도메인, 환경 변수, 팀 접근 권한을 설정하는 곳이다. Netlify API를 통한 사이트 생성 자동화도 가능하지만 일회성 작업에 복잡도를 더할 뿐이다. Site ID를 얻고 나면 이후의 모든 배포는 `make deploy-*` 한 줄로 끝난다.

---

## 실제 배포 흐름

랜딩 페이지 하나를 수정할 때:

```bash
# 1. HTML 수정
vim landing/[서비스-A]/index.html

# 2. 해당 사이트만 배포
make deploy-service-a

# 3. 확인
# → https://[서비스-a].netlify.app
```

여러 페이지를 동시에 배포해야 할 때:

```bash
make deploy-all
```

평균 배포 시간은 10–15초다. 컴파일도, 트랜스파일도, 에셋 해싱도 없다. CLI가 디렉토리 내용을 압축해서 Netlify CDN으로 직접 전송한다. 출력을 다 읽기 전에 사이트가 라이브 상태가 된다.

이 속도는 실전에서 의미 있다. App Store 심사자가 개인정보처리방침 URL이 404를 반환한다고 지적하거나 연락처 이메일이 잘못됐을 때, 1분 안에 수정을 반영할 수 있다.

---

## 커스텀 도메인 연결

각 Netlify 사이트에 독립적으로 커스텀 도메인을 연결할 수 있다:

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

SSL 인증서는 Netlify가 Let's Encrypt로 자동 발급한다. 도메인 연결 후 24시간 이내에 HTTPS가 된다 — 보통은 훨씬 빠르다. 인증서 갱신도 자동이라 만료 날짜를 추적할 필요가 없다.

서브도메인 패턴에서는 CNAME 방식이 IP 기반 A 레코드보다 깔끔하다. `[site-name].netlify.app`을 가리키는 CNAME을 추가하면 서브도메인에 대한 인증서 발급까지 Netlify가 처리한다.

---

## 유지보수 패턴

### 공통 컴포넌트 없이 운영하는 이유

헤더와 푸터를 공통화하고 싶은 유혹이 있다. 모든 페이지에 회사 이름과 연락처 이메일이 담긴 내비게이션과 푸터가 있다. DRY 원칙을 엄격하게 따르면 이걸 템플릿으로 중앙화해야 한다.

하지 않은 이유: 페이지들은 디자인이 다르고, 배포 시점이 다르고, 콘텐츠 요구사항도 다르다. 공통 푸터 템플릿은 하나를 바꿀 때 모든 페이지에 영향을 준다는 뜻이다. 거의 업데이트되지 않는 랜딩 페이지에서 이 결합은 이점을 제공하지 않고 위험만 더한다. 푸터 변경이 다른 일곱 페이지를 망가뜨리지 않았는지 확인하는 오버헤드는 HTML 몇 줄을 절약하는 것과 맞바꿀 가치가 없다.

YAGNI (You Aren't Gonna Need It) 원칙이 적용되는 경우다. 이 페이지들은 컴포넌트 라이브러리가 아니라 독립적인 마케팅 자산이다. 복붙이 올바른 도구다.

공통 템플릿을 도입할 기준점은 이렇게 생각하면 된다: "공유 콘텐츠가 한 달에 한 번 이상 여러 페이지에서 동시에 변경된다면." 그 조건이 충족된 적은 한 번도 없었다.

### 법적 페이지 관리

앱 배포 플랫폼들은 구체적인 URL 요구사항을 가지고 있다:

- Apple App Store: 실제 도메인에 호스팅된 URL 필요 (앱 심사 링크 불가)
- Google Play: 인증 없이 접근 가능한 URL 필요

```
[서비스-A]/
├── index.html
├── privacy/
│   └── index.html    # https://[domain]/[서비스-A]/privacy/
└── terms/
    └── index.html    # https://[domain]/[서비스-A]/terms/
```

각 법적 페이지의 내용은 단순한 템플릿 치환이 아니라 앱마다 실질적으로 다르다. 수집하는 데이터 유형, 사용하는 서드파티 SDK (Firebase, Amplitude, RevenueCat), 적용 가능한 법적 관할권이 서비스마다 다르기 때문이다. 이를 따로 관리하면 잘못된 법적 조항을 앱에 게시하는 실수를 방지할 수 있다.

---

## 배포 전 체크리스트

`make deploy-*`를 실행하기 전에 이 체크리스트를 확인한다:

```
□ 스크린샷 최신 앱 버전으로 교체
□ App Store / Play Store 링크 활성 여부 확인
□ 연락처 이메일 정확한지 확인
□ Privacy / Terms 페이지 접근 가능한지 확인 (HTTP 200, 404 아님)
□ 모바일 반응형 확인 (375px 기준)
□ meta description 설정 확인 (120-160자)
□ og:image 설정 및 정상 로드 확인
```

실전에서 가장 흔한 실수는 오래된 스크린샷(App Store 버전이 랜딩 페이지보다 앞서 있음)과 끊어진 스토어 링크(앱이 심사 대기 상태로 들어가서 링크가 일시적으로 사용 불가)다. 이 목록을 매 배포 전에 확인하는 데 2분이면 충분하고, 나중에 고치기 민망한 문제들을 방지할 수 있다.

---

## 규모 확장 시 고려사항

이 구조는 서비스가 약 15개에서 20개 정도까지는 Makefile이 너무 길어지기 전에 잘 작동한다. 그 이상이 되면 서비스 목록을 설정 파일에서 읽는 래퍼 스크립트가 명시적 타겟보다 깔끔할 것이다:

```bash
for service in $(cat services.txt); do
  netlify deploy --prod \
    --dir "$BASE/$service" \
    --site "$(grep "^$service " site-ids.txt | awk '{print $2}')"
done
```

하지만 8개 서비스 수준에서는 명시적 Makefile 방식이 더 읽기 쉽고, 감사하기 쉽고, 스크립트 버그로 인해 잘못된 것을 배포할 가능성이 낮다.

---

## 핵심 정리

- **저장소 1개, Netlify 사이트 N개**: 이것이 이 방식을 작동하게 만드는 근본 구조다. 코드 관리는 중앙화, 배포는 서비스별로 독립적.
- **Pure HTML + Tailwind CDN**: 빌드 도구를 완전히 제거한다. 단순함 자체가 기능이지, 타협이 아니다.
- **`--dir`에 절대경로**: 협상 불가. 상대경로는 환경에 따라 달라지는 동작을 만들어 언젠가는 잘못된 배포를 일으킨다.
- **스크립트보다 Makefile**: 명시적 타겟은 읽기 쉽고, 감사 가능하고, 개별 또는 전체로 실행할 수 있다.
- **공통 컴포넌트 없음**: 발산적 디자인을 가진 드물게 업데이트되는 페이지에서 복붙은 템플릿보다 위험이 낮다.
- **법적 페이지는 필수 인프라**: `privacy/`와 `terms/` 하위 디렉토리는 App Store / Google Play 배포에 필수다. 처음부터 계획에 포함할 것.
- **배포 시간 10-15초**: 빌드 단계가 없기 때문에 필요할 때 수정이 1분 안에 라이브된다.

앱이 늘어나도 새 서비스를 추가하는 과정은 동일하다: 디렉토리 생성, `index.html` 작성, 새 Site ID로 Makefile 타겟 추가, 배포 실행. 설정할 프레임워크도, 확장할 빌드 파이프라인도, 검증할 공유 컴포넌트도 없다. 서비스당 한계 비용이 낮고 예측 가능하다.
