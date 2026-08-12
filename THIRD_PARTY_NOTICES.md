# Third-party Notices

Проект `water-regime-gis` распространяется под лицензией MIT.

## Runtime текущего интерфейса

- Python standard library — Python Software Foundation License.
- Browser runtime — браузер пользователя.
- Leaflet — BSD 2-Clause License, используется в локальном веб-интерфейсе для выбора точки на карте через CDN.
- MapLibre GL JS и MapLibre GL Leaflet — BSD 3-Clause License, используются для отображения русскоязычной векторной карты.
- OpenFreeMap / OpenMapTiles — векторная картографическая подложка без API-ключа; требуется атрибуция OpenFreeMap, OpenMapTiles и OpenStreetMap.
- OpenStreetMap — используется как картографическая подложка в веб-интерфейсе и QGIS-проекте; данные OSM распространяются на условиях Open Database License (ODbL).

Текущая версия интерфейса не добавляет внешних Python-зависимостей.

## Экспериментальный Tkinter-модуль

В репозитории остается черновой модуль `src/water_regime_gis/app.py` на Tkinter / Tcl-Tk. Он не является основным интерфейсом запуска.

## Геоданные

Тестовый AOI `data/aoi/tula_test_field.geojson` получен из OpenStreetMap через Overpass API. Данные OpenStreetMap распространяются на условиях Open Database License (ODbL). Перед коммерческим или публичным распространением производных наборов данных нужно отдельно проверить требования атрибуции OSM.
