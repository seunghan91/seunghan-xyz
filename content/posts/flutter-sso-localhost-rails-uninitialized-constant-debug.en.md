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
categories: ["Rails"]
---

While fixing a bug where social login (Apple, Google) was failing entirely on TestFlight, I also discovered the server was crashing at the same time. The causes were completely independent of each other, and both had to be resolved for the app to work properly. This post walks through the full investigation process, root causes, and fixes for each issue.

---

## Symptoms

Pressing the Apple Login or Google Login button on a real device running a TestFlight build showed the following errors:

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

Two things immediately stood out as wrong:

1. It was trying to connect to `localhost` — not the production server URL
2. The ports were random high ports like 56837 and 56839 — not port 3000 from the baseUrl

The first observation was the important one. A real device running a TestFlight build has no local Rails server to connect to. `localhost` on an iPhone refers to the device itself, not the developer's Mac. So any attempt to connect there will always refuse.

---

## Cause 1: Hardcoded Flutter API baseUrl

Checking the Flutter code revealed this in `ApiService`:

```dart
class ApiService {
  static const String baseUrl = 'http://localhost:3000';

  // ...
}
```

It was set to point at the local development server and was never updated to the production URL before uploading the TestFlight build.

This is an easy mistake to make during active development. You add SSO, test it against your local Rails server, everything works fine in the simulator, and you ship the build — only to have it fail immediately on a real device because it is still pointing at your laptop.

### Why the Port Number Was 56837

The `baseUrl` was `localhost:3000` but the error showed port 56837, which was initially confusing. The explanation is that when `api.post('/sso/apple', ...)` tries to connect to localhost, iOS assigns an ephemeral source port for the outgoing socket at the OS networking layer. That source port — the one the device opened on its end — is what gets printed in the `SocketException` error message. It is not the destination port (3000). The actual destination was still localhost:3000, but the socket never connected, and the error reported the source port.

The practical takeaway: when you see a high ephemeral port like 56837 in a `SocketException`, ignore the port number and focus on the address. The address being `localhost` is the bug.

### The Proper Fix: Environment-Based Configuration

The minimal fix is to change the string:

```dart
class ApiService {
  static const String baseUrl = 'https://your-production-server.onrender.com';

  // ...
}
```

But this is also fragile — hardcoding the production URL is only marginally better. The real solution is to externalize environment configuration so the same codebase can target different servers without code changes.

#### Option A: `--dart-define` at build time

```bash
# Development
flutter run --dart-define=API_BASE_URL=http://localhost:3000

# Production / TestFlight
flutter build ipa --dart-define=API_BASE_URL=https://your-production-server.onrender.com
```

```dart
class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:3000',
  );
}
```

#### Option B: Separate config files per flavor

```dart
// lib/config/env.dart
abstract class Env {
  static const String apiBaseUrl = String.fromEnvironment('API_BASE_URL');
}
```

Using Flutter flavors (`--flavor development`, `--flavor production`) combined with `--dart-define-from-file` lets you manage all environment differences in a single JSON file per environment, keeping them out of source-controlled Dart code.

Either approach ensures that a TestFlight or App Store build can never accidentally point at localhost.

---

## Cause 2: Rails Server Was Not Even Starting

Fixing the Flutter URL alone was not sufficient. Even with the correct production URL, the server was returning errors. Checking the Render logs revealed the server itself was crashing on startup:

```
[128353] ! Unable to start worker
[128353] uninitialized constant Admin::BaseController
/app/controllers/admin/blockchain_batches_controller.rb:2:in '<module:Admin>'
[128353] Early termination of worker
```

During Rails eager loading, `Admin::BlockchainBatchesController` was trying to inherit from `Admin::BaseController`, but that class did not exist anywhere in the codebase. Because Rails cannot resolve the constant, the worker process terminates before it can serve a single request.

This meant the server was down entirely. Even if the Flutter URL had been perfectly configured pointing at the production server, every request would have returned a 503 or a connection refused — because no worker was alive to handle it.

### Why This Did Not Appear in Development

This is one of the most common "works on my machine" failure modes in Rails: the difference between lazy loading and eager loading.

| Environment | Loading strategy | When constants are resolved |
|-------------|-----------------|----------------------------|
| Development | Lazy loading | At the moment of the first request to that route |
| Production  | Eager loading (`config.eager_load = true`) | At server startup, all at once |

