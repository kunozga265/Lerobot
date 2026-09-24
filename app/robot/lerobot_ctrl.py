"""Real RobotController running the trained ACT skills (PLAN.md §4) on the SO-101 follower.

The follower is connected *without* cameras: the app's CameraManager owns both cameras
(only one process can hold a camera on macOS), so this controller reads the latest frames
from it and converts them to what the policy saw while recording (RGB, 640x480).

`place_to(box)` runs that box's policy at `fps` until the arm is back near the home pose
(after `min_seconds`) or `max_seconds` pass. There is no box recount: the game takes the
sum from the commands it sent (see engine.py)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

import cv2
import numpy as np

from app.robot.interface import Box, RobotController

GRIPPER_KEY = "gripper.pos"  # ignored for the "near home" check: open/closed varies at home


class FrameSource(Protocol):
    def get_frame(self, name: str) -> np.ndarray | None: ...


class PolicyRunner(Protocol):
    camera_names: list[str]

    def reset(self) -> None: ...

    def act(self, state: np.ndarray, images: dict[str, np.ndarray]) -> np.ndarray: ...


class ActPolicyRunner:
    """One trained ACT skill: the policy plus the pre/post-processors saved with it
    (they hold the dataset normalisation stats)."""

    def __init__(self, path: str, task: str, device: str | None = None):
        import torch
        from lerobot.policies.act.modeling_act import ACTPolicy
        from lerobot.policies.factory import make_pre_post_processors

        self.policy = ACTPolicy.from_pretrained(path)
        if device:
            self.policy.config.device = device
        self.device = torch.device(self.policy.config.device)
        self.policy.to(self.device)
        self.policy.eval()
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            self.policy.config,
            pretrained_path=path,
            preprocessor_overrides={"device_processor": {"device": str(self.device)}},
        )
        self.task = task
        self.camera_names = [
            key.removeprefix("observation.images.")
            for key in self.policy.config.input_features
            if key.startswith("observation.images.")
        ]

    def reset(self) -> None:
        self.policy.reset()
        self.preprocessor.reset()
        self.postprocessor.reset()

    def act(self, state: np.ndarray, images: dict[str, np.ndarray]) -> np.ndarray:
        import torch
        from lerobot.policies.utils import prepare_observation_for_inference

        observation = {"observation.state": state.astype(np.float32)}
        for name in self.camera_names:
            observation[f"observation.images.{name}"] = images[name]
        with torch.inference_mode():
            batch = prepare_observation_for_inference(observation, self.device, self.task, "so101_follower")
            batch = self.preprocessor(batch)
            action = self.postprocessor(self.policy.select_action(batch))
        return action.squeeze(0).cpu().numpy()


class LeRobotController(RobotController):
    def __init__(
        self,
        robot,
        frames: FrameSource,
        policies: dict[Box, PolicyRunner],
        home_pose: dict[str, float] | None = None,
        fps: int = 30,
        min_seconds: float = 3.0,
        max_seconds: float = 20.0,
        home_tolerance: float = 4.0,
        image_size: tuple[int, int] = (640, 480),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.robot = robot
        self.frames = frames
        self.policies = policies
        self.home_pose = home_pose
        self.fps = fps
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.home_tolerance = home_tolerance
        self.image_size = image_size
        self._clock = clock
        self._sleep = sleep
        self._motor_keys = list(robot.action_features)  # "shoulder_pan.pos", ..., same order as the dataset
        self._bus_lock = threading.Lock()  # stop() runs on the GUI thread while a skill runs on the engine thread
        self._cancel = threading.Event()
        self._torque_off = False

    # --- RobotController ---------------------------------------------------
    def place_to(self, box: Box) -> bool:
        policy = self.policies[box]
        policy.reset()
        self._cancel.clear()
        self._ensure_torque()
        period = 1.0 / self.fps
        start = self._clock()
        obs = None

        while True:
            tick = self._clock()
            elapsed = tick - start
            if elapsed >= self.max_seconds:
                break
            with self._bus_lock:
                if self._cancel.is_set():
                    return False
                obs = self.robot.get_observation()
                if self.home_pose and elapsed >= self.min_seconds and self._near_home(obs):
                    return True
                images = self._policy_images(policy.camera_names)
                if images is not None:
                    state = np.array([obs[k] for k in self._motor_keys], dtype=np.float32)
                    action = policy.act(state, images)
                    self.robot.send_action(dict(zip(self._motor_keys, action.tolist())))
            self._sleep(max(0.0, period - (self._clock() - tick)))

        # Timed out. Without a saved home pose there's nothing to check, so trust the run.
        return self.home_pose is None or (obs is not None and self._near_home(obs))

    def return_from(self, box: Box) -> bool:
        raise NotImplementedError("no return skill was trained; a helper resets the shapes between rounds")

    def go_home(self, seconds: float = 2.0) -> None:
        """Move in a straight joint-space line from the current pose to the saved home pose."""
        if not self.home_pose:
            return
        self._cancel.clear()
        self._ensure_torque()
        with self._bus_lock:
            obs = self.robot.get_observation()
        start = {k: float(obs[k]) for k in self._motor_keys}
        steps = max(1, int(seconds * self.fps))
        for i in range(1, steps + 1):
            with self._bus_lock:
                if self._cancel.is_set():
                    return
                t = i / steps
                self.robot.send_action(
                    {k: start[k] + t * (self.home_pose.get(k, start[k]) - start[k]) for k in self._motor_keys}
                )
            self._sleep(1.0 / self.fps)

    def stop(self, emergency: bool = False) -> None:
        self._cancel.set()
        if emergency:
            with self._bus_lock:
                self.robot.bus.disable_torque()
                self._torque_off = True

    def disconnect(self) -> None:
        self.stop()
        with self._bus_lock:
            self.robot.disconnect()

    # --- helpers -----------------------------------------------------------
    def _ensure_torque(self) -> None:
        if self._torque_off:
            with self._bus_lock:
                self.robot.bus.enable_torque()
                self._torque_off = False

    def _near_home(self, obs: dict) -> bool:
        return all(
            abs(float(obs[k]) - target) <= self.home_tolerance
            for k, target in self.home_pose.items()
            if k != GRIPPER_KEY
        )

    def _policy_images(self, names: list[str]) -> dict[str, np.ndarray] | None:
        """Latest camera frames as the policy saw them while recording: RGB at `image_size`.
        None if a camera hasn't produced a frame yet (skip this tick rather than guess)."""
        images = {}
        for name in names:
            frame = self.frames.get_frame(name)
            if frame is None:
                return None
            if (frame.shape[1], frame.shape[0]) != self.image_size:
                frame = cv2.resize(frame, self.image_size, interpolation=cv2.INTER_AREA)
            images[name] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # CameraManager gives OpenCV BGR
        return images

    # --- construction from config.yaml -------------------------------------
    @classmethod
    def from_config(cls, config: dict, frames: FrameSource) -> "LeRobotController":
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

        robot_cfg = config["robot"]
        policy_cfg = robot_cfg["policies"]
        robot = SO101Follower(
            SO101FollowerConfig(
                port=robot_cfg["follower_port"],
                id=robot_cfg["follower_id"],
                max_relative_target=robot_cfg.get("max_relative_target"),
            )
        )
        robot.connect(calibrate=False)  # never prompt on stdin from inside the GUI
        if not robot.is_calibrated:
            if not robot.calibration:
                robot.disconnect()
                raise RuntimeError(
                    f"No calibration for follower id '{robot_cfg['follower_id']}'. "
                    "Run lerobot-calibrate with that id first."
                )
            robot.bus.write_calibration(robot.calibration)

        device = policy_cfg.get("device")
        policies = {
            box: ActPolicyRunner(policy_cfg[box]["path"], policy_cfg[box]["task"], device)
            for box in ("left", "right")
        }
        return cls(
            robot,
            frames,
            policies,
            home_pose=robot_cfg.get("home_pose"),
            fps=policy_cfg.get("fps", 30),
            min_seconds=policy_cfg.get("min_seconds", 3.0),
            max_seconds=policy_cfg.get("max_seconds", 20.0),
            home_tolerance=policy_cfg.get("home_tolerance", 4.0),
            image_size=(policy_cfg.get("image_width", 640), policy_cfg.get("image_height", 480)),
        )
