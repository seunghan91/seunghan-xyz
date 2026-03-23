---
title: "Rails OG 이미지 최적화 — Python PIL로 1200×630 생성 + 메타태그 완전판"
date: 2025-12-23
draft: true
tags: ["Rails", "OG Image", "Open Graph", "Python", "PIL", "SEO", "카카오톡"]
description: "og:image를 정사각형 아이콘에서 1200x630 전용 이미지로 교체하고, og:url / og:site_name / Twitter Card까지 메타태그를 완성한 기록"
cover:
  image: "/images/og/rails-og-image-1200x630-python-pil.png"
  alt: "Rails Og Image 1200X630 Python Pil"
  hidden: true
categories: ["Rails"]
---

카카오톡에 링크를 붙여넣으니 아이콘이 작고 이상하게 나왔다. 원인은 `og:image`가 512×512 정사각형 앱 아이콘을 그대로 쓰고 있었기 때문이다.

---

## 문제

```erb
<%# 기존 — 정사각형 아이콘을 og:image로 사용 %>
<meta property="og:image" content="/icon.png">
```

OG 이미지 권장 크기는 **1200×630** (1.91:1 비율)이다. 정사각형을 넣으면 플랫폼마다 잘리거나 여백이 생긴다.

또 `/icon.png` 같은 상대경로는 카카오톡·슬랙 등에서 이미지를 못 불러오는 경우가 있다. 절대 URL이 필요하다.

### 왜 1200×630인가

Open Graph 프로토콜은 Facebook이 제안했고, 이후 카카오톡·슬랙·트위터·링크드인 등 거의 모든 SNS가 같은 규격을 따른다. 최소 크기는 600×314이지만, 레티나 디스플레이와 고해상도 환경을 감안하면 **1200×630이 사실상 표준**이다.

- 카카오톡: 최소 300×158, 권장 800×400 이상
- Facebook: 최소 200×200, 권장 1200×630
- Twitter (X): `summary_large_image` 카드는 2:1 비율 이상 권장
- Slack: 1200×630 또는 동등 비율이면 선명하게 표시

플랫폼마다 조금씩 다르지만, 1200×630은 모든 플랫폼에서 잘리지 않고 레이아웃이 잡히는 최소공배수다.

---

## Python PIL로 OG 이미지 생성

별도 디자인 툴 없이 PIL로 간단하게 만들 수 있다.

```python
#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
img = Image.new('RGB', (W, H), (17, 17, 17))   # 검정 배경
draw = ImageDraw.Draw(img)

# 폰트 (macOS 기준)
font_bold = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 120)
font_sub  = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 34)

# 메인 텍스트
text = 'MyApp'
bbox = draw.textbbox((0, 0), text, font=font_bold)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

# 빨간 dot
dot_r = int(th * 0.42)
dot_gap = 14
total_w = tw + dot_gap + dot_r * 2

x = (W - total_w) // 2
y = (H - th) // 2 - 40

draw.text((x, y), text, fill=(255, 255, 255), font=font_bold)

dot_cx = x + tw + dot_gap + dot_r
dot_cy = y + th - dot_r + 4
draw.ellipse(
    [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
    fill=(232, 64, 42)   # #E8402A
)

# 서브타이틀 (한글)
sub_text = '서비스 한 줄 설명'
sub_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
sub_w = sub_bbox[2] - sub_bbox[0]
sub_x = (W - sub_w) // 2
sub_y = y + th + 32
draw.text((sub_x, sub_y), sub_text, fill=(140, 140, 140), font=font_sub)

img.save('public/og-image.png', 'PNG', optimize=True)
print(f'Done: {os.path.getsize("public/og-image.png")//1024}KB')
```

결과물: 검정 배경 + 흰색 로고 텍스트 + 빨간 dot + 회색 서브타이틀, 약 20KB.

### PIL 설치 및 주의사항

