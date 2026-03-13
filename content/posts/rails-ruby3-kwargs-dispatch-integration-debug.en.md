---
title: "A Day of Debugging — Ruby 3.0 kwargs, Docker env, NAS Cron, SSH Special Characters"
date: 2026-01-02
draft: false
tags: ["Rails", "Ruby", "Docker", "Synology", "NAS", "Deployment", "Debugging", "Cron"]
description: "Bugs encountered while integrating AI agents with Rails API: Ruby 3.0 keyword argument separation, Docker env_file reload issues, Synology NAS cron setup, and SSH heredoc special character issues."
cover:
  image: "/images/og/rails-ruby3-kwargs-dispatch-integration-debug.png"
  alt: "Rails Ruby3 Kwargs Dispatch Integration Debug"
  hidden: true
---


AI 에이전트가 Rails API 서버를 호출해서 티켓을 자동 배정하는 디스패처를 만들었다. 로직 자체는 간단한데 붙이는 과정에서 예상치 못한 곳에서 계속 막혔다. 겪은 것들을 기록해 둔다.

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

**Ruby 2.x**에서는 `render_success(tickets: ..., pagination: ...)` 호출 시 `{tickets: ..., pagination: ...}` 해시가 `data`에 들어갔다.

**Ruby 3.0**부터 키워드 인수와 일반 인수가 완전히 분리됐다. `tickets:`, `pagination:` 이 키워드처럼 생겼으니 Ruby 3.0은 이것들을 키워드 인수로 인식한다. 그런데 `render_success`는 `data` 하나만 positional 인수로 받으니 `ArgumentError`.

단일 키워드처럼 생긴 것도 마찬가지다:

```ruby
render_success(ticket: ticket_json(@ticket))
# → ArgumentError: wrong number of arguments (given 0, expected 1)
```

`ticket:` 하나도 키워드 인수로 해석되어 `data`에 아무것도 안 들어간다.

**해결:** 명시적으로 해시 `{}`로 감싸면 Ruby가 "이건 해시 리터럴이다"라고 확실히 인식한다.

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

**원인:** `docker compose restart`는 프로세스만 재시작한다. 컨테이너 자체를 재생성하지 않기 때문에 `env_file`을 다시 읽지 않는다.

**해결:** 컨테이너를 재생성해야 한다.

```bash
docker compose up -d
```

`up -d`는 설정이 바뀐 서비스를 재생성(Recreate)한다. 이렇게 해야 `env_file`의 새 값이 컨테이너에 반영된다.

```
Container mycontainer  Recreate
Container mycontainer  Recreated
Container mycontainer  Starting
Container mycontainer  Started
```

---

## 3. Synology NAS에는 `crontab` 명령이 없다

파이썬 스크립트를 5분마다 실행하는 크론잡을 걸려고 했다.

```bash
ssh user@nas "crontab -e"
# → crontab: command not found
```

Synology DSM은 일반 Linux와 다르게 `crontab` 명령을 기본으로 제공하지 않는다. `/etc/crontab`을 직접 편집해야 한다.

```bash
# /etc/crontab 형식: 분 시 일 월 요일 실행유저 명령
*/5    *    *    *    *    root    /usr/local/bin/docker exec mycontainer python3 /home/node/script.py >> /path/to/logs/script.log 2>&1
```

주의할 점:
- 필드 구분은 **탭**이 원칙이지만 공백도 동작한다
- 실행 유저 컬럼(`root`)이 일반 사용자용 crontab과 달리 있다
- `sudo` 권한으로 편집해야 한다

---

## 4. SSH heredoc에서 `!` 문자가 문제가 된다

Rails runner로 서버에서 짧은 Ruby 코드를 실행하고 싶었다:

```bash
ssh user@server 'bundle exec rails runner "record.update!(key: value)"'
```

이게 자꾸 실패했다. `update!`의 `!`가 bash에서 히스토리 확장 문자로 해석되는 것이 문제다.

단순 따옴표 안에서도 SSH를 타면 해석 방식이 달라져서 heredoc을 쓰면 더 심각해진다:

```bash
# heredoc에서 update! → update\! 로 변환되어 Ruby 문법 에러
ssh user@server << 'EOF'
  record.update!(key: value)
EOF
```

**해결 1:** `!`를 쓰지 않는 메서드로 교체한다. Rails에는 bang 메서드 대신 쓸 수 있는 것들이 있다:

