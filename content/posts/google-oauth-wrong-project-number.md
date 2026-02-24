---
title: "Google OAuth 클라이언트 ID의 프로젝트 번호가 Firebase 프로젝트 번호와 다른 경우"
date: 2026-02-24
draft: false
tags: ["Google OAuth", "Firebase", "GCP", "삽질"]
description: ".env에 저장된 Google OAuth Client ID의 프로젝트 번호가 Firebase 프로젝트 번호와 달라서 secret을 찾을 수 없었던 경험 정리"
---

Google OAuth를 새로운 환경에서 재설정하려는데 기존에 저장된 Client ID의 프로젝트 번호가 Firebase 프로젝트 번호와 달라 secret을 찾을 수 없었던 케이스를 정리한다.

---

## 상황

`.env` 파일에 이런 형태로 저장되어 있었다.

```
GOOGLE_CLIENT_ID=1091056260493-xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=   # 비어있음
```

Firebase 콘솔을 확인하니 해당 앱의 실제 프로젝트 번호는 `333977052282`였다.

Google OAuth Client ID의 앞부분 숫자가 **GCP 프로젝트 번호**다. 즉 `1091056260493`이라는 프로젝트가 따로 존재해야 하는데, gcloud 계정에서 확인해보니 해당 번호의 프로젝트가 없었다.

---

## 원인 파악

```bash
# 전체 프로젝트 목록 확인
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects" | \
  python3 -c "import sys,json; [print(p['projectNumber'], p['projectId']) for p in json.load(sys.stdin)['projects']]"
```

결과에서 `1091056260493` 번호를 가진 프로젝트가 없음을 확인.

가능한 원인들:
- 과거에 다른 Google 계정으로 생성한 프로젝트
- 프로젝트가 삭제됨
- 다른 용도로 생성했다가 방치된 OAuth 클라이언트

---

## 해결: 올바른 프로젝트에서 새로 생성

Firebase 프로젝트의 실제 번호(`333977052282`)에 해당하는 GCP 프로젝트에서 새 OAuth 클라이언트를 생성했다.

**Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → OAuth 클라이언트 ID 만들기**

- 애플리케이션 유형: 웹 애플리케이션
- 이름: 임의 설정

생성 결과:
```
Client ID: 333977052282-xxxxxxxxx.apps.googleusercontent.com
Client Secret: GOCSPX-xxxxxxxxxxxxxxxx
```

앞부분 번호(`333977052282`)가 Firebase 프로젝트 번호와 일치한다.

---

## OAuth 클라이언트와 Firebase 프로젝트의 관계

Firebase 프로젝트는 내부적으로 GCP 프로젝트 위에서 동작한다. Firebase 콘솔에서 보이는 **프로젝트 번호 = GCP 프로젝트 번호**다.

OAuth 클라이언트를 생성할 때 어떤 GCP 프로젝트에서 만드느냐에 따라 Client ID 앞의 번호가 달라진다. Firebase 앱과 연동할 OAuth 클라이언트라면 **같은 Firebase/GCP 프로젝트에서 생성**해야 한다.

```
Firebase 프로젝트: my-app (프로젝트 번호: 333977052282)
                    ↓ 같은 프로젝트에서 생성해야 함
OAuth Client ID: 333977052282-xxxxx.apps.googleusercontent.com
```

---

## Downloads 폴더에서 JSON 찾기

과거에 다운로드한 OAuth 클라이언트 JSON 파일들이 있다면 파일명에 Client ID가 포함되어 있다.

```bash
ls ~/Downloads/client_secret_*.json
# client_secret_333977052282-xxxxx.apps.googleusercontent.com.json
```

파일 이름 앞의 숫자가 현재 Firebase 프로젝트 번호와 일치하는지 확인하면 된다.

---

## 정리

- Google OAuth Client ID의 앞 숫자 = GCP 프로젝트 번호
- Firebase 프로젝트 번호 = 해당 Firebase 앱의 GCP 프로젝트 번호
- 둘이 다르면 해당 OAuth 클라이언트는 다른 프로젝트에서 만들어진 것
- `.env`의 Client ID가 현재 Firebase 프로젝트 번호와 다르다면 새로 생성하는 게 빠르다
