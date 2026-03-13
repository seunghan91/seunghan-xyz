---
title: "Rails + Flutter App Unimplemented Features Audit and In-App Purchase Integration"
date: 2026-01-30
draft: false
tags: ["Rails", "Flutter", "IAP", "in_app_purchase", "FCM", "API", "iOS"]
description: "Full audit of unimplemented features in Rails API and Flutter app before release, filling endpoints with routes but no controllers, and integrating in-app purchases."
cover:
  image: "/images/og/rails-flutter-iap-unimplemented-features-audit.png"
  alt: "Rails Flutter Iap Unimplemented Features Audit"
  hidden: true
---


While preparing to release a voice message-based social app, I performed a full audit of unimplemented features. There were quite a few cases where routes existed but controller actions did not, or the Flutter UI was complete but payment logic was blocked with `// TODO`. Here is the record of cataloging and implementing them one by one.

---

## How to Audit Unimplemented Features

### Backend Audit

The fastest method is comparing `routes.rb` against the actual controllers.

```bash
bundle exec rails routes | grep -v "^  #"
```

If a route exists but the controller has no corresponding action, you get an `ActionController::MethodNotImplemented` error at runtime. Better to catch it early.

### Frontend Audit

For Flutter, searching for `// TODO` and placeholder SnackBar patterns is the quickest approach.

```bash
grep -rn "TODO\|coming soon\|not implemented" lib/
```

---

## Backend: Filling Missing Endpoints

### 1. `conversations#close` / `conversations#unread_count`

Declared in `routes.rb` but missing from the controller.

```ruby
# config/routes.rb
resources :conversations, only: [:index, :show, :destroy] do
  member do
    post :close          # <- action missing
    get  :unread_count   # <- action missing
  end
end
```

Both actions need repeated "authorization check" logic. Extracting it into a private helper keeps things clean.

```ruby
def close
  @conversation = find_authorized_conversation
  return unless @conversation

  @conversation.update!(active: false)
  render json: { message: "Conversation closed.", id: @conversation.id }
end

def unread_count
  @conversation = find_authorized_conversation
  return unless @conversation

  count = @conversation.messages
                       .where.not(sender_id: current_user.id)
                       .where(read: false)
                       .count

  render json: { conversation_id: @conversation.id, unread_count: count }
end

private

def find_authorized_conversation
  conversation = Conversation.find_by(id: params[:id])
  unless conversation
    render json: { error: "Conversation not found." }, status: :not_found
    return nil
  end
  unless conversation.user_a_id == current_user.id || conversation.user_b_id == current_user.id
    render json: { error: "Not authorized for this conversation." }, status: :forbidden
    return nil
  end
  conversation
end
```

### 2. `wallets#transfer` -- User-to-User Coin Transfer

Withdrawal and deposit must be wrapped inside an `ActiveRecord::Base.transaction` block. If either fails, the entire operation rolls back.

```ruby
def transfer
  amount = params[:amount].to_f
  recipient = User.find_by(id: params[:recipient_id])

  return render json: { error: "Insufficient balance." }, status: :unprocessable_entity \
    if sender_wallet.balance < amount

  ActiveRecord::Base.transaction do
    sender_wallet.withdraw(amount, description: "Transfer to #{recipient.nickname}")
    recipient_wallet = recipient.wallet || recipient.create_wallet
    recipient_wallet.deposit(amount, description: "Transfer from #{current_user.nickname}")
  end

  render json: { success: true, balance: sender_wallet.reload.balance }
end
```

### 3. `payments_controller.rb` -- IAP Receipt Verification

The route existed but the file itself did not. The structure calls the Apple verifyReceipt API for iOS and the Google Play Developer API for Android to verify receipts before granting coins.

For iOS, you need the production-to-sandbox fallback pattern. Sending a sandbox receipt to the production server returns status `21007`, at which point you retry with the sandbox URL.

```ruby
def verify_ios_receipt(receipt_data, product)
  result = call_apple_verification(receipt_data, sandbox: false)

  # Retry with sandbox if a sandbox receipt was submitted to production
  result = call_apple_verification(receipt_data, sandbox: true) if result[:status] == 21007

  if result[:status] == 0
    latest = result[:latest_receipt_info]&.find { |r| r["product_id"] == product.store_product_id }
    latest ? { valid: true, transaction_id: latest["transaction_id"] } \
           : { valid: false, reason: "Product not found in receipt" }
  else
    { valid: false, reason: "Apple verification failed (status: #{result[:status]})" }
  end
end
```

Duplicate payment prevention must also be handled. Store the `transaction_id` in `metadata` and check against it.

```ruby
if transaction_id.present? && WalletTransaction.exists?(metadata: { transaction_id: transaction_id })
  return render json: { error: "This payment has already been processed." }, status: :conflict
end
```

### 4. FCM Token Auto-Cleanup

