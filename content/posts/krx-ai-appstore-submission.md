---
title: "KRX AI — App Store 제출 정보 레퍼런스"
date: 2026-03-05
draft: false
tags: ["KRX", "AppStore", "iOS", "제출", "레퍼런스"]
description: "KRX AI 임직원 전용 앱 App Store Connect 제출 시 입력할 내용 정리"
---

> Apple ID: **6760086555** · Bundle ID: `com.krxai.app` · 버전: **1.0**

---

## 프로모션 텍스트 (최대 170자)

```
한국거래소 임직원을 위한 AI 업무 지원 플랫폼. Claude AI 기반 업무 질의, 서비스 요청, 실시간 알림을 한 앱에서.
```

---

## 설명 (최대 4,000자)

```
KRX AI는 한국거래소(KRX) 임직원 전용 AI 업무 지원 플랫폼입니다.

■ 주요 기능

▸ AI 대화
Claude AI 기반의 업무 보조 채팅으로 복잡한 질의도 빠르게 처리합니다.
회의실 예약 현황, 내부 규정 검색, 보고서 초안 작성 등 다양한 업무를 지원합니다.

▸ 서비스 요청
IT 서비스 요청을 간편하게 제출하고 처리 현황을 실시간으로 확인합니다.
웍스 AI 요금 상향, IT 문의, 시스템 접근 권한 등 업무 요청을 담당자에게 전달합니다.

▸ 알림 센터
서비스 요청 처리 결과와 중요 공지사항을 푸시 알림으로 실시간 수신합니다.

■ 사용 대상
한국거래소(KRX) 임직원 전용 서비스입니다.
KRX 사내 이메일(@krx.co.kr) 계정으로 로그인하세요.

■ 문의
디지털혁신팀 내선 8893, 8894
```

---

## 키워드 (최대 100자)

```
KRX,한국거래소,AI,업무지원,임직원,서비스요청,AI채팅,디지털혁신,기업용,ITSM
```

> 46자

---

## URL

| 항목 | 값 |
|------|-----|
| 지원 URL | `https://krx-ai-web.onrender.com/` |
| 마케팅 URL | `https://krx-ai-web.onrender.com/` |

---

## 버전 / 저작권

| 항목 | 값 |
|------|-----|
| 버전 | `1.0` |
| 저작권 | `© 2026 한국거래소 (KRX)` |

---

## 앱 심사 정보

### 로그인 정보

> ⚠️ 이 앱은 **@krx.co.kr 사내 이메일 OTP 인증** 방식으로 로그인합니다.
> 일반 계정/비밀번호가 없으므로 메모에 설명을 명시하세요.

- **로그인 필요**: ✅ 체크
- **사용자 이름**: `reviewer` *(심사용 데모 계정 아이디)*
- **암호**: *(없음 — 아래 메모 참조)*

### 연락처 정보

| 항목 | 값 |
|------|-----|
| 이름 | `Seunghan` |
| 성 | `Kim` |
| 전화번호 | *(담당자 전화번호 입력)* |
| 이메일 | `theqwe2000@naver.com` |

### 메모 (심사팀에 전달할 내용)

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

## 카테고리 / 연령 등급

| 항목 | 값 |
|------|-----|
| 기본 카테고리 | 비즈니스 (Business) |
| 추가 카테고리 | 생산성 (Productivity) |
| 연령 등급 | **4+** |

---

## 암호화

`Info.plist` 에 추가:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

---

## 스크린샷 파일 위치

`/Users/seunghan/krx_ai/icon_drafts/store_export/`

| 슬롯 | 파일명 | 크기 |
|------|--------|------|
| iPhone 6.5" | `01_hero_iphone_65.png` | 1242×2688 |
| iPhone 6.5" | `03_service_iphone_65.png` | 1242×2688 |
| iPhone 6.5" | `05_cta_iphone_65.png` | 1242×2688 |
| iPhone 6.5" (대안) | `*_iphone_65b.png` | 1284×2778 |
| iPhone 6.9" | `01_hero_iphone_69.png` | 1290×2796 |
| iPhone 6.9" | `03_service_iphone_69.png` | 1290×2796 |
| iPhone 6.9" | `05_cta_iphone_69.png` | 1290×2796 |

---

## 버전 출시 방법

- **수동으로 버전 출시** 선택 권장 *(심사 통과 후 직접 타이밍 조절)*
