---
title: "AI로 디자인 시스템 마이그레이션했는데 사실 CSS 리스킨이었다 — Token/Component/Template/Page 4-layer 재설계 회고"
date: 2026-04-08T09:00:00+09:00
draft: false
tags: ["design-system", "atomic-design", "rails", "css", "ai-coding"]
categories: ["AI Engineering", "Rails"]
description: "Rails 8 + Hotwire 프로젝트에 iOS 26 디자인 시스템을 7주에 걸쳐 마이그레이션했다. 위반 417건이 0건이 됐다. 그런데 클라이언트 한 마디에 전부 가짜였다는 걸 깨달았다. Atomic Design 4-layer로 재설계한 회고."
---

Rails 8 + Hotwire 프로젝트에 iOS 26 Liquid Glass 디자인 시스템을 전면 도입했다. 7주간 39개 페이지를 마이그레이션했고, 디자인 가이드 위반 417건이 0건이 됐다. 18개 파일로 구성된 마이그레이션 설계서도 있었고, 단계별(Phase 1-7) 체크리스트도 있었다. 스스로 만족했다.

그 다음에 사용자가 한마디 했다.

> "토큰/컴포넌트/템플릿/페이지 형태로 반영이되어야하는데 디자인시스템부터 점검해"

그 문장 하나로 전부 무너졌다. 점검해보니 내가 한 건 디자인 시스템이 아니라 CSS 리스킨이었다. 이 글은 그 깨달음과 재설계 과정의 기록이다.

---

## AI 코딩의 함정 — 페이지마다 "시스템처럼" 보이게 만들기

처음에는 단계별로 잘 진행했다고 생각했다. 토큰 파일을 만들었고(iOS 26 79개 컬러 × 4모드), 6개 공통 ERB 파셜을 만들었고(toolbar, list_row, button 등), 각 페이지마다 전용 CSS 파일을 분리했다. 39개 페이지가 모두 새 디자인으로 바뀌었고, grep으로 위반을 측정했더니 0건이었다.

측정 지표상으로는 완벽했다. 문제는 측정 지표가 잘못됐다는 것.

사용자 피드백 후 점검 명령어 몇 개 돌려봤다.

```bash
# 각 페이지 전용 CSS 파일의 클래스 수
for f in app/assets/stylesheets/zz_ios26/0[5-9]*.css app/assets/stylesheets/zz_ios26/1*.css; do
  count=$(grep -cE '^\.[a-z][a-z0-9_-]*' "$f")
  echo "  $(basename $f): ${count}개 클래스"
done
```

결과:

```
05_dashboard.css: 36개 클래스
07_chat.css: 46개 클래스
09_service_requests.css: 95개 클래스
13_admin_departments.css: 53개 클래스
14_admin_notices.css: 62개 클래스
15_admin_users.css: 60개 클래스
17_auth.css: 111개 클래스
...
총합: 610개 페이지 전용 클래스, 3,954줄
```

페이지마다 자체 클래스를 600개 넘게 정의하고 있었다. 한 파일에 95개, 다른 파일에 111개. 이름은 모두 달랐지만 실제로는 같은 걸 반복하고 있었다.

더 결정적인 증거:

```bash
for pattern in "form-card" "form-input" "form-textarea" "form-select" "form-actions" "form-error"; do
  files=$(grep -lE "\.[a-z][a-z0-9_-]*${pattern}" app/assets/stylesheets/zz_ios26/0[5-9]*.css app/assets/stylesheets/zz_ios26/1*.css)
  count=$(echo "$files" | grep -c .)
  echo "  '$pattern': ${count}개 페이지"
done
```

```
'form-card': 4개 페이지
'form-input': 5개 페이지
'form-textarea': 3개 페이지
'form-select': 4개 페이지
'form-actions': 3개 페이지
'form-error': 4개 페이지
```

