"""Mock-камера: отдаёт кадры из файлов на диске.

Назначение — разработка и тесты без реального железа (в т. ч. в виртуалке).
Можно подать один файл (будет повторяться) или папку (кадры по очереди).
Поддерживает .bmp/.png/.tif (через OpenCV) и .npy.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .base import BaseCamera, CameraInfo, FrameInfo

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None


def _load_image(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        return np.load(path)
    if cv2 is None:
        raise RuntimeError("Для чтения изображений нужен opencv-python (см. requirements.txt)")
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Не удалось прочитать кадр: {path}")
    return img


class MockCamera(BaseCamera):
    def __init__(self, frame_path: str | Path, exposure_us: int = 10000, gain: float = 100.0):
        self.frame_path = Path(frame_path)
        self._frames: list[Path] = []
        self._cursor = 0
        self._exposure = exposure_us
        self._gain = gain
        self._auto = False
        self._size = (0, 0)
        self._opened = False

    def open(self) -> CameraInfo:
        if self.frame_path.is_dir():
            exts = {".bmp", ".png", ".tif", ".tiff", ".jpg", ".jpeg", ".npy"}
            self._frames = sorted(p for p in self.frame_path.iterdir() if p.suffix.lower() in exts)
            if not self._frames:
                raise FileNotFoundError(f"В папке нет кадров: {self.frame_path}")
        else:
            self._frames = [self.frame_path]
        probe = _load_image(self._frames[0])
        h, w = probe.shape[:2]
        self._size = (w, h)
        self._opened = True
        return CameraInfo(name="MockCamera", width=w, height=h, device_id=str(self.frame_path))

    def close(self) -> None:
        self._opened = False

    def get_size(self) -> tuple[int, int]:
        return self._size

    def set_exposure(self, exposure_us: int) -> None:
        self._exposure = int(exposure_us)

    def get_exposure(self) -> int:
        return self._exposure

    def set_gain(self, gain: float) -> None:
        self._gain = float(gain)

    def set_auto_exposure(self, enabled: bool) -> None:
        self._auto = bool(enabled)

    def grab(self, timeout_s: float = 5.0) -> tuple[np.ndarray, FrameInfo]:
        if not self._opened:
            raise RuntimeError("Камера не открыта (вызовите open())")
        path = self._frames[self._cursor % len(self._frames)]
        idx = self._cursor
        self._cursor += 1
        img = _load_image(path)
        h, w = img.shape[:2]
        info = FrameInfo(
            width=w, height=h, exposure_us=self._exposure, gain=self._gain,
            timestamp_us=int(time.time() * 1e6), index=idx,
        )
        return img, info
