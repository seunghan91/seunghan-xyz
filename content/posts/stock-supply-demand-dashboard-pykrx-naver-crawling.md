---
title: "한국 주식 수급분석 대시보드 만들기 — pykrx 사망부터 네이버 크롤링까지"
date: 2026-03-24
draft: false
tags: ["python", "nextjs", "pykrx", "주식", "크롤링"]
description: "pykrx가 pandas 2.x와 KRX 사이트 변경으로 완전히 깨진 상황에서, 네이버 증권 크롤링으로 외국인/기관 수급 데이터를 수집하고 Next.js + lightweight-charts로 실시간 대시보드를 만든 과정을 정리했다."
---

주식 투자에서 "외국인이 샀다", "기관이 팔았다"는 뉴스를 자주 접하지만, 정작 이 데이터를 프로그래밍으로 가져와서 분석하려면 막막한 경우가 많다. 특히 한국 시장은 KRX가 투자자별 매매동향을 공개하고 있어 데이터 접근성이 좋은 편인데, 문제는 이걸 자동화하는 도구들이 생각보다 불안정하다는 거다.

이번에 수급분석 웹 대시보드를 만들면서 겪은 삽질을 기록한다. pykrx가 완전히 깨져서 네이버 증권 크롤링으로 우회한 과정, lightweight-charts로 누적 순매수 차트를 구현하면서 Y축 포맷팅에서 막힌 부분, 그리고 실제 데이터를 수집해서 대시보드에 연결하기까지의 전체 과정이다.

---

## 수급분석이란

수급분석은 매매주체별 거래 흐름을 추적하는 방법이다. 한국 시장에서는 크게 세 가지 주체로 나뉜다.

| 매매주체 | 설명 | 특징 |
|---------|------|------|
| 외국인 | 해외 기관/개인 | 대형주 주도세력, 방향성 일관적 |
| 기관 | 연기금, 금융투자, 사모, 보험 등 | 세부 분류별 성격이 다름 |
| 개인 | 국내 개인 투자자 | 다수가 제각각 → 방향성 약함 |

핵심은 **외국인·기관의 순매수 추세가 주가 방향과 일치하는 경우가 많다**는 점이다. 삼성전자의 경우 외국인이 순매도하면 주가가 하락하고, 순매수로 전환하면 주가가 반등하는 패턴이 반복적으로 관찰된다.

이걸 웹 대시보드로 만들면 HTS/MTS 없이도 수급 흐름을 한눈에 파악할 수 있다.

---

## pykrx는 왜 죽었나

Python으로 한국 주식 데이터를 가져올 때 가장 먼저 떠오르는 라이브러리가 pykrx다. KRX 웹사이트를 스크래핑해서 OHLCV, 시가총액, 투자자별 순매수 등을 제공한다. 설치도 간단하고 API도 직관적이다.

```python
from pykrx import stock

# 삼성전자 투자자별 순매수 (detail=True → 기관 세분화)
df = stock.get_market_trading_value_by_date('20260310', '20260323', '005930', detail=True)
```

문제는 이 코드가 2026년 3월 기준으로 **Empty DataFrame을 반환**한다는 거다.

```
=== 삼성전자 순매수 (detail=True) ===
Empty DataFrame
Columns: []
Index: []
```

시가총액 함수는 아예 에러가 난다.

```python
cap = stock.get_market_cap_by_ticker('20260323')
```

```
KeyError: "None of [Index(['종가', '시가총액', '거래량', '거래대금'], dtype='object')] are in the [columns]"
```

### 원인 1: KRX 웹사이트 구조 변경

pykrx는 KRX의 HTML을 파싱해서 데이터를 추출한다. KRX가 웹사이트 구조를 바꾸면 파싱 로직이 깨진다. 2024~2025년 사이에 KRX가 상당한 구조 변경을 했고, pykrx의 여러 함수가 동시에 영향을 받았다.

GitHub 이슈를 보면 `#228`, `#227`, `#225` 등 다수의 관련 이슈가 Open 상태로 남아있다.

