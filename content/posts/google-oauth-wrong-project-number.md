---
title: "Google OAuth 클라이언트 ID의 프로젝트 번호가 Firebase 프로젝트 번호와 다른 경우"
date: 2025-06-15
draft: true
tags: ["Google OAuth", "Firebase", "GCP", "삽질"]
description: ".env에 저장된 Google OAuth Client ID의 프로젝트 번호가 Firebase 프로젝트 번호와 달라서 secret을 찾을 수 없었던 경험 정리"
cover:
  image: "/images/og/google-oauth-wrong-project-number.png"
  alt: "Google Oauth Wrong Project Number"
  hidden: true
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

이 상황에서 대부분의 개발자는 "Client ID는 있는데 왜 Secret을 찾을 수 없지?"라는 의문에 빠진다. 에러 메시지는 보통 다음과 같은 형태로 나타난다.

```
Error 401: invalid_client
The OAuth client was not found.
```

또는 Devise + OmniAuth 조합의 Rails 앱이라면:

```
OmniAuth::Strategies::OAuth2::CallbackError
invalid_client: The OAuth client was not found.
```

Client ID가 존재하는 것처럼 보이기 때문에 처음에는 Secret이 잘못됐거나 `.env` 로딩 문제라고 오해하기 쉽다. 하지만 진짜 문제는 **Client ID 자체가 현재 계정에서 접근할 수 없는 프로젝트에 속해 있다**는 것이다.

---

## GCP 프로젝트 번호란?

Google Cloud에서 프로젝트를 생성하면 세 가지 식별자가 부여된다.

| 식별자 | 예시 | 특징 |
|--------|------|------|
| 프로젝트 ID | `my-app-2025` | 사람이 읽기 쉬운 고유 문자열, 변경 불가 |
| 프로젝트 번호 | `333977052282` | 시스템이 부여하는 고유 숫자, 변경 불가 |
| 프로젝트 이름 | `My App` | 표시용, 변경 가능 |

OAuth 클라이언트를 생성하면 `{프로젝트번호}-{랜덤문자열}.apps.googleusercontent.com` 형태의 Client ID가 발급된다. 즉, Client ID 앞의 숫자만 봐도 **어느 GCP 프로젝트에서 만들어진 OAuth 클라이언트인지** 바로 알 수 있다.

Firebase 프로젝트는 GCP 프로젝트 위에서 동작하는 레이어다. Firebase 콘솔 → 프로젝트 설정에서 보이는 "프로젝트 번호"는 실제로는 그 Firebase 프로젝트가 연결된 **GCP 프로젝트 번호**와 동일하다.

---

## 원인 파악

```bash
# 현재 gcloud 계정에서 접근 가능한 전체 프로젝트 목록 확인
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects" | \
  python3 -c "import sys,json; [print(p['projectNumber'], p['projectId']) for p in json.load(sys.stdin)['projects']]"
```

결과에서 `1091056260493` 번호를 가진 프로젝트가 없음을 확인.

가능한 원인들:
- 과거에 다른 Google 계정으로 생성한 프로젝트
- 프로젝트가 삭제됨
- 다른 용도로 생성했다가 방치된 OAuth 클라이언트

개발을 오래 하다 보면 테스트용 GCP 프로젝트를 여러 개 만들었다 지우는 경우가 많다. 또는 팀 프로젝트에서 다른 팀원의 계정으로 설정한 OAuth 클라이언트를 그대로 `.env`에 복사해서 쓰다가 해당 계정이 팀에서 나가거나, 프로젝트가 삭제된 경우도 흔하다.

---

## 단계별 디버깅 과정

### 1단계: Client ID의 프로젝트 번호 추출

Client ID에서 프로젝트 번호를 추출한다.

```bash
# .env에서 Client ID 확인
grep GOOGLE_CLIENT_ID .env

# 앞의 숫자만 추출
echo "1091056260493-xxxxxxxx.apps.googleusercontent.com" | cut -d'-' -f1
# 출력: 1091056260493
```

### 2단계: Firebase 프로젝트 번호 확인

Firebase 콘솔 → 프로젝트 설정 → 일반 탭에서 "프로젝트 번호"를 확인한다. 또는 CLI로:

```bash
# firebase-tools 설치되어 있다면
firebase projects:list

# 또는 gcloud로
gcloud projects list --format="table(projectNumber, projectId, name)"
```

### 3단계: 두 번호 비교

```bash
CLIENT_PROJECT_NUM=$(grep GOOGLE_CLIENT_ID .env | cut -d'=' -f2 | cut -d'-' -f1)
FIREBASE_PROJECT_NUM="333977052282"  # Firebase 콘솔에서 확인한 번호

if [ "$CLIENT_PROJECT_NUM" = "$FIREBASE_PROJECT_NUM" ]; then
  echo "일치: 같은 프로젝트의 OAuth 클라이언트"
else
  echo "불일치: Client ID=$CLIENT_PROJECT_NUM, Firebase=$FIREBASE_PROJECT_NUM"
  echo "새 OAuth 클라이언트를 생성해야 함"
fi
```

### 4단계: 해당 프로젝트 존재 여부 확인

```bash
# 특정 프로젝트 번호로 프로젝트 조회
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects/1091056260493" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('projectId', 'NOT FOUND'))"
```

프로젝트가 없거나 접근 권한이 없으면 `NOT FOUND` 또는 403 에러가 반환된다.

---

## 해결: 올바른 프로젝트에서 새로 생성

