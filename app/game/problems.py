"""Operand/operation generation with the constraints from PLAN.md §2."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

Operation = Literal["+", "-", "*"]


@dataclass(frozen=True)
class Problem:
    a: int
    b: int
    operation: Operation

    @property
    def answer(self) -> int:
        if self.operation == "+":
            return self.a + self.b
        if self.operation == "-":
            return self.a - self.b
        return self.a * self.b

    def __str__(self) -> str:
        return f"{self.a} {self.operation} {self.b} = ?"


def _generate_add(margin_pieces: int, rng: random.Random) -> Problem:
    while True:
        a = rng.randint(1, 5)
        b = rng.randint(1, 5)
        if a + b <= 10 and a + b <= margin_pieces:
            return Problem(a, b, "+")


def _generate_subtract(margin_pieces: int, rng: random.Random) -> Problem:
    while True:
        a = rng.randint(2, 6)
        b = rng.randint(1, a - 1)
        if a <= margin_pieces:
            return Problem(a, b, "-")


def _generate_multiply(margin_pieces: int, rng: random.Random) -> Problem:
    while True:
        a = rng.randint(1, 3)
        b = rng.randint(1, 3)
        if a * b <= 10 and a + b <= margin_pieces:
            return Problem(a, b, "*")


_GENERATORS = {"+": _generate_add, "-": _generate_subtract, "*": _generate_multiply}


def generate_problem(
    operation: Operation, margin_pieces: int = 15, rng: random.Random | None = None
) -> Problem:
    """Generate a single problem for `operation` honouring PLAN.md §2 constraints."""
    rng = rng or random.Random()
    return _GENERATORS[operation](margin_pieces, rng)


def generate_round_operations(
    rounds: int = 10,
    mix: dict[Operation, int] | None = None,
    rng: random.Random | None = None,
) -> list[Operation]:
    """Balance `rounds` operations per the mix (default ~4 add, 3 subtract, 3 multiply), shuffled."""
    rng = rng or random.Random()
    mix = mix or {"+": 4, "-": 3, "*": 3}
    operations: list[Operation] = []
    for op, count in mix.items():
        operations.extend([op] * count)
    # Top up or trim if `rounds` doesn't match the mix total, cycling the mix keys.
    keys = list(mix.keys())
    i = 0
    while len(operations) < rounds:
        operations.append(keys[i % len(keys)])
        i += 1
    operations = operations[:rounds]
    rng.shuffle(operations)
    return operations


def generate_game(
    rounds: int = 10,
    mix: dict[Operation, int] | None = None,
    margin_pieces: int = 15,
    rng: random.Random | None = None,
) -> list[Problem]:
    """Generate a full game's worth of problems, balanced per `mix`."""
    rng = rng or random.Random()
    return [
        generate_problem(op, margin_pieces, rng)
        for op in generate_round_operations(rounds, mix, rng)
    ]
