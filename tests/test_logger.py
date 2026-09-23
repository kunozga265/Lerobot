import csv

from app.game.engine import RoundResult
from app.game.logger import RoundLogger
from app.game.problems import Problem


def make_result(round_number=1, correct=True, given=5, retries=0):
    return RoundResult(
        round_number=round_number,
        problem=Problem(a=3, b=2, operation="+"),
        given_answer=given,
        correct=correct,
        planned_problem=Problem(a=3, b=2, operation="+"),
        setup_retries=retries,
        setup_seconds=1.234,
        answer_seconds=2.5,
    )


def test_creates_file_and_directory_and_writes_header(tmp_path):
    log_path = tmp_path / "nested" / "games.csv"
    logger = RoundLogger(path=log_path)

    logger.log_round(make_result())

    assert log_path.exists()
    with log_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["round_number"] == "1"
    assert rows[0]["operation"] == "+"
    assert rows[0]["planned_a"] == "3"
    assert rows[0]["verified_a"] == "3"
    assert rows[0]["answer"] == "5"
    assert rows[0]["given_answer"] == "5"
    assert rows[0]["correct"] == "True"
    assert rows[0]["setup_retries"] == "0"
    assert rows[0]["setup_seconds"] == "1.234"
    assert rows[0]["answer_seconds"] == "2.5"


def test_appends_rows_without_repeating_header(tmp_path):
    log_path = tmp_path / "games.csv"
    logger = RoundLogger(path=log_path)

    logger.log_round(make_result(round_number=1))
    logger.log_round(make_result(round_number=2, correct=False, given=7, retries=1))

    with log_path.open() as f:
        lines = f.readlines()
        f.seek(0)
        rows = list(csv.DictReader(f))

    assert lines[0].startswith("timestamp,round_number")  # header written exactly once
    assert len(rows) == 2
    assert [r["round_number"] for r in rows] == ["1", "2"]
    assert rows[1]["correct"] == "False"
    assert rows[1]["setup_retries"] == "1"


def test_reuses_existing_file_across_logger_instances(tmp_path):
    log_path = tmp_path / "games.csv"

    RoundLogger(path=log_path).log_round(make_result(round_number=1))
    RoundLogger(path=log_path).log_round(make_result(round_number=2))  # simulates a new game session

    with log_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
