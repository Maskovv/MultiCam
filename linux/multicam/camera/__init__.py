from .base import BaseCamera, CameraInfo, FrameInfo
from .mock_backend import MockCamera

__all__ = ["BaseCamera", "CameraInfo", "FrameInfo", "MockCamera", "open_camera"]


def open_camera(backend: str = "auto", **kwargs):
    """Фабрика камеры.

    backend:
      * "mock"  — чтение кадров из файлов (для разработки/CI без железа);
      * "nncam" — реальная камера через libnncam.so / nncam.dll;
      * "auto"  — попытка nncam, при неудаче — mock.
    """
    if backend == "mock":
        return MockCamera(**kwargs)
    if backend == "nncam":
        from .nncam_backend import NncamCamera
        return NncamCamera(**kwargs)
    if backend == "auto":
        try:
            from .nncam_backend import NncamCamera
            cam = NncamCamera(**{k: v for k, v in kwargs.items() if k != "frame_path"})
            return cam
        except Exception:
            return MockCamera(**{k: v for k, v in kwargs.items() if k != "device_id"})
    raise ValueError(f"Неизвестный backend: {backend}")
