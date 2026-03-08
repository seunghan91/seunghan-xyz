---
title: "Hugo 블로그 AdSense 승인 준비 — 사이트 구조 정리와 필수 페이지 세팅"
date: 2026-03-08
draft: false
tags: ["AdSense", "Hugo", "블로그", "SEO", "Netlify", "PaperMod"]
description: "Hugo + PaperMod 블로그에서 Google AdSense 승인을 위해 사이트 구조를 정리한 실제 작업 기록. 필수 페이지 생성, 앱 정책 페이지 noindex 처리, 빈 카테고리 제거까지."
cover:
  image: ""
  alt: "Hugo AdSense 승인 준비"
  relative: false
---

Google AdSense에 사이트를 등록했는데 상태가 "준비 중"에서 멈춰 있었다. 글은 80개 넘게 있는데 왜 승인이 안 되는 걸까? 조사해보니 **콘텐츠 양의 문제가 아니라 사이트 구조의 문제**였다.

이 글에서는 Hugo + PaperMod 블로그에서 AdSense 승인 확률을 높이기 위해 실제로 수정한 내용을 정리한다.

---

## 현황 진단

AdSense 신청 후 거절되는 주요 사유는 크게 3가지다:

| 거절 사유 | 의미 |
|----------|------|
| **가치가 별로 없는 콘텐츠** | 글이 독창적이지 않거나 AI 생성물 그대로 |
| **게시자 콘텐츠가 없는 화면에 광고** | 빈 페이지나 정책 페이지에 광고 코드가 삽입됨 |
| **준비 중** | 필수 페이지 누락, 사이트 구조 미비 |

내 블로그는 세 번째 — "준비 중" 상태였다. 글 수는 충분했지만 **구조적인 결함**이 있었다.

---

## 문제 1: 필수 페이지 누락

AdSense 승인에 필요한 **5대 필수 페이지**:

| 페이지 | 존재 여부 |
|--------|----------|
| About (소개) | 있음 |
| Contact (문의) | 있음 |
| Privacy Policy (개인정보처리방침) | 있음 |
| **Terms of Service (이용약관)** | **없음** |
| **Disclaimer (면책조항)** | **없음** |

이용약관과 면책조항이 빠져 있었다. Google은 이 페이지들을 통해 "이 사이트가 진지하게 운영되고 있는가"를 판단한다.

### 해결: Hugo에서 페이지 생성

```bash
mkdir -p content/terms content/disclaimer
```

`content/terms/index.md`:
```markdown
---
title: "이용약관"
date: 2025-01-01
draft: false
hidemeta: true
ShowBreadCrumbs: false
ShowPostNavLinks: false
ShowReadingTime: false
---

## 이용약관

본 약관은 [사이트명]의 이용 조건을 규정합니다...
```

면책조항도 같은 구조로 작성했다. 기술 블로그에 맞는 내용을 포함:
- 코드 스니펫은 "AS-IS"로 제공
- 전문적 기술 컨설팅이 아님
- 외부 링크에 대한 책임 면제

### 푸터 메뉴에 추가

`hugo.toml`에서 footer 메뉴에 추가:

```toml
[[languages.ko.menu.footer]]
identifier = "privacy-policy"
name = "개인정보처리방침"
url = "/privacy-policy/"
weight = 10

[[languages.ko.menu.footer]]
identifier = "terms"
name = "이용약관"
url = "/terms/"
weight = 20

[[languages.ko.menu.footer]]
identifier = "disclaimer"
name = "면책조항"
url = "/disclaimer/"
weight = 30

[[languages.ko.menu.footer]]
identifier = "contact"
name = "문의"
url = "/contact/"
weight = 40
```

다국어 사이트라면 영문 메뉴(`languages.en.menu.footer`)에도 동일하게 추가해야 한다.

---

## 문제 2: 앱 정책 페이지가 색인에 포함

블로그에 앱 스토어 제출용 개인정보처리방침, 지원 페이지를 호스팅하고 있었다. 이런 페이지들은:

