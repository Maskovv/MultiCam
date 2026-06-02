"""Низкоуровневый ctypes-биндинг к SDK камеры (nncam / toupcam).

nncam.dll (Windows) и libnncam.so (Linux/arm64) — это OEM-сборка SDK ToupTek.
Экспортируемые функции имеют префикс Nncam_ (в некоторых сборках Toupcam_),
поэтому загрузчик пробует оба варианта имён.

Здесь объявлены только структуры и функции, которые реально использует штатное ПО
MultiCam (по импортам MultiCam.exe):
    Nncam_EnumV2, Nncam_Open, Nncam_Close,
    Nncam_StartPullModeWithCallback, Nncam_PullImageV3, Nncam_Stop,
    Nncam_get_Size, Nncam_get/put_ExpoTime, Nncam_get_ExpTimeRange,
    Nncam_get/put_ExpoAGain, Nncam_get_ExpoAGainRange,
    Nncam_put_AutoExpoEnable, Nncam_put_Option, Nncam_put_Roi,
    Nncam_put_VFlip, Nncam_put_HFlip.
"""
from __future__ import annotations

import ctypes as C
import platform
import sys
from ctypes.util import find_library

NNCAM_MAX = 16

# --- Коды событий (TOUPCAM_EVENT_*) ---
EVENT_EXPOSURE = 0x0001
EVENT_TEMPTINT = 0x0002
EVENT_IMAGE = 0x0004
EVENT_STILLIMAGE = 0x0005
EVENT_ERROR = 0x0080
EVENT_DISCONNECTED = 0x0081
EVENT_NOFRAMETIMEOUT = 0x0082
EVENT_NOPACKETTIMEOUT = 0x0084

# --- Опции (TOUPCAM_OPTION_*) ---
OPTION_RAW = 0x04          # 0 = RGB, 1 = выдавать сырые данные сенсора
OPTION_BITDEPTH = 0x07     # 0 = 8 бит, 1 = повышенная разрядность (10/12/14/16)
OPTION_PIXEL_FORMAT = 0x2f


class Resolution(C.Structure):
    _fields_ = [("width", C.c_uint), ("height", C.c_uint)]


class ModelV2(C.Structure):
    _fields_ = [
        ("name", C.c_char_p),
        ("flag", C.c_ulonglong),
        ("maxspeed", C.c_uint),
        ("preview", C.c_uint),
        ("still", C.c_uint),
        ("maxfanspeed", C.c_uint),
        ("ioctrol", C.c_uint),
        ("xpixsz", C.c_float),
        ("ypixsz", C.c_float),
        ("res", Resolution * NNCAM_MAX),
    ]


class DeviceV2(C.Structure):
    # На Linux/macOS строки — char[64]; на Windows API использует wchar_t.
    _fields_ = [
        ("displayname", C.c_char * 64),
        ("id", C.c_char * 64),
        ("model", C.POINTER(ModelV2)),
    ]


class FrameInfoV3(C.Structure):
    _fields_ = [
        ("width", C.c_uint),
        ("height", C.c_uint),
        ("flag", C.c_uint),
        ("seq", C.c_uint),
        ("timestamp", C.c_ulonglong),
        ("shutterseq", C.c_uint),
        ("expotime", C.c_ulonglong),
        ("expogain", C.c_ushort),
        ("blacklevel", C.c_ushort),
    ]


# Тип колбэка события: void(*)(unsigned nEvent, void* ctx)
EVENT_CALLBACK = C.CFUNCTYPE(None, C.c_uint, C.c_void_p)

HNncam = C.c_void_p


def _candidate_lib_names() -> list[str]:
    if sys.platform.startswith("win"):
        return ["nncam.dll", "toupcam.dll"]
    if sys.platform == "darwin":
        return ["libnncam.dylib", "libtoupcam.dylib"]
    return ["libnncam.so", "libtoupcam.so"]


def load_library(explicit_path: str | None = None) -> C.CDLL:
    """Загружает разделяемую библиотеку SDK."""
    errors: list[str] = []
    names = [explicit_path] if explicit_path else _candidate_lib_names()
    for name in names:
        if not name:
            continue
        try:
            return C.CDLL(name)
        except OSError as exc:
            errors.append(f"{name}: {exc}")
    # Последняя попытка — через find_library.
    for base in ("nncam", "toupcam"):
        found = find_library(base)
        if found:
            try:
                return C.CDLL(found)
            except OSError as exc:
                errors.append(f"{found}: {exc}")
    raise OSError(
        "Не удалось загрузить SDK камеры (libnncam.so / nncam.dll). "
        "Проверь, что библиотека лежит рядом или в LD_LIBRARY_PATH.\n"
        + "\n".join(errors)
    )


