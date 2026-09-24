"""Headless GUI verification, with no display required (QT_QPA_PLATFORM=offscreen).

Split into two tests deliberately:
- test_full_game_playable_headless drives the real MainWindow/EngineThread/GameEngine
  through a full 10-round game, calling the facilitator force-submit hotkey's *method*
  directly (bypassing simulated OS key events) with a retry loop. GameEngine resets
  `_force_submit_requested = False` once per round, right as `_wait_for_answer` starts;
  a single request racing that reset can land in the same instant it gets cleared and be
  silently lost (observed directly with per-iteration tracing during development - not
  something feedback_seconds/hand_clear_seconds tuning can fix, since it's about request
  vs. reset ordering, not overall timing budget). request_force_submit() only sets a bool,
  so it's safe to re-issue every poll tick until the round actually evaluates.
- test_round_screen_hotkeys verifies keyPressEvent -> engine/vision call mapping via real
  simulated keystrokes, in isolation (single widget, no worker thread to race).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.gui.main_window import MainWindow
from app.gui.round_screen import RoundScreen

TEST_CONFIG = {
    "game": {
        "rounds_per_game": 10,
        "operation_mix": {"+": 4, "-": 3, "*": 3},
        "max_answer": 10,
        "hand_clear_seconds": 0.05,
        "count_stable_seconds": 0.05,
        "feedback_seconds": 0.05,
    },
    "mock": {"robot_seconds_per_piece": 0.01},
    # Audio disabled: the smoke test drives 10 real rounds and shouldn't spawn real
    # `say`/`afplay` subprocesses each time (see app/gui/audio_feedback.py's own
    # mocked-subprocess tests for that behaviour in isolation).
    "gui": {"tts_enabled": False, "sound_enabled": False},
}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _wait_until(condition, timeout_s: float = 5.0) -> bool:
    elapsed = 0
    step = 20
    while elapsed < timeout_s * 1000:
        if condition():
            return True
        QTest.qWait(step)
        elapsed += step
    return condition()


def test_full_game_playable_headless(qapp, tmp_path):
    window = MainWindow(TEST_CONFIG)
    window.round_logger.path = tmp_path / "games.csv"  # keep the real logs/games.csv untouched
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowExposed(window)

    start_button = _find_button(window.start_screen, "Start")
    QTest.mouseClick(start_button, Qt.LeftButton)

    assert _wait_until(lambda: window.thread is not None and window.thread.isRunning())

    ready_rounds = []
    window.thread.round_ready.connect(lambda n, _problem: ready_rounds.append(n))
    round_results = []
    window.thread.round_result.connect(lambda result: round_results.append(result))

    total_rounds = TEST_CONFIG["game"]["rounds_per_game"]
    for round_number in range(1, total_rounds + 1):
        # Between rounds the engine waits for the helper's Enter (shapes back on their spots);
        # re-issue it every poll tick for the same reset-race reason as force-submit below.
        assert _wait_until(lambda: _confirm_boxes_and_check(window, round_number, ready_rounds)), (
            f"round {round_number} never became ready"
        )

        # `_wait_for_answer` resets `_force_submit_requested = False` when it starts, right
        # after `_round_setup` (which is what fires `round_ready`) returns. A single
        # request can land in that reset's narrow window and get wiped before the engine's
        # poll loop ever sees it. request_force_submit() is idempotent (just sets a bool),
        # so keep re-issuing it until the round actually evaluates instead of gambling on
        # a fixed delay being long enough.
        assert _wait_until(lambda: _resubmit_and_check(window, round_number, round_results)), (
            f"round {round_number} never evaluated; engine state {window.thread.engine.state}"
        )

    assert _wait_until(lambda: window.stack.currentWidget() is window.end_screen)
    assert f"/ {total_rounds}" in window.end_screen.score_label.text()

    expected_score = sum(1 for r in round_results if r.correct)
    assert f"{expected_score} / {total_rounds}" == window.end_screen.score_label.text()

    assert window.round_logger.path.exists()
    with window.round_logger.path.open() as f:
        logged_rows = f.read().count("\n") - 1  # header + one line per round
    assert logged_rows == total_rounds

    window._stop_current_game()
    window.close()


def test_round_screen_hotkeys(qapp):
    """Verifies keyPressEvent dispatch in isolation, where QTest.keyClick is reliable
    (no competing worker thread / queued cross-thread signals to race)."""
    screen = RoundScreen()
    engine = _FakeEngine()
    vision = _FakeVision()
    screen.bind_engine(engine)
    screen.bind_mock_vision(vision)
    screen.show()
    screen.activateWindow()
    QTest.qWaitForWindowExposed(screen)

    QTest.keyClick(screen, Qt.Key_Space)
    assert engine.force_submit_calls == 1

    QTest.keyClick(screen, Qt.Key_N)
    assert engine.skip_calls == 1

    QTest.keyClick(screen, Qt.Key_R)
    assert engine.go_home_calls == 1

    QTest.keyClick(screen, Qt.Key_H)
    assert vision.hand_on_mat is True
    QTest.keyClick(screen, Qt.Key_H)
    assert vision.hand_on_mat is False

    QTest.keyClick(screen, Qt.Key_7)
    assert vision.bars == 7

    QTest.keyClick(screen, Qt.Key_Return)
    assert engine.boxes_ready_calls == 1
    assert vision.boxes_reset is True

    QTest.keyClick(screen, Qt.Key_Escape)
    assert engine.stop_calls == 1
    assert engine.last_stop_emergency is True  # Esc is the emergency stop (torque off)

    screen.close()


class _FakeEngine:
    def __init__(self):
        self.force_submit_calls = 0
        self.skip_calls = 0
        self.stop_calls = 0
        self.go_home_calls = 0
        self.boxes_ready_calls = 0

    def request_force_submit(self):
        self.force_submit_calls += 1

    def request_skip_round(self):
        self.skip_calls += 1

    def request_stop(self, emergency=False):
        self.stop_calls += 1
        self.last_stop_emergency = emergency

    def request_go_home(self):
        self.go_home_calls += 1

    def request_boxes_ready(self):
        self.boxes_ready_calls += 1


class _FakeVision:
    def __init__(self):
        self.bars = None
        self.hand_on_mat = None

    def set_bars(self, count):
        self.bars = count

    def set_hand_on_mat(self, on_mat):
        self.hand_on_mat = on_mat

    def reset_boxes(self):
        self.boxes_reset = True


def _resubmit_and_check(window: MainWindow, round_number: int, round_results: list) -> bool:
    if len(round_results) == round_number:
        return True
    window.thread.engine.request_force_submit()
    return False



def _confirm_boxes_and_check(window, round_number, ready_rounds) -> bool:
    if round_number in ready_rounds:
        return True
    window.thread.engine.request_boxes_ready()
    return False

def _find_button(widget, text: str) -> QPushButton:
    for button in widget.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"no QPushButton with text {text!r} found")
