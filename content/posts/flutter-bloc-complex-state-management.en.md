---
title: "Flutter BLoC State Design Beyond Lists — Handling Multi-Step Session Flows"
date: 2025-07-06
draft: false
tags: ["Flutter", "BLoC", "State Management", "UX"]
categories: ["Flutter"]
description: "BLoC is easy for simple lists. But how do you model multi-step flows — create session, add questions, receive answers, complete? Here's a state design approach that scales without spaghetti."
cover:
  image: "/images/og/flutter-bloc-complex-state-management.png"
  alt: "Flutter Bloc Complex State Management"
  hidden: true
---

A BLoC that just loads and displays a list is not hard.
The challenge comes when you need to manage session-based workflows in a single BLoC -- things like "create a session -> add questions -> receive answers -> complete."

This pattern appears constantly in real-world apps: review Q&A systems, multi-step surveys, onboarding flows. If you have ever watched your UI collapse under the weight of a single `isLoading` boolean, this post is for you.

---

## Why BLoC Is Well-Suited for Complex Flows

The core value of BLoC (Business Logic Component) is complete separation between UI and business logic. For simple data fetching this advantage is subtle, but when state transitions become multi-stage and independent loading feedback is required within the same screen, BLoC's structural benefits become obvious.

The current `flutter_bloc` API -- the `on<Event>` handler approach -- cleanly isolates the processing logic for each event type. Even with ten or more handlers the code does not devolve into spaghetti, because each handler is a focused, independently testable unit.

---

## Draw the States First

Before writing any BLoC code, define the states first.
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

Writing this list before touching the keyboard is itself a design act. Any state omitted here will return later as an unhandled edge case.

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

State classes need to be this specific so the UI can branch cleanly with `if (state is ReviewQaSessionLoaded)`. Collapsing all state into a single class using booleans and enums causes conditional combinations to explode at the UI layer.

### Sealed Class Pattern (Dart 3+)

From Dart 3 onward, `sealed class` forces the compiler to require exhaustive handling of every subtype. Combined with switch expressions, missing cases become a build-time error rather than a runtime surprise.

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

With `sealed`, a `switch (state)` in the UI without a wildcard `_` requires every subtype to be handled. Adding a new state class later forces every switch site to be updated, preventing silent omissions.

---

## Event Design

Create events that correspond to each state transition. Events represent "something the user or system did," so naming them with imperative or past-tense verbs is the common convention.

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

Applying `Equatable` to event classes allows the BLoC to skip processing when the same event is dispatched consecutively. This is particularly useful when using `transformEvents` with `distinct()`.

---

## BLoC Implementation — Event Handlers

Handlers for each event. In `flutter_bloc 8+`, `mapEventToState` is deprecated; the `on<Event>` approach is the current standard.

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
    // Do not transition to a full loading state -- keep the current state
    // because the existing list must remain visible while a question is being added
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

### Using Event Transformers

When registering `on<Event>`, a second argument accepts an `EventTransformer`. For events that fire in rapid succession (such as search input), use `debounce`. To prevent duplicate execution, use `droppable()`.

```dart
import 'package:bloc_concurrency/bloc_concurrency.dart';

on<AddQuestion>(
  _onAddQuestion,
  transformer: droppable(), // ignores new events while one is already in flight
);
```

The `bloc_concurrency` package provides four transformers: `sequential()`, `concurrent()`, `droppable()`, and `restartable()`. Choosing the right one based on the event's nature eliminates an entire class of race-condition bugs.

---

## Caution: Do Not Overuse the Loading State

You should not `emit(ReviewQaLoading())` on every event.

Having the entire list disappear and a full-screen spinner appear while adding a question is the worst possible UX.
`ReviewQaLoading` should only be used for "initial loading where replacing the entire screen is acceptable."

For granular actions (adding questions, submitting answers), include a separate `isSubmitting` flag inside the loaded state and use `copyWith` to update only that field.

