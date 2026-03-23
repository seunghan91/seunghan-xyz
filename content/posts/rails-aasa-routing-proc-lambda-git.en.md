---
title: "3 Rails AASA Routing Traps: proc vs lambda, Missing Paths, Git Untracked"
date: 2025-09-03
draft: true
tags: ["Rails", "iOS", "Universal Links", "AASA", "Routing", "Debugging"]
description: "Three problems that can occur simultaneously when serving Apple App Site Association (AASA) files from Rails: proc usage, path omission, and git untracked files."
cover:
  image: "/images/og/rails-aasa-routing-proc-lambda-git.png"
  alt: "Rails Aasa Routing Proc Lambda Git"
  hidden: true
categories: ["Rails"]
---

To set up iOS Universal Links, you need to return JSON from the `/.well-known/apple-app-site-association` path. Here are three common traps when routing this in Rails, and why each one silently breaks your Universal Links.

---

## Background: How iOS Universal Links Work

iOS Universal Links are Apple's deep-linking mechanism that allows a standard HTTPS URL to open your app directly, bypassing Safari. When a user taps `https://example.com/trips/123`, if the app is installed the system opens it immediately. If not, the browser handles the URL as a normal web page.

For this to work, Apple's CDN fetches the `apple-app-site-association` file from your domain either at app installation time or on a periodic schedule. This file maps URL patterns to your app. If the file is missing, returns an error, or has the wrong content type, Universal Links silently stop working — no error message, no fallback indication, just a link that opens Safari instead of your app.

---

## The Error

```
ActionController::RoutingError (No route matches [GET] "/.well-known/apple-app-site-association"):
ActionController::RoutingError (No route matches [GET] "/apple-app-site-association"):
```

These errors repeat in deployment server logs, and Universal Links stop working in the iOS app.

At first glance this looks like a simple fix — just add a route. But in practice, three distinct problems at different layers tend to appear at the same time.

---

## Trap 1: Using proc as a Rack App

A common approach is to return the AASA file inline from the routes file using a proc.

```ruby
# Code that does not work
get "/.well-known/apple-app-site-association", to: proc {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}
```

This looks correct at a glance. It returns the proper Rack response format (`[status, headers, body]`). But it either raises an error or produces no response at all.

### Root Cause: The Rack Interface Contract

The Rack specification requires that a Rack application implement a `call(env)` method that accepts a single argument — the environment hash. This hash contains all information about the incoming request: HTTP method, headers, query string, and more. When you pass a callable directly to Rails' `to:` option, the same contract applies.

In Ruby, `proc { }` without an explicit argument list creates a callable that accepts no arguments. When Rails calls it as a Rack app via `call(env)`, the behavior is undefined or incorrect because proc does not enforce argument arity.

### proc vs lambda: A Fundamental Difference

| Property | proc | lambda |
|----------|------|--------|
| Argument count check | Lenient (extras ignored, missing become nil) | Strict (raises ArgumentError on mismatch) |
| `return` behavior | Returns from enclosing method | Returns only from itself |
| Rack app suitability | Unreliable | Safe and correct |

The key distinction is argument handling. A Rack app must receive exactly one argument. A lambda enforces this contract strictly, making it the right choice for the `to:` option.

**Fix: Switch to lambda**

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
```

The stabby lambda syntax (`->`) explicitly declares its argument list, satisfying the Rack interface reliably.

### A Simpler Alternative: Static File Serving

There is actually an even simpler approach. If you place the AASA file in `public/.well-known/`, Rails will serve it as a static file with no routing code needed. However, depending on your Nginx or CDN configuration, the `/.well-known/` path may be intercepted before reaching Rails. Explicit routing is more defensive and guarantees the correct response headers.

---

## Trap 2: Missing Path Alias

Apple can request the AASA file from two different paths:

- `/.well-known/apple-app-site-association`
- `/apple-app-site-association`

If you only route one of them, requests to the other return 404. You need to connect the same handler to both paths.

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
get "/apple-app-site-association", to: aasa_handler   # add alias
```

### Why Apple Uses Both Paths

When Universal Links were introduced at WWDC 2015, Apple recommended the `/.well-known/` path as the canonical location, following the RFC 5785 convention for well-known URIs. However, for backward compatibility with early adopters, Apple continued to support the root-level path `/apple-app-site-association` as well.

In practice, iOS versions differ in which path they attempt first. Older devices running iOS 9 through 13 tend to prefer the root path, while iOS 14 and later primarily use `/.well-known/`. Apple's CDN behavior also varies, and the official documentation does not guarantee a single canonical behavior. Routing both paths is the only safe choice.

### The Importance of Content-Type

The AASA file must be served with `Content-Type: application/json` or `application/pkcs7-mime`. If your server returns `text/plain` or omits the content type entirely, Apple's servers may reject the file during validation. This is why the lambda handler explicitly sets `"Content-Type" => "application/json"` — do not rely on the default content type inference.

---

## Trap 3: File Not Tracked by Git

If everything works locally — the file exists, routing is correct, and you can curl the endpoint — but the deployment server keeps throwing errors, the file is almost certainly not included in git.

The `public/.well-known/` directory is not part of Rails' default `.gitignore`, but manually created files remain in an untracked state until you explicitly add them.

```bash
# Check
git status
# ?? server/public/.well-known/

# Add
git add server/public/.well-known/apple-app-site-association
git commit -m "Add AASA file for Universal Links"
```

### Why This Mistake Is So Common

After creating the file locally and confirming it works, running `git add .` captures most files. But directories prefixed with a dot (`dot directories`) like `.well-known` are easy to overlook in `git status` output, especially in large repositories where the output is long.

