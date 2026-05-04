"""
Anthropic Claude API — OKYiSS sohbet modu (Ollama yokken veya tercih olarak).

Resmi SDK: Python'da `anthropic` paketi (pip install anthropic); Node için eşdeğeri `@anthropic-ai/sdk`.
Aynı Messages API ve modeller; bu backend Python olduğu için `anthropic` import edilir.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from app.config import reload_dotenv_files, settings

logger = logging.getLogger(__name__)


def get_anthropic_api_key() -> Optional[str]:
    """
    Claude için anahtar: önce .env yeniden yüklenir, sonra os.environ.
    (Sadece settings nesnesine güvenmek bazen boş kalır; dosya güncellendiğinde bu yol güvenilir.)
    """
    reload_dotenv_files()
    raw = os.getenv("ANTHROPIC_API_KEY")
    if raw and str(raw).strip():
        return str(raw).strip()
    sk = getattr(settings, "ANTHROPIC_API_KEY", None)
    if sk and str(sk).strip():
        return str(sk).strip()
    return None


def anthropic_api_key_ready() -> bool:
    """Gerçek anahtar var mı (boş / .env placeholder değil)."""
    k = get_anthropic_api_key()
    if not k:
        return False
    if "REPLACE_WITH_YOUR_KEY" in k:
        return False
    return True


try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[misc, assignment]


def is_claude_chat_available() -> bool:
    if Anthropic is None:
        logger.warning("anthropic paketi yüklü değil: pip install anthropic")
        return False
    if not anthropic_api_key_ready():
        k = get_anthropic_api_key()
        if k and "REPLACE_WITH_YOUR_KEY" in str(k):
            logger.warning(
                "ANTHROPIC_API_KEY hâlâ placeholder — MA/backend/.env içinde gerçek sk-ant-... ile değiştirin."
            )
        else:
            logger.warning(
                "ANTHROPIC_API_KEY tanımlı değil — MA/backend/.env içinde sk-ant-... ayarlayıp API'yi yeniden başlatın."
            )
        return False
    return True


def normalize_messages_for_claude(
    prior: Optional[List[Dict[str, Any]]],
    current_user_text: str,
    max_messages: int = 10,
) -> List[Dict[str, str]]:
    """user/assistant çiftleri + güncel kullanıcı mesajı; son max_messages."""
    out: List[Dict[str, str]] = []
    for item in prior or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant"):
            continue
        if content is None:
            continue
        text = str(content).strip()
        if not text:
            continue
        out.append({"role": str(role), "content": text})
    cur = (current_user_text or "").strip()
    if cur:
        out.append({"role": "user", "content": cur})
    if len(out) > max_messages:
        out = out[-max_messages:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


OKYISS_CHAT_SYSTEM = """You are OKYiSS, a crypto intelligence assistant.

CRITICAL LANGUAGE RULE: You MUST detect the language of the user's message and respond in EXACTLY the same language.
- User writes in Turkish → respond in Turkish
- User writes in English → respond in English
- User writes in Chinese → respond in Chinese
- User writes in Arabic → respond in Arabic
- User writes in any other language → respond in that language
NEVER respond in a different language than the user wrote in.
This rule overrides everything else.

You are an expert in cryptocurrency markets, blockchain technology, DeFi, trading strategies, and Web3. Give helpful, accurate, and concise responses. Never give financial advice; offer analysis and context instead. Remember conversation history and refer back to previous messages.

Style for chat mode:
- Short and clear; avoid unnecessary repetition.
- Prefer natural conversational prose over bullet lists unless a short list truly helps.
- Use emojis sparingly."""


def build_chat_system_prompt(
    server_agent_memory: Optional[str],
    client_agent_context: Optional[str],
    ui_locale: Optional[str] = None,
    wallet_context: Optional[str] = None,
) -> str:
    base = OKYISS_CHAT_SYSTEM
    blocks: List[str] = []
    if server_agent_memory and str(server_agent_memory).strip():
        blocks.append(f"Recent server-side analysis summary: {str(server_agent_memory).strip()[:2000]}")
    if client_agent_context and str(client_agent_context).strip():
        blocks.append(f"Extra context from the client about the last analysis: {str(client_agent_context).strip()[:2000]}")
    if wallet_context and str(wallet_context).strip():
        blocks.append(
            "Wallet / on-chain analysis (OKYiSS Wallet module; use for questions about tokens received, "
            "profit/loss estimates, last transactions, chain exposure): "
            f"{str(wallet_context).strip()[:12000]}"
        )
    if blocks:
        base = base + "\n\n" + "\n".join(blocks)
    if (ui_locale or "").lower() == "en":
        base += (
            "\n\nAPPLICATION UI LOCALE IS ENGLISH (en): Always write your entire reply in English, "
            "even if the latest user message is in Turkish or another language. Do not switch languages."
        )
    return base


AGENT_SUMMARY_SYSTEM = """You turn raw multi-agent crypto analysis into a single user-facing reply.

