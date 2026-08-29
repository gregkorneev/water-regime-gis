import unittest

import numpy as np

from qgis_plugins.water_regime_gis_plugin.radar_series import (
    mean_backscatter_db,
    relative_moisture_proxy,
    rolling_median,
)


class RadarSeriesTest(unittest.TestCase):
    def test_mean_db_ignores_nodata_and_rolling_median_suppresses_spike(self):
        mean_db, valid, nodata = mean_backscatter_db(np.array([0.0, 0.01, 0.1, np.nan]), 0.0)

        self.assertAlmostEqual(mean_db, 10.0 * np.log10(0.055))
        self.assertEqual((valid, nodata), (2, 2))
        self.assertEqual(rolling_median([1.0, 1.0, 9.0, 1.0, 1.0]), [1.0] * 5)

    def test_relative_moisture_proxy_normalizes_vv_signal(self):
        self.assertEqual(relative_moisture_proxy([-12.0, -8.0, -4.0]), [0.15, 0.2615, 0.373])
        self.assertEqual(relative_moisture_proxy([-8.0, -8.0]), [0.2615, 0.2615])
        self.assertEqual(relative_moisture_proxy([-12.0, -8.0, -4.0], target_mean=0.25), [0.15, 0.25, 0.35])
        self.assertEqual(relative_moisture_proxy([-8.0, -8.0], target_mean=0.25), [0.25, 0.25])
        self.assertEqual(
            [round(value, 12) for value in relative_moisture_proxy([-12.0, -8.0, -4.0], target_mean=0.25, target_stddev=0.05)],
            [0.2, 0.25, 0.3],
        )


if __name__ == "__main__":
    unittest.main()
