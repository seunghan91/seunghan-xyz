---
title: "Flutter+Rails 실시간 인프라 4대 단절 고치기 — FCM 딥링크, ActionCable JWT, 익명→회원 연결"
date: 2026-04-16T09:00:00+09:00
draft: false
tags: ["Flutter", "Rails", "FCM", "ActionCable", "JWT"]
description: "모바일 앱에서 푸시 알림 탭이 특정 화면으로 안 열리는 이유, ActionCable이 WebSocket에서 JWT를 못 받는 이유, 익명 게스트 데이터를 회원가입 시 이관하는 race-safe 패턴까지 한 세션에서 다 고친 기록."
---

토너먼트 앱 하나를 Flutter로 전환하고 있는데, 사용자 입장에서 제일 중요한 시나리오가 동작을 안 했다. "로그인 → 알림 수신 → 알림 탭 → 내 코트로 이동 → 대기/경기/결과 확인". 이게 끊기면 앱이 있으나 마나다.

처음에는 코드 조각은 대부분 있는 것 같았다. FCM 토큰 등록 로직도 있고, ActionCable 클라이언트 클래스도 있고, 스코어 입력 화면도 있다. 그런데 막상 실제로 알림을 탭해도 앱이 홈으로만 열린다. 실시간 업데이트도 안 온다. 왜?

탐색해보니 **연결된 것처럼 보이는 부품 사이에 네 군데가 끊겨 있었다**. 이 포스트는 그 네 군데를 하루 세션에서 다 고친 기록이다. 각 단절마다 왜 그게 2026년에도 여전히 함정인지 근거도 같이 정리한다.

---

## 플로우별 단절 진단

사용자 관점의 9단계를 표로 점검한다.

| # | 단계 | 상태 | 원인 |
|---|------|------|------|
| 1 | 로그인 (JWT) | ✅ | 완비 |
| 2 | FCM 토큰 등록 | ✅ | 완비 |
| 3 | 푸시 수신 | ⚠️ | 서버 이벤트 2종뿐 (코트배정/경기결과). "라운드 시작", "선수 호출", "매치 예정"은 발송 자체가 없음 |
| 4 | 알림 탭 → 딥링크 | ❌ | **단절**. `onMessageOpenedApp`/`getInitialMessage`/`onBackgroundMessage` 핸들러 0개 |
| 5 | "내 다음 경기" 조회 | ⚠️ | 전용 API 없음. 전체 매치 필터링으로 우회 |
| 6 | 실시간 업데이트 | ❌ | **단절**. ActionCable Connection이 session 기반만. 모바일 JWT 토큰 인식 불가 → 폴링 의존 |
| 7 | 체크인/스코어 | ✅ | 완비 |
| 8 | 결과 확인 | ⚠️ | Flutter UI만 남음 |
| 9 | 익명→회원 연결 | ❌ | 구현 없음 |

③④⑥⑨가 실제 단절. 이거 네 개가 동시에 깨져 있으면 증상만 보고 원인을 못 찾는다. 알림이 안 오는 건지, 알림은 왔는데 탭이 반응을 안 하는 건지, 탭은 반응하는데 화면이 안 뜨는 건지 구분이 안 된다. 하나씩 거꾸로 뚫어야 한다.

---

## 단절 1: FCM 딥링크가 없다

알림이 시스템 트레이에는 뜨는데 탭하면 앱이 홈으로만 열리는 증상. 원인은 간단하다. **FCM에는 네 가지 상태가 있고, 각각 다른 API로 받아야 하는데 하나도 연결돼 있지 않았다.**

### 네 가지 상태, 네 가지 API

| 상태 | API | 실행 위치 |
|------|-----|-----------|
| Foreground (앱 사용 중) | `FirebaseMessaging.onMessage.listen` | 메인 아이솔레이트 |
| Background 탭 (앱 백그라운드) | `FirebaseMessaging.onMessageOpenedApp.listen` | 메인 아이솔레이트 |
| Terminated cold start (앱 꺼진 상태 → 탭으로 실행) | `FirebaseMessaging.instance.getInitialMessage()` | 메인 아이솔레이트 (한 번만 반환) |
| Terminated data-only (data-only 메시지, 앱 꺼짐) | `FirebaseMessaging.onBackgroundMessage(handler)` | **별도 아이솔레이트** |

여기서 두 가지가 핵심 함정이다.

**함정 1: `getInitialMessage()`는 `runApp()` *전*에 불러야 한다.**

