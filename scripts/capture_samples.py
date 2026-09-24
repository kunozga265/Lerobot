"""Capture labelled overhead frames for tuning and measuring the answer-mat counter.

    pipenv run python scripts/capture_samples.py

Keys in the preview window:
  0-4    set the true number of bars on the mat
  h      toggle the "hand on mat" label
  space  save the current frame with its labels
  q      quit

Frames go to data/vision_eval/ and labels to data/vision_eval/labels.csv. Aim for 100+
frames: every count 0-4, bars apart and touching, all colours, hands on/at the edge/away.
Keep the ring light as it will be at the demo.
"""

from __future__ import annotations

import csv
import datetime

import cv2

from _vision_common import EVAL_DIR, LABELS_CSV, load_config, open_overhead

WINDOW = "capture samples (0-4 bars, h hand, space save, q quit)"


def main() -> None:
    config = load_config()
    cameras, _, polygon = open_overhead(config)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not LABELS_CSV.exists()
    bars, hand, saved = 0, False, 0
    try:
        with LABELS_CSV.open("a", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(["file", "bars", "hand"])
            while True:
                frame = cameras.get_frame("overhead")
                if frame is None:
                    cv2.waitKey(30)
                    continue
                view = frame.copy()
                cv2.polylines(view, [polygon], True, (255, 0, 255), 2)
                cv2.putText(view, f"label: bars={bars} hand={'yes' if hand else 'no'}   saved: {saved}",
                            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.imshow(WINDOW, view)
                key = cv2.waitKey(30) & 0xFF
                if key == ord("q"):
                    break
                if ord("0") <= key <= ord("4"):
                    bars = key - ord("0")
                elif key == ord("h"):
                    hand = not hand
                elif key == ord(" "):
                    name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".png"
                    cv2.imwrite(str(EVAL_DIR / name), frame)
                    writer.writerow([name, bars, int(hand)])
                    f.flush()
                    saved += 1
    finally:
        cameras.stop()
        cv2.destroyAllWindows()
    print(f"Saved {saved} frames to {EVAL_DIR}")


if __name__ == "__main__":
    main()