```bash
pip install Pillow
```

macOS에서 시스템 폰트 경로가 버전마다 다를 수 있다. 폰트 파일이 없으면 `OSError: cannot open resource` 에러가 난다. 아래처럼 경로를 확인한다.

```bash
# Arial Bold 경로 확인
find /System/Library/Fonts -name "*Arial*Bold*" 2>/dev/null

# 한글 폰트 경로 확인
find /System/Library/Fonts -name "*.ttc" | grep -i gothic
```

CI/CD 환경(Linux)이라면 시스템 폰트가 없으므로 `fonts-noto` 또는 NanumGothic 같은 패키지를 직접 설치해야 한다.

```bash
# Ubuntu/Debian
sudo apt-get install fonts-noto-cjk

# 경로 예시 (배포 서버)
font_bold = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 120)
```

### `draw.textbbox` vs `draw.textsize`

PIL 9.2.0부터 `textsize()`가 deprecated 되고 `textbbox()`가 표준이 됐다. 오래된 코드에서 `textsize`를 쓰면 경고가 뜨고 미래에는 제거된다. `textbbox((0,0), text, font=font)`를 사용해 `(left, top, right, bottom)` 튜플로 크기를 계산하면 된다.

---

## Rails 메타태그 완전판

```erb
<%# app/views/layouts/application.html.erb %>

<%# Open Graph %>
<meta property="og:site_name" content="MyApp">
<meta property="og:title"       content="<%= @meta_tags&.dig(:title) || 'MyApp — 서비스 한 줄 설명' %>">
<meta property="og:description" content="<%= @meta_tags&.dig(:description) || '서비스 상세 설명' %>">
<meta property="og:image"       content="<%= @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png" %>">
<meta property="og:image:width"  content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type"        content="website">
<meta property="og:url"         content="<%= request.url %>">

<%# Twitter Card %>
<meta name="twitter:card"        content="summary_large_image">
<meta name="twitter:title"       content="<%= @meta_tags&.dig(:title) || 'MyApp — 서비스 한 줄 설명' %>">
<meta name="twitter:description" content="<%= @meta_tags&.dig(:description) || '서비스 상세 설명' %>">
<meta name="twitter:image"       content="<%= @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png" %>">
```

핵심 포인트:
- `og:image`에 `request.base_url`을 붙여 절대 URL 사용
- `og:image:width/height` 명시 → 플랫폼이 미리 크기를 알고 레이아웃 잡음
- `og:url`에 `request.url` → 각 페이지 고유 URL 반영
- Twitter Card는 `summary_large_image`가 넓은 이미지 표시

### `og:url`이 필요한 이유

`og:url`을 빠뜨리면 플랫폼이 크롤러가 접근한 URL을 그대로 canonical URL로 사용한다. 쿼리 파라미터(`?ref=kakao`)가 붙은 URL이 공유되거나, 같은 콘텐츠가 여러 URL에서 공유됐을 때 좋아요·공유 수가 분산된다. `og:url`을 명시하면 이 카운트가 한 URL로 집계된다.

### `og:type` 값 선택

| 타입 | 설명 |
|------|------|
| `website` | 일반 페이지 (기본값) |
| `article` | 블로그 포스트, 뉴스 기사 |
| `product` | 상품 페이지 (Facebook 카탈로그) |
| `video.other` | 동영상 콘텐츠 |

Rails 앱에서 블로그나 게시글이 있다면 해당 뷰에서 `article`로 오버라이드하는 게 정석이다.

---

## 페이지별 OG 태그 오버라이드

컨트롤러에서 `@meta_tags`를 세팅하면 레이아웃의 기본값이 교체된다.

```ruby
# app/controllers/posts_controller.rb
def show
  @post = Post.find(params[:id])
  @meta_tags = {
    title: "#{@post.title} — MyApp",
    description: @post.excerpt,
    image: @post.thumbnail_url || "#{request.base_url}/og-image.png"
  }
end
```

