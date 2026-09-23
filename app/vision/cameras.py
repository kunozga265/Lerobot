"""CameraManager per PLAN.md §3/§5: owns both cameras, grabs frames on a background
thread, and shares the latest frame per camera. macOS only allows one process to hold
a given camera open, so this is the single place in the app that touches cv2.VideoCapture."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

CameraName = str  # "overhead" | "wrist"


class CameraManager:
    def __init__(self, indices: dict[CameraName, int], width: int = 1920, height: int = 1080, fps: int = 30):
        self._indices = dict(indices)
        self._width = width
        self._height = height
        self._fps = fps
        self._captures: dict[CameraName, cv2.VideoCapture] = {}
        self._frames: dict[CameraName, np.ndarray | None] = dict.fromkeys(indices)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def open(self) -> dict[CameraName, bool]:
        """Open every configured camera. Returns success per camera name; callers should
        show a clear error (PLAN.md §6) for any name that comes back False rather than
        silently continuing without that feed."""
        results: dict[CameraName, bool] = {}
        for name, index in self._indices.items():
            cap = cv2.VideoCapture(index)
            if self._width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            if self._height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            ok = cap.isOpened()
            results[name] = ok
            if ok:
                self._captures[name] = cap
            else:
                cap.release()
        return results

    def start(self) -> None:
        """Start the background frame-grabbing thread. No-op if already running."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._thread.start()

    def _grab_loop(self) -> None:
        interval = 1.0 / self._fps if self._fps else 0.0
        while not self._stop_event.is_set():
            for name, cap in self._captures.items():
                ok, frame = cap.read()
                if ok:
                    with self._lock:
                        self._frames[name] = frame
            if interval:
                time.sleep(interval)

    def get_frame(self, name: CameraName) -> np.ndarray | None:
        """Latest frame for `name`, or None if nothing's been grabbed yet. Returns a
        copy so callers can safely draw on it without racing the grab thread."""
        with self._lock:
            frame = self._frames.get(name)
            return None if frame is None else frame.copy()

    def grab_single_frame(self, name: CameraName, timeout_s: float = 2.0) -> np.ndarray | None:
        """Blocking single-frame read, for tools (e.g. calibrate_board.py) that don't
        want to run the background thread — reads directly off the open capture."""
        cap = self._captures.get(name)
        if cap is None:
            return None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok:
                return frame
        return None

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for cap in self._captures.values():
            cap.release()
        self._captures.clear()
        self._frames = dict.fromkeys(self._indices)
