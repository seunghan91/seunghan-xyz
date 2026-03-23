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

They serve different roles, so they are separated. But I wanted to manage them all from one place. I initially split them into separate repositories, but eventually settled on grouping them under a single directory. This post documents that structure and the configuration choices for each blog.

---

## Why Hugo

Among static site generators, the reason for choosing Hugo is straightforward: it is **fast**. Hundreds of posts build in under a second. It runs as a single Go binary, so there is no dependency management overhead. Unlike Node.js-based tools, there is no `node_modules` folder accumulating hundreds of megabytes.

Other advantages include:

- **Theme ecosystem**: High-quality free themes like PaperMod, Stack, and Blowfish are readily available
- **Built-in multilingual support**: No plugins needed — just an `i18n/` folder and `hugo.toml` configuration
- **Hugo Modules**: Manages themes using Go Modules, making version pinning and updates clean
- **Official Netlify support**: Specifying the Hugo version in `netlify.toml` guarantees the build environment

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

All three blogs live under the same `~/domain/` directory, but they are completely independent Hugo projects. Each has its own `hugo.toml`, `themes/`, and `public/`. Nothing is shared between them.

The advantage of this structure is **clear boundaries**. Upgrading the Hugo version of one blog has no effect on the others. Changing theme configuration is equally isolated.

---

## Theme Selection

### Dev Blog: PaperMod

```toml
# hugo.toml
theme = 'PaperMod'
```

Minimal and fast. Code highlighting is clean and dark mode is supported by default. Search, archive, and table of contents features are built in, requiring almost no additional configuration.

Code block style configuration:

```toml
[markup.highlight]
style = "github-dark"
noClasses = false
```

Setting `noClasses = false` makes Hugo output CSS classes instead of inline styles. This allows custom CSS to override code block styles.

PaperMod is managed as a git submodule. This is more intuitive than Hugo Modules, and submodule status is immediately visible on GitHub.

```bash
# When cloning for the first time
git clone --recurse-submodules https://github.com/username/seunghan-xyz

# Initializing submodules in an already-cloned repo
git submodule update --init --recursive
```

### App Blog: Hugo Stack v3

```toml
# hugo.toml
[module]
  [[module.imports]]
    path = "github.com/CaiJimmy/hugo-theme-stack/v3"
```

Card-style layout. Suits pages with many visual elements, like app introduction pages. Installed via Hugo Modules for easy updates:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

Using Hugo Modules creates `go.mod` and `go.sum` files that lock the theme version. Run `hugo mod get -u` to upgrade to the latest version, and `hugo mod tidy` to clean up unused dependencies.

### Theme Installation Methods Compared

| Method | Pros | Cons |
|--------|------|------|
| git submodule | Intuitive, status visible on GitHub | Requires `--recurse-submodules` on clone |
| Hugo Modules | Clean version locking, easy updates | Requires managing `go.mod`, requires Go installed |
| Direct copy | Simplest approach | Inconvenient to update, difficult to track changes |

---

## Multilingual Setup (App Blog)

App store reviews require an app homepage URL, and an English page is often needed as well. Apple App Store review guidelines require a support URL and a marketing URL. If the review is conducted in English and no English page exists, the submission may be rejected.

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

UI strings are managed in the `i18n/` folder:

```yaml
# i18n/en.yaml
- id: home
  translation: "Home"

- id: readMore
  translation: "Read More"
```

Pages without translations fall back to the default language (Korean). It is more practical to translate only key pages rather than everything. Translating the app description page, privacy policy, and terms of service is sufficient to pass review.

### URL Structure

The URL structure changes after enabling multilingual support:

- Korean: `https://example.com/posts/feature-update/`
- English: `https://example.com/en/posts/feature-update/`

Setting `DefaultContentLanguage = "ko"` means Korean pages have no language prefix, while English pages get the `/en/` prefix. Without this setting, Korean pages would also have a `/ko/` prefix, breaking existing URLs.

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

Specifying `HUGO_VERSION` is critical. Without it, Netlify uses an older Hugo version, which may cause build failures or unexpected output. The safest approach is to pin the exact version currently in use locally.

The `hugo --minify` flag compresses HTML, CSS, and JS. It reduces file size and improves load time. During development, build without minify to inspect output; the flag only applies on deployment.

### Automatic Deployment (GitHub Integration)

Connect a GitHub repository to Netlify and it auto-builds on `main` branch pushes. Setup steps:

1. Netlify dashboard → "Add new site" → "Import an existing project"
2. Select the GitHub repository
3. Build settings: `hugo --minify`, Publish directory: `public`
4. If `netlify.toml` is present, Netlify reads it automatically

Note: If `netlify.toml` settings conflict with the Netlify dashboard settings, `netlify.toml` takes precedence.

### Manual Deployment (Dev Blog)

```bash
cd ~/domain/seunghan-xyz
hugo && netlify deploy --prod \
  --dir ~/domain/seunghan-xyz/public \
  --site [SITE_ID]
```

**Absolute path required** for `--dir`. Using a relative path deploys based on the current working directory, uploading the wrong files. This mistake results in deploying an empty directory or files from a different project entirely.

`SITE_ID` can be found in the Netlify dashboard under "Site settings" → "Site details", or in the `.netlify/state.json` file.

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

