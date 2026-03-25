---
title: "Rails에서 Slack 메시지 렌더링하기 — HTML 엔티티, 이모지, mrkdwn, whitespace-pre-wrap 함정까지"
date: 2025-03-25
draft: false
tags: ["rails", "slack", "html-escape", "erb", "emoji"]
description: "Slack 채팅 데이터를 Rails ERB 뷰에서 렌더링할 때 발생하는 HTML 엔티티 이중 이스케이프, 이모지 shortcode 미변환, mrkdwn 마크업 파싱, whitespace-pre-wrap 들여쓰기 버그를 실전 코드와 함께 해결한다."
---

Slack 채널 데이터를 Rails 앱에 넣고 그대로 뷰에서 뿌려봤더니, 화면이 온통 `&gt;`와 `:raised_hands:`로 도배되어 있었다. 이모지는 텍스트 그대로, 볼드는 별표 그대로, 링크는 꺾쇠 그대로. 거기에 `whitespace-pre-wrap` CSS가 붙은 말풍선에서는 ERB 들여쓰기까지 렌더링돼서 모든 메시지가 들여쓰기된 것처럼 보였다.

이 글에서는 Slack 메시지를 Rails에서 제대로 렌더링하기 위해 겪은 삽질과 해결 과정을 정리한다.

---

## Slack 메시지 포맷의 특성

Slack은 자체 마크업 언어인 **mrkdwn**을 사용한다. Markdown과 비슷하지만 문법이 다르다.

| 포맷 | Slack mrkdwn | Markdown |
|------|-------------|----------|
| 볼드 | `*bold*` | `**bold**` |
| 이탤릭 | `_italic_` | `*italic*` |
| 취소선 | `~strike~` | `~~strike~~` |
| 인용문 | `>` 줄 시작 | `>` 줄 시작 (동일) |
| 코드 | `` `code` `` | `` `code` `` (동일) |
| 링크 | `<url\|label>` | `[label](url)` |
| 멘션 | `<@U123>`, `<!everyone>` | 없음 |

공식 문서(docs.slack.dev)에 따르면, Slack API를 통해 메시지를 **가져올 때** 세 가지 문자가 HTML 엔티티로 인코딩된 상태다:

```
& → &amp;
< → &lt;
> → &gt;
```

또한 이모지는 유니코드가 아닌 **colon 포맷**(`:smile:`, `:raised_hands:`)으로 변환되어 저장된다. Slack은 클라이언트에서 이 colon 포맷을 네이티브 이모지로 변환하는데, 우리가 가져온 데이터에는 당연히 그 처리가 없다.

---

## 문제 1: HTML 엔티티 이중 이스케이프

### 증상

화면에 `&gt;`가 그대로 표시된다. 이게 `>`가 되어야 하는데.

```
입력 데이터: 저는 AI를 활용해 &amp; 협업합니다 &gt; 인용문
화면 출력:   저는 AI를 활용해 &amp; 협업합니다 &gt; 인용문
```

### 원인

Slack 데이터에는 이미 `&amp;`, `&lt;`, `&gt;`가 들어있다. 그런데 ERB의 `<%= %>`는 출력할 때 **자동으로 HTML 이스케이프**를 수행한다(Rails 3부터 기본 동작). 그래서:

```
DB 데이터:    &amp;
ERB 이스케이프: &amp;amp;
브라우저 표시:  &amp;
```

이중 이스케이프가 발생하는 거다.

### 해결

Slack 데이터의 HTML 엔티티를 먼저 디코딩하고, 그 다음 ERB 이스케이프를 직접 제어해야 한다.

```ruby
# 1단계: Slack HTML 엔티티 디코딩
formatted = text.dup
formatted.gsub!("&amp;", "&")
formatted.gsub!("&lt;", "<")
formatted.gsub!("&gt;", ">")

# 2단계: 우리가 직접 HTML 이스케이프
escaped = ERB::Util.html_escape(formatted)

# 3단계: html_safe로 마킹해서 ERB의 자동 이스케이프 방지
escaped.html_safe
```

`html_safe`를 쓰는 건 XSS 위험이 있기 때문에, 반드시 **먼저 `html_escape`로 안전하게 이스케이프한 후**에 호출해야 한다. 순서가 중요하다.

---

## 문제 2: Slack 이모지 shortcode 미변환

### 증상

```
안녕하세요 :slightly_smiling_face:
:raised_hands: 파이팅!
:four_leaf_clover: 좋은 하루
```

이모지 코드가 텍스트 그대로 보인다.

### 원인

