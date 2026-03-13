---
title: "Multi-Domain Static Site Operations Development Guide"
date: 2025-09-13
draft: false
tags: ["Hugo", "Netlify", "Static Site", "DevOps", "Deployment"]
description: "Hugo + Netlify based multi-site static hosting architecture and deployment workflow guide."
cover:
  image: "/images/og/domain-projects-dev-guide.png"
  alt: "Domain Projects Dev Guide"
  hidden: true
---

## Overview

A guide documenting the structure and deployment workflow for managing multiple static sites (landing pages + blogs) from a single directory.

---

## Directory Structure

```
~/domain/
├── dcode/
│   └── landing/          # Static HTML landing page collection
│       ├── index.html    # Main page
│       ├── app-a/        # Per-app subdirectory
│       │   ├── index.html
│       │   ├── privacy/
│       │   └── terms/
│       ├── app-b/
│       └── Makefile
│
├── seunghan-xyz/         # Personal blog (Hugo)
│   ├── content/
│   │   ├── posts/        # Tech blog posts
│   │   ├── projects/     # Project introductions
│   │   └── about/
│   ├── hugo.toml
│   └── public/           # Build output (git excluded)
│
└── blogs/
    └── blog_richdada/    # Hugo blog collection
        ├── site-a/       # Site A (Korean/English)
        └── site-b/       # Site B
```

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Personal blog | Hugo + PaperMod Theme |
| App blog | Hugo + Stack Theme v3 |
| Landing pages | Static HTML + Tailwind CSS (CDN) |
| Hosting | Netlify |
| Domain management | Namecheap |

---

## Deployment Methods

### 1. Personal Blog (Hugo -> Netlify CLI)

Build then deploy directly with Netlify CLI. GitHub push is **not** connected to auto-deploy.

```bash
cd ~/domain/seunghan-xyz

# Hugo build
hugo

# Netlify deploy (absolute path required)
netlify deploy --prod \
  --dir /Users/[username]/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

> Warning: Relative paths like `--dir .` or `--dir public` may deploy the wrong directory depending on execution location. **Always use absolute paths.**

### 2. Landing Pages (Static HTML -> Netlify CLI)

```bash
cd ~/domain/dcode/landing

# Using Makefile
make deploy

# Or run directly
netlify deploy --prod \
  --dir /Users/[username]/domain/dcode/landing \
  --site [SITE_ID]
```

`Makefile` contents:
```makefile
NETLIFY_SITE_ID = [SITE_ID]

deploy:
	netlify deploy --prod --dir . --site $(NETLIFY_SITE_ID)
```

### 3. Hugo Blogs (Netlify Auto Deploy)

Blog sites auto-build and deploy on Netlify when pushed to the GitHub main branch.

```bash
cd ~/domain/blogs/blog_richdada/site-a

# Dev server
hugo server -D

# Production build (for verification)
hugo --minify

# Push to GitHub -> auto deploy
git add . && git commit -m "update" && git push origin main
```

---

## Local Development

### Personal Blog Dev Server

```bash
cd ~/domain/seunghan-xyz
hugo server -D       # include drafts
# -> http://localhost:1313
```

### Hugo Blog Dev Server

```bash
cd ~/domain/blogs/blog_richdada/site-a
hugo server -D
# -> http://localhost:1313

# Multi-language check
hugo server --baseURL http://localhost:1313
```

### Landing Page Local Preview

No build needed -- open `index.html` directly in browser, or use a simple local server:

```bash
cd ~/domain/dcode/landing
python3 -m http.server 8080
# -> http://localhost:8080
```

---

## Content Creation

### Adding Blog Posts (seunghan-xyz)

```bash
cd ~/domain/seunghan-xyz
hugo new posts/my-new-post.md
```

Generated frontmatter:
```yaml
---
title: "Post Title"
date: 2025-09-13
draft: true          # change to false for deployment
tags: ["tag1"]
categories: ["Dev"]
description: "description"
---
```

### Adding Landing Page Apps

Create a new app directory and copy the existing structure:

```
app-new/
├── index.html      # Main landing
├── app_icon.png    # App icon (1024x1024)
├── privacy/
│   └── index.html  # Privacy policy
└── terms/
    └── index.html  # Terms of service
```

---

## Domain & Deployment Status

| Site | Deployment Method | Auto-deploy |
|------|-------------------|-------------|
| Personal blog | Netlify CLI (manual) | No |
| Landing pages | Netlify CLI / make deploy | No |
| App blog A | Netlify (GitHub integration) | Yes |
| App blog B | Netlify (GitHub integration) | Yes |

---

## Frequently Used Commands

```bash
# Personal blog build + deploy (one shot)
cd ~/domain/seunghan-xyz && hugo && \
  netlify deploy --prod \
  --dir /Users/[username]/domain/seunghan-xyz/public \
  --site [SITE_ID]

# Landing page deploy
cd ~/domain/dcode/landing && make deploy

# Check git status across all sites
for dir in seunghan-xyz dcode/landing; do
  echo "=== $dir ===" && cd ~/domain/$dir && git status --short && cd ~/domain
done

# Check Hugo version
hugo version

# Check Netlify CLI login status
netlify status
```

---

## Important Notes

1. **Use absolute paths** -- Always specify absolute paths for Netlify CLI `--dir` option
2. **GitHub push does not equal deploy** -- Personal blog and landing pages are not connected to auto-deploy; manual CLI deploy required
3. **Hugo public/ directory** -- Included in `.gitignore`, verify existence after build and before deploy
4. **Multi-language Hugo sites** -- Check `DefaultContentLanguage` when running `hugo server`; root URL redirection may need configuration
5. **Tailwind CSS CDN** -- Landing pages use CDN approach, no separate build process needed, requires internet connection

---

## References

- [Hugo Official Documentation](https://gohugo.io/documentation/)
- [PaperMod Theme](https://github.com/adityatelange/hugo-PaperMod)
- [Hugo Stack Theme](https://github.com/CaiJimmy/hugo-theme-stack)
- [Netlify CLI Documentation](https://docs.netlify.com/cli/get-started/)
