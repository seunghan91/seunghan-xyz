---
title: "앱스토어 마케팅 스크린샷 자동화 — Puppeteer + features.json 분석 주도 파이프라인"
date: 2026-03-26
draft: false
tags: ["AppStore", "Puppeteer", "Flutter", "마케팅", "자동화"]
description: "HTML/CSS로 마케팅 프레임 만들고 Puppeteer로 렌더링하는 앱스토어 스크린샷 자동화 파이프라인. 스크린샷 먼저 찍고 분석 후 문구를 결정하는 features.json 방식으로 50개를 한 번에 뽑아낸다."
---

앱 출시를 앞두고 스토어 스크린샷을 만들어야 하는 상황이 됐다. Figma로 하나씩 만드는 건 너무 비효율적이고, 10가지 디자인 시안에 5개 기능 화면을 조합하면 50장인데 수작업으로 한다는 건 말이 안 된다.

그래서 HTML/CSS로 마케팅 프레임을 만들고 Puppeteer로 PNG를 뽑아내는 파이프라인을 짰다. 처음엔 대충 만들었다가 구조적으로 틀린 부분이 있다는 걸 나중에 깨달았는데, 그 과정이 의외로 중요한 교훈을 남겼다.

---

## 처음 접근 방식의 문제

처음엔 이런 식으로 기능 배열을 하드코딩했다.

```js
const FEATURES = [
  { id: 'expense', title: '지출을 한번에', sub: 'AI가 영수증을 읽어드립니다', screen: '02_expense_detail' },
  { id: 'camera',  title: '사진 찍으면 끝', sub: 'OCR로 즉시 기록', screen: '03_camera_hub' },
  // ...
];
```

문제는 이 파일명들(`02_expense_detail.png`, `03_camera_hub.png`)이 실제로 존재하지 않았다는 것이다. 캡처 스크립트가 자동으로 화면을 이동하다가 실패해서 홈 화면만 5번 찍혔는데, 파일명은 다 달랐다. 결과적으로 모든 슬롯이 placeholder(검은 화면)였다.

```bash
md5 screenshots/raw/*.png
# 01_home_trip_list.png: 1f477573e7f94a08f86c771c730fa120
# 02_trip_detail.png:    1f477573e7f94a08f86c771c730fa120  ← 동일
# 03_expense_tab.png:    1f477573e7f94a08f86c771c730fa120  ← 동일
# 04_camera_hub.png:     1f477573e7f94a08f86c771c730fa120  ← 동일
```

MD5가 전부 같다. 같은 홈 화면을 4번 찍어서 파일명만 다르게 저장된 것이다.

---

## 진짜 문제: 순서가 거꾸로였다

단순히 파일명이 틀린 게 아니라 워크플로우 자체가 거꾸로였다.

**잘못된 순서:**
```
기능/문구 먼저 결정 → 파일명 맞추려 시도 → 없으면 placeholder
```

**올바른 순서:**
```
스크린샷 자유롭게 캡처 → 화면 분석 → 그 화면에 맞는 문구 결정 → 렌더링
```

스크린샷을 보기 전에 문구를 정하면 나중에 억지로 끼워맞추게 된다. 실제 앱 화면이 어떻게 생겼는지, 어떤 정보를 담고 있는지를 먼저 봐야 "지출을 한번에"가 맞는 표현인지 "카테고리별 자동 분류"가 맞는지 판단할 수 있다.

---

## features.json 분석 주도 방식

이걸 해결하기 위해 `features.json`을 중간 단계로 추가했다.

```
캡처 → features.json 작성 → 렌더링
```

`features.json`은 단순한 설정 파일이 아니라 **화면 분석의 결과물**이다. 화면을 직접 보고, 어떤 기능을 가장 잘 보여주는지 판단한 뒤에 작성한다.

```json
[
  {
    "id": "expense",
    "title": "지출을 한번에",
    "sub": "카테고리별 자동 분류",
    "screen": "expense_list"
  },
  {
    "id": "trip_detail",
    "title": "여행의 모든 것",
    "sub": "일정·지출·정산이 한 화면에",
    "screen": "trip_detail"
  }
]
```

`screen` 필드는 `screenshots/raw/` 안의 실제 파일명(확장자 제외)을 그대로 쓴다. 파일이 없으면 placeholder가 뜨기 때문에 즉시 확인 가능하다.

렌더링 스크립트는 이 파일을 읽어서 처리한다.

```js
const FEATURES_CFG = path.join(ROOT, 'screenshots/features.json');
const FEATURES = JSON.parse(fs.readFileSync(FEATURES_CFG, 'utf8'));

// 매핑 검증
FEATURES.forEach(f => {
  const p = path.join(RAW_DIR, `${f.screen}.png`);
  if (!fs.existsSync(p)) {
    console.warn(`⚠️  [${f.id}] 파일 없음: ${f.screen}.png → placeholder 사용`);
  }
});
```

