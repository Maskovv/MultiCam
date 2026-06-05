"""Командная строка для офлайн-разработки и проверки на Linux/VM.

Подкоманды:
  selftest  — самопроверка формул индексов по эталонному спектру (без камеры);
  process   — прогон пайплайна на сохранённых кадрах объекта и референса;
  probe     — поиск камеры через SDK (на Jetson/с железом);
  capture   — захват N кадров в файлы (на Jetson/с железом).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from . import WAVELENGTHS
from .io.calibration import calibration_path_for_distance, load_calibration
from .processing import indices as _indices
from .processing.pipeline import Pipeline
from .processing.channels import ChannelLayout

# Эталонные значения из штатного ПО (файл `grafik`) для регрессионной самопроверки.
_REF_SPECTRUM = {
    400: 0.807161, 450: 0.357816, 500: 0.389187, 550: 0.418616,
    600: 0.478426, 650: 0.354705, 700: 0.405074, 750: 0.797681,
    800: 0.787553, 850: 0.7807, 900: 0.791218, 950: 0.873464,
}
_REF_INDICES = {
    "NDVI": 0.375192, "CIre": 0.507814, "MCARI": 0.623839,
    "NDVI700": 0.326423, "CAR": 0.142263, "PSSRc": 2.201,
}


def _cmd_selftest(args: argparse.Namespace) -> int:
    print("Самопроверка формул индексов по эталонному спектру из штатного ПО...\n")
    computed = _indices.compute_all(_REF_SPECTRUM)
    ok = True
    for name, expected in _REF_INDICES.items():
        got = float(computed[name])
        diff = abs(got - expected)
        status = "OK " if diff < 1e-3 else "FAIL"
        if diff >= 1e-3:
            ok = False
        print(f"  [{status}] {name:8s} ожидалось {expected:.6f}  получено {got:.6f}  d={diff:.2e}")
    print("\nИтог:", "ВСЕ ИНДЕКСЫ СОВПАЛИ" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
    return 0 if ok else 1


def _read_frame(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        return np.load(path)
    import cv2  # noqa: WPS433
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit(f"Не удалось прочитать кадр: {path}")
    return img


def _cmd_process(args: argparse.Namespace) -> int:
    cal_path = (
        Path(args.calibration)
        if args.calibration
        else calibration_path_for_distance(args.calibration_dir, args.distance)
    )
    calibration = load_calibration(cal_path, args.distance)
    layout = ChannelLayout()
    pipeline = Pipeline(calibration=calibration, layout=layout, custom_index=args.custom_index)

    obj = _read_frame(Path(args.object))
    ref = _read_frame(Path(args.reference))
    dark = _read_frame(Path(args.dark)) if args.dark else None

    roi = tuple(args.roi) if args.roi else None
    result = pipeline.process(obj, ref, dark_frame=dark, roi=roi, compute_maps=args.maps)

    print("Спектр отражения (усреднён по области):")
    for wl in WAVELENGTHS:
        if wl in result.spectrum:
            print(f"  {wl:4d}  {result.spectrum[wl]:.6f}")
    print("\nВегетационные индексы:")
    for name, val in result.index_values.items():
        print(f"  {name:8s} {float(val):.6f}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write("Спектр отражения: \n")
            for wl in WAVELENGTHS:
                if wl in result.spectrum:
                    f.write(f"{wl}  {result.spectrum[wl]:.6f}\n")
            f.write("Вегетационные индексы: \n")
            for name, val in result.index_values.items():
                f.write(f"{name}  {float(val):.6f}\n")
        print(f"\nСохранено: {out}")
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from .camera.nncam_backend import NncamCamera
    cam = NncamCamera(lib_path=args.lib)
    cams = cam.enumerate()
    if not cams:
        print("Камеры не найдены. Проверь USB-подключение, udev-правило и LD_LIBRARY_PATH.")
        return 1
    print(f"Найдено камер: {len(cams)}")
    for i, info in enumerate(cams):
        print(f"  [{i}] {info.name}  id={info.device_id}  {info.width}x{info.height}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Диагностика окружения: платформа, зависимости, SDK, USB, камера."""
    import platform
    import shutil
    import subprocess

    ok = True

    print("=== MultiCam doctor ===\n")

    # 1) Платформа и Python.
    print(f"Платформа : {platform.system()} {platform.release()}")
    print(f"Архитектура: {platform.machine()}  (для этой арки нужен соответствующий libnncam.so)")
    print(f"Python    : {platform.python_version()}\n")

    # 2) Python-зависимости.
    for mod in ("numpy", "cv2", "yaml"):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            print(f"  [OK ] модуль {mod} ({ver})")
        except ImportError:
            opt = mod == "yaml"
            print(f"  [{'WARN' if opt else 'FAIL'}] модуль {mod} не установлен"
                  + ("  (нужен только для config/channels.yaml)" if opt else ""))
            if not opt:
                ok = False
    print()

    # 3) Загрузка SDK камеры.
    try:
        from .camera import nncam_sdk
        sdk = nncam_sdk.NncamSDK(args.lib)
        ver_fn = getattr(sdk.lib, "Nncam_Version", None) or getattr(sdk.lib, "Toupcam_Version", None)
        ver = ""
        if ver_fn is not None:
            ver_fn.restype = C.c_char_p if sys.platform != "win32" else C.c_wchar_p
            try:
                raw = ver_fn()
                ver = raw.decode() if isinstance(raw, bytes) else str(raw)
            except Exception:
                ver = "(не удалось получить версию)"
        print(f"  [OK ] SDK камеры загружен  версия: {ver}")
    except OSError as exc:
        ok = False
        print(f"  [FAIL] SDK камеры не загружен:\n      {exc}")
        sdk = None
    print()

    # 4) lsusb (Linux): подсказка по USB-подключению.
    if shutil.which("lsusb"):
        try:
            out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5).stdout
            hits = [ln for ln in out.splitlines()
                    if any(k in ln.lower() for k in ("touptek", "nncam", "bigeye", "0547", "549a"))]
            if hits:
                print("  [OK ] похожее USB-устройство найдено:")
                for ln in hits:
                    print(f"        {ln}")
            else:
                print("  [WARN] в lsusb не видно знакомого устройства камеры.")
                print("         В VirtualBox проверь USB-фильтр и Extension Pack.")
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] не удалось выполнить lsusb: {exc}")
    else:
        print("  [..] lsusb недоступен (не Linux или не установлен) — пропускаю USB-проверку.")
    print()

    # 5) Перечисление камер через SDK.
    if sdk is not None:
        try:
            from .camera.nncam_backend import NncamCamera
            cam = NncamCamera(lib_path=args.lib)
            cams = cam.enumerate()
            if cams:
                print(f"  [OK ] камер обнаружено: {len(cams)}")
                for i, info in enumerate(cams):
                    print(f"        [{i}] {info.name}  id={info.device_id}")
            else:
                print("  [WARN] SDK загружен, но камера не обнаружена (Enum вернул 0).")
                print("         Проверь питание/кабель USB3, udev-правило и проброс USB в VM.")
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] ошибка перечисления камер: {exc}")

    print("\nИтог:", "окружение готово" if ok else "есть проблемы (см. FAIL выше)")
    return 0 if ok else 1


