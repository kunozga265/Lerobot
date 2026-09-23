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
    problem: Problem  # the sum the robot was commanded to set up (same as planned_problem)
    given_answer: int
    correct: bool
    planned_problem: Problem
    setup_retries: int
    setup_seconds: float
    answer_seconds: float
    failed_placements: int = 0  # place_to() calls that reported failure (robot reliability metric)


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
        self._boxes_ready_requested = False

    # --- facilitator hotkeys -------------------------------------------------
    def request_force_submit(self) -> None:
        self._force_submit_requested = True

    def request_skip_round(self) -> None:
        self._skip_requested = True

    def request_stop(self) -> None:
        self._stop_requested = True

    def request_go_home(self) -> None:
        self.robot.go_home()

    def request_boxes_ready(self) -> None:
        """Helper confirms the shapes are back on their margin spots (Enter)."""
        self._boxes_ready_requested = True

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
            max_per_box=self.config.get("max_pieces_per_box"),
        )

        for planned in problems:
            if self._stop_requested:
                return
            self.round_number += 1

            setup_start = time.monotonic()
            problem, failed_placements = self._round_setup(planned)
            setup_seconds = time.monotonic() - setup_start
            if self._stop_requested:
                return

            answer_start = time.monotonic()
            given = self._wait_for_answer()
            answer_seconds = time.monotonic() - answer_start
            if self._stop_requested:
                return

            correct = self._evaluate(problem, given)
            self._feedback(planned, problem, given, correct, failed_placements, setup_seconds, answer_seconds)
            self._round_reset(wait_for_helper=self.round_number < len(problems))

        self._set_state(GameState.END_SCREEN)

    def _round_setup(self, planned: Problem) -> tuple[Problem, int]:
        """Command the robot to place `a` pieces left and `b` right. The sum shown is what
        was commanded, not a vision recount, so a dropped piece never changes the answer."""
        self._set_state(GameState.ROUND_SETUP)
        self._status("Watch the robot…")
        failed = 0
        for box, count in (("left", planned.a), ("right", planned.b)):
            for _ in range(count):
                if self._stop_requested:
                    return planned, failed
                if not self.robot.place_to(box):
                    failed += 1
        if self.on_round_ready:
            self.on_round_ready(self.round_number, planned)
        return planned, failed

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
        failed_placements: int,
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
                    setup_retries=0,
                    setup_seconds=setup_seconds,
                    answer_seconds=answer_seconds,
                    failed_placements=failed_placements,
                )
            )
        self._interruptible_sleep(self.config["feedback_seconds"])

    def _round_reset(self, wait_for_helper: bool = True) -> None:
        self._set_state(GameState.ROUND_RESET)
        self._status("Please clear the mat")
        self._skip_requested = False
        while not self._stop_requested:
            state = self.vision.get_state()
            if (state.bars == 0 and not state.hand_on_mat) or self._skip_requested:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        if not wait_for_helper:
            return  # last round: go straight to the end screen; the helper resets there

        # The robot has no return skill, so a helper puts the shapes back on their spots.
        self._status("Helper: put the shapes back on their spots, then press Enter")
        self._skip_requested = False
        self._boxes_ready_requested = False
        while not self._stop_requested:
            if self._boxes_ready_requested or self._skip_requested:
                self._boxes_ready_requested = False
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