---

## 전체 파이프라인 구조

```
screenshots/
├── raw/           # 원본 캡처 PNG (아무 이름이나 가능)
├── features.json  # 화면 분석 결과 (화면파일 + 마케팅 문구)
├── marketing/     # 최종 출력 PNG (1320×2868, 스토어 업로드용)
└── templates/     # 중간 HTML 파일
```

### 1단계: 캡처

시뮬레이터에서 화면을 자유롭게 캡처한다. 파일명에 규칙은 없다. 나중에 features.json에서 연결하면 되기 때문이다.

```bash
xcrun simctl io D06F2A40-B4E8-4BAE-9151-CF38EE189469 screenshot screenshots/raw/expense_list.png
xcrun simctl io D06F2A40-B4E8-4BAE-9151-CF38EE189469 screenshot screenshots/raw/trip_detail.png
```

캡처 전에 상태바를 정리해두면 더 깔끔한 스크린샷이 나온다.

```bash
xcrun simctl status_bar booted override \
  --time '9:41' \
  --dataNetwork 'wifi' \
  --batteryState 'charged' \
  --wifiBars 3
```

### 2단계: 화면 분석 후 features.json 작성

raw/ 폴더를 열어서 각 PNG가 어떤 화면인지 확인한다. 그리고 그 화면이 전달할 수 있는 가장 임팩트 있는 문구를 결정한다.

좋은 마케팅 문구의 기준:
- **기능** 나열이 아닌 **혜택** 중심: "시간 추적" → "하루 2시간 절약"
- 2025년 이후 Apple이 스크린샷 텍스트를 검색 메타데이터로 인덱싱하기 때문에 키워드 포함이 중요해졌다
- 제목은 7단어 이내, 한눈에 읽히는 길이

### 3단계: 렌더링

```bash
node scripts/screenshots/render_templates.js
```

10가지 디자인 스타일 × features.json의 슬롯 수 = 출력 PNG 수

현재 5개 슬롯이면 50개 PNG가 `marketing/` 폴더에 저장된다.

---

## HTML/CSS 마케팅 프레임 구조

각 PNG는 순수 HTML/CSS로 만들어진 1320×2868px 페이지를 Puppeteer가 캡처한 것이다.

```html
<!-- 1320×2868px 캔버스 -->
<body style="width:1320px; height:2868px; background: {style.bg}">

  <!-- 헤더: 배지 + 큰 제목 + 부제목 -->
  <div class="header">
    <div class="badge">AppName</div>          <!-- accent 색 테두리 -->
    <div class="title">{feature.title}</div>   <!-- 116px, 900weight -->
    <div class="subtitle">{feature.sub}</div>  <!-- 52px, 400weight -->
  </div>

  <!-- 디바이스 목업 -->
  <div class="phone-frame">
    <div class="phone-screen">
      <img src="file:///path/to/raw/screenshot.png">
    </div>
  </div>

  <!-- 푸터 -->
  <div class="footer">
    <div class="app-name">AppName</div>
    <div class="store-badge">✈️ AI 여행 기록 앱</div>
  </div>

</body>
```

폰 프레임 CSS:

```css
.phone-frame {
  width: 640px;
  height: 1385px;
  background: #0a0a0a;
  border-radius: 72px;
  padding: 20px;
  box-shadow: 0 0 60px rgba(32,178,170,0.4), 0 40px 80px rgba(0,0,0,0.5);
}
.phone-screen {
  width: 100%;
  height: 100%;
  border-radius: 56px;
  overflow: hidden;
}
.phone-screen img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top;
}
```

### Puppeteer 렌더링 핵심 설정

```js
const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--font-render-hinting=none']
});

const page = await browser.newPage();
await page.setViewport({ width: 1320, height: 2868, deviceScaleFactor: 1 });

// networkidle0: 폰트, 이미지 완전 로드 후 캡처
await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle0' });

await page.screenshot({ path: outPath, fullPage: false });
```

`waitUntil: 'networkidle0'`이 중요하다. Google Fonts가 로드되기 전에 캡처하면 시스템 폰트로 렌더링돼서 디자인이 깨진다.

`deviceScaleFactor: 1`로 설정하면 1320px 그대로 출력된다. 2로 올리면 2640px로 나오지만 파일 크기가 4배가 되므로 앱스토어 제출 규격(10MB 이하)에 맞게 조정 필요.

---

## 10가지 디자인 스타일

앱 주색에 따라 스타일을 고르면 된다.

