import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/qgis/download_field_imagery.py"
SPEC = importlib.util.spec_from_file_location("download_field_imagery", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SceneQualityTest(unittest.TestCase):
    def test_degraded_processing_loses_to_clean_reprocessing(self):
        clean = {
            "properties": {
                "eo:cloud_cover": 0.031,
                "s2:degraded_msi_data_percentage": 0.0,
                "s2:nodata_pixel_percentage": 65.59,
            }
        }
        degraded = {
            "properties": {
                "eo:cloud_cover": 0.029,
                "s2:degraded_msi_data_percentage": 0.8692,
                "s2:nodata_pixel_percentage": 65.59,
            }
        }

        self.assertLess(MODULE.scene_quality(clean), MODULE.scene_quality(degraded))


if __name__ == "__main__":
    unittest.main()