def _bind(lib: C.CDLL, base_name: str):
    """Возвращает функцию по имени Nncam_* или Toupcam_*."""
    for prefix in ("Nncam_", "Toupcam_"):
        fn = getattr(lib, prefix + base_name, None)
        if fn is not None:
            return fn
    raise AttributeError(f"В библиотеке нет функции {base_name} (ни Nncam_, ни Toupcam_)")


class NncamSDK:
    """Тонкая обёртка: настраивает прототипы функций ctypes."""

    def __init__(self, lib_path: str | None = None):
        self.lib = load_library(lib_path)
        self._setup_prototypes()

    def _setup_prototypes(self) -> None:
        lib = self.lib

        self.EnumV2 = _bind(lib, "EnumV2")
        self.EnumV2.argtypes = [DeviceV2 * NNCAM_MAX]
        self.EnumV2.restype = C.c_uint

        self.Open = _bind(lib, "Open")
        self.Open.argtypes = [C.c_char_p]
        self.Open.restype = HNncam

        self.Close = _bind(lib, "Close")
        self.Close.argtypes = [HNncam]
        self.Close.restype = None

        self.StartPullModeWithCallback = _bind(lib, "StartPullModeWithCallback")
        self.StartPullModeWithCallback.argtypes = [HNncam, EVENT_CALLBACK, C.c_void_p]
        self.StartPullModeWithCallback.restype = C.c_int

        self.PullImageV3 = _bind(lib, "PullImageV3")
        self.PullImageV3.argtypes = [
            HNncam, C.c_void_p, C.c_int, C.c_int, C.c_int, C.POINTER(FrameInfoV3)
        ]
        self.PullImageV3.restype = C.c_int

        self.Stop = _bind(lib, "Stop")
        self.Stop.argtypes = [HNncam]
        self.Stop.restype = C.c_int

        self.get_Size = _bind(lib, "get_Size")
        self.get_Size.argtypes = [HNncam, C.POINTER(C.c_int), C.POINTER(C.c_int)]
        self.get_Size.restype = C.c_int

        self.put_ExpoTime = _bind(lib, "put_ExpoTime")
        self.put_ExpoTime.argtypes = [HNncam, C.c_uint]
        self.put_ExpoTime.restype = C.c_int

        self.get_ExpoTime = _bind(lib, "get_ExpoTime")
        self.get_ExpoTime.argtypes = [HNncam, C.POINTER(C.c_uint)]
        self.get_ExpoTime.restype = C.c_int

        self.get_ExpTimeRange = _bind(lib, "get_ExpTimeRange")
        self.get_ExpTimeRange.argtypes = [
            HNncam, C.POINTER(C.c_uint), C.POINTER(C.c_uint), C.POINTER(C.c_uint)
        ]
        self.get_ExpTimeRange.restype = C.c_int

        self.put_ExpoAGain = _bind(lib, "put_ExpoAGain")
        self.put_ExpoAGain.argtypes = [HNncam, C.c_ushort]
        self.put_ExpoAGain.restype = C.c_int

        self.get_ExpoAGain = _bind(lib, "get_ExpoAGain")
        self.get_ExpoAGain.argtypes = [HNncam, C.POINTER(C.c_ushort)]
        self.get_ExpoAGain.restype = C.c_int

        self.put_AutoExpoEnable = _bind(lib, "put_AutoExpoEnable")
        self.put_AutoExpoEnable.argtypes = [HNncam, C.c_int]
        self.put_AutoExpoEnable.restype = C.c_int

        self.put_Option = _bind(lib, "put_Option")
        self.put_Option.argtypes = [HNncam, C.c_uint, C.c_int]
        self.put_Option.restype = C.c_int

        # ROI и flip — опциональны, биндим мягко.
        for name, args in (
            ("put_Roi", [HNncam, C.c_uint, C.c_uint, C.c_uint, C.c_uint]),
            ("put_VFlip", [HNncam, C.c_int]),
            ("put_HFlip", [HNncam, C.c_int]),
        ):
            try:
                fn = _bind(lib, name)
                fn.argtypes = args
                fn.restype = C.c_int
                setattr(self, name, fn)
            except AttributeError:
                setattr(self, name, None)


def succeeded(hr: int) -> bool:
    """HRESULT: успех — неотрицательное значение."""
    return hr >= 0
