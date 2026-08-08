---
title: "iOS BLE 연결이 CBError Code=1 로 거부됐다 — auto-reconnect 옵션 함정"
date: 2026-08-08T15:27:13+09:00
draft: false
tags: ["iOS", "CoreBluetooth", "BLE", "디버깅", "Swift"]
description: "CBConnectPeripheralOptionEnableAutoReconnect 를 얹으면 CoreBluetooth 가 연결 요청을 CBError Code=1 로 거부한다. 헛짚은 가설 세 개를 거쳐 실기 로그로 좁혀간 기록."
---

BLE 녹음기를 앱에 붙이는 작업을 하다가, 아이폰에서 기기 연결이 안 되는 상황을 만났다. 안드로이드 쪽은 같은 기기에 잘 붙는데 아이폰만 안 됐다.

증상이 묘했다. 스캔은 완벽하게 됐다. 기기가 목록에 이름까지 정확히 떴고, 시스템 블루투스 로그를 보면 RSSI −50dB 로 바로 옆에 있는 것처럼 잡혔다. 그런데 목록에서 그 항목을 탭하면 "연결하지 못했습니다"만 떴다.

더 이상했던 건 이 기능을 처음 만들었을 때는 분명히 됐다는 점이다. 그 뒤로 한동안 다른 기능을 붙이다가 어느 순간 이렇게 됐다. 전형적인 회귀인데, 언제 깨졌는지가 안 보였다.

결론부터 쓰면 원인은 `CBConnectPeripheralOptionEnableAutoReconnect` 였다. iOS 17 에서 추가된 자동 재연결 옵션인데, 이걸 얹은 채 connect 하면 CoreBluetooth 가 요청 자체를 `CBError Code=1` 로 거부한다. 옵션만 떼자 같은 기기에 그대로 붙었다.

여기까지 오는 데 가설을 세 번 갈아탔고, 그중 두 번은 그럴듯했지만 틀렸다. 마지막에는 "조건부로 켜면 된다"고 고친 처방마저 틀렸다. 그 과정을 그대로 적는다.

---

## CoreBluetooth 연결이 어떻게 흘러가는가

먼저 흐름을 정리해두자. CoreBluetooth 로 기기에 붙는 경로는 크게 둘이다.

**처음 붙일 때 (pairing)**

1. `centralManagerDidUpdateState` 에서 `.poweredOn` 을 기다린다
2. `scanForPeripherals(withServices:)` 로 스캔
3. `didDiscover` 콜백에서 `CBPeripheral` 을 받는다
4. `connect(peripheral, options:)`
5. `didConnect` → `discoverServices` → `discoverCharacteristics` → 구독

**다시 붙일 때 (reconnect)**

1. `.poweredOn` 대기
2. 저장해둔 UUID 로 `retrievePeripherals(withIdentifiers:)`
3. 나오면 바로 `connect`. 스캔이 필요 없다

두 번째 경로가 훨씬 빠르다. 스캔은 몇 초씩 걸리는데 조회는 즉시다. 그래서 "연결했던 기기를 기억해두고 다음엔 스캔 없이 바로 붙는다"는 기능을 넣는 건 자연스러운 개선이다.

문제는 그 개선을 넣으면서 연결 옵션까지 함께 바꿨다는 거다.

---

## 잘못 짚은 가설 두 개

원인을 찾기까지 두 번 헛짚었다. 이 과정을 남겨두는 이유는, 둘 다 그럴듯했고 실제로 같은 증상을 만들 수 있는 원인이기 때문이다.

### 가설 1: 스캔 결과를 값으로만 들고 있었다

코드를 보다가 이걸 발견했다.

```swift
private var discovered: [UUID: DiscoveredDevice] = [:]   // 값 타입 DTO

func transportDidDiscover(_ p: PeripheralHandle, name: String?, rssi: Int) {
  let dev = DiscoveredDevice(id: p.identifier, name: name, rssi: rssi)
  discovered[p.identifier] = dev    // peripheral 객체는 버려진다
}
```

스캔에서 발견한 `CBPeripheral` 객체를 안 들고 있고, id/name/rssi 만 담은 값 타입을 저장한다. 그런데 연결할 때는 이렇게 되찾으려 했다.

