---
title: "Flutter에서 Gemini, OpenAI, Claude 직접 연동하기 — 멀티 AI 프로바이더 패턴 구현"
date: 2026-03-26
draft: false
tags: ["Flutter", "AI API", "Gemini", "OpenAI", "Claude", "Dart"]
description: "Flutter 앱에서 하드코딩된 AI API 키를 제거하고, Gemini/OpenAI/Claude를 직접 연동하는 멀티 프로바이더 패턴을 구현한 실전 기록. Vision API 요청 포맷 차이, Dio 클라이언트 설계, iOS objective_c.framework IOSSIMULATOR 빌드 에러 해결까지."
---

## 시작 — 하드코딩된 API 키 문제

Flutter 앱에서 AI 기능(영수증 OCR, 이미지 번역, 블로그 자동 생성)을 넣을 때, 처음에는 BizRouter라는 AI 프록시 서비스를 썼다. 모든 요청을 하나의 엔드포인트로 보내면 내부에서 Gemini, GPT, Claude 등으로 라우팅해주는 구조였다.

문제는 API 키가 소스 코드에 하드코딩되어 있다는 것이었다.

```dart
class BizRouterService {
  static const _apiKey = 'sk-br-v1-d6872ae8e164...'; // 이게 코드에 그대로
  static const _baseUrl = 'https://api.bizrouter.ai/v1';
```

지인들에게 배포하는 MVP라 처음에는 괜찮았지만, 사용자가 자기 키를 입력해서 쓸 수 있게 만들어야 했다. Gemini 키가 있는 사람은 Gemini로, OpenAI 키가 있는 사람은 GPT로, Claude 키가 있는 사람은 Claude로 — 각자 가진 키를 쓸 수 있어야 했다.

---

## 프로바이더별 Vision API 요청 포맷 비교

세 프로바이더 모두 이미지를 base64로 보내는 건 같지만, 요청 구조가 전부 다르다. 이게 핵심 삽질 포인트였다.

### Google Gemini

```dart
// POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
// 인증: x-goog-api-key 헤더

{
  "systemInstruction": {"parts": [{"text": "시스템 프롬프트"}]},
  "contents": [{
    "role": "user",
    "parts": [
      {"inline_data": {"mime_type": "image/jpeg", "data": "BASE64"}},
      {"text": "이 영수증을 분석해줘"}
    ]
  }],
  "generationConfig": {
    "temperature": 0.1,
    "maxOutputTokens": 1000
  }
}
```

Gemini는 `inline_data` 안에 `mime_type`과 `data`를 넣는다. 시스템 프롬프트는 `systemInstruction`이라는 별도 필드에 들어간다. 응답은 `candidates[0].content.parts[0].text`에서 꺼낸다.

### OpenAI

```dart
// POST https://api.openai.com/v1/chat/completions
// 인증: Authorization: Bearer {key}

{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "시스템 프롬프트"},
    {"role": "user", "content": [
      {"type": "text", "text": "이 영수증을 분석해줘"},
      {"type": "image_url", "image_url": {
        "url": "data:image/jpeg;base64,BASE64"
      }}
    ]}
  ],
  "temperature": 0.1,
  "max_tokens": 1000
}
```

OpenAI는 `data:image/jpeg;base64,` 프리픽스를 URL에 붙여야 한다. 시스템 프롬프트는 `messages` 배열의 첫 번째 `system` 메시지로 넣는다. 응답은 `choices[0].message.content`.

### Anthropic Claude

```dart
// POST https://api.anthropic.com/v1/messages
// 인증: x-api-key 헤더 + anthropic-version: 2023-06-01

{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1000,
  "system": "시스템 프롬프트",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image", "source": {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "BASE64"
      }},
      {"type": "text", "text": "이 영수증을 분석해줘"}
    ]
  }],
  "temperature": 0.1
}
```

Claude는 `system` 필드가 `messages` 밖에 따로 있다. 이미지는 `source` 안에 `type`, `media_type`, `data` 세 필드가 필요하다. 응답은 `content[0].text`.

### 비교 표

