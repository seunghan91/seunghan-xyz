---
title: "배달앱 수수료 구조의 맹점과 Rails 8 비동기 결제 플로우 설계"
date: 2026-03-09
draft: false
tags: ["Rails", "Turbo Native", "ActionCable", "Stimulus", "결제", "PG", "아키텍처"]
description: "배달앱 간편결제 수수료가 왜 자영업자에게 전가되는지 구조를 분석하고, Rails 8 + Turbo Native로 비동기 인보이스 결제 플로우를 설계한 기록"
---

배달앱 수수료 문제를 파고들다가 결제 구조의 맹점을 발견했고, 이를 우회하는 방식으로 Rails 8 아키텍처를 설계한 기록이다.

---

## 문제 인식: 카드 수수료를 낮춰줬는데 왜 체감이 없나

정부가 영세 가맹점 카드 수수료를 인하해도 배달 매출 비중이 높은 자영업자는 혜택이 거의 없다.

이유는 **결제 주체**가 다르기 때문이다.

| 결제 경로 | 적용 법률 | 영세가맹점 수수료 |
|---------|---------|----------------|
| 매장 직접 카드 결제 | 여신전문금융업법 | 0.5 ~ 0.8% |
| 배달앱 간편결제 | 전자금융거래법 | 3.0 ~ 3.3% |

배달앱을 통한 결제에서 카드사 가맹점은 **자영업자가 아니라 배달앱(또는 PG사)**이다. 자영업자는 배달앱의 "입점업체"일 뿐, 카드사와 직접 계약 관계가 없다.

PG사는 전자금융거래법 적용 대상이라 **여신전문금융업법의 우대수수료 규제를 받지 않는다.** 법 체계 자체가 다르기 때문에 국세청이나 카드사에 민원을 넣어도 구조적으로 해결되지 않는다.

---

## 자영업자가 직접 카드를 받을 수 없는 이유

기술적으로는 방법이 있다.

**가게배달 + 만나서 결제** 옵션을 쓰면 배달원이 카드 단말기를 가져가 현장에서 0.5~1.3% 수수료로 결제를 받을 수 있다. 단, 배민1 같은 플랫폼 배달 상품에서는 불가능하고, 가게배달 노출은 점점 줄어드는 추세다.

전화/카카오톡 직접 주문을 유도해 카드 단말기로 받는 방법도 있지만 주문 접수부터 배달까지 직접 처리해야 하는 운영 부담이 생긴다.

결국 **결제 수수료 문제는 개별 자영업자가 해결할 수 있는 범위 밖**이고, 입법 규제(수수료 상한제, PG사 우대수수료 의무화)가 되어야 근본적으로 해결된다.

---

## 설계 방향: 결제를 뒤로 미루는 인보이스 모델

이 구조적 문제에서 힌트를 얻어, 결제 흐름 자체를 바꾸는 아키텍처를 설계했다.

**기존 배달앱 방식 (동기화 결제)**
```
고객 결제 완료 → 주문 식당에 전달
```

**인보이스 방식 (비동기 결제)**
```
고객 주문 요청 → 사장님 승인 → 결제 링크 발송 → 고객 결제 완료 → 조리 시작
```

이 모델의 핵심 장점은 **취소/환불 CS가 원천 차단**된다는 점이다. 기존 방식은 결제 후 재료가 없으면 PG 취소를 해야 하고(수수료 + 수일 소요), 이게 주요 CS 비용이 된다. 승인 후 결제 방식은 사장님이 OK한 건에만 결제가 이뤄진다.

---

## Rails 8 구현: 주문 플로우

### Order 상태 머신

```
requested → approved → paid → cooking → delivered
```

고객이 [주문 요청] 버튼을 누르면 `status: requested` 상태의 Order 레코드만 생성된다. 결제는 발생하지 않는다.

### ActionCable로 사장님 화면 실시간 갱신

```ruby
# app/models/order.rb
after_create_commit -> {
  broadcast_prepend_to "store_#{store_id}_orders",
    target: "orders_list",
    partial: "orders/order",
    locals: { order: self }
}
```

사장님이 띄워둔 대시보드 웹 화면에 새로고침 없이 주문이 즉시 등장한다. Turbo Streams 덕분에 별도 WebSocket 서버 구축 없이 Rails 하나로 처리된다.

### 딥링크 결제 URL

사장님이 수락을 누르면 서버가 고유 결제 URL을 생성하고, SMS / 알림톡으로 고객에게 발송한다.

```
localorder://pay/order_id=1234
```

