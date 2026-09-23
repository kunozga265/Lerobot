"""Shared vision output per PLAN.md §5. Both MockVision (Phase 1) and the real
vision pipeline (Phase 3) expose `get_state() -> BoardState`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BoardState:
    left: int
    right: int
    margin: int
    bars: int
    hand_on_mat: bool
    timestamp: float
    stable: bool
