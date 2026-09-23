"""Round screen. In Phase 1, also doubles as the keyboard-driven MockVision
control surface (0-9 = bar count, H = toggle hand-on-mat) and the facilitator
hotkey surface from PLAN.md §3 (Space = force-submit, N = skip round,
R = robot home, Esc = stop)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class RoundScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.vision = None
        self.engine = None
        self.rounds_total = 10
        self._bars = 0
        self._hand_on_mat = False

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.round_label = QLabel("Round 0 / 10")
        self.round_label.setStyleSheet("font-size: 20px;")
        self.score_label = QLabel("Score: 0")
        self.score_label.setStyleSheet("font-size: 20px;")
        top_row.addWidget(self.round_label)
        top_row.addStretch()
        top_row.addWidget(self.score_label)
        layout.addLayout(top_row)

        self.problem_label = QLabel("Get ready…")
        self.problem_label.setAlignment(Qt.AlignCenter)
        self.problem_label.setStyleSheet("font-size: 72px; font-weight: bold;")
        layout.addWidget(self.problem_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 26px; color: #2aa66c;")
        layout.addWidget(self.status_label)

        self.mock_panel = QLabel("")
        self.mock_panel.setAlignment(Qt.AlignCenter)
        self.mock_panel.setWordWrap(True)
        self.mock_panel.setStyleSheet("font-size: 14px; color: #888;")
        layout.addWidget(self.mock_panel)

    def bind_mock_vision(self, vision) -> None:
        self.vision = vision
        self._bars = 0
        self._hand_on_mat = False
        self._refresh_mock_panel()

    def bind_engine(self, engine) -> None:
        self.engine = engine

    def reset(self, rounds: int) -> None:
        self.rounds_total = rounds
        self.round_label.setText(f"Round 0 / {rounds}")
        self.score_label.setText("Score: 0")
        self.problem_label.setText("Get ready…")
        self.status_label.setText("")

    def set_problem(self, round_number: int, problem) -> None:
        self.round_label.setText(f"Round {round_number} / {self.rounds_total}")
        self.problem_label.setText(str(problem))

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_score(self, score: int) -> None:
        self.score_label.setText(f"Score: {score}")

    def keyPressEvent(self, event) -> None:
        key = event.key()
        text = event.text()

        if self.engine is None:
            super().keyPressEvent(event)
            return

        if key == Qt.Key_Escape:
            self.engine.request_stop()
        elif key == Qt.Key_Space:
            self.engine.request_force_submit()
        elif text.lower() == "n":
            self.engine.request_skip_round()
        elif text.lower() == "r":
            self.engine.request_go_home()
        elif text.lower() == "h" and self.vision is not None:
            self._hand_on_mat = not self._hand_on_mat
            self.vision.set_hand_on_mat(self._hand_on_mat)
            self._refresh_mock_panel()
        elif text.isdigit() and self.vision is not None:
            self._bars = int(text)
            self.vision.set_bars(self._bars)
            self._refresh_mock_panel()
        else:
            super().keyPressEvent(event)

    def _refresh_mock_panel(self) -> None:
        hand = "hand ON mat" if self._hand_on_mat else "hand clear"
        self.mock_panel.setText(
            f"[dev] bars={self._bars} ({hand}) — 0–9 set bars, H toggle hand, "
            "Space force-submit, N skip round, R robot home, Esc stop"
        )
