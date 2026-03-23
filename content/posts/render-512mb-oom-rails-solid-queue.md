---
title: "Render 512MB Starter에서 Rails OOM 삽질 — render.yaml이 범인이었다"
date: 2026-01-13
draft: true
tags: ["Rails", "Render", "Solid Queue", "Puma", "배포", "메모리"]
description: "puma.rb 아무리 고쳐도 OOM이 안 잡힌 이유 — render.yaml 환경변수가 코드 기본값을 덮어쓰고 있었다"
cover:
  image: "/images/og/render-512mb-oom-rails-solid-queue.png"
  alt: "Render 512Mb Oom Rails Solid Queue"
  hidden: true
categories: ["Rails"]
---

Rails 8 앱을 Render Starter 플랜(512MB)에 올리고 나서 주기적으로 메모리 초과로 서비스가 다운됐다. puma.rb의 스레드 수를 줄이고, queue.yml도 최적화했는데 효과가 없었다. 한참 삽질하고 나서야 진짜 원인을 찾았다.

---

## 증상

Render 대시보드에서 OOM(Out of Memory) 이벤트가 반복됐다. 메모리 사용량이 512MB를 넘기면서 프로세스가 강제 종료됐고, Render가 자동으로 재시작했지만 몇 분 후 다시 같은 패턴이 반복됐다. 트래픽이 없어도 일정 시간이 지나면 메모리가 계속 늘어나다 결국 터지는 형태였다.

Render의 메트릭 뷰에서 보면 메모리가 서서히 상승하다 512MB 직전에서 수직으로 떨어지는 패턴 — 프로세스가 죽고 재시작하는 전형적인 OOM 그래프다.

---

## 첫 번째 시도 — puma.rb 수정

가장 먼저 의심한 건 Puma 설정이었다. 기본값으로 스레드가 많이 열려있으면 각 스레드가 메모리를 점유하니까, 스레드 수를 줄이는 게 정석 접근이다.

```ruby
# config/puma.rb
threads_count = ENV.fetch("RAILS_MAX_THREADS", 2)  # 3에서 2로 줄임
threads threads_count, threads_count
workers ENV.fetch("WEB_CONCURRENCY", 1)
```

배포하고 모니터링했다. 여전히 OOM 발생. 코드를 분명히 바꿨는데 아무 변화가 없으니 더 혼란스러웠다.

두 번째로 Solid Queue 설정도 확인했다. threads 수를 줄이고, 큐 폴링 간격을 늘렸다. 마찬가지로 효과 없었다.

---

## 진짜 원인 — render.yaml이 코드보다 우선

두어 시간 삽질하다 문득 render.yaml을 확인했다. 프로젝트 초기에 설정하고 잊고 있었던 파일이었다.

```yaml
envVars:
  - key: WEB_CONCURRENCY
    value: "2"
  - key: RAILS_MAX_THREADS
    value: "5"
```

바로 이게 원인이었다.

**환경변수 우선순위: render.yaml(외부 주입) > 코드 기본값**

`ENV.fetch("RAILS_MAX_THREADS", 2)`는 환경변수가 없을 때만 `2`를 쓴다. render.yaml이 `RAILS_MAX_THREADS=5`를 주입하면 코드 기본값은 완전히 무시된다. 아무리 puma.rb를 고쳐도 render.yaml의 값이 살아있는 한 반영될 리 없었다.

이건 Rails나 Puma만의 문제가 아니라 12-Factor App의 환경변수 원칙 자체다. 프로세스는 코드가 아니라 환경에서 설정을 읽는다. Render는 이 방식으로 컨테이너에 환경변수를 주입하기 때문에, render.yaml에 명시된 값이 코드 기본값보다 항상 우선한다.

### 실제 메모리 계산

`WEB_CONCURRENCY=2`, `RAILS_MAX_THREADS=5` 상태에서 메모리를 계산해보면:

| 항목 | 예상 메모리 |
|------|------------|
| Puma master | ~50MB |
| Puma worker × 2 | ~300MB |
| Solid Queue dispatcher | ~50MB |
| Solid Queue worker | ~100MB |
| **합계** | **~500MB+** |

안정 상태에서 이미 500MB 수준이다. 여기서 메모리 스파이크가 한 번이라도 발생하면 512MB를 넘어 프로세스가 종료된다. 이게 왜 주기적으로 터졌는지 설명이 된다.

Rails 앱은 ActiveRecord 쿼리, 이메일 렌더링, 파일 처리 등 여러 작업에서 순간적으로 메모리 사용이 급등할 수 있다. 512MB 제한 환경에서 500MB를 기본으로 깔고 있으면 안전 마진이 사실상 0이다.

---

## 해결 — render.yaml 수정

```yaml
envVars:
  - key: WEB_CONCURRENCY
    value: "1"
  - key: RAILS_MAX_THREADS
    value: "2"
  - key: MALLOC_ARENA_MAX
    value: "2"
```

`MALLOC_ARENA_MAX=2`는 코드 변경 없이 glibc의 메모리 단편화를 줄여주는 환경변수다. glibc는 기본적으로 CPU 코어 수에 비례해 메모리 아레나(arena)를 여러 개 만드는데, 컨테이너 환경에서는 이 수를 제한하지 않으면 실제로는 한 프로세스에서만 사용하는 메모리가 여러 아레나로 분산되어 OS에 반환이 안 되는 문제가 생긴다. `MALLOC_ARENA_MAX=2`로 제한하면 메모리 단편화가 줄고 실효 메모리 사용량이 눈에 띄게 감소한다.

### 최적화 후 메모리