Firebase 프로젝트의 실제 번호(`333977052282`)에 해당하는 GCP 프로젝트에서 새 OAuth 클라이언트를 생성했다.

**Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → OAuth 클라이언트 ID 만들기**

- 애플리케이션 유형: 웹 애플리케이션
- 이름: 임의 설정
- 승인된 리디렉션 URI: 실제 사용하는 콜백 URL 입력

생성 결과:
```
Client ID: 333977052282-xxxxxxxxx.apps.googleusercontent.com
Client Secret: GOCSPX-xxxxxxxxxxxxxxxx
```

앞부분 번호(`333977052282`)가 Firebase 프로젝트 번호와 일치한다.

생성 후 `.env` 업데이트:
```bash
GOOGLE_CLIENT_ID=333977052282-xxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

---

## OAuth 클라이언트와 Firebase 프로젝트의 관계

Firebase 프로젝트는 내부적으로 GCP 프로젝트 위에서 동작한다. Firebase 콘솔에서 보이는 **프로젝트 번호 = GCP 프로젝트 번호**다.

OAuth 클라이언트를 생성할 때 어떤 GCP 프로젝트에서 만드느냐에 따라 Client ID 앞의 번호가 달라진다. Firebase 앱과 연동할 OAuth 클라이언트라면 **같은 Firebase/GCP 프로젝트에서 생성**해야 한다.

```
Firebase 프로젝트: my-app (프로젝트 번호: 333977052282)
                    ↓ 같은 프로젝트에서 생성해야 함
OAuth Client ID: 333977052282-xxxxx.apps.googleusercontent.com
```

왜 이게 중요한가? OAuth 인증 흐름에서 Google 서버는 Client ID를 받으면 해당 프로젝트의 설정을 조회한다. 허용된 리디렉션 URI, 앱 이름, 스코프 등이 모두 그 프로젝트에 저장되어 있다. 프로젝트가 삭제되었거나 접근할 수 없는 프로젝트에 속한 Client ID라면 Google 서버가 `invalid_client` 에러를 반환하는 것이다.

---

## Downloads 폴더에서 JSON 찾기

과거에 다운로드한 OAuth 클라이언트 JSON 파일들이 있다면 파일명에 Client ID가 포함되어 있다.

```bash
ls ~/Downloads/client_secret_*.json
# client_secret_333977052282-xxxxx.apps.googleusercontent.com.json
```

파일 이름 앞의 숫자가 현재 Firebase 프로젝트 번호와 일치하는지 확인하면 된다.

파일 내용에서도 바로 확인할 수 있다:

```bash
cat ~/Downloads/client_secret_*.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
web = data.get('web', {})
print('client_id:', web.get('client_id'))
print('project_id:', web.get('project_id'))
"
```

이 방법으로 올바른 프로젝트의 JSON 파일을 찾으면 새로 생성하지 않고 재사용할 수 있다.

---

## 재발 방지 팁

**1. `.env` 파일에 프로젝트 번호 주석 추가**

```bash
# Firebase 프로젝트: my-app (프로젝트 번호: 333977052282)
GOOGLE_CLIENT_ID=333977052282-xxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

Client ID 앞 번호와 Firebase 프로젝트 번호를 주석으로 명시해두면, 나중에 다시 설정할 때 불일치를 바로 발견할 수 있다.

**2. 프로젝트 네이밍 일관성 유지**

GCP 프로젝트 ID와 Firebase 프로젝트 ID를 동일하게 설정하거나, 관련 프로젝트임을 알 수 있는 접두사를 붙인다. 예: `my-app-prod`, `my-app-staging`.

**3. OAuth 클라이언트 생성 시 올바른 프로젝트에서 시작**

새 OAuth 클라이언트를 만들기 전에 항상 현재 선택된 GCP 프로젝트가 Firebase 프로젝트와 동일한 프로젝트인지 확인한다.

```bash
# 현재 선택된 프로젝트 확인
gcloud config get-value project

# Firebase 프로젝트 ID와 일치하는지 확인
firebase use
```

**4. 오래된 `.env` 파일 정기적으로 감사**

장기 프로젝트에서는 초기에 설정한 `.env` 값들이 그대로 유지되는 경우가 많다. 특히 팀 프로젝트에서 멤버 교체가 있거나 GCP 프로젝트 구조가 변경된 경우에는 OAuth 클라이언트의 유효성을 주기적으로 확인하는 것이 좋다.

---

## Key Takeaways

- **Google OAuth Client ID의 앞 숫자 = GCP 프로젝트 번호**. 이 번호만 봐도 어느 프로젝트에서 만들어진 OAuth 클라이언트인지 즉시 알 수 있다.
- **Firebase 프로젝트 번호 = 해당 Firebase 앱의 GCP 프로젝트 번호**. Firebase와 GCP는 같은 프로젝트를 서로 다른 콘솔로 보는 것이다.
- **두 번호가 다르면 잘못된 프로젝트의 OAuth 클라이언트**를 쓰고 있는 것이다. `invalid_client` 에러의 가장 흔한 원인 중 하나다.
- **Secret을 아무리 찾아봐도 없다면** Client ID 자체가 접근 불가능한 프로젝트에 속해 있을 가능성을 먼저 의심하라.
- **해결책은 단순하다**: 현재 Firebase 프로젝트와 동일한 GCP 프로젝트에서 새 OAuth 클라이언트를 만들고 `.env`를 업데이트하면 된다.
- **Downloads 폴더의 JSON 파일**이 구원투수가 될 수 있다. 과거에 올바른 프로젝트에서 다운로드한 파일이 남아 있다면 재사용 가능하다.
