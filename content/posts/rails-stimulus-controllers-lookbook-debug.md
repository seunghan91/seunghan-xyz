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
categories: ["Rails", "Hotwire"]
---

Rails + ViewComponent + Lookbook 조합으로 컴포넌트 라이브러리를 만들 때, Stimulus 컨트롤러가 전부 스텁(빈 껍데기) 상태로 남아있는 상황을 맞닥뜨렸다. 13개 컨트롤러 중 3개만 동작하고 나머지 10개는 `connect() {}` 한 줄짜리였다. 이걸 전부 구현하면서 겪은 삽질을 정리한다.

이 글은 단순히 코드를 붙여넣는 게 아니라, 각 컨트롤러를 구현하면서 **왜 그런 방식을 선택했는지**, **어떤 문제가 발생했는지**, 그리고 **어떻게 해결했는지**에 초점을 맞춘다.

---

## 구현 대상

총 11개 컨트롤러를 4단계로 나눠서 구현했다. 복잡도와 의존성을 기준으로 순서를 정했다. DOM 직접 조작 → 스크롤 연동 → RAF 애니메이션 → 인터랙티브 캐러셀 순서로 진행하면 각 단계에서 배운 패턴이 다음 단계에 자연스럽게 이어진다.

| Wave | 컨트롤러 | 핵심 기술 |
|------|---------|---------|
| 1 | TagInput, FileDropzone, CategoryTab | DOM 조작, 드래그 이벤트 |
| 2 | ScrollReveal, ScrollScale, VideoScrubbing, HorizontalScroll | RAF 쓰로틀, IntersectionObserver, ResizeObserver |
| 3 | ScrambleText, RandomReveal | RAF 애니메이션 루프, Fisher-Yates 셔플 |
| 4 | ImageCarousel, CarouselContainer | 드래그/터치, translateX 트랜지션 |

---

## 삽질 1: Lookbook 프리뷰에서 Stimulus가 아예 안 됨

가장 크게 막혔던 부분이다. 컨트롤러를 다 구현하고 Lookbook을 열었는데 아무 동작도 하지 않는다. 크롬 DevTools를 열어보니 `data-controller` 속성은 붙어있는데 Stimulus가 연결이 안 된 상태였다.

개발 서버에서 직접 열면 잘 동작하는데, Lookbook 프리뷰에서만 망가지는 상황이라 처음엔 원인을 파악하기 어려웠다. Stimulus 자체 버그인지, ViewComponent 문제인지, 아니면 내 코드가 잘못된 건지 한참 헤맸다.

### 원인

Lookbook은 프리뷰를 `<iframe>`으로 렌더링한다. 이 iframe의 레이아웃 파일이 따로 있는데:

```erb
<%# app/views/layouts/previews/preview.html.erb %>
<head>
  <%= stylesheet_link_tag "application" %>
  <%# javascript_importmap_tags 가 없었음! %>
</head>
```

`stylesheet_link_tag`만 있고 `javascript_importmap_tags`가 없었다. CSS는 불러오는데 JS는 로드 자체가 안 된 것이다.

iframe은 완전히 독립된 브라우징 컨텍스트다. 부모 페이지에서 JavaScript가 로드되어 있어도, iframe 안에서 따로 로드하지 않으면 iframe 내부 DOM에는 Stimulus가 연결되지 않는다. 이 원리를 이해하고 나면 당연한 문제지만, 처음엔 Lookbook이 알아서 처리해줄 거라 막연히 기대했다.

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

Webpacker나 esbuild를 쓰는 환경이라면 `javascript_importmap_tags` 대신 해당 빌드 도구의 태그 헬퍼를 사용해야 한다. Importmap 기준으로는 위 한 줄이 전부다.

---

## Wave 1: DOM 조작 컨트롤러

### TagInput

Enter나 콤마로 태그를 추가하고, × 버튼으로 삭제, Backspace로 마지막 태그를 지우는 컨트롤러. 태그 입력 UI는 흔히 쓰이지만 제대로 구현하려면 신경 쓸 게 많다. 중복 방지, XSS 방어, 포커스 유지, 키보드 접근성 등을 모두 고려해야 한다.

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

