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
categories: ["Flutter", "Rails"]
---

전자계약 보관 시스템에 **법적 증거력**을 부여하기 위해 두 가지를 동시에 구현해야 했다:

1. **블록체인 Merkle Tree 앵커링** — 계약 해시들을 모아 Merkle Root를 L2 체인에 기록
2. **RFC 3161 TSA 타임스탬프** — 신뢰할 수 있는 제3자 시간 증명

간단해 보였는데, 삽질의 연속이었다. 각 문제를 해결하는 데 예상보다 훨씬 많은 시간이 걸렸고, 특히 Ruby 4.0의 API 변경과 Rails 8의 멀티 데이터베이스 동작이 예상치 못한 방식으로 얽혔다.

---

## 1. RFC 3161 TSA란?

RFC 3161은 **Time-Stamp Authority(TSA)** 프로토콜로, 특정 데이터가 특정 시점에 존재했음을 제3자가 증명해주는 국제 표준(RFC 3161, RFC 5816로 업데이트)이다. 법적 맥락에서는 "이 문서가 이 날짜에 존재했음"을 공인 제3자가 서명으로 보증한다는 의미다.

흐름은 간단하다:

```
클라이언트 → SHA-256 해시 생성 → TSA 서버에 요청 → 서명된 타임스탬프 토큰 수신
```

TSA 서버는 요청을 받아 자신의 개인키로 서명한 **TimeStampToken(TST)**을 DER 인코딩으로 반환한다. 이 토큰에는 해시값, 타임스탬프, TSA의 인증서 체인이 포함되어 있어 누구든지 검증할 수 있다.

무료 TSA 서버들:
- **DigiCert**: `http://timestamp.digicert.com` (가장 안정적, 권장)
- **Sectigo**: `http://timestamp.sectigo.com` (15초 rate limit 있음)
- **Entrust**: `http://timestamp.entrust.net/TSS/RFC3161sha2TS` (가끔 느림)

Ruby에는 `OpenSSL::Timestamp` 모듈이 내장되어 있어서, 외부 gem 없이 구현 가능하다. 다만 Ruby 버전에 따라 API가 달라지므로 주의가 필요하다.

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

  private

  def build_timestamp_request(digest)
    req = OpenSSL::Timestamp::Request.new
    req.algorithm = "SHA256"
    req.message_imprint = digest
    req.cert_requested = true
    req.nonce = OpenSSL::BN.rand(64)
    req
  end

  def send_tsa_request(request_der)
    TSA_SERVERS.each do |provider, url|
      response = try_tsa_server(url, request_der)
      return response if response
    rescue => e
      Rails.logger.warn "TSA #{provider} failed: #{e.message}"
    end
    nil
  end

  def try_tsa_server(url, request_der)
    uri = URI.parse(url)
    http = Net::HTTP.new(uri.host, uri.port)
    http.open_timeout = 10
    http.read_timeout = 30
    req = Net::HTTP::Post.new(uri.path.presence || "/")
    req["Content-Type"] = "application/timestamp-query"
    req.body = request_der
    response = http.request(req)
    response.body if response.is_a?(Net::HTTPSuccess)
  end
end
```

### Merkle Tree 구현

Merkle Tree는 리프 노드들의 해시를 쌍으로 묶어 올라가면서 최종 Root 해시를 계산한다. Bitcoin의 트랜잭션 검증에 사용된 것과 동일한 구조다:

```ruby
class MerkleTree
  def self.build(leaves)
    return nil if leaves.empty?
    return leaves.first if leaves.size == 1

    # 홀수 개이면 마지막 노드를 복제
    leaves = leaves + [leaves.last] if leaves.size.odd?

    parent_layer = leaves.each_slice(2).map do |left, right|
      Digest::SHA256.hexdigest(left + right)
    end

    build(parent_layer)
  end

  def self.proof(leaves, target_index)
    proof_nodes = []
    layer = leaves.dup
    idx = target_index

    while layer.size > 1
      layer = layer + [layer.last] if layer.size.odd?
      sibling_idx = idx.even? ? idx + 1 : idx - 1
      proof_nodes << { hash: layer[sibling_idx], position: idx.even? ? :right : :left }
      layer = layer.each_slice(2).map { |l, r| Digest::SHA256.hexdigest(l + r) }
      idx /= 2
    end

    proof_nodes
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