```dart
// 잘못된 위치: Widget.initState 안에서 호출
@override
void initState() {
  super.initState();
  FirebaseMessaging.instance.getInitialMessage().then(_handle);
  // 이미 늦었다. 네이티브 레이어가 메시지를 소비해버렸다.
}
```

Firebase 공식 문서에도 `getInitialMessage()`는 콜드 스타트 시 앱을 실행시킨 `RemoteMessage`를 **한 번만** 돌려준다고 못 박혀 있다. 엔진이 이미 루트 위젯을 그리기 시작했으면 그 페이로드는 이미 사라진 뒤다. 결과: 딥링크 무응답, 앱이 루트에서 시작.

올바른 순서는 이렇다.

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();

  // 1. 백그라운드 핸들러를 제일 먼저 등록
  FirebaseMessaging.onBackgroundMessage(_firebaseBackgroundHandler);

  // 2. getInitialMessage는 runApp 전에
  final RemoteMessage? initial =
      await FirebaseMessaging.instance.getInitialMessage();
  if (initial != null) {
    // 라우터가 준비된 후 소비할 수 있게 어딘가에 쟁여둔다
    _pendingIntent = parsePayload(initial);
  }

  runApp(const MyApp());
}
```

**함정 2: `onBackgroundMessage` 핸들러는 `@pragma('vm:entry-point')` 필수.**

별도 아이솔레이트에서 Dart VM이 직접 진입하는 함수라서 top-level이어야 하고, AOT 컴파일 시 tree-shaking에 의해 제거되지 않도록 명시해야 한다. pragma 없으면 증상이 **조용한 실패**다. 컴파일도 되고 실행도 되는데 백그라운드 메시지가 들어왔을 때 핸들러가 호출되지 않는다. 로그도 안 남는다.

```dart
@pragma('vm:entry-point')
Future<void> _firebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(); // 이 아이솔레이트에서도 초기화 필요
  // 여기서는 GoRouter도, BLoC도, Provider도 접근 불가
  // 필요하면 SharedPreferences 같은 영속 저장소에만 쓴다
}
```

### 페이로드 → 라우트 매핑

핸들러에서 직접 `router.go()`를 호출하면 라우터가 아직 준비 안 된 시점이라 깨지기 쉽다. Perplexity로 조사해 봐도 2026년 Flutter 커뮤니티 best practice는 **"intent를 상태에 저장 → 라우터가 ready일 때 consume"** 패턴이다.

```dart
class NotificationIntent {
  final String type; // 'match', 'court', 'round_started' 등
  final String? id;

  String toPath() {
    switch (type) {
      case 'match':
      case 'match_upcoming':
      case 'player_called':
        return id != null ? '/m/$id' : '/';
      case 'court_assigned':
        return id != null ? '/courts/$id' : '/courts';
      case 'round_started':
        return '/bracket';
      default:
        return '/';
    }
  }
}
```

실제로는 cold start 시 `runApp()` 이전에 파싱한 intent를 글로벌 서비스에 pending으로 저장해 두고, 라우터 위젯 `initState` 안에서 `WidgetsBinding.instance.addPostFrameCallback`으로 1프레임 뒤에 `router.go(intent.toPath())`를 호출한다.

이 패턴은 BLoC든 Riverpod이든 Provider든 무관하다. **FCM에서 중요한 건 상태관리 선택이 아니라 "언제 consume하느냐"다.**

---

## 단절 2: ActionCable이 모바일 JWT를 못 받는다

백엔드가 Rails라서 실시간은 기본 ActionCable을 쓰고 있었다. Rails의 `ApplicationCable::Connection#connect`는 보통 이렇게 생겼다.

```ruby
module ApplicationCable
  class Connection < ActionCable::Connection::Base
    identified_by :current_user

    def connect
      self.current_user = find_verified_user
      reject_unauthorized_connection unless current_user
    end

    private

    def find_verified_user
      User.find_by(id: request.session[:user_id])
    end
  end
end
```

브라우저에서는 잘 돌아간다. 세션 쿠키가 WebSocket upgrade 시 자동으로 같이 가기 때문이다. 그런데 **모바일 앱은 세션 쿠키가 아니라 JWT를 쓴다**. 그리고 WebSocket은 브라우저 API 제약 때문에 Authorization 헤더를 못 붙인다. 모바일 클라이언트는 JS가 아니어도 호환성 때문에 같은 제약을 따르는 경우가 많다.

### 해결: 쿼리 파라미터 `?token=<jwt>`

2026년에도 가장 널리 쓰이는 패턴이 이거다. 모바일에서는 HTTPS/WSS로 암호화되고 표준 로그 설정에서 쿼리 파라미터가 노출될 여지는 있지만 대부분의 팀이 trade-off를 받아들이고 있다.