Slack은 이모지를 colon 포맷으로 저장한다. 클라이언트에서 네이티브 이모지로 변환해주는 건 Slack 앱의 역할이다. 우리 Rails 앱에는 그런 변환 로직이 없다.

### 해결: 매핑 테이블 방식

`gemoji` gem을 쓸 수도 있지만, 의존성을 추가하기 싫어서 직접 매핑 테이블을 만들었다.

```ruby
module SlackEmojiHelper
  SLACK_EMOJI_MAP = {
    "smile" => "😄", "laughing" => "😆", "blush" => "😊",
    "heart_eyes" => "😍", "raised_hands" => "🙌", "pray" => "🙏",
    "clap" => "👏", "fire" => "🔥", "tada" => "🎉",
    "slightly_smiling_face" => "🙂", "thinking_face" => "🤔",
    "four_leaf_clover" => "🍀", "people_hugging" => "🫂",
    # ... 200+ 매핑
  }.freeze

  def replace_slack_emoji(text)
    return text if text.blank?
    text.gsub(/:([a-zA-Z0-9_+-]+):/) do
      SLACK_EMOJI_MAP[$1] || ":#{$1}:"
    end
  end
end
```

정규식 `/:([a-zA-Z0-9_+-]+):/`가 colon 사이의 shortcode를 잡아서 매핑 테이블에서 유니코드 이모지로 치환한다. 매핑에 없으면 원본 그대로 둔다.

### 실수했던 부분: 중복 키

Ruby Hash에서 같은 키를 두 번 선언하면 경고 없이 마지막 값으로 덮어쓴다.

```ruby
{
  "wave" => "👋",  # 줄 15
  # ... 100줄 뒤 ...
  "wave" => "👋",  # 줄 115 — 중복! 경고만 뜨고 동작은 함
}
```

`ruby -w` 옵션이나 `RUBYOPT="-w"` 환경변수를 설정하면 `warning: key "wave" is duplicated and overwritten` 경고를 볼 수 있다. 200개 넘는 매핑을 추가할 때는 `sort -u`로 먼저 중복 체크하는 게 좋다.

---

## 문제 3: Slack mrkdwn 마크업 렌더링

### 증상

```
*볼드 텍스트* ← 별표가 그대로 보임
_이탤릭_ ← 언더스코어 그대로
>인용문 ← 꺾쇠 그대로
@here ← 그냥 텍스트
```

### 해결: 단계별 변환 파이프라인

핵심은 **변환 순서**다. HTML 이스케이프와 마크업 변환의 순서를 잘못 잡으면 패턴 매칭이 깨진다.

```ruby
def format_slack_message(text)
  return "".html_safe if text.blank?

  formatted = text.dup

  # 1. Slack HTML 엔티티 디코딩
  formatted.gsub!("&amp;", "&")
  formatted.gsub!("&lt;", "<")
  formatted.gsub!("&gt;", ">")

  # 2. 이모지 shortcode 변환
  formatted = replace_slack_emoji(formatted)

  # 3. Slack 링크 추출 (<url|label>) — HTML 이스케이프 전에!
  links = []
  formatted = formatted.gsub(/<(https?:\/\/[^|>]+)\|([^>]+)>/) do
    idx = links.length
    links << { url: $1, label: $2 }
    "%%SLACKLINK#{idx}%%"
  end

  # 4. HTML 이스케이프 (XSS 방지)
  escaped = ERB::Util.html_escape(formatted)

  # 5. 링크 복원
  links.each_with_index do |link, idx|
    safe_url = ERB::Util.html_escape(link[:url])
    safe_label = ERB::Util.html_escape(link[:label])
    escaped = escaped.gsub(
      "%%SLACKLINK#{idx}%%",
      %(<a href="#{safe_url}" target="_blank">#{safe_label}</a>)
    )
  end

  # 6. 볼드: *text* → <strong>text</strong>
  escaped = escaped.gsub(/\*([^*\n]+)\*/, '<strong>\1</strong>')

  # 7. 이탤릭: _text_ → <em>text</em>
  escaped = escaped.gsub(
    /(?<![a-zA-Z0-9])_([^_\n]+)_(?![a-zA-Z0-9])/,
    '<em>\1</em>'
  )

  # 8. @here, @channel 멘션
  escaped = escaped.gsub(/@(here|channel|everyone)/) do
    %(<span class="slack-mention">@#{$1}</span>)
  end

  escaped.html_safe
end
```

### 링크 처리가 까다로운 이유

Slack 링크 형식 `<url|label>`에서 `<`와 `>`가 HTML과 충돌한다. HTML 이스케이프 후에 처리하면 `&lt;url|label&gt;`가 되어서 정규식이 안 맞는다.

