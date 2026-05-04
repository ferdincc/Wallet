"""Localized strings for prediction API responses (confidence, XAI, warnings)."""
from __future__ import annotations

from typing import Optional


def normalize_lang(lang: Optional[str]) -> str:
    """Product UI is English-only; ignore legacy `tr` query values."""
    return "en"


def is_english(lang: Optional[str]) -> bool:
    return normalize_lang(lang) == "en"


def confidence_message(
    lang: Optional[str],
    score: float,
    up: bool,
    *,
    simple_fallback: bool = False,
    neutral: bool = False,
) -> str:
    en = is_english(lang)
    if neutral:
        if en:
            base = f"Our model shows no clear directional bias ({score:.0f}% confidence)"
        else:
            base = f"Modelimiz %{score:.0f} güven oranıyla değişim bekliyor"
        if simple_fallback and en:
            return f"{base} (simple trend analysis)"
        if simple_fallback and not en:
            return f"{base} (Basit trend analizi)"
        return base
    if en:
        move = "an upward move" if up else "a downward move"
        base = f"Our model expects {move} with {score:.0f}% confidence"
        if simple_fallback:
            return f"{base} (simple trend analysis)"
        return base
    direction = "yükseliş" if up else "düşüş"
    base = f"Modelimiz %{score:.0f} güven oranıyla {direction} bekliyor"
    if simple_fallback:
        return f"{base} (Basit trend analizi)"
    return base


def direction_label(lang: Optional[str], up: bool, neutral: bool = False) -> str:
    if neutral:
        return "change" if is_english(lang) else "değişim"
    if is_english(lang):
        return "up" if up else "down"
    return "yükseliş" if up else "düşüş"


def fallback_warning(lang: Optional[str]) -> str:
    if is_english(lang):
        return (
            "Advanced models (Prophet/LightGBM) are not installed. "
            "Using simple trend analysis."
        )
    return (
        "Gelişmiş modeller (Prophet/LightGBM) yüklü değil. "
        "Basit trend analizi kullanılıyor."
    )


def feature_importance_labels(lang: Optional[str]) -> dict[str, str]:
    """Keys: rsi, macd, sma, past, vol, other — values are display labels for charts."""
    en = is_english(lang)
    if en:
        return {
            "rsi": "RSI",
            "macd": "MACD",
            "sma": "SMA",
            "past": "Past price",
            "vol": "Volume",
            "other": "Other",
        }
    return {
        "rsi": "RSI",
        "macd": "MACD",
        "sma": "SMA",
        "past": "Geçmiş Fiyat",
        "vol": "Hacim",
        "other": "Diğer",
    }


def xai_explanation(
    lang: Optional[str],
    *,
    model: str,
    periods: int,
    timeframe: str,
    confidence_score: float,
    directional_accuracy: float,
    mape: float,
    current_price: float,
    change_pct: float,
    direction_up: bool,
) -> str:
    en = is_english(lang)
    if confidence_score >= 70:
        conf_level_tr, conf_level_en = "yüksek", "high"
    elif confidence_score >= 50:
        conf_level_tr, conf_level_en = "orta", "medium"
    else:
        conf_level_tr, conf_level_en = "düşük", "low"

    if model == "fallback":
        if en:
            intro = (
                f"A simple trend-based fallback produced a forecast {periods} {timeframe} ahead "
                f"(Prophet/LightGBM were not available)."
            )
        else:
            intro = (
                f"Prophet/LightGBM kullanılamadığı için basit trend tabanlı yedek model "
                f"{periods} {timeframe} sonrası için tahmin üretti."
            )
    elif model == "prophet":
        if en:
            intro = (
                f"Prophet used time-series analysis to produce a forecast "
                f"{periods} {timeframe} ahead."
            )
        else:
            intro = (
                f"Prophet modeli, zaman serisi analizi kullanarak "
                f"{periods} {timeframe} sonrası için tahmin yaptı."
            )
    elif model == "lightgbm":
        if en:
            intro = (
                f"LightGBM used technical indicators (RSI, MACD) and historical prices "
                f"to produce a forecast {periods} {timeframe} ahead."
            )
        else:
            intro = (
                f"LightGBM modeli, teknik indikatörler (RSI, MACD) ve geçmiş fiyat verilerini kullanarak "
                f"{periods} {timeframe} sonrası için tahmin yaptı."
            )
    else:
        if en:
            intro = (
                f"The ensemble model (Prophet + LightGBM) combined multiple approaches "
                f"to produce a forecast {periods} {timeframe} ahead."
            )
        else:
            intro = (
                f"Ensemble modeli (Prophet + LightGBM), birden fazla yaklaşımı birleştirerek "
                f"{periods} {timeframe} sonrası için tahmin yaptı."
            )

    if en:
        mid = (
            f"Confidence score: {confidence_score:.0f}% ({conf_level_en} confidence). "
            f"On historical data the model showed {directional_accuracy:.1f}% directional accuracy "
            f"and {mape:.2f}% mean absolute percentage error (MAPE)."
        )
        dir_phrase = "upward" if direction_up else "downward"
        tail = (
            f"Forecast: From the current price of ${current_price:,.2f}, "
            f"a {abs(change_pct):.2f}% {dir_phrase} move is expected."
        )
        parts = [intro, mid, tail]
        if confidence_score < 60:
            parts.append(
                "Warning: With a low confidence score, changes in market conditions may affect the forecast."
            )
        return " ".join(parts)

    mid = (
        f"Güven skoru: %{confidence_score:.0f} ({conf_level_tr} güven). "
        f"Model, geçmiş verilerde %{directional_accuracy:.1f} yön doğruluğu ve "
        f"%{mape:.2f} ortalama mutlak yüzde hatası (MAPE) gösterdi."
    )
    dir_word = "yükseliş" if direction_up else "düşüş"
    tail = (
        f"Tahmin: Mevcut fiyat ${current_price:,.2f}'dan {dir_word} yönünde "
        f"%{abs(change_pct):.2f} değişim bekleniyor."
    )
    parts = [intro, mid, tail]
    if confidence_score < 60:
        parts.append(
            "Uyarı: Düşük güven skoru nedeniyle, piyasa koşullarındaki değişiklikler tahmini etkileyebilir."
        )
    return " ".join(parts)


def xai_explanation_failed(lang: Optional[str]) -> str:
    return "Could not generate forecast explanation." if is_english(lang) else "Tahmin açıklaması oluşturulamadı."


def err_symbol_required(lang: Optional[str]) -> str:
    return "Symbol is required for prediction" if is_english(lang) else "Symbol parametresi gereklidir"


def err_fetch_timeout(lang: Optional[str]) -> str:
    return "Data fetch timed out. Please try again." if is_english(lang) else "Veri çekme zaman aşımına uğradı. Lütfen tekrar deneyin."


def err_no_market_data(lang: Optional[str]) -> str:
    return "Market data is unavailable. Please try again later." if is_english(lang) else "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin."


def err_insufficient_history(lang: Optional[str]) -> str:
    return "Not enough history for a forecast. Please try again later." if is_english(lang) else "Tahmin için yeterli geçmiş veri bulunamadı. Lütfen daha sonra tekrar deneyin."


def err_prediction_failed(lang: Optional[str], detail: str) -> str:
    if is_english(lang):
        return f"Forecast error: {detail}"
    return f"Fiyat tahmini hatası: {detail}"
