"""Регистрация (совмещение) спектральных каналов по калибровочным сдвигам.

Каждый канал сдвигается на (dx, dy) из калибровки так, чтобы все каналы
совпали с опорным (800 нм). Используется аффинное преобразование сдвига.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - cv2 ставится через requirements
    cv2 = None

from .. import WAVELENGTHS
from ..io.calibration import Calibration


def _shift_numpy(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Целочисленный сдвиг через np.roll (fallback, если нет OpenCV)."""
    sx, sy = int(round(dx)), int(round(dy))
    out = np.roll(img, shift=(sy, sx), axis=(0, 1))
    # Обнуляем "завёрнутые" края.
    if sy > 0:
        out[:sy, :] = 0
    elif sy < 0:
        out[sy:, :] = 0
    if sx > 0:
        out[:, :sx] = 0
    elif sx < 0:
        out[:, sx:] = 0
    return out


def register_channels(
    channels: dict[int, np.ndarray],
    calibration: Calibration,
) -> dict[int, np.ndarray]:
    """Применяет сдвиг к каждому каналу согласно калибровке.

    channels: {длина_волны: тайл}; порядок матриц в calibration совпадает с WAVELENGTHS.
    """
    out: dict[int, np.ndarray] = {}
    for ch_index, wl in enumerate(WAVELENGTHS):
        if wl not in channels:
            continue
        img = channels[wl]
        dx, dy = calibration.shift_for(ch_index)
        if cv2 is not None:
            mat = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
            out[wl] = cv2.warpAffine(
                img, mat, (img.shape[1], img.shape[0]),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            )
        else:
            out[wl] = _shift_numpy(img, dx, dy)
    return out