그래서 **HTML 이스케이프 전에 링크를 추출해서 플레이스홀더로 치환**하고, 이스케이프 후에 복원하는 방식을 썼다. URL과 label은 별도로 이스케이프해서 XSS를 방지한다.

### Slack 링크 아티팩트 정리

Slack 내보내기 데이터에는 `|>`나 `<< >`같은 잔해가 남아있는 경우가 있다. 사용자가 Slack 클라이언트에서 링크를 수동으로 입력했을 때 발생한다.

```ruby
# Slack 링크 아티팩트 정리
formatted.gsub!(/\|>/, "")
formatted.gsub!(/<<\s*>/, "")
```

이건 데이터를 직접 확인해보고 발견한 패턴이다. 데이터마다 다를 수 있으니 실제 메시지를 샘플링해서 확인해야 한다.

---

## 문제 4: whitespace-pre-wrap 들여쓰기 버그

### 증상

채팅 말풍선에서 모든 메시지의 첫 줄이 들여쓰기된 것처럼 표시된다.

### 원인

CSS `white-space: pre-wrap`은 소스 코드의 공백과 줄바꿈을 **그대로 렌더링**한다. ERB 템플릿에서:

```erb
<div class="whitespace-pre-wrap">
          <%= format_slack_message(chat_message.body) %>
        </div>
```

이 코드에서 `<div>` 닫는 태그와 `<%= %>` 사이의 줄바꿈 + 들여쓰기(10칸 공백)가 `pre-wrap` 때문에 그대로 화면에 렌더링된다.

렌더링된 HTML:

```html
<div class="whitespace-pre-wrap">
          안녕하세요 반갑습니다</div>
```

브라우저에서 보면 "안녕하세요" 앞에 줄바꿈과 10칸 공백이 보인다.

### 해결

`<div>` 닫는 태그와 `<%= %>`를 한 줄에 붙인다:

```erb
<div class="whitespace-pre-wrap"
     style="..."><%= format_slack_message(chat_message.body) %></div>
```

ERB에서 `>` 바로 뒤에 `<%=`를 붙이고, `%>` 바로 뒤에 `</div>`를 붙여야 한다.

### 이건 왜 까먹기 쉬운가

일반적인 HTML에서는 태그 사이 공백이 무시되거나 하나의 스페이스로 축약된다. 그래서 ERB 들여쓰기를 신경 쓸 일이 거의 없다. 하지만 `pre-wrap`, `pre`, `pre-line`이 적용된 요소에서는 **모든 공백이 보존**된다.

이런 요소들에서 ERB 출력을 사용할 때는 항상 주의해야 한다:

```
위험한 요소: <pre>, <code>, <textarea>
위험한 CSS: white-space: pre, pre-wrap, pre-line
```

Rails 커뮤니티에서도 오래된 이슈다. ERB의 `<%-` `-%>` trim 모드로 줄바꿈을 제거할 수 있지만, 들여쓰기 공백까지 제거하지는 못한다. 결국 태그를 붙여쓰는 게 가장 확실한 방법이다.

HAML이나 Slim 같은 대안 템플릿 엔진은 들여쓰기 기반이라 이 문제가 좀 다른 형태로 나타난다. HAML에서는 `ugly` 모드를 켜서 출력 시 들여쓰기를 제거하는 옵션이 있다.

---

## 전체 구현: SlackEmojiHelper

최종적으로 만든 헬퍼 모듈의 구조다:

```ruby
module SlackEmojiHelper
  SLACK_EMOJI_MAP = {
    # 200+ emoji shortcode → unicode 매핑
  }.freeze

  def replace_slack_emoji(text)
    text.gsub(/:([a-zA-Z0-9_+-]+):/) do
      SLACK_EMOJI_MAP[$1] || ":#{$1}:"
    end
  end

  def format_slack_message(text)
    # 1. HTML 엔티티 디코딩
    # 2. 이모지 변환
    # 3. Slack 링크 추출 → 플레이스홀더
    # 4. HTML 이스케이프
    # 5. 링크 복원
    # 6. mrkdwn 마크업 변환 (볼드, 이탤릭, 멘션, 인용문)
    # 7. 일반 URL 자동 링크
    escaped.html_safe
  end
end
```

ApplicationHelper에 include하면 모든 뷰에서 사용 가능하다:

```ruby
module ApplicationHelper
  include SlackEmojiHelper
end
```

### 뷰에서 사용

```erb
<%# 채팅 메시지 — whitespace-pre-wrap 주의!
<div class="whitespace-pre-wrap"><%= format_slack_message(chat_message.body) %></div>

<%# 마크다운 헬퍼에서도 사용 %>
def markdown(text)
  converted = replace_slack_emoji(text)
  # ... Redcarpet 렌더링
end
```

