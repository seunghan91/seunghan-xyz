---
title: "ViewComponent 디자인 시스템을 Lookbook으로 이관하면서 만난 삽질들 — Rails 8 + Tailwind CSS 4"
date: 2026-03-10
draft: false
tags: ["Rails 8", "ViewComponent", "Lookbook", "디자인 토큰", "CSS Custom Properties", "Tailwind CSS 4", "컴포넌트 시스템"]
description: "47개 ViewComponent를 BMC 스타일 디자인 시스템으로 마이그레이션하면서 만난 실전 이슈들. CSS 변수 fallback 함정, @!group URL 매핑, String#[] TypeError 등 Lookbook 프리뷰 디버깅 기록."
cover:
  image: "/images/og/viewcomponent-design-system-lookbook-migration.png"
  alt: "ViewComponent Design System Lookbook Migration"
  hidden: true
categories: ["Rails", "Frontend"]
---

Rails 8에서 47개 ViewComponent 기반 디자인 시스템을 warm orange 테마로 전환하고, Lookbook 프리뷰를 전면 구축하면서 만난 삽질들을 정리했다.

---

## 배경

기존 프로젝트에는 다음이 갖춰져 있었다:
- **47개 ViewComponent** (input, layout, navigation, card, typography 등 15개 카테고리)
- **CSS Custom Properties** 기반 디자인 토큰 (`tokens.css`)
- **Tailwind CSS 4** + Propshaft 에셋 파이프라인

목표는 BMC(Buy Me a Coffee) 디자인을 레퍼런스로, warm orange 테마 + dark sidebar + stone palette로 전환하고, **Lookbook으로 전체 프리뷰를 구축**하는 것이었다.

---

## 1단계: 토큰 업데이트 — 의외로 빠진 것

### 문제: "토큰 파일 업데이트했는데 왜 파란색이지?"

```css
/* 기존 tokens.css (33줄) */
:root {
  --color-primary: #0000FF;
  --radius: 0px;
}
```

분명 디자인 가이드 문서(`reference/01_DESIGN_SYSTEM.md`)를 작성했고, 컴포넌트도 15개 새로 만들었는데 — **정작 `tokens.css` 자체를 업데이트하지 않았다.** 문서만 만들고 실제 파일을 안 건드린 것.

### 해결

```css
/* 업데이트된 tokens.css (130줄) */
:root {
  --color-primary-500: #FF6B2C;  /* warm orange */
  --color-primary: var(--color-primary-500);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius: var(--radius-md);  /* 하위호환 */
  --surface-sidebar: #1E293B;
  --border-default: #E7E5E4;
  /* ... 120줄의 완전한 토큰 */
}
```

**교훈**: 설계 문서 작성과 실제 구현을 분리하면, 문서만 완벽하고 코드는 그대로인 상태가 된다. **감사(audit) 단계**를 반드시 넣을 것.

---

## 2단계: Lookbook 설정 — ViewComponent 4.x API 변경

### 문제: `preview_paths`가 동작 안 함

```ruby
# 이전 API (ViewComponent 3.x)
config.view_component.preview_paths << Rails.root.join("test/components/previews")
config.view_component.default_preview_layout = "component_preview"
```

ViewComponent 4.x에서 API가 바뀌었다:

```ruby
# 현재 API (ViewComponent 4.x)
config.view_component.previews.paths << Rails.root.join("test/components/previews")
config.view_component.previews.default_layout = "component_preview"
```

RuboCop 린터가 자동 수정해줬지만, 수동으로 작업했다면 한참 헤맸을 것.

### 문제: Lookbook 접속 시 다른 앱이 뜸

`localhost:3000/lookbook`에 접속했는데 **완전히 다른 Rails 프로젝트**의 라우팅 에러가 떴다. `lsof -ti:3000`으로 확인하니 이전에 띄워둔 다른 프로젝트의 Puma가 살아있었다.

```bash
# stale PID 처리
kill $(lsof -ti:3000)
rm -f tmp/pids/server.pid
bin/rails server -p 3000
```

**교훈**: 여러 Rails 프로젝트를 오가며 작업할 때, 포트 충돌 확인은 습관화.

---

## 3단계: 6개 기존 컴포넌트 수정 — CSS 변수 fallback 함정

### 문제: `var(--color-primary, #0000FF)` fallback이 런타임에서 사용되지 않음

기존 컴포넌트들이 이런 패턴을 쓰고 있었다:

```ruby
# GnbComponent의 active 스타일
"background: var(--color-primary, #0000FF); color: #fff;"
```

`tokens.css`를 업데이트했으므로 `--color-primary`가 정의되어 있고, fallback `#0000FF`는 사용되지 않는다. **런타임에는 문제없지만 코드에 `#0000FF`가 남아있는 것은 혼란을 줌.**

### 해결 전략