| 항목 | Gemini | OpenAI | Claude |
|------|--------|--------|--------|
| **엔드포인트** | `/models/{model}:generateContent` | `/chat/completions` | `/messages` |
| **인증 헤더** | `x-goog-api-key` | `Authorization: Bearer` | `x-api-key` + `anthropic-version` |
| **이미지 전달** | `inline_data.data` | `image_url.url` (data URI) | `source.data` |
| **시스템 프롬프트** | `systemInstruction` 필드 | messages의 system role | `system` 필드 |
| **응답 경로** | `candidates[0].content.parts[0].text` | `choices[0].message.content` | `content[0].text` |
| **추가 헤더** | 없음 | 없음 | `anthropic-version` 필수 |

---

## 멀티 프로바이더 서비스 설계

### 핵심 아이디어: 지연 초기화 + 포맷 분기

프로바이더를 enum으로 정의하고, Dio 인스턴스를 프로바이더에 맞게 생성한다. 핵심은 **공개 API는 동일하게 유지**하면서, 내부에서 프로바이더별로 요청/응답 포맷을 분기하는 것이다.

```dart
enum AiProvider { gemini, openai, claude, bizrouter }

class AiService {
  AiProvider? _provider;
  String? _apiKey;
  Dio? _dio;

  // 매 호출마다 설정을 확인해서 변경사항 반영
  Future<_Resolved> _resolve() async {
    final provider = await AiProviderConfig.getProvider();
    final apiKey = await AiProviderConfig.getApiKey(provider);

    if (apiKey == null || apiKey.isEmpty) {
      throw AiKeyNotConfiguredException(provider);
    }

    // 설정 변경 없으면 캐시된 Dio 재사용
    if (_dio != null && _provider == provider && _apiKey == apiKey) {
      return _Resolved(dio: _dio!, provider: provider);
    }

    _provider = provider;
    _apiKey = apiKey;
    _dio = _createDio(provider, apiKey);
    return _Resolved(dio: _dio!, provider: provider);
  }
}
```

이 구조의 장점은 사용자가 설정 화면에서 프로바이더를 변경하면, **다음 API 호출부터 자동으로 새 설정이 적용**된다는 점이다. Dio 인스턴스를 매번 새로 만들지 않고, 설정이 바뀔 때만 재생성한다.

### Dio 인스턴스 생성

각 프로바이더마다 base URL과 인증 헤더가 다르다.

```dart
static Dio _createDio(AiProvider provider, String apiKey) {
  const timeout = Duration(seconds: 30);
  const recv = Duration(seconds: 60);

  switch (provider) {
    case AiProvider.gemini:
      return Dio(BaseOptions(
        baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
        headers: {'x-goog-api-key': apiKey, 'Content-Type': 'application/json'},
        connectTimeout: timeout, receiveTimeout: recv,
      ));
    case AiProvider.openai:
      return Dio(BaseOptions(
        baseUrl: 'https://api.openai.com/v1',
        headers: {'Authorization': 'Bearer $apiKey', 'Content-Type': 'application/json'},
        connectTimeout: timeout, receiveTimeout: recv,
      ));
    case AiProvider.claude:
      return Dio(BaseOptions(
        baseUrl: 'https://api.anthropic.com/v1',
        headers: {
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'Content-Type': 'application/json'
        },
        connectTimeout: timeout, receiveTimeout: recv,
      ));
  }
}
```

### 요청 포맷 분기

공개 메서드에서 `_sendVision`을 호출하면, 내부에서 프로바이더별 private 메서드로 분기한다.

```dart
Future<String> _sendVision({
  required _Resolved cfg,
  required String model,
  required String systemPrompt,
  required String userPrompt,
  required String base64Image,
  required double temperature,
  required int maxTokens,
}) async {
  switch (cfg.provider) {
    case AiProvider.gemini:
      return _geminiVision(cfg.dio, model, systemPrompt, userPrompt, base64Image, temperature, maxTokens);
    case AiProvider.claude:
      return _claudeVision(cfg.dio, model, systemPrompt, userPrompt, base64Image, temperature, maxTokens);
    case AiProvider.openai:
      return _openaiVision(cfg.dio, model, systemPrompt, userPrompt, base64Image, temperature, maxTokens);
  }
}
```

각 프로바이더의 Vision 요청은 앞서 정리한 포맷 그대로 구현한다.