같은 `form-card` 개념이 4개의 다른 페이지에서 각자의 CSS로 정의되고 있었다. `.sr-form-card`, `.admin-dept-form-card`, `.admin-notices-form-card`, `.admin-users-form-card`. 이름은 페이지별로 다르지만 결국 같은 것이었다.

즉, **내가 만든 건 일관성이 아니라 "일관성 있어 보이는 복제"**였다.

---

## Atomic Design과 실전 4-layer

디자인 시스템을 제대로 이해하려면 [Atomic Design](https://atomicdesign.bradfrost.com/chapter-2/)을 알아야 한다. Brad Frost가 2013년에 제안한 모델이고, 여전히 가장 널리 쓰이는 멘탈 모델이다.

5단계로 구성된다:

| 레벨 | 이름 | 역할 | 예시 |
|------|------|------|------|
| 1 | Atoms (원자) | 더 이상 쪼갤 수 없는 UI 요소 | Button, Input, Label, Icon |
| 2 | Molecules (분자) | 원자 2-5개 조합, 단일 기능 | SearchField, FormField, Pagination |
| 3 | Organisms (유기체) | 분자와 원자의 복합체, 독립된 섹션 | Header, ProductCard, RegistrationForm |
| 4 | Templates (템플릿) | 유기체를 배치한 페이지 레이아웃 스켈레톤 | HomepageTemplate, DetailTemplate |
| 5 | Pages (페이지) | 실제 콘텐츠가 들어간 템플릿 인스턴스 | UserProfilePage, LandingPage |

Brad Frost가 강조하는 건 **이게 선형 프로세스가 아니라는 점**이다. "Step 1: atoms, Step 2: molecules"가 아니라 동시에 만들고 서로 영향을 주는 멘탈 모델이다.

실전에서는 대부분의 팀이 5단계를 엄격히 지키지 않는다. Midrocket 가이드에 따르면, 실전에서는 3-4단계로 적응하는 경우가 많다:

- 3단계: primitives / composites / sections
- 4단계: base / components / patterns / layouts

핵심은 **정확한 분류가 아니라 계층적 구성(hierarchical composition)이라는 원칙**이다. Atoms를 Tokens로, Molecules/Organisms를 Components로 묶고, Templates + Pages를 그대로 가져가면 4-layer가 된다.

### Token → Component → Template → Page

```
┌─────────────────────────────┐
│  PAGE — 실제 콘텐츠를 가진   │
│  템플릿의 인스턴스            │
├─────────────────────────────┤
│  TEMPLATE — 페이지 레이아웃  │
│  스켈레톤 (콘텐츠 없음)      │
├─────────────────────────────┤
│  COMPONENT — 재사용 가능한   │
│  UI 블록 (atoms + molecules) │
├─────────────────────────────┤
│  TOKEN — 색상/타이포/간격    │
│  원자적 변수                 │
└─────────────────────────────┘
```

이 피라미드에서 위 레이어는 아래 레이어만 참조해야 한다. 페이지는 템플릿을 사용하고, 템플릿은 컴포넌트를 조합하고, 컴포넌트는 토큰을 참조한다. 페이지가 토큰을 직접 참조하거나 (컴포넌트가 없어서) 자체 클래스를 만들기 시작하면, 그건 시스템이 아니다.

---

## 점검 결과 — 4-layer 중 2-layer만 있었다

내가 만든 걸 이 피라미드에 대입해봤다.

```
┌─────────────────────────────┐
│  PAGE (39)                  │  ← 페이지 ERB + 3,954줄 CSS
├─────────────────────────────┤
│  TEMPLATE (0) ❌            │  ← 없음
├─────────────────────────────┤
│  COMPONENT (6) ⚠️           │  ← 너무 적음
├─────────────────────────────┤
│  TOKEN (3) ✅               │  ← 정상
└─────────────────────────────┘
```

**Template layer는 완전히 비어 있었다.** 페이지마다 직접 컨테이너, 헤더, 폼 레이아웃을 다시 작성하고 있었다. "목록 페이지", "상세 페이지", "폼 페이지", "2-column 페이지"라는 반복 패턴이 명백한데, 그걸 추상화한 게 없었다.

**Component layer도 겨우 6개였다.** 39개 페이지를 조합하기엔 터무니없이 부족한 수. 그래서 페이지마다 form-card, form-input, profile-card, empty-state 같은 걸 개별로 정의했던 것이다.

더 심각한 건 기존에 있던 ViewComponent 47개를 방치한 것. `app/components/` 디렉토리에 그대로 있었는데, 한 번도 "실제로 쓰는지" 확인 안 했다.

```bash
for f in $(find app/components -name "*_component.rb"); do
  cls=$(grep -oE "class\s+\w+Component" "$f" | awk '{print $2}' | head -1)
  used=$(grep -rE "${cls}\.new|render.*${cls}" app/views/ app/controllers/ 2>/dev/null | grep -v "components/" | wc -l)
  [ "$used" -eq 0 ] && echo "$f"
done | wc -l
```

```
47 / 47
```

**47개 ViewComponent가 모두 사용 0건이었다.** 마이그레이션 내내 "사용 빈도 미확인이라 나중에 처리"로 미뤄뒀던 그 디렉토리. 사실 전부 dead code였다. 진작에 `grep` 한 번만 돌렸으면 삭제할 수 있었다.

### CSS Stats 함정 — 생각과 코드의 차이

[CSS-Tricks의 Robin Rendle의 CSS 감사 글](https://css-tricks.com/a-quick-css-audit-and-general-notes-about-design-systems/)에 정확히 같은 상황이 나온다. 팀이 68개의 unique color를 정의했는데, 실제 프로덕션 CSS를 돌려보니 101개의 unique color가 나타났다. 배경색은 115개.

"내가 이해하는 디자인 시스템과 실제 코드가 다르다"는 문제.

Rendle은 이렇게 쓴다:

> If my understanding of the design system is different from how the CSS works, then there's enormous potential for engineers and designers to pick up on the wrong patterns and for confusion to disseminate across our organization.

정확히 내가 하고 있던 일이었다. 설계서에는 "Token → Component → Page"라고 썼지만, 실제 코드는 "Token → 페이지 전용 CSS 610개"였다. 설계와 구현의 drift.

---

## 재설계 — Phase 8

문제가 명확해지니 해법도 명확해졌다. Component layer를 확장하고, Template layer를 새로 만들고, 페이지 전용 CSS는 슬림화하고, dead code는 삭제한다.

### 1단계: Dead ViewComponent 삭제

가장 먼저 한 건 삭제. 사용 0건 확인했으니 고민할 것도 없었다.

```bash
rm -rf app/components/ test/components/previews/
bin/rails runner 'puts "OK: app boots"'
```

158개 파일이 사라졌고 앱은 정상 부팅됐다.

### 2단계: Component layer 확장 (6 → 14)

반복 패턴을 기반으로 8개 새 파셜을 만들었다:

```
app/views/shared/ios26/
├── _page_shell.html.erb     # 배경 + max-width + safe-area
├── _page_header.html.erb    # large title + back + trailing
├── _empty_state.html.erb    # 아이콘 + title + action
├── _form_card.html.erb      # errors + fields wrapper
├── _form_field.html.erb     # label + input/textarea/select
├── _status_badge.html.erb   # 7 variants × 2 sizes
├── _profile_card.html.erb   # 큰 아바타 + 이름 + 메타
└── _detail_list.html.erb    # key/value 정의 리스트
```

각 파셜은 여러 페이지에 쓰이는 걸 전제로 설계했다. 예를 들어 `_form_field`는 `type: :text|:email|:textarea|:select`를 받아서 분기한다.

```erb
<%= render "shared/ios26/form_field",
      form: f,
      name: :email,
      label: "이메일",
      type: :email,
      required: true %>
```

이제 `admin-users-form-input`, `admin-notices-form-input`, `sr-form-input` 같은 이름들이 전부 `.ios-form-input` 하나로 통합된다.

### 3단계: Template layer 신규 (0 → 4)

4가지 페이지 셸을 만들었다:

```
app/views/shared/ios26/templates/
├── _list.html.erb      # 목록 페이지 (header + content + pagination)
├── _detail.html.erb    # 상세 페이지 (header + content + actions)
├── _form.html.erb      # 폼 페이지 (header + form_with + form_card + actions)
└── _split.html.erb     # 2-column (sidebar + main)
```

Template 파셜은 `page_shell` + `page_header`를 포함하고 안에 컨텐츠를 yield한다:

```erb
<%= render "shared/ios26/templates/form",
      title: "사용자 수정",
      back_url: admin_user_path(@user),
      model: [:admin, @user],
      submit_label: "저장",
      errors: @user.errors.full_messages do |f| %>
  <%= render "shared/ios26/form_field", form: f, name: :name, label: "이름" %>
  <%= render "shared/ios26/form_field", form: f, name: :email, label: "이메일", type: :email %>
<% end %>
```

이게 전부다. `admin/users/edit.html.erb`가 이 한 덩어리로 줄어든다.

### 4단계: 페이지 ERB 슬림화

admin 14개 파일을 재작성해봤다.

| 파일 | Before | After | 감소 |
|------|-------:|------:|-----:|
| departments/_form | 40줄 | 9줄 | **-78%** |
| notices/_form | 67줄 | 32줄 | **-52%** |
| users/edit | 65줄 | 36줄 | **-45%** |
| notices/show | 79줄 | 53줄 | -33% |
| departments/new | 18줄 | 12줄 | -33% |
| **합계** | 623줄 | 455줄 | **-27%** |

CSS 슬림화는 더 극적이었다. 04b_patterns.css에 이미 있는 패턴을 각 페이지 CSS에서 제거했다:

| 파일 | Before | After | 감소 |
|------|-------:|------:|-----:|
| 15_admin_users.css | 286줄 | **38줄** | **-87%** |
| 14_admin_notices.css | 343줄 | 112줄 | -67% |
| 13_admin_departments.css | 361줄 | 124줄 | -66% |
| 16_admin_settings.css | 139줄 | 92줄 | -34% |
| **합계** | 1,129줄 | **366줄** | **-68%** |

`15_admin_users.css`가 286줄에서 38줄이 된 건 상징적이다. 필터 바와 아바타 row 정도만 페이지 고유로 남고, 나머지는 전부 컴포넌트 파셜로 이동했다.

### 5단계: 결과

전체 시스템 구조가 이렇게 바뀌었다:

```
Phase 7 (재설계 전):                 Phase 8 (재설계 후):
┌─────────────────────────┐         ┌─────────────────────────┐
│  PAGE (39)              │         │  PAGE (54) ✅           │  마이그레이션 영역 확장
│  + 3,954줄 페이지 CSS   │         │  + 2,690줄 페이지 CSS   │  -32%
├─────────────────────────┤         ├─────────────────────────┤
│  TEMPLATE (0) ❌        │    →    │  TEMPLATE (4) ✅        │  신규
├─────────────────────────┤         ├─────────────────────────┤
│  COMPONENT (6) ⚠️       │         │  COMPONENT (14) ✅      │  +83%
├─────────────────────────┤         ├─────────────────────────┤
│  TOKEN (3) ✅           │         │  TOKEN (3) ✅           │  동일
└─────────────────────────┘         └─────────────────────────┘

ViewComponent 47 (dead)   →   0 (삭제)
```

---

## Drift가 생기는 이유 — 5가지 패턴

[Design System Ops](https://designsystemops.com)의 `drift-detection` 스킬 설명에서 흥미로운 분류를 발견했다. 시스템과 구현이 어긋나는(drift) 이유는 5가지가 있다:

1. **Intentional divergence** — 팀이 의도적으로 분기. 정당한 예외.
2. **Version lag** — 최신 버전을 못 따라감. 업데이트 필요.
3. **Accidental drift** — 실수로 어긋남. 수정해야 함.
4. **Misunderstanding** — 시스템을 잘못 이해. 문서화 필요.
5. **System gap** — 시스템에 없는 기능이라 페이지가 자체 구현. **시스템을 확장해야 함**.

내 경우는 전부 **#5 System gap**이었다. form 패턴, empty state, profile card 같은 게 시스템에 없으니까 페이지가 자체 구현했다. 결과적으로 일관성 있어 보였지만, 실제로는 페이지 수만큼 복제가 생겼다.

이게 왜 문제냐면, 나중에 design token이 바뀌었을 때를 생각해보면 된다. `--ios-color-cyan`을 `#00B4D6`에서 `#0091C7`로 바꿨다고 치자. 컴포넌트 하나만 바꾸면 끝나야 하는데, 페이지 47군데 form-card를 각자 수정해야 한다. 그 중 한두 개는 놓쳐서 색깔이 어긋나고, 그게 새로운 drift가 된다.

---

## Replay의 통계 — legacy rewrite 70% 실패

[Replay.build](https://www.replay.build/blog/how-to-build-a-consistent-design-system-from-production-ui)의 분석이 인상적이었다:

- **Legacy rewrite의 70%가 실패하거나 일정 초과** — CSS Spaghetti의 복잡도 과소평가 때문.
- **평균 기업 앱에 같은 "Primary Button"이 15가지 변형** — 팀이 빠르게 움직이면서 문서 관리 실패, CSS override 누적.
- **Manual audit은 화면당 40시간** — 숨은 의존성 때문에 자주 실패.
- **Legacy CSS의 40%가 dead code** — 삭제된 기능의 스타일이 그대로 남음.

내 프로젝트는 엄청 큰 기업 앱은 아니었지만, 원칙은 동일했다. `app/components/` 47개 dead ViewComponent가 "그대로 두면 언젠가 쓰겠지"라는 이유로 7주간 방치됐다. 페이지 CSS의 form-card 중복도 "페이지마다 컨텍스트가 다르니까"라는 핑계로 정당화했다.

둘 다 착각이었다.

---

## AI 코딩에서 배운 것들

AI로 대규모 마이그레이션을 해보면서 느낀 점:

### 1. Grep 통계는 시스템을 증명하지 못한다

"위반 417건 → 0건"은 멋진 숫자지만, 시스템의 건강도를 증명하지 않는다. 0건이어도 내부에서는 같은 패턴이 반복되고 있을 수 있다. 진짜 지표는:

- 페이지가 템플릿을 얼마나 재사용하는가
- 컴포넌트가 몇 페이지에서 쓰이는가
- 페이지 전용 CSS의 총 줄 수가 감소하고 있는가
- Dead code를 주기적으로 삭제하고 있는가

### 2. AI는 "반복해서 만드는" 걸 잘한다

에이전트를 병렬로 돌리면 4시간 걸릴 작업을 10분에 끝낸다. 근데 이게 오히려 함정이다. **반복해서 만드는 게 쉬워지면, 추상화할 필요를 못 느낀다.**

사람이 수동으로 8개 페이지의 form을 작성한다면, 3개쯤 쓰다가 "아 공통 컴포넌트 만들자"고 판단한다. AI는 8개를 다 만들 수 있으니 그냥 만든다. 결과적으로 중복이 쌓이는 걸 알아차리지 못한다.

### 3. 디자인 시스템은 측정 가능해야 한다

재설계 이후부터는 단순한 측정 지표를 매 Phase 끝에 확인한다:

```bash
# 컴포넌트 재사용 빈도
grep -rn "render \"shared/ios26/" app/views/ | awk -F'"' '{print $2}' | sort | uniq -c | sort -rn

# 페이지 전용 CSS 대비 시스템 CSS 비율
sys=$(wc -l app/assets/stylesheets/zz_ios26/0[1-4]*.css | tail -1 | awk '{print $1}')
pages=$(wc -l app/assets/stylesheets/zz_ios26/0[5-9]*.css app/assets/stylesheets/zz_ios26/1*.css | tail -1 | awk '{print $1}')
echo "system: $sys, pages: $pages, ratio: $(echo "scale=2; $pages/$sys" | bc)"

# Dead component 검사
for cls in $(grep -oE 'class \w+Component' app/components/**/*.rb | awk '{print $2}'); do
  used=$(grep -rE "${cls}" app/views/ app/controllers/ | grep -v components/ | wc -l)
  [ "$used" -eq 0 ] && echo "DEAD: $cls"
done
```

숫자를 매 phase마다 기록하고 추세를 본다. 페이지 CSS가 증가하고 있다면 컴포넌트 추출이 부족한 것. 비율이 1:1을 넘어가면 시스템보다 페이지 고유 스타일이 더 많다는 뜻.

### 4. "선택적으로 제외"는 위험 신호다

"market 페이지는 제거 예정이라 제외", "ViewComponent는 사용 빈도 미확인이라 보류", "pages/는 마케팅이라 제외". 이런 제외가 쌓이면 결국 시스템이 아니다. 일관성이 깨진 부분이 시스템 내부에 살아있기 때문이다.

제거 예정이면 **지금 제거**하거나, **지금 마이그레이션 대상에 포함**해야 한다. "나중에"는 거짓말이다.

---

## 시스템의 건강을 유지하는 습관

재설계 이후 반복하는 루틴:

**매 기능 추가 시:**
1. 페이지 전용 CSS를 새로 쓸 생각이면 잠깐 멈춘다
2. 기존 컴포넌트로 해결 가능한지 확인
3. 안 되면 컴포넌트를 확장할지, 아니면 **정말로** 페이지 고유 스타일인지 판단
4. 2-3개 페이지에서 반복되는 패턴이면 컴포넌트로 승격

**매 주:**
1. Dead component grep
2. 페이지 전용 CSS 라인 수 추세 확인
3. 컴포넌트 재사용 빈도 확인

**매 분기:**
1. 전체 CSS stats 돌려보기 (unique color, font, spacing)
2. 설계 문서와 실제 코드 drift 확인

Atomic Design 원칙은 명확하다. 아래 레이어는 위 레이어에 의존하지 않고, 위 레이어는 아래 레이어만 참조한다. 이 원칙이 깨지면 시스템이 아니라 그냥 CSS 파일의 모음이다.

---

## 결론

7주간 AI로 디자인 시스템을 마이그레이션했고, 위반 0건을 달성했다. 그런데 사용자 한 마디에 전부 CSS 리스킨이었다는 걸 깨달았다. Template layer가 없었고, Component layer가 터무니없이 부족했고, dead ViewComponent 47개가 방치돼 있었다.

재설계하는 데 하루 걸렸다. 그 하루에 ViewComponent 47개 삭제, 파셜 8개 추가, 템플릿 4개 신규 작성, admin 페이지 CSS 68% 감소를 끝냈다. 한 달 동안 못 본 문제가 하루만에 해결됐다.

교훈은 간단하다: **디자인 시스템은 위반 수가 아니라 Token/Component/Template/Page 4-layer의 건강도로 측정한다.** AI가 코드를 잘 쓰는 시대일수록 더 중요하다. AI는 반복해서 만드는 걸 쉽게 하니까, 추상화의 필요성을 사람이 명시적으로 검증해야 한다.

마이그레이션이 끝났다고 생각할 때 한 번 더 grep 돌려보자:

```bash
# 페이지마다 자기 CSS 클래스를 몇 개 정의하고 있는가
for f in app/assets/stylesheets/**/page-*.css; do
  echo "$(basename $f): $(grep -cE '^\.[a-z]' $f)"
done
```

숫자가 커지고 있으면 재설계 타이밍이다.