- `var(--color-primary, #0000FF)` → `var(--color-primary-500)` 로 명시적 교체
- `#fff` → `var(--text-inverse)` 토큰 참조
- `#e0e0e0` → `var(--border-default)` 토큰 참조

**전체 47개 컴포넌트**에서 레거시 하드코딩을 제거하려면 `grep`으로 전수조사가 필수:

```bash
grep -r "#0000FF" app/components/     # 5곳
grep -r "#e0e0e0" app/components/     # 13곳
grep -r "radius, 0)" app/components/  # 8곳
```

---

## 4단계: Lookbook 프리뷰 500 에러 — `String#[]` TypeError

### 문제: `no implicit conversion of Symbol into Integer`

344개 Lookbook 프리뷰 URL을 전수 검사했더니 **10개가 500 에러**를 내고 있었다.

```bash
# 전수 검사 스크립트
cat urls.txt | xargs -I{} curl -s -o /dev/null -w "%{http_code} {}\n" \
  "http://localhost:3000/lookbook/inspect/{}" | grep -v "^200 "
```

원인은 CSS 변수 교체 시 발생한 **타입 안전성 문제**:

```erb
<!-- 수정 전: 안전함 (original) -->
<%= category %>

<!-- 수정 후: 위험함 -->
<%= category[:label] || category["label"] || category %>
```

`category`가 `"Design"` 같은 **String**일 때, `"Design"[:label]`은 Ruby에서 `String#[]`을 호출하고, Symbol을 Integer로 변환하려다 `TypeError`가 발생한다.

### 해결

```erb
<%= category.is_a?(Hash) ? (category[:label] || category["label"]) : category %>
```

**영향받은 컴포넌트 3개:**
- `CategoryTabComponent` — categories 배열이 문자열일 때
- `SlidingHighlightMenuComponent` — items 배열이 문자열일 때
- `TableComponent` — columns/rows가 문자열 배열일 때

TableComponent는 추가로 **자동 정규화** 로직을 넣었다:

```ruby
def normalize_columns(columns)
  columns.map.with_index do |col, i|
    col.is_a?(Hash) ? col : { label: col.to_s, key: i }
  end
end
```

**교훈**: 컴포넌트의 props 타입을 확장할 때, **기존 사용처의 데이터 형식**을 반드시 확인. Hash만 기대하는 코드에 String이 오면 깨진다.

---

## 5단계: Lookbook 404 — `@!group` 어노테이션의 URL 매핑

### 문제: 42개 URL이 404인데 페이지는 존재함

```ruby
# Button Preview
# @!group Sizes
def small; end
def medium; end
def large; end
# @!endgroup
```

Lookbook의 `@!group` 어노테이션은 그룹 내 메서드들을 **하나의 URL로 합친다**:
- `/atoms/button/small` → 404
- `/atoms/button/sizes` → 200 (small + medium + large 한 페이지에 표시)

메서드명으로 URL을 구성했던 테스트 스크립트가 잘못된 것이었다.

### 해결

Lookbook의 실제 사이드바 HTML에서 URL을 추출해서 검증:

```bash
curl -sL "http://localhost:3000/lookbook" | \
  grep -o 'href="/lookbook/inspect/[^"]*"' | \
  sort -u > actual_urls.txt
# 310개 실제 URL → 전부 200 OK
```

---

## 최종 결과

| 항목 | Before | After |
|-----|--------|-------|
| tokens.css | 33줄, `#0000FF` | 130줄, warm orange `#FF6B2C` |
| 컴포넌트 | 47개 (레거시 색상) | 62개 (21개 수정/추가, CSS 변수 통일) |
| Lookbook 프리뷰 | 없음 | 310개 URL, 7계층 (atoms→pages→ux_flows) |
| 하드코딩 색상 | `#0000FF` 5곳, `#e0e0e0` 13곳 | 0곳 |
| 500 에러 | 10개 | 0개 |

---

## 핵심 교훈 요약

1. **설계 문서 ≠ 구현** — 문서를 아무리 잘 써도 코드가 안 바뀌면 의미 없다. 감사 단계 필수.
2. **CSS 변수 fallback은 안전망이자 함정** — `var(--token, #legacy)`는 런타임엔 안전하지만, 코드 리뷰 시 혼란을 준다. 토큰 정의 후 fallback 제거할 것.
3. **Ruby의 `String#[]`은 위험** — `obj[:key]`는 Hash에서만 안전. 범용 컴포넌트는 `is_a?(Hash)` 체크 필수.
4. **Lookbook `@!group`은 URL을 합침** — 개별 메서드 URL이 아니라 그룹 URL로 접근해야 한다.
5. **포트 충돌은 흔한 삽질** — 여러 Rails 앱 작업 시 `lsof -ti:PORT`로 확인 습관화.
6. **전수 검사는 curl로** — 수백 개 프리뷰를 눈으로 확인하지 말고, HTTP 상태 코드로 자동 검증.
