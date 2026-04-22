---
title: "RFC 3161 TSA Timestamp + Blockchain Merkle Anchoring: Debugging in Rails"
date: 2026-02-06
draft: false
tags: ["Rails", "Ruby", "OpenSSL", "Blockchain", "RFC 3161", "TSA", "Merkle Tree", "Debugging", "Migration"]
description: "Debugging struggles implementing RFC 3161 TSA timestamps and blockchain Merkle Tree anchoring in Rails 8 + Ruby 4.0. OpenSSL API changes, multi-database migration conflicts, and test environment issues."
cover:
  image: "/images/og/rails-rfc3161-tsa-blockchain-merkle-debugging.png"
  alt: "Rails Rfc3161 Tsa Blockchain Merkle Debugging"
  hidden: true
categories: ["Flutter", "Rails"]
---

To give an electronic contract storage system **legal evidentiary weight**, I needed to implement two things simultaneously:

1. **Blockchain Merkle Tree anchoring** — collect contract hashes, compute a Merkle Root, and record it on an L2 chain
2. **RFC 3161 TSA timestamps** — cryptographic proof of existence at a specific point in time, certified by a trusted third party

It looked straightforward. It was not. Each problem took far longer than expected to resolve, and the issues compounded in unexpected ways — especially where Ruby 4.0 API changes intersected with Rails 8's multi-database behavior.

---

## 1. What is RFC 3161 TSA?

RFC 3161 is the **Time-Stamp Authority (TSA)** protocol, an international standard (updated by RFC 5816) for having a trusted third party certify that a specific piece of data existed at a specific point in time. In a legal context, this means a recognized authority signs off on "this document existed on this date."

The flow is straightforward:

```
Client → generate SHA-256 hash → send request to TSA server → receive signed timestamp token
```

The TSA server takes the request, signs it with its private key, and returns a **TimeStampToken (TST)** in DER encoding. The token contains the hash value, the timestamp, and the TSA's certificate chain, so anyone can independently verify it.

Free TSA servers:
- **DigiCert**: `http://timestamp.digicert.com` (most reliable, recommended)
- **Sectigo**: `http://timestamp.sectigo.com` (has a 15-second rate limit)
- **Entrust**: `http://timestamp.entrust.net/TSS/RFC3161sha2TS` (occasionally slow)

Ruby includes the `OpenSSL::Timestamp` module in its standard library, so no external gem is required. However, the API differs across Ruby versions, and this turned out to be the first major source of pain.

---

## 2. Implementation Structure

### TSA Service

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

### Merkle Tree Implementation

A Merkle Tree pairs up leaf node hashes and combines them upward until a single Root hash remains. This is the same structure used in Bitcoin to verify transactions in a block:

```ruby
class MerkleTree
  def self.build(leaves)
    return nil if leaves.empty?
    return leaves.first if leaves.size == 1

    # Duplicate the last node if the count is odd
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

### Merkle + TSA Anchoring Flow

```
1. Collect unanchored Merkle leaves
2. Build Merkle Tree → compute root hash
3. Record root hash on blockchain (receive tx_hash)
4. Send root hash to TSA server for timestamp
5. Save tx_hash + TSA token together in the batch record
```

TSA failure is **non-fatal** — the blockchain record is the primary evidence, and TSA is supplementary. A TSA failure must not abort the entire anchoring process.

---

## 3. Bug 1: Ruby 4.0 OpenSSL::Timestamp API Changes

### Problem

```ruby
# Written based on older examples
def verify(token_der, data_hash)
  token = OpenSSL::Timestamp::Token.new(token_der)
  token.message_imprint == digest
end
```

```
NameError: uninitialized constant OpenSSL::Timestamp::Token
```

### Cause

In Ruby 4.0 (based on OpenSSL 3.x), the `OpenSSL::Timestamp::Token` class **does not exist**. A large number of older blog posts and Stack Overflow answers demonstrate examples using this class — those were written against older Ruby versions.

The classes actually available in the current API:
- `OpenSSL::Timestamp::Request` — build a timestamp request
- `OpenSSL::Timestamp::Response` — parse the server's response
- `OpenSSL::Timestamp::TokenInfo` — access token metadata (extracted from Response)
- `OpenSSL::Timestamp::Factory` — generate self-signed responses for testing

`Token` is gone. You must extract `token_info` from the `Response` object. `token_info` returns a `TokenInfo` instance, which exposes `message_imprint`, `serial_number`, `gen_time`, and so on.

### Fix

```ruby
def verify(token_der, data_hash)
  digest = [data_hash].pack("H*")
  resp = OpenSSL::Timestamp::Response.new(token_der)

  # Check response status first
  return false unless resp.status == OpenSSL::Timestamp::Response::GRANTED

  token_info = resp.token_info
  token_info.message_imprint == digest
