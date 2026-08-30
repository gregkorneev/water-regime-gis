#!/usr/bin/env python3
"""Refresh Sentinel-1/2 and index products for the user-selected field layer."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data/interim/external_timeseries/latest.json"
IMAGERY = ROOT / "outputs/imagery"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Sentinel data for uploaded field contours.")
    parser.add_argument("--fields", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fields = args.fields.expanduser().resolve()
    if not fields.exists():
        raise FileNotFoundError(fields)
    if not STATE.exists():
        raise FileNotFoundError("Сначала загрузите временные ряды из внешнего сервиса.")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    dataset = safe_name(fields.stem).lower()
    date_from, date_to = state["date_from"], state["date_to"]
    commands = [
        ["download_field_imagery.py", "--input", fields, "--date-from", date_from, "--date-to", date_to],
        ["download_field_analysis.py", "--dataset", dataset, "--date-from", date_from, "--date-to", date_to],
        ["calculate_sentinel2_fcover.py", "--dataset", dataset],
        ["calculate_kaa_zonal_means.py", "--dataset", dataset, "--report", ROOT / "outputs/reports/user_fields_zonal_means.csv"],
        ["../analysis/build_external_index_models.py", "--series-state", STATE, "--indices", ROOT / "outputs/reports/user_fields_zonal_means.csv"],
        ["download_field_imagery.py", "--input", fields, "--output", IMAGERY / "sentinel1", "--collection", "sentinel-1-rtc", "--asset", "vv", "vh", "--output-name", "sentinel_rtc.tif", "--no-cloud-filter", "--date-from", date_from, "--date-to", date_to],
        ["calculate_sentinel1_zonal_means.py", "--dataset", dataset, "--report", ROOT / "outputs/reports/user_fields_sentinel1_zonal_means.csv"],
    ]
    for index, command in enumerate(commands, start=1):
        run(command)
        print(f"PROGRESS {index * 100 / len(commands):.0f}", flush=True)
    print("Refresh complete: Sentinel-1/2, cloud filtering, indices and zonal series updated.")
    return 0


def run(parts: list[Path | str]) -> None:
    script = ROOT / "scripts/qgis" / str(parts[0])
    command = [sys.executable, "-u", script, *map(str, parts[1:])]
    print("RUN " + " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_") or "fields"


if __name__ == "__main__":
    raise SystemExit(main())