`_escapeHtml`을 직접 구현한 이유는 `innerHTML`로 태그 내용을 삽입할 때 XSS를 막기 위해서다. 사용자 입력값을 그대로 `innerHTML`에 넣으면 `<script>` 같은 태그가 실행될 수 있다.

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

`data-action`에 여러 이벤트를 공백으로 구분해서 나열할 수 있다. 동일한 이벤트에 두 개의 액션을 붙이는 패턴이다.

### CategoryTab — underline indicator 애니메이션

기존 구현은 배경색만 바꾸는 방식이었다. 하단 인디케이터가 슬라이딩하는 방식으로 교체했다. 배경색 토글은 구현이 간단하지만 시각적으로 딱딱하다. 인디케이터가 탭 사이를 부드럽게 이동하는 방식이 훨씬 세련된 UX를 제공한다.

핵심은 선택된 탭의 `offsetLeft`와 `offsetWidth`를 읽어서 인디케이터 `<span>`에 적용하는 것이다:

```javascript
_moveIndicator(index) {
  const tab = this.element.querySelectorAll("[role='tab']")[index]
  if (!tab || !this.hasIndicatorTarget) return
  this.indicatorTarget.style.width = `${tab.offsetWidth}px`
  this.indicatorTarget.style.left = `${tab.offsetLeft}px`
}
```

인디케이터에 `transition: width 0.3s ease, left 0.3s ease`를 주면 탭 이동 시 자연스럽게 슬라이딩된다. `offsetLeft`는 부모 요소 기준의 픽셀 값이므로, 인디케이터가 탭 컨테이너에 `position: relative`를 가져야 정확히 위치한다.

초기 렌더링 시에는 `connect()`에서 현재 활성 탭을 찾아 `_moveIndicator`를 호출해야 한다. 그렇지 않으면 페이지 로드 시 인디케이터가 잘못된 위치에 있다가 첫 탭 클릭 시에야 제자리를 찾는다.

### FileDropzone

파일 드래그&드롭 컨트롤러는 `dragenter`, `dragover`, `dragleave`, `drop` 네 가지 이벤트를 모두 처리해야 한다. `dragover`에서 `event.preventDefault()`를 반드시 호출해야 `drop` 이벤트가 발생한다는 점이 가장 흔한 실수다.

드래그가 자식 요소 위를 통과할 때 `dragleave`가 의도치 않게 발생하는 문제는 카운터 방식으로 해결할 수 있다:

```javascript
connect() {
  this._dragCounter = 0
}

onDragEnter() {
  this._dragCounter++
  this.element.classList.add("drag-over")
}

onDragLeave() {
  this._dragCounter--
  if (this._dragCounter === 0) {
    this.element.classList.remove("drag-over")
  }
}

onDrop(event) {
  event.preventDefault()
  this._dragCounter = 0
  this.element.classList.remove("drag-over")
  const files = Array.from(event.dataTransfer.files)
  // 파일 처리 로직
}
```

---

## Wave 2: 스크롤 기반 컨트롤러

스크롤 이벤트는 무조건 RAF(requestAnimationFrame) 쓰로틀을 걸어야 한다. 매 스크롤 이벤트마다 DOM을 건드리면 렉이 생긴다. 스크롤 이벤트는 초당 수십 번 발생하는데, 각 이벤트마다 `getBoundingClientRect()` 같은 레이아웃 계산을 하면 강제 레이아웃(forced layout/reflow)이 연속으로 발생한다.

RAF 쓰로틀 패턴은 다음과 같다: 스크롤 이벤트가 발생하면 RAF를 예약하고, 실제 업데이트는 다음 프레임에 한 번만 수행한다. 이미 예약된 RAF가 있으면 중복 예약하지 않는다.

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

`{ passive: true }` 옵션은 이 이벤트 핸들러에서 `preventDefault()`를 호출하지 않겠다고 브라우저에게 알려주는 것이다. 이를 통해 브라우저가 스크롤 성능을 최적화할 수 있다.

