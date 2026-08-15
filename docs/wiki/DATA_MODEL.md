# Data Model

## Локальные входы

- `data/aoi/selected_field_point.geojson` — выбранная точка, `EPSG:4326`.
- `data/aoi/selected_field_area.geojson` — рабочая граница, `EPSG:4326`, с `analysis_crs` и `source`.
- внешний GeoJSON границ полей — необязательный вход `split_field_boundaries.py`.

`source = nspd_getfeatureinfo` означает кадастровый контур, `source = map_point_buffer` — временный буфер.

## Промежуточные данные

- `data/interim/satellite/latest_scene.json` — metadata выбранной Sentinel-2 сцены;
- `data/interim/satellite/<scene_id>/*.tif` — обрезанные каналы;
- `data/processed/field_boundaries/*.geojson` — разделенные поля SP/KAA и минимальные прямоугольники.

## Результаты

- `outputs/rasters/ndvi.tif`;
- `outputs/rasters/ndmi.tif`;
- `outputs/rasters/ndwi.tif`;
- `outputs/rasters/mndwi.tif`;
- `outputs/rasters/savi.tif`;
- `outputs/rasters/ndre.tif`;
- `outputs/reports/latest_metrics.json` — сцена, дата, облачность, CRS и статистика каждого индекса;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_true_color.tif` — RGB Sentinel-2, обрезанный по отдельному полю и дате;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/sentinel_analysis.tif` — B02/B03/B04/B05/B08/B11/B12 и SCL на общей сетке 10 м;
- `outputs/imagery/<dataset>/<field_id>/<YYYY-MM-DD>/cloud_mask.tif` — бинарная маска невалидных пикселей по SCL;
- `outputs/imagery/download_manifest.json` — статус загрузки всех полей KAA/SP;
- `outputs/imagery/analysis_manifest.json` — статус докачки аналитических каналов KAA/SP;
- `outputs/maps/water_regime_gis.qgs`.

Для каждого рассчитанного индекса отчет содержит `valid_pixel_count`, `nodata_pixel_count`, `minimum`, `maximum`, `mean` и `standard_deviation`.

GeoJSON используется для небольших геометрий, GeoTIFF — для растров. Все локальные входы и результаты исключены из git, кроме `.gitkeep`.

## Будущие измерения

Для кригинга понадобится точечный слой с идентификатором, датой, координатами, числовым значением, единицами и методикой измерения.
