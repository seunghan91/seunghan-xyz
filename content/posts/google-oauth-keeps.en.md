---
title: "Flutter App Google OAuth Consent Screen Setup Guide"
date: 2025-06-11
draft: true
tags: ["Flutter", "OAuth", "Google", "App Development"]
description: "Google Cloud Console OAuth consent screen configuration and the certification submission process troubles."
cover:
  image: "/images/og/google-oauth-keeps.png"
  alt: "Google Oauth Keeps"
  hidden: true
---

This post documents the process of adding Google Sign-In to a Flutter app, including setting up the OAuth consent screen and completing the verification process.

When issuing an OAuth client ID directly from Google Cloud Console without Firebase, unexpected errors frequently occur during consent screen configuration and certification submission. The official documentation glosses over many of these edge cases. This guide focuses on the real issues encountered during implementation.

---

## Overall Flow

1. Create an OAuth 2.0 client ID in Google Cloud Console (iOS type)
2. Configure the consent screen branding
3. Register the app domain and privacy policy URL
4. Set up required scopes
5. Submit for verification and switch to production

This flow looks straightforward but each step hides validation logic that will silently reject your submission if the conditions are not met precisely.

---

## Creating the OAuth Client ID

In Google Cloud Console, navigate to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.

For a Flutter iOS app, select **iOS** as the application type. Enter the Bundle ID and download the generated `.plist` file. This file contains the `REVERSED_CLIENT_ID`, which is used as the OAuth redirect URL scheme on iOS.

For Android, a **SHA-1 certificate fingerprint** is required. Debug and release builds have different fingerprints, so make sure to register the release keystore SHA-1 before shipping to production.

```bash
# Get SHA-1 from the debug keystore
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
```

In your Flutter project, add the `google_sign_in` package:

```yaml
# pubspec.yaml
dependencies:
  google_sign_in: ^6.2.0
```

On iOS, register the `REVERSED_CLIENT_ID` as a URL scheme in `Info.plist` so that the OAuth callback can return to your app:

```xml
<!-- ios/Runner/Info.plist -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.googleusercontent.apps.YOUR_CLIENT_ID</string>
    </array>
  </dict>
</array>
```

Without this, the sign-in flow will complete on the browser side but the app will never receive the callback token.

---

## Branding Configuration

Go to Google Cloud Console → **APIs & Services → OAuth consent screen → Branding** and fill in the following fields:

- **App name**: The name displayed on the consent screen (must exactly match the text visible on your homepage)
- **User support email**: Contact email shown to users
- **App domain**: Homepage, privacy policy, and terms of service URLs
- **Authorized domains**: Root domains of the URLs above

For authorized domains, enter only the top-level domain. If your privacy policy URL is `https://example.com/app/privacy/`, the authorized domain is just `example.com`. Including subdomains or paths causes validation errors.

---

## Gotcha 1: App Name Mismatch Error

After saving, the following error may appear when submitting for verification:

> The app name configured on the OAuth consent screen does not match the app name on the homepage.

Google crawls your homepage URL and compares the **text rendered in the page body** against the app name entered in the console.

`<title>` tags or `<meta>` tags alone will not pass. The text must be visible in the actual DOM. For single-page applications where content is rendered by JavaScript, the crawler may not execute the JS and therefore fail to find the text. Embedding the app name in static HTML is the safest approach.

### Solution

Add text identical to the console app name directly in the homepage HTML body:

```html
<p>Your App Name (exactly as entered in the console)</p>
```

For static site generators like Hugo or Jekyll, add the app name to a header or footer partial so it appears on every page. Hiding the text with CSS (`display: none`) is unreliable since it is unclear whether Google's crawler treats hidden text as visible. Place the text somewhere that fits naturally in the page layout.

---

## Data Access (Scopes)

**If you only need basic Google Sign-In, you do not need to add any scopes.**

`openid`, `email`, and `profile` are included by default with Google Sign-In. They work automatically without adding them in the console, and no separate verification review is required for these.

Cases where explicit scope addition is necessary:

| Feature | Scope | Review Type |
|---|---|---|
| Google Drive file access | `drive.file` | Sensitive scope review |
| Gmail access | `gmail.*` | Restricted scope review |
| Google Calendar | `calendar` | Sensitive scope review |

