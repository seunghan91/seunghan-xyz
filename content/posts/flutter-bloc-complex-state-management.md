---
title: "Flutter BLoC - Q&A 세션처럼 상태가 복잡할 때 설계하기"
date: 2026-02-25
draft: false
tags: ["Flutter", "BLoC", "상태관리", "UX"]
description: "단순한 목록/상세가 아닌, 세션 생성 → 질문 추가 → 답변 → 완료 흐름을 BLoC로 관리할 때 이벤트와 상태를 어떻게 나눌지 정리"
---

목록을 불러오고 보여주는 수준의 BLoC는 어렵지 않다.
문제는 세션 기반의 흐름, 예를 들어 "세션을 만들고 → 질문을 추가하고 → 답변을 받고 → 완료" 같은 단계적 워크플로우를 BLoC 하나로 관리할 때다.

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

상태 클래스를 이렇게 구체적으로 나눠야 UI에서 `if (state is ReviewQaSessionLoaded)` 처럼 명확하게 분기할 수 있다.

---

## 이벤트 설계

상태에 대응하는 이벤트를 만든다.

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

---

## BLoC 구현 - mapEventToState

각 이벤트를 처리하는 핸들러다.

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

---

## 정리

- 상태 클래스를 구체적으로 나눠야 UI 분기가 명확해진다
- 전체 로딩과 세부 액션 로딩을 구분해야 UX가 망가지지 않는다
- `copyWith` 패턴으로 현재 상태를 유지하면서 일부만 바꾸는 것이 핵심
- 이벤트 처리 후 자동으로 상세를 다시 로드할지, 낙관적 업데이트를 할지는 서버 응답 속도에 따라 결정한다
