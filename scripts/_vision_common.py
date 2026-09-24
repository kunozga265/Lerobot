"""Shared setup for the answer-mat vision scripts: config, overhead camera, mat outline."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.vision.cameras import CameraManager  # noqa: E402
from app.vision.counter import check_polygon_fits, mat_polygon  # noqa: E402

CONFIG_PATH = ROOT / "app" / "config.yaml"
EVAL_DIR = ROOT / "data" / "vision_eval"
LABELS_CSV = EVAL_DIR / "labels.csv"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def open_overhead(config: dict):
    """Open only the overhead camera at the game's capture size, and return
    (camera manager, first frame, mat polygon). Exits with a clear message on problems."""
    cam_cfg = config["cameras"]
    cameras = CameraManager(
        {"overhead": cam_cfg["overhead"]},
        width=cam_cfg.get("width", 1920),
        height=cam_cfg.get("height", 1080),
        fps=cam_cfg.get("fps", 30),
    )
    if not cameras.open().get("overhead"):
        sys.exit(f"Could not open the overhead camera (index {cam_cfg['overhead']}).")
    cameras.start()
    frame = None
    for _ in range(10):  # let exposure settle
        frame = cameras.grab_single_frame("overhead")
    if frame is None:
        cameras.stop()
        sys.exit("No image from the overhead camera.")
    polygon = mat_polygon(config["vision"])
    try:
        check_polygon_fits(polygon, frame.shape)
    except ValueError as e:
        cameras.stop()
        sys.exit(str(e))
    return cameras, frame, polygon
