---
title: "Flutter SSO Login Failure + Rails Server Crash Simultaneous Debugging Record"
date: 2025-10-01
draft: true
tags: ["Flutter", "Rails", "TestFlight", "SSO", "Render", "Debugging"]
description: "TestFlight app's SSO login connecting to localhost and failing, while Rails server simultaneously crashes with uninitialized constant — debugging both at once."
cover:
  image: "/images/og/flutter-sso-localhost-rails-uninitialized-constant-debug.png"
  alt: "Flutter Sso Localhost Rails Uninitialized Constant Debug"
  hidden: true
---


While fixing a bug where social login (Apple, Google) was failing entirely on TestFlight, I also discovered the server was crashing. The causes were different, and both had to be fixed for the app to work properly.

---

## Symptoms

Pressing the Apple Login or Google Login button on the real device (TestFlight) showed the following errors:

```
Apple login failed: DioException [connection error]: The connection errored:
Connection refused This indicates an error which most likely cannot be solved
by the library.
Error: SocketException: Connection refused (OS Error: Connection refused, errno = 61),
address = localhost, port = 56837
```

```
Google login failed: DioException [connection error]: ...
address = localhost, port = 56839
```

Two things were odd:

1. It was trying to connect to `localhost` -- not the production server URL
2. The ports were random high ports like 56837 and 56839 -- not the baseUrl's port 3000

---

## Cause 1: Hardcoded Flutter API baseUrl

Checking the Flutter code revealed this in `ApiService`:

```dart
class ApiService {
  static const String baseUrl = 'http://localhost:3000';

  // ...
}
```

It was set to point at the local server during development and was never changed to the production URL before uploading the TestFlight build.

### Why the Port Number Was 56837

The `baseUrl` was `localhost:3000` but the error showed 56837, which was confusing. What actually happened was that when `api.post('/sso/apple', ...)` tried to connect to localhost, iOS internally output an ephemeral socket port in the error message. It is socket-level error information, not the destination port. The key point is that it was attempting to connect to `localhost` at all.

### Fix

```dart
class ApiService {
  static const String baseUrl = 'https://your-production-server.onrender.com';

  // ...
}
```

---

## Cause 2: Rails Server Was Not Even Starting

Fixing the Flutter URL was not the end. Checking the server logs revealed the server itself was crashing:

```
[128353] ! Unable to start worker
[128353] uninitialized constant Admin::BaseController
/app/controllers/admin/blockchain_batches_controller.rb:2:in '<module:Admin>'
[128353] Early termination of worker
```

During Rails eager loading, `Admin::BlockchainBatchesController` was trying to inherit from `Admin::BaseController`, but that class did not exist, so the server could not start at all.

In other words, the server was down, so even if the Flutter URL had been correct, it would have returned 503.

### Cause

Controllers were added that inherited from `Admin::BaseController`, but the base controller itself was never created. In the development environment with lazy loading, the error went unnoticed because those controllers were never actually requested.

Production Rails uses eager loading (`config.eager_load = true`) by default, so it loads all constants at startup and crashes immediately.

### Fix

Created `app/controllers/admin/base_controller.rb`:

```ruby
module Admin
  class BaseController < ApplicationController
    include ApiResponse
    include Paginatable

    skip_before_action :verify_authenticity_token
    skip_before_action :require_authentication

    before_action :authenticate_api!
    before_action :set_current_attributes

    private

    def authenticate_api!
      token = request.headers["Authorization"]&.sub("Bearer ", "")
      api_token = ApiTokenService.authenticate(token)

      if api_token
        Current.api_token = api_token
      else
        render_unauthorized("Authentication required", error_code: "unauthorized")
      end
    end

    def set_current_attributes
      Current.user_agent = request.user_agent
      Current.ip_address = request.remote_ip
    end

    def current_user
      Current.user
    end
  end
end
```

---

## How to Find Crashes in Server Logs

When using Render, to quickly find key errors in logs:

- Filter by `type: ["app"]`
- Look for keywords: `! Unable to start worker`, `uninitialized constant`, `Early termination`

The most common pattern where errors that do not appear in development crash in production:

| Cause | Development | Production |
|------|------|----------|
| Eager loading | Lazy (loads on request) | Loads everything at startup |
| Undefined constant | Not noticed if controller is unused | Crashes immediately on startup |

---

## Final Fix Order

```
1. Check server logs → Discover missing Admin::BaseController
2. Create admin/base_controller.rb → push → Render auto-deploy
3. Fix Flutter baseUrl → localhost:3000 → https://production-URL
4. make build-testflight (includes auto build number increment)
5. Upload to TestFlight with xcrun altool
```

---

## TestFlight Upload Command

```bash
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/app.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_UUID
```

The API key file must be at `~/.appstoreconnect/private_keys/AuthKey_KEYID.p8` for altool to find it automatically.

---

## Lessons Learned

- **Never hardcode Flutter API URLs** -- manage them with `--dart-define` or environment-specific config files
- **When adding Rails admin controllers, create the BaseController first**
- **Check production server logs before deploying to TestFlight** -- even if the app is correct, it is useless if the server is down
- Even if the port number in the error message looks odd, the real issue is that it was trying to connect to `localhost` at all
