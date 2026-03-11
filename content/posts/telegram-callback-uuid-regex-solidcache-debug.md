---
title: "Telegram 봇 Inline Keyboard 버튼이 무반응인 버그 — UUID Regex + Solid Cache 디버깅"
date: 2026-03-11
draft: false
tags: ["Rails", "Telegram", "디버깅", "Ruby", "Regex", "Cache"]
description: "Telegram 봇의 확인 버튼을 눌러도 아무 반응이 없는 버그를 추적한 과정. \\d+ 정규식이 UUID를 매칭 못 하는 문제와, Solid Cache write/read 추적을 위한 디버그 로그 추가까지."
---

Telegram 봇에서 자연어 입력 → AI 분석 → Inline Keyboard 확인 버튼 방식으로 할 일을 추가하는 기능을 운영하던 중, 버튼을 눌러도 아무 반응이 없는 증상이 발생했다.

---

## 증상

사용자가 자연어로 일정을 입력하면 봇이 다음처럼 확인 메시지를 보낸다.

```
📝 할 일을 추가할까요? (개인일정)
"부장님 점심식사" [📅03/24 ⏰12:00]

[✅ 추가]  [❌ 취소]
```

그런데 `[✅ 추가]` 버튼을 눌러도 응답이 없었다. Telegram 클라이언트에는 "알 수 없는 요청입니다." 라는 토스트 메시지만 표시됐다.

---

## 서버 로그 확인

서버 쪽 webhook 로그를 보면 버튼 클릭은 정상적으로 서버에 도달하고 있었다.

```
POST /api/telegram/webhook → 200 OK in 312ms (1 ActiveRecord query)
```

그런데 AR 쿼리가 **1개**밖에 없었다. 확인 버튼 처리 로직이 실행됐다면 최소 2~3개의 쿼리(사용자 조회 + 캐시 읽기 + 태스크 생성)가 찍혔어야 했다.

---

## 원인 분석

### callback_data 구조

Inline Keyboard의 `callback_data`는 이런 형식으로 구성돼 있다.

```
task_confirm:{user_id}:{short_key}
```

예시:
```
task_confirm:8a6a34fa-aeff-4d33-95b2-880727a23be5:53604d77d97d
```

### 문제의 정규식

콜백 핸들러에서 이 데이터를 파싱하는 `case/when` 패턴이 이렇게 돼 있었다.

```ruby
case data
when /^task_confirm:(\d+):([a-f0-9]+)$/
  _user_id, short_key = $1, $2
  handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
# ...
else
  answer_callback_query(callback_id, "알 수 없는 요청입니다.")
end
```

**`\d+`는 숫자만 매칭한다.** 그런데 `user_id`가 UUID 형식(`8a6a34fa-aeff-4d33-95b2-880727a23be5`)이라 하이픈(`-`)이 포함되어 있어서 정규식이 매칭에 실패했다.

결과적으로 `else` 브랜치로 떨어져 "알 수 없는 요청입니다."를 반환하고 끝났던 것이다.

---

## 수정

`\d+` → `[a-f0-9-]+`로 변경하고 `/i` 플래그를 추가해 대소문자를 무시하도록 했다.

```ruby
# Before (broken)
when /^task_confirm:(\d+):([a-f0-9]+)$/

# After (fixed)
when /^task_confirm:([a-f0-9-]+):([a-f0-9]+)$/i
```

`task_cancel`도 동일한 패턴을 사용하므로 함께 수정했다.

```ruby
when /^task_cancel:([a-f0-9-]+):([a-f0-9]+)$/i
```

---

## 어떻게 처음부터 잘못됐나

초기 구현 당시에는 `user_id`를 정수 ID(auto-increment)로 설계했을 가능성이 높다. 이후 어느 시점에 UUID 기반으로 전환하면서 `callback_data`의 `user_id` 부분도 UUID가 됐는데, 정규식은 그대로 남아 있었던 것이다.

