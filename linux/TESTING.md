# Как мы тестируем порт (Ubuntu 22.04 VM → потом Jetson)

Тестирование делится на **3 уровня**:

```
Уровень 1: формулы и парсеры        → VM, без камеры, без OpenCV   (✅ проверено)
Уровень 2: офлайн-пайплайн на кадре  → VM, без камеры, с OpenCV     (✅ проверено)
Уровень 3: живой захват с камеры     → камера по USB + libnncam.so  (✅ проверено в VirtualBox!)
```

> ✅ **Статус:** живой захват кадра 2048×2048 с камеры `BigEye4200KME` получен на
> Ubuntu в VirtualBox через `libnncam.so` — без Windows и без штатного `.exe`.
> Цепочка «камера → Linux-SDK → кадр → файл» работает.

---

## ⭐ Быстрый сквозной прогон (все команды по порядку)

Это «шпаргалка»: команды друг за другом, как мы реально запускали. Реальная раскладка
в VM: проект в `~/obshaya`, venv в `~/venvs/multicam`, библиотека и udev-правило в
`~/obshaya`. Пути при необходимости подставь свои.

```bash
# (0) Активировать окружение и перейти в проект
source ~/venvs/multicam/bin/activate
cd ~/obshaya

# (1) Самопроверка формул индексов (без камеры) — должно быть "ВСЕ ИНДЕКСЫ СОВПАЛИ"
python -m multicam.cli selftest

# (2) Полный набор юнит-тестов (без камеры)
pytest -v

# (3) Офлайн-обработка реального кадра (без камеры): кадр -> каналы -> индексы
python -m multicam.cli process \
  --object Reference/fr_14_41_17_557.bmp \
  --reference Reference/fr_14_41_17_557.bmp \
  --distance 1.0 --calibration-dir . \
  --roi 100 400 100 400 \
  --output result.txt

# (4) Диагностика окружения перед камерой (платформа, зависимости, SDK, USB)
python -m multicam.cli doctor --lib ~/obshaya/libnncam.so

# (5) ОДИН РАЗ: установить udev-правило для доступа к камере без sudo,
#     затем ФИЗИЧЕСКИ переподключить камеру (вынуть-вставить USB)
sudo cp ~/obshaya/99-toupcam.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

# (6) Проверить, что Linux видит камеру по USB
lsusb

# (7) Найти камеру через SDK
python -m multicam.cli probe --lib ~/obshaya/libnncam.so

# (8) Захватить кадры с камеры в папку captures/
#     По умолчанию PNG (16 бит, без потерь). Для научного анализа/GeoTIFF: --format tiff.
#     Для точного numpy-массива без OpenCV: --format npy.
#     В VirtualBox поток USB3 нестабилен — помогают --interval (пауза) и --retries.
python -m multicam.cli capture --backend nncam --count 5 \
  --exposure 10000 --lib ~/obshaya/libnncam.so --output-dir captures \
  --format tiff --interval 1.0 --retries 5

# (9) Прогнать реально снятый кадр через обработку
#     (пока object = reference, просто чтобы проверить, что пайплайн ест живой кадр)
python -m multicam.cli process \
  --object captures/frame_0000.png \
  --reference captures/frame_0000.png \
  --distance 1.0 --calibration-dir . \
  --roi 100 400 100 400
```

> Если в твоей раскладке проект лежит в `~/obshaya/linux`, а калибровки/`Reference`
> на уровень выше — используй `--calibration-dir ..` и пути `../Reference/...`.

---

## Подробные пояснения по каждому уровню

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
    --object /Reference/fr_14_41_17_557.bmp \
    --reference /Reference/fr_14_41_17_557.bmp \
    --distance 1.0 --calibration-dir  \
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

## Диагностика окружения — команда `doctor`

Перед попыткой работы с камерой запусти диагностику. Она проверяет платформу,
архитектуру, Python-зависимости, загрузку SDK, наличие устройства в `lsusb` и
перечисление камер:

```bash
python -m multicam.cli doctor
```

По выводу сразу видно, чего не хватает (модуль, библиотека, USB-устройство, udev).

## Уровень 3 — живой захват с камеры

> ⚠️ **Важно про архитектуру.** Библиотека `libnncam.so` должна совпадать с
> архитектурой системы, где запущен Python:
> * **Ubuntu в VirtualBox на ноутбуке = x86_64 → нужен `x64/libnncam.so`** (НЕ arm64!);
> * **реальный Jetson Orin Nano = aarch64 → нужен `arm64/libnncam.so`**.
> Это самая частая ошибка: берут arm64-файл для VM и получают «не загружается».

### 3A. Живой тест в VirtualBox (proof-of-concept на ноутбуке)

Это законный способ убедиться, что камера в принципе видна Linux и отдаёт кадр.
Полноценную стабильность стрима в VM не гарантируем — финал всё равно на Jetson.

**Шаг 1. Включить USB в VirtualBox**
1. Установить **VirtualBox Extension Pack** той же версии, что и VirtualBox
   (без него нет USB 2.0/3.0).
2. ВМ выключить → **Settings → USB** → выбрать **USB 3.0 (xHCI)**.
3. Нажать «+», добавить камеру в **USB Device Filters** (чтобы пробрасывалась автоматически).
4. На хосте (Windows) закрыть штатное ПО MultiCam, чтобы оно не держало камеру.

