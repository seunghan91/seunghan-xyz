---
title: "Rails + Flutter 앱 미구현 항목 점검 및 인앱 결제(IAP) 연동 기록"
date: 2026-01-30
draft: false
tags: ["Rails", "Flutter", "IAP", "in_app_purchase", "FCM", "API", "iOS"]
description: "출시 직전 Rails API와 Flutter 앱의 미구현 항목을 전수 점검하고, route만 있고 컨트롤러가 없는 엔드포인트들을 채우고 인앱 결제까지 연동한 과정"
cover:
  image: "/images/og/rails-flutter-iap-unimplemented-features-audit.png"
  alt: "Rails Flutter Iap Unimplemented Features Audit"
  hidden: true
categories: ["Rails"]
---

음성 메시지 기반 소셜 앱을 출시 준비하면서 미구현 항목을 전수 점검했다. route는 있는데 controller action이 없거나, Flutter UI는 완성됐는데 결제 로직이 `// TODO` 로 막혀 있는 경우들이 꽤 있었다. 정리하고 하나씩 구현한 기록.

---

## 미구현 항목 점검 방법

### 백엔드 점검

가장 빠른 방법은 `routes.rb`와 실제 controller를 비교하는 것이다.

```bash
bundle exec rails routes | grep -v "^  #"
```

route가 있는데 controller에 해당 action이 없으면 런타임에 `ActionController::MethodNotImplemented` 에러가 난다. 미리 찾아내는 게 낫다.

### 프론트엔드 점검

Flutter는 `// TODO`, `SnackBar(content: Text('기능 준비 중'))` 패턴을 검색하면 빠르다.

```bash
grep -rn "TODO\|준비 중\|오픈 예정" lib/
```

---

## 백엔드: 빠진 엔드포인트 채우기

### 1. `conversations#close` / `conversations#unread_count`

`routes.rb`에는 선언돼 있었지만 controller에 없었다.

```ruby
# config/routes.rb
resources :conversations, only: [:index, :show, :destroy] do
  member do
    post :close          # ← action 없음
    get  :unread_count   # ← action 없음
  end
end
```

두 action 모두 반복되는 "권한 확인" 로직이 필요하다. private 헬퍼로 분리하면 깔끔하다.

```ruby
def close
  @conversation = find_authorized_conversation
  return unless @conversation

  @conversation.update!(active: false)
  render json: { message: "대화가 종료되었습니다.", id: @conversation.id }
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
    render json: { error: "대화를 찾을 수 없습니다." }, status: :not_found
    return nil
  end
  unless conversation.user_a_id == current_user.id || conversation.user_b_id == current_user.id
    render json: { error: "이 대화에 대한 권한이 없습니다." }, status: :forbidden
    return nil
  end
  conversation
end
```

### 2. `wallets#transfer` — 사용자 간 코인 이체

`ActiveRecord::Base.transaction` 블록 안에서 출금·입금을 묶어야 한다. 하나라도 실패하면 전체 롤백.

```ruby
def transfer
  amount = params[:amount].to_f
  recipient = User.find_by(id: params[:recipient_id])

  return render json: { error: "잔액이 부족합니다." }, status: :unprocessable_entity \
    if sender_wallet.balance < amount

  ActiveRecord::Base.transaction do
    sender_wallet.withdraw(amount, description: "#{recipient.nickname}님에게 이체")
    recipient_wallet = recipient.wallet || recipient.create_wallet
    recipient_wallet.deposit(amount, description: "#{current_user.nickname}님으로부터 이체")
  end

  render json: { success: true, balance: sender_wallet.reload.balance }
end
```

### 3. `payments_controller.rb` — IAP 영수증 검증

route만 있고 파일 자체가 없었다. iOS는 Apple verifReceipt API, Android는 Google Play Developer API를 호출해서 영수증을 검증한 뒤 코인을 지급하는 구조.

iOS는 프로덕션 → 샌드박스 폴백 패턴을 써야 한다. 프로덕션 서버에 샌드박스 영수증을 보내면 status `21007`을 반환하는데, 이때 샌드박스 URL로 재시도한다.

