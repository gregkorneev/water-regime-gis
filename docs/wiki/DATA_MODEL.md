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
- `outputs/maps/water_regime_gis.qgs`.

GeoJSON используется для небольших геометрий, GeoTIFF — для растров. Все локальные входы и результаты исключены из git, кроме `.gitkeep`.

## Будущие измерения

Для кригинга понадобится точечный слой с идентификатором, датой, координатами, числовым значением, единицами и методикой измерения.
