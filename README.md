# Water Regime GIS

Личный QGIS-плагин для выбора сельскохозяйственного поля, загрузки Sentinel-2 и расчета индексов водного режима.

## Требования

- macOS;
- QGIS в `/Applications/QGIS.app`;
- репозиторий в `/Users/korneev/Desktop/water-regime-gis`;
- профиль QGIS `default`;
- интернет для НСПД, Planetary Computer STAC и спутниковых COG.

Observearth и Isoliner устанавливаются через стандартный менеджер модулей QGIS. Для кадастрового контура используется `rosreestr-search-qgis-plugin`.

## Установка

```bash
cd /Users/korneev/Desktop/water-regime-gis
python3 scripts/install_qgis_plugin.py
python3 scripts/install_nspd_plugin.py
```

Затем перезапустить QGIS, открыть `Модули -> Управление модулями` и включить:

- `Water Regime GIS`;
- `Observearth`;
- `Isoliner`;
- `rosreestr-search-qgis-plugin`.

## Как пользоваться

1. Открыть QGIS.
2. Нажать кнопку `Water Regime GIS` на панели инструментов.
3. Нажать `Проверить среду`.
4. Нажать `Взять точку с карты` и кликнуть внутри нужного поля.
5. Нажать `Уточнить границу`. Если НСПД не вернет подходящий участок, останется буфер 500 м.
6. Нажать `Рассчитать индексы` и дождаться завершения фоновой задачи.
7. Выбрать растр `NDMI` в списке слоев и нажать `Построить изолинии`.
8. Нажать `Собрать проект/слои`, чтобы добавить доступные результаты без дублей и сохранить проект.

`Открыть Observearth` нужен для интерактивной проверки спутниковых сцен. Перед открытием выделите одно поле в полигональном слое.

`Кригинг измерений` работает только с активным точечным слоем, содержащим минимум три объекта и числовое поле измерения. Без реальных наземных точек расчет намеренно не запускается.

## Результаты

- выбранная точка: `data/aoi/selected_field_point.geojson`;
- рабочая граница: `data/aoi/selected_field_area.geojson`;
- обрезанные каналы и metadata сцены: `data/interim/satellite/`;
- индексные GeoTIFF: `outputs/rasters/`;
- метрики индексов: `outputs/reports/latest_metrics.json`;
- QGIS-проект: `outputs/maps/water_regime_gis.qgs`;
- импортированные и разделенные границы: `data/processed/field_boundaries/`.

Локальные данные и результаты исключены из git.

## Импорт готовых границ

Для исходного файла с атрибутом `dataset_code`:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/split_field_boundaries.py \
  --input /Users/korneev/Desktop/kornix_field_boundaries_import_20260530_v2.geojson
```

Скрипт создает слои SP/KAA и минимальные прямоугольники в `data/processed/field_boundaries/`. Их можно добавить в QGIS обычной командой `Слой -> Добавить слой -> Добавить векторный слой`.

## Снимки Sentinel-2 и Sentinel-1 для KAA/SP

Загрузить временной ряд RGB-снимков для каждого из 156 полей с 1 апреля по 10 августа 2026 года:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py
```

По умолчанию используются `/Users/korneev/Desktop/KAA.gpkg` и `/Users/korneev/Desktop/SP.gpkg`. Для каждого календарного дня выбирается одна наименее облачная сцена. Результаты сохраняются в `outputs/imagery/kaa/<field_id>/<YYYY-MM-DD>/` и `outputs/imagery/sp/<field_id>/<YYYY-MM-DD>/`. Общий журнал находится в `outputs/imagery/download_manifest.json`.

Повторный запуск пропускает готовые поля. Полезные параметры:

```bash
# Проверить одно поле
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py --limit 1

# Только поля, готовые к расчету
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py --where "calculation_ready = 1"

# Пересчитать существующие снимки за другим периодом
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py \
  --date-from 2026-06-01 --date-to 2026-08-14 --overwrite
```

Докачать аналитические каналы и маску облаков для уже выбранных сцен KAA и SP:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_analysis.py
```

Скрипт использует `scene_id` из существующих `metadata.json`, поэтому повторно не ищет и не меняет сцены. Для каждой даты создаются `sentinel_analysis.tif` с каналами B02/B03/B04/B05/B08/B11/B12/SCL и `cloud_mask.tif`. Выполнение возобновляемое; журнал сохраняется в `outputs/imagery/analysis_manifest.json`.

Рассчитать Sentinel-2 FCover для уже сохранённых сцен:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/calculate_sentinel2_fcover.py --dataset sp
```

Скрипт докачивает недостающие B06/B07/B8A и геометрию наблюдения той же сцены, применяет SNAP-совместимую нейросетевую модель FCover и сохраняет `sentinel_fcover.tif` рядом с аналитическим растром.

Скачать Sentinel-1 RTC с поляризациями VV/VH в отдельный каталог:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py \
  --input /Users/korneev/Desktop/SP.gpkg \
  --output outputs/imagery/sentinel1 \
  --collection sentinel-1-rtc --asset vv vh \
  --output-name sentinel_rtc.tif --no-cloud-filter \
  --date-from 2026-04-01 --date-to 2026-08-27
```

Результат `sentinel_rtc.tif` — двухканальный Float32 GeoTIFF (VV, VH) с
разрешением 10 м. Для приоритизации полей КОРНИКС передайте в `--where` фильтр
по `field_external_key`; второй запуск с `NOT IN` завершит остальные поля SP.

Посчитать зональное среднее индексов по каждому растровому пятну KAA:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/calculate_kaa_zonal_means.py
```

Скрипт читает `outputs/imagery/kaa/<field_id>/<YYYY-MM-DD>/sentinel_analysis.tif`, исключает nodata и облачные пиксели по `cloud_mask.tif`, затем сохраняет таблицу `outputs/reports/kaa_zonal_means.csv` и манифест `outputs/reports/kaa_zonal_means.json`. Если рядом есть `sentinel_fcover.tif`, в таблицу также попадает `FCOVER`.

## Анализ спутниковых индексов и наземных измерений

Подготовить wide-таблицу спутниковых индексов, QA-отчет, сезонную сводку и заготовки для объединения с наземными измерениями:

```bash
python3 scripts/analysis/run_satellite_ground_pipeline.py
```

По умолчанию входом служит `outputs/reports/kaa_zonal_means.csv`. Результаты пишутся в `results/`:

- `results/data/prepared_satellite_data.csv` — `field_id × scene_date × NDMI/NDRE/SAVI/NDVI`;
- `results/tables/seasonal_summary.csv` — среднее, медиана, p25 и p75 по датам;
- `results/reports/satellite_quality_report.md` — проверка дублей, пропусков и диапазонов;
- `results/data/model_dataset.csv` — таблица для моделей после добавления ground-данных;
- `results/tables/model_comparison.csv` — M1–M4, сейчас помечены как skipped без наземных измерений.

Шаблон наземной таблицы: `data/ground_measurements.example.csv`. Рабочий файл должен называться `data/ground_measurements.csv`. Конфигурация путей и параметров находится в `configs/analysis.example.json`.

## Проверка проекта

```bash
python3 scripts/check_project.py
python3 scripts/check_qgis_plugin.py
python3 scripts/check_satellite_pipeline.py
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/check_qgis_context.py
```

Подробности текущего процесса: `docs/wiki/QGIS_WORKFLOW.md`.
