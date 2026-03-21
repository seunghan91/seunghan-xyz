---
title: "대진표에 FAB 피드백 버튼, 수정 권한 체계, Audit Log 붙이기 — Rails 8 삽질 기록"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus", "Turbo", "Pundit", "Audit Log", "FAB", "Telegram", "ViewComponent"]
description: "스포츠 대진표 앱에 세 가지 기능을 동시에 추가하면서 만난 설계 결정들: FAB 피드백 버튼(Stimulus + Telegram), 역할 기반 대진표 수정 권한(Pundit), 수정 이력 audit log. 삽질 포인트와 설계 트레이드오프 중심 정리."
cover:
  image: "/images/og/bracket-fab-audit-log-rails.png"
  alt: "Bracket FAB Audit Log Rails"
  hidden: true
categories: ["Rails"]
---

한 번에 세 가지 기능을 동시에 설계하다 보면 서로 얽히는 부분이 생긴다. 이번에는 대진표 관리 앱에 다음을 추가했다.

1. **FAB 피드백 버튼** — 우측 하단 플로팅 버튼 → Telegram 전송
2. **역할 기반 대진표 수정 권한** — 대회 vs 친선 모드에 따라 일반 참가자에게 수정 권한 부여 여부 선택
3. **Audit Log** — 누가 언제 무엇을 바꿨는지 전/후 데이터와 함께 기록

각각은 단순해 보이지만, 셋을 한꺼번에 설계하다 보니 "어디서 권한을 체크하고, 어디서 로그를 남기고, 어디까지 UI에 노출하는가"에 대한 결정이 계속 붙었다.

---

## 1. FAB 피드백 버튼

### 설계 선택지

처음에는 기존 피드백 시스템(Lookbook 개발 도구용)에 붙이려 했는데, 그건 인증 구조가 달라서 분리하는 게 맞았다.

결국 만든 구조:

```
UserFeedbacksController#create
  → TelegramNotifier.notify_user_feedback
  → 200 JSON 응답
```

뷰는 Stimulus 컨트롤러 하나로 처리했다.

```js
// feedback_fab_controller.js
static targets = ["panel", "fab", "formArea", "success", "message", "submitBtn"]

async submit(event) {
  event.preventDefault()
  const data = new FormData(event.target)
  const response = await fetch(form.action, {
    method: "POST",
    headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content },
    body: data
  })
  if (response.ok) {
    this.formAreaTarget.classList.add("hidden")
    this.successTarget.classList.remove("hidden")
    setTimeout(() => this.close(), 2500)
  }
}
```

`turbo: false` 없이 그냥 fetch로 처리한 이유는, Turbo Stream 응답 없이 success 상태만 로컬에서 토글하면 되는 단순한 경우였기 때문이다. Turbo를 쓰면 오히려 panel 상태 관리가 복잡해진다.

### Telegram 전송 서비스

기존 서비스에 메서드 하나 추가:

```ruby
def self.notify_user_feedback(user:, message:, context: nil)
  return unless configured?

  text = <<~MSG
    💬 *앱 피드백*
    👤 *사용자:* `#{escape(user.display_name)}`
    📧 *이메일:* `#{escape(user.email)}`
    #{"📍 *페이지:* `#{escape(context)}`\n" if context.present?}
    💬 *메시지:*
    #{escape(message.truncate(500))}
  MSG

  send_message(text.strip)
end
```

`context`로 현재 `request.path`를 넘기면, 어떤 페이지에서 피드백을 보냈는지 텔레그램 메시지에서 바로 알 수 있어서 디버깅에 유용하다.

---

## 2. 역할 기반 대진표 수정 권한

### 요구사항 정리

- **토너먼트 모드**: 주최자/어드민만 대진표 수정 가능
- **친선 모드**: 주최자가 옵션을 켜면 일반 참가자도 대진표 수정 가능

Tournament 모델에 컬럼 하나 추가:

```ruby
# migration
add_column :tournaments, :allow_user_bracket_edit, :boolean, default: false, null: false
```

Pundit 정책:

```ruby
def edit_bracket?
  return false unless authenticated?
  return true if admin? || tournament_organizer?
  return false unless record.respond_to?(:allow_user_bracket_edit)

  record.allow_user_bracket_edit? && tournament_player?
