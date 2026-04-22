---
title: "Multi-Domain Static Site Operations Development Guide"
date: 2025-09-13
draft: false
tags: ["Hugo", "Netlify", "Static Site", "DevOps", "Deployment"]
categories: ["DevOps"]
description: "Hugo + Netlify based multi-site static hosting architecture and deployment workflow guide."
cover:
  image: "/images/og/domain-projects-dev-guide.png"
  alt: "Domain Projects Dev Guide"
  hidden: true
---

## Overview

A guide documenting the structure and deployment workflow for managing multiple static sites (landing pages and blogs) from a single directory. This covers practical problems that arise when operating sites with different characteristics — a personal tech blog, per-app landing pages, and multilingual blogs — along with concrete solutions for each.

Static sites have no server overhead, deploy fast, and benefit from highly efficient CDN caching, making them ideal for small personal projects and app marketing pages. However, running multiple sites simultaneously makes it easy to create confusion when each site has a different deployment strategy. This guide clearly separates the deployment approach for each site type and explains how to automate repetitive tasks.

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

### Design Principles Behind the Structure

This directory layout follows three core principles.

**Role separation**: `dcode/landing` is exclusively for app marketing pages. It consists of plain HTML files with no Hugo dependency, making it easy for designers or external collaborators to edit. `seunghan-xyz` is a tech blog that takes full advantage of Hugo's markdown pipeline.

**Independent Git repositories**: Each site is managed as a separate Git repository. Adding a single blog post does not pollute the landing page history. Each site can be versioned independently without conflicts.

**Explicit deployment strategies**: Deployment strategies differ per site. Whether a site uses automatic or manual deployment is made explicit through the directory structure and Makefiles, removing ambiguity for anyone working across multiple sites.

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Personal blog | Hugo + PaperMod Theme |
| App blog | Hugo + Stack Theme v3 |
| Landing pages | Static HTML + Tailwind CSS (CDN) |
| Hosting | Netlify |
| Domain management | Namecheap |

### Why Hugo

Hugo is a static site generator written in Go and is the fastest among competing tools. It transforms hundreds of markdown files into HTML in seconds. It requires no separate runtime and operates as a single binary, making local setup trivial.

The PaperMod theme is SEO-friendly and ships with dark mode, search, and social sharing meta tags out of the box. The Stack theme has a sidebar layout and category archive feature, making it well-suited for content-heavy app blogs.

### Why Netlify

Netlify is a platform optimized for static site hosting. It provides GitHub-connected auto-deployment, a global CDN, automatic HTTPS provisioning, and preview deploy URLs — all available in the free tier for small projects. The mature `netlify-cli` tool makes script-based automation straightforward.

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

The personal blog intentionally disconnects GitHub auto-deployment. This prevents drafts from accidentally deploying and preserves a workflow where the build output (`public/`) is reviewed locally before going live. Since `public/` is in `.gitignore`, the Git history stays clean.

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

Using a Makefile removes the need to remember or type the site ID every time. A single `make deploy` command completes the deployment. If a collaborator joins, you hand them `make deploy` instead of a multi-line CLI command.

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

Manage build configuration as code using `netlify.toml`:

```toml
[build]
  command = "hugo --minify"
  publish = "public"

[build.environment]
  HUGO_VERSION = "0.148.1"
```

Pinning the Hugo version in `netlify.toml` prevents build failures caused by Hugo version updates on Netlify's servers. In practice, Hugo versions after 0.120 changed template syntax that broke several themes mid-build.

---

## Local Development

### Personal Blog Dev Server

```bash
cd ~/domain/seunghan-xyz
hugo server -D       # include drafts
# -> http://localhost:1313
```

The `-D` flag renders posts with `draft: true` locally. This is useful for previewing work in progress. Hugo automatically excludes draft posts at build time, so there is nothing extra to manage at deployment.

### Hugo Blog Dev Server

```bash
cd ~/domain/blogs/blog_richdada/site-a
hugo server -D
# -> http://localhost:1313

# Multi-language check
hugo server --baseURL http://localhost:1313
```

Without specifying `--baseURL` on a multilingual site, language-switch links can point to incorrect URLs. When developing both a Korean and English version in parallel, always provide the `--baseURL` flag explicitly.

### Landing Page Local Preview

No build needed. Open `index.html` directly in browser, or use a simple local server:

```bash
cd ~/domain/dcode/landing
python3 -m http.server 8080
# -> http://localhost:8080
```

Opening via the `file://` protocol can cause CORS errors for relative path references and fetch API calls. Using a local server prevents these issues.

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

