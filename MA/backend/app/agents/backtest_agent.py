"""
Backtest Agent - Runs automated backtests and summarizes results for chat.

Integrates with Node backtest backend:
  POST {BACKTEST_NODE_URL}/run
Default BACKTEST_NODE_URL: http://127.0.0.1:3001/api/backtest
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
import os
import math

import httpx

from app.agents.base_agent import BaseAgent
from app.agents.reasoning_log import ReasoningStepType


SUPPORTED_MODELS = ["prophet", "lgbm", "arima", "ensemble"]


def _to_backend_symbol(symbol: str) -> str:
    """
    Convert UI symbol like 'BTC/USDT' to Binance-style 'BTCUSDT'.
    If already in that format, returns unchanged.
    """
    s = (symbol or "").strip().upper()
    if "/" in s:
        return s.replace("/", "")
    return s


def _utc_date_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
        return None
    except Exception:
        return None


class BacktestAgent(BaseAgent):
    """Agent responsible for running backtests and interpreting model performance."""

    def __init__(self):
        super().__init__("BacktestAgent")

    async def execute(
        self,
        symbol: str,
        days: int = 90,
        window_days: int = 30,
        models: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        import time

        models = models or SUPPORTED_MODELS
        models = [m for m in models if m in SUPPORTED_MODELS]
        if not models:
            return {"success": False, "error": "No valid models provided", "agent": self.name}

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        backend_symbol = _to_backend_symbol(symbol)

        node_url = os.getenv("BACKTEST_NODE_URL") or os.getenv("BACKTEST_NODE_API") or "http://127.0.0.1:3001/api/backtest"

        if self.reasoning_log:
            self.reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.DATA_FETCH,
                description="Backtest servisine istek hazırlanıyor",
                data={
                    "symbol": symbol,
                    "backend_symbol": backend_symbol,
                    "days": days,
                    "window_days": window_days,
                    "models": models,
                    "node_url": node_url,
                },
            )

        payload = {
            "symbol": backend_symbol,
            "models": models,
            "startDate": _utc_date_str(start_dt),
            "endDate": _utc_date_str(end_dt),
            "windowDays": window_days,
        }

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{node_url.rstrip('/')}/run", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            if self.reasoning_log:
                self.reasoning_log.add_step(
                    agent_name=self.name,
                    step_type=ReasoningStepType.WARNING,
                    description="Backtest servisine erişilemedi",
                    data={"error": str(e)},
                )
            return {
                "success": False,
                "error": f"Backtest servisine erişilemedi: {str(e)}",
                "agent": self.name,
            }
        duration_ms = (time.time() - t0) * 1000

        summaries = data.get("summaries") or []
        if self.reasoning_log:
            self.reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.DATA_FETCH,
                description="Backtest sonuçları alındı",
                data={"summary_count": len(summaries)},
                duration_ms=duration_ms,
            )

        analysis = self._analyze_summaries(summaries)
        if self.reasoning_log:
            self.reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.ANALYSIS,
                description="Backtest sonuçları analiz edildi",
                data=analysis,
            )

        narrative = self._build_narrative(symbol=symbol, days=days, analysis=analysis)

        return {
            "success": True,
            "agent": self.name,
            "symbol": symbol,
            "days": days,
            "window_days": window_days,
            "models": models,
            "raw": data,
            "analysis": analysis,
            "narrative": narrative,
        }

    def _analyze_summaries(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Normalize and score models
        normalized = []
        for s in summaries:
            model = (s.get("model") or "").lower()
            if model not in SUPPORTED_MODELS:
                continue
            normalized.append(
                {
                    "model": model,
                    "avgMAPE": _safe_float(s.get("avgMAPE")),
                    "avgRMSE": _safe_float(s.get("avgRMSE")),
                    "directionAccuracy": _safe_float(s.get("directionAccuracy")),
                    "totalPredictions": int(s.get("totalPredictions") or 0),
                    "results": s.get("results") or [],
                    "error": s.get("error"),
                }
            )

        if not normalized:
            return {"models": [], "best_overall": None, "worst_overall": None, "notes": ["No usable summaries returned."]}

        # Score: favor higher directionAccuracy, lower MAPE and RMSE
        def score(item: Dict[str, Any]) -> float:
            da = item.get("directionAccuracy") or 0.0
            mape = item.get("avgMAPE") or 100.0
            rmse = item.get("avgRMSE") or 0.0
            rmse_pen = min(rmse / 100.0, 100.0)  # crude normalization
            return (da * 0.5) + ((100.0 - min(mape, 100.0)) * 0.35) + ((100.0 - rmse_pen) * 0.15)

        scored = [{"model": x["model"], "score": score(x), **x} for x in normalized if x.get("totalPredictions", 0) > 0]
        scored.sort(key=lambda x: x["score"], reverse=True)

        best = scored[0] if scored else None
        worst = scored[-1] if scored else None

        # Build per-regime notes using shared actual series by date
        # We infer daily trend from actual_price changes between consecutive dates.
        actual_by_date = {}
        for x in normalized:
            for r in x.get("results", []):
                d = r.get("date")
                a = _safe_float(r.get("actual_price"))
                if d and a is not None:
                    actual_by_date[d] = a
        dates_sorted = sorted(actual_by_date.keys())
        trend_by_date = {}
        prev_a = None
        for d in dates_sorted:
            a = actual_by_date[d]
            if prev_a is None:
                trend_by_date[d] = None
            else:
                trend_by_date[d] = "up" if a > prev_a else "down" if a < prev_a else "flat"
            prev_a = a

        regime_stats = {}
        for x in normalized:
            m = x["model"]
            up_total = up_ok = down_total = down_ok = 0
            for r in x.get("results", []):
                d = r.get("date")
                if not d or trend_by_date.get(d) in (None, "flat"):
                    continue
                ok = bool(r.get("direction_correct"))
                if trend_by_date[d] == "up":
                    up_total += 1
                    if ok:
                        up_ok += 1
                elif trend_by_date[d] == "down":
                    down_total += 1
                    if ok:
                        down_ok += 1
            regime_stats[m] = {
                "up_accuracy": (up_ok / up_total * 100.0) if up_total else None,
                "down_accuracy": (down_ok / down_total * 100.0) if down_total else None,
                "up_samples": up_total,
                "down_samples": down_total,
            }

        return {
            "models": scored,
            "best_overall": best,
            "worst_overall": worst,
            "regime_stats": regime_stats,
        }

    def _build_narrative(self, symbol: str, days: int, analysis: Dict[str, Any]) -> str:
        best = analysis.get("best_overall")
        worst = analysis.get("worst_overall")
        regime = analysis.get("regime_stats", {})

        if not best:
            return "Backtest sonuçları alınamadı veya yeterli veri yok."

        def nice_model(m: str) -> str:
            return {"lgbm": "LightGBM", "prophet": "Prophet", "arima": "ARIMA", "ensemble": "Ensemble"}.get(m, m)

        parts = []
        parts.append(f"📌 Son {days} gün için {symbol} backtest sonucuna göre genel lider: **{nice_model(best['model'])}**.")
        if best.get("directionAccuracy") is not None:
            parts.append(f"- Yön doğruluğu: **%{best['directionAccuracy']:.1f}**")
        if best.get("avgMAPE") is not None:
            parts.append(f"- Ortalama MAPE: **%{best['avgMAPE']:.2f}**")
        if best.get("avgRMSE") is not None:
            parts.append(f"- RMSE: **{best['avgRMSE']:.2f}**")

        if worst:
            parts.append(f"\n🔻 Bu aralıkta en zayıf model: **{nice_model(worst['model'])}**.")

        # Add regime insights (up vs down) for ARIMA as requested, and best model too.
        for m in ["arima", best["model"]]:
            rs = regime.get(m) or {}
            up_acc = rs.get("up_accuracy")
            down_acc = rs.get("down_accuracy")
            if up_acc is None and down_acc is None:
                continue
            parts.append(f"\n📈 Rejim analizi ({nice_model(m)}):")
            if up_acc is not None:
                parts.append(f"- Yükseliş günleri yön doğruluğu: **%{up_acc:.1f}** (n={rs.get('up_samples')})")
            if down_acc is not None:
                parts.append(f"- Düşüş günleri yön doğruluğu: **%{down_acc:.1f}** (n={rs.get('down_samples')})")

        return "\n".join(parts)

