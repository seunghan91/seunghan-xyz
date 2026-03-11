---
title: "App Store 스크린샷 리젝 2.3.3 해결기 — AI 생성 이미지에서 실제 앱 캡처로"
date: 2026-03-11
draft: false
tags: ["iOS", "App Store", "Flutter", "스크린샷", "앱심사", "Python", "PIL"]
description: "App Store 심사에서 Guideline 2.3.3 (Accurate Metadata)으로 리젝된 경험. AI 생성 마케팅 이미지 대신 시뮬레이터 실제 캡처 + Python PIL로 App Store 스타일 스크린샷을 만들어 해결한 과정."
---

App Store에 첫 앱을 제출했는데, 스크린샷 문제로 리젝당했다. 해결까지의 삽질 기록.

---

## 리젝 사유

**Guideline 2.3.3 - Performance: Accurate Metadata**

> The screenshots do not show the actual app in use in the majority of the screenshots.

심사 디바이스: iPad Air 11-inch (M3)

### 원인

Gemini Image Generation API로 Neo-Brutalism 스타일의 **가짜 UI 마케팅 이미지**를 만들어서 스크린샷으로 제출했다. 앱 화면과 전혀 다른 디자인이었으니 당연한 결과.

Apple이 요구하는 건:
- **대다수(majority)** 스크린샷이 **실제 앱 사용 화면**이어야 함
- 마케팅/프로모션 자료만으로는 부적절
- 스플래시/로그인 화면만으로도 부족

다만, **실제 앱 화면 + 텍스트 오버레이** 조합은 허용된다. 대부분의 앱이 이 방식을 쓴다.

---

## 해결 전략

1. iOS 시뮬레이터에서 **실제 앱 화면 5장** 캡처
2. Python PIL로 **헤드라인 + 폰 프레임** 조합한 App Store 스타일 이미지 생성
3. App Store 요구 해상도에 맞게 출력

---

## Step 1: 시뮬레이터에서 실제 앱 캡처

### 더미 데이터 준비

빈 앱을 캡처하면 의미가 없다. 자연스러운 더미 데이터를 코드로 삽입했다.

```dart
// main.dart에서 앱 시작 전 seed 실행
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await seedDemoData(StorageService()); // 임시 — 캡처 후 제거
  runApp(const ProviderScope(child: MyApp()));
}
```

seed 함수에서 기업 4~6개, 각 기업당 자소서 질문 1~3개, 실제 같은 한국어 내용을 넣었다.

### 화면별 캡처

Flutter 앱에서 GoRouter의 `StatefulShellRoute`를 사용하고 있었는데, 시뮬레이터 터치 이벤트(`xcrun simctl io`)가 지원되지 않아서 화면 이동이 어려웠다.

**해결법**: `initialLocation`을 바꿔가며 빌드 → 캡처 → 반복.

```yaml
# 각 탭 화면 캡처
initialLocation: '/jasoseo'   → 메인 리스트
initialLocation: '/calendar'  → 캘린더
initialLocation: '/questions' → 문항별
initialLocation: '/settings'  → 설정
```

질문 편집 화면처럼 path parameter가 필요한 화면은 **임시 독립 라우트**를 추가했다.

```dart
GoRoute(
  path: '/screenshot-edit/:companyId/:questionId',
  builder: (context, state) => QuestionEditScreen(
    companyId: state.pathParameters['companyId']!,
    questionId: state.pathParameters['questionId']!,
  ),
),
```

캡처 명령:

```bash
xcrun simctl io booted screenshot ~/screenshots/raw/01_list.png
```

### 삽질 포인트: 검정 배경

`Scaffold(backgroundColor: Colors.transparent)`를 쓰는 화면을 AppShell 밖에서 독립 라우트로 열면, 뒤에 아무것도 없어서 **검정 배경**이 나온다.

해결: 임시 래퍼 위젯으로 AppShell과 같은 그라디언트 배경을 넣었다.

```dart
class _ScreenshotBgWrapper extends StatelessWidget {
  const _ScreenshotBgWrapper({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    // AppShell과 동일한 그라디언트 배경 재현
    return Stack(
      children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [/* seed color 기반 그라디언트 */],
              ),
            ),
          ),
        ),
        Positioned.fill(child: child),
      ],
    );
  }
}
```

### 삽질 포인트: 키보드

