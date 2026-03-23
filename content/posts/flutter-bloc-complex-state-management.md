---
title: "Flutter BLoC 상태 설계 — 단순 목록을 넘어 복잡한 단계 흐름 다루기"
date: 2025-07-06
draft: false
tags: ["Flutter", "BLoC", "상태관리", "UX"]
description: "BLoC로 목록 하나 띄우는 건 쉽다. 문제는 '세션 생성 → 질문 추가 → 답변 → 완료' 같은 단계형 흐름을 어떻게 이벤트·상태로 나눠야 유지보수가 되는지다. 설계 방법을 정리했다."
cover:
  image: "/images/og/flutter-bloc-complex-state-management.png"
  alt: "Flutter Bloc Complex State Management"
  hidden: true
---

목록을 불러오고 보여주는 수준의 BLoC는 어렵지 않다.
문제는 세션 기반의 흐름, 예를 들어 "세션을 만들고 → 질문을 추가하고 → 답변을 받고 → 완료" 같은 단계적 워크플로우를 BLoC 하나로 관리할 때다.

이런 패턴은 리뷰 Q&A 시스템, 멀티스텝 설문, 온보딩 플로우 등 실무에서 자주 등장한다. 단순히 `isLoading` 불리언 하나로 버티다가 UX가 무너지는 경험을 해봤다면, 이 글이 도움이 될 것이다.

---

## 왜 BLoC가 복잡한 흐름에 적합한가

BLoC(Business Logic Component)의 핵심 가치는 UI와 비즈니스 로직의 완전한 분리다. 단순한 데이터 페칭에서는 이 장점이 와닿지 않는다. 하지만 상태가 여러 단계로 전이되고, 같은 화면에서 독립적인 로딩 피드백이 필요해질 때 BLoC의 구조적 이점이 드러난다.

특히 `flutter_bloc` 패키지의 현재 API(`on<Event>` 핸들러 방식)는 각 이벤트 타입에 대한 처리 로직을 명확하게 분리하기 때문에, 핸들러가 10개가 넘어도 코드가 스파게티가 되지 않는다.

---

## 상태를 먼저 그려라

BLoC를 코딩하기 전에 상태부터 정의하는 게 순서다.
이 워크플로우에서 UI가 보여줘야 하는 상태를 나열하면:

- 초기 (아무것도 없음)
- 세션 목록 로딩 중
- 세션 목록 표시
- 새 세션 생성 중
- 세션 상세 로딩 중
- 세션 상세 표시 (질문 목록 포함)
- 질문 추가 중
- 답변 입력 중
- 오류

이 목록을 먼저 적어두는 것 자체가 설계다. 이 목록에서 빠진 상태가 있으면 나중에 반드시 예외 케이스로 돌아온다.

```dart
abstract class ReviewQaState {}

class ReviewQaInitial extends ReviewQaState {}
class ReviewQaLoading extends ReviewQaState {}

class ReviewQaSessionListLoaded extends ReviewQaState {
  final List<QaSession> sessions;
  ReviewQaSessionListLoaded(this.sessions);
}

class ReviewQaSessionLoaded extends ReviewQaState {
  final QaSession session;
  final List<ReviewQuestion> questions;
  ReviewQaSessionLoaded({required this.session, required this.questions});
}

class ReviewQaQuestionAdded extends ReviewQaState {
  final ReviewQuestion question;
  ReviewQaQuestionAdded(this.question);
}

class ReviewQaError extends ReviewQaState {
  final String message;
  ReviewQaError(this.message);
}
```

상태 클래스를 이렇게 구체적으로 나눠야 UI에서 `if (state is ReviewQaSessionLoaded)` 처럼 명확하게 분기할 수 있다. 상태를 하나의 클래스에 불리언과 열거형으로 때워버리면, UI 레이어에서 조건 조합이 폭발적으로 늘어난다.

### Sealed Class 패턴 (Dart 3+)

Dart 3부터는 `sealed class`를 사용하면 컴파일러가 모든 하위 타입을 강제 처리하도록 요구한다. `switch` 표현식과 결합하면 빠진 케이스를 빌드 타임에 잡아낼 수 있다.