고객이 링크를 클릭하면 브라우저가 아닌 네이티브 앱이 열린다 (Universal Link / App Link). 앱 안에서 Rails 서버의 결제 페이지를 Turbo Native 화면으로 렌더링하고, 토스페이 / 카카오페이로 결제를 완료한다.

---

## Stimulus로 포스기 알림음 구현

사장님이 화면을 안 보고 있을 때 주문이 와도 소리가 나야 한다. 브라우저의 Autoplay Policy 제약 때문에 단순 자동 재생은 차단된다.

**우회 방법**: 사장님이 아침에 [영업 시작] 버튼을 한 번 클릭하게 유도해 오디오 재생 권한을 획득해 두면, 이후 Turbo Streams로 새 주문 DOM이 삽입될 때 Stimulus `connect()` 훅에서 소리를 낼 수 있다.

```javascript
// app/javascript/controllers/order_alert_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  connect() {
    const audio = new Audio('/sounds/new_order_alert.mp3')
    audio.play().catch(() => {
      // 오디오 권한 없으면 조용히 실패 (영업 시작 버튼 클릭 유도)
    })
    this.element.classList.add("bg-yellow-200", "animate-pulse")
  }
}
```

새 주문 HTML 조각에 `data-controller="order-alert"`를 붙이면, DOM이 화면에 마운트되는 순간 자동으로 `connect()`가 호출된다.

---

## SMS 발송: 무료 vs 유료 투트랙

플랫폼 서버 비용을 최소화하면서 사장님에게 선택권을 주는 구조다.

### 무료: sms: URI Scheme

서버를 전혀 거치지 않는다. 사장님의 무제한 문자 요금제를 활용한다.

```html
<a href="sms:01012345678?body=[알림] 주문이 승인되었습니다. 결제: localorder://pay/1234">
  주문 수락 및 문자 보내기
</a>
```

[수락] 클릭 시 사장님 폰의 기본 문자 앱이 내용이 채워진 채로 열린다. 전송 버튼만 누르면 끝. **플랫폼 발송 비용 0원.**

### 유료: 백그라운드 자동 발송 (SaaS 구독)

피크타임에 일일이 전송 버튼을 누를 수 없는 사장님을 위한 구독 모델이다.

```ruby
# app/jobs/send_payment_link_job.rb
class SendPaymentLinkJob < ApplicationJob
  def perform(order_id)
    order = Order.find(order_id)
    SmsService.send(
      to: order.customer_phone,
      body: payment_sms_body(order)
    )
  end
end
```

[수락] 클릭 즉시 SolidQueue가 백그라운드에서 알림톡/SMS API를 호출한다. 월 9,900원에 500건 무료 포함 같은 SaaS 형태로 과금한다.

---

## 고객 대기 화면: 결제 이탈 방지

비동기 모델의 약점은 고객이 기다리다 이탈하는 것이다.

주문 직후 고객 앱에 **"사장님이 확인 중입니다 (평균 30초 소요)"** 대기 화면을 띄운다. 사장님이 수락하는 순간 ActionCable로 고객 화면도 실시간 갱신되어 [결제하기] 버튼으로 전환된다.

SMS는 고객이 앱 밖으로 나갔을 경우를 위한 Fallback 안전망이다.

---

## 개발 생산성 측면

Turbo Native를 쓰면 모바일 앱에 별도 API나 Swift / Kotlin UI 코드를 짤 필요가 없다. Rails에서 HTML 뷰만 관리하면 iOS / Android 앱은 브라우저처럼 화면을 렌더링한다.

1인 개발자가 웹 + iOS + Android를 동시에 유지보수할 수 있는 구조다.

PG 연동도 플랫폼이 돈을 쥐는 서브몰/에스크로 계약이 필요 없다. 사장님 본인의 토스 페이먼츠 계정에 웹훅만 연결하면 돈이 플랫폼을 거치지 않고 사장님 계좌로 직접 입금된다.

---

## 정리

| 항목 | 기존 방식 | 이 아키텍처 |
|------|---------|-----------|
| 결제 타이밍 | 주문과 동시 | 사장님 승인 후 |
| 취소/환불 CS | PG 취소 필요 | 승인 전엔 결제 없음 |
| 실시간 알림 | 별도 소켓 서버 | ActionCable 내장 |
| 모바일 앱 | Swift/Kotlin 별도 | Turbo Native 공유 |
| SMS 발송 비용 | 건당 플랫폼 부담 | 무료(sms: URI) or 구독 |

결제 수수료 문제는 단기간에 법으로 해결되기 어렵다. 그 사이에 아키텍처 레벨에서 플랫폼을 최대한 단순하게 만들어 비용 구조 자체를 바꾸는 접근이 현실적이라고 생각한다.
