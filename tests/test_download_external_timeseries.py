import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/qgis/download_external_timeseries.py"
SPEC = importlib.util.spec_from_file_location("download_external_timeseries", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExternalTimeseriesTest(unittest.TestCase):
    def test_reads_day_and_date_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.csv").write_text("day,value\n2026-04-01,1\n", encoding="utf-8")
            (root / "forcing.csv").write_text("date,value\n2026-04-03,2\n", encoding="utf-8")
            self.assertEqual(
                MODULE.dates_from_csv(sorted(root.glob("*.csv"))),
                [dt.date(2026, 4, 3), dt.date(2026, 4, 1)],
            )


if __name__ == "__main__":
    unittest.main()