`disconnect()`에서 리스너를 제거하지 않으면 컨트롤러가 DOM에서 제거된 후에도 스크롤 이벤트가 계속 발생한다. Turbo Drive 환경에서는 페이지 이동 시 컨트롤러가 `disconnect`되므로 반드시 정리해야 한다.

### ScrollReveal — 글자별 순차 등장

텍스트를 한 글자씩 `<span>`으로 쪼개고, 스크롤 진행도에 따라 `settledCount`개만큼 색상을 바꾼다. 사용자가 스크롤을 내릴수록 텍스트가 희미한 색에서 활성 색으로 순차적으로 변하는 효과다.

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

`window.innerHeight * 0.8`은 화면 높이의 80% 지점을 의미한다. 요소의 상단이 이 지점에 닿았을 때 애니메이션이 시작된다. 이 값을 조정하면 효과가 시작되는 시점을 변경할 수 있다.

공백 문자는 `<span>`으로 감싸지 않고 그대로 출력해야 단어 간 간격이 유지된다. `&nbsp;`를 쓰거나 그냥 공백을 HTML에 넣으면 되는데, 후자가 더 안전하다.

### VideoScrubbing

스크롤 위치를 `video.currentTime`에 매핑한다. IntersectionObserver로 화면에 들어왔을 때만 스크롤 리스너를 붙여서 성능을 아낀다. 비디오가 화면 밖에 있을 때도 스크롤 이벤트를 처리하는 건 순수한 낭비다.

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

비디오는 `muted playsinline preload="auto"` 속성이 필수다. `preload="auto"` 없으면 `duration`이 NaN이라 아무것도 안 된다. 브라우저가 비디오 메타데이터를 미리 로드하지 않으면 `duration` 값을 알 수 없기 때문이다.

또한 `video.currentTime`에 값을 설정하면 브라우저가 해당 프레임을 디코딩해야 하므로, 비디오 파일은 반드시 프레임 탐색이 가능한 형식(보통 MP4/H.264)이어야 한다.

### HorizontalScroll — 수직 스크롤 → 수평 이동

sticky container 안에서 수직 스크롤을 수평 translateX로 변환한다. 컨테이너 높이를 `100vh + scrollDistance`로 설정해서 스크롤 여유 공간을 확보하는 게 핵심이다.

이 효과는 Apple 제품 페이지에서 자주 볼 수 있다. sticky 포지셔닝 덕분에 내부 콘텐츠는 화면에 고정된 채로 스크롤 진행도를 translateX 값으로 환산한다.

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

`scrollWidth`는 가로 스크롤 가능한 전체 너비다. 화면 너비를 빼면 실제로 이동해야 할 거리가 나온다. 이 거리만큼 컨테이너 높이를 늘려서 스크롤 여유 공간을 만든다.

ResizeObserver로 뷰포트 크기 변경을 감지해서 `_setup()`을 다시 호출하는 것도 중요하다. 화면 크기가 바뀌면 `scrollDistance`가 달라지기 때문이다.

---

## Wave 3: 텍스트 애니메이션

### ScrambleText

텍스트가 랜덤 문자로 뒤섞인 후 좌→우 순서로 정착되는 효과. RAF 루프로 구현한다. 해킹 영화에서 자주 보이는 그 효과다. 구현 원리는 간단하다: 진행도(0~1)에 따라 앞쪽 `settledCount`개의 문자는 원본을, 나머지는 랜덤 문자를 보여준다.

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

`disconnect()`에서 `cancelAnimationFrame(this._rafId)`를 호출하지 않으면 컨트롤러가 제거된 후에도 RAF 루프가 계속 돌아간다. 아무것도 참조하지 않는 고아 RAF 루프는 메모리 누수와 CPU 낭비를 유발한다.

IntersectionObserver로 화면에 들어올 때 애니메이션을 트리거한다. `threshold: 0.3`으로 설정하면 30% 보일 때 시작된다.

