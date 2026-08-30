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

    def test_average_chart_hides_cover_and_shifts_expected_fcover(self):
        self.assertNotIn("canopy_cover_fraction_derived", settings.AVERAGE_CHART_KORNIX_SERIES.values())
        self.assertNotIn("soil_surface_0_10_theta", settings.AVERAGE_CHART_KORNIX_SERIES.values())
        self.assertEqual(settings.AVERAGE_CHART_RADAR_KORNIX_SERIES, {"Влага КОРНИКС 0–10 см": "soil_surface_0_10_theta"})
        self.assertIn("soil_surface_0_10_theta", settings.AVERAGE_CHART_RADAR_KORNIX_SERIES.values())
        self.assertEqual(settings.AVERAGE_CHART_DATE_OFFSETS["satellite_fcover_expected"], 12)


if __name__ == "__main__":
    unittest.main()
