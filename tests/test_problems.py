import random

import pytest

from app.game.problems import Problem, generate_game, generate_problem, generate_round_operations

OPERATIONS = ["+", "-", "*", "/"]


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
        elif operation == "*":
            assert 1 <= problem.a <= 3 and 1 <= problem.b <= 3
        else:
            assert 1 <= problem.b <= 3
            assert problem.a % problem.b == 0  # b divides a exactly


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


@pytest.mark.parametrize("operation", OPERATIONS)
def test_generate_problem_single_block_mode(operation):
    # PLAN.md temporary simplification: with only 1 piece per box available, every
    # operator must fall back to "1 op 1" - there's no other valid pair.
    rng = random.Random(7)
    for _ in range(50):
        problem = generate_problem(operation, rng=rng, max_per_box=1)
        assert problem == Problem(1, 1, operation)


def test_generate_game_respects_max_per_box():
    rng = random.Random(6)
    game = generate_game(rounds=10, mix={"+": 5, "-": 2, "*": 3}, rng=rng, max_per_box=2)
    assert len(game) == 10
    assert all(p.a <= 2 and p.b <= 2 for p in game)


def test_generate_round_operations_balanced_and_shuffled():
    rng = random.Random(2)
    operations = generate_round_operations(rounds=10, rng=rng)
    assert len(operations) == 10
    assert sorted(operations.count(op) for op in ["+", "-", "*"]) == [3, 3, 4]


def test_generate_round_operations_custom_length():
    rng = random.Random(3)
    operations = generate_round_operations(rounds=5, mix={"+": 4, "-": 3, "*": 3}, rng=rng)
    assert len(operations) == 5
    assert all(op in OPERATIONS for op in operations)


def test_generate_round_operations_trims_randomly_not_deterministically():
    # Regression case: trimming used to happen before shuffling, so with more mix
    # entries than rounds it silently dropped the same operator every time (whichever
    # sorted last in mix dict order) instead of a random one.
    mix = {"+": 1, "-": 1, "*": 1, "/": 1}
    dropped = set()
    for seed in range(30):
        operations = generate_round_operations(rounds=3, mix=mix, rng=random.Random(seed))
        assert len(operations) == 3
        missing = set(mix) - set(operations)
        assert len(missing) == 1
        dropped.add(next(iter(missing)))
    assert len(dropped) > 1  # more than one operator got dropped across these seeds


def test_generate_game_produces_valid_problems():
    rng = random.Random(4)
    game = generate_game(rounds=10, rng=rng)
    assert len(game) == 10
    for problem in game:
        assert 1 <= problem.answer <= 10
