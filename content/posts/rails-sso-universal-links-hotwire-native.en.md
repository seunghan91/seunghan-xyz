---
title: "How I Built Rails SSO Between Two Apps — Plus iOS Universal Links Auto-Switching"
date: 2026-02-17
draft: false
tags: ["Rails", "SSO", "iOS", "Universal Links", "Hotwire Native", "Security"]
description: "How to build custom SSO between two Rails 8 apps — then add iOS Universal Links so the native app handles auth automatically. Covers session loss, redirect loops, and AASA debugging."
cover:
  image: "/images/og/rails-sso-universal-links-hotwire-native.png"
  alt: "Rails Sso Universal Links Hotwire Native"
  hidden: true
categories: ["Hotwire Native", "iOS"]
series: ["Hotwire Native Mobile App"]
---

I have two Rails 8 services. One is the main app acting as the Identity Provider (IdP), and the other is a partner service acting as the Relying Party (RP). I wanted to add a "Sign in with Main App" button to the partner service's login page, authenticate via SSO, and redirect back. Then I went one step further: if the user has the iOS Hotwire Native app installed, the authentication should open in the native app instead of the browser, via Universal Links.

I did not use OAuth 2.0 or a third-party IdP like Auth0 or Cognito. Both services are internal systems I operate myself, so a full OAuth implementation would have been overkill. The core concepts — token issuance, back-channel verification, session management — are the same as any standard SSO flow.

---

## Target Flow

```
[RP Service] User clicks "Sign in with Main App"
  → Redirect to IdP /auth/sso/authorize
  → (App installed) iOS Universal Link → native app opens
  → (App not installed) browser login
  → Already signed in → issue token immediately
  → Not signed in → OTP login → issue token
  → "Authentication complete" page (2-second wait) → redirect to callback URL
  → RP verifies token → login complete
```

On the RP side, clicking the login button generates a `state` parameter that gets stored in the session. When the callback comes back, the RP verifies the `state` to prevent CSRF attacks.

---

## Problem 1: SSO Parameters Lost During Multi-Step Login

### The Problem

I had `before_action :require_authentication` on the SSO authorize endpoint. Here is what happened with unauthenticated users:

1. User hits the SSO authorize endpoint without being signed in
2. `store_location` saves the current URL to `session[:return_to]`
3. User gets redirected to the login page
4. User completes OTP authentication
5. `redirect_back_or(dashboard_path)` sends them back to `/auth/sso/authorize`
6. **But the query string (`client_id`, `redirect_uri`, `state`) is gone!**

`store_location` stores `request.fullpath`, which should include query parameters — and it does on the first redirect. The problem is that multi-step authentication (OTP code entry, magic link click, email reply) involves multiple intermediate POST requests and page transitions. Some of those steps overwrite `session[:return_to]` with a new URL that no longer includes the original SSO parameters.

Looking at the Rails `store_location` implementation directly: it stores `request.fullpath` unconditionally whenever it is called. Each authentication step that triggers a `require_authentication` guard resets the stored URL. By the time the user finishes OTP authentication, the original authorize URL with its SSO parameters has been replaced.

### The Fix

I removed `before_action :require_authentication` from the SSO controller and explicitly saved the SSO parameters to a dedicated session key:

```ruby
# IdP: SSO Controller
def authorize
  # Validate params (client_id allowlist, redirect_uri allowlist)
  validate_sso_params!

  unless signed_in?
    session[:sso_params] = {
      redirect_uri: redirect_uri,
      state: state,
      client_id: client_id
    }
    redirect_to sign_in_path
    return
  end

  # Issue token and render completion page
  sso_token = SsoToken.create!(
    user: current_user,
    client_id: client_id,
    expires_at: 5.minutes.from_now
  )
  @callback_url = "#{redirect_uri}?token=#{CGI.escape(sso_token.token)}&state=#{CGI.escape(state)}"
  render :authorize_complete
end
```

Added a `complete` action to resume the SSO flow after login:

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

All login success paths in the session controller now check for a pending SSO flow:

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

I refactored every authentication method — OTP code entry, magic link, email reply — to call this shared method on success.

**Key insight**: Do not rely on the framework's `store_location` / `redirect_back_or` for important context that must survive multi-step flows. Store critical state explicitly under a dedicated session key. The framework helpers are designed for simple one-step redirects, not multi-step authentication pipelines.

