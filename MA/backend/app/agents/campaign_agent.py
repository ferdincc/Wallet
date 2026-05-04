"""
Campaign Agent — OKYiSS Node /api/campaigns ile kampanya & fırsat özeti.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.agents.base_agent import BaseAgent
from app.agents.reasoning_log import ReasoningStepType
from app.config import settings


def _node_base() -> str:
    return os.getenv("NODE_BACKEND_BASE_URL") or getattr(
        settings, "NODE_BACKEND_BASE_URL", None
    ) or "http://127.0.0.1:3001"


class CampaignAgent(BaseAgent):
    """Kampanya / airdrop / yeni listeleme sorguları."""

    def __init__(self):
        super().__init__("CampaignAgent")

    async def execute(
        self,
        campaign_filter: str = "all",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        campaign_filter: all | airdrop | AI_CONTENT | listing | today
        """
        base = _node_base().rstrip("/")
        url = f"{base}/api/campaigns"
        params: Dict[str, str] = {}
        cf = (campaign_filter or "all").strip()
        if cf.lower() == "today":
            pass  # tümünü çek, sonra UTC bugün süz
        elif cf.lower() in ("airdrop",):
            params["type"] = "AIRDROP"
        elif cf.upper() in ("AI_CONTENT", "TESTNET", "LAUNCH", "NFT_MINT", "REFERRAL"):
            params["type"] = cf.upper()
        elif cf.lower() in ("ai_content",):
            params["type"] = "AI_CONTENT"
        elif cf.lower() in ("listing", "new_token", "coinmarketcap"):
            params["source"] = "coinmarketcap"

        if self.reasoning_log:
            self.reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.DATA_FETCH,
                description="Kampanya API çağrısı",
                data={"url": url, "params": params},
            )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url, params=params or None)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            if self.reasoning_log:
                self.reasoning_log.add_step(
                    agent_name=self.name,
                    step_type=ReasoningStepType.WARNING,
                    description="Kampanya API hatası",
                    data={"error": str(e)},
                )
            return {
                "success": False,
                "error": str(e),
                "agent": self.name,
                "narrative": f"Kampanya verisi alınamadı: {e}",
            }

        items: List[Dict[str, Any]] = data.get("items") or []
        if cf.lower() == "today":
            items = _filter_today(items)

        narrative = _build_narrative(items, cf)

        if self.reasoning_log:
            self.reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.ANALYSIS,
                description="Kampanya listesi işlendi",
                data={"count": len(items)},
            )

        return {
            "success": True,
            "agent": self.name,
            "campaign_filter": cf,
            "items": items[:25],
            "narrative": narrative,
            "raw": data,
        }


def _filter_today(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from datetime import timedelta

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = start + timedelta(days=1)

    out = []
    for it in items:
        for key in ("publishedAt", "startTime", "dateAdded"):
            raw = it.get(key)
            if not raw:
                continue
            try:
                d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                if start <= d < day_end:
                    out.append(it)
                    break
            except Exception:
                continue
    return out


def _build_narrative(items: List[Dict[str, Any]], flt: str) -> str:
    if not items:
        return "Şu an listelenecek kampanya bulunamadı. Fırsatlar sayfasından veya daha sonra tekrar deneyin."

    fk = (flt or "all").strip().lower()
    title_map = {
        "airdrop": "Airdrop odaklı öne çıkanlar",
        "ai_content": "AI içerik ödülleri",
        "listing": "Yeni listeleme / launch kayıtları",
        "new_token": "Yeni listeleme / launch kayıtları",
        "coinmarketcap": "Yeni listeleme / launch kayıtları",
        "today": "Bugün eklenen / başlayan kayıtlar",
        "all": "Öne çıkan kampanyalar",
    }
    title = title_map.get(fk) or "Kampanyalar"

    lines = []
    lines.append(f"📢 {title}\n")

    for i, it in enumerate(items[:8], 1):
        name = it.get("title") or it.get("name") or "Kampanya"
        reward = it.get("rewardAmount") or it.get("rewardType") or "—"
        end = it.get("endTime") or ""
        url = it.get("url") or ""
        score = it.get("importanceScore")
        tag = it.get("typeTag") or ""

        end_s = ""
        if end:
            try:
                ed = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days = (ed - now).days
                if days >= 0:
                    end_s = f"{days} gün sonra" if days else "bugün"
                else:
                    end_s = "süresi dolmuş"
            except Exception:
                end_s = str(end)[:16]

        extra = f" [Önem: {score}]" if score is not None else ""
        line = f"{i}. **{name}** ({tag}) — Ödül: {reward}"
        if end_s:
            line += f" — Bitiş: {end_s}"
        line += extra
        if url:
            line += f"\n   → {url}"
        lines.append(line)

    if len(items) > 8:
        lines.append(f"\n_…ve {len(items) - 8} kayıt daha (Fırsatlar sayfasında tam liste)._")

    return "\n".join(lines)
