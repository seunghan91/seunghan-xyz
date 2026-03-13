---
title: "Flutter BLoC - Designing State Management for Complex Q&A Sessions"
date: 2025-07-06
draft: false
tags: ["Flutter", "BLoC", "State Management", "UX"]
description: "How to structure events and states in BLoC for complex flows like session creation, question addition, answering, and completion, beyond simple list/detail views."
cover:
  image: "/images/og/flutter-bloc-complex-state-management.png"
  alt: "Flutter Bloc Complex State Management"
  hidden: true
---


A BLoC that just loads and displays a list isn't hard.
The challenge comes when you need to manage session-based workflows in a single BLoC -- things like "create a session -> add questions -> receive answers -> complete."

---

## Draw the States First

Before coding the BLoC, define the states first.
Listing all the states the UI needs to display for this workflow:

- Initial (nothing loaded)
- Session list loading
- Session list displayed
- Creating new session
- Session detail loading
- Session detail displayed (with question list)
- Adding question
- Submitting answer
- Error

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

State classes need to be this specific so the UI can branch clearly with `if (state is ReviewQaSessionLoaded)`.

---

## Event Design

Create events that correspond to each state.

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

## BLoC Implementation - mapEventToState

Handlers for each event.

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
    // Don't transition to loading state -- keep current state
    // because the existing list should remain visible while adding a question
    final currentState = state;
    try {
      final newQuestion = await _repository.addQuestion(
        sessionId: event.sessionId,
        content: event.content,
      );
      emit(ReviewQaQuestionAdded(newQuestion));

      // Reload detail after adding
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

## Caution: Don't Overuse the Loading State

You shouldn't `emit(ReviewQaLoading())` on every event.

Having the entire list disappear and a spinner appear while adding a question is the worst UX.
`ReviewQaLoading` should only be used for "initial loading where it's okay to replace the entire screen."

For granular actions (adding questions, submitting answers), it's better to include a separate local state or `isSubmitting` flag within the BLoC state.

```dart
class ReviewQaSessionLoaded extends ReviewQaState {
  final QaSession session;
  final List<ReviewQuestion> questions;
  final bool isAddingQuestion;  // Whether a question is being added

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
    emit(current.copyWith(isAddingQuestion: true));  // Keep list, only change flag

    try {
      final newQuestion = await _repository.addQuestion(...);
      final updatedQuestions = [...current.questions, newQuestion];
      emit(current.copyWith(
        questions: updatedQuestions,
        isAddingQuestion: false,
      ));
    } catch (e) {
      emit(current.copyWith(isAddingQuestion: false));
      // Error handling
    }
  }
}
```

---

## Branching in the UI

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
            const LinearProgressIndicator()  // Thin progress bar instead of full spinner
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

## Summary

- Splitting state classes into specific types makes UI branching clear
- Distinguishing between full-screen loading and granular action loading is essential for good UX
- The `copyWith` pattern -- keeping current state while changing only parts -- is the key technique
- Whether to auto-reload details after event processing or use optimistic updates depends on server response speed
