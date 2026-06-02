"""Тесты парсинга калибровок на реальных файлах из корня репозитория."""
from pathlib import Path

import numpy as np
import pytest

from multicam import WAVELENGTHS, ANCHOR_WAVELENGTH
from multicam.io.calibration import load_calibration, calibration_path_for_distance

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../MultiCam


@pytest.mark.parametrize("distance", [0.5, 1.0, 1.5])
def test_load_real_calibration(distance):
    path = calibration_path_for_distance(REPO_ROOT, distance)
    if not path.exists():
        pytest.skip(f"нет файла калибровки {path}")
    cal = load_calibration(path, distance)
    assert cal.n_channels == len(WAVELENGTHS)


@pytest.mark.parametrize("distance", [0.5, 1.0, 1.5])
def test_anchor_channel_is_identity(distance):
    """У опорного канала (800 нм) сдвиг должен быть нулевым."""
    path = calibration_path_for_distance(REPO_ROOT, distance)
    if not path.exists():
        pytest.skip(f"нет файла калибровки {path}")
    cal = load_calibration(path, distance)
    anchor_idx = WAVELENGTHS.index(ANCHOR_WAVELENGTH)
    dx, dy = cal.shift_for(anchor_idx)
    assert dx == 0.0 and dy == 0.0
