---
title: "3 Telegram Bot Intent Classification Bugs and Inline Keyboard Confirmation Flow"
date: 2025-06-25
draft: false
tags: ["Rails", "Telegram", "AI", "Debugging", "Ruby"]
description: "Fixing time parsing errors and over-matching completion patterns in an AI-based Telegram bot, and improving UX from immediate execution to inline keyboard confirmation."
cover:
  image: "/images/og/telegram-bot-intent-classification-bugs.png"
  alt: "Telegram Bot Intent Classification Bugs"
  hidden: true
---

While running a Telegram bot that lets users add tasks through natural language input, I ran into three separate bugs and then improved the overall UX by introducing an inline keyboard confirmation step. This post walks through each bug, its root cause, and how it was fixed.

The bot's basic architecture works like this: a user sends a free-form message, the Rails backend first applies a regex-based pre-filter to make a quick guess at intent, and then calls Gemini AI to extract the final intent along with parameters (date, time, content, etc.). This two-stage pipeline is where each bug was hiding, and the results combined in unexpected ways that caused unintended actions for users.

---

## Bug 1: "Evening 9pm" Parsed as 09:00 (AM)

### Symptom

```
Input:    "Tomorrow evening coffee chat meeting evening9pm"
Expected: due_time = "21:00"
Actual:   due_time = "09:00"
```

In Korean, it is natural to write time expressions like "evening9pm" (저녁9시) as a single compound phrase — a time-of-day modifier immediately followed by a number. The `extract_time_from_text` method that handled these expressions had a flaw in its pattern priority design.

### Cause

The pattern checks were evaluated in the wrong order. The method works by checking patterns from top to bottom and returning as soon as the first one matches. The problem was that the `case/when` block for Korean time-of-day modifiers like "evening" (저녁) and "night" (밤) was placed **after** the generic numeric hour pattern, making it unreachable.

```ruby
# Buggy code
if match = text.match(/오후\s*(\d{1,2})시/)   # 1) "PM" + hour
  ...
end
if match = text.match(/오전\s*(\d{1,2})시/)   # 2) "AM" + hour
  ...
end
if match = text.match(/(\d{1,2})시\s*(\d{1,2})?분?/)  # 3) bare number + hour marker
  hour = match[1].to_i  # matches "9" -> returns "09:00", unreachable below
  return "#{hour.to_s.rjust(2, '0')}:00"
end

case text
when /저녁/    # "evening"
  return "18:00"  # <- never reached
end
```

For the input "evening9pm" (저녁9시), neither the "PM" nor "AM" patterns match, but the third pattern `/(\d{1,2})시/` catches `9시` and immediately returns `09:00`. The `case when /저녁/` block below it is dead code — it can never execute.

This is the classic **pattern priority mistake** in regex-based parsing. When a more general pattern appears before a more specific one, the specific pattern never fires. In this case, `bare number + hour` was more general than `evening modifier + number + hour`, but the general pattern came first.

### Fix

Move the compound "evening/night + number" pattern **before** the bare numeric hour pattern. The most specific patterns must always come first.

```ruby
# 1) Explicit "PM" marker + hour
if match = text.match(/오후\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 2) Explicit "AM" marker + hour (midnight edge case: AM 12 = 00:00)
if match = text.match(/오전\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour = 0 if hour == 12
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 3) Evening/night modifier + hour — MUST come before the bare numeric pattern
if match = text.match(/(?:저녁|밤|야간)\s*(\d{1,2})시/)
  hour = match[1].to_i
  hour += 12 if hour < 12  # evening 9 -> 21
  return "#{hour.to_s.rjust(2, '0')}:00"
end

# 4) Bare numeric hour, no modifier (last resort)
if match = text.match(/(\d{1,2})시\s*(\d{1,2})?분?/)
  hour = match[1].to_i
  minute = match[2]&.to_i || 0
  return "#{hour.to_s.rjust(2, '0')}:#{minute.to_s.rjust(2, '0')}"
end
```

With this fix, "evening9pm" (저녁9시) hits pattern 3 and returns `21:00`. A bare "9pm" with no modifier falls through to pattern 4.

---

## Bug 2: A Task-Add Request Misclassified as Task Completion

### Symptom

