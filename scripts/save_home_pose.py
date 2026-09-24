"""Save the follower's home pose to config.yaml (robot.home_pose).

LeRobotController uses it to end a placement once the arm is back home, and for the R
(go home) key. Every recorded episode started and ended at home, so put the arm in that
same pose:

    pipenv run python scripts/save_home_pose.py

Torque is turned off so you can move the follower by hand, then press Enter to save.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "app" / "config.yaml"


def main() -> None:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    robot_cfg = yaml.safe_load(CONFIG_PATH.read_text())["robot"]
    robot = SO101Follower(SO101FollowerConfig(port=robot_cfg["follower_port"], id=robot_cfg["follower_id"]))
    robot.connect(calibrate=False)
    if not robot.is_calibrated:
        if not robot.calibration:
            sys.exit(f"No calibration for '{robot_cfg['follower_id']}'. Run lerobot-calibrate first.")
        robot.bus.write_calibration(robot.calibration)
    try:
        robot.bus.disable_torque()
        input("Torque is off. Move the follower to the home pose, then press Enter...")
        obs = robot.get_observation()
        pose = {k: round(float(v), 2) for k, v in obs.items() if k.endswith(".pos")}
    finally:
        robot.disconnect()

    text = CONFIG_PATH.read_text()
    line = "  home_pose: " + yaml.safe_dump(pose, default_flow_style=True, width=1000).strip()
    new_text, n = re.subn(r"^  home_pose:.*$", line, text, count=1, flags=re.MULTILINE)
    if n != 1:
        sys.exit("config.yaml has no robot.home_pose line to replace")
    CONFIG_PATH.write_text(new_text)
    print(f"Saved home pose to {CONFIG_PATH}:\n{line}")


if __name__ == "__main__":
    main()
