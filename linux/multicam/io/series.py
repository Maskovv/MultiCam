"""Чтение справочного файла настроек серии (формат как в Reference/settings.txt).

Пример содержимого:
    Start time: 10/03/2023 14:41:16
    Custom Note:
    Camera name: BigEye4200KME
    Files path: C:/Users/.../s_10_03_23_14_41_16
    Exposure, us: 77088
    Gain, %: 100
    Frame rate, Hz: 0
    Width, px: 2048
    Height, px: 2048
    Offset X, px: 0
    Offset Y, px: 0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SeriesSettings:
    start_time: str = ""
    note: str = ""
    camera_name: str = ""
    files_path: str = ""
    exposure_us: int = 0
    gain_percent: float = 0.0
    frame_rate_hz: float = 0.0
    width: int = 0
    height: int = 0
    offset_x: int = 0
    offset_y: int = 0
    extra: dict[str, str] = field(default_factory=dict)


# Соответствие префиксов строк полям датакласса.
_FIELD_MAP = {
    "Start time": ("start_time", str),
    "Custom Note": ("note", str),
    "Camera name": ("camera_name", str),
    "Files path": ("files_path", str),
    "Exposure, us": ("exposure_us", int),
    "Gain, %": ("gain_percent", float),
    "Frame rate, Hz": ("frame_rate_hz", float),
    "Width, px": ("width", int),
    "Height, px": ("height", int),
    "Offset X, px": ("offset_x", int),
    "Offset Y, px": ("offset_y", int),
}


def parse_settings(path: Path | str) -> SeriesSettings:
    settings = SeriesSettings()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in _FIELD_MAP:
            attr, caster = _FIELD_MAP[key]
            try:
                setattr(settings, attr, caster(value) if value else getattr(settings, attr))
            except ValueError:
                settings.extra[key] = value
        else:
            settings.extra[key] = value
    return settings
