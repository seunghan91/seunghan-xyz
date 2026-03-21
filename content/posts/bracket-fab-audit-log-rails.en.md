---
title: "Adding a FAB Feedback Button, Edit Permissions, and Audit Log to a Tournament Bracket — Rails 8 Notes"
date: 2026-03-17
draft: false
tags: ["Rails 8", "Stimulus", "Turbo", "Pundit", "Audit Log", "FAB", "Telegram", "ViewComponent"]
description: "Three features added to a sports bracket app at once: a FAB feedback button (Stimulus + Telegram), role-based bracket edit permissions (Pundit), and a full edit audit log with before/after data. Notes on design decisions and gotchas."
cover:
  image: "/images/og/bracket-fab-audit-log-rails.png"
  alt: "Bracket FAB Audit Log Rails"
  hidden: true
categories: ["Rails"]
---

When you're designing three features simultaneously, they start bleeding into each other. This time I added the following to a tournament bracket management app:

1. **FAB Feedback Button** — floating button bottom-right → Telegram notification
2. **Role-Based Bracket Edit Permissions** — tournament vs. friendly mode determines whether regular participants can edit the bracket
3. **Audit Log** — records who changed what and when, with before/after data

Each is simple on its own, but doing them together forced a lot of decisions: where to check permissions, where to write logs, and how much to expose in the UI.

---

## 1. FAB Feedback Button

### Design Choice

My first instinct was to reuse the existing feedback system (which was built as a Lookbook dev tool), but the auth structure was different enough that it made more sense to create a separate controller.

Final structure:

```
UserFeedbacksController#create
  → TelegramNotifier.notify_user_feedback
  → 200 JSON response
```

The view is handled by a single Stimulus controller.

```js
// feedback_fab_controller.js
static targets = ["panel", "fab", "formArea", "success", "message", "submitBtn"]

async submit(event) {
  event.preventDefault()
  const data = new FormData(event.target)
  const response = await fetch(event.target.action, {
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

I used plain `fetch` instead of Turbo Streams because I only need to toggle local panel state on success — no DOM updates from the server. Turbo Streams would add complexity without benefit here.

### Telegram Service

Added one method to the existing notifier service:

```ruby
def self.notify_user_feedback(user:, message:, context: nil)
  return unless configured?

  text = <<~MSG
    💬 *App Feedback*
    👤 *User:* `#{escape(user.display_name)}`
    📧 *Email:* `#{escape(user.email)}`
    #{"📍 *Page:* `#{escape(context)}`\n" if context.present?}
    💬 *Message:*
    #{escape(message.truncate(500))}
  MSG

  send_message(text.strip)
end
```

Passing `request.path` as `context` means the Telegram message shows exactly which page the user was on — useful for debugging.

---

## 2. Role-Based Bracket Edit Permissions

### Requirements

- **Tournament mode**: only organizer/admin can edit the bracket
- **Friendly mode**: organizer can optionally allow regular participants to edit

One column added to the Tournament model:

```ruby
# migration
add_column :tournaments, :allow_user_bracket_edit, :boolean, default: false, null: false
```

Pundit policy:

```ruby
def edit_bracket?
  return false unless authenticated?
  return true if admin? || tournament_organizer?
  return false unless record.respond_to?(:allow_user_bracket_edit)

  record.allow_user_bracket_edit? && tournament_player?
end
```

### Form UI: Show Checkbox Only in Friendly Mode

A Stimulus controller listens to the mode select and toggles the checkbox section:

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

Initial state matters: when editing an existing friendly tournament, `tournament.friendly?` is already true so we start without `hidden`. For new creates or tournament mode, start hidden.

---

## 3. Audit Log Design

### Schema

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

I used `jsonb` for before/after data. The fields stored differ by `action_type`, so a flexible jsonb column is cleaner than trying to normalize everything into fixed columns.

### Writing Logs in the Controller

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
end
```

