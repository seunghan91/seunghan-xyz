---
title: "Flutter IAP Store Beta Mode Design and Purchase Logic Hardening"
date: 2025-11-08
draft: false
tags: ["Flutter", "IAP", "In-App Purchase", "Beta", "StoreKit", "BLoC"]
description: "How to handle the store screen during open beta, preventing IAP Restore duplicate credits, protecting unauthenticated user credits, and other purchase logic gaps found in practice."
cover:
  image: "/images/og/flutter-store-beta-mode-purchase-logic.png"
  alt: "Flutter Store Beta Mode Purchase Logic"
  hidden: true
---

When implementing IAP (In-App Purchase) in a Flutter app and running an open beta, gaps like "it is beta but the store shows paid prices" or "credits are duplicated on Restore" start to surface. Here are the issues I encountered and how they were resolved.

---

## 1. The Contradiction Between Beta Mode and the Store

### Problem

```dart
// constants.dart
static const bool isOpenBeta = true;
```

When `isOpenBeta = true`, `spendCredits()` does not deduct credits. This means AI features are free.

```dart
// credit_repository.dart
Future<bool> spendCredits(int amount, String reason) async {
  if (AppConstants.isOpenBeta) {
    // No credit deduction — free
    await _addTransaction(CreditTransaction(
      amount: 0,
      reason: '$reason (Beta - Free)',
    ));
    return true;
  }
  // ... actual deduction logic
}
```

However, the store screen was still showing prices like $2.99, $9.99, $24.99 with purchase buttons active. It is confusing for users -- is it beta or are you charging money?

### Solution: Apply `isOpenBeta` Branching Across the Entire Store

```dart
// store_screen.dart
final isBeta = AppConstants.isOpenBeta;

// 1. AppBar title branching
title: Text(isBeta ? s.store : s.buyCredits),

// 2. Add beta banner
if (isBeta) ...[
  _BetaBanner(),  // "Free during Open Beta" notice
  const SizedBox(height: 20),
],

// 3. Credit pack description branching
Text(
  isBeta ? s.freeDuringBeta : s.oneCreditOneUpscale,
  style: UnmaskTypography.bodySmall.copyWith(
    color: isBeta ? UnmaskColors.success : UnmaskColors.textSubtle,
  ),
),

// 4. Card price → FREE, button disabled
_CreditPackCard(
  product: product,
  isBeta: isBeta,
  onBuy: isBeta ? null : () => _handleBuy(context, product),
),

// 5. Hide payment/restore UI at the bottom
if (!isBeta) ...[
  // Restore Purchases, Payment method note
],
```

Branching in the card widget as well:

```dart
// Price display
Text(isBeta ? s.free : product.priceFormatted),

// Button text
Text(isBeta ? s.comingSoon : s.buy),

// Overall opacity
Opacity(opacity: isBeta ? 0.5 : 1.0, child: ...)
```

**Key point**: A single `isOpenBeta` flag switches the entire store between beta and production mode. When the time comes, just change it to `false` and the paid transition is complete.

---

## 2. Preventing Duplicate Credits on Restore Purchases

### Problem

When `restorePurchases()` is called, previous purchase history flows through the `purchaseStream`. The existing code treated `PurchaseStatus.restored` identically to `PurchaseStatus.purchased`.

```dart
case PurchaseStatus.purchased:
case PurchaseStatus.restored:
  // Both deliver credits the same way → duplicates!
  await _deliverCredits(product, purchase);
```

Every time the user presses Restore, credits keep stacking up.

### Solution: Deduplication with transaction_id

```dart
case PurchaseStatus.purchased:
case PurchaseStatus.restored:
  // Deduplication check only for Restore
  if (purchase.status == PurchaseStatus.restored) {
    final alreadyDelivered = await _isAlreadyDelivered(
      purchase.purchaseID,
    );
    if (alreadyDelivered) {
      await _purchaseRepo.completeIapPurchase(purchase);
      emit(state.copyWith(status: PurchaseFlowStatus.ready));
      break;  // Already delivered → skip
    }
  }
  // ... normal delivery logic
```

Query by `transaction_id` on the server (Supabase):

