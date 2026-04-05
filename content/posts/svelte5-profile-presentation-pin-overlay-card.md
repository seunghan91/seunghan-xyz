---
title: "프로필 페이지 발표자료 핀 시스템 — Instagram 스타일 +N 오버레이 카드 만들기"
date: 2026-04-05
draft: false
tags: ["svelte5", "rails", "ui-design", "css", "active-storage"]
description: "Rails 8 + Svelte 5 프로필 페이지에 발표자료 핀 시스템을 만들면서 겪은 디자인 진화 과정. 버튼 → 빈 카드 → Instagram 스타일 썸네일 오버레이까지, Service Worker 캐시 함정과 N+1 해결기."
---

공개 프로필 페이지를 만들고 있었다. link-in-bio 스타일로, `/@username` 경로에서 사용자의 소개, 링크, 발표자료를 보여주는 페이지다. 발표자료가 9개 올라가 있었는데, 전부 나열하니까 프로필이 포트폴리오 사이트처럼 변해버렸다. 스크롤이 길어지고, 정작 중요한 링크들이 묻혔다.

사용자가 원하는 3개만 "핀"해서 보여주고, 나머지는 별도 페이지로 유도하는 게 맞았다. 그런데 "더보기"를 어떻게 보여줄지가 문제였다. 별도 버튼? 빈 카드? 결국 Instagram 앨범처럼 마지막 썸네일 위에 반투명 오버레이를 올리는 방식으로 갔다. 이 글은 그 과정의 기록이다.

---

## 기존 구조: 전부 보여주기

처음 구현은 단순했다. 컨트롤러에서 `published.on_profile` 스코프로 가져온 발표자료를 전부 넘기고, 프론트에서 2열 그리드로 렌더링했다.

```ruby
# public_profiles_controller.rb
presentations = user.presentations.published.on_profile
  .includes(thumbnail_attachment: :blob).ordered
  .map { |pt| presentation_summary_json(pt) }
```

DB에는 이미 `show_on_profile` boolean 컬럼이 있었다. 프레젠테이션 매니저에서 토글할 수 있게 해뒀던 건데, 제한이 없어서 9개 전부 `true`였다. 프로필 페이지가 썸네일 갤러리가 돼버렸다.

---

## 1단계: Model에 핀 제한 걸기

DB 스키마를 건드리지 않고, 기존 `show_on_profile` 컬럼에 최대 개수 제한만 추가했다.

```ruby
# app/models/presentation.rb
class Presentation < ApplicationRecord
  MAX_PINNED = 3

  validate :validate_max_pinned, if: :show_on_profile_changed?

  private

  def validate_max_pinned
    return unless show_on_profile?

    pinned_count = user.presentations
      .where(show_on_profile: true)
      .where.not(id: id).count

    if pinned_count >= MAX_PINNED
      errors.add(:show_on_profile,
        "은 최대 #{MAX_PINNED}개까지만 설정할 수 있습니다")
    end
  end
end
```

핵심은 `where.not(id: id)`다. 자기 자신을 제외하고 카운트해야 이미 핀된 레코드를 다시 저장할 때 validation이 통과한다. 이걸 빼먹으면 기존 핀도 수정이 안 된다.

---

## 2단계: 컨트롤러 — 3+1 쿼리 전략

프로필에는 3개만 보여주면 되는데, "더보기" 오버레이에 4번째 썸네일이 필요했다. 그래서 `limit(MAX_PINNED + 1)`로 4개를 가져오고, 전체 개수는 별도로 카운트했다.

```ruby
# public_profiles_controller.rb#show
pinned_presentations = user.presentations.published.on_profile
  .includes(thumbnail_attachment: :blob)
  .ordered.limit(Presentation::MAX_PINNED + 1)
  .map { |pt| presentation_summary_json(pt, show_status: is_owner) }

total_published_count = user.presentations.published.count

render inertia: "Public/Profile", props: {
  presentations: pinned_presentations,
  total_presentations_count: total_published_count,
  # ...
}
```

`total_presentations_count`를 프론트에 넘기는 이유는 "+6"처럼 남은 개수를 계산하기 위해서다. `9 - 3 = 6`이 프론트에서 계산된다.

전체 발표자료를 볼 수 있는 페이지도 추가했다.

```ruby
# config/routes.rb
get "/@:username/presentations",
    to: "public_profiles#presentations",
    as: :public_profile_presentations,
    constraints: { username: /[a-z0-9_]{3,30}/ }
```