```dart
sealed class ReviewQaState {}

final class ReviewQaInitial extends ReviewQaState {}
final class ReviewQaLoading extends ReviewQaState {}
final class ReviewQaSessionListLoaded extends ReviewQaState {
  final List<QaSession> sessions;
  const ReviewQaSessionListLoaded(this.sessions);
}
final class ReviewQaSessionLoaded extends ReviewQaState {
  final QaSession session;
  final List<ReviewQuestion> questions;
  final bool isAddingQuestion;
  const ReviewQaSessionLoaded({
    required this.session,
    required this.questions,
    this.isAddingQuestion = false,
  });
}
final class ReviewQaError extends ReviewQaState {
  final String message;
  const ReviewQaError(this.message);
}
```

`sealed`를 쓰면 UI에서 `switch (state)` 시 `_` 와일드카드 없이도 컴파일러가 모든 케이스를 요구한다. 신규 상태를 추가했을 때 관련 UI 코드를 빠뜨리는 실수를 방지할 수 있다.

---

## 이벤트 설계

상태에 대응하는 이벤트를 만든다. 이벤트는 "사용자 또는 시스템이 무언가를 했다"는 의미이므로 과거형 또는 명령형 동사로 이름을 짓는 게 관례다.

```dart
abstract class ReviewQaEvent {}

class LoadQaSessions extends ReviewQaEvent {
  final int listingId;
  LoadQaSessions(this.listingId);
}

class CreateQaSession extends ReviewQaEvent {
  final int listingId;
  final String title;
  CreateQaSession({required this.listingId, required this.title});
}

class LoadQaSessionDetail extends ReviewQaEvent {
  final int sessionId;
  LoadQaSessionDetail(this.sessionId);
}

class AddQuestion extends ReviewQaEvent {
  final int sessionId;
  final String content;
  AddQuestion({required this.sessionId, required this.content});
}

class SubmitAnswer extends ReviewQaEvent {
  final int questionId;
  final String answer;
  SubmitAnswer({required this.questionId, required this.answer});
}
```

이벤트 클래스에도 `Equatable`을 적용하면 같은 이벤트가 중복 발행됐을 때 BLoC가 처리를 건너뛸 수 있다. 특히 `transformEvents`에서 `distinct()`를 걸 때 유용하다.

---

## BLoC 구현 - 이벤트 핸들러

각 이벤트를 처리하는 핸들러다. `flutter_bloc 8+`에서는 `mapEventToState`가 deprecated되고 `on<Event>` 방식을 사용한다.

```dart
class ReviewQaBloc extends Bloc<ReviewQaEvent, ReviewQaState> {
  final ReviewQaRepository _repository;

  ReviewQaBloc({required ReviewQaRepository repository})
      : _repository = repository,
        super(ReviewQaInitial()) {
    on<LoadQaSessions>(_onLoadSessions);
    on<CreateQaSession>(_onCreateSession);
    on<LoadQaSessionDetail>(_onLoadDetail);
    on<AddQuestion>(_onAddQuestion);
    on<SubmitAnswer>(_onSubmitAnswer);
  }

  Future<void> _onLoadSessions(
    LoadQaSessions event,
    Emitter<ReviewQaState> emit,
  ) async {
    emit(ReviewQaLoading());
    try {
      final sessions = await _repository.getSessions(event.listingId);
      emit(ReviewQaSessionListLoaded(sessions));
    } catch (e) {
      emit(ReviewQaError(e.toString()));
    }
  }

  Future<void> _onAddQuestion(
    AddQuestion event,
    Emitter<ReviewQaState> emit,
  ) async {
    // 로딩 상태로 전환하지 않고 현재 상태를 유지하면서 처리
    // 질문 추가 중에도 기존 목록을 보여줘야 하기 때문
    final currentState = state;
    try {
      final newQuestion = await _repository.addQuestion(
        sessionId: event.sessionId,
        content: event.content,
      );
      emit(ReviewQaQuestionAdded(newQuestion));

      // 추가 후 상세 다시 로드
      if (currentState is ReviewQaSessionLoaded) {
        add(LoadQaSessionDetail(currentState.session.id));
      }
    } catch (e) {
      emit(ReviewQaError(e.toString()));
    }
  }
}
```

