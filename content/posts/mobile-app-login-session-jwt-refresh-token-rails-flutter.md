---
title: "모바일 앱 로그인이 자꾸 풀리는 진짜 이유 — JWT Refresh Token 아키텍처 완전 정리"
date: 2026-03-23
draft: false
tags: ["JWT", "Flutter", "Rails", "인증", "모바일"]
description: "Flutter + Rails API 환경에서 모바일 앱 로그인이 반복적으로 풀리는 근본 원인을 분석하고, JWT access token TTL, refresh token rotation, Redis 세션 제거, Puma 메모리 최적화까지 단계별로 해결한 실전 기록."
---

모바일 앱을 운영하다 보면 가장 많이 받는 불만 중 하나가 "로그인이 자꾸 풀려요"다. 카카오톡이나 인스타그램은 한 번 로그인하면 직접 로그아웃하기 전까지 영원히 유지되는데, 내 앱은 왜 하루만 지나면 다시 로그인하라고 하는 걸까?

이 글은 Flutter 앱 + Rails 8 API 환경에서 로그인 세션이 반복적으로 풀리는 문제를 추적하고 해결한 과정을 기록한다. 단순히 "TTL을 늘려라"가 아니라, JWT 인증 시스템의 구조적 문제를 하나씩 찾아가는 과정이다.

---

## 증상: 1시간마다 로그인이 풀림

앱을 백그라운드에 두었다가 1시간 후에 열면 로그인 화면으로 돌아간다. 사용 중에는 문제가 없는데, 잠깐 앱을 닫았다 열면 세션이 사라진다.

서버 로그를 확인해보니 이런 패턴이 반복되었다:

```
[TokenRefresh] Found refresh_token in request params
[TokenRefresh] refresh_token_success for user 123
```

Refresh 자체는 성공하고 있었다. 그런데 왜 로그인이 풀릴까?

---

## 원인 1: Access Token TTL이 너무 짧았다

가장 직접적인 원인은 access token의 수명이 **60분**으로 설정되어 있었다는 것이다.

```ruby
# api_token.rb
def self.default_lifespan_for(client_type)
  case client_type
  when 'flutter'
    ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_MINUTES', 60).to_i.minutes
  when 'web', 'pwa'
    ENV.fetch('API_TOKEN_LIFESPAN_WEB_HOURS', 24).to_i.hours
  end
end
```

웹은 24시간인데 모바일은 1시간. 보안 가이드라인에서 "access token은 15-60분이 적당하다"라고 하니까 그대로 따른 것이다. 하지만 이 가이드라인에는 중요한 전제가 빠져 있다.

### Proactive Refresh가 모바일에서는 작동하지 않는다

웹 앱에서는 access token 만료 8분 전에 미리 갱신하는 **proactive refresh** 전략을 쓸 수 있다. 브라우저 탭이 열려 있는 한 타이머가 계속 돌아가기 때문이다.

```dart
// auth_bloc.dart — proactive refresh timer
final refreshTime = timeUntilExpiry - const Duration(minutes: 8);
// 52분 시점에 자동 갱신
```

하지만 모바일에서는 다르다. 사용자가 앱을 백그라운드로 보내면:
1. 타이머가 **중단**된다 (iOS/Android 모두)
2. 60분이 지나면 access token이 만료된다
3. 앱을 다시 열면 만료된 토큰으로 API 호출
4. 401 에러 → reactive refresh 시도

여기서 reactive refresh가 성공하면 괜찮지만, 앱 콜드 스타트 시의 세션 복원 로직에서 문제가 발생했다.

### 해결: 모바일 TTL 24시간으로 변경

```ruby
when 'flutter'
  # 모바일: 24시간 (백그라운드 시 proactive refresh 불가)
  ENV.fetch('API_TOKEN_LIFESPAN_FLUTTER_MINUTES', 1440).to_i.minutes
```

Perplexity로 조사한 결과, **모바일 앱에서 access token 60분은 업계 표준 범위 내이지만, proactive refresh가 불가능한 환경에서는 부적절**하다는 결론이 나왔다. Auth0 문서에서도 모바일 앱은 "offline_access" scope와 함께 충분히 긴 access token을 권장한다.

---

## 원인 2: 앱 시작 시 타임아웃으로 세션이 소실됨

두 번째 문제는 Flutter 앱의 콜드 스타트 로직이었다. 앱이 시작될 때 저장된 토큰을 읽는 과정에 **5초 타임아웃**이 걸려 있었다.

