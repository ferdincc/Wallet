"""
ARIMA price prediction model for backtesting.

INPUT  (stdin): JSON array of objects:
    [{ "timestamp": "...", "close": 123.45 }, ...]
OUTPUT (stdout): JSON object:
    { "predicted_price": float, "confidence": float, "model_name": "arima" }

Non-zero fallback: convergence failure, short windows, or invalid forecasts
use EWMA / drift-naive / last close — never null predicted_price when input has data.
"""

from __future__ import annotations

import json
import sys
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller

# Minimum points to attempt full AIC grid (must exceed max(p)+max(q)+d + margin)
MIN_LEN_FULL_GRID = 22
MIN_LEN_SMALL_ARIMA = 12
MIN_LEN_ANY = 5

# Search space (crypto: short memory, allow d=0..2)
MAX_P = 3
MAX_Q = 3
MAX_D = 2


def parse_input(raw: str) -> List[Dict[str, Any]]:
    if not raw.strip():
        raise ValueError("No input data provided to ARIMA model")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array")
    return data


def prepare_series(data: List[Dict[str, Any]]) -> pd.Series:
    if not data:
        raise ValueError("Input array is empty")

    df = pd.DataFrame(data)
    if "timestamp" not in df.columns or "close" not in df.columns:
        raise ValueError("Each item must contain 'timestamp' and 'close' fields")

    try:
        index = pd.to_datetime(df["timestamp"], errors="raise")
    except Exception:
        index = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")

    if index.isna().any():
        raise ValueError("Invalid timestamps in input data")

    series = pd.Series(df["close"].astype(float).values, index=index).sort_index()
    series = series.replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < MIN_LEN_ANY:
        raise ValueError(f"At least {MIN_LEN_ANY} data points are required")
    return series


def _positive_price(x: float, floor: float = 1e-12) -> float:
    if not np.isfinite(x):
        return floor
    return float(max(x, floor))


def adf_stationary(series: pd.Series, alpha: float = 0.05) -> bool:
    """Augmented Dickey–Fuller: True if series appears stationary at level."""
    try:
        x = series.dropna().astype(float)
        if len(x) < 8:
            return False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, pvalue, *_ = adfuller(x, autolag="AIC")
        _ = stat  # unused
        return bool(pvalue < alpha)
    except Exception:
        return False


def min_obs_for_order(p: int, d: int, q: int) -> int:
    """Conservative minimum length so ARIMA can estimate (crypto + margin)."""
    return p + q + d + 8


def ewma_forecast_next(series: pd.Series, alpha: float = 0.35) -> float:
    """Simple EWMA one-step ahead (level)."""
    x = series.astype(float).dropna()
    if len(x) == 0:
        return 1e-12
    if len(x) == 1:
        return _positive_price(float(x.iloc[-1]))
    s = float(x.iloc[0])
    for v in x.iloc[1:]:
        s = alpha * float(v) + (1.0 - alpha) * s
    return _positive_price(s)


def drift_naive_forecast(series: pd.Series) -> float:
    """Last close plus average recent daily change (short drift)."""
    x = series.astype(float).dropna()
    n = len(x)
    if n == 0:
        return 1e-12
    last = float(x.iloc[-1])
    if n < 2:
        return _positive_price(last)
    tail = x.iloc[-min(7, n) :]
    diffs = tail.diff().dropna()
    drift = float(diffs.mean()) if len(diffs) else 0.0
    pred = last + drift
    return _positive_price(pred)


def fallback_predict(series: pd.Series) -> Tuple[float, str]:
    """
    When ARIMA cannot run or converges badly — prefer EWMA, then drift-naive.
    """
    n = len(series)
    if n >= 3:
        e = ewma_forecast_next(series)
        d = drift_naive_forecast(series)
        # Blend: slightly favor EWMA for noisy crypto
        blended = 0.55 * e + 0.45 * d
        return _positive_price(blended), "ewma_drift_blend"
    if n >= 1:
        return _positive_price(float(series.iloc[-1])), "last_close"
    return 1e-12, "empty"


def try_fit_arima(series: pd.Series, order: Tuple[int, int, int]):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ARIMA(series.astype(float), order=order)
        return model.fit(method_kwargs={"warn_convergence": False})


def select_best_arima_by_aic(
    series: pd.Series,
    max_p: int = MAX_P,
    max_q: int = MAX_Q,
    max_d: int = MAX_D,
) -> Tuple[Optional[Any], Optional[Tuple[int, int, int]], float]:
    """
    Grid search with AIC. Prefer lower d if level series is stationary.
    Returns (fitted_result, order, aic) or (None, None, inf).
    """
    n = len(series)
    best_aic = np.inf
    best_fit = None
    best_order: Optional[Tuple[int, int, int]] = None

    stationary_level = adf_stationary(series)

    d_candidates = list(range(0, max_d + 1))
    if not stationary_level and 1 not in d_candidates:
        d_candidates = [1, 0, 2]
    elif not stationary_level:
        # Non-stationary: try differencing first in search order
        d_candidates = [d for d in [1, 2, 0] if d <= max_d]

    for d in d_candidates:
        for p in range(0, max_p + 1):
            for q in range(0, max_q + 1):
                if p == 0 and q == 0:
                    continue
                need = min_obs_for_order(p, d, q)
                if n < need:
                    continue
                try:
                    fit = try_fit_arima(series, (p, d, q))
                    aic = float(fit.aic)
                    if np.isfinite(aic) and aic < best_aic:
                        best_aic = aic
                        best_fit = fit
                        best_order = (p, d, q)
                except Exception:
                    continue

    if best_fit is None or best_order is None:
        return None, None, np.inf
    return best_fit, best_order, best_aic


