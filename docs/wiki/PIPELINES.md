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
6. сохраняет GeoTIFF в `outputs/rasters/`;
7. записывает статистику индексов в `outputs/reports/latest_metrics.json`.

Скрипт поддерживает параметры `--area`, `--interim`, `--rasters`, `--metadata`, `--report`, `--indices`, `--date-from`, `--date-to` и `--scene-id` для изолированной проверки.

## 4. Проверка Observearth

`scripts/qgis/compare_observearth_ndmi.py` рассчитывает NDMI установленным движком Observearth на тех же NIR/SWIR1 и сравнивает пиксели с проектным GeoTIFF при допуске `1e-6`.

## 4.1. RGB-снимки для всех полей KAA/SP

`scripts/qgis/download_field_imagery.py` обходит объекты `/Users/korneev/Desktop/KAA.gpkg` и `/Users/korneev/Desktop/SP.gpkg`. Для каждого поля он ищет все Sentinel-2 L2A сцены с 2026-04-01 по 2026-08-10, оставляет одну наименее облачную сцену на календарный день, загружает B04/B03/B02, обрезает их по геометрии и сохраняет RGB GeoTIFF с разрешением 10 м. Повторный запуск продолжает обработку, пропуская готовые даты.

## 4.2. Аналитические каналы KAA/SP

`scripts/qgis/download_field_analysis.py` читает `scene_id` из готовых `metadata.json` и докачивает B02/B03/B04/B05/B08/B11/B12/SCL без повторного выбора сцен. Каналы приводятся к общей сетке 10 м в CRS поля; SCL ресемплируется ближайшим соседом. Результат сохраняется как восьмиканальный `sentinel_analysis.tif`, а классы SCL 0/1/3/8/9/10/11 формируют `cloud_mask.tif`. В metadata дополнительно записывается облачность внутри поля.

## 4.3. Зональные средние KAA

`scripts/qgis/calculate_kaa_zonal_means.py` обходит готовые `outputs/imagery/kaa/<field_id>/<YYYY-MM-DD>/sentinel_analysis.tif`, рассчитывает NDVI/NDMI/NDWI/MNDWI/NDRE/SAVI и берет среднее по валидным пикселям каждого обрезанного пятна. По умолчанию облака, тени, снег, насыщение и nodata исключаются через `cloud_mask.tif`. Результат сохраняется в `outputs/reports/kaa_zonal_means.csv`, параметры запуска — в `outputs/reports/kaa_zonal_means.json`.

## 4.4. Табличный анализ индексов и ground-данных

`scripts/analysis/run_satellite_ground_pipeline.py` читает long-таблицу `outputs/reports/kaa_zonal_means.csv`, проверяет дубли `field_id + scene_date + index`, преобразует ее в wide-формат и пишет `results/data/prepared_satellite_data.csv`. Скрипт также формирует QA-отчет, сезонную сводку по датам, шаблон `ground_measurements`, nearest-date merge с сохранением `days_difference` и отчет M1–M4. Пока `data/ground_measurements.csv` отсутствует, модели честно помечаются как `skipped`.

OPTRAM не вычисляется из готовых индексов. Скрипт проверяет наличие `sentinel_analysis.tif` с B04/B08/B12 и пишет `results/reports/optram_availability.json`; для реального OPTRAM еще нужны параметры/методика wet/dry edge.

## 4.5. Интерактивные графики по полям

Кнопка плагина `График по полю` включает QGIS map tool для KAA/SP-полигонов. Инструмент подгружает доступные слои `data/processed/field_boundaries/kaa_fields.geojson`, `data/processed/field_boundaries/sp_fields.geojson`, `/Users/korneev/Desktop/KAA.gpkg` и `/Users/korneev/Desktop/SP.gpkg`, при наведении показывает вычисленный `field_id`, а по двойному щелчку строит временной график NDVI/NDMI/NDWI/MNDWI/NDRE/SAVI из `outputs/reports/field_zonal_means.csv`. Исходные наблюдения показываются отдельными точками; все индексы нормализуются в собственный диапазон и аппроксимируются одной seasonal-формой с возможной почти горизонтальной полкой, ростом до пика и снижением после пика.

## 5. Изолинии и кригинг

Плагин открывает Processing-диалоги Isoliner. Изолинии строятся по активному растру. Кригинг доступен только для реального точечного слоя минимум с тремя объектами и числовым полем.

## 6. Импорт границ

`scripts/qgis/split_field_boundaries.py` делит внешний GeoJSON по `dataset_code = SP/KAA` и создает минимальные ориентированные прямоугольники в локальной UTM CRS каждого поля.

## Не реализовано

- DEM и гидрологические производные;
- импорт наземных измерений;
- автоматическая классификация зон и итоговый отчет.
