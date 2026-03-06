---
title: "Rails + Stimulus 컨트롤러 11개 구현기: 스크롤·캐러셀·텍스트 애니메이션"
date: 2025-11-18
draft: false
tags: ["Rails", "Stimulus", "ViewComponent", "Lookbook", "JavaScript", "애니메이션"]
description: "스텁(빈 껍데기) 상태의 Stimulus 컨트롤러 11개를 실제 동작하도록 구현하면서 겪은 삽질과 해결 과정. Lookbook 프리뷰에서 Stimulus가 작동하지 않는 버그 포함."
cover:
  image: "/images/og/rails-stimulus-controllers-lookbook-debug.png"
  alt: "Rails Stimulus Controllers Lookbook Debug"
  hidden: true
---

Rails + ViewComponent + Lookbook 조합으로 컴포넌트 라이브러리를 만들 때, Stimulus 컨트롤러가 전부 스텁(빈 껍데기) 상태로 남아있는 상황을 맞닥뜨렸다. 13개 컨트롤러 중 3개만 동작하고 나머지 10개는 `connect() {}` 한 줄짜리였다. 이걸 전부 구현하면서 겪은 삽질을 정리한다.

---

## 구현 대상

총 11개 컨트롤러를 4단계로 나눠서 구현했다.

| Wave | 컨트롤러 | 핵심 기술 |
|------|---------|---------|
| 1 | TagInput, FileDropzone, CategoryTab | DOM 조작, 드래그 이벤트 |
| 2 | ScrollReveal, ScrollScale, VideoScrubbing, HorizontalScroll | RAF 쓰로틀, IntersectionObserver, ResizeObserver |
| 3 | ScrambleText, RandomReveal | RAF 애니메이션 루프, Fisher-Yates 셔플 |
| 4 | ImageCarousel, CarouselContainer | 드래그/터치, translateX 트랜지션 |

---

## 삽질 1: Lookbook 프리뷰에서 Stimulus가 아예 안 됨

가장 크게 막혔던 부분이다. 컨트롤러를 다 구현하고 Lookbook을 열었는데 아무 동작도 하지 않는다. 크롬 DevTools를 열어보니 `data-controller` 속성은 붙어있는데 Stimulus가 연결이 안 된 상태였다.

### 원인

Lookbook은 프리뷰를 `<iframe>`으로 렌더링한다. 이 iframe의 레이아웃 파일이 따로 있는데:

```erb
<%# app/views/layouts/previews/preview.html.erb %>
<head>
  <%= stylesheet_link_tag "application" %>
  <%# javascript_importmap_tags 가 없었음! %>
</head>
```

`stylesheet_link_tag`만 있고 `javascript_importmap_tags`가 없었다. CSS는 불러오는데 JS는 로드 자체가 안 된 것.

### 수정

```erb
<head>
  <%= stylesheet_link_tag "application" %>
  <%= javascript_importmap_tags %>
</head>
```

한 줄 추가로 해결됐다. Rails 8 Importmap 환경에서 Lookbook을 쓴다면 반드시 확인해야 할 부분이다. 프리뷰 레이아웃 파일이 2곳에 있었는데 둘 다 수정해야 했다:

- `app/views/layouts/previews/preview.html.erb`
- `app/views/previews/preview.html.erb`

---

## Wave 1: DOM 조작 컨트롤러

### TagInput

Enter나 콤마로 태그를 추가하고, × 버튼으로 삭제, Backspace로 마지막 태그를 지우는 컨트롤러.

```javascript
// app/javascript/controllers/tag_input_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["input", "container"]

  connect() {
    this.tags = []
  }

  addTag(event) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault()
      const value = this.inputTarget.value.trim().replace(/,$/, "")
      if (value && !this.tags.includes(value)) {
        this.tags.push(value)
        this._renderTag(value)
        this.inputTarget.value = ""
      }
    }
  }

  removeOnBackspace(event) {
    if (event.key === "Backspace" && this.inputTarget.value === "") {
      this._removeLastTag()
    }
  }

  removeTag(event) {
    const chip = event.currentTarget.closest("[data-tag]")
    const value = chip?.dataset.tag
    if (value) {
      this.tags = this.tags.filter(t => t !== value)
      chip.remove()
    }
  }

  _renderTag(value) {
    const chip = document.createElement("span")
    chip.dataset.tag = value
    chip.className = "tag-chip"
    chip.innerHTML = `${this._escapeHtml(value)} <button data-action="click->tag-input#removeTag">×</button>`
    this.containerTarget.insertBefore(chip, this.inputTarget)
  }

  _removeLastTag() {
    const last = this.containerTarget.querySelector("[data-tag]:last-of-type")
    if (last) {
      this.tags = this.tags.filter(t => t !== last.dataset.tag)
      last.remove()
    }
  }

  _escapeHtml(text) {
    return text.replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]))
  }
}
```