```swift
guard let p = central.retrievePeripherals(withIdentifiers: [id]).first
  ?? central.retrieveConnectedPeripherals(withService: service)
      .first(where: { $0.identifier == id })
else { throw Error.notFound }
```

이건 실제로 문제다. Punch Through 의 BLE 가이드가 이 점을 명확히 적어놨다.

> Once the scan callback returns a CBPeripheral object, you *must* retain a strong reference to it in your code. If you simply call connect immediately from the didDiscover delegate method and let that function block complete without strongly storing the peripheral elsewhere, the peripheral object will be deallocated and any connection or pending connection broken.

`CBCentralManager` 는 발견한 peripheral 을 내부적으로 강하게 붙들지 않는다. 앱이 참조를 놓으면 해제되고, 진행 중이던 연결도 끊어진다.

그리고 `retrievePeripherals(withIdentifiers:)` 는 **시스템이 아는 기기**만 돌려준다. Apple 문서 표현으로는 "peripherals that you've discovered or connected to in the past" 인데, 실무에서는 캐시 상태에 따라 처음 만나는 기기가 안 나오는 경우가 흔하다. Apple 의 Channel Sounding 샘플 코드도 이 점을 전제로 짜여 있다.

> On the first launch after pairing, Core Bluetooth's cache is empty, so `retrieveAndConnect` scans by service UUID and connects when `didDiscover` finds a peripheral with a matching identifier. On subsequent launches, the peripheral is already in the cache, so the app uses `retrievePeripherals(withIdentifiers:)` to fetch it directly without scanning.

즉 **첫 연결은 스캔 핸들로, 재연결은 조회로** 가 정석이다. 그래서 딕셔너리가 핸들을 들도록 고쳤다.

```swift
private var discovered: [UUID: PeripheralHandle] = [:]

func transportDidDiscover(_ p: PeripheralHandle, name: String?, rssi: Int) {
  let dev = DiscoveredDevice(id: p.identifier, name: name, rssi: rssi)
  discovered[p.identifier] = p    // 핸들을 붙잡아 둔다
  scanContinuation?.yield(dev)
}
```

여기서 흥미로운 건 이 `discovered` 딕셔너리가 **쓰기만 하고 아무도 읽지 않는 죽은 코드**였다는 점이다. 그래서 리팩터링을 여러 번 거치는 동안 아무도 이상하다고 못 느꼈다.

고치고 다시 시험했다. 여전히 안 됐다.

### 가설 2: 다른 기기가 BLE 를 점유하고 있다

BLE 주변장치는 한 번에 하나의 중앙장치에만 연결된다. 그날 오후 내내 안드로이드로 같은 기기를 검증하고 있었으니, 안드로이드가 붙잡고 있어서 아이폰이 못 붙는 건 아주 그럴듯한 시나리오였다.

실제로 안드로이드 쪽을 확인해보니 앱이 살아있었다. 강제 종료했는데도 주기 동기화 워커가 앱을 다시 깨웠다. 그래서 블루투스 자체를 껐다.

```bash
adb shell am force-stop {package}
adb shell svc bluetooth disable
adb shell settings get global bluetooth_on   # 0
```

그런데도 안 됐다. 그리고 결정적으로, 기기 쪽에 연결 표시등이 안 들어와 있었다. 애초에 아무와도 연결돼 있지 않았던 거다. 이 가설도 접었다.

두 번 헛짚고 나서야 추측을 멈추고 로그를 보기로 했다.

---

## 로그를 보려는데 로그가 안 보인다

여기서 또 한참을 썼다. iOS 실기의 앱 로그를 CLI 로 보는 게 생각보다 까다롭다.

시도한 것들:

```bash
# 1. macOS log 명령 — 원격 기기 미지원
log stream --device <UDID> --predicate 'process == "MyApp"'
# log: unrecognized option `--device'

# 2. devicectl console — 이 버전엔 서브커맨드가 없음
xcrun devicectl device console --device <UUID>
# Error: Unknown option '--device'

