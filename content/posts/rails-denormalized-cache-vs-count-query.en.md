---
title: "Rails Denormalized Cache Column vs COUNT Query Mismatch: When Seed Data Creates 0%"
date: 2025-12-16
draft: false
tags: ["Rails", "Debugging", "Database", "Denormalization", "Seed Data", "PostgreSQL"]
description: "Why seed data that directly updated columns showed 0% on screen. Debugging the mismatch between vote_count cache column and votes.count() query."
cover:
  image: "/images/og/rails-denormalized-cache-vs-count-query.png"
  alt: "Rails Denormalized Cache Vs Count Query"
  hidden: true
---


I inserted demo seed data directly into a Rails app, and all percentages showed as **0%** on the screen.

Server logs were clean, the data was clearly in the DB, yet the numbers would not appear.

---

## Situation

This was a Rails app with a voting feature. There is a screen showing vote counts per choice, calculating percentages against total votes and displaying them with progress bars and numbers.

I needed to show a demo, so I fetched real-time data from an external API and inserted it as seed data. The approach was simple:

```ruby
# Seed data: directly update columns
choice.update_column(:vote_count, 4712)
pick.update_column(:total_votes, 6536)
```

Querying the DB directly showed the numbers were properly stored. But on the screen:

```
Choice A   0%
Choice B   0%
Choice C   0%
```

All 0%.

---

## Cause Analysis

I opened the `results` method of the `Pick` model.

```ruby
# The problematic code
def results
  total = votes.count  # <- COUNTs actual Vote records
  ordered_choices = choices.order(:position).to_a

  ordered_choices.map.with_index do |choice, index|
    {
      choice_id: choice.id,
      label: choice.label,
      count: choice.vote_count,
      percentage: total.zero? ? 0 : (choice.vote_count.to_f / total * 100).round(1),
      color: result_color_for_choice(index, choice.color)
    }
  end
end
```

`total = votes.count` -- that was the problem.

This code COUNTs actual records in the `Vote` table through the association.
The seed data only updated the `vote_count` and `total_votes` **columns**,
without inserting a single record into the `Vote` table.

The result:

| Data | Value |
|------|-------|
| `pick.total_votes` | 6,536 |
| `choice.vote_count` | 4,712 |
| `Vote.where(pick: pick).count` | **0** |

Since `total` (the denominator) was 0, `percentage` was also 0.

---

## Model Structure: Two Kinds of Counts

The app's models had two paths for tracking vote counts.

```
votes (table)           <- Actual records created when a user votes
  - user_id
  - pick_id
  - choice_id

choices (table)
  - vote_count          <- Denormalized cache column (integer)

picks (table)
  - total_votes         <- Denormalized cache column (integer)
```

In the normal voting flow, both are updated simultaneously.

```ruby
# When voting: Create Vote record + increment cache columns
Vote.create!(user: user, pick: pick, choice: choice)
choice.increment!(:vote_count)
pick.increment!(:total_votes)
```

However, since the seed data skipped this flow and only touched the cache columns, the `results` method that calculates based on `votes.count` perceived "there are no votes at all."

---

## Solution

Changed the code to use the `total_votes` cache column as the denominator.

```ruby
# After fix
def results
  total = total_votes.to_i  # <- Use cache column
  ordered_choices = choices.order(:position).to_a

  ordered_choices.map.with_index do |choice, index|
    {
      choice_id: choice.id,
      label: choice.label,
      count: choice.vote_count,
      percentage: total.zero? ? 0 : (choice.vote_count.to_f / total * 100).round(1),
      color: result_color_for_choice(index, choice.color)
    }
  end
end
```

The change is a single line: `votes.count` to `total_votes.to_i`.

---

## Which Choice Is Correct

Which one should you use? It depends on the situation.

### When to Use `votes.count`

- When real-time accuracy is critical
- When the cache column update logic cannot be trusted
- When the data volume is small enough that N+1 is not a major issue

```sql
-- COUNT query fires every time
SELECT COUNT(*) FROM votes WHERE pick_id = ?
```

### When to Use the `total_votes` Cache Column

- The principle is to read display numbers from cache columns
- Resolved with a single column read without an extra query
- Compatible with direct updates like seed data and admin manual adjustments

For cases like vote tallying where data is **frequently read and accuracy matters**, denormalization is a common pattern.
The very reason `total_votes` exists is "to avoid firing a COUNT query every time,"
so it is consistent to base display logic on this column.

---

## Cautions When Writing Seed Data

The root cause of this issue was that the seed data did not follow the app's "business flow."

The app's normal voting flow is:

```
Create Vote record -> increment vote_count -> increment total_votes
```

The seed data only touched the cache columns. If the reading side expects Vote records, problems arise.

There are two seed data strategies:

**Method A: Insert Through Service Objects/Methods (Recommended)**

```ruby
# Consistency guaranteed because it follows the app's voting logic
VoteService.call(user: admin_user, pick: pick, choice: choice)
```

**Method B: Directly Update Only Cache Columns (Simple but Requires Caution)**

```ruby
# The reading logic must be cache-column-based
choice.update_column(:vote_count, 4712)
pick.update_column(:total_votes, 6536)
```

When using Method B, you must verify that all methods consuming the data use the cache columns.

---

## Debugging Flow Summary

```
Confirm 0% display
  -> Check CSS class in HTML (option-compact-prob)
  -> Check component code -> Confirm pick.results call
  -> Check pick.rb results method
  -> Find votes.count -> Check Vote record count -> 0 records
  -> Check total_votes column -> Has value
  -> Change total = votes.count -> total = total_votes
```

Understanding what the cause was mattered more than the time spent finding it.
If you only look at the symptom "0% appears on screen" and dig through views, you will get lost. You need to trace the data flow.

---

## Closing

Denormalized cache columns are frequently used for performance, but you must always be aware that they create **two sources of truth**.

- Source: `Vote` table records
- Cache: `total_votes`, `vote_count` columns

It is important to always ensure that the reading code and the writing code are looking at the same source, and that seed data or admin operations are updating the correct source.
