---
title: "Rails 두 앱 사이에 SSO 구현하기 — 세션 유실·리다이렉트 루프·Universal Links 삽질까지"
date: 2026-02-17
draft: false
tags: ["Rails", "SSO", "iOS", "Universal Links", "Hotwire Native", "보안"]
description: "Rails 8 두 앱 사이에 커스텀 SSO를 구현하고, Hotwire Native 앱이 설치돼 있으면 Universal Links로 자동 전환되도록 만든 과정. 세션 유실·리다이렉트 루프·AASA 설정 삽질까지."
cover:
  image: "/images/og/rails-sso-universal-links-hotwire-native.png"
  alt: "Rails Sso Universal Links Hotwire Native"
  hidden: true
categories: ["Hotwire Native", "iOS"]
series: ["Hotwire Native Mobile App"]
---

두 개의 Rails 8 서비스가 있다. 하나는 메인 앱(IdP 역할), 다른 하나는 연동 서비스(RP 역할). 연동 서비스 로그인 페이지에 "메인 앱으로 로그인" 버튼을 넣고, SSO로 인증 후 돌아오는 플로우를 구현했다.

거기에 iOS Hotwire Native 앱이 설치돼 있으면, 브라우저 대신 네이티브 앱에서 인증이 진행되도록 Universal Links까지 붙였다.

OAuth 2.0 같은 표준 프로토콜을 쓰지 않고 직접 구현한 이유는 두 서비스 모두 직접 운영하는 내부 시스템이고, 외부 IdP(Auth0, Cognito 등)를 붙이기에는 오버엔지니어링이었기 때문이다. 핵심 개념(토큰 발급, 검증, 세션 관리)은 표준과 동일하다.

---

## 목표 플로우

```
[연동 서비스] "메인 앱으로 로그인" 클릭
  → 메인 앱 /auth/sso/authorize 로 리다이렉트
  → (앱 설치 시) iOS Universal Link → 네이티브 앱 열림
  → (미설치 시) 브라우저에서 로그인
  → 이미 로그인 상태면 바로 토큰 발급
  → 미로그인이면 OTP 로그인 → 토큰 발급
  → "인증 완료" 페이지 (2초 대기) → 콜백 URL로 리다이렉트
  → 연동 서비스가 토큰 검증 → 로그인 완료
```

RP(Relying Party) 쪽에서는 로그인 버튼 클릭 시 `state` 파라미터를 생성해서 세션에 저장하고, 콜백에서 이를 검증해 CSRF를 방지한다.

---

## 삽질 1: SSO 파라미터가 로그인 과정에서 유실됨

### 문제

SSO authorize 엔드포인트에 `before_action :require_authentication`을 걸어놨더니:

1. 미로그인 상태에서 SSO authorize 접근
2. `store_location`이 현재 URL을 `session[:return_to]`에 저장
3. 로그인 페이지로 리다이렉트
4. OTP 인증 완료
5. `redirect_back_or(dashboard_path)`가 `/auth/sso/authorize`로 돌려보냄
6. **하지만 query string(`client_id`, `redirect_uri`, `state`)이 날아감!**

`store_location`은 `request.fullpath`를 저장하니까 쿼리 파라미터도 포함되어야 하는데, OTP 인증 플로우가 여러 단계(코드 입력, 매직링크, 이메일 답장 등)를 거치면서 세션이 꼬이는 경우가 있었다.

Rails의 `store_location` 구현을 직접 들여다보면, `request.fullpath`를 그대로 저장하는 건 맞다. 문제는 다단계 인증 과정에서 각 단계마다 POST 요청이 들어오고, 일부 구현에서는 각 단계마다 `store_location`이 새 값으로 덮어씌워진다. OTP 코드 입력 페이지, 매직링크 클릭 후 처리 페이지 등을 거치면서 원래 SSO 파라미터가 포함된 URL이 사라지는 것이다.

### 해결

`before_action :require_authentication`을 제거하고, SSO 파라미터를 명시적으로 세션에 저장하는 방식으로 변경했다:

```ruby
# IdP: SSO Controller
def authorize
  # 파라미터 검증 (client_id, redirect_uri, state)
  validate_sso_params! # client_id 허용 목록, redirect_uri 허용 목록 검증

  unless signed_in?
    session[:sso_params] = {
      redirect_uri: redirect_uri,
      state: state,
      client_id: client_id
    }
    redirect_to sign_in_path
    return
  end

  # 토큰 발급 + 인증 완료 페이지
  sso_token = SsoToken.create!(
    user: current_user,
    client_id: client_id,
    expires_at: 5.minutes.from_now
  )
  @callback_url = "#{redirect_uri}?token=#{CGI.escape(sso_token.token)}&state=#{CGI.escape(state)}"
  render :authorize_complete
end
```

