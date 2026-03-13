---
title: "Lessons from Integrating 5 Cryptocurrency Exchange APIs"
date: 2025-12-06
draft: false
tags: ["Ruby", "Rails", "API", "Cryptocurrency", "Debugging", "Faraday", "Circuit Breaker"]
description: "Problems and solutions encountered while integrating funding rate APIs from Binance, Bybit, OKX, Bitget, and HyperLiquid in Rails. API docs vs actual behavior, error handling patterns, and Faraday retry configuration."
cover:
  image: "/images/og/crypto-exchange-api-integration-lessons.png"
  alt: "Crypto Exchange Api Integration Lessons"
  hidden: true
---

Notes on the problems encountered while building a funding rate collection feature from multiple cryptocurrency exchanges in Ruby on Rails. Each of the 5 exchanges had different API behavior, and in some cases the official documentation didn't match the actual behavior.

---

## Building a Common Base Client for Exchange APIs

Before connecting multiple exchanges, I built a common HTTP client first. Used Faraday with retry and Circuit Breaker logic centralized here.

### Faraday + faraday-retry Configuration

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

Combining `backoff_factor: 2` with `interval_randomness: 0.5` (jitter) gives retry intervals that exponentially increase from 0.5s -> 1s -> 2s with some randomness added. This prevents the "thundering herd" problem where all clients retry simultaneously when an exchange API returns a Rate Limit (429).

### Custom Circuit Breaker Implementation

Built a simple one without external libraries. After 5 consecutive failures, it blocks requests to that exchange for 60 seconds.

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

Error handling differentiated by HTTP status code:

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

## OKX: The instType Parameter Was Gone

### Problem

The official docs said you could get the full list of funding rates with `instType=SWAP`.

```
GET /api/v5/public/funding-rate?instType=SWAP
```

The actual response:

```json
{"code":"51000","data":[],"msg":"Parameter instId can not be empty"}
```

`instId` was a required parameter that was missing from the docs.

### Solution

Switched to making individual calls per symbol. Limited to major symbols like BTC, ETH, SOL.

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
    # Continue with remaining symbols even if one fails
  end
  results
end
```

Without batch queries, you need as many HTTP requests as symbols. 5 symbols means 5 requests. Not bad, but could be an issue at scale.

---

## Bitget: Was Calling a Non-Existent Endpoint

### Problem

Was using the `/current-funding-rate` endpoint for funding rate queries:

```json
{"code":"40009","msg":"Request URL NOT FOUND"}
```

The endpoint had changed when Bitget upgraded to API v2.

### Solution

The `/tickers?productType=USDT-FUTURES` endpoint included funding rate information.

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
      mark_price: ticker["markPrice"]&.to_f  # allow nil
    }
  end
  results
end
```

Some tickers don't have a `markPrice` field, so handled it nil-safe with `&.to_f`.

---

## HyperLiquid: Not REST but POST + JSON Body

HyperLiquid's API works differently from other exchanges. Instead of GET requests, you send POST with a JSON body.

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
      # HyperLiquid returns hourly rate -> convert to 8-hour rate
      funding_rate: ctx["funding"].to_f * 8,
      open_interest: ctx["openInterest"].to_f
    }
  end
  results
end
```

### Hourly Rate Conversion

Other exchanges (Binance, Bybit, etc.) return 8-hour funding rates. HyperLiquid returns hourly rates, so you need to multiply by 8 for comparison. Missing this makes your spread calculations off by 8x.

---

## Binance Response Was an Array but Treated as Hash

A simple mistake, but took time to find the cause.

### Problem

There was a parsing bug in the exchange API testing script.

```ruby
data = JSON.parse(response.body)
if data.key?("error")  # <- NoMethodError: undefined method 'key?' for Array
```

Binance's `/fapi/v1/premiumIndex` response is an Array, not a Hash.

```json
[
  {"symbol":"BTCUSDT","markPrice":"...","lastFundingRate":"..."},
  ...
]
```

### Solution

```ruby
data = JSON.parse(response.body)
if data.is_a?(Hash) && data.key?("error")
  # error handling
end
```

Check the type first, or understand the Array/Hash response format from the start.

---

## Foundry Installation and OpenZeppelin Dependency Setup

Besides the Rails API, I also worked on smart contracts. Ran into a few issues with Solidity development environment setup.

### forge install --no-commit Flag Removed

Older tutorials show this:

```bash
forge install OpenZeppelin/openzeppelin-contracts --no-commit
```

In the latest Foundry, the `--no-commit` flag has been removed. Just use it without:

```bash
forge install OpenZeppelin/openzeppelin-contracts
```

Note that `forge install` only works inside a git repository. You need to `git init` first.

### Remappings Configuration

After installing OpenZeppelin, you need to add remappings to `foundry.toml` for `import` statements to work.

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
// Now you can import like this
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
```

### src/ Folder Structure

Foundry looks for Solidity files in the `src/` folder by default. Placing `.sol` files at the root won't build.

```
contracts/
├── src/           <- put .sol files here
│   └── MyContract.sol
├── script/
│   └── Deploy.s.sol
├── test/
├── lib/
│   └── openzeppelin-contracts/
└── foundry.toml
```

I initially put `Contract.sol` at the root and spent a while wondering why `forge build` wasn't working.

---

## Verifying Actual APIs with Test Scripts

When you want to quickly verify without installing gems, using only the standard library:

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

# Usage
data = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
puts data.is_a?(Array) ? data.first : data
```

You can quickly verify exchange API integration without spinning up the Rails environment.

---

## API-Only Rails App Configuration for Render Deploy

Things to watch out for in the build script when deploying a Rails API server to Render.

### Remove assets:precompile

Using the standard Rails app deploy example gives you this build script:

```bash
bundle install
bundle exec rails assets:precompile
bundle exec rails assets:clean
bundle exec rails db:migrate
```

API-only apps don't use the Asset Pipeline. Running `assets:precompile` causes Sprockets errors or wastes time.

```bash
#!/usr/bin/env bash
set -o errexit

bundle install
bundle exec rails db:migrate
```

This is sufficient.

### render.yaml Blueprint

When configuring PostgreSQL and web service together on Render:

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
        sync: false  # enter directly in dashboard
```

`RAILS_MASTER_KEY` should be set to `sync: false` and entered directly in the Render dashboard. You shouldn't commit the `config/master.key` file to git.

---

## Summary

The biggest time sinks in this work:

1. **API documentation mismatch** -- Both OKX and Bitget had actual behavior that differed from docs. Directly checking actual requests/responses is faster than trusting official docs.

2. **Response type verification** -- Exchanges return Arrays or Hashes inconsistently. Check the type with `is_a?` before parsing, or write defensively.

3. **Rate unit normalization** -- Converting HyperLiquid's hourly rate to match other exchanges' 8-hour rate. Comparing numbers with different units gives wrong results.

4. **Foundry project structure** -- `src/` folder, `git init` prerequisite, remappings configuration. Works fine following official docs, but got confused by outdated tutorials.

5. **Remove asset-related commands from API-only Rails** -- Seems obvious, but easy to miss when copy-pasting templates.
