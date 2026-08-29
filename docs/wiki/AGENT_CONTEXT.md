# Agent Context

## Текущее состояние

- Основной и единственный интерфейс: QGIS-плагин `Water Regime GIS`.
- Личная среда: macOS, `/Applications/QGIS.app`, профиль `default`, репозиторий `/Users/korneev/Desktop/water-regime-gis`.
- Плагин установлен симлинком через `python3 scripts/install_qgis_plugin.py`.
- Observearth 1.0.2 и Isoliner 5.6.21 установлены в профиль QGIS.
- Работают выбор точки, fallback AOI, попытка уточнения НСПД, Sentinel-2 и индексы NDVI/NDMI/SAVI/NDRE.
- Каждый спутниковый расчет создает `outputs/reports/latest_metrics.json` со статистикой индексных растров.
- `scripts/qgis/download_field_imagery.py` загружает временной ряд RGB Sentinel-2 для каждого поля из `KAA.gpkg` и `SP.gpkg` за 2026-04-01–2026-08-10, с manifest и возобновлением по датам.
- Тот же скачиватель поддерживает Sentinel-1 RTC: параметры `--collection sentinel-1-rtc --asset vv vh --output-name sentinel_rtc.tif --no-cloud-filter` создают двухканальный VV/VH GeoTIFF в `outputs/imagery/sentinel1/`. При докачке SP сначала запускаются 37 полей из поставки КОРНИКС, затем остальные.
- `scripts/qgis/download_field_analysis.py` возобновляемо докачивает B02/B03/B04/B05/B08/B11/B12/SCL для сохраненных сцен KAA/SP, создает `sentinel_analysis.tif`, `cloud_mask.tif` и AOI-облачность.
- `scripts/qgis/calculate_kaa_zonal_means.py` считает зональное среднее NDVI/NDMI/NDRE/SAVI по каждому готовому растровому пятну KAA/SP, исключая nodata и облака. Для SP сформировано 5 436 строк в `outputs/reports/sp_zonal_means.csv`.
- QGIS-плагин имеет инструмент `График по полю`: при наведении на KAA/SP-полигон показывает `field_id`, а двойной щелчок открывает временной график NDVI/NDMI/NDRE/SAVI из `outputs/reports/field_zonal_means.csv`; все ряды fit-ятся одной восьмипараметрической unimodal double-logistic формулой с необязательной начальной полкой, без fallback на сплайн, и получают устойчивую метрику `Qrob`.
- Для SP тот же QGIS-диалог показывает вторым графиком ежедневные модельные
  ряды КОРНИКС выбранного метода: покрытие, Ks, влагу 0–10 см и ET/PET.
- При включении `График по полю` для `SP.gpkg` добавляется прозрачный временный
  слой `КОРНИКС: подписи полей SP`: для каждого поля — культура, дата посева,
  средняя температура, осадки и ET₀ последнего дня ряда; поля вне поставки
  помечаются `КОРНИКС: нет данных`.
- `scripts/analysis/run_satellite_ground_pipeline.py` преобразует long CSV KAA в wide, пишет QA, сезонные сводки, шаблон ground-данных, model dataset и skipped-отчет M1–M4 до появления `data/ground_measurements.csv`.
- Isoliner открывает `isoliner:raster_to_isolines` и `isoliner:kriging2d`.
- Кригинг требует реальный точечный слой минимум с тремя объектами и числовым полем.
- `Собрать проект/слои` загружает доступные AOI/растры без дублей и сохраняет текущую сессию в `outputs/maps/water_regime_gis.qgs`.
- Legacy web/desktop/Docker/Windows/release-код удален.
- Пользовательские данные и производные результаты не коммитятся, кроме явно
  согласованной поставки КОРНИКС в `data/interim/kornix_timeseries/`.
- Поставка КОРНИКС SP за 2026-04-01—2026-08-27 включает 37 полей, 149 дней,
  четыре метода и 22 052 записи. Эталонный каталог —
  `sp_satellite_timeseries_20260401_20260827_v001`; ключ —
  `field_short_name + method_code + day`; `field_short_name` имеет вид `1.1`.
- `scripts/analysis/merge_kornix_sentinel.py` объединяет КОРНИКС с валидными
  SP-индексами Sentinel-2 по нормализованному полю и точной дате. На 2026-08-28
  получено 448 совпадений по всем 37 полям для `ivanov_n4l_meteo_soil`.

## Следующие функции

1. Выбор конкретного контура, если НСПД возвращает неоднозначный объект.
2. Заполнить `data/ground_measurements.csv` реальными soil moisture/LAI/FCOVER и перезапустить analysis-пайплайн.
3. DEM: уклон, экспозиция, аккумуляция стока и водосборы.
4. Временные ряды и итоговая классификация зон водного режима.

Перед изменениями читать `README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `PIPELINES.md` и `DECISIONS.md`.