**Шаг 2. Дать права на USB внутри Ubuntu**
```bash
sudo usermod -aG vboxusers $USER   # затем перелогиниться
```

**Шаг 3. Подключить камеру и проверить, что Linux её видит**
```bash
lsusb        # в списке должно появиться устройство камеры (ToupTek/похожее)
```
Если в `lsusb` устройства нет — проблема в пробросе VirtualBox (фильтр/Extension Pack),
а не в нашем коде.

**Шаг 4. Положить x64-библиотеку и запустить диагностику**
```bash
python -m multicam.cli doctor --lib ~/obshaya/libnncam.so
```

**Шаг 5. ОБЯЗАТЕЛЬНО: установить udev-правило (иначе ошибка доступа)**

Без udev-правила `probe` может находить камеру, но `capture` падает на старте потока
с ошибкой `HRESULT=0x80070005` (E_ACCESSDENIED) — у процесса нет прав на чтение/запись
USB-устройства. Лечится так:

```bash
sudo cp ~/obshaya/99-toupcam.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# затем ФИЗИЧЕСКИ переподключить камеру (вынуть-вставить USB)
```

> Быстрая проверка, что проблема именно в правах: запуск под root должен срабатывать —
> `sudo ~/venvs/multicam/bin/python -m multicam.cli capture --backend nncam --count 1 --lib ~/obshaya/libnncam.so --output-dir captures`.
> Если под `sudo` работает, а без — нет, значит дело в udev (правило не применилось/не переподключили камеру).

**Шаг 6. Обнаружение и захват**
```bash
python -m multicam.cli probe --lib ~/obshaya/libnncam.so

python -m multicam.cli capture --backend nncam --count 5 \
    --exposure 10000 --output-dir captures --lib ~/obshaya/libnncam.so
```

> Если `probe` находит камеру, но `capture` рвётся/таймаутит (а доступ уже починен) —
> это нестабильность USB3 в VirtualBox. Снизь нагрузку (меньше кадров, больше
> `--timeout`), воткни в USB-порт напрямую без хабов, либо переходи к Jetson.

### Что делать, если кадр 0 снялся, а дальше `TimeoutError`

Это самый типичный симптом в VirtualBox: первый кадр приходит, непрерывный поток
обрывается. Это **ограничение виртуалки, а не кода**. Варианты по возрастанию усилий:

1. **Снимать с паузой и ретраями** (код уже умеет):
   ```bash
   python -m multicam.cli capture --backend nncam --count 5 \
     --lib ~/obshaya/libnncam.so --output-dir captures \
     --interval 1.0 --retries 5 --timeout 15
   ```
   Пауза между кадрами даёт USB-стеку VM «выдохнуть», ретраи переживают единичные срывы.
2. **Снимать по одному кадру** — единичный захват работает стабильно:
   ```bash
   python -m multicam.cli capture --backend nncam --count 1 --lib ~/obshaya/libnncam.so
   ```
   Для дрона это и есть основной сценарий (периодические снимки, а не видео).
3. **Сменить контроллер USB в настройках VM** на **USB 2.0 (EHCI)** — медленнее, но для
   изохронного потока часто стабильнее, чем эмуляция USB 3.0 (xHCI).
4. **Перейти на Jetson** — там нативный USB, без прослойки виртуализации, поток ровный.

### 3B. Финальный тест на Jetson Orin Nano (aarch64)

```bash
# arm64-библиотека + udev-правило из SDK ToupTek:
sudo cp arm64/libnncam.so /usr/local/lib/ && sudo ldconfig
sudo cp 99-toupcam.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

python -m multicam.cli doctor
python -m multicam.cli probe
python -m multicam.cli capture --backend nncam --count 5 \
    --exposure 10000 --output-dir captures
```

SDK ToupTek (x64 и arm64 в одном архиве) — раздел Development Kits на
[официальном центре загрузок](https://www.touptekphotonics.com/download/).

Дальше эти кадры прогоняем через `process` (уровень 2) — так замыкаем полный цикл
«камера → обработка → индексы».

## Тест mock-камеры (имитация захвата в VM)

Чтобы проверить код захвата без железа, mock-бэкенд отдаёт кадры из файлов:

```bash
python -m multicam.cli capture --backend mock \
    --mock-frame ../Reference/fr_14_41_17_557.bmp --count 3 --output-dir captures
```

## Чек-лист «всё ок»

- [x] `selftest` → все индексы OK
- [x] `pytest` → зелёный
- [x] `process` на BMP → выводит спектр и индексы, пишет `result.txt`
- [x] `doctor` → зависимости и SDK без FAIL
- [x] (VM) `lsusb` видит камеру
- [x] (VM) `probe` находит камеру
- [x] udev-правило установлено, ошибка доступа `0x80070005` устранена
- [x] (VM) `capture` сохраняет кадры ← **получен живой кадр 2048×2048**
- [ ] спектр/индексы из нашего пайплайна совпадают с выводом штатного ПО на тех же кадрах
- [ ] карта «тайл → длина волны» сверена с реальным кадром (`config/channels.yaml`)
- [ ] (Jetson) повторить прогон с `arm64/libnncam.so`