In development, if you never make a request to an admin route that hits `Admin::BlockchainBatchesController`, the missing `Admin::BaseController` constant is never resolved and never causes an error. The bug hides perfectly until you deploy.

In production, Rails loads the entire application on startup. Every class, every module, every constant reference is resolved immediately. The missing base class surfaces instantly, before the server can accept a single connection.

### The Fix: Create the Missing Base Controller

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

The base controller centralizes concerns shared by all admin controllers: API token authentication, current attributes setup, and common concerns like `ApiResponse` and `Paginatable`. Every child controller inheriting from this gets these behaviors automatically, which is exactly why forgetting to create it breaks everything.

### Catching Eager Load Errors Locally

You do not have to wait until production to catch this class of error. Running the following command locally simulates production eager loading:

```bash
RAILS_ENV=production bundle exec rails runner "puts 'Eager load OK'"
```

Or more directly:

```bash
bundle exec rails zeitwerk:check
```

The `zeitwerk:check` command (Rails 6+) verifies that all files in autoload paths can be loaded without errors. Running this as part of a pre-deploy checklist or CI step catches missing constants before they crash production.

---

## How to Find Crashes in Server Logs on Render

When using Render, the logs can contain a lot of noise from load balancers and health checks. To quickly find startup crash errors:

- Filter by `type: ["app"]` to exclude infrastructure-level logs
- Look for these keywords: `! Unable to start worker`, `uninitialized constant`, `Early termination`

A crash at startup will typically show the same sequence:

```
Unable to start worker
<Ruby exception with backtrace>
Early termination of worker
```

If you see `Early termination` without a matching `Started GET` or any request logs, the server never came up at all.

---

## Debugging Order That Saved Time

Working through two simultaneous bugs efficiently required checking the right things first. Server-side issues always take priority over client-side configuration because a dead server invalidates all client-side fixes anyway.

```
1. Check server logs on Render
   → Identify "uninitialized constant Admin::BaseController"
2. Create app/controllers/admin/base_controller.rb
   → git push → Render auto-deploys → server comes up healthy
3. Verify server responds to a health check or basic request
4. Then investigate the Flutter error
   → Identify "address = localhost" in DioException
5. Fix Flutter baseUrl → localhost:3000 → https://production-URL
6. Switch to --dart-define based env config for durability
7. make build-testflight (includes auto build number increment)
8. Upload to TestFlight with xcrun altool
```

The order matters. Fixing the Flutter URL first and then noticing the server is still down wastes a build cycle and a TestFlight submission.

---

## TestFlight Upload Command

```bash
xcrun altool --upload-app --type ios \
  -f build/ios/ipa/app.ipa \
  --apiKey YOUR_KEY_ID \
  --apiIssuer YOUR_ISSUER_UUID
```

The API key file must be located at `~/.appstoreconnect/private_keys/AuthKey_KEYID.p8` for `altool` to find it automatically. If the file is elsewhere, altool will prompt for a password instead of using the key.

Note that `xcrun altool` is deprecated in favor of `xcrun notarytool` for notarization tasks, but for TestFlight uploads it still works as of Xcode 15. The replacement command for upload is `xcrun altool` itself or the newer `xcrun altool --upload-package` depending on Xcode version. Check Apple's release notes if you encounter deprecation warnings.

---

## Key Takeaways

- **Never hardcode Flutter API URLs.** Use `--dart-define` or environment-specific config files. A hardcoded `localhost:3000` is invisible during simulator testing and catastrophic on real devices.
- **A high ephemeral port in a `SocketException` is a red herring.** The address field (`localhost`) is what matters, not the port number.
- **Rails eager loading is a production-only behavior by default.** Errors caused by missing constants, unresolved autoload paths, or circular dependencies will only surface at startup in production. Run `bundle exec rails zeitwerk:check` locally to catch them early.
- **When adding Rails admin controllers, create the BaseController first.** Any controller that inherits from a non-existent class will silently pass all development tests and crash production on deploy.
- **Check production server logs before investigating Flutter errors.** A dead server invalidates any client-side debugging. Confirm the server is healthy first, then work on the client.
- **Two independent bugs can produce a single confusing failure.** SSO login failing on TestFlight looked like one issue — it was actually a client misconfiguration and a server crash at the same time. Fix both.
