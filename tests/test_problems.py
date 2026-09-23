import random

import pytest

from app.game.problems import generate_game, generate_problem, generate_round_operations

OPERATIONS = ["+", "-", "*"]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_generate_problem_constraints_hold(operation):
    rng = random.Random(0)
    for _ in range(500):
        problem = generate_problem(operation, margin_pieces=15, rng=rng)
        assert 1 <= problem.answer <= 10
        assert problem.a + problem.b <= 15
        if operation == "+":
            assert 1 <= problem.a <= 5 and 1 <= problem.b <= 5
        elif operation == "-":
            assert 2 <= problem.a <= 6
            assert 1 <= problem.b <= problem.a - 1
            assert problem.answer >= 1
        else:
            assert 1 <= problem.a <= 3 and 1 <= problem.b <= 3


def test_generate_problem_respects_margin_cap():
    rng = random.Random(1)
    for _ in range(200):
        problem = generate_problem("+", margin_pieces=4, rng=rng)
        assert problem.a + problem.b <= 4



@pytest.mark.parametrize("operation", OPERATIONS)
def test_generate_problem_respects_max_per_box(operation):
    rng = random.Random(5)
    for _ in range(200):
        problem = generate_problem(operation, rng=rng, max_per_box=2)
        assert 1 <= problem.a <= 2 and 1 <= problem.b <= 2
        assert problem.answer >= 1


def test_generate_game_respects_max_per_box():
    rng = random.Random(6)
    game = generate_game(rounds=10, mix={"+": 5, "-": 2, "*": 3}, rng=rng, max_per_box=2)
    assert len(game) == 10
    assert all(p.a <= 2 and p.b <= 2 for p in game)

def test_generate_round_operations_balanced_and_shuffled():
    rng = random.Random(2)
    operations = generate_round_operations(rounds=10, rng=rng)
    assert len(operations) == 10
    assert sorted(operations.count(op) for op in OPERATIONS) == [3, 3, 4]


def test_generate_round_operations_custom_length():
    rng = random.Random(3)
    operations = generate_round_operations(rounds=5, mix={"+": 4, "-": 3, "*": 3}, rng=rng)
    assert len(operations) == 5
    assert all(op in OPERATIONS for op in operations)


def test_generate_game_produces_valid_problems():
    rng = random.Random(4)
    game = generate_game(rounds=10, rng=rng)
    assert len(game) == 10
    for problem in game:
        assert 1 <= problem.answer <= 10