The `-D` flag includes posts with `draft: true` in the preview server. This is useful for reviewing posts in progress. When building for deployment, running `hugo` without this flag excludes all drafts automatically.

`hugo server` detects file changes and automatically refreshes the browser via LiveReload. Changes appear in real time while writing.

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

The `description` field is the meta description shown in search results. Keep it between 120 and 160 characters. Leaving it empty causes Hugo to truncate the beginning of the body text, which often produces awkward phrasing, so writing it explicitly is better.

### Filename Convention

```
posts/flutter-testflight-makefile-automation.md
posts/rails-dart-api-integration.md
posts/hugo-blog-multi-site-management.md
```

All lowercase, hyphen-separated. The URL maps directly to the filename.

Since the URL matches the filename exactly, there is consistency from an SEO perspective. Renaming the file later changes the URL and breaks existing links, so it is worth choosing the name carefully upfront.

### OG Image

The image displayed when sharing on social media is specified via `cover.image` in front matter:

```markdown
cover:
  image: "/images/og/hugo-blog-multi-site-management.png"
  alt: "Hugo Blog Multi Site Management"
  hidden: true
```

`hidden: true` means the image is used only in OG tags and not rendered in the post body. It prevents the cover image from automatically appearing at the top of the article.

---

## Theme Updates

### PaperMod (git submodule)

```bash
cd ~/domain/seunghan-xyz
git submodule update --remote --merge
git add themes/PaperMod
git commit -m "chore: update PaperMod theme"
```

The `--remote` flag fetches the latest commit from the submodule's remote repository. `--merge` merges local changes if any exist. As long as the theme has not been modified directly, the update will complete without conflicts.

### Stack v3 (Hugo Modules)

```bash
cd ~/domain/blogs/blog_richdada/[app]-blog
hugo mod get -u
hugo mod tidy
```

`hugo mod get -u` updates all modules to their latest versions. To update a specific module only, specify the path:

```bash
hugo mod get -u github.com/CaiJimmy/hugo-theme-stack/v3
```

Always verify locally after updating. A major version bump in a theme can change layout structures or configuration conventions.

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

Setting `enableRobotsTXT = true` causes Hugo to generate a `robots.txt` file automatically. Search engine crawlers read this file to understand the site structure. The default configuration allows all crawlers.

### Sitemap

Hugo generates `sitemap.xml` by default. Registering this URL in Google Search Console helps new posts get indexed faster:

```
https://seunghan.xyz/sitemap.xml
```

Sitemap generation can be customized:

```toml
[sitemap]
  changefreq = "weekly"
  priority = 0.5
  filename = "sitemap.xml"
```

### Canonical URL

When the same content is accessible from multiple URLs, specifying a canonical URL avoids duplicate content penalties. Hugo adds a canonical tag to each page by default. Confirm that `baseURL` is set correctly:

```toml
baseURL = "https://seunghan.xyz/"
```

---

## Problems Encountered in Production

### 1. Forgetting git add Breaks Deployment

Creating a file under `content/` and committing without `git add` means the file never reaches GitHub. Netlify automatic deployment operates based on the GitHub repository, so even if the file exists locally, it will not appear in the deployment.

```bash
# Good habit to establish
git status
git add .
git commit -m "post: add new article"
git push
```

### 2. Hugo Version Mismatch

When something builds locally but fails on Netlify, the cause is usually that `HUGO_VERSION` in `netlify.toml` does not match the local version.

```bash
# Check local version
hugo version
```

Copy the output version number directly into `netlify.toml`.

### 3. Relative Path Mistake on Manual Deployment

```bash
# Wrong
netlify deploy --prod --dir public

# Correct
netlify deploy --prod --dir ~/domain/seunghan-xyz/public
```

Using a relative path while not inside `~/domain/seunghan-xyz/` will deploy a `public/` folder from the wrong location.

---

## Summary

| Purpose | Theme | Deployment | Notes |
|---------|-------|------------|-------|
| Dev blog | PaperMod | Netlify CLI (manual) | This blog |
| App homepage | Stack v3 | Netlify (auto, GitHub linked) | ko/en multilingual |
| Personal blog | Stack v3 | Netlify (auto, GitHub linked) | — |

All three blogs build and deploy independently. The temptation to share common configurations existed, but since each has different Hugo versions and requirements, keeping them fully independent turned out to be the right call.

---

## Key Takeaways

- **Single directory, independent Hugo projects**: Keep all blogs under one filesystem location, but maintain strict Hugo project boundaries between them
- **Choose theme management method by purpose**: Technical blog with PaperMod (git submodule); visual-heavy content with Stack (Hugo Modules)
- **Always pin Hugo version in netlify.toml**: This is the foundation of build reproducibility — without an explicit version, the build environment is not guaranteed
- **Use absolute paths on manual deployment**: Relative paths in `--dir` deploy files from the wrong location
- **Draft workflow**: Start with `draft: true`, flip to `false` on completion to prevent accidental deployment
- **Multilingual only where needed**: For app store review compliance, translating the description, privacy policy, and terms of service is sufficient — full translation is not necessary
- **Confirm git add**: After creating a file, always run `git status` to verify — untracked files do not get deployed