Adding unnecessary scopes increases review complexity and timeline significantly. Only request scopes your app actually uses.

In your Flutter code, the `scopes` parameter in `google_sign_in` must match what is registered in the console. Declaring a scope in code without registering it in the console will cause a runtime error during the sign-in flow.

```dart
final GoogleSignIn _googleSignIn = GoogleSignIn(
  scopes: [
    'email',
    'profile',
    // Only add extra scopes if genuinely needed
    // 'https://www.googleapis.com/auth/drive.file',
  ],
);
```

---

## Verification Submission

- **Testing status**: Only test accounts registered in the console can sign in
- **Production status**: All Google account users can sign in after verification is complete

After completing branding and data access settings, submit in the **Verification** tab.

Before submitting, confirm that all required fields are filled in and that every URL is live and accessible. If the privacy policy URL returns a 404 at submission time, the request is rejected immediately.

---

## Gotcha 2: Privacy Policy URL Validation Failure

The privacy policy URL entered in the app domain section must be accessible to Google's crawler.

If you run a static site on a platform like Hugo hosted on Netlify, the URL must be a deployed production URL. `localhost` or undeployed staging URLs will fail validation. Check that the URL is reachable before submitting.

When using Netlify or GitHub Pages, use the production domain URL, not a deploy preview URL such as `deploy-preview-xxx.netlify.app`. Also verify that your `robots.txt` does not block Googlebot, since crawling restrictions apply to consent screen verification too.

A privacy policy page that passes Google's review should contain at minimum:

- What data is collected (name, email, etc.)
- How the data is used
- Data retention and deletion policy
- Contact email for privacy inquiries

---

## Gotcha 3: "App Not Verified" Warning in Testing Status

When the OAuth consent screen is in **Testing** status, signing in with an account that is not registered as a test user will show an "App not verified" warning. This is expected behavior and will disappear once verification is submitted and the status switches to production.

During the testing phase, add test account emails to the **Test users** section in the console to allow login without the warning.

One additional edge case: even for registered test users, an existing session from a previous sign-in can sometimes cause the warning to reappear. To resolve this, revoke the app's access permissions at `accounts.google.com/permissions` and sign in again.

---

## Verification Review Timeline

Google OAuth verification review typically completes within a few days when no sensitive scopes are involved (basic login only). When sensitive scopes such as `drive` or `gmail` are included, the review can take weeks to months, and submission of an official app website and a demo video is required.

For apps that only use basic Google Sign-In, switching to production is possible immediately without a separate review period.

Review status is visible in the **OAuth consent screen → Verification** tab in Google Cloud Console. If the submission is rejected, the rejection reason is displayed alongside the status. Resubmission is allowed without a limit on attempts, so corrections can be submitted as many times as needed.

---

## Post-Production Considerations

After switching to production, modifying the app name, privacy policy URL, or registered scopes may trigger a re-review. Adding a new sensitive scope in particular can temporarily revert the app to testing status while the new scope is under review.

If scopes need to change after the app has shipped, minimize the scope of changes and use feature flags so that existing functionality remains unaffected while the review is in progress.

---

## Key Takeaways

- The **app name** in the console must exactly match text rendered in the homepage DOM. `<title>` and `<meta>` tags do not count.
- The **privacy policy URL** must be a deployed, publicly accessible URL at the time of submission.
- **Basic Google Sign-In** (`openid`, `email`, `profile`) requires no additional scopes and no separate review for production.
- The **"App not verified" warning** in testing status is normal behavior; register test user emails to bypass it during development.
- **iOS** requires the `REVERSED_CLIENT_ID` as a URL scheme in `Info.plist`; **Android** requires both debug and release keystore SHA-1 fingerprints.
- With no sensitive scopes, the verification review typically completes within a few days.

---

## Summary

| Item | Notes |
|------|---------|
| App name | Console input must match visible homepage DOM text |
| Privacy policy URL | Must be a deployed URL accessible to Google's crawler |
| Scopes | No addition needed for basic Sign-In only |
| Test accounts | In testing status, only registered accounts can sign in without warning |
| Verification submission | Immediate production switch possible with no sensitive scopes |
| iOS setup | REVERSED_CLIENT_ID must be registered as a URL scheme in Info.plist |
| Android setup | Both debug and release keystore SHA-1 fingerprints must be registered |
