# Agent Context

## Текущее состояние

- Основной и единственный интерфейс: QGIS-плагин `Water Regime GIS`.
- Личная среда: macOS, `/Applications/QGIS.app`, профиль `default`, репозиторий `/Users/korneev/Desktop/water-regime-gis`.
- Плагин установлен симлинком через `python3 scripts/install_qgis_plugin.py`.
- Observearth 1.0.2 и Isoliner 5.6.21 установлены в профиль QGIS.
- Работают выбор точки, fallback AOI, попытка уточнения НСПД, Sentinel-2 и индексы NDVI/NDMI/SAVI/NDRE.
- Каждый спутниковый расчет создает `outputs/reports/latest_metrics.json` со статистикой индексных растров.
- `scripts/qgis/download_field_imagery.py` загружает временной ряд RGB Sentinel-2 для каждого поля из `KAA.gpkg` и `SP.gpkg` за 2026-04-01–2026-08-10, с manifest и возобновлением по датам.
- `scripts/qgis/download_field_analysis.py` возобновляемо докачивает B02/B03/B04/B05/B08/B11/B12/SCL для сохраненных сцен KAA/SP, создает `sentinel_analysis.tif`, `cloud_mask.tif` и AOI-облачность.
- `scripts/qgis/calculate_kaa_zonal_means.py` считает зональное среднее NDVI/NDMI/NDRE/SAVI по каждому готовому растровому пятну KAA, исключая nodata и облака, и пишет `outputs/reports/kaa_zonal_means.csv`.
- QGIS-плагин имеет инструмент `График по полю`: при наведении на KAA/SP-полигон показывает `field_id`, а двойной щелчок открывает временной график NDVI/NDMI/NDRE/SAVI из `outputs/reports/field_zonal_means.csv`; каждый `field_id + index` fit-ится отдельно, предпочтительно одной seasonal double-logistic формой, без искусственного дорисовывания полки.
- `scripts/analysis/run_satellite_ground_pipeline.py` преобразует long CSV KAA в wide, пишет QA, сезонные сводки, шаблон ground-данных, model dataset и skipped-отчет M1–M4 до появления `data/ground_measurements.csv`.
- Isoliner открывает `isoliner:raster_to_isolines` и `isoliner:kriging2d`.
- Кригинг требует реальный точечный слой минимум с тремя объектами и числовым полем.
- `Собрать проект/слои` загружает доступные AOI/растры без дублей и сохраняет текущую сессию в `outputs/maps/water_regime_gis.qgs`.
- Legacy web/desktop/Docker/Windows/release-код удален.
- Пользовательские данные и производные результаты не коммитятся.

## Следующие функции

1. Выбор конкретного контура, если НСПД возвращает неоднозначный объект.
2. Заполнить `data/ground_measurements.csv` реальными soil moisture/LAI/FCOVER и перезапустить analysis-пайплайн.
3. DEM: уклон, экспозиция, аккумуляция стока и водосборы.
4. Временные ряды и итоговая классификация зон водного режима.

Перед изменениями читать `README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `PIPELINES.md` и `DECISIONS.md`.
