---
title: "Render 512MB Starter에서 Rails OOM 삽질 — render.yaml이 범인이었다"
date: 2026-03-05
draft: false
tags: ["Rails", "Render", "Solid Queue", "Puma", "배포", "메모리"]
description: "puma.rb 아무리 고쳐도 OOM이 안 잡힌 이유 — render.yaml 환경변수가 코드 기본값을 덮어쓰고 있었다"
---

Rails 8 앱을 Render Starter 플랜(512MB)에 올리고 나서 주기적으로 메모리 초과로 서비스가 다운됐다. puma.rb의 스레드 수를 줄이고, queue.yml도 최적화했는데 효과가 없었다. 한참 삽질하고 나서야 진짜 원인을 찾았다.

---

## 증상

Render 대시보드에서 OOM(Out of Memory) 이벤트가 반복됨. 메모리 사용량이 512MB를 넘기면서 프로세스가 강제 종료.

---

## 첫 번째 시도 — puma.rb 수정

puma.rb의 스레드 기본값을 낮췄다.

```ruby
# config/puma.rb
threads_count = ENV.fetch("RAILS_MAX_THREADS", 2)  # 3에서 2로
threads threads_count, threads_count
workers ENV.fetch("WEB_CONCURRENCY", 1)
```

배포했는데 여전히 OOM 발생. 이상했다.

---

## 진짜 원인 — render.yaml이 코드보다 우선

render.yaml을 보니 이렇게 되어 있었다.

```yaml
envVars:
  - key: WEB_CONCURRENCY
    value: "2"
  - key: RAILS_MAX_THREADS
    value: "5"
```

**환경변수 우선순위: render.yaml > 코드 기본값**

puma.rb에서 `ENV.fetch("RAILS_MAX_THREADS", 2)`라고 써도, render.yaml이 `RAILS_MAX_THREADS=5`로 주입하면 5가 적용된다. 코드 수정은 완전히 무의미했던 것.

### 실제 메모리 계산

`WEB_CONCURRENCY=2`, `RAILS_MAX_THREADS=5` 상태에서:

| 항목 | 예상 메모리 |
|------|------------|
| Puma master | ~50MB |
| Puma worker × 2 | ~300MB |
| Solid Queue dispatcher | ~50MB |
| Solid Queue worker | ~100MB |
| **합계** | **~500MB+** |

스파이크 한 번에 512MB를 넘는 구조였다.

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

`MALLOC_ARENA_MAX=2`는 코드 변경 없이 glibc의 메모리 단편화를 줄여주는 환경변수다. Render 같은 제한된 환경에서 체감 효과가 크다.

### 최적화 후 메모리

| 항목 | 예상 메모리 |
|------|------------|
| Puma master | ~50MB |
| Puma worker × 1 | ~150MB |
| Solid Queue dispatcher | ~40MB |
| Solid Queue worker (threads=1) | ~60MB |
| **합계** | **~300MB** |

512MB에서 여유 있게 운영 가능한 수준.

---

## 보너스 — Solid Queue 크래시 루프

같은 날 다른 Rails 앱에서 `Bad Gateway`가 발생했다. 로그를 보니:

```
Solid Queue has gone away
Puma stopping...
```

Solid Queue가 죽자 Puma puma 플러그인이 이를 감지하고 Puma까지 종료하는 패턴이었다.

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

`SolidQueue::Configuration#ensure_configured_processes`가 검증에 실패하면서 Solid Queue가 `exit 1`로 죽고, Puma 플러그인이 이를 감지해 Puma도 종료. 결과적으로 Bad Gateway.

Solid Queue 설정 오류가 있거나 안정성이 중요하다면 puma.rb에서 플러그인을 비활성화하고 별도 프로세스로 분리하는 게 낫다.

```ruby
# config/puma.rb
# plugin :solid_queue if ENV["SOLID_QUEUE_IN_PUMA"]  # 주석 처리
```

---

## 정리

1. **render.yaml의 환경변수가 코드보다 우선**한다. puma.rb 기본값을 고쳐도 render.yaml에 같은 키가 있으면 의미 없다.
2. **512MB에서 WEB_CONCURRENCY=2는 위험**하다. 워커 1개 + 스레드 2개가 현실적인 최대치.
3. **MALLOC_ARENA_MAX=2**는 환경변수 하나로 메모리 단편화를 줄이는 가장 쉬운 최적화.
4. **queue.yml 들여쓰기/구조**는 런타임에 검증되므로 배포 전에 눈으로 꼼꼼히 확인해야 한다.
