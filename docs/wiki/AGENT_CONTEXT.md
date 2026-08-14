# Agent Context

## Текущее состояние

- Основной и единственный интерфейс: QGIS-плагин `Water Regime GIS`.
- Личная среда: macOS, `/Applications/QGIS.app`, профиль `default`, репозиторий `/Users/korneev/Desktop/water-regime-gis`.
- Плагин установлен симлинком через `python3 scripts/install_qgis_plugin.py`.
- Observearth 1.0.2 и Isoliner 5.6.21 установлены в профиль QGIS.
- Работают выбор точки, fallback AOI, попытка уточнения НСПД, Sentinel-2 и индексы NDVI/NDMI/NDWI/MNDWI/SAVI/NDRE.
- Каждый спутниковый расчет создает `outputs/reports/latest_metrics.json` со статистикой индексных растров.
- `scripts/qgis/download_field_imagery.py` загружает временной ряд RGB Sentinel-2 для каждого поля из `KAA.gpkg` и `SP.gpkg` за 2026-04-01–2026-08-10, с manifest и возобновлением по датам.
- Isoliner открывает `isoliner:raster_to_isolines` и `isoliner:kriging2d`.
- Кригинг требует реальный точечный слой минимум с тремя объектами и числовым полем.
- `Собрать проект/слои` загружает доступные AOI/растры без дублей и сохраняет текущую сессию в `outputs/maps/water_regime_gis.qgs`.
- Legacy web/desktop/Docker/Windows/release-код удален.
- Пользовательские данные и производные результаты не коммитятся.

## Следующие функции

1. Выбор конкретного контура, если НСПД возвращает неоднозначный объект.
2. Импорт реальных наземных измерений и кригинг.
3. DEM: уклон, экспозиция, аккумуляция стока и водосборы.
4. Временные ряды и итоговая классификация зон водного режима.

Перед изменениями читать `README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `PIPELINES.md` и `DECISIONS.md`.
