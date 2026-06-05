from .base import BaseCamera, CameraInfo, FrameInfo
from .mock_backend import MockCamera

__all__ = ["BaseCamera", "CameraInfo", "FrameInfo", "MockCamera", "open_camera"]


# Имена аргументов, которые понимает каждый бэкенд (остальное отбрасываем,
# чтобы единый набор kwargs из CLI не вызывал TypeError).
_NNCAM_KWARGS = {"device_id", "lib_path", "raw", "bits"}
_MOCK_KWARGS = {"frame_path", "exposure_us", "gain"}


def _filter(kwargs: dict, allowed: set) -> dict:
    return {k: v for k, v in kwargs.items() if k in allowed and v is not None}


def open_camera(backend: str = "auto", **kwargs):
    """Фабрика камеры.

    backend:
      * "mock"  — чтение кадров из файлов (для разработки/CI без железа);
      * "nncam" — реальная камера через libnncam.so / nncam.dll;
      * "auto"  — попытка nncam, при неудаче — mock.

    Принимает общий набор kwargs (lib_path, frame_path, ...) и сам отбирает
    те, что подходят выбранному бэкенду.
    """
    if backend == "mock":
        return MockCamera(**_filter(kwargs, _MOCK_KWARGS))
    if backend == "nncam":
        from .nncam_backend import NncamCamera
        return NncamCamera(**_filter(kwargs, _NNCAM_KWARGS))
    if backend == "auto":
        try:
            from .nncam_backend import NncamCamera
            return NncamCamera(**_filter(kwargs, _NNCAM_KWARGS))
        except Exception:
            return MockCamera(**_filter(kwargs, _MOCK_KWARGS))
    raise ValueError(f"Неизвестный backend: {backend}")
