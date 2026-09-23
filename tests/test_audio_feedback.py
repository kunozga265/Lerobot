from unittest.mock import patch

from app.game.engine import RoundResult
from app.game.problems import Problem
from app.gui.audio_feedback import CORRECT_SOUND, INCORRECT_SOUND, AudioFeedback


def make_result(correct: bool) -> RoundResult:
    problem = Problem(a=3, b=2, operation="+")
    return RoundResult(
        round_number=1,
        problem=problem,
        given_answer=problem.answer if correct else problem.answer + 1,
        correct=correct,
        planned_problem=problem,
        setup_retries=0,
        setup_seconds=0.1,
        answer_seconds=0.1,
    )


@patch("app.gui.audio_feedback.subprocess.Popen")
def test_on_round_ready_speaks_problem_with_operator_words(mock_popen):
    audio = AudioFeedback()
    audio.on_round_ready(1, Problem(a=3, b=2, operation="+"))

    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args[0] == "say"
    assert "3 plus 2" in args[1]


@patch("app.gui.audio_feedback.subprocess.Popen")
def test_on_round_result_correct_plays_glass_and_speaks_well_done(mock_popen):
    audio = AudioFeedback()
    audio.on_round_result(make_result(correct=True))

    calls = [call.args[0] for call in mock_popen.call_args_list]
    assert ["afplay", CORRECT_SOUND] in calls
    assert any(call[0] == "say" and "Well done" in call[1] for call in calls)


@patch("app.gui.audio_feedback.subprocess.Popen")
def test_on_round_result_incorrect_plays_tink_and_speaks_answer(mock_popen):
    audio = AudioFeedback()
    audio.on_round_result(make_result(correct=False))

    calls = [call.args[0] for call in mock_popen.call_args_list]
    assert ["afplay", INCORRECT_SOUND] in calls
    assert any(call[0] == "say" and "5" in call[1] for call in calls)


@patch("app.gui.audio_feedback.subprocess.Popen")
def test_disabled_tts_and_sound_never_call_subprocess(mock_popen):
    audio = AudioFeedback(tts_enabled=False, sound_enabled=False)
    audio.on_round_ready(1, Problem(a=3, b=2, operation="+"))
    audio.on_round_result(make_result(correct=True))

    mock_popen.assert_not_called()
