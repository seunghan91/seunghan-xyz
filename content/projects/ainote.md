---
title: "AInote"
date: 2025-06-20
draft: false
tags: ["Flutter", "AI", "Productivity", "Cross-Platform"]
description: "AI 기반 크로스 플랫폼 스마트 노트 서비스"
weight: 1
---

## AInote

AI 기반 크로스 플랫폼 스마트 노트 서비스입니다. 맥, 웹, 모바일, 텔레그램까지 어디서든 메모를 작성하고 AI의 도움을 받을 수 있습니다.

---

## Mac App

macOS 네이티브 앱으로, 데스크톱 환경에 최적화된 경험을 제공합니다.

### 주요 기능

- **메뉴바 퀵 노트**: 메뉴바에서 빠르게 메모 작성
- **글로벌 단축키**: 어떤 앱에서든 단축키로 즉시 메모
- **Spotlight 통합**: Spotlight에서 바로 노트 검색
- **iCloud 동기화**: Apple 기기 간 자동 동기화
- **AI 어시스턴트**: 텍스트 요약, 번역, 문법 교정

### 기술 스택

- Swift / SwiftUI
- Core Data
- CloudKit

---

## Web App

브라우저에서 접근 가능한 웹 애플리케이션입니다.

### 주요 기능

- **반응형 디자인**: 데스크톱/태블릿/모바일 모든 화면 지원
- **실시간 동기화**: 모든 기기에서 실시간으로 노트 동기화
- **마크다운 에디터**: 풍부한 마크다운 편집 기능
- **AI 기반 검색**: 자연어로 노트 검색
- **태그 & 폴더**: 체계적인 노트 정리
- **다크 모드**: 눈의 피로를 줄이는 다크 테마

### 기술 스택

- React / Next.js
- TypeScript
- Supabase (Auth, Database, Realtime)
- Tailwind CSS

---

## Mobile App

iOS와 Android를 지원하는 모바일 앱입니다.

### 주요 기능

- **음성 녹음 & 전사**: 음성을 녹음하고 AI가 자동으로 텍스트 변환
- **OCR 스캔**: 카메라로 문서를 스캔하여 텍스트 추출
- **위젯 지원**: 홈 화면에서 빠르게 메모 확인 및 작성
- **오프라인 모드**: 인터넷 없이도 메모 작성 가능
- **푸시 알림**: 리마인더 및 공유 노트 알림
- **생체 인증**: Face ID / Touch ID / 지문 인식 잠금

### 기술 스택

- Flutter / Dart
- Riverpod (상태 관리)
- Hive (로컬 저장소)
- Firebase (푸시 알림, 분석)

### 다운로드

- [App Store](https://apps.apple.com)
- [Google Play](https://play.google.com)

---

## Telegram Bot

텔레그램에서 바로 메모를 작성하고 관리할 수 있는 봇입니다.

### 주요 기능

- **빠른 메모**: 메시지를 보내면 바로 노트로 저장
- **음성 메모**: 음성 메시지를 텍스트로 변환하여 저장
- **사진 & 파일**: 이미지, 문서를 노트에 첨부
- **AI 대화**: 저장된 노트를 바탕으로 AI와 대화
- **노트 검색**: `/search` 명령어로 노트 검색
- **리마인더**: `/remind` 명령어로 알림 설정

### 명령어

```
/start - 봇 시작 및 계정 연결
/new - 새 노트 작성
/list - 최근 노트 목록
/search [키워드] - 노트 검색
/remind [시간] [내용] - 리마인더 설정
/ai [질문] - AI에게 질문
```

### 기술 스택

- Node.js
- Telegraf (Telegram Bot Framework)
- OpenAI API (Whisper, GPT)

---

## 공통 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Supabase (PostgreSQL, Auth, Storage) |
| AI | OpenAI API (GPT-4, Whisper) |
| 인프라 | Cloudflare, Vercel |
| 모니터링 | Sentry, Analytics |
