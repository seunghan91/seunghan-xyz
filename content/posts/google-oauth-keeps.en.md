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


Here is the process of adding Google Sign-In to a Flutter app, including completing the OAuth consent screen verification.

When issuing an OAuth client ID directly from Google Cloud Console without Firebase, unexpected errors frequently occur during consent screen configuration and certification submission. This is a record focused on the actual troubles encountered.

---

## Overall Flow Summary

1. Create an OAuth 2.0 client ID in Google Cloud Console (iOS type)
2. Configure the consent screen branding
3. Register app domain and privacy policy URL
4. Set up required scopes
5. Submit for verification and switch to production

---

## Branding Configuration

Go to Google Cloud Console -> **APIs & Services -> OAuth consent screen -> Branding** and fill in the following items.

- **App name**: The name displayed on the consent screen (must match exactly with the text on the homepage)
- **User support email**: Contact email
- **App domain**: Homepage, privacy policy, terms of service URLs
- **Authorized domains**: Root domains of the URLs above

---

## Gotcha: App Name Mismatch Error

After saving, the following error may occur when submitting for verification.

> The app name configured on the OAuth consent screen does not match the app name on the homepage.

Google crawls the homepage URL and compares the **text rendered in the page body** with the app name entered in the console.

`<title>` tags or `<meta>` tags alone will not pass. It must be text visible in the actual DOM.

### Solution

Add text identical to the console app name to the homepage HTML body.

```html
<p>App Name (exactly as entered in the console)</p>
```

---

## Data Access (Scopes)

**If you are only implementing basic Google Sign-In, you do not need to add any scopes.**

`openid`, `email`, `profile` are scopes included by default in Google Sign-In. They work automatically without separate addition in the console, and no separate review is required.

Cases where scope addition is necessary:

| Feature | Scope | Review |
|---|---|---|
| Google Drive storage | `drive.file` | Sensitive scope review |
| Gmail | `gmail.*` | Restricted scope review |
| Google Calendar | `calendar` | Sensitive scope review |

Adding unnecessary scopes only increases the review difficulty, so add only what you actually use.

---

## Verification Submission

- **Testing status**: Only test accounts registered in the console can log in
- **Production status**: After verification is complete, all Google account users can log in

After completing branding and data access settings, submit in the **Verification** tab.

---

## Gotcha: Privacy Policy URL Validation Failure

The privacy policy URL entered in the app domain field must be accessible to Google's bot.

If you run a static site like a Hugo blog, it must be a deployed URL. `localhost` or undeployed URLs will not pass validation. Verify that the actual URL is accessible before submitting for verification.

---

## Gotcha: "App Not Verified" Warning in Testing Status

When the OAuth consent screen is in **Testing** status, logging in with an account other than registered test accounts will show an "App not verified" warning. This is normal and will disappear once verification is submitted and the status switches to production.

During the testing phase, add test account emails to the **Test users** section in the console to allow login without the warning.

---

## Verification Review Timeline

Google OAuth verification review typically completes within a few days when no sensitive scopes are present (basic login only). When sensitive scopes (`drive`, `gmail`, etc.) are included, it can take weeks to months, and submission of an official app website and demo video is required.

For apps that only use basic Google Sign-In, switching to production is possible immediately without separate review.

---

## Summary

| Item | Notes |
|------|---------|
| App name | Console input must match homepage DOM text |
| Privacy policy URL | Must be a deployed URL that is actually accessible |
| Scopes | No addition needed for basic login only |
| Test accounts | In testing status, only registered accounts can log in without warning |
| Verification submission | Immediate production switch possible if no sensitive scopes |
