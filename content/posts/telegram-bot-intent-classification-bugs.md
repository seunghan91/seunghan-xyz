---
title: "Telegram 봇 의도 분류 버그 3가지와 Inline Keyboard 확인 플로우 구현"
date: 2025-06-25
draft: false
tags: ["Rails", "Telegram", "AI", "디버깅", "Ruby"]
description: "AI 기반 Telegram 봇에서 발생한 시간 파싱 오류, 완료 패턴 과잉 매칭 문제를 수정하고, 즉시 실행 방식에서 inline keyboard 확인 방식으로 UX를 개선한 과정"
cover:
  image: "/images/og/telegram-bot-intent-classification-bugs.png"
  alt: "Telegram Bot Intent Classification Bugs"
  hidden: true
---

Telegram 봇에 자연어로 할 일을 추가하는 기능을 운영하던 중 발생한 버그 3가지와, 사용자 경험 개선을 위한 inline keyboard 확인 플로우 구현 내용을 정리한다.

---

## 버그 1: "저녁9시" → 09:00(AM)으로 파싱되는 문제

### 현상

```
입력: "내일 저녁 커피챗 미팅 저녁9시일정추가"
기대: due_time = "21:00"
실제: due_time = "09:00"
```

### 원인

`extract_time_from_text` 메서드에서 패턴 체크 순서가 잘못되어 있었다.

```ruby
# 버그 코드
if match = text.match(/오후\s*(\d{1,2})시/)   # 1) 오후
  ...
end
if match = text.match(/오전\s*(\d{1,2})시/)   # 2) 오전
  ...
end
if match = text.match(/(\d{1,2})시\s*(\d{1,2})?분?/)  # 3) 숫자시 ← 여기서 "9시" 매칭
  hour = match[1].to_i  # 9 → "09:00" 반환, 아래 case/when은 도달 불가
  return "#{hour.to_s.rjust(2, '0')}:00"
end

case text
when /저녁/
  return "18:00"  # ← 절대 도달 못 함
end
```

"저녁9시"에서 `오후`, `오전` 패턴은 불일치하지만 세 번째 `/(\d{1,2})시/` 패턴이 `9시`를 잡아 `09:00`을 반환해버린다. 그 아래 `case when /저녁/`은 절대 실행되지 않는다.

### 수정

"저녁/밤 + 숫자시" 복합 패턴을 일반 숫자시 패턴보다 **먼저** 체크한다.

```ruby
if match = text.match(/오후\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12
  return "#{hour.to_s.rjust(2, '0')}:00"
end

if match = text.match(/오전\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour = 0 if hour == 12  # 오전 12시 = 00:00
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 저녁/밤 + 숫자시 → 반드시 일반 숫자시 패턴보다 먼저
if match = text.match(/(?:저녁|밤|야간)\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 그 다음 일반 숫자시
if match = text.match(/(\d{1,2})시\s*(\d{1,2})?분?/)
  ...
end
```

---

## 버그 2: 할 일 추가 요청이 완료 처리로 오분류되는 문제

### 현상

```
입력: "위의 메모와 3월 5일까지 완료 할일 추가해"
기대: intent = "task" (할 일 추가)
실제: intent = "complete_task" (완료 처리 시도)
      → 엉뚱한 다른 할 일이 완료 처리됨
```

### 원인

사전 필터링용 `completion_patterns`가 너무 greedy했다.

```ruby
# 버그 코드
completion_patterns = [
  /(.+)\s*(완료|끝|끝났|했|함|했어|끝났어|완료처리|완료해|끝내|마쳤|마침|마쳤어|체크|완료됨)/i,
  /(완료|끝|체크|했어|마쳤어|끝났어)\s*(.+)/i,
  /(\d+)\s*(번|번째)?\s*(완료|끝|체크|했어|끝났어)/i
]
```

