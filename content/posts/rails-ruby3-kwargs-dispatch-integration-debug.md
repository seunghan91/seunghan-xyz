---
title: "하루 종일 삽질한 것들 — Ruby 3.0 kwargs, Docker env, NAS 크론, SSH 특수문자"
date: 2026-01-02
draft: false
tags: ["Rails", "Ruby", "Docker", "Synology", "NAS", "배포", "디버깅", "크론"]
description: "AI 에이전트와 Rails API를 연동하는 작업을 하면서 만난 버그들: Ruby 3.0 키워드 인수 분리, Docker env_file 재로드 문제, Synology NAS 크론 설정, SSH heredoc 특수문자 이슈까지."
cover:
  image: "/images/og/rails-ruby3-kwargs-dispatch-integration-debug.png"
  alt: "Rails Ruby3 Kwargs Dispatch Integration Debug"
  hidden: true
categories: ["Rails", "DevOps"]
---

AI 에이전트가 Rails API 서버를 호출해서 티켓을 자동 배정하는 디스패처를 만들었다. 로직 자체는 간단한데 붙이는 과정에서 예상치 못한 곳에서 계속 막혔다. 하루 동안 7개의 서로 다른 버그를 순서대로 만났고, 각각은 사소하지만 연속으로 터지니 꽤 피로했다. 비슷한 스택을 쓰는 사람에게 도움이 됐으면 해서 기록해 둔다.

---

## 1. Ruby 3.0 kwargs 분리 — `render_success(key: val)` 가 왜 터지나

가장 오래 고생한 것. Rails 컨트롤러에서 응답 헬퍼를 이렇게 호출했다:

```ruby
render_success(tickets: tickets_list, pagination: pagination_data)
```

서버 로그에 찍힌 에러:

```
ArgumentError - unknown keywords: :tickets, :pagination
```

헬퍼 정의는 이렇다:

```ruby
def render_success(data, status: :ok)
  render json: { success: true, data: data }, status: status
end
```

### 왜 Ruby 3.0부터 달라졌나

**Ruby 2.x**에서는 `render_success(tickets: ..., pagination: ...)` 호출 시 `{tickets: ..., pagination: ...}` 해시가 `data`에 묵시적으로 들어갔다. 이것을 "hash rocket implicit conversion"이라고 불렀다. Ruby 인터프리터가 "키워드처럼 생겼지만 positional 인수 자리에 맞게 해시로 변환해주겠다"는 관대한 동작을 했다.

**Ruby 3.0**부터는 이 동작이 완전히 제거됐다 (Ruby 2.7에서 deprecation warning으로 먼저 예고됐다). 키워드 인수(`key: value` 문법)와 일반 positional 인수는 완전히 분리된다. `tickets:`, `pagination:`이 키워드처럼 생겼으니 Ruby 3.0은 이것들을 키워드 인수로 인식한다. 그런데 `render_success`는 `data` 하나만 positional 인수로 받고, 정의에 없는 키워드(`tickets:`, `pagination:`)가 넘어오니 `ArgumentError: unknown keywords`.

단일 키워드처럼 생긴 것도 마찬가지다:

```ruby
render_success(ticket: ticket_json(@ticket))
# → ArgumentError: wrong number of arguments (given 0, expected 1)
```

`ticket:` 하나도 키워드 인수로 해석되어 `data`에 아무것도 안 들어가고, positional 인수가 0개가 되어 에러가 난다.

### 해결

명시적으로 해시 `{}`로 감싸면 Ruby가 "이건 해시 리터럴이다"라고 확실히 인식한다.

```ruby
# 전부 이렇게 바꿔야 한다
render_success({ ticket: ticket_json(@ticket) })
render_success({ tickets: tickets_list, pagination: pagination_data })
```

프로젝트 전체 컨트롤러를 훑어서 `render_success(` 뒤에 `{`가 없는 것을 전부 수정했다. 한 줄짜리는 sed로 일괄 처리:

```bash
sed -i '' \
  -e 's/render_success(ticket: \(.*\))/render_success({ ticket: \1 })/g' \
  -e 's/render_success(message: "\(.*\)")/render_success({ message: "\1" })/g' \
  app/controllers/api/v1/tickets_controller.rb
```

### 예방책

Ruby 2.7 프로젝트라면 지금 당장 로그에서 `warning: Using the last argument as keyword parameters is deprecated` 메시지를 찾아보자. 3.0 업그레이드 전에 미리 고칠 수 있다.

