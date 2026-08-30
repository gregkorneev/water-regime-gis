from __future__ import annotations

import datetime as dt
import math
import statistics

import numpy as np
from scipy.interpolate import UnivariateSpline


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


def relative_moisture_proxy(vv_db_values, minimum: float = 0.153527, maximum: float = 0.367581):
    """Normalize a field's VV signal into the shared Sentinel-1 moisture scale."""
    values = [float(value) for value in vv_db_values]
    if len(values) < 2:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [(minimum + maximum) / 2] * len(values)
    normalized = [(value - low) / (high - low) for value in values]
    return [minimum + (maximum - minimum) * value for value in normalized]


def robust_spline(values, trim_fraction: float = 0.05):
    """Smooth dated values after removing the largest local positive and negative residuals."""
    if len(values) < 4:
        return values
    dates, numbers = zip(*values)
    baseline = rolling_median(list(numbers))
    residuals = [value - trend for value, trend in zip(numbers, baseline)]
    trim_count = max(1, round(len(values) * trim_fraction))
    lowest = set(sorted(range(len(values)), key=lambda index: residuals[index])[:trim_count])
    highest = set(sorted(range(len(values)), key=lambda index: residuals[index], reverse=True)[:trim_count])
    keep = [index for index in range(len(values)) if index not in lowest | highest]
    if len(keep) < 4:
        return values
    x = np.asarray([(date - dates[0]).days for date in dates], dtype=float)
    x_keep = x[keep]
    y_keep = np.asarray([numbers[index] for index in keep], dtype=float)
    spline = UnivariateSpline(
        x_keep,
        y_keep,
        k=min(3, len(keep) - 1),
        s=len(keep) * float(np.var(y_keep)) * 0.28,
    )
    dense_x = np.linspace(x[0], x[-1], max(120, len(values) * 4))
    return [(dates[0] + dt.timedelta(days=float(day)), float(value)) for day, value in zip(dense_x, spline(dense_x))]