텍스트 편집 화면에서 `autofocus: true`가 설정되어 있으면 시뮬레이터 실행 즉시 키보드가 올라온다. 키보드가 올라온 상태의 캡처도 나쁘진 않지만, 상단 영역이 잘려서 보기 좋지 않았다.

추가로 **배경 탭으로 키보드 dismiss** 기능이 없어서 이것도 함께 수정:

```dart
return GestureDetector(
  onTap: () => FocusScope.of(context).unfocus(),
  child: Scaffold(
    // ...
  ),
);
```

---

## Step 2: Python PIL로 App Store 스타일 이미지 생성

캡처한 실제 화면을 폰 프레임 안에 넣고, 상단에 헤드라인 텍스트를 배치하는 스크립트를 만들었다.

### 구조

```
[크림 그라디언트 배경]
├── 헤드라인 텍스트 (Bold 한국어)
├── 서브타이틀 텍스트
├── 악센트 라인
└── [둥근 모서리 폰 프레임]
    └── 실제 앱 스크린샷
```

### 핵심 코드

```python
from PIL import Image, ImageDraw, ImageFont

SIZES = {
    "6.5inch": (1284, 2778),  # iPhone 15 Pro Max 등
    "6.9inch": (1320, 2868),  # iPhone 16 Pro Max
}

SCREENSHOTS = [
    {"id": "01_hero", "raw": "01_list.png",
     "headline": "내 자소서,\n내 폰에만",
     "subtitle": "완전 오프라인 · 서버 없음"},
    # ... 5장
]
```

### 삽질 포인트: 비율 깨짐

폰 프레임 영역의 **최대 높이**를 제한했는데, 높이가 잘릴 때 **너비는 그대로** 유지해서 이미지가 가로로 늘어나는 버그가 있었다.

```python
# ❌ 잘못된 코드
phone_w = max_phone_w
phone_h = min(phone_max_h, int(phone_w * raw_h / raw_w))
# phone_h가 max로 잘려도 phone_w는 그대로 → 비율 깨짐

# ✅ 수정
if phone_h_by_w <= phone_max_h:
    phone_w = max_phone_w
    phone_h = phone_h_by_w
else:
    phone_h = phone_max_h
    phone_w = int(phone_h * raw_w / raw_h)  # 비율 유지
    phone_margin = (target_w - phone_w) // 2  # 중앙 정렬
```

### 삽질 포인트: 6.5" 해상도

처음에 6.5" 사이즈를 1290×2796으로 설정했는데, App Store Connect에서 거부당했다.

```
6.5" 허용 해상도: 1242×2688 또는 1284×2778
6.9" 허용 해상도: 1320×2868
```

1290×2796은 어디에도 해당하지 않는 사이즈였다.

---

## Step 3: 빌드 & 업로드

```bash
make testflight  # bump build + flutter build ipa + xcrun altool upload
```

Makefile에 빌드 번호 자동 증가 + IPA 빌드 + TestFlight 업로드를 자동화해둔 덕분에 한 줄로 끝.

---

## 최종 결과물

| # | 헤드라인 | 실제 앱 화면 |
|---|--------|-----------|
| 01 | 내 자소서, 내 폰에만 | 메인 자소서 리스트 |
| 02 | 언제 어디서나 바로 작성 | 질문 편집 화면 |
| 03 | 같은 질문, 회사별 비교 | 문항별 화면 |
| 04 | 마감일을 한눈에 | 캘린더 화면 |
| 05 | 백업도 내 손안에 | 설정 화면 |

각 스크린샷에 **실제 시뮬레이터 캡처 화면**이 들어있으므로 Guideline 2.3.3을 만족한다.

---

## 교훈

1. **AI 생성 이미지는 스크린샷으로 쓸 수 없다** — "실제 앱 사용 화면"이 필수
2. **텍스트 오버레이 + 실제 캡처 조합은 OK** — 대부분의 앱이 이 방식
3. **시뮬레이터 캡처 시 더미 데이터 필수** — 빈 앱은 의미 없음
4. **App Store 해상도를 정확히 확인** — 1px이라도 틀리면 업로드 거부
5. **`backgroundColor: Colors.transparent`** 사용 시 독립 라우트에서 검정 배경 주의
6. **PIL로 충분하다** — AI 이미지 생성 없이도 깔끔한 App Store 스크린샷 제작 가능
