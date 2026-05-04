"""
Chat Agent - Main conversational agent that coordinates other agents
"""
from typing import Dict, Any, Optional, List
import asyncio
import json
import logging
import os
import re
import httpx
from app.agents.base_agent import BaseAgent
from app.agents.data_agent import DataAgent
from app.agents.analysis_agent import AnalysisAgent
from app.agents.sentiment_agent import SentimentAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.risk_agent import RiskAgent
from app.agents.consensus_agent import ConsensusAgent
from app.agents.backtest_agent import BacktestAgent
from app.agents.campaign_agent import CampaignAgent
from app.agents.wallet_agent import WalletAgent
from app.agents.llm_service import llm_service
from app.agents.reasoning_log import ReasoningLog, ReasoningStepType
from app.services.user_profile_service import user_profile_service
from app.services.historical_return_service import try_answer_long_horizon_query
from app.config import BACKEND_ROOT, reload_dotenv_files
from app.agents.agent_i18n import (
    resolve_lang,
    tx,
    rsi_status_label,
    risk_warnings_for_comprehensive,
    recommendation_label,
)
from app.models.user import User
from sqlalchemy.orm import Session
import time

# --- Sohbet modu: ücretsiz LLM (Groq → Ollama → Gemini). Sadece bu dosyada tanımlı. ---
_chat_mode_logger = logging.getLogger("app.agents.chat_agent.sohbet")

# Groq: llama3-8b-8192 kapatıldı (Groq deprecations) — llama-3.1-8b-instant kullan.
# İsteğe bağlı: MA/backend/.env içinde GROQ_CHAT_MODEL=...
DEFAULT_GROQ_CHAT_MODEL = "llama-3.1-8b-instant"
GROQ_MODEL_FALLBACKS = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
)
OLLAMA_MODELS_TO_TRY = ("llama3", "mistral", "llama3:latest", "mistral:latest")
GEMINI_CHAT_MODEL = "gemini-1.5-flash"
DEFAULT_CLAUDE_CHAT_MODEL = "claude-sonnet-4-20250514"


def _reload_env_for_chat_mode() -> None:
    """
    Sohbet çağrısı öncesi .env yolları (app.config ile aynı):
    MA/.env (override=False) → MA/backend/.env (override=True).
    """
    try:
        from dotenv import load_dotenv

        root_env = BACKEND_ROOT.parent / ".env"
        backend_env = BACKEND_ROOT / ".env"
        load_dotenv(root_env, override=False)
        load_dotenv(backend_env, override=True)
        _chat_mode_logger.warning(
            "[sohbet env] root=%s backend=%s file_exists=(%s,%s)",
            root_env,
            backend_env,
            root_env.is_file(),
            backend_env.is_file(),
        )
    except ImportError:
        _chat_mode_logger.error(
            "[sohbet env] python-dotenv yok; GROQ_API_KEY dosyadan okunmayabilir. pip install python-dotenv"
        )


