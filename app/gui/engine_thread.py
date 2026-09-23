"""Runs GameEngine.run_game() on a worker QThread and re-emits its plain-Python
callbacks as Qt signals, per PLAN.md §3 ("Robot and vision work must run in worker
threads, never on the GUI thread. Every state emits a signal the GUI uses.")."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.game.engine import GameEngine


class EngineThread(QThread):
    state_changed = Signal(object)  # GameState
    status_message = Signal(str)
    score_changed = Signal(int)
    round_result = Signal(object)  # RoundResult
    round_ready = Signal(int, object)  # round_number, Problem

    def __init__(self, engine: GameEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        engine.on_state_changed = self.state_changed.emit
        engine.on_status_message = self.status_message.emit
        engine.on_score_changed = self.score_changed.emit
        engine.on_round_result = self.round_result.emit
        engine.on_round_ready = self.round_ready.emit

    def run(self) -> None:
        self.engine.run_game()
