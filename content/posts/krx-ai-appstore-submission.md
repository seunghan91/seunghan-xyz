---
title: "KRX AI — App Store 제출 정보 레퍼런스"
date: 2025-12-30
draft: true
tags: ["KRX", "AppStore", "iOS", "제출", "레퍼런스"]
description: "KRX AI 임직원 전용 앱 App Store Connect 제출 시 입력할 내용 정리"
cover:
  image: "/images/og/krx-ai-appstore-submission.png"
  alt: "Krx Ai Appstore Submission"
  hidden: true
---

> Apple ID: **6760086555** · Bundle ID: `com.krxai.app` · 버전: **1.0**

---

## 개요

KRX AI는 한국거래소(KRX) 임직원 전용 AI 업무 지원 플랫폼이다. 외부 공개 앱이 아니라 사내 툴이기 때문에 App Store 심사 과정에서 일반 앱과 다른 접근 방식이 필요하다. 이 문서는 App Store Connect 제출 시 입력할 텍스트, 심사팀 대응 방법, 기술적 주의사항을 한 곳에 모은 실무 레퍼런스다.

스택 요약:
- **백엔드**: Rails 8 + Hotwire (Turbo/Stimulus)
- **모바일**: Hotwire Native (iOS / Android)
- **AI**: Anthropic Claude API
- **인증**: KRX 사내 이메일 OTP (passwordless)
- **배포**: Render (싱가포르 리전)

---

## 프로모션 텍스트 (최대 170자)

```
한국거래소 임직원을 위한 AI 업무 지원 플랫폼. Claude AI 기반 업무 질의, 서비스 요청, 실시간 알림을 한 앱에서.
```

프로모션 텍스트는 App Store 설명 위에 표시되며, 심사 없이 언제든 수정 가능하다. 새로운 기능 출시나 이벤트가 있을 때 빠르게 업데이트할 수 있는 유일한 필드다. KRX AI는 내부 서비스이므로 공격적인 마케팅 문구보다 기능 요약에 집중한다.

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

키워드 선정 시 고려한 사항:
- **KRX / 한국거래소**: 브랜드 검색 대응. 직원들이 사내 앱을 검색할 때 가장 먼저 입력할 단어.
- **ITSM**: IT Service Management 약어. 서비스 요청 기능의 성격을 명확히 한다.
- **기업용**: 일반 사용자 대상 앱과 구분되도록 카테고리 신호를 제공.
- 중복이나 변형어(예: 인공지능, AI챗)는 100자 제한 안에서 우선순위가 낮아 제외.

---

## URL

| 항목 | 값 |
|------|-----|
| 지원 URL | `https://krx-ai-web.onrender.com/` |
| 마케팅 URL | `https://krx-ai-web.onrender.com/` |

Render의 무료 플랜은 일정 시간 미사용 시 슬립 상태에 빠진다. 심사 기간 중에는 반드시 유료 플랜으로 전환하거나 cron job으로 heartbeat 요청을 보내 슬립을 방지해야 한다. 심사팀이 지원 URL에 접근할 때 타임아웃이 발생하면 심사 거절 사유가 될 수 있다.

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

연령 등급 설정 시 주의할 점: 성인 콘텐츠, 폭력, 도박 등 관련 항목은 모두 "없음"으로 체크한다. AI 채팅 기능이 있더라도, 사용자 생성 콘텐츠(UGC)가 아닌 Claude API 응답이므로 특별한 등급 상향 없이 4+로 유지 가능하다.

---

## 암호화

`Info.plist` 에 추가:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

이 설정 없이 제출하면 심사팀에서 수출 규정 준수 문서(ERN)를 요청하거나 심사가 지연될 수 있다. KRX AI는 표준 HTTPS/TLS만 사용하며 별도의 암호화 알고리즘을 구현하지 않으므로 `false`가 올바른 값이다. `project.yml`에도 동일하게 추가하고 `make gen-ios` 실행 후 Xcode 프로젝트를 재생성해야 Info.plist에 반영된다.

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

스크린샷 업로드 시 주의사항:
- App Store Connect는 각 기기 슬롯별로 최소 1장, 최대 10장을 요구한다.
- 6.5" 슬롯에 이미지가 있으면 6.9" 슬롯은 선택이지만, 6.9" (iPhone 16 Pro Max 기준)가 없으면 6.5" 이미지가 스케일업되어 표시된다. 품질을 위해 두 슬롯 모두 업로드 권장.
- 스크린샷에 기기 프레임이 없어도 심사 통과에는 문제없다.

---

## 버전 출시 방법

- **수동으로 버전 출시** 선택 권장 *(심사 통과 후 직접 타이밍 조절)*

자동 출시를 선택하면 심사 통과 즉시 배포된다. KRX AI처럼 사내 서비스는 배포 전 내부 확인 절차가 필요할 수 있으므로, 수동 출시를 선택해 KRX 디지털혁신팀과 출시 타이밍을 조율하는 것이 안전하다.

---

## 기술 배경: Hotwire Native 선택 이유

KRX AI는 Ruby on Rails 8 + Hotwire를 백엔드로 사용하는 웹 앱을 iOS/Android에서 Hotwire Native로 감싼 구조다. 이 접근 방식을 선택한 이유:

**단일 코드베이스 유지**: Rails 뷰 레이어가 웹과 모바일에서 동일하게 동작하므로, 기능 추가 시 별도의 iOS/Android 네이티브 코드 작성이 불필요하다. KRX 내부 업무 특성상 빠른 요구사항 변경이 잦아 이 점이 결정적이었다.