| 스타일 ID | 이름 | 배경 | 맞는 앱 장르 |
|---|---|---|---|
| `dark_glass` | 다크 글라스모피즘 | 다크 + 청록 글로우 | 금융, 테크, 피트니스 |
| `clean_white` | 클린 화이트 | 밝은 회백색 | 생산성, 헬스 |
| `teal_gradient` | 틸 그라디언트 | 네이비 → 청록 | 여행, 소셜 |
| `midnight_blue` | 미드나이트 블루 | 딥 네이비 + 퍼플 | 명상, 수면, 금융 |
| `warm_sunset` | 워밍 선셋 | 퍼플 → 레드 → 오렌지 | 여행, 음식, 라이프스타일 |
| `forest_dark` | 포레스트 다크 | 다크 그린 | 건강, 환경 |
| `aurora` | 오로라 | 다크 퍼플 + 그린 | AI, 명상, 프리미엄 |
| `bold_black` | 볼드 블랙 | 순수 블랙 | 패션, 음악, 카메라 |
| `soft_lavender` | 소프트 라벤더 | 밝은 라벤더 | 웰니스, 다이어리 |
| `ocean_depth` | 오션 딥 | 딥 오션 블루 | 여행, 스포츠 |

스타일 선택 시 한 가지 함정이 있다. **앱 UI가 밝은 베이지/화이트 배경이면 다크 배경과 극단적으로 대비된다.** 프레임이 보이지 않거나 앱 화면이 너무 튀어 보인다.

해결 방법:
```css
/* frameBg를 살짝 밝게 올려서 배경과 분리 */
.phone-frame {
  background: #1a2a2a;  /* #0a0a0a 대신 */
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1),
              0 0 60px rgba(32,178,170,0.4),
              0 40px 80px rgba(0,0,0,0.5);
}
```

또는 앱 UI가 밝으면 `clean_white`나 `soft_lavender` 같은 밝은 배경 스타일을 선택하는 게 낫다.

---

## 앱스토어 업로드 규격 (2026 기준)

2024년 9월 iPhone 16 출시 이후 규격이 바뀌었다.

| 플랫폼 | 슬롯 | 픽셀 | 필수 여부 |
|---|---|---|---|
| iOS | iPhone 6.9" | 1320×2868 또는 1290×2796 | **필수** |
| iOS | iPad 13" | 2064×2752 | **필수** (iPad 앱) |
| iOS | iPhone 6.5" | 1284×2778 | 선택 (6.9" 있으면 자동 스케일) |
| Android | Phone | 1080×1920 | 필수 |
| Android | Feature Graphic | 1024×500 | 필수 |

**핵심 변화**: 6.9인치 1장만 제출하면 6.5", 6.1", 5.5" 전부 자동 스케일 다운 처리된다. 즉 iPhone용은 1320×2868 하나면 충분하다.

현재 파이프라인이 정확히 1320×2868로 출력하고 있으므로 iOS는 바로 업로드 가능하다. Android용은 별도로 1080×1920 캔버스를 만들어야 한다.

---

## 2025-2026 스크린샷 트렌드 반영

조사하면서 알게 된 중요한 변화가 하나 있다.

**2025년 6월부터 Apple이 스크린샷의 텍스트를 검색 인덱스에 포함시켰다.** 스크린샷 위에 올라가는 문구가 이제 직접 검색 순위에 영향을 미친다. features.json에 문구를 작성할 때 단순한 마케팅 카피가 아니라 검색 키워드 전략과 연동해야 한다는 뜻이다.

그 외 2025-2026 트렌드:
- **첫 3장이 전체 engagement의 83%** → 핵심 가치 제안을 앞쪽 슬롯에 배치
- 고대비 색상(Teal, Coral, Neon 그라디언트)이 스크롤 중 주목도 높음
- 디바이스 프레임 없이 raw UI만 올리면 미완성처럼 보임

---

## 화면 추가할 때

새 스크린샷이 생기면 세 단계로 처리한다.

```bash
# 1. raw/ 에 복사
cp ~/Desktop/new_screen.png screenshots/raw/

# 2. features.json 에 항목 추가
# { "id": "new_id", "title": "임팩트 제목", "sub": "한줄 설명", "screen": "new_screen" }

# 3. 재렌더링
node scripts/screenshots/render_templates.js
```

features.json 항목 수가 늘어나는 만큼 마케팅 PNG 수가 늘어난다. 6개 슬롯이면 60장.

---

## 정리

처음엔 단순히 "스크린샷 파일명이 틀렸다"는 문제인 줄 알았는데, 파고드니 워크플로우 설계 자체가 거꾸로였다. 문구를 먼저 정하고 화면을 끼워맞추려 하면 실제 화면이 문구와 안 맞는 상황이 반드시 생긴다.

**분석이 먼저, 문구는 나중.** features.json이 그 중간 단계로서 화면을 직접 보고 판단한 결과를 담는 역할을 한다.

파이프라인 전체를 코드로 보고 싶다면 `render_templates.js`와 `capture_sim.sh`를 참고하면 된다. Puppeteer만 있으면 어떤 앱이든 동일한 구조로 재사용 가능하다.
