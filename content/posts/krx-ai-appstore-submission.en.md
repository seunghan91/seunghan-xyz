---
title: "KRX AI — App Store Submission Reference"
date: 2025-12-30
draft: true
tags: ["KRX", "AppStore", "iOS", "Submission", "Reference"]
description: "Reference for App Store Connect submission information for the KRX AI employee-only app."
cover:
  image: "/images/og/krx-ai-appstore-submission.png"
  alt: "Krx Ai Appstore Submission"
  hidden: true
---

> Apple ID: **6760086555** -- Bundle ID: `com.krxai.app` -- Version: **1.0**

---

## Overview

KRX AI is an AI-powered work support platform built exclusively for employees of Korea Exchange (KRX). Because this is an internal enterprise tool rather than a public-facing app, the App Store review process requires a different approach compared to consumer apps. This document consolidates all the text needed for App Store Connect submission, guidance on handling the review team, and key technical notes in one practical reference.

Stack summary:
- **Backend**: Rails 8 + Hotwire (Turbo/Stimulus)
- **Mobile**: Hotwire Native (iOS / Android)
- **AI**: Anthropic Claude API
- **Authentication**: KRX corporate email OTP (passwordless)
- **Deployment**: Render (Singapore region)

---

## Promotional Text (max 170 characters)

```
AI work support platform for Korea Exchange employees. Claude AI-powered work queries, service requests, and real-time notifications in one app.
```

The promotional text appears above the description on the App Store listing and can be updated at any time without going through review. This makes it the only field that can be changed quickly for new feature announcements or internal communications. Since KRX AI is an internal service, the text focuses on feature clarity rather than marketing language.

---

## Description (max 4,000 characters)

```
KRX AI is an AI work support platform exclusively for Korea Exchange (KRX) employees.

- Key Features

> AI Chat
Claude AI-powered work assistant chat that quickly handles complex queries.
Supports various tasks including meeting room reservation status, internal regulation search, and report draft creation.

> Service Requests
Easily submit IT service requests and check processing status in real time.
Forwards work requests such as Works AI rate increases, IT inquiries, and system access permissions to the responsible staff.

> Notification Center
Receive service request results and important announcements via push notifications in real time.

- Target Users
This is an exclusive service for Korea Exchange (KRX) employees.
Log in with your KRX corporate email (@krx.co.kr) account.

- Contact
Digital Innovation Team ext. 8893, 8894
```

---

## Keywords (max 100 characters)

```
KRX,Korea Exchange,AI,work support,employee,service request,AI chat,digital innovation,enterprise,ITSM
```

> 46 characters

Keyword selection rationale:
- **KRX / Korea Exchange**: Brand search coverage. These are the first terms employees will type when looking for the internal app.
- **ITSM**: IT Service Management. Clearly signals the nature of the service request feature.
- **enterprise**: Differentiates the app from consumer-facing tools in the same category.
- Variants and synonyms (e.g., artificial intelligence, chatbot) were deprioritized given the 100-character limit.

---

## URLs

| Item | Value |
|------|-------|
| Support URL | `https://krx-ai-web.onrender.com/` |
| Marketing URL | `https://krx-ai-web.onrender.com/` |

Important: Render's free tier puts instances to sleep after a period of inactivity. During the review period, either upgrade to a paid plan or set up a cron job to send periodic heartbeat requests and prevent sleep. If the App Store review team encounters a timeout when accessing the support URL, it can become grounds for rejection.

---

## Version / Copyright

| Item | Value |
|------|-------|
| Version | `1.0` |
| Copyright | `(c) 2026 Korea Exchange (KRX)` |

---

## App Review Information

### Login Information

> This app uses **@krx.co.kr corporate email OTP authentication** for login.
> There is no standard username/password, so provide an explanation in the notes.

- **Sign-in required**: Checked
- **Username**: `reviewer` *(demo account ID for review)*
- **Password**: *(none -- see notes below)*

### Contact Information