이런 류의 버그는 평소에는 조용하다가 특정 조건(여기선 UUID 포함 콜백)에서만 터진다. 로그에 에러도 안 찍힌다—그냥 `else` 브랜치를 타고 조용히 실패한다.

---

## 배포 후에도 오류가 남아 있는 경우

정규식 수정 후 배포를 하고 새 메시지를 보내서 새 확인 버튼을 받았는데, 이번엔 "오류가 발생했습니다." 메시지가 나왔다.

이건 다른 문제다. 정규식은 이제 매칭을 하는데, 그 뒤 로직(캐시 읽기 또는 태스크 생성)에서 예외가 발생하고 있다는 뜻이다.

로그를 더 자세히 찍어보기로 했다.

---

## Solid Cache 추적을 위한 디버그 로깅 추가

Rails의 `config/cache_store`를 `solid_cache_store`로 쓰는 경우, 캐시 읽기/쓰기가 DB 쿼리로 실행된다. 그런데 production 로그에서 캐시 관련 쿼리가 보이지 않아 실제로 write가 성공했는지 확인이 필요했다.

확인 메시지 생성 시 캐시 write 결과를 로그로 찍도록 수정했다.

```ruby
write_result = Rails.cache.write(cache_key, pending_data, expires_in: 10.minutes)
Rails.logger.info "[Bot] cache write key=#{cache_key} result=#{write_result}"
```

확인 버튼 처리 핸들러에도 단계별 로그를 추가했다.

```ruby
def handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  cache_key = "..."
  Rails.logger.info "[Bot] reading cache key=#{cache_key}"
  pending_data = Rails.cache.read(cache_key)
  Rails.logger.info "[Bot] pending_data=#{pending_data.inspect}"

  unless pending_data
    Rails.logger.warn "[Bot] cache miss for key=#{cache_key}"
    # ...
    return
  end

  # ...
  task = user.tasks.create!(...)
  Rails.logger.info "[Bot] task created id=#{task.id}"
rescue => e
  Rails.logger.error "[Bot] failed: #{e.message}\n#{e.backtrace.first(5).join("\n")}"
  # ...
end
```

이 로그가 찍히면 다음 세 가지 경우 중 어디서 멈추는지 바로 알 수 있다.

| 상황 | 로그 |
|------|------|
| 캐시 write 실패 | `result=false` |
| 캐시 miss | `cache miss for key=...` |
| 태스크 생성 실패 | `failed: ...` + backtrace |

---

## 교훈

### 1. `callback_data`에 user ID를 넣을 때 타입을 확인하라

UUID는 정수가 아니다. `\d+`로 파싱하면 UUID가 포함된 콜백은 조용히 실패한다. 처음 설계할 때부터 `[a-f0-9-]+`나 `\S+`처럼 넉넉하게 잡는 게 낫다.

### 2. `else` 브랜치 실패는 에러 로그가 없다

`answer_callback_query(callback_id, "알 수 없는 요청입니다.")`는 에러가 아니라 정상 처리로 취급된다. Rails 에러 로그에 아무것도 안 찍힌다. 증상은 클라이언트에서만 보인다.

### 3. Solid Cache는 DB 기반이라 별도 인프라가 없어도 됩지만, write 실패 시 조용히 넘어간다

`Rails.cache.write`의 반환값은 `true/false`다. 실패해도 예외를 던지지 않는다. 중요한 데이터를 캐시에 쓸 때는 반환값을 체크하거나 write 결과를 로그에 남겨두는 게 좋다.

### 4. AR 쿼리 카운트로 코드 경로를 역추적할 수 있다

로그에 `1 ActiveRecord query`만 찍혔을 때, 이게 "사용자 조회 1개뿐"이라는 의미임을 파악하면서 캐시 읽기나 태스크 생성에 도달하지 못했다는 걸 추론할 수 있었다. 쿼리 카운트는 꽤 유용한 단서다.