The order matters: `authorize` must come before the DB write and the log. If the user doesn't have permission, `NotAuthorizedError` is raised and nothing gets written.

### Displaying Before/After in the View

```erb
<div class="grid grid-cols-2 gap-3">
  <div class="rounded-xl border border-rose-100 bg-rose-50 p-3">
    <p class="text-xs font-semibold text-rose-500">Before</p>
    <% log.before_data.each do |key, value| %>
      <p class="text-xs text-rose-700"><%= key %>: <code><%= value %></code></p>
    <% end %>
  </div>
  <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-3">
    <p class="text-xs font-semibold text-emerald-500">After</p>
    <% log.after_data.each do |key, value| %>
      <p class="text-xs text-emerald-700"><%= key %>: <code><%= value %></code></p>
    <% end %>
  </div>
</div>
```

Iterating over the jsonb directly keeps the view simple. The tradeoff is that key names need to be human-readable when saved.

---

## 4. The + Button: Adding Rounds and Slots

Added + buttons to the bracket view: one per round card (adds a slot to that round) and one at the end of the round list (adds a new round).

```erb
<%# Per-round: add slot %>
<%= button_to tournament_bracket_add_slot_path(@tournament),
    method: :post,
    params: { round_id: round.id },
    data: { turbo_confirm: "Add a slot to #{round.display_name}?" } do %>
  + icon
<% end %>

<%# End of list: add round %>
<%= button_to tournament_bracket_add_round_path(@tournament),
    method: :post,
    data: { turbo_confirm: "Add a new round?" } do %>
  + Add Round
<% end %>
```

`turbo_confirm` handles the confirmation dialog without extra JS. Turbo intercepts `data-turbo-confirm` and shows a native `window.confirm` before the form submits.

---

## Gotchas

### 1. `button_to` generates a `<form>`

When you need POST via a button, `button_to` is the right tool — it wraps the button in a `<form>`. I initially tried `link_to` with `method: :post` but ran into Turbo method conflicts. `button_to` just works.

### 2. Stimulus `data-action` event prefix

`data-action="feedback-fab#toggle"` automatically binds to the `click` event. But for form submission you must be explicit: `submit->feedback-fab#submit`. Without the event prefix, Stimulus won't catch the submit event.

### 3. Ruby symbol keys in jsonb come back as strings

If you write `before_data: { rounds_count: 3 }` (symbol key), PostgreSQL stores it as `"rounds_count"` (string key). Accessing `log.before_data[:rounds_count]` returns `nil`. Use `log.before_data["rounds_count"]` or call `stringify_keys` before saving. I switched to always using string keys when writing to jsonb to stay consistent.

### 4. Authorization before side effects

Pundit's `authorize` raises `NotAuthorizedError` immediately if the user lacks permission. Any DB writes or log entries after `authorize` won't execute on an unauthorized request. If you want to log unauthorized attempts, you'd need to rescue the error explicitly.

---

## Admin Panel Reflection

After adding features, they need to be visible in the admin panel. Added to the admin tournament detail page:

- **Event Settings card**: match type, bracket format, sets/games, `allow_user_bracket_edit` status
- **Bracket edit history card**: most recent 10 log entries
- **Operational section links**: direct links to players, courts, matches, bracket
- **Dynamic risk box**: actual DB-based warnings (no courts, no players, draft status) instead of static placeholder text

Making admin visibility a habit matters. If a config flag is changed and it's not surfaced in the admin panel, it's effectively invisible to operators — you won't know something is wrong until it affects users.

---

## Summary

| Feature | Key decision |
|---------|-------------|
| FAB feedback | `fetch` + Stimulus state, not Turbo Streams |
| Edit permissions | Pundit `edit_bracket?` with mode-based branching |
| Audit log | jsonb before/after, string keys for consistency |
| + button | `button_to` + `turbo_confirm` |
| Admin | Config visibility, log card, dynamic risk warnings |

The three features share a single flow: "an authorized user makes a change → log it." Keeping that in one place in the controller keeps it consistent.
