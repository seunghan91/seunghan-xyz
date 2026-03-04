---
title: "Production DB에 테이블이 없다: schema.rb와 migration 파일 불일치 사고"
date: 2026-02-26
draft: false
tags: ["Rails", "PostgreSQL", "DevOps", "CI/CD", "디버깅", "마이그레이션"]
description: "schema.rb에는 있지만 migration 파일이 누락되어 production DB에 테이블이 생성되지 않은 사고. 원인 분석과 3가지 방어 체계 구축기."
---

회원가입, 로그인이 전부 안 된다는 제보를 받았다. 앱에서는 "예상하지 못한 오류가 발생했습니다"만 반복.

---

## 증상

- 회원가입 시도 → 500 Internal Server Error
- 로그인 시도 → 동일하게 500
- Health check API → 200 OK, DB 연결 정상

서버는 살아있고 DB도 연결되어 있는데, 인증 관련 기능만 전멸.

---

## 조사 과정

### 1단계: 서버 상태 확인

SSH로 접속해서 Rails 환경 확인.

```bash
rails runner "puts Rails.env"
# => production

rails runner "puts User.count"
# => 13
```

서버 정상, DB 연결 정상, 유저 데이터도 존재.

### 2단계: API 직접 호출

```bash
# 회원가입 테스트
curl -X POST https://api.example.com/api/v1/auth/registrations \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"01088887777","password":"test1234",...}'

# => {"error":"회원가입 중 오류가 발생했습니다."}
# => HTTP 500
```

그런데 DB를 확인해보면:

```bash
rails runner "puts User.find(14).phone_number"
# => 01088887777
```

**유저는 생성되었는데 500?** 유저 생성 이후의 후처리에서 터지고 있다.

### 3단계: 코드 추적

회원가입 플로우:

```ruby
# 1. User 생성 → ✅ 성공
user = create_user!

# 2. Wallet 생성 → ✅ 성공
@wallet_service.create_wallet_for_user(user)

# 3. Session 생성 → ❌ 여기서 터짐
session = user.sessions.create!(
  ip_address: request.remote_ip,
  user_agent: request.user_agent,
  last_active_at: Time.current
)
```

### 4단계: 근본 원인 발견

```bash
rails runner "puts Session.column_names"
```

```
PG::UndefinedTable: ERROR: relation "sessions" does not exist
```

**`sessions` 테이블이 DB에 없다.**

---

## 왜 이런 일이 발생했나

### 핵심: 테스트 환경과 Production의 DB 생성 방식이 다르다

| 구분 | 테스트 (RSpec/CI) | Production |
|------|------------------|------------|
| DB 생성 방식 | `schema.rb`로 전체 로드 | `db:migrate`로 순차 실행 |
| sessions 테이블 | `schema.rb`에 있으므로 ✅ | migration 파일 없으면 ❌ |

`schema.rb`에는 sessions 테이블이 완벽하게 정의되어 있었다:

```ruby
# db/schema.rb
create_table "sessions", force: :cascade do |t|
  t.bigint "user_id", null: false
  t.string "token", null: false
  t.string "ip_address"
  t.string "user_agent"
  t.datetime "last_active_at"
  t.timestamps
  t.index ["token"], unique: true
  t.index ["user_id"]
end
```

하지만 `db/migrate/` 디렉토리에 `create_sessions.rb` 마이그레이션 파일이 **배포되지 않았다.**

테스트는 `schema.rb`를 통째로 로드하므로 항상 통과. Production은 `db:migrate`를 실행하므로 마이그레이션 파일이 없으면 테이블이 생성되지 않는다.

### 타임라인

```
1. sessions 마이그레이션 파일 생성 (로컬)
2. schema.rb 업데이트 (로컬 db:migrate 실행)
3. 테스트 통과 (schema.rb 기반이라 문제 없음)
4. 배포 시 마이그레이션 파일이 누락됨
5. Production: db:migrate 실행 → sessions 마이그레이션 없음 → 테이블 미생성
6. 모든 인증 기능 사망
```

---

## 즉시 조치

Production DB에 직접 테이블 생성:

```ruby
rails runner '
ActiveRecord::Base.connection.create_table :sessions do |t|
  t.references :user, null: false, foreign_key: true
  t.string :token, null: false
  t.string :ip_address
  t.string :user_agent
  t.datetime :last_active_at
  t.timestamps
end
ActiveRecord::Base.connection.add_index :sessions, :token, unique: true
'
```

회원가입/로그인 즉시 복구 확인.

---

## 재발 방지: 3가지 방어 체계

### 1. CI에서 migration 무결성 검증

