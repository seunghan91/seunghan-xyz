---
title: "Hugo 블로그 Google Search Console '크롤링됨 - 현재 색인이 생성되지 않음' 완벽 해결"
date: 2026-03-23
draft: false
tags: ["SEO", "Hugo", "Google Search Console", "robots.txt", "PaperMod"]
categories: ["DevOps"]
description: "Google Search Console에서 '크롤링됨 - 현재 색인이 생성되지 않음' 14개 페이지 문제를 robots.txt RSS 피드 차단과 noindex 태그로 해결한 과정. Hugo PaperMod 테마 기준 실전 가이드."
faq:
  - q: "robots.txt로 차단하면 색인이 완전히 방지되나요?"
    a: "아닙니다. robots.txt는 크롤링을 막지만 색인을 완전히 방지하지는 않습니다. 외부 사이트에서 차단된 URL로 링크를 걸면 Google은 URL 자체를 색인할 수 있습니다(내용 없이). 색인을 확실하게 막으려면 noindex 메타 태그나 X-Robots-Tag HTTP 헤더를 사용해야 합니다. RSS 피드처럼 외부 링크 가능성이 낮은 페이지는 robots.txt 차단으로 충분합니다."
  - q: "Hugo에서 특정 태그 페이지만 sitemap에서 제외하는 방법이 있나요?"
    a: "layouts/sitemap.xml 커스텀 템플릿을 만들어 term Kind 페이지 중 글 수가 적은 것을 필터링할 수 있습니다. 단, noindex를 적용한 페이지는 sitemap에서도 제거해야 Google에 일관된 신호를 줄 수 있습니다. noindex 페이지가 sitemap에 남아있으면 Google이 혼동할 수 있고, 처리 속도도 느려집니다."
  - q: "유효성 검사를 요청했는데 반영이 너무 느립니다. 얼마나 기다려야 하나요?"
    a: "GSC 유효성 검사는 일반적으로 수일에서 수 주가 걸립니다. Google이 재크롤링하는 시점에 따라 달라지며, 개인 블로그 규모에서는 대개 1~3주 정도 기다리면 상태가 업데이트됩니다. 개별 URL은 GSC 상단 검색창에 URL 입력 후 '색인 생성 요청'으로 우선 크롤링을 요청할 수 있습니다. robots.txt나 noindex 변경 후 sitemap을 GSC에 재제출하면 처리가 조금 빨라질 수 있습니다."
---

## 어느 날 날아온 Google Search Console 경고 메일

블로그를 운영하다 보면 Google Search Console(이하 GSC)에서 메일이 날아올 때가 있다. 대부분은 "색인 생성이 완료되었습니다" 같은 좋은 소식이지만, 이번에는 달랐다.

> **크롤링됨 - 현재 색인이 생성되지 않음**
> 유효성 검사 상태: 실패함
> 영향을 받은 페이지: 14개

14개 페이지가 Google에 의해 크롤링은 되었지만, 검색 결과에는 나타나지 않는 상태였다. 이전에 유효성 검사를 요청했지만 실패로 돌아왔다. 무엇이 문제인지, 어떻게 해결했는지 기록한다.

---

## '크롤링됨 - 현재 색인이 생성되지 않음'이란?

Google의 페이지 색인 생성 과정은 크게 3단계로 나뉜다:

| 단계 | 설명 | 상태 |
|------|------|------|
| **발견** | Googlebot이 URL의 존재를 인지 | 발견됨 |
| **크롤링** | Googlebot이 실제로 페이지를 방문하여 내용을 읽음 | 크롤링됨 |
| **색인 생성** | Google이 페이지를 검색 결과 데이터베이스에 등록 | 색인됨 |

"크롤링됨 - 현재 색인이 생성되지 않음"은 2단계까지는 완료되었지만, **3단계에서 Google이 "이 페이지는 색인할 가치가 없다"고 판단**한 상태다.

Google 공식 문서에 따르면 이 상태는 다음과 같은 이유로 발생한다:

