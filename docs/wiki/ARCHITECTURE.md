# Architecture

## Принцип

Проект работает как личный QGIS-плагин на macOS и Windows. Для локального
чтения документации добавлен автономный web-просмотрщик на Python standard
library; он не является API, не хранит данные и доступен только на `127.0.0.1`.
Отдельной Docker-сборки, desktop-оболочки и многопользовательского режима нет.

Диаграммы подтверждающего эксперимента Sentinel-1/Sentinel-2 остаются
воспроизводимыми PNG-файлами в `results/figures/`, но открываются из того же
QGIS-плагина, а не во внешнем просмотрщике.

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
9. `docs_site/` — localhost-сервер и статический интерфейс wiki. При каждом
   запросе сервер заново находит `docs/**/*.md`; браузер проверяет изменения
   списка статей раз в 10 секунд.

Служебные файлы исполнения не являются частью системы: Python-байткод,
`.DS_Store` и временные рендеры в `tmp/` игнорируются Git.

## Выполнение

На macOS плагин вызывает QGIS Python `/Applications/QGIS.app/Contents/MacOS/python`.
На Windows путь к QGIS и `python-qgis.bat` задается переменными среды
`QGIS_PREFIX_PATH` и `QGIS_PYTHON`. Долгие команды выполняются через `QgsTask`.
Пользователь выбирает локальный полигональный слой, а URL CSV/ZIP выгрузки
внешней модели; после новой выгрузки автоматически запускается последовательность
Sentinel-2, облачной маски, индексов, Sentinel-1 и зональных рядов только для
этого слоя. `PROGRESS` этапов передается в progress bar панели. Новые снимки
добавляются в текущую сессию QGIS, а `Собрать проект/слои` сохраняет ее в
`outputs/maps/water_regime_gis.qgs`.

Жесткие пути собраны в `qgis_plugins/water_regime_gis_plugin/settings.py` и `src/water_regime_gis/qgis_runtime.py`.

## Внешние сервисы

- НСПД: уточнение кадастрового контура через WMS `GetFeatureInfo`;
- Microsoft Planetary Computer STAC: поиск Sentinel-2 L2A и Sentinel-1 RTC;
- Sentinel-2 и Sentinel-1 COG: чтение каналов GDAL через `/vsicurl/`.

PostGIS, DEM и наземная база измерений пока отсутствуют.