### 원인 2: pandas 2.x 호환 문제

pykrx는 pandas 1.x 시절에 만들어졌다. pandas 2.x에서는 `astype()` 등의 타입 변환이 엄격해졌는데, KRX가 휴장일에 반환하는 `-` 같은 값을 정수로 변환하려 하면 ValueError가 발생한다.

흔히 제안되는 해결법은 pandas 다운그레이드다.

```bash
pip install pandas==2.0.3
```

실제로 시도해봤다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install 'numpy<2' 'pandas==2.0.3' pykrx
```

결과: pandas 버전을 맞춰도 **Empty DataFrame 문제는 그대로**였다. KRX 웹사이트 구조 자체가 바뀐 게 근본 원인이라 pandas 버전과는 무관했다.

### KRX 직접 API 호출도 실패

pykrx를 버리고 KRX API를 직접 호출해봤다. KRX data.krx.co.kr은 OTP 발급 → 데이터 요청 2단계 구조다.

```python
otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
data_url = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'

otp_resp = requests.get(otp_url, params=params, headers=headers)
data_resp = requests.post(data_url, data={'code': otp_resp.text}, headers=headers)
```

```
Not JSON. Text: <!DOCTYPE HTML>
<html>
<head>
<title>한국거래소</title>
```

HTML 에러 페이지가 반환됐다. KRX가 외부 스크래핑을 차단하고 있는 것으로 보인다.

---

## 네이버 증권 크롤링으로 우회

pykrx도 안 되고, KRX 직접 호출도 안 되니 남은 건 네이버 증권이다. 네이버 증권은 두 가지 데이터 소스를 제공한다.

### 1. siseJson API — OHLCV 데이터

네이버가 제공하는 JSON API로, 인증 없이 바로 사용할 수 있다.

```python
url = "https://api.finance.naver.com/siseJson.naver"
params = {
    "symbol": "005930",
    "requestType": 1,
    "startTime": "20250101",
    "endTime": "20260324",
    "timeframe": "day",
}
resp = requests.get(url, params=params)
```

응답은 JavaScript 배열 형식이다.

```
[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],
["20260310", 187600, 191500, 184300, 187900, 33530170, 49.79],
["20260311", 193000, 194800, 187700, 190000, 24311356, 49.77],
...
```

JSON이 아니라 JS 리터럴이라서 `'`를 `"`로 바꿔야 파싱된다.

```python
text = resp.text.strip().replace("'", '"')
data = json.loads(text)
```

### 2. frgn.naver 페이지 — 외국인/기관 순매수

종목별 외국인·기관 순매매 데이터는 HTML 테이블로 제공된다.

```
https://finance.naver.com/item/frgn.naver?code=005930&page=1
```

BeautifulSoup으로 파싱하면 된다. 테이블 구조는 이렇다.

| 날짜 | 종가 | 전일비 | 등락률 | 거래량 | 기관 | 외국인 | 보유주수 | 보유율 |
|------|------|--------|--------|--------|------|--------|---------|--------|

핵심 코드:

```python
from bs4 import BeautifulSoup
import requests

url = f"https://finance.naver.com/item/frgn.naver?code=005930&page=1"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(resp.text, "html.parser")

for t in soup.select("table.type2"):
    ths = [th.get_text(strip=True) for th in t.select("th")]
    if "기관" in ths and "외국인" in ths:
        # 이 테이블이 순매수 데이터
        for row in t.select("tr"):
            tds = row.select("td")
            if len(tds) >= 9:
                date = tds[0].get_text(strip=True)
                institution_net = parse_number(tds[5].get_text(strip=True))
                foreign_net = parse_number(tds[6].get_text(strip=True))
```

한 페이지에 20일치 데이터가 있고, `page` 파라미터를 올리면 과거 데이터를 가져올 수 있다. 30페이지면 약 600일치가 나온다.

### 개인 순매수는 직접 계산

네이버 증권은 개인 순매수를 별도로 제공하지 않는다. 하지만 주식시장에서 **순매수 = 순매도** 등식이 항상 성립하므로 역산할 수 있다.

