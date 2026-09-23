from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class EndScreen(QWidget):
    play_again_clicked = Signal()
    exit_clicked = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addStretch()

        self.score_label = QLabel("0 / 10")
        self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setStyleSheet("font-size: 64px; font-weight: bold;")
        layout.addWidget(self.score_label)

        self.celebration_label = QLabel("")
        self.celebration_label.setAlignment(Qt.AlignCenter)
        self.celebration_label.setStyleSheet("font-size: 32px;")
        layout.addWidget(self.celebration_label)

        layout.addSpacing(30)

        buttons = QHBoxLayout()
        play_again = QPushButton("Play again")
        play_again.setFixedHeight(50)
        play_again.setStyleSheet("font-size: 20px;")
        play_again.clicked.connect(self.play_again_clicked.emit)
        buttons.addWidget(play_again)

        exit_button = QPushButton("Exit")
        exit_button.setFixedHeight(50)
        exit_button.setStyleSheet("font-size: 20px;")
        exit_button.clicked.connect(self.exit_clicked.emit)
        buttons.addWidget(exit_button)

        layout.addLayout(buttons)
        layout.addStretch()

    def set_final_score(self, score: int, total: int) -> None:
        self.score_label.setText(f"{score} / {total}")
        stars = "★" * (score * 5 // max(total, 1))
        self.celebration_label.setText(stars if score > 0 else "Nice try — play again!")