```dart
// 수정 전: 타임아웃 + 에러 시 null 반환 → 로그아웃
final storedRefreshToken = await _authRepository
    .getRefreshToken()
    .timeout(const Duration(seconds: 5))
    .onError<TimeoutException>((error, stackTrace) {
      return null;  // null → 로그아웃 처리!
    });
```

`flutter_secure_storage`는 iOS Keychain / Android Keystore에서 토큰을 읽는다. 이건 로컬 작업이라 보통 밀리초 단위로 끝나지만, 기기 상태에 따라 느릴 수 있다:

- iOS: Keychain이 잠금 상태에서 접근 불가 (`errSecInteractionNotAllowed`)
- Android: KeyStore 초기화 지연 (특히 구형 기기)
- 공통: 앱 업데이트 후 첫 실행 시 Keychain 마이그레이션

**5초 안에 읽지 못하면 null → "refresh token 없음" → 로그아웃**이 되어버리는 구조였다.

### 해결: 타임아웃 제거 + 캐시 fallback

```dart
// 수정 후: 타임아웃 없이 직접 읽기
final storedRefreshToken = await _authRepository.getRefreshToken();
```

`getCurrentUser()`에도 같은 문제가 있었다. API 호출이 5초 안에 실패하면 토큰이 유효해도 로그아웃되었다:

```dart
// 수정 후: 네트워크 실패 시 캐시에서 user 복원
User? user;
try {
  user = await _authRepository
      .getCurrentUser()
      .timeout(const Duration(seconds: 10));
} catch (e) {
  AppLogger.warning('getCurrentUser failed, trying cached user', e);
}
user ??= await _authRepository.getCachedUser();
```

GitHub 이슈를 검색해보면 `flutter_secure_storage`에서 앱 재시작 후 데이터가 null로 반환되는 케이스가 여럿 보고되어 있다. iOS에서는 `KeychainAccessibility.first_unlock` 옵션이 필수인데, 이 설정이 없으면 기기 재부팅 후 첫 잠금 해제 전에는 Keychain에 접근할 수 없다.

---

## 원인 3: Refresh Token도 영구적이지 않았다

앱에서 로그인이 안 풀리려면, refresh token이 **명시적 로그아웃 전까지 영구 유지**되어야 한다. 하지만 서버의 refresh token 설정은 이랬다:

| 설정 | 값 | 문제 |
|------|-----|------|
| 절대 만료 | 90일 | 3개월 후 무조건 로그아웃 |
| 비활성 만료 | 30일 | 한 달 안 쓰면 로그아웃 |

카카오톡을 3개월 안 쓴다고 로그아웃되지는 않는다. 모바일 앱에서는 refresh token의 절대 만료를 사실상 무한으로 설정하고, **rotation**으로 보안을 유지하는 게 표준이다.

### Token Rotation이 핵심이다

Refresh token rotation은 매번 refresh할 때마다:
1. 기존 refresh token을 **폐기**
2. 새 refresh token을 **발급**
3. 새 토큰의 만료 시간을 **다시 10년 후로 설정**

```ruby
def calculate_rotated_expiry(user_agent)
  if self.class.mobile_app_request?(user_agent)
    mobile_lifetime = self.class.mobile_token_lifetime  # 10년
    mobile_lifetime.from_now  # 매번 갱신
  else
    self.class.token_lifetime.from_now
  end
end
```

이렇게 하면 앱을 한 달에 한 번이라도 열면 refresh token이 갱신되어 사실상 영구 유지된다. 30일 비활성 만료는 분실/도난 기기를 위한 최소한의 보안 방어선으로 남겨둔다.

### Reuse Detection으로 보안 확보

"refresh token이 영구적이면 보안 위험 아닌가?"라는 질문이 나올 수 있다. 여기서 **reuse detection**이 중요하다:

```ruby
def reuse_detected?
  revoked?  # 이미 사용(폐기)된 토큰이 다시 사용되면 탐지
end

# 탐지 시: 같은 family의 모든 토큰 폐기 → 재로그인 강제
RefreshToken.revoke_family!(family_id, reason: 'reuse_detected')
```

공격자가 탈취한 refresh token을 사용하면, 정상 사용자가 다음 refresh를 할 때 "이미 폐기된 토큰"임을 감지하고 **전체 토큰 체인을 무효화**한다. Auth0, Firebase 모두 이 패턴을 권장한다.

### 해결: 모바일 refresh token 10년 + rotation