```python
individual_net = -(foreign_net + institution_net)
```

### 네이버 vs pykrx 비교

| 항목 | pykrx (사망) | 네이버 크롤링 |
|------|-------------|-------------|
| OHLCV | ✅ → ❌ | ✅ (siseJson API) |
| 외국인 순매수 | ✅ → ❌ | ✅ (frgn.naver) |
| 기관 순매수 | ✅ → ❌ | ✅ (합계만) |
| 기관 세분화 | ✅ detail=True | ❌ 미제공 |
| 순매수 랭킹 | ✅ → ❌ | ❌ 별도 구현 필요 |
| 외국인 보유율 | ❌ | ✅ |
| Rate Limit | 없음 (스크래핑) | 없음 (0.3초 딜레이 권장) |
| 안정성 | ❌ KRX 구조 의존 | ✅ 네이버 안정적 |

네이버의 가장 큰 한계는 **기관 세분화가 안 된다**는 점이다. 연기금, 금융투자, 사모, 보험 등을 구분할 수 없다. 이건 KRX만 제공하는 데이터라서 pykrx가 정상화되거나 KRX가 공식 API를 만들기 전까지는 어쩔 수 없다.

---

## 수집 스크립트 작성

네이버 증권에서 10개 종목의 데이터를 한 번에 수집하는 스크립트를 만들었다.

```python
STOCKS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "373220": "LG에너지솔루션",
    "005380": "현대자동차",
    "035420": "NAVER",
    "068270": "셀트리온",
    "105560": "KB금융",
    "055550": "신한지주",
    "000270": "기아",
    "006400": "삼성SDI",
}
```

OHLCV 500일 + 투자자 30페이지(600일)를 수집해서 JSON으로 저장한다.

```
📊 삼성전자 (005930)
  OHLCV: 331일
  투자자: 600일
  ✅ stock_005930.json
```

JSON 구조는 이렇다.

```json
{
  "ticker": "005930",
  "name": "삼성전자",
  "trading_days": 331,
  "daily": [
    {
      "date": "2025-01-02",
      "open": 55000, "high": 55800, "low": 54200, "close": 55500,
      "volume": 18234567,
      "investors": { "foreign": 1234567, "institution": -567890, "individual": -666677 },
      "cumulative": { "foreign": 1234567, "institution": -567890, "individual": -666677 },
      "foreign_ratio": "49.56%"
    }
  ]
}
```

누적 순매수는 수집 시점에 미리 계산해서 저장한다. 프론트엔드에서 매번 계산하지 않아도 되게.

### KRX 데이터 갱신 시점

하나 중요한 점이 있다. **KRX 최종 데이터는 매일 18:00 KST 이후에 확정**된다. 장 마감(15:30)과 데이터 확정 사이에 2시간 반의 갭이 있다. 이 시간 동안은 데이터가 미확정 상태이므로 수집하면 안 된다.

cron으로 돌리려면 18:15 이후에 실행하는 게 안전하다.

```bash
# crontab -e
15 18 * * 1-5 cd /path/to/project && python3 scripts/collect_naver.py
```

---

## Next.js + lightweight-charts로 대시보드 구현

프론트엔드는 Next.js 16 + TypeScript + Tailwind CSS로 만들었다. 차트는 TradingView의 오픈소스 라이브러리인 lightweight-charts를 사용했다.

### 프로젝트 구조

```
stock_dashboard/
├── src/
│   ├── app/
│   │   ├── page.tsx              # 메인 (종목 수급 현황)
│   │   ├── ranking/page.tsx      # 순매수 랭킹
│   │   ├── leader/page.tsx       # 주도세력 분석
│   │   └── api/stocks/route.ts   # 데이터 서빙 API
│   ├── components/charts/        # lightweight-charts 컴포넌트
│   └── components/tables/        # @tanstack/react-table 테이블
├── public/data/                  # 수집된 JSON 파일
└── scripts/
    └── collect_naver.py          # 데이터 수집 스크립트
```