로그인 완료 후 SSO 플로우를 재개하는 `complete` 액션 추가:

```ruby
def complete
  sso_params = session.delete(:sso_params)
  return redirect_to dashboard_path unless sso_params

  redirect_to auth_sso_authorize_path(
    client_id: sso_params["client_id"],
    redirect_uri: sso_params["redirect_uri"],
    state: sso_params["state"]
  )
end
```

그리고 세션 컨트롤러의 모든 로그인 성공 경로에서 SSO 플로우를 체크:

```ruby
private

def redirect_after_sign_in
  if session[:sso_params].present?
    redirect_to auth_sso_complete_path
  else
    redirect_back_or(dashboard_path)
  end
end
```

OTP, 매직링크, 이메일 인증 등 모든 로그인 방식에서 이 메서드를 공통으로 호출하도록 리팩터링했다.

**핵심**: 프레임워크의 `store_location`/`redirect_back_or`에 의존하지 말고, 중요한 컨텍스트는 명시적으로 세션에 저장할 것. 특히 다단계 인증 플로우(OTP, 매직링크 등)에서는 중간에 세션 데이터가 예상과 다르게 동작할 수 있다.

---

## 삽질 2: 토큰 검증 시 HMAC 서명 불일치

### 문제

IdP가 발급한 SSO 토큰을 RP가 back-channel로 검증하는 구조:

```
RP → POST /auth/sso/verify (token + HMAC signature) → IdP
IdP → 서명 검증 + 토큰 유효성 확인 → 사용자 정보 반환
```

front-channel(브라우저 리다이렉트)로만 토큰을 주고받으면, 중간자가 토큰을 탈취해서 다른 사용자인 척 RP에 요청을 보낼 수 있다. back-channel 검증은 이를 막기 위한 것이다.

로컬에서는 잘 되는데 배포 환경에서 서명 불일치가 발생했다. 원인: **양쪽 서버의 `SSO_SHARED_SECRET` 환경변수가 달랐다.**

Render 같은 배포 플랫폼에서 환경변수를 각각 설정할 때, 복사붙여넣기 과정에서 앞뒤 공백이 들어가는 경우가 있다. HMAC은 바이트 단위로 비교하므로 공백 하나만 달라도 100% 불일치가 발생한다.

### 해결

배포 플랫폼 API로 양쪽 서비스에 동일한 시크릿을 설정:

```bash
# 시크릿 생성
SECRET=$(openssl rand -hex 32)
echo $SECRET  # 이 값을 양쪽 서비스에 동일하게 설정

# Render API로 환경변수 설정 (IdP와 RP 서비스 각각 실행)
curl -X PUT "https://api.render.com/v1/services/$SERVICE_ID/env-vars" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"key":"SSO_SHARED_SECRET","value":"'"$SECRET"'"}]'
```

HMAC 검증 코드:

```ruby
# RP → IdP 요청 시
body = { token: token }.to_json
signature = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, body)}"

response = HTTP.headers(
  "Content-Type" => "application/json",
  "X-SSO-Signature" => signature
).post("#{IDP_URL}/auth/sso/verify", json: { token: token })

# IdP에서 검증
def verify
  body = request.body.read
  expected = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, body)}"
  signature_header = request.headers["X-SSO-Signature"]

  unless ActiveSupport::SecurityUtils.secure_compare(signature_header.to_s, expected)
    render json: { error: "invalid_signature" }, status: :unauthorized
    return
  end

  # 토큰 유효성 확인
  params = JSON.parse(body)
  sso_token = SsoToken.find_by(token: params["token"])

  if sso_token.nil? || sso_token.expires_at < Time.current || sso_token.used_at.present?
    render json: { error: "invalid_token" }, status: :unauthorized
    return
  end

  sso_token.update!(used_at: Time.current)
  render json: { user: { id: sso_token.user.id, email: sso_token.user.email } }
end
```

**핵심**: `secure_compare`로 타이밍 공격 방지. 일반 `==` 비교는 문자열 길이에 따라 응답 시간이 달라져서 시크릿을 추론할 수 있다. 또한 `request.body.read`는 한 번만 읽을 수 있으므로, 검증과 파싱 중 어느 쪽을 먼저 하든 body를 변수에 저장해서 재사용해야 한다.

