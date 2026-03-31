---
title: "JANDI 채팅방 크롤링 — AngularJS 가상 스크롤 SPA를 Puppeteer로 전수 수집한 삽질기"
date: 2026-03-31
draft: false
tags: ["puppeteer", "crawling", "spa", "render", "jandi"]
description: "JANDI 메신저의 AngularJS SPA를 Puppeteer로 크롤링하면서 겪은 가상 스크롤, 세션 관리, Render cron job 배포까지의 전 과정을 정리했다. Playwright에서 Puppeteer + @sparticuz/chromium-min으로 전환한 이유도 함께."
---

## 왜 JANDI 채팅방을 크롤링해야 했나

한국거래소(KRX)에서 증권사 담당자들과 소통하는 채널로 JANDI 메신저를 사용하고 있다. "[KRX] 거래시간 연장 및 장애대응 실시간 채팅"이라는 채팅방에서 400여 명의 증권사 담당자들이 질문하고, KRX 측이 답변하는 구조다.

문제는 이 Q&A 내역을 체계적으로 관리할 방법이 없다는 것이었다. JANDI에는 메시지 읽기 API가 없고, Outgoing Webhook은 시작 키워드가 필수라서 모든 메시지를 수신할 수 없다. 결국 **브라우저 자동화로 직접 크롤링**하는 수밖에 없었다.

---

## JANDI의 기술 스택이 만든 함정

JANDI 웹앱은 **AngularJS 기반 SPA**(Single Page Application)다. 열어보면 URL이 `https://next-it.jandi.com/app/#!/room/34791415` 같은 해시 라우팅을 쓰고 있다. 이게 크롤링에 어떤 영향을 주는지 처음엔 몰랐다.

### 가상 스크롤 (Virtual Scrolling)

가장 큰 함정은 **가상 스크롤**이었다. 채팅방에 수백 개의 메시지가 있지만, DOM에는 현재 화면에 보이는 30~80개 정도만 렌더링된다. 위아래로 스크롤하면 기존 요소가 사라지고 새 요소가 나타나는 구조다.

```javascript
// 처음에 시도한 방식 — 전부 실패
const allMessages = document.querySelectorAll('.message');
// 결과: 현재 화면에 보이는 30개만 반환
```

일반적인 무한 스크롤(infinite scroll)과 다른 점은, 스크롤해서 새 메시지가 로드되면 **이전 메시지가 DOM에서 제거**된다는 것이다. 그래서 한 번에 모든 메시지를 수집할 수 없다.

### 메시지 구조의 복잡성

JANDI 메시지 DOM은 `content-type` 속성으로 구분된다:

| content-type | 의미 | 비고 |
|-------------|------|------|
| `dateDivider` | 날짜 구분선 | "2025년 12월 9일 화요일" |
| `systemEvent` | 시스템 메시지 | 초대/퇴장 알림 |
| `text` | 일반 메시지 | 실제 대화 내용 |
| `comment` | 스레드 댓글 | 원글에 달린 답글 |
| `poll` | 투표 | 투표 메시지 |

같은 사람이 연속으로 보내면 두 번째 메시지부터 `text-child text-split` 클래스가 추가되면서 **작성자 이름이 표시되지 않는다**. 시간 정보도 `<time>` 태그의 `tooltip` 속성에 들어있는데, 모든 메시지에 `tooltip`이 있는 건 아니다.

---

## 도구 선택: Hyperbrowser → Playwright → Puppeteer

### Hyperbrowser (실패)

처음에는 MCP 도구인 Hyperbrowser를 시도했다. 클라우드 브라우저로 JANDI에 로그인까지는 성공했지만, CAPTCHA 문제와 스텝 제한(최대 50 스텝) 때문에 전수 수집은 불가능했다.

```
Final Result: I encountered a captcha after attempting to log in.
The page displays a captcha with the instruction "Select all images with crosswalks".
```

### Playwright MCP (성공, 로컬 한정)

로컬 Playwright MCP로 전환하니 훨씬 나았다. 브라우저를 직접 제어할 수 있어서 로그인, 스크롤, 데이터 추출이 자유로웠다.

