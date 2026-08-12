# Third-party Notices

Проект `water-regime-gis` распространяется под лицензией MIT.

## Runtime текущего интерфейса

- Python standard library — Python Software Foundation License.
- Apple WebKit / WKWebView — системный web runtime macOS, используется в release `.app`.
- Microsoft Edge WebView2 — системный web runtime Windows, используется в Windows desktop shell.
- Leaflet — BSD 2-Clause License, используется в локальном веб-интерфейсе для выбора точки на карте через CDN.
- MapLibre GL JS и MapLibre GL Leaflet — BSD 3-Clause License, используются для слоя подписей гибридной карты через CDN.
- OpenFreeMap / OpenMapTiles — используются как источник векторных подписей гибридной карты; атрибуция отображается непосредственно на карте.
- OpenStreetMap — используется как картографическая подложка в веб-интерфейсе и QGIS-проекте; данные OSM распространяются на условиях Open Database License (ODbL).

Текущая версия интерфейса не добавляет внешних Python-зависимостей.

## Экспериментальный Tkinter-модуль

В репозитории остается черновой модуль `src/water_regime_gis/app.py` на Tkinter / Tcl-Tk. Он не является основным интерфейсом запуска.

## Геоданные

Тестовый AOI `data/aoi/tula_test_field.geojson` получен из OpenStreetMap через Overpass API. Данные OpenStreetMap распространяются на условиях Open Database License (ODbL). Перед коммерческим или публичным распространением производных наборов данных нужно отдельно проверить требования атрибуции OSM.
