---
title: "5개 암호화폐 거래소 API 연동하면서 겪은 삽질 모음"
date: 2025-12-06
draft: false
tags: ["Ruby", "Rails", "API", "암호화폐", "디버깅", "Faraday", "Circuit Breaker"]
description: "Binance, Bybit, OKX, Bitget, HyperLiquid 5개 거래소 펀딩레이트 API를 Rails에서 연동하면서 마주친 문제들과 해결 방법. 문서와 다른 실제 API 동작, 에러 처리 패턴, Faraday 재시도 설정까지."
cover:
  image: "/images/og/crypto-exchange-api-integration-lessons.png"
  alt: "Crypto Exchange Api Integration Lessons"
  hidden: true
---

Ruby on Rails로 여러 암호화폐 거래소의 펀딩레이트(funding rate)를 수집하는 기능을 만들면서 겪은 문제들을 정리한다. 5개 거래소를 붙이면서 각 거래소마다 API 동작 방식이 달랐고, 공식 문서와 실제 동작이 다른 경우도 있었다.

---

## 거래소 API의 공통 기반 클라이언트 만들기

여러 거래소를 붙이기 전에 공통 HTTP 클라이언트를 먼저 만들었다. Faraday를 사용했고, 재시도와 Circuit Breaker를 여기에 몰아 넣었다.

### Faraday + faraday-retry 설정

```ruby
# Gemfile
gem "faraday"
gem "faraday-retry"
```

```ruby
def connection
  @connection ||= Faraday.new(url: base_url) do |f|
    f.request :retry, {
      max: 3,
      interval: 0.5,
      backoff_factor: 2,
      interval_randomness: 0.5,  # jitter
      retry_statuses: [429, 503, 504],
      retry_block: -> (env, options, retries, exc) {
        Rails.logger.warn("[#{exchange_name}] Retrying... #{retries} left. Status: #{env.status}")
      }
    }
    f.adapter Faraday.default_adapter
    f.options.timeout = 10
    f.options.open_timeout = 5
  end
end
```

`backoff_factor: 2`와 `interval_randomness: 0.5`(jitter)를 조합하면 재시도 간격이 0.5초 → 1초 → 2초로 지수 증가하면서 약간의 무작위성이 붙는다. 거래소 API가 Rate Limit(429)을 돌려줄 때 모든 클라이언트가 동시에 재시도하는 "thundering herd" 문제를 막아준다.

### Circuit Breaker 직접 구현

외부 라이브러리 없이 간단하게 만들었다. 연속 5회 실패하면 60초 동안 해당 거래소 요청을 차단한다.

```ruby
CIRCUIT_BREAKER = {}

def circuit_open?(exchange)
  state = CIRCUIT_BREAKER[exchange]
  return false unless state
  return false if Time.now > state[:reset_at]
  true
end

def record_failure(exchange)
  state = CIRCUIT_BREAKER[exchange] ||= { failures: 0, reset_at: nil }
  state[:failures] += 1
  if state[:failures] >= 5
    state[:reset_at] = Time.now + 60
    Rails.logger.error("[#{exchange}] Circuit opened. Blocking for 60s")
  end
end

def record_success(exchange)
  CIRCUIT_BREAKER.delete(exchange)
end
```

응답 처리에서 HTTP 상태 코드별로 에러를 구분했다:

```ruby
case response.status
when 429
  raise RateLimitError, "Rate limit exceeded"
when 401, 403
  raise AuthenticationError, "Invalid credentials"
when 404
  raise NotFoundError, "Endpoint not found: #{url}"
when 500..599
  raise ServerError, "Server error: #{response.status}"
end
```

---

## OKX: instType 파라미터가 사라졌다

### 문제

공식 문서에는 펀딩레이트 조회 시 `instType=SWAP`으로 전체 목록을 가져올 수 있다고 나와 있었다.

```
GET /api/v5/public/funding-rate?instType=SWAP
```

실제로 호출하면:

```json
{"code":"51000","data":[],"msg":"Parameter instId can not be empty"}
```

`instId`가 필수 파라미터인데 문서에 빠져 있었다.

### 해결

심볼별로 개별 호출하는 방식으로 바꿨다. BTC, ETH, SOL 같은 주요 심볼만 조회하도록 제한했다.

