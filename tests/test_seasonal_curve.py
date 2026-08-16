import datetime as dt
import unittest

import numpy as np

from qgis_plugins.water_regime_gis_plugin import settings
from qgis_plugins.water_regime_gis_plugin.seasonal_curve import fit_seasonal_curve


class SeasonalCurveTest(unittest.TestCase):
    def test_fit_has_one_peak_and_ignores_a_sharp_downward_dip(self):
        days = np.arange(0.0, 141.0, 10.0)
        values = np.array(
            [
                0.12,
                0.12,
                0.13,
                0.13,
                0.18,
                0.31,
                0.52,
                0.25,
                0.72,
                0.68,
                0.56,
                0.42,
                0.30,
                0.22,
                0.17,
            ]
        )
        start = dt.date(2026, 4, 1)
        observations = [
            (start + dt.timedelta(days=float(day)), value)
            for day, value in zip(days, values)
        ]

        fit = fit_seasonal_curve(observations, settings.SEASONAL_CHART_FIT)
        peak = int(np.argmax(fit.values))

        self.assertGreater(fit.quality, 0.7)
        self.assertGreater(fit.observed_fit[7], values[7] + 0.3)
        self.assertTrue(np.all(np.diff(fit.values[: peak + 1]) >= -1e-9))
        self.assertTrue(np.all(np.diff(fit.values[peak:]) <= 1e-9))


if __name__ == "__main__":
    unittest.main()