- **콘텐츠 품질 부족**: 페이지에 고유한 가치가 없다고 판단
- **중복 콘텐츠**: 다른 페이지와 내용이 겹침
- **얇은 콘텐츠(Thin Content)**: 글이 1-2개뿐인 태그/카테고리 페이지
- **RSS/XML 피드**: 검색 결과로 보여줄 가치가 없는 기술적 페이지

---

## 문제 분석: 14개 페이지의 정체

GSC에서 영향받는 URL 목록을 확인했다:

| URL | 유형 | 최종 크롤링 |
|-----|------|------------|
| `/en/categories/rails/` | 영문 카테고리 페이지 | 2026-03-22 |
| `/tags/activerecord/` | 태그 페이지 | 2026-03-21 |
| `/tags/offline-first/index.xml` | RSS 피드 | 2026-03-20 |
| `/tags/synology/index.xml` | RSS 피드 | 2026-03-19 |
| `/tags/테마/index.xml` | RSS 피드 | 2026-03-19 |
| `/tags/di/index.xml` | RSS 피드 | 2026-03-10 |
| `/tags/build_runner/index.xml` | RSS 피드 | 2026-03-10 |
| `/tags/iap/index.xml` | RSS 피드 | 2026-03-10 |
| `/tags/webview/index.xml` | RSS 피드 | 2026-03-10 |
| `/tags/playwright/index.xml` | RSS 피드 | 2026-03-10 |

패턴이 보인다. 크게 **두 가지 유형**이었다:

### 유형 1: RSS 피드 (`index.xml`) — 대다수

`/tags/*/index.xml` 형태의 URL이 10개 중 8개를 차지했다. Hugo는 태그별로 RSS 피드 파일을 자동 생성하는데, 이 XML 파일들은 검색 결과에 표시할 콘텐츠가 아니다. Google이 크롤링은 했지만 당연히 색인하지 않는다.

문제는 **크롤링 자체가 낭비**라는 점이다.

### 유형 2: 얇은 콘텐츠 태그/카테고리 페이지

`/tags/activerecord/`나 `/en/categories/rails/` 같은 페이지는 해당 태그에 글이 1-2개밖에 없는 "얇은 콘텐츠" 페이지다. Google은 이런 페이지를 "고유한 가치가 부족하다"고 판단해서 색인에서 제외한다.

---

## 핵심 개념: 크롤링 예산(Crawl Budget)

여기서 중요한 SEO 개념이 등장한다. **크롤링 예산(Crawl Budget)**이다.

Google은 각 웹사이트에 일정량의 크롤링 자원을 할당한다. Googlebot이 사이트를 방문할 때 모든 페이지를 한 번에 크롤링하지 않고, 할당된 예산 내에서 크롤링한다.

Google 공식 문서에 따르면 크롤링 예산은 두 가지 요소로 결정된다:

- **크롤링 속도 제한(Crawl Rate Limit)**: 서버에 과부하를 주지 않기 위한 동시 연결 수 제한
- **크롤링 수요(Crawl Demand)**: Google이 크롤링하고 싶어하는 URL의 인기도와 신선도

개인 블로그 같은 소규모 사이트에서는 크롤링 예산이 크게 문제되지 않지만, RSS 피드처럼 **색인될 가치가 없는 페이지에 예산을 소모하면 중요한 새 글의 색인이 지연**될 수 있다.

### robots.txt vs noindex의 차이

| 방법 | 크롤링 | 색인 | 용도 |
|------|--------|------|------|
| `robots.txt Disallow` | 차단 | 가능(외부 링크 시) | 크롤링 예산 절약 |
| `<meta name="robots" content="noindex">` | 허용 | 차단 | 확실한 색인 제거 |
| 둘 다 적용 | 차단 | noindex를 못 읽음 | **금지! 충돌 발생** |

**중요**: `robots.txt`로 차단한 페이지에 `noindex`를 넣으면 안 된다. Googlebot이 페이지를 크롤링하지 못하면 `noindex` 태그를 읽을 수 없기 때문이다. 두 방법은 용도에 맞게 분리해서 사용해야 한다.