```javascript
connect() {
  this._observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        this._startTime = null
        this._rafId = requestAnimationFrame(this._animate.bind(this))
        this._observer.unobserve(this.element)
      }
    },
    { threshold: 0.3 }
  )
  this._observer.observe(this.element)
}

disconnect() {
  if (this._rafId) cancelAnimationFrame(this._rafId)
  if (this._observer) this._observer.disconnect()
}
```

`unobserve`로 한 번 트리거된 후에는 더 이상 관찰하지 않는다. 페이지를 위아래로 스크롤할 때마다 애니메이션이 재실행되는 것을 막기 위해서다. 재실행이 필요하다면 `unobserve` 대신 `_startTime = null`만 리셋하면 된다.

### RandomReveal

Fisher-Yates 셔플로 글자 등장 순서를 랜덤하게 만들고, `delay + index * stagger` ms 간격으로 staggered setTimeout을 건다. ScrambleText가 좌→우 순서로 정착된다면, RandomReveal은 글자가 임의의 순서로 하나씩 나타나는 효과다.

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

Fisher-Yates 셔플은 완전히 균등한 분포를 보장하는 알고리즘이다. `Math.random()`으로 정렬하는 방식(`arr.sort(() => Math.random() - 0.5)`)은 특정 순열이 더 자주 나오는 편향이 있어 권장하지 않는다.

`setTimeout`을 많이 걸어두면 컨트롤러 `disconnect` 시 모두 취소해야 한다. 타이머 ID를 배열로 저장해두는 방법:

```javascript
this._timers = []
indices.forEach((charIndex, order) => {
  const id = setTimeout(() => { ... }, delay)
  this._timers.push(id)
})

disconnect() {
  this._timers?.forEach(clearTimeout)
}
```

---

## Wave 4: 캐러셀

### ImageCarousel — 드래그/터치/키보드/버튼

캐러셀에서 가장 신경 써야 할 건 드래그 판정 임계값이다. 50px 미만으로 드래그하면 클릭으로 처리하고, 50px 이상이면 슬라이드를 넘긴다. 임계값이 없으면 이미지를 클릭하려다 슬라이드가 넘어가는 불상사가 생긴다.

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

`event.clientX ?? event.touches?.[0].clientX` 패턴은 마우스 이벤트와 터치 이벤트를 동시에 처리한다. 마우스 이벤트는 `clientX`를 직접 제공하고, 터치 이벤트는 `touches` 배열에서 첫 번째 접촉점의 좌표를 사용한다.

`touchend` 이벤트에서는 `event.touches`가 비어있다. 종료된 접촉점의 좌표는 `event.changedTouches`에서 가져와야 한다.

오토플레이는 `setInterval`로 구현하되, 사용자가 수동으로 조작하면 인터벌을 초기화해야 자연스럽다:

```javascript
_resetAutoPlay() {
  if (this._autoPlayTimer) clearInterval(this._autoPlayTimer)
  if (this.autoPlayValue) {
    this._autoPlayTimer = setInterval(() => this.next(), this.autoPlayIntervalValue)
  }
}
```

`next()`나 `prev()`가 호출될 때마다 `_resetAutoPlay()`를 호출한다. 사용자가 수동으로 슬라이드를 바꾼 직후에도 타이머가 리셋되어 오토플레이 주기가 자연스럽게 재시작된다.

키보드 접근성도 고려해야 한다. `data-action`에 `keydown->image-carousel#onKeydown`을 추가하고, `ArrowLeft`/`ArrowRight` 키를 처리한다. 캐러셀 컨테이너에 `tabindex="0"`을 주어야 포커스를 받을 수 있다.

### CarouselContainer — 반응형 visible count

ResizeObserver로 컨테이너 너비가 바뀔 때마다 아이템 너비를 재계산한다. 반응형 레이아웃에서는 뷰포트 크기에 따라 보여줄 아이템 수가 달라진다. 미디어 쿼리로 `visible` 값을 바꿔주고 ResizeObserver가 변경을 감지하면 레이아웃을 재계산한다.

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

