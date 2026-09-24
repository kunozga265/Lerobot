"""Interactive board calibration, per PLAN.md §5.

Click the 4 corners of LEFT_BOX, then RIGHT_BOX, then the answer mat, on a live frame
from the overhead camera - each shape traced separately and independently, going
around its own corners in ANY order that doesn't skip across the shape (clockwise,
counterclockwise, starting wherever you like - it does not need to match the order
you used for the other two shapes; the tool searches all valid orderings and keeps
whichever fits best). You identify which taped box is "left" and which is "right";
nothing here guesses that from the camera's orientation, since a rotated/angled camera
mount makes on-screen left/right an unreliable stand-in for which box is which.

Only LEFT_BOX and RIGHT_BOX go through the homography fit, to a canonical board image
(LEFT_BOX to the left, RIGHT_BOX to the right of it). The mat is deliberately NOT
warped through that same homography: a homography assumes everything clicked is on
one flat plane, and if the mat sits at a different height than the taped table surface
(e.g. it has real thickness), forcing it into the box's homography distorts the whole
fit to compensate - which is what happened here in practice, not a clicking-precision
problem. The mat's 4 corners are instead stored as-is in camera-pixel coordinates
(`rois.mat_camera_px`), used directly against the raw camera frame rather than a
warped one.

Writes LEFT_BOX/RIGHT_BOX/MARGIN (board-pixel coordinates) and MAT (camera-pixel
coordinates - see above) into config.yaml's `vision:` section.

Usage: pipenv run python scripts/calibrate_board.py
Controls while the window is open:
  click   = place the next corner
  u       = undo the last point
  r       = restart the shape currently being clicked
  s       = save (only once all three shapes have 4 points each; refuses if the
            LEFT_BOX/RIGHT_BOX fit looks bad even after trying every corner ordering -
            see REPROJECTION_ERROR_LIMIT_PX)
  f       = force-save anyway despite a bad fit
  q / Esc = quit without saving

Re-run this whenever the overhead camera moves.
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # so `python scripts/calibrate_board.py` finds the `app` package

from app.vision.cameras import CameraManager  # noqa: E402

CONFIG_PATH = REPO_ROOT / "app" / "config.yaml"

# Board canvas layout: LEFT_BOX and RIGHT_BOX side by side. (The mat is NOT part of
# this canvas - see module docstring for why.) Each box is calibrated from its OWN 4
# clicked corners against its OWN fixed destination rectangle (fit together as one
# least-squares homography), rather than clicking one outer box rectangle and
# splitting it into left/right halves in code - that approach silently assumed
# on-screen left/right matched real left/right, which broke for a camera mounted at an
# angle where the box rectangle doesn't appear "landscape" on screen.
PAD_X = 200
PAD_Y = 150
BOX_WIDTH = 300
BOX_HEIGHT = 400
BOX_GAP = 60  # gap between LEFT_BOX and RIGHT_BOX
BOX_INSET = 15  # PLAN.md §5: "inset a few px from tape"

LEFT_BOX_DST = [
    (PAD_X, PAD_Y),
    (PAD_X + BOX_WIDTH, PAD_Y),
    (PAD_X + BOX_WIDTH, PAD_Y + BOX_HEIGHT),
    (PAD_X, PAD_Y + BOX_HEIGHT),
]
RIGHT_BOX_X = PAD_X + BOX_WIDTH + BOX_GAP
RIGHT_BOX_DST = [
    (RIGHT_BOX_X, PAD_Y),
    (RIGHT_BOX_X + BOX_WIDTH, PAD_Y),
    (RIGHT_BOX_X + BOX_WIDTH, PAD_Y + BOX_HEIGHT),
    (RIGHT_BOX_X, PAD_Y + BOX_HEIGHT),
]
BOARD_WIDTH = RIGHT_BOX_X + BOX_WIDTH + PAD_X
BOARD_HEIGHT = PAD_Y + BOX_HEIGHT + PAD_Y

WINDOW = "Calibrate board"
SHAPES = ["left_box", "right_box", "mat"]  # UI click-collection stages
HOMOGRAPHY_SHAPES = ["left_box", "right_box"]  # only these two are fit to board space
DST_BY_SHAPE = {"left_box": LEFT_BOX_DST, "right_box": RIGHT_BOX_DST}
SHAPE_COLORS = {"left_box": (0, 255, 0), "right_box": (0, 255, 255), "mat": (255, 0, 255)}
CORNER_LABELS = ["1", "2", "3", "4"]  # order doesn't need to match between shapes - see resolve_click_order

# If any clicked box corner, once warped through the fitted homography, lands more
# than this many board-pixels from where it should, the fit is almost certainly wrong
# - block saving rather than writing a silently-broken calibration. BOX_WIDTH is 300,
# so 40px is ~13% of a box's own width: enough slack for real click imprecision, tight
# enough to catch a genuinely bad fit.
REPROJECTION_ERROR_LIMIT_PX = 40.0


def _load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _write_vision_config(vision: dict) -> None:
    """Replace just the `vision:` block in config.yaml, leaving the rest of the file
    (including its comments) untouched - a full yaml round-trip would drop them."""
    text = CONFIG_PATH.read_text()
    match = re.search(r"^vision:.*", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise RuntimeError("config.yaml has no `vision:` key to replace")
    new_block = yaml.safe_dump({"vision": vision}, sort_keys=False, default_flow_style=None)
    CONFIG_PATH.write_text(text[: match.start()] + new_block)


def compute_homography(clicked: dict[str, list[tuple[float, float]]]) -> np.ndarray:
    """3x3 homography mapping camera-pixel coordinates to board-pixel coordinates,
    least-squares fit from the 8 clicked LEFT_BOX/RIGHT_BOX corners (already in an
    order consistent with DST_BY_SHAPE - see resolve_click_order) against their
    canonical destinations."""
    src = np.array([pt for name in HOMOGRAPHY_SHAPES for pt in clicked[name]], dtype=np.float32)
    dst = np.array([pt for name in HOMOGRAPHY_SHAPES for pt in DST_BY_SHAPE[name]], dtype=np.float32)
    homography, _ = cv2.findHomography(src, dst)
    return homography


def reprojection_error_px(homography: np.ndarray, clicked: dict[str, list[tuple[float, float]]]) -> float:
    """Worst-case distance, in board pixels, between a clicked LEFT_BOX/RIGHT_BOX
    corner (warped through `homography`) and where it should have landed."""
    worst = 0.0
    for name in HOMOGRAPHY_SHAPES:
        for src_pt, dst_pt in zip(clicked[name], DST_BY_SHAPE[name]):
            x, y, w = homography @ [src_pt[0], src_pt[1], 1]
            error = ((x / w - dst_pt[0]) ** 2 + (y / w - dst_pt[1]) ** 2) ** 0.5
            worst = max(worst, error)
    return worst


def _cyclic_variants(points: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """All 8 traversal-preserving orderings of 4 points already clicked in some
    consistent order around a shape (clockwise or counterclockwise, from any starting
    corner): the 4 rotations of that order, and the 4 rotations of its reverse. A
    rectangle looks the same from any of its 4 corners, so which of these 8 is
    "correct" isn't knowable from one shape in isolation - see resolve_click_order."""
    variants = []
    for base in (list(points), list(reversed(points))):
        for i in range(4):
            variants.append(base[i:] + base[:i])
    return variants