```dart
// Gemini: inline_data 방식
Future<String> _geminiVision(Dio dio, String model, ...) async {
  final response = await dio.post('/models/$model:generateContent', data: {
    'systemInstruction': {'parts': [{'text': sys}]},
    'contents': [{'role': 'user', 'parts': [
      {'inline_data': {'mime_type': 'image/jpeg', 'data': base64}},
      {'text': user},
    ]}],
    'generationConfig': {'temperature': temp, 'maxOutputTokens': maxTokens},
  });
  return response.data['candidates'][0]['content']['parts'][0]['text'];
}

// Claude: source.type 방식
Future<String> _claudeVision(Dio dio, String model, ...) async {
  final response = await dio.post('/messages', data: {
    'model': model, 'max_tokens': maxTokens, 'system': sys,
    'messages': [{'role': 'user', 'content': [
      {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64}},
      {'type': 'text', 'text': user},
    ]}],
    'temperature': temp,
  });
  return response.data['content'][0]['text'];
}

// OpenAI: data URI 방식
Future<String> _openaiVision(Dio dio, String model, ...) async {
  final response = await dio.post('/chat/completions', data: {
    'model': model,
    'messages': [
      {'role': 'system', 'content': sys},
      {'role': 'user', 'content': [
        {'type': 'text', 'text': user},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,$base64'}},
      ]},
    ],
    'temperature': temp, 'max_tokens': maxTokens,
  });
  return response.data['choices'][0]['message']['content'];
}
```

---

## API 키 검증 기능

사용자가 키를 입력한 후 "연결 확인" 버튼을 누르면, 가벼운 요청으로 키 유효성을 검증한다.

```dart
static Future<String?> verifyApiKey(AiProvider provider, String apiKey) async {
  if (apiKey.trim().isEmpty) return 'API 키를 입력해주세요.';

  final dio = _createDio(provider, apiKey.trim());
  try {
    switch (provider) {
      case AiProvider.gemini:
        await dio.get('/models');  // 모델 목록 조회 (가벼운 GET)
      case AiProvider.openai:
        await dio.get('/models');
      case AiProvider.claude:
        await dio.post('/messages', data: {
          'model': 'claude-haiku-4-5-20251001',
          'max_tokens': 1,
          'messages': [{'role': 'user', 'content': 'hi'}],
        });
    }
    return null; // 성공
  } on DioException catch (e) {
    final status = e.response?.statusCode;
    if (status == 401 || status == 403) return 'API 키가 유효하지 않습니다.';
    if (status == 429) return '요청 한도 초과. 잠시 후 다시 시도하세요.';
    return '연결 실패: ${e.message}';
  }
}
```

Gemini와 OpenAI는 `GET /models`로 모델 목록만 조회한다. 토큰 소비가 없는 가벼운 요청이다. Claude는 모델 목록 API가 없어서 최소 토큰(1) 메시지를 보낸다. 비용은 거의 0에 가깝다.

---

## 프로바이더별 모델 목록 관리

각 프로바이더마다 사용 가능한 모델이 다르다. 설정 화면에서 프로바이더를 바꾸면 모델 목록도 자동으로 바뀌어야 한다.

```dart
static const Map<AiProvider, List<ModelDef>> visionModels = {
  AiProvider.gemini: [
    ModelDef(id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', price: '\$0.30/1M'),
    ModelDef(id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', price: '\$1.25/1M'),
  ],
  AiProvider.openai: [
    ModelDef(id: 'gpt-4o-mini', label: 'GPT-4o Mini', price: '\$0.15/1M'),
    ModelDef(id: 'gpt-4o', label: 'GPT-4o', price: '\$2.50/1M'),
  ],
  AiProvider.claude: [
    ModelDef(id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', price: '\$1.00/1M'),
    ModelDef(id: 'claude-sonnet-4-6', label: 'Sonnet 4.6', price: '\$3.00/1M'),
  ],
};
```

모델 선택은 프로바이더별로 SharedPreferences에 인덱스로 저장한다. 프로바이더를 바꿔도 이전 선택이 유지된다.

---

## 가격 비교 — 어떤 프로바이더를 선택할까

2026년 3월 기준, Vision API 가격(1M 입력 토큰 기준):

