---
title: "Rails OG Image Optimization — Generating 1200x630 with Python PIL + Complete Meta Tags"
date: 2025-12-23
draft: true
tags: ["Rails", "OG Image", "Open Graph", "Python", "PIL", "SEO", "KakaoTalk"]
description: "Replacing square icon og:image with dedicated 1200x630 images, and completing meta tags including og:url, og:site_name, and Twitter Card."
cover:
  image: "/images/og/rails-og-image-1200x630-python-pil.png"
  alt: "Rails Og Image 1200X630 Python Pil"
  hidden: true
categories: ["Rails"]
---


When I pasted a link into KakaoTalk, the icon appeared small and distorted. The cause was that `og:image` was using the 512x512 square app icon as-is.

---

## Problem

```erb
<%# Before — using square icon as og:image %>
<meta property="og:image" content="/icon.png">
```

The recommended OG image size is **1200x630** (1.91:1 ratio). Using a square image results in cropping or whitespace depending on the platform.

Also, relative paths like `/icon.png` sometimes fail to load images on platforms like KakaoTalk and Slack. An absolute URL is required.

---

## Generating OG Images with Python PIL

You can create them simply with PIL, without any separate design tools.

```python
#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
img = Image.new('RGB', (W, H), (17, 17, 17))   # black background
draw = ImageDraw.Draw(img)

# Fonts (macOS)
font_bold = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 120)
font_sub  = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 34)

# Main text
text = 'MyApp'
bbox = draw.textbbox((0, 0), text, font=font_bold)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

# Red dot
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

# Subtitle
sub_text = 'One-line service description'
sub_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
sub_w = sub_bbox[2] - sub_bbox[0]
sub_x = (W - sub_w) // 2
sub_y = y + th + 32
draw.text((sub_x, sub_y), sub_text, fill=(140, 140, 140), font=font_sub)

img.save('public/og-image.png', 'PNG', optimize=True)
print(f'Done: {os.path.getsize("public/og-image.png")//1024}KB')
```

Result: black background + white logo text + red dot + gray subtitle, approximately 20KB.

---

## Complete Rails Meta Tags

```erb
<%# app/views/layouts/application.html.erb %>

<%# Open Graph %>
<meta property="og:site_name" content="MyApp">
<meta property="og:title"       content="<%= @meta_tags&.dig(:title) || 'MyApp — One-line description' %>">
<meta property="og:description" content="<%= @meta_tags&.dig(:description) || 'Detailed service description' %>">
<meta property="og:image"       content="<%= @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png" %>">
<meta property="og:image:width"  content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type"        content="website">
<meta property="og:url"         content="<%= request.url %>">

<%# Twitter Card %>
<meta name="twitter:card"        content="summary_large_image">
<meta name="twitter:title"       content="<%= @meta_tags&.dig(:title) || 'MyApp — One-line description' %>">
<meta name="twitter:description" content="<%= @meta_tags&.dig(:description) || 'Detailed service description' %>">
<meta name="twitter:image"       content="<%= @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png" %>">
```

Key points:
- Append `request.base_url` to `og:image` for absolute URL usage
- Specify `og:image:width/height` so platforms know the dimensions for layout in advance
- Use `request.url` for `og:url` to reflect each page's unique URL
- For Twitter Card, `summary_large_image` displays the wide image format

---

## Per-Page OG Tag Override

Setting `@meta_tags` in the controller replaces the layout defaults.

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

## Validation Tools

| Platform | Debugger URL |
|----------|-------------|
| KakaoTalk | developers.kakao.com/tool/clear/og |
| Facebook | developers.facebook.com/tools/debug |
| Twitter | cards-dev.twitter.com/validator |
| General | opengraph.xyz |

After deployment, cached data may persist, so clear the cache in the debugger before checking.
