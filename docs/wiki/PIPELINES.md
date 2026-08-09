# Pipelines

## Принцип

Пайплайны должны быть простыми, воспроизводимыми и пригодными для запуска на macOS. Сложная обработка добавляется только после появления тестового AOI и набора данных.

## Планируемые пайплайны

## 1. Выбор поля

Вход:

- точка, выбранная пользователем на карте;
- целевой CRS `EPSG:32637`.

Выход:

- `data/aoi/selected_field_point.geojson`;
- `data/aoi/selected_field_area.geojson`.

Команда:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/select_field_point.py --lon 38.107 --lat 53.84
```

Текущая логика:

- принимает координаты точки в `EPSG:4326`;
- через PyQGIS перепроецирует точку в рабочую CRS;
- строит временный буфер вокруг точки;
- сохраняет точку и рабочую область как GeoJSON.

До подключения источника реальных границ полей буфер является временной рабочей областью, а не научно подтвержденной границей поля.

## 2. Подготовка спутниковых данных

Вход:

- Sentinel-2 или Landsat сцены;
- AOI;
- параметры облачности и дат.

Выход:

- обрезанные и приведенные к общему CRS растры.

## 3. Расчет спектральных индексов

Вход:

- подготовленные каналы спутниковых данных.

Выход:

- GeoTIFF для NDVI, NDMI, NDWI, MNDWI, SAVI, NDRE.

## 4. DEM-анализ

Вход:

- DEM;
- AOI.

Выход:

- уклон;
- экспозиция;
- аккумуляция стока;
- водосборы.

## 5. Сравнительный анализ

Вход:

- индексы;
- DEM-производные;
- зоны или сетка анализа.

Выход:

- таблицы CSV/Parquet;
- векторные слои GeoPackage;
- карты.

## Команды запуска

Проверка структуры проекта:

```bash
python3 scripts/check_project.py
```

Команда:

- запускается из корня проекта;
- использует стандартную библиотеку Python;
- читает `configs/project.example.json`;
- проверяет наличие обязательных каталогов;
- не читает и не изменяет геоданные.

Запуск desktop-приложения:

```bash
python3 scripts/run_app.py
```

Проверка модели интерфейса без открытия окна:

```bash
python3 scripts/check_app.py
```

Проверка QGIS/PyQGIS-контекста через приложение или напрямую:

```bash
<qgis-python> scripts/qgis/check_qgis_context.py
```

`<qgis-python>` должен быть указан в `configs/project.example.json` как `qgis.python_executable`.

Создание демонстрационного QGIS-проекта:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/create_demo_project.py
```

Выход:

- `outputs/maps/water_regime_gis.qgs`;
- `outputs/maps/water_regime_gis_preview.png`;
- слой `Selected field point`;
- слой `Selected field working area`;
- CRS проекта `EPSG:32637`;
- простой зеленый стиль рабочей области.

Новые команды должны фиксировать:

- рабочую директорию;
- Python-окружение;
- входные параметры;
- выходные файлы.
