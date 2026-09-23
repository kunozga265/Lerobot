"""Per-round CSV logging, per PLAN.md §7 Phase 5."""

from __future__ import annotations

import csv
import datetime
from pathlib import Path

from app.game.engine import RoundResult

DEFAULT_LOG_PATH = Path("logs/games.csv")

_FIELDNAMES = [
    "timestamp",
    "round_number",
    "operation",
    "planned_a",
    "planned_b",
    "verified_a",
    "verified_b",
    "answer",
    "given_answer",
    "correct",
    "setup_retries",
    "failed_placements",
    "setup_seconds",
    "answer_seconds",
]


class RoundLogger:
    def __init__(self, path: Path = DEFAULT_LOG_PATH):
        self.path = Path(path)

    def log_round(self, result: RoundResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists()
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                    "round_number": result.round_number,
                    "operation": result.problem.operation,
                    "planned_a": result.planned_problem.a,
                    "planned_b": result.planned_problem.b,
                    "verified_a": result.problem.a,
                    "verified_b": result.problem.b,
                    "answer": result.problem.answer,
                    "given_answer": result.given_answer,
                    "correct": result.correct,
                    "setup_retries": result.setup_retries,
                    "failed_placements": result.failed_placements,
                    "setup_seconds": round(result.setup_seconds, 3),
                    "answer_seconds": round(result.answer_seconds, 3),
                }
            )