TSA 실패는 **non-fatal** — 블록체인 기록이 주 증거이고, TSA는 보조 증거다. 따라서 TSA 요청 실패가 전체 앵커링 프로세스를 중단시키면 안 된다.

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

Ruby 4.0 (OpenSSL 3.x 기반)에서는 `OpenSSL::Timestamp::Token` 클래스가 **존재하지 않는다**. 오래된 블로그 포스트나 Stack Overflow 답변 중 상당수가 이 클래스를 사용하는 예제를 보여주는데, 그것들은 구버전 Ruby를 기준으로 작성된 것이다.

실제로 사용 가능한 클래스:
- `OpenSSL::Timestamp::Request` — 요청 객체 생성
- `OpenSSL::Timestamp::Response` — 서버 응답 파싱
- `OpenSSL::Timestamp::TokenInfo` — 토큰 메타데이터 (Response에서 추출)
- `OpenSSL::Timestamp::Factory` — 테스트용 자체 서명 응답 생성

`Token`은 없다. `Response` 객체에서 `token_info`를 꺼내야 한다. `token_info`가 `TokenInfo` 객체를 반환하고, 여기서 `message_imprint`, `serial_number`, `gen_time` 등에 접근할 수 있다.

### 수정

```ruby
def verify(token_der, data_hash)
  digest = [data_hash].pack("H*")
  resp = OpenSSL::Timestamp::Response.new(token_der)

  # 응답 상태 먼저 확인
  return false unless resp.status == OpenSSL::Timestamp::Response::GRANTED

  token_info = resp.token_info
  token_info.message_imprint == digest
rescue OpenSSL::Timestamp::TimestampError, StandardError => e
  Rails.logger.error "TSA verification failed: #{e.message}"
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

`cert_requested` (물음표 없이)는 존재하지 않는다. Ruby의 Boolean accessor 네이밍 컨벤션을 엄격하게 따른 결과다. attr_accessor가 아닌 custom accessor이기 때문에 getter와 setter의 이름이 다르게 정의되어 있다. Ruby에서 boolean 값을 읽을 때는 `?`로 끝나는 predicate 메서드를 쓰는 것이 관례인데, OpenSSL 바인딩이 이 관례를 따른다.

### 수정

```ruby
assert req.cert_requested?  # ? 추가
```

이와 비슷한 패턴이 `nonce_opt`에서도 발생할 수 있다. OpenSSL Timestamp API를 사용할 때는 Ruby 4.0 기준 문서를 직접 참조하는 것이 안전하다.

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

마이그레이션이 엉뚱한 에러를 뱉었다. 내가 추가한 TSA 컬럼과는 전혀 무관한 foreign key 충돌이었다.

### 원인

Rails 8의 **Solid Stack** (Solid Cache, Solid Queue, Solid Cable) 때문이다. Rails 8은 기본으로 4개의 데이터베이스를 사용한다:

```
primary:  메인 애플리케이션 데이터   ← 여기만 건드리면 됨
cache:    Solid Cache               ← 건드리면 안 됨
queue:    Solid Queue               ← 건드리면 안 됨
cable:    Solid Cable               ← 건드리면 안 됨
```

`bin/rails db:migrate`는 `database.yml`에 설정된 **모든** 데이터베이스를 대상으로 마이그레이션을 실행한다. Solid Queue/Cable/Cache의 마이그레이션이 이미 적용된 상태인데, `db:migrate`가 이들을 다시 시도하면서 이미 존재하는 foreign key를 또 만들려다 충돌이 발생한 것이다.

더 당혹스러운 것은 에러 메시지가 내가 작성한 마이그레이션과 무관한 테이블을 가리킨다는 점이다. 처음에는 내 마이그레이션 파일에 문제가 있다고 생각해서 한참 헤맸다.

### 수정

```bash
# primary DB만 특정 마이그레이션 적용
bin/rails db:migrate:up:primary VERSION=20260306100000
```

핵심: Rails 8 multi-database 앱에서는 `db:migrate` 대신 **`db:migrate:up:primary`**로 대상 DB를 명시해야 한다. `db:migrate`는 편의 명령어처럼 보이지만, 멀티 DB 환경에서는 예상치 못한 부작용이 있다.

rollback도 마찬가지다:
```bash
bin/rails db:migrate:down:primary VERSION=20260306100000
```

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

테스트 DB의 environment 태그가 `development`로 설정되어 있었다. Rails는 DB마다 `ar_internal_metadata` 테이블에 환경 정보를 저장하는데, 개발 환경에서 마이그레이션을 돌리는 과정에서 테스트 DB의 환경 태그까지 `development`로 덮어써진 것이다.

이 에러는 실수로 wrong environment에서 마이그레이션이 실행되는 것을 막기 위한 Rails의 보호 장치다. 하지만 멀티 DB 환경에서 `db:migrate`를 잘못 사용하면 의도치 않게 여러 DB의 환경 태그가 동시에 바뀔 수 있다.

### 수정 과정

```bash
# 1. 테스트 환경으로 environment 태그 재설정
RAILS_ENV=test bin/rails db:environment:set