**네이티브 전환 비용 최소화**: Hotwire Native는 특정 URL 패턴에 대해 네이티브 뷰를 오버레이할 수 있는 Path Configuration을 지원한다. 핵심 화면(AI 채팅 인터페이스)만 선택적으로 네이티브로 구현하고, 나머지는 웹 기반으로 빠르게 제공할 수 있다.

**App Store 심사 대응**: Hotwire Native 앱은 실질적으로 WKWebView 기반이므로, 심사팀이 웹뷰 전용 앱(단순 URL 래퍼)으로 오해할 수 있다. 이를 방지하기 위해 리뷰 메모에 Hotwire Native 아키텍처에 대한 간략한 설명을 포함하고, 네이티브 기능(푸시 알림, 로컬 인증 등)이 활성화되어 있음을 명시한다.

---

## 디버깅 기록: 주요 이슈와 해결

### 1. OTP 심사 계정 구성

**문제**: 심사팀이 `@krx.co.kr` 도메인 이메일이 없어 OTP를 받을 수 없다. 일반적인 테스트 계정(아이디/비밀번호)이 없는 passwordless 앱은 심사 거절의 일반적 원인이다.

**해결**: 도메인 제한을 우회하는 `reviewer` 계정을 데모 모드로 구성했다. Rails 백엔드에서 특정 사용자명(`reviewer`)에 대해 OTP 없이 세션을 생성하는 조건 분기를 추가했으며, 이 경로는 프로덕션 환경에서만 활성화되고 스테이징에서는 비활성화된다.

```ruby
# app/controllers/sessions_controller.rb (간략화)
def create_otp_session
  if params[:username] == "reviewer" && Rails.env.production?
    # 심사용: OTP 없이 세션 생성
    session[:user_id] = demo_user.id
    redirect_to root_path
  else
    # 일반 경로: OTP 발송
    send_otp_to(params[:username])
  end
end
```

### 2. Render 슬립 타임아웃

**문제**: Render 무료 플랜에서 15분 이상 요청이 없으면 인스턴스가 슬립 상태로 진입한다. 심사팀이 지원 URL(`https://krx-ai-web.onrender.com/`)에 접근할 때 콜드 스타트로 인해 30초 이상 대기가 발생했고, 이것이 심사 지연 요인이 됐다.

**해결**: 심사 제출 전 Render 서비스를 Standard 플랜($7/월)으로 업그레이드했다. 또는 무료 플랜 유지 시 GitHub Actions cron job으로 10분마다 헬스체크 요청을 보내 슬립을 방지할 수 있다.

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

### 3. ITSAppUsesNonExemptEncryption 누락

**문제**: 처음 TestFlight 업로드 시 App Store Connect에서 "Missing Compliance" 경고가 발생했다. 이 항목을 설정하지 않으면 매 빌드마다 수출 규정 준수 여부를 수동으로 응답해야 하며, 심사 제출 자체가 막히기도 한다.

**해결**: `Info.plist`에 `ITSAppUsesNonExemptEncryption = false`를 추가. `project.yml`(XcodeGen 설정 파일)에도 동일한 항목을 추가하고 `make gen-ios`로 Xcode 프로젝트를 재생성해야 실제로 반영된다. `Info.plist`를 직접 수정하면 다음 `gen-ios` 실행 시 덮어씌워진다.

### 4. 스크린샷 크기 오류

**문제**: App Store Connect가 6.5" 슬롯에 1242×2688 이미지를 업로드할 때 거부한 케이스가 있었다. 실제로는 1284×2778(iPhone 12 Pro Max 기준) 또는 1242×2688(iPhone 11 Pro Max 기준) 두 규격이 모두 허용된다.

**해결**: `*_iphone_65b.png` 파일(1284×2778)을 대안으로 준비해 두었다. App Store Connect UI에서 오류 메시지를 확인하고 크기를 전환하면 해결된다.

---

## Key Takeaways

1. **Passwordless 앱은 심사 계정 구성이 핵심이다.** OTP 또는 SSO 전용 인증 방식을 사용하는 엔터프라이즈 앱은, 심사팀이 직접 로그인할 수 있는 별도 데모 경로를 반드시 구현해야 한다. 메모란에 로그인 방식을 영어로 명확히 설명해야 심사 거절을 피할 수 있다.

2. **Render 슬립 문제는 심사 기간에 반드시 해결해야 한다.** 지원 URL이 응답하지 않으면 심사팀이 앱이 작동하지 않는다고 판단할 수 있다. cron heartbeat 또는 유료 플랜 전환으로 사전 차단한다.

3. **ITSAppUsesNonExemptEncryption은 빌드 파이프라인에 포함시킨다.** XcodeGen을 사용하는 프로젝트에서 `project.yml` 기반으로 관리하면 수동 수정 실수를 방지할 수 있다.

4. **Hotwire Native 앱은 웹뷰 앱과 구분되어야 한다.** 심사 메모에서 아키텍처와 네이티브 기능을 명시하지 않으면 "단순 URL 래퍼" 거절(Guideline 4.2)을 받을 수 있다.

5. **수동 출시를 기본으로 한다.** 내부 서비스는 심사 통과 후에도 관련 팀과 출시 타이밍을 조율해야 하므로, 자동 배포보다 수동 출시가 안전하다.