# 3. idevicesyslog — 시스템 데몬 로그는 보이는데 앱 로그가 없음
idevicesyslog -u <UDID> | grep MyApp
```

세 번째가 특히 함정이었다. `idevicesyslog` 로 `bluetoothd` 로그는 아주 잘 보인다. 스캔에서 기기가 잡히는 것도 실시간으로 확인됐다.

```
bluetoothd[97] <Debug>: Found device "Public XX:XX:XX:XX:XX:XX RSSI:-51
  with data:"MyDevice-0001", Service UUIDs: 0xAE70, ... connectable
```

그런데 앱 로그는 한 줄도 안 나왔다. 이유는 단순했다. 앱이 `print` 를 안 쓰고 `os.Logger` 만 쓰는데, **os_log 는 통합 로깅 시스템으로 가지 stdout/syslog 로 안 간다.** `idevicesyslog` 는 구형 syslog 스트림이라 이걸 못 본다.

여기서 한 번 더 헛다리를 짚었다. bluetoothd 로그에 연결 시도가 안 보이길래 "앱이 connect 를 아예 호출하지 않는다"고 결론 냈는데, 이것도 틀렸다. **bluetoothd 는 대부분의 로그에서 기기 주소를 `<private>` 로 마스킹한다.** 주소로 필터를 걸었으니 connect 관련 줄이 통째로 걸러진 거였다.

결국 가장 원시적인 방법이 답이었다. 실패 지점에 `print` 를 박고, 콘솔을 붙인 채로 앱을 띄웠다.

```swift
func transportDidFailToConnect(_ p: PeripheralHandle, error: Error?) {
  print("DIAG didFailToConnect id=\(p.identifier) error=\(String(describing: error))")
  finishConnectWaiter(p, throwing: .connectionFailed(error?.localizedDescription ?? ""))
}
```

```bash
xcrun devicectl device process launch --console --terminate-existing \
  --device <UUID> com.example.app > diag.log 2>&1
```

`--console` 은 stdout/stderr 를 그대로 받아온다. `print` 만 붙이면 다 보인다.

---

## 진짜 원인

로그 두 줄이 전부 설명해줬다.

```
DIAG connect 호출 id=A1DCFFC7-…-0AA9CD84EE6E source=scan
DIAG didFailToConnect id=A1DCFFC7-…-0AA9CD84EE6E
  error=Optional(Error Domain=CBErrorDomain Code=1
  "One or more parameters were invalid."
  UserInfo={NSLocalizedDescription=One or more parameters were invalid.})
```

`source=scan` 은 앞서 고친 핸들 보관이 작동한다는 뜻이다. 스캔에서 붙잡아둔 핸들로 connect 를 걸었다. 그러니 가설 1 의 수정 자체는 맞았다.

문제는 그 다음이다. `CBErrorDomain Code=1` — `CBError.invalidParameters`. CoreBluetooth 가 **파라미터가 잘못됐다며 연결 요청을 거부**했다.

파라미터라고는 옵션 딕셔너리뿐이다.

```swift
func connect(_ peripheral: PeripheralHandle, autoReconnect: Bool) {
  var options: [String: Any] = [:]
  if autoReconnect, #available(iOS 17.0, *) {
    options[CBConnectPeripheralOptionEnableAutoReconnect] = true
  }
  manager.connect(p.peripheral, options: options)
}
```

그리고 이 함수를 부르는 쪽은 **항상** `autoReconnect: true` 였다.

Apple 문서의 정의를 다시 읽어보면 답이 그대로 적혀 있다.

> An NSNumber (Boolean) indicating that the AutoReconnect is enabled for the peripheral is connected. **After peripheral device is connected**, this will allow the system to initiate connect to the peer device automatically when link is dropped.

"연결된 **뒤**, 링크가 끊기면 시스템이 자동으로 다시 붙게 한다." 이건 처음부터 **이미 연결된 기기의 재연결**을 위한 옵션이다. 아직 그 상태가 아닌 기기에 얹으면 파라미터가 유효하지 않다.

그런데 "그럼 언제부터 유효한가"를 코드로 판별하는 게 다음 함정이었다.

---

## 첫 번째 처방도 틀렸다

원인을 알았으니 고치는 건 쉬울 줄 알았다. "시스템이 아는 기기에만 켜면 되겠지" 하고 이렇게 갈랐다.

```swift
let known = central.retrievePeripherals(withIdentifiers: [id]).first
  ?? central.retrieveConnectedPeripherals(withService: serviceUUID)
      .first(where: { $0.identifier == id })