---

## 해결 방법 1: robots.txt에서 RSS 피드 차단

RSS 피드(`index.xml`)는 검색 결과에 표시될 필요가 없다. `robots.txt`에서 크롤링 자체를 차단하는 것이 적절하다.

### 수정 전 (`layouts/robots.txt`)

```text
User-agent: *
Allow: /
Disallow:

User-agent: Yeti
Allow: /

Sitemap: {{ .Site.BaseURL }}sitemap.xml
Sitemap: {{ .Site.BaseURL }}ko/sitemap.xml
Sitemap: {{ .Site.BaseURL }}en/sitemap.xml
```

문제점:
1. `Disallow:` 가 비어있어서 아무것도 차단하지 않음
2. 사이트맵을 3개나 선언 — Hugo의 sitemap index가 이미 하위 사이트맵을 참조하므로 중복

### 수정 후

```text
User-agent: *
Allow: /
Disallow: /tags/*/index.xml
Disallow: /categories/*/index.xml
Disallow: /en/tags/*/index.xml
Disallow: /en/categories/*/index.xml

User-agent: Yeti
Allow: /

Sitemap: {{ .Site.BaseURL }}sitemap.xml
```

변경 내용:
- **태그/카테고리별 RSS 피드 크롤링 차단**: `/tags/*/index.xml` 패턴으로 모든 태그 RSS를 차단
- **다국어(en) 경로도 포함**: Hugo 다국어 설정으로 `/en/tags/*/index.xml` 경로도 생성되므로 함께 차단
- **중복 사이트맵 제거**: Hugo의 `sitemap.xml`이 이미 sitemap index 형태로 `ko/sitemap.xml`과 `en/sitemap.xml`을 참조하므로 하나만 선언

### Hugo에서 robots.txt 활성화

`hugo.toml`에서 다음 설정이 필요하다:

```toml
enableRobotsTXT = true
```

이 설정이 있어야 Hugo가 `layouts/robots.txt` 템플릿을 사용해서 `public/robots.txt`를 생성한다. 이 설정이 없으면 Hugo는 기본 robots.txt만 생성하거나, `static/robots.txt` 파일을 그대로 복사한다.

---

## 해결 방법 2: 얇은 태그/카테고리 페이지에 noindex 추가

글이 1개 이하인 태그 페이지는 사실상 목록 페이지로서의 가치가 없다. 이런 페이지에는 `noindex`를 적용해서 Google에 "이 페이지는 색인하지 마세요"라고 알려주는 것이 좋다.

단, `noindex`를 적용할 때는 `follow`를 함께 사용한다. 해당 페이지에 링크된 **실제 글은 계속 크롤링되어야** 하기 때문이다.

### Hugo PaperMod 테마에서 noindex 구현

PaperMod 테마는 `layouts/partials/extend_head.html` 파일을 통해 `<head>` 태그에 커스텀 코드를 삽입할 수 있다.

```html
{{- /* noindex for thin taxonomy pages (tags/categories with few posts) */ -}}
{{- if .Data.Terms }}{{- /* taxonomy list page (e.g. /tags/, /categories/) */ -}}
{{- else if and (eq .Kind "term") (le (len .Pages) 1) }}
<meta name="robots" content="noindex, follow" />
{{- end -}}
```

이 코드의 동작 원리:

| 조건 | 대상 페이지 | 동작 |
|------|------------|------|
| `.Data.Terms` 존재 | `/tags/`, `/categories/` (목록 페이지) | 아무것도 안 함 (색인 허용) |
| `.Kind == "term"` + 글 1개 이하 | `/tags/activerecord/` 등 | `noindex, follow` 적용 |
| 그 외 | 일반 포스트, 홈 등 | 아무것도 안 함 (색인 허용) |

### Hugo의 페이지 Kind 이해하기

Hugo는 각 페이지를 `Kind`라는 속성으로 분류한다:

```
home       → 홈페이지 (/)
page       → 일반 페이지, 포스트 (/posts/my-article/)
section    → 섹션 목록 (/posts/)
taxonomy   → 택소노미 목록 (/tags/, /categories/)
term       → 개별 택소노미 (/tags/seo/, /categories/devops/)
```

`taxonomy` Kind는 `.Data.Terms`를 가지고 있어서 구분할 수 있고, `term` Kind는 `.Pages`로 해당 태그에 속한 글 목록을 접근할 수 있다.

---

## 왜 모든 태그 페이지를 noindex하지 않는가?

여기서 한 가지 의문이 생길 수 있다. "그냥 모든 태그/카테고리 페이지를 noindex 하면 안 되나?"

**아니다.** 글이 많은 태그 페이지는 SEO에 도움이 된다:

1. **랜딩 페이지 역할**: `/tags/flutter/`에 글이 15개 있다면, "flutter 블로그"를 검색하는 사용자에게 유용한 진입점이 된다
2. **내부 링크 허브**: 관련 글들을 연결하는 허브 역할로 Google이 사이트 구조를 이해하는 데 도움
3. **검색 유입 채널**: 실제로 태그 페이지를 통해 검색 트래픽이 들어오는 경우가 있다

Google의 John Mueller도 "태그 페이지가 사용자에게 가치를 제공한다면 색인되어도 좋다"고 확인한 바 있다. 핵심은 **가치가 있는 페이지만 색인**되도록 하는 것이다.

그래서 **글이 1개 이하인 태그만** 선별적으로 noindex를 적용했다. 글이 2개 이상이면 목록 페이지로서의 가치가 있다고 판단한 것이다.

---

## 배포와 확인

### 빌드

```bash
cd /path/to/hugo-blog
hugo
```

빌드 후 `public/robots.txt`를 확인한다:

```text
User-agent: *
Allow: /
Disallow: /tags/*/index.xml
Disallow: /categories/*/index.xml
Disallow: /en/tags/*/index.xml
Disallow: /en/categories/*/index.xml

User-agent: Yeti
Allow: /

Sitemap: https://seunghan.xyz/sitemap.xml
```

### Git Push + Netlify 배포

```bash
git add layouts/robots.txt layouts/partials/extend_head.html
git commit -m "fix: block RSS feed crawling and noindex thin taxonomy pages"
git push origin main
```

Netlify가 자동으로 빌드하고 배포한다. 1-2분 후 라이브 사이트에서 확인:

```
https://seunghan.xyz/robots.txt
```

### GSC에서 유효성 검사 재요청