rescue OpenSSL::Timestamp::TimestampError, StandardError => e
  Rails.logger.error "TSA verification failed: #{e.message}"
  false
end
```

---

## 4. Bug 2: `cert_requested` vs `cert_requested?`

### Problem

```ruby
# In a test assertion
assert req.cert_requested
```

```
NoMethodError: undefined method 'cert_requested' for OpenSSL::Timestamp::Request
```

### Cause

In Ruby 4.0's `OpenSSL::Timestamp::Request`:
- **Write**: `req.cert_requested = true` (setter, uses `=`)
- **Read**: `req.cert_requested?` (predicate, uses `?`)

`cert_requested` without a question mark does not exist. This is Ruby's strict boolean accessor naming convention at work. Because this is a custom accessor rather than a standard `attr_accessor`, the getter and setter are defined with different names. In Ruby, reading a boolean value conventionally uses a `?`-suffixed predicate method, and the OpenSSL bindings enforce this convention.

### Fix

```ruby
assert req.cert_requested?  # add the ?
```

Similar issues can arise with other boolean attributes on OpenSSL Timestamp objects. When in doubt, consult the Ruby 4.0 docs directly rather than relying on older examples.

---

## 5. Bug 3: Rails 8 Multi-Database Migration Conflict

### Situation

I created a migration to add four TSA-related columns:

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

### Problem

```bash
$ bin/rails db:migrate
```

```
PG::DuplicateObject: ERROR: constraint "fk_rails_xxxxx" already exists
```

The migration threw an error completely unrelated to the TSA columns I was adding — a foreign key constraint conflict on a table I had never touched.

### Cause

This is caused by Rails 8's **Solid Stack** (Solid Cache, Solid Queue, Solid Cable). Rails 8 uses four separate databases by default:

```
primary:  main application data   ← the only one I need to touch
cache:    Solid Cache              ← leave alone
queue:    Solid Queue              ← leave alone
cable:    Solid Cable              ← leave alone
```

`bin/rails db:migrate` attempts to migrate **all** databases listed in `database.yml`. The migrations for Solid Queue/Cable/Cache had already been applied, but running `db:migrate` again tried to recreate foreign keys that already existed, causing the conflict.

What made this especially confusing is that the error message pointed at tables from the Solid Stack schemas — tables I had never written a migration for. My first instinct was that something was wrong with my migration file, leading to a long debugging session before I realized the real cause.

### Fix

```bash
# Apply migration only to the primary database
bin/rails db:migrate:up:primary VERSION=20260306100000
```

The key insight: in a Rails 8 multi-database application, use `db:migrate:up:primary` instead of `db:migrate` to target a specific database. The generic `db:migrate` command looks convenient but carries unexpected side effects in multi-database environments.

Rollback works the same way:
```bash
bin/rails db:migrate:down:primary VERSION=20260306100000
```

---

## 6. Bug 4: Test Database Environment Mismatch

### Problem

After applying the migration, running the test suite produced:

```
ActiveRecord::EnvironmentMismatchError:
You are attempting to modify a database that was last run in `development`
environment. You are running in `test` environment.
```

### Cause

The test database's environment tag was set to `development`. Rails stores environment information in an `ar_internal_metadata` table in each database. During the migration process, running commands in the development environment had accidentally overwritten the test database's environment tag.

This error is a Rails safety mechanism to prevent accidental modifications to the wrong environment's database. However, in a multi-database setup, misusing `db:migrate` can silently overwrite environment tags across multiple databases at once.

### Resolution Steps

```bash
# 1. Reset the environment tag for the test environment
RAILS_ENV=test bin/rails db:environment:set

# 2. Reload the primary schema
RAILS_ENV=test bin/rails db:schema:load:primary