첫 번째 패턴 `/(.+)\s*(완료|...)/i`는 텍스트에 `완료`가 어디든 포함되어 있으면 매칭된다. "완료 할일 **추가해**"처럼 완료가 목적어 위치에 쓰인 경우도 완료 처리 요청으로 분류해버린다.

세 번째 케이스도 문제였다. AI가 `complete_task`로 분류하고 task_reference로 일부 내용을 추출한 뒤, 실제 할 일 목록에서 가장 유사한 항목을 자동으로 완료 처리했다. 사용자가 전혀 의도하지 않은 할 일이 완료 처리되는 결과로 이어졌다.

### 수정

1. 할 일 추가 요청이나 취소 의도가 감지되면 completion pattern 체크를 건너뜀
2. 패턴 자체를 `$`(문장 끝 앵커)로 더 엄격하게 변경

```ruby
# 할일 추가 요청 또는 취소 의도가 있으면 completion 패턴 체크 skip
has_add_request = text.match?(/할\s*일\s*(추가|만들|생성|넣어|등록)|(추가|만들어|등록)\s*해\s*줘?/i)
has_cancel_intent = text.match?(/^취소|취소\s*해/i)

unless has_add_request || has_cancel_intent
  completion_patterns = [
    # 문장 끝에 완료동사가 오는 패턴 ($ 앵커로 엄격하게)
    /(.+)\s*(완료했어|완료됐어|완료처리해줘|끝났어|끝냈어|마쳤어|체크했어|완료됨)$/i,
    /(.+)\s+(완료|끝)\s*했?어?$/i,
    /(\d+)\s*(번|번째)?\s*(완료|끝|체크|했어|끝났어)$/i,
    /^(완료처리|완료해줘|끝내줘|체크해줘)$/i
  ]
  ...
end
```

### AI 프롬프트에도 반례 추가

패턴 매칭을 통과하더라도 AI(Gemini)가 잘못 분류할 수 있으므로 프롬프트에 명시적 반례를 추가했다.

```
- complete_task: 기존 할 일 완료 요청 ("XX 완료했어", "XX 끝났어")
  ⚠️ 중요: "완료 할일 추가해" 같이 할일 추가 요청이 포함된 경우는 complete_task가 아님!
  ⚠️ 중요: 단순히 텍스트에 "완료"라는 단어가 있다고 complete_task로 분류하지 말 것

- "위의 메모와 3월 5일까지 완료 할일 추가해" → intent: "task"
```

---

## 버그 3: "취소해방금 완료처리" 처리 실패

### 현상

```
입력: "취소해방금 완료처리"  (방금 완료처리 취소해달라는 의미)
기대: 최근 완료 처리를 되돌림
실제: "취소해방금 처리"와 일치하는 할 일을 찾을 수 없습니다.
```

### 원인

두 가지가 복합적으로 작용했다.

1. `completion_patterns`에서 "완료처리"가 먼저 매칭되어 `complete_task`로 분류됨
2. `task_reference`로 "취소해방금"이 추출되어 해당 이름의 할 일을 찾다가 실패

버그 2 수정에서 `has_cancel_intent = text.match?(/^취소|취소\s*해/i)` 체크를 추가했으므로, "취소해방금..."으로 시작하는 메시지는 completion 패턴 체크를 건너뛰게 된다.

---

## UX 개선: Inline Keyboard 확인 플로우

### 기존 방식의 문제

```
사용자 입력 → AI 분석 → 즉시 실행
```

위 버그들처럼 AI가 의도를 잘못 파악하면 되돌리기 어려운 액션(할 일 완료 처리, 엉뚱한 할 일 추가)이 즉시 실행된다.

### 새로운 방식

```
사용자 입력 → AI 분석 → inline keyboard로 확인 요청 → 버튼 클릭 → 실행
```

### Telegram Inline Keyboard 동작 원리