| 항목 | 예상 메모리 |
|------|------------|
| Puma master | ~50MB |
| Puma worker × 1 | ~150MB |
| Solid Queue dispatcher | ~40MB |
| Solid Queue worker (threads=1) | ~60MB |
| **합계** | **~300MB** |

512MB 한도에서 200MB 여유가 생겼다. 웬만한 메모리 스파이크는 흡수할 수 있는 수준이다.

---

## 디버깅 팁 — 실제 메모리를 어떻게 확인할까

render.yaml을 수정하기 전에 실제 메모리 사용 현황을 파악하는 것이 중요하다.

**Render 대시보드**: 서비스 → Metrics 탭에서 메모리 그래프를 확인할 수 있다. 어느 시간대에 OOM이 발생하는지 패턴을 파악하는 데 유용하다.

**Rails 콘솔에서 직접 확인**:
```ruby
# 현재 프로세스 메모리
puts `ps -o rss= -p #{Process.pid}`.to_i / 1024
# => MB 단위 메모리 출력
```

**Render SSH로 확인** (유료 플랜):
```bash
# 실행 중인 Ruby 프로세스 메모리 전체 확인
ps aux | grep ruby
```

**환경변수 확인** — 배포된 서버에서 실제 어떤 값이 적용되고 있는지:
```ruby
# Rails 콘솔
puts ENV["RAILS_MAX_THREADS"]
puts ENV["WEB_CONCURRENCY"]
puts ENV["MALLOC_ARENA_MAX"]
```

render.yaml을 수정했다면 반드시 재배포 후 이 값들이 올바르게 반영됐는지 확인해야 한다.

---

## 보너스 — Solid Queue 크래시 루프

같은 날 다른 Rails 앱에서 `Bad Gateway`가 발생했다. 로그를 보니:

```
Solid Queue has gone away
Puma stopping...
```

Solid Queue가 죽자 Puma 플러그인이 이를 감지하고 Puma까지 종료하는 패턴이었다.

원인은 `config/queue.yml` 구조 오류였다.

```yaml
# 잘못된 구조 — dispatchers가 workers 안에 중첩됨
production:
  workers:
    - queues: [default]
      dispatchers:
        polling_interval: 1

# 올바른 구조
production:
  dispatchers:
    - polling_interval: 1
      batch_size: 500
  workers:
    - queues: [default]
      threads: 1
```

`SolidQueue::Configuration#ensure_configured_processes`가 검증에 실패하면서 Solid Queue가 `exit 1`로 죽고, Puma 플러그인이 이를 감지해 Puma도 종료됐다. 결과적으로 Bad Gateway.

### Puma 플러그인 의존성 끊기

Solid Queue 설정에 오류가 있거나 큐 처리가 잠깐 멈춰도 웹 서버는 살아있어야 한다면, Puma 플러그인 연동을 끊고 별도 프로세스로 분리하는 것이 더 안전하다.

```ruby
# config/puma.rb
# plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]  # 주석 처리
```

그리고 render.yaml에 Solid Queue를 별도 worker 서비스로 추가한다:

```yaml
services:
  - type: web
    name: myapp-web
    env: ruby
    buildCommand: bundle exec rails assets:precompile
    startCommand: bundle exec puma -C config/puma.rb

  - type: worker
    name: myapp-worker
    env: ruby
    startCommand: bundle exec rails solid_queue:start
    envVars:
      - key: RAILS_MAX_THREADS
        value: "1"
```

이렇게 분리하면 Solid Queue가 죽어도 웹 서버는 영향을 받지 않는다. 단, Render에서 worker 서비스는 별도 요금이 발생한다.

512MB Starter 플랜이라면 별도 worker를 뛰우는 것 자체가 부담이 되므로, 플러그인 방식을 유지하되 queue.yml 구조를 꼼꼼히 검증하는 것이 현실적인 선택이다.

---

## 정리

1. **render.yaml의 환경변수가 코드보다 우선**한다. puma.rb 기본값을 고쳐도 render.yaml에 같은 키가 있으면 의미 없다. 설정 변경 후에는 반드시 배포된 환경에서 실제 환경변수 값을 확인하라.
2. **512MB에서 WEB_CONCURRENCY=2는 위험**하다. 워커 1개 + 스레드 2개가 현실적인 최대치이며, 안정 메모리를 300MB 이하로 유지해야 스파이크를 흡수할 수 있다.
3. **MALLOC_ARENA_MAX=2**는 환경변수 하나로 메모리 단편화를 줄이는 가장 쉬운 최적화다. Ruby + Puma 환경에서 거의 부작용 없이 메모리를 아낄 수 있다.
4. **queue.yml 들여쓰기/구조**는 런타임에 검증되므로 배포 전에 눈으로 꼼꼼히 확인해야 한다. `dispatchers`는 `workers`와 같은 레벨에 있어야 한다.
5. **Solid Queue + Puma 플러그인 조합**은 편리하지만, Solid Queue가 죽으면 웹 서버도 같이 죽는다. 안정성이 중요하다면 별도 프로세스로 분리하는 것을 고려하라.

---

## Key Takeaways

- Render에서 환경변수를 수정할 때는 대시보드의 Environment 탭과 render.yaml 양쪽을 반드시 확인해야 한다. 둘 다 설정되어 있으면 render.yaml이 우선한다.
- 512MB 플랜에서 Rails + Solid Queue를 안정적으로 운영하려면 `WEB_CONCURRENCY=1`, `RAILS_MAX_THREADS=2`, `MALLOC_ARENA_MAX=2` 조합이 검증된 출발점이다.
- OOM 디버깅 시 코드보다 환경변수를 먼저 확인하라. 특히 `rails s` 로컬과 Render 배포 환경이 다르게 동작한다면 환경변수 불일치를 의심해야 한다.
