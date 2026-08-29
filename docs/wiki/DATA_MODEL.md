# Data Model

## Локальные входы

- `data/aoi/selected_field_point.geojson` — выбранная точка, `EPSG:4326`.
- `data/aoi/selected_field_area.geojson` — рабочая граница, `EPSG:4326`, с `analysis_crs` и `source`.
- внешний GeoJSON границ полей — необязательный вход `split_field_boundaries.py`.

`source = nspd_getfeatureinfo` означает кадастровый контур, `source = map_point_buffer` — временный буфер.

## Промежуточные данные

- `data/interim/satellite/latest_scene.json` — metadata выбранной Sentinel-2 сцены;
- `data/interim/satellite/<scene_id>/*.tif` — обрезанные каналы;
- `data/interim/kornix_timeseries/sp_satellite_timeseries_20260401_20260827_v001/` —
  эталонная поставка суточных рядов КОРНИКС по 37 полям SP за 2026-04-01—2026-08-27:
  `sp_all_fields_all_methods_daily.csv`, 37 файлов `by_field/`, словарь
  `series_catalog.csv`, методика и `manifest.json` с SHA-256. Ключ строки:
  `field_short_name + method_code + day`; `field_short_name` имеет вид `1.1`,
  а `field_long_name` — `SP:1.1`; доступно четыре метода водного баланса.
- `data/interim/kornix_timeseries/sp_satellite_timeseries_probe/` и архив
  `sp_satellite_timeseries_20260401_20260827_v001.tar.gz` — исходная копия поставки;
  они сохраняются для трассируемости, но не являются источником для анализа.
- `data/processed/field_boundaries/*.geojson` — разделенные поля SP/KAA и минимальные прямоугольники.

## Результаты

- `outputs/rasters/ndvi.tif`;
- `outputs/rasters/ndmi.tif`;
- `outputs/rasters/savi.tif`;
- `outputs/rasters/ndre.tif`;
- `outputs/reports/latest_metrics.json` — сцена, дата, облачность, CRS и статистика каждого индекса;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_true_color.tif` — RGB Sentinel-2, обрезанный по отдельному полю и дате;
- `outputs/imagery/sentinel1/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_rtc.tif` —
  Sentinel-1 RTC, обрезанный по отдельному полю и дате, два канала Float32:
  VV и VH;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_analysis.tif` — B02/B03/B04/B05/B08/B11/B12 и SCL на общей сетке 10 м;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/cloud_mask.tif` — бинарная маска невалидных пикселей по SCL;
- `outputs/imagery/download_manifest.json` — статус загрузки всех полей KAA/SP;
- `outputs/imagery/sentinel1/download_manifest.json` — статус загрузки Sentinel-1 RTC;
- `outputs/reports/sentinel1_zonal_means.csv` — зональные средние Sentinel-1
  по каждому полю, дате и поляризации VV/VH. `zonal_mean_db` хранит
  `10*log10` от среднего линейного обратного рассеяния с исключением нулевых и
  nodata-пикселей; это источник третьего графика QGIS для SP;
- `outputs/imagery/analysis_manifest.json` — статус докачки аналитических каналов KAA/SP;
- `outputs/reports/kaa_zonal_means.csv` — зональные средние индексов по каждому готовому растровому пятну KAA;
- `outputs/reports/kaa_zonal_means.json` — параметры последнего расчета зональных средних KAA;
- `outputs/reports/sp_zonal_means.csv` — зональные средние NDVI/NDMI/NDRE/SAVI
  по растрам SP; источник для объединения с КОРНИКС;
- `outputs/reports/field_zonal_means.csv` — long-таблица зональных средних KAA/SP с колонками `dataset`, `field_id`, `scene_date`, `scene_id`, `index`, `zonal_mean`, `valid_pixel_count`, `nodata_pixel_count`, `aoi_cloud_cover`, `analysis_raster`; используется QGIS-плагином для интерактивных графиков по полю;
- `results/data/prepared_satellite_data.csv` — wide-таблица KAA `field_id × scene_date × NDMI/NDRE/SAVI/NDVI`;
- `results/data/model_dataset.csv` — объединение спутниковых и наземных измерений после появления `data/ground_measurements.csv`;
- `results/data/sp_kornix_sentinel_daily.csv` — точное объединение суточных
  рядов КОРНИКС SP выбранного метода с валидными индексами Sentinel-2;
- `results/reports/sp_kornix_sentinel_merge.json` — число совпадений и поля,
  отсутствующие у одной из сторон объединения;
- `results/tables/seasonal_summary.csv` — обзорная сезонная динамика по всем KAA-полям;
- `results/reports/satellite_quality_report.md` — отчет о дублях, пропусках, датах и диапазонах индексов;
- `outputs/maps/water_regime_gis.qgs`.

Для каждого рассчитанного индекса отчет содержит `valid_pixel_count`, `nodata_pixel_count`, `minimum`, `maximum`, `mean` и `standard_deviation`.

QGIS-график SP дополнительно читает отдельный CSV КОРНИКС из
`data/interim/kornix_timeseries/.../by_field/SP_<группа>_<поле>_daily.csv`;
для визуализации используются записи `ivanov_n4l_meteo_soil`.

При включении инструмента `График по полю` плагин добавляет временный, прозрачный
слой `КОРНИКС: подписи полей SP`. Он не меняет `SP.gpkg`; в нем для каждого
полигона хранится `field_id` и текстовая подпись. Для полей, присутствующих в
КОРНИКС, подпись содержит культуру, дату посева и погоду последнего дня ряда
(среднюю температуру, осадки и ET₀); для остальных — `КОРНИКС: нет данных`.

GeoJSON используется для небольших геометрий, GeoTIFF — для растров. Все локальные
входы и результаты исключены из git, кроме `.gitkeep` и явно согласованной поставки
КОРНИКС в `data/interim/kornix_timeseries/`.

## Будущие измерения

Для кригинга понадобится точечный слой с идентификатором, датой, координатами, числовым значением, единицами и методикой измерения.

Для табличного анализа используется `data/ground_measurements.csv` со столбцами из `data/ground_measurements.example.csv`: `field_id`, `date`, `soil_moisture`, `LAI`, `FCOVER`, дополнительные глубины влажности, полив и осадки.
