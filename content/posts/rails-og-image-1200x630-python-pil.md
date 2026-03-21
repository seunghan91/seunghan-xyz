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

---

## 검증 도구

| 플랫폼 | 디버거 URL |
|--------|------------|
| 카카오톡 | developers.kakao.com/tool/clear/og |
| 페이스북 | developers.facebook.com/tools/debug |
| 트위터 | cards-dev.twitter.com/validator |
| 범용 | opengraph.xyz |

배포 후 캐시가 남아 있을 수 있으니 디버거에서 "캐시 초기화" 후 확인한다.
