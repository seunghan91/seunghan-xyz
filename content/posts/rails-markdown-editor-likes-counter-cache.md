---
title: "Rails 커뮤니티 게시판에 마크다운 에디터 + 좋아요 시스템 붙이기 — importmap 환경에서의 현실적인 선택"
date: 2026-03-24
draft: false
tags: ["Rails", "Stimulus", "counter_cache", "마크다운", "importmap"]
categories: ["Rails"]
description: "Rails 8 importmap 환경에서 마크다운 에디터 라이브러리를 검토하고, 기존 Stimulus 컨트롤러를 재사용한 과정. counter_cache 패턴으로 좋아요 토글 구현, ERB 멀티라인 삼항연산자 구문 오류까지."
---

커뮤니티 게시판에 Q&A 기능을 만들고 있었다. 질문을 올릴 때 코드 블록이나 볼드 처리를 할 수 있어야 했고, 추천순 정렬 필터도 있으니 좋아요 기능도 필요했다. 그런데 이 프로젝트는 importmap-rails 기반이라 npm 패키지를 자유롭게 쓸 수 없는 환경이었다.

결론부터 말하면, 외부 라이브러리 없이 기존 Stimulus 컨트롤러를 재사용하는 게 가장 좋은 선택이었다. 그 과정에서 겪은 삽질들을 정리한다.

---

## importmap-rails 환경에서 마크다운 에디터 선택지

Rails 8의 기본 JS 관리 방식은 importmap이다. esbuild나 webpack 같은 번들러 없이, ESM(ES Modules)을 CDN에서 직접 가져다 쓴다. 설정이 단순한 대신 CommonJS 전용 패키지나 CSS를 함께 번들링해야 하는 라이브러리는 쓰기 어렵다.

마크다운 에디터 후보를 조사해봤다.

| 라이브러리 | 크기 | importmap 호환 | 특징 | 문제점 |
|-----------|------|---------------|------|--------|
| **EasyMDE** | ~100KB | O | 기본 툴바, side-by-side 프리뷰 | 2024년 이후 유지보수 불투명 |
| **Toast UI Editor** | ~200KB | O | 풀 툴바, split 프리뷰, 성숙도 높음 | CSS 별도 pin 필요, 무거움 |
| **ByteMD** | ~50KB | O | 초경량, 플러그인 기반 | 커스텀 설정 필요 |
| **Milkdown** | ~300KB+ | 부분적 | 플러그인 아키텍처 | React 의존성, 설정 복잡 |
| **Tiptap** | ~400KB+ | O | ProseMirror 기반, 확장성 | 마크다운 import/export 별도 구현 |
| **커스텀 Stimulus** | ~5KB | O | 완전한 제어, 제로 의존성 | 직접 구현해야 함 |

importmap에서 외부 라이브러리를 쓰려면 `./bin/importmap pin 패키지명 --from jsdelivr` 명령으로 vendor에 다운로드하는 방식이다. JS 파일만 딱 가져오면 되는 경우엔 잘 작동하지만, EasyMDE처럼 CSS도 함께 로드해야 하는 라이브러리는 별도로 stylesheet를 추가해줘야 한다.

```bash
# importmap으로 EasyMDE 설치 시도
./bin/importmap pin easymde --from jsdelivr
# => Pinning "easymde" to vendor/javascript/easymde.js
```

여기서 한 가지 깨달은 게 있었다.

---

## 이미 있는 걸 왜 다시 만드나

EasyMDE를 pin하고 Stimulus 컨트롤러를 작성하려던 참에, 프로젝트에 이미 `markdown_editor_controller.js`가 있다는 걸 발견했다. 과제 제출 폼에서 쓰고 있던 컨트롤러였다.

