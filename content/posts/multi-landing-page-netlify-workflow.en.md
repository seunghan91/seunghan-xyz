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

When you are building multiple apps simultaneously, each one eventually needs its own landing page. The naive solution — creating eight separate repositories — multiplies management overhead by eight. The opposite extreme — one monolithic repository with a single Netlify deployment — creates a different problem: every change to any single page triggers a full redeployment, and one mistake can break all the others.

The approach I settled on sits between these two extremes: a **single repository** with **N independent Netlify sites**, each deployed to its own subdirectory via the Netlify CLI. This post documents the structure, the reasoning behind each decision, and the patterns that make this maintainable at scale.

---

## Directory Structure

```
landing/
├── index.html          # Company main page
├── [service-A]/
│   ├── index.html
│   ├── privacy/
│   │   └── index.html
│   └── terms/
│       └── index.html
├── [service-B]/
│   ├── index.html
│   ├── privacy/
│   └── terms/
├── [service-C]/
│   └── index.html
│ ...
└── Makefile
```

Each service lives in its own top-level directory. The `privacy/` and `terms/` subdirectories are not optional — App Store and Google Play both require publicly accessible URLs for Privacy Policy and Terms of Service before they will approve an app for distribution.

The flat, predictable structure means any developer can understand the layout in seconds. There is no configuration to parse, no framework knowledge required.

---

## Why This Tech Stack

### Pure HTML + Tailwind CDN

The entire setup has zero build dependencies. No `npm install`, no `node_modules`, no `package.json`, no lockfile, no bundler.

```html
<script src="https://cdn.tailwindcss.com"></script>
```

Landing pages have focused, limited functionality: a hero section, scroll animations, CTA buttons, app screenshots, and legal pages. For this scope, introducing a full webpack or Vite pipeline is over-engineering. The cognitive overhead of maintaining build configuration is not justified by the problem being solved.

The CDN approach does have a real tradeoff: you cannot purge unused CSS classes, so the full Tailwind stylesheet (roughly 350KB uncompressed) loads on every visit. In practice, this has never caused a measurable performance issue. The CDN URL is the same across all Tailwind projects worldwide, meaning it is almost always already cached in the visitor's browser from an unrelated site they visited earlier. The actual page HTML is tiny — typically under 20KB — so the total payload is acceptable.

For projects that need production-grade performance optimization, moving to Tailwind CLI with PurgeCSS is straightforward. But for landing pages with relatively low traffic, the simplicity tradeoff is worth it.

### Why Not a Static Site Generator?

Tools like Hugo, Eleventy, or Astro are excellent choices for content-heavy sites. But they introduce a build step, a templating language to learn, and a dependency to maintain. Since each landing page here has a completely different design — not just different content — shared templates would provide minimal benefit. The pages are not generated from data; they are crafted individually.

The decision rule is simple: if the pages shared enough structure to benefit from templates, a generator would be worth it. Since they do not, plain HTML wins.

### Per-Page Design Systems

Using the same Tailwind utility classes, each service gets a completely distinct visual identity tailored to its brand and target audience:

| Service Type | Style | Primary Colors |
|---|---|---|
| Company main | Trust & Authority | Black + Gold |
| Fortune/Entertainment | Glassmorphism | Blue + Orange |
| Film/Retro | Motion-Driven | Black + White |
| Travel/Lifestyle | Soft UI | Sky Blue + Orange |
| AI Service | Tech Minimal | Gray + Accent |
| Real Estate/Documents | Clean Professional | Navy + White |

Glassmorphism — with `backdrop-blur`, semi-transparent `bg-white/10` backgrounds, and gradient borders — gives an entirely different feel from a clean `bg-white` professional layout, even though both are written in Tailwind. The utility-first approach makes this kind of divergent design practical without maintaining separate CSS files.

---

## Netlify Deployment Structure

The core architecture is one repository mapped to multiple Netlify sites. Each site has its own Site ID, its own domain, and its own independent deployment pipeline. Changes to one site cannot affect any other.

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

Two design decisions in this Makefile are worth explaining:

**Absolute paths for `--dir`.** This is not a stylistic preference — it is a correctness requirement. The `--dir` flag tells Netlify CLI which directory to upload. If you use a relative path like `--dir .`, the result depends entirely on the working directory when `make` is invoked. Run it from the root of the repository, you deploy the whole repository. Run it from a service subdirectory, you deploy only that subdirectory. The behavior is unpredictable across different terminal sessions and CI environments. Absolute paths remove this ambiguity entirely.

**One Makefile target per service.** This is intentional repetition. You could DRY this up with a loop or a function, but the explicitness is valuable. You can see at a glance which Site IDs exist, which services are registered, and which services are not in the automated pipeline. When you add a new service, the process is mechanical: add a directory, add a target, add it to `deploy-all`.

### Netlify CLI Setup

```bash
npm install -g netlify-cli
netlify login
```

The first site for each service must be created manually in the Netlify dashboard. This is intentional — the Netlify dashboard is where you configure domains, environment variables, and team access. Automating site creation via the Netlify API is possible but adds complexity for a one-time operation. After the Site ID is obtained, every subsequent deployment is a single `make deploy-*` invocation.

---

## Actual Deployment Flow

