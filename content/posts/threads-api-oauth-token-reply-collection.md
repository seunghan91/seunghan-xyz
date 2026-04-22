---
title: "Threads API로 내 게시물 댓글 151개 수집하기 — OAuth 토큰부터 pagination까지"
date: 2026-04-20T09:00:00+09:00
draft: false
tags: ["threads-api", "oauth", "meta-graph-api", "scraping", "curl"]
categories: ["Dev"]
description: "Meta Threads API OAuth 2.0 flow로 단기/장기 토큰 발급받고, /replies 엔드포인트로 커뮤니티 모집글 댓글 151개를 수집한 과정. 실제 삽질 포인트와 curl 명령어 포함."
---

커뮤니티 모집글을 Threads에 올려서 댓글이 잔뜩 달렸다. 참가자에게 DM으로 설문 링크를 돌리려면 댓글 작성자 `@handle` 목록이 필요한데, 수동으로 스크롤하며 복사하는 건 100개 넘어가면 현실적이지 않다.

Meta가 2024년에 공식 Threads API를 열었다는 건 알고 있었지만 실제로 써본 적은 없었다. "Instagram Graph API랑 뭔가 다른 것 같은데 뭐가 다른지 모르겠다" 상태에서 시작해, 삽질하면서 151개 댓글 / 151명 유니크 작성자를 추출하기까지의 과정을 정리한다. 공식 문서에는 흩어져 있고, 커뮤니티 자료는 대부분 게시 자동화(content publish) 쪽에 치중돼 있어서 **"읽기(read replies)"만 필요한 케이스**를 한 페이지에 모은 게 없었다.

이 글에서는 (1) Meta 개발자 앱을 만들고 Threads API use case를 고르는 것부터 (2) OAuth code를 받아 60일 장기 토큰으로 교환하고 (3) 실제 `/replies` 엔드포인트에 pagination 호출을 걸어 전체 데이터를 내려받는 것까지를 실제 curl 명령어와 함께 다룬다.

## Threads API가 왜 따로 있나

결론부터 말하면 Threads API는 **Instagram Graph API와 완전히 분리된 별도 스택**이다. 겉보기엔 Meta 생태계의 Instagram 확장으로 보이지만, 내부적으로는 엔드포인트·인증 flow·OAuth grant type까지 전부 다르다.

| 구분 | Threads API | Instagram Graph API | Facebook Graph API |
|------|-------------|--------------------|--------------------|
| Base URL | `graph.threads.net` | `graph.facebook.com` | `graph.facebook.com` |
| Authorize URL | `threads.net/oauth/authorize` | `api.instagram.com/oauth/authorize` | `facebook.com/dialog/oauth` |
| Token Exchange URL | `graph.threads.net/oauth/access_token` | `api.instagram.com/oauth/access_token` | `graph.facebook.com/oauth/access_token` |
| Long-lived Grant | `th_exchange_token` | `ig_exchange_token` | `fb_exchange_token` |
| Scope Format | comma-separated string | array | array |
| Versioning | `v1.0` 하나뿐 | versionless | v17.0 ~ v23.0 |

즉 Facebook 앱으로 발급받은 토큰은 Threads에서 **전혀 작동하지 않는다.** 여러 플랫폼 통합 봇을 만들 때는 플랫폼별로 별개의 OAuth 흐름을 따로 구축해야 한다. 이게 Threads 연동을 처음 붙일 때 제일 헷갈리는 부분이다.

## Step 1 — Meta 개발자 앱 생성