### API Route — 실제 데이터 서빙

`public/data/stock_005930.json` 같은 파일을 읽어서 API로 제공한다.

```typescript
// src/app/api/stocks/route.ts
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const filePath = path.join(process.cwd(), "public", "data", `stock_${code}.json`);
    const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    return NextResponse.json(data);
  }
  // 전체 종목 목록 반환 (요약)
}
```

### lightweight-charts Y축 포맷팅 삽질

lightweight-charts로 누적 순매수 차트를 만들었는데, Y축에 소수점 2자리까지 표시되는 문제가 있었다. 주식 수량은 정수인데 `1234567.00` 이런 식으로 나오니 보기 불편했다.

처음에는 `priceFormat`으로 해결하려 했다.

```typescript
const series = chart.addSeries(LineSeries, {
  priceFormat: { type: "price", precision: 0, minMove: 1 },
});
```

이것만으로는 Y축 눈금(tick mark)에는 적용이 안 됐다. **`localization.priceFormatter`를 써야** Y축 전체에 포맷이 적용된다.

```typescript
const chart = createChart(container, {
  localization: {
    priceFormatter: (price: number) => {
      if (Math.abs(price) >= 1000000) return `${(price / 10000).toFixed(0)}만`;
      if (Math.abs(price) >= 10000) return `${(price / 10000).toFixed(1)}만`;
      return price.toLocaleString();
    },
  },
});
```

이렇게 하면 Y축에 `-803만`, `+142만` 같은 한국식 단위로 표시된다.

### leftPriceScale 활성화

일별 순매수 차트에서 더 큰 문제가 있었다. `priceScaleId: "left"`로 시리즈를 추가했는데 Y축 자체가 안 보였다.

```typescript
const foreignSeries = chart.addSeries(HistogramSeries, {
  priceScaleId: "left",  // 왼쪽 스케일에 바인딩
});
```

원인은 leftPriceScale을 명시적으로 활성화하지 않아서였다.

```typescript
const chart = createChart(container, {
  rightPriceScale: { visible: false },
  leftPriceScale: {
    visible: true,  // 이게 빠져있었음
    borderColor: "#374151",
  },
});
```

lightweight-charts는 기본적으로 rightPriceScale만 보여준다. left를 쓰려면 `visible: true`를 명시해야 한다.

---

## 장중 0주 문제

대시보드를 띄워보니 상단 요약 카드에 "외국인 순매수 0주, 기관 순매수 0주"가 표시됐다.

원인은 단순했다. 장중에는 당일 수급 데이터가 아직 확정되지 않아서 0으로 들어온다. 18:00 이후에야 실제 수치가 반영된다.

해결: 데이터가 0인 당일 대신, 실제 수급 데이터가 있는 가장 최근 거래일을 찾아서 표시한다.

```typescript
const lastWithData = [...filteredDaily].reverse().find(
  (d) => d.investors.foreign !== 0 || d.investors.institution !== 0
);
const displayInvestors = lastWithData || last;
```

카드 레이블에 날짜도 같이 표시해서 언제 기준 데이터인지 명확하게 했다.

```
외국인 순매수 (2026-03-23)    기관 순매수 (2026-03-23)
-801.7만주                   -647.8만주
```

---

## 데이터 소스 비교 — 어디서 가져올 것인가

이번 삽질을 통해 한국 주식 수급 데이터 소스를 전수 조사하게 됐다. 결과를 정리하면 이렇다.

| 소스 | 방식 | 기관 세분화 | 실시간 | 안정성 | 비용 |
|------|------|-----------|--------|--------|------|
| pykrx | KRX 스크래핑 | ✅ | ❌ | ❌ 사망 | 무료 |
| 네이버 증권 | HTML 크롤링 | ❌ 합계만 | ❌ | ✅ | 무료 |
| FinanceDataReader | 네이버/KRX | ❌ | ❌ | △ | 무료 |
| KRX Data Marketplace | 공식 | ✅ | △ | ✅ | 유/무료 |
| HTS/MTS | 전용 프로그램 | ✅ | ✅ | ✅ | 무료 |
| judal.co.kr | 웹 크롤링 | ❌ | △ | ✅ | 무료 |

