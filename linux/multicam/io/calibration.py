"""Чтение калибровочных файлов calibration05/10/15.txt.

Формат файла: подряд идущие 3x3 матрицы (по 3 строки на матрицу, числа через пробел),
по одной на каждый спектральный канал в порядке WAVELENGTHS (400..950 нм).

На практике это аффинные матрицы переноса вида
    [[1, 0, dx],
     [0, 1, dy],
     [0, 0,  1]]
то есть чистый сдвиг канала (dx, dy) в пикселях относительно опорного канала (800 нм),
у которого матрица единичная.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import WAVELENGTHS

# Соответствие "дистанция съёмки в метрах" -> имя файла калибровки.
_DISTANCE_FILES = {
    0.5: "calibration05.txt",
    1.0: "calibration10.txt",
    1.5: "calibration15.txt",
}


@dataclass
class Calibration:
    """Набор аффинных матриц регистрации каналов для конкретной дистанции съёмки."""

    distance_m: float
    matrices: np.ndarray  # shape (N, 3, 3), float64

    @property
    def n_channels(self) -> int:
        return int(self.matrices.shape[0])

    def shift_for(self, channel_index: int) -> tuple[float, float]:
        """Возвращает (dx, dy) в пикселях для канала по индексу."""
        m = self.matrices[channel_index]
        return float(m[0, 2]), float(m[1, 2])

    def affine_2x3(self, channel_index: int) -> np.ndarray:
        """Матрица 2x3 для cv2.warpAffine."""
        return self.matrices[channel_index][:2, :].astype(np.float32)


def calibration_path_for_distance(base_dir: Path | str, distance_m: float) -> Path:
    """Путь к файлу калибровки для дистанции 0.5 / 1.0 / 1.5 м."""
    try:
        name = _DISTANCE_FILES[float(distance_m)]
    except KeyError as exc:
        valid = ", ".join(str(k) for k in _DISTANCE_FILES)
        raise ValueError(
            f"Калибровка доступна только для дистанций: {valid} м (получено {distance_m})"
        ) from exc
    return Path(base_dir) / name


def load_calibration(path: Path | str, distance_m: float | None = None) -> Calibration:
    """Парсит файл калибровки в набор 3x3 матриц.

    Поднимает ValueError, если число прочитанных матриц не совпало с числом каналов.
    """
    path = Path(path)
    values: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        values.extend(float(tok) for tok in line.split())

    if len(values) % 9 != 0:
        raise ValueError(
            f"{path.name}: число значений ({len(values)}) не кратно 9 (3x3 матрицы)"
        )

    matrices = np.array(values, dtype=np.float64).reshape(-1, 3, 3)

    expected = len(WAVELENGTHS)
    if matrices.shape[0] != expected:
        raise ValueError(
            f"{path.name}: ожидалось {expected} матриц по числу каналов, "
            f"получено {matrices.shape[0]}"
        )

    if distance_m is None:
        # Попытка вывести дистанцию из имени файла.
        for dist, name in _DISTANCE_FILES.items():
            if path.name == name:
                distance_m = dist
                break
    return Calibration(distance_m=float(distance_m or 0.0), matrices=matrices)
