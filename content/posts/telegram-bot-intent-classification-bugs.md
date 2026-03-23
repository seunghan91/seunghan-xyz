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

이 봇의 기본 동작 방식은 다음과 같다. 사용자가 자유 형식 문자열을 입력하면, Rails 백엔드가 먼저 정규식 기반 사전 필터를 거쳐 의도를 추측하고, 이후 Gemini AI를 호출해 최종 intent와 파라미터(날짜, 시간, 내용 등)를 추출한다. 이 2단계 구조에서 각 단계에 버그가 하나씩 숨어 있었고, 그 결과가 예상치 못한 방식으로 결합되어 사용자가 의도하지 않은 동작을 일으켰다.

---

## 버그 1: "저녁9시" → 09:00(AM)으로 파싱되는 문제

### 현상

```
입력: "내일 저녁 커피챗 미팅 저녁9시일정추가"
기대: due_time = "21:00"
실제: due_time = "09:00"
```

한국어에서는 "저녁9시"처럼 시간대 수식어와 숫자를 붙여 쓰는 경우가 흔하다. "오후"나 "오전" 대신 "저녁", "밤", "야간" 같은 표현이 더 자연스럽게 쓰이기도 한다. 이 입력을 처리하는 `extract_time_from_text` 메서드에서 패턴 우선순위가 잘못 설계되어 있었다.

### 원인

패턴 체크 순서가 잘못되어 있었다. 메서드는 위에서부터 순서대로 패턴을 검사하다가 처음 매칭되는 시점에 값을 반환한다. 문제는 "저녁"이나 "밤" 같은 한국어 시간대 수식어를 처리하는 `case/when` 블록이 일반 숫자시 패턴보다 **뒤에** 위치하고 있었다는 점이다.

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

이 문제의 핵심은 **패턴 우선순위 설계 실수**다. 더 구체적인 패턴(저녁+숫자시)이 더 일반적인 패턴(숫자시) 뒤에 위치하면, 구체적인 패턴은 절대 실행되지 않는다. 정규식 기반 파싱에서 흔히 발생하는 실수다.

### 수정

"저녁/밤 + 숫자시" 복합 패턴을 일반 숫자시 패턴보다 **먼저** 체크한다. 가장 구체적인 패턴이 항상 앞에 와야 한다는 원칙을 적용했다.

```ruby
# 1) 오후 + 숫자시
if match = text.match(/오후\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 2) 오전 + 숫자시 (오전 12시는 00:00)
if match = text.match(/오전\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour = 0 if hour == 12  # 오전 12시 = 00:00
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 3) 저녁/밤/야간 + 숫자시 → 반드시 일반 숫자시 패턴보다 먼저
if match = text.match(/(?:저녁|밤|야간)\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12  # 저녁 9시 → 21시
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 4) 일반 숫자시 (수식어 없음, 맨 마지막에)
if match = text.match(/(\d{1,2})시\s*(\d{1,2})?분?/)
  hour = match[1].to_i
  minute = match[2]&.to_i || 0
  return "#{hour.to_s.rjust(2, '0')}:#{minute.to_s.rjust(2, '0')}"
end
```

이 수정으로 "저녁9시"는 3번 패턴에 매칭되어 `21:00`을 반환하게 된다. 수식어가 없는 "9시"만 입력된 경우에는 4번 패턴이 처리한다.

---

## 버그 2: 할 일 추가 요청이 완료 처리로 오분류되는 문제

### 현상

```
입력: "위의 메모와 3월 5일까지 완료 할일 추가해"
기대: intent = "task" (할 일 추가)
실제: intent = "complete_task" (완료 처리 시도)
      → 엉뚱한 다른 할 일이 완료 처리됨
```

이 버그는 단순한 잘못된 분류를 넘어, 사용자가 전혀 의도하지 않은 기존 할 일이 완료 처리되는 파괴적인 결과를 낳았다.

### 원인

사전 필터링용 `completion_patterns`가 너무 greedy했다. 이 패턴들은 AI를 호출하기 전에 빠른 사전 분류를 목적으로 설계된 것인데, 문장 내 단어 위치나 문법적 역할을 전혀 고려하지 않고 단순히 키워드 존재 여부만 확인했다.

```ruby
# 버그 코드
completion_patterns = [
  /(.+)\s*(완료|끝|끝났|했|함|했어|끝났어|완료처리|완료해|끝내|마쳤|마침|마쳤어|체크|완료됨)/i,
  /(완료|끝|체크|했어|마쳤어|끝났어)\s*(.+)/i,
  /(\d+)\s*(번|번째)?\s*(완료|끝|체크|했어|끝났어)/i
]
```

