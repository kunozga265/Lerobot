"""Answer-bar counter for the black mat (PLAN.md §5, INTEGRATION_PLAN.md step 3).

Bars are brightly coloured cylinders on a dark mat, so a pixel belongs to a bar when it is
both saturated and bright in HSV. Inside the calibrated mat polygon we threshold, clean
up with a morphological open/close, and count contours. Bars laid side by side merge into
one blob; its short side divided by one bar's width says how many bars it holds.

Tunable values live in config.yaml under `vision.mat` (all optional; defaults below).
Tune them live with scripts/test_counter.py and check accuracy with scripts/eval_counter.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

import cv2
import numpy as np


@dataclass
class MatParams:
    sat_min: int = 80  # HSV saturation (0-255) a bar pixel must reach; the mat is grey/black
    val_min: int = 70  # HSV brightness (0-255); dark blue bars may need this lower
    min_bar_area_px: int = 150  # blobs smaller than this are noise (crumbs, glare)
    morph_kernel_px: int = 5  # open/close kernel; larger merges gaps, smaller keeps noise
    bar_width_px: float | None = None  # one bar's width, to split touching bars; None = no splitting

    @classmethod
    def from_config(cls, cfg: dict | None) -> "MatParams":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (cfg or {}).items() if k in known})


@dataclass
class Blob:
    contour: np.ndarray
    area: float
    short_side: float  # of the rotated bounding rectangle, in px
    long_side: float
    bars: int  # how many bars this blob is counted as


@dataclass
class BarCount:
    count: int
    blobs: list[Blob] = field(default_factory=list)
    mask: np.ndarray | None = None  # final binary mask, for debug overlays


def mat_polygon(config_vision: dict) -> np.ndarray:
    """The mat outline in camera pixels, from calibrate_board.py (`rois.mat_camera_px`)."""
    points = config_vision.get("rois", {}).get("mat_camera_px")
    if not points:
        raise ValueError("config.yaml has no vision.rois.mat_camera_px; run scripts/calibrate_board.py")
    return np.asarray(points, dtype=np.int32)


def check_polygon_fits(polygon: np.ndarray, frame_shape: tuple[int, ...]) -> None:
    """Fail loudly if the calibration was made at a different camera resolution: a mat
    outline outside the frame would silently count nothing."""
    height, width = frame_shape[:2]
    xs, ys = polygon[:, 0], polygon[:, 1]
    if xs.min() < 0 or ys.min() < 0 or xs.max() >= width or ys.max() >= height:
        raise ValueError(
            f"The calibrated mat outline (x up to {xs.max()}, y up to {ys.max()}) doesn't fit the "
            f"{width}x{height} overhead frame. The calibration was made at another resolution: "
            "re-run scripts/calibrate_board.py with the current cameras.width/height."
        )


def polygon_mask(frame_shape: tuple[int, ...], polygon: np.ndarray) -> np.ndarray:
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [polygon.astype(np.int32)], 255)
    return mask


def colour_mask(frame_bgr: np.ndarray, params: MatParams) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (0, params.sat_min, params.val_min), (179, 255, 255))


def count_bars(
    frame_bgr: np.ndarray,
    polygon: np.ndarray,
    params: MatParams,
    region: np.ndarray | None = None,
) -> BarCount:
    """Count answer bars inside `polygon`. Pass a precomputed `region` (polygon_mask) when
    calling every frame to skip redrawing it."""
    if region is None:
        region = polygon_mask(frame_bgr.shape, polygon)
    mask = cv2.bitwise_and(colour_mask(frame_bgr, params), region)
    if params.morph_kernel_px > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (params.morph_kernel_px, params.morph_kernel_px))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < params.min_bar_area_px:
            continue
        (_, _), (w, h), _ = cv2.minAreaRect(contour)
        short_side, long_side = sorted((w, h))
        bars = 1
        if params.bar_width_px:
            bars = max(1, round(short_side / params.bar_width_px))
        blobs.append(Blob(contour, area, short_side, long_side, bars))
    return BarCount(sum(b.bars for b in blobs), blobs, mask)


def draw_overlay(frame_bgr: np.ndarray, polygon: np.ndarray, result: BarCount, hand: bool | None = None) -> np.ndarray:
    """Debug view: mat outline, each blob with its bar count and width, and the totals."""
    out = frame_bgr.copy()
    cv2.polylines(out, [polygon.astype(np.int32)], True, (255, 0, 255), 2)
    for blob in result.blobs:
        cv2.drawContours(out, [blob.contour], -1, (0, 255, 0), 2)
        x, y, _, _ = cv2.boundingRect(blob.contour)
        cv2.putText(out, f"{blob.bars} (w{blob.short_side:.0f})", (x, max(12, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    text = f"bars: {result.count}"
    if hand is not None:
        text += f"   hand: {'ON MAT' if hand else 'clear'}"
    cv2.putText(out, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return out