### 이벤트 변환(transformer) 활용

`on<Event>` 등록 시 두 번째 인자로 `EventTransformer`를 넘길 수 있다. 검색 입력처럼 빠르게 연속 발행되는 이벤트에는 `debounce`를, 중복 실행을 막으려면 `droppable()`을 사용한다.

```dart
import 'package:bloc_concurrency/bloc_concurrency.dart';

on<AddQuestion>(
  _onAddQuestion,
  transformer: droppable(), // 진행 중인 요청이 있으면 새 이벤트 무시
);
```

`bloc_concurrency` 패키지가 제공하는 `sequential()`, `concurrent()`, `droppable()`, `restartable()` 네 가지 트랜스포머를 상황에 맞게 선택하면 된다.

---

## 주의: 로딩 상태를 남발하지 말 것

모든 이벤트에서 `emit(ReviewQaLoading())`을 하면 안 된다.

질문을 추가하는 동안 목록 전체가 사라지고 스피너가 뜨는 경험은 최악이다.
`ReviewQaLoading`은 "화면 전체를 대체해도 되는 초기 로딩"에만 써야 한다.

세부 액션(질문 추가, 답변 제출)에는 별도의 로컬 상태나 `isSubmitting` 플래그를 BLoC 상태에 포함시키는 게 낫다.

```dart
class ReviewQaSessionLoaded extends ReviewQaState {
  final QaSession session;
  final List<ReviewQuestion> questions;
  final bool isAddingQuestion;  // 질문 추가 중 여부

  ReviewQaSessionLoaded({
    required this.session,
    required this.questions,
    this.isAddingQuestion = false,
  });

  ReviewQaSessionLoaded copyWith({
    QaSession? session,
    List<ReviewQuestion>? questions,
    bool? isAddingQuestion,
  }) {
    return ReviewQaSessionLoaded(
      session: session ?? this.session,
      questions: questions ?? this.questions,
      isAddingQuestion: isAddingQuestion ?? this.isAddingQuestion,
    );
  }
}
```

```dart
Future<void> _onAddQuestion(...) async {
  if (state is ReviewQaSessionLoaded) {
    final current = state as ReviewQaSessionLoaded;
    emit(current.copyWith(isAddingQuestion: true));  // 목록은 유지, 플래그만 변경

    try {
      final newQuestion = await _repository.addQuestion(...);
      final updatedQuestions = [...current.questions, newQuestion];
      emit(current.copyWith(
        questions: updatedQuestions,
        isAddingQuestion: false,
      ));
    } catch (e) {
      emit(current.copyWith(isAddingQuestion: false));
      // 에러 처리
    }
  }
}
```

`copyWith` 패턴은 불변 상태(immutable state)를 유지하면서 일부 필드만 변경된 새 인스턴스를 반환한다. `flutter_bloc`이 `==` 비교로 상태 변화를 감지하므로, 상태 클래스에 `Equatable`을 적용하거나 `copyWith`로 실제로 다른 인스턴스를 반환해야 리빌드가 트리거된다.

---

## UI에서 분기

```dart
BlocBuilder<ReviewQaBloc, ReviewQaState>(
  builder: (context, state) {
    if (state is ReviewQaLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state is ReviewQaSessionLoaded) {
      return Column(
        children: [
          ListView.builder(
            itemCount: state.questions.length,
            itemBuilder: (_, i) => QuestionCard(state.questions[i]),
          ),
          if (state.isAddingQuestion)
            const LinearProgressIndicator()  // 전체 스피너 대신 얇은 진행바
          else
            AddQuestionButton(
              onPressed: () => context.read<ReviewQaBloc>().add(
                AddQuestion(sessionId: state.session.id, content: _controller.text),
              ),
            ),
        ],
      );
    }

    if (state is ReviewQaError) {
      return ErrorView(message: state.message);
    }

    return const SizedBox.shrink();
  },
)
```

