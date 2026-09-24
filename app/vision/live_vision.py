"""Real answer-mat vision: same `get_state() -> BoardState` interface as MockVision.

Runs on its own thread at `vision.fps` (default 10), reading the overhead frame from the
shared CameraManager. `bars` is the most common count over the last `smoothing_seconds`
so a flickering blob doesn't reset the engine's "count stable" timer. The boxes are never
counted (the game takes the sum from the robot commands), so left/right/margin stay 0.

Built by app/hardware.py when `vision.mode: live`.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque

from app.hardware import HardwareError
from app.vision.board_state import BoardState
from app.vision.counter import MatParams, check_polygon_fits, count_bars, mat_polygon, polygon_mask
from app.vision.hands import HandDetector, HandParams

FIRST_FRAME_TIMEOUT_S = 3.0


class LiveVision:
    def __init__(self, cameras, config: dict, camera_name: str = "overhead"):
        vision_cfg = config["vision"]
        self.cameras = cameras
        self.camera_name = camera_name
        self.polygon = mat_polygon(vision_cfg)
        self.mat_params = MatParams.from_config(vision_cfg.get("mat"))
        self.hand_params = HandParams.from_config(vision_cfg.get("hands"))
        self.fps = vision_cfg.get("fps", 10)
        self.smoothing_seconds = vision_cfg.get("smoothing_seconds", 1.0)

        self._region = None
        self._hands: HandDetector | None = None
        self._history: deque[tuple[float, int]] = deque()
        self._state = BoardState(0, 0, 0, 0, False, time.time(), False)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        frame = self._wait_for_frame()
        try:
            check_polygon_fits(self.polygon, frame.shape)
        except ValueError as e:
            raise HardwareError(str(e)) from e
        self._region = polygon_mask(frame.shape, self.polygon)
        self._hands = HandDetector(self._region, self.hand_params)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_state(self) -> BoardState:
        with self._lock:
            return self._state

    # --- internals ---------------------------------------------------------
    def _wait_for_frame(self):
        deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_S
        while time.monotonic() < deadline:
            frame = self.cameras.get_frame(self.camera_name)
            if frame is not None:
                return frame
            time.sleep(0.05)
        raise HardwareError(f"No image from the {self.camera_name} camera after {FIRST_FRAME_TIMEOUT_S:.0f} s.")

    def _loop(self) -> None:
        period = 1.0 / self.fps
        while not self._stop.is_set():
            tick = time.monotonic()
            frame = self.cameras.get_frame(self.camera_name)
            if frame is not None:
                self.process(frame, tick)
            time.sleep(max(0.0, period - (time.monotonic() - tick)))

    def process(self, frame, now: float) -> BoardState:
        """One vision step; public so tests and scripts can feed frames directly."""
        if self._region is None or self._region.shape != frame.shape[:2]:
            self._region = polygon_mask(frame.shape, self.polygon)
            self._hands = HandDetector(self._region, self.hand_params)
        bars = count_bars(frame, self.polygon, self.mat_params, self._region).count
        hand = self._hands.update(frame).on_mat

        self._history.append((now, bars))
        while self._history and self._history[0][0] < now - self.smoothing_seconds:
            self._history.popleft()
        counts = Counter(c for _, c in self._history)
        smoothed = counts.most_common(1)[0][0]
        state = BoardState(
            left=0,
            right=0,
            margin=0,
            bars=smoothed,
            hand_on_mat=hand,
            timestamp=time.time(),
            stable=len(counts) == 1,
        )
        with self._lock:
            self._state = state
        return state
