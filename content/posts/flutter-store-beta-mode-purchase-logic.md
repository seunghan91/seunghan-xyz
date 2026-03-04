---
title: "Flutter IAP 스토어 베타 모드 설계와 구매 로직 보강 실전기"
date: 2026-02-27
draft: false
tags: ["Flutter", "IAP", "In-App Purchase", "베타", "StoreKit", "BLoC"]
description: "오픈 베타 기간에 스토어 화면을 어떻게 처리할 것인가, IAP Restore 중복 지급 방지, 미인증 사용자 크레딧 보호 등 실전에서 만난 구매 로직 허점들과 해결법"
---

Flutter 앱에서 IAP(In-App Purchase)를 구현하고 오픈 베타를 운영하다 보면, "베타인데 스토어는 유료 가격이 그대로 보인다"거나 "Restore하면 크레딧이 중복 지급된다" 같은 허점들이 드러난다. 실제로 마주친 문제들과 해결 과정을 정리한다.

---

## 1. 베타 모드와 스토어의 모순

### 문제

```dart
// constants.dart
static const bool isOpenBeta = true;
```

`isOpenBeta = true`이면 `spendCredits()`에서 크레딧을 차감하지 않는다. AI 기능이 무료라는 뜻이다.

```dart
// credit_repository.dart
Future<bool> spendCredits(int amount, String reason) async {
  if (AppConstants.isOpenBeta) {
    // 크레딧 차감 안 함 — 무료
    await _addTransaction(CreditTransaction(
      amount: 0,
      reason: '$reason (Beta - Free)',
    ));
    return true;
  }
  // ... 실제 차감 로직
}
```

그런데 스토어 화면은 `₩3,300`, `₩11,000`, `₩29,900` 가격이 그대로 표시되고 구매 버튼도 활성화되어 있었다. 베타인데 돈을 받겠다는 건지, 무료인데 왜 가격이 보이는지 — 사용자 입장에서 혼란스럽다.

### 해결: `isOpenBeta` 분기를 스토어 전체에 적용

```dart
// store_screen.dart
final isBeta = AppConstants.isOpenBeta;

// 1. 앱바 타이틀 분기
title: Text(isBeta ? s.store : s.buyCredits),

// 2. 베타 배너 추가
if (isBeta) ...[
  _BetaBanner(),  // "Open Beta 기간 무료" 안내
  const SizedBox(height: 20),
],

// 3. 크레딧 팩 설명 분기
Text(
  isBeta ? s.freeDuringBeta : s.oneCreditOneUpscale,
  style: UnmaskTypography.bodySmall.copyWith(
    color: isBeta ? UnmaskColors.success : UnmaskColors.textSubtle,
  ),
),

// 4. 카드에서 가격 → FREE, 버튼 비활성화
_CreditPackCard(
  product: product,
  isBeta: isBeta,
  onBuy: isBeta ? null : () => _handleBuy(context, product),
),

// 5. 하단 결제/복원 UI 숨김
if (!isBeta) ...[
  // Restore Purchases, Payment method note
],
```

카드 위젯에서도 분기:

```dart
// 가격 표시
Text(isBeta ? s.free : product.priceFormatted),

// 버튼 텍스트
Text(isBeta ? s.comingSoon : s.buy),

// 전체 opacity
Opacity(opacity: isBeta ? 0.5 : 1.0, child: ...)
```

**핵심**: `isOpenBeta` 플래그 하나로 스토어 전체가 베타/정식 모드를 전환한다. 나중에 `false`로만 바꾸면 유료 전환 완료.

---

## 2. Restore Purchases 중복 지급 방지

### 문제

IAP의 `restorePurchases()`를 호출하면 이전 구매 내역이 `purchaseStream`으로 들어온다. 기존 코드는 `PurchaseStatus.restored`를 `PurchaseStatus.purchased`와 동일하게 처리했다.

```dart
case PurchaseStatus.purchased:
case PurchaseStatus.restored:
  // 둘 다 똑같이 크레딧 지급 → 중복!
  await _deliverCredits(product, purchase);
```

사용자가 Restore를 누를 때마다 크레딧이 계속 쌓인다.

### 해결: transaction_id로 중복 체크

```dart
case PurchaseStatus.purchased:
case PurchaseStatus.restored:
  // Restore인 경우에만 중복 체크
  if (purchase.status == PurchaseStatus.restored) {
    final alreadyDelivered = await _isAlreadyDelivered(
      purchase.purchaseID,
    );
    if (alreadyDelivered) {
      await _purchaseRepo.completeIapPurchase(purchase);
      emit(state.copyWith(status: PurchaseFlowStatus.ready));
      break;  // 이미 지급됨 → skip
    }
  }
  // ... 정상 지급 로직
```