[developers.facebook.com](https://developers.facebook.com/apps) 에서 **Create App**.

여기서 첫 번째 함정이 있다. Use case 선택 단계에서 **"Access the Threads API" 하나만** 체크해야 한다. 처음에 "기왕 만드는 김에 나중에 쓸지도 모르니까"라면서 Messenger, Instagram 메시지 콘텐츠 관리, 다른 웹사이트에 Threads 콘텐츠, Instagram 퍼가기까지 전부 체크했다가, 권한 탭이 사용 사례별로 따로 생기면서 UI가 산만해지고 어떤 permission이 어느 use case에 속하는지 알 수 없게 됐다. 결국 앱을 지우고 다시 만들었다.

**교훈: use case는 최소한만.** 나중에 필요해지면 use case를 추가하는 건 언제든 가능하지만, 처음부터 많이 넣으면 대시보드가 복잡해진다.

## Step 2 — Permissions와 Settings

앱 생성 후 좌측 사이드바 **"Access the Threads API → Customize"** 로 들어가면 Permissions / Settings / Token Generator 같은 탭이 나온다.

### Permissions 탭

Threads API가 제공하는 permission은 크게 이렇다:

| Permission | 용도 | 비고 |
|------------|------|------|
| `threads_basic` | 본인 프로필 정보 | 기본 |
| `threads_content_publish` | 새 게시물 작성 | |
| `threads_delete` | 게시물 삭제 | |
| `threads_manage_insights` | 분석 데이터 조회 | |
| `threads_manage_mentions` | 멘션 조회/관리 | |
| `threads_manage_replies` | 댓글 작성/숨김/답글 차단 | |
| `threads_read_replies` | 내 게시물 댓글 읽기 | **댓글 수집 필수** |
| `threads_profile_discovery` | 다른 사람 공개 프로필 조회 | ⚠️ App Review 필요 |
| `threads_keyword_search` | 키워드 검색 | |
| `threads_location_tagging` | 위치 태그 | |
| `threads_share_to_instagram` | Instagram 동시 게시 | |

댓글 수집만 할 거면 `threads_basic` + `threads_read_replies` 두 개면 충분하다. 자동 답글 기능까지 미리 활성화할 거면 `threads_manage_replies` 추가. **`threads_profile_discovery`는 추가하지 않는 걸 권장한다.** 댓글 응답에 이미 `username`이 포함돼 있어서 DM 보낼 핸들 목록 뽑는 데는 필요 없고, App Review 심사 리스크가 크다.

### Settings 탭

세 개 필드가 있다:

```
Redirect Callback URLs: https://localhost/
Uninstall Callback URL: https://localhost/uninstall
Data Deletion Request URL: https://localhost/delete
```

로컬 테스트 단계에서는 `https://localhost/`만 넣으면 된다. 정식 서비스 배포 시에는 실제 서버 URL로 교체(`https://mydomain.com/auth/threads/callback` 등). **중요: redirect_uri는 OAuth 교환할 때 정확히 일치해야 한다.** 한 글자라도 다르면 "Invalid parameter" 에러.

### App Roles — Tester 추가

Threads API는 **Tester로 등록된 계정만** 인증 플로우를 진행할 수 있다. Roles 탭에서 본인 Threads 계정을 Tester로 추가 → Threads 앱에서 초대 수락. 수락 안 하면 `authorize` URL 방문 시 "This app is in development mode" 에러가 뜬다.

## Step 3 — OAuth authorize URL 방문

여기가 본격적인 토큰 발급 시작점이다. 아래 URL을 브라우저 주소창에 붙여넣는다:

```
https://threads.net/oauth/authorize
  ?client_id=YOUR_APP_ID
  &redirect_uri=https://localhost/
  &scope=threads_basic,threads_read_replies,threads_manage_replies
  &response_type=code
```

scope는 **comma-separated string**이다. Instagram/Facebook처럼 배열이나 공백 구분자를 쓰면 안 된다.

승인 버튼을 누르면 `https://localhost/?code=AQBccIwXXsW4sS...` 로 리다이렉트된다. 브라우저는 당연히 "localhost 연결 실패" 에러를 띄우지만 **상관없다.** 중요한 건 주소창의 `code=...` 값이다. 이 값을 복사한다.

⚠️ **authorization code는 단발성(single-use)이다.** 한 번 exchange API에 던지면 그걸로 끝. 두 번째로 똑같은 코드로 호출하면:

```json
{
  "error": {
    "code": 100,
    "error_subcode": 4279030,
    "error_user_title": "유효하지 않은 인증 코드 지정됨",
    "error_user_msg": "유효하지 않은 인증 코드입니다. 이유: used_authorization_code."
  }
}
```

나는 첫 번째 curl에서 stdout이 필터링 도구에 의해 가려진 상태로 실행돼서 code가 소진된 줄 모르고 두 번째 curl을 때렸다가 이 에러로 5분을 날렸다. **한 번에 제대로 실행되도록 준비하고 호출할 것.**

## Step 4 — Code → 단기 토큰 (1시간)

```bash
curl -X POST https://graph.threads.net/oauth/access_token \
  -F client_id=YOUR_APP_ID \
  -F client_secret=YOUR_APP_SECRET \
  -F grant_type=authorization_code \
  -F redirect_uri=https://localhost/ \
  -F code=AQBccIwXXsW4sS...
```

응답:

```json
{
  "access_token": "THAAfCAtVdrF5BYm...",
  "user_id": 26074073295626765
}
```

이 토큰은 **1시간** 후 만료된다. 당장 쓸 게 아니면 다음 단계로 바로 넘어가서 장기 토큰으로 교환한다.

## Step 5 — 단기 → 장기 토큰 (60일)

```bash
curl -G https://graph.threads.net/access_token \
  --data-urlencode "grant_type=th_exchange_token" \
  --data-urlencode "client_secret=YOUR_APP_SECRET" \
  --data-urlencode "access_token=THAAfCAtVdrF5BYm..."
```

응답:

```json
{
  "access_token": "THAAfCAtVdrF5BYll6...",
  "token_type": "bearer",
  "expires_in": 5184000
}
```

`expires_in` 5,184,000초 ≈ **60일**. 이 값을 `.env`에 저장하면 두 달 동안 재인증 없이 쓸 수 있다.

⚠️ **60일 후 처리**는 두 가지 선택지가 있다:
1. `GET /refresh_access_token?grant_type=th_refresh_token&access_token=LONG_TOKEN` 호출해서 또 60일 연장
2. 만료되면 다시 OAuth 플로우 처음부터

refresh는 장기 토큰이 **아직 유효한 동안에만** 가능하다. 만료되면 새로 authorize 받아야 한다. 크론으로 55일째에 자동 refresh 걸어두는 게 깔끔.

## Step 6 — 본인 프로필 확인 (sanity check)

토큰이 제대로 발급됐는지 먼저 확인한다:

```bash
curl -G https://graph.threads.net/v1.0/me \
  --data-urlencode "fields=id,username,name,threads_biography" \
  --data-urlencode "access_token=THAAfCAtVdrF5BYll6..."
```

```json
{
  "id": "26074073295626765",
  "username": "seungha__n",
  "name": "김승한",
  "threads_biography": "한국거래소(KRX)에서 \nAI와 함께 일하는 방식을 만듭니다."
}
```

본인 username과 bio가 정상 출력되면 통과.

## Step 7 — 게시물 numeric ID 찾기 (shortcode 함정)

여기가 Threads API에서 가장 혼란스러운 부분이다. Threads 게시물 URL을 보면 이렇다:

```
https://www.threads.net/@seungha__n/post/DXQ_OjhmsWN
```

뒤쪽 `DXQ_OjhmsWN`은 **shortcode**다. 사람이 읽을 수 있는 short ID. 그런데 API 엔드포인트는 대부분 **numeric media ID**를 요구한다.

`/replies?post_id=DXQ_OjhmsWN` 같은 식으로 넣으면 "Invalid parameter". shortcode → numeric ID 변환 공개 API는 없다. 대신 본인 게시물 목록을 조회해서 매핑을 직접 추출해야 한다.

```bash
curl -G "https://graph.threads.net/v1.0/me/threads" \
  --data-urlencode "fields=id,shortcode,text,timestamp,permalink,reply_count" \
  --data-urlencode "limit=25" \
  --data-urlencode "access_token=THAAfCAtVdrF5BYll6..."
```

응답에서 원하는 shortcode를 찾아 `id` 필드를 뽑는다:

```json
{
  "data": [
    {
      "id": "18090652949273588",
      "shortcode": "DXQ_OjhmsWN",
      "text": "여의도에서 저녁 주 1회 평일이나 주말에...",
      "reply_count": 0,
      "timestamp": "2026-04-18T..."
    }
  ]
}
```

여기서 두 번째 함정이 있다. **`reply_count`가 0으로 표시되는데 실제로는 100+ 댓글이 있을 수 있다.** 이건 Meta 내부의 집계 캐시가 느리게 업데이트되는 것 같고, `/replies` 엔드포인트를 **직접 호출하면** 실제 데이터는 정상적으로 나온다.

처음엔 "아 댓글이 정말 0개인가 봐, API 연동 잘못됐나?" 하고 30분 헤맸다. 그냥 reply_count는 참고만 하고 바로 `/replies` 때리는 게 정답이다.

## Step 8 — 댓글 pagination 수집

이제 진짜 댓글 끌어오기. Graph API는 cursor-based pagination을 쓰기 때문에 `paging.next` URL을 계속 따라가야 한다:

```bash
#!/usr/bin/env bash
TOKEN="THAAfCAtVdrF5BYll6..."
POST_ID="18090652949273588"
URL="https://graph.threads.net/v1.0/$POST_ID/replies?fields=id,username,text,timestamp,permalink,has_replies,hide_status&limit=100&access_token=$TOKEN"
PAGE=0

while [ -n "$URL" ] && [ "$URL" != "null" ]; do
  PAGE=$((PAGE+1))
  OUT=/tmp/threads_page_$PAGE.json
  curl -s "$URL" -o "$OUT"
  COUNT=$(python3 -c "import json; print(len(json.load(open('$OUT')).get('data', [])))")
  NEXT=$(python3 -c "import json; d=json.load(open('$OUT')); print(d.get('paging', {}).get('next') or '')")
  echo "Page $PAGE: $COUNT replies"
  URL="$NEXT"
done
```

결과:

```
Page 1: 100 replies
Page 2: 51 replies
```

**총 151개 댓글, 모두 유니크 작성자.** 소요 시간 약 3초.

페이지를 모두 합쳐서 username만 뽑으면 바로 DM 발송용 명단이 나온다:

```python
import json, glob

all_replies = []
for f in sorted(glob.glob('/tmp/threads_page_*.json')):
    all_replies.extend(json.load(open(f)).get('data', []))

unique_users = sorted({r.get('username', '') for r in all_replies if r.get('username')})
print(f"Total: {len(all_replies)}, Unique: {len(unique_users)}")
# Total: 151, Unique: 151
```

## `/replies`가 반환하는 필드

실제로 쓸모 있는 정보가 뭐 있는지 정리:

| 필드 | 타입 | 내용 |
|------|------|------|
| `id` | string | Threads 댓글 ID (numeric) |
| `username` | string | 작성자 핸들 (`@` 제외) |
| `text` | string | 댓글 본문 |
| `timestamp` | ISO 8601 | 작성 시각 |
| `permalink` | URL | 웹에서 보는 URL |
| `has_replies` | bool | 이 댓글에 답글이 달렸는지 |
| `replied_to` | object | 원래 게시물/댓글 참조 |
| `hide_status` | string | 숨김 상태 (NOT_HUSH / HIDDEN 등) |
| `root_post` | object | 최상위 게시물 |

**작성자의 display_name이나 bio는 여기 없다.** 코멘터의 프로필 정보가 필요하면 `threads_profile_discovery` 권한이 필요한데, 앞서 말했듯 App Review를 통과해야 하고 "커뮤니티 운영" 목적으로는 승인 잘 안 난다.

실용적으로는 username으로 `https://www.threads.net/@username` 방문해서 Playwright로 bio만 스크랩하거나, 수동으로 필요한 사람만 확인하는 게 낫다.

## 실전 사용 시나리오

개발하다 느낀 건, 이 flow는 딱 세 가지 용도에 잘 맞는다:

1. **커뮤니티 운영** — 모집글 댓글로 참여자 추출, 설문 링크 배포, 주간 공지 자동화
2. **콘텐츠 성과 측정** — 본인 게시물들의 reply 패턴 분석, 어떤 주제가 반응이 좋은지
3. **자동 답글 봇** — `threads_manage_replies` 추가하면 특정 키워드 댓글에 자동 DM 링크 발송 가능

반대로 잘 **안 맞는** 용도:
- 다른 사람 게시물 댓글 수집 — 공식 API로는 불가 (스크래핑 영역)
- 트렌드 분석 / 키워드 모니터링 — `threads_keyword_search` 권한이 있지만 제한적
- 팔로워 목록 추출 — 현재 API 미제공

## 주의사항

### 토큰은 60일마다 refresh

Threads는 자동 token refresh를 제공하지 않는다. 수동으로 refresh 엔드포인트를 호출하거나, 아니면 60일 지나서 OAuth 처음부터 다시. production 시스템이면 cron으로 55일째에 자동 refresh 걸어두는 게 안전.

```bash
curl -G https://graph.threads.net/refresh_access_token \
  --data-urlencode "grant_type=th_refresh_token" \
  --data-urlencode "access_token=CURRENT_LONG_TOKEN"
```

### Rate limit

Threads API의 정확한 rate limit은 공개돼 있지 않지만, Meta Graph API 계열은 보통 **앱당 200 call/hour**가 기본이고 users/tokens로 늘어난다. 댓글 수집 목적이면 페이지네이션 총 몇 번 때리는 정도라 전혀 문제 없음. 몇만 개 댓글을 크롤한다면 exponential backoff 필수.

### HTTPS만

모든 엔드포인트는 HTTPS. `redirect_uri`에 `http://localhost/`(s 없음)를 등록하면 authorize URL에서 에러. 로컬 테스트도 `https://`로 넣어야 한다. 브라우저가 인증서 오류로 최종 페이지를 못 띄우지만 code 추출엔 지장 없음.

### App Review 언제 필요한가

Development mode에서는 Tester(본인 계정)만 인증 가능. 일반 Threads 사용자의 앱 사용을 허용하려면 App Review 통과 필요. 단순 본인 계정 데이터 수집용이면 Development mode로 계속 유지해도 무방하다.

### 민감한 권한은 App Review 무겁다

`threads_profile_discovery`, `threads_keyword_search` 같은 건 사용 목적을 상세 서술하고 스크린 녹화 데모까지 요구한다. 불필요하면 절대 추가하지 말 것. 권한이 많을수록 심사 난이도가 올라간다.

## 결론

Meta Threads API로 **내 게시물 댓글만 수집**하는 정도는 훨씬 간단할 줄 알았는데 첫 회 세팅에만 1시간 정도 썼다. Instagram/Facebook API 경험이 있어도 endpoint와 grant type이 전부 달라서 따로 익혀야 했고, shortcode vs numeric ID / reply_count 캐시 이슈 / code 단발성 같은 함정도 있었다.

전체 flow를 한 줄로 요약하면:

```
Meta 앱 생성 → Threads API use case 선택 → permissions 3개 추가 
→ redirect URL 등록 → Tester 초대 수락 
→ authorize URL로 code 받기 → code → 1시간 토큰 → 60일 토큰 교환
→ /me/threads로 게시물 numeric ID 찾기 
→ /replies 페이지네이션
```

한 번 해두면 `.env`에 박아놓고 계속 재사용 가능하니까, 커뮤니티 운영이나 본인 게시물 분석 자동화할 계획이 있으면 충분히 투자할 만한 시간이다. 다음 단계는 수집한 댓글 데이터를 `SurveyResponse` 같은 DB 테이블에 연결해서 "댓글 단 사람 → 설문 응답자 → 스터디 배정" 파이프라인을 자동화하는 쪽. 그건 다음 글에서.

---

**관련 글:**
- [ActiveRecord 배치 upsert로 151건 import 빠르게 처리하기](https://seunghan.xyz/posts/)
- [OAuth 2.0 single-use code 구조 이해하기](https://seunghan.xyz/posts/)