guard let p = known ?? discovered[id] else { throw Error.notFound }

let autoReconnect = known != nil    // ← 이게 틀렸다
central.connect(p, autoReconnect: autoReconnect)
```

빌드해서 다시 눌렀더니 여전히 실패했다. 로그를 보고 나서야 왜인지 알았다.

```
DIAG connect 호출 id=A1DCFFC7-…-0AA9CD84EE6E known=true
DIAG didFailToConnect ... Code=1 "One or more parameters were invalid."
```

`known=true` 였다. `retrievePeripherals(withIdentifiers:)` 가 이 기기를 돌려준 거다. 그래서 옵션이 켜진 채로 나갔고 그대로 거부당했다.

여기서 이 API 의 정의를 다시 봐야 한다. Apple 문서는 이렇게 적는다.

> Retrieve a list of known peripherals — peripherals that **you've discovered or connected to** in the past.

**"발견했거나(discovered)" 연결한** 이다. 방금 스캔에서 본 기기도 known 으로 잡힌다. 즉 이 API 는 "연결해 본 적 있는가"를 알려주지 않는다. auto-reconnect 를 쓸 수 있는 상태인지 **판별할 수단이 아니었던 것**이다.

그래서 옵션을 아예 빼고 A/B 로 확인했다.

```swift
let autoReconnect = false   // 실험: 옵션만 뗀다
```

이 빌드에서 같은 기기에 바로 붙었다.

```
DIAG connect 호출 known=false
DIAG didConnect — 서비스 탐색 시작
```

---

## 고친 방법 — 옵션을 쓰지 않는다

결론은 조건부가 아니라 제거였다.

```swift
// 애플 권장 순서: retrievePeripherals → retrieveConnectedPeripherals → 스캔
let known = central.retrievePeripherals(withIdentifiers: [id]).first
  ?? central.retrieveConnectedPeripherals(withService: serviceUUID)
      .first(where: { $0.identifier == id })
// 조회에 안 잡히는 기기는 스캔에서 붙잡아 둔 핸들이 메운다
guard let p = known ?? discovered[id] else { throw Error.notFound }

// auto-reconnect 옵션은 어느 경로에서도 켜지 않는다.
central.connect(p, autoReconnect: false)
```

| 상황 | peripheral 출처 | auto-reconnect |
|------|----------------|----------------|
| 처음 붙이는 기기 | 스캔에서 보관한 핸들 | **끈다** |
| 조회로 찾은 기기 | `retrievePeripherals` | **끈다** |
| 시스템에 이미 붙어 있음 | `retrieveConnectedPeripherals` | **끈다** |

peripheral 을 찾는 순서(조회 우선, 스캔 핸들 폴백)는 Apple 샘플 구조 그대로 두고, **옵션만 뺐다.**

잃는 게 있나 따져봤는데 거의 없었다. 링크가 끊긴 뒤 다시 붙는 일은 이미 앱이 한다 — 화면에 들어올 때 기억한 기기로 재연결하고, 주기 동기화도 따로 돈다. 시스템 auto-reconnect 는 그 위에 중복으로 얹히는 셈이다.

오히려 켜져 있으면 손해가 하나 있다. **자동 재연결이 켜진 상태에서는 실패가 `didFailToConnect` 로 오지 않는다.** 시스템이 계속 재시도하기 때문인데, 그래서 앱은 아무 콜백도 못 받고 타임아웃까지 매달린다. 진단을 어렵게 만드는 옵션이었던 셈이다.

### 회귀 시점 찾기

옵션이 언제 들어왔는지는 `git log -S` 한 줄로 나왔다.

```bash
git log --oneline -S "CBConnectPeripheralOptionEnableAutoReconnect" -- ios/
```

"연결한 기기를 기억해 스캔 없이 다시 붙는다"는 커밋이었다. 재연결을 빠르게 하려고 넣은 옵션이 정작 연결 자체를 막았다. 그 커밋과 증상이 드러난 시점 사이가 몇 주 벌어져 있어서, 코드만 봐서는 연결이 잘 안 됐다.

---

## 곁들여 만난 함정들

### dyld 심볼 누락으로 앱이 시작조차 안 되는 경우

이건 직접 겪진 않았지만 조사하다 발견한 함정이라 적어둔다. `CBConnectPeripheralOptionEnableAutoReconnect` 는 iOS 17 에서 추가된 심볼인데, `#available` 로 런타임 분기를 해도 **dyld 가 앱 시작 시점에 모든 참조 심볼을 해석**한다. iOS 16 이하에서는 심볼이 없어서 코드가 그 분기에 도달하는지와 무관하게 실행 즉시 크래시한다.

