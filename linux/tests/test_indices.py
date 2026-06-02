"""Регрессионные тесты формул индексов по эталонному выводу штатного ПО (файл `grafik`)."""
import numpy as np
import pytest

from multicam.processing import indices
from multicam.processing.custom_index import evaluate_custom_index, CustomIndexError

REF_SPECTRUM = {
    400: 0.807161, 450: 0.357816, 500: 0.389187, 550: 0.418616,
    600: 0.478426, 650: 0.354705, 700: 0.405074, 750: 0.797681,
    800: 0.787553, 850: 0.7807, 900: 0.791218, 950: 0.873464,
}
REF_INDICES = {
    "NDVI": 0.375192, "CIre": 0.507814, "MCARI": 0.623839,
    "NDVI700": 0.326423, "CAR": 0.142263, "PSSRc": 2.201,
}


@pytest.mark.parametrize("name,expected", REF_INDICES.items())
def test_index_matches_reference(name, expected):
    got = float(indices.compute_all(REF_SPECTRUM)[name])
    assert abs(got - expected) < 1e-3, f"{name}: {got} != {expected}"


def test_indices_work_on_arrays():
    """Те же формулы должны работать поэлементно (карты индексов)."""
    spectrum = {wl: np.full((4, 4), v) for wl, v in REF_SPECTRUM.items()}
    ndvi_map = indices.ndvi(spectrum)
    assert ndvi_map.shape == (4, 4)
    assert np.allclose(ndvi_map, REF_INDICES["NDVI"], atol=1e-3)


def test_custom_index_scalar():
    val = evaluate_custom_index("x800 / x450", REF_SPECTRUM)
    assert abs(val - REF_SPECTRUM[800] / REF_SPECTRUM[450]) < 1e-9


def test_custom_index_rejects_unknown_channel():
    with pytest.raises(CustomIndexError):
        evaluate_custom_index("x710 / x716", REF_SPECTRUM)


def test_custom_index_rejects_code_injection():
    with pytest.raises(CustomIndexError):
        evaluate_custom_index("__import__('os').system('echo hi')", REF_SPECTRUM)
