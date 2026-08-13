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

## Проверка проекта

```bash
python3 scripts/check_project.py
python3 scripts/check_qgis_plugin.py
python3 scripts/check_satellite_pipeline.py
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/check_qgis_context.py
```

Подробности текущего процесса: `docs/wiki/QGIS_WORKFLOW.md`.