해법은 둘이다.

```swift
// 방법 1: 문자열 리터럴로 대체 (연결 옵션은 본질적으로 문자열 상수다)
options["CBConnectPeripheralOptionEnableAutoReconnect"] = true
```

또는 Build Phases → Link Binary With Libraries 에서 CoreBluetooth.framework 를 `Required` → `Optional` 로 바꿔 weak linking 을 건다. 그러면 심볼이 없을 때 dyld 가 크래시 대신 nil 로 두고, `#available` 분기가 정상 동작한다.

### connect 에는 시한이 없다

CoreBluetooth 의 `connect` 는 타임아웃이 없다. 기기가 나타날 때까지 무한정 pending 상태로 남는다. 이게 설계 의도이긴 하다 — 범위 밖으로 나간 기기가 돌아오면 자동으로 붙는다.

문제는 Swift concurrency 와 섞을 때다. `withCheckedThrowingContinuation` 은 **취소에 반응하지 않는다.** TaskGroup 의 다른 자식이 타임아웃을 던지고 `cancelAll()` 을 해도, 연결을 기다리는 continuation 은 영원히 깨어나지 않는다. TaskGroup 은 자식이 전부 끝나야 반환하므로 `connect()` 자체가 돌아오지 않는다.

타임아웃은 **대기 중인 continuation 을 직접 깨우는** 방식이어야 한다.

```swift
let timeoutTask = Task { [weak self] in
  try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
  guard !Task.isCancelled else { return }
  self?.abortConnect(p, error: .timeout)   // 대기를 직접 종결시킨다
}
defer { timeoutTask.cancel() }
```

### 에러의 실제 사유를 버리면 진단이 몇 시간 길어진다

이번 디버깅이 길어진 직접적 이유가 이거였다.

```swift
enum BleError: LocalizedError {
  case notFound
  case connectionFailed(String)   // ← 사유를 담는 자리가 있는데
  case timeout

  var errorDescription: String? {
    switch self {
    // ...
    case .connectionFailed: return "연결하지 못했습니다.\n잠시 후 다시 시도해 주세요."
    }
  }
}
```

`connectionFailed(String)` 에 CoreBluetooth 가 준 실제 사유가 담겨 있는데, `errorDescription` 이 그걸 통째로 버리고 고정 문구를 반환한다. 그래서 화면에도 로그에도 `Code=1 "One or more parameters were invalid."` 라는 결정적 단서가 안 남았다.

사용자에게 보여주는 문구는 부드러워야 하지만, **로그에는 원문이 남아야 한다.** 최소한 이 정도는 필요하다.

```swift
func transportDidFailToConnect(_ p: PeripheralHandle, error: Error?) {
  Log.ble.error("연결 실패 — \(error?.localizedDescription ?? "이유 없음", privacy: .public)")
  finishConnectWaiter(p, throwing: .connectionFailed(error?.localizedDescription ?? ""))
}
```

### 안드로이드에는 없는 함정이다

같은 기능을 안드로이드에서 만들면 이 문제가 아예 안 생긴다. 안드로이드는 MAC 주소만 있으면 `BluetoothAdapter.getRemoteDevice(address)` 로 언제든 `BluetoothDevice` 객체를 만들 수 있다. 스캔에서 발견했든 안 했든, 시스템이 알든 모르든 상관없다.