# 3. Apply the TSA migration
RAILS_ENV=test bin/rails db:migrate:up:primary VERSION=20260306100000
```

That was not the end of it. The Solid Queue/Cable/Cache test databases also had foreign key conflicts:

```bash
# Drop and recreate the three Solid Stack test databases
RAILS_ENV=test bin/rails db:drop:queue db:drop:cable db:drop:cache
RAILS_ENV=test bin/rails db:create:queue db:create:cable db:create:cache
RAILS_ENV=test bin/rails db:migrate
```

After this, all four test databases were back in a clean state. The order matters: `db:environment:set` first, then `db:schema:load`, then `db:migrate`.

---

## 7. Bug 5: Building a Self-Signed TSA Response for Tests

Making real HTTP requests to an external TSA server during tests makes the suite slow and flaky — especially problematic in CI environments. `OpenSSL::Timestamp::Factory` allows you to generate a complete, cryptographically valid TSA response locally, with no external dependencies:

```ruby
def build_self_signed_tsa_response(data_hash)
  factory = OpenSSL::Timestamp::Factory.new
  factory.gen_time = Time.now
  factory.serial_number = 1
  factory.allowed_digests = ["sha256"]

  # 2048-bit RSA is sufficient for test purposes
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

  # This extension is REQUIRED — Factory will reject the certificate without it
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

If you omit the `extendedKeyUsage` extension with `timeStamping`, the Factory raises `OpenSSL::Timestamp::TimestampError` and refuses to generate the response. This extension designates the certificate as valid for signing timestamps, and RFC 3161 requires it. Tracking down this requirement took longer than it should have.

In tests, the DER data produced by this method can be used exactly like a real TSA server response:

```ruby
# Test helper module
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

## 8. Full Architecture Overview

The complete flow of the finished system:

```
Contract signed
  ↓
SHA-256 hash generated
  ↓
MerkleLeaf created (unanchored)
  ↓
Daily Cron Job (AnchorService.call)
  ↓
┌─────────────────────────────────────┐
│ 1. Build Merkle Tree                │
│ 2. Root → record on blockchain      │
│    (receive tx_hash)                │
│ 3. Root → TSA timestamp (optional)  │
│ 4. Update Batch + Leaves            │
└─────────────────────────────────────┘
  ↓
Evidence Package (ASiC-E)
├── document.pdf
├── META-INF/manifest.xml
├── META-INF/blockchain-proof.json
└── META-INF/timestamp.tst   ← TSA token
```

What each component contributes:
- **Blockchain**: data integrity + proof of existence (primary evidence) — written to an immutable public ledger
- **TSA**: third-party time certification (supplementary evidence) — signed by a recognized timestamp authority
- **ASiC-E**: EU eIDAS-compatible evidence package — a standardized format acceptable for court submission
- **Merkle Proof**: a cryptographic path proving that an individual contract was included in a specific batch

The reason for combining blockchain anchoring and TSA is that they are complementary. Blockchain prevents data tampering but provides relatively weak proof of *when* something occurred. TSA provides a precise, third-party-certified timestamp but depends on a centralized server. Using both means that even if confidence in one approach erodes over time, the other maintains the evidentiary value.

---

## Key Takeaways

1. **Always verify Ruby 4.0 OpenSSL APIs against current documentation.** Older examples and Stack Overflow answers will not work. `OpenSSL::Timestamp::Token` does not exist. Predicate methods require `?`. Check the official Ruby docs for the exact version you are running.

2. **Rails 8 multi-database migration requires explicit targeting.** Use `db:migrate:up:primary VERSION=xxx` instead of the generic `db:migrate`. Running `db:migrate` in a Solid Stack setup will attempt to re-migrate the cache/queue/cable databases and trigger foreign key conflicts. The error messages will point at tables you never touched — do not let that mislead you.

3. **Manage test environment state explicitly.** Forgetting `RAILS_ENV=test` can corrupt environment tags across databases. In a multi-database Rails 8 app, all four databases need their environment state verified independently. Recovery order: `db:environment:set` → `db:schema:load` → `db:migrate`.

4. **Treat TSA failures as non-fatal.** A TSA server outage must not abort the blockchain anchoring process. Wrap TSA calls in `rescue`, log the failure, and continue. TSA is supplementary evidence — the system must remain functional without it.

5. **DigiCert is the most reliable free TSA server.** Sectigo has a 15-second rate limit that makes it unsuitable for batch processing. Entrust is occasionally slow. Use DigiCert as primary and configure the others as fallbacks in an ordered chain.

6. **Use `OpenSSL::Timestamp::Factory` for test isolation.** It enables complete round-trip testing with no network dependency. The `extendedKeyUsage: timeStamping` extension on the test certificate is mandatory — without it, the Factory will refuse to generate the response entirely.
