"""Fake robot for development, per PLAN.md Phase 1: sleeps to simulate motion time
and updates the shared MockVision board directly (see vision/mock_vision.py)."""

from __future__ import annotations

import time

from app.robot.interface import Box, RobotController
from app.vision.mock_vision import MockVision


class MockRobotController(RobotController):
    def __init__(self, board: MockVision, seconds_per_piece: float = 1.0):
        self.board = board
        self.seconds_per_piece = seconds_per_piece

    def place_to(self, box: Box) -> bool:
        time.sleep(self.seconds_per_piece)
        return self.board.add_piece(box)

    def return_from(self, box: Box) -> bool:
        time.sleep(self.seconds_per_piece)
        return self.board.remove_piece(box)

    def go_home(self) -> None:
        time.sleep(self.seconds_per_piece * 0.5)
