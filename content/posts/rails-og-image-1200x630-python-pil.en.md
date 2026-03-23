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

When I pasted a link into KakaoTalk, the preview icon appeared small and distorted. The root cause was straightforward: `og:image` was pointing directly at the 512x512 square app icon without any customization.

---

## The Problem

```erb
<%# Before — using square icon as og:image %>
<meta property="og:image" content="/icon.png">
```

The recommended OG image size is **1200x630** (1.91:1 ratio). Using a square image results in either cropping or unwanted whitespace depending on the platform. Neither looks intentional.

There is a second problem hiding in that snippet: the path `/icon.png` is relative. KakaoTalk, Slack, and other external crawlers fetch OG metadata from their own servers, not from the user's browser. A relative path means the crawler has no base URL to resolve against and simply skips the image entirely. An absolute URL is required.

### Why 1200x630

The Open Graph protocol was originally proposed by Facebook, and almost every major platform adopted the same specification: KakaoTalk, Slack, Twitter, LinkedIn, iMessage link previews. The minimum image size varies by platform, but the de facto standard that renders cleanly everywhere is **1200x630**.

| Platform | Minimum | Recommended |
|----------|---------|-------------|
| Facebook | 200x200 | 1200x630 |
| KakaoTalk | 300x158 | 800x400+ |
| Twitter (X) | 300x157 | 1200x628 |
| Slack | any | 1200x630 or equivalent ratio |
| LinkedIn | 1200x627 | 1200x627 |

At 1200x630, your image avoids cropping on all major platforms. It is the least-common-denominator size that Just Works everywhere.

---

## Generating OG Images with Python PIL

No design tools needed. The Python Imaging Library (PIL, via Pillow) is sufficient for generating clean, branded OG images programmatically.

```python
#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
img = Image.new('RGB', (W, H), (17, 17, 17))   # black background
draw = ImageDraw.Draw(img)

# Fonts (macOS paths)
font_bold = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 120)
font_sub  = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 34)

# Main text
text = 'MyApp'
bbox = draw.textbbox((0, 0), text, font=font_bold)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

# Red dot accent
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

Result: dark background, white logo text, red dot accent, gray subtitle — roughly 20KB on disk.

### Installation and Font Path Issues

```bash
pip install Pillow
```

On macOS, system font paths vary by OS version. If the font file is missing you will see `OSError: cannot open resource`. Find the correct path first:

```bash
# Find Arial Bold
find /System/Library/Fonts -name "*Arial*Bold*" 2>/dev/null

# Find a CJK font
find /System/Library/Fonts -name "*.ttc" | grep -i gothic
```

On a Linux CI or production server, system fonts are not installed by default. You need to install a font package explicitly:

```bash
# Ubuntu / Debian
sudo apt-get install fonts-noto-cjk

# Then update the font path in the script
font_bold = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 120)
```

This is one of the more common failure points when running the script in a Docker container or on a remote server. Adding a font existence check with a clear error message saves debugging time:

```python
import os, sys

font_path = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
if not os.path.exists(font_path):
    sys.exit(f'Font not found: {font_path}')