# 2. primary 스키마 초기화 및 로드
RAILS_ENV=test bin/rails db:schema:load:primary

# 3. TSA 마이그레이션 적용
RAILS_ENV=test bin/rails db:migrate:up:primary VERSION=20260306100000
```

여기서 끝이 아니었다. Solid Queue/Cable/Cache의 테스트 DB도 foreign key 충돌이 발생했다:

```bash
# Solid 3개 DB를 drop & recreate
RAILS_ENV=test bin/rails db:drop:queue db:drop:cable db:drop:cache
RAILS_ENV=test bin/rails db:create:queue db:create:cable db:create:cache
RAILS_ENV=test bin/rails db:migrate
```

이렇게 해서 4개 DB 모두 테스트 환경이 정상화됐다. 순서가 중요하다: environment 태그 설정 → schema load → migrate 순으로 진행해야 한다.

---

## 7. 삽질 5: 테스트에서 self-signed TSA 만들기

실제 TSA 서버에 요청하면 테스트가 느려지고 불안정해진다. 네트워크 요청이 포함된 테스트는 CI 환경에서 특히 취약하다. `OpenSSL::Timestamp::Factory`를 사용하면 외부 의존성 없이 완전한 round-trip 테스트가 가능하다:

```ruby
def build_self_signed_tsa_response(data_hash)
  factory = OpenSSL::Timestamp::Factory.new
  factory.gen_time = Time.now
  factory.serial_number = 1
  factory.allowed_digests = ["sha256"]

  # RSA 키 생성 (테스트용이므로 2048 비트로 충분)
  key = OpenSSL::PKey::RSA.new(2048)

  cert = OpenSSL::X509::Certificate.new
  cert.version = 2
  cert.serial = 1
  cert.subject = OpenSSL::X509::Name.parse("/CN=Test TSA")
  cert.issuer = cert.subject
  cert.public_key = key.public_key
  cert.not_before = Time.now - 60
  cert.not_after = Time.now + 3600

  ef = OpenSSL::X509::ExtensionFactory.new
  ef.subject_certificate = cert
  ef.issuer_certificate = cert

  # 이 extension이 없으면 Factory가 거부함!
  cert.add_extension(
    ef.create_extension("extendedKeyUsage", "timeStamping", true)
  )
  cert.add_extension(
    ef.create_extension("basicConstraints", "CA:FALSE")
  )

  cert.sign(key, "SHA256")

  req = OpenSSL::Timestamp::Request.new
  req.algorithm = "SHA256"
  req.message_imprint = [data_hash].pack("H*")
  req.cert_requested = true

  resp = factory.create_timestamp(key, cert, req)
  resp.to_der