| Item | Value |
|------|-------|
| First name | `Seunghan` |
| Last name | `Kim` |
| Phone | *(enter contact phone number)* |
| Email | `theqwe2000@naver.com` |

### Notes (for the review team)

```
This app is an internal enterprise tool exclusively for employees of Korea Exchange (KRX).

[Login Method]
This app uses a passwordless OTP (One-Time Password) authentication via corporate email.
Normal login requires a @krx.co.kr corporate email address.

[For App Review]
A demo account has been configured for review purposes that bypasses the corporate email restriction.
Demo credentials:
  - Username: reviewer (enter without @krx.co.kr)
  - An OTP code will be sent to the review team email, or please use the magic link if provided.

Alternatively, the app can be reviewed in demo mode:
  - All core features (AI Chat, Service Requests, Notifications) are fully functional once logged in.
  - The AI Chat feature uses Claude API and requires network connectivity.

[Contact]
For any questions during review, please contact: theqwe2000@naver.com
```

---

## Category / Age Rating

| Item | Value |
|------|-------|
| Primary category | Business |
| Secondary category | Productivity |
| Age rating | **4+** |

When completing the age rating questionnaire, mark all content categories (mature/suggestive content, violence, gambling, etc.) as "None." Even though KRX AI includes an AI chat feature powered by Claude, the responses are generated by a backend API rather than user-generated content (UGC), so no age-rating escalation is required. The 4+ rating is appropriate.

---

## Encryption

Add to `Info.plist`:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

Submitting without this key causes App Store Connect to request Export Compliance documentation (ERN) or delay the build. KRX AI uses only standard HTTPS/TLS and does not implement any proprietary encryption algorithms, so `false` is correct. If you use XcodeGen, add the same entry to `project.yml` and run `make gen-ios` to regenerate the Xcode project. Editing `Info.plist` directly will be overwritten on the next `gen-ios` run.

---

## Screenshot File Locations

`/Users/seunghan/krx_ai/icon_drafts/store_export/`

| Slot | Filename | Size |
|------|----------|------|
| iPhone 6.5" | `01_hero_iphone_65.png` | 1242x2688 |
| iPhone 6.5" | `03_service_iphone_65.png` | 1242x2688 |
| iPhone 6.5" | `05_cta_iphone_65.png` | 1242x2688 |
| iPhone 6.5" (alt) | `*_iphone_65b.png` | 1284x2778 |
| iPhone 6.9" | `01_hero_iphone_69.png` | 1290x2796 |
| iPhone 6.9" | `03_service_iphone_69.png` | 1290x2796 |
| iPhone 6.9" | `05_cta_iphone_69.png` | 1290x2796 |

Screenshot upload notes:
- App Store Connect requires a minimum of 1 and a maximum of 10 screenshots per device slot.
- If the 6.9" slot is left empty, App Store will scale up the 6.5" images for iPhone 16 Pro Max. Uploading both slots is recommended for visual quality.
- Device frames around screenshots are optional and have no impact on review outcome.

---

## Release Method

- **Manual release** recommended *(control timing yourself after review approval)*

Choosing automatic release deploys the build immediately upon approval. For an internal service like KRX AI, there may be internal sign-off steps required before the app reaches all employees. Manual release lets the team coordinate the go-live timing with the KRX Digital Innovation team rather than being locked to Apple's approval schedule.

---

## Technical Background: Why Hotwire Native

KRX AI wraps a Rails 8 + Hotwire web application inside a Hotwire Native shell for both iOS and Android. The rationale behind this architectural choice:

**Single codebase**: Because the Rails view layer works identically for web and mobile, adding features does not require separate iOS/Android native code. KRX internal workflows change frequently due to shifting requirements, and this architecture makes those changes cheap to ship.

**Selective native escalation**: Hotwire Native's Path Configuration lets specific URL patterns trigger native view overlays. The AI chat interface, where a smooth typing and streaming experience matters most, can be built as a native view while the rest of the app (service request forms, notification list, settings) runs on the web layer.