end
```

### 폼 UI: 친선 모드일 때만 체크박스 노출

Stimulus로 mode select 변경을 감지해서 체크박스 섹션을 토글했다.

```js
// tournament_form_controller.js
toggleFriendlyOptions(event) {
  const isFriendly = event.target.value === "friendly"
  this.friendlyOptionsTargets.forEach(el => {
    el.classList.toggle("hidden", !isFriendly)
  })
}
```

```erb
<div data-tournament-form-target="friendlyOptions"
     class="<%= tournament.friendly? ? '' : 'hidden' %> ...">
  <%= f.check_box :allow_user_bracket_edit %>
  ...
</div>
```

초기값 처리가 중요하다. 기존 친선 대회를 편집할 때는 이미 `friendly?`가 true이므로 `hidden`을 붙이지 않고, 신규 생성이나 토너먼트 모드라면 `hidden`으로 시작한다.

---

## 3. Audit Log 설계

### 스키마

```ruby
create_table :bracket_edit_logs do |t|
  t.references :tournament, null: false, foreign_key: true
  t.references :round, foreign_key: true, null: true
  t.references :bracket_slot, foreign_key: true, null: true
  t.references :user, foreign_key: true, null: true
  t.string :action_type, null: false   # "add_round", "add_slot", ...
  t.jsonb :before_data
  t.jsonb :after_data
  t.text :note
  t.timestamps
end
add_index :bracket_edit_logs, [:tournament_id, :created_at]
```

`before_data` / `after_data`를 jsonb로 자유롭게 담았다. action_type별로 담는 내용이 다르기 때문에 컬럼을 정규화하는 것보다 jsonb가 훨씬 유연하다.

### 컨트롤러에서 로그 기록

```ruby
def add_round
  authorize @tournament, :edit_bracket?

  round = @tournament.rounds.create!(number: next_number, name: "Round #{next_number}", ...)

  BracketEditLog.create!(
    tournament: @tournament,
    round: round,
    user: current_user,
    action_type: "add_round",
    before_data: { rounds_count: next_number - 1 },
    after_data: { round_id: round.id, round_name: round.name, number: next_number }
  )
  ...
end
```

권한 체크(`authorize`) 다음에 로그를 남기는 순서가 중요하다. 권한이 없어서 예외가 발생하면 로그도 남으면 안 되므로.

### 뷰에서 전/후 비교

```erb
<div class="grid grid-cols-2 gap-3">
  <div class="rounded-xl border border-rose-100 bg-rose-50 p-3">
    <p class="text-xs font-semibold text-rose-500">수정 전</p>
    <% log.before_data.each do |key, value| %>
      <p class="text-xs text-rose-700"><%= key %>: <code><%= value %></code></p>
    <% end %>
  </div>
  <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-3">
    <p class="text-xs font-semibold text-emerald-500">수정 후</p>
    <% log.after_data.each do |key, value| %>
      <p class="text-xs text-emerald-700"><%= key %>: <code><%= value %></code></p>
    <% end %>
  </div>
</div>
```

jsonb를 그대로 순회하니 뷰 코드가 단순해진다. 다만 key 이름이 사람이 읽기 좋아야 하므로 컨트롤러에서 저장할 때 한국어 또는 명확한 영어로 키를 정한다.

---

## 4. + 버튼: 라운드/슬롯 추가

대진표 라운드 카드에 + 버튼을 달아서, 2라운드까지 만든 대진표에 3라운드를 추가하거나, 특정 라운드의 빈 코트 슬롯을 추가할 수 있게 했다.

```erb
<%# 각 라운드 카드 우측 상단에 %>
<%= button_to tournament_bracket_add_slot_path(@tournament),
    method: :post,
    params: { round_id: round.id },
    data: { turbo_confirm: "#{round.display_name}에 슬롯을 추가할까요?" } do %>
  + 아이콘