그래서 두 플랫폼을 같이 개발하면 "안드로이드는 되는데 iOS 만 안 된다"가 되고, 코드 구조가 비슷하니 원인을 코드 대칭성에서 찾게 된다. 실제로는 플랫폼 API 의 전제가 다른 거다.

---

## 실전 체크리스트

BLE 기기를 iOS 앱에 붙일 때 확인할 것들을 정리했다.

1. **`.poweredOn` 을 기다린 뒤에 스캔한다.** 그 전에 부른 `scanForPeripherals` 는 조용히 무시된다.
2. **발견한 peripheral 은 반드시 강한 참조로 보관한다.** 값 타입 DTO 만 저장하면 안 된다.
3. **첫 연결은 스캔 핸들로, 재연결은 `retrievePeripherals` 로.** 순서를 섞지 않는다.
4. **`CBConnectPeripheralOptionEnableAutoReconnect` 는 시스템이 아는 기기에만.** 처음 만나는 기기에 걸면 `CBError Code=1`.
5. **iOS 16 이하를 지원하면 심볼 참조에 주의한다.** 문자열 리터럴이나 weak linking.
6. **연결 실패의 원문 error 를 로그에 남긴다.** 사용자 문구와 진단 정보는 별개다.
7. **타임아웃은 continuation 을 직접 깨우는 방식으로.** Task 취소에 기대지 않는다.
8. **새 기기 / 캐시가 빈 상태로 한 번은 시험한다.** 이 버그류는 그 경로에서만 드러난다.

마지막 항목이 이번 건의 핵심 교훈이다. "붙여본 적 있는 기기"로만 시험하면 첫 연결 경로는 영원히 검증되지 않는다. 릴리스 전에 페어링을 지우거나 다른 기기로 한 번은 붙여봐야 한다.

---

## 정리

세 줄로 요약하면 이렇다.

- `CBConnectPeripheralOptionEnableAutoReconnect` 는 **연결된 뒤**의 재연결용 옵션이다. 첫 연결에 얹으면 `CBError Code=1` 로 요청 자체가 거부된다.
- "시스템이 아는 기기에만 켜면 된다"도 **틀렸다.** `retrievePeripherals` 는 *발견만 한* 기기도 돌려주므로 그 판정으로는 가릴 수 없다. 답은 조건부가 아니라 제거였다.
- 스캔에서 발견한 `CBPeripheral` 은 강한 참조로 들고 있어야 하고, 첫 연결은 그 핸들로 걸어야 한다.

가설 두 개와 처방 하나를 연달아 틀렸는데, 셋 다 "그럴듯했지만 로그로 확인한 게 아니었다". 결국 실패 지점에 `print` 하나 박고 `--console` 로 띄운 게 5분 만에 답을 줬고, 그 뒤 옵션만 떼는 A/B 한 번이 처방까지 확정해줬다. 추측을 겹쳐 쌓기 전에 계측부터 하는 게 빠르다는 걸 또 배웠다.

마지막 하나 — **고쳤다고 생각한 뒤에도 실기로 한 번 더 확인해야 한다.** 이 글의 처방은 원래 "조건부로 켠다"였고, 그대로 공개했다가 실기 로그에 반박당해 고쳤다.

iOS 플랫폼 버그를 A/B 로 좁혀간 다른 기록은 [iOS 26 CAEmitterLayer 전체폭 line emitter 방출 드롭 회귀](/posts/ios-26-caemitterlayer-full-width-line-emitter-bug/)에 정리해뒀다.

## 참고

- [CBConnectPeripheralOptionEnableAutoReconnect — Apple Developer](https://developer.apple.com/documentation/corebluetooth/cbconnectperipheraloptionenableautoreconnect)
- [Best Practices for Interacting with a Remote Peripheral Device — Apple](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/BestPracticesForInteractingWithARemotePeripheralDevice/BestPracticesForInteractingWithARemotePeripheralDevice.html)
- [Why Your iOS BLE Scan Returns No Results — Punch Through](https://punchthrough.com/ios-ble-scan-returns-no-results/)
- [Measuring distance between devices using Channel Sounding — Apple](https://developer.apple.com/documentation/CoreBluetooth/measuring-distance-between-devices-using-channel-sounding)
