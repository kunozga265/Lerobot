from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class StartScreen(QWidget):
    start_clicked = Signal()
    quit_clicked = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addStretch()

        title = QLabel("Robot Maths Tutor")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 48px; font-weight: bold;")
        layout.addWidget(title)

        how_to_play = QLabel(
            "Watch the robot set up a sum, then put your answer on the black mat\n"
            "using the coloured bars. Ten rounds — let's see your score!"
        )
        how_to_play.setAlignment(Qt.AlignCenter)
        how_to_play.setStyleSheet("font-size: 18px;")
        layout.addWidget(how_to_play)

        layout.addSpacing(40)

        start_button = QPushButton("Start")
        start_button.setFixedHeight(60)
        start_button.setFixedWidth(240)
        start_button.setStyleSheet(
            "font-size: 24px; border-radius: 12px; background-color: #2aa66c; color: white;"
        )
        start_button.clicked.connect(self.start_clicked.emit)
        layout.addWidget(start_button, alignment=Qt.AlignCenter)

        quit_button = QPushButton("Quit")
        quit_button.setFixedHeight(36)
        quit_button.setFixedWidth(140)
        quit_button.clicked.connect(self.quit_clicked.emit)
        layout.addWidget(quit_button, alignment=Qt.AlignCenter)

        layout.addStretch()
