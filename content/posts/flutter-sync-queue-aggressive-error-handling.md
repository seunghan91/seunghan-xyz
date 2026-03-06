---
title: "Flutter Sync Queue에서 불필요한 에러가 반복 노출되는 문제 해결"
date: 2025-10-04
draft: false
tags: ["Flutter", "Sync", "Offline-First", "디버깅", "모바일"]
description: "Transactional Outbox 패턴 기반 sync queue에서 retryable failure를 blocking failure로 취급하여 사용자에게 에러가 반복 노출되던 문제를 분석하고 해결한 과정"
cover:
  image: "/images/og/flutter-sync-queue-aggressive-error-handling.png"
  alt: "Flutter Sync Queue Aggressive Error Handling"
  hidden: true
---

모바일 앱에서 오프라인 동기화를 위해 Transactional Outbox 패턴을 구현하던 중, 동기화가 실제로는 정상 완료되었는데도 "동기화 실패" 에러가 반복적으로 사용자에게 노출되는 문제를 발견했다.

---

## 현상

앱에서 다음과 같은 에러가 반복적으로 발생했다:

```
AppException: Failed to push changes: AppException: Push completed with failures;
retry count: 2, pending changes remain in queue.
```

서버 로그를 확인하면 동기화 pull은 정상 동작하고, 실제 데이터도 이미 동기화된 상태였다.

## 구조 파악: Transactional Outbox 패턴

앱의 동기화 구조는 다음과 같다:

```
┌────────────────┐     ┌──────────────┐     ┌────────────────┐
│  Local DB      │────▶│  Sync Queue  │────▶│  Remote API    │
│  (Drift/SQLite)│     │  (Outbox)    │     │  (Rails)       │
└────────────────┘     └──────────────┘     └────────────────┘
```

1. 로컬에서 데이터 변경 → sync queue에 pending 아이템 추가
2. `performFullSync()` 호출 시 pull → push 순서로 동기화
3. push 단계에서 queue의 각 아이템을 서버에 전송
4. 성공하면 queue에서 제거, 실패하면 retry count 증가

## 원인 분석

`_pushChanges()` 메서드의 에러 처리 로직에 문제가 있었다:

```dart
// 문제의 코드
var hasBlockingFailure = false;

for (final item in syncQueue) {
  try {
    await _processSyncQueueItem(item);
    await database.deleteSyncQueueItem(item.id);
    successCount++;
  } catch (e) {
    failedCount++;

    final shouldRemove = _shouldRemoveSyncItem(e);

    if (shouldRemove) {
      // 404, 409, 410, 412, 422 → 큐에서 제거 (정상)
      await database.deleteSyncQueueItem(item.id);
      continue;
    }

    // retry count 증가 (정상)
    await database.incrementRetryCount(item.id);

    // ❌ 문제: retryable한 실패도 무조건 blocking으로 취급
    if (!shouldRemove) {
      hasBlockingFailure = true;
    }
  }
}

// ❌ 문제: retry 예정인 아이템이 하나라도 있으면 에러 throw
if (hasBlockingFailure) {
  throw SyncException(
    'Push completed with failures; retry count: $failedCount, '
    'pending changes remain in queue.',
  );
}
```

### 핵심 문제 3가지

**1. retry 큐에 넣고 에러도 던지는 이중처리**

아이템의 retry count를 증가시켜 "다음에 재시도하겠다"고 해놓고, 동시에 `SyncException`을 throw해서 전체 sync를 실패로 처리했다. retry 메커니즘이 있는데 에러를 throw하면 retry의 의미가 없다.

**2. 에러 래핑으로 메시지가 중첩**

throw된 `SyncException`이 상위 catch에서 다시 래핑되면서:

```
SyncException → "Failed to push changes: AppException: Push completed with failures..."
```

이 중첩된 메시지가 사용자에게 그대로 노출되었다.

**3. 과도한 retry 횟수**

`_maxRetries = 5`로 설정되어 있어, 실제로는 복구 불가능한 에러도 5번이나 재시도했다. 네트워크 일시 장애라면 2-3번이면 충분하고, 그 이상은 서버 부하만 증가시킨다.

## 해결

### Before: 공격적인 에러 전파

```
아이템 실패 → retry 큐에 추가 + hasBlockingFailure = true
               → 루프 종료 후 SyncException throw
               → 사용자에게 "동기화 실패" 표시
               → 다음 sync에서도 같은 에러 반복
```

### After: Silent retry