<% end %>

<%# 라운드 목록 맨 끝에 %>
<%= button_to tournament_bracket_add_round_path(@tournament),
    method: :post,
    data: { turbo_confirm: "새 라운드를 추가할까요?" } do %>
  + 라운드 추가
<% end %>
```

`turbo_confirm`을 붙여서 실수로 누르는 경우를 방지했다. confirm 다이얼로그는 추가 JS 없이 Turbo가 처리해준다.

---

## 삽질 포인트

### 1. `button_to`는 form을 생성한다

`button_to`로 POST 요청을 날릴 때, 내부적으로 `<form>` 태그가 생성된다. 이 form 안에 다시 `<button>` 아이콘 SVG를 넣으면 됐는데, 처음에 `link_to`에 `method: :post`를 달려다가 Turbo method 충돌이 생겼다. `button_to`가 정답.

### 2. Stimulus `data-action` 이벤트 prefix

`data-action="feedback-fab#toggle"`은 자동으로 click 이벤트에 바인딩되지만, form의 submit은 명시적으로 `submit->feedback-fab#submit`으로 써야 한다. prefix를 빼면 submit 이벤트가 Stimulus에 안 잡힌다.

### 3. jsonb에 루비 심볼 키를 쓰면 DB에 문자열로 저장된다

`before_data: { rounds_count: 3 }` — 이렇게 심볼로 넣으면 PostgreSQL에서 꺼낼 때 `"rounds_count"`(문자열)로 나온다. 뷰에서 `log.before_data[:rounds_count]`로 접근하면 `nil`이 된다. `log.before_data["rounds_count"]`로 접근하거나, 아예 저장 전에 `stringify_keys`를 호출해야 한다.

Rails의 `jsonb` 컬럼은 읽을 때 자동으로 문자열 키로 반환하니, 저장 시점부터 문자열 키를 쓰는 게 일관성이 있다.

### 4. 권한 체크 순서

Pundit `authorize`를 컨트롤러 맨 위에서 호출하면, 그 이후에 DB 변경이나 로그 기록이 일어난다. 권한이 없으면 `NotAuthorizedError`가 raise되어 이후 코드가 실행되지 않는다. 의도한 동작이지만, rescue 핸들러에서 로그를 찍고 싶다면 따로 처리해야 한다.

---

## 어드민 페이지 반영

기능을 추가했으면 어드민에도 표시해야 한다. 이번에 어드민 대회 상세 페이지에 추가한 것들:

- **대회 설정 카드**: match_type, 브래킷 형식, 세트/게임 수, `allow_user_bracket_edit` 허용 여부
- **수정 내역 카드**: 최근 10건의 bracket edit log
- **운영 섹션 링크**: 참가자/코트/경기/대진표로 바로가기
- **리스크 박스 동적화**: 코트 미생성, 참가자 없음, 초안 상태 등 실제 DB 상태 기반으로 경고 표시

어드민에 기능을 반영하는 건 사소해 보이지만, "관리자가 이 기능이 켜져 있는지 어떻게 아는가"를 해결한다. DB만 바꾸고 어드민에 안 보이면, 운영하다가 설정이 의도치 않게 바뀌었을 때 알기 어렵다.

---

## 정리

| 기능 | 핵심 결정 |
|------|-----------|
| FAB 피드백 | Turbo 대신 fetch + Stimulus 상태 관리 |
| 수정 권한 | Pundit `edit_bracket?` + 모드별 분기 |
| Audit Log | jsonb 전/후 데이터, 문자열 키 일관성 |
| + 버튼 | `button_to` + `turbo_confirm` |
| 어드민 반영 | 설정 가시화, 로그 카드, 동적 리스크 |

세 기능이 겹치는 지점은 "권한 있는 사람이 수정하면 → 로그를 남긴다"는 흐름이다. 이 흐름을 컨트롤러 한 곳에서 처리하니 일관성이 생겼다.