There was code that only logged a warning when FCM returned an `UNREGISTERED` error. Actually deleting the token from the DB is necessary to prevent repeated failed push attempts.

```ruby
if result.dig("error", "details")&.any? { |d| d["errorCode"] == "UNREGISTERED" }
  # Before: Rails.logger.warn "should be removed"
  # After:
  User.where(push_token: push_token).update_all(push_token: nil)
end
```

---

## Flutter: In-App Purchase (IAP) Integration

### Package

```yaml
dependencies:
  in_app_purchase: ^3.2.0
```

Wraps iOS StoreKit and Android Google Play into a single API.

### Structure

```
IapService          <- IAP initialization, purchase, receipt extraction
    | callback
WalletBloc          <- WalletIapPurchaseRequested event
    |
WalletRepository    <- POST receipt to server
    |
Backend verification -> coin grant
```

### IapService Core Pattern

IAP purchase completion arrives through an asynchronous stream. Subscribe to the stream and handle each status.

```dart
class IapService {
  static final IapService _instance = IapService._internal();
  factory IapService() => _instance;  // Singleton

  StreamSubscription<List<PurchaseDetails>>? _subscription;

  Future<void> initialize({IapPurchaseCallback? onPurchaseResult}) async {
    _isAvailable = await InAppPurchase.instance.isAvailable();
    if (!_isAvailable) return;

    _subscription = InAppPurchase.instance.purchaseStream.listen(
      _onPurchaseUpdated,
    );

    // Restore unfinished purchases on app restart
    await InAppPurchase.instance.restorePurchases();
  }

  Future<void> _handlePurchase(PurchaseDetails purchase) async {
    switch (purchase.status) {
      case PurchaseStatus.pending:
        return; // Waiting, do nothing
      case PurchaseStatus.error:
        _onPurchaseResult?.call(IapPurchaseResult(success: false, error: purchase.error?.message));
      case PurchaseStatus.canceled:
        _onPurchaseResult?.call(IapPurchaseResult(success: false, error: 'canceled'));
      case PurchaseStatus.purchased:
      case PurchaseStatus.restored:
        _onPurchaseResult?.call(IapPurchaseResult(
          success: true,
          receiptData: purchase.verificationData.serverVerificationData,
          transactionId: purchase.purchaseID,
        ));
    }
    await InAppPurchase.instance.completePurchase(purchase);
  }
}
```

`completePurchase()` must be called. If omitted, consumable products remain in a non-repurchasable state.

### BLoC Integration

```dart
// event
class WalletIapPurchaseRequested extends WalletEvent {
  final String productId;
  final String? receiptData;
  final String platform; // 'ios' | 'android'
  // ...
}

// bloc handler
Future<void> _onIapPurchaseRequested(
  WalletIapPurchaseRequested event,
  Emitter<WalletState> emit,
) async {
  emit(state.copyWith(status: WalletStatus.purchasing));

  final result = await _walletRepository.purchaseIap(
    productId: event.productId,
    platform: event.platform,
    receiptData: event.receiptData,
  );

  if (result.success) {
    final wallet = await _walletRepository.getWallet();
    emit(state.copyWith(status: WalletStatus.loaded, wallet: wallet, successMessage: result.message));
  } else {
    emit(state.copyWith(status: WalletStatus.error, errorMessage: result.message));
  }
}
```

### UI -- Purchase Button

```dart
// In CoinChargeSheet
Future<void> _onPurchaseTap() async {
  setState(() => _isPurchasing = true);

  // Re-register callback on IapService (maintain latest context)
  await IapService().initialize(onPurchaseResult: _onIapPurchaseResult);
  await IapService().purchase(_selectedPackage!);

  // Result handled in _onIapPurchaseResult
}

void _onIapPurchaseResult(IapPurchaseResult result) {
  if (result.success) {
    context.read<WalletBloc>().add(WalletIapPurchaseRequested(
      productId: _getBackendProductId(result.productId!),
      platform: Platform.isIOS ? 'ios' : 'android',
      receiptData: result.receiptData,
      transactionId: result.transactionId,
    ));
  }
  setState(() => _isPurchasing = false);
}
```

---

## Pre-Store Deployment IAP Checklist

- Register consumable in-app products in App Store Connect (product ID must exactly match the app code)
- Add `APPLE_SHARED_SECRET` to backend environment variables (App Store Connect -> App -> In-App Purchases -> Shared Secret)
- Test the entire purchase flow with a Sandbox account
- For Android, register products in Google Play Console + set up a Google Play Developer API service account

---

## Summary

Common patterns found during pre-release audit of a Rails + Flutter app:

1. **Routes exist but actions are missing** -- Cross-reference `rails routes` with controllers to catch them early
2. **UI is complete, logic is TODO** -- Run `grep -rn "TODO"` to list them all at once
3. **IAP is an async stream** -- Do not miss status-specific handling and the `completePurchase()` call
4. **FCM UNREGISTERED** -- Do not just log it; actually clean up the DB