end
```

`extendedKeyUsage`에 `timeStamping`을 넣지 않으면 Factory가 `OpenSSL::Timestamp::TimestampError`를 발생시키며 거부한다. 이 extension은 해당 인증서가 타임스탬프 서명용임을 명시하는 것으로, RFC 3161 스펙에서 요구하는 사항이다.

테스트에서는 이 메서드로 생성한 DER 데이터를 실제 TSA 서버 응답처럼 사용할 수 있다:

```ruby
# 테스트 헬퍼
module TsaTestHelper
  def stub_tsa_response(data_hash)
    tsa_der = build_self_signed_tsa_response(data_hash)
    allow_any_instance_of(TsaTimestampService)
      .to receive(:send_tsa_request)
      .and_return(tsa_der)
  end
end
```

---

## 8. 전체 아키텍처 정리

완성된 시스템의 전체 흐름은 다음과 같다:

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

각 구성 요소의 역할:
- **블록체인**: 데이터 무결성 + 존재 증명 (주 증거) — 불변 공개 원장에 기록
- **TSA**: 제3자 시간 증명 (보조 증거) — 공인된 타임스탬프 서버의 서명
- **ASiC-E**: EU eIDAS 호환 증거 패키지 — 법원 제출 가능한 표준 포맷
- **Merkle Proof**: 개별 계약이 배치에 포함되었음을 증명하는 경로

블록체인과 TSA를 함께 사용하는 이유는 상호 보완적이기 때문이다. 블록체인은 데이터 위변조를 막지만 "언제"라는 시간 증명이 상대적으로 약하다. TSA는 공인된 제3자가 서명한 정확한 시간을 제공하지만 중앙화된 서버에 의존한다. 두 방식을 함께 사용하면 어느 하나가 신뢰를 잃더라도 다른 하나로 증거력을 유지할 수 있다.

---

## 교훈

1. **Ruby 4.0 OpenSSL API를 반드시 직접 확인하라** — 구버전 문서나 Stack Overflow 예제가 동작하지 않는다. `OpenSSL::Timestamp::Token` 클래스는 없고, predicate 메서드에 `?`가 필요하다. Ruby 공식 문서에서 현재 버전 기준으로 확인하라.

2. **Rails 8 multi-database는 마이그레이션이 까다롭다** — `db:migrate` 대신 `db:migrate:up:primary VERSION=xxx`로 특정 DB만 건드려라. Solid Stack DB(cache/queue/cable)를 건드리면 foreign key 충돌이 발생한다. 에러 메시지가 내 마이그레이션과 무관한 테이블을 가리키더라도 당황하지 마라.

3. **테스트 환경은 별도로 관리하라** — `RAILS_ENV=test`를 빼먹으면 environment 태그가 꼬인다. multi-database 앱에서는 4개 DB 모두 상태를 확인해야 한다. 복구 순서는 `db:environment:set` → `db:schema:load` → `db:migrate`다.

4. **TSA 실패는 non-fatal로 처리하라** — TSA 서버가 다운되어도 블록체인 앵커링은 성공해야 한다. `rescue`로 감싸고 로그만 남겨라. TSA는 보조 증거이므로 이것 때문에 전체 프로세스가 중단되어서는 안 된다.

5. **무료 TSA 서버는 DigiCert가 가장 안정적이다** — Sectigo는 15초 rate limit이 있어 배치 처리에 적합하지 않다. Entrust는 가끔 느리다. DigiCert를 primary로, 나머지를 fallback으로 구성하는 것을 권장한다.

6. **self-signed TSA로 테스트하라** — `OpenSSL::Timestamp::Factory`를 쓰면 외부 의존성 없이 round-trip 테스트가 가능하다. `extendedKeyUsage: timeStamping` extension을 반드시 포함시켜야 한다. 이것 없이는 Factory가 생성 자체를 거부한다.