```ruby
# 모바일: 명시적 로그아웃 전까지 영구 (10년, rotation마다 갱신)
def self.mobile_token_lifetime
  ENV.fetch('MOBILE_REFRESH_TOKEN_LIFETIME_DAYS', 3650).to_i.days
end

# 비활성 만료: 30일 유지 (보안 방어선)
def self.inactivity_timeout
  ENV.fetch('REFRESH_TOKEN_INACTIVITY_DAYS', 30).to_i.days
end
```

---

## 보너스: Redis 세션 스토어를 제거하다

로그인 문제를 조사하면서 웹 세션 쪽에서도 문제를 발견했다. Production 환경에서 Redis를 세션 스토어로 사용하고 있었다:

```ruby
# 수정 전: Redis session store
Rails.application.config.session_store :redis_store,
  servers: [{ url: ENV['REDIS_URL'], namespace: 'ainote_session' }],
  expire_after: 1.week,
  same_site: :none,
  secure: true
```

그런데 Render 배포 설정을 확인해보니:

```yaml
# render.yaml
numInstances: 1  # 단일 인스턴스!
```

Redis 세션 스토어는 **멀티 인스턴스 환경에서 세션을 공유**하기 위한 것이다. 단일 인스턴스에서는 불필요할 뿐 아니라 오히려 해롭다:

1. **Render 재배포 시 Redis 연결이 순간적으로 끊김** → 세션 조회 실패 → CSRF 검증 실패 → 로그아웃
2. **`same_site: :none`과 `:lax` 혼용** → 쿠키 전송 불일치
3. **추가 의존성** → 장애 포인트 증가

### Rails 8 Solid Stack으로 Redis 대체

Rails 8은 **Solid Trifecta** (Solid Queue, Solid Cache, Solid Cable)로 Redis 없이도 운영 가능하다:

| 용도 | Before (Redis) | After (Solid) |
|------|---------------|---------------|
| 세션 스토어 | redis_store | cookie_store |
| 캐싱 | Redis | Solid Cache (DB 기반) |
| 백그라운드 잡 | Sidekiq + Redis | Solid Queue (DB 기반) |
| WebSocket | AnyCable + Redis | Solid Cable (DB 기반) |
| Rate limiting | Redis | MemoryStore fallback |

```ruby
# 수정 후: cookie_store (단일 인스턴스에 최적)
Rails.application.config.session_store :cookie_store,
  key: '_ainote_session',
  same_site: :lax,
  secure: Rails.env.production?,
  httponly: true
```

Cookie store는 외부 의존성이 전혀 없고, Render 재배포 시에도 세션이 유지된다. 단일 인스턴스라면 이게 가장 안정적인 선택이다.

향후 멀티 인스턴스로 확장할 때는 Redis가 아니라 `activerecord-session_store`나 Solid Cache 기반 세션을 고려하는 게 Rails 8의 방향성에 맞다.

---

## 보너스: Puma 메모리 최적화

Render Standard 플랜(1GB RAM)에서 health check 에러가 간헐적으로 발생했다:

```
Instance failed: connection reset by peer while running your code
```

원인은 메모리 압박이었다. 기존 Puma 설정:

```ruby
# 수정 전
workers 2       # 2개 프로세스
threads 5, 5    # 프로세스당 5스레드
```

이 설정의 메모리 사용량:
- Master: 40MB
- Worker 1 (CoW): 60-80MB
- Worker 2 (CoW): 60-80MB
- Solid Queue: 25MB
- DB connections: 15MB
- **합계: ~270MB** (피크 시 430MB+)

### Rails 공식 가이드의 권장값

Rails Tuning Performance 가이드와 Puma 메인테이너의 권장사항을 종합하면:

- **Workers**: CPU 코어 수와 동일 (Render Standard = 1 vCPU → **1 worker**)
- **Threads**: 3이 최적 (2025년 Rails 커뮤니티 벤치마크 결론)
- **DB Pool**: threads + 여유분 (Solid Queue용)

```ruby
# 수정 후
max_threads_count = ENV.fetch("RAILS_MAX_THREADS") { 3 }
min_threads_count = ENV.fetch("RAILS_MIN_THREADS") { 2 }
threads min_threads_count, max_threads_count

workers ENV.fetch("WEB_CONCURRENCY") { 1 }  # 1 vCPU = 1 worker
```

```yaml
# database.yml
pool: <%= ENV.fetch("DB_POOL") { ENV.fetch("RAILS_MAX_THREADS") { 3 }.to_i + 3 } %>
```

왜 threads 3인가? Judoscale 블로그의 벤치마크 결과에 따르면, **5 threads는 throughput 대비 latency 손해가 크다**. 3 threads는 5 대비 throughput이 거의 비슷하면서 p95 latency가 훨씬 안정적이다. 이 결론은 DHH가 Rails repo에서 직접 주도한 논의에서도 확인되었고, Rails 8 이후의 기본값이 3으로 변경되었다.