def resolve_click_order(
    clicked: dict[str, list[tuple[float, float]]],
) -> dict[str, list[tuple[float, float]]]:
    """Returns a copy of the LEFT_BOX/RIGHT_BOX entries of `clicked`, each reordered
    to whichever of its 8 valid traversals makes the combined 8-point homography fit
    best, searched jointly across both shapes (8**2 = 64 combinations, each a cheap
    homography fit)."""
    options = {name: _cyclic_variants(clicked[name]) for name in HOMOGRAPHY_SHAPES}
    dst_flat = np.array([pt for name in HOMOGRAPHY_SHAPES for pt in DST_BY_SHAPE[name]], dtype=np.float32)

    best_error = None
    best_combo = None
    for combo in itertools.product(*(options[name] for name in HOMOGRAPHY_SHAPES)):
        src_flat = np.array([pt for shape_points in combo for pt in shape_points], dtype=np.float32)
        homography, _ = cv2.findHomography(src_flat, dst_flat)
        if homography is None:
            continue
        error = 0.0
        for src_pt, dst_pt in zip(src_flat, dst_flat):
            x, y, w = homography @ [src_pt[0], src_pt[1], 1]
            error = max(error, ((x / w - dst_pt[0]) ** 2 + (y / w - dst_pt[1]) ** 2) ** 0.5)
        if best_error is None or error < best_error:
            best_error, best_combo = error, combo

    return dict(zip(HOMOGRAPHY_SHAPES, best_combo))


def compute_rois(mat_camera_px: list[tuple[float, float]]) -> dict:
    """LEFT_BOX/RIGHT_BOX/MARGIN in board-pixel coordinates (fixed rectangles
    determined by the canonical layout, since that's what `compute_homography` fits
    the camera frame *to*); MAT in raw camera-pixel coordinates, unwarped - see module
    docstring for why the mat doesn't go through the box homography.

    `margin` is deliberately the full board canvas rather than a hand-carved band:
    Phase 3's counter.py is what actually tallies pieces per region, and it's simpler
    for it to exclude the box overlap when counting margin pieces than for this script
    to guess a band shape that may not match the real margin layout.
    """
    left_box = [PAD_X + BOX_INSET, PAD_Y + BOX_INSET, PAD_X + BOX_WIDTH - BOX_INSET, PAD_Y + BOX_HEIGHT - BOX_INSET]
    right_box = [
        RIGHT_BOX_X + BOX_INSET,
        PAD_Y + BOX_INSET,
        RIGHT_BOX_X + BOX_WIDTH - BOX_INSET,
        PAD_Y + BOX_HEIGHT - BOX_INSET,
    ]
    margin = [0, 0, BOARD_WIDTH, BOARD_HEIGHT]

    return {
        "left_box": [round(v) for v in left_box],
        "right_box": [round(v) for v in right_box],
        "margin": margin,
        "mat_camera_px": [[round(x), round(y)] for x, y in mat_camera_px],
    }


