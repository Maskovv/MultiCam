"""Реальная камера через SDK nncam/toupcam (pull-режим с колбэком).

Повторяет логику штатного ПО: Enum -> Open -> put настроек -> StartPullModeWithCallback,
по событию EVENT_IMAGE вызывается PullImageV3, который копирует кадр в буфер.

Работает на Linux/arm64 (Jetson) с libnncam.so и на Windows с nncam.dll.
"""
from __future__ import annotations

import ctypes as C
import threading

import numpy as np

from . import nncam_sdk as sdk
from .base import BaseCamera, CameraInfo, FrameInfo


class NncamError(RuntimeError):
    pass


def _check(hr: int, what: str) -> None:
    if not sdk.succeeded(hr):
        raise NncamError(f"{what} вернул ошибку HRESULT=0x{hr & 0xFFFFFFFF:08x}")


class NncamCamera(BaseCamera):
    def __init__(
        self,
        device_id: str | None = None,
        lib_path: str | None = None,
        raw: bool = True,
        bits: int = 16,
    ):
        self._sdk = sdk.NncamSDK(lib_path)
        self._device_id = device_id
        self._raw = raw
        self._bits = bits
        self._h: sdk.HNncam = None
        self._w = 0
        self._hgt = 0
        self._image_event = threading.Event()
        self._last_error: int | None = None
        # Колбэк держим как атрибут, чтобы его не собрал GC.
        self._cb = sdk.EVENT_CALLBACK(self._on_event)
        self._info = CameraInfo(name="", width=0, height=0)

    # --- enumeration / open ---
    def enumerate(self) -> list[CameraInfo]:
        arr = (sdk.DeviceV2 * sdk.NNCAM_MAX)()
        count = self._sdk.EnumV2(arr)
        result = []
        for i in range(count):
            dev = arr[i]
            name = dev.displayname.decode(errors="ignore")
            dev_id = dev.id.decode(errors="ignore")
            w = h = 0
            if dev.model:
                res0 = dev.model.contents.res[0]
                w, h = int(res0.width), int(res0.height)
            result.append(CameraInfo(name=name, width=w, height=h, device_id=dev_id))
        return result

    def open(self) -> CameraInfo:
        dev_id = self._device_id
        if dev_id is None:
            cams = self.enumerate()
            if not cams:
                raise NncamError("Камеры не найдены (Nncam_EnumV2 вернул 0)")
            dev_id = cams[0].device_id

        self._h = self._sdk.Open(dev_id.encode() if dev_id else None)
        if not self._h:
            raise NncamError("Nncam_Open вернул NULL (камера не открылась)")

        if self._raw:
            self._sdk.put_Option(self._h, sdk.OPTION_RAW, 1)
            self._sdk.put_Option(self._h, sdk.OPTION_BITDEPTH, 1 if self._bits > 8 else 0)

        w = C.c_int(0)
        h = C.c_int(0)
        _check(self._sdk.get_Size(self._h, C.byref(w), C.byref(h)), "get_Size")
        self._w, self._hgt = int(w.value), int(h.value)

        _check(
            self._sdk.StartPullModeWithCallback(self._h, self._cb, None),
            "StartPullModeWithCallback",
        )
        self._info = CameraInfo(
            name="Nncam", width=self._w, height=self._hgt, device_id=dev_id or ""
        )
        return self._info

    def close(self) -> None:
        if self._h:
            try:
                self._sdk.Stop(self._h)
            finally:
                self._sdk.Close(self._h)
                self._h = None

    # --- callback ---
    def _on_event(self, event: int, ctx) -> None:
        if event == sdk.EVENT_IMAGE:
            self._image_event.set()
        elif event in (sdk.EVENT_ERROR, sdk.EVENT_DISCONNECTED,
                       sdk.EVENT_NOFRAMETIMEOUT, sdk.EVENT_NOPACKETTIMEOUT):
            self._last_error = event
            self._image_event.set()

    # --- settings ---
    def get_size(self) -> tuple[int, int]:
        return self._w, self._hgt

    def set_exposure(self, exposure_us: int) -> None:
        _check(self._sdk.put_ExpoTime(self._h, int(exposure_us)), "put_ExpoTime")

    def get_exposure(self) -> int:
        val = C.c_uint(0)
        _check(self._sdk.get_ExpoTime(self._h, C.byref(val)), "get_ExpoTime")
        return int(val.value)

    def exposure_range(self) -> tuple[int, int, int]:
        lo, hi, dft = C.c_uint(0), C.c_uint(0), C.c_uint(0)
        _check(
            self._sdk.get_ExpTimeRange(self._h, C.byref(lo), C.byref(hi), C.byref(dft)),
            "get_ExpTimeRange",
        )
        return int(lo.value), int(hi.value), int(dft.value)

    def set_gain(self, gain: float) -> None:
        _check(self._sdk.put_ExpoAGain(self._h, int(gain)), "put_ExpoAGain")

    def set_auto_exposure(self, enabled: bool) -> None:
        _check(self._sdk.put_AutoExpoEnable(self._h, 1 if enabled else 0), "put_AutoExpoEnable")

    # --- grab ---
    def grab(self, timeout_s: float = 5.0) -> tuple[np.ndarray, FrameInfo]:
        if not self._h:
            raise NncamError("Камера не открыта")
        self._last_error = None
        self._image_event.clear()
        if not self._image_event.wait(timeout_s):
            raise TimeoutError(f"Кадр не пришёл за {timeout_s} с")
        if self._last_error is not None:
            raise NncamError(f"Событие ошибки камеры: 0x{self._last_error:02x}")

        bits = self._bits
        dtype = np.uint16 if bits > 8 else np.uint8
        bytes_per_px = 2 if bits > 8 else 1
        row_pitch = self._w * bytes_per_px
        buf = np.empty((self._hgt, self._w), dtype=dtype)
        fi = sdk.FrameInfoV3()
        _check(
            self._sdk.PullImageV3(
                self._h, buf.ctypes.data_as(C.c_void_p), 0, bits, row_pitch, C.byref(fi)
            ),
            "PullImageV3",
        )
        info = FrameInfo(
            width=int(fi.width) or self._w,
            height=int(fi.height) or self._hgt,
            exposure_us=int(fi.expotime),
            gain=float(fi.expogain),
            timestamp_us=int(fi.timestamp),
            index=int(fi.seq),
        )
        return buf, info
