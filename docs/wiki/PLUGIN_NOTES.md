# Plugin Notes

## Rosreestr NSPD Search

Выбран как первый источник кадастровых границ.

- QGIS plugin: `rosreestr-search-qgis-plugin`;
- страница: `https://plugins.qgis.org/plugins/rosreestr-search-qgis-plugin-master/`;
- репозиторий: `https://github.com/matmatamat/rosreestr-search-qgis-plugin`;
- назначение: поиск по Публичной кадастровой карте НСПД и загрузка слоев НСПД;
- актуальная проверенная по каталогу QGIS версия на 2026-08-09: 2.5;
- минимальная версия QGIS для 2.5: 3.40.

В проект добавлен скрипт проверки:

```bash
/Applications/QGIS.app/Contents/MacOS/python scripts/qgis/check_nspd_plugin.py
```

На macOS 2026-08-09 плагин установлен в профиль QGIS `default`:

```text
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/rosreestr-search-qgis-plugin-master
```

Для headless PyQGIS важно не перетирать prefix на `/Applications/QGIS.app/Contents/MacOS`. Правильный prefix для загрузки WMS-провайдера: `/Applications/QGIS.app`.

Важно: слой `Земельные участки из ЕГРН` из НСПД подключается как WMS. Он полезен для визуального контроля границ, но для расчетов нужен векторный полигон конкретного участка.

## Observearth

Observearth рассматривается как возможный QGIS-плагин для работы со спутниковыми данными. Перед включением в обязательный стек нужно проверить:

- поддержку нужных источников данных;
- удобство работы на macOS;
- совместимость с актуальной версией QGIS;
- возможность воспроизводимого запуска или документирования действий.

## Isoliner

Isoliner рассматривается как возможный QGIS-плагин для построения изолиний и анализа поверхностей.

Перед использованием нужно проверить:

- качество результата на DEM и расчетных растрах;
- альтернативы через стандартный QGIS Processing и GDAL;
- воспроизводимость операций.

## Правило по плагинам

Плагины можно использовать как вспомогательный инструмент, но базовые пайплайны должны опираться на QGIS Processing, PyQGIS и GDAL, чтобы проект оставался воспроизводимым.
