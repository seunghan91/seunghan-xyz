---
title: "Rails AASA 라우팅 3가지 함정: proc vs lambda, 경로 누락, git 미추적"
date: 2025-09-03
draft: true
tags: ["Rails", "iOS", "Universal Links", "AASA", "라우팅", "디버깅"]
description: "Rails에서 Apple App Site Association(AASA) 파일을 서빙할 때 proc 사용, 경로 누락, git 미추적 3가지 문제가 동시에 발생할 수 있다. 각각의 원인과 수정 방법을 정리한다."
cover:
  image: "/images/og/rails-aasa-routing-proc-lambda-git.png"
  alt: "Rails Aasa Routing Proc Lambda Git"
  hidden: true
categories: ["Rails"]
---

iOS 유니버설 링크(Universal Links)를 설정하려면 `/.well-known/apple-app-site-association` 경로에서 JSON을 반환해야 한다. Rails에서 이걸 라우팅할 때 흔히 빠지는 함정 3가지를 정리한다.

---

## 배경: iOS 유니버설 링크란?

iOS 유니버설 링크는 일반 HTTP(S) URL을 앱으로 직접 열 수 있게 해주는 Apple의 딥링크 메커니즘이다. 사용자가 `https://example.com/trips/123` 같은 URL을 탭하면, 앱이 설치된 경우 Safari를 거치지 않고 앱이 직접 열린다. 앱이 없으면 일반 웹 페이지로 fallback된다.

이를 위해 Apple 서버(정확히는 CDN)는 앱 설치 시점 또는 특정 주기로 해당 도메인의 `apple-app-site-association` 파일을 가져가서 앱과 URL 패턴을 매핑한다. 이 파일이 올바르게 서빙되지 않으면 유니버설 링크는 조용히 작동을 멈춘다.

---

## 에러

```
ActionController::RoutingError (No route matches [GET] "/.well-known/apple-app-site-association"):
ActionController::RoutingError (No route matches [GET] "/apple-app-site-association"):
```

배포 서버 로그에서 이 에러가 반복되고, iOS 앱에서 유니버설 링크가 동작하지 않는다.

증상만 보면 단순히 라우팅을 추가하면 해결될 것 같다. 하지만 실제로는 서로 다른 레이어에서 발생하는 3가지 문제가 동시에 얽혀 있는 경우가 많다.

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

이 코드는 얼핏 보면 문제 없어 보인다. Rack 응답 형식(`[status, headers, body]`)을 올바르게 반환하고 있으니까. 그런데 실제로 실행하면 에러가 발생하거나, 아무 응답도 내려가지 않는다.

### 원인: Rack 인터페이스 요구사항

Rack 명세에 따르면 Rack 앱(app)은 반드시 `call(env)` 메서드를 구현해야 한다. Rails 라우팅에서 `to:` 옵션에 callable을 직접 넣을 때도 동일한 규칙이 적용된다. `env`는 요청 정보(HTTP 메서드, 헤더, 쿼리스트링 등)를 담은 해시로, Rack 앱은 이 인자를 받아야만 인터페이스를 만족한다.

Ruby에서 `proc { }` 블록은 인자를 명시하지 않으면 인자를 받지 않는 callable이 된다. `call(env)` 를 호출하면 `env`를 무시하고 실행되는 것처럼 보이지만, Rails 내부에서 이를 Rack 앱으로 검증할 때 실패하거나, 예상치 못한 방식으로 동작한다.

반면 `proc { |env| }` 처럼 인자를 명시하면 어느 정도 동작하는 것처럼 보일 수 있다. 하지만 proc과 lambda는 인자 처리 방식에서 근본적인 차이가 있다.

### proc vs lambda 핵심 차이

| 특성 | proc | lambda |
|------|------|--------|
| 인자 개수 검사 | 느슨함 (초과/부족 허용) | 엄격함 (불일치 시 ArgumentError) |
| return 동작 | 외부 메서드까지 return | 자신의 스코프에서만 return |
| Rack 앱으로 사용 | 인터페이스 불안정 | 안전하게 동작 |

Rack 앱은 정확히 하나의 인자(`env`)를 받아야 한다. lambda는 이 인자 개수를 엄격하게 관리하기 때문에 Rack 인터페이스에 적합하다.

