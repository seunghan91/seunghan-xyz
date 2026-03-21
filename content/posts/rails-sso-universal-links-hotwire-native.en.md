---
title: "Rails SSO Implementation + iOS Universal Links for Automatic App Switching"
date: 2026-02-17
draft: false
tags: ["Rails", "SSO", "iOS", "Universal Links", "Hotwire Native", "Security"]
description: "Implementing custom SSO between two Rails apps and integrating iOS Universal Links for automatic native app authentication when the app is installed. Session loss, redirect loops, and AASA configuration debugging."
cover:
  image: "/images/og/rails-sso-universal-links-hotwire-native.png"
  alt: "Rails Sso Universal Links Hotwire Native"
  hidden: true
categories: ["Hotwire Native", "Rails"]
series: ["Hotwire Native Mobile App"]
---


두 개의 Rails 8 서비스가 있다. 하나는 메인 앱(IdP 역할), 다른 하나는 연동 서비스(RP 역할). 연동 서비스 로그인 페이지에 "메인 앱으로 로그인" 버튼을 넣고, SSO로 인증 후 돌아오는 플로우를 구현했다.

거기에 iOS Hotwire Native 앱이 설치돼 있으면, 브라우저 대신 네이티브 앱에서 인증이 진행되도록 Universal Links까지 붙였다.

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

---

## 삽질 1: SSO 파라미터가 로그인 과정에서 유실됨

### Problem

SSO authorize 엔드포인트에 `before_action :require_authentication`을 걸어놨더니:

1. 미로그인 상태에서 SSO authorize 접근
2. `store_location`이 현재 URL을 `session[:return_to]`에 저장
3. 로그인 페이지로 리다이렉트
4. OTP 인증 완료
5. `redirect_back_or(dashboard_path)`가 `/auth/sso/authorize`로 돌려보냄
6. **하지만 query string(`client_id`, `redirect_uri`, `state`)이 날아감!**

`store_location`은 `request.fullpath`를 저장하니까 쿼리 파라미터도 포함되어야 하는데, OTP 인증 플로우가 여러 단계(코드 입력, 매직링크, 이메일 답장 등)를 거치면서 세션이 꼬이는 경우가 있었다.

### Solution

`before_action :require_authentication`을 제거하고, SSO 파라미터를 명시적으로 세션에 저장하는 방식으로 변경했다:

```ruby
# IdP: SSO Controller
def authorize
  # 파라미터 검증 (client_id, redirect_uri, state)
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
  sso_token = SsoToken.create!(...)
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

**핵심**: 프레임워크의 `store_location`/`redirect_back_or`에 의존하지 말고, 중요한 컨텍스트는 명시적으로 세션에 저장할 것. 특히 다단계 인증 플로우(OTP, 매직링크 등)에서는 중간에 세션 데이터가 예상과 다르게 동작할 수 있다.

---

## 삽질 2: 토큰 검증 시 HMAC 서명 불일치

### Problem

IdP가 발급한 SSO 토큰을 RP가 back-channel로 검증하는 구조:

```
RP → POST /auth/sso/verify (token + HMAC signature) → IdP
IdP → 서명 검증 + 토큰 유효성 확인 → 사용자 정보 반환
```

로컬에서는 잘 되는데 배포 환경에서 서명 불일치가 발생했다. 원인: **양쪽 서버의 `SSO_SHARED_SECRET` 환경변수가 달랐다.**

### Solution

배포 플랫폼 API로 양쪽 서비스에 동일한 시크릿을 설정:

```bash
# 시크릿 생성
openssl rand -hex 32

# 양쪽 서비스에 동일한 값 설정
# (배포 플랫폼의 환경변수 관리 기능 사용)
```

HMAC 검증 코드:

```ruby
# RP → IdP 요청 시
body = { token: token }.to_json
signature = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, body)}"

# IdP에서 검증
expected = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, request.body.read)}"
unless ActiveSupport::SecurityUtils.secure_compare(signature_header, expected)
  render json: { error: "invalid_signature" }, status: :unauthorized
end
```

**핵심**: `secure_compare`로 타이밍 공격 방지. 일반 `==` 비교는 문자열 길이에 따라 응답 시간이 달라져서 시크릿을 추론할 수 있다.

---

## 삽질 3: 인증 완료 후 사용자에게 아무 피드백 없이 리다이렉트

### Problem

SSO 인증 성공 후 즉시 `redirect_to callback_url`을 하면:
- 사용자 입장에서 "뭐가 된 거지?" 하고 혼란스러움
- 특히 앱 간 전환 시 화면이 순간적으로 깜빡이기만 함

### Solution

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

---

## 삽질 4: iOS 앱이 설치돼 있어도 브라우저에서 열림

### Problem

SSO 리다이렉트 URL이 `https://example.com/auth/sso/authorize?...`인데, iOS에서 이 URL을 열면 앱이 아닌 Safari가 열린다.

### Cause

**Universal Links 설정이 없었다.** 3가지가 모두 필요하다:

1. 서버: `/.well-known/apple-app-site-association` (AASA) 파일
2. iOS 앱: `Associated Domains` entitlement
3. Apple Developer Console: capability 활성화

### Solution

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

cold start 시 0.5초 딜레이를 주는 이유: Hotwire Native의 WebView가 초기화되기 전에 route를 호출하면 무시된다.

---

## 삽질 5: SSO 콜백이 앱 내 WebView에서 열려서 세션이 안 맞음

### Problem

SSO 인증 완료 후 콜백 URL(`https://rp-app.com/auth/sso/callback?token=...`)로 리다이렉트될 때, IdP 앱의 WebView 안에서 열린다. RP 서비스의 세션 쿠키가 IdP 앱 WebView에는 없으므로 로그인이 안 된다.

### Solution

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

---

## 배운 것

1. **다단계 인증 + SSO = 세션 관리가 핵심이다.** OTP, 매직링크, 이메일 답장 인증 등 여러 경로가 있으면 각각에서 SSO 컨텍스트를 유지해야 한다. 프레임워크의 `store_location`만으로는 부족하다.

2. **Universal Links는 서버 + 앱 + Apple Console 3곳 모두 설정해야 한다.** 하나라도 빠지면 그냥 브라우저로 열린다. 에러 메시지도 없다.

3. **앱 간 리다이렉트 시 쿠키 격리를 고려해야 한다.** IdP 앱의 WebView에서 RP 서비스 콜백을 열면 세션이 없다. 시스템 브라우저로 열어야 한다.

4. **인증 완료 중간 페이지가 UX를 크게 개선한다.** 즉시 리다이렉트하면 사용자가 뭐가 된 건지 모른다. 2초 대기 + 체크마크 하나만 넣어도 체감이 다르다.

5. **App Store Connect API로 capability를 코드로 관리할 수 있다.** Apple Developer Console 웹에서 클릭클릭하는 것보다 재현 가능하고 자동화할 수 있다.
