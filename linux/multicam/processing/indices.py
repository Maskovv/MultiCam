"""Вегетационные индексы.

Формулы взяты из руководства MultiCam (Manual.pdf, стр. 18) и СВЕРЕНЫ с реальным
выводом штатного ПО (файл `grafik`) — совпадают до 5-го знака:

    NDVI   = (R850 - R650) / (R850 + R650)
    CIre   = R700 / R750                      # нестандартное определение, как в ПО MultiCam
    MCARI  = [(R750 - R700) - 0.2*(R750 - R550)] * (R750 / R700)
    NDVIre = (R750 - R700) / (R750 + R700)
    CAR    = (1/R500 - 1/R550) * R800
    PSSRc  = R800 / R450

Каждый индекс работает как со скаляром (спектр, усреднённый по области),
так и поэлементно с массивами numpy (карты индексов), за счёт того что
обращение к "каналу" возвращает либо число, либо 2D-массив отражения.
"""
from __future__ import annotations

from typing import Callable, Mapping

import numpy as np

# Тип "спектр": отображение длина_волны_нм -> отражение (скаляр или 2D-массив).
Spectrum = Mapping[int, "float | np.ndarray"]

_EPS = 1e-12


def _safe_div(a, b):
    """Деление с защитой от нуля (для карт)."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.divide(a, b, out=np.zeros_like(np.broadcast_arrays(a, b)[0], dtype=float),
                          where=np.abs(b) > _EPS)
    return a / b if abs(b) > _EPS else 0.0


def ndvi(s: Spectrum):
    return _safe_div(s[850] - s[650], s[850] + s[650])


def cire(s: Spectrum):
    return _safe_div(s[700], s[750])


def mcari(s: Spectrum):
    return ((s[750] - s[700]) - 0.2 * (s[750] - s[550])) * _safe_div(s[750], s[700])


def ndvire(s: Spectrum):
    return _safe_div(s[750] - s[700], s[750] + s[700])


def car(s: Spectrum):
    return (_safe_div(1.0, s[500]) - _safe_div(1.0, s[550])) * s[800]


def pssrc(s: Spectrum):
    return _safe_div(s[800], s[450])


# Реестр штатных индексов: имя -> функция. Порядок как в выводе ПО.
INDEX_FUNCS: dict[str, Callable[[Spectrum], "float | np.ndarray"]] = {
    "NDVI": ndvi,
    "CIre": cire,
    "MCARI": mcari,
    "NDVI700": ndvire,  # в выводе ПО NDVIre назван NDVI700
    "CAR": car,
    "PSSRc": pssrc,
}


def compute_all(s: Spectrum) -> dict[str, "float | np.ndarray"]:
    """Считает все штатные индексы для заданного спектра."""
    return {name: func(s) for name, func in INDEX_FUNCS.items()}
