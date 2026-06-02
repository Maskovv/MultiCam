# Как мы тестируем порт (Ubuntu 22.04 VM → потом Jetson)

Тестирование делится на **3 уровня**. В виртуалке без камеры проходят уровни 1–2,
полностью «живой» уровень 3 — на реальном Jetson с подключённой камерой.

```
Уровень 1: формулы и парсеры        → VM, без камеры, без OpenCV   (есть сейчас)
Уровень 2: офлайн-пайплайн на кадре  → VM, без камеры, с OpenCV     (есть сейчас)
Уровень 3: живой захват с камеры     → Jetson + libnncam.so + USB   (код готов, нужно железо)
```

## 0. Доступ к коду в VM через общую папку

У тебя уже настроена общая папка VirtualBox (мост Windows ↔ Ubuntu). Папка с Windows
обычно монтируется в `/media/sf_<ИмяПапки>`. Проверь:

```bash
ls /media/sf_*        # увидишь содержимое D:\multi Cam
# чтобы текущий пользователь имел доступ к shared folder:
sudo usermod -aG vboxsf $USER     # затем перелогиниться
```

> Работать с git прямо в общей папке можно, но удобнее **скопировать проект внутрь VM**
> (быстрее и без проблем с правами/симлинками):
>
> ```bash
> cp -r /media/sf_multi\ Cam/MultiCam ~/multicam && cd ~/multicam/linux
> ```
>
> Либо просто склонировать наш репозиторий с GitHub:
> ```bash
> git clone https://github.com/Maskovv/MultiCam.git ~/multicam && cd ~/multicam/linux
> ```

## 1. Окружение

```bash
cd ~/multicam/linux
sudo apt update && sudo apt install -y python3-venv python3-pip
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Уровень 1 — формулы и парсеры (без камеры)

Это «дымовой тест»: проверяет, что математика индексов совпадает со штатным ПО.

```bash
python -m multicam.cli selftest
```

Ожидаемо: все 6 индексов `[OK]`, итог «ВСЕ ИНДЕКСЫ СОВПАЛИ».

Полный набор юнит-тестов:

```bash
pip install pytest
pytest -v
```

Проверяется:
- совпадение NDVI/CIre/MCARI/NDVIre/CAR/PSSRc с эталоном;
- работа формул и на скаляре, и на массивах (карты индексов);
- пользовательский индекс и защита от инъекций кода;
- парсинг реальных `calibration05/10/15.txt` (12 каналов, опорный 800 нм = 0 сдвиг).

## Уровень 2 — офлайн-пайплайн на реальном кадре (без камеры)

Используем сохранённый кадр `Reference/fr_14_41_17_557.bmp` (2048×2048) как вход.
Здесь нужен OpenCV (стоит из `requirements.txt`).

```bash
python -m multicam.cli process \
    --object ../Reference/fr_14_41_17_557.bmp \
    --reference ../Reference/fr_14_41_17_557.bmp \
    --distance 1.0 --calibration-dir .. \
    --roi 100 400 100 400 \
    --output result.txt
```

Что проверяем:
- кадр режется на 12 каналов, каналы совмещаются по калибровке;
- считается отражение и спектр по области;
- выводятся индексы; формат `result.txt` совпадает с форматом штатного ПО (`grafik`).

> Когда у нас будут отдельные кадры объекта и белого эталона из реальной съёмки —
> подставляем их в `--object` и `--reference` и сверяем спектр/индексы с тем, что
> выдавала Windows-программа на тех же данных. Это и есть проверка «функция в функцию».

Пользовательский индекс и карты:

```bash
python -m multicam.cli process --object ../Reference/fr_14_41_17_557.bmp \
    --reference ../Reference/fr_14_41_17_557.bmp \
    --calibration-dir .. --custom-index "x650 / x900" --maps
```

## Уровень 3 — живой захват (Jetson + камера)

В обычной VirtualBox это делать не рекомендуется (USB3-камера капризна к проброшенному
USB). Делаем на реальном Jetson Orin Nano.

### 3.1 Установка SDK под Linux arm64

1. Скачать SDK ToupTek (раздел Development Kits) с
   [официального центра загрузок](https://www.touptekphotonics.com/download/).
2. Взять из него `arm64/libnncam.so` (или `libtoupcam.so`) и udev-правило
   `99-toupcam.rules`.
3. Установить:

```bash
sudo cp libnncam.so /usr/local/lib/ && sudo ldconfig
sudo cp 99-toupcam.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 3.2 Проверка обнаружения и захвата

```bash
# Камера должна определиться без root (через udev-правило):
python -m multicam.cli probe

# Захват 5 кадров:
python -m multicam.cli capture --backend nncam --count 5 \
    --exposure 10000 --output-dir captures
```

Дальше эти кадры прогоняем через `process` (уровень 2) — так замыкаем полный цикл
«камера → обработка → индексы» уже на целевом железе.

## Тест mock-камеры (имитация захвата в VM)

Чтобы проверить код захвата без железа, mock-бэкенд отдаёт кадры из файлов:

```bash
python -m multicam.cli capture --backend mock \
    --mock-frame ../Reference/fr_14_41_17_557.bmp --count 3 --output-dir captures
```

## Чек-лист «всё ок»

- [ ] `selftest` → все индексы OK
- [ ] `pytest` → зелёный
- [ ] `process` на BMP → выводит спектр и индексы, пишет `result.txt`
- [ ] (Jetson) `probe` находит камеру
- [ ] (Jetson) `capture` сохраняет кадры
- [ ] спектр/индексы из нашего пайплайна совпадают с выводом штатного ПО на тех же кадрах
