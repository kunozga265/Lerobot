"""Answer-mat vision on synthetic frames: a dark mat with coloured bars drawn on it."""

import numpy as np
import pytest

from app.hardware import HardwareError, build_hardware
from app.vision.counter import MatParams, check_polygon_fits, count_bars, polygon_mask
from app.vision.hands import HandDetector, HandParams
from app.vision.live_vision import LiveVision

H, W = 480, 640
MAT = np.array([[100, 100], [540, 100], [540, 400], [100, 400]], dtype=np.int32)
MAT_GREY = (25, 25, 25)
# BGR bar colours matching the physical bars: red, blue, green, yellow
COLOURS = [(40, 40, 220), (200, 60, 30), (50, 180, 40), (30, 210, 230)]
BAR_W, BAR_L = 14, 160
SKIN = [(140, 170, 220), (60, 85, 130)]  # a light and a darker skin tone, BGR


def mat_frame():
    frame = np.full((H, W, 3), 235, dtype=np.uint8)  # white table around the mat
    frame[100:401, 100:541] = MAT_GREY
    return frame


def draw_bar(frame, x, y=160, colour=COLOURS[0]):
    frame[y : y + BAR_L, x : x + BAR_W] = colour


def frame_with_bars(xs):
    frame = mat_frame()
    for i, x in enumerate(xs):
        draw_bar(frame, x, colour=COLOURS[i % len(COLOURS)])
    return frame


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4])
def test_counts_separated_bars(n):
    frame = frame_with_bars([150 + 60 * i for i in range(n)])
    assert count_bars(frame, MAT, MatParams()).count == n


def test_touching_bars_split_by_width():
    frame = mat_frame()
    for i in range(3):  # three bars side by side with no gap
        draw_bar(frame, 200 + BAR_W * i, colour=COLOURS[i])

    assert count_bars(frame, MAT, MatParams()).count == 1  # no bar width configured: one blob
    assert count_bars(frame, MAT, MatParams(bar_width_px=BAR_W)).count == 3


def test_ignores_bars_off_the_mat_and_small_noise():
    frame = frame_with_bars([200])
    draw_bar(frame, 20)  # on the white table, outside the mat
    frame[300:304, 400:404] = COLOURS[1]  # a coloured crumb on the mat

    assert count_bars(frame, MAT, MatParams()).count == 1


def test_polygon_from_another_resolution_is_rejected():
    # The real config had a 1080p mat outline while cameras were switched to 640x480.
    polygon_1080p = np.array([[1170, 89], [1752, 86], [1746, 840], [1181, 850]])
    with pytest.raises(ValueError, match="re-run scripts/calibrate_board.py"):
        check_polygon_fits(polygon_1080p, (H, W, 3))
    check_polygon_fits(MAT, (H, W, 3))  # fits: no error


@pytest.mark.parametrize("skin", SKIN)
def test_hand_detected_from_skin(skin):
    detector = HandDetector(polygon_mask((H, W), MAT), HandParams())
    frame = mat_frame()
    detector.update(frame)
    frame[250:400, 250:350] = skin  # a still hand resting on the mat

    assert detector.update(frame).on_mat
    assert detector.update(frame).on_mat  # still there when not moving


def test_bars_alone_are_not_a_hand():
    detector = HandDetector(polygon_mask((H, W), MAT), HandParams())
    frame = frame_with_bars([150, 210, 270, 330])
    detector.update(frame)

    assert not detector.update(frame).on_mat


def test_hand_detected_from_motion():
    detector = HandDetector(polygon_mask((H, W), MAT), HandParams(skin_min_frac=1.0))  # motion only
    frame = mat_frame()
    detector.update(frame)
    moved = frame.copy()
    moved[150:350, 150:300] = (90, 90, 90)  # a grey sleeve sweeping over the mat

    assert detector.update(moved).on_mat


class FakeCameras:
    def __init__(self, frame):
        self.frame = frame

    def get_frame(self, name):
        return self.frame


def live_config(mat=MAT):
    return {"vision": {"rois": {"mat_camera_px": mat.tolist()}, "smoothing_seconds": 1.0}}


def test_live_vision_smooths_flicker_with_the_most_common_count():
    vision = LiveVision(FakeCameras(None), live_config())
    two, three = frame_with_bars([150, 250]), frame_with_bars([150, 250, 350])
    t = 0.0
    for frame in [two, two, three, two, two]:  # one flickering frame
        state = vision.process(frame, t)
        t += 0.1

    assert state.bars == 2
    assert state.stable is False  # the window still holds the flicker

    for _ in range(12):  # >1 s of steady frames pushes it out of the window
        state = vision.process(two, t)
        t += 0.1
    assert state.bars == 2 and state.stable is True
    assert vision.get_state() is state


def test_build_hardware_live_vision_rejects_wrong_resolution_calibration(monkeypatch):
    class Cameras:
        def __init__(self, indices, **_):
            self.indices = indices

        def open(self):
            return {name: True for name in self.indices}

        def start(self):
            pass

        def stop(self):
            pass

        def get_frame(self, name):
            return mat_frame()  # 640x480

    monkeypatch.setattr("app.vision.cameras.CameraManager", Cameras)
    polygon_1080p = np.array([[1170, 89], [1752, 86], [1746, 840], [1181, 850]])
    config = {
        "robot": {"mode": "mock"},
        "vision": {"mode": "live", "rois": {"mat_camera_px": polygon_1080p.tolist()}},
        "cameras": {"overhead": 1, "wrist": 0},
    }

    with pytest.raises(HardwareError, match="calibrate_board"):
        build_hardware(config)
