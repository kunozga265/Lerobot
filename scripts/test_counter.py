"""Live answer-mat counter with overlays and sliders, for tuning `vision.mat` / `vision.hands`.

    pipenv run python scripts/test_counter.py

Sliders change the thresholds live. Blob labels show each blob's bar count and its width
("w14"): lay ONE bar on the mat and read its width to set bar_width. Press p to print
the values as YAML for config.yaml, q to quit.
"""

from __future__ import annotations

import cv2
import yaml

from _vision_common import load_config, open_overhead
from app.vision.counter import MatParams, count_bars, draw_overlay, polygon_mask
from app.vision.hands import HandDetector, HandParams

WINDOW = "answer-mat counter (p print config, q quit)"


def main() -> None:
    config = load_config()
    cameras, frame, polygon = open_overhead(config)
    mat = MatParams.from_config(config["vision"].get("mat"))
    hand_params = HandParams.from_config(config["vision"].get("hands"))
    region = polygon_mask(frame.shape, polygon)
    hands = HandDetector(region, hand_params)

    cv2.namedWindow(WINDOW)
    sliders = {
        "sat_min": (mat.sat_min, 255),
        "val_min": (mat.val_min, 255),
        "min_bar_area_px": (mat.min_bar_area_px, 3000),
        "morph_kernel_px": (mat.morph_kernel_px, 21),
        "bar_width_px (0=off)": (int(mat.bar_width_px or 0), 100),
        "skin_min_pct": (int(hand_params.skin_min_frac * 100), 50),
        "motion_min_pct": (int(hand_params.motion_min_frac * 100), 50),
    }
    for name, (value, maximum) in sliders.items():
        cv2.createTrackbar(name, WINDOW, value, maximum, lambda _: None)

    try:
        while True:
            frame = cameras.get_frame("overhead")
            if frame is None:
                cv2.waitKey(30)
                continue
            mat.sat_min = cv2.getTrackbarPos("sat_min", WINDOW)
            mat.val_min = cv2.getTrackbarPos("val_min", WINDOW)
            mat.min_bar_area_px = cv2.getTrackbarPos("min_bar_area_px", WINDOW)
            mat.morph_kernel_px = max(1, cv2.getTrackbarPos("morph_kernel_px", WINDOW))
            mat.bar_width_px = cv2.getTrackbarPos("bar_width_px (0=off)", WINDOW) or None
            hand_params.skin_min_frac = cv2.getTrackbarPos("skin_min_pct", WINDOW) / 100
            hand_params.motion_min_frac = max(1, cv2.getTrackbarPos("motion_min_pct", WINDOW)) / 100

            result = count_bars(frame, polygon, mat, region)
            reading = hands.update(frame)
            view = draw_overlay(frame, polygon, result, reading.on_mat)
            cv2.putText(view, f"skin {reading.skin_frac:.1%}  motion {reading.motion_frac:.1%}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
            mask_view = cv2.cvtColor(result.mask, cv2.COLOR_GRAY2BGR)
            cv2.imshow(WINDOW, cv2.hconcat([view, mask_view]))

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("p"):
                print(yaml.safe_dump({"vision": {
                    "mat": {k: getattr(mat, k) for k in ("sat_min", "val_min", "min_bar_area_px",
                                                        "morph_kernel_px", "bar_width_px")},
                    "hands": {"skin_min_frac": hand_params.skin_min_frac,
                              "motion_min_frac": hand_params.motion_min_frac},
                }}, sort_keys=False))
                print("Copy the mat: and hands: blocks under vision: in app/config.yaml.")
    finally:
        cameras.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
