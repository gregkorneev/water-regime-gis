from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit


@dataclass(frozen=True)
class SeasonalCurveFit:
    dates: list[dt.datetime]
    values: np.ndarray
    observed_fit: np.ndarray
    quality: float
    parameters: dict[str, float]


def seasonal_curve(parameters, days):
    """Eight-parameter unimodal double logistic with an optional initial shelf."""
    (
        base,
        amplitude,
        plateau_days,
        plateau_slope,
        growth_midpoint,
        width,
        growth_rate,
        senescence_rate,
    ) = parameters
    days = np.asarray(days, dtype=float)
    seasonal_days = np.maximum(days - plateau_days, 0.0)
    growth = expit(growth_rate * (seasonal_days - growth_midpoint))
    senescence = expit(-senescence_rate * (seasonal_days - growth_midpoint - width))
    initial_seasonal_level = expit(-growth_rate * growth_midpoint) * expit(
        senescence_rate * (growth_midpoint + width)
    )
    return (
        base
        + plateau_slope * np.minimum(days, plateau_days)
        + amplitude * (growth * senescence - initial_seasonal_level)
    )


def fit_seasonal_curve(values, config: dict) -> SeasonalCurveFit:
    dates = [date for date, _ in values]
    original_y = np.asarray([value for _, value in values], dtype=float)
    y_low = float(np.nanpercentile(original_y, 5))
    y_high = float(np.nanpercentile(original_y, 95))
    scale = max(y_high - y_low, config["amplitude_floor"])
    y = (original_y - y_low) / scale

    days = np.asarray([(date - dates[0]).days for date in dates], dtype=float)
    span = max(float(days[-1]), 1.0)
    weights = downward_dip_weights(days, y, config)
    lower, upper = parameter_bounds(span, config)
    starts = initial_parameters(days, y, lower, upper, config)

    def residuals(parameters):
        data_residuals = np.sqrt(weights) * (seasonal_curve(parameters, days) - y)
        plateau_penalty = np.sqrt(config["plateau_penalty"]) * parameters[2] / span
        return np.append(data_residuals, plateau_penalty)

    candidates = []
    for start in starts:
        try:
            result = least_squares(
                residuals,
                start,
                bounds=(lower, upper),
                loss=config["loss"],
                f_scale=config["robust_f_scale"],
                max_nfev=config["max_nfev"],
            )
        except ValueError:
            continue
        if np.all(np.isfinite(result.x)):
            candidates.append(result.x)

    # Even if optimization cannot improve a start, the displayed line remains
    # the same common model rather than switching to another interpolator.
    candidates.extend(starts)
    parameters = min(
        candidates,
        key=lambda item: fit_objective(item, days, y, weights, span, config),
    )
    observed_fit = seasonal_curve(parameters, days)
    quality = robust_quality(y, observed_fit, weights, config)

    dense_days = np.linspace(0.0, span, max(120, len(values) * 16))
    dense_values = seasonal_curve(parameters, dense_days) * scale + y_low
    start_datetime = dt.datetime.combine(dates[0], dt.time())
    dense_dates = [start_datetime + dt.timedelta(days=float(day)) for day in dense_days]

    names = (
        "baseline",
        "amplitude",
        "plateau_days",
        "plateau_slope",
        "growth_midpoint",
        "season_width",
        "growth_rate",
        "senescence_rate",
    )
    restored = np.asarray(parameters, dtype=float).copy()
    restored[0] = restored[0] * scale + y_low
    restored[1] *= scale
    restored[3] *= scale
    return SeasonalCurveFit(
        dates=dense_dates,
        values=dense_values,
        observed_fit=observed_fit * scale + y_low,
        quality=quality,
        parameters=dict(zip(names, map(float, restored))),
    )


def parameter_bounds(span: float, config: dict):
    minimum_width = max(
        config["minimum_width_days"],
        config["minimum_width_fraction"] * span,
    )
    lower = np.asarray(
        [
            config["baseline_bounds"][0],
            config["amplitude_bounds"][0],
            0.0,
            config["plateau_slope_bounds"][0],
            0.0,
            minimum_width,
            config["rate_bounds"][0],
            config["rate_bounds"][0],
        ]
    )
    upper = np.asarray(
        [
            config["baseline_bounds"][1],
            config["amplitude_bounds"][1],
            config["maximum_plateau_fraction"] * span,
            config["plateau_slope_bounds"][1],
            config["maximum_growth_midpoint_fraction"] * span,
            span + config["width_extra_days"],
            config["rate_bounds"][1],
            config["rate_bounds"][1],
        ]
    )
    return lower, upper


def initial_parameters(days, y, lower, upper, config: dict):
    baseline = float(np.nanpercentile(y, 10))
    peak_day = float(days[int(np.nanargmax(y))])
    base = np.asarray(
        [
            baseline,
            1.1,
            0.0,
            0.0,
            max(1.0, peak_day * 0.45),
            max(10.0, float(days[-1]) * 0.55),
            0.07,
            0.07,
        ]
    )
    starts = []
    for plateau_fraction, rate in config["multi_starts"]:
        guess = base.copy()
        guess[2] = float(days[-1]) * plateau_fraction
        guess[4] = max(0.0, (peak_day - guess[2]) * 0.45)
        guess[6] = rate
        guess[7] = rate
        starts.append(np.clip(guess, lower + 1e-8, upper - 1e-8))
    return starts


def downward_dip_weights(days, values, config: dict):
    weights = np.ones(len(values), dtype=float)
    threshold = config["downward_dip_threshold"]
    for index in range(1, len(values) - 1):
        interval = max(days[index + 1] - days[index - 1], 1.0)
        fraction = (days[index] - days[index - 1]) / interval
        local_trend = values[index - 1] + fraction * (values[index + 1] - values[index - 1])
        drop = max(0.0, local_trend - values[index])
        if drop > threshold:
            weights[index] = max(config["minimum_dip_weight"], (threshold / drop) ** 2)
    return weights


def fit_objective(parameters, days, values, weights, span: float, config: dict) -> float:
    residuals = np.sqrt(weights) * (seasonal_curve(parameters, days) - values)
    scale = config["robust_f_scale"]
    soft_l1 = 2.0 * scale**2 * (np.sqrt(1.0 + (residuals / scale) ** 2) - 1.0)
    plateau_penalty = config["plateau_penalty"] * (parameters[2] / span) ** 2
    return float(np.sum(soft_l1) + plateau_penalty)


def robust_quality(values, fitted, weights, config: dict) -> float:
    cap = config["metric_residual_cap"]
    model_error = np.average(np.minimum(np.abs(values - fitted), cap), weights=weights)
    baseline = float(np.nanmedian(values))
    baseline_error = np.average(np.minimum(np.abs(values - baseline), cap), weights=weights)
    if baseline_error <= 1e-12:
        return 1.0 if model_error <= 1e-12 else 0.0
    return float(np.clip(1.0 - model_error / baseline_error, 0.0, 1.0))
