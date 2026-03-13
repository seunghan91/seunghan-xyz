---
title: "3 Rails AASA Routing Traps: proc vs lambda, Missing Paths, Git Untracked"
date: 2025-09-03
draft: false
tags: ["Rails", "iOS", "Universal Links", "AASA", "Routing", "Debugging"]
description: "Three problems that can occur simultaneously when serving Apple App Site Association (AASA) files from Rails: proc usage, path omission, and git untracked files."
cover:
  image: "/images/og/rails-aasa-routing-proc-lambda-git.png"
  alt: "Rails Aasa Routing Proc Lambda Git"
  hidden: true
---


To set up iOS Universal Links, you need to return JSON from the `/.well-known/apple-app-site-association` path. Here are three common traps when routing this in Rails.

---

## Error

```
ActionController::RoutingError (No route matches [GET] "/.well-known/apple-app-site-association"):
ActionController::RoutingError (No route matches [GET] "/apple-app-site-association"):
```

This error repeats in deployment server logs, and Universal Links do not work in the iOS app.

---

## Trap 1: Using proc as a Rack App

Sometimes a proc is used to return a file inline from Rails routes.

```ruby
# Code that does not work
get "/.well-known/apple-app-site-association", to: proc {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}
```

When passing a Rack app directly to the `to:` option in Rails routing, it must be a callable that accepts an `env` argument. A `proc { }` block defined without arguments does not satisfy the Rack interface.

**Fix: Change to lambda**

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
```

`->` (lambda) explicitly accepts arguments, so it works as a Rack app.

---

## Trap 2: Missing Path Alias

Apple can request the AASA file from both paths:

- `/.well-known/apple-app-site-association`
- `/apple-app-site-association`

If you only route one, requests to the other path will return 404. You need to connect the same handler to both paths.

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
get "/apple-app-site-association", to: aasa_handler   # add alias
```

---

## Trap 3: File Not Tracked by Git

If everything works locally -- the file exists and routing is correct -- but the deployment server keeps throwing errors, it is likely that the file is not included in git.

The `public/.well-known/` directory is not included in Rails' default gitignore, but if you do not explicitly add a manually created file, it remains in an untracked state.

```bash
# Check
git status
# ?? server/public/.well-known/

# Add
git add server/public/.well-known/apple-app-site-association
git commit -m "Add AASA file for Universal Links"
```

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

---

## Checklist

If AASA still does not work after deployment, check the following in order:

- [ ] Are you using lambda (`->`) and not proc?
- [ ] Are both paths routed?
- [ ] Is the AASA file added to git? (Check with `git status`)
- [ ] After deployment, does `curl https://yourdomain.com/.well-known/apple-app-site-association` return JSON?