---

## 삽질 3: 인증 완료 후 사용자에게 아무 피드백 없이 리다이렉트

### 문제

SSO 인증 성공 후 즉시 `redirect_to callback_url`을 하면:
- 사용자 입장에서 "뭐가 된 거지?" 하고 혼란스러움
- 특히 앱 간 전환 시 화면이 순간적으로 깜빡이기만 함
- 에러가 나도 너무 빠르게 지나가서 디버깅이 어려움

### 해결

"인증 완료" 중간 페이지를 추가하고 2초 후 자동 리다이렉트:

```erb
<div class="text-center">
  <div class="checkmark-icon"><!-- 체크마크 SVG --></div>
  <h2>인증 완료</h2>
  <p><strong><%= current_user.name %></strong>님으로 인증되었습니다.</p>
  <div class="spinner"><!-- 로딩 스피너 --></div>
  <a href="<%= @callback_url %>">자동으로 이동하지 않으면 여기를 클릭하세요</a>
</div>

<script>
  setTimeout(function() {
    window.location.href = "<%= j @callback_url %>";
  }, 2000);
</script>
```

`j` 헬퍼(= `escape_javascript`)로 콜백 URL을 이스케이프하는 게 중요하다. 콜백 URL에 따옴표나 슬래시가 있으면 XSS가 발생할 수 있다.

이 중간 페이지는 Hotwire Native 앱에서도 잘 동작한다. 2초 후 `window.location.href`를 변경하면 Hotwire가 이를 감지해서 적절히 처리한다.

---

## 삽질 4: iOS 앱이 설치돼 있어도 브라우저에서 열림

### 문제

SSO 리다이렉트 URL이 `https://example.com/auth/sso/authorize?...`인데, iOS에서 이 URL을 열면 앱이 아닌 Safari가 열린다.

### 원인

**Universal Links 설정이 없었다.** 3가지가 모두 필요하다:

1. 서버: `/.well-known/apple-app-site-association` (AASA) 파일
2. iOS 앱: `Associated Domains` entitlement
3. Apple Developer Console: capability 활성화

iOS는 앱 설치 시 및 주기적으로 AASA 파일을 CDN을 통해 내려받아 캐시한다. 이 파일이 없거나 잘못 설정되어 있으면 Universal Links가 동작하지 않는다. 에러 메시지나 로그가 전혀 없어서 원인 파악이 어렵다.

### 해결

**1단계: Rails에서 AASA 서빙**

```ruby
# routes.rb
get "/.well-known/apple-app-site-association",
    to: "pages#apple_app_site_association",
    defaults: { format: :json }

# controller
def apple_app_site_association
  render json: {
    applinks: {
      apps: [],
      details: [{
        appID: "TEAMID.com.example.app",
        paths: ["/auth/sso/authorize*", "/auth/verify/*", "/dashboard", "/conversations/*"]
      }]
    },
    webcredentials: {
      apps: ["TEAMID.com.example.app"]
    }
  }
end
```

`paths`에 앱에서 열고 싶은 경로만 명시하는 게 중요하다. `["*"]`로 하면 모든 URL이 앱으로 열려서 웹 공유 링크 등에서 문제가 생긴다.

AASA 파일은 반드시 HTTPS로 서빙되어야 하며, 리다이렉트 없이 직접 응답해야 한다. `Content-Type: application/json`이 설정되어 있어야 한다.

**2단계: iOS Entitlements**

```xml
<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:example.com</string>
    <string>webcredentials:example.com</string>
</array>
```

XcodeGen 사용 시 `project.yml`:

```yaml
entitlements:
  path: App/App.entitlements
  properties:
    com.apple.developer.associated-domains:
      - applinks:example.com
      - webcredentials:example.com
```

**3단계: Apple Developer Console**

App Store Connect API로 Associated Domains capability 활성화:

```python
import jwt, time, requests

# JWT 토큰 생성
token = jwt.encode({
    'iss': ISSUER_ID,
    'iat': int(time.time()),
    'exp': int(time.time()) + 1200,
    'aud': 'appstoreconnect-v1'
}, private_key, algorithm='ES256', headers={'kid': KEY_ID})

# Bundle ID 조회
resp = requests.get(
    'https://api.appstoreconnect.apple.com/v1/bundleIds',
    params={'filter[identifier]': 'com.example.app'},
    headers={'Authorization': f'Bearer {token}'}
)
bundle_id = resp.json()['data'][0]['id']

# Associated Domains capability 추가
requests.post(
    'https://api.appstoreconnect.apple.com/v1/bundleIdCapabilities',
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    json={
        'data': {
            'type': 'bundleIdCapabilities',
            'attributes': {'capabilityType': 'ASSOCIATED_DOMAINS', 'settings': []},
            'relationships': {
                'bundleId': {'data': {'type': 'bundleIds', 'id': bundle_id}}
            }
        }
    }
)
```

