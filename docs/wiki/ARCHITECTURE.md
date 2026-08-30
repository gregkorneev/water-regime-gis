# Architecture

## Принцип

Проект работает только как личный QGIS-плагин на macOS. Отдельного web-сервиса, desktop-оболочки, Docker-сборки, HTTP API и многопользовательского режима нет.

## Состав

1. `qgis_plugins/water_regime_gis_plugin/` — меню, toolbar action и dock-панель QGIS.
2. `scripts/qgis/` — PyQGIS/GDAL-операции выбора поля, НСПД, Sentinel-2 и импорта границ.
3. `src/water_regime_gis/` — только общие функции конфигурации, CRS и QGIS runtime.
4. `scripts/analysis/` — воспроизводимые табличные расчеты по спутниковым индексам и будущим наземным измерениям.
5. `configs/project.example.json` — конфигурация QGIS/Sentinel-пайплайна.
6. `configs/analysis.example.json` — конфигурация табличного анализа.
7. `data/` — AOI, промежуточные и обработанные данные, версионируемые вместе с проектом.
8. `outputs/` и `results/` — растры, QGIS-проекты и табличные результаты,
   версионируемые вместе с проектом.

## Выполнение

Плагин вызывает QGIS Python `/Applications/QGIS.app/Contents/MacOS/python`. Долгие команды выполняются через `QgsTask`. Пользователь выбирает локальный полигональный слой, а URL CSV/ZIP выгрузки внешней модели; после новой выгрузки автоматически запускается последовательность Sentinel-2, облачной маски, индексов, Sentinel-1 и зональных рядов только для этого слоя. `PROGRESS` этапов передается в progress bar панели. Новые снимки добавляются в текущую сессию QGIS, а `Собрать проект/слои` сохраняет ее в `outputs/maps/water_regime_gis.qgs`.

Жесткие пути собраны в `qgis_plugins/water_regime_gis_plugin/settings.py` и `src/water_regime_gis/qgis_runtime.py`.

## Внешние сервисы

- НСПД: уточнение кадастрового контура через WMS `GetFeatureInfo`;
- Microsoft Planetary Computer STAC: поиск Sentinel-2 L2A и Sentinel-1 RTC;
- Sentinel-2 и Sentinel-1 COG: чтение каналов GDAL через `/vsicurl/`.

PostGIS, DEM и наземная база измерений пока отсутствуют.
