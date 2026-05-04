"""
Wallet Agent — Node /api/wallet çok zincirli analiz + istemci snapshot (wallet_context).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.agents.base_agent import BaseAgent
from app.config import settings
from app.agents.agent_i18n import resolve_lang, tx

logger = logging.getLogger(__name__)


class WalletAgent(BaseAgent):
    """Cüzdan verisi: önce frontend snapshot, yoksa Node Etherscan analizi."""

    def __init__(self):
        super().__init__("WalletAgent")

    def _node_base(self) -> str:
        return str(getattr(settings, "NODE_BACKEND_BASE_URL", "http://127.0.0.1:3010")).rstrip("/")

    async def _fetch_llm_context(self, address: str) -> Optional[str]:
        base = self._node_base()
        url = f"{base}/api/wallet/llm-context/{address}"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(url, params={"chain": "all"})
                if r.status_code != 200:
                    logger.warning("Wallet llm-context HTTP %s: %s", r.status_code, r.text[:200])
                    return None
                data = r.json()
                return data.get("context") if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Wallet Node fetch failed: %s", e)
            return None

    async def execute(
        self,
        wallet_address: Optional[str] = None,
        wallet_mode: str = "balance",
        wallet_context: Optional[str] = None,
        locale: str = "en",
        **kwargs,
    ) -> Dict[str, Any]:
        lang = resolve_lang(locale, "")
        ctx = (wallet_context or kwargs.get("wallet_context") or "").strip()
        addr = (wallet_address or "").strip()

        if ctx:
            headline = tx(lang, "wallet_snapshot_headline")
            body = ctx[:12000]
            narrative = f"{headline}\n\n{body}"
            return {
                "success": True,
                "agent": self.name,
                "narrative": narrative,
                "wallet_mode": wallet_mode,
                "source": "client_context",
            }

        if addr.startswith("0x") and len(addr) == 42:
            text = await self._fetch_llm_context(addr)
            if text:
                headline = tx(lang, "wallet_node_headline")
                narrative = f"{headline}\n\n{text[:12000]}"
                return {
                    "success": True,
                    "agent": self.name,
                    "narrative": narrative,
                    "wallet_mode": wallet_mode,
                    "source": "node_etherscan",
                }

        return {
            "success": False,
            "agent": self.name,
            "error": "wallet_unavailable",
            "narrative": tx(lang, "wallet_need_address_or_module"),
        }