CRITICAL LANGUAGE RULE: Detect the language of the user's latest message and respond in EXACTLY that same language for the entire reply. Never switch languages.

Summarize the analysis results in the user's language in simple, natural conversational prose — not a stiff bullet list unless a short list truly helps.
Do not give personalized investment advice; present analysis, metrics, and risks in an educational way.
Use emojis sparingly. Preserve important numbers when relevant but weave them into sentences."""


async def summarize_agent_output_for_user(
    user_query: str,
    raw_agent_text: str,
    *,
    max_tokens: int = 2500,
    ui_locale: Optional[str] = None,
) -> str:
    """Ajan çıktısını Claude ile sade, akıcı metne çevirir."""
    if not is_claude_chat_available():
        raise RuntimeError("Claude is not available (missing API key or anthropic package).")
    raw = (raw_agent_text or "").strip()
    if not raw:
        return raw
    clipped = raw[:28000]
    user_block = (
        f"User message / question:\n{user_query.strip()}\n\n"
        f"---\nAgent analysis results to summarize:\n{clipped}\n\n"
        "---\nSummarize these results for the user in their language: plain, friendly prose."
    )
    if (ui_locale or "").lower() == "en":
        user_block += (
            "\n\nThe application UI is set to English: write the entire summary in English only, "
            "even if the original analysis text contained Turkish."
        )
        system = (
            AGENT_SUMMARY_SYSTEM
            + "\n\nUI locale is English: produce the full summary in English only."
        )
    else:
        system = AGENT_SUMMARY_SYSTEM
    messages: List[Dict[str, str]] = [{"role": "user", "content": user_block}]
    return await claude_chat_completion(messages, system=system, max_tokens=max_tokens)


def _extract_message_text(resp: Any) -> str:
    parts: List[str] = []
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(str(block.text))
    return "".join(parts).strip()


def _sync_messages_create(
    messages: List[Dict[str, str]],
    system: str,
    max_tokens: int,
) -> str:
    key = get_anthropic_api_key()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to MA/backend/.env and restart uvicorn.")
    client = Anthropic(api_key=key)  # type: ignore[misc]
    model = (getattr(settings, "CLAUDE_CHAT_MODEL", None) or "").strip() or "claude-sonnet-4-20250514"
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return _extract_message_text(resp)


async def test_claude_minimal_message() -> Dict[str, Any]:
    """
    Minimal Claude call for diagnostics (GET /api/.../chat/test-llm).
    Returns ok/reply/error without exposing the API key.
    """
    out: Dict[str, Any] = {
        "anthropic_sdk_installed": Anthropic is not None,
        "api_key_configured": anthropic_api_key_ready(),
    }
    if Anthropic is None:
        out["ok"] = False
        out["error"] = "Python package `anthropic` is not installed. Run: pip install anthropic"
        return out
    if not anthropic_api_key_ready():
        k = get_anthropic_api_key()
        out["ok"] = False
        if k and "REPLACE_WITH_YOUR_KEY" in str(k):
            out["error"] = (
                "ANTHROPIC_API_KEY is still the placeholder in MA/backend/.env. "
                "Replace REPLACE_WITH_YOUR_KEY with your real key and restart."
            )
        else:
            out["error"] = (
                "ANTHROPIC_API_KEY is not set. Put it in MA/backend/.env (not node-backend/.env) "
                "as ANTHROPIC_API_KEY=sk-ant-... and restart the FastAPI process."
            )
        return out
    try:
        text = await claude_chat_completion(
            [{"role": "user", "content": "Reply with exactly: hello"}],
            system="You are a test harness. Reply with exactly: hello",
            max_tokens=32,
        )
        out["ok"] = True
        out["reply"] = (text or "").strip()
        return out
    except Exception as e:
        logger.exception("test_claude_minimal_message failed")
        out["ok"] = False
        out["error"] = str(e)
        return out


async def claude_chat_completion(
    messages: List[Dict[str, str]],
    system: str,
    max_tokens: int = 1000,
) -> str:
    if not is_claude_chat_available():
        raise RuntimeError(
            "Claude chat unavailable: pip install anthropic, set a real ANTHROPIC_API_KEY in MA/backend/.env "
            "(not the placeholder), and restart the API."
        )
    try:
        return await asyncio.to_thread(
            _sync_messages_create, messages, system, max_tokens
        )
    except Exception as e:
        logger.exception("Claude API hatası: %s", e)
        raise