```
Input:    "Add a task to complete the memo above by March 5th"
Expected: intent = "task"         (add a new task)
Actual:   intent = "complete_task" (mark an existing task as done)
          -> A completely unrelated task gets marked complete
```

This bug went beyond a simple misclassification — it caused a destructive outcome where a task the user never intended to touch was silently marked as complete.

### Cause

The pre-filter `completion_patterns` were too greedy. These patterns were designed for quick pre-classification before calling the AI, but they made no attempt to understand where in the sentence a keyword appeared or what grammatical role it played.

```ruby
# Buggy code
completion_patterns = [
  /(.+)\s*(완료|끝|끝났|했|함|했어|끝났어|완료처리|완료해|끝내|마쳤|마침|마쳤어|체크|완료됨)/i,
  /(완료|끝|체크|했어|마쳤어|끝났어)\s*(.+)/i,
  /(\d+)\s*(번|번째)?\s*(완료|끝|체크|했어|끝났어)/i
]
```

The first pattern `/(.+)\s*(complete|...)/i` matches any text that contains the keyword "complete" (완료) anywhere in the string. This means "add a **complete** task" — where "complete" is used as an adjective modifying "task" — gets flagged as a completion request.

Korean follows Subject-Object-Verb (SOV) word order, so the verb that expresses the actual intent always comes at the very end of the sentence. Looking only at whether a keyword exists somewhere in the middle of the sentence, without anchoring to the end, will inevitably produce these false positives. In "add a complete task" (완료 할일 추가해), the intent verb is "add" (추가해) at the end, but the pattern fires on "complete" (완료) in the middle.

The downstream effect was also severe. Once the AI model classified the input as `complete_task`, it extracted a `task_reference` string and then automatically completed the most similar task in the user's list. A task the user had no intention of completing got quietly checked off.

### Fix

Two changes were applied together:

1. If a task-add request or a cancel intent is detected, skip the completion pattern check entirely (exclusion takes priority)
2. Make the patterns themselves stricter by anchoring to the end of the string with `$` — completion verbs must appear at the very end to match

```ruby
# Skip completion pattern check if an add request or cancel intent is detected
has_add_request = text.match?(/할\s*일\s*(추가|만들|생성|넣어|등록)|(추가|만들어|등록)\s*해\s*줘?/i)
has_cancel_intent = text.match?(/^취소|취소\s*해/i)

unless has_add_request || has_cancel_intent
  completion_patterns = [
    # Completion verb must appear at the end of the sentence ($ anchor)
    /(.+)\s*(완료했어|완료됐어|완료처리해줘|끝났어|끝냈어|마쳤어|체크했어|완료됨)$/i,
    /(.+)\s+(완료|끝)\s*했?어?$/i,
    /(\d+)\s*(번|번째)?\s*(완료|끝|체크|했어|끝났어)$/i,
    /^(완료처리|완료해줘|끝내줘|체크해줘)$/i
  ]
  # proceed with completion_patterns check
end
```

With the `$` anchor in place, "add a complete task" (완료 할일 추가해) no longer matches any pattern because the sentence ends with "add" (추가해), not a completion verb.

### Adding Counter-Examples to the AI Prompt

Even after the regex pre-filter is fixed, the AI model can still misclassify. Counter-examples were added directly to the system prompt to steer the model away from this edge case.

```
- complete_task: user requests marking an existing task as done ("XX is done", "finished XX")
  ⚠️ Important: if the message contains a task-add request like "add a complete task", it is NOT complete_task!
  ⚠️ Important: do not classify as complete_task just because the word "complete" appears anywhere in the text

- "Add a task to complete the memo above by March 5th" -> intent: "task"
```

Adding counter-examples to the prompt is a form of few-shot prompting that explicitly teaches the model where the classification boundary lies. This is especially effective for languages like Korean where word order differs significantly from English — the model's training distribution may not cover all the edge cases well.

---

## Bug 3: "Cancel the completion I just did" Handled Incorrectly

### Symptom

```
Input:    "cancelthatjustcompletion"  (typed without spaces: "cancel that just-completed action")
Expected: Undo the most recent task completion
Actual:   "cancelthatjust action" — no matching task found
```

On mobile, users often type quickly and omit spaces. "Cancel the just-completed action" was typed as a single run-on string, and the parser interpreted it in an entirely unexpected way.

