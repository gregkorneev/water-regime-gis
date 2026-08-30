import unittest

from scripts.analysis.build_external_index_models import fit_models


class ExternalIndexModelsTest(unittest.TestCase):
    def test_fits_exact_field_date_pairs(self):
        series = [
            {"field_id": "A", "date": "2026-04-01", "soil": "1"},
            {"field_id": "A", "date": "2026-04-02", "soil": "2"},
            {"field_id": "A", "date": "2026-04-03", "soil": "3"},
        ]
        indices = {
            ("A", "2026-04-01"): {"NDVI": 0.1},
            ("A", "2026-04-02"): {"NDVI": 0.2},
            ("A", "2026-04-03"): {"NDVI": 0.3},
        }
        model = fit_models(series, indices)[0]
        self.assertEqual((model["variable"], model["index"], model["pairs"]), ("soil", "NDVI", 3))
        self.assertAlmostEqual(model["r_squared"], 1.0)


if __name__ == "__main__":
    unittest.main()