```javascript
// app/javascript/controllers/markdown_editor_controller.js
import { Controller } from "@hotwired/stimulus"

const MARKED_CDN = "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"

export default class extends Controller {
  static targets = ["textarea", "preview", "previewPanel",
                     "editorPanel", "previewTab", "editTab"]

  connect() {
    this.mode = "edit"
    this.loadMarked()
  }

  // Marked.js를 동적 로드
  loadMarked() {
    if (window.marked) return
    const script = document.createElement("script")
    script.src = MARKED_CDN
    script.onload = () => {
      window.marked.setOptions({ breaks: true, gfm: true })
    }
    document.head.appendChild(script)
  }

  // 툴바 액션들
  bold()       { this.wrap("**", "**") }
  italic()     { this.wrap("*", "*") }
  code()       { this.wrap("`", "`") }
  codeblock()  { this.wrap("\n```\n", "\n```\n") }
  link()       { this.wrap("[", "](url)") }
  listBullet() { this.insertLine("- ") }
  listOrdered(){ this.insertLine("1. ") }
  heading()    { this.insertLine("## ") }

  // 편집/미리보기 탭 전환
  showPreview() {
    if (!window.marked) {
      alert("마크다운 라이브러리 로딩 중입니다.")
      return
    }
    this.previewTarget.innerHTML =
      window.marked.parse(this.textareaTarget.value || "")
    this.editorPanelTarget.classList.add("hidden")
    this.previewPanelTarget.classList.remove("hidden")
  }

  // 텍스트 감싸기 유틸
  wrap(before, after) {
    const ta = this.textareaTarget
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const selected = ta.value.substring(start, end)
    ta.value = ta.value.substring(0, start)
      + before + selected + after
      + ta.value.substring(end)
    ta.focus()
    ta.setSelectionRange(
      start + before.length,
      start + before.length + selected.length
    )
  }
}
```

이 컨트롤러가 제공하는 기능:
- **툴바**: 굵게, 기울임, 인라인 코드, 코드 블록, 제목, 목록, 링크
- **편집/미리보기 탭** 전환 (Marked.js로 렌더링)
- **이미지 붙여넣기 / 드래그앤드롭** 업로드
- 외부 의존성: Marked.js만 CDN으로 동적 로드

EasyMDE를 설치하면 100KB+ 번들이 추가되고, CSS도 별도 관리해야 하고, 또 다른 Stimulus 컨트롤러를 작성해야 한다. 반면 기존 컨트롤러는 5KB도 안 되고, 이미 검증된 코드다.

**바로 EasyMDE를 unpin했다.**

```bash
./bin/importmap unpin easymde
# => Unpinning and removing "easymde"
```

---

## 커스텀 Stimulus 에디터 vs 외부 라이브러리 — 언제 뭘 쓸까

Rails Designer 블로그에서도 비슷한 접근을 권장한다. GitHub 스타일의 마크다운 textarea를 Stimulus로 직접 구현하는 방식이다. 핵심 로직은 `selectionStart`, `selectionEnd`, `setRangeText` 세 가지 Web API면 충분하다.

```javascript
// GitHub 스타일 마크다운 포맷팅의 핵심
formatText({ with: marker, by = "wrapping" }) {
  const start = this.contentTarget.selectionStart
  const end = this.contentTarget.selectionEnd
  const selected = this.contentTarget.value
    .substring(start, end) || "text"

  const formatted = by === "wrapping"
    ? `${marker}${selected}${marker}`
    : `${marker}${selected}`

  this.contentTarget.setRangeText(formatted, start, end, "select")
}
```

### 커스텀 Stimulus가 나은 경우
- importmap 환경 (번들러 없음)
- 필요한 기능이 기본 포맷팅 + 미리보기 정도
- 프로젝트에 이미 유사한 컨트롤러가 있을 때
- 번들 크기에 민감한 경우

### 외부 라이브러리가 나은 경우
- WYSIWYG 수준의 편집 경험이 필요할 때
- 테이블 에디터, 수식(KaTeX), 다이어그램 등 고급 기능
- esbuild/webpack 환경이라 번들링 자유로울 때

AppSignal 블로그(2025.12)에서는 Rails 8.1부터 마크다운이 content type으로 지원되고, Marksmith 같은 gem도 나왔다고 소개한다. 하지만 2026년 3월 기준으로 importmap과 매끄럽게 통합되는 올인원 솔루션은 아직 없다. 결국 "기존 코드 재사용"이 가장 현실적인 선택이었다.

---

## ERB에서 재사용: 뷰 파셜에 에디터 적용

기존 과제 제출 폼에서 쓰던 에디터 마크업을 Q&A 폼에 그대로 적용했다. 핵심은 `data-controller="markdown-editor"`를 감싸는 div 하나다.

