"""Accuracy of the answer-mat counter on the labelled frames from capture_samples.py.

    pipenv run python scripts/eval_counter.py

Uses the current `vision.mat` / `vision.hands` settings in config.yaml. Target: at least
95% for bars and for hands (INTEGRATION_PLAN.md step 3). Hands are judged from single
frames, so only the skin check applies here (motion needs consecutive frames).
Failures are listed so you can open those images and adjust thresholds.
"""

from __future__ import annotations

import csv
import sys

import cv2

from _vision_common import EVAL_DIR, LABELS_CSV, load_config
from app.vision.counter import MatParams, check_polygon_fits, count_bars, mat_polygon, polygon_mask
from app.vision.hands import HandDetector, HandParams

TARGET = 0.95


def main() -> None:
    if not LABELS_CSV.exists():
        sys.exit(f"No labels at {LABELS_CSV}; run scripts/capture_samples.py first.")
    config = load_config()
    polygon = mat_polygon(config["vision"])
    mat = MatParams.from_config(config["vision"].get("mat"))
    hand_params = HandParams.from_config(config["vision"].get("hands"))

    rows = list(csv.DictReader(LABELS_CSV.open()))
    bar_ok = bar_scored = hand_ok = 0
    bar_fail, hand_fail = [], []
    for row in rows:
        frame = cv2.imread(str(EVAL_DIR / row["file"]))
        if frame is None:
            sys.exit(f"Missing image {row['file']}")
        check_polygon_fits(polygon, frame.shape)
        region = polygon_mask(frame.shape, polygon)
        got_bars = count_bars(frame, polygon, mat, region).count
        got_hand = HandDetector(region, hand_params).update(frame).on_mat
        want_bars, want_hand = int(row["bars"]), bool(int(row["hand"]))
        if not want_hand:  # counts under a hand don't matter: the game waits for the hand to leave
            bar_scored += 1
            if got_bars == want_bars:
                bar_ok += 1
            else:
                bar_fail.append(f"{row['file']}: counted {got_bars}, labelled {want_bars}")
        if got_hand == want_hand:
            hand_ok += 1
        else:
            hand_fail.append(f"{row['file']}: detected {'hand' if got_hand else 'no hand'}, labelled {'hand' if want_hand else 'no hand'}")

    n = len(rows)
    print(f"{n} frames")
    bar_acc = bar_ok / bar_scored if bar_scored else 0.0
    print(f"bars:  {bar_ok}/{bar_scored} = {bar_acc:.1%}  (frames without a hand)")
    print(f"hands: {hand_ok}/{n} = {hand_ok / n:.1%}")
    for line in bar_fail + hand_fail:
        print("  FAIL", line)
    ok = bar_acc >= TARGET and hand_ok / n >= TARGET
    print("PASS" if ok else f"Below the {TARGET:.0%} target: tune with scripts/test_counter.py")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
