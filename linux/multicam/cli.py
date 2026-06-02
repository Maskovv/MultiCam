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


def _cmd_capture(args: argparse.Namespace) -> int:
    import cv2  # noqa: WPS433
    from .camera import open_camera

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cam = open_camera(backend=args.backend, lib_path=args.lib, frame_path=args.mock_frame)
    info = cam.open()
    print(f"Открыта камера: {info.name} {info.width}x{info.height}")
    try:
        if args.exposure:
            cam.set_exposure(args.exposure)
        for i in range(args.count):
            frame, finfo = cam.grab(timeout_s=args.timeout)
            path = out_dir / f"frame_{i:04d}.png"
            cv2.imwrite(str(path), frame)
            print(f"  кадр {i}: {path}  ({finfo.width}x{finfo.height}, ts={finfo.timestamp_us})")
    finally:
        cam.close()
    return 0


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

    cap = sub.add_parser("capture", help="захват кадров в файлы")
    cap.add_argument("--backend", default="auto", choices=["auto", "nncam", "mock"])
    cap.add_argument("--lib", help="путь к libnncam.so / nncam.dll")
    cap.add_argument("--mock-frame", help="кадр/папка для mock-бэкенда")
    cap.add_argument("--count", type=int, default=1)
    cap.add_argument("--exposure", type=int, help="экспозиция, мкс")
    cap.add_argument("--timeout", type=float, default=5.0)
    cap.add_argument("--output-dir", default="captures")
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