judal.co.kr도 조사해봤는데, 소외지수나 버핏초이스 같은 독자 지표는 있지만 투자자별 순매수 데이터는 제공하지 않았다. 보조 데이터 소스로는 괜찮지만 수급 분석의 대체는 불가능하다.

결론적으로 **무료로 프로그래밍 가능한 수급 데이터 소스는 네이버 증권 크롤링이 현재 가장 안정적**이다. 기관 세분화가 필요하면 pykrx 정상화를 기다리거나 KRX 공식 API를 모니터링하는 수밖에 없다.

---

## 실제 데이터에서 보이는 패턴

수집한 삼성전자 실제 데이터를 보면 블로그에서 설명한 수급 패턴이 정확히 드러난다.

```
날짜         종가      외국인        기관         개인
2026-03-18  208,500  +1,369,284  +4,424,253  -5,793,537
2026-03-19  200,500  -2,135,532  -1,121,429  +3,256,961
2026-03-20  199,400    -196,136  -7,302,259  +7,498,395
2026-03-23  186,300  -8,017,053  -6,477,862 +14,494,915
```

3월 18일 이후 외국인·기관이 대규모 순매도를 하면서 주가가 208,500원 → 186,300원으로 급락했다. 개인은 이 물량을 받아내고 있다. 전형적인 "외국인·기관 매도 → 개인 매수" 패턴이다.

누적 순매수를 보면 더 명확하다. 외국인 누적 포지션이 -19,889,155에서 -30,237,876으로 급격히 하락했다. 6거래일 만에 1천만 주 이상을 순매도한 셈이다.

---

## 주의사항과 한계

### 네이버 크롤링의 리스크

네이버 증권은 공식 API가 아니다. 언제든 HTML 구조가 바뀔 수 있고, 그러면 크롤링 코드가 깨진다. pykrx가 KRX 의존으로 죽은 것과 같은 패턴이 반복될 수 있다.

방어 전략:
- 수집 결과를 검증하는 로직 추가 (빈 DataFrame 체크)
- 수집 실패 시 알림 발송
- 데이터를 DB에 캐싱해서 크롤링 실패해도 과거 데이터는 사용 가능하게

### 기관 세분화 불가

네이버 증권은 기관을 하나의 합계로만 제공한다. 연기금이 사는 건지 금융투자(증권사)가 사는 건지 구분이 안 된다. 수급 분석에서 주도세력을 세밀하게 판별하려면 이 구분이 중요한데, 현재로서는 한계다.

### 데이터 갱신 타이밍

무료 소스로는 장중 실시간 수급 데이터를 가져올 수 없다. 장 마감 후 18:00 KST 이후에 확정된 데이터만 수집 가능하다. 실시간이 필요하면 HTS/MTS를 써야 한다.

---

## 결론

pykrx가 KRX 사이트 구조 변경 + pandas 2.x 호환 문제로 사실상 사망한 상태에서, 네이버 증권 크롤링이 현실적인 대안이었다. 기관 세분화를 포기하는 대신 외국인/기관/개인 3주체 순매수와 누적 추이를 안정적으로 수집할 수 있었다.

lightweight-charts는 금융 차트에 최적화된 가벼운 라이브러리지만, Y축 포맷팅에서 `localization.priceFormatter`를 써야 한다는 점, `leftPriceScale`을 명시적으로 활성화해야 한다는 점은 문서를 꼼꼼히 읽지 않으면 놓치기 쉽다.

한국 주식 데이터 생태계가 KRX 공식 API 없이 스크래핑에 의존하는 구조라서, 이런 삽질이 반복될 수밖에 없는 것 같다. KRX가 공식 REST API를 제공해주면 이 문제가 근본적으로 해결될 텐데, 당분간은 네이버 크롤링 + 방어 코드가 최선이다.
