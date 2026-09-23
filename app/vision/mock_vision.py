"""MockVision per PLAN.md Phase 1: keyboard-driven bar count + hand-on-mat toggle,
so the game is playable with no cameras. Box/margin counts are driven directly by
MockRobotController (see robot/mock_ctrl.py) since there's no camera to observe
ground truth from in Phase 1 — the mock robot's placements *are* ground truth."""

from __future__ import annotations

import time

from app.vision.board_state import BoardState


class MockVision:
    def __init__(self, margin_pieces: int = 15):
        self.left = 0
        self.right = 0
        self.margin = margin_pieces
        self.bars = 0
        self.hand_on_mat = False

    # --- called by MockRobotController --------------------------------------
    def add_piece(self, box: str) -> bool:
        if self.margin <= 0:
            return False
        if box == "left":
            self.left += 1
        else:
            self.right += 1
        self.margin -= 1
        return True

    def remove_piece(self, box: str) -> bool:
        count = self.left if box == "left" else self.right
        if count <= 0:
            return False
        if box == "left":
            self.left -= 1
        else:
            self.right -= 1
        self.margin += 1
        return True

    def reset_boxes(self) -> None:
        """Helper puts every placed shape back on the margin (Enter between rounds)."""
        self.margin += self.left + self.right
        self.left = self.right = 0

    # --- called by the GUI (keyboard-driven learner side) -------------------
    def set_bars(self, count: int) -> None:
        self.bars = max(0, count)

    def set_hand_on_mat(self, on_mat: bool) -> None:
        self.hand_on_mat = on_mat

    # --- polled by GameEngine ------------------------------------------------
    def get_state(self) -> BoardState:
        return BoardState(
            left=self.left,
            right=self.right,
            margin=self.margin,
            bars=self.bars,
            hand_on_mat=self.hand_on_mat,
            timestamp=time.time(),
            stable=True,  # no sensor noise to smooth over in mock mode
        )