---

## 추가 발견: Google OAuth "데이터 액세스 허용" 이메일

로그인할 때마다 Google에서 이런 이메일이 왔다:

> "일부 Google 계정 데이터에 대한 AI SimpleNote의 액세스를 허용하셨습니다"

원인은 Google Calendar OAuth 연동 코드에서 `prompt: 'consent'`를 사용하고 있었기 때문이다:

```ruby
# 수정 전: 매번 동의 화면 강제
client = Signet::OAuth2::Client.new(
  prompt: 'consent'  # 매번 재동의 요구 → Google 이메일 발송
)

# 수정 후: 계정 선택만 (이미 동의한 경우 스킵)
client = Signet::OAuth2::Client.new(
  prompt: 'select_account'
)
```

`prompt: 'consent'`는 매번 사용자에게 권한 동의를 요구한다. 이미 권한을 부여한 상태에서도 다시 묻고, Google은 "새로 액세스를 허용했다"는 보안 알림 이메일을 보낸다. `select_account`로 바꾸면 이미 동의한 사용자는 계정만 선택하면 된다.

---

## 최종 정리: 모바일 앱 인증 정책

| 조건 | 동작 |
|------|------|
| 앱 사용 중 | access token 24시간, 만료 시 자동 refresh |
| 앱 백그라운드 후 복귀 | access token 갱신 → 세션 유지 |
| 30일 미사용 | refresh token 비활성 만료 → 재로그인 |
| 명시적 로그아웃 | 모든 토큰 폐기 |
| 비밀번호 변경 | 전 세션 폐기 |
| 토큰 탈취 시도 | reuse detection → 토큰 체인 전체 무효화 |

핵심은 **access token은 짧게, refresh token은 길게, rotation으로 보안 유지**다. 모바일 앱에서 로그인이 풀리는 대부분의 원인은 이 세 가지 중 하나의 설정이 잘못된 것이다.

---

## 주의사항과 알려진 함정

1. **flutter_secure_storage iOS 설정**: `KeychainAccessibility.first_unlock`을 반드시 설정하라. 없으면 기기 재부팅 후 토큰을 읽지 못한다.

2. **Dio interceptor에서 refresh 무한 루프**: refresh 요청 자체가 401을 받으면 또 refresh를 시도한다. 반드시 `isRefreshRequest` 체크를 넣어야 한다.

3. **동시 401 처리**: 5개 요청이 동시에 401을 받으면 refresh를 5번 시도한다. mutex나 flag로 **단일 refresh**만 실행되게 해야 한다.

4. **서버 시간 vs 클라이언트 시간**: JWT `exp` claim은 서버 시간 기준이다. 사용자 기기의 시간이 잘못되면 토큰이 즉시 만료로 판정될 수 있다.

5. **Redis 제거 시 health check 확인**: `Rails.cache.redis.ping` 같은 코드가 남아있으면 Solid Cache 환경에서 에러가 난다. 모니터링 코드도 같이 수정해야 한다.

---

관련 글: [API 응답 래퍼와 토큰 파싱 디버깅](/posts/api-response-wrapper-token-parsing-debug/)

## 개발자 추천 장비

{{< coupang url="https://link.coupang.com/re/AFFSDP?lptag=AF3486423&pageKey=8189842355&itemId=23433983921&vendorItemId=90460914324&traceid=V0-153-b89cce56defcbeca&requestid=20260323105137686044907300&token=31850C%7CMIXED&landing_exp=APP_LANDING_A" name="HP 450 프로그래밍 무선 키보드" price="36,600원" img="https://ads-partners.coupang.com/image1/-tKIoE3x8p2aHuvR-naPNG25uUGPYnK0BeMFDahk53vK-f27q9dRoYNa1Pp1CYyeqcDQHkXDvMzCgyYJOCfGjb04Bu7ZQGEFf3wl9l1hr5upJV3kQzL8WsQ5QWit0QggkVsZWc-RHPdMavIgZLjNSRhyj-xe5C5d2t44YcoNiKzJ1SEbf-2JxG1XqEnXIWxcDQhxn69fktf06CmgaFynL97G44fXehjRFdhwngYNpF_ArBGTrycix2Hc8Y2rA8ICUUOqhF4TSgrXOUjPSPDVE6IuHBwfchbD21sWbDHl6FVlA9q34JU=" rocket="true" >}}

{{< coupang-disclosure >}}
