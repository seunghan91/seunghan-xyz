---
title: "Managing 3 Hugo Blogs from a Single Folder"
date: 2025-10-08
draft: false
tags: ["Hugo", "Netlify", "Blog", "Static Site", "PaperMod", "Stack"]
description: "How to operate 3 Hugo blogs with different purposes (dev blog, app homepage, personal blog) from a single directory with independent Netlify deployments."
cover:
  image: "/images/og/hugo-blog-multi-site-management.png"
  alt: "Hugo Blog Multi Site Management"
  hidden: true
---


I run 3 Hugo blogs for different purposes.

1. **Dev blog** — Development debugging logs, technical documentation (this blog)
2. **[App] Homepage** — App introduction + update blog, multilingual (ko/en)
3. **Personal blog** — Non-development writing

They are separated by role, but I wanted to manage them all from one place.

---

## Directory Structure

```
~/domain/
├── seunghan-xyz/           # Dev blog
│   ├── content/
│   │   ├── posts/          # Technical posts
│   │   ├── projects/       # Project introductions
│   │   └── about/
│   ├── themes/
│   │   └── PaperMod/       # git submodule
│   ├── hugo.toml
│   └── public/             # Build output
│
├── blogs/
│   └── blog_richdada/
│       ├── [app]-blog/     # App homepage + blog
│       │   ├── content/
│       │   │   ├── posts/
│       │   │   ├── features/
│       │   │   ├── legal/
│       │   │   └── mcp/
│       │   ├── i18n/       # ko.yaml, en.yaml
│       │   ├── hugo.toml
│       │   └── netlify.toml
│       │
│       └── personal-blog/  # Personal blog
│           ├── content/
│           │   └── posts/
│           └── hugo.toml
│
└── dcode/
    └── landing/            # Static landing pages
```

---

## Theme Selection

### Dev Blog: PaperMod

```toml
# hugo.toml
theme = 'PaperMod'
```

Minimal and fast. Code highlighting is clean and dark mode is supported by default. Search, archive, and table of contents features are built in, requiring almost no additional configuration.

```toml
[markup.highlight]
style = "github-dark"
noClasses = false
```

### App Blog: Hugo Stack v3

```toml
# hugo.toml
[module]
  [[module.imports]]
    path = "github.com/CaiJimmy/hugo-theme-stack/v3"
```

Card-style layout. Suits pages with many visual elements like app introduction pages. Installed via Hugo Modules for easy updates:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

---

## Multilingual Setup (App Blog)

App store reviews require an app homepage URL, and an English page is often needed as well.

```toml
# hugo.toml
DefaultContentLanguage = "ko"

[languages]
  [languages.ko]
    languageName = "Korean"
    weight = 1
  [languages.en]
    languageName = "English"
    weight = 2
```

Content file structure:

```
content/
├── posts/
│   ├── ko/
│   │   └── feature-update.md
│   └── en/
│       └── feature-update.md
├── features/
│   └── _index.ko.md
│   └── _index.en.md
```

Pages without translations fall back to the default language (ko). It is more practical to translate only key pages rather than everything.

---

## Netlify Deployment

Each blog has its own `netlify.toml` and a separate Netlify site.

```toml
# netlify.toml
[build]
  publish = "public"
  command = "hugo --minify"

[build.environment]
  HUGO_VERSION = "0.141.0"

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
```

Automatic deployment: Connect the GitHub repository to Netlify and it auto-builds on `main` branch pushes.

Manual deployment (dev blog):
```bash
cd ~/domain/seunghan-xyz
hugo && netlify deploy --prod \
  --dir ~/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

**Absolute path required** for `--dir`. Using a relative path deploys based on the current working directory, uploading the wrong files.

---

## Local Development

```bash
# Dev blog
cd ~/domain/seunghan-xyz
hugo server -D          # Preview including drafts
hugo server --port 1314 # Avoid port conflicts

# App blog
cd ~/domain/blogs/blog_richdada/[app]-blog
hugo server -D --port 1315

# Personal blog
cd ~/domain/blogs/blog_richdada/personal-blog
hugo server -D --port 1316
```

All three servers can run simultaneously. Just use different ports.

---

## Post Writing Patterns

### Front Matter Template

```markdown
---
title: "Title"
date: 2025-10-08
draft: false
tags: ["tag1", "tag2"]
description: "One-line SEO description"
---
```

Write with `draft: true` and change to `false` when complete. This prevents drafts from being accidentally deployed.

### Filename Convention

```
posts/flutter-testflight-makefile-automation.md
posts/rails-dart-api-integration.md
posts/hugo-blog-multi-site-management.md
```

All lowercase, hyphen-separated. The URL becomes the filename directly.

---

## Theme Updates

### PaperMod (git submodule)

```bash
cd ~/domain/seunghan-xyz
git submodule update --remote --merge
git add themes/PaperMod
git commit -m "chore: update PaperMod theme"
```

### Stack v3 (Hugo Modules)

```bash
cd ~/domain/blogs/blog_richdada/[app]-blog
hugo mod get -u
hugo mod tidy
```

---

## SEO Configuration

```toml
# hugo.toml
enableRobotsTXT = true

[outputs]
home = ["HTML", "RSS", "JSON"]

[params]
  description = "..."
  keywords = ["development", "Flutter", "iOS", "Rails"]
```

JSON output is needed for Fuse.js search. When you enable the search feature in PaperMod, it is used automatically.

---

## Summary

| Purpose | Theme | Deployment | Notes |
|---------|-------|------------|-------|
| Dev blog | PaperMod | Netlify CLI (manual) | This blog |
| App homepage | Stack v3 | Netlify (auto, GitHub linked) | ko/en multilingual |
| Personal blog | Stack v3 | Netlify (auto, GitHub linked) | -- |

All three blogs build and deploy independently of each other.
I was tempted to share common configurations, but since each has different Hugo versions and requirements, the conclusion was to keep them independent.