1. [Google Search Console](https://search.google.com/search-console) 접속
2. 좌측 메뉴 → **페이지** (페이지 색인 생성)
3. "크롤링됨 - 현재 색인이 생성되지 않음" 클릭
4. 우측 상단 **"유효성 검사"** 또는 **"새 유효성 검사 시작"** 클릭

개별 URL도 빠르게 재크롤링을 요청할 수 있다:
1. GSC 상단 검색창에 URL 입력 (예: `https://seunghan.xyz/tags/activerecord/`)
2. **"색인 생성 요청"** 클릭

---

## robots.txt의 한계와 주의사항

Google 공식 문서에서 명확히 경고하는 내용이 있다:

> **robots.txt는 페이지를 Google에서 숨기는 메커니즘이 아닙니다.** robots.txt로 차단된 URL이라도 외부에서 링크하면 색인될 수 있습니다.

즉, robots.txt로 `/tags/seo/index.xml`을 차단해도, 다른 사이트가 이 URL을 링크하면 Google은 URL 자체를 색인할 수 있다(내용 없이 URL만 검색 결과에 표시).

**확실하게 색인을 막으려면:**
- `noindex` 메타 태그 사용 (가장 확실)
- `X-Robots-Tag: noindex` HTTP 헤더 사용
- 페이지 자체 삭제 또는 비밀번호 보호

RSS 피드의 경우는 외부에서 직접 링크할 가능성이 거의 없으므로 robots.txt 차단만으로 충분하다.

---

## 추가 최적화: 사이트맵에서 불필요한 페이지 제거

robots.txt와 noindex 외에도 사이트맵 최적화를 고려할 수 있다. Hugo는 기본적으로 모든 페이지를 사이트맵에 포함시키는데, 태그/카테고리 페이지를 사이트맵에서 제외하면 Google에 더 명확한 신호를 줄 수 있다.

Hugo의 커스텀 사이트맵 템플릿(`layouts/sitemap.xml`)을 만들어서 `term` Kind 페이지를 제외할 수 있지만, 이번에는 robots.txt + noindex 조합만으로 충분했기 때문에 추가 작업은 하지 않았다.

사이트맵과 noindex가 일관성 있어야 한다는 점은 기억해두자. noindex한 페이지가 사이트맵에 남아있으면 Google에 혼동을 줄 수 있다.

---

## 해결 후 기대 효과

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| RSS 피드 크롤링 | Googlebot이 태그별 RSS 피드 모두 크롤링 | robots.txt로 차단, 크롤링 예산 절약 |
| 얇은 태그 페이지 | "크롤링됨 - 색인 안 됨" 경고 | noindex로 명확한 의도 전달 |
| 사이트맵 | 3개 중복 선언 | 1개만 선언 (index가 하위 참조) |
| GSC 상태 | 14개 페이지 문제 | RSS는 크롤링 안 함, 태그는 의도적 noindex |

수정 후 Google이 재크롤링하면 "크롤링됨 - 현재 색인이 생성되지 않음" 페이지 수가 줄어들 것이다. RSS 피드는 아예 크롤링 목록에서 빠지고, 얇은 태그 페이지는 "noindex에 의해 제외됨"으로 상태가 변경된다.

---

## 주의사항 / 알려진 함정

1. **robots.txt + noindex 동시 사용 금지**: Disallow된 페이지의 noindex 태그는 Googlebot이 읽을 수 없다. 둘 중 하나만 사용할 것
2. **유효성 검사 시간**: GSC 유효성 검사는 며칠에서 수주가 걸릴 수 있다. 조급해하지 말 것
3. **중요한 글이 색인 안 되는 경우**: 실제 포스트가 "크롤링됨 - 색인 안 됨"이면 콘텐츠 품질 문제일 수 있다. 글을 보완하고 수동으로 색인 요청
4. **Hugo 테마 업데이트 시 주의**: `layouts/partials/extend_head.html`은 테마 커스텀 파일이므로 테마 업데이트 시 덮어쓰이지 않지만, 구조가 바뀌면 확인 필요
5. **Yeti는 네이버 크롤러**: `robots.txt`에 Yeti(네이버봇) 허용 규칙이 있다면 네이버 검색 노출도 확인할 것

---

## 결론

Google Search Console의 "크롤링됨 - 현재 색인이 생성되지 않음" 문제는 대부분 **RSS 피드나 얇은 콘텐츠 페이지** 때문이다. 실제 중요한 포스트가 색인되지 않는 게 아니라면, robots.txt와 noindex 조합으로 깔끔하게 해결할 수 있다.

핵심 정리:
- **RSS 피드**: `robots.txt`에서 크롤링 차단 → 크롤링 예산 절약
- **얇은 태그/카테고리**: `noindex, follow` 메타 태그 → 색인 제외하되 링크는 추적
- **robots.txt + noindex 동시 사용 금지**: 용도에 맞게 분리

블로그를 운영한다면 GSC를 주기적으로 확인하는 습관을 들이자. "통과"라고 표시되어도 "크롤링됨 - 색인 안 됨" 항목은 따로 챙겨봐야 한다.

---

## 자주 묻는 질문 (FAQ)

### Q: `robots.txt`로 차단하면 Google 색인이 완전히 방지되나요?

아니다. `robots.txt`는 크롤링을 막지만 **색인을 완전히 방지하지는 않는다**. Google 공식 문서에 명시된 대로, 외부 사이트가 차단된 URL로 링크를 걸면 Google은 URL 자체를 색인할 수 있다(내용 없이). 색인을 확실하게 막으려면 `noindex` 메타 태그나 `X-Robots-Tag: noindex` HTTP 헤더를 사용해야 한다. RSS 피드처럼 외부에서 직접 링크될 가능성이 낮은 페이지는 `robots.txt` 차단만으로 충분하다. 단, 절대로 `robots.txt`로 차단한 페이지에 `noindex`를 동시에 적용하지 말아야 한다. Googlebot이 페이지를 방문하지 못하면 `noindex` 태그를 읽을 수도 없기 때문이다.

### Q: Hugo에서 특정 태그 페이지만 `sitemap.xml`에서 제외할 수 있나요?

`layouts/sitemap.xml` 커스텀 템플릿을 만들어서 `term` Kind이면서 글이 적은 페이지를 필터링할 수 있다. 예를 들어 `{{- if and (ne .Kind "term") (gt (len .Pages) 1) -}}` 같은 조건을 추가하면 된다. `noindex`를 적용한 페이지는 사이트맵에서도 제거하는 것이 권장된다. `noindex` 페이지가 사이트맵에 남아있으면 Google에 상충된 신호를 보내게 되어 처리가 지연되거나 혼동을 줄 수 있다.

### Q: GSC 유효성 검사를 요청했는데 반영이 너무 느립니다. 얼마나 기다려야 하나요?

GSC 유효성 검사는 일반적으로 수일에서 수 주가 걸린다. 개인 블로그 규모에서는 대개 1~3주를 기다려야 상태가 업데이트된다. 개별 URL의 경우 GSC 상단 검색창에 URL을 입력하고 "색인 생성 요청"을 클릭하면 우선 크롤링을 요청할 수 있다. `robots.txt`나 `noindex` 변경 후 GSC의 사이트맵 섹션에서 사이트맵을 재제출하면 Google이 변경 사항을 인식하는 속도가 조금 빨라진다.

### Q: 글이 적은 태그 페이지를 noindex하면 해당 태그에 달린 글의 검색 노출에도 영향이 있나요?

없다. `noindex, follow`를 사용하기 때문에 태그 페이지 자체는 색인되지 않지만, 해당 페이지에서 링크된 실제 포스트는 Google이 계속 크롤링하고 색인한다. `follow`는 "이 페이지의 링크는 따라가도 된다"는 의미로, 태그 페이지를 허브로 삼아 연결된 글들은 영향받지 않는다. 만약 `noindex, nofollow`를 사용했다면 링크 추적도 차단되므로 반드시 `follow`와 함께 써야 한다.

---

## 관련 이슈 및 추가 팁

### Core Web Vitals와 색인의 관계

"크롤링됨 - 현재 색인이 생성되지 않음" 중 RSS나 태그 페이지가 아닌 **실제 포스트**가 포함되어 있다면, 해당 페이지의 Core Web Vitals(LCP, CLS, INP) 점수가 낮을 가능성이 있다. Google은 페이지 경험(Page Experience) 신호를 색인 순위 결정에 활용하며, 극단적으로 나쁜 페이지 경험은 색인 자체를 늦추는 요인이 될 수 있다. GSC의 "Core Web Vitals" 섹션에서 모바일/데스크톱 상태를 함께 확인해보는 것이 좋다.

### Hugo PaperMod 다국어 블로그의 robots.txt 주의사항

한국어/영어 다국어 Hugo 블로그에서는 `/ko/tags/*/index.xml`, `/en/tags/*/index.xml`처럼 언어 prefix가 붙은 경로가 별도로 생성된다. `robots.txt`에서 언어 prefix 없는 경로만 차단하면 다른 언어의 RSS 피드는 여전히 크롤링된다. 다국어 설정을 사용한다면 각 언어 prefix별 경로를 모두 `Disallow`에 추가하거나, `Disallow: /*/tags/*/index.xml` 같은 와일드카드 패턴을 사용해야 한다.