```ruby
def find_verified_user
  user_from_jwt || User.find_by(id: request.session[:user_id])
end

def user_from_jwt
  token = request.params[:token].presence
  return nil unless token

  payload = Api::V2::Auth::TokenEncoder.decode(token)
  return nil unless payload["sub_type"] == "user"

  api_token = ApiToken.active.find_by(id: payload["api_token_id"])
  return nil unless api_token&.subject_type == "user" &&
                    api_token.user_id.to_s == payload["sub"].to_s

  api_token.user
rescue Api::V2::Auth::TokenEncoder::InvalidTokenError
  nil
end
```

참가자/게스트 토큰은 의도적으로 거절한다. 채널을 구독할 수 있는 주체를 명시적으로 좁히는 게 안전하다.

### 보안 트레이드오프

Perplexity로 업계 대안들을 비교해봤다.

| 접근 | 방법 | 장점 | 단점 |
|------|------|------|------|
| ActionCable + query token | `?token=jwt` | Rails 8에서 바로 됨 | 로그 노출 가능 |
| Sec-WebSocket-Protocol | `['jwt', token]` 서브프로토콜에 토큰 | URL에 안 남음 | 일부 프록시 호환성 이슈, 핸드셰이크 복잡 |
| Pusher Channels | 앱키 + 서버 서명 auth endpoint | 토큰 미노출 | 벤더 lock-in, 비용 |
| Socket.io | 쿼리나 커스텀 핸드셰이크 | 유연함 | JS 전용 디펜던시 |

현실적으로 모바일 앱에서 짧은 만료(15분 이하) + HTTPS + 서버 로그 마스킹이면 query param이 비용 대비 무난하다. 로그 마스킹이 조직 정책상 부담스러우면 Sec-WebSocket-Protocol로 넘어가는 게 정공법이다.

### Flutter 쪽 클라이언트

```dart
final String? token = await _session.accessToken();
final Uri cableUri = token == null || token.isEmpty
    ? baseUri
    : baseUri.replace(
        queryParameters: <String, String>{
          ...baseUri.queryParameters,
          'token': token,
        },
      );
await _client.connect(cableUri);
```

WebSocketChannel 자체는 Uri 하나만 받으니 토큰을 URL에 끼워 넣는 게 사실상 유일한 방법이다.

### 테스트

Rails ActionCable TestCase로 검증했다.

```ruby
test "jwt token query param authenticates user" do
  user = users(:one)
  bundle = Api::V2::Auth::TokenManager.new(request: fake_request).issue_user_tokens(user)

  connect "/cable?token=#{bundle[:access_token]}"
  assert_equal user, connection.current_user
end

test "invalid jwt is rejected" do
  assert_reject_connection { connect "/cable?token=not-a-real-token" }
end

test "participant jwt does not authenticate as user" do
  # ... participant 토큰은 거절돼야 함
end
```

참고로 세션 기반 로그인 테스트는 ActionCable TestCase에서 `request.session`을 세팅하기가 까다롭다. 그건 프로덕션 브라우저 테스트로 커버하고 유닛 테스트는 새로 추가한 JWT 경로에 집중시키는 게 실용적이다.

---

## 단절 3: 알림 이벤트 자체가 부족하다

딥링크가 열려도 **알림 자체가 안 오면 의미가 없다**. 기존에는 두 가지 이벤트만 있었다.

- `notify_court_assigned` — 코트 배정 시
- `notify_match_completed` — 경기 종료 시

"라운드 시작했으니 본인 경기 확인해라", "상대가 기다린다 빨리 와라", "15분 뒤 시작이다" 같은 **액션 유도성 알림**이 0개였다. 그러면 사용자는 앱을 켜서 확인해야 하는데, 이게 매번 있으면 앱을 안 열게 된다.

세 개를 추가했다.

```ruby
module Notifications
  class PushService
    # 라운드 시작 → Flutter에서 /bracket으로 딥링크
    def self.notify_round_started(tournament:, round_number:, match_ids: [])
      matches = tournament.matches.where(id: match_ids)
                          .includes(match_players: { participant: :user })
      users = matches.flat_map { |m| 
        m.match_players.filter_map { |mp| mp.participant.try(:user) } 
      }.uniq
      return if users.empty?

      users.each do |user|
        PushNotificationJob.perform_later(
          user_id: user.id,
          notification_type: "match_invite",
          title: "Round #{round_number} started",
          body: "...",
          data: {
            type: "round_started",
            id: tournament.id.to_s,
            round_number: round_number
          }
        )
      end
    end

    # 운영자가 선수 호출 → Flutter에서 /m/:id로 딥링크
    def self.notify_player_called(match:, called_by: nil)
      # ...
    end

    # 매치 15분 전 리마인더 → Flutter에서 /m/:id로 딥링크
    def self.notify_match_upcoming(match:, minutes_until: 15)
      # ...
    end
  end
end
```

