import threading

from app.game.engine import AnswerWatcher, GameEngine
from app.game.problems import Problem
from app.robot.mock_ctrl import MockRobotController
from app.vision.mock_vision import MockVision

ENGINE_CONFIG = {
    "rounds_per_game": 10,
    "operation_mix": {"+": 4, "-": 3, "*": 3},
    "max_answer": 10,
    "hand_clear_seconds": 2.0,
    "count_stable_seconds": 1.5,
    "feedback_seconds": 3.5,
}


def make_engine(margin_pieces: int) -> GameEngine:
    vision = MockVision(margin_pieces=margin_pieces)
    robot = MockRobotController(vision, seconds_per_piece=0.0)
    return GameEngine(robot, vision, ENGINE_CONFIG)


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_watcher(hand_clear=2.0, count_stable=1.5):
    clock = FakeClock()
    watcher = AnswerWatcher(hand_clear_seconds=hand_clear, count_stable_seconds=count_stable, clock=clock)
    return watcher, clock


def test_no_submit_before_any_hand_seen():
    watcher, clock = make_watcher()
    assert watcher.update(bars=3, hand_on_mat=False) is False
    clock.advance(10)
    assert watcher.update(bars=3, hand_on_mat=False) is False


def test_no_submit_while_hand_still_on_mat():
    watcher, clock = make_watcher()
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(10)
    assert watcher.update(bars=3, hand_on_mat=True) is False


def test_no_submit_until_hand_clear_duration_elapses():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(1.0)
    assert watcher.update(bars=3, hand_on_mat=False) is False  # hand gone only 1.0s < 2.0s


def test_no_submit_until_count_stable_duration_elapses():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(0.1)
    watcher.update(bars=3, hand_on_mat=False)
    clock.advance(2.0)  # hand clear satisfied
    # bar count only just became "stable" now (changed at hand-removal time in this test setup)
    assert watcher.update(bars=4, hand_on_mat=False) is False  # count just changed
    clock.advance(1.0)
    assert watcher.update(bars=4, hand_on_mat=False) is False  # only 1.0s stable, need 1.5s


def test_submits_once_all_three_conditions_hold():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)  # hand seen
    clock.advance(0.1)
    watcher.update(bars=4, hand_on_mat=False)  # hand now gone, count already stable since first sample
    clock.advance(2.0)  # hand clear for >= 2.0s
    assert watcher.update(bars=4, hand_on_mat=False) is True


def test_count_change_resets_stability_even_after_hand_clear():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    assert watcher.update(bars=4, hand_on_mat=False) is True  # stable the whole time, submits

    watcher.reset()
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    watcher.update(bars=5, hand_on_mat=False)  # count changes right when hand clears
    assert watcher.update(bars=5, hand_on_mat=False) is False  # not stable long enough yet
    clock.advance(1.6)
    assert watcher.update(bars=5, hand_on_mat=False) is True


def test_hand_seen_again_after_clearing_requires_full_clear_wait_again():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    watcher.update(bars=4, hand_on_mat=False)  # would submit next sample
    watcher.update(bars=4, hand_on_mat=True)  # hand returns to mat
    assert watcher.update(bars=4, hand_on_mat=False) is False  # must wait hand_clear_seconds again


class RecordingRobot:
    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[str] = []

    def place_to(self, box):
        self.calls.append(box)
        return self.succeed

    def return_from(self, box):
        raise AssertionError("the game must not call return_from: boxes are reset by a helper")

    def go_home(self):
        pass


def test_round_setup_places_planned_counts_on_each_side():
    robot = RecordingRobot()
    engine = GameEngine(robot, MockVision(), ENGINE_CONFIG)

    problem, failed = engine._round_setup(Problem(a=2, b=1, operation="+"))

    assert robot.calls == ["left", "left", "right"]
    assert problem == Problem(a=2, b=1, operation="+")
    assert failed == 0


def test_round_setup_keeps_planned_sum_when_robot_fails():
    # The displayed sum is what was commanded, never a recount of the boxes.
    robot = RecordingRobot(succeed=False)
    engine = GameEngine(robot, MockVision(), ENGINE_CONFIG)

    problem, failed = engine._round_setup(Problem(a=2, b=2, operation="*"))

    assert problem == Problem(a=2, b=2, operation="*")
    assert problem.answer == 4
    assert failed == 4


def test_round_reset_waits_for_helper_enter():
    engine = make_engine(margin_pieces=15)  # mock mat is already clear (0 bars, no hand)
    finished = threading.Event()
    worker = threading.Thread(target=lambda: (engine._round_reset(), finished.set()))
    worker.start()

    assert not finished.wait(0.3)  # still waiting for the helper
    engine.request_boxes_ready()
    assert finished.wait(1.0)
    worker.join()
