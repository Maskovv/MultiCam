"""Разрезка сырого кадра 2048x2048 на спектральные каналы.

Камера BigEye4200KME — мультиапертурная: на одном сенсоре 2048x2048 формируется
сетка субизображений, снятых через разные спектральные фильтры. Базовое
предположение (уточняется по реальным данным/штатному ПО): сетка 4x4 = 16 тайлов
по 512x512, из которых 12 — узкополосные каналы 400..950 нм.

ВАЖНО: точное соответствие "тайл -> длина волны" зависит от конкретного прибора и
берётся из конфигурации (config/channels.yaml). Здесь реализована геометрия и
применение карты, а конкретные индексы тайлов вынесены в ChannelLayout, чтобы их
можно было откалибровать, не трогая код.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import WAVELENGTHS


@dataclass
class ChannelLayout:
    """Геометрия разрезки кадра на тайлы и карта 'длина волны -> номер тайла'.

    tile_of_wavelength: для каждой длины волны (нм) — линейный индекс тайла
    в сетке (по строкам слева-направо, сверху-вниз: 0..grid_rows*grid_cols-1).
    """

    grid_rows: int = 4
    grid_cols: int = 4
    tile_of_wavelength: dict[int, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.tile_of_wavelength is None:
            # По умолчанию: первые 12 тайлов по порядку = 12 длин волн.
            # Это ЗАГЛУШКА для офлайн-разработки, требует калибровки на реальных данных.
            self.tile_of_wavelength = {
                wl: i for i, wl in enumerate(WAVELENGTHS)
            }

    @classmethod
    def from_yaml(cls, path: "str | Path") -> "ChannelLayout":
        """Загружает геометрию и карту каналов из config/channels.yaml."""
        import yaml  # локальный импорт, чтобы PyYAML не требовался без YAML

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            grid_rows=int(data.get("grid_rows", 4)),
            grid_cols=int(data.get("grid_cols", 4)),
            tile_of_wavelength={int(k): int(v) for k, v in data["tile_of_wavelength"].items()},
        )

    def tile_rect(self, tile_index: int, frame_h: int, frame_w: int) -> tuple[int, int, int, int]:
        """Возвращает (y0, y1, x0, x1) тайла в кадре."""
        th = frame_h // self.grid_rows
        tw = frame_w // self.grid_cols
        r = tile_index // self.grid_cols
        c = tile_index % self.grid_cols
        return r * th, (r + 1) * th, c * tw, (c + 1) * tw


def to_gray(frame: np.ndarray) -> np.ndarray:
    """Приводит кадр к одноканальному (камера монохромная; BMP может быть 3-канальным)."""
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3:
        # Каналы BGR одинаковы для моно-сенсора — берём первый.
        return frame[..., 0]
    raise ValueError(f"Неподдерживаемая форма кадра: {frame.shape}")


def split_channels(frame: np.ndarray, layout: ChannelLayout | None = None) -> dict[int, np.ndarray]:
    """Режет кадр на каналы по длинам волн.

    Возвращает dict {длина_волны_нм: 2D-массив тайла}.
    """
    layout = layout or ChannelLayout()
    gray = to_gray(frame)
    h, w = gray.shape[:2]
    channels: dict[int, np.ndarray] = {}
    for wl, tile_idx in layout.tile_of_wavelength.items():
        y0, y1, x0, x1 = layout.tile_rect(tile_idx, h, w)
        channels[wl] = gray[y0:y1, x0:x1]
    return channels