```erb
<%# 기존: plain textarea %>
<%= form.text_area :body, rows: 10,
    placeholder: "질문 내용을 입력하세요",
    class: "w-full rounded-2xl border px-4 py-3" %>

<%# 변경 후: 마크다운 에디터 %>
<div data-controller="markdown-editor">
  <%# 편집/미리보기 탭 %>
  <div style="display:flex; gap:4px; border-bottom:1px solid var(--border-default);">
    <button type="button"
      data-markdown-editor-target="editTab"
      data-action="click->markdown-editor#showEdit">편집</button>
    <button type="button"
      data-markdown-editor-target="previewTab"
      data-action="click->markdown-editor#showPreview">미리보기</button>
  </div>

  <%# 툴바 %>
  <div data-markdown-editor-target="editorPanel">
    <div style="display:flex; flex-wrap:wrap; gap:2px; padding:5px 4px;">
      <% [
        ["B",   "굵게",     "bold",      "font-weight:700"],
        ["I",   "기울임",   "italic",    "font-style:italic"],
        ["</>", "코드",     "code",      "font-family:monospace"],
        ["```", "코드블록", "codeblock", "font-family:monospace"],
        ["H2",  "제목",     "heading",   "font-weight:600"],
        ["•—",  "목록",     "listBullet",""],
        ["1.",  "번호목록", "listOrdered",""],
      ].each do |label, title, action, style| %>
        <button type="button" title="<%= title %>"
          data-action="click->markdown-editor#<%= action %>"
          style="<%= style %>"><%= label %></button>
      <% end %>
    </div>

    <%= form.text_area :body, rows: 10,
      data: {
        "markdown-editor-target": "textarea",
        action: "paste->markdown-editor#handlePaste"
      },
      style: "font-family:monospace;" %>
  </div>

  <%# 미리보기 패널 %>
  <div data-markdown-editor-target="previewPanel" class="hidden">
    <div data-markdown-editor-target="preview"
         class="prose prose-sm max-w-none"></div>
  </div>
</div>
```

ERB에서 툴바 버튼을 배열로 선언하고 `each`로 돌리는 패턴이 눈에 띌 거다. 버튼이 8개나 되니까 하드코딩하면 마크업이 엄청나게 길어진다. Ruby 배열로 정리하면 한 곳에서 관리할 수 있다.

이 마크업을 Q&A 글 작성 폼, 답변 작성 폼, 일반 게시판 댓글 폼 — 총 3곳에 적용했다.

---

## 좋아요 시스템: counter_cache 패턴

추천순 정렬 필터가 있었는데, 기존 구현은 댓글 수 기반이었다.

```ruby
# 기존: 댓글 수로 정렬 (N+1 쿼리 위험)
scope :ordered_by_popular, -> {
  left_joins(:post_comments)
    .group(:id)
    .order(Arel.sql("COUNT(post_comments.id) DESC"))
}
```

이걸 실제 좋아요 기반으로 바꾸려면 `post_likes` 테이블이 필요하다.

### 테이블 설계

1인 1좋아요를 보장하기 위해 `[post_id, user_id]`에 unique index를 건다.

```ruby
# db/migrate/xxx_create_post_likes.rb
class CreatePostLikes < ActiveRecord::Migration[8.1]
  def change
    create_table :post_likes do |t|
      t.references :post, null: false, foreign_key: true
      t.references :user, null: false, foreign_key: true
      t.timestamps
    end
    add_index :post_likes, [:post_id, :user_id], unique: true
  end
end

# db/migrate/xxx_add_likes_count_to_posts.rb
class AddLikesCountToPosts < ActiveRecord::Migration[8.1]
  def change
    add_column :posts, :likes_count, :integer, default: 0, null: false
  end
end
```

`default: 0, null: false`는 필수다. 이게 없으면 `nil + 1`이 되면서 counter_cache가 깨진다. Rails 공식 문서에서도 이 부분을 강조한다.

### 모델 설정

```ruby
# app/models/post_like.rb
class PostLike < ApplicationRecord
  belongs_to :post, counter_cache: :likes_count
  belongs_to :user

  validates :user_id, uniqueness: { scope: :post_id }
end

# app/models/post.rb
class Post < ApplicationRecord
  has_many :post_likes, dependent: :destroy

  scope :ordered_by_popular, -> {
    order(pinned: :desc, likes_count: :desc, created_at: :desc)
  }

  def liked_by?(user)
    post_likes.exists?(user: user)
  end
end
```

`counter_cache: :likes_count`를 `belongs_to` 쪽에 선언하면, PostLike가 생성/삭제될 때 자동으로 Post의 `likes_count`가 증감된다. 직접 `UPDATE` 쿼리를 날릴 필요가 없다.

### counter_cache의 동작 원리

counter_cache는 콜백 기반이다. 내부적으로 이런 일이 벌어진다:

```ruby
# PostLike가 create될 때 (내부 동작)
Post.increment_counter(:likes_count, post_id)
# => UPDATE posts SET likes_count = COALESCE(likes_count, 0) + 1
#    WHERE id = ?