기존 `/@:username/posts`, `/@:username/followers`와 같은 패턴이라 라우트 구조가 자연스럽다.

---

## 3단계: 프론트엔드 디자인 진화 — 세 번의 시도

여기서 가장 오래 걸렸다. "더보기"를 어떻게 보여줄지 세 가지 접근을 시도했다.

### 시도 1: 별도 버튼

그리드 아래에 `발표자료 전체보기 (9) →` 링크 버튼을 넣었다.

```svelte
{#if total_presentations_count > presentations.length}
  <a href="/@{profile.username}/presentations" class="pt-more-link">
    발표자료 전체보기 ({total_presentations_count})
  </a>
{/if}
```

동작은 했지만, 카드 그리드와 버튼 사이에 시각적 분리감이 있었다. 프로필 페이지에서 이 버튼이 너무 "기능적"으로 보였다. link-in-bio 스타일과 안 어울렸다.

### 시도 2: 빈 "+N 더보기" 카드

그리드 안에 카드 형태로 넣어봤다. 2x2 그리드의 4번째 칸에 "+6 더보기" 텍스트만 있는 카드.

```svelte
<a href="/@{profile.username}/presentations" class="pt-card pt-more-card">
  <div class="pt-thumb pt-more-thumb">
    <span class="pt-more-count">+6</span>
    <span class="pt-more-label">더보기</span>
  </div>
</a>
```

그리드 안에 들어가니 레이아웃은 깔끔했지만, 썸네일 3개 옆에 빈 카드가 하나 있으니 허전했다. 시각적으로 "빠진 느낌"이 있었다.

### 시도 3 (최종): 썸네일 위 반투명 오버레이

Facebook이나 Instagram에서 앨범 사진이 많을 때 마지막 사진 위에 "+3"을 올리는 패턴이 있다. 이걸 가져왔다. 4번째 발표자료의 실제 썸네일을 보여주면서, 그 위에 반투명 검정 오버레이와 "+6" 텍스트를 올렸다.

```svelte
<script>
  const maxVisiblePts = 3
  const hasMorePts = $derived(total_presentations_count > maxVisiblePts)
  const remainingPtsCount = $derived(total_presentations_count - maxVisiblePts)
  const visiblePts = $derived(
    hasMorePts ? presentations.slice(0, maxVisiblePts) : presentations
  )
  const overlayPt = $derived(
    hasMorePts && presentations.length > maxVisiblePts
      ? presentations[maxVisiblePts] : null
  )
</script>

{#if hasMorePts}
  <a href="/@{profile.username}/presentations" class="pt-card pt-more-card">
    <div class="pt-thumb">
      {#if overlayPt?.thumbnail_url}
        <img src={overlayPt.thumbnail_url} alt="더보기" />
      {/if}
      <div class="pt-more-overlay">
        <span class="pt-more-count">+{remainingPtsCount}</span>
      </div>
    </div>
  </a>
{/if}
```

CSS는 간단하다. `position: absolute; inset: 0;`으로 썸네일 전체를 덮는 오버레이를 만들고, hover 시 밝기를 조절한다.

```css
.pt-more-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}

.pt-more-card:hover .pt-more-overlay {
  background: rgba(0, 0, 0, 0.4);
}

.pt-more-count {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.02em;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}
```

이 패턴이 좋은 이유는 4번째 썸네일이 "더 있다"는 시각적 힌트를 주기 때문이다. 빈 카드보다 정보 밀도가 높고, 클릭 유도력도 강하다.

---

## 디자인 패턴 비교

| 방식 | 장점 | 단점 |
|------|------|------|
| 별도 버튼 | 구현 간단, 명확한 CTA | 그리드와 분리감, 페이지 길어짐 |
| 빈 카드 | 그리드 안에 통합 | 시각적으로 허전, 정보 없음 |
| 썸네일 오버레이 | 정보 밀도 높음, 자연스러운 유도 | 4번째 데이터 추가 쿼리 필요 |

Instagram, Facebook, Google Photos 등 사진 갤러리 서비스들이 오버레이 패턴을 쓰는 건 이유가 있다. 사용자가 "이 뒤에 뭐가 더 있구나"를 직관적으로 이해한다. 별도 버튼은 텍스트를 읽어야 하지만, 오버레이는 이미지 위의 숫자만으로 충분하다.

---

## 삽질 1: Service Worker가 Vite HMR을 먹었다