```dart
Future<bool> _isAlreadyDelivered(String? transactionId) async {
  if (transactionId == null || transactionId.isEmpty) return false;
  try {
    final result = await Supabase.instance.client
        .from('purchases')
        .select('id')
        .eq('user_id', userId)
        .eq('transaction_id', transactionId)
        .limit(1);
    return (result as List).isNotEmpty;
  } catch (e) {
    // If check fails, allow delivery (better than taking money and not giving credits)
    return false;
  }
}
```

**Design principle**: If the deduplication check fails, return `false` to allow delivery. "Receiving credits you already got" is far less bad than "paying but not receiving credits."

---

## 3. Protecting Credits for Unauthenticated Users

### Problem

Original code:

```dart
Future<void> _deliverCredits(CreditProduct product, PurchaseDetails purchase) async {
  final userId = Supabase.instance.client.auth.currentUser?.id;
  if (userId == null) {
    throw Exception('User not authenticated');  // Credits lost
  }
  // ...
}
```

If the user completed payment but the auth session expired, the exception is thrown and credits are not delivered. The worst scenario: **money is charged but credits are not received**.

### Solution: Deliver Locally at Minimum

```dart
if (userId == null) {
  // Cannot record on server, but credits must be delivered locally
  await _creditRepo.addCredits(
    product.totalCredits,
    'Purchased ${product.label} (${product.totalCredits} credits) [offline]',
  );
  await _creditCubit.loadCredits();
  return;
}
```

Also changed DB insert to `upsert` to prevent duplicate records on retries:

```dart
await supabase.from('purchases').upsert(
  { /* purchase data */ },
  onConflict: 'transaction_id',
);
```

---

## 4. Restore Timeout Handling

### Problem

When `restorePurchases()` is called, restored purchases come through the `purchaseStream`. But **if there are no purchases to restore, the stream never emits**. The UI gets stuck forever in the `purchasing` state (loading spinner).

### Solution: 10-Second Timeout

```dart
Future<void> restorePurchases() async {
  try {
    emit(state.copyWith(status: PurchaseFlowStatus.purchasing));
    await _purchaseRepo.restorePurchases();

    // Auto-recover after 10 seconds if no stream events
    Future.delayed(const Duration(seconds: 10), () {
      if (!isClosed && state.status == PurchaseFlowStatus.purchasing) {
        emit(state.copyWith(status: PurchaseFlowStatus.ready));
      }
    });
  } catch (e) {
    emit(state.copyWith(
      status: PurchaseFlowStatus.error,
      errorMessage: 'Restore failed: ${e.toString()}',
    ));
  }
}
```

The `isClosed` check guards against the case where the Cubit has already been disposed.

---

## 5. Missing Navigation from Camera Screen to Store

### Problem

The app title at the top of the camera screen was a plain `Text` widget, so tapping it did nothing. It was supposed to navigate to the store (market).

```dart
// Before — not tappable
Text('unmask', style: ...)
```

### Solution

```dart
// After — tap to go to store
GestureDetector(
  onTap: widget.onStore,
  child: Text('unmask', style: ...),
)
```

Connect the callback from higher in the widget tree:

```dart
onStore: () {
  Haptics.selection();
  context.push(AppRoutes.store);
},
```

If the `StatefulWidget` is callback-based like `_CameraOverlay`, you need to add a new callback field and inject it at creation time. The reason you should not call `context.push()` directly inside the overlay is that the overlay is a separate `StatefulWidget` and may have a different `BuildContext` than the parent.

---

## Summary: IAP Checklist

Items that are easy to miss in practice:

| Item | Description |
|------|------|
| Beta/production mode branching | Switch entire store UI with `isOpenBeta` flag |
| Restore duplicate prevention | Deduplication check with `transaction_id` on server |
| Unauthenticated purchase protection | Local delivery fallback on session expiry |
| DB upsert | Prevent duplicate records on retries |
| Restore timeout | Prevent infinite loading when there are no purchases to restore |
| Receipt verification | Must switch `strictReceiptVerification` to `true` before production |
| Credit server sync | SharedPreferences alone means credits are lost on app deletion (future task) |

Beta mode is convenient, but it is easy to miss consistency with the store. The key is designing the entire app to behave consistently with a single `isOpenBeta` flag.