```dart
class ReviewQaSessionLoaded extends ReviewQaState {
  final QaSession session;
  final List<ReviewQuestion> questions;
  final bool isAddingQuestion;  // Whether a question add is in progress

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
    emit(current.copyWith(isAddingQuestion: true));  // Keep list, only flip the flag

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

The `copyWith` pattern maintains immutable state while returning a new instance with only the changed fields. Because `flutter_bloc` detects state changes via `==` comparison, either apply `Equatable` to state classes or ensure `copyWith` always returns a genuinely different instance to trigger rebuilds.

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
            const LinearProgressIndicator()  // Thin progress bar instead of a full spinner
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

- `BlocBuilder`: use when state drives widget rebuilds
- `BlocListener`: use for side effects (snack bars, navigation) that should not rebuild the widget tree
- `BlocConsumer`: use when both are needed simultaneously

To show a snack bar after a question is added successfully, wrap a `BlocListener` around the `BlocBuilder`. This separation of concerns keeps UI code clean and prevents listener logic from polluting builder logic.

```dart
BlocConsumer<ReviewQaBloc, ReviewQaState>(
  listener: (context, state) {
    if (state is ReviewQaQuestionAdded) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Question added successfully')),
      );
    }
    if (state is ReviewQaError) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(state.message)),
      );
    }
  },
  builder: (context, state) {
    // Widget build logic
  },
)
```

---

## Testing Strategy

One of the biggest practical advantages of BLoC is testability. The `bloc_test` package makes it concise to verify state transitions for a given sequence of events.

```dart
blocTest<ReviewQaBloc, ReviewQaState>(
  'AddQuestion emits copyWith(isAddingQuestion: true) then updated questions',
  build: () {
    when(mockRepository.addQuestion(
      sessionId: 1,
      content: 'Test question',
    )).thenAnswer((_) async => fakeQuestion);
    return ReviewQaBloc(repository: mockRepository);
  },
  seed: () => ReviewQaSessionLoaded(
    session: fakeSession,
    questions: [],
  ),
  act: (bloc) => bloc.add(AddQuestion(sessionId: 1, content: 'Test question')),
  expect: () => [
    ReviewQaSessionLoaded(session: fakeSession, questions: [], isAddingQuestion: true),
    ReviewQaQuestionAdded(fakeQuestion),
    // LoadQaSessionDetail event is dispatched automatically inside the handler
  ],
);
```

Because business logic is fully isolated inside the BLoC, every scenario can be verified as a pure Dart test without a widget tree. This is one of the most pragmatic reasons to adopt BLoC over simpler state management approaches.

---

## Key Takeaways

- **Start with the state list**: Enumerating every state the UI will display before writing code is half the design work. Omitted states return as edge case bugs.
- **Keep state classes specific**: Use an abstract base and concrete subclasses. With Dart 3+, prefer `sealed class` for compile-time exhaustiveness checking.
- **Distinguish full-screen loading from inline loading**: `ReviewQaLoading` is for initial loads that replace the whole screen. Granular actions use `copyWith` to flip an inline flag.
- **`copyWith` is the core technique**: Immutable state with targeted field updates enables fine-grained state transitions without disrupting the existing UI.
- **Use event transformers**: Declare concurrency strategy -- `droppable()`, `restartable()`, etc. -- at the `on<Event>` registration site to eliminate race conditions declaratively.
- **Side effects belong in `BlocListener`**: Navigation and snack bars are side effects, not widget rebuilds. Keep them in a listener, not the builder.
- **Tests require no widget tree**: Business logic isolation means `bloc_test` lets you verify every scenario as a pure Dart unit test. This is one of the most compelling practical reasons to choose BLoC.
- **Choose between reload and optimistic update based on latency**: Whether to re-fetch from the server after an event (dispatch `LoadQaSessionDetail` again) or immediately apply changes locally (optimistic update) depends on your API's response speed. Low-latency APIs can afford a refetch; high-latency ones benefit from optimistic updates with rollback on error.