### Cause

Two issues compounded each other:

1. The `completion_patterns` matched "completion" (완료처리) and classified the whole message as `complete_task`
2. "cancelthat" (취소해방금) was extracted as the `task_reference`, and the bot tried to find a task with that name — and naturally failed

In other words, the bot read the input as: "Please mark the task named 'cancelthat' as complete." The user actually wanted to undo a previous completion action, but the parser reacted to "completion" (완료처리) in the middle of the string before it could understand the overall intent.

### Fix

The `has_cancel_intent` check added in Bug 2 — `text.match?(/^취소|취소\s*해/i)` — resolves this case automatically. A message starting with "cancel" (취소해...) matches the `^취소` anchor and skips the completion pattern check entirely.

Once forwarded to the AI model, "cancelthatjustcompletion" gets correctly classified as an `undo_complete` or `cancel` intent.

This fix demonstrates the value of designing exclusion conditions broadly. The cancel intent check wasn't written just to handle one specific input; it covers the entire class of inputs where the user's stated intent is cancellation, regardless of what other keywords appear in the message.

---

## UX Improvement: Inline Keyboard Confirmation Flow

### The Problem with Immediate Execution

```
User input -> AI analysis -> immediate execution
```

When the AI or pattern matcher misreads the intent — as in all three bugs above — irreversible actions (marking a task complete, adding the wrong task) execute immediately with no opportunity to intervene. Eliminating bugs entirely is impossible, so adding a confirmation step before any destructive action is the more robust solution.

### The New Flow

```
User input -> AI analysis -> show confirmation via inline keyboard -> user clicks -> execute
```

The AI's interpretation is shown to the user first. If it's wrong, the user can cancel and nothing happens.

### How Telegram Inline Keyboards Work

Telegram's inline keyboard attaches interactive buttons directly to a message. Unlike a reply keyboard that takes over the input field, inline buttons appear below the message itself and pressing one does not produce a new message in the chat.

The flow:
- The bot sends a message with a `reply_markup` containing an `inline_keyboard` array
- When the user taps a button, Telegram sends a `callback_query` event to the bot's webhook
- `callback_query.data` contains the string that was set when the button was created
- The bot calls `answerCallbackQuery` to dismiss the loading spinner on the button (skipping this leaves the spinner spinning indefinitely, which looks broken)
- The bot calls `editMessageText` to replace the confirmation message with the final result message

### Implementation

**Sending the confirmation request:**
```ruby
def ask_task_confirmation(user, text, chat_id)
  analysis = ai_service.analyze_task_input(text, user_context)

  # Store AI-parsed data in cache for 10 minutes; nothing is written to DB yet
  cache_key = "telegram:confirm_task:#{user.id}:#{SecureRandom.hex(6)}"
  Rails.cache.write(cache_key, pending_data, expires_in: 10.minutes)

  # callback_data has a 64-byte limit; only include the short hex key
  short_key = cache_key.split(':').last

  inline_buttons = [[
    { text: "✅ Add", callback_data: "task_confirm:#{user.id}:#{short_key}" },
    { text: "❌ Cancel", callback_data: "task_cancel:#{user.id}:#{short_key}" }
  ]]

  send_inline_keyboard(chat_id, confirm_text, inline_buttons)
end
```

The AI-parsed pending data is held in Rails.cache. The task is written to the database only when the user clicks the confirm button. If the user cancels or 10 minutes pass, the cache entry expires automatically and nothing is persisted.

**Receiving and routing the callback_query:**
```ruby
def process_message(data)
  if data['callback_query'].present?
    # Button tap events — separate branch from normal messages
    handle_callback_query(data['callback_query'])
  elsif data['message'].present?
    handle_text_message(data['message'])
  end
end

def handle_callback_query(callback_query)
  callback_id = callback_query['id']               # required for answerCallbackQuery
  chat_id     = callback_query['message']['chat']['id']
  message_id  = callback_query['message']['message_id']  # required for editMessageText
  data        = callback_query['data']

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
    edit_message_text(chat_id, message_id, "❌ Cancelled.")
  when /^complete_confirm:(\d+)$/
    task_id = $1.to_i
    handle_complete_confirm_callback(user, callback_id, chat_id, message_id, task_id)
  when /^complete_cancel:(\d+)$/
    answer_callback_query(callback_id)
    edit_message_text(chat_id, message_id, "❌ Cancelled.")
  end
end
```