```ruby
def verify_ios_receipt(receipt_data, product)
  result = call_apple_verification(receipt_data, sandbox: false)

  # 샌드박스 영수증이 프로덕션에 제출된 경우 재시도
  result = call_apple_verification(receipt_data, sandbox: true) if result[:status] == 21007

  if result[:status] == 0
    latest = result[:latest_receipt_info]&.find { |r| r["product_id"] == product.store_product_id }
    latest ? { valid: true, transaction_id: latest["transaction_id"] } \
           : { valid: false, reason: "영수증에 해당 상품 없음" }
  else
    { valid: false, reason: "Apple 검증 실패 (status: #{result[:status]})" }
  end
end
```

중복 결제 방지도 챙겨야 한다. `transaction_id`를 `metadata`에 저장해두고 체크한다.

```ruby
if transaction_id.present? && WalletTransaction.exists?(metadata: { transaction_id: transaction_id })
  return render json: { error: "이미 처리된 결제입니다." }, status: :conflict
end
```

### 4. FCM 토큰 자동 정리

FCM에서 `UNREGISTERED` 에러가 오면 로그만 남기고 넘어가는 코드가 있었다. 실제로 DB에서 삭제해야 반복적인 실패 발송을 막을 수 있다.

```ruby
if result.dig("error", "details")&.any? { |d| d["errorCode"] == "UNREGISTERED" }
  # 기존: Rails.logger.warn "should be removed"
  # 수정:
  User.where(push_token: push_token).update_all(push_token: nil)
end
```

---

## Flutter: 인앱 결제(IAP) 연동

### 패키지

```yaml
dependencies:
  in_app_purchase: ^3.2.0
```

iOS StoreKit과 Android Google Play를 하나의 API로 감싸준다.

### 구조

```
IapService          ← IAP 초기화, 구매, 영수증 추출
    ↓ 콜백
WalletBloc          ← WalletIapPurchaseRequested 이벤트
    ↓
WalletRepository    ← 서버에 영수증 POST
    ↓
백엔드 검증 → 코인 지급
```

### IapService 핵심 패턴

IAP는 구매 완료가 비동기 스트림으로 온다. 스트림을 구독하고 상태별로 처리한다.

```dart
class IapService {
  static final IapService _instance = IapService._internal();
  factory IapService() => _instance;  // 싱글톤

  StreamSubscription<List<PurchaseDetails>>? _subscription;

  Future<void> initialize({IapPurchaseCallback? onPurchaseResult}) async {
    _isAvailable = await InAppPurchase.instance.isAvailable();
    if (!_isAvailable) return;

    _subscription = InAppPurchase.instance.purchaseStream.listen(
      _onPurchaseUpdated,
    );

    // 앱 재시작 시 미처리 구매 복원
    await InAppPurchase.instance.restorePurchases();
  }

  Future<void> _handlePurchase(PurchaseDetails purchase) async {
    switch (purchase.status) {
      case PurchaseStatus.pending:
        return; // 대기 중, 아무것도 하지 않음
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

`completePurchase()`는 반드시 호출해야 한다. 빠뜨리면 consumable 상품이 재구매 불가 상태로 남는다.

### BLoC 연동

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

### UI — 구매 버튼

```dart
// CoinChargeSheet에서
Future<void> _onPurchaseTap() async {
  setState(() => _isPurchasing = true);

  // IapService에 콜백 재등록 (최신 context 유지)
  await IapService().initialize(onPurchaseResult: _onIapPurchaseResult);
  await IapService().purchase(_selectedPackage!);

  // 결과는 _onIapPurchaseResult에서 처리
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

## 스토어 배포 전 IAP 체크리스트

- App Store Connect에 consumable 인앱 상품 등록 (product ID가 앱 코드와 정확히 일치해야 함)
- 백엔드 환경변수에 `APPLE_SHARED_SECRET` 추가 (App Store Connect → 앱 → 인앱 결제 → 공유 암호)
- Sandbox 계정으로 전체 구매 플로우 테스트
- Android는 Google Play Console에 상품 등록 + Google Play Developer API 서비스 계정 설정

---

## 정리

Rails + Flutter 앱을 출시 직전에 점검하면서 자주 나오는 패턴:

1. **route는 있는데 action이 없음** — `rails routes`와 controller를 대조해서 미리 잡는다
2. **UI는 완성, 로직은 TODO** — `grep -rn "TODO"` 로 한 번에 목록화
3. **IAP는 비동기 스트림** — 상태별 처리와 `completePurchase()` 호출을 빠뜨리지 않는다
4. **FCM UNREGISTERED** — 로그만 남기지 말고 실제로 DB 정리까지