ERB에서의 연결 패턴:

```erb
<div data-controller="tag-input" class="tag-input-wrapper">
  <div data-tag-input-target="container">
    <input
      data-tag-input-target="input"
      data-action="keydown->tag-input#addTag keydown->tag-input#removeOnBackspace"
    />
  </div>
</div>
```

### CategoryTab — underline indicator 애니메이션

기존 구현은 배경색만 바꾸는 방식이었다. 하단 인디케이터가 슬라이딩하는 방식으로 교체했다.

핵심은 선택된 탭의 `offsetLeft`와 `offsetWidth`를 읽어서 인디케이터 `<span>`에 적용하는 것이다:

```javascript
_moveIndicator(index) {
  const tab = this.element.querySelectorAll("[role='tab']")[index]
  if (!tab || !this.hasIndicatorTarget) return
  this.indicatorTarget.style.width = `${tab.offsetWidth}px`
  this.indicatorTarget.style.left = `${tab.offsetLeft}px`
}
```

인디케이터에 `transition: width 0.3s ease, left 0.3s ease`를 주면 탭 이동 시 자연스럽게 슬라이딩된다.

---

## Wave 2: 스크롤 기반 컨트롤러

스크롤 이벤트는 무조건 RAF(requestAnimationFrame) 쓰로틀을 걸어야 한다. 매 스크롤 이벤트마다 DOM을 건드리면 렉이 생긴다.

```javascript
connect() {
  this._ticking = false
  this._onScroll = () => {
    if (!this._ticking) {
      requestAnimationFrame(() => {
        this._update()
        this._ticking = false
      })
      this._ticking = true
    }
  }
  window.addEventListener("scroll", this._onScroll, { passive: true })
}

disconnect() {
  window.removeEventListener("scroll", this._onScroll)
}
```

### ScrollReveal — 글자별 순차 등장

텍스트를 한 글자씩 `<span>`으로 쪼개고, 스크롤 진행도에 따라 `settledCount`개만큼 색상을 바꾼다.

```javascript
connect() {
  const text = this.element.textContent.trim()
  this.chars = text.split("")
  this.element.innerHTML = this.chars
    .map(c => c === " "
      ? " "
      : `<span style="color:${this.inactiveColorValue}">${c}</span>`)
    .join("")
  this.spans = this.element.querySelectorAll("span")
  // ... scroll listener
}

_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = (window.innerHeight * 0.8 - rect.top) / rect.height
  const count = Math.floor(this.spans.length * Math.min(Math.max(progress, 0), 1))
  this.spans.forEach((s, i) => {
    s.style.color = i < count ? this.activeColorValue : this.inactiveColorValue
  })
}
```

### VideoScrubbing

스크롤 위치를 `video.currentTime`에 매핑한다. IntersectionObserver로 화면에 들어왔을 때만 스크롤 리스너를 붙여서 성능을 아낀다.

```javascript
_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = Math.min(Math.max(
    -rect.top / (rect.height - window.innerHeight), 0), 1)
  if (this.hasVideoTarget && this.videoTarget.duration) {
    this.videoTarget.currentTime = this.videoTarget.duration * progress
  }
}
```

비디오는 `muted playsinline preload="auto"` 속성이 필수다. `preload="auto"` 없으면 `duration`이 NaN이라 아무것도 안 된다.

### HorizontalScroll — 수직 스크롤 → 수평 이동

sticky container 안에서 수직 스크롤을 수평 translateX로 변환한다. 컨테이너 높이를 `100vh + scrollDistance`로 설정해서 스크롤 여유 공간을 확보하는 게 핵심이다.

```javascript
_setup() {
  const trackWidth = this.trackTarget.scrollWidth
  const scrollDistance = trackWidth - window.innerWidth
  this.element.style.height = `${window.innerHeight + scrollDistance}px`
  this._scrollDistance = scrollDistance
}

_update() {
  const rect = this.element.getBoundingClientRect()
  const progress = Math.min(Math.max(-rect.top / this._scrollDistance, 0), 1)
  this.trackTarget.style.transform = `translateX(-${progress * this._scrollDistance}px)`
}
```

---

## Wave 3: 텍스트 애니메이션

### ScrambleText

텍스트가 랜덤 문자로 뒤섞인 후 좌→우 순서로 정착되는 효과. RAF 루프로 구현한다.

```javascript
_animate(timestamp) {
  if (!this._startTime) this._startTime = timestamp
  const elapsed = timestamp - this._startTime
  const progress = Math.min(elapsed / this.durationValue, 1)
  const settledCount = Math.floor(this._text.length * progress)

  const result = this._text.split("").map((char, i) => {
    if (i < settledCount) return char
    if (char === " ") return " "
    return this.charsetValue[Math.floor(Math.random() * this.charsetValue.length)]
  }).join("")

  this.element.textContent = result

  if (progress < 1) {
    this._rafId = requestAnimationFrame(this._animate.bind(this))
  }
}
```

