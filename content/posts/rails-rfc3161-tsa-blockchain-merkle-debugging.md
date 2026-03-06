---
title: "RFC 3161 TSA 타임스탬프 + 블록체인 Merkle 앵커링: Rails에서 삽질 기록"
date: 2026-02-06
draft: false
tags: ["Rails", "Ruby", "OpenSSL", "블록체인", "RFC 3161", "TSA", "Merkle Tree", "디버깅", "마이그레이션"]
description: "Rails 8 + Ruby 4.0 환경에서 RFC 3161 TSA 타임스탬프와 블록체인 Merkle Tree 앵커링을 구현하면서 만난 삽질들. OpenSSL API 변경, multi-database 마이그레이션 충돌, 테스트 환경 꼬임까지."
cover:
  image: "/images/og/rails-rfc3161-tsa-blockchain-merkle-debugging.png"
  alt: "Rails Rfc3161 Tsa Blockchain Merkle Debugging"
  hidden: true
---

전자계약 보관 시스템에 **법적 증거력**을 부여하기 위해 두 가지를 동시에 구현해야 했다:

1. **블록체인 Merkle Tree 앵커링** — 계약 해시들을 모아 Merkle Root를 L2 체인에 기록
2. **RFC 3161 TSA 타임스탬프** — 신뢰할 수 있는 제3자 시간 증명

간단해 보였는데, 삽질의 연속이었다.

---

## 1. RFC 3161 TSA란?

RFC 3161은 **Time-Stamp Authority(TSA)** 프로토콜로, 특정 데이터가 특정 시점에 존재했음을 제3자가 증명해주는 표준이다.

흐름은 간단하다:

```
클라이언트 → SHA-256 해시 생성 → TSA 서버에 요청 → 서명된 타임스탬프 토큰 수신
```

무료 TSA 서버들:
- **DigiCert**: `http://timestamp.digicert.com` (가장 안정적)
- **Sectigo**: `http://timestamp.sectigo.com` (15초 rate limit)
- **Entrust**: `http://timestamp.entrust.net/TSS/RFC3161sha2TS`

Ruby에는 `OpenSSL::Timestamp` 모듈이 내장되어 있어서, 외부 gem 없이 구현 가능하다.

---

## 2. 구현 구조

### TSA 서비스

```ruby
class TsaTimestampService
  TSA_SERVERS = {
    digicert: "http://timestamp.digicert.com",
    sectigo:  "http://timestamp.sectigo.com",
    entrust:  "http://timestamp.entrust.net/TSS/RFC3161sha2TS"
  }.freeze

  def stamp(data_hash)
    digest = [data_hash].pack("H*")
    req = build_timestamp_request(digest)
    response_der = send_tsa_request(req.to_der)
    parse_tsa_response(response_der, digest)
  end
end
```

### Merkle + TSA 앵커링 흐름

```
1. 미앵커링 Merkle leaf들 수집
2. Merkle Tree 구성 → root 해시 계산
3. 블록체인에 root 해시 기록 (tx_hash 수신)
4. TSA 서버에 root 해시로 타임스탬프 요청
5. batch에 tx_hash + TSA 토큰 모두 저장
```

TSA 실패는 **non-fatal** — 블록체인 기록이 주 증거이고, TSA는 보조 증거다.

---

## 3. 삽질 1: Ruby 4.0의 OpenSSL::Timestamp API 변경

### 문제

```ruby
# 이렇게 작성했다
def verify(token_der, data_hash)
  token = OpenSSL::Timestamp::Token.new(token_der)
  token.message_imprint == digest
end
```

```
NameError: uninitialized constant OpenSSL::Timestamp::Token
```

### 원인

Ruby 4.0 (OpenSSL 3.x 기반)에서는 `OpenSSL::Timestamp::Token` 클래스가 **존재하지 않는다**.