class _ClickCollector:
    def __init__(self, frame: np.ndarray):
        self.base_frame = frame
        self.points: dict[str, list[tuple[int, int]]] = {name: [] for name in SHAPES}

    @property
    def stage(self) -> str:
        for name in SHAPES:
            if len(self.points[name]) < 4:
                return name
        return "done"

    def on_click(self, event, x, y, flags, param) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        stage = self.stage
        if stage != "done":
            self.points[stage].append((x, y))

    def undo(self) -> None:
        for name in reversed(SHAPES):
            if self.points[name]:
                self.points[name].pop()
                return

    def reset_current_shape(self) -> None:
        stage = self.stage
        if stage != "done":
            self.points[stage].clear()

    def render(self) -> np.ndarray:
        frame = self.base_frame.copy()
        for name in SHAPES:
            self._draw_shape(frame, self.points[name], SHAPE_COLORS[name], name.upper())

        stage = self.stage
        if stage == "done":
            prompt = "All 3 shapes done - press 's' to save, 'r' to redo current, 'q' to quit"
        else:
            n = len(self.points[stage])
            prompt = f"Click {stage.upper().replace('_', ' ')} corner {n + 1}/4 (any order, just go around the shape)"
        cv2.putText(frame, prompt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(
            frame, "u=undo  r=redo shape  s=save  f=force-save  q=quit", (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA,
        )
        return frame

    @staticmethod
    def _draw_shape(frame: np.ndarray, points: list[tuple[int, int]], color: tuple, label: str) -> None:
        for i, (x, y) in enumerate(points):
            cv2.circle(frame, (x, y), 6, color, -1)
            cv2.putText(
                frame, f"{label}-{CORNER_LABELS[i]}", (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA,
            )
        if len(points) > 1:
            cv2.polylines(frame, [np.array(points, dtype=np.int32)], len(points) == 4, color, 2)


def main() -> None:
    config = _load_config()
    overhead_index = config["cameras"]["overhead"]
    if overhead_index is None:
        print("config.yaml: cameras.overhead is not set. Set it, then re-run.")
        return

    cam_cfg = config["cameras"]
    # Same capture size as the game (config cameras.width/height): the mat ROI is in these pixels.
    manager = CameraManager(
        {"overhead": overhead_index},
        width=cam_cfg.get("width", 1920),
        height=cam_cfg.get("height", 1080),
    )
    if not manager.open().get("overhead"):
        print(f"Could not open the overhead camera at index {overhead_index}.")
        return

    frame = None
    for _ in range(10):  # let auto-exposure/white-balance settle before the frame we calibrate against
        frame = manager.grab_single_frame("overhead")
    manager.stop()

    if frame is None:
        print("Could not grab a frame from the overhead camera.")
        return

    collector = _ClickCollector(frame)
    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, collector.on_click)
    print(__doc__)

    while True:
        cv2.imshow(WINDOW, collector.render())
        key = cv2.waitKey(30) & 0xFF
        if key in (27, ord("q")):
            print("Cancelled - config.yaml not changed.")
            break
        if key == ord("u"):
            collector.undo()
        elif key == ord("r"):
            collector.reset_current_shape()
        elif key in (ord("s"), ord("f")) and collector.stage == "done":
            resolved = resolve_click_order(collector.points)
            homography = compute_homography(resolved)
            error = reprojection_error_px(homography, resolved)
            print(f"Worst-case reprojection error: {error:.1f} board-px (limit {REPROJECTION_ERROR_LIMIT_PX:.0f})")

            if error > REPROJECTION_ERROR_LIMIT_PX and key == ord("s"):
                print(
                    "LEFT_BOX/RIGHT_BOX fit looks bad even after trying every corner "
                    "ordering - likely a mis-click. Press 'r' to redo a shape, or 'f' "
                    "to save anyway if you're confident this is fine."
                )
                continue

            vision = {
                **config.get("vision", {}),  # keep non-calibration keys (e.g. vision.mode)
                "board_width": BOARD_WIDTH,
                "board_height": BOARD_HEIGHT,
                "homography": [[round(v, 6) for v in row] for row in homography.tolist()],
                "rois": compute_rois(collector.points["mat"]),
            }
            _write_vision_config(vision)
            print(f"Saved calibration to {CONFIG_PATH}")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
