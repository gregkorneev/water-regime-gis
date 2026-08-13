# Pipelines

## 1. Выбор поля

Плагин передает координаты клика в `scripts/qgis/select_field_point.py`. Скрипт выбирает локальную UTM-зону, сохраняет точку и создает буфер 500 м.

## 2. Уточнение границы

`scripts/qgis/resolve_field_boundary.py` запрашивает НСПД через WMS `GetFeatureInfo`. Подходящий полигон заменяет буфер. При сетевой ошибке, отсутствии полигона или превышении `max_selected_parcel_area_ha` буфер остается рабочей областью.

## 3. Sentinel-2 и индексы

`scripts/qgis/process_satellite_indices.py`:

1. читает рабочую границу;
2. ищет Sentinel-2 L2A через Microsoft Planetary Computer STAC;
3. выбирает наименее облачную сцену за последние 60 дней при облачности до 30%;
4. обрезает Blue, Green, Red, Red Edge, NIR и SWIR1 через GDAL `/vsicurl/`;
5. рассчитывает NDVI, NDMI, NDWI, MNDWI, SAVI и NDRE;
6. сохраняет GeoTIFF в `outputs/rasters/`.

Скрипт поддерживает параметры `--area`, `--interim`, `--rasters`, `--metadata`, `--indices`, `--date-from`, `--date-to` и `--scene-id` для изолированной проверки.

## 4. Проверка Observearth

`scripts/qgis/compare_observearth_ndmi.py` рассчитывает NDMI установленным движком Observearth на тех же NIR/SWIR1 и сравнивает пиксели с проектным GeoTIFF при допуске `1e-6`.

## 5. Изолинии и кригинг

Плагин открывает Processing-диалоги Isoliner. Изолинии строятся по активному растру. Кригинг доступен только для реального точечного слоя минимум с тремя объектами и числовым полем.

## 6. Импорт границ

`scripts/qgis/split_field_boundaries.py` делит внешний GeoJSON по `dataset_code = SP/KAA` и создает минимальные ориентированные прямоугольники в локальной UTM CRS каждого поля.

## Не реализовано

- DEM и гидрологические производные;
- временные ряды;
- импорт наземных измерений;
- автоматическая классификация зон и итоговый отчет.