사용 가능한 클래스:
- `OpenSSL::Timestamp::Request` — 요청 생성
- `OpenSSL::Timestamp::Response` — 응답 파싱
- `OpenSSL::Timestamp::TokenInfo` — 토큰 정보 (Response에서 추출)
- `OpenSSL::Timestamp::Factory` — 테스트용 자체 서명 응답 생성

`Token`은 없다. `Response`에서 `token_info`를 꺼내야 한다.

### 수정

```ruby
def verify(token_der, data_hash)
  digest = [data_hash].pack("H*")
  resp = OpenSSL::Timestamp::Response.new(token_der)
  token_info = resp.token_info
  token_info.message_imprint == digest
rescue OpenSSL::Timestamp::TimestampError, StandardError => e
  false
end
```

---

## 4. 삽질 2: `cert_requested` vs `cert_requested?`

### 문제

```ruby
# 테스트에서
assert req.cert_requested
```

```
NoMethodError: undefined method 'cert_requested' for OpenSSL::Timestamp::Request
```

### 원인

Ruby 4.0의 `OpenSSL::Timestamp::Request`에서:
- **쓰기**: `req.cert_requested = true` (setter, `=` 사용)
- **읽기**: `req.cert_requested?` (predicate, `?` 사용)

`cert_requested` (물음표 없이)는 존재하지 않는다. Ruby의 Boolean accessor 네이밍 컨벤션을 엄격하게 따른 결과.

### 수정

```ruby
assert req.cert_requested?  # ? 추가
```

---

## 5. 삽질 3: Rails 8 Multi-Database 마이그레이션 충돌

### 상황

TSA 컬럼 4개를 추가하는 마이그레이션을 만들었다:

```ruby
class AddTsaToBlockchainBatches < ActiveRecord::Migration[8.0]
  def change
    add_column :blockchain_batches, :tsa_token, :binary
    add_column :blockchain_batches, :tsa_timestamp, :datetime
    add_column :blockchain_batches, :tsa_provider, :string
    add_column :blockchain_batches, :tsa_serial, :string
  end
end
```

### 문제

```bash
$ bin/rails db:migrate
```

```
PG::DuplicateObject: ERROR: constraint "fk_rails_xxxxx" already exists
```

마이그레이션이 엉뚱한 에러를 뱉었다. TSA 컬럼과는 무관한 foreign key 충돌.

### 원인

Rails 8의 **Solid Stack** (Cache, Queue, Cable) 때문이다. `db:migrate`는 4개 DB를 모두 마이그레이트하려고 시도하는데, Solid Queue/Cable/Cache의 마이그레이션이 이미 적용된 foreign key를 다시 만들려고 해서 충돌.

```
primary:  메인 데이터          ← 여기만 건드리면 됨
cache:    Solid Cache          ← 건드리면 안 됨
queue:    Solid Queue          ← 건드리면 안 됨
cable:    Solid Cable          ← 건드리면 안 됨
```

### 수정

```bash
# primary DB만 특정 마이그레이션 적용
bin/rails db:migrate:up:primary VERSION=20260306100000
```

핵심: Multi-database 앱에서는 `db:migrate` 대신 **`db:migrate:up:primary`**로 특정 DB를 지정해야 한다.

---

## 6. 삽질 4: 테스트 DB 환경 꼬임

### 문제

마이그레이션 후 테스트를 돌렸더니:

```
ActiveRecord::EnvironmentMismatchError:
You are attempting to modify a database that was last run in `development`
environment. You are running in `test` environment.
```

### 원인

테스트 DB의 environment 태그가 `development`로 되어 있었다. 개발 환경에서 마이그레이션을 돌리다가 테스트 DB까지 건드린 결과.

### 수정 과정

```bash
# 1. 테스트 환경 설정
RAILS_ENV=test bin/rails db:environment:set

# 2. primary 스키마 로드
RAILS_ENV=test bin/rails db:schema:load:primary

# 3. TSA 마이그레이션 적용
RAILS_ENV=test bin/rails db:migrate:up:primary VERSION=20260306100000
```