아이템 너비를 `minWidth`와 `maxWidth` 둘 다 설정하는 이유는 flex 컨테이너에서 아이템이 늘어나거나 줄어드는 것을 막기 위해서다. `width`만 설정하면 flex 동작에 따라 의도와 다르게 렌더링될 수 있다.

`_goTo(this._currentIndex)` 호출은 레이아웃이 바뀐 후 현재 슬라이드 위치가 올바른 translateX 값을 갖도록 재계산하는 것이다.

---

## 검증: Playwright로 iframe 내부 확인

Lookbook 프리뷰가 iframe이라 일반적인 Playwright locator로는 접근이 안 된다. `frameLocator`를 써야 한다. iframe 내부의 DOM은 부모 페이지의 DOM과 완전히 분리되어 있기 때문이다.

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

`evaluate()` 콜백은 브라우저 컨텍스트에서 실행된다. 이 안에서 Stimulus 컨트롤러 인스턴스에 직접 접근하려면 `element.stimulus` 같은 방식이 아니라 DOM 속성과 스타일을 통해 간접적으로 검증해야 한다.

각 컨트롤러별 검증 포인트:

- **CategoryTab**: 탭 클릭 후 indicator의 `left` 값 변경 여부
- **TagInput**: Enter 입력 후 `data-tag` 속성 chip 생성 여부
- **ScrambleText**: 애니메이션 완료 후 원본 텍스트와 일치 여부
- **ImageCarousel**: next 클릭 후 track의 `translateX` 값 변경 여부
- **CarouselContainer**: next 클릭 후 `translate3d` 값 변경 여부

Stimulus 자체가 연결됐는지 확인하려면 `data-controller` 속성이 있는 요소에 Stimulus가 추가하는 특수 속성(예: `data-[controller-name]-[value]-value`)이 올바르게 설정됐는지 보는 방법도 있다.

---

## 정리

Rails + Lookbook 환경에서 Stimulus를 쓸 때 놓치기 쉬운 포인트:

1. **프리뷰 레이아웃에 `javascript_importmap_tags` 추가** — 이게 없으면 Stimulus 자체가 로드 안 됨
2. **스크롤 이벤트는 RAF 쓰로틀** — `passive: true`도 함께 설정
3. **disconnect()에서 리스너 정리** — 메모리 누수 방지 (스크롤 리스너, RAF, setTimeout, Observer 모두)
4. **video scrubbing은 `preload="auto"`** — 없으면 `duration`이 NaN
5. **Lookbook iframe 내부는 `frameLocator`** — 일반 locator로 접근 불가

---

## Key Takeaways

- **Lookbook iframe 버그**: Lookbook은 프리뷰를 iframe으로 렌더링한다. `javascript_importmap_tags`가 iframe 레이아웃에 없으면 Stimulus가 아예 로드되지 않는다. Rails 8 Importmap 환경에서 Lookbook을 설치한 직후 반드시 확인할 것.
- **RAF 쓰로틀은 선택이 아닌 필수**: 스크롤 이벤트 핸들러에서 DOM을 조작할 때 RAF 쓰로틀 없이는 반드시 퍼포먼스 문제가 생긴다. 패턴은 항상 동일하므로 복사해서 쓰면 된다.
- **disconnect() 정리 철저히**: Turbo Drive 환경에서 페이지 이동 시 컨트롤러는 `disconnect`된다. 스크롤 리스너, RAF, setTimeout, IntersectionObserver, ResizeObserver를 모두 정리하지 않으면 고아 콜백이 남아 메모리 누수가 발생한다.
- **드래그 임계값**: 캐러셀에서 클릭과 드래그를 구분하는 50px 임계값은 UX의 핵심이다. 이 값 없이는 이미지 클릭 시 슬라이드가 의도치 않게 넘어간다.
- **코드 주석의 언어**: 인라인 주석은 팀 컨벤션에 맞추면 되지만, 공개 라이브러리나 블로그 예제라면 영어로 통일하는 것이 가독성에 유리하다.
