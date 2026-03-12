---
title: "Slack Events API로 채널 메시지 자동 수집하기 — Rails 서비스 설계"
date: 2026-03-12
draft: false
tags: ["Rails", "Slack API", "Events API", "자동화", "삽질"]
description: "Slack 봇이 멘션될 때만 동작하던 수집 시스템을 채널 메시지 자동 수집으로 확장했다. message.channels, reaction_added, file_shared 이벤트를 활용한 설계와 삽질 기록."
cover:
  image: "/images/og/slack-events-api-auto-collection-rails.png"
  alt: "Slack Events API Auto Collection Rails"
  hidden: true
---

Slack 봇에 `@봇 이관`이라고 멘션해야만 메시지가 수집되는 구조였다. 멘토가 매번 봇을 호출하는 게 번거롭다는 피드백이 왔다. "채널에 글이 올라오면 알아서 수집하면 안 되냐?"는 질문에서 시작된 작업 기록이다.

---

## 기존 구조: app_mention 기반

기존에는 Slack의 `app_mention` 이벤트만 구독하고 있었다.

```ruby
def handle_event(event)
  case event["type"]
  when "app_mention"
    handle_mention(event)
  end
end
```

누군가 `@봇 이관` 또는 `@봇 피드백 홍길동 잘했어요`라고 멘션하면 처리되는 구조. 문제는:

1. **멘토가 매번 봇을 불러야 한다** — 피드백을 쓰고 나서 다시 봇을 호출하는 이중 작업
2. **수강생 제출물도 수동 수집** — 과제 채널에 올라온 메시지를 누군가 이관해줘야 함
3. **파일만 올린 경우 놓침** — 텍스트 없이 파일만 공유하면 수집되지 않음

---

## 해결: 세 가지 이벤트 추가 구독

Slack 앱 설정에서 Bot Events에 다음을 추가했다:

| 이벤트 | 설명 | Required Scope |
|--------|------|----------------|
| `message.channels` | 공개 채널 메시지 수신 | `channels:history` |
| `reaction_added` | 이모지 리액션 감지 | `reactions:read` |
| `file_shared` | 파일 공유 감지 | `files:read` |
| `message.im` | 봇 DM 메시지 | `im:history` |

**중요**: 이벤트를 추가한 후 반드시 **Reinstall App**을 해야 새 권한이 적용된다.

---

## 컨트롤러 라우팅

이벤트 타입별로 분기하는 구조:

```ruby
def handle_event(event)
  case event["type"]
  when "app_mention"
    handle_mention(event)
  when "message"
    handle_message(event)
  when "reaction_added"
    handle_reaction(event)
  end
end
```

### message 이벤트 필터링이 핵심

`message.channels`를 구독하면 **모든** 메시지가 들어온다. 봇 자신의 메시지, 시스템 메시지, 멘션 메시지까지. 필터링이 없으면 무한 루프에 빠진다.

```ruby
def handle_message(event)
  return if event["subtype"].present?   # bot_message, message_changed 등 제외
  return if event["bot_id"].present?    # 봇 메시지 제외
  return if event["text"].to_s.include?("<@")  # 멘션은 app_mention에서 처리

  SlackAutoCollector.call(event)
end
```

세 가지 필터:
1. **`subtype` 체크** — Slack은 봇 메시지에 `subtype: "bot_message"`를 붙인다. `message_changed`, `message_deleted` 등 시스템 이벤트도 subtype으로 구분된다.
2. **`bot_id` 체크** — 일부 봇 메시지는 subtype 없이 `bot_id`만 가진다.
3. **멘션 제외** — `<@U1234>` 패턴이 포함된 메시지는 `app_mention`에서 이미 처리하므로 중복 방지.

이 세 줄을 빼먹으면 **봇이 자기 응답을 다시 수집 → 응답 → 수집** 무한 루프에 빠진다.

---

## 자동 수집 서비스 설계

```ruby
class SlackAutoCollector
  def handle
    display_name = fetch_display_name(@slack_user)
    file_ids     = @files.map { |f| f["id"] }

    # 스레드 답글이면 feedback, 최상위 메시지면 auto_message
    action = @thread_ts.present? ? "auto_feedback" : "auto_message"

    SlackCollectedItem.create!(
      slack_user_id:               @slack_user,
      channel:                     @channel,
      thread_ts:                   @thread_ts || @ts,
      raw_text:                    @text,
      parsed_action:               action,
      original_slack_display_name: display_name,
      original_text:               @text,
      slack_file_ids:              file_ids,
      status:                      :pending
    )
  end
end
```