```

### `draw.textbbox` vs `draw.textsize`

As of Pillow 9.2.0, `textsize()` is deprecated and will be removed in a future release. Old tutorials still use it, which causes deprecation warnings at runtime. The replacement is `textbbox((0, 0), text, font=font)`, which returns a `(left, top, right, bottom)` tuple. Width and height are then computed as:

```python
bbox = draw.textbbox((0, 0), text, font=font)
width  = bbox[2] - bbox[0]
height = bbox[3] - bbox[1]
```

The `(0, 0)` anchor is important: `textbbox` calculates bounding box relative to a given origin, so passing `(0, 0)` gives you dimensions as if the text were rendered at the top-left corner of the canvas.

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
- Use `request.base_url` on `og:image` to produce an absolute URL
- Declare `og:image:width` and `og:image:height` so platforms can finalize layout before the image download completes
- Set `og:url` to `request.url` so each page has its own canonical URL in OG context
- `summary_large_image` for Twitter Card renders the wide image format instead of a small thumbnail

### Why `og:url` Matters

Omitting `og:url` causes the crawling platform to use whatever URL it accessed as the canonical identifier. If someone shares a URL with query parameters like `?ref=kakao`, those parameters pollute the canonical record. Worse, if the same content is reachable at multiple paths, social engagement counts (likes, shares) fragment across those URLs instead of aggregating on one. Explicitly setting `og:url` consolidates all engagement onto a single canonical URL.

### Choosing the Right `og:type`

| Value | Use case |
|-------|----------|
| `website` | Generic pages and homepages (default) |
| `article` | Blog posts, news articles |
| `product` | Product pages (used by Facebook commerce) |
| `video.other` | Video content pages |

For a Rails app with a blog or posts resource, override the type to `article` in those views. The `article` type also unlocks additional OG properties like `article:published_time` and `article:author` that some platforms surface.

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

### Abstracting into a Helper

Once the same pattern appears in multiple controllers, it is worth extracting into a helper:

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
    @meta_tags&.dig(:title) || 'MyApp — One-line description'
  end

  def meta_tag_description
    @meta_tags&.dig(:description) || 'Detailed service description'
  end

  def meta_tag_image
    @meta_tags&.dig(:image) || "#{request.base_url}/og-image.png"
  end
end
```

The layout becomes cleaner:

```erb
<meta property="og:title"       content="<%= meta_tag_title %>">
<meta property="og:description" content="<%= meta_tag_description %>">
<meta property="og:image"       content="<%= meta_tag_image %>">
```

---

## Debugging: Common Issues

### The image still does not appear in KakaoTalk

KakaoTalk caches OG data aggressively. Even after clearing cache in the developer tool, the device-level cache may persist. Check in this order:

1. Go to `developers.kakao.com/tool/clear/og` and delete the URL cache
2. Open KakaoTalk app settings and clear the cache
3. Test by sending the link from a different device

### The absolute URL is set correctly but the image does not load

Rails in development runs at `http://localhost:3000`, which is unreachable by external crawlers. KakaoTalk, Facebook, and Slack crawl from their own servers — they cannot reach your localhost. Deploy to a staging or production domain before testing with OG debuggers. As a workaround for local testing, ngrok can expose a local port to a public URL temporarily.

### `request.base_url` returns `http://` instead of `https://`

This is common when Rails runs behind a proxy such as Nginx or a cloud load balancer (Render.com, Heroku, Fly.io). The proxy terminates SSL and forwards the request over plain HTTP internally, so Rails sees an HTTP connection. Fix it by trusting the forwarded protocol header:

```ruby
# config/environments/production.rb
config.force_ssl = true
```

On Rails 7.1+, the cleaner option for proxy environments is:

```ruby
# config/environments/production.rb
config.assume_ssl = true
```

`assume_ssl` tells Rails to treat all requests as HTTPS without requiring an actual SSL connection, which is the correct posture when the proxy handles SSL termination.

---

## Validation Tools

| Platform | Debugger URL |
|----------|-------------|
| KakaoTalk | developers.kakao.com/tool/clear/og |
| Facebook | developers.facebook.com/tools/debug |
| Twitter | cards-dev.twitter.com/validator |
| General | opengraph.xyz |

After deployment, cached previews may persist across tools and devices. Always hit "Scrape Again" or equivalent in each debugger and test from a clean session before declaring the issue resolved.

---

## Key Takeaways

- **1200x630** is the cross-platform standard for OG images. Anything square will be cropped or padded on at least one major platform.
- `og:image` must be an **absolute URL**. Relative paths are silently ignored by external crawlers.
- Python PIL (Pillow) can generate branded OG images without any design tools. Watch out for font path differences between macOS development and Linux production.
- The deprecated `textsize()` API has been replaced by `textbbox()` since Pillow 9.2.0.
- Declare `og:image:width` and `og:image:height` so the platform can reserve layout space before fetching the image.
- `og:url` consolidates social engagement counts onto a single canonical URL. Do not omit it.
- If `request.base_url` returns HTTP in production, configure `assume_ssl = true` or review your proxy's forwarded-protocol headers.
- KakaoTalk's cache is aggressive. Clear it through the developer tool and the device app before concluding a fix did not work.
