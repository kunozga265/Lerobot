"""Non-blocking TTS + gentle sound cues for round announcements/feedback, per PLAN.md §6.

Uses macOS's built-in `say`/`afplay` rather than bundling audio assets. Both are
fire-and-forget subprocess calls so they never block the GUI thread.
"""

from __future__ import annotations

import subprocess

from app.game.engine import RoundResult
from app.game.problems import Problem

_OPERATOR_WORDS = {"+": "plus", "-": "minus", "*": "times", "/": "divided by"}

# Gentle system sounds (PLAN.md §6: "never harsh for wrong answers").
CORRECT_SOUND = "/System/Library/Sounds/Glass.aiff"
INCORRECT_SOUND = "/System/Library/Sounds/Tink.aiff"


class AudioFeedback:
    def __init__(self, tts_enabled: bool = True, sound_enabled: bool = True):
        self.tts_enabled = tts_enabled
        self.sound_enabled = sound_enabled

    def on_round_ready(self, _round_number: int, problem: Problem) -> None:
        operator_word = _OPERATOR_WORDS.get(problem.operation, problem.operation)
        self._speak(f"{problem.a} {operator_word} {problem.b}. Put your answer on the mat!")

    def on_round_result(self, result: RoundResult) -> None:
        self._play(CORRECT_SOUND if result.correct else INCORRECT_SOUND)
        message = "Well done!" if result.correct else f"Not quite. The answer was {result.problem.answer}."
        self._speak(message)

    def _speak(self, text: str) -> None:
        if self.tts_enabled:
            self._run(["say", text])

    def _play(self, sound_path: str) -> None:
        if self.sound_enabled:
            self._run(["afplay", sound_path])

    @staticmethod
    def _run(args: list[str]) -> None:
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass  # `say`/`afplay` unavailable (non-macOS) - audio is optional polish, not fatal