첫 번째 패턴 `/(.+)\s*(완료|...)/i`는 텍스트에 `완료`가 어디든 포함되어 있으면 매칭된다. "완료 할일 **추가해**"처럼 완료가 목적어 위치에 쓰인 경우도 완료 처리 요청으로 분류해버린다.

한국어의 특성상 동사가 문장 끝에 오고 명사구가 앞에 오는 SOV 구조이기 때문에, 문장 끝에 어떤 동사가 왔는지를 보지 않고 중간에 등장한 키워드만 보면 이런 오분류가 생긴다. "완료 할일 추가해"에서 실제 의도를 나타내는 동사는 가장 끝의 "추가해"인데, 패턴이 중간의 "완료"에 걸려버린 것이다.

세 번째 케이스도 문제였다. AI가 `complete_task`로 분류하고 `task_reference`로 일부 내용을 추출한 뒤, 실제 할 일 목록에서 가장 유사한 항목을 자동으로 완료 처리했다. 사용자가 전혀 의도하지 않은 할 일이 완료 처리되는 결과로 이어졌다.

### 수정

두 가지 방향으로 수정했다.

1. 할 일 추가 요청이나 취소 의도가 감지되면 completion pattern 체크를 건너뜀 (exclusion 우선)
2. 패턴 자체를 `$`(문장 끝 앵커)로 더 엄격하게 변경 — 완료 동사가 반드시 문장 끝에 와야만 매칭

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
  # completion_patterns 검사 진행
end
```

`$` 앵커를 추가함으로써 완료 동사가 문장 끝에 위치할 때만 매칭된다. "완료 할일 추가해"는 끝이 "추가해"이므로 어느 패턴에도 걸리지 않는다.

### AI 프롬프트에도 반례 추가

패턴 매칭을 통과하더라도 AI(Gemini)가 잘못 분류할 수 있으므로 프롬프트에 명시적 반례를 추가했다. 모델은 학습 데이터 기반으로 동작하기 때문에 "완료"라는 단어가 있으면 완료 처리 의도로 편향될 수 있다. 반례를 명시하면 이 편향을 억제하는 데 도움이 된다.

```
- complete_task: 기존 할 일 완료 요청 ("XX 완료했어", "XX 끝났어")
  ⚠️ 중요: "완료 할일 추가해" 같이 할일 추가 요청이 포함된 경우는 complete_task가 아님!
  ⚠️ 중요: 단순히 텍스트에 "완료"라는 단어가 있다고 complete_task로 분류하지 말 것