```ruby
SYMBOLS = %w[BTC ETH SOL BNB XRP]

def fetch_funding_rates
  results = {}
  SYMBOLS.each do |sym|
    response = connection.get("/api/v5/public/funding-rate", {
      instId: "#{sym}-USDT-SWAP"
    })
    data = JSON.parse(response.body)
    next unless data["code"] == "0" && data["data"].present?

    item = data["data"].first
    results[sym] = {
      symbol: sym,
      funding_rate: item["fundingRate"].to_f,
      next_funding_time: Time.at(item["nextFundingTime"].to_i / 1000)
    }
  rescue => e
    Rails.logger.warn("[OKX] Failed for #{sym}: #{e.message}")
    # 한 심볼 실패해도 나머지 계속 진행
  end
  results
end
```

배치 조회가 안 되니 심볼 수만큼 HTTP 요청이 나간다. 5개 심볼이면 5번의 요청. 나쁘진 않지만 확장하면 문제가 될 수 있다.

---

## Bitget: 없는 엔드포인트를 호출하고 있었다

### 문제

펀딩레이트 조회용으로 `/current-funding-rate` 엔드포인트를 쓰고 있었는데:

```json
{"code":"40009","msg":"Request URL NOT FOUND"}
```

Bitget API v2로 업그레이드되면서 엔드포인트가 바뀐 것이었다.

### 해결

`/tickers?productType=USDT-FUTURES`에 펀딩레이트 정보가 포함되어 있었다.

```ruby
def fetch_funding_rates
  response = connection.get("/api/v2/mix/market/tickers", {
    productType: "USDT-FUTURES"
  })
  data = JSON.parse(response.body)

  results = {}
  data["data"].each do |ticker|
    sym = ticker["symbol"].gsub("USDT", "").gsub("PERP", "").strip
    next unless ticker["fundingRate"]

    results[sym] = {
      symbol: sym,
      funding_rate: ticker["fundingRate"].to_f,
      mark_price: ticker["markPrice"]&.to_f  # nil 허용
    }
  end
  results
end
```

`markPrice` 필드가 없는 티커도 있어서 `&.to_f`로 nil-safe하게 처리했다.

---

## HyperLiquid: REST가 아니라 POST + JSON Body

HyperLiquid는 다른 거래소와 API 방식이 다르다. GET 요청이 아니라 POST로 JSON body를 보내야 한다.

```ruby
def fetch_funding_rates
  response = connection.post("/info") do |req|
    req.headers["Content-Type"] = "application/json"
    req.body = { type: "metaAndAssetCtxs" }.to_json
  end

  meta, asset_ctxs = JSON.parse(response.body)
  universe = meta["universe"]

  results = {}
  universe.each_with_index do |asset, idx|
    ctx = asset_ctxs[idx]
    next unless ctx["funding"]

    sym = asset["name"]
    results[sym] = {
      symbol: sym,
      # HyperLiquid는 hourly rate → 8시간 rate로 변환
      funding_rate: ctx["funding"].to_f * 8,
      open_interest: ctx["openInterest"].to_f
    }
  end
  results
end
```

### hourly rate 변환

다른 거래소(Binance, Bybit 등)는 8시간 단위 펀딩레이트를 반환한다. HyperLiquid는 1시간 단위(hourly)로 반환하기 때문에 비교하려면 `* 8`을 해줘야 한다. 이 부분을 놓치면 스프레드 계산이 8배 틀린다.

---

## Binance 응답이 Array인데 Hash처럼 처리했다

간단한 실수였지만 원인 찾는 데 시간이 걸렸다.

### 문제

거래소 API를 테스트하는 스크립트를 짜면서 응답 파싱에 버그가 있었다.

```ruby
data = JSON.parse(response.body)
if data.key?("error")  # ← NoMethodError: undefined method 'key?' for Array
```

Binance의 `/fapi/v1/premiumIndex` 응답은 Array다. Hash가 아니다.

```json
[
  {"symbol":"BTCUSDT","markPrice":"...","lastFundingRate":"..."},
  ...
]
```

### 해결

```ruby
data = JSON.parse(response.body)
if data.is_a?(Hash) && data.key?("error")
  # 에러 처리
end
```

타입 체크를 먼저 하거나, 처음부터 Array/Hash 응답 형태를 파악하고 짜야 한다.

---

## Foundry 설치와 OpenZeppelin 의존성 설정

Rails API 외에 스마트 컨트랙트도 작업했다. Solidity 개발 환경 설정에서 몇 가지 걸렸다.

### forge install --no-commit 플래그 제거됨

오래된 튜토리얼에는 이렇게 나와 있다:

```bash
forge install OpenZeppelin/openzeppelin-contracts --no-commit
```

최신 Foundry에서는 `--no-commit` 플래그가 없어졌다. 그냥 쓰면 된다:

```bash
forge install OpenZeppelin/openzeppelin-contracts
```