---

## Problem 2: HMAC Signature Mismatch During Token Verification

### The Problem

The RP verifies the SSO token issued by the IdP via back-channel:

```
RP → POST /auth/sso/verify (token + HMAC signature) → IdP
IdP → verify signature + check token validity → return user info
```

Without back-channel verification, a man-in-the-middle could intercept the token from the browser redirect and impersonate a user. The HMAC signature proves that the request comes from a server that knows the shared secret.

Everything worked locally but produced signature mismatches in the deployed environment. The cause: **the `SSO_SHARED_SECRET` environment variable had different values on the two servers.**

When setting environment variables manually through a deployment platform UI, it is easy to accidentally include leading or trailing whitespace during copy-paste. HMAC comparison is byte-for-byte — a single extra space character causes 100% mismatch every time.

### The Fix

Set the same secret on both services using the deployment platform API to avoid manual copy-paste errors:

```bash
# Generate the secret
SECRET=$(openssl rand -hex 32)
echo $SECRET  # Set this exact value on both services

# Set on Render (run for both IdP and RP service IDs)
curl -X PUT "https://api.render.com/v1/services/$SERVICE_ID/env-vars" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"key":"SSO_SHARED_SECRET","value":"'"$SECRET"'"}]'
```

HMAC verification code:

```ruby
# RP side — build and send the signed request
body = { token: token }.to_json
shared_secret = ENV.fetch("SSO_SHARED_SECRET")
signature = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, body)}"

response = HTTP.headers(
  "Content-Type" => "application/json",
  "X-SSO-Signature" => signature
).post("#{IDP_URL}/auth/sso/verify", body: body)

# IdP side — verify the signature and validate the token
def verify
  body = request.body.read  # read once and store — body IO can only be read once
  shared_secret = ENV.fetch("SSO_SHARED_SECRET")
  expected = "sha256=#{OpenSSL::HMAC.hexdigest('SHA256', shared_secret, body)}"
  signature_header = request.headers["X-SSO-Signature"]

  unless ActiveSupport::SecurityUtils.secure_compare(signature_header.to_s, expected)
    render json: { error: "invalid_signature" }, status: :unauthorized
    return
  end

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

**Key insights**:

- Use `ActiveSupport::SecurityUtils.secure_compare` instead of `==`. A plain string comparison returns early as soon as it finds a mismatch, and the time difference is measurable. An attacker can use timing measurements to determine the correct secret character by character. `secure_compare` always takes the same amount of time regardless of where the mismatch occurs.
- `request.body.read` can only be read once from the IO stream. Store the result in a variable before using it for both signature verification and JSON parsing.

---

## Problem 3: Immediate Redirect With No User Feedback

### The Problem

Calling `redirect_to callback_url` immediately after SSO authentication succeeds creates a poor user experience:

- Users have no idea what just happened — they see a flash of a screen and end up somewhere new
- During app-to-app transitions the screen just blinks
- If something goes wrong, errors are invisible because the page disappears too quickly to read

### The Fix

Add an intermediate "Authentication Complete" page with an automatic 2-second redirect:

```erb
<div class="text-center">
  <div class="checkmark-icon"><!-- Checkmark SVG --></div>
  <h2>Authentication Complete</h2>
  <p>Signed in as <strong><%= current_user.name %></strong>.</p>
  <div class="spinner"><!-- Loading spinner --></div>
  <a href="<%= @callback_url %>">Click here if you are not redirected automatically</a>
</div>

<script>
  setTimeout(function() {
    window.location.href = "<%= j @callback_url %>";
  }, 2000);
</script>
```

The `j` helper (`escape_javascript`) is important here. The callback URL contains query parameters including the SSO token. Without escaping, a crafted token value could break out of the JavaScript string literal and create an XSS vulnerability.

This intermediate page also works well in the Hotwire Native app. When `window.location.href` changes after 2 seconds, Hotwire detects it and handles the navigation appropriately. The fallback link ensures users can always proceed even if JavaScript fails.

---

## Problem 4: App Installed but Browser Opens Anyway

### The Problem

The SSO redirect URL is `https://example.com/auth/sso/authorize?...`. On iOS, tapping this URL opens Safari even when the app is installed.