Apple Developer Console 웹에서 수동으로 해도 되지만, API로 하면 CI에서 자동화할 수 있다.

**4단계: Hotwire Native에서 Universal Link 수신 처리**

```swift
// SceneController.swift

// 앱이 이미 실행 중일 때
func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
          let url = userActivity.webpageURL,
          isAppURL(url) else { return }
    tabBarController.activeNavigator.route(url)
}

// Cold start 시
private func handleUniversalLinks(from connectionOptions: UIScene.ConnectionOptions) {
    if let userActivity = connectionOptions.userActivities.first(where: {
        $0.activityType == NSUserActivityTypeBrowsingWeb
    }), let url = userActivity.webpageURL, isAppURL(url) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            self?.tabBarController.activeNavigator.route(url)
        }
    }
}
```

cold start 시 0.5초 딜레이를 주는 이유: Hotwire Native의 WebView가 초기화되기 전에 route를 호출하면 무시된다. 앱이 이미 실행 중일 때는 딜레이 없이 바로 처리해도 된다.

---

## 삽질 5: SSO 콜백이 앱 내 WebView에서 열려서 세션이 안 맞음

### 문제

SSO 인증 완료 후 콜백 URL(`https://rp-app.com/auth/sso/callback?token=...`)로 리다이렉트될 때, IdP 앱의 WebView 안에서 열린다. RP 서비스의 세션 쿠키가 IdP 앱 WebView에는 없으므로 로그인이 안 된다.

Hotwire Native는 기본적으로 모든 링크 클릭을 WebView 내에서 처리한다. RP 도메인이 IdP 앱의 도메인과 다르므로, 아무 처리 없이 두면 RP 콜백 URL도 IdP 앱의 WKWebView 안에서 열린다. WKWebView는 Safari와 쿠키를 공유하지 않기 때문에 RP 서비스의 세션 쿠키가 없는 상태다.

### 해결

외부 URL은 시스템 브라우저(`UIApplication.shared.open`)로 열도록 변경:

```swift
func handle(proposal: VisitProposal) -> ProposalResult {
    if !isAppURL(proposal.url) {
        // 외부 HTTPS URL → 시스템 브라우저 (세션 쿠키 유지)
        if proposal.url.scheme == "https" {
            UIApplication.shared.open(proposal.url)
        } else {
            let safariVC = SFSafariViewController(url: proposal.url)
            rootViewController.present(safariVC, animated: true)
        }
        return .reject
    }
    return .accept
}
```

`SFSafariViewController`는 앱 내에서 열리지만 쿠키가 앱과 격리되어 있다. `UIApplication.shared.open`은 시스템 Safari에서 열려서 RP 서비스의 기존 세션 쿠키를 사용할 수 있다.

이 처리 덕분에 SSO 콜백 흐름이 완성된다: IdP 앱 WebView → 인증 완료 페이지 → 시스템 Safari로 RP 콜백 URL 열기 → RP 세션 쿠키 사용 → 로그인 완료.

---

## Android App Links

Android은 `AndroidManifest.xml`에 intent-filter가 이미 있었고, 서버에 `assetlinks.json`만 추가하면 됐다:

```ruby
# routes.rb
get "/.well-known/assetlinks.json",
    to: "pages#assetlinks",
    defaults: { format: :json }

# controller
def assetlinks
  render json: [{
    relation: ["delegate_permission/common.handle_all_urls"],
    target: {
      namespace: "android_app",
      package_name: "com.example.app",
      sha256_cert_fingerprints: [ENV.fetch("ANDROID_SHA256_FINGERPRINT", "")]
    }
  }]
end
```

SHA256 fingerprint는 `keytool -list -v -keystore your.keystore`로 확인한다.

iOS의 AASA와 달리 Android의 assetlinks.json은 CDN 캐시 없이 직접 서버에서 가져온다. 배포 후 즉시 적용되는 장점이 있지만, 서버가 느리면 App Links 인증이 실패할 수 있다.

---

## 최종 아키텍처

