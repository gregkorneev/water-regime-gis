# Agent Context

Краткая актуальная память проекта для Codex и будущих AI-агентов.

## Состояние

Проект находится на первом этапе. Создан каркас репозитория, базовая wiki, `.gitignore`, правила для агентов, `pyproject.toml`, пример конфига и скрипт проверки структуры.

## Цель

Разработать QGIS-ориентированную систему анализа водного режима сельскохозяйственных земель на основе спутниковых данных, DEM и расчетных слоев. Наземные точки будут добавлены позже.

## Текущие решения

- Документация ведется на русском языке.
- Имена файлов и папок — на английском.
- Основной стек: macOS, QGIS, PyQGIS, QGIS Processing, GDAL/OGR, Python.
- PostGIS планируется, но не требуется на первом этапе.
- Большие геоданные не добавляются в git без явного разрешения.
- `docs/wiki/DECISIONS.md` является журналом решений.
- Все завершенные изменения должны автоматически коммититься и пушиться на GitHub, если пользователь явно не попросил обратное.
- Первый исполняемый скрипт: `python3 scripts/check_project.py`.
- Базовый конфиг: `configs/project.example.json`.
- Тестовый AOI: `data/aoi/tula_test_field.geojson`, сельхозполе в Тульской области из OpenStreetMap (`way/78250539`).
- Рабочая CRS для тестового AOI: `EPSG:32637`.
- Проект теперь развивается как desktop-приложение для Windows и macOS.
- Первая версия GUI: `python3 scripts/run_app.py`, локальный веб-интерфейс `http://127.0.0.1:8765` на стандартной библиотеке Python.
- Код проекта распространяется под MIT; сведения о сторонних лицензиях в `THIRD_PARTY_NOTICES.md`.
- Проверка AOI: `python3 scripts/check_aoi.py --write-normalized`; в GUI кнопка `Проверить AOI`.
- Нормализованная рабочая копия AOI пишется в `data/interim/tula_test_field.normalized.geojson` и не коммитится.
- QGIS найден на macOS в `/Applications/QGIS.app`; для PyQGIS использовать wrapper `/Applications/QGIS.app/Contents/MacOS/python`.
- Демонстрационный QGIS-проект создается командой `/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/create_demo_project.py`.
- Выходной проект: `outputs/maps/water_regime_gis.qgs`.

## Следующий практический шаг

Подключить первый DEM-слой или создать демонстрационный аналитический слой поверх AOI.
