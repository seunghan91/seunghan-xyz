---
title: "Managing 8 App Landing Pages from a Single Repository"
date: 2025-10-11
draft: false
tags: ["Netlify", "TailwindCSS", "Static Site", "Deployment", "Landing Page", "Workflow"]
description: "Operating multiple app landing pages from a single repository using Pure HTML + Tailwind CDN without build tools, deployed via Netlify CLI."
cover:
  image: "/images/og/multi-landing-page-netlify-workflow.png"
  alt: "Multi Landing Page Netlify Workflow"
  hidden: true
---


When building multiple apps, each one needs its own landing page. Creating 8 separate repositories is too much management overhead, and bundling them together makes deployment complex. The solution I settled on was a single repository + individual Netlify sites strategy.

---

## Directory Structure

```
landing/
├── index.html          # Company main page
├── [service-A]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [service-B]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [service-C]/
│   └── index.html
│ ...
└── Makefile
```

Each service has its own independent directory. The `privacy/` and `terms/` subpages are required for App Store / Google Play review submission.

---

## Why This Tech Stack

### Pure HTML + Tailwind CDN

No build process. No `npm install`, no `node_modules`, no `package.json` -- nothing.

```html
<script src="https://cdn.tailwindcss.com"></script>
```

Landing pages have simple functionality. Scroll animations, CTA buttons, a few screenshots. Adding webpack/vite configuration for this is over-engineering.

The downside is CSS bundle size optimization is impossible. But Tailwind served from CDN goes into browser cache, and the page itself is small, so it has never been a real problem.

### Per-Page Design Systems

Different designs were applied to match each app's character:

| Service Type | Style | Primary Colors |
|-------------|-------|---------------|
| Company main | Trust & Authority | Black + Gold |
| Fortune/Entertainment | Glassmorphism | Blue + Orange |
| Film/Retro | Motion-Driven | Black + White |
| Travel/Lifestyle | Soft UI | Sky Blue + Orange |
| AI Service | Tech Minimal | Gray + Accent |
| Real Estate/Documents | Clean Professional | Navy + White |

Using the same Tailwind with different color palettes and component styles creates completely different impressions.

---

## Netlify Deployment Structure

Create one Netlify site per service. One repository, but independent deployments.

### Makefile

```makefile
NETLIFY := netlify
BASE := /Users/$(USER)/domain/[company]/landing

deploy-main:
	$(NETLIFY) deploy --prod \
		--dir $(BASE) \
		--site [SITE_ID_MAIN]

deploy-service-a:
	$(NETLIFY) deploy --prod \
		--dir $(BASE)/[service-A] \
		--site [SITE_ID_A]

deploy-service-b:
	$(NETLIFY) deploy --prod \
		--dir $(BASE)/[service-B] \
		--site [SITE_ID_B]

deploy-all:
	$(MAKE) deploy-main
	$(MAKE) deploy-service-a
	$(MAKE) deploy-service-b
```

Using absolute paths for `--dir` is important. Using relative paths (`--dir .`) deploys different directories depending on where `make` is executed. Experience this once and the absolute path habit forms.

### Netlify CLI Installation

```bash
npm install -g netlify-cli
netlify login
```

For the first site, manually create it in the Netlify dashboard and get the Site ID. After that, a single `make deploy-*` command is all you need.

---

## Actual Deployment Flow

When modifying a single landing page:

```bash
# 1. Edit HTML
vim landing/[service-A]/index.html

# 2. Deploy only that site
make deploy-service-a

# 3. Verify
# -> https://[service-a].netlify.app
```

When a full deployment is needed:
```bash
make deploy-all
```

Average deployment time is 10-15 seconds. Fast because there is no build process.

---

## Custom Domain Connection

Connect custom domains to each site in the Netlify dashboard.

```
Company main    -> [company-domain].com
Service A       -> [service-A].[company-domain].com (subdomain)
Service B       -> Separate domain
```

DNS settings:
```
A     @    75.2.60.5        (Netlify Load Balancer)
CNAME www  [netlify-site].netlify.app
```

SSL certificates are automatically issued by Netlify via Let's Encrypt. HTTPS is ready within 24 hours of domain connection.

---

## Maintenance Patterns

### Why No Shared Components

There is a temptation to share headers and footers, but I did not. Each page is independent, has different designs, and different deployment timing. Creating shared components means checking everything when changing one thing.

The thought "let's follow the DRY principle" can actually increase complexity. For static files with infrequent changes like landing pages, copy-paste is better.

### Legal Page Management

App Store / Google Play reviews require Privacy Policy and Terms of Service URLs.

```
[service-A]/
├── index.html
├── privacy/
│   └── index.html    # https://[domain]/[service-A]/privacy/
└── terms/
    └── index.html    # https://[domain]/[service-A]/terms/
```

Each page has different content tailored to the app's characteristics, because data collection items and third-party SDK lists differ by service.

---

## Pre-Deployment Checklist

```
[ ] Screenshots updated to latest version
[ ] App Store / Play Store links verified active
[ ] Contact email verified correct
[ ] Privacy / Terms pages verified accessible
[ ] Mobile responsive verified (375px baseline)
[ ] meta description, og:image settings verified
```

---

## Summary

- **1 repository**, **N Netlify sites** structure offers good management efficiency
- **Pure HTML + Tailwind CDN**: Instant deployment without builds
- **Makefile**: Deploy with a single `make deploy-[service]` line
- **Absolute paths required**: Always use absolute paths for the `--dir` option
- **Independent deployment**: Each service deploys without affecting others

As apps grow, just add one directory and one Makefile target, and you are done.
