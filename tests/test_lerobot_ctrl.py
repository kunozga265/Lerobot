"""LeRobotController against fake hardware: no arm, cameras or trained policy needed."""

import numpy as np
import pytest

from app.game.engine import GameEngine
from app.hardware import HardwareError, build_hardware
from app.robot.lerobot_ctrl import LeRobotController, _as_float_or_none
from app.robot.mock_ctrl import MockRobotController
from app.vision.mock_vision import MockVision

MOTORS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
HOME = {f"{m}.pos": 0.0 for m in MOTORS}
AWAY = {f"{m}.pos": 40.0 for m in MOTORS}


class FakeBus:
    def __init__(self):
        self.torque_on = True

    def disable_torque(self):
        self.torque_on = False

    def enable_torque(self):
        self.torque_on = True


class FakeRobot:
    def __init__(self, pose):
        self.pose = dict(pose)
        self.bus = FakeBus()
        self.action_features = {k: float for k in HOME}
        self.sent = []

    def get_observation(self):
        return dict(self.pose)

    def send_action(self, action):
        self.sent.append(action)
        self.pose = dict(action)
        return action


class FakeFrames:
    def get_frame(self, name):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[..., 0] = 255  # pure blue in OpenCV's BGR order
        return frame


class ScriptedPolicy:
    """Drives the arm away from home for `away_steps` actions, then back home."""

    camera_names = ["overhead", "wrist"]

    def __init__(self, away_steps=30, on_act=None):
        self.away_steps = away_steps
        self.on_act = on_act
        self.calls = 0
        self.resets = 0
        self.last_images = None

    def reset(self):
        self.resets += 1
        self.calls = 0

    def act(self, state, images):
        self.calls += 1
        self.last_images = images
        if self.on_act:
            self.on_act(self.calls)
        target = AWAY if self.calls <= self.away_steps else HOME
        return np.array([target[k] for k in HOME], dtype=np.float32)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 1 / 30)  # every control tick costs at least one frame


def make_controller(policy, home_pose=HOME, max_seconds=20.0):
    clock = FakeClock()
    robot = FakeRobot(HOME)
    ctrl = LeRobotController(
        robot,
        FakeFrames(),
        {"left": policy, "right": policy},
        home_pose=home_pose,
        fps=30,
        min_seconds=3.0,
        max_seconds=max_seconds,
        clock=clock,
        sleep=clock.sleep,
    )
    return ctrl, robot, clock


def test_place_succeeds_once_arm_is_back_home_after_min_seconds():
    policy = ScriptedPolicy(away_steps=150)  # ~5 s away from home at 30 Hz
    ctrl, robot, clock = make_controller(policy)

    assert ctrl.place_to("left") is True
    assert policy.resets == 1
    assert 5.0 <= clock.now < 6.0  # ended as soon as it got home, not at max_seconds


def test_policy_gets_rgb_frames_at_training_size():
    policy = ScriptedPolicy(away_steps=150)
    ctrl, _, _ = make_controller(policy)
    ctrl.place_to("left")

    for name in ("overhead", "wrist"):
        image = policy.last_images[name]
        assert image.shape == (480, 640, 3)
        assert image[0, 0].tolist() == [0, 0, 255]  # blue moved to the last channel (RGB)


def test_place_fails_when_arm_never_returns_home():
    policy = ScriptedPolicy(away_steps=10_000)
    ctrl, _, clock = make_controller(policy, max_seconds=8.0)

    assert ctrl.place_to("right") is False
    assert clock.now >= 8.0


def test_place_fails_when_policy_never_leaves_home():
    # A policy that outputs the home pose from the very first action never attempts the
    # task - it must not be reported as a successful placement just because it's
    # technically "near home" the whole time. This is the failure mode observed on the
    # real rig: the arm barely moves when the box already has a piece in it.
    policy = ScriptedPolicy(away_steps=0)
    ctrl, _, clock = make_controller(policy, max_seconds=8.0)

    assert ctrl.place_to("left") is False
    assert clock.now >= 8.0  # ran the full timeout rather than exiting early at min_seconds


def test_without_home_pose_runs_full_duration_and_trusts_it():
    policy = ScriptedPolicy(away_steps=10_000)
    ctrl, _, clock = make_controller(policy, home_pose=None, max_seconds=8.0)

    assert ctrl.place_to("left") is True
    assert clock.now >= 8.0


def test_stop_mid_placement_aborts_without_further_actions():
    holder = {}
    policy = ScriptedPolicy(away_steps=10_000, on_act=lambda n: n == 20 and holder["ctrl"].stop())
    ctrl, robot, _ = make_controller(policy)
    holder["ctrl"] = ctrl

    assert ctrl.place_to("left") is False
    assert len(robot.sent) == 20  # the action computed on the stop tick is still sent; nothing after
    assert robot.bus.torque_on  # a plain stop keeps torque on


def test_emergency_stop_cuts_torque_and_next_move_restores_it():
    policy = ScriptedPolicy(away_steps=150)
    ctrl, robot, _ = make_controller(policy)

    ctrl.stop(emergency=True)
    assert robot.bus.torque_on is False

    assert ctrl.place_to("left") is True
    assert robot.bus.torque_on is True


def test_go_home_moves_to_saved_pose():
    ctrl, robot, _ = make_controller(ScriptedPolicy())
    robot.pose = dict(AWAY)

    ctrl.go_home()

    assert robot.pose == HOME


def test_return_from_is_not_supported():
    ctrl, _, _ = make_controller(ScriptedPolicy())
    with pytest.raises(NotImplementedError):
        ctrl.return_from("left")


def test_engine_stop_passes_emergency_to_robot():
    stops = []

    class Robot(MockRobotController):
        def stop(self, emergency=False):
            stops.append(emergency)

    board = MockVision()
    engine = GameEngine(Robot(board, seconds_per_piece=0), board, {})
    engine.request_stop()
    engine.request_stop(emergency=True)

    assert stops == [False, True]


def test_as_float_or_none_casts_plain_yaml_int_to_float():
    # Regression case: config.yaml's `max_relative_target: 15` (no decimal point) parses
    # as a Python int, which lerobot's ensure_safe_goal_position rejects outright - it
    # only accepts float, dict[str, float], or None (see so_follower.py's isinstance
    # checks), raising TypeError deep inside send_action on the first real placement.
    result = _as_float_or_none(15)
    assert result == 15.0
    assert isinstance(result, float)


def test_as_float_or_none_passes_through_none():
    assert _as_float_or_none(None) is None


def test_build_hardware_all_mock_opens_nothing():
    hardware = build_hardware({"robot": {"mode": "mock"}, "vision": {"mode": "mock"}})
    assert hardware.cameras is None and hardware.robot is None and hardware.vision is None


def test_build_hardware_missing_camera_is_a_clear_error(monkeypatch):
    class NoCameras:
        def __init__(self, indices, **_):
            self.indices = indices

        def open(self):
            return {name: False for name in self.indices}

        def stop(self):
            pass

    monkeypatch.setattr("app.vision.cameras.CameraManager", NoCameras)
    config = {"robot": {"mode": "lerobot"}, "vision": {"mode": "mock"}, "cameras": {"overhead": 1, "wrist": 0}}

    with pytest.raises(HardwareError, match="Camera missing: overhead \\(index 1\\), wrist \\(index 0\\)"):
        build_hardware(config)