여기서 중요한 게 **`data.type` 값이 Flutter 쪽 `NotificationIntent.toPath()`와 같은 어휘를 써야 한다**는 점이다. 서버/클라이언트에서 따로 문자열을 정의하면 오타 하나에 몇 시간씩 날아간다. 가능하면 공유 YAML이나 서버 스키마 한 곳에서 enum으로 관리하는 게 장기적으로 안전하다.

### 자동 스케줄은 모델 콜백에 꽂는다

`notify_match_upcoming`은 15분 전에 쏴야 한다. 수동 스케줄로 두면 개발자가 까먹는다. Match 모델에 `after_commit` 훅을 추가했다.

```ruby
class Match < ApplicationRecord
  after_commit :schedule_upcoming_reminder,
               on: %i[create update],
               if: :reminder_scheduling_needed?

  private

  def reminder_scheduling_needed?
    saved_change_to_scheduled_at? &&
      status_scheduled? &&
      scheduled_at.present? &&
      scheduled_at > 15.minutes.from_now
  end

  def schedule_upcoming_reminder
    users_for_reminder.each do |user|
      next unless user.push_match_reminder?
      MatchReminderJob
        .set(wait_until: scheduled_at - 15.minutes)
        .perform_later(match_id: id, user_id: user.id)
    end
  end
end
```

포인트는 `saved_change_to_scheduled_at?`. scheduled_at이 실제로 바뀐 커밋에서만 재스케줄한다. 안 그러면 단순 업데이트마다 중복 잡이 쌓인다.

---

## 단절 4: 익명으로 참가한 데이터가 회원가입 후 사라진다

모바일 토너먼트 앱에서 흔한 시나리오다. 현장에서 QR 스캔으로 참가 → 경기 하러 감 → 집에 가서 "이거 내 기록 보고 싶네" 해서 회원가입. 이 순간 **과거 기록이 새 계정에 안 붙으면** 앱을 다시 안 쓴다.

Firebase의 `linkWithCredential()`과 똑같은 문제인데 Rails에서는 직접 구현해야 한다. Perplexity 조사 결과 2026년 표준 패턴은 이렇다.

### 스키마 설계

별도 `ClaimToken` 테이블을 만드는 것보다 **대상 레코드에 `claim_device_id` 컬럼을 직접 달고 `user_id` nullable**을 두는 게 단순하다. 클레임은 그냥 "user_id가 nil이고 device_id가 일치하면 user_id를 채운다"로 줄어든다.

```ruby
class AddClaimDeviceIdToPlayers < ActiveRecord::Migration[8.1]
  def change
    add_column :players, :claim_device_id, :string
    # 부분 인덱스: 아직 clamim 안된 레코드만 조회 대상
    add_index :players, :claim_device_id,
              where: "user_id IS NULL AND claim_device_id IS NOT NULL",
              name: "index_players_on_claim_device_id_unclaimed"
  end
end
```

### Race-safe 서비스

두 기기에서 동시에 같은 device_id로 클레임하면? 트랜잭션 없이는 둘 다 성공해서 양쪽 계정에 이중 귀속될 수 있다. 해결은 SERIALIZABLE + row-level lock.

```ruby
class GuestDataClaimer
  Result = Struct.new(:claimed_count, :player_ids, keyword_init: true)

  def self.call(user:, device_identifier:)
    new(user: user, device_identifier: device_identifier).call
  end

  def call
    return Result.new(claimed_count: 0, player_ids: []) \
      if @device_identifier.blank? || @user.nil?

    player_ids = []
    ApplicationRecord.transaction(isolation: :serializable) do
      players = Player
                  .lock("FOR UPDATE")
                  .where(claim_device_id: @device_identifier, user_id: nil)
                  .to_a
      player_ids = players.map(&:id)

      if player_ids.any?
        Player.where(id: player_ids).update_all(
          user_id: @user.id,
          updated_at: Time.current
        )
      end
    end

    Result.new(claimed_count: player_ids.size, player_ids: player_ids)
  end
end
```

두 번째 호출이 첫 번째를 기다렸다가 돌기 때문에, 두 번째 호출은 이미 claim된 레코드를 못 찾아 0건 반환된다. 멱등(idempotent)이다.

