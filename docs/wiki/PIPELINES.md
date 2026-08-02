# Pipelines

## Принцип

Пайплайны должны быть простыми, воспроизводимыми и пригодными для запуска на macOS. Сложная обработка добавляется только после появления тестового AOI и набора данных.

## Планируемые пайплайны

## 1. Подготовка AOI

Вход:

- `data/aoi/tula_test_field.geojson`;
- целевой CRS `EPSG:32637`.

Выход:

- нормализованный слой AOI в `data/aoi/`.
- рабочая копия `data/interim/tula_test_field.normalized.geojson` при запуске `scripts/check_aoi.py --write-normalized`.

Команда:

```bash
python3 scripts/check_aoi.py --write-normalized
```

Текущая проверка:

- читает GeoJSON стандартной библиотекой Python;
- проверяет тип `Polygon`;
- проверяет замкнутость кольца;
- считает bbox в `EPSG:4326`;
- считает примерную площадь в гектарах;
- проверяет, что bbox попадает в ожидаемые пределы Тульской области.

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
- слой `Tula test field AOI`;
- CRS проекта `EPSG:32637`;
- простой зеленый стиль AOI.

Новые команды должны фиксировать:

- рабочую директорию;
- Python-окружение;
- входные параметры;
- выходные файлы.