---

## 2. Docker `restart` 는 env_file을 재로드하지 않는다

`.env` 파일에 환경 변수를 추가하고 컨테이너를 재시작했다:

```bash
docker compose restart
```

그런데 컨테이너 안에서 확인하면 새 변수가 없다.

```bash
docker exec mycontainer python3 -c "import os; print(os.environ.get('NEW_VAR', 'MISSING'))"
# → MISSING
```

### 원인

`docker compose restart`는 실행 중인 프로세스를 SIGTERM으로 종료한 뒤 같은 컨테이너 이미지를 다시 시작하는 것이다. **컨테이너 자체를 재생성하지 않는다.** `env_file` 설정은 컨테이너를 생성(create)할 때 한 번만 읽힌다. 이미 생성된 컨테이너의 환경 변수는 재시작해도 바뀌지 않는다.

이는 `docker run`으로 시작한 컨테이너도 동일하다. 환경 변수는 컨테이너 생성 시 `docker inspect`로 확인할 수 있는 불변 설정의 일부다.

### 해결

컨테이너를 재생성해야 한다.

```bash
docker compose up -d
```

`up -d`는 현재 `docker-compose.yml` 설정과 실행 중인 컨테이너를 비교해서, 설정이 바뀐 서비스를 재생성(Recreate)한다. 이렇게 해야 `env_file`의 새 값이 컨테이너에 반영된다.

```
Container mycontainer  Recreate
Container mycontainer  Recreated
Container mycontainer  Starting
Container mycontainer  Started
```

### 강제 재생성이 필요한 경우

설정이 바뀌지 않았는데 강제로 재생성하려면:

```bash
docker compose up -d --force-recreate
```

환경 변수가 제대로 들어갔는지 확인:

```bash
docker exec mycontainer env | grep NEW_VAR
```

---

## 3. Synology NAS에는 `crontab` 명령이 없다

파이썬 스크립트를 5분마다 실행하는 크론잡을 걸려고 했다.

```bash
ssh user@nas "crontab -e"
# → crontab: command not found
```

### 원인

Synology DSM은 일반 Linux 배포판과 다르게 `crontab` 명령을 기본으로 제공하지 않는다. DSM의 크론 데몬(`crond`)은 직접 동작하지만, 사용자 인터페이스인 `crontab` 유틸리티가 없다.

### 해결: /etc/crontab 직접 편집

`/etc/crontab` 파일을 직접 편집해야 한다. 이 파일은 시스템 레벨 crontab으로, 일반 사용자용 crontab과 달리 실행 유저 컬럼이 있다.

```bash
# /etc/crontab 형식: 분 시 일 월 요일 실행유저 명령
*/5    *    *    *    *    root    /usr/local/bin/docker exec mycontainer python3 /home/node/script.py >> /path/to/logs/script.log 2>&1
```

주의할 점:
- 필드 구분은 **탭**이 원칙이지만 공백도 동작한다
- 실행 유저 컬럼(`root`)이 일반 사용자용 crontab과 달리 있다
- `sudo` 권한으로 편집해야 한다
- `/etc/crontab`은 DSM 업데이트 시 **덮어쓰여질 수 있다**. 중요한 크론잡은 별도로 백업해 두거나, DSM의 Task Scheduler(제어판 > 작업 스케줄러)를 사용하는 것이 더 안전하다

### 편집 후 적용

`/etc/crontab`을 저장하면 `crond`가 자동으로 변경을 감지하는 경우도 있지만, 명시적으로 재시작하면 확실하다:

```bash
# crond 재시작 (DSM 방식)
sudo synoservicectl --restart crond
```

---

## 4. SSH heredoc에서 `!` 문자가 문제가 된다

Rails runner로 서버에서 짧은 Ruby 코드를 실행하고 싶었다:

```bash
ssh user@server 'bundle exec rails runner "record.update!(key: value)"'
```

이게 자꾸 실패했다. `update!`의 `!`가 bash에서 히스토리 확장(history expansion) 문자로 해석되는 것이 문제다.

### 왜 단순 따옴표 안에서도 문제가 생기나

bash 인터랙티브 셸에서 `!`는 히스토리 확장 트리거다. 단순 따옴표(single quote) 안에서는 보통 이스케이프되지만, SSH 명령을 통해 원격 셸로 전달될 때 따옴표 처리 레이어가 하나 더 생기면서 예상치 못하게 동작한다.