def _ollama_base_url() -> str:
    return (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")


def _mask_env_flag(name: str) -> str:
    return "set" if (os.getenv(name) or "").strip() else "missing"


def _groq_models_to_try() -> List[str]:
    """Ortam GROQ_CHAT_MODEL önce, sonra bilinen çalışan modeller (deprecated model atlanır)."""
    out: List[str] = []
    env_m = (os.getenv("GROQ_CHAT_MODEL") or "").strip()
    deprecated = frozenset({"llama3-8b-8192", "llama3-70b-8192"})
    if env_m:
        if env_m.lower() not in {d.lower() for d in deprecated}:
            out.append(env_m)
        else:
            _chat_mode_logger.warning(
                "[Groq] GROQ_CHAT_MODEL=%s kullanımdan kalktı; varsayılanlar deneniyor.",
                env_m,
            )
    for m in GROQ_MODEL_FALLBACKS:
        if m not in out:
            out.append(m)
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

AGENT_SUMMARY_SYSTEM = """You turn raw multi-agent crypto analysis into a single user-facing reply.

CRITICAL LANGUAGE RULE: Detect the language of the user's latest message and respond in EXACTLY that same language for the entire reply. Never switch languages.

Summarize the analysis results in the user's language in simple, natural conversational prose — not a stiff bullet list unless a short list truly helps.
Do not give personalized investment advice; present analysis, metrics, and risks in an educational way.
Use emojis sparingly. Preserve important numbers when relevant but weave them into sentences."""


def _normalize_chat_messages(
    prior: Optional[List[Dict[str, Any]]],
    current_user_text: str,
    max_messages: int = 10,
) -> List[Dict[str, str]]:
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


def _build_free_chat_system_prompt(
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
        blocks.append(
            f"Extra context from the client about the last analysis: {str(client_agent_context).strip()[:2000]}"
        )
    if wallet_context and str(wallet_context).strip():
        blocks.append(
            "Wallet / on-chain analysis (OKYiSS Wallet module; use for questions about tokens received, "
            "profit/loss estimates, last transactions, chain exposure): "
            f"{str(wallet_context).strip()[:12000]}"
        )
    if blocks:
        base = base + "\n\n" + "\n".join(blocks)

    ul = (ui_locale or "").strip().lower()
    if ul.startswith("tr"):
        base += (
            "\n\n---\nÖNCELİKLİ KURAL: Uygulama arayüz dili Türkçe seçili (tr). "
            "Bu sohbetteki TÜM yanıtları kesinlikle Türkçe yazın. "
            "Kullanıcı İngilizce veya başka dilde yazmış olsa bile yanıtı tamamen Türkçe verin; "
            "gerekirse terimleri İngilizce parantez içinde ekleyebilirsiniz."
        )
    elif ul.startswith("en"):
        base += (
            "\n\nAPPLICATION UI LOCALE IS ENGLISH (en): Always write your entire reply in English, "
            "even if the latest user message is in Turkish or another language. Do not switch languages."
        )
    return base


# Intent / sembol çıkarma: yalnızca bilinen baz semboller; fiil ve genel İngilizce kelimeler asla ticker sayılmaz.
QUOTE_CURRENCIES = frozenset({"USDT", "USD", "USDC", "BUSD", "EUR", "TRY", "FDUSD", "TUSD"})

KNOWN_BASE_SYMBOLS = frozenset({
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC", "POL", "SHIB", "TRX",
    "LINK", "ATOM", "UNI", "LTC", "BCH", "NEAR", "APT", "OP", "ARB", "PEPE", "FET", "SUI", "SEI",
    "TIA", "WLD", "INJ", "STX", "RNDR", "IMX", "GRT", "ALGO", "VET", "FIL", "HBAR", "ICP", "ETC",
    "LDO", "AAVE", "MKR", "FTM", "SNX", "CRV", "RUNE", "EGLD", "FLOW", "MANA", "SAND", "AXS", "CHZ",
    "XLM", "EOS", "WIF", "BONK", "FLOKI", "STRK", "JUP", "PYTH", "ORDI", "1000SATS", "NOT",
})

_NON_SYMBOL_WORDS = frozenset({
    "ANALYZE", "ANALYSIS", "ANALYSES", "ANALYSE", "MARKET", "MARKETS", "CHART", "CHARTS", "PRICE",
    "PRICES", "VOLUME", "TREND", "TRENDS", "SIGNAL", "SIGNALS", "FORECAST", "PREDICT", "PREDICTION",
    "CANDLE", "CANDLES", "CRYPTO", "CRYPTOCURRENCY", "COIN", "COINS", "TOKEN", "TOKENS", "ASSET",
    "ASSETS", "PAIR", "PAIRS", "SPOT", "FUTURES", "MARGIN", "ORDER", "ORDERS", "TRADE", "TRADES",
    "TRADING", "BUY", "SELL", "LONG", "SHORT", "BULL", "BEAR", "SWAP", "STAKE", "YIELD", "POOL",
    "WHAT", "WHEN", "WHERE", "WHY", "WHICH", "WHO", "HOW", "SHOW", "TELL", "GIVE", "GET", "MAKE",
    "TAKE", "FIND", "HELP", "PLEASE", "ABOUT", "WITH", "FROM", "INTO", "THAT", "THIS", "THESE",
    "THOSE", "YOUR", "THEIR", "HAVE", "HAS", "HAD", "WILL", "WOULD", "COULD", "SHOULD", "JUST",
    "ONLY", "VERY", "ALSO", "SOME", "MANY", "MUCH", "MORE", "MOST", "LESS", "LAST", "NEXT", "FIRST",
    "OPEN", "HIGH", "LOW", "CLOSE", "HIGHLIGHT", "RANGE", "TIME", "TIMEFRAME", "NOW", "TODAY",
    "UPDATE", "CURRENT", "RECENT", "LATEST", "GOOD", "BEST", "BAD", "BIG", "SMALL", "NEW", "OLD",
    "YES", "NOT", "ALL", "ANY", "CAN", "DAY", "WEEK", "MONTH", "YEAR", "HOUR", "MINUTE",
})

_CRYPTO_NAME_ALIASES = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "ether": "ETH",
    "solana": "SOL",
    "bnb": "BNB",
    "binance coin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "avalanche": "AVAX",
    "polygon": "MATIC",
    "matic": "MATIC",
}

# Bilinen sembol alternasyonu (uzun eşleşme önce)
_KNOWN_ALT = "|".join(sorted(KNOWN_BASE_SYMBOLS, key=len, reverse=True))

ACTIONS_REQUIRING_RESOLVED_SYMBOL = frozenset({
    "fetch_price", "analyze", "comprehensive_analyze", "sentiment", "predict", "backtest", "portfolio_trade",
})


def _build_known_pair_pattern():
    q = "|".join(sorted(QUOTE_CURRENCIES, key=len, reverse=True))
    return re.compile(rf"\b({_KNOWN_ALT})/({q})\b", re.IGNORECASE)


_KNOWN_PAIR_RE = _build_known_pair_pattern()


class ChatAgent(BaseAgent):
    """Main conversational agent that routes queries and coordinates other agents"""
    
    def __init__(self):
        super().__init__("ChatAgent")
        self.data_agent = DataAgent()
        self.analysis_agent = AnalysisAgent()
        self.sentiment_agent = SentimentAgent()
        self.prediction_agent = PredictionAgent()
        self.risk_agent = RiskAgent()
        self.consensus_agent = ConsensusAgent()
        self.backtest_agent = BacktestAgent()
        self.campaign_agent = CampaignAgent()
        self.wallet_agent = WalletAgent()
        self.context_history = []
        self._last_agent_memory: str = ""

    def _groq_chat_sync(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> str:
        try:
            from groq import Groq
        except ImportError as e:
            _chat_mode_logger.error(
                "[Groq] import başarısız: %s — pip install groq (Python SDK; npm groq-sdk değil).",
                e,
            )
            raise

        key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not key:
            _chat_mode_logger.warning("[Groq] GROQ_API_KEY boş (MA/backend/.env veya ortam değişkeni).")
            return ""
        client = Groq(api_key=key)
        openai_messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

        for model in _groq_models_to_try():
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                choice = resp.choices[0].message
                text = (getattr(choice, "content", None) or "").strip()
                if text:
                    return text
                _chat_mode_logger.warning("[Groq] Boş yanıt gövdesi (model=%s).", model)
            except Exception as e:
                _chat_mode_logger.warning(
                    "[Groq] model=%s başarısız: %s — sıradaki model deneniyor.",
                    model,
                    e,
                )
                continue

        _chat_mode_logger.error("[Groq] Tüm modeller başarısız veya boş (ör. anahtar/kota).")
        return ""

    async def _chat_with_groq(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int = 1500,
    ) -> str:
        try:
            return await asyncio.to_thread(self._groq_chat_sync, messages, system, max_tokens)
        except ImportError as e:
            self.log(f"Groq SDK yüklü değil — pip install groq: {e}", "WARNING")
            _chat_mode_logger.error("[Groq] ImportError: %s", e)
            return ""
        except Exception as e:
            self.log(f"Groq sohbet hatası: {e}", "WARNING")
            _chat_mode_logger.exception("[Groq] beklenmeyen hata")
            return ""

    def _anthropic_chat_sync(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> str:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            _chat_mode_logger.error(
                "[Anthropic] import başarısız: %s — pip install anthropic", e
            )
            raise

        key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not key or "REPLACE_WITH_YOUR_KEY" in key:
            _chat_mode_logger.warning(
                "[Anthropic] ANTHROPIC_API_KEY boş veya placeholder (MA/backend/.env)."
            )
            return ""
        model = (os.getenv("CLAUDE_CHAT_MODEL") or "").strip() or DEFAULT_CLAUDE_CHAT_MODEL
        client = Anthropic(api_key=key)
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
        except Exception as e:
            _chat_mode_logger.exception("[Anthropic] API çağrısı başarısız: %s", e)
            raise
        parts: List[str] = []
        for block in getattr(resp, "content", None) or []:
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                parts.append(block.text)
        text = "".join(parts).strip()
        if not text:
            _chat_mode_logger.warning("[Anthropic] Metin bloğu yok (model=%s).", model)
        return text

    async def _chat_with_anthropic(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int = 1500,
    ) -> str:
        try:
            return await asyncio.to_thread(
                self._anthropic_chat_sync, messages, system, max_tokens
            )
        except ImportError as e:
            self.log(f"anthropic paketi yok — pip install anthropic: {e}", "WARNING")
            _chat_mode_logger.error("[Anthropic] ImportError: %s", e)
            return ""
        except Exception as e:
            self.log(f"Anthropic sohbet hatası: {e}", "WARNING")
            _chat_mode_logger.exception("[Anthropic] beklenmeyen hata")
            return ""

    async def _chat_with_ollama(
        self,
        messages: List[Dict[str, str]],
        system: str,
    ) -> str:
        payload_base = {
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": False,
        }
        url = f"{_ollama_base_url()}/api/chat"
        async with httpx.AsyncClient(timeout=120.0) as client:
            for model in OLLAMA_MODELS_TO_TRY:
                try:
                    r = await client.post(url, json={**payload_base, "model": model})
                    if r.status_code >= 400:
                        continue
                    data = r.json()
                    msg = (data.get("message") or {}).get("content")
                    if msg and str(msg).strip():
                        return str(msg).strip()
                except httpx.ConnectError:
                    self.log(
                        "Ollama bağlantısı yok (http://127.0.0.1:11434). Kurulu ve çalışıyor mu kontrol edin.",
                        "WARNING",
                    )
                    return ""
                except Exception as e:
                    self.log(f"Ollama sohbet hatası ({model}): {e}", "WARNING")
        return ""

    def _gemini_chat_sync(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int,
    ) -> str:
        import google.generativeai as genai

        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            return ""
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            GEMINI_CHAT_MODEL,
            system_instruction=system,
        )
        prompt_parts: List[str] = []
        for m in messages:
            prompt_parts.append(f"{m['role']}: {m['content']}")
        prompt = "\n\n".join(prompt_parts)
        resp = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.7},
        )
        text = getattr(resp, "text", None)
        if text:
            return str(text).strip()
        return ""

    async def _chat_with_gemini(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int = 1500,
    ) -> str:
        try:
            return await asyncio.to_thread(self._gemini_chat_sync, messages, system, max_tokens)
        except ImportError:
            return ""
        except Exception as e:
            self.log(f"Gemini sohbet hatası: {e}", "WARNING")
            return ""

    async def _free_llm_chat_completion(
        self,
        messages: List[Dict[str, str]],
        system: str,
        max_tokens: int = 1500,
    ) -> str:
        """Öncelik: Groq → Anthropic (Claude) → Ollama → Gemini."""
        _reload_env_for_chat_mode()
        reload_dotenv_files()
        _chat_mode_logger.warning(
            "[sohbet] Anahtar özeti: GROQ=%s ANTHROPIC=%s GEMINI=%s (değerler loglanmaz)",
            _mask_env_flag("GROQ_API_KEY"),
            _mask_env_flag("ANTHROPIC_API_KEY"),
            _mask_env_flag("GEMINI_API_KEY"),
        )

        if (os.getenv("GROQ_API_KEY") or "").strip():
            out = await self._chat_with_groq(messages, system, max_tokens=max_tokens)
            if out:
                return out
            _chat_mode_logger.warning(
                "[sohbet] Groq boş döndü; sıradaki sağlayıcı deneniyor (Anthropic / Ollama / Gemini)."
            )

        if (os.getenv("ANTHROPIC_API_KEY") or "").strip():
            out = await self._chat_with_anthropic(messages, system, max_tokens=max_tokens)
            if out:
                return out
            _chat_mode_logger.warning(
                "[sohbet] Anthropic boş veya hata; Ollama / Gemini deneniyor."
            )

        out_ollama = await self._chat_with_ollama(messages, system)
        if out_ollama:
            return out_ollama

        if (os.getenv("GEMINI_API_KEY") or "").strip():
            out = await self._chat_with_gemini(messages, system, max_tokens=max_tokens)
            if out:
                return out
        else:
            _chat_mode_logger.warning("[sohbet] GEMINI_API_KEY yok; Gemini atlandı.")

        _chat_mode_logger.error(
            "[sohbet] Tüm sağlayıcılar başarısız / boş. "
            "Kontrol: MA/backend/.env, pip install groq anthropic, kredi (Anthropic), Groq quota."
        )
        return ""

    def _route_to_chat_mode(self, query: str, intent: Dict[str, Any]) -> bool:
        """Serbest sohbet (ücretsiz LLM) vs multi-agent: açık veri/analiz istekleri ajan modunda."""
        if intent.get("action") == "general":
            return True
        q = query.lower()
        # Multi-agent / veri modu — bu anahtarlar varken sohbet moduna düşme
        agent_force = [
            "fiyat", "price", "kaç tl", "kaç dolar", "kaç $", "analiz", "analysis",
            "analiz yap", "kapsamlı analiz", "kapsamli analiz", "detaylı analiz", "detayli analiz",
            "teknik analiz", "technical", "piyasa analizi", "piyasa analizi yap",
            "rsi", "macd", "bollinger", "tahmin", "predict", "forecast", "ne olacak",
            "ne kadar olur", "sentiment", "duygu", "backtest", "kampanya", "airdrop",
            "cüzdan", "cuzdan", "portföy", "portfolio", "wallet", "metamask",
            "son haber", "güncel haber", "guncel haber", "btc analiz", "eth analiz",
            "sol analiz", "sol sentiment", "btc fiyat", "eth fiyat", "chart", "grafik",
        ]
        if any(x in q for x in agent_force):
            return False
        chat_markers = [
            "sence", "ne düşünüyorsun", "ne dusunuyorsun", "düşünüyorsun", "dusunuyorsun",
            "düşünüyor musun", "dusunuyor musun", "ne dersin", "yorumun", "yorum",
            "peki sence", "peki ya", "bence", "mantıklı mı", "mantikli mi", "alınır mı",
            "alinir mi", "satılır mı", "satilir mi", "riskli mi", "neler söylersin",
            "neler soyler", "açıkla", "acikla", "özetle", "ozetle", "kripto nedir",
            "bitcoin nedir", "defi nedir", "blockchain nedir", "nasıl çalışır", "nasil calisir",
            "merhaba", "selam", "teşekkür", "tesekkur", "what do you think", "do you think",
            "should i buy", "should i sell", "in your opinion", "your thoughts",
            "ne anlama geliyor", "ne demek", "what does this mean", "what is", "nedir",
            "explain", "peki bu", "anlamı ne", "comment on",
        ]
        return any(x in q for x in chat_markers)

    async def _run_chat_mode(
        self,
        query: str,
        reasoning_log: ReasoningLog,
        *,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        last_agent_context: Optional[str] = None,
        locale_lang: Optional[str] = None,
        wallet_context: Optional[str] = None,
    ) -> str:
        reasoning_log.add_decision(
            agent_name=self.name,
            decision="Sohbet modu",
            reasoning="Serbest sohbet (ücretsiz: Groq → Ollama → Gemini; son 10 mesaj + ajan özeti)",
            duration_ms=0,
        )
        if conversation_history is not None:
            prior = [
                {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
                for m in conversation_history
                if isinstance(m, dict)
                and m.get("role") in ("user", "assistant")
                and (m.get("content") or "").strip()
            ]
        else:
            prior = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in (self.context_history[:-1] if self.context_history else [])
                if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
            ]

        lc = (last_agent_context or "").strip()
        if lc:
            prior = list(prior) + [
                {"role": "assistant", "content": f"Agent analysis result: {lc[:12000]}"}
            ]

        system = _build_free_chat_system_prompt(
            self._last_agent_memory or None,
            last_agent_context,
            ui_locale=locale_lang,
            wallet_context=wallet_context,
        )
        chat_messages = _normalize_chat_messages(prior, query, max_messages=10)

        text = await self._free_llm_chat_completion(chat_messages, system, max_tokens=1500)
        if text:
            return text

        lang = resolve_lang(locale_lang, query)
        return tx(lang, "chat_mode_llm_unavailable_full")

    async def _summarize_agent_response_if_needed(
        self, user_query: str, raw: str, *, locale_lang: Optional[str] = None
    ) -> Optional[str]:
        """Uzun ajan çıktısını ücretsiz LLM ile sade metne indirger; kısa metinde dokunmaz."""
        text = (raw or "").strip()
        if len(text) < 500:
            return None
        clipped = text[:28000]
        user_block = (
            f"User message / question:\n{user_query.strip()}\n\n"
            f"---\nAgent analysis results to summarize:\n{clipped}\n\n"
            "---\nSummarize these results for the user in plain, friendly prose."
        )
        lc = (locale_lang or "").strip().lower()
        if lc.startswith("tr"):
            user_block += (
                "\n\nUygulama arayüzü Türkçe: özetin tamamını Türkçe yazın; "
                "özgün analiz metni İngilizce olsa bile çıktı Türkçe olsun."
            )
            sys_prompt = (
                AGENT_SUMMARY_SYSTEM
                + "\n\nUI locale Turkish: produce the entire summary in Turkish only."
            )
        elif lc.startswith("en"):
            user_block += (
                "\n\nThe application UI is set to English: write the entire summary in English only, "
                "even if the original analysis text contained Turkish."
            )
            sys_prompt = (
                AGENT_SUMMARY_SYSTEM
                + "\n\nUI locale is English: produce the full summary in English only."
            )
        else:
            sys_prompt = (
                AGENT_SUMMARY_SYSTEM
                + "\n\nDetect the user's message language and summarize in that language."
            )
        messages: List[Dict[str, str]] = [{"role": "user", "content": user_block}]
        try:
            out = await self._free_llm_chat_completion(
                messages, sys_prompt, max_tokens=2500
            )
            out = (out or "").strip()
            return out if len(out) > 80 else None
        except Exception as e:
            self.log(f"Ajan yanıtı özetlenemedi, ham metin kullanılıyor: {e}", "WARNING")
            return None

    def _remember_analysis_snapshot(
        self,
        symbol: str,
        ta: Optional[Dict[str, Any]],
        extra: Optional[str] = None,
        lang: str = "en",
    ) -> None:
        if not ta:
            self._last_agent_memory = (extra or tx(lang, "mem_limited", symbol=symbol))[:1500]
            return
        parts: List[str] = [symbol]
        rsi = ta.get("rsi")
        if rsi is not None:
            try:
                parts.append(f"RSI ~{float(rsi):.1f}")
            except (TypeError, ValueError):
                parts.append(f"RSI: {rsi}")
        macd = ta.get("macd")
        if isinstance(macd, dict):
            m = macd.get("macd") or 0
            s = macd.get("signal") or 0
            parts.append(tx(lang, "mem_macd_bull") if m > s else tx(lang, "mem_macd_bear"))
        sigs = ta.get("signals")
        if isinstance(sigs, list) and sigs:
            parts.append(tx(lang, "mem_signals") + ": " + ", ".join(str(x) for x in sigs[:4]))
        if extra:
            parts.append(extra)
        self._last_agent_memory = " | ".join(parts)[:1500]
    
    def _extract_symbol(self, query: str) -> Optional[str]:
        """Sorgudan bilinen coin bazını çıkarır; genel büyük harf kelimeleri (ANALYZE vb.) asla sembol saymaz."""
        if not (query or "").strip():
            return None
        qu = query.strip()

        m = _KNOWN_PAIR_RE.search(qu)
        if m:
            base = m.group(1).upper()
            quote = m.group(2).upper()
            if base in KNOWN_BASE_SYMBOLS and quote in QUOTE_CURRENCIES:
                return f"{base}/{quote}"

        qu_upper = qu.upper()
        for sym in sorted(KNOWN_BASE_SYMBOLS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(sym)}\b", qu_upper):
                return f"{sym}/USDT"

        q_lower = qu.lower()
        for phrase, sym in sorted(_CRYPTO_NAME_ALIASES.items(), key=lambda x: -len(x[0])):
            if re.search(rf"\b{re.escape(phrase)}\b", q_lower):
                return f"{sym}/USDT"

        return None

    def _coerce_valid_symbol(self, raw: Optional[str], query: str) -> Optional[str]:
        """Intent'ten gelen sembolü doğrular; geçersizse (ANALYZE vb.) sorgudan yeniden çıkarım."""
        extracted = self._extract_symbol(query)
        if not raw or not str(raw).strip():
            return extracted
        s = str(raw).strip().upper()
        if "/" in s:
            base, _, quote = s.partition("/")
            base, quote = base.strip(), quote.strip()
            if base in _NON_SYMBOL_WORDS or base not in KNOWN_BASE_SYMBOLS:
                return extracted
            if quote and quote not in QUOTE_CURRENCIES:
                return extracted
            return f"{base}/{quote}" if quote else f"{base}/USDT"
        if s in _NON_SYMBOL_WORDS:
            return extracted
        if s in KNOWN_BASE_SYMBOLS:
            return f"{s}/USDT"
        return extracted

    def _sanitize_intent_symbols(self, intent: Dict[str, Any], query: str) -> Dict[str, Any]:
        """LLM veya hatalı routing'in ürettiği geçersiz sembolleri düzeltir; sembol yoksa veri aksiyonunu sohbete çevirir."""
        out = dict(intent)
        coerced = self._coerce_valid_symbol(out.get("symbol"), query)
        if coerced:
            out["symbol"] = coerced
        else:
            out.pop("symbol", None)

        act = out.get("action")
        if act in ACTIONS_REQUIRING_RESOLVED_SYMBOL and not out.get("symbol"):
            out["action"] = "general"
        return out
    
    async def execute(
        self,
        query: str,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        wallet_address: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        last_agent_context: Optional[str] = None,
        wallet_context: Optional[str] = None,
        locale: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Process user query and generate response"""
        # Initialize reasoning log
        reasoning_log = ReasoningLog()
        start_time = time.time()
        lang = resolve_lang(locale, query)

        try:
            # Add to context
            self.context_history.append({"role": "user", "content": query})
            
            reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.DATA_FETCH,
                description="Kullanıcı sorgusu alındı",
                data={"query": query}
            )
            
            # Use LLM to determine intent and required actions
            intent_start = time.time()
            if llm_service.is_available():
                intent = await llm_service.determine_intent(query, self.context_history)
            else:
                # Fallback to rule-based intent detection
                intent = self._determine_intent_fallback(query)
            intent = self._sanitize_intent_symbols(intent, query)
            intent_duration = (time.time() - intent_start) * 1000
            
            reasoning_log.add_decision(
                agent_name=self.name,
                decision=f"Intent belirlendi: {intent.get('action')}",
                reasoning=f"Kullanıcı sorgusundan '{intent.get('action')}' aksiyonu çıkarıldı",
                duration_ms=intent_duration
            )

            if intent.get("action") == "campaigns" and not intent.get("campaign_filter"):
                intent["campaign_filter"] = self._campaign_filter_from_query(query)
            if intent.get("action") == "wallet" and not intent.get("wallet_mode"):
                intent["wallet_mode"] = self._wallet_mode_from_query(query)
            
            # Set reasoning log for all agents
            self.data_agent.set_reasoning_log(reasoning_log)
            self.analysis_agent.set_reasoning_log(reasoning_log)
            self.sentiment_agent.set_reasoning_log(reasoning_log)
            self.prediction_agent.set_reasoning_log(reasoning_log)
            self.risk_agent.set_reasoning_log(reasoning_log)
            self.backtest_agent.set_reasoning_log(reasoning_log)
            self.campaign_agent.set_reasoning_log(reasoning_log)
            self.wallet_agent.set_reasoning_log(reasoning_log)
            
            # Execute based on intent
            agent_result = None
            response_text = ""
            response_agent_name = self.name

            hist_cached = await try_answer_long_horizon_query(query)
            if hist_cached:
                reasoning_log.add_analysis(
                    agent_name=self.name,
                    analysis_type="historical_return",
                    description="Uzun vadeli spot: günlük OHLCV ile yaklaşık getiri",
                    result={"exchange": "binance", "timeframe": "1d"},
                )

            response_mode = "agent"
            if hist_cached:
                response_text = hist_cached
            elif self._route_to_chat_mode(query, intent):
                response_text = await self._run_chat_mode(
                    query,
                    reasoning_log,
                    conversation_history=conversation_history,
                    last_agent_context=last_agent_context,
                    locale_lang=lang,
                    wallet_context=wallet_context,
                )
                response_mode = "chat"
            elif intent.get("action") == "fetch_price":
                symbol = intent.get("symbol") or self._extract_symbol(query)
                if symbol:
                    agent_result = await self.data_agent.execute(symbol=symbol)
                    if agent_result.get("success"):
                        data = agent_result.get("data")
                        price = data.get("price", 0)
                        if isinstance(price, str):
                            try:
                                price = float(price)
                            except (TypeError, ValueError):
                                price = 0
                        response_text = tx(
                            lang,
                            "price_line",
                            symbol=symbol,
                            price=f"{price:,.2f}",
                            ch=f"{data.get('change_24h', 0):.2f}",
                            vol=f"{data.get('volume_24h', 0):,.0f}",
                        )
            
            elif intent.get("action") == "analyze":
                symbol = intent.get("symbol") or self._extract_symbol(query)
                if not symbol:
                    # Try to extract from query
                    query_lower = query.lower()
                    if "btc" in query_lower or "bitcoin" in query_lower:
                        symbol = "BTC/USDT"
                    elif "eth" in query_lower or "ethereum" in query_lower:
                        symbol = "ETH/USDT"
                    else:
                        symbol = "BTC/USDT"  # Default
                
                if symbol:
                    # Get technical analysis
                    agent_result = await self.analysis_agent.execute(
                        symbol=symbol,
                        include_sentiment=False  # Don't include sentiment in simple analyze
                    )
                    if agent_result.get("success"):
                        ta = agent_result.get("technical_analysis", {})
                        current_data = agent_result.get("current_data", {})
                        llm_analysis = agent_result.get("llm_analysis", {})
                        
                        response_text = tx(lang, "analyze_title", symbol=symbol)
                        response_text += "=" * 50 + "\n\n"
                        
                        # Current Price Info
                        if current_data:
                            response_text += tx(lang, "current_price_info")
                            response_text += f"{tx(lang, 'price_lbl')}: ${current_data.get('price', 0):,.2f}\n"
                            response_text += f"{tx(lang, 'high24')}: ${current_data.get('high_24h', 0):,.2f}\n"
                            response_text += f"{tx(lang, 'low24')}: ${current_data.get('low_24h', 0):,.2f}\n"
                            response_text += f"{tx(lang, 'ch24')}: {current_data.get('change_24h', 0):.2f}%\n"
                            response_text += f"{tx(lang, 'vol24')}: ${current_data.get('volume_24h', 0):,.0f}\n\n"
                        
                        # Technical Indicators
                        response_text += tx(lang, "tech_indicators")
                        
                        if ta.get("rsi"):
                            rsi = ta['rsi']
                            rsi_status = rsi_status_label(lang, rsi)
                            response_text += f"   RSI (14): {rsi:.2f} - {rsi_status}\n"
                        
                        if ta.get("macd"):
                            macd = ta['macd']
                            response_text += f"{tx(lang, 'macd_hdr')}: {macd.get('macd', 0):.4f}\n"
                            response_text += f"{tx(lang, 'signal_lbl')}: {macd.get('signal', 0):.4f}\n"
                            response_text += f"{tx(lang, 'hist_lbl')}: {macd.get('histogram', 0):.4f}\n"
                            macd_trend = tx(lang, "macd_up") if (macd.get('macd', 0) > macd.get('signal', 0)) else tx(lang, "macd_down")
                            response_text += f"   Trend: {macd_trend}\n"
                        
                        if ta.get("bollinger_bands"):
                            bb = ta['bollinger_bands']
                            current_price = ta.get('current_price', 0)
                            response_text += tx(lang, "bb_hdr")
                            response_text += f"     {tx(lang, 'bb_upper')}: ${bb.get('upper', 0):,.2f}\n"
                            response_text += f"     {tx(lang, 'bb_mid')}: ${bb.get('middle', 0):,.2f}\n"
                            response_text += f"     {tx(lang, 'bb_lower')}: ${bb.get('lower', 0):,.2f}\n"
                            if current_price > bb.get('upper', 0):
                                response_text += f"     {tx(lang, 'status_lbl')}: {tx(lang, 'bb_above')}\n"
                            elif current_price < bb.get('lower', 0):
                                response_text += f"     {tx(lang, 'status_lbl')}: {tx(lang, 'bb_below')}\n"
                            else:
                                response_text += f"     {tx(lang, 'status_lbl')}: {tx(lang, 'bb_normal')}\n"
                        
                        if ta.get("sma_20"):
                            response_text += f"{tx(lang, 'sma20')}: ${ta['sma_20']:,.2f}\n"
                        if ta.get("sma_50"):
                            response_text += f"{tx(lang, 'sma50')}: ${ta['sma_50']:,.2f}\n"
                        if ta.get("ema_12"):
                            response_text += f"{tx(lang, 'ema12')}: ${ta['ema_12']:,.2f}\n"
                        
                        # Trading Signals
                        if ta.get("signals"):
                            response_text += tx(lang, "trade_sig_hdr")
                            for signal in ta['signals']:
                                response_text += f"   • {signal}\n"
                        
                        # LLM Analysis
                        if llm_analysis.get("analysis"):
                            response_text += tx(lang, "ai_summary")
                            response_text += f"   {llm_analysis['analysis']}\n"
                        
                        # Price Change
                        if ta.get("price_change_24h"):
                            response_text += tx(lang, "chg24h", p=ta['price_change_24h'])
                        
                        self._remember_analysis_snapshot(symbol, ta, lang=lang)
                        agent_result = agent_result
                    else:
                        # If analysis failed, provide error message
                        response_text = tx(lang, "analysis_failed", symbol=symbol)
                        agent_result = {
                            "success": False,
                            "error": "Analysis failed"
                        }
            
            elif intent.get("action") == "comprehensive_analyze":
                symbol = intent.get("symbol") or self._extract_symbol(query)
                
                # If no symbol found, try to extract from context
                if not symbol and self.context_history:
                    for msg in reversed(self.context_history[-5:]):  # Check last 5 messages
                        if msg.get("role") == "user":
                            extracted = self._extract_symbol(msg.get("content", ""))
                            if extracted:
                                symbol = extracted
                                break
                
                # If still no symbol, use default or ask user
                initial_response_text = ""
                if not symbol:
                    # Try common symbols from query
                    query_lower = query.lower()
                    if "btc" in query_lower or "bitcoin" in query_lower:
                        symbol = "BTC/USDT"
                    elif "eth" in query_lower or "ethereum" in query_lower:
                        symbol = "ETH/USDT"
                    elif "sol" in query_lower or "solana" in query_lower:
                        symbol = "SOL/USDT"
                    else:
                        # Default to BTC if no symbol found
                        symbol = "BTC/USDT"
                        initial_response_text = tx(lang, "symbol_default_btc")
                
                if symbol:
                    RW = risk_warnings_for_comprehensive(lang)
                    # Comprehensive analysis: Technical + Sentiment + Prediction + Risk
                    response_text = initial_response_text + tx(lang, "comprehensive_title", symbol=symbol)
                    response_text += "=" * 50 + "\n\n"
                    
                    # Collect all sources
                    all_sources = []
                    
                    # 1. Technical Analysis (Piyasa Analisti)
                    reasoning_log.add_coordination(
                        from_agent=self.name,
                        to_agent="AnalysisAgent",
                        message=f"{symbol} için teknik analiz başlatılıyor"
                    )
                    ta_start = time.time()
                    ta_result = await self.analysis_agent.execute(symbol=symbol, include_sentiment=False)
                    ta_duration = (time.time() - ta_start) * 1000
                    reasoning_log.add_analysis(
                        agent_name="AnalysisAgent",
                        analysis_type="Teknik Analiz",
                        description=f"RSI, MACD, Bollinger Bands hesaplandı",
                        duration_ms=ta_duration
                    )
                    if ta_result.get("success"):
                        ta = ta_result.get("technical_analysis", {})
                        current_data = ta_result.get("current_data", {})
                        
                        response_text += tx(lang, "section1_ta")
                        response_text += "-" * 30 + "\n"
                        if current_data:
                            response_text += f"{tx(lang, 'current_price_short')}: ${current_data.get('price', 0):,.2f}\n"
                            response_text += f"{tx(lang, 'change_24h')}: {current_data.get('change_24h', 0):.2f}%\n"
                        if ta.get("rsi"):
                            rsi = ta['rsi']
                            rsi_status = rsi_status_label(lang, rsi)
                            response_text += tx(lang, "rsi_line", rsi=rsi, status=rsi_status) + "\n"
                        if ta.get("macd"):
                            macd = ta['macd']
                            mt = tx(lang, "macd_up") if (macd.get('macd', 0) > macd.get('signal', 0)) else tx(lang, "macd_down")
                            response_text += tx(
                                lang,
                                "macd_line",
                                m=macd.get('macd', 0),
                                s=macd.get('signal', 0),
                                trend=mt,
                            )
                        if ta.get("signals"):
                            response_text += f"{tx(lang, 'trade_signals')}: {', '.join(ta['signals'])}\n"
                        response_text += "\n"
                    
                    # 2. Sentiment Analysis (Haber-Sentiment Uzmanı)
                    reasoning_log.add_coordination(
                        from_agent=self.name,
                        to_agent="SentimentAgent",
                        message=f"{symbol} için sentiment analizi başlatılıyor"
                    )
                    sentiment_start = time.time()
                    sentiment_result = await self.sentiment_agent.execute(
                        symbol=symbol.split("/")[0] if "/" in symbol else symbol,
                        include_news=True,
                        include_reddit=True,
                        hours=24
                    )
                    sentiment_duration = (time.time() - sentiment_start) * 1000
                    if sentiment_result.get("success"):
                        reasoning_log.add_analysis(
                            agent_name="SentimentAgent",
                            analysis_type="Sentiment Analizi",
                            description=f"Haberlere ve Reddit'e bakıldı, genel sentiment: {sentiment_result.get('overall_sentiment', {}).get('sentiment', 'neutral')}",
                            duration_ms=sentiment_duration
                        )
                    if sentiment_result.get("success"):
                        overall = sentiment_result.get("overall_sentiment", {})
                        response_text += tx(lang, "section2_sent")
                        response_text += "-" * 30 + "\n"
                        response_text += f"{tx(lang, 'overall_sentiment')}: {overall.get('sentiment', 'neutral').upper()}\n"
                        response_text += f"{tx(lang, 'score')}: {overall.get('score', 0):.4f}\n"
                        response_text += f"{tx(lang, 'confidence')}: {overall.get('confidence', 0):.2%}\n"
                        response_text += f"{tx(lang, 'sample_size')}: {overall.get('sample_size', 0)}\n"
                        if sentiment_result.get("sources"):
                            sources_count = len(sentiment_result.get('sources', []))
                            response_text += tx(lang, "source_count", n=sources_count)
                            all_sources.extend(sentiment_result.get('sources', []))
                        response_text += "\n"
                    
                    # 3. Price Prediction (Tahminci)
                    reasoning_log.add_coordination(
                        from_agent=self.name,
                        to_agent="PredictionAgent",
                        message=f"{symbol} için 7 günlük fiyat tahmini başlatılıyor"
                    )
                    prediction_start = time.time()
                    prediction_result = await self.prediction_agent.execute(
                        symbol=symbol,
                        periods=7,
                        model="ensemble"
                    )
                    prediction_duration = (time.time() - prediction_start) * 1000
                    if prediction_result.get("success"):
                        pred_change = prediction_result.get("predicted_change", {}).get("percentage", 0)
                        reasoning_log.add_analysis(
                            agent_name="PredictionAgent",
                            analysis_type="Fiyat Tahmini",
                            description=f"7 günlük tahmin: {pred_change:+.2f}% değişim bekleniyor",
                            duration_ms=prediction_duration
                        )
                    if prediction_result.get("success"):
                        predicted_change = prediction_result.get("predicted_change", {})
                        metrics = prediction_result.get("metrics", {})
                        response_text += tx(lang, "section3_pred")
                        response_text += "-" * 30 + "\n"
                        if predicted_change:
                            response_text += tx(lang, "pred_price_line", p=predicted_change.get('last_period_price', 0))
                            response_text += tx(lang, "exp_chg_line", pct=predicted_change.get('percentage', 0))
                        response_text += tx(lang, "model_acc", acc=metrics.get('directional_accuracy', 0))
                        response_text += tx(lang, "mae_line", v=metrics.get('mae', 0))
                        response_text += "\n"
                    
                    # 4. Risk Assessment (Risk Kontrolörü)
                    if current_data and current_data.get('price'):
                        # Basic risk assessment based on technical indicators
                        risk_warnings = []
                        risk_score = 0.0  # 0-100, higher = more risk
                        
                        if ta.get("rsi"):
                            if ta['rsi'] > 70:
                                risk_warnings.append(RW["rsi_high"])
                                risk_score += 30
                            elif ta['rsi'] < 30:
                                risk_warnings.append(RW["rsi_low"])
                                risk_score -= 10
                        
                        if ta.get("bollinger_bands"):
                            bb = ta['bollinger_bands']
                            current_price = current_data.get('price', 0)
                            if current_price > bb.get('upper', 0):
                                risk_warnings.append(RW["bb_high"])
                                risk_score += 20
                            elif current_price < bb.get('lower', 0):
                                risk_warnings.append(RW["bb_low"])
                                risk_score -= 5
                        
                        if sentiment_result.get("success"):
                            sentiment_score = sentiment_result.get("overall_sentiment", {}).get("score", 0)
                            if sentiment_score < -0.3:
                                risk_warnings.append(RW["sent_neg"])
                                risk_score += 25
                        
                        if prediction_result.get("success"):
                            pred_change = prediction_result.get("predicted_change", {}).get("percentage", 0)
                            if pred_change < -5:
                                risk_warnings.append(RW["pred_down"])
                                risk_score += 20
                        
                        response_text += tx(lang, "section4_risk")
                        response_text += "-" * 30 + "\n"
                        response_text += f"{tx(lang, 'risk_score')}: {min(100, max(0, risk_score)):.1f}/100\n"
                        if risk_warnings:
                            response_text += f"{tx(lang, 'warnings')}:\n"
                            for warning in risk_warnings:
                                response_text += f"  • {warning}\n"
                        else:
                            response_text += tx(lang, "no_major_risk")
                        response_text += "\n"
                    
                    # 5. Consensus Voting (Ajanlar Arası Oylama)
                    reasoning_log.add_coordination(
                        from_agent=self.name,
                        to_agent="ConsensusAgent",
                        message="Ajanlar arası konsensüs için oylama başlatılıyor"
                    )
                    consensus_start = time.time()
                    consensus_result = await self.consensus_agent.get_agent_votes(symbol, reasoning_log)
                    consensus_duration = (time.time() - consensus_start) * 1000
                    
                    response_text += tx(lang, "section5_vote")
                    response_text += "-" * 30 + "\n"
                    
                    for agent_name, vote_data in consensus_result.get("votes", {}).items():
                        vote_icon = "✅" if vote_data["vote"] == "BUY" else "❌" if vote_data["vote"] == "SELL" else "⏸️"
                        response_text += tx(
                            lang,
                            "vote_line",
                            icon=vote_icon,
                            agent=agent_name,
                            vote=vote_data["vote"],
                            conf=vote_data["confidence"] * 100,
                        )
                        response_text += f"   {vote_data['reasoning']}\n"
                    
                    response_text += f"\n📊 {tx(lang, 'consensus')}: {consensus_result.get('consensus', 'HOLD')}\n"
                    response_text += f"   {tx(lang, 'confidence_pct')}: {consensus_result.get('consensus_confidence', 0)*100:.0f}%\n"
                    
                    if consensus_result.get("disagreement"):
                        response_text += tx(lang, "disagreement_title")
                        response_text += tx(lang, "disagreement_body")
                        for reason in consensus_result.get("disagreement_reasons", [])[:3]:
                            response_text += f"   • {reason}\n"
                    else:
                        response_text += tx(lang, "majority_ok")
                        response_text += tx(lang, "majority_body")
                    
                    response_text += "\n"
                    
                    # 6. Trading Recommendation (Portföy Yöneticisi önerisi)
                    response_text += tx(lang, "section6_trade")
                    response_text += "-" * 30 + "\n"
                    
                    # Use consensus result for recommendation
                    reasoning_log.add_coordination(
                        from_agent=self.name,
                        to_agent="RiskAgent",
                        message="Konsensüs sonucuna göre trading önerisi oluşturuluyor"
                    )
                    
                    # Get user profile if available
                    user = None
                    if db and user_id:
                        user = db.query(User).filter(User.id == user_id).first()
                    
                    # Calculate confidence score from prediction metrics
                    confidence_score = 0.5  # Default
                    if prediction_result.get("success"):
                        metrics = prediction_result.get("metrics", {})
                        directional_acc = metrics.get("directional_accuracy", 0) / 100.0
                        mape = metrics.get("mape", 0) / 100.0
                        # Combine metrics for confidence
                        confidence_score = (directional_acc * 0.7) + ((1 - min(mape, 0.5)) * 0.3)
                    
                    # Get sentiment score
                    sentiment_score = 0.0
                    if sentiment_result.get("success"):
                        sentiment_score = sentiment_result.get("overall_sentiment", {}).get("score", 0)
                    
                    # Get prediction change
                    pred_change = 0.0
                    if prediction_result.get("success"):
                        pred_change = prediction_result.get("predicted_change", {}).get("percentage", 0)
                    
                    # Use consensus result for recommendation
                    consensus_vote = consensus_result.get("consensus", "HOLD")
                    if consensus_vote == "BUY":
                        recommendation = "AL"
                    elif consensus_vote == "SELL":
                        recommendation = "SAT"
                    else:
                        recommendation = "NÖTR"
                    
                    recommendation_reason = []
                    
                    # Add consensus info to reasoning
                    if consensus_result.get("disagreement"):
                        recommendation_reason.append(tx(lang, "recommend_disagree"))
                    else:
                        vote_count = len([v for v in consensus_result.get("votes", {}).values() if v["vote"] == consensus_vote])
                        total_votes = len(consensus_result.get("votes", {}))
                        recommendation_reason.append(
                            tx(
                                lang,
                                "recommend_consensus",
                                vote_count=vote_count,
                                total_votes=total_votes,
                                vote=consensus_vote,
                            )
                        )
                    
                    # Use user profile service if user exists
                    if user:
                        profile_recommendation = user_profile_service.should_recommend_trade(
                            user=user,
                            confidence_score=consensus_result.get("consensus_confidence", confidence_score),
                            prediction_change=pred_change,
                            sentiment_score=sentiment_score,
                            lang=lang,
                        )
                        
                        # Override with profile recommendation if more conservative
                        if profile_recommendation.get("action") == "NÖTR" and recommendation != "NÖTR":
                            recommendation = "NÖTR"
                            recommendation_reason.append(profile_recommendation.get("reasoning", ""))
                        
                        # Add profile info to response
                        response_text += f"{tx(lang, 'user_profile')}: {user.risk_appetite.value.upper()}\n"
                        response_text += f"   {user_profile_service.get_profile_description(user.risk_appetite, lang=lang)}\n"
                        response_text += tx(
                            lang,
                            "conf_score_need",
                            a=consensus_result.get('consensus_confidence', 0) * 100,
                            b=user_profile_service.get_confidence_threshold(user) * 100,
                        )
                    
                    if ta_result.get("success") and ta.get("signals"):
                        signals = ta['signals']
                        if any("AL" in s.upper() or "BUY" in s.upper() for s in signals):
                            recommendation = "AL"
                            recommendation_reason.append(tx(lang, "recommend_tech_buy"))
                        elif any("SAT" in s.upper() or "SELL" in s.upper() for s in signals):
                            recommendation = "SAT"
                            recommendation_reason.append(tx(lang, "recommend_tech_sell"))
                    
                    if sentiment_result.get("success"):
                        sentiment = sentiment_result.get("overall_sentiment", {}).get("sentiment", "neutral")
                        if sentiment == "positive":
                            if recommendation == "NÖTR":
                                recommendation = "AL"
                            recommendation_reason.append(tx(lang, "recommend_sent_pos"))
                        elif sentiment == "negative":
                            if recommendation == "AL":
                                recommendation = "NÖTR"
                            recommendation_reason.append(tx(lang, "recommend_sent_neg"))
                    
                    if prediction_result.get("success"):
                        pred_change = prediction_result.get("predicted_change", {}).get("percentage", 0)
                        if pred_change > 5:
                            if recommendation == "NÖTR":
                                recommendation = "AL"
                            recommendation_reason.append(tx(lang, "recommend_pred_rise", pct=pred_change))
                        elif pred_change < -5:
                            if recommendation == "AL":
                                recommendation = "NÖTR"
                            recommendation_reason.append(tx(lang, "recommend_pred_drop", pct=pred_change))
                    
                    response_text += tx(lang, "rec_line", rec=recommendation_label(lang, recommendation))
                    if recommendation_reason:
                        response_text += tx(lang, "rec_reason", txt=", ".join(recommendation_reason))
                    response_text += "\n"
                    response_text += tx(lang, "not_advice")
                    
                    # Final decision
                    reasoning_log.add_decision(
                        agent_name=self.name,
                        decision=tx(
                            lang,
                            "final_rec_prefix",
                            rec=recommendation_label(lang, recommendation),
                        ),
                        reasoning=", ".join(recommendation_reason)
                        if recommendation_reason
                        else tx(lang, "final_rec_reason_default"),
                    )

                    if ta_result.get("success"):
                        ta_mem = ta_result.get("technical_analysis", {}) or {}
                        cons = consensus_result.get("consensus", "HOLD")
                        self._remember_analysis_snapshot(
                            symbol,
                            ta_mem,
                            extra=tx(lang, "mem_consensus", cons=cons),
                            lang=lang,
                        )
                    
                    # Combine all results with sources
                    agent_result = {
                        "technical": ta_result,
                        "sentiment": sentiment_result,
                        "prediction": prediction_result,
                        "risk": {
                            "risk_score": min(100, max(0, risk_score)),
                            "warnings": risk_warnings
                        },
                        "consensus": consensus_result,  # Add consensus data
                        "recommendation": {
                            "action": recommendation,
                            "reasons": recommendation_reason
                        },
                        "sources": all_sources[:10]  # Top 10 sources
                    }
            
            elif intent.get("action") == "fetch_news":
                # Son haberler veya coin haberleri (Node News API)
                coin = intent.get("symbol") or self._extract_symbol(query)
                coin_str = (coin.split("/")[0] if coin and "/" in coin else coin) if coin else None
                from app.services.node_news_client import fetch_latest_news
                news_result = fetch_latest_news(coin=coin_str, limit=5)
                if news_result.get("success") and news_result.get("items"):
                    items = news_result["items"]
                    label = f"{coin_str} " if coin_str else ""
                    response_text = tx(lang, "news_latest", label=label)
                    for i, item in enumerate(items, 1):
                        title = (item.get("title") or tx(lang, "untitled"))[:80]
                        if len(item.get("title") or "") > 80:
                            title += "..."
                        response_text += f"{i}. {title}\n"
                        response_text += f"   {item.get('source', 'N/A')} · {item.get('url', '')}\n"
                        if item.get("sentiment"):
                            response_text += tx(lang, "sentiment_line", s=item.get("sentiment"))
                        response_text += "\n"
                    pos = sum(1 for x in items if x.get("sentiment") == "POSITIVE")
                    neg = sum(1 for x in items if x.get("sentiment") == "NEGATIVE")
                    neu = len(items) - pos - neg
                    total = len(items)
                    response_text += tx(lang, "summary_prefix")
                    if total > 0:
                        parts = []
                        if pos:
                            parts.append(tx(lang, "news_sent_pos", pct=int(pos / total * 100)))
                        if neu:
                            parts.append(tx(lang, "news_sent_neu", pct=int(neu / total * 100)))
                        if neg:
                            parts.append(tx(lang, "news_sent_neg", pct=int(neg / total * 100)))
                        response_text += ", ".join(parts) + ".\n"
                    else:
                        response_text += tx(lang, "no_data")
                    response_text += tx(lang, "news_footer")
                    agent_result = {"success": True, "news_count": len(items), "sources": [x.get("url") for x in items]}
                else:
                    err = news_result.get("error") or (
                        "News unavailable." if lang == "en" else "Haberler alınamadı."
                    )
                    response_text = tx(lang, "news_fail", err=err)
                    agent_result = {"success": False, "error": err}

            elif intent.get("action") == "campaigns":
                cf = intent.get("campaign_filter") or self._campaign_filter_from_query(query)
                reasoning_log.add_coordination(
                    from_agent=self.name,
                    to_agent="CampaignAgent",
                    message=f"Kampanya listesi isteniyor (filtre: {cf})",
                )
                camp_start = time.time()
                agent_result = await self.campaign_agent.execute(campaign_filter=cf)
                camp_duration = (time.time() - camp_start) * 1000
                reasoning_log.add_analysis(
                    agent_name="CampaignAgent",
                    analysis_type="Kampanyalar",
                    description="Node /api/campaigns yanıtı işlendi",
                    duration_ms=camp_duration,
                )
                response_text = agent_result.get("narrative") or tx(lang, "campaign_fail")
                response_agent_name = "CampaignAgent"

            elif intent.get("action") == "wallet":
                wm = intent.get("wallet_mode") or self._wallet_mode_from_query(query)
                reasoning_log.add_coordination(
                    from_agent=self.name,
                    to_agent="WalletAgent",
                    message=f"Cüzdan sorgusu (mod: {wm})",
                )
                w_start = time.time()
                agent_result = await self.wallet_agent.execute(
                    wallet_address=wallet_address,
                    wallet_mode=wm,
                    locale=lang,
                    wallet_context=wallet_context,
                )
                w_duration = (time.time() - w_start) * 1000
                reasoning_log.add_analysis(
                    agent_name="WalletAgent",
                    analysis_type="Cüzdan",
                    description="Node /api/wallet verisi işlendi",
                    duration_ms=w_duration,
                )
                response_text = agent_result.get("narrative") or tx(lang, "wallet_fail")
                response_agent_name = "WalletAgent"

            elif intent.get("action") == "sentiment":
                symbol = intent.get("symbol") or self._extract_symbol(query)
                if symbol:
                    # Get sentiment analysis
                    from sqlalchemy.orm import Session
                    # Note: db session would need to be passed from API endpoint
                    sentiment_result = await self.sentiment_agent.execute(
                        symbol=symbol,
                        include_news=True,
                        include_reddit=True,
                        hours=24
                    )
                    if sentiment_result.get("success"):
                        overall = sentiment_result.get("overall_sentiment", {})
                        sources = sentiment_result.get("sources", [])
                        
                        response_text = tx(lang, "sentiment_title", symbol=symbol)
                        response_text += f"{tx(lang, 'overall_sentiment')}: {overall.get('sentiment', 'neutral').upper()}\n"
                        response_text += f"{tx(lang, 'score')}: {overall.get('score', 0):.2f}\n"
                        response_text += f"{tx(lang, 'confidence')}: {overall.get('confidence', 0):.2%}\n"
                        response_text += f"{tx(lang, 'sample_size')}: {overall.get('sample_size', 0)}\n"
                        
                        if sources:
                            response_text += tx(lang, "sources_n", n=len(sources))
                            for i, source in enumerate(sources[:5], 1):  # Show first 5
                                response_text += f"{i}. {source.get('title', 'N/A')[:50]}...\n"
                                response_text += f"   {source.get('url', '')}\n"
                        
                        agent_result = sentiment_result
            
            elif intent.get("action") == "predict":
                symbol = intent.get("symbol") or self._extract_symbol(query)
                if symbol:
                    # Get prediction
                    prediction_result = await self.prediction_agent.execute(
                        symbol=symbol,
                        periods=7,
                        model="ensemble"
                    )
                    if prediction_result.get("success"):
                        predictions = prediction_result.get("predictions", [])
                        metrics = prediction_result.get("metrics", {})
                        predicted_change = prediction_result.get("predicted_change", {})
                        current_price = prediction_result.get("current_price", 0)
                        
                        response_text = tx(lang, "pred_title", symbol=symbol)
                        response_text += f"{tx(lang, 'current_price')}: ${current_price:,.2f}\n\n"
                        
                        if predicted_change:
                            change_pct = predicted_change.get("percentage", 0)
                            change_abs = predicted_change.get("absolute", 0)
                            last_price = predicted_change.get("last_period_price", 0)
                            
                            response_text += tx(lang, "pred_price_line", p=last_price)
                            response_text += f"{tx(lang, 'expected_change')}: ${change_abs:,.2f} ({change_pct:+.2f}%)\n\n"
                        
                        response_text += f"{tx(lang, 'model_metrics')}:\n"
                        response_text += tx(lang, "mae_line", v=metrics.get("mae", 0))
                        response_text += tx(lang, "mape_line", v=metrics.get("mape", 0))
                        response_text += tx(lang, "dir_acc_line", v=metrics.get("directional_accuracy", 0))
                        response_text += "\n"
                        
                        if predictions:
                            response_text += tx(lang, "first_3_days")
                            for i, pred in enumerate(predictions[:3], 1):
                                date = pred.get("date", "")[:10]  # Just date part
                                price = pred.get("price", 0)
                                response_text += f"{i}. {date}: ${price:,.2f}\n"
                        
                        agent_result = prediction_result

            elif intent.get("action") == "backtest":
                symbol = intent.get("symbol") or self._extract_symbol(query)

                reasoning_log.add_coordination(
                    from_agent=self.name,
                    to_agent="BacktestAgent",
                    message=f"{symbol} için son 90 gün backtest başlatılıyor"
                )

                backtest_start = time.time()
                backtest_result = await self.backtest_agent.execute(
                    symbol=symbol,
                    days=90,
                    window_days=30,
                    models=["prophet", "lgbm", "arima", "ensemble"],
                )
                backtest_duration = (time.time() - backtest_start) * 1000

                if backtest_result.get("success"):
                    analysis = backtest_result.get("analysis", {})
                    best = analysis.get("best_overall") or {}
                    best_model = (best.get("model") or "").lower()
                    best_da = best.get("directionAccuracy")
                    best_mape = best.get("avgMAPE")

                    reasoning_log.add_analysis(
                        agent_name="BacktestAgent",
                        analysis_type="Backtest",
                        description=f"90 gün walk-forward backtest tamamlandı. En iyi model: {best_model or 'N/A'}",
                        duration_ms=backtest_duration
                    )

                    # Human-friendly response
                    pretty = {
                        "prophet": "Prophet",
                        "lgbm": "LightGBM",
                        "arima": "ARIMA",
                        "ensemble": "Ensemble"
                    }
                    response_text = tx(lang, "bt_title", symbol=symbol)
                    response_text += "=" * 50 + "\n\n"
                    if best_model:
                        response_text += tx(
                            lang,
                            "bt_best",
                            model=pretty.get(best_model, best_model),
                        )
                        if best_da is not None:
                            response_text += tx(lang, "bt_dir_acc", pct=float(best_da))
                        if best_mape is not None:
                            response_text += tx(lang, "bt_mape", pct=float(best_mape))
                        response_text += "\n"

                    # Add regime insights (trend up/down)
                    response_text += backtest_result.get("narrative", "")

                    agent_result = backtest_result
                else:
                    err = backtest_result.get("error") or (
                        "Unknown error" if lang == "en" else "Bilinmeyen hata"
                    )
                    response_text = tx(lang, "bt_fail", err=err)
                    agent_result = backtest_result
            
            elif intent.get("action") == "portfolio_status":
                # Portfolio durumu sorgulama
                if db and user_id:
                    from app.models.portfolio import Portfolio, Position
                    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
                    
                    if portfolio:
                        positions = db.query(Position).filter(Position.portfolio_id == portfolio.id).all()
                        
                        response_text = tx(lang, "ps_title")
                        response_text += "=" * 50 + "\n\n"
                        response_text += tx(lang, "ps_portfolio", name=portfolio.name)
                        response_text += tx(lang, "ps_initial", v=portfolio.initial_balance)
                        response_text += tx(lang, "ps_current", v=portfolio.current_balance)
                        
                        # Calculate total position value
                        total_position_value = 0
                        for position in positions:
                            ticker = await self.data_agent.execute(symbol=position.symbol)
                            if ticker.get("success"):
                                current_price = ticker.get("data", {}).get("price", 0)
                                position_value = position.quantity * current_price
                                total_position_value += position_value
                        
                        total_value = portfolio.current_balance + total_position_value
                        portfolio_change = ((total_value - portfolio.initial_balance) / portfolio.initial_balance) * 100
                        
                        response_text += tx(lang, "ps_pos_value", v=total_position_value)
                        response_text += tx(lang, "ps_total_value", v=total_value)
                        response_text += tx(lang, "ps_total_change", pct=portfolio_change)
                        
                        if positions:
                            response_text += tx(lang, "ps_positions", n=len(positions))
                            for position in positions:
                                ticker = await self.data_agent.execute(symbol=position.symbol)
                                if ticker.get("success"):
                                    current_price = ticker.get("data", {}).get("price", 0)
                                    position_value = position.quantity * current_price
                                    unrealized_pnl = (current_price - (position.avg_buy_price or 0)) * position.quantity
                                    unrealized_pnl_pct = ((current_price - (position.avg_buy_price or 0)) / (position.avg_buy_price or 1)) * 100
                                    
                                    response_text += tx(
                                        lang,
                                        "ps_pos_line",
                                        symbol=position.symbol,
                                        qty=position.quantity,
                                        price=current_price,
                                    )
                                    response_text += tx(
                                        lang,
                                        "ps_pl_line",
                                        val=position_value,
                                        pnl=unrealized_pnl,
                                        pnlpct=unrealized_pnl_pct,
                                    )
                        
                        # Risk analysis
                        if db:
                            risk_result = await self.risk_agent.execute(
                                portfolio_id=portfolio.id,
                                db=db
                            )
                            if risk_result.get("success") and risk_result.get("warnings"):
                                response_text += tx(lang, "ps_risk")
                                for warning in risk_result.get("warnings", [])[:3]:
                                    response_text += f"  • {warning.get('message', '')}\n"
                        
                        agent_result = {
                            "portfolio": {
                                "id": portfolio.id,
                                "name": portfolio.name,
                                "initial_balance": portfolio.initial_balance,
                                "current_balance": portfolio.current_balance,
                                "total_value": total_value,
                                "change_percent": portfolio_change
                            },
                            "positions": len(positions)
                        }
                    else:
                        response_text = tx(lang, "ps_none")
                else:
                    response_text = tx(lang, "ps_login")
            
            elif intent.get("action") == "portfolio_trade":
                # Paper trading işlemi önerisi
                symbol = intent.get("symbol") or self._extract_symbol(query)
                trade_type = intent.get("trade_type", "buy")  # buy or sell
                
                if symbol:
                    # Get comprehensive analysis first
                    comprehensive_result = await self.execute(
                        query=tx(lang, "comprehensive_query_inline", symbol=symbol),
                        user_id=user_id,
                        db=db,
                        locale=locale,
                    )
                    
                    if comprehensive_result.get("success"):
                        recommendation = comprehensive_result.get("agent_data", {}).get("recommendation", {})
                        recommendation_action = recommendation.get("action", "NÖTR")
                        
                        response_text = tx(lang, "pt_title", symbol=symbol)
                        response_text += "=" * 50 + "\n\n"
                        rationale_hdr = f"{tx(lang, 'rationale')}:\n"
                        
                        if recommendation_action == "AL":
                            response_text += tx(lang, "pt_buy_hdr")
                            response_text += rationale_hdr
                            for reason in recommendation.get("reasons", []):
                                response_text += f"  • {reason}\n"
                            response_text += "\n" + tx(lang, "pt_sample_trade")
                            response_text += tx(lang, "pt_symbol", symbol=symbol)
                            response_text += tx(lang, "pt_type_buy")
                            response_text += tx(lang, "pt_amount_hint")
                        elif recommendation_action == "SAT":
                            response_text += tx(lang, "pt_sell_hdr")
                            response_text += rationale_hdr
                            for reason in recommendation.get("reasons", []):
                                response_text += f"  • {reason}\n"
                        else:
                            response_text += tx(lang, "pt_neutral_hdr")
                            response_text += rationale_hdr
                            for reason in recommendation.get("reasons", []):
                                response_text += f"  • {reason}\n"
                        
                        response_text += "\n" + tx(lang, "not_advice")
                        response_text += tx(lang, "paper_trading_hint")
                        
                        agent_result = comprehensive_result.get("agent_data", {})
                else:
                    response_text = tx(lang, "pt_need_symbol")
            
            else:
                response_text = await self._run_chat_mode(
                    query,
                    reasoning_log,
                    conversation_history=conversation_history,
                    last_agent_context=last_agent_context,
                    locale_lang=lang,
                    wallet_context=wallet_context,
                )
                response_mode = "chat"

            if not (response_text or "").strip():
                response_text = await self._run_chat_mode(
                    query,
                    reasoning_log,
                    conversation_history=conversation_history,
                    last_agent_context=last_agent_context,
                    locale_lang=lang,
                    wallet_context=wallet_context,
                )
                response_mode = "chat"

            # Ajan modu: ham teknik metni Claude ile sade özet (dil kullanıcıyla uyumlu)
            if response_mode == "agent" and (response_text or "").strip():
                summarized = await self._summarize_agent_response_if_needed(
                    query, response_text, locale_lang=lang
                )
                if summarized:
                    response_text = summarized
            
            # Update context
            self.context_history.append({"role": "assistant", "content": response_text})
            
            # Keep context size manageable
            if len(self.context_history) > 20:
                self.context_history = self.context_history[-10:]
            
            # Prepare agent_data with sources if available
            agent_data_response = agent_result
            if agent_result:
                # Add sources from sentiment if available
                if isinstance(agent_result, dict):
                    if agent_result.get("sources"):
                        agent_data_response["sources"] = agent_result.get("sources", [])
                    # For comprehensive analysis, combine sources
                    if agent_result.get("sentiment") and agent_result["sentiment"].get("sources"):
                        if "sources" not in agent_data_response:
                            agent_data_response["sources"] = []
                        agent_data_response["sources"].extend(agent_result["sentiment"].get("sources", []))
            
            # Finalize reasoning log
            reasoning_data = reasoning_log.finalize()
            
            return {
                "success": True,
                "response": response_text,
                "intent": intent,
                "agent_data": agent_data_response,
                "agent": response_agent_name,
                "reasoning_log": reasoning_data,
                "response_mode": response_mode,
                "language": lang,
            }
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            self.log(f"Error in ChatAgent: {error_msg}", "ERROR")
            self.log(f"Traceback: {traceback_str}", "ERROR")
            
            reasoning_log.add_step(
                agent_name=self.name,
                step_type=ReasoningStepType.WARNING,
                description=f"Hata oluştu: {error_msg}",
                data={"error": error_msg, "traceback": traceback_str}
            )
            reasoning_data = reasoning_log.finalize()

            try:
                intent_safe = intent
            except NameError:
                intent_safe = {"action": "error"}

            fallback_chat = await self._run_chat_mode(
                query,
                reasoning_log,
                conversation_history=conversation_history,
                last_agent_context=last_agent_context,
                locale_lang=lang,
                wallet_context=wallet_context,
            )
            combined = tx(lang, "chat_error_fallback_prefix") + fallback_chat
            self.context_history.append({"role": "assistant", "content": combined})
            if len(self.context_history) > 20:
                self.context_history = self.context_history[-10:]

            return {
                "success": True,
                "error": error_msg,
                "response": combined,
                "intent": intent_safe,
                "agent_data": None,
                "agent": self.name,
                "reasoning_log": reasoning_data,
                "response_mode": "chat",
                "language": lang,
            }

    def _looks_like_wallet_query(self, query_lower: str) -> bool:
        if any(
            w in query_lower
            for w in ["cüzdan", "cuzdan", "metamask", "cüzdanım", "cuzdanim", "cüzdanımda", "cuzdanimda"]
        ):
            return True
        if "wallet" in query_lower and "portföy" not in query_lower and "portfolio" not in query_lower:
            return True
        if any(w in query_lower for w in ["son işlem", "son islem", "işlemlerim", "islem", "transactions"]):
            return True
        if ("kazanç" in query_lower or "kazanc" in query_lower) and any(
            w in query_lower for w in ["bu hafta", "hafta", "cüzdan", "cuzdan", "metamask", "pnl"]
        ):
            return True
        if "eth" in query_lower and any(w in query_lower for w in ["cüzdan", "cuzdan", "metamask", "wallet"]):
            if "portföy" not in query_lower and "portfolio" not in query_lower:
                return True
        if "eth" in query_lower and "bakiye" in query_lower and "portföy" not in query_lower and "portfolio" not in query_lower:
            return True
        return False

    def _looks_like_campaign_query(self, query_lower: str) -> bool:
        return any(
            w in query_lower
            for w in [
                "kampanya",
                "kampanyalar",
                "airdrop",
                "fırsat",
                "fırsatı",
                "firsat",
                "ai içerik",
                "ai icerik",
                "yeni token",
                "listing",
                "listeleme",
                "coinmarketcap",
                "bugün hangi",
                "bugun hangi",
            ]
        )

    def _campaign_filter_from_query(self, query: str) -> str:
        q = query.lower()
        if "bugün" in q or "bugun" in q or "today" in q:
            return "today"
        if "airdrop" in q:
            return "airdrop"
        if "ai içerik" in q or "ai icerik" in q or "ai content" in q:
            return "ai_content"
        if any(x in q for x in ["yeni token", "listing", "listeleme", "coinmarketcap", "çıktı mı", "cikti mi"]):
            return "listing"
        return "all"

    def _wallet_mode_from_query(self, query: str) -> str:
        q = query.lower()
        if any(x in q for x in ["son işlem", "son islem", "işlemlerim", "islem", "transactions", "transaction", "işlemlerimi"]):
            return "transactions"
        if any(x in q for x in ["bu hafta", "hafta", "7 gün", "haftalık", "haftalik"]) and not any(
            x in q for x in ["tahmin", "predict", "forecast", "analiz", "ne olacak"]
        ):
            return "pnl_week"
        if any(x in q for x in ["bu ay", "30 gün", "aylık", "son 30"]):
            return "pnl_month"
        return "balance"
    
    def _determine_intent_fallback(self, query: str) -> Dict[str, Any]:
        """Fallback intent detection without LLM - Improved pattern matching"""
        query_lower = query.lower().strip()
        
        # Extract symbol first
        symbol = self._extract_symbol(query)

        if self._looks_like_wallet_query(query_lower):
            return {"action": "wallet", "wallet_mode": self._wallet_mode_from_query(query)}
        if self._looks_like_campaign_query(query_lower):
            return {"action": "campaigns", "campaign_filter": self._campaign_filter_from_query(query)}

        # Tanım / eğitim — "bitcoin nedir" kapsamlı analize düşmesin
        data_hint = [
            "fiyat", "price", "analiz", "chart", "grafik", "rsi", "macd", "tahmin",
            "sentiment", "haber", "news", "kaç", "ne kadar $",
        ]
        edu_phrases = [
            "nedir", "ne demek", "what is", "what are", "how does", "how do",
            "define ", "tanımı", "açıkla", "acikla", "explain ",
        ]
        if any(p in query_lower for p in edu_phrases) and not any(
            d in query_lower for d in data_hint
        ):
            return {"action": "general"}

        opinion_markers = [
            "sence", "ne dersin", "ne düşünüyorsun", "dusunuyorsun", "düşünüyor musun",
            "dusunuyor musun", "yorumun", "mantıklı mı", "mantikli mi", "what do you think",
            "should i buy", "should i sell", "in your opinion",
        ]
        if any(p in query_lower for p in opinion_markers):
            hard_data = any(
                w in query_lower
                for w in [
                    "fiyat", "analiz yap", "kapsamlı analiz", "kapsamli analiz", "teknik analiz",
                    "backtest", "kampanya", "cüzdan", "cuzdan", "portföy durumu", "portfoy durumu",
                    "haberleri", "rsi", "macd", "tahmin et", "piyasa analizi yap",
                ]
            )
            if not hard_data:
                return {"action": "general"}
        
        # Uzun vadeli / tarihsel getiri veya genel bilgi — kapsamlı ajan zincirini tetikleme
        historical_or_educational = [
            "10 yıl", "10 yılda", "10 yilda", "on yıl", "on yilda", "son 10 yıl", "son 10 yılda", "son 10 yilda",
            "20 yıl", "5 yıl", "yıllık getiri", "yillik getiri", "geçmişte", "gecmiste",
            "tarihsel", "all time", "all-time", "ath", "last decade", "last 10 years",
            "past 10 years", "how much did", "ne kadar arttı", "ne kadar artti",
        ]
        if any(p in query_lower for p in historical_or_educational):
            return {"action": "general"}
        
        # Price queries
        price_keywords = ["fiyat", "price", "ne kadar", "kaç", "değer", "value", "fiyatı", "fiyatı nedir"]
        if any(word in query_lower for word in price_keywords):
            return {"action": "fetch_price", "symbol": symbol}
        
        # Son haberler / coin haberleri -> fetch_news (Node API listesi)
        news_list_keywords = ["son haberler", "son 5 haber", "son haber", "haberleri", "haberlerini", "güncel haber"]
        if any(phrase in query_lower for phrase in news_list_keywords):
            return {"action": "fetch_news", "symbol": symbol}
        if "haber" in query_lower and (symbol or any(c in query_lower for c in ["btc", "eth", "sol", "ada", "xrp", "doge", "bnb"])):
            # "BTC haberleri" benzeri
            return {"action": "fetch_news", "symbol": symbol}
        
        # Sentiment queries (detaylı analiz)
        sentiment_keywords = ["sentiment", "duygu", "sentiment analizi", "duygu analizi", "reddit", "sosyal medya"]
        if any(word in query_lower for word in sentiment_keywords):
            return {"action": "sentiment", "symbol": symbol}
        
        # Prediction queries
        prediction_keywords = ["tahmin", "predict", "forecast", "gelecek", "ne olacak", "tahmin et", "fiyat tahmini"]
        if any(word in query_lower for word in prediction_keywords):
            return {"action": "predict", "symbol": symbol}

        # Backtest / model comparison queries
        backtest_keywords = [
            "backtest", "geriye dönük test", "geri test", "back test",
            "hangi model", "en iyi model", "model daha iyi", "model karşılaştır", "performans karşılaştır"
        ]
        if any(word in query_lower for word in backtest_keywords):
            return {"action": "backtest", "symbol": symbol}
        
        # Comprehensive analysis keywords (check first before simple analysis)
        comprehensive_keywords = ["kapsamlı analiz", "detaylı analiz", "tam analiz", "comprehensive", "full analysis", 
                                 "tüm analiz", "complete analysis", "piyasa analizi yap", "analiz yap"]
        if any(word in query_lower for word in comprehensive_keywords):
            return {"action": "comprehensive_analyze", "symbol": symbol}
        
        # Simple analysis keywords
        analysis_keywords = ["analiz", "analysis", "rsi", "macd", "teknik", "piyasa", "market analysis", "market"]
        if any(word in query_lower for word in analysis_keywords):
            return {"action": "analyze", "symbol": symbol}
        
        # Portfolio queries
        portfolio_keywords = ["portföy", "portfolio", "pozisyon", "position", "bakiye", "balance"]
        if any(word in query_lower for word in portfolio_keywords):
            if any(word in query_lower for word in ["al", "buy", "sat", "sell", "işlem", "trade"]):
                trade_type = "buy" if any(w in query_lower for w in ["al", "buy"]) else "sell"
                return {"action": "portfolio_trade", "trade_type": trade_type, "symbol": symbol}
            return {"action": "portfolio_status"}
        
        # Trading queries
        trade_keywords = ["al", "buy", "sat", "sell", "işlem", "trade"]
        if any(word in query_lower for word in trade_keywords) and symbol:
            trade_type = "buy" if any(w in query_lower for w in ["al", "buy"]) else "sell"
            return {"action": "portfolio_trade", "trade_type": trade_type, "symbol": symbol}
        
        # If we have a symbol but no clear intent, default to comprehensive analysis
        if symbol:
            return {"action": "comprehensive_analyze", "symbol": symbol}
        
        # Default to general chat
        return {"action": "general"}

