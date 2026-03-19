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

## Promotional Text (max 170 characters)

```
AI work support platform for Korea Exchange employees. Claude AI-powered work queries, service requests, and real-time notifications in one app.
```

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

---

## URLs

| Item | Value |
|------|-------|
| Support URL | `https://krx-ai-web.onrender.com/` |
| Marketing URL | `https://krx-ai-web.onrender.com/` |

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

---

## Encryption

Add to `Info.plist`:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

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

---

## Release Method

- **Manual release** recommended *(control timing yourself after review approval)*