```ruby
record.update_columns(key: value)   # update! 대신
record.save(validate: false)        # save! 대신
```

**해결 2:** 코드를 서버 파일로 먼저 쓴 다음 실행한다.

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

---

## 5. SCP/SFTP가 안 되는 디렉토리 — base64 우회

NAS 서버에 파일을 올리려고 했는데:

```bash
scp script.py user@nas:/path/to/dir/
# → scp: /path/to/dir/script.py: Permission denied
```

디렉토리가 root로 생성되어 있어서 일반 SSH 계정으로는 SCP/SFTP 쓰기가 안 됐다. `chmod`로 권한을 줘도 SSH 세션에서는 바로 적용이 안 되는 상황.

**우회 방법:** SSH + base64 인코딩으로 전송한다.

로컬에서:
```bash
base64 script.py | ssh user@nas "base64 -d | sudo tee /path/to/dir/script.py > /dev/null"
```

또는 Python으로 내용을 직접 echo:

```bash
CONTENT=$(base64 < script.py)
ssh user@nas "echo '$CONTENT' | base64 -d | sudo tee /path/to/dir/script.py"
```

SCP는 SFTP 서브시스템을 타지만, 이 방식은 순수 SSH 셸 명령만 사용해서 `sudo`로 권한 우회가 가능하다.

---

## 6. `update_column` vs `update_columns` — PostgreSQL 배열 컬럼

마이그레이션에서 PostgreSQL 배열 타입 컬럼을 업데이트하려고 했다:

```ruby
record.update_column(:permissions, record.permissions + ['new_perm'])
```

이게 말썽이었다. `update_column`은 단수형으로, 단일 컬럼만 바꾸고 콜백도 건너뛴다. 배열 연산 결과(`Array`)를 그대로 넘기면 pg 드라이버가 직렬화를 제대로 못 하는 경우가 있다.

**`update_columns` (복수형)**을 쓰면 더 안정적으로 동작했다:

```ruby
new_perms = (record.permissions || []) | ['new_perm']
record.update_columns(permissions: new_perms)
```

`|` 연산자는 중복 없이 배열을 합쳐준다. `+`는 중복을 허용하므로 권한 목록에는 `|`가 더 적합하다.

---

## 7. `wip_count` 가 DB 컬럼인 줄 알았는데 computed field였다

유저 모델에 `wip_count` 속성이 있길래 `update_columns(wip_count: 0)`으로 리셋하려 했다:

```
can't write unknown attribute 'wip_count'
```

확인해 보니 DB 컬럼이 아니라 Ruby 메서드였다:

```ruby
def wip_count
  assigned_tickets.where(aasm_state: %w[assigned in_progress]).count
end
```

실시간으로 활성 티켓 수를 세는 computed field. 값을 바꾸려면 관련 티켓의 상태를 바꾸거나, `max_wip`을 조정해야 한다.

```ruby
# wip_count는 못 바꾸고, max_wip을 늘리면 수용 가능 티켓 수가 늘어난다
user.update_columns(max_wip: 20)
```

---

## Summary

| 문제 | 핵심 원인 | 해결 |
|------|-----------|------|
| `render_success(key: val)` 500 에러 | Ruby 3.0 kwargs/positional 분리 | `{}` 명시적 해시 래핑 |
| Docker 환경 변수 미반영 | `restart`는 컨테이너 재생성 안 함 | `up -d` 사용 |
| NAS `crontab` 없음 | Synology DSM 특성 | `/etc/crontab` 직접 편집 |
| SSH heredoc `!` 오류 | bash 히스토리 확장 | `update_columns` 등 `!` 없는 메서드 사용 |
| SCP Permission denied | root 소유 디렉토리 | base64 + SSH tee 우회 |
| PostgreSQL 배열 업데이트 | `update_column` 직렬화 이슈 | `update_columns` + `|` 연산자 |
| `update_columns` 오류 | computed field를 DB 컬럼으로 착각 | 모델 정의 확인 후 `max_wip` 조정 |

하루 동안 겪은 것들인데 각각은 사소하지만 연속으로 터지니 꽤 피로했다. 특히 Ruby 3.0 kwargs 변경은 마이그레이션 안 한 프로젝트에서 자주 만날 것 같아서 기록해 둔다.