The `description` field in frontmatter directly affects SEO. It appears in search result previews, so aim for 120 to 160 characters that capture the core subject. The `tags` and `categories` fields connect to Hugo's taxonomy system and automatically generate listing pages.

### Writing Bilingual Posts

When maintaining Korean and English posts as pairs, follow a consistent file naming convention:

```
posts/
├── my-post.md        # Korean (default language)
└── my-post.en.md     # English
```

When the default language is set to Korean in `hugo.toml`, `.md` files are treated as Korean versions and `.en.md` files as English versions. The `date` in frontmatter and the filename-based path must match across both files for language-switch links to work correctly.

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

App store submissions require a privacy policy (`/privacy/`) and terms of service (`/terms/`) URL. On Netlify, `privacy/index.html` is served at the `/privacy/` URL with no additional configuration.

---

## Domain & Deployment Status

| Site | Deployment Method | Auto-deploy |
|------|-------------------|-------------|
| Personal blog | Netlify CLI (manual) | No |
| Landing pages | Netlify CLI / make deploy | No |
| App blog A | Netlify (GitHub integration) | Yes |
| App blog B | Netlify (GitHub integration) | Yes |

The reason for mixing automatic and manual deployment is that stability requirements differ by site type. Frequently updated blogs benefit from push-to-deploy automation. Personal blogs and landing pages, however, benefit from intentional review before deployment, which reduces the chance of publishing errors.

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

# Create new post and start dev server immediately
cd ~/domain/seunghan-xyz && \
  hugo new posts/new-post.md && \
  hugo server -D
```

---

## Troubleshooting

### Changes Not Reflected After Deployment

Netlify CDN cache may still be serving the old version. Run "Clear cache and retry deploy" from the Netlify dashboard, or force a redeploy via CLI:

```bash
netlify deploy --prod --dir [absolute-path] --site [SITE_ID]
```

If the issue is a browser-side cache, try a hard refresh (`Cmd+Shift+R` on macOS or `Ctrl+Shift+R` on Windows/Linux).

### Hugo Build Error: Template Parsing Failure

After a Hugo version update, some themes may produce an `execute of template failed` error. Pin `HUGO_VERSION` in `netlify.toml` to a version that was previously working, and check the theme repository for a compatible update:

```toml
[build.environment]
  HUGO_VERSION = "0.136.5"  # pin to stable version
```

### Netlify Auto Deploy Not Triggering After Git Push

Check the GitHub integration status under "Site configuration > Build & deploy > Continuous deployment" in the Netlify dashboard. If the GitHub App permissions have expired or repository access has changed, re-connecting the integration may be required.

---

## Important Notes

1. **Use absolute paths** -- Always specify absolute paths for the Netlify CLI `--dir` option
2. **GitHub push does not equal deploy** -- Personal blog and landing pages are not connected to auto-deploy; manual CLI deploy required
3. **Hugo public/ directory** -- Included in `.gitignore`; verify it exists after build and before deploy
4. **Multi-language Hugo sites** -- Check `DefaultContentLanguage` when running `hugo server`; root URL redirection may need configuration
5. **Tailwind CSS CDN** -- Landing pages use a CDN approach with no separate build process, but require an internet connection
6. **Track new files in Git** -- Forgetting `git add` after creating a new file means it never reaches GitHub and will be missing from auto-deploys

---

## Key Takeaways

- **Separate deployment strategies by site type**: Auto-deploy is convenient but is not always the right choice for every site. Intentionally keeping manual deployment for sites that need review reduces the chance of publishing mistakes.
- **Enforce absolute path rules**: Using relative paths with Netlify CLI's `--dir` option can silently deploy the wrong directory depending on where the command runs — a subtle and hard-to-debug failure mode.
- **Pin Hugo version in code**: Declaring `HUGO_VERSION` in `netlify.toml` prevents unexpected build failures from platform-side Hugo updates.
- **Wrap repetitive commands in Makefiles**: Complex CLI commands wrapped in Makefile targets simplify deployment for everyone working on the project.
- **Exclude `public/` from Git**: Tracking build artifacts in Git pollutes the history and increases repository size unnecessarily. Let Netlify handle builds or upload directly via CLI.

---

## References

- [Hugo Official Documentation](https://gohugo.io/documentation/)
- [PaperMod Theme](https://github.com/adityatelange/hugo-PaperMod)
- [Hugo Stack Theme](https://github.com/CaiJimmy/hugo-theme-stack)
- [Netlify CLI Documentation](https://docs.netlify.com/cli/get-started/)