```
[RP 서비스]                    [IdP 서비스]                [iOS 앱]
    │                              │                         │
    │  1. "메인 앱으로 로그인"       │                         │
    │────────────────────────────→│                         │
    │  GET /auth/sso/authorize    │                         │
    │  (client_id, redirect_uri,  │                         │
    │   state)                    │                         │
    │                             │  Universal Link 감지     │
    │                             │←────────────────────────│
    │                             │  앱에서 WebView 로딩      │
    │                             │                         │
    │                             │  2. 로그인 (OTP)         │
    │                             │  3. SSO 토큰 발급        │
    │                             │  4. "인증 완료" 페이지     │
    │                             │                         │
    │  5. 콜백 (token + state)    │                         │
    │←───────────────────────────│  시스템 브라우저로 열기     │
    │                             │                         │
    │  6. Back-channel 토큰 검증   │                         │
    │────────────────────────────→│                         │
    │  POST /auth/sso/verify      │                         │
    │  (HMAC-SHA256 서명)          │                         │
    │                             │                         │
    │  7. 사용자 정보 반환          │                         │
    │←───────────────────────────│                         │
    │                             │                         │
    │  8. 로그인 완료               │                         │
```

---

## 보안 체크리스트

- [x] State 파라미터로 CSRF 방지 (`SecureRandom.urlsafe_base64`)
- [x] `secure_compare`로 타이밍 공격 방지
- [x] SSO 토큰 5분 만료 + 일회용 (`used_at` 기록)
- [x] `redirect_uri` 허용 목록 검증 (환경변수로 관리)
- [x] HMAC-SHA256으로 back-channel 요청 서명
- [x] SSO 세션 타임아웃 (10분)
- [x] 토큰/state 값 URL 인코딩 (`CGI.escape`)
- [x] AASA `paths`에 필요한 경로만 명시 (와일드카드 `*` 전체 사용 금지)
- [x] back-channel 검증 후 토큰 즉시 소각 (`used_at` 설정)

---

## 배운 것

1. **다단계 인증 + SSO = 세션 관리가 핵심이다.** OTP, 매직링크, 이메일 답장 인증 등 여러 경로가 있으면 각각에서 SSO 컨텍스트를 유지해야 한다. 프레임워크의 `store_location`만으로는 부족하다.

2. **Universal Links는 서버 + 앱 + Apple Console 3곳 모두 설정해야 한다.** 하나라도 빠지면 그냥 브라우저로 열린다. 에러 메시지도 없다.

3. **앱 간 리다이렉트 시 쿠키 격리를 고려해야 한다.** IdP 앱의 WebView에서 RP 서비스 콜백을 열면 세션이 없다. 시스템 브라우저로 열어야 한다.

4. **인증 완료 중간 페이지가 UX를 크게 개선한다.** 즉시 리다이렉트하면 사용자가 뭐가 된 건지 모른다. 2초 대기 + 체크마크 하나만 넣어도 체감이 다르다.

5. **App Store Connect API로 capability를 코드로 관리할 수 있다.** Apple Developer Console 웹에서 클릭클릭하는 것보다 재현 가능하고 자동화할 수 있다.

---

## Key Takeaways

- **SSO 파라미터는 별도 세션 키로 보존하라.** `session[:sso_params]`에 `client_id`, `redirect_uri`, `state`를 직접 저장하면 다단계 인증 도중 URL이 바뀌어도 컨텍스트를 잃지 않는다.
- **back-channel 검증 + HMAC 서명은 필수다.** front-channel(브라우저 리다이렉트)만으로 토큰을 교환하면 탈취 위험이 있다.
- **Universal Links 디버깅은 3곳을 동시에 봐야 한다.** AASA 파일(서버), Associated Domains(앱), Apple Developer Console(capability) 중 하나라도 빠지면 작동하지 않으며 OS가 아무 에러도 내지 않는다.
- **WKWebView는 Safari 쿠키를 공유하지 않는다.** Hotwire Native 앱에서 다른 도메인으로 리다이렉트할 때는 `UIApplication.shared.open`으로 시스템 Safari를 사용해야 기존 세션이 유지된다.
- **Cold start 시 WebView 초기화 딜레이를 고려하라.** Universal Link로 앱이 처음 열릴 때는 0.5초 정도 대기 후 라우팅해야 WebView가 준비된 상태에서 URL을 처리할 수 있다.
- **토큰은 일회용이어야 한다.** `used_at` 타임스탬프를 기록해 재사용을 방지하고, 5분 만료 시간을 설정해 탈취된 토큰의 유효 시간을 최소화한다.
