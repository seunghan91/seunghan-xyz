---
title: "Fixing Unnecessary Error Exposure in Flutter Sync Queue"
date: 2025-10-04
draft: false
tags: ["Flutter", "Sync", "Offline-First", "Debugging", "Mobile"]
description: "Analyzing and fixing the issue where retryable failures were treated as blocking failures in a Transactional Outbox pattern sync queue, repeatedly exposing errors to users."
cover:
  image: "/images/og/flutter-sync-queue-aggressive-error-handling.png"
  alt: "Flutter Sync Queue Aggressive Error Handling"
  hidden: true
---


While implementing a Transactional Outbox pattern for offline sync in a mobile app, I discovered that "sync failed" errors were repeatedly shown to users even though synchronization had actually completed successfully.

---

## Symptoms

The app repeatedly threw the following error:

```
AppException: Failed to push changes: AppException: Push completed with failures;
retry count: 2, pending changes remain in queue.
```

Checking server logs confirmed that sync pull was working normally and the data was already synchronized.

## Understanding the Structure: Transactional Outbox Pattern

The app's sync architecture:

```
┌────────────────┐     ┌──────────────┐     ┌────────────────┐
│  Local DB      │────>│  Sync Queue  │────>│  Remote API    │
│  (Drift/SQLite)│     │  (Outbox)    │     │  (Rails)       │
└────────────────┘     └──────────────┘     └────────────────┘
```

1. Local data change -> add pending item to sync queue
2. When `performFullSync()` is called, sync in pull -> push order
3. During push, send each queue item to the server
4. On success, remove from queue; on failure, increment retry count

## Root Cause Analysis

The error handling logic in the `_pushChanges()` method was flawed:

```dart
// Problem code
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
      // 404, 409, 410, 412, 422 -> remove from queue (normal)
      await database.deleteSyncQueueItem(item.id);
      continue;
    }

    // Increment retry count (normal)
    await database.incrementRetryCount(item.id);

    // Problem: retryable failures treated as blocking unconditionally
    if (!shouldRemove) {
      hasBlockingFailure = true;
    }
  }
}

// Problem: throws error if even one item is scheduled for retry
if (hasBlockingFailure) {
  throw SyncException(
    'Push completed with failures; retry count: $failedCount, '
    'pending changes remain in queue.',
  );
}
```

### 3 Core Problems

**1. Double handling: enqueue for retry AND throw error**

The item's retry count was incremented meaning "we will retry later," but simultaneously a `SyncException` was thrown marking the entire sync as failed. If a retry mechanism exists, throwing an error defeats its purpose.

**2. Nested error messages from wrapping**

The thrown `SyncException` got re-wrapped in the upper catch:

```
SyncException -> "Failed to push changes: AppException: Push completed with failures..."
```

This nested message was displayed directly to users.

**3. Excessive retry count**

`_maxRetries = 5` meant even unrecoverable errors were retried 5 times. For temporary network issues, 2-3 retries are sufficient; beyond that, it only increases server load.

## Solution

### Before: Aggressive error propagation

```
Item fails -> add to retry queue + hasBlockingFailure = true
               -> SyncException thrown after loop ends
               -> "Sync failed" shown to user
               -> Same error repeats on next sync
```

### After: Silent retry

```
Item fails -> add to retry queue + warning log
               -> Loop ends normally
               -> Auto-retry on next sync
               -> Remove from queue after 3 failures (give up)
```

Core of the fixed code:

```dart
for (final item in syncQueue) {
  try {
    await _processSyncQueueItem(item);
    await database.deleteSyncQueueItem(item.id);
    successCount++;
  } catch (e, stackTrace) {
    failedCount++;

    // Auth failure (401/403) -> abort immediately (retry is pointless)
    if (e is DioException &&
        (e.response?.statusCode == 401 ||
         e.response?.statusCode == 403)) {
      throw AuthException('Unauthorized');
    }

    // Unrecoverable (404/409/410/412/422) -> remove from queue
    if (_shouldRemoveSyncItem(e)) {
      await database.deleteSyncQueueItem(item.id);
      continue;
    }

    // Retryable -> log warning only, retry on next sync
    await database.incrementRetryCount(item.id);
    if (nextRetryCount >= _maxRetries) {  // 3 times
      await database.deleteSyncQueueItem(item.id);
    }
    // No error thrown -> sync treated as normally completed
  }
}
// No hasBlockingFailure logic -> normal termination
```

### Error Classification System

| HTTP Status | Classification | Handling |
|------------|------|------|
| 401, 403 | Auth failure | Throw immediately (retry is pointless) |
| 404, 410 | Resource not found | Remove from queue (already deleted on server) |
| 409, 412 | Conflict/version mismatch | Remove from queue (client data is stale) |
| 422 | Validation failure | Remove from queue (data itself is invalid) |
| 5xx, timeout | Temporary server/network issue | Retry queue (up to 3 times) |

### Retry Count Adjustment

```dart
// Before
static const int _maxRetries = 5;  // Excessive

// After
static const int _maxRetries = 3;  // Sufficient
```

In mobile apps, sync retries typically run at 30-second intervals. 3 retries means about 1.5 minutes of retrying, and most temporary network issues recover within this window. Waiting up to 5 retries (2.5 minutes) is unnecessary from a user experience perspective.

## Lessons Learned

### 1. If a retry mechanism exists, do not throw errors

Putting an item in the retry queue means "we will try again later." But simultaneously throwing an error says "it failed right now" -- a contradiction. The user sees "sync failed," but in reality it will auto-resolve shortly through retry.

**Principle: If scheduled for retry, log a warning. If giving up, log an error.**

### 2. Only auth failures are worth throwing immediately

The only case where sync push should abort immediately is authentication failure. Token expiry, lack of permissions, etc. will not resolve with retries, so the user needs to be asked to re-login. Everything else can be handled with "try again later."

### 3. Cross-verify server logs and client errors

When debugging this issue, only after confirming `SYNC COMPLETED SUCCESSFULLY` in server logs could I tell "this is a client-side problem." Looking only at client error messages, it is easy to mistake it for a server issue.

### 4. Only wrap errors when adding information

```dart
// Bad: wrapping without adding information
throw SyncException('Failed to push changes: $e');

// Good: adding context information
throw SyncException('Failed to push changes', cause: e, context: {...});
```

Converting the original error to a string and embedding it in a new error creates nested messages like `AppException: Failed to push changes: AppException: Push completed with...`.

---

## Related Patterns

- **Transactional Outbox Pattern**: Bundle local DB changes and sync queue additions into a single transaction to ensure data consistency
- **Exponential Backoff + Jitter**: Progressively increase retry intervals with some randomness to distribute server load
- **Circuit Breaker**: Block requests for a period after consecutive failures (in this case, removing from queue after 3 failures serves a similar function)