- "위의 메모와 3월 5일까지 완료 할일 추가해" → intent: "task"
```

프롬프트에 반례를 넣는 것은 few-shot prompting의 일종으로, 경계 케이스를 명시적으로 학습시키는 효과가 있다. 특히 한국어처럼 문법 구조가 영어와 다른 언어에서는 이런 명시적 안내가 분류 정확도를 크게 높인다.

---

## 버그 3: "취소해방금 완료처리" 처리 실패

### 현상

```
입력: "취소해방금 완료처리"  (방금 완료처리 취소해달라는 의미)
기대: 최근 완료 처리를 되돌림
실제: "취소해방금 처리"와 일치하는 할 일을 찾을 수 없습니다.
```

모바일에서 빠르게 타이핑하다 보면 띄어쓰기 없이 붙여 쓰는 경우가 자주 발생한다. "취소해 방금 완료처리"를 붙여 쓴 이 입력이 전혀 다른 방식으로 파싱되었다.

### 원인

두 가지가 복합적으로 작용했다.

1. `completion_patterns`에서 "완료처리"가 먼저 매칭되어 `complete_task`로 분류됨
2. `task_reference`로 "취소해방금"이 추출되어 해당 이름의 할 일을 찾다가 실패

즉, 봇은 "취소해방금"이라는 이름의 할 일을 완료 처리하라는 요청으로 해석했다. 실제로는 방금 한 완료 처리를 취소해달라는 요청이었는데, 파서가 문장 전체의 의도를 파악하지 못하고 중간에 등장한 "완료처리"에 먼저 반응했다.

### 수정

버그 2 수정에서 추가한 `has_cancel_intent = text.match?(/^취소|취소\s*해/i)` 체크가 이 케이스도 함께 해결한다. "취소해방금..."으로 시작하는 메시지는 `^취소` 패턴에 매칭되어 completion 패턴 검사를 건너뛰게 된다.

이후 AI에게 전달되면, "취소해방금 완료처리"는 최근 완료 처리를 되돌리는 `undo_complete` 또는 `cancel` intent로 올바르게 분류된다.

이 버그는 버그 2의 수정이 단순히 해당 케이스만 고친 것이 아니라, 취소 의도가 담긴 더 넓은 범위의 입력을 올바르게 처리하는 방향으로 설계되었기 때문에 자연스럽게 해결됐다.

---

## UX 개선: Inline Keyboard 확인 플로우

### 기존 방식의 문제

```
사용자 입력 → AI 분석 → 즉시 실행
```

위 버그들처럼 AI나 패턴 매처가 의도를 잘못 파악하면 되돌리기 어려운 액션(할 일 완료 처리, 엉뚱한 할 일 추가)이 즉시 실행된다. 버그를 완전히 없애는 것은 불가능하기 때문에, 사용자가 실행 전에 의도를 확인할 수 있는 단계를 추가하는 것이 근본적인 해결책이다.

### 새로운 방식

```
사용자 입력 → AI 분석 → inline keyboard로 확인 요청 → 버튼 클릭 → 실행
```

AI가 파악한 결과를 먼저 사용자에게 보여주고 확인을 받는다. 잘못 파악했을 경우 취소 버튼으로 아무 일도 일어나지 않게 한다.

### Telegram Inline Keyboard 동작 원리

Telegram의 inline keyboard는 메시지에 인터랙티브 버튼을 붙이는 기능이다. 일반 reply keyboard와 달리 메시지 바로 아래에 붙고, 사용자가 버튼을 눌러도 채팅창에 별도 메시지가 생기지 않는다.

동작 흐름:
- 봇이 `reply_markup`에 `inline_keyboard` 배열을 포함해서 메시지를 전송
- 사용자가 버튼 클릭 시 Telegram이 `callback_query` 이벤트를 webhook으로 전송
- `callback_query.data`에 버튼 생성 시 설정한 문자열이 담겨 옴
- `answerCallbackQuery` API로 버튼 응답 처리 (클릭 시 나타나는 로딩 스피너 제거 — 이걸 안 하면 스피너가 계속 돌아 UX가 나빠짐)
- `editMessageText` API로 버튼이 달린 메시지를 최종 결과 메시지로 교체

### 구현

**할 일 추가 확인 요청:**
```ruby
def ask_task_confirmation(user, text, chat_id)
  analysis = ai_service.analyze_task_input(text, user_context)

  # AI가 파싱한 결과를 pending 데이터로 캐시에 저장 (10분)
  # 사용자가 확인 버튼을 누를 때까지 DB에 저장하지 않음
  cache_key = "telegram:confirm_task:#{user.id}:#{SecureRandom.hex(6)}"
  Rails.cache.write(cache_key, pending_data, expires_in: 10.minutes)

  # callback_data는 64bytes 제한이 있으므로 hex 부분만 사용
  short_key = cache_key.split(':').last

  inline_buttons = [[
    { text: "✅ 추가", callback_data: "task_confirm:#{user.id}:#{short_key}" },
    { text: "❌ 취소", callback_data: "task_cancel:#{user.id}:#{short_key}" }
  ]]

  send_inline_keyboard(chat_id, confirm_text, inline_buttons)
end
```

pending 데이터를 Rails.cache에 저장하고, 사용자가 확인 버튼을 눌렀을 때 비로소 DB에 저장한다. 취소하거나 10분이 지나면 캐시가 자동으로 만료되어 아무 일도 일어나지 않는다.

**callback_query 수신 및 분기 처리:**
```ruby
def process_message(data)
  if data['callback_query'].present?
    # 버튼 클릭 이벤트 처리 (일반 메시지와 별도 분기)
    handle_callback_query(data['callback_query'])
  elsif data['message'].present?
    # 일반 텍스트 메시지 처리
    handle_text_message(data['message'])
  end
end

def handle_callback_query(callback_query)
  callback_id = callback_query['id']    # answerCallbackQuery에 필요
  chat_id = callback_query['message']['chat']['id']
  message_id = callback_query['message']['message_id']  # editMessageText에 필요
  data = callback_query['data']

  case data
  when /^task_confirm:(\d+):([a-f0-9]+)$/
    user_id, short_key = $1, $2
    user = User.find(user_id)
    handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  when /^task_cancel:(\d+):([a-f0-9]+)$/
    user_id, short_key = $1, $2
    cache_key = "telegram:confirm_task:#{user_id}:#{short_key}"
    Rails.cache.delete(cache_key)
    answer_callback_query(callback_id)
    edit_message_text(chat_id, message_id, "❌ 취소되었습니다.")
  when /^complete_confirm:(\d+)$/
    task_id = $1.to_i
    handle_complete_confirm_callback(user, callback_id, chat_id, message_id, task_id)
  when /^complete_cancel:(\d+)$/
    answer_callback_query(callback_id)
    edit_message_text(chat_id, message_id, "❌ 취소되었습니다.")
  end