**수정: lambda로 변경**

```ruby
aasa_handler = ->(env) {
  file = Rails.root.join("public/.well-known/apple-app-site-association")
  [200, { "Content-Type" => "application/json" }, [File.read(file)]]
}

get "/.well-known/apple-app-site-association", to: aasa_handler
```

`->` (stabby lambda 문법)는 인자를 명시적으로 받으므로 Rack 앱으로 안전하게 동작한다.

### 더 나은 대안: 정적 파일 서빙

사실 이 방식보다 훨씬 간단한 방법이 있다. AASA 파일을 `public/.well-known/` 디렉토리에 두면 Rails가 정적 파일로 자동 서빙한다. 별도 라우팅이 필요 없다. 단, Nginx나 CDN 설정에 따라 `.well-known` 경로가 Rails까지 도달하지 않고 차단되는 경우가 있어서 라우팅을 명시하는 방식이 더 안전한 경우도 있다.

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

### Apple이 두 경로를 모두 사용하는 이유

WWDC 2015에서 유니버설 링크가 도입될 때, Apple은 `/.well-known/` 경로를 권장했지만 하위 호환성을 위해 루트 경로(`/apple-app-site-association`)도 지원했다. 이후 iOS 버전에 따라, 그리고 Apple CDN의 캐싱 동작에 따라 어떤 경로를 먼저 시도하는지 달라질 수 있다.

iOS 9~13 구버전 기기에서는 루트 경로를 주로 사용하는 경향이 있고, iOS 14 이후에는 `/.well-known/` 경로를 우선시한다는 보고가 있다. 정확한 동작은 Apple 문서에도 명확히 명시되어 있지 않으므로, 두 경로 모두 라우팅하는 것이 가장 안전하다.

### Content-Type 헤더 중요성

AASA 파일은 반드시 `application/json` 또는 `application/pkcs7-mime` Content-Type으로 서빙되어야 한다. 일부 서버 설정에서 `.well-known` 파일을 `text/plain`으로 내려보내면 Apple 서버가 파일을 파싱하지 못한다. 위의 lambda 핸들러에서 `"Content-Type" => "application/json"` 을 명시하는 것이 이 때문이다.

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

### 왜 이 실수를 자주 하는가

개발자가 로컬에서 파일을 생성하고, 라우팅 테스트까지 마친 후 `git add .`을 실행하면 대부분의 파일은 포함된다. 하지만 `.well-known` 같은 숨겨진 디렉토리(`dot directory`)는 `git status` 출력에서 눈에 잘 띄지 않아 지나치기 쉽다.

또한 일부 프로젝트에서는 `public/` 디렉토리 하위 파일 중 생성된 에셋(CSS, JS 등)을 gitignore에 추가해 놓기도 한다. 이 경우 `public/` 전체를 ignore하는 규칙이 있을 수 있으므로 반드시 확인이 필요하다.

```bash
# .gitignore에 public/ 관련 규칙이 있는지 확인
cat .gitignore | grep public

# force add (gitignore에 포함된 경우)
git add -f public/.well-known/apple-app-site-association
```

### 배포 환경에서의 추가 확인

git에 추가했더라도 배포 파이프라인 설정에 따라 `public/` 디렉토리가 배포에서 제외될 수 있다. Render, Heroku 같은 PaaS에서는 일반적으로 git 저장소 전체가 배포되므로 문제없지만, 커스텀 CI/CD 파이프라인에서 `public/` 디렉토리를 별도로 처리하는 경우라면 배포 스크립트도 확인해야 한다.

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

### AASA 파일 JSON 구조 설명

- `applinks.details[].appIDs`: `TEAMID.BundleID` 형식. Apple Developer Portal의 팀 ID와 앱의 Bundle Identifier를 조합한다.
- `components`: URL 패턴 목록. `/trips/*` 는 `/trips/` 하위 모든 경로를 매핑한다.
- `webcredentials`: iCloud Keychain의 비밀번호 공유에 사용. 유니버설 링크와 별개로 설정한다.

