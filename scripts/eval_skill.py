"""INTEGRATION_PLAN.md step 2: trial a trained skill on the real arm through the *game's*
controller (LeRobotController + CameraManager), so the result also covers the camera
resize/colour path the game uses (step 6), not just lerobot's own rollout.

    pipenv run python scripts/eval_skill.py left 20
    pipenv run python scripts/eval_skill.py right 20

Before each trial set up the margin/box (alternate: box empty / one piece already in),
press Enter, watch, then answer whether the piece ended up inside the box. Results are
appended to training/eval_results.csv.
"""

from __future__ import annotations

import csv
import datetime
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hardware import build_hardware  # noqa: E402

RESULTS = ROOT / "training" / "eval_results.csv"


def main() -> None:
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in ("left", "right"):
        print(__doc__)
        sys.exit(2)
    box = sys.argv[1]
    trials = int(sys.argv[2]) if len(sys.argv) == 3 else 20

    config = yaml.safe_load((ROOT / "app" / "config.yaml").read_text())
    config["robot"]["mode"] = "lerobot"
    config["vision"]["mode"] = "mock"  # only the cameras are needed, for the policy
    hardware = build_hardware(config)
    robot = hardware.robot
    successes = 0
    try:
        for trial in range(1, trials + 1):
            variant = "empty box" if trial % 2 else "one piece already in the box"
            input(f"\n[{trial}/{trials}] Set up: {variant}. Press Enter to run place_{box}...")
            finished_home = robot.place_to(box)
            answer = input(f"  arm {'returned home' if finished_home else 'did NOT get home'}. Piece inside the box? [y/n] ")
            success = answer.strip().lower().startswith("y")
            successes += success
            RESULTS.parent.mkdir(exist_ok=True)
            is_new = not RESULTS.exists()
            with RESULTS.open("a", newline="") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow(["timestamp", "skill", "policy", "trial", "variant", "finished_home", "success"])
                writer.writerow([
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    f"place_{box}",
                    config["robot"]["policies"][box]["path"],
                    trial,
                    variant,
                    finished_home,
                    success,
                ])
            print(f"  running success rate: {successes}/{trial} ({successes / trial:.0%})")
    except KeyboardInterrupt:
        robot.stop(emergency=True)
        print("\nStopped (torque off).")
    finally:
        hardware.close()
    print(f"\nplace_{box}: {successes}/{trials} (target: at least 80% on the first attempt)")


if __name__ == "__main__":
    main()