### 헬퍼로 추상화하기

같은 패턴이 여러 컨트롤러에 반복된다면 헬퍼로 뽑아내는 게 낫다.

```ruby
# app/helpers/meta_tags_helper.rb
module MetaTagsHelper
  def set_meta_tags(title: nil, description: nil, image: nil)
    @meta_tags = {
      title:       title,
      description: description,
      image:       image || "#{request.base_url}/og-image.png"
    }.compact
  end

  def meta_tag_title
    @meta_tags&.dig(:title) || 'MyApp — 서비스 한 줄 설명'
  end

  def meta_tag_description
    @meta_tags&.dig(:description) || '서비스 상세 설명'
  end

  def meta_tag_image
    @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png"
  end
end
```

그러면 레이아웃을 더 읽기 쉽게 정리할 수 있다.

```erb
<meta property="og:title"       content="<%= meta_tag_title %>">
<meta property="og:description" content="<%= meta_tag_description %>">
<meta property="og:image"       content="<%= meta_tag_image %>">
```

---

## 디버깅: 자주 겪는 문제

### 카카오톡에서 이미지가 여전히 안 나온다

카카오톡은 OG 캐시를 매우 공격적으로 유지한다. 개발자 도구에서 캐시를 초기화해도 기기 캐시가 남아 있을 수 있다. 확인 순서:

1. `developers.kakao.com/tool/clear/og` 에서 URL 캐시 삭제
2. 카카오톡 앱 → 설정 → 캐시 삭제
3. 다른 기기에서 링크를 공유해 확인

### og:image가 절대 URL인데도 안 보인다

Rails 개발 환경은 `http://localhost:3000`이므로 카카오톡 같은 외부 크롤러가 접근할 수 없다. 스테이징 또는 프로덕션 도메인에 배포한 뒤 디버거로 확인해야 한다. ngrok으로 로컬을 임시 노출하는 방법도 있다.

### `request.base_url`이 https가 아니라 http로 나온다

프록시(Nginx, Load Balancer) 뒤에서 Rails가 실행될 때 흔히 발생한다. `config/environments/production.rb`에 다음을 추가한다.

```ruby
config.force_ssl = true
# 또는
config.action_dispatch.x_forwarded_proto_header = "x-forwarded-proto"
```

Render.com이나 Heroku처럼 HTTPS를 프록시가 처리하는 플랫폼에서는 `config.assume_ssl = true` (Rails 7.1+) 를 사용한다.

---

## 검증 도구

| 플랫폼 | 디버거 URL |
|--------|------------|
| 카카오톡 | developers.kakao.com/tool/clear/og |
| 페이스북 | developers.facebook.com/tools/debug |
| 트위터 | cards-dev.twitter.com/validator |
| 범용 | opengraph.xyz |

배포 후 캐시가 남아 있을 수 있으니 디버거에서 "캐시 초기화" 후 확인한다.

---

## Key Takeaways

- OG 이미지는 **1200×630**이 사실상 모든 플랫폼의 표준 크기다.
- `og:image` 경로는 반드시 **절대 URL**이어야 카카오톡·슬랙에서 정상 표시된다.
- Python PIL로 로컬에서 빠르게 이미지를 생성할 수 있다. CI 환경이라면 Linux 폰트 경로를 별도로 맞춰야 한다.
- `og:image:width/height`를 명시하면 플랫폼이 이미지를 내려받기 전에 레이아웃을 확정하므로 렌더링이 빨라진다.
- `og:url`을 빠뜨리면 좋아요·공유 카운트가 URL마다 분산된다.
- 카카오톡은 캐시가 강하다. 변경 후에는 반드시 디버거로 캐시를 초기화하고 확인한다.
- `request.base_url`이 http로 나온다면 프록시 설정(`assume_ssl`, `x-forwarded-proto`)을 점검한다.
