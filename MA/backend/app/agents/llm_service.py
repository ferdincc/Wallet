"""
LLM Service for integration with Llama or other models via LangChain
"""
from typing import Dict, Any, List, Optional
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions using LangChain"""
    
    def __init__(self):
        self.is_available_flag = False
        self.llm = None
        self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize LLM connection"""
        try:
            # Try to import LangChain (different import paths for different versions)
            try:
                from langchain_community.chat_models import ChatOllama
            except ImportError:
                try:
                    from langchain.chat_models import ChatOllama
                except ImportError:
                    logger.warning("ChatOllama not found. Trying Ollama directly...")
                    from langchain_community.llms import Ollama as OllamaLLM
                    # Use regular LLM instead of chat model
                    if settings.LLM_API_BASE:
                        self.llm = OllamaLLM(
                            base_url=settings.LLM_API_BASE,
                            model=settings.LLM_MODEL_NAME,
                            temperature=settings.LLM_TEMPERATURE
                        )
                    else:
                        self.llm = OllamaLLM(
                            model=settings.LLM_MODEL_NAME,
                            temperature=settings.LLM_TEMPERATURE
                        )
                    self.is_available_flag = True
                    logger.info(f"LLM initialized (Ollama): {settings.LLM_MODEL_NAME}")
                    return
            
            # If ChatOllama was imported successfully
            if settings.LLM_API_BASE:
                # Use custom API base (e.g., Ollama)
                self.llm = ChatOllama(
                    base_url=settings.LLM_API_BASE,
                    model=settings.LLM_MODEL_NAME,
                    temperature=settings.LLM_TEMPERATURE
                )
            else:
                # Default to local Ollama
                self.llm = ChatOllama(
                    model=settings.LLM_MODEL_NAME,
                    temperature=settings.LLM_TEMPERATURE
                )
            
            self.is_available_flag = True
            logger.info(f"LLM initialized: {settings.LLM_MODEL_NAME}")
            
        except ImportError as e:
            logger.warning(f"LangChain not installed or Ollama not available: {e}. LLM features will be disabled.")
            self.is_available_flag = False
        except Exception as e:
            logger.error(f"Error initializing LLM: {e}")
            self.is_available_flag = False
    
    def is_available(self) -> bool:
        """Check if LLM is available"""
        return self.is_available_flag and self.llm is not None
    
    async def chat(
        self,
        query: str,
        context: List[Dict[str, str]] = None,
        *,
        system_prompt: Optional[str] = None,
        history_limit: int = 10,
    ) -> Dict[str, Any]:
        """Chat with LLM (with 15 second timeout)"""
        if not self.is_available():
            return {"response": "LLM servisi şu anda kullanılamıyor."}
        
        import asyncio
        try:
            # Add 15 second timeout
            return await asyncio.wait_for(
                self._chat_internal(
                    query, context, system_prompt=system_prompt, history_limit=history_limit
                ),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error("LLM chat timeout after 15 seconds")
            return {"response": "Analiz devam ediyor, lütfen birkaç saniye sonra tekrar deneyin."}
        except Exception as e:
            logger.error(f"Error in LLM chat: {e}")
            return {"response": f"Hata: {str(e)}"}

    async def chat_crypto_assistant(
        self,
        query: str,
        context: List[Dict[str, str]] = None,
        agent_memory: Optional[str] = None,
        history_limit: int = 10,
    ) -> Dict[str, Any]:
        """Serbest sohbet: kısa, samimi yanıt; önceki ajan özetini sistem mesajına ekler."""
        memory_block = ""
        if agent_memory and str(agent_memory).strip():
            memory_block = (
                "\n\nÖnceki ajan analizi özeti (gerekirse referans ver; kullanıcıya aynen tekrar etmek zorunda değilsin):\n"
                f"{str(agent_memory).strip()[:2000]}\n"
            )
        system = (
            "Sen kripto piyasaları ve blokzincir konusunda bilgili, samimi bir sohbet asistanısın.\n"
            "Yanıtların kısa ve akıcı olsun (tercihen 2–5 cümle). Türkçe soruda Türkçe, İngilizce soruda İngilizce yanıt ver.\n"
            "Kesin yatırım tavsiyesi verme; görüş sorulduğunda bunun kişisel karar ve risk olduğunu kısaca hatırlat.\n"
            f"{memory_block}"
        )
        return await self.chat(
            query, context, system_prompt=system, history_limit=history_limit
        )
    
    async def _chat_internal(
        self,
        query: str,
        context: List[Dict[str, str]] = None,
        *,
        system_prompt: Optional[str] = None,
        history_limit: int = 10,
    ) -> Dict[str, Any]:
        """Internal chat method without timeout"""
        try:
            # Try to use chat prompts if available
            try:
                from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
                
                # Build prompt with context
                default_system = """Sen yardımcı bir asistansın. Önceliğin kripto para piyasaları, teknik analiz ve bu uygulamadaki veri kaynakları;
ancak kullanıcı genel bilgi, tarih, eğitim veya sohbet tarzı sorular sorarsa da makul ölçüde yanıt ver.
Yanıt dilini kullanıcının diline uydur: Türkçe soruya Türkçe, İngilizce soruya İngilizce.
Yatırım tavsiyesi verme; fiyat/risk hakkında konuşurken bunun bilgilendirme olduğunu kısaca belirt.
Eksik veya kesin olmayan bilgilerde dürüst ol."""
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt or default_system),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}")
                ])
                
                chain = prompt | self.llm
                
                lim = max(1, min(history_limit, 20))
                formatted_context = [
                    (msg.get("role", "user") if msg.get("role") == "user" else "assistant", 
                     msg.get("content", ""))
                    for msg in (context or [])[-lim:]
                ]
                
                response = await chain.ainvoke({
                    "input": query,
                    "chat_history": formatted_context
                })
                
                return {
                    "response": response.content if hasattr(response, 'content') else str(response),
                    "model": settings.LLM_MODEL_NAME
                }
            except:
                # Fallback to simple prompt (system_prompt = sohbet modu / ajan özeti için)
                base_rules = """Yardımcı bir asistansın. Kripto ve finans konusunda güçlüsün; ayrıca genel sorulara da kısa ve net yanıt ver.
Kullanıcının sorusu hangi dildeyse o dilde yanıt ver.
Yatırım tavsiyesi verme; gerekirse verilerin yaklaşık/kaynaklı olduğunu belirt."""
                sys_prefix = (system_prompt.strip() + "\n\n") if system_prompt else ""
                simple_prompt = f"""{sys_prefix}{base_rules}

Soru: {query}

Yanıt:"""
                
                response = await self.llm.ainvoke(simple_prompt)
                return {
                    "response": str(response),
                    "model": settings.LLM_MODEL_NAME
                }
            
        except Exception as e:
            logger.error(f"Error in LLM chat: {e}")
            return {"response": f"Hata: {str(e)}"}
    
    async def analyze_market(
        self, 
        symbol: str,
        technical_data: Dict[str, Any],
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Analyze market using LLM (with 15 second timeout)"""
        if not self.is_available():
            return {}
        
        import asyncio
        try:
            # Add 15 second timeout
            return await asyncio.wait_for(
                self._analyze_market_internal(symbol, technical_data, current_price),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error("LLM market analysis timeout after 15 seconds")
            return {"analysis": "Analiz devam ediyor, lütfen birkaç saniye sonra tekrar deneyin."}
        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            return {}
    
    async def _analyze_market_internal(
        self, 
        symbol: str,
        technical_data: Dict[str, Any],
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Internal analyze market method without timeout"""
        try:
            analysis_prompt = f"""Aşağıdaki teknik analiz verilerine dayanarak {symbol} için bir piyasa analizi yap:

Teknik Göstergeler:
- RSI: {technical_data.get('rsi', 'N/A')}
- MACD: {technical_data.get('macd', {})}
- Bollinger Bands: {technical_data.get('bollinger_bands', {})}
- Mevcut Fiyat: ${current_price or 'N/A'}
- 24s Değişim: {technical_data.get('price_change_24h', 'N/A')}%

Sinyaller: {', '.join(technical_data.get('signals', []))}

Kısa ve öz bir analiz yap (2-3 cümle). Türkçe yanıt ver.
Yatırım tavsiyesi değil, sadece piyasa durumu analizi yap."""
            
            response = await self.llm.ainvoke(analysis_prompt)
            
            return {
                "analysis": response.content if hasattr(response, 'content') else str(response),
                "model": settings.LLM_MODEL_NAME
            }
            
        except Exception as e:
            logger.error(f"Error in market analysis internal: {e}")
            raise
    
    async def determine_intent(self, query: str, context: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Determine user intent using LLM (with 15 second timeout)"""
        if not self.is_available():
            return {"action": "general"}
        
        import asyncio
        try:
            # Add 15 second timeout
            return await asyncio.wait_for(
                self._determine_intent_internal(query, context),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error("LLM intent determination timeout after 15 seconds")
            return {"action": "general"}
        except Exception as e:
            logger.error(f"Error determining intent: {e}")
            return {"action": "general"}
    
    async def _determine_intent_internal(self, query: str, context: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Internal determine intent method without timeout"""
        try:
            intent_prompt = f"""Kullanıcı sorgusu: "{query}"

Bu sorgu ne istiyor? Şunlardan birini seç:
1. fetch_price - Kripto para fiyatı sorgulama (fiyat, ne kadar, kaç) — sadece genel coin fiyatı; cüzdan/MetaMask ile ilgili değilse
2. analyze - Teknik analiz isteme (analiz, teknik, rsi, macd, piyasa analizi)
3. comprehensive_analyze - Kapsamlı analiz (kapsamlı, detaylı, tam analiz, piyasa analizi yap)
4. fetch_news - Son haberler listesi (son haberler, BTC haberleri, güncel haber - liste ve sentiment özeti)
5. sentiment - Sentiment analizi detayı (sentiment analizi, duygu analizi, reddit)
6. predict - Fiyat tahmini (tahmin, predict, gelecek, ne olacak)
7. portfolio_status - Uygulama içi paper portföy (portföy, portfolio, pozisyon — simülasyon portföyü)
8. portfolio_trade - İşlem önerisi (al, buy, sat, sell, işlem)
9. backtest - Backtest / hangi model daha iyi (backtest yap, model karşılaştır, hangi model iyi)
10. campaigns - Kampanyalar / airdrop / fırsatlar / AI içerik ödülü / yeni token listeleme (kampanya, airdrop, bugün hangi kampanya, coinmarketcap listing)
11. wallet - MetaMask / cüzdan bakiyesi, ETH miktarı, son işlemler, haftalık kazanç-PnL (cüzdan, metamask, son işlemlerim, bu hafta kazancım)
12. general - Genel soru/sohbet, tarihsel getiri / uzun vadeli fiyat geçmişi, eğitim, tanım, kod, günlük konuşma (örn. "BTC son 10 yılda ne kadar arttı", "what is DeFi")

Sadece JSON formatında yanıt ver. Ek alanlar:
- campaigns için: "campaign_filter": "all" | "today" | "airdrop" | "ai_content" | "listing"
- wallet için: "wallet_mode": "balance" | "pnl_week" | "pnl_month" | "transactions"

Örnekler:
- "BTC fiyatı" -> {{"action": "fetch_price", "symbol": "BTC/USDT"}}
- "son haberler" -> {{"action": "fetch_news"}}
- "bugün hangi kampanyalar var" -> {{"action": "campaigns", "campaign_filter": "today"}}
- "airdrop var mı" -> {{"action": "campaigns", "campaign_filter": "airdrop"}}
- "cüzdanımda ne kadar eth var" -> {{"action": "wallet", "wallet_mode": "balance"}}
- "bu hafta kazancım" -> {{"action": "wallet", "wallet_mode": "pnl_week"}}
- "piyasa analizi yap" -> {{"action": "comprehensive_analyze"}}
- "ETH analiz" -> {{"action": "analyze", "symbol": "ETH/USDT"}}
- "portföy durumu" -> {{"action": "portfolio_status"}}
- "BTC al" -> {{"action": "portfolio_trade", "symbol": "BTC/USDT", "trade_type": "buy"}}
- "BTC son 10 yılda ne kadar arttı" -> {{"action": "general"}}
- "How much did Bitcoin rise in the last decade?" -> {{"action": "general"}}
- "peki sence alınır mı" / "what do you think should I buy" -> {{"action": "general"}} (görüş/sohbet, ajan analizi değil)"""
            
            response = await self.llm.ainvoke(intent_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Try to parse JSON from response
            import json
            try:
                # Extract JSON from response if wrapped in text
                if '{' in response_text:
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    json_str = response_text[json_start:json_end]
                    return json.loads(json_str)
            except:
                pass
            
            return {"action": "general"}
            
        except Exception as e:
            logger.error(f"Error determining intent internal: {e}")
            raise
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Define available tools for LLM tool use"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_price",
                    "description": "Binance'den son fiyatı çek. Kullanıcı bir coin'in fiyatını sorduğunda kullan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Coin sembolü (örn: BTC/USDT, ETH/USDT)"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_sentiment",
                    "description": "Sentiment analizi sonucunu getir. Kullanıcı haber veya sentiment hakkında sorduğunda kullan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Coin sembolü (örn: BTC, ETH)"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_prediction",
                    "description": "Fiyat tahmini sonucunu getir. Kullanıcı gelecek fiyat veya tahmin hakkında sorduğunda kullan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Coin sembolü (örn: BTC/USDT)"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_technical_analysis",
                    "description": "Teknik analiz sonucunu getir. Kullanıcı RSI, MACD veya teknik göstergeler hakkında sorduğunda kullan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Coin sembolü (örn: BTC/USDT)"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            }
        ]
    
    async def chat_with_tools(
        self,
        query: str,
        context: List[Dict[str, str]] = None,
        tools_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Chat with LLM using tool use capability (with 15 second timeout)
        
        Args:
            query: User query
            context: Chat history
            tools_callback: Function to call when tool is requested
                Should accept (tool_name: str, parameters: dict) and return result
        """
        if not self.is_available():
            return {"response": "LLM servisi şu anda kullanılamıyor."}
        
        import asyncio
        try:
            # Add 15 second timeout
            return await asyncio.wait_for(
                self._chat_with_tools_internal(query, context, tools_callback),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error("LLM chat with tools timeout after 15 seconds")
            return {"response": "Analiz devam ediyor, lütfen birkaç saniye sonra tekrar deneyin."}
        except Exception as e:
            logger.error(f"Error in LLM chat with tools: {e}")
            return {"response": f"Hata: {str(e)}"}
    
    async def _chat_with_tools_internal(
        self,
        query: str,
        context: List[Dict[str, str]] = None,
        tools_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Internal chat with tools method without timeout"""
        try:
            # Check if LLM supports tool use (Llama 3.1+)
            tools = self.get_tools()
            
            # Enhanced prompt with tool descriptions
            system_prompt = """Sen kripto para piyasaları konusunda uzman bir finansal danışmansın.
Kullanıcılara kripto para piyasaları hakkında bilgi veriyor, analizler yapıyor ve tavsiyeler sunuyorsun.

Kullanabileceğin araçlar:
1. get_price(symbol) - Binance'den son fiyatı çek
2. get_sentiment(symbol) - Sentiment analizi sonucunu getir
3. get_prediction(symbol) - Fiyat tahmini sonucunu getir
4. get_technical_analysis(symbol) - Teknik analiz sonucunu getir

Kullanıcı bir coin hakkında soru sorduğunda, önce ilgili aracı kullanarak veriyi çek, sonra yanıt ver.
Örnek: "BTC fiyatı nedir?" -> get_price("BTC/USDT") çağır, sonra sonucu kullanıcıya açıkla.

Yanıtlarını Türkçe ver ve profesyonel ama anlaşılır bir dil kullan."""
            
            # Try to use structured output or tool calling if available
            try:
                from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
                from langchain_core.messages import HumanMessage, SystemMessage
                
                messages = [
                    SystemMessage(content=system_prompt)
                ]
                
                # Add context
                if context:
                    for msg in context[-5:]:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        if role == "user":
                            messages.append(HumanMessage(content=content))
                        else:
                            from langchain_core.messages import AIMessage
                            messages.append(AIMessage(content=content))
                
                # Add current query
                messages.append(HumanMessage(content=query))
                
                # Try to bind tools if LLM supports it
                try:
                    if hasattr(self.llm, 'bind_tools'):
                        llm_with_tools = self.llm.bind_tools(tools)
                        response = await llm_with_tools.ainvoke(messages)
                        
                        # Check if LLM wants to use a tool
                        if hasattr(response, 'tool_calls') and response.tool_calls:
                            tool_results = []
                            for tool_call in response.tool_calls:
                                tool_name = tool_call.get('name', '')
                                tool_args = tool_call.get('args', {})
                                
                                if tools_callback:
                                    tool_result = await tools_callback(tool_name, tool_args)
                                    tool_results.append(tool_result)
                            
                            # Get final response with tool results
                            if tool_results:
                                messages.append(response)
                                for result in tool_results:
                                    from langchain_core.messages import ToolMessage
                                    messages.append(ToolMessage(content=str(result), tool_call_id=""))
                                
                                final_response = await llm_with_tools.ainvoke(messages)
                                return {
                                    "response": final_response.content if hasattr(final_response, 'content') else str(final_response),
                                    "model": settings.LLM_MODEL_NAME,
                                    "tools_used": [tc.get('name') for tc in response.tool_calls] if hasattr(response, 'tool_calls') else []
                                }
                        
                        return {
                            "response": response.content if hasattr(response, 'content') else str(response),
                            "model": settings.LLM_MODEL_NAME
                        }
                except AttributeError:
                    # LLM doesn't support tool binding, fall through to regular chat
                    pass
                
                # Fallback to regular chat
                response = await self.llm.ainvoke(messages)
                return {
                    "response": response.content if hasattr(response, 'content') else str(response),
                    "model": settings.LLM_MODEL_NAME
                }
                
            except Exception as e:
                logger.warning(f"Tool use not available, falling back to regular chat: {e}")
                # Fallback to regular chat
                return await self._chat_internal(query, context)
            
        except Exception as e:
            logger.error(f"Error in LLM chat with tools internal: {e}")
            raise


# Global instance
llm_service = LLMService()