# PostLike가 destroy될 때
Post.decrement_counter(:likes_count, post_id)
# => UPDATE posts SET likes_count = COALESCE(likes_count, 0) - 1
#    WHERE id = ?
```

`COALESCE`로 nil-safe하게 처리되고, 단일 `UPDATE` 쿼리라서 `SELECT COUNT(*)` 대비 훨씬 빠르다.

| 방식 | 쿼리 | 성능 |
|------|------|------|
| `post.post_likes.count` | `SELECT COUNT(*) FROM post_likes WHERE post_id = ?` | 매번 집계 |
| `post.likes_count` | 이미 posts 테이블에 저장 | 추가 쿼리 없음 |

목록 페이지에서 20개 게시글의 좋아요 수를 보여줄 때, count 방식이면 20번의 추가 쿼리가 발생한다. counter_cache면 0번이다.

### 주의할 점

counter_cache에는 알려진 함정이 몇 가지 있다:

1. **직접 SQL로 데이터를 삭제하면 카운터가 틀어진다.** `PostLike.delete_all` 같은 건 콜백을 타지 않는다. `destroy_all`을 써야 한다.
2. **동시 요청 시 race condition.** 같은 게시글에 수백 명이 동시에 좋아요를 누르면 DB row lock이 걸릴 수 있다. 소규모 커뮤니티라면 문제없지만, 대규모라면 Redis 버퍼를 고려해야 한다.
3. **카운터가 틀어졌을 때 리셋.** `Post.reset_counters(post.id, :post_likes)`로 실제 count와 동기화할 수 있다.

```ruby
# 전체 게시글 카운터 리셋 (rake task로 만들어두면 좋다)
Post.find_each do |post|
  Post.reset_counters(post.id, :post_likes)
end
```

---

## 댓글 좋아요도 같은 패턴으로

글 좋아요와 동일한 구조를 댓글에도 적용했다. 테이블 하나 더 만들면 된다.

```ruby
# app/models/post_comment_like.rb
class PostCommentLike < ApplicationRecord
  belongs_to :post_comment, counter_cache: :likes_count
  belongs_to :user

  validates :user_id, uniqueness: { scope: :post_comment_id }
end
```

### 토글 컨트롤러 액션

좋아요는 "토글" 방식이다. 이미 좋아요 했으면 취소, 안 했으면 추가.

```ruby
# app/controllers/community_posts_controller.rb
def toggle_like
  like = @post.post_likes.find_by(user: current_user)
  if like
    like.destroy
  else
    @post.post_likes.create!(user: current_user)
  end
  redirect_back fallback_location: community_post_path(@category, @post)
end
```

unique index 덕분에 동시에 두 번 좋아요를 누르더라도 DB 레벨에서 중복이 막힌다. `validates :user_id, uniqueness: ...`는 애플리케이션 레벨 방어, unique index는 DB 레벨 방어 — 이중으로 잡는 거다.

### 뷰에서 좋아요 상태 표시

```erb
<% liked = @post.liked_by?(current_user) %>
<%= button_to toggle_like_path, method: :post,
      style: liked ? "color: var(--color-primary-500);"
                   : "color: var(--text-secondary);" do %>
  <svg viewBox="0 0 24 24"
       fill="<%= liked ? 'currentColor' : 'none' %>"
       stroke="currentColor">
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06
             a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78
             1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
  </svg>
  좋아요 <%= @post.likes_count if @post.likes_count > 0 %>
<% end %>
```

좋아요 여부에 따라 하트 아이콘의 `fill`을 `currentColor`(채움) / `none`(빈 하트)으로 토글한다. CSS 변수로 색상을 제어하니까 다크모드도 자연스럽게 대응된다.

### N+1 방지

목록에서 각 댓글의 좋아요 여부를 확인하면 N+1이 발생한다. `includes`로 미리 로드한다.

```ruby
# 컨트롤러
@post_comments = @post.post_comments
  .top_level
  .includes(:user, :post_comment_likes)
  .ordered
