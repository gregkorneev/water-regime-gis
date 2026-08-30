#!/usr/bin/env python3
"""Download an exported external-model time-series package for the next refresh."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "data/interim/external_timeseries"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download external time series as CSV or ZIP.")
    parser.add_argument("--url", required=True, help="Direct HTTPS URL of the CSV or ZIP export.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    target = DESTINATION / stamp
    target.mkdir(parents=True)
    suffix = ".zip" if args.url.lower().split("?", 1)[0].endswith(".zip") else ".csv"
    payload = target / f"service_export{suffix}"
    request = Request(args.url, headers={"User-Agent": "water-regime-gis"})
    with urlopen(request, timeout=120) as response, payload.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if zipfile.is_zipfile(payload):
        with zipfile.ZipFile(payload) as archive:
            safe_extract(archive, target)
    csvs = sorted(target.rglob("*.csv"))
    if not csvs:
        raise ValueError("Выгрузка не содержит CSV-файлов временных рядов.")
    dates = dates_from_csv(csvs)
    if not dates:
        raise ValueError("В выгрузке нет столбца date или day с датами ISO-8601.")
    state = {
        "source_url": args.url,
        "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "directory": str(target),
        "date_from": min(dates).isoformat(),
        "date_to": max(dates).isoformat(),
        "csv_files": [str(path) for path in csvs],
    }
    (DESTINATION / "latest.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Loaded {len(csvs)} CSV files for {state['date_from']}—{state['date_to']}")
    return 0


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        path = (root / member.filename).resolve()
        if root not in path.parents and path != root:
            raise ValueError("ZIP contains a path outside the destination.")
    archive.extractall(root)


def dates_from_csv(paths: list[Path]) -> list[dt.date]:
    import csv

    dates = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                value = row.get("day") or row.get("date")
                if value:
                    try:
                        dates.append(dt.date.fromisoformat(value[:10]))
                    except ValueError:
                        pass
    return dates


if __name__ == "__main__":
    raise SystemExit(main())