| 모델 | 프로바이더 | 입력 가격 | 출력 가격 | 추천 용도 |
|------|-----------|----------|----------|----------|
| Gemini 2.5 Flash Lite | Google | $0.10 | $0.40 | 대량 처리, 비용 최적화 |
| GPT-4o Mini | OpenAI | $0.15 | $0.60 | 가성비 영어 처리 |
| Gemini 2.5 Flash | Google | $0.30 | $2.50 | 범용 추천 |
| Claude Haiku 4.5 | Anthropic | $1.00 | $5.00 | 한국어 이해력 |
| GPT-4o | OpenAI | $2.50 | $10.00 | 고정밀 OCR |
| Claude Sonnet 4.6 | Anthropic | $3.00 | $15.00 | 감성적 글쓰기 |

영수증 OCR처럼 구조화된 출력이 필요한 경우 Gemini 2.5 Flash가 가성비 최고다. 블로그 같은 창작 글쓰기에는 Claude Sonnet이 한국어 품질이 좋다.

---

## iOS 빌드 에러 — objective_c.framework IOSSIMULATOR

멀티 프로바이더 구현을 끝내고 TestFlight에 올리려는데, App Store Connect에서 거부당했다.

```
Validation failed (409) Invalid executable.
The "Runner.app/Frameworks/objective_c.framework/objective_c"
executable references an unsupported platform in the arm64 slice.
Simulator platforms aren't permitted.
```

`objective_c` 패키지(Flutter FFI 관련)의 프레임워크 바이너리에 시뮬레이터 플랫폼 메타데이터가 포함되어 있었다.

### 첫 번째 시도 — lipo로 x86_64 제거 (실패)

```bash
lipo -remove x86_64 "$binary" -output "$binary"
```

x86_64 아키텍처는 제거됐지만, **arm64 slice 자체에 IOSSIMULATOR 플랫폼 태그**가 붙어있어서 여전히 거부당했다.

### 두 번째 시도 — vtool로 플랫폼 태그 수정 (성공)

```bash
$ vtool -show Runner.app/Frameworks/objective_c.framework/objective_c
Load command 9
      cmd LC_BUILD_VERSION
 platform IOSSIMULATOR    # <-- 이게 문제
    minos 14.0
      sdk 26.2
```

`vtool`로 플랫폼을 `IOS`로 변경했다.

```bash
vtool -set-build-version ios 14.0 26.2 -replace \
  -output "$binary" "$binary"
```

수정 후 확인:

```bash
$ vtool -show objective_c
 platform IOS    # 정상
```

re-export 후 업로드하니 성공했다.

```
UPLOAD SUCCEEDED with no errors
Delivery UUID: 78d518f6-c276-4b53-8016-37b86c94031f
Transferred 32290189 bytes in 1.520 seconds (21.2MB/s)
```

### Makefile에 영구 반영

매번 수동으로 하면 까먹으니까 Makefile의 archive → export 사이에 자동 strip + vtool fix 단계를 넣었다.

```makefile
build-ipa: bump-build
	flutter build ios --release --no-codesign
	# Xcode Archive
	xcodebuild -workspace $(WORKSPACE) -scheme Runner ...
	# Archive에서 시뮬레이터 아키텍처/플랫폼 자동 수정
	@find $(ARCHIVE_PATH)/Products -name "*.framework" -type d | while read fw; do \
		binary="$$fw/$$(basename $$fw .framework)"; \
		if [ -f "$$binary" ]; then \
			if lipo -info "$$binary" 2>/dev/null | grep -q x86_64; then \
				lipo -remove x86_64 "$$binary" -output "$$binary" 2>/dev/null || true; \
			fi; \
			if vtool -show "$$binary" 2>/dev/null | grep -q "IOSSIMULATOR"; then \
				vtool -set-build-version ios 14.0 26.2 -replace \
				  -output "$$binary" "$$binary" 2>/dev/null || true; \
			fi; \
		fi; \
	done
	# IPA Export
	xcodebuild -exportArchive ...
```

이렇게 하면 `make testflight` 한 번으로 빌드부터 업로드까지 자동 처리된다.

---

## 테스트 — 기존 테스트 깨지지 않게

서비스 클래스를 교체할 때 가장 중요한 건 기존 테스트가 깨지지 않는 것이다. `forTesting` 생성자를 유지해서 MockDio 주입이 가능하게 했다.