### Flutter 쪽 device identifier

클라이언트에는 안정적인 per-install 식별자가 필요하다. 로그아웃해도 지우면 안 된다 (다시 회원가입했을 때 이전 게스트 기록이 계속 달라붙어야 함).

```dart
@lazySingleton
class DeviceIdentifierService {
  DeviceIdentifierService(this._storage);
  final FlutterSecureStorage _storage;
  static const String _key = 'guest_device_identifier';

  Future<String> getOrCreate() async {
    final existing = await _storage.read(key: _key);
    if (existing != null && existing.isNotEmpty) return existing;
    final fresh = _generate();
    await _storage.write(key: _key, value: fresh);
    return fresh;
  }

  String _generate() {
    final rnd = Random.secure();
    final bytes = List<int>.generate(16, (_) => rnd.nextInt(256));
    return 'dev-${bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
  }
}
```

`flutter_secure_storage`는 iOS에서 Keychain, Android에서 EncryptedSharedPreferences를 쓴다. 앱 삭제 시 초기화되는 플랫폼도 있지만, 같은 앱 설치 상태에서는 안정적이다.

게스트로 Player를 만들 때 이 식별자를 body에 함께 전송하고, 로그인/회원가입 성공 시 claim 엔드포인트를 한 번 호출한다.

```dart
Future<void> _claimGuestData() async {
  try {
    final deviceId = await _deviceIdentifierService.read();
    if (deviceId == null || deviceId.isEmpty) return;
    await _api.claimGuestData(<String, dynamic>{
      'deviceIdentifier': deviceId,
    });
  } catch (_) {
    // 실패해도 로그인 자체는 성공 상태를 유지.
    // 사용자가 프로필에서 수동 재시도할 수 있게 UX 보강 여지.
  }
}
```

---

## 실전에서 배운 것

같은 기능을 다시 만들 일이 있으면 이렇게 순서를 잡을 것 같다.

1. **플로우를 숫자 단계로 쪼개서 표로 그린다**. ✅/⚠️/❌로 표시하면 어디가 진짜 끊어졌는지 보인다. 머리로만 생각하면 "대충 되는 것 같은데 뭔가 이상한" 상태로 영영 머문다.

2. **알림 인프라는 "발송"과 "수신"을 분리해서 검증한다**. 둘 다 끊어져 있으면 alert 테스트가 double negative라서 뭘 고쳐야 할지 판단이 안 선다. 서버 로그에서 job이 enqueue 되는지, 디바이스 토큰으로 실제 전송 시도가 있는지, 탭 핸들러에 도달하는지를 각각 다른 방법으로 확인.

3. **WebSocket 인증은 세션과 토큰이 별도 경로로 붙을 수 있게 설계한다**. 세션 삭제는 하고 싶지 않고, 토큰 경로만 추가하는 식으로. `find_verified_user`에서 `token || session` OR 패턴이 생각보다 자주 유용하다.

4. **익명→회원 전환은 처음부터 device_id 컬럼을 잡아둔다**. 나중에 "Firebase Anonymous Auth 쓸까?" 하다가 구조가 어긋나면 마이그레이션이 훨씬 비싸다. 초기에 nullable + partial index 한 줄이면 끝나는 일이다.

5. **Flutter DI 관련**: `@lazySingleton`으로 묶어두면 build_runner가 알아서 연결한다. 생성자 시그니처만 바꾸고 `dart run build_runner build --delete-conflicting-outputs` 한 번 돌리면 끝. 그 다음 `dart analyze lib/`로 에러 0 확인하고 넘어간다.

21개 새 테스트 추가, 29개 기존 테스트 회귀 확인, `dart analyze lib/` 에러 0으로 세션을 마무리했다. 실기기 E2E는 다음 차례.

---

## 자주 찾아오는 에러 키워드

구글 검색용으로 남겨둔다. 같은 증상 만난 사람이 들어올 수 있게.

- `Flutter FCM getInitialMessage returns null`
- `FirebaseMessaging.onBackgroundMessage not called pragma vm:entry-point`
- `Flutter FCM notification tap does not navigate`
- `ActionCable WebSocket Authorization header not supported`
- `Rails ApplicationCable Connection JWT mobile`
- `Flutter WebSocketChannel query parameter token`
- `Rails anonymous user data link after signup`
- `SERIALIZABLE transaction Rails claim data migration`
- `flutter_secure_storage device identifier persistence`

네 가지 단절 중 하나라도 겪고 있으면 이 순서대로 뚫어보면 된다.