여기서 끝이 아니었다. Solid Queue/Cable/Cache의 테스트 DB도 foreign key 충돌:

```bash
# Solid 3개 DB를 drop & recreate
RAILS_ENV=test bin/rails db:drop:queue db:drop:cable db:drop:cache
RAILS_ENV=test bin/rails db:create:queue db:create:cable db:create:cache
RAILS_ENV=test bin/rails db:migrate
```

이렇게 해서 테스트 환경이 정상화됐다.

---

## 7. 삽질 5: 테스트에서 self-signed TSA 만들기

실제 TSA 서버에 요청하면 테스트가 느려지고 불안정해진다. `OpenSSL::Timestamp::Factory`로 자체 서명 TSA 응답을 만들 수 있다:

```ruby
def build_self_signed_tsa_response(data_hash)
  factory = OpenSSL::Timestamp::Factory.new
  factory.gen_time = Time.now
  factory.serial_number = 1
  factory.allowed_digests = ["sha256"]

  key = OpenSSL::PKey::RSA.new(2048)
  cert = OpenSSL::X509::Certificate.new
  # ... 인증서 설정 ...
  cert.add_extension(
    ef.create_extension("extendedKeyUsage", "timeStamping", true)
  )
  cert.sign(key, "SHA256")

  req = OpenSSL::Timestamp::Request.new
  req.algorithm = "SHA256"
  req.message_imprint = [data_hash].pack("H*")

  resp = factory.create_timestamp(key, cert, req)
  resp.to_der
end
```

`extendedKeyUsage`에 `timeStamping`을 넣지 않으면 Factory가 거부한다. 이것도 알아내는 데 시간이 걸렸다.

---

## 8. 전체 아키텍처 정리

```
계약 서명
  ↓
SHA-256 해시 생성
  ↓
MerkleLeaf 생성 (unanchored)
  ↓
Daily Cron Job (AnchorService.call)
  ↓
┌─────────────────────────────────┐
│ 1. Merkle Tree 구성             │
│ 2. Root → 블록체인 기록 (tx_hash) │
│ 3. Root → TSA 타임스탬프 (선택적)  │
│ 4. Batch + Leaves 업데이트       │
└─────────────────────────────────┘
  ↓
Evidence Package (ASiC-E)
├── document.pdf
├── META-INF/manifest.xml
├── META-INF/blockchain-proof.json
└── META-INF/timestamp.tst        ← TSA 토큰
```

- **블록체인**: 데이터 무결성 + 존재 증명 (주 증거)
- **TSA**: 제3자 시간 증명 (보조 증거)
- **ASiC-E**: EU eIDAS 호환 증거 패키지

---

## 교훈

1. **Ruby 4.0 OpenSSL API를 반드시 확인하라** — 구버전 문서나 예제가 동작하지 않는다. `Token` 클래스는 없고, predicate 메서드에 `?`가 필요하다.

2. **Rails 8 multi-database는 마이그레이션이 까다롭다** — `db:migrate` 대신 `db:migrate:up:primary VERSION=xxx`로 특정 DB만 건드려라. Solid Stack DB를 건드리면 foreign key 충돌이 발생한다.

3. **테스트 환경은 별도로 관리하라** — `RAILS_ENV=test`를 빼먹으면 environment 태그가 꼬인다. multi-database 앱에서는 4개 DB 모두 상태를 확인해야 한다.

4. **TSA 실패는 non-fatal로 처리하라** — TSA 서버가 다운되어도 블록체인 앵커링은 성공해야 한다. `rescue`로 감싸고 로그만 남겨라.

5. **무료 TSA 서버는 DigiCert가 가장 안정적이다** — Sectigo는 15초 rate limit이 있고, Entrust는 가끔 느리다. fallback 체인을 구성하는 게 좋다.

6. **self-signed TSA로 테스트하라** — `OpenSSL::Timestamp::Factory`를 쓰면 외부 의존성 없이 round-trip 테스트가 가능하다. `extendedKeyUsage: timeStamping` 잊지 마라.