```javascript
// Playwright MCP로 JANDI 로그인
await page.goto('https://www.jandi.com/signin');
await page.getByRole('textbox', { name: '이메일' }).fill('email@example.com');
await page.getByRole('textbox', { name: '비밀번호' }).fill('password');
await page.getByRole('button', { name: '로그인' }).click();
```

문제는 이걸 **서버에서 자동화**할 수 없다는 것이다. Playwright는 시스템 의존성(`libX11`, `libatk` 등)이 필요한데, Render.com의 Node.js 환경에서는 root 권한이 없어서 설치가 불가능하다.

```
Password: su: Authentication failure
Failed to install browsers
Error: Installation process exited with code: 1
```

### Puppeteer + @sparticuz/chromium-min (최종 선택)

서버리스 환경에서 headless 브라우저를 돌리는 표준 해법이 있었다. `puppeteer-core`와 `@sparticuz/chromium-min` 조합이다.

```json
{
  "dependencies": {
    "puppeteer-core": "^24.0.0",
    "@sparticuz/chromium-min": "^143.0.0"
  }
}
```

`@sparticuz/chromium-min`은 AWS Lambda 환경용으로 만들어진 Chromium 바이너리다. 시스템 의존성 없이 자체적으로 동작하며, Render의 Node.js cron job에서도 문제없이 실행된다.

```javascript
const puppeteer = require("puppeteer-core");
const chromium = require("@sparticuz/chromium-min");

const browser = await puppeteer.launch({
  headless: "new",
  args: chromium.args,
  executablePath: await chromium.executablePath(),
  defaultViewport: chromium.defaultViewport,
});
```

주의할 점이 있다. **`puppeteer`가 아니라 `puppeteer-core`를 써야 한다**. `puppeteer`는 자체 Chromium을 다운로드하는데, 이게 서버리스 환경에서는 경로 충돌을 일으킨다.

---

## 가상 스크롤 SPA 크롤링 전략

### 핵심: 점진적 수집 + ID 기반 중복 제거

가상 스크롤 때문에 한 번에 모든 메시지를 가져올 수 없다. 대신 **스크롤하면서 각 위치에서 보이는 메시지를 수집하고, ID로 중복을 제거**하는 방식을 사용했다.

```javascript
const allMessages = {}; // id -> message (중복 방지)
const allDates = [];

// 맨 아래(최신)부터 시작 → 위로 스크롤하며 과거 로드
await page.evaluate(() => {
  document.getElementById("msgs_container").scrollTop = 
    document.getElementById("msgs_container").scrollHeight;
});

let prevH = 0, stableH = 0, iter = 0;
while (stableH < 5 && iter < 300) {
  // 5개 지점에서 수집 (100%, 70%, 40%, 10%, 0%)
  for (const ratio of [1, 0.7, 0.4, 0.1, 0]) {
    await page.evaluate((r) => {
      const c = document.getElementById("msgs_container");
      c.scrollTop = c.scrollHeight * r;
    }, ratio);
    await new Promise(r => setTimeout(r, 350));
    addItems(await collect());
  }

  // 맨 위로 → 과거 메시지 로드 트리거
  await page.evaluate(() => {
    document.getElementById("msgs_container").scrollTop = 0;
  });
  await new Promise(r => setTimeout(r, 1500));
  addItems(await collect());

  // scrollHeight가 더 이상 늘어나지 않으면 종료
  const curH = await page.evaluate(() => 
    document.getElementById("msgs_container")?.scrollHeight || 0
  );
  if (curH === prevH) stableH++;
  else stableH = 0;
  prevH = curH;
  iter++;
}
```

여기서 **5개 비율 지점(100%, 70%, 40%, 10%, 0%)에서 수집**하는 게 핵심이다. 가상 스크롤은 현재 스크롤 위치 근처의 메시지만 DOM에 렌더링하기 때문에, 한 위치에서만 수집하면 중간 메시지를 놓칠 수 있다.

### scrollHeight 변화로 로딩 완료 감지

JANDI는 맨 위로 스크롤하면 과거 메시지를 추가 로드한다. 이때 `scrollHeight`가 증가하는데, 더 이상 증가하지 않으면 모든 메시지가 로드된 것이다. `stableH < 5`는 5번 연속 변화 없으면 종료하는 조건이다.

