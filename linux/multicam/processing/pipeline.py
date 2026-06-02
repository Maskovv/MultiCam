"""Сквозной конвейер обработки: кадр -> каналы -> регистрация -> отражение -> индексы.

Связывает воедино модули разрезки, регистрации, отражения и расчёта индексов.
Поддерживает два режима результата:
  * спектр и индексы, усреднённые по области (ROI);
  * карты индексов (поэлементно по всему кадру).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import indices as _indices
from .channels import ChannelLayout, split_channels
from .custom_index import evaluate_custom_index
from .reflectance import mean_spectrum, to_reflectance
from .registration import register_channels
from ..io.calibration import Calibration


@dataclass
class PipelineResult:
    reflectance: dict[int, np.ndarray]
    spectrum: dict[int, float] = field(default_factory=dict)
    index_values: dict[str, float] = field(default_factory=dict)
    index_maps: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class Pipeline:
    calibration: Calibration
    layout: ChannelLayout = field(default_factory=ChannelLayout)
    custom_index: str | None = None

    def _channels(self, frame: np.ndarray) -> dict[int, np.ndarray]:
        return register_channels(split_channels(frame, self.layout), self.calibration)

    def process(
        self,
        object_frame: np.ndarray,
        reference_frame: np.ndarray,
        dark_frame: np.ndarray | None = None,
        roi: tuple[int, int, int, int] | None = None,
        compute_maps: bool = False,
    ) -> PipelineResult:
        obj = self._channels(object_frame)
        ref = self._channels(reference_frame)
        dark = self._channels(dark_frame) if dark_frame is not None else None

        reflectance = to_reflectance(obj, ref, dark)
        result = PipelineResult(reflectance=reflectance)

        # Усреднённый по области спектр и индексы.
        result.spectrum = mean_spectrum(reflectance, roi)
        result.index_values = _indices.compute_all(result.spectrum)
        if self.custom_index:
            result.index_values["Custom"] = float(
                evaluate_custom_index(self.custom_index, result.spectrum)
            )

        # Карты индексов (по всему кадру).
        if compute_maps:
            result.index_maps = _indices.compute_all(reflectance)
            if self.custom_index:
                result.index_maps["Custom"] = evaluate_custom_index(
                    self.custom_index, reflectance
                )
        return result