---

## 변환 파이프라인 순서가 중요한 이유

10단계 파이프라인에서 순서를 바꾸면 바로 문제가 생긴다.

| 순서 | 처리 | 이유 |
|------|------|------|
| 1 | HTML 엔티티 디코딩 | `&gt;` → `>` 복원해야 후속 처리 가능 |
| 2 | 이모지 변환 | `:smile:` → `😄` (이스케이프 전에 해야 colon이 안 깨짐) |
| 3 | Slack 링크 추출 | `<url\|label>` → 플레이스홀더 (이스케이프하면 `<`가 `&lt;`로 바뀜) |
| 4 | HTML 이스케이프 | XSS 방지 필수 |
| 5 | 링크 복원 | 플레이스홀더 → `<a>` 태그 |
| 6-7 | mrkdwn 변환 | 이스케이프 후에 해야 `<strong>` 태그가 재이스케이프 안 됨 |
| 8 | 멘션 변환 | `@here` → 하이라이트 뱃지 |
| 9 | 인용문 변환 | `&gt;`(이스케이프된 `>`)를 blockquote로 |
| 10 | 일반 URL 자동 링크 | 마지막에 해야 이미 `<a>` 태그인 URL을 중복 처리 안 함 |

3번(링크 추출)을 4번(이스케이프) 후에 하면 `<`가 `&lt;`로 바뀌어서 정규식 `/<(https?:\/\/.../`가 매칭 안 된다. 6번(볼드)을 4번 전에 하면 `<strong>` 태그가 이스케이프돼서 화면에 태그 텍스트가 보인다.

---

## gemoji gem vs 직접 매핑, 뭘 쓸까

Ruby에는 Slack 이모지 처리를 위한 여러 옵션이 있다.

| 방식 | 장점 | 단점 |
|------|------|------|
| `gemoji` gem | 전체 이모지 지원, GitHub 호환 | 의존성 추가, 데이터 파일 큼 |
| `unicode-emoji` gem | 유니코드 표준 기반 정규식 | shortcode→emoji 매핑은 없음 |
| 직접 매핑 Hash | 의존성 없음, 필요한 것만 | 새 이모지 수동 추가 필요 |
| Slack API `emoji.list` | 커스텀 이모지 포함 | API 호출 필요, 인증 필요 |

프로젝트에 이미 Slack 데이터가 고정되어 있고 새 메시지가 계속 들어오는 게 아니라면 직접 매핑이 가장 간단하다. 동적으로 Slack 메시지를 수신하는 경우에는 `gemoji` gem이 낫다.

---

## 주의사항

### html_safe의 위험성

`html_safe`는 Rails의 XSS 보호를 우회한다. 반드시 `ERB::Util.html_escape`로 먼저 이스케이프한 후에 사용해야 한다. 순서가 바뀌면 사용자 입력이 그대로 HTML로 렌더링돼서 XSS 공격에 노출된다.

```ruby
# 안전한 순서
escaped = ERB::Util.html_escape(user_input)
# ... 안전한 HTML 태그 삽입 ...
escaped.html_safe

# 위험한 패턴 — 절대 이렇게 하면 안 된다
user_input.html_safe  # 이스케이프 없이 바로 safe 마킹
```

### Slack 데이터가 항상 같은 포맷은 아니다

Slack 내보내기 방식(공식 Export, API, 서드파티 도구)에 따라 데이터 포맷이 다를 수 있다. 실제 데이터를 샘플링해서 패턴을 확인하는 게 필수다.

### 테스트 코드 작성

```ruby
# rails runner로 빠르게 확인
include SlackEmojiHelper
puts format_slack_message('*bold* :smile: &gt; 인용문')
# => <strong>bold</strong> 😄 <span...>인용문</span>
```

---

## 결론

Slack 메시지를 Rails 뷰에서 렌더링하는 건 겉보기보다 복잡하다. HTML 엔티티 이중 이스케이프, 이모지 shortcode, mrkdwn 마크업, `whitespace-pre-wrap` 들여쓰기 버그까지 — 각각은 작은 문제지만 조합되면 디버깅이 꽤 귀찮다.

핵심은 **변환 순서**다. 디코딩 → 이모지 → 링크 추출 → 이스케이프 → 링크 복원 → 마크업 변환 순서를 지키면 각 단계가 서로를 방해하지 않는다.

그리고 `whitespace-pre-wrap`이 적용된 요소에서 ERB를 쓸 때는, 꼭 태그를 붙여쓰자. ERB 들여쓰기가 화면에 보이는 건 정말 은근한 버그다.
