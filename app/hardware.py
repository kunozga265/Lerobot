"""Builds the long-lived real hardware once at startup, per `robot.mode` / `vision.mode`
in config.yaml. Anything left on `mock` is created per game by MainWindow instead, so
every mix works: mock/mock (no hardware), real vision + mock robot, mock vision + real
robot, or both real. Everything shares one CameraManager, since only one process can own
a camera on macOS (PLAN.md §3)."""

from __future__ import annotations

from dataclasses import dataclass


class HardwareError(RuntimeError):
    """A camera or the robot couldn't be started; the message is shown to the facilitator."""


@dataclass
class Hardware:
    cameras: object | None = None  # CameraManager
    robot: object | None = None  # RobotController (real)
    vision: object | None = None  # live vision exposing get_state() -> BoardState

    def close(self) -> None:
        if self.robot is not None and hasattr(self.robot, "disconnect"):
            self.robot.disconnect()
        if self.vision is not None and hasattr(self.vision, "stop"):
            self.vision.stop()
        if self.cameras is not None:
            self.cameras.stop()


def robot_mode(config: dict) -> str:
    return config.get("robot", {}).get("mode", "mock")


def vision_mode(config: dict) -> str:
    return config.get("vision", {}).get("mode", "mock")


def build_hardware(config: dict) -> Hardware:
    hardware = Hardware()
    if robot_mode(config) == "mock" and vision_mode(config) == "mock":
        return hardware

    try:
        hardware.cameras = _open_cameras(config)
        if vision_mode(config) == "live":
            try:
                from app.vision.live_vision import LiveVision
            except ImportError as e:
                raise HardwareError(
                    "vision.mode is 'live' but live vision isn't built yet (INTEGRATION_PLAN.md step 3). "
                    "Set vision.mode: mock for now."
                ) from e
            try:
                hardware.vision = LiveVision(hardware.cameras, config)
            except ValueError as e:  # e.g. no mat calibration yet
                raise HardwareError(str(e)) from e
            hardware.vision.start()
        if robot_mode(config) == "lerobot":
            from app.robot.lerobot_ctrl import LeRobotController

            try:
                hardware.robot = LeRobotController.from_config(config, hardware.cameras)
            except Exception as e:
                reason = " ".join(str(e).split()) or type(e).__name__  # lerobot's messages span lines
                raise HardwareError(
                    f"Robot not connected on {config['robot'].get('follower_port')}: {reason}"
                ) from e
    except BaseException:
        hardware.close()
        raise
    return hardware


def _open_cameras(config: dict):
    from app.vision.cameras import CameraManager

    cam_cfg = config["cameras"]
    indices = {name: cam_cfg[name] for name in ("overhead", "wrist")}
    cameras = CameraManager(
        indices,
        width=cam_cfg.get("width", 1920),
        height=cam_cfg.get("height", 1080),
        fps=cam_cfg.get("fps", 30),
    )
    opened = cameras.open()
    missing = [f"{name} (index {indices[name]})" for name, ok in opened.items() if not ok]
    if missing:
        cameras.stop()
        raise HardwareError(
            f"Camera missing: {', '.join(missing)}. Check the USB hub and the indices in config.yaml "
            "(they can change on replug; run lerobot-find-cameras opencv)."
        )
    cameras.start()
    return cameras