```
아이템 실패 → retry 큐에 추가 + warning 로그
               → 루프 정상 종료
               → 다음 sync에서 자동 재시도
               → 3번 실패 시 큐에서 제거 (포기)
```

수정된 코드의 핵심:

```dart
for (final item in syncQueue) {
  try {
    await _processSyncQueueItem(item);
    await database.deleteSyncQueueItem(item.id);
    successCount++;
  } catch (e, stackTrace) {
    failedCount++;

    // Auth 실패(401/403) → 즉시 중단 (재시도 무의미)
    if (e is DioException &&
        (e.response?.statusCode == 401 ||
         e.response?.statusCode == 403)) {
      throw AuthException('Unauthorized');
    }

    // Unrecoverable (404/409/410/412/422) → 큐에서 제거
    if (_shouldRemoveSyncItem(e)) {
      await database.deleteSyncQueueItem(item.id);
      continue;
    }

    // Retryable → warning만 남기고 다음 sync 때 재시도
    await database.incrementRetryCount(item.id);
    if (nextRetryCount >= _maxRetries) {  // 3회
      await database.deleteSyncQueueItem(item.id);
    }
    // ✅ 에러를 throw하지 않음 → sync는 정상 완료로 처리
  }
}
// ✅ hasBlockingFailure 로직 없음 → 정상 종료
```

### 에러 분류 체계

| HTTP Status | 분류 | 처리 |
|------------|------|------|
| 401, 403 | Auth 실패 | 즉시 throw (재시도 무의미) |
| 404, 410 | 리소스 없음 | 큐에서 제거 (서버에서 이미 삭제) |
| 409, 412 | 충돌/버전 불일치 | 큐에서 제거 (클라이언트 데이터 낡음) |
| 422 | 유효성 검증 실패 | 큐에서 제거 (데이터 자체가 잘못됨) |
| 5xx, timeout | 서버/네트워크 일시 장애 | retry 큐 (3회까지) |

### Retry 횟수 조정

```dart
// Before
static const int _maxRetries = 5;  // 과도함

// After
static const int _maxRetries = 3;  // 충분함
```

모바일 앱에서 sync retry는 보통 30초 간격으로 실행된다. 3회면 약 1.5분간 재시도하는 셈이고, 대부분의 일시적 네트워크 장애는 이 안에 복구된다. 5회(2.5분)까지 기다리는 것은 사용자 경험 측면에서도 불필요하다.

## 교훈

### 1. Retry 메커니즘이 있으면 에러를 throw하지 마라

retry 큐에 넣었다는 것은 "나중에 다시 시도하겠다"는 의미다. 그런데 동시에 에러를 throw하면 "지금 실패했다"고 알리는 것이므로 모순이다. 사용자 입장에서는 "동기화 실패"를 보게 되지만, 실제로는 잠시 후 자동으로 재시도되어 해결된다.

**원칙: retry 예정이면 warning, 포기했으면 error.**

### 2. Auth 실패만 즉시 throw할 가치가 있다

sync push에서 즉시 중단해야 하는 유일한 경우는 인증 실패다. 토큰 만료, 권한 없음 등은 재시도해도 해결되지 않으므로 사용자에게 재로그인을 요청해야 한다. 나머지는 모두 "나중에 다시"로 처리 가능하다.

### 3. 서버 로그와 클라이언트 에러를 교차 검증하라

이번 문제를 디버깅할 때, 서버 로그에서 `SYNC COMPLETED SUCCESSFULLY`를 확인하고 나서야 "이건 클라이언트 쪽 문제"라는 것을 알 수 있었다. 클라이언트 에러 메시지만 보면 서버 문제로 오해하기 쉽다.

### 4. 에러 래핑은 정보를 추가할 때만

```dart
// Bad: 정보 추가 없이 래핑만
throw SyncException('Failed to push changes: $e');

// Good: 맥락 정보 추가
throw SyncException('Failed to push changes', cause: e, context: {...});
```

원본 에러를 문자열로 변환해서 새 에러에 넣으면 `AppException: Failed to push changes: AppException: Push completed with...` 같은 중첩 메시지가 생긴다.

---

## 관련 패턴

- **Transactional Outbox Pattern**: 로컬 DB 변경과 sync queue 추가를 하나의 트랜잭션으로 묶어 데이터 일관성 보장
- **Exponential Backoff + Jitter**: retry 간격을 점진적으로 늘리되, 약간의 랜덤성을 추가해 서버 부하 분산
- **Circuit Breaker**: 연속 실패 시 일정 기간 요청을 차단 (이번 케이스에서는 3회 실패 후 큐에서 제거하는 방식으로 유사하게 동작)