### The Cause

**Universal Links were not configured.** All three of the following must be in place:

1. Server: `/.well-known/apple-app-site-association` (AASA) file
2. iOS app: `Associated Domains` entitlement
3. Apple Developer Console: capability enabled

iOS downloads and caches the AASA file at app installation time and periodically afterward (via Apple's CDN). If the file is missing, has an incorrect format, or lists the wrong paths, Universal Links silently fall back to Safari. There is no error message, no log output, and no indication of what went wrong — it just opens the browser.

### The Fix

**Step 1: Serve the AASA file from Rails**

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

Only list the paths you want the app to handle in the `paths` array. Using `["*"]` to match everything causes every URL on your domain to open in the app — including web-only share links and marketing pages — which breaks the web experience for users who have the app installed.

The AASA file must be served over HTTPS without any redirects, and with `Content-Type: application/json`.

**Step 2: Add the Associated Domains entitlement to the iOS app**

```xml
<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:example.com</string>
    <string>webcredentials:example.com</string>
</array>
```

If you use XcodeGen, configure this in `project.yml`:

```yaml
entitlements:
  path: App/App.entitlements
  properties:
    com.apple.developer.associated-domains:
      - applinks:example.com
      - webcredentials:example.com
```

**Step 3: Enable the capability in Apple Developer Console**

You can do this manually in the Apple Developer Console web UI, or automate it using the App Store Connect API — useful for CI pipelines or new team members setting up from scratch:

```python
import jwt, time, requests

# Generate a JWT for the App Store Connect API
token = jwt.encode({
    'iss': ISSUER_ID,
    'iat': int(time.time()),
    'exp': int(time.time()) + 1200,
    'aud': 'appstoreconnect-v1'
}, private_key, algorithm='ES256', headers={'kid': KEY_ID})

# Look up the bundle ID record
resp = requests.get(
    'https://api.appstoreconnect.apple.com/v1/bundleIds',
    params={'filter[identifier]': 'com.example.app'},
    headers={'Authorization': f'Bearer {token}'}
)
bundle_id = resp.json()['data'][0]['id']

# Enable the Associated Domains capability
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

**Step 4: Handle the Universal Link in Hotwire Native**

```swift
// SceneController.swift

// App is already running — handle the incoming Universal Link
func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
          let url = userActivity.webpageURL,
          isAppURL(url) else { return }
    tabBarController.activeNavigator.route(url)
}

// Cold start — app was launched by tapping a Universal Link
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

The 0.5-second delay on cold start is necessary because Hotwire Native's WebView has not finished initializing when `scene(_:willConnectTo:options:)` runs. Calling `route` before the WebView is ready silently discards the navigation. When the app is already running, the WebView is already initialized, so no delay is needed.

---

## Problem 5: SSO Callback Opens Inside WebView, Breaking Session

### The Problem

After SSO authentication completes, the callback URL (`https://rp-app.com/auth/sso/callback?token=...`) gets redirected to inside the IdP app's WebView. The RP service's session cookie does not exist in the IdP app's WKWebView, so the login fails.

Hotwire Native handles all link taps inside its WKWebView by default. Since the RP domain is different from the IdP domain, the RP callback URL opens in the IdP app's WebView — which has no knowledge of the user's session on the RP service. WKWebView does not share cookies with Safari, so the RP's session cookie is unavailable.

### The Fix

Route external URLs to the system browser instead of the app's WebView:

