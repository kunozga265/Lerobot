import time
from unittest.mock import patch

import numpy as np

from app.vision.cameras import CameraManager


class FakeCapture:
    def __init__(self, index):
        self.index = index
        self.opened = index != 99  # index 99 simulates a camera that fails to open
        self.released = False
        self.read_count = 0

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        pass

    def read(self):
        self.read_count += 1
        frame = np.full((4, 4, 3), self.read_count, dtype=np.uint8)
        return True, frame

    def release(self):
        self.released = True


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_open_reports_success_per_camera(mock_ctor):
    manager = CameraManager({"overhead": 0, "wrist": 1})
    results = manager.open()
    assert results == {"overhead": True, "wrist": True}


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_open_reports_failure_for_camera_that_wont_open(mock_ctor):
    manager = CameraManager({"overhead": 99, "wrist": 1})
    results = manager.open()
    assert results == {"overhead": False, "wrist": True}
    assert manager.get_frame("overhead") is None  # never opened, no frames possible


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_start_grabs_frames_in_background(mock_ctor):
    manager = CameraManager({"overhead": 0, "wrist": 1}, fps=100)
    manager.open()
    manager.start()
    try:
        deadline = time.monotonic() + 2.0
        while manager.get_frame("overhead") is None and time.monotonic() < deadline:
            time.sleep(0.01)
        frame = manager.get_frame("overhead")
        assert frame is not None
        assert frame.shape == (4, 4, 3)
    finally:
        manager.stop()


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_get_frame_returns_a_copy_not_the_live_buffer(mock_ctor):
    manager = CameraManager({"overhead": 0, "wrist": 1}, fps=100)
    manager.open()
    manager.start()
    try:
        deadline = time.monotonic() + 2.0
        while manager.get_frame("overhead") is None and time.monotonic() < deadline:
            time.sleep(0.01)
        frame = manager.get_frame("overhead")
        frame[:] = 255  # mutate the copy
        frame2 = manager.get_frame("overhead")
        assert not np.array_equal(frame, frame2)  # the live buffer wasn't touched
    finally:
        manager.stop()


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_stop_releases_captures_and_clears_frames(mock_ctor):
    manager = CameraManager({"overhead": 0, "wrist": 1}, fps=100)
    manager.open()
    manager.start()
    time.sleep(0.05)
    manager.stop()

    assert manager.get_frame("overhead") is None
    assert manager.get_frame("wrist") is None


@patch("app.vision.cameras.cv2.VideoCapture", side_effect=FakeCapture)
def test_grab_single_frame_reads_directly_without_background_thread(mock_ctor):
    manager = CameraManager({"overhead": 0, "wrist": 1})
    manager.open()
    frame = manager.grab_single_frame("overhead")
    assert frame is not None
    assert frame.shape == (4, 4, 3)