- 블로그 콘텐츠가 아닌 **앱 정책 문서**
- 사용자에게 직접적 가치를 제공하지 않음
- Google 크롤러가 "콘텐츠 없는 페이지"로 판단할 수 있음

### 해결: Hugo에서 noindex 처리

각 앱 정책 페이지의 front matter에 `_build`와 `sitemap` 설정을 추가:

```yaml
---
title: "앱 개인정보처리방침"
draft: false
_build:
  list: never      # 목록 페이지에 표시하지 않음
  render: always   # 페이지 자체는 접근 가능 (앱 스토어 링크용)
sitemap:
  priority: 0          # 사이트맵 우선순위 최하
  changefreq: never    # 변경 빈도 없음
---
```

이렇게 하면:
- 앱 스토어 심사용 URL은 그대로 유지됨
- 블로그 메인이나 카테고리 목록에는 노출되지 않음
- 사이트맵에서 우선순위가 최하로 설정됨

총 8개 페이지에 적용했다.

---

## 문제 3: 콘텐츠 부족한 카테고리

상단 메뉴에 "New"라는 카테고리가 있었는데, 글이 2개뿐이었다. AdSense 크롤러가 이 카테고리 페이지를 방문하면 **콘텐츠가 거의 없는 빈 페이지**로 판단할 수 있다.

### 해결: 카테고리 제거 + 글 이동

```bash
# 글 2개를 일반 posts 디렉토리로 이동
mv content/new/macbook-neo-2026.md content/posts/
mv content/new/csa-aliro-1-0.md content/posts/

# 빈 카테고리 디렉토리 삭제
rm -rf content/new/
```

`hugo.toml`에서 상단 메뉴 항목도 제거:

```toml
# 삭제
# [[languages.ko.menu.main]]
# identifier = "new"
# name = "New"
# url = "/new/"
# weight = 40
```

**핵심**: 모든 메뉴 항목은 충분한 콘텐츠가 있는 페이지로 연결되어야 한다.

---

## 최종 체크리스트

작업 후 Hugo 빌드가 정상인지 확인:

```bash
hugo
# Pages: 622 | 533 (ko | en)
# Total in 942 ms ✅
```

| 항목 | 상태 |
|------|------|
| 고품질 글 20개+ | 87개 ✅ |
| About 페이지 | ✅ |
| Contact 페이지 | ✅ |
| Privacy Policy | ✅ |
| Terms of Service | ✅ (신규) |
| Disclaimer | ✅ (신규) |
| ads.txt | ✅ |
| sitemap.xml | Hugo 자동생성 ✅ |
| HTTPS | Netlify 기본 제공 ✅ |
| Google Search Console | 등록 완료 ✅ |
| 앱 정책 페이지 noindex | ✅ (8개) |
| 빈 카테고리 제거 | ✅ |

---

## 배포

GitHub에 push하면 Netlify가 자동 빌드+배포한다:

```bash
git add .
git commit -m "AdSense 승인 준비: 필수 페이지 추가 및 사이트 구조 정리"
git push origin main
```

배포 후 AdSense 정책 센터에서 "검토 요청"을 제출하면 된다. 승인까지는 보통 1~14일.

---

## 정리

AdSense 승인이 안 되는 이유는 대부분 글의 양이 아니라 **사이트 구조**에 있다:

1. **필수 페이지 5종**을 모두 갖추고 푸터에서 접근 가능하게
2. **앱 정책 페이지** 같은 비콘텐츠 페이지는 색인에서 제외
3. **빈 카테고리**는 과감히 제거하거나 콘텐츠를 채우기
4. 모든 메뉴 링크가 **실제 콘텐츠가 있는 페이지**로 연결되는지 확인

글을 아무리 많이 써도 구조가 엉망이면 "준비 중"에서 벗어나기 어렵다. 반대로, 구조만 잘 잡으면 글 20~30개로도 승인받는 사례가 많다.