end
```

**버튼 확인 후 실제 저장 처리:**
```ruby
def handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  cache_key = "telegram:confirm_task:#{user.id}:#{short_key}"
  pending_data = Rails.cache.read(cache_key)

  if pending_data.nil?
    # 캐시 만료(10분 초과) 또는 이미 처리된 경우
    answer_callback_query(callback_id, "요청이 만료되었습니다. 다시 입력해주세요.")
    return
  end

  task = user.tasks.create!(pending_data)
  Rails.cache.delete(cache_key)  # 처리 후 캐시 삭제

  due_info = task.due_at ? " 📅#{task.due_at.strftime('%m/%d')} ⏰#{task.due_at.strftime('%H:%M')}" : ""
  answer_callback_query(callback_id, "추가 완료!")
  edit_message_text(chat_id, message_id, "✅ 추가되었습니다!\n\"#{task.content}\"#{due_info}")
end
```

캐시가 만료된 경우를 명시적으로 처리하는 것이 중요하다. 사용자가 10분 뒤에 버튼을 누르면 graceful하게 처리해야 한다.

### callback_data 설계 주의사항

Telegram callback_data는 **64bytes 이하** 제한이 있다. 전체 캐시 키(`telegram:confirm_task:USER_ID:HEXKEY`)를 그대로 넣으면 초과할 수 있으므로, hex 부분만 callback_data에 담고 캐시 키는 서버에서 재구성한다.

```
callback_data: "task_confirm:123:a1b2c3"  ← 짧게 유지
서버에서 재구성: "telegram:confirm_task:123:a1b2c3"
```

이 패턴은 보안 측면에서도 유리하다. callback_data만 봐서는 캐시 키 전체를 알 수 없기 때문에, 악의적인 사용자가 다른 사용자의 pending 데이터에 접근하기 어렵다. 실제로는 user_id를 callback_data에 포함시키고 서버에서 해당 user의 요청인지 검증하는 로직도 추가하는 것이 좋다.

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

AI가 "저녁9시"를 21:00으로 정확하게 파싱했고, 사용자가 확인 후 저장하는 플로우가 자연스럽게 동작한다.

---

## 정리

| 문제 | 원인 | 해결 |
|------|------|------|
| 저녁9시 → 09:00 | 패턴 체크 순서 오류 | 복합 패턴(저녁+숫자시)을 먼저 체크 |
| 할일추가 → 완료처리 | greedy regex | $ 앵커 + 추가 요청 exclusion |
| 취소 처리 실패 | 완료 패턴에 먼저 매칭 | cancel intent 감지 시 completion 패턴 skip |
| 즉시 실행으로 실수 | UX 설계 | inline keyboard로 확인 후 실행 |

---

## 핵심 교훈

**1. 정규식 패턴은 구체적인 것이 앞에 와야 한다.**
일반적인 패턴이 먼저 오면 구체적인 패턴은 절대 실행되지 않는다. `저녁9시` 버그는 이 원칙을 어긴 결과였다. 패턴을 작성할 때는 항상 "이 앞 패턴이 이 입력을 먼저 잡아가지는 않을까?"를 확인해야 한다.

**2. 문장 끝 앵커(`$`)로 greedy 매칭을 막아라.**
한국어는 SOV 구조라 의도를 나타내는 동사가 항상 문장 끝에 온다. `$` 앵커를 활용하면 중간에 관련 키워드가 등장해도 실제 의도 동사를 기준으로 분류할 수 있다.

**3. Exclusion 조건을 먼저 적용하라.**
"추가해"나 "취소해"처럼 의도를 명확히 드러내는 표현이 있으면 다른 패턴 검사를 건너뛰는 것이 정확도를 높인다. 무엇을 하려는지 명확한 케이스를 먼저 처리하고, 나머지에 대해 ambiguous한 패턴을 적용하는 방식이 효과적이다.

**4. AI 프롬프트에 반례를 충분히 포함하라.**
모델은 학습 데이터의 분포를 반영하기 때문에 경계 케이스에서 예측 가능한 방식으로 실패한다. 실제로 발생한 오분류 케이스를 프롬프트에 명시적 반례로 추가하면 같은 실수가 반복되지 않는다. 버그를 수정할 때 코드만 고치지 말고 프롬프트도 함께 업데이트하는 습관이 중요하다.

**5. 되돌리기 어려운 액션에는 확인 단계를 넣어라.**
AI 파싱이 아무리 잘 동작해도 100% 정확하지는 않다. 완료 처리나 삭제처럼 되돌리기 어려운 액션에는 반드시 확인 단계를 추가해야 한다. Telegram의 inline keyboard는 이런 패턴을 구현하기에 적합한 도구다.
