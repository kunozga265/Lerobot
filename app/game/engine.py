"""Game state machine per PLAN.md §3. Framework-agnostic (no Qt) so it can run in
any worker thread and be unit tested directly; the GUI wraps it in a QThread."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from app.game.problems import Operation, Problem, generate_game

POLL_INTERVAL_SECONDS = 0.1


class GameState(Enum):
    START_PAGE = auto()
    NEW_GAME = auto()
    ROUND_SETUP = auto()
    WAIT_FOR_ANSWER = auto()
    EVALUATE = auto()
    FEEDBACK = auto()
    ROUND_RESET = auto()
    END_SCREEN = auto()


@dataclass
class RoundResult:
    round_number: int
    problem: Problem  # verified/ground-truth problem (may differ from planned_problem)
    given_answer: int
    correct: bool
    planned_problem: Problem
    setup_retries: int
    setup_seconds: float
    answer_seconds: float


class AnswerWatcher:
    """Implements PLAN.md's "When is an answer submitted?" rule:
    1. A hand has been seen over the mat at least once since the round started.
    2. No hand has been detected for `hand_clear_seconds`.
    3. The bar count has been stable for `count_stable_seconds`.
    """

    def __init__(
        self,
        hand_clear_seconds: float = 2.0,
        count_stable_seconds: float = 1.5,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.hand_clear_seconds = hand_clear_seconds
        self.count_stable_seconds = count_stable_seconds
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self._hand_seen = False
        self._hand_last_seen_at: float | None = None
        self._last_bar_count: int | None = None
        self._count_stable_since: float | None = None

    def update(self, bars: int, hand_on_mat: bool) -> bool:
        """Feed one vision sample; returns True if the answer should be submitted now."""
        now = self._clock()

        if hand_on_mat:
            self._hand_seen = True
            self._hand_last_seen_at = now

        if bars != self._last_bar_count:
            self._last_bar_count = bars
            self._count_stable_since = now

        if not self._hand_seen or hand_on_mat:
            return False

        hand_clear_for = now - self._hand_last_seen_at
        if hand_clear_for < self.hand_clear_seconds:
            return False

        count_stable_for = now - self._count_stable_since
        return count_stable_for >= self.count_stable_seconds


class GameEngine:
    def __init__(self, robot, vision, config: dict, rng: random.Random | None = None):
        self.robot = robot
        self.vision = vision
        self.config = config
        self.rng = rng or random.Random()

        self.state = GameState.START_PAGE
        self.score = 0
        self.round_number = 0

        self.on_state_changed: Callable[[GameState], None] | None = None
        self.on_status_message: Callable[[str], None] | None = None
        self.on_score_changed: Callable[[int], None] | None = None
        self.on_round_result: Callable[[RoundResult], None] | None = None
        self.on_round_ready: Callable[[int, Problem], None] | None = None

        self._stop_requested = False
        self._skip_requested = False
        self._force_submit_requested = False

    # --- facilitator hotkeys -------------------------------------------------
    def request_force_submit(self) -> None:
        self._force_submit_requested = True

    def request_skip_round(self) -> None:
        self._skip_requested = True

    def request_stop(self) -> None:
        self._stop_requested = True

    def request_go_home(self) -> None:
        self.robot.go_home()

    # --- game loop -------------------------------------------------------------
    def run_game(self) -> None:
        self._stop_requested = False
        self.score = 0
        self.round_number = 0
        self._set_state(GameState.NEW_GAME)

        problems = generate_game(
            rounds=self.config["rounds_per_game"],
            mix=self.config["operation_mix"],
            rng=self.rng,
        )

        for planned in problems:
            if self._stop_requested:
                return
            self.round_number += 1

            setup_start = time.monotonic()
            problem, setup_retries = self._round_setup(planned)
            setup_seconds = time.monotonic() - setup_start
            if self._stop_requested:
                return

            answer_start = time.monotonic()
            given = self._wait_for_answer()
            answer_seconds = time.monotonic() - answer_start
            if self._stop_requested:
                return

            correct = self._evaluate(problem, given)
            self._feedback(planned, problem, given, correct, setup_retries, setup_seconds, answer_seconds)
            self._round_reset()

        self._set_state(GameState.END_SCREEN)

    def _round_setup(self, planned: Problem) -> tuple[Problem, int]:
        self._set_state(GameState.ROUND_SETUP)
        self._status("Watch the robot…")
        actual_a, actual_b, attempts = self._setup_boxes(planned.a, planned.b)
        problem = Problem(actual_a, actual_b, planned.operation)
        if self.on_round_ready:
            self.on_round_ready(self.round_number, problem)
        return problem, max(0, attempts - 1)  # attempts=1 means it succeeded first try, i.e. 0 retries

    def _setup_boxes(self, target_a: int, target_b: int, max_attempts: int = 3) -> tuple[int, int, int]:
        state = self.vision.get_state()
        attempts = 0
        for _ in range(max_attempts):
            if self._stop_requested:
                break
            attempts += 1
            self._move_box_to_count("left", state.left, target_a)
            self._move_box_to_count("right", state.right, target_b)
            state = self.vision.get_state()
            if state.left == target_a and state.right == target_b:
                break
        return state.left, state.right, attempts

    def _move_box_to_count(self, box: str, current: int, target: int) -> None:
        if target > current:
            for _ in range(target - current):
                if self._stop_requested:
                    return
                self.robot.place_to(box)
        elif target < current:
            for _ in range(current - target):
                if self._stop_requested:
                    return
                self.robot.return_from(box)

    def _wait_for_answer(self) -> int:
        self._set_state(GameState.WAIT_FOR_ANSWER)
        self._status("Count the shapes and put your answer on the black mat!")
        watcher = AnswerWatcher(self.config["hand_clear_seconds"], self.config["count_stable_seconds"])
        self._force_submit_requested = False
        self._skip_requested = False

        while not self._stop_requested:
            state = self.vision.get_state()
            if watcher.update(state.bars, state.hand_on_mat) or self._force_submit_requested:
                return state.bars
            if self._skip_requested:
                self._skip_requested = False
                return state.bars
            time.sleep(POLL_INTERVAL_SECONDS)
        return 0

    def _evaluate(self, problem: Problem, given: int) -> bool:
        self._set_state(GameState.EVALUATE)
        self._status("Checking…")
        correct = given == problem.answer
        if correct:
            self.score += 1
            if self.on_score_changed:
                self.on_score_changed(self.score)
        return correct

    def _feedback(
        self,
        planned: Problem,
        problem: Problem,
        given: int,
        correct: bool,
        setup_retries: int,
        setup_seconds: float,
        answer_seconds: float,
    ) -> None:
        self._set_state(GameState.FEEDBACK)
        message = "Well done! ✓" if correct else f"Not quite — the answer was {problem.answer}"
        self._status(message)
        if self.on_round_result:
            self.on_round_result(
                RoundResult(
                    round_number=self.round_number,
                    problem=problem,
                    given_answer=given,
                    correct=correct,
                    planned_problem=planned,
                    setup_retries=setup_retries,
                    setup_seconds=setup_seconds,
                    answer_seconds=answer_seconds,
                )
            )
        self._interruptible_sleep(self.config["feedback_seconds"])

    def _round_reset(self) -> None:
        self._set_state(GameState.ROUND_RESET)
        self._status("Please clear the mat")
        self._skip_requested = False
        while not self._stop_requested:
            state = self.vision.get_state()
            if (state.bars == 0 and not state.hand_on_mat) or self._skip_requested:
                self._skip_requested = False
                return
            time.sleep(POLL_INTERVAL_SECONDS)

    # --- helpers -----------------------------------------------------------
    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop_requested and time.monotonic() < end:
            time.sleep(min(POLL_INTERVAL_SECONDS, end - time.monotonic()))

    def _set_state(self, state: GameState) -> None:
        self.state = state
        if self.on_state_changed:
            self.on_state_changed(state)

    def _status(self, message: str) -> None:
        if self.on_status_message:
            self.on_status_message(message)