- 봇이 메시지에 인라인 버튼을 포함해서 전송
- 사용자가 버튼 클릭 시 Telegram이 `callback_query` 이벤트를 webhook으로 전송
- `callback_query.data`에 버튼 생성 시 설정한 문자열이 담겨 옴
- `answerCallbackQuery` API로 버튼 응답 처리 (클릭 스피너 제거)
- `editMessageText` API로 버튼 메시지를 결과 메시지로 교체

### 구현

**할 일 추가 확인:**
```ruby
def ask_task_confirmation(user, text, chat_id)
  analysis = ai_service.analyze_task_input(text, user_context)

  # pending 데이터를 캐시에 저장 (10분)
  cache_key = "telegram:confirm_task:#{user.id}:#{SecureRandom.hex(6)}"
  Rails.cache.write(cache_key, pending_data, expires_in: 10.minutes)

  short_key = cache_key.split(':').last

  inline_buttons = [[
    { text: "✅ 추가", callback_data: "task_confirm:#{user.id}:#{short_key}" },
    { text: "❌ 취소", callback_data: "task_cancel:#{user.id}:#{short_key}" }
  ]]

  send_inline_keyboard(chat_id, confirm_text, inline_buttons)
end
```

**callback_query 처리:**
```ruby
def process_message(data)
  if data['callback_query'].present?
    handle_callback_query(data['callback_query'])
  elsif data['message'].present?
    # 기존 메시지 처리
  end
end

def handle_callback_query(callback_query)
  data = callback_query['data']

  case data
  when /^task_confirm:(\d+):([a-f0-9]+)$/
    handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  when /^task_cancel:(\d+):([a-f0-9]+)$/
    Rails.cache.delete(cache_key)
    edit_message_text(chat_id, message_id, "❌ 취소되었습니다.")
  when /^complete_confirm:(\d+)$/
    handle_complete_confirm_callback(user, callback_id, chat_id, message_id, task_id)
  when /^complete_cancel:(\d+)$/
    edit_message_text(chat_id, message_id, "❌ 취소되었습니다.")
  end
end
```

**버튼 클릭 후 메시지 교체:**
```ruby
def handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  pending_data = Rails.cache.read(cache_key)
  task = user.tasks.create!(pending_data)

  answer_callback_query(callback_id, "추가 완료!")
  edit_message_text(chat_id, message_id, "✅ 추가되었습니다!\n\"#{task.content}\"#{due_info}")
end
```

### callback_data 설계 주의사항

Telegram callback_data는 **64bytes 이하** 제한이 있다. 전체 캐시 키(`telegram:confirm_task:USER_ID:HEXKEY`)를 그대로 넣으면 초과할 수 있으므로, hex 부분만 callback_data에 담고 캐시 키는 서버에서 재구성한다.

```
callback_data: "task_confirm:123:a1b2c3"  ← 짧게
서버에서 재구성: "telegram:confirm_task:123:a1b2c3"
```

### 결과

```
사용자: "내일 저녁 커피챗 미팅 저녁9시"

봇: 📝 할 일을 추가할까요? (개인일정)
    "커피챗 미팅" 📅내일 ⏰21:00
    [✅ 추가]  [❌ 취소]

사용자: [✅ 추가] 클릭

봇: ✅ 추가되었습니다!
    "커피챗 미팅" 📅내일 ⏰21:00
```

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| 저녁9시 → 09:00 | 패턴 체크 순서 오류 | 복합 패턴(저녁+숫자시)을 먼저 체크 |
| 할일추가 → 완료처리 | greedy regex | $ 앵커 + 추가 요청 exclusion |
| 취소 처리 실패 | 완료 패턴에 먼저 매칭 | cancel intent 감지 시 completion 패턴 skip |
| 즉시 실행으로 실수 | UX 설계 | inline keyboard로 확인 후 실행 |

regex 패턴 작성 시 가장 구체적인 패턴부터, 문장 끝 앵커(`$`)를 활용해 오매칭을 줄이는 것이 중요하다. AI 프롬프트에도 반례를 충분히 포함시키면 모델의 오분류를 줄이는 데 도움이 된다.