When updating a single landing page:

```bash
# 1. Edit the HTML
vim landing/[service-A]/index.html

# 2. Deploy only that site
make deploy-service-a

# 3. Verify the live URL
# -> https://[service-a].netlify.app
```

When a release affects multiple pages simultaneously:

```bash
make deploy-all
```

Average deployment time is 10 to 15 seconds. There is no compilation, no transpilation, no asset fingerprinting. The CLI compresses the directory contents and transfers them directly to Netlify's CDN. The site is live before you finish reading the output.

This speed matters in practice. When an App Store reviewer flags that a privacy policy URL is returning 404, or a contact email address is wrong, you can push a fix in under a minute.

---

## Custom Domain Connection

Each Netlify site can be assigned a custom domain independently:

```
Company main    -> [company-domain].com
Service A       -> [service-A].[company-domain].com (subdomain)
Service B       -> Separate domain
```

DNS configuration follows a standard pattern:

```
A     @    75.2.60.5        (Netlify Load Balancer)
CNAME www  [netlify-site].netlify.app
```

Netlify provisions SSL certificates automatically via Let's Encrypt. After connecting a domain, HTTPS is active within 24 hours — typically much faster. Certificate renewal is also automatic; there is no expiry date to track.

For the subdomains pattern, Netlify's CNAME approach is cleaner than managing IP-based A records: add a CNAME pointing to `[site-name].netlify.app` and Netlify handles the rest, including certificate issuance for the subdomain.

---

## Maintenance Patterns

### Why No Shared Components

The obvious refactoring opportunity is extracting shared headers and footers. Every page has a navigation bar and a footer with the company name and contact email. Following DRY strictly, you would centralize this into a template.

The reason I did not: the pages have different designs, different deployment timing, and different content needs. A shared footer template means a change to one footer affects all pages. With landing pages that are rarely updated, this coupling provides no benefit and introduces risk. The overhead of checking that a footer change did not break seven other pages is not worth saving a few lines of HTML.

This is a case where YAGNI (You Aren't Gonna Need It) applies. The pages are not a component library — they are independent marketing assets. Copy-paste is the right tool.

The threshold for introducing shared templates would be something like: "If the shared content changes more than once a month across multiple pages simultaneously." That condition has never been true.

### Legal Page Management

App distribution platforms have specific URL requirements:

- Apple App Store: requires a URL hosted on a real domain (not an app review link)
- Google Play: requires the URL to be accessible without authentication

```
[service-A]/
├── index.html
├── privacy/
│   └── index.html    # https://[domain]/[service-A]/privacy/
└── terms/
    └── index.html    # https://[domain]/[service-A]/terms/
```

The content of each legal page is different for each app, not just a template swap. The specific data types collected, the third-party SDKs used (Firebase, Amplitude, RevenueCat), and the applicable jurisdictions vary per service. Maintaining them separately prevents accidentally publishing the wrong legal terms for an app.

---

## Pre-Deployment Checklist

Before running `make deploy-*`, work through this checklist:

```
[ ] Screenshots updated to latest app version
[ ] App Store / Play Store links verified active
[ ] Contact email address correct
[ ] Privacy / Terms pages accessible (HTTP 200, not 404)
[ ] Mobile responsive layout verified at 375px
[ ] meta description set (120-160 characters)
[ ] og:image set and loading correctly
```

The most common mistakes in practice are stale screenshots (App Store version is ahead of the landing page) and broken store links (the app was removed from review and the link is temporarily unavailable). Running through this list before every deploy takes two minutes and prevents issues that are embarrassing to fix after the fact.

---

## Scaling Considerations

This structure scales well up to approximately 15 to 20 services before the Makefile becomes unwieldy. At that point, a wrapper script that reads a list of services from a configuration file would be cleaner than explicit targets. Something like:

```bash
for service in $(cat services.txt); do
  netlify deploy --prod \
    --dir "$BASE/$service" \
    --site "$(grep "^$service " site-ids.txt | awk '{print $2}')"
done
```

But at 8 services, the explicit Makefile approach is more readable, easier to audit, and less likely to deploy the wrong thing due to a script bug.

---

## Key Takeaways

- **One repository, N Netlify sites**: The fundamental structure that makes this work. Code management is centralized; deployment is independent per service.
- **Pure HTML + Tailwind CDN**: Eliminates build tooling entirely. The simplicity is the feature, not a compromise.
- **Absolute paths in `--dir`**: Non-negotiable. Relative paths introduce environment-dependent behavior that will cause a misdeployment sooner or later.
- **Makefile over scripts**: Explicit targets are readable, auditable, and can be invoked individually or all at once.
- **No shared components**: For infrequently updated pages with divergent designs, copy-paste is lower risk than templates.
- **Legal pages are mandatory infrastructure**: `privacy/` and `terms/` subdirectories are required for App Store / Google Play distribution. Plan for them from the start.
- **Deployment time is 10-15 seconds**: The absence of a build step means fixes are live in under a minute when needed.

As apps grow, adding a new service requires: create a directory, write an `index.html`, add a Makefile target with the new Site ID, and run the deploy. There is no framework to configure, no build pipeline to extend, and no shared components to verify. The marginal cost of each new service is low and predictable.