def _cmd_capture(args: argparse.Namespace) -> int:
    from .camera import open_camera

    # cv2 нужен только для png/tiff; для npy обходимся без OpenCV.
    cv2 = None
    if args.format != "npy":
        import cv2  # noqa: WPS433

    import time

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cam = open_camera(backend=args.backend, lib_path=args.lib, frame_path=args.mock_frame)
    info = cam.open()
    print(f"Открыта камера: {info.name} {info.width}x{info.height}")
    ext = {"png": ".png", "tiff": ".tiff", "npy": ".npy"}[args.format]
    warned_8bit = False
    saved = 0
    try:
        if args.exposure:
            cam.set_exposure(args.exposure)
        for i in range(args.count):
            # Устойчивость к срывам потока (актуально для USB3 в VirtualBox):
            # на таймаут делаем несколько повторных попыток получить кадр.
            frame = finfo = None
            for attempt in range(args.retries + 1):
                try:
                    frame, finfo = cam.grab(timeout_s=args.timeout)
                    break
                except TimeoutError:
                    if attempt < args.retries:
                        print(f"  [retry] кадр {i}: таймаут, попытка "
                              f"{attempt + 2}/{args.retries + 1}...")
                        time.sleep(0.2)
                    else:
                        print(f"  [skip] кадр {i}: не пришёл за "
                              f"{args.retries + 1} попыток — пропускаю.")
            if frame is None:
                continue

            # Защита битности: для мультиспектра важно сохранять полную разрядность
            # без потерь. Предупреждаем, если кадр неожиданно оказался 8-битным.
            if frame.dtype == np.uint8 and not warned_8bit:
                print("  [WARN] кадр пришёл 8-битным — для спектрального анализа "
                      "желательно 16 бит (проверь raw/bitdepth камеры).")
                warned_8bit = True

            path = out_dir / f"frame_{i:04d}{ext}"
            if args.format == "npy":
                # Точное побайтовое сохранение массива (гарантированно без потерь).
                np.save(str(path), frame)
            else:
                # PNG и TIFF — оба без потерь и поддерживают 16 бит (uint16 сохранится).
                ok = cv2.imwrite(str(path), frame)
                if not ok:
                    raise SystemExit(f"Не удалось сохранить кадр в {path}")
            saved += 1
            print(f"  кадр {i}: {path}  ({finfo.width}x{finfo.height}, "
                  f"{frame.dtype}, ts={finfo.timestamp_us})")

            # Пауза между кадрами — даёт USB-стеку VM «передохнуть».
            if args.interval > 0 and i < args.count - 1:
                time.sleep(args.interval)
    finally:
        cam.close()
    print(f"\nИтого сохранено кадров: {saved} из {args.count}")
    return 0 if saved > 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="multicam", description="MultiCam Linux pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("selftest", help="самопроверка формул индексов (без камеры)")
    s.set_defaults(func=_cmd_selftest)

    pr = sub.add_parser("process", help="офлайн-обработка сохранённых кадров")
    pr.add_argument("--object", required=True, help="кадр объекта (.bmp/.png/.tif/.npy)")
    pr.add_argument("--reference", required=True, help="кадр референса (белый эталон)")
    pr.add_argument("--dark", help="тёмный кадр (опционально)")
    pr.add_argument("--distance", type=float, default=1.0, help="дистанция съёмки: 0.5/1.0/1.5")
    pr.add_argument("--calibration", help="явный путь к файлу калибровки")
    pr.add_argument("--calibration-dir", default=".", help="папка с calibration*.txt")
    pr.add_argument("--roi", type=int, nargs=4, metavar=("Y0", "Y1", "X0", "X1"),
                    help="область усреднения в каналах (после разрезки)")
    pr.add_argument("--custom-index", help="пользовательский индекс, напр. 'x650 / x900'")
    pr.add_argument("--maps", action="store_true", help="считать карты индексов")
    pr.add_argument("--output", help="сохранить результат в .txt")
    pr.set_defaults(func=_cmd_process)

    pb = sub.add_parser("probe", help="поиск камеры через SDK (нужно железо)")
    pb.add_argument("--lib", help="путь к libnncam.so / nncam.dll")
    pb.set_defaults(func=_cmd_probe)

    dc = sub.add_parser("doctor", help="диагностика окружения (платформа, зависимости, SDK, USB)")
    dc.add_argument("--lib", help="путь к libnncam.so / nncam.dll")
    dc.set_defaults(func=_cmd_doctor)

    cap = sub.add_parser("capture", help="захват кадров в файлы")
    cap.add_argument("--backend", default="auto", choices=["auto", "nncam", "mock"])
    cap.add_argument("--lib", help="путь к libnncam.so / nncam.dll")
    cap.add_argument("--mock-frame", help="кадр/папка для mock-бэкенда")
    cap.add_argument("--count", type=int, default=1)
    cap.add_argument("--exposure", type=int, help="экспозиция, мкс")
    cap.add_argument("--timeout", type=float, default=10.0,
                     help="ожидание одного кадра, с (по умолчанию 10)")
    cap.add_argument("--retries", type=int, default=3,
                     help="повторных попыток на кадр при таймауте (для нестабильного USB в VM)")
    cap.add_argument("--interval", type=float, default=0.0,
                     help="пауза между кадрами, с (помогает USB в VirtualBox)")
    cap.add_argument("--output-dir", default="captures")
    cap.add_argument("--format", default="png", choices=["png", "tiff", "npy"],
                     help="формат сохранения (все без потерь, 16 бит): "
                          "png — универсально; tiff — научный стандарт (и под GeoTIFF); "
                          "npy — точный numpy-массив")
    cap.set_defaults(func=_cmd_capture)

    return p


def main(argv: list[str] | None = None) -> int:
    # На Windows-консоли (cp1251) принудительно включаем UTF-8 для кириллицы.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
