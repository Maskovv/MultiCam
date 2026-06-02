"""Абстрактный интерфейс камеры.

Один и тот же интерфейс реализуют MockCamera (файлы) и NncamCamera (реальный SDK),
поэтому весь код обработки/съёмки не зависит от наличия железа.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np


@dataclass
class CameraInfo:
    name: str
    width: int
    height: int
    device_id: str = ""


@dataclass
class FrameInfo:
    width: int
    height: int
    exposure_us: int = 0
    gain: float = 0.0
    timestamp_us: int = 0
    index: int = 0


class BaseCamera(abc.ABC):
    """Контракт камеры: открыть -> настроить -> получать кадры -> закрыть."""

    @abc.abstractmethod
    def open(self) -> CameraInfo: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def get_size(self) -> tuple[int, int]:
        """(width, height) текущего кадра."""

    @abc.abstractmethod
    def set_exposure(self, exposure_us: int) -> None: ...

    @abc.abstractmethod
    def get_exposure(self) -> int: ...

    @abc.abstractmethod
    def set_gain(self, gain: float) -> None: ...

    @abc.abstractmethod
    def set_auto_exposure(self, enabled: bool) -> None: ...

    @abc.abstractmethod
    def grab(self, timeout_s: float = 5.0) -> tuple[np.ndarray, FrameInfo]:
        """Захватить один кадр (блокирующе)."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