핵심 설계 결정:

### 1. 스레드 위치로 액션 구분

- **최상위 메시지** → `auto_message` (과제 제출 가능성)
- **스레드 답글** → `auto_feedback` (피드백 가능성)

실제로 과제 채널에서는 수강생이 최상위에 과제를 올리고, 멘토가 스레드로 피드백을 달기 때문에 이 구분이 잘 맞는다.

### 2. 모든 건 pending 상태로

자동 수집된 항목은 무조건 `pending`으로 들어간다. 멘토가 대시보드에서 검토하고 승인/거절하는 프로세스는 그대로 유지. 자동화는 **수집**만 하고, **판단**은 사람이 한다.

### 3. 파일도 함께 수집

`event["files"]`에 Slack 파일 ID가 들어온다. 나중에 승인 시 `SlackFileImporter`로 다운로드하여 ActiveStorage에 첨부한다.

---

## 리액션 핸들러

```ruby
class SlackReactionHandler
  def handle
    case @reaction
    when "white_check_mark", "heavy_check_mark", "+1"
      mark_acknowledged
    when "eyes"
      log_seen
    end
  end
end
```

현재는 로깅만 한다. 향후 확장 포인트:
- ✅ 리액션 → 자동 승인 (멘토 권한 확인 후)
- 👀 리액션 → 읽음 상태 표시

---

## 피드백 내용 자동 수집

기존에는 피드백 명령에 내용을 직접 입력해야 했다:

```
@봇 피드백 홍길동 전체적으로 잘했습니다
```

"내용을 공란으로 넣어도 알아서 넣어지게 안 돼?" 라는 피드백을 받고 추가한 기능:

```
@봇 피드백 홍길동
```

스레드에서 이렇게만 입력하면 **스레드 원본 메시지**를 피드백 내용으로 자동 사용한다.

```ruby
def save_feedback_by_name_auto(name)
  unless in_thread?
    reply_to_slack("내용 없이 피드백하려면 스레드에서 사용해주세요.")
    return
  end

  parent = fetch_parent_message
  auto_body = parent["text"].to_s.strip

  save_feedback_by_name(name, auto_body)
end
```

스레드 밖에서 사용하면 안내 메시지를 보여준다. `conversations.replies` API로 스레드 원본을 가져오는 로직은 기존 `이관` 명령에서 이미 구현되어 있어서 재사용했다.

---

## 삽질 포인트 정리

1. **봇 무한 루프** — `message.channels`를 구독하면 봇 자신의 응답도 이벤트로 들어온다. `subtype`, `bot_id`, 멘션 패턴 세 가지로 필터링해야 한다.

2. **Reinstall 필수** — Slack 앱 설정에서 이벤트를 추가한 후 Reinstall하지 않으면 새 이벤트가 전달되지 않는다. 설정만 바꾸고 "왜 안 오지?" 하며 30분을 날렸다.

3. **app_mention과 message 중복** — 봇을 멘션하는 메시지는 `app_mention`과 `message` 이벤트가 **동시에** 발생한다. 멘션 포함 메시지를 message 핸들러에서 제외하지 않으면 하나의 메시지가 두 번 수집된다.

4. **thread_ts vs ts** — 스레드 답글은 `thread_ts`(부모 타임스탬프)와 `ts`(자신의 타임스탬프) 두 개를 가진다. 최상위 메시지는 `thread_ts`가 없다. 이걸로 "제출물 vs 피드백"을 구분할 수 있다.

---

## 최종 이벤트 흐름

```
Slack 채널 메시지
├─ 봇 멘션 포함? → app_mention → SlackMentionHandler (명령 파싱)
├─ 일반 메시지?  → message     → SlackAutoCollector (자동 수집)
└─ 이모지 리액션? → reaction   → SlackReactionHandler (로깅/승인)

SlackCollectedItem (pending)
└─ 멘토 대시보드에서 검토 → 승인 or 거절
```

자동 수집은 "데이터를 놓치지 않는 것"이 목적이고, 실제 반영 여부는 멘토가 판단한다. 자동화와 수동 검토의 균형점이다.
