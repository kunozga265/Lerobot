"""Hand-over-mat detection (PLAN.md §5, INTEGRATION_PLAN.md step 3).

No model needed: a hand counts as "on the mat" when either
  - enough of the mat shows skin colour (YCrCb skin range; bars are too saturated to match), or
  - enough of the mat changed since the previous frame (a moving hand or sleeve).
The game only submits once the hand has been clear for `hand_clear_seconds` *and* the bar
count has been stable, so a hand briefly missed mid-move just delays submission.

MediaPipe Hands can be added behind `HandDetector.update` later if eval_counter.py shows
this isn't accurate enough. Tunable values live under `vision.hands` in config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import cv2
import numpy as np

# Commonly used skin range in YCrCb (works across skin tones better than HSV hue).
SKIN_LOW = (0, 133, 77)
SKIN_HIGH = (255, 173, 127)


@dataclass
class HandParams:
    skin_min_frac: float = 0.03  # fraction of the mat that must look like skin
    motion_min_frac: float = 0.04  # fraction of the mat that must have changed
    motion_pixel_threshold: int = 30  # grey-level change (0-255) that counts as "changed"

    @classmethod
    def from_config(cls, cfg: dict | None) -> "HandParams":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (cfg or {}).items() if k in known})


@dataclass
class HandReading:
    on_mat: bool
    skin_frac: float
    motion_frac: float


class HandDetector:
    def __init__(self, region: np.ndarray, params: HandParams):
        self.region = region  # polygon_mask of the mat
        self.params = params
        self._region_px = max(1, int(np.count_nonzero(region)))
        self._previous: np.ndarray | None = None

    def update(self, frame_bgr: np.ndarray) -> HandReading:
        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        skin = cv2.bitwise_and(cv2.inRange(ycrcb, SKIN_LOW, SKIN_HIGH), self.region)
        skin_frac = np.count_nonzero(skin) / self._region_px

        grey = cv2.GaussianBlur(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        motion_frac = 0.0
        if self._previous is not None and self._previous.shape == grey.shape:
            diff = cv2.absdiff(grey, self._previous)
            changed = cv2.bitwise_and((diff >= self.params.motion_pixel_threshold).astype(np.uint8) * 255, self.region)
            motion_frac = np.count_nonzero(changed) / self._region_px
        self._previous = grey

        on_mat = skin_frac >= self.params.skin_min_frac or motion_frac >= self.params.motion_min_frac
        return HandReading(on_mat, skin_frac, motion_frac)
