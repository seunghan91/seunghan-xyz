---
title: "Rails AASA 라우팅 3가지 함정: proc vs lambda, 경로 누락, git 미추적"
date: 2026-02-25
draft: false
tags: ["Rails", "iOS", "Universal Links", "AASA", "라우팅", "디버깅"]
description: "Rails에서 Apple App Site Association(AASA) 파일을 서빙할 때 proc 사용, 경로 누락, git 미추적 3가지 문제가 동시에 발생할 수 있다. 각각의 원인과 수정 방법을 정리한다."
---

iOS 유니버설 링크(Universal Links)를 설정하려면 `/.well-known/apple-app-site-association` 경로에서 JSON을 반환해야 한다. Rails에서 이걸 라우팅할 때 흔히 빠지는 함정 3가지를 정리한다.

---

## 에러

```
ActionController::RoutingError (No route matches [GET] "/.well-known/apple-app-site-association"):
ActionController::RoutingError (No route matches [GET] "/apple-app-site-association"):
```

배포 서버 로그에서 이 에러가 반복되고, iOS 앱에서 유니버설 링크가 동작하지 않는다.

---

## 함정 1: proc을 Rack 앱으로 사용

Rails routes에서 inline으로 파일을 반환하려고 proc을 쓰는 경우가 있다.

```ruby
# 동작하지 않는 코드
get "/.well-known/apple-app-site-association", to: proc {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}
```

Rails 라우팅에서 `to:` 옵션에 Rack 앱을 직접 넣을 때는 `env` 인자를 받는 callable이어야 한다. `proc { }` 블록은 인자 없이 정의되어 있어서 Rack 인터페이스를 만족하지 못한다.

**수정: lambda로 변경**

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
```

`->` (lambda)는 인자를 명시적으로 받으므로 Rack 앱으로 동작한다.

---

## 함정 2: 경로 alias 누락

Apple은 AASA 파일을 두 경로에서 모두 요청할 수 있다.

- `/.well-known/apple-app-site-association`
- `/apple-app-site-association`

하나만 라우팅하면 나머지 경로로 요청이 들어올 때 404가 발생한다. 같은 핸들러를 두 경로에 모두 연결해야 한다.

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
get "/apple-app-site-association", to: aasa_handler   # alias 추가
```

---

## 함정 3: 파일이 git에 추적되지 않음

로컬에서는 파일이 있고 라우팅도 맞아서 잘 되는데, 배포 서버에서는 계속 에러가 난다면 파일이 git에 포함되지 않은 경우다.

`public/.well-known/` 디렉토리는 gitignore에 명시하지 않아도 Rails 기본 gitignore에 포함되지는 않지만, 직접 생성한 파일을 add하지 않으면 untracked 상태로 남는다.

```bash
# 확인
git status
# ?? server/public/.well-known/

# 추가
git add server/public/.well-known/apple-app-site-association
git commit -m "Add AASA file for Universal Links"
```

---

## 최종 코드

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

## 체크리스트

배포 후에도 AASA가 안 된다면 아래를 순서대로 확인한다.

- [ ] lambda(`->`)를 쓰고 있는가 (proc이 아닌지)
- [ ] 두 경로 모두 라우팅되어 있는가
- [ ] AASA 파일이 git에 추가되어 있는가 (`git status`로 확인)
- [ ] 배포 후 `curl https://yourdomain.com/.well-known/apple-app-site-association`으로 JSON이 반환되는가
