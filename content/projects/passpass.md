---
title: "PassPass - 간편인증 자동입력"
date: 2026-02-24
draft: false
tags: ["Chrome Extension", "JavaScript", "Productivity", "Automation"]
description: "공공기관·금융 사이트의 간편인증 팝업에서 이름·생년월일·휴대폰번호를 자동 입력하는 Chrome 확장프로그램"
weight: 2
---

## PassPass

공공기관·금융 사이트에서 매번 반복되는 간편인증 정보 입력을 자동화하는 Chrome 확장프로그램입니다.

홈택스, 정부24, 민원24 등에서 본인인증 팝업이 열리면 이름·생년월일·휴대폰번호를 자동으로 입력하고, 선호하는 인증기관(PASS, 카카오, 토스 등)까지 자동으로 선택합니다.

---

## 주요 기능

### 간편인증(OACX) 자동입력
- 이름 / 생년월일 / 휴대폰번호 자동 입력
- PASS · 카카오톡 · 토스 · 국민인증서 · 네이버 · 신한 · 하나 · 우리 · NH · 삼성패스 · 뱅크샐러드 자동 선택

### KMC 휴대폰 본인인증 자동화 (kmcert.com)
- 통신사 자동 선택 (SKT / KT / LGU+ / 알뜰폰)
- SMS · PASS · QR 인증방식 자동 선택
- 이름 · 생년월일 · 주민번호 성별코드 · 휴대폰번호 자동 입력

### NICE 본인인증 자동화 (nice.checkplus.co.kr)
- 통신사 · 인증방식 자동 선택
- SMS 정보 입력 자동 처리

### 토스 인증 자동입력 (auth.cert.toss.im)
- 이름 · 휴대폰번호 · 생년월일 자동 입력
- 개인정보 수집·이용 동의 자동 체크

### PIN 잠금 보안
- 숫자 4자리 PIN으로 개인정보 보호
- 브라우저 세션 종료 시 자동 잠금

---

## 지원 사이트

국세청 홈택스, 정부24, 국민건강보험공단, 국민연금공단, 행정안전부, 학점은행제, 법무부 전자공증, 대법원 전자소송, SRT, 우체국, 병무청, 복지로, 워크24 등 **50개 이상의 공공·금융 사이트** 및 KMC·NICE 인증 연동 사이트 전체를 지원합니다.

---

## 기술 스택

- **Chrome Extension Manifest V3**
- Vanilla JavaScript (Content Script, Background Service Worker)
- Chrome Storage API (session / local)
- MutationObserver 기반 DOM 감지 및 자동입력

---

## 개인정보 보호

- 입력한 모든 정보는 내 브라우저(로컬 스토리지)에만 저장
- 외부 서버로 개인정보 전송 없음
- PIN 잠금으로 제3자 접근 차단

---

## 다운로드

- [Chrome 웹 스토어](https://chrome.google.com/webstore/detail/dpignhngmpbbnekagndefmlkoifpcemm)