CI 파이프라인에 `db:migrate` 결과와 `schema.rb`를 비교하는 단계를 추가.

```yaml
# .github/workflows/ci.yml
- name: Verify migration integrity
  run: |
    # db:migrate로 생성된 스키마 덤프
    bundle exec rails db:schema:dump
    cp db/schema.rb /tmp/schema_from_migrate.rb

    # 커밋된 schema.rb 복원
    git checkout db/schema.rb

    # 구조적 라인 비교
    if diff <(grep -E '^\s+(create_table|add_foreign_key|t\.)' db/schema.rb | sort) \
             <(grep -E '^\s+(create_table|add_foreign_key|t\.)' /tmp/schema_from_migrate.rb | sort); then
      echo "마이그레이션과 schema.rb 일치"
    else
      echo "불일치 감지!"
      exit 1
    fi
```

이렇게 하면 schema.rb에는 있지만 마이그레이션으로 생성할 수 없는 테이블을 PR 단계에서 잡아낸다.

### 2. 배포 후 Smoke Test

배포 완료 후 핵심 API 엔드포인트를 자동 호출:

```yaml
# 배포 후 자동 실행
- name: Smoke Test
  run: |
    # Health check
    curl -sf https://api.example.com/health | jq '.database_connected'

    # 회원가입 API (500이면 실패)
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST https://api.example.com/api/v1/auth/registrations \
      -H "Content-Type: application/json" \
      -d '{"phone_number":"01000009999","password":"test1234",...}')

    if [ "$STATUS" = "500" ]; then
      echo "회원가입 API 500 에러 - DB 테이블 누락 가능성"
      exit 1
    fi

    # 로그인 API 동일하게 검증
```

200/401/422는 정상 동작(성공/실패 무관). **500만 잡으면 된다.**

### 3. 서버 시작 전 테이블 존재 검증

Rake task를 만들어서 서버 시작 전에 실행:

```ruby
# lib/tasks/db_integrity.rake
namespace :db do
  task check_tables: :environment do
    schema_content = File.read(Rails.root.join("db", "schema.rb"))
    schema_tables = schema_content.scan(/create_table "(\w+)"/).flatten
    actual_tables = ActiveRecord::Base.connection.tables
    missing = schema_tables - actual_tables

    if missing.any?
      puts "누락된 테이블: #{missing.join(', ')}"
      exit 1  # 서버 시작 차단
    end
  end
end
```

배포 설정에서 puma 시작 전에 실행:

```yaml
startCommand: >
  bundle exec rake db:migrate &&
  bundle exec rake db:check_tables &&
  bundle exec puma -C config/puma.rb
```

테이블이 하나라도 누락되면 **서버가 아예 시작되지 않는다.** 불완전한 상태로 트래픽을 받는 것보다 낫다.

---

## 교훈

### schema.rb는 "현재 상태"이고, migration은 "과정"이다

- `schema.rb`: 로컬 DB의 현재 스냅샷
- `db/migrate/`: 빈 DB에서 현재 상태까지 도달하는 단계별 명령

이 둘이 동기화되지 않으면, 로컬/테스트에서는 잘 되는데 production에서만 터지는 유령 버그가 발생한다.

### 테스트가 통과한다고 안심할 수 없다

Rails의 테스트 DB 설정(`maintain_test_schema!`)은 `schema.rb`를 기준으로 동작한다. 마이그레이션 파일의 존재 여부는 검증하지 않는다.

**"테스트 환경과 production 환경의 DB 생성 경로가 다르다"**는 사실을 항상 인식해야 한다.

### 방어는 겹겹이

| 방어 계층 | 시점 | 역할 |
|-----------|------|------|
| CI migration 검증 | PR/Push | schema.rb ↔ migration 불일치 감지 |
| 서버 시작 전 검증 | 배포 시 | 누락 테이블 있으면 시작 차단 |
| Smoke test | 배포 후 | 실제 API 동작 확인 |

어느 한 계층이 뚫려도 다른 계층에서 잡는다.

---

## 로컬 검증 방법

전체 일관성 검증 rake task도 만들어두면 편하다:

```bash
bundle exec rails db:verify_schema_consistency RAILS_ENV=test
```

임시 DB를 만들어서 마이그레이션만으로 스키마를 구성하고, `schema.rb`와 테이블/컬럼/FK 단위로 비교한다. CI에서도 로컬에서도 동일하게 실행 가능.

```
=== 마이그레이션 ↔ schema.rb 일관성 검증 ===
1. 임시 데이터베이스 생성
2. 모든 마이그레이션 실행
3. 스키마 비교
✅ 마이그레이션과 schema.rb가 완전히 일치합니다.
```
