---
title: "배포는 됐는데 앱이 죽는다 — Solid Queue가 Puma를 끌고 내려간 이야기"
date: 2026-03-10
draft: false
tags: ["Rails", "Render", "SolidQueue", "Puma", "배포", "디버깅"]
description: "Render에 Rails 앱을 배포했더니 인스턴스가 계속 죽었다. 원인은 Solid Queue 플러그인의 Ruby truthy 체크 버그 하나였다. 그리고 render.yaml 최소화 빌드 구성까지 정리한 기록."
categories: ["Rails"]
---

Render에 Rails 앱을 새로 배포했다. 빌드는 성공했고 "Deploy live" 메시지도 떴다.

그런데 몇 분 뒤 대시보드에 이런 메시지가 반복됐다.

```
Instance failed: wcvg7
Application exited early while running your code.
```

---

## 증상 파악

Render 로그를 뒤지니 이런 흐름이 보였다.

```
SolidQueue::Configuration#ensure_configured_processes  ← 여기서 에러
→ exit 1
→ "Detected Solid Queue has gone away, stopping Puma..."
→ Puma 종료
→ 인스턴스 실패
```

Puma가 죽은 게 아니었다. **Solid Queue가 먼저 죽고, Puma가 그걸 감지해서 스스로 내려간 것**이었다.

`solid_queue` Puma 플러그인에는 Solid Queue 프로세스가 사라지면 Puma도 같이 종료하는 로직이 있다. 덕분에 좀비 Puma가 남지 않는다는 장점이 있지만, 반대로 Solid Queue 하나 잘못되면 서버 전체가 죽는다.

---

## 원인: Ruby의 truthy 함정

`config/puma.rb`를 열었더니 이렇게 되어 있었다.

```ruby
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]
```

언뜻 보면 문제가 없어 보인다. `SOLID_QUEUE_IN_PUMA` 환경변수가 설정되어 있을 때만 로드하겠다는 의도다.

그런데 Render 환경변수 설정을 보니 이렇게 되어 있었다.

```yaml
- key: SOLID_QUEUE_IN_PUMA
  value: "false"
```

**Ruby에서 `"false"` 문자열은 truthy다.**

`if ENV["SOLID_QUEUE_IN_PUMA"]`는 환경변수가 존재하기만 하면 `"true"`든 `"false"`든 무조건 플러그인을 로드한다. 비활성화할 의도로 `"false"`를 넣었지만, 오히려 Solid Queue가 돌아가게 된 것이다.

그리고 Solid Queue가 로드됐지만 `config/solid_queue.yml`이 제대로 없거나, queue DB 연결이 안 되거나 하면 `ensure_configured_processes`에서 예외가 터지고 프로세스가 죽는다.

---

## 수정

한 줄 수정이었다.

```ruby
# 수정 전
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]

# 수정 후
plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"] == "true"
```

`== "true"` 명시적 비교로 바꾸니까 `"false"`, `"0"`, 미설정 등 어떤 경우에도 의도대로 동작한다.

---

## 같은 패턴, 다른 곳에도

이 버그는 Rails 8 기본 생성 코드에서 자주 보인다. `rails new` 로 만들면 기본 `puma.rb`에 이 코드가 들어간다. 개발 초기에 그냥 쓰다가 배포할 때 환경변수를 잘못 넣으면 그대로 맞는다.

Solid Queue를 Puma 안에서 쓸 계획이 없다면 아예 주석 처리하는 게 깔끔하다.

```ruby
# Solid Queue를 Puma 외부에서 별도 실행하는 경우 아래 줄 비활성화
# plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"] == "true"
```

---

## render.yaml 최소화 빌드 구성 정리

이번 기회에 `render.yaml`도 정리했다. 기존에는 `render-build.sh`에서 DB 마이그레이션까지 다 돌리고 있었다.

```bash
# 기존 render-build.sh (잘못된 방식)
bundle install
bundle exec rails assets:precompile
bundle exec rails db:migrate   # ← 빌드 단계에서 DB 작업은 안 된다
```

Render의 빌드 단계는 코드와 에셋을 준비하는 단계다. 이때는 DB가 아직 준비 안 됐을 수 있고, 여러 인스턴스가 동시에 빌드를 실행하면 마이그레이션 충돌이 생길 수 있다.

마이그레이션은 `preDeployCommand`로 분리해야 한다. Render는 배포 직전에 단 한 번, 단일 인스턴스에서 실행해준다.

```bash
# 수정 후 render-build.sh
bundle install
bundle exec rails assets:precompile
```

```yaml
# render.yaml
services:
  - type: web
    name: my-app
    runtime: ruby
    region: singapore
    plan: starter
    buildCommand: "./bin/render-build.sh"
    preDeployCommand: "bundle exec rails db:migrate"
    startCommand: "bin/rails server -b 0.0.0.0 -p $PORT"
    healthCheckPath: /up
    envVars:
      - key: RAILS_MASTER_KEY
        sync: false
      - key: SECRET_KEY_BASE
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: my-app-db
          property: connectionString
      - key: SOLID_QUEUE_IN_PUMA
        value: "true"
      - key: WEB_CONCURRENCY
        value: "1"
      - key: RAILS_MAX_THREADS
        value: "3"
```

`startCommand`도 `bundle exec rails server` 대신 `bin/rails server -b 0.0.0.0 -p $PORT`로 바꿨다. `-b 0.0.0.0`이 없으면 Render가 헬스체크를 못 뚫는다.

---

## 타임라인 정리

```
12:47 PM — Solid Queue 크래시 (ensure_configured_processes 실패)
12:50 PM — Puma 연쇄 종료 (Solid Queue gone away 감지)
12:53 PM — 수정 버전 배포 완료 (truthy 체크 → == "true" 수정)
12:57 PM — Render 대시보드에 "Instance failed" 이벤트 표시 (지연 리포트)
01:03 PM — 두 번째 "Instance failed" 이벤트 표시 (동일 크래시의 지연 보고)
```

12:57, 1:03 PM의 실패 이벤트는 실제 크래시가 Render 대시보드에 늦게 반영된 것이라 이미 수정된 후였다. 처음엔 배포 후에도 실패가 뜨는 줄 알고 패닉했지만 로그 타임스탬프를 확인하니 아니었다.

---

## 정리

- `if ENV["VAR"]` 패턴은 Ruby에서 값과 무관하게 환경변수 존재 여부만 체크한다
- Solid Queue on/off 제어는 반드시 `== "true"` 명시적 비교로
- Render `render-build.sh`에서 DB 작업 제거, `preDeployCommand`로 분리
- `startCommand`에 `-b 0.0.0.0 -p $PORT` 명시 필수
- Render 인스턴스 실패 이벤트는 실제 크래시보다 수 분 늦게 표시될 수 있음
