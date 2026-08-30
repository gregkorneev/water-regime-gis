# Data Model

## Локальные входы

- `data/aoi/selected_field_point.geojson` — выбранная точка, `EPSG:4326`.
- `data/aoi/selected_field_area.geojson` — рабочая граница, `EPSG:4326`, с `analysis_crs` и `source`.
- внешний GeoJSON границ полей — необязательный вход `split_field_boundaries.py`.

`source = nspd_getfeatureinfo` означает кадастровый контур, `source = map_point_buffer` — временный буфер.

## Промежуточные данные

- `data/interim/satellite/latest_scene.json` — metadata выбранной Sentinel-2 сцены;
- `data/interim/external_timeseries/<timestamp>/` — неизменяемая выгрузка CSV или ZIP внешнего сервиса; `latest.json` хранит URL, период и список CSV последней выгрузки. Для запуска автоматического обновления в одном из CSV обязательна колонка `day` или `date` с датой ISO-8601.
- `data/interim/satellite/<scene_id>/*.tif` — обрезанные каналы;
- `data/interim/kornix_timeseries/sp_all_calculation_timeseries_20260401_20260827_v006/` —
  эталонная поставка v006 суточных рядов КОРНИКС по 37 полям SP за 2026-04-01—2026-08-27:
  `sp_all_fields_all_methods_daily.csv`, 37 файлов `by_field/`, словарь
  `series_catalog.csv`, методика и `manifest.json` с SHA-256. Ключ строки:
  `field_short_name + method_code + day`; `field_short_name` имеет вид `1.1`,
  а `field_long_name` — `SP:1.1`; доступно четыре метода водного баланса.
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
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_fcover.tif` — FCover Sentinel-2 (Float32, диапазон 0–1) по SNAP-совместимой модели; `-9999` обозначает невалидный пиксель;
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
- `outputs/reports/sp_zonal_means.csv` — зональные средние NDVI/NDMI/NDRE/SAVI/FCOVER
  по растрам SP; источник для объединения с КОРНИКС;
- `outputs/reports/field_zonal_means.csv` — long-таблица зональных средних KAA/SP с колонками `dataset`, `field_id`, `scene_date`, `scene_id`, `index`, `zonal_mean`, `valid_pixel_count`, `nodata_pixel_count`, `aoi_cloud_cover`, `analysis_raster`; используется QGIS-плагином для интерактивных графиков по полю;
- `results/data/prepared_satellite_data.csv` — wide-таблица KAA `field_id × scene_date × NDMI/NDRE/SAVI/NDVI`;
- `results/tables/external_index_models.csv` — линейные модели внешняя числовая переменная → индекс Sentinel-2, построенные только по точным совпадениям `field_id + date`; для каждой связи хранятся коэффициенты, Pearson r, R² и число пар.
- `results/data/model_dataset.csv` — объединение спутниковых и наземных измерений после появления `data/ground_measurements.csv`;
- `results/data/sp_kornix_sentinel_daily.csv` — точное объединение суточных
  рядов КОРНИКС SP выбранного метода с валидными индексами Sentinel-2;
- `results/reports/sp_kornix_sentinel_merge.json` — число совпадений и поля,
  отсутствующие у одной из сторон объединения;
- `results/tables/sp_kornix_expected_fcover_by_field.csv` — прямое
  сопоставление `satellite_fcover_expected` КОРНИКС с FCOVER Sentinel-2 на
  совпадающие даты, отдельно по каждому полю: число пар, Pearson r, средние,
  bias, MAE, RMSE и воспроизводимая группа совпадения;
- `results/data/sp_kornix_sentinel1_moisture.csv` — точное объединение
  Sentinel-1 VV/VH с влагой КОРНИКС 0–10 см и суммами осадков/полива за 3 и 7 суток;
- `results/reports/sp_kornix_sentinel1_moisture.json` — оценка связи Sentinel-1
  и КОРНИКС после учета поступления воды;
- `results/data/sp_kornix_sentinel1_field_holdout_predictions.csv` —
  ретроспективная реконструкция влаги КОРНИКС 0–10 см для 14 полей, не
  участвовавших в обучении;
- `results/reports/sp_kornix_sentinel1_field_holdout.json` — состав split 23/14
  и метрики воспроизведения КОРНИКС по Sentinel-1 и поступлению воды;
- `results/tables/seasonal_summary.csv` — обзорная сезонная динамика по всем KAA-полям;
- `results/reports/satellite_quality_report.md` — отчет о дублях, пропусках, датах и диапазонах индексов;
- `outputs/maps/water_regime_gis.qgs`.

Для каждого рассчитанного индекса отчет содержит `valid_pixel_count`, `nodata_pixel_count`, `minimum`, `maximum`, `mean` и `standard_deviation`.

QGIS-график SP дополнительно читает отдельный CSV КОРНИКС v006 из
`data/interim/kornix_timeseries/sp_all_calculation_timeseries_20260401_20260827_v006/by_field/SP_<группа>_<поле>_daily.csv`;
для визуализации используются записи `ivanov_n4l_meteo_soil`.

Для кнопки `Средний график` плагин читает эти же исходные файлы напрямую, не
создавая отдельной производной таблицы: данные остаются актуальными на момент
нажатия кнопки. В агрегат включаются поля с файлом КОРНИКС выбранного метода,
кроме `SP_2_7`, `SP_4_3`, `SP_6_6`, `SP_6_7` и `SP_7_3`.

При включении инструмента `График по полю` плагин добавляет временный служебный
слой `КОРНИКС: подписи полей SP`. Он не меняет `SP.gpkg`; в нем для каждого
полигона хранится `field_id` и текстовая подпись. Подпись показывается только
для полей, присутствующих в КОРНИКС, и содержит культуру, дату посева и погоду
последнего дня ряда (среднюю температуру, осадки и ET₀); эти поля также
выделяются цветом. SP 7.3 не добавляется в этот интерактивный слой и не
показывается инструментом графика, однако его исходные данные остаются в
поставке и локальных отчетах.

GeoJSON используется для небольших геометрий, GeoTIFF — для растров. Все локальные
входы и результаты исключены из git, кроме `.gitkeep` и явно согласованной поставки
КОРНИКС в `data/interim/kornix_timeseries/`.

## Будущие измерения

Для кригинга понадобится точечный слой с идентификатором, датой, координатами, числовым значением, единицами и методикой измерения.

Для табличного анализа используется `data/ground_measurements.csv` со столбцами из `data/ground_measurements.example.csv`: `field_id`, `date`, `soil_moisture`, `LAI`, `FCOVER`, дополнительные глубины влажности, полив и осадки.