IntersectionObserver로 화면에 들어올 때 애니메이션을 트리거한다. `threshold: 0.3`으로 설정하면 30% 보일 때 시작된다.

### RandomReveal

Fisher-Yates 셔플로 글자 등장 순서를 랜덤하게 만들고, `delay + index * stagger` ms 간격으로 staggered setTimeout을 건다.

```javascript
connect() {
  const text = this.element.textContent.trim()
  const chars = text.split("")

  // 글자별 span 생성, 초기엔 blur + opacity 0
  this.element.innerHTML = chars.map((c, i) =>
    `<span data-index="${i}" style="opacity:0;filter:blur(8px);transition:opacity 0.4s,filter 0.4s">${c}</span>`
  ).join("")

  // Fisher-Yates 셔플
  const indices = chars.map((_, i) => i)
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]]
  }

  // 랜덤 순서로 순차 등장
  const spans = this.element.querySelectorAll("span")
  indices.forEach((charIndex, order) => {
    setTimeout(() => {
      spans[charIndex].style.opacity = "1"
      spans[charIndex].style.filter = "blur(0)"
    }, this.delayValue + order * this.staggerValue)
  })
}
```

---

## Wave 4: 캐러셀

### ImageCarousel — 드래그/터치/키보드/버튼

캐러셀에서 가장 신경 써야 할 건 드래그 판정 임계값이다. 50px 미만으로 드래그하면 클릭으로 처리하고, 50px 이상이면 슬라이드를 넘긴다.

```javascript
onDragStart(event) {
  this._dragStartX = event.clientX ?? event.touches?.[0].clientX
  this._isDragging = true
}

onDragEnd(event) {
  if (!this._isDragging) return
  const endX = event.clientX ?? event.changedTouches?.[0].clientX
  const diff = this._dragStartX - endX

  if (Math.abs(diff) > 50) {
    diff > 0 ? this.next() : this.prev()
  }
  this._isDragging = false
}
```

오토플레이는 `setInterval`로 구현하되, 사용자가 수동으로 조작하면 인터벌을 초기화해야 자연스럽다:

```javascript
_resetAutoPlay() {
  if (this._autoPlayTimer) clearInterval(this._autoPlayTimer)
  if (this.autoPlayValue) {
    this._autoPlayTimer = setInterval(() => this.next(), this.autoPlayIntervalValue)
  }
}
```

### CarouselContainer — 반응형 visible count

ResizeObserver로 컨테이너 너비가 바뀔 때마다 아이템 너비를 재계산한다.

```javascript
_updateLayout() {
  const items = this.itemTargets
  if (!items.length) return
  const containerWidth = this.element.offsetWidth
  const gap = 16
  const itemWidth = (containerWidth - gap * (this.visibleValue - 1)) / this.visibleValue
  items.forEach(item => {
    item.style.minWidth = `${itemWidth}px`
    item.style.maxWidth = `${itemWidth}px`
  })
  this._itemWidth = itemWidth + gap
  this._goTo(this._currentIndex)
}
```

---

## 검증: Playwright로 iframe 내부 확인

Lookbook 프리뷰가 iframe이라 일반적인 Playwright locator로는 접근이 안 된다. `frameLocator`를 써야 한다.

```javascript
// iframe 내부 접근
const iframe = page.frameLocator('iframe[title="viewport"]')

// Stimulus 연결 확인 + 값 읽기
const result = await iframe.locator('body').evaluate((el) => {
  const ctrl = el.querySelector('[data-controller="category-tab"]')
  return {
    connected: !!ctrl,
    indicatorLeft: ctrl?.querySelector('[data-category-tab-target="indicator"]')?.style.left
  }
})
```

각 컨트롤러별 검증 포인트:

- **CategoryTab**: 탭 클릭 후 indicator의 `left` 값 변경 여부
- **TagInput**: Enter 입력 후 `data-tag` 속성 chip 생성 여부
- **ScrambleText**: 애니메이션 완료 후 원본 텍스트와 일치 여부
- **ImageCarousel**: next 클릭 후 track의 `translateX` 값 변경 여부
- **CarouselContainer**: next 클릭 후 `translate3d` 값 변경 여부

---

## 정리

Rails + Lookbook 환경에서 Stimulus를 쓸 때 놓치기 쉬운 포인트:

1. **프리뷰 레이아웃에 `javascript_importmap_tags` 추가** — 이게 없으면 Stimulus 자체가 로드 안 됨
2. **스크롤 이벤트는 RAF 쓰로틀** — `passive: true`도 함께 설정
3. **disconnect()에서 리스너 정리** — 메모리 누수 방지
4. **video scrubbing은 `preload="auto"`** — 없으면 `duration`이 NaN
5. **Lookbook iframe 내부는 `frameLocator`** — 일반 locator로 접근 불가