단, `forge install`은 git 저장소 안에서만 실행된다. `git init`을 먼저 해야 한다.

### remappings 설정

OpenZeppelin을 설치한 후 `foundry.toml`에 remappings을 추가해야 `import` 구문이 동작한다.

```toml
# foundry.toml
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
remappings = [
  "@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/"
]
```

```solidity
// 이제 이렇게 import 가능
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
```

### src/ 폴더 구조

Foundry는 기본적으로 `src/` 폴더에서 Solidity 파일을 찾는다. 루트에 `.sol` 파일을 두면 빌드가 안 된다.

```
contracts/
├── src/           ← 여기에 .sol 파일
│   └── MyContract.sol
├── script/
│   └── Deploy.s.sol
├── test/
├── lib/
│   └── openzeppelin-contracts/
└── foundry.toml
```

처음에 루트에 `Contract.sol`을 두고 `forge build`가 왜 안 되는지 한참 봤다.

---

## 테스트 스크립트로 실제 API 검증

gem을 설치하지 않고 표준 라이브러리만으로 빠르게 검증하고 싶을 때 이런 패턴을 쓴다:

```ruby
#!/usr/bin/env ruby
require "net/http"
require "json"
require "uri"

def fetch(url, method: :get, body: nil, headers: {})
  uri = URI(url)
  http = Net::HTTP.new(uri.host, uri.port)
  http.use_ssl = uri.scheme == "https"
  http.open_timeout = 5
  http.read_timeout = 10

  req = method == :post ? Net::HTTP::Post.new(uri) : Net::HTTP::Get.new(uri)
  headers.each { |k, v| req[k] = v }
  req.body = body.to_json if body
  req["Content-Type"] = "application/json" if body

  res = http.request(req)
  JSON.parse(res.body)
rescue => e
  { "error" => e.message }
end

# 사용
data = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
puts data.is_a?(Array) ? data.first : data
```

Rails 환경을 띄우지 않아도 거래소 API 연동을 빠르게 확인할 수 있다.

---

## Render 배포 시 API-only Rails 앱 설정

Render에 Rails API 서버를 배포할 때 빌드 스크립트에서 주의할 점이 있다.

### assets:precompile 제거

일반 Rails 앱 배포 예제를 그대로 쓰면 이런 빌드 스크립트가 된다:

```bash
bundle install
bundle exec rails assets:precompile
bundle exec rails assets:clean
bundle exec rails db:migrate
```

API-only 앱은 Asset Pipeline을 안 쓴다. `assets:precompile`을 실행하면 Sprockets 관련 에러가 나거나 불필요한 시간을 낭비한다.

```bash
#!/usr/bin/env bash
set -o errexit

bundle install
bundle exec rails db:migrate
```

이걸로 충분하다.

### render.yaml Blueprint

Render에서 PostgreSQL과 웹 서비스를 함께 구성할 때:

```yaml
databases:
  - name: myapp-db
    databaseName: myapp_production
    user: myapp

services:
  - type: web
    name: myapp-api
    runtime: ruby
    buildCommand: "./bin/render-build.sh"
    startCommand: "bin/rails server -p $PORT -e production"
    healthCheckPath: /up
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: myapp-db
          property: connectionString
      - key: RAILS_MASTER_KEY
        sync: false  # 대시보드에서 직접 입력
```

`RAILS_MASTER_KEY`는 `sync: false`로 두고 Render 대시보드에서 직접 입력해야 한다. `config/master.key` 파일을 git에 올리면 안 되니까.

---

## 정리

이번 작업에서 가장 많이 걸린 부분:

1. **API 문서 불일치** - OKX, Bitget 모두 실제 동작이 문서와 달랐다. 공식 문서보다 실제 요청/응답을 직접 확인하는 게 빠르다.

2. **응답 타입 확인** - 거래소마다 Array로 오기도 하고 Hash로 오기도 한다. 파싱 전에 `is_a?`로 타입을 확인하거나, 방어적으로 작성해야 한다.

3. **Rate 단위 통일** - HyperLiquid hourly rate를 다른 거래소의 8시간 rate와 비교하려면 변환이 필요하다. 단위가 다른 숫자를 그냥 비교하면 틀린 결과가 나온다.

4. **Foundry 프로젝트 구조** - `src/` 폴더, `git init` 선행, remappings 설정. 공식 문서대로만 하면 잘 되는데 오래된 튜토리얼을 보다가 헤맸다.

5. **API-only Rails에서 assets 관련 명령 제거** - 당연한 것 같지만 템플릿 그대로 복붙하다 실수하기 쉽다.
