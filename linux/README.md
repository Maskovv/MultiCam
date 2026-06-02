# MultiCam — Linux/Jetson порт

Порт обработки данных мультиспектральной камеры **BigEye4200KME** (16-апертурный
сенсор 2048×2048, USB3) с Windows-ПО `MultiCam.exe` на Linux/Jetson Orin Nano.

## Главная идея

`nncam.dll` — это OEM-сборка SDK **ToupTek**, у которого есть **официальная сборка
под Linux arm64** (`libnncam.so`). Поэтому низкоуровневый доступ к камере НЕ нужно
реверсить — мы переиспользуем тот же API (`Nncam_*`). Заново пишем только слой
обработки (разрезка каналов → регистрация → отражение → вегетационные индексы),
формулы которого взяты из `Manual.pdf` и сверены с реальным выводом ПО.

## Архитектура

```
multicam/
  camera/            # доступ к камере
    base.py          # абстрактный интерфейс (одинаков для всех бэкендов)
    mock_backend.py  # отдаёт кадры из файлов — для разработки/тестов без железа
    nncam_sdk.py     # ctypes-биндинг к libnncam.so / nncam.dll
    nncam_backend.py # реальная камера (pull-режим, как в штатном ПО)
  processing/        # обработка
    channels.py      # разрезка кадра 2048x2048 на 16 тайлов (12 спектр. каналов)
    registration.py  # совмещение каналов по калибровочным сдвигам
    reflectance.py   # коэффициент отражения (объект/референс) + усреднение по ROI
    indices.py       # NDVI, CIre, MCARI, NDVIre, CAR, PSSRc (сверены с ПО)
    custom_index.py  # безопасный парсер пользовательских индексов (xλ)
    pipeline.py      # сквозной конвейер
  io/
    calibration.py   # парсер calibration05/10/15.txt
    series.py        # парсер settings.txt
  cli.py             # командная строка
config/channels.yaml # геометрия разрезки (карта "тайл -> длина волны")
tests/               # pytest
```

## Что уже работает и проверено

- Формулы 6 индексов сходятся с эталонным выводом ПО (`grafik`) — `multicam.cli selftest`.
- Парсер калибровок: 12 матриц, опорный канал 800 нм = нулевой сдвиг.
- Сквозной пайплайн (split → register → reflectance → indices) на кадре 2048×2048.

## Что ещё предстоит уточнить (важно)

1. **Карта «тайл → длина волны»** в `config/channels.yaml` — пока заглушка.
   Нужно сверить с реальным кадром/штатным ПО (какой субкадр соответствует какой λ).
2. **Калибровки лабораторные** (0.5/1/1.5 м). Для съёмки с дрона геометрию и
   спектральную коррекцию надо пересчитывать (об этом прямо сказано в мануале).
3. **Геотеги** — отдельный модуль (берём координаты от полётного контроллера по
   MAVLink и пишем в EXIF/GeoTIFF). Пока не реализовано.

См. подробный план тестов в [TESTING.md](TESTING.md).

## Быстрый старт

```bash
cd linux
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Самопроверка формул (без камеры и без OpenCV):
python -m multicam.cli selftest

# 2) Офлайн-обработка сохранённых кадров:
python -m multicam.cli process \
    --object ../Reference/fr_14_41_17_557.bmp \
    --reference ../Reference/fr_14_41_17_557.bmp \
    --distance 1.0 --calibration-dir .. \
    --roi 100 400 100 400

# 3) На Jetson с реальной камерой:
python -m multicam.cli probe
python -m multicam.cli capture --backend nncam --count 5 --output-dir captures
```