### 메시지 추출 함수

```javascript
const collect = () => page.evaluate(() => {
  const c = document.getElementById("chat-messages");
  if (!c) return [];
  let lastAuthor = "";
  return Array.from(c.children).map(el => {
    const ct = el.getAttribute("content-type") || "";
    const id = el.id || "";
    
    if (ct === "dateDivider")
      return { _t: "D", text: el.querySelector(".msg-system")?.textContent?.trim() };
    if (ct === "systemEvent" || !id) return null;

    // 작성자: text-child면 이전 작성자 이어받기
    const isChild = el.classList.contains("text-child");
    let author = el.querySelector(".member-names")?.textContent?.trim() || "";
    if (!author && isChild) author = lastAuthor;
    if (author) lastAuthor = author;

    // 시간: tooltip 속성 우선
    const timeEl = el.querySelector("time.fn-time-stamp");
    const time = timeEl?.getAttribute("tooltip") || 
                 timeEl?.getAttribute("data-write-time") || "";

    const text = el.querySelector(".msg-text-box")?.textContent?.trim() || "";
    return { _t: ct, id, author, time, text };
  }).filter(Boolean);
});
```

---

## 데이터 후처리: 빠진 정보 채우기

크롤링 원본 데이터에는 빠진 정보가 상당했다.

| 항목 | 크롤링 직후 | 후처리 후 |
|------|-----------|---------|
| 작성자 | 203/315 (64%) | **315/315 (100%)** |
| 시간 | 297/315 (94%) | **315/315 (100%)** |
| 날짜 | 289/315 (92%) | **315/315 (100%)** |

### 작성자 이어받기

JANDI에서 같은 사람이 연속 메시지를 보내면 두 번째부터 이름이 안 나온다. ID순으로 정렬한 뒤 빈 작성자를 이전 값으로 채웠다.

```python
last_author = ''
for m in data:
    if m.get('author'):
        last_author = m['author']
    elif not m.get('author') and last_author:
        m['author'] = last_author
```

### 시간 보간

시간이 없는 18개 메시지는 앞뒤 메시지의 시간으로 보간했다. 메시지 본문에 "현시점(13:30)부터"처럼 시간이 포함된 경우도 있어서, 정규식으로 추출하는 로직도 추가했다.

```python
time_match = re.search(r'현시점\((\d{1,2}:\d{2})\)', text)
if time_match:
    extracted = time_match.group(1)  # "13:30"
    # AM/PM 변환 + 앞 메시지의 날짜 부분 결합
```

---

## Q&A 자동 분류

크롤링한 315개 메시지에서 Q&A를 자동으로 추출했다.

### 질문 감지 패턴

```ruby
question_patterns = [
  /\?/, /？/,
  /문의/, /여쭤/, /확인.*부탁/, /확인.*가능/, /맞[을나는]까/,
  /인[가지]요/, /될까요/, /할까요/, /나요\?/,
  /어떻게/, /어떤/, /언제/
]
```

KRX 직원의 메시지는 제외하고(`[KRX`로 시작하는 작성자), 10자 미만 텍스트도 제외했다.

### 응답 매칭

질문에 대한 KRX 응답을 3단계로 탐색했다:

1. **스레드 댓글** — 질문에 직접 달린 답글
2. **인라인 댓글** — 메시지에 펼쳐진 댓글
3. **이후 10개 메시지** — 같은 날짜 내에서 KRX 작성자의 메시지

### 중복 제거

같은 사람이 같은 질문을 여러 번 한 경우(JANDI 가상 스크롤 때문에 중복 수집됨)를 `question_text + asker_name` 조합으로 제거했다. 72개 → 40개로 정리되었다.

---

## Render cron job으로 자동화

### 왜 GitHub Actions가 아닌 Render인가

| 방법 | 비용 | 문제 |
|------|------|------|
| GitHub Actions | 무료 (2000분/월) | **Billing 한도 초과 시 실행 불가** |
| Render cron job | Starter ($7/월) | Node.js 환경에서 Puppeteer 실행 가능 |
| 맥미니 cron | 무료 | 항상 켜놔야 함 |