**Saving the task after confirmation:**
```ruby
def handle_task_confirm_callback(user, callback_id, chat_id, message_id, short_key)
  cache_key    = "telegram:confirm_task:#{user.id}:#{short_key}"
  pending_data = Rails.cache.read(cache_key)

  if pending_data.nil?
    # Cache expired (10 min timeout) or already processed
    answer_callback_query(callback_id, "This request has expired. Please try again.")
    return
  end

  task = user.tasks.create!(pending_data)
  Rails.cache.delete(cache_key)  # clean up after successful processing

  due_info = task.due_at ? " 📅#{task.due_at.strftime('%m/%d')} ⏰#{task.due_at.strftime('%H:%M')}" : ""
  answer_callback_query(callback_id, "Added!")
  edit_message_text(chat_id, message_id, "✅ Task added!\n\"#{task.content}\"#{due_info}")
end
```

Handling the expired-cache case explicitly is important. If a user taps a button 15 minutes after the message was sent, the response should be graceful rather than crashing or silently doing nothing.

### callback_data Size Constraint

Telegram limits `callback_data` to **64 bytes**. Putting the full cache key (`telegram:confirm_task:USER_ID:HEXKEY`) directly into `callback_data` can exceed this limit, so only the short hex part is included and the full cache key is reconstructed server-side.

```
callback_data:   "task_confirm:123:a1b2c3"           <- stays short
server rebuilds: "telegram:confirm_task:123:a1b2c3"  <- full key
```

This pattern also has a minor security benefit: the full cache key is never exposed in the payload, making it harder for a malicious actor to guess or enumerate other users' pending entries. In production you would also validate that the `user_id` in `callback_data` matches the authenticated session making the request.

### Result

```
User: "Tomorrow evening coffee chat meeting evening9pm"

Bot: 📝 Add this task? (personal)
     "Coffee chat meeting" 📅tomorrow ⏰21:00
     [✅ Add]  [❌ Cancel]

User: [✅ Add] tapped

Bot: ✅ Task added!
     "Coffee chat meeting" 📅tomorrow ⏰21:00
```

The AI correctly parsed "evening9pm" as 21:00, and the confirmation flow works naturally. The user has a chance to review what the bot understood before anything is saved.

---

## Summary

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| Evening 9pm -> 09:00 | Wrong pattern evaluation order | Check compound patterns (evening + hour) before bare numeric patterns |
| Task-add misclassified as completion | Greedy regex with no position anchoring | Add `$` end anchor + exclusion for add-request inputs |
| Cancel undo failed | Completion pattern matched before cancel intent | Skip completion check when cancel intent is detected at start of input |
| Unintended immediate execution | UX design: no confirmation step | Inline keyboard confirmation before executing destructive actions |

---

## Key Takeaways

**1. Specific patterns must come before general ones.**
If a general pattern appears first, more specific patterns below it will never execute. The "evening9pm" bug was exactly this: the bare numeric hour pattern fired before the compound evening+hour pattern could. When writing a chain of regex checks, always ask "will any pattern above this one steal this input?"

**2. Use the `$` end anchor to prevent greedy keyword matching.**
Korean SOV word order means the intent-expressing verb always comes last. Anchoring completion patterns to `$` ensures that a keyword in the middle of the sentence — used in a non-completion role — does not trigger a false positive.

**3. Apply exclusion conditions first.**
When an input clearly signals a specific intent (e.g., "add", "cancel"), skip the ambiguous pattern checks entirely. Handle the unambiguous cases first, then apply probabilistic pattern matching to everything else.

**4. Add counter-examples to your AI prompt.**
Language models reflect their training distribution, so they fail in predictable ways on edge cases. When a misclassification occurs, fix the code _and_ add the offending example explicitly to the prompt as a negative example. Without both fixes, the same mistake will reappear in a slightly different form.

**5. Destructive actions need a confirmation step.**
No matter how good the intent classification is, it will never be 100% accurate. Any action that is hard to undo — completing a task, deleting a record, sending a message — should have a confirmation step. Telegram's inline keyboard is a clean, native way to implement this pattern without breaking the conversational flow.