There is another subtle variation: some Rails projects add broad rules to `.gitignore` that cover parts of `public/`. For example, if your project generates compiled assets into `public/assets/` and the gitignore rule is too broad, it might inadvertently cover `public/.well-known/` as well.

```bash
# Check whether .gitignore has rules covering public/
cat .gitignore | grep public

# Force-add if the file matches a gitignore rule
git add -f public/.well-known/apple-app-site-association
```

### Deployment Pipeline Considerations

Even after the file is committed, some CI/CD pipelines have deployment steps that skip or transform the `public/` directory. On PaaS providers like Render or Heroku, the full git repository is deployed by default, so this is usually not an issue. On custom pipelines with separate asset upload steps, verify that the `.well-known` directory is included in the deployment artifact.

---

## Final Code

```ruby
# config/routes.rb
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}
get "/.well-known/apple-app-site-association", to: aasa_handler
get "/apple-app-site-association", to: aasa_handler
```

```json
// public/.well-known/apple-app-site-association
{
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID.com.example.app"],
        "components": [
          { "/": "/trips/*" },
          { "/": "/invite/*" }
        ]
      }
    ]
  },
  "webcredentials": {
    "apps": ["TEAMID.com.example.app"]
  }
}
```

### AASA JSON Structure Explained

- `applinks.details[].appIDs`: The format is `TEAMID.BundleID`. Your Team ID comes from Apple Developer Portal, and the Bundle Identifier is the one set in your Xcode project.
- `components`: The list of URL patterns to handle. `/trips/*` matches all paths under `/trips/`. This replaces the older `paths` key, which was deprecated in iOS 15.4.
- `webcredentials`: Used for iCloud Keychain password sharing. This is independent of Universal Links and controls which apps can share credentials with your website.

Always use the `components` format for new projects. The older `paths` array syntax still works but is no longer recommended by Apple.

---

## Step-by-Step Debugging Guide

### Step 1: Confirm the file is actually being served

```bash
curl -v https://yourdomain.com/.well-known/apple-app-site-association
curl -v https://yourdomain.com/apple-app-site-association
```

Both should return HTTP 200 with valid JSON. A 404 indicates a routing problem. If the response is HTML or empty, the file path in your handler is wrong.

### Step 2: Check the Content-Type header

```bash
curl -I https://yourdomain.com/.well-known/apple-app-site-association
```

The response must include `Content-Type: application/json`. If it shows `text/plain` or is missing entirely, Apple's servers may silently discard the file.

### Step 3: Use Apple's validation tool

Apple provides the [App Search API Validation Tool](https://search.developer.apple.com/appsearch-validation-tool/) at their developer portal. Enter your domain and it will fetch the AASA file and validate its structure and content.

Third-party tools like `aasa-validator` (available as a CLI package) also work well for local or automated validation.

### Step 4: Test on a real device

Simulators do not reliably simulate Universal Link behavior. On a physical device, paste the URL into Notes and long-press it — if "Open in App" appears, the link is working. If it opens Safari instead, the AASA is not being recognized.

On iOS 16 and later, enabling Developer Mode (`Settings > Privacy & Security > Developer Mode`) gives you additional debugging options for Universal Links.

---

## Prevention Tips

### 1. Add an automated post-deploy check

```bash
#!/bin/bash
# deploy_check.sh
DOMAIN="https://yourdomain.com"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$DOMAIN/.well-known/apple-app-site-association")
if [ "$STATUS" != "200" ]; then
  echo "AASA check failed: HTTP $STATUS"
  exit 1
fi
echo "AASA check passed"
```

Add this script to your CI/CD pipeline as a post-deployment step. It will catch AASA serving failures on every deploy before they affect users.

### 2. Add error handling to the lambda

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  if file.exist?
    [200, { "Content-Type" => "application/json" }, [File.read(file)]]
  else
    Rails.logger.error("AASA file not found at #{file}")
    [404, { "Content-Type" => "text/plain" }, ["Not Found"]]
  end
}
```

Without this guard, a missing file raises `Errno::ENOENT` and Rails returns a 500 response. Returning a clean 404 and logging the error makes the failure much easier to diagnose.

### 3. Include AASA in your project initialization checklist

If a project uses Universal Links, make creating the AASA file and committing it to git an explicit step in your project setup checklist. It is easy to defer and easy to forget, and the failure mode is non-obvious since Universal Links work fine locally.

---

## Checklist

If AASA still does not work after deployment, check the following in order:

- [ ] Are you using lambda (`->`) and not proc?
- [ ] Are both paths routed? (`/.well-known/apple-app-site-association` and `/apple-app-site-association`)
- [ ] Is the AASA file added to git? (Verify with `git status`)
- [ ] After deployment, does `curl https://yourdomain.com/.well-known/apple-app-site-association` return JSON?
- [ ] Is the Content-Type header `application/json`?
- [ ] Does the `appIDs` field in the JSON contain the correct Team ID?
- [ ] Have you validated the file structure with Apple's validation tool?

---

## Key Takeaways

- When passing a Rack app to Rails' `to:` option, always use a **lambda** with an explicit `env` argument. A plain `proc` does not satisfy the Rack interface and will fail unpredictably.
- Apple requests the AASA file from **two paths** — `/.well-known/apple-app-site-association` and `/apple-app-site-association`. Route both to the same handler, or Universal Links will fail on some iOS versions.
- If the endpoint works locally but fails after deployment, check for **untracked git files** first. The `public/.well-known/` directory is easy to create locally and forget to commit, since dot directories are easy to miss in `git status` output.
- All three traps can be present simultaneously, and any single one is enough to break Universal Links entirely. After every deployment, verify the endpoint with `curl` and check the Content-Type header before testing on device.
