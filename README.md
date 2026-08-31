# Water Regime GIS

Личный QGIS-плагин и набор воспроизводимых PyQGIS/GDAL-пайплайнов для работы с
границами сельскохозяйственных полей, Sentinel-2, Sentinel-1 RTC и рядами
КОРНИКС. Основной интерфейс — плагин **Water Regime GIS** в QGIS 3.

Проект не содержит web-сервиса, Docker-сборки, базы PostGIS или отдельного
desktop-приложения. Он рассчитан на локальный запуск в QGIS.

## Быстрый старт

Нужны QGIS 3 с Python/GDAL и Git. На macOS QGIS по умолчанию установлен в
`/Applications/QGIS.app`; на Windows используйте `python-qgis.bat` из каталога
вашей установки QGIS.

```bash
git clone https://github.com/gregkorneev/water-regime-gis.git
cd water-regime-gis
python3 scripts/install_qgis_plugin.py
python3 scripts/check_project.py
python3 scripts/check_qgis_plugin.py
/Applications/QGIS.app/Contents/MacOS/python -m unittest discover -s tests -v
```

На Windows вместо последней команды запустите:

```powershell
& $env:QGIS_PYTHON -m unittest discover -s tests -v
```

После этого перезапустите QGIS и включите `Water Regime GIS` в менеджере
модулей. `Observearth`, `Isoliner` и `rosreestr-search-qgis-plugin` нужны
только для соответствующих кнопок плагина. Установка модуля НСПД:

```bash
python3 scripts/install_nspd_plugin.py
```

На Windows перед запуском укажите путь к QGIS:

```powershell
setx QGIS_PREFIX_PATH "C:\Program Files\QGIS 3.xx\apps\qgis"
setx QGIS_PYTHON "C:\Program Files\QGIS 3.xx\bin\python-qgis.bat"
```

Откройте новое окно PowerShell после `setx`. Скрипт установки на Windows копирует
плагин в профиль QGIS, на macOS создаёт симлинк.

## Работа в QGIS

1. Откройте панель `Water Regime GIS` и нажмите `Проверить среду`.
2. Загрузите локальный полигональный слой через `Загрузить контуры полей` или
   выберите точку на карте и при необходимости уточните кадастровую границу НСПД.
3. Для одного поля используйте `Рассчитать индексы`; для загруженного набора
   полей и новых рядов — `Загрузить ряды из сервиса`, затем
   `Обновить Sentinel-1/2`.
4. `График по полю` открывает ряды Sentinel-2, КОРНИКС и относительный
   индикатор Sentinel-1 VV; `Средний график` строит сводку по полям.
5. `Диаграммы эксперимента` пересчитывает PNG и единый JSON-протокол
   подтверждающего эксперимента. `Собрать проект/слои` сохраняет QGIS-проект.

Sentinel-1 на графиках — относительный proxy, а не процент влажности почвы.
`SP 7.3` исключено из интерактивных и аналитических выборок; его исходные
данные сохранены.

## Командные пайплайны

Все команды с GDAL/PyQGIS запускайте Python из установки QGIS.

```bash
# Разделить импортированные границы на слои SP/KAA
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/split_field_boundaries.py \
  --input /path/to/field_boundaries.geojson

# Скачать Sentinel-2 для SP/KAA, затем аналитические каналы и FCover
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_imagery.py
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/download_field_analysis.py
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/calculate_sentinel2_fcover.py --dataset sp

# Получить зональные ряды Sentinel-2 и Sentinel-1
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/calculate_kaa_zonal_means.py --dataset sp \
  --report outputs/reports/sp_zonal_means.csv
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/calculate_sentinel1_zonal_means.py

# Сопоставить КОРНИКС и Sentinel-2, затем обновить эксперимент
python3 scripts/analysis/merge_kornix_sentinel.py
python3 scripts/analysis/refresh_surface_validation_charts.py
```

`download_field_imagery.py` поддерживает Sentinel-1 RTC: передайте
`--collection sentinel-1-rtc --asset vv vh --output-name sentinel_rtc.tif
--no-cloud-filter`. Повторные запуски загрузчиков возобновляемы; `--overwrite`
пересчитывает уже существующие сцены.

## Структура проекта

| Путь | Назначение |
| --- | --- |
| `qgis_plugins/` | исходники QGIS-плагина |
| `src/water_regime_gis/` | общие функции конфигурации, CRS и QGIS runtime |
| `scripts/qgis/` | PyQGIS/GDAL-обработка и загрузки |
| `scripts/analysis/` | воспроизводимый табличный анализ |
| `data/aoi/`, `data/interim/`, `data/processed/` | AOI, промежуточные и подготовленные данные |
| `outputs/` | растры, проекты QGIS, снимки и оперативные отчёты |
| `results/` | таблицы, JSON-отчёты и иллюстрации экспериментов |
| `docs/wiki/` | актуальная архитектура, данные, пайплайны и решения |

Исходные геоданные, результаты и QGIS-проекты сохранены в репозитории. Не
добавляйте новые большие растры и сцены без отдельного решения. Локальные
кэши Python, `.DS_Store` и содержимое `tmp/` намеренно игнорируются.

## Проверка

```bash
python3 scripts/check_project.py
python3 scripts/check_qgis_plugin.py
python3 scripts/check_satellite_pipeline.py
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/check_qgis_context.py
/Applications/QGIS.app/Contents/MacOS/python -m unittest discover -s tests -v
```

Подробности: [wiki](docs/wiki/INDEX.md), включая [рабочий сценарий QGIS](docs/wiki/QGIS_WORKFLOW.md), [модель данных](docs/wiki/DATA_MODEL.md) и [описание пайплайнов](docs/wiki/PIPELINES.md).
