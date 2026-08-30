import unittest

from qgis_plugins.water_regime_gis_plugin.aggregate_series import average_by_date
from qgis_plugins.water_regime_gis_plugin import settings


class AggregateSeriesTest(unittest.TestCase):
    def test_averages_fields_after_collapsing_duplicate_scenes(self):
        rows = [
            {"field_id": "SP_1_1", "scene_date": "2026-06-01", "index": "NDVI", "value": "0.2"},
            {"field_id": "SP_1_1", "scene_date": "2026-06-01", "index": "NDVI", "value": "0.4"},
            {"field_id": "SP_1_2", "scene_date": "2026-06-01", "index": "NDVI", "value": "0.8"},
        ]

        result = average_by_date(rows, "scene_date", ("value",), ("index",))

        self.assertEqual(result, [{"index": "NDVI", "scene_date": "2026-06-01", "value": 0.55}])

    def test_skips_missing_values_without_dropping_other_fields(self):
        rows = [
            {"field_id": "SP_1_1", "day": "2026-06-01", "value": ""},
            {"field_id": "SP_1_2", "day": "2026-06-01", "value": "0.4"},
        ]

        result = average_by_date(rows, "day", ("value",))

        self.assertEqual(result, [{"day": "2026-06-01", "value": 0.4}])

    def test_average_chart_excludes_unstable_lag_fields(self):
        self.assertEqual(
            settings.AVERAGE_CHART_EXCLUDED_FIELDS,
            {"SP_2_7", "SP_4_3", "SP_6_6", "SP_6_7", "SP_7_3"},
        )


if __name__ == "__main__":
    unittest.main()
