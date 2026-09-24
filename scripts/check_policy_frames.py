"""INTEGRATION_PLAN.md step 6: does the game's camera frame look like what the policy
was trained on?

The policies saw 640x480 frames from lerobot's own camera capture. In the game,
CameraManager captures at cameras.width x cameras.height (1920x1080) and LeRobotController
resizes down. If the camera's 640x480 mode is a *crop* rather than a scale, the two images
differ in field of view and the policy will fail. This saves a side-by-side image per
camera (training frame | game frame) so you can check by eye.

    pipenv run python scripts/check_policy_frames.py honestogarrido/place_left_20260923_174813
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vision.cameras import CameraManager  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "app" / "config.yaml"
OUT_DIR = Path("data/policy_frame_check")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    repo_id = sys.argv[1]
    config = yaml.safe_load(CONFIG_PATH.read_text())
    cam_cfg = config["cameras"]
    size = (config["robot"]["policies"]["image_width"], config["robot"]["policies"]["image_height"])

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    sample = LeRobotDataset(repo_id, episodes=[0])[0]

    cameras = CameraManager(
        {name: cam_cfg[name] for name in ("overhead", "wrist")},
        width=cam_cfg.get("width", 1920),
        height=cam_cfg.get("height", 1080),
    )
    opened = cameras.open()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for name in ("overhead", "wrist"):
            key = f"observation.images.{name}"
            if key not in sample or not opened.get(name):
                print(f"{name}: skipped (in dataset: {key in sample}, camera open: {opened.get(name)})")
                continue
            trained = (sample[key].permute(1, 2, 0).numpy() * 255).astype(np.uint8)  # CHW float RGB -> HWC
            trained = cv2.cvtColor(trained, cv2.COLOR_RGB2BGR)
            for _ in range(10):  # let exposure settle
                live = cameras.grab_single_frame(name)
            if live is None:
                print(f"{name}: no frame from camera")
                continue
            print(f"{name}: training frame {trained.shape[1]}x{trained.shape[0]}, game capture {live.shape[1]}x{live.shape[0]}")
            game = cv2.resize(live, size, interpolation=cv2.INTER_AREA)
            trained = cv2.resize(trained, size, interpolation=cv2.INTER_AREA)
            side_by_side = np.hstack([trained, game])
            cv2.putText(side_by_side, "training", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(side_by_side, "game (resized)", (size[0] + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            out = OUT_DIR / f"{name}.png"
            cv2.imwrite(str(out), side_by_side)
            print(f"  saved {out}")
    finally:
        cameras.stop()
    print(
        "\nOpen the PNGs. Same view on both sides -> keep cameras.width/height as they are.\n"
        "Game side shows MORE of the table (training was cropped) -> set cameras.width: 640,\n"
        "height: 480 in config.yaml and re-run scripts/calibrate_board.py."
    )


if __name__ == "__main__":
    main()
