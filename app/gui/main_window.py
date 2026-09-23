from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QStackedWidget

from app.game.engine import GameEngine, GameState
from app.gui.end_screen import EndScreen
from app.gui.engine_thread import EngineThread
from app.gui.round_screen import RoundScreen
from app.gui.start_screen import StartScreen
from app.robot.mock_ctrl import MockRobotController
from app.vision.mock_vision import MockVision


class MainWindow(QMainWindow):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.setWindowTitle("Robot Maths Tutor")
        self.resize(1000, 700)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.start_screen = StartScreen()
        self.round_screen = RoundScreen()
        self.end_screen = EndScreen()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.round_screen)
        self.stack.addWidget(self.end_screen)

        self.start_screen.start_clicked.connect(self.start_new_game)
        self.start_screen.quit_clicked.connect(self.close)
        self.end_screen.play_again_clicked.connect(self.start_new_game)
        self.end_screen.exit_clicked.connect(self.show_start_screen)

        self.thread: EngineThread | None = None
        self.stack.setCurrentWidget(self.start_screen)

    def show_start_screen(self) -> None:
        self._stop_current_game()
        self.stack.setCurrentWidget(self.start_screen)

    def start_new_game(self) -> None:
        self._stop_current_game()

        vision = MockVision()
        robot = MockRobotController(
            vision, seconds_per_piece=self.config["mock"]["robot_seconds_per_piece"]
        )
        engine = GameEngine(robot, vision, self.config["game"])

        self.round_screen.bind_mock_vision(vision)
        self.round_screen.bind_engine(engine)
        self.round_screen.reset(rounds=self.config["game"]["rounds_per_game"])

        self.thread = EngineThread(engine)
        self.thread.status_message.connect(self.round_screen.set_status)
        self.thread.score_changed.connect(self.round_screen.set_score)
        self.thread.round_ready.connect(self.round_screen.set_problem)
        self.thread.finished.connect(self._on_game_finished)

        self.stack.setCurrentWidget(self.round_screen)
        self.round_screen.setFocus()
        self.thread.start()

    def _on_game_finished(self) -> None:
        if self.thread is None:
            return
        if self.thread.engine.state == GameState.END_SCREEN:
            self.end_screen.set_final_score(
                self.thread.engine.score, self.config["game"]["rounds_per_game"]
            )
            self.stack.setCurrentWidget(self.end_screen)
        else:
            self.stack.setCurrentWidget(self.start_screen)

    def _stop_current_game(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.engine.request_stop()
            self.thread.wait(3000)
        self.thread = None

    def closeEvent(self, event) -> None:
        self._stop_current_game()
        super().closeEvent(event)