```

---

## ERB 멀티라인 삼항연산자 — 은근히 자주 걸리는 함정

작업 도중 채팅 페이지에서 `ActionView::SyntaxErrorInTemplate` 에러가 터졌다. 원인은 이거였다:

```erb
<%# 이러면 에러 난다 %>
<div style="<%= is_mine
                  ? 'background: blue;'
                  : 'background: gray;' %>">
```

ERB 태그 `<%= ... %>` 안에서 멀티라인 삼항연산자를 쓰면 파서가 제대로 해석하지 못한다. ERB는 `<%= ... %>`를 한 줄의 Ruby 표현식으로 처리하는데, 줄바꿈이 들어가면 각 줄을 별도 구문으로 파싱하려고 시도한다.

RuboCop에도 `Style/MultilineTernaryOperator` 규칙이 있다. "멀티라인 삼항연산자 대신 if/unless를 쓰라"고 경고한다.

### 해결법

한 줄로 합치면 된다:

```erb
<%# 한 줄로 합치면 정상 동작 %>
<div style="<%= is_mine ? 'background: blue;' : 'background: gray;' %>">
```

너무 길어서 한 줄이 부담스러우면 헬퍼 메서드로 빼거나, `if/else` 블록을 사용한다:

```erb
<%# if/else 블록으로 분리 %>
<% bg_style = if is_mine
     'background: blue; color: white;'
   else
     'background: gray; color: black;'
   end %>
<div style="<%= bg_style %>">
```

이 에러가 특히 위험한 건, **개발 서버에서는 잘 되다가 특정 시점에 갑자기 터지기도 한다**는 것이다. ERB 파서 버전이나 Ruby 버전에 따라 동작이 미묘하게 다를 수 있다. 안전하게 가려면 `<%= %>` 안에서는 항상 한 줄 표현식을 유지하는 게 좋다.

---

## 라우트 설계: 좋아요 토글 엔드포인트

```ruby
# config/routes.rb
scope "community/:category", as: :community do
  resources :posts, controller: :community_posts do
    member do
      patch :resolve
      patch :reopen
      post :toggle_like  # 글 좋아요 토글
    end
  end
end

resources :posts do
  resources :post_comments do
    member do
      patch :accept
      patch :upvote
      post :toggle_like  # 댓글 좋아요 토글
    end
  end
end
```

좋아요 토글은 `POST` 메서드를 사용했다. `PATCH`로 할 수도 있지만, "리소스를 생성하거나 삭제한다"는 의미에서 `POST`가 더 적절하다고 판단했다. RESTful하게 가려면 별도 리소스(`/posts/:id/likes`)로 분리하는 방법도 있지만, 토글 하나에 리소스를 분리하는 건 과하다.

---

## 최종 결과 정리

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| Q&A 질문 작성 | plain textarea | 마크다운 에디터 (툴바 + 미리보기) |
| 답변 작성 | TextAreaComponent | 마크다운 에디터 |
| 일반 댓글 | TextAreaComponent | 마크다운 에디터 |
| 추천순 정렬 | 댓글 수 기반 (`COUNT` 쿼리) | `likes_count` 컬럼 기반 (쿼리 없음) |
| 좋아요 | 없음 | 글 + 댓글 모두 1인 1좋아요 토글 |
| 외부 라이브러리 추가 | - | 0개 (기존 코드 재사용) |

---

## 돌아보며

이번 작업에서 가장 큰 교훈은 **"새 라이브러리를 추가하기 전에 기존 코드를 먼저 확인하라"**는 것이다. EasyMDE를 pin하고 컨트롤러를 작성하려던 순간, 이미 잘 동작하는 에디터가 프로젝트에 있었다. 5분이면 적용할 수 있는 걸 새 패키지 설치부터 시작했으면 30분은 더 걸렸을 거다.

counter_cache 패턴도 마찬가지다. 좋아요 수를 매번 `COUNT(*)`로 세는 건 기능적으로는 동일하지만, 게시글이 수백 개만 되어도 체감 성능 차이가 난다. `default: 0, null: false` 두 옵션만 기억하면 설정은 간단하다.

ERB 삼항연산자 에러는 한 번 겪으면 안 잊어버린다. `<%= %>` 안에서는 무조건 한 줄.

관련 포스트로 [ViewComponent 디자인 시스템 마이그레이션](/posts/viewcomponent-design-system-lookbook-migration/)과 [Tailwind v4 CSS 변수 테마 설정](/posts/tailwind-v4-theme-css-variable-override-pitfall/)도 참고하면 좋다.
