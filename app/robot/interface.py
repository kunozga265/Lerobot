"""Abstract RobotController per PLAN.md §3/§4. The game only ever talks to this
interface, so `mock_ctrl.py`, `lerobot_ctrl.py`, and a scripted-IK fallback are
interchangeable without the game logic caring which one is active."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

Box = Literal["left", "right"]


class RobotController(ABC):
    @abstractmethod
    def place_to(self, box: Box) -> bool:
        """Move one piece from the margin into `box`. Returns True on success."""

    @abstractmethod
    def return_from(self, box: Box) -> bool:
        """Move one piece from `box` back to the margin. Returns True on success."""

    @abstractmethod
    def go_home(self) -> None:
        """Return the arm to its fixed home pose."""