GitHub Actions는 billing 문제로 실행이 안 됐고, 맥미니는 상시 운영이 부담스러워서 Render cron job을 선택했다.

### Render cron job 설정

```yaml
Name: krx-jandi-crawl
Runtime: Node
Schedule: 0 15 * * *  (매일 KST 자정)
Build Command: cd scripts && npm install
Start Command: node scripts/jandi_crawl.js
Region: Singapore
```

크롤링 결과는 웹 서비스의 import API로 POST한다:

```javascript
const res = await fetch(`${IMPORT_URL}?token=${TOKEN}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(messages),
});
```

### Render에서 Puppeteer 실행 시 주의사항

1. **`puppeteer-core`를 사용할 것** — `puppeteer`는 자체 Chromium 다운로드를 시도하는데 Render에서 실패한다
2. **`@sparticuz/chromium-min` 버전 확인** — npm에서 실제 버전은 `143.0.0`대인데, 블로그 글에서 `^1.1.3`으로 잘못 알려진 경우가 많다
3. **`--with-deps` 쓰지 말 것** — root 권한이 없어서 시스템 deps 설치가 불가능하다

```
# 이렇게 하면 실패
npx playwright install chromium --with-deps
# su: Authentication failure
# Failed to install browsers

# 이렇게 해야 성공
npm install puppeteer-core @sparticuz/chromium-min
```

---

## 교훈

### SPA 크롤링의 핵심 원칙

1. **DOM에 모든 데이터가 있다고 가정하지 말 것** — 가상 스크롤은 보이는 것만 렌더링한다
2. **scrollHeight 변화를 로딩 완료 신호로 활용** — `networkidle`은 SPA에서 신뢰할 수 없다
3. **ID 기반 중복 제거는 필수** — 같은 메시지가 여러 스크롤 위치에서 수집될 수 있다
4. **API 인터셉트를 먼저 시도** — DOM 파싱보다 XHR/fetch 응답을 가로채는 게 더 안정적이다 (JANDI는 API가 없어서 이 방법을 못 썼다)

### 도구 선택 가이드

| 상황 | 추천 도구 |
|------|----------|
| 로컬 개발/테스트 | Playwright (기능 풍부, auto-wait 우수) |
| 서버리스/cron | puppeteer-core + @sparticuz/chromium-min |
| 클라우드 브라우저 | Hyperbrowser, Browserless (간단한 작업만) |
| CI/CD | Playwright (GitHub Actions Ubuntu runner) |

### JANDI 연동 옵션 정리

| 방법 | 실시간 | 전체 수집 | API 필요 |
|------|--------|----------|---------|
| Outgoing Webhook | O | X (키워드 필수) | X |
| Incoming Webhook | X (발신 전용) | X | X |
| Puppeteer 크롤링 | X (cron) | O | X |
| JANDI API | - | - | **없음** |

JANDI에 메시지 읽기 API가 없다는 건 처음 알았다. Slack은 `conversations.history` API가 있어서 프로그래밍으로 메시지를 가져올 수 있는데, JANDI는 웹훅만 제공한다. 결국 브라우저 크롤링이 유일한 방법이었다.

---

## 결과

매일 자정 Render cron job이 돌면서 JANDI 채팅방을 크롤링하고, 새 메시지를 DB에 저장한다. Rails 앱에서 Q&A 모니터링 페이지를 제공하고, 미응답 질문을 추적할 수 있게 되었다.

| 항목 | 수치 |
|------|------|
| 수집 메시지 | 315개 |
| 작성자/시간/날짜 | 100% |
| Q&A 감지 | 40개 (중복 제거 후) |
| 응답 완료 | 30개 (75%) |
| 미응답 | 10개 (25%) |

가장 오래 걸린 건 가상 스크롤 문제를 파악하는 거였다. "왜 메시지가 80개밖에 안 잡히지?"라는 의문에서 시작해서, DOM 구조를 분석하고, 스크롤 전략을 바꾸고, 도구를 3번 갈아타는 데 반나절이 걸렸다. 하지만 한 번 구조를 잡아놓으니 cron으로 자동화하는 건 수월했다.