```swift
func handle(proposal: VisitProposal) -> ProposalResult {
    if !isAppURL(proposal.url) {
        // External HTTPS URLs → system Safari (preserves session cookies)
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

`SFSafariViewController` opens inside the app but uses a cookie store that is isolated from both the app's WKWebView and system Safari. `UIApplication.shared.open` opens in system Safari, which shares cookies with Safari — meaning the user's existing RP session cookie is available and the login completes successfully.

With this in place, the complete SSO callback flow becomes: IdP app WebView → authentication complete page → system Safari opens RP callback URL → RP session cookie used → login complete.

---

## Android App Links

Android was simpler. The `AndroidManifest.xml` already had the intent-filter configured, so I only needed to add the `assetlinks.json` file on the server:

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

Get the SHA256 fingerprint with: `keytool -list -v -keystore your.keystore`

Unlike iOS AASA files (which are downloaded via Apple's CDN and cached), Android's `assetlinks.json` is fetched directly from your server. This means changes take effect immediately after deployment — no cache to worry about. The tradeoff is that a slow server response can cause App Links verification to fail.

---

## Final Architecture

```
[RP Service]                    [IdP Service]               [iOS App]
    |                               |                            |
    |  1. "Sign in with Main App"   |                            |
    |-----------------------------→ |                            |
    |  GET /auth/sso/authorize      |                            |
    |  (client_id, redirect_uri,    |                            |
    |   state)                      |                            |
    |                               |  Universal Link detected   |
    |                               | ←--------------------------|
    |                               |  WebView loads in app      |
    |                               |                            |
    |                               |  2. Login (OTP)            |
    |                               |  3. Issue SSO token        |
    |                               |  4. "Auth complete" page   |
    |                               |                            |
    |  5. Callback (token + state)  |                            |
    | ←-----------------------------|  Open via system browser   |
    |                               |                            |
    |  6. Back-channel verification |                            |
    |-----------------------------→ |                            |
    |  POST /auth/sso/verify        |                            |
    |  (HMAC-SHA256 signature)       |                            |
    |                               |                            |
    |  7. Return user info          |                            |
    | ←-----------------------------|                            |
    |                               |                            |
    |  8. Login complete            |                            |
```

---

## Security Checklist

- [x] CSRF prevention via `state` parameter (`SecureRandom.urlsafe_base64`)
- [x] Timing attack prevention via `secure_compare`
- [x] SSO tokens expire after 5 minutes and are single-use (`used_at` timestamp)
- [x] `redirect_uri` validated against an allowlist (managed via environment variables)
- [x] Back-channel requests signed with HMAC-SHA256
- [x] SSO session timeout after 10 minutes
- [x] Token and state values URL-encoded with `CGI.escape`
- [x] AASA `paths` limited to specific routes (no wildcard `*` for everything)
- [x] Token immediately invalidated after back-channel verification (`used_at` set)

---

## Lessons Learned

1. **Multi-step authentication plus SSO means session management is everything.** When there are multiple login paths — OTP, magic link, email reply — each one must preserve the SSO context. The framework's `store_location` is not designed for this.

2. **Universal Links require three separate configurations, all correct.** Server AASA file, app entitlement, and Apple Developer Console capability. Any one missing and the link silently opens in the browser with no error.

3. **Cookie isolation between apps must be accounted for.** Opening the RP service callback inside the IdP app's WebView means there is no RP session cookie. Always route cross-domain callbacks to the system browser.

4. **An intermediate "auth complete" page dramatically improves UX.** An immediate redirect leaves users confused about what happened. Two seconds and a checkmark make the transition feel intentional and trustworthy.

5. **App Store Connect API lets you manage capabilities as code.** Clicking through the Apple Developer Console web UI is slow and not reproducible. The API makes it scriptable and CI-friendly.

---

## Key Takeaways

- **Save SSO parameters under a dedicated session key.** Store `client_id`, `redirect_uri`, and `state` in `session[:sso_params]` explicitly. This survives the multiple POST requests and page transitions that happen during multi-step authentication, whereas `store_location` / `redirect_back_or` will lose the original URL.
- **Back-channel token verification with HMAC signing is non-negotiable.** Front-channel (browser redirect) token exchange alone is vulnerable to interception. The HMAC signature proves the verification request comes from a server that holds the shared secret.
- **Universal Links debugging requires checking three places simultaneously.** AASA file (server), Associated Domains (app entitlement), and Apple Developer Console (capability). A failure at any single point causes a silent fallback to Safari with no error output from the OS.
- **WKWebView does not share Safari cookies.** When a Hotwire Native app needs to complete an action on a different domain, use `UIApplication.shared.open` to open system Safari and preserve existing session cookies — not `SFSafariViewController`, which also isolates its cookie store.
- **Account for WebView initialization time on cold start.** When a Universal Link launches the app from a cold start, wait approximately 0.5 seconds before calling the router. The WebView needs time to initialize; routing before it is ready silently discards the navigation.
- **SSO tokens must be single-use.** Record a `used_at` timestamp when the token is first verified and reject any subsequent attempts. Combined with a short expiry window (5 minutes), this limits the damage from a stolen token.
