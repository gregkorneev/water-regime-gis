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


def relative_moisture_proxy(vv_db_values, target_mean=None, minimum: float = 0.15, maximum: float = 0.373):
    """Normalize VV into a field-relative moisture proxy, optionally matching a target mean."""
    values = [float(value) for value in vv_db_values]
    if len(values) < 2:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [float(target_mean) if target_mean is not None else (minimum + maximum) / 2] * len(values)
    normalized = [(value - low) / (high - low) for value in values]
    if target_mean is not None:
        maximum = minimum + (float(target_mean) - minimum) / statistics.mean(normalized)
    return [minimum + (maximum - minimum) * value for value in normalized]