### BlocListener vs BlocBuilder vs BlocConsumer

- `BlocBuilder`: 상태에 따라 위젯을 다시 빌드할 때 사용
- `BlocListener`: 상태 변화에 따른 부수 효과(스낵바, 네비게이션)에 사용. 위젯을 빌드하지 않음
- `BlocConsumer`: 두 가지를 동시에 사용해야 할 때

질문 추가 성공 후 스낵바를 보여주려면 `BlocListener`를 `BlocBuilder` 위에 감싸면 된다. 이 관심사 분리 덕분에 UI 코드가 깔끔하게 유지된다.

```dart
BlocConsumer<ReviewQaBloc, ReviewQaState>(
  listener: (context, state) {
    if (state is ReviewQaQuestionAdded) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('질문이 추가되었습니다')),
      );
    }
    if (state is ReviewQaError) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(state.message)),
      );
    }
  },
  builder: (context, state) {
    // 위젯 빌드 로직
  },
)
```

---

## 테스트 전략

BLoC의 가장 큰 이점 중 하나는 테스트 용이성이다. `bloc_test` 패키지를 사용하면 이벤트 시퀀스에 대한 상태 전이를 간결하게 검증할 수 있다.

```dart
blocTest<ReviewQaBloc, ReviewQaState>(
  'AddQuestion emits copyWith(isAddingQuestion: true) then updated questions',
  build: () {
    when(mockRepository.addQuestion(
      sessionId: 1,
      content: '테스트 질문',
    )).thenAnswer((_) async => fakeQuestion);
    return ReviewQaBloc(repository: mockRepository);
  },
  seed: () => ReviewQaSessionLoaded(
    session: fakeSession,
    questions: [],
  ),
  act: (bloc) => bloc.add(AddQuestion(sessionId: 1, content: '테스트 질문')),
  expect: () => [
    ReviewQaSessionLoaded(session: fakeSession, questions: [], isAddingQuestion: true),
    ReviewQaQuestionAdded(fakeQuestion),
    // LoadQaSessionDetail 이벤트가 자동으로 추가됨
  ],
);
```

비즈니스 로직이 BLoC 안에 완전히 격리되어 있기 때문에, 위젯 트리 없이 순수 Dart 테스트로 모든 시나리오를 검증할 수 있다.

---

## Key Takeaways

- **상태 목록부터 시작하라**: 코드를 짜기 전에 UI가 보여줄 모든 상태를 나열하는 것 자체가 설계의 절반이다.
- **상태 클래스를 구체적으로 나눠라**: `abstract class`와 여러 구체 클래스로 상태를 나누면 UI 분기가 명확해진다. Dart 3+에서는 `sealed class`로 컴파일 타임 안전성을 확보하라.
- **전체 로딩과 부분 로딩을 구분하라**: `ReviewQaLoading`은 화면 전체를 대체하는 초기 로딩에만 쓰고, 세부 액션에는 `copyWith`로 플래그를 갱신하라.
- **`copyWith` 패턴은 핵심 기법이다**: 불변 상태를 유지하면서 일부 필드만 변경하여 UX를 망가뜨리지 않는 세밀한 상태 전이를 구현할 수 있다.
- **이벤트 트랜스포머를 활용하라**: `droppable()`, `restartable()` 등으로 중복 이벤트 처리 전략을 이벤트 등록 시점에 선언적으로 지정하라.
- **부수 효과는 `BlocListener`에**: 네비게이션, 스낵바 같은 부수 효과는 빌더와 분리해 리스너에서 처리하라.
- **테스트는 위젯 없이 가능하다**: 비즈니스 로직이 격리되어 있으므로 `bloc_test`로 순수 Dart 테스트를 작성하라. 이것이 BLoC를 선택하는 가장 실용적인 이유 중 하나다.
- **서버 응답 속도에 따라 전략을 선택하라**: 이벤트 처리 후 서버에서 다시 데이터를 가져올지(`LoadQaSessionDetail` 재호출), 아니면 로컬에서 즉시 반영하는 낙관적 업데이트를 할지는 레이턴시에 따라 결정한다.