서버(Supabase)에서 `transaction_id`로 조회:

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
    // 체크 실패 시 지급 허용 (돈 받고 안 주는 것보다 나음)
    return false;
  }
}
```

**설계 원칙**: 중복 체크가 실패하면 `false`를 반환해서 지급을 허용한다. "이미 받은 크레딧을 또 받는 것"보다 "돈을 냈는데 못 받는 것"이 훨씬 나쁘다.

---

## 3. 미인증 사용자의 크레딧 보호

### 문제

기존 코드:

```dart
Future<void> _deliverCredits(CreditProduct product, PurchaseDetails purchase) async {
  final userId = Supabase.instance.client.auth.currentUser?.id;
  if (userId == null) {
    throw Exception('User not authenticated');  // 💥 크레딧 소실
  }
  // ...
}
```

사용자가 결제를 완료했는데 인증 세션이 만료된 경우, 예외가 던져지고 크레딧이 지급되지 않는다. **돈은 빠져나갔는데 크레딧은 안 들어오는** 최악의 상황.

### 해결: 로컬이라도 지급

```dart
if (userId == null) {
  // 서버 기록은 못 하지만, 로컬에 크레딧은 반드시 지급
  await _creditRepo.addCredits(
    product.totalCredits,
    'Purchased ${product.label} (${product.totalCredits} credits) [offline]',
  );
  await _creditCubit.loadCredits();
  return;
}
```

그리고 DB insert도 `insert` → `upsert`로 변경해서 재시도 시 중복 레코드를 방지:

```dart
await supabase.from('purchases').upsert(
  { /* purchase data */ },
  onConflict: 'transaction_id',
);
```

---

## 4. Restore 타임아웃 처리

### 문제

`restorePurchases()`를 호출하면 복원된 구매가 `purchaseStream`으로 들어온다. 그런데 **복원할 구매가 없으면 stream이 아예 안 온다**. UI는 `purchasing` 상태(로딩 스피너)에서 영원히 멈춘다.

### 해결: 10초 타임아웃

```dart
Future<void> restorePurchases() async {
  try {
    emit(state.copyWith(status: PurchaseFlowStatus.purchasing));
    await _purchaseRepo.restorePurchases();

    // Stream이 안 오면 10초 후 자동 복귀
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

`isClosed` 체크로 Cubit이 이미 dispose된 경우를 방어한다.

---

## 5. 카메라 화면 → 스토어 네비게이션 누락

### 문제

카메라 화면 상단 앱 타이틀이 단순 `Text` 위젯이라 탭해도 아무 일도 안 일어났다. 원래는 스토어(마켓)로 이동해야 했다.

```dart
// Before — 탭 불가
Text('unmask', style: ...)
```

### 해결

```dart
// After — 탭하면 스토어로
GestureDetector(
  onTap: widget.onStore,
  child: Text('unmask', style: ...),
)
```

위젯 트리 상위에서 콜백 연결:

```dart
onStore: () {
  Haptics.selection();
  context.push(AppRoutes.store);
},
```

`StatefulWidget`이 `_CameraOverlay`처럼 콜백 기반이면, 새 콜백 필드를 추가하고 생성 시점에서 주입해야 한다. `context.push()`를 overlay 내부에서 직접 호출하면 안 되는 이유는 overlay가 별도 `StatefulWidget`이라 부모의 `BuildContext`와 다를 수 있기 때문.

---

## 정리: IAP 체크리스트

실제로 빠뜨리기 쉬운 항목들:

| 항목 | 설명 |
|------|------|
| 베타/정식 모드 분기 | `isOpenBeta` 플래그로 스토어 UI 전체 전환 |
| Restore 중복 방지 | `transaction_id`로 서버에서 중복 체크 |
| 미인증 결제 보호 | 세션 만료 시 로컬 지급 fallback |
| DB upsert | 재시도 시 중복 레코드 방지 |
| Restore 타임아웃 | 복원 건 없을 때 UI 무한 로딩 방지 |
| 영수증 검증 | `strictReceiptVerification` 프로덕션 전 `true` 전환 필수 |
| 크레딧 서버 동기화 | SharedPreferences만으로는 앱 삭제 시 소실 (향후 과제) |

베타 모드는 편하지만, 스토어와의 정합성을 빼먹기 쉽다. `isOpenBeta` 하나로 앱 전체가 일관되게 동작하도록 설계하는 게 핵심이다.