Svelte 파일을 수정했는데 브라우저에 반영이 안 됐다. Vite 캐시 삭제, 서버 재시작, 브라우저 새 탭 — 전부 소용없었다.

디버그 텍스트를 넣어봤다.

```svelte
<h3 class="presentations-heading">PRESENTATIONS_V2</h3>
```

파일에는 분명히 `PRESENTATIONS_V2`가 있는데, 브라우저에서는 계속 `Presentations`가 나왔다. Vite가 이 파일을 서빙하지 않고 있었다.

원인은 두 가지였다.

### 원인 1: 프로덕션 빌드 잔재

`public/vite-dev/assets/`에 이전 `rails assets:precompile`로 생성된 번들 파일이 남아있었다.

```
public/vite-dev/assets/
├── application-BqP15WHm.css
├── application-DH9g7BpV.js   ← 이 파일이 dev 서버를 무시하게 만듦
└── actioncable.esm-C2w5f1W4.js
```

Rails가 이 정적 파일을 직접 서빙하고 있어서, Vite dev 서버의 최신 코드가 무시됐다. `rm -rf public/vite-dev/assets/`로 해결.

### 원인 2: Service Worker 캐시

PWA를 위해 Service Worker를 등록해둔 상태였는데, SW가 이전 빌드의 JS 번들을 캐시하고 있었다. 프로덕션 빌드 잔재를 지우고 Vite dev 서버에서 로드하게 만들어도, SW 캐시에 남아있는 이전 버전이 계속 서빙됐다.

```javascript
// SW 등록 해제 + 캐시 전체 삭제
const regs = await navigator.serviceWorker.getRegistrations();
for (const reg of regs) await reg.unregister();
const keys = await caches.keys();
for (const key of keys) await caches.delete(key);
```

이걸 실행하고 나서야 최신 코드가 반영됐다. Vite 공식 문서에도 Service Worker가 캐시 관련 이슈를 일으킬 수 있다고 나와있다. dev 환경에서는 SW를 비활성화하거나, `navigator.serviceWorker.register()`에 조건을 거는 게 좋다.

```javascript
// 프로덕션에서만 SW 등록
if (import.meta.env.PROD) {
  navigator.serviceWorker.register('/sw.js');
}
```

Vite의 `node_modules/.vite` 캐시와 브라우저의 HTTP 캐시(`max-age=31536000,immutable`)도 원인이 될 수 있지만, 이번 경우는 SW 캐시가 주범이었다.

---

## 삽질 2: Svelte 5의 `{@const}` 제한

처음에는 템플릿 안에서 `{@const}`로 계산값을 선언했다.

```svelte
<!-- 에러 발생! -->
<div class="presentations-grid">
  {@const maxVisible = 3}
  {@const hasMore = total_presentations_count > maxVisible}
  ...
</div>
```

Vite 에러가 떴다:

```
[plugin:vite-plugin-svelte]
`{@const}` must be the immediate child of
`{#snippet}`, `{#if}`, `{:else if}`,
`{:else}`, `{#each}`, `{:then}`,
`{:catch}`, `<svelte:fragment>`,
or `<Component>`
```

Svelte 5에서 `{@const}`는 로직 블록(`{#if}`, `{#each}` 등) 안에서만 쓸 수 있다. 일반 HTML 엘리먼트의 직접 자식으로는 안 된다. `$derived`로 옮겨서 해결했다.

```svelte
<script>
  // $derived로 스크립트 블록에 선언
  const maxVisiblePts = 3
  const hasMorePts = $derived(total_presentations_count > maxVisiblePts)
  const remainingPtsCount = $derived(total_presentations_count - maxVisiblePts)
  const visiblePts = $derived(
    hasMorePts ? presentations.slice(0, maxVisiblePts) : presentations
  )
</script>
```

Svelte 4에서는 `$:` 반응형 선언으로 어디서든 사용할 수 있었지만, Svelte 5의 runes 모드에서는 `$derived`, `$state` 등을 스크립트 블록에 명시적으로 선언해야 한다. `{@const}`는 특정 블록 스코프 안에서만 허용되는 제한이 생겼다.

---

## 삽질 3: Active Storage N+1 — Bullet 경고

프로필 페이지를 로드하니 Bullet gem이 경고를 띄웠다.

```
USE eager loading detected
User => [:avatar_attachment]
Add to your query: .includes([:avatar_attachment])
```

`profile_json`에서 `user.avatar_url`을 호출하는데, `avatar`가 Active Storage attachment라서 별도 쿼리가 발생한 것이다. Rails에서 Active Storage는 내부적으로 `ActiveStorage::Attachment`와 `ActiveStorage::Blob` 두 모델을 사용한다.

```ruby
# has_one_attached :avatar 가 내부적으로 추가하는 association:
has_one :avatar_attachment,
  -> { where(name: "avatar") },
  class_name: "ActiveStorage::Attachment",
  as: :record
has_one :avatar_blob,
  through: :avatar_attachment,
  class_name: "ActiveStorage::Blob",
  source: :blob
```

해결은 `includes`에 `avatar_attachment: :blob`을 추가하는 것이다.

```ruby
# Before
user = User.kept.includes(:page_theme)
  .find_by!(username: params[:username])

# After
user = User.kept.includes(:page_theme, avatar_attachment: :blob)
  .find_by!(username: params[:username])
```

Rails에서는 `with_attached_avatar` 스코프를 제공하지만, 다른 association과 함께 eager load할 때는 `includes(avatar_attachment: :blob)` 형태가 더 명시적이다. `with_attached_avatar`는 내부적으로 `includes("avatar_attachment": :blob)`과 동일하다.

같은 패턴의 쿼리가 `show`, `posts`, `followers`, `following` 4개 액션에 있어서 전부 수정했다.

---

## Active Storage eager loading 정리

Active Storage의 N+1 문제는 흔하지만 놓치기 쉽다. 정리하면 이렇다.

| attachment 타입 | eager loading | scope |
|----------------|--------------|-------|
| `has_one_attached :avatar` | `includes(avatar_attachment: :blob)` | `with_attached_avatar` |
| `has_many_attached :images` | `includes(images_attachments: :blob)` | `with_attached_images` |

주의할 점:

- `has_one_attached`는 `avatar_attachment` (단수)
- `has_many_attached`는 `images_attachments` (복수)
- variant를 사용하면 `variant_records`도 eager load해야 할 수 있다
- 중첩된 association이면 `includes(user: { avatar_attachment: :blob })` 형태로

Bullet gem을 사용하면 개발 환경에서 이런 문제를 JS 콘솔 경고로 바로 잡아준다. 프로덕션에 N+1이 나가기 전에 잡을 수 있어서, Rails 프로젝트라면 필수로 넣어두는 게 좋다.

---

## 전체 구조 요약

최종적으로 이런 구조가 됐다.

```
/@seunghan (프로필 페이지)
├─ 프로필 헤더 (아바타, 이름, 소속, bio)
├─ 소셜 링크
├─ 통계 (게시글, 팔로워, 발표자료)
├─ 링크 목록
├─ Presentations (2x2 그리드)
│  ├─ 핀된 발표자료 1
│  ├─ 핀된 발표자료 2
│  ├─ 핀된 발표자료 3
│  └─ 4번째 썸네일 + "+6" 오버레이 → /@seunghan/presentations
├─ 이메일 캡처 폼
└─ Powered by AX Hub

/@seunghan/presentations (전체 목록)
├─ 프로필 미니 헤더
└─ 전체 발표자료 그리드 (2-3열)
```

데이터 흐름:

```
Controller: .limit(MAX_PINNED + 1) → 4개
           + total_count → 9

Frontend:  visiblePts = slice(0, 3) → 카드 3개
           overlayPt = [3] → 4번째 썸네일
           remainingCount = 9 - 3 = 6 → "+6"
```

서버에서 4개만 가져오기 때문에 9개를 전부 가져오는 것보다 효율적이다. 전체 카운트는 `COUNT(*)` 쿼리 하나로 처리되니 부담이 없다.

---

## 결론

"더보기"를 어떻게 보여줄지는 사소해 보이지만, 프로필 페이지의 전체 인상을 바꾼다. 별도 버튼은 "클릭하세요"라고 말하지만, 썸네일 오버레이는 "여기 더 있어요"를 보여준다. 같은 기능이지만 사용자 경험이 다르다.

기술적으로는 DB 스키마 변경 없이 기존 컬럼에 validation만 추가해서 핀 제한을 구현한 것, 4개 쿼리로 3+1 데이터를 효율적으로 가져온 것이 깔끔했다.

삽질 면에서는 Service Worker 캐시가 Vite dev 서버를 완전히 무력화시킨 게 가장 당황스러웠다. dev 환경에서 SW를 끄는 건 앞으로 모든 PWA 프로젝트에서 기본으로 해둬야 할 것 같다.