**App Store review implications**: Hotwire Native apps are fundamentally WKWebView-based. The review team may flag the app as a "web wrapper" under Guideline 4.2 if the submission does not make the native functionality clear. The review notes must explicitly describe the Hotwire Native architecture and call out native features such as push notifications and device-level authentication.

---

## Debugging Log: Key Issues and Resolutions

### 1. Demo Account for OTP Authentication

**Problem**: The App Store review team does not have a `@krx.co.kr` corporate email address, so they cannot receive an OTP. Passwordless enterprise apps without a fallback login path are one of the most common causes of rejection under Guideline 5.1.1.

**Resolution**: A `reviewer` demo account was configured to bypass the corporate email restriction in demo mode. The Rails backend adds a conditional branch that creates a session for the username `reviewer` without requiring OTP, active only in the production environment.

```ruby
# app/controllers/sessions_controller.rb (simplified)
def create_otp_session
  if params[:username] == "reviewer" && Rails.env.production?
    # Review path: create session without OTP
    session[:user_id] = demo_user.id
    redirect_to root_path
  else
    # Standard path: send OTP
    send_otp_to(params[:username])
  end
end
```

### 2. Render Sleep Timeout

**Problem**: On Render's free tier, instances sleep after 15 minutes of inactivity. When the review team accessed the support URL (`https://krx-ai-web.onrender.com/`), cold-start latency exceeded 30 seconds, causing the review to stall.

**Resolution**: The Render service was upgraded to the Standard plan ($7/month) before submission. For free-tier setups, a GitHub Actions cron job sending a health check every 10 minutes effectively prevents sleep.

```yaml
# .github/workflows/keep-alive.yml
name: Keep Render Alive
on:
  schedule:
    - cron: "*/10 * * * *"
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -s https://krx-ai-web.onrender.com/up
```

### 3. Missing ITSAppUsesNonExemptEncryption

**Problem**: On the first TestFlight upload, App Store Connect displayed a "Missing Compliance" warning. Without this key, every build requires manually answering export compliance questions, and in some cases the submission to review is blocked entirely.

**Resolution**: Added `ITSAppUsesNonExemptEncryption = false` to `Info.plist`. For XcodeGen projects, the same entry must be added to `project.yml` followed by `make gen-ios` to regenerate the Xcode project. Editing `Info.plist` directly is overwritten on the next generation run.

### 4. Screenshot Dimension Rejection

**Problem**: App Store Connect occasionally rejected 1242x2688 images uploaded to the 6.5" slot. Both 1284x2778 (iPhone 12 Pro Max) and 1242x2688 (iPhone 11 Pro Max) are valid, but the portal's error messages are not always clear about which size it expects.

**Resolution**: An alternative set of screenshots at 1284x2778 (`*_iphone_65b.png`) was prepared. Switching to the alternative size resolved the error immediately.

---

## Key Takeaways

1. **The demo account is the critical path for passwordless enterprise apps.** Any app using OTP, SSO, or corporate email authentication must implement a dedicated demo login path that the review team can actually use. Clearly explain the login mechanism in English in the review notes — vague descriptions are a common rejection trigger.

2. **Eliminate Render sleep before submitting.** A support URL that times out signals to the review team that the backend is broken or unreachable. Upgrade to a paid plan or add a cron-based keepalive during the review window.

3. **Bake ITSAppUsesNonExemptEncryption into the build pipeline.** For XcodeGen projects, manage this in `project.yml` rather than editing `Info.plist` by hand. Manual edits will be silently overwritten on the next project generation, causing the compliance warning to reappear on the next upload.

4. **Distinguish Hotwire Native from a web wrapper in the review notes.** Without a clear explanation of the architecture and native features (push notifications, device authentication), the app risks a Guideline 4.2 rejection for being a "simple web wrapper." A one-paragraph description of how Hotwire Native uses a native shell with selective WKWebView rendering is usually sufficient.

5. **Default to manual release for internal services.** Enterprise apps often require sign-off from internal stakeholders before reaching all users. Manual release preserves the ability to coordinate that timing after Apple's approval, rather than going live automatically at an unpredictable moment.