iOS 15.4 이후부터는 `components` 배열 방식을 사용해야 한다. 이전의 `paths` 방식은 deprecated되었으므로 새 프로젝트에서는 `components`를 쓰는 것이 좋다.

---

## 디버깅 단계별 가이드

### 1단계: 서버에서 파일이 실제로 반환되는지 확인

```bash
curl -v https://yourdomain.com/.well-known/apple-app-site-association
curl -v https://yourdomain.com/apple-app-site-association
```

두 경로 모두 200 응답과 올바른 JSON을 반환해야 한다. 404면 라우팅 문제, 파일 내용이 비어있거나 HTML이 반환되면 파일 경로 문제다.

### 2단계: Content-Type 헤더 확인

```bash
curl -I https://yourdomain.com/.well-known/apple-app-site-association
```

`Content-Type: application/json` 이어야 한다. `text/plain` 이거나 헤더가 없으면 Apple 서버가 거부할 수 있다.

### 3단계: Apple의 AASA 유효성 검사 도구 사용

Apple은 [App Search API Validation Tool](https://search.developer.apple.com/appsearch-validation-tool/)을 제공한다. 도메인을 입력하면 AASA 파일을 가져와서 형식과 내용을 검증해준다.

또는 `aasa-validator` 같은 서드파티 도구도 있다.

### 4단계: 기기에서 직접 테스트

시뮬레이터는 유니버설 링크를 제대로 테스트하기 어렵다. 실 기기에서 Notes 앱에 URL을 붙여넣고 길게 눌러 "Open in App"이 나타나는지 확인하는 것이 가장 확실하다.

iOS 16 이후에는 개발자 모드(`설정 > 개인정보 보호 및 보안 > 개발자 모드`)를 활성화하면 유니버설 링크 테스트가 더 쉬워진다.

---

## 예방 팁

### 1. 배포 직후 자동 검증 스크립트 추가

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

CI/CD 파이프라인에 이 스크립트를 배포 후 단계에 추가하면, 배포할 때마다 AASA 서빙 여부를 자동으로 검증할 수 있다.

### 2. lambda 핸들러에 에러 처리 추가

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

파일이 없을 때 500 에러가 아닌 명시적인 404를 반환하고 로그를 남기면 디버깅이 훨씬 쉬워진다.

### 3. 새 프로젝트 체크리스트에 AASA 포함

유니버설 링크를 사용하는 프로젝트라면 프로젝트 초기 설정 단계에서 AASA 파일 생성과 git 추가를 체크리스트에 넣어두는 것이 좋다. 나중에 기억에서 빠질 가능성이 높다.

---

## 체크리스트

배포 후에도 AASA가 안 된다면 아래를 순서대로 확인한다.

- [ ] lambda(`->`)를 쓰고 있는가 (proc이 아닌지)
- [ ] 두 경로 모두 라우팅되어 있는가
- [ ] AASA 파일이 git에 추가되어 있는가 (`git status`로 확인)
- [ ] 배포 후 `curl https://yourdomain.com/.well-known/apple-app-site-association`으로 JSON이 반환되는가
- [ ] Content-Type이 `application/json`인가
- [ ] AASA JSON 내 `appIDs`에 올바른 Team ID가 들어가 있는가
- [ ] Apple 검증 도구로 파일 형식을 확인했는가

---

## Key Takeaways

- Rails 라우팅의 `to:` 옵션에 Rack 앱을 넘길 때는 반드시 `env` 인자를 받는 **lambda**를 써야 한다. `proc`은 Rack 인터페이스를 만족하지 못한다.
- Apple은 AASA 파일을 **두 경로**(`/.well-known/apple-app-site-association`, `/apple-app-site-association`)에서 모두 요청하므로, 두 경로에 같은 핸들러를 연결해야 한다.
- 로컬에서 동작해도 배포 서버에서 실패한다면 **git 미추적** 파일일 가능성을 먼저 의심한다. `public/.well-known/` 같은 숨겨진 디렉토리는 `git add`를 빠뜨리기 쉽다.
- 세 가지 문제 중 하나만 있어도 유니버설 링크가 완전히 작동하지 않으므로, 배포 후 반드시 `curl`로 실제 응답을 검증하는 습관을 들이는 것이 중요하다.
