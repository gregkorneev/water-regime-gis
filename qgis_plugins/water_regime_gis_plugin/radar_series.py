from __future__ import annotations

import math
import statistics

import numpy as np


def mean_backscatter_db(array, nodata=None):
    values = np.asarray(array, dtype=float)
    valid_mask = np.isfinite(values) & (values > 0)
    if nodata is not None and math.isfinite(nodata):
        valid_mask &= values != nodata
    valid = values[valid_mask]
    mean_db = 10.0 * math.log10(float(valid.mean())) if valid.size else None
    return mean_db, int(valid.size), int(values.size - valid.size)


def rolling_median(values, window: int = 5):
    radius = max(0, window // 2)
    return [
        statistics.median(values[max(0, index - radius) : index + radius + 1])
        for index in range(len(values))
    ]