```dart
class AiService {
  // 프로덕션 생성자
  AiService() : _isTest = false, _testOcrModel = null, _testBlogModel = null;

  // 테스트 생성자 — MockDio 주입, OpenAI 포맷으로 응답 파싱
  AiService.forTesting(Dio dio, {String? ocrModel, String? blogModel})
      : _isTest = true, _testOcrModel = ocrModel, _testBlogModel = blogModel {
    _provider = AiProvider.bizrouter; // OpenAI-compatible 포맷
    _dio = dio;
  }
}
```

테스트 코드에서는 import와 클래스명만 바꾸면 된다.

```dart
// Before
import 'bizrouter_service.dart';
final service = BizRouterService.forTesting(mockDio, ocrModel: 'test');

// After
import 'ai_service.dart';
final service = AiService.forTesting(mockDio, ocrModel: 'test');
```

실제로 32개 테스트가 수정 없이 전부 통과했다.

---

## 설정 UI — 프로바이더 칩 + 키 입력 + 검증

설정 화면 구성은 간단하다.

1. **프로바이더 선택 칩**: Gemini / OpenAI / Claude / BizRouter 중 선택. 키가 입력된 프로바이더에는 체크 아이콘 표시.
2. **API 키 입력**: 마스킹된 입력 필드 + 저장 버튼. 프로바이더별로 키 힌트 다르게 표시(`AIza...`, `sk-...`, `sk-ant-...`).
3. **연결 확인**: 저장 후 "연결 확인" 클릭하면 로딩 → 녹색 체크(성공) / 빨간 X(실패).
4. **모델 선택**: 현재 프로바이더에서 사용 가능한 모델만 표시. OCR용 / 블로그용 각각 선택.

프로바이더를 바꿀 때마다 모델 목록이 자동으로 갱신되고, 각 프로바이더별 모델 선택은 독립적으로 저장된다.

---

## 주의사항과 알려진 함정

### API 키 보안

SharedPreferences는 iOS Keychain/Android Keystore가 아니다. 지인 배포 MVP라서 쓴 거지, 프로덕션에서는 `flutter_secure_storage`를 써야 한다. 루팅된 기기에서 SharedPreferences는 평문 노출 가능하다.

### Claude의 모델 목록 API 부재

Gemini와 OpenAI는 `GET /models`로 키 유효성을 토큰 소비 없이 확인할 수 있다. Claude는 이 API가 없어서 최소 토큰 메시지를 보내야 한다. 비용은 무시할 수준이지만 구조적으로 아쉬운 부분이다.

### objective_c.framework 문제의 근본 원인

이 문제는 Flutter의 `objective_c` 패키지(9.3.0)가 시뮬레이터 바이너리를 릴리스 빌드에 포함시키는 버그다. 패키지 업데이트로 해결될 수 있지만, 그 전까지는 vtool 워크어라운드가 필요하다. Xcode 15.1 이상에서 vtool을 사용할 수 있다.

### BizRouter 같은 프록시 서비스의 장단점

BizRouter처럼 OpenAI-compatible API를 제공하는 프록시 서비스는 편리하지만, 단일 장애 지점(SPOF)이 된다. 직접 연동하면 프로바이더 하나가 다운되어도 다른 걸로 전환할 수 있다. 대신 각 프로바이더의 요청 포맷을 직접 관리해야 하는 부담이 있다.

---

## 결론

Flutter 앱에서 멀티 AI 프로바이더 패턴을 구현하면, 사용자가 자기 키로 원하는 서비스를 쓸 수 있게 된다. 핵심은 세 가지:

1. **Dio 인스턴스를 프로바이더별로 생성** — base URL, 인증 헤더가 전부 다르다.
2. **요청/응답 포맷을 switch로 분기** — 공개 API는 동일하게, 내부만 프로바이더별로 처리.
3. **iOS 빌드 시 vtool로 플랫폼 태그 수정** — `objective_c.framework` IOSSIMULATOR 문제 해결.

전체 변경 파일은 10개 미만이었고, 기존 32개 테스트가 그대로 통과했다. 멀티 프로바이더 전환은 생각보다 큰 작업이 아니었다.
