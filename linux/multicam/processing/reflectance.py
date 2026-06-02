"""Перевод сырых каналов в коэффициент отражения.

Отражение = (объект - тёмное) / (референс - тёмное), поканально.
Референс — съёмка белого эталона (лист белой бумаги / эталон отражения) при тех же
настройках. Тёмное (dark) — опционально (кадр при закрытом объективе); если нет,
считается нулевым.
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-6


def to_reflectance(
    object_channels: dict[int, np.ndarray],
    reference_channels: dict[int, np.ndarray],
    dark_channels: dict[int, np.ndarray] | None = None,
    clip: bool = True,
) -> dict[int, np.ndarray]:
    """Поканальный расчёт коэффициента отражения."""
    out: dict[int, np.ndarray] = {}
    for wl, obj in object_channels.items():
        ref = reference_channels.get(wl)
        if ref is None:
            raise KeyError(f"В референсе нет канала {wl} нм")
        obj_f = obj.astype(np.float64)
        ref_f = ref.astype(np.float64)
        if dark_channels and wl in dark_channels:
            dark_f = dark_channels[wl].astype(np.float64)
            obj_f = obj_f - dark_f
            ref_f = ref_f - dark_f
        denom = np.where(np.abs(ref_f) > _EPS, ref_f, _EPS)
        refl = obj_f / denom
        if clip:
            refl = np.clip(refl, 0.0, 2.0)
        out[wl] = refl
    return out


def mean_spectrum(
    reflectance: dict[int, np.ndarray],
    roi: tuple[int, int, int, int] | None = None,
) -> dict[int, float]:
    """Усредняет отражение по области (y0, y1, x0, x1) -> спектр {нм: значение}."""
    spectrum: dict[int, float] = {}
    for wl, refl in reflectance.items():
        region = refl if roi is None else refl[roi[0]:roi[1], roi[2]:roi[3]]
        spectrum[wl] = float(np.mean(region))
    return spectrum