heredoc을 쓰면 더 심각해진다:

```bash
# heredoc에서 update! → update\! 로 변환되어 Ruby 문법 에러
ssh user@server << 'EOF'
  record.update!(key: value)
EOF
```

### 해결 1: bang 메서드를 쓰지 않는다

`!`를 쓰지 않는 메서드로 교체한다. Rails에는 bang 메서드 대신 쓸 수 있는 것들이 있다:

```ruby
record.update_columns(key: value)   # update! 대신
record.save(validate: false)        # save! 대신
```

`update_columns`는 콜백과 유효성 검사를 건너뛰고 DB를 직접 업데이트한다. 일회성 데이터 수정 스크립트에서는 오히려 더 적합할 때가 많다.

### 해결 2: 코드를 파일로 먼저 써서 실행한다

복잡한 코드라면 Python으로 파일을 서버에 먼저 쓴 다음 실행한다:

```bash
# Python으로 파일 작성 (! 문자 포함 가능)
ssh user@server "python3 -c \"
with open('/tmp/fix.rb', 'w') as f:
    f.write('''
k = Model.find_by(token: \\\"TOKEN\\\")
k.update_columns(permissions: k.permissions | [\\\"new_perm\\\"])
puts k.reload.permissions.inspect
''')
\""

# 그 다음 실행
ssh user@server 'bundle exec rails runner /tmp/fix.rb'
```

### 해결 3: bash -s 패턴

또 다른 방법으로 stdin으로 스크립트를 넘기는 방식도 있다:

```bash
ssh user@server bash -s << 'SCRIPT'
cd /app && bundle exec rails runner - << 'RUBY'
puts "Hello from Rails"
RUBY
SCRIPT
```

---

## 5. SCP/SFTP가 안 되는 디렉토리 — base64 우회

NAS 서버에 파일을 올리려고 했는데:

```bash
scp script.py user@nas:/path/to/dir/
# → scp: /path/to/dir/script.py: Permission denied
```

디렉토리가 root로 생성되어 있어서 일반 SSH 계정으로는 SCP/SFTP 쓰기가 안 됐다. `chmod`로 권한을 줘도 SSH 세션에서는 바로 적용이 안 되는 상황.

### 원인

SCP와 SFTP는 별도의 서브시스템(`sftp-server`)을 통해 동작한다. 이 서브시스템은 일반 SSH 셸 세션과 달리 `sudo` 권한 상승이 불가능하다. 따라서 접근 권한이 없는 디렉토리에는 SCP/SFTP로 쓰기가 근본적으로 불가능하다.

### 우회 방법: SSH + base64 인코딩

SSH + base64 인코딩으로 전송한다. 이 방식은 순수 SSH 셸 명령만 사용하므로 `sudo`로 권한 우회가 가능하다.

로컬에서:
```bash
base64 script.py | ssh user@nas "base64 -d | sudo tee /path/to/dir/script.py > /dev/null"
```

또는 Python으로 내용을 직접 echo:

```bash
CONTENT=$(base64 < script.py)
ssh user@nas "echo '$CONTENT' | base64 -d | sudo tee /path/to/dir/script.py"
```

### 주의사항

파일이 크면 base64 인코딩으로 크기가 약 33% 늘어난다. 대용량 파일에는 적합하지 않다. 대용량이라면 먼저 `chmod`나 `chown`으로 디렉토리 권한을 고치는 것이 근본 해결책이다.

---

## 6. `update_column` vs `update_columns` — PostgreSQL 배열 컬럼

마이그레이션에서 PostgreSQL 배열 타입 컬럼을 업데이트하려고 했다:

```ruby
record.update_column(:permissions, record.permissions + ['new_perm'])
```

이게 말썽이었다.

### `update_column` vs `update_columns` 차이

`update_column`(단수)은 Active Record에서 단일 컬럼을 콜백 없이 DB에 직접 업데이트하는 메서드다. 배열 연산 결과(`Array`)를 그대로 넘기면 pg 드라이버가 직렬화를 제대로 못 하는 경우가 있다. 특히 Ruby Array 타입을 PostgreSQL `text[]` 타입으로 변환할 때 문제가 생길 수 있다.

**`update_columns` (복수형)**을 쓰면 더 안정적으로 동작했다:

```ruby
new_perms = (record.permissions || []) | ['new_perm']
record.update_columns(permissions: new_perms)
```

### `|` vs `+` 연산자

`|` 연산자는 중복 없이 배열을 합쳐준다(union). `+`는 중복을 허용하므로 권한 목록에는 `|`가 더 적합하다:

```ruby
['admin', 'read'] | ['read', 'write']  # → ['admin', 'read', 'write']
['admin', 'read'] + ['read', 'write']  # → ['admin', 'read', 'read', 'write']
```

### nil 방어 패턴

`record.permissions`가 nil일 수 있는 경우 `||`로 방어해야 한다:

```ruby
new_perms = (record.permissions || []) | ['new_perm']
```

마이그레이션에서 `default: []`를 설정하지 않은 컬럼이라면 기존 레코드가 nil일 수 있다.

---

## 7. `wip_count` 가 DB 컬럼인 줄 알았는데 computed field였다

유저 모델에 `wip_count` 속성이 있길래 `update_columns(wip_count: 0)`으로 리셋하려 했다:

```
can't write unknown attribute 'wip_count'
```

### 원인

확인해 보니 DB 컬럼이 아니라 Ruby 메서드였다:

```ruby
def wip_count
  assigned_tickets.where(aasm_state: %w[assigned in_progress]).count
end
```

실시간으로 활성 티켓 수를 세는 computed field다. `schema.rb`에는 없고 모델 파일에만 정의된 메서드여서 처음에는 DB 컬럼으로 착각했다.

### 해결

값을 바꾸려면 관련 티켓의 상태를 바꾸거나, `max_wip`을 조정해야 한다:

```ruby
# wip_count는 못 바꾸고, max_wip을 늘리면 수용 가능 티켓 수가 늘어난다
user.update_columns(max_wip: 20)
```

### 빠른 확인 방법

모델에 해당 속성이 DB 컬럼인지 computed field인지 확실하지 않으면:

```ruby
# Rails console에서
User.column_names.include?('wip_count')  # false면 computed field
User.columns_hash['wip_count']            # nil이면 DB 컬럼 아님
```

또는 `db/schema.rb`를 직접 검색하면 가장 빠르다.

---

## 정리

| 문제 | 핵심 원인 | 해결 |
|------|-----------|------|
| `render_success(key: val)` 500 에러 | Ruby 3.0 kwargs/positional 분리 | `{}` 명시적 해시 래핑 |
| Docker 환경 변수 미반영 | `restart`는 컨테이너 재생성 안 함 | `up -d` 사용 |
| NAS `crontab` 없음 | Synology DSM 특성 | `/etc/crontab` 직접 편집 |
| SSH heredoc `!` 오류 | bash 히스토리 확장 | `update_columns` 등 `!` 없는 메서드 사용 |
| SCP Permission denied | root 소유 디렉토리 | base64 + SSH tee 우회 |
| PostgreSQL 배열 업데이트 | `update_column` 직렬화 이슈 | `update_columns` + `|` 연산자 |
| `update_columns` 오류 | computed field를 DB 컬럼으로 착각 | 모델 정의 확인 후 `max_wip` 조정 |

---

## Key Takeaways

- **Ruby 3.0 kwargs 분리는 조용한 시한폭탄이다.** Ruby 2.7에서 3.0으로 업그레이드할 때 `render_success(key: val)` 패턴을 쓰는 모든 곳을 찾아야 한다. `render_success(` 다음에 `{`가 없는 호출을 전부 수정하면 된다.
- **Docker 환경 변수는 컨테이너 생성 시 고정된다.** `restart`가 아닌 `up -d`로 재생성해야 한다. CI/CD 파이프라인에서도 이 차이를 놓치지 않도록 주의하자.
- **Synology NAS는 표준 Linux가 아니다.** `crontab`, `apt`, `systemctl` 등 익숙한 명령들이 없거나 다르게 동작한다. DSM 문서를 먼저 확인하자.
- **SSH + `!` 문자 조합은 항상 위험하다.** Rails bang 메서드(`update!`, `save!`)를 SSH heredoc으로 실행할 때는 `update_columns`/`save(validate: false)`로 교체하거나 파일로 분리하자.
- **computed field와 DB 컬럼을 혼동하지 않으려면** `schema.rb` 또는 `column_names`로 먼저 확인하는 습관을 들이자.