def select_small_window_arima(series: pd.Series) -> Tuple[Optional[Any], Optional[Tuple[int, int, int]], float]:
    """Fewer points: try only tight, stable orders."""
    n = len(series)
    candidates = [
        (1, 1, 1),
        (0, 1, 1),
        (1, 0, 1),
        (1, 1, 0),
        (0, 1, 0),
        (2, 1, 0),
    ]
    best_aic = np.inf
    best_fit = None
    best_order: Optional[Tuple[int, int, int]] = None
    for order in candidates:
        p, d, q = order
        if n < min_obs_for_order(p, d, q):
            continue
        try:
            fit = try_fit_arima(series, order)
            aic = float(fit.aic)
            if np.isfinite(aic) and aic < best_aic:
                best_aic = aic
                best_fit = fit
                best_order = order
        except Exception:
            continue
    if best_fit is None:
        return None, None, np.inf
    return best_fit, best_order, best_aic


def forecast_one_step(fitted) -> Optional[float]:
    try:
        fc = fitted.get_forecast(steps=1)
        mean = fc.predicted_mean
        val = float(mean.iloc[0]) if hasattr(mean, "iloc") else float(mean[0])
        if not np.isfinite(val):
            return None
        return val
    except Exception:
        return None


def calculate_confidence(series: pd.Series, fitted, aic: float, used_fallback: bool) -> float:
    """Map in-sample fit quality + AIC to 0–100; conservative on fallback."""
    if used_fallback:
        return 38.0
    try:
        n = len(series)
        if n < 3:
            return 45.0
        # In-sample predicted mean vs actual (last window)
        start = max(0, n - min(30, n))
        pred = fitted.get_prediction(start=start, end=n - 1)
        pm = pred.predicted_mean
        actual = series.iloc[start : n].values.astype(float)
        ph = np.asarray(pm, dtype=float).ravel()
        m = min(len(actual), len(ph))
        if m < 2:
            return max(25.0, min(90.0, 100.0 - np.log1p(max(0.0, aic)) * 3.0))
        actual = actual[-m:]
        ph = ph[-m:]
        mask = np.abs(actual) > 1e-12
        if not mask.any():
            return 50.0
        mape = float(np.mean(np.abs((actual[mask] - ph[mask]) / actual[mask])) * 100.0)
        base = max(10.0, min(95.0, 100.0 - mape))
        # Penalize very high AIC relative to sample size
        aic_pen = min(15.0, max(0.0, (aic / max(n, 1)) * 0.5))
        return float(max(15.0, min(96.0, base - aic_pen)))
    except Exception:
        try:
            return float(max(25.0, min(88.0, 100.0 - np.log1p(max(0.0, aic)) * 4.0)))
        except Exception:
            return 48.0


def main() -> None:
    raw = sys.stdin.read()
    series: Optional[pd.Series] = None
    try:
        data = parse_input(raw)
        series = prepare_series(data)
        n = len(series)
        pred: Optional[float] = None
        used_fallback = False
        fitted = None
        aic = np.inf

        if n < MIN_LEN_SMALL_ARIMA:
            pred, _fb = fallback_predict(series)
            used_fallback = True
        elif n < MIN_LEN_FULL_GRID:
            fitted, _order, aic = select_small_window_arima(series)
            if fitted is not None:
                pred = forecast_one_step(fitted)
            if pred is None or not np.isfinite(pred) or pred <= 0:
                pred, _fb = fallback_predict(series)
                used_fallback = True
                fitted = None
        else:
            fitted, _order, aic = select_best_arima_by_aic(series)
            if fitted is not None:
                pred = forecast_one_step(fitted)
            if pred is None or not np.isfinite(pred) or pred <= 0:
                fitted2, _, aic2 = select_small_window_arima(series)
                if fitted2 is not None:
                    pred = forecast_one_step(fitted2)
                    if pred is not None and np.isfinite(pred) and pred > 0:
                        fitted = fitted2
                        if np.isfinite(aic2):
                            aic = float(aic2)
                    else:
                        pred = None
            if pred is None or not np.isfinite(pred) or pred <= 0:
                pred, _fb = fallback_predict(series)
                used_fallback = True
                fitted = None

        pred = _positive_price(float(pred))

        confidence = calculate_confidence(series, fitted, float(aic) if np.isfinite(aic) else 9999.0, used_fallback)

        output: Dict[str, Any] = {
            "predicted_price": pred,
            "confidence": float(max(5.0, min(100.0, confidence))),
            "model_name": "arima",
        }
        sys.stdout.write(json.dumps(output))
    except Exception as e:
        # stdin tek okunur; seri oluştuysa EWMA/drift fallback, yoksa yapılandırılmış hata
        err_output: Dict[str, Any]
        if series is not None:
            try:
                pred_fb, _ = fallback_predict(series)
                err_output = {
                    "predicted_price": _positive_price(pred_fb),
                    "confidence": 32.0,
                    "model_name": "arima",
                    "error": str(e),
                }
            except Exception:
                err_output = {
                    "predicted_price": None,
                    "confidence": 0.0,
                    "model_name": "arima",
                    "error": str(e),
                }
        else:
            err_output = {
                "predicted_price": None,
                "confidence": 0.0,
                "model_name": "arima",
                "error": str(e),
            }
        sys.stdout.write(json.dumps(err_output))


if __name__ == "__main__":
    main()
