import { useState, useEffect, useLayoutEffect, useRef, useCallback, type KeyboardEvent } from 'react'
import {
  chatApi,
  marketsApi,
  newsApi,
  predictionApi,
  Ticker,
  TechnicalAnalysis,
  type ChatHistoryTurn,
} from '../services/api'
import { translate, readStoredLocale } from '../i18n/messages'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { useWalletAnalysis } from '../contexts/WalletAnalysisContext'
import { Send, Bot, User, TrendingUp, TrendingDown, BarChart3, Activity, AlertCircle, ExternalLink, Sparkles, Brain, X, Clock, CheckCircle2, XCircle, PauseCircle, Users, Megaphone, Wallet2, ChevronDown } from 'lucide-react'
import TradingViewWidget from '../components/TradingViewWidget'
import VoiceAssistant from '../components/VoiceAssistant'

interface ReasoningStep {
  timestamp: string
  agent: string
  type: string
  description: string
  data?: any
  result?: any
  duration_ms?: number
}

interface ReasoningLog {
  query_id: string
  start_time: string
  end_time: string
  total_duration_ms: number
  steps: ReasoningStep[]
  step_count: number
  agents_involved: string[]
}

interface Consensus {
  votes?: Record<string, { vote: string; confidence: number }>
  consensus?: string
  consensus_confidence?: number
  disagreement?: boolean
}

interface Recommendation {
  action: 'AL' | 'SAT' | 'NÖTR'
  reasons?: string[]
}

const CHAT_AGENT_ROSTER = [
  'ChatAgent',
  'DataAgent',
  'AnalysisAgent',
  'SentimentAgent',
  'PredictionAgent',
  'RiskAgent',
  'ConsensusAgent',
  'BacktestAgent',
  'CampaignAgent',
  'WalletAgent',
] as const

/** API bazen sayıları string döndürür; .toFixed doğrudan çağrılırsa render patlar */
function fmtFixed(value: unknown, digits: number, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return fallback
  return n.toFixed(digits)
}

function formatUsd(value: unknown, minD = 2, maxD = 2): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return '—'
  try {
    return n.toLocaleString('en-US', { minimumFractionDigits: minD, maximumFractionDigits: maxD })
  } catch {
    return fmtFixed(n, maxD)
  }
}

function normalizeSourceList(raw: unknown): Array<{ title: string; url: string; type: string }> {
  if (!Array.isArray(raw)) return []
  const out: Array<{ title: string; url: string; type: string }> = []
  for (const s of raw) {
    if (!s || typeof s !== 'object') continue
    const o = s as Record<string, unknown>
    const url = typeof o.url === 'string' ? o.url : '#'
    const title = typeof o.title === 'string' ? o.title : url
    const type = typeof o.type === 'string' ? o.type : 'news'
    out.push({ title, url, type })
  }
  return out
}

function assistantTextFromResponse(res: unknown): string {
  if (res === null || res === undefined) return ''
  if (typeof res === 'string') return res
  if (typeof res === 'object') {
    try {
      return JSON.stringify(res)
    } catch {
      return String(res)
    }
  }
  return String(res)
}

/** Backend ChatResponse veya proxy sarmalayıcılarından asistan metnini çıkarır */
function extractAssistantMessageFromChatResponse(payload: unknown): string {
  if (payload == null) return ''
  if (typeof payload === 'string') return payload.trim()
  if (typeof payload !== 'object') return String(payload).trim()

  const o = payload as Record<string, unknown>

  const tryStringFields = (obj: Record<string, unknown>): string => {
    const keys = [
      'response',
      'message',
      'content',
      'text',
      'result',
      'answer',
      'reply',
      'output',
    ] as const
    for (const k of keys) {
      const v = obj[k]
      if (typeof v === 'string' && v.trim() !== '') return v.trim()
    }
    return ''
  }

  // Bazı proxy / eski istemciler: { data: { response: "..." } }
  if (o.data !== null && typeof o.data === 'object') {
    const fromData = tryStringFields(o.data as Record<string, unknown>)
    if (fromData) return fromData
    const deep = (o.data as Record<string, unknown>).data
    if (deep !== null && typeof deep === 'object') {
      const inner = tryStringFields(deep as Record<string, unknown>)
      if (inner) return inner
    }
  }

  // Axios benzeri tam gövde (nadiren buraya düşer)
  const direct = tryStringFields(o)
  if (direct) return direct

  return ''
}

/** Avoids render crashes when API/state yields non-string content */
function safeMessageText(content: unknown): string {
  if (content == null) return ''
  if (typeof content === 'string') return content
  return assistantTextFromResponse(content)
}

function normalizeReasoningStep(raw: unknown): ReasoningStep | null {
  if (raw == null || typeof raw !== 'object') return null
  const s = raw as Record<string, unknown>
  const agent =
    typeof s.agent === 'string'
      ? s.agent
      : s.agent != null
        ? String(s.agent)
        : '—'
  return {
    timestamp: typeof s.timestamp === 'string' ? s.timestamp : '',
    agent,
    type: typeof s.type === 'string' ? s.type : 'data_fetch',
    description: typeof s.description === 'string' ? s.description : '',
    data: s.data,
    result: s.result,
    duration_ms: typeof s.duration_ms === 'number' ? s.duration_ms : undefined,
  }
}

function normalizeReasoningLog(raw: unknown): ReasoningLog | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const rawSteps = Array.isArray(o.steps) ? o.steps : []
  const steps = rawSteps
    .map(normalizeReasoningStep)
    .filter((x): x is ReasoningStep => x != null)
  const agentsRaw = Array.isArray(o.agents_involved) ? o.agents_involved : []
  const agents = agentsRaw.filter((a): a is string => typeof a === 'string' && a.length > 0)
  const dur = Number(o.total_duration_ms)
  return {
    query_id: typeof o.query_id === 'string' ? o.query_id : '—',
    start_time: typeof o.start_time === 'string' ? o.start_time : '',
    end_time: typeof o.end_time === 'string' ? o.end_time : '',
    total_duration_ms: Number.isFinite(dur) ? dur : 0,
    steps,
    step_count: typeof o.step_count === 'number' ? o.step_count : steps.length,
    agents_involved: agents,
  }
}

/** API bazen agent alanını nesne veya sayı döndürebilir; ikon/renk switch'leri string bekler */
function coerceAgentName(v: unknown): string {
  if (typeof v === 'string' && v.trim()) return v.trim()
  if (v != null && typeof v === 'object' && 'name' in v && typeof (v as { name?: unknown }).name === 'string') {
    return (v as { name: string }).name
  }
  return 'ChatAgent'
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  /** Açılış hoşgeldin balonu — dil değişince metin t() ile yenilenir */
  isWelcome?: boolean
  agent?: string
  /** Backend: agent = veri/çoklu ajan, chat = serbest LLM sohbeti */
  responseMode?: 'agent' | 'chat'
  sources?: Array<{ title: string; url: string; type: string }>
  intent?: { action: string; symbol?: string }
  reasoning_log?: ReasoningLog
  coinData?: {
    symbol: string
    ticker?: Ticker
    analysis?: TechnicalAnalysis
    sentiment?: any
    prediction?: any
    consensus?: Consensus
    recommendation?: Recommendation
  }
}

/** Son ajan analizi (sohbet modunda Claude system bağlamı) */
function buildLastAgentContext(msgs: Message[], t: (k: string) => string): string | undefined {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m.role !== 'assistant' || m.responseMode !== 'agent') continue
    const cd = m.coinData
    const bits: string[] = []
    if (cd?.symbol) bits.push(`${t('coin.symbolLabel')}: ${cd.symbol}`)
    const rsi = cd?.analysis?.rsi
    if (typeof rsi === 'number' && Number.isFinite(rsi)) bits.push(`RSI=${rsi.toFixed(1)}`)
    const macd = cd?.analysis?.macd
    if (macd && typeof macd === 'object') {
      const mm = macd as { macd?: number; signal?: number }
      const bullish = (mm.macd ?? 0) > (mm.signal ?? 0)
      bits.push(bullish ? 'MACD Bullish' : 'MACD Bearish')
    }
    if (cd?.consensus?.consensus)
      bits.push(`${t('chat.consensusLabel')} ${cd.consensus.consensus}`)
    if (bits.length) return bits.join(', ')
  }
  return undefined
}

export default function Chat() {
  const { t, locale } = useAppPreferences()
  const { walletContextForChat, walletAddress } = useWalletAnalysis()
  const [messages, setMessages] = useState<Message[]>(() => [
    {
      role: 'assistant',
      content: translate(readStoredLocale(), 'chat.welcome'),
      isWelcome: true,
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null)
  const [coinDetails, setCoinDetails] = useState<any>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  /** Kullanıcı mesaj listesinde yukarı kaydırdıysa otomatik alta çekme */
  const stickToBottomRef = useRef(true)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [showReasoningLog, setShowReasoningLog] = useState<boolean>(false)
  const [currentReasoningLog, setCurrentReasoningLog] = useState<ReasoningLog | null>(null)
  const [agentProgress, setAgentProgress] = useState<{ agent: string; status: string }[]>([])
  /** Uzun asistan yanıtlarında "Devamını göster" */
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({})
  const COLLAPSE_ASSISTANT_CHARS = 1600

  const scrollChatToBottom = useCallback(() => {
    const el = messagesContainerRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    } else {
      messagesEndRef.current?.scrollIntoView({ block: 'end', behavior: 'auto' })
    }
  }, [])

  const updateStickFromScroll = useCallback(() => {
    const el = messagesContainerRef.current
    if (!el) return
    const thresholdPx = 120
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const nearBottom = distFromBottom < thresholdPx
    stickToBottomRef.current = nearBottom
    const hasOverflow = el.scrollHeight > el.clientHeight + 8
    setShowScrollDown(hasOverflow && !nearBottom)
  }, [])

  /** Yalnızca kullanıcı zaten en alta yakınsa takip et; geçmişe çıkınca sağ panel kayması chat'i oynatmaz */
  useLayoutEffect(() => {
    if (!stickToBottomRef.current) return
    scrollChatToBottom()
    const t = window.setTimeout(scrollChatToBottom, 0)
    const t2 = window.setTimeout(scrollChatToBottom, 100)
    return () => {
      window.clearTimeout(t)
      window.clearTimeout(t2)
    }
  }, [messages, isLoading, agentProgress, scrollChatToBottom])

  useEffect(() => {
    const id = requestAnimationFrame(() => updateStickFromScroll())
    return () => cancelAnimationFrame(id)
  }, [messages, isLoading, agentProgress, updateStickFromScroll])

  useEffect(() => {
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'assistant' && m.isWelcome
          ? { ...m, content: t('chat.welcome') }
          : m,
      ),
    )
  }, [locale, t])

  useEffect(() => {
    if (selectedCoin) {
      loadCoinDetails(selectedCoin)
    }
  }, [selectedCoin, locale])

  const loadCoinDetails = async (symbol: string) => {
    try {
      const symbolOnly = symbol.split('/')[0] || symbol
      
      const [ticker, analysis, sentiment, prediction] = await Promise.allSettled([
        marketsApi.getTicker(symbol).catch(err => {
          console.warn('Ticker error:', err)
          return null
        }),
        marketsApi.getAnalysis(symbol).catch(err => {
          console.warn('Analysis error:', err)
          return null
        }),
        newsApi.getSentiment(symbolOnly, true, true, 24, locale).catch(err => {
          console.warn('Sentiment error:', err)
          return null
        }),
        predictionApi.getPrediction(symbol, 'binance', '1h', 7, 'ensemble', locale).catch(err => {
          console.warn('Prediction error:', err)
          return null
        })
      ])
      
      const details: any = { symbol }
      
      if (ticker.status === 'fulfilled' && ticker.value) {
        details.ticker = ticker.value
      }
      
      if (analysis.status === 'fulfilled' && analysis.value) {
        details.analysis = analysis.value.analysis || analysis.value
      }
      
      if (sentiment.status === 'fulfilled' && sentiment.value && sentiment.value.success !== false) {
        details.sentiment = sentiment.value
      }
      
      if (prediction.status === 'fulfilled' && prediction.value && prediction.value.success !== false) {
        details.prediction = prediction.value
      }
      
      setCoinDetails(details)
    } catch (error) {
      console.error('Error loading coin details:', error)
      // Set basic details even on error
      setCoinDetails({ symbol })
    }
  }

  const extractSymbolFromMessage = (content: string): string | null => {
    // Extract symbol patterns
    const patterns = [
      /(?:^|\s)([A-Z]{2,10}\/[A-Z]{2,10})(?:\s|$)/,  // BTC/USDT
      /(?:^|\s)([A-Z]{2,10})(?:\s|$)/,  // BTC, ETH
    ]
    
    for (const pattern of patterns) {
      const match = content.match(pattern)
      if (match) {
        let symbol = match[1]
        if (!symbol.includes('/')) {
          symbol = `${symbol}/USDT`
        }
        return symbol
      }
    }
    
    // Check for coin names
    const contentLower = content.toLowerCase()
    if (contentLower.includes('bitcoin') || contentLower.includes('btc')) return 'BTC/USDT'
    if (contentLower.includes('ethereum') || contentLower.includes('eth')) return 'ETH/USDT'
    if (contentLower.includes('solana') || contentLower.includes('sol')) return 'SOL/USDT'
    if (contentLower.includes('cardano') || contentLower.includes('ada')) return 'ADA/USDT'
    if (contentLower.includes('ripple') || contentLower.includes('xrp')) return 'XRP/USDT'
    
    return null
  }

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    stickToBottomRef.current = true

    const userMessage: Message = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMessage])
    
    // Extract symbol from message
    const symbol = extractSymbolFromMessage(input)
    if (symbol) {
      setSelectedCoin(symbol)
    }
    
    const query = input
    setInput('')
    setIsLoading(true)
    setAgentProgress([])

    // Simulate agent progress (will be replaced with real-time updates)
    const progressSteps = [
      { agent: 'ChatAgent', status: t('chat.progress.chat') },
      { agent: 'DataAgent', status: t('chat.progress.data') },
      { agent: 'AnalysisAgent', status: t('chat.progress.analysis') },
      { agent: 'SentimentAgent', status: t('chat.progress.sentiment') },
      { agent: 'PredictionAgent', status: t('chat.progress.prediction') },
      { agent: 'RiskAgent', status: t('chat.progress.risk') },
    ]
    
    // Show progress steps gradually
    let stepIndex = 0
    let progressInterval: ReturnType<typeof setInterval> | null = null
    let safetyTimeout: ReturnType<typeof setTimeout> | null = null
    
    progressInterval = setInterval(() => {
      if (stepIndex < progressSteps.length) {
        setAgentProgress(prev => [...prev, progressSteps[stepIndex]])
        stepIndex++
      } else {
        // Stop adding more steps after all are shown
        if (progressInterval) {
          clearInterval(progressInterval)
          progressInterval = null
        }
      }
    }, 500)

    // Safety timeout - clear progress after 2 minutes
    safetyTimeout = setTimeout(() => {
      if (progressInterval) {
        clearInterval(progressInterval)
        progressInterval = null
      }
      setAgentProgress([])
      setIsLoading(false)
      console.warn('Request timeout - clearing loading state')
      const timeoutMessage: Message = {
        role: 'assistant',
        content: `⏱️ ${t('chat.requestTimeout')}`,
      }
      setMessages((prev) => [...prev, timeoutMessage])
    }, 120000) // 2 minutes

    try {
      console.log('Sending message to backend:', query)
      const conversationHistory: ChatHistoryTurn[] = messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({ role: m.role, content: safeMessageText(m.content) }))
        .slice(-10)
      const lastAgentContext = buildLastAgentContext(messages, t)

      const response = await chatApi.sendMessage({
        message: query,
        conversationHistory,
        lastAgentContext,
        wallet_address: walletAddress || undefined,
        walletContext: walletContextForChat || undefined,
        locale,
      })
      console.log('Full response:', JSON.stringify(response, null, 2))
      if (progressInterval) {
        clearInterval(progressInterval)
        progressInterval = null
      }
      if (safetyTimeout) {
        clearTimeout(safetyTimeout)
        safetyTimeout = null
      }
      setAgentProgress([])
      
      let sources: Array<{ title: string; url: string; type: string }> = []
      if (response.agent_data) {
        const ad = response.agent_data as Record<string, unknown>
        if (Array.isArray(ad.sources)) {
          sources = normalizeSourceList(ad.sources)
        } else if (ad.sentiment && typeof ad.sentiment === 'object') {
          const sen = ad.sentiment as Record<string, unknown>
          sources = normalizeSourceList(sen.sources)
        }
      }
      
      // Extract coin data from agent response (with safe access)
      const coinData: any = {}
      try {
        // First, try to extract symbol from response or use extracted symbol
        let finalSymbol = symbol
        const agentData = response.agent_data || {}
        
        // Try to get symbol from response
        if (agentData.symbol) {
          finalSymbol = agentData.symbol
        } else if (response.intent?.symbol) {
          finalSymbol = response.intent.symbol
        }
        
        // If we have a symbol, set it and extract data
        if (finalSymbol) {
          coinData.symbol = finalSymbol
          setSelectedCoin(finalSymbol)
          
          // Extract ticker data
          if (agentData.current_data) {
            coinData.ticker = agentData.current_data
          } else if (agentData.data) {
            coinData.ticker = agentData.data
          } else if (agentData.technical?.current_data) {
            coinData.ticker = agentData.technical.current_data
          } else if (agentData.ticker) {
            coinData.ticker = agentData.ticker
          }
          
          // Extract technical analysis
          if (agentData.technical_analysis) {
            coinData.analysis = agentData.technical_analysis
          } else if (agentData.technical?.technical_analysis) {
            coinData.analysis = agentData.technical.technical_analysis
          } else if (agentData.analysis) {
            coinData.analysis = agentData.analysis
          }
          
          // Extract sentiment
          if (agentData.sentiment) {
            coinData.sentiment = agentData.sentiment
          } else if (agentData.sentiment?.overall_sentiment) {
            coinData.sentiment = agentData.sentiment
          }
          
          // Extract prediction
          if (agentData.prediction) {
            coinData.prediction = agentData.prediction
          } else if (agentData.prediction?.predictions) {
            coinData.prediction = agentData.prediction
          }
          
          // Add recommendation, risk, and consensus data (safe access)
          if (agentData.recommendation) {
            coinData.recommendation = agentData.recommendation
          }
          if (agentData.risk) {
            coinData.risk = agentData.risk
          }
          if (agentData.consensus) {
            coinData.consensus = agentData.consensus
          }
        }
      } catch (err) {
        console.error('Error extracting coin data:', err)
        // Continue without coin data if extraction fails
      }
      
      // Determine agent name safely
      let agentName = 'ChatAgent'
      try {
        const agentData = response.agent_data || {}
        if (response.agent != null && response.agent !== '') {
          agentName = coerceAgentName(response.agent)
        } else if (agentData.agent != null && agentData.agent !== '') {
          agentName = coerceAgentName(agentData.agent)
        } else if (agentData.sentiment) {
          agentName = 'SentimentAgent'
        } else if (agentData.technical || agentData.technical_analysis) {
          agentName = 'AnalysisAgent'
        } else if (agentData.prediction) {
          agentName = 'PredictionAgent'
        }
      } catch (err) {
        console.error('Error determining agent name:', err)
      }
      
      const safeReasoning = normalizeReasoningLog(response.reasoning_log)
      const modeRaw = (response as { response_mode?: string }).response_mode
      const responseMode: 'agent' | 'chat' = modeRaw === 'chat' ? 'chat' : 'agent'

      const assistantPlain = extractAssistantMessageFromChatResponse(response)

      const assistantMessage: Message = {
        role: 'assistant',
        content:
          assistantPlain.trim() !== ''
            ? assistantPlain
            : t('chat.errorEmpty'),
        agent: agentName,
        responseMode,
        sources,
        intent: response.intent || null,
        reasoning_log: safeReasoning ?? undefined,
        coinData: Object.keys(coinData).length > 0 ? coinData : undefined,
      }

      setMessages((prev) => [...prev, assistantMessage])
      
      // If coin data exists, update coin details (safe access)
      try {
        if (coinData && coinData.symbol) {
          // If we have data from backend, use it; otherwise load from API
          if (coinData.ticker || coinData.analysis || coinData.sentiment || coinData.prediction) {
            // Merge with existing coinDetails to preserve any existing data
            setCoinDetails((prev: any) => {
              const merged = { ...prev, ...coinData }
              // Ensure symbol is set
              merged.symbol = coinData.symbol
              return merged
            })
          } else {
            // If no data from backend, load from API
            loadCoinDetails(coinData.symbol)
          }
        } else if (symbol) {
          // If we have a symbol but no coinData, load from API
          loadCoinDetails(symbol)
        }
      } catch (err) {
        console.error('Error updating coin details:', err)
        // Fallback: try to load from API if we have a symbol
        if (symbol) {
          loadCoinDetails(symbol)
        }
      }
    } catch (error: any) {
      if (progressInterval) clearInterval(progressInterval)
      if (safetyTimeout) clearTimeout(safetyTimeout)
      setAgentProgress([])
      setIsLoading(false)
      console.error('Chat error:', error)
      
      let errorDetail = t('chat.errorUnknown')
      let errorTitle = t('chat.errorServerTitle')

      if (error.response) {
        const status = error.response.status
        const data = error.response.data

        if (status === 500) {
          errorTitle = t('chat.errorServerTitle')
          errorDetail = data?.detail || data?.message || t('chat.errorServerBody')
        } else if (status === 504) {
          errorTitle = t('chat.errorTimeoutTitle')
          errorDetail = t('chat.errorTimeoutBody')
        } else if (status === 400) {
          errorTitle = t('chat.errorBadRequestTitle')
          errorDetail = data?.detail || t('chat.errorBadRequestBody')
        } else {
          errorTitle = `${t('chat.errorServerTitle')} (${status})`
          errorDetail = data?.detail || data?.message || error.response.statusText
        }
      } else if (error.request) {
        errorTitle = t('chat.errorConnectionTitle')
        errorDetail = t('chat.errorConnectionBody')
      } else if (error.message) {
        errorTitle = t('chat.errorServerTitle')
        errorDetail = error.message
      }

      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorTitle = t('chat.errorTimeoutTitle')
        errorDetail = t('chat.errorTimeoutBody')
      }

      const errorMessage: Message = {
        role: 'assistant',
        content: `❌ ${errorTitle}: ${errorDetail}\n\n💡 ${t('chat.errorHintsTitle')}:\n1. ${t('chat.errorHint1')}\n2. ${t('chat.errorHint2')}\n3. ${t('chat.errorHint3')}\n4. ${t('chat.errorHint4')}\n5. ${t('chat.errorHint5')}`,
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
      setAgentProgress([])
      // Ensure all intervals are cleared
      if (progressInterval) clearInterval(progressInterval)
      if (safetyTimeout) clearTimeout(safetyTimeout)
    }
  }

  const handleInputKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const getAgentIcon = (agent?: string) => {
    switch (agent) {
      case 'SentimentAgent':
        return <TrendingUp className="w-4 h-4" />
      case 'AnalysisAgent':
        return <BarChart3 className="w-4 h-4" />
      case 'PredictionAgent':
        return <Sparkles className="w-4 h-4" />
      case 'RiskAgent':
        return <AlertCircle className="w-4 h-4" />
      case 'CampaignAgent':
        return <Megaphone className="w-4 h-4" />
      case 'WalletAgent':
        return <Wallet2 className="w-4 h-4" />
      default:
        return <Bot className="w-4 h-4" />
    }
  }

  const getAgentColor = (agent?: string) => {
    switch (agent) {
      case 'SentimentAgent':
        return 'text-yellow-400'
      case 'AnalysisAgent':
        return 'text-purple-400'
      case 'PredictionAgent':
        return 'text-pink-400'
      case 'RiskAgent':
        return 'text-red-400'
      case 'CampaignAgent':
        return 'text-emerald-400'
      case 'WalletAgent':
        return 'text-cyan-400'
      default:
        return 'text-blue-400'
    }
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col basis-0 overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col basis-0 overflow-hidden md:flex-row md:items-stretch">
      {/* Left: yalnızca orta alan kayar; giriş şeridi sabit */}
      <div className="flex h-[min(52vh,560px)] min-h-0 min-w-0 w-full shrink-0 flex-col border-b border-white/[0.06] bg-zinc-900/40 backdrop-blur-md md:h-full md:max-h-full md:w-[38%] md:border-b-0 md:border-r md:shrink-0 lg:w-1/3">
        {/* Chat Header */}
        <div className="border-b border-white/[0.06] bg-zinc-900/60 p-4">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-white sm:text-xl">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-crypto-cyan/25 bg-crypto-cyan/10">
              <Bot className="h-5 w-5 text-crypto-cyan" strokeWidth={2} />
            </span>
            <span>{t('chat.title')}</span>
          </h2>
          <p className="mt-1.5 text-sm text-zinc-500">{t('chat.subtitle')}</p>
          <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Multi-agent roster">
            {CHAT_AGENT_ROSTER.map((name) => (
              <span
                key={name}
                className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium bg-slate-700/80 ${getAgentColor(name)}`}
              >
                {getAgentIcon(name)}
                {name}
              </span>
            ))}
          </div>
        </div>

        <div className="relative min-h-0 flex-1 flex flex-col">
        {/* Messages — sabit composer için alt boşluk (pb) */}
        <div
          ref={messagesContainerRef}
          onScroll={updateStickFromScroll}
          className="chat-scroll-y min-h-0 flex-1 overscroll-y-contain p-4 pb-44 pt-2 space-y-4 md:pb-40"
        >
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`flex items-start space-x-2 max-w-[85%] ${
                  message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
                }`}
              >
                <div
                  className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                    message.role === 'user'
                      ? 'bg-primary-600'
                      : 'bg-slate-600'
                  }`}
                >
                  {message.role === 'user' ? (
                    <User className="w-4 h-4 text-white" />
                  ) : (
                    <div className={getAgentColor(coerceAgentName(message.agent))}>
                      {getAgentIcon(coerceAgentName(message.agent))}
                    </div>
                  )}
                </div>
                <div
                  className={`rounded-lg px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-primary-600 text-white'
                      : message.responseMode === 'chat'
                        ? 'bg-slate-700/95 text-slate-200 border-l-4 border-emerald-500 shadow-[inset_4px_0_0_0_rgba(16,185,129,0.35)]'
                        : 'bg-slate-700/95 text-slate-200 border-l-4 border-blue-500 shadow-[inset_4px_0_0_0_rgba(59,130,246,0.35)]'
                  }`}
                >
                  {message.role === 'assistant' && message.responseMode && (
                    <div
                      className={`text-[11px] font-medium mb-2 px-2 py-1 rounded-md inline-block ${
                        message.responseMode === 'chat'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-blue-500/15 text-blue-300'
                      }`}
                    >
                      {message.responseMode === 'chat'
                        ? `💬 ${t('chat.modeChat')}`
                        : `🤖 ${t('chat.modeAgent')}`}
                    </div>
                  )}
                  {/* Agent Badge */}
                  {message.role === 'assistant' && message.agent && (
                    <div className="flex items-center space-x-2 mb-2 pb-2 border-b border-slate-600">
                      <div className={`flex items-center space-x-1 text-xs ${getAgentColor(coerceAgentName(message.agent))}`}>
                        {getAgentIcon(coerceAgentName(message.agent))}
                        <span className="font-medium">{coerceAgentName(message.agent)}</span>
                      </div>
                    </div>
                  )}
                  {(() => {
                    const text = safeMessageText(message.content)
                    const isLong =
                      message.role === 'assistant' && text.length > COLLAPSE_ASSISTANT_CHARS
                    const expanded = expandedMessages[index]
                    const displayText =
                      isLong && !expanded
                        ? `${text.slice(0, COLLAPSE_ASSISTANT_CHARS)}…`
                        : text
                    return (
                      <>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{displayText}</p>
                        {isLong && (
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedMessages((prev) => ({
                                ...prev,
                                [index]: !prev[index],
                              }))
                            }
                            className="mt-2 text-sm font-medium text-primary-400 hover:text-primary-300"
                          >
                            {expanded ? t('chat.showLess') : t('chat.showMore')}
                          </button>
                        )}
                      </>
                    )
                  })()}
                  
                  {/* Sources */}
                  {message.role === 'assistant' &&
                    Array.isArray(message.sources) &&
                    message.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-600">
                      <div className="text-xs text-slate-400 mb-2 font-medium flex items-center space-x-1">
                        <span>📚</span>
                        <span>
                          {t('chat.sourcesCountLabel').replace(
                            '{count}',
                            String(message.sources.length),
                          )}
                        </span>
                        <span className="text-slate-500 text-[10px]">{t('chat.sourcesMultiHint')}</span>
                      </div>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {message.sources.slice(0, 5).map((source, idx) => (
                          <a
                            key={idx}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center space-x-1 text-xs text-primary-400 hover:text-primary-300 underline group"
                          >
                            <span className="truncate flex-1">{source.title || source.url}</span>
                            <span className="text-[10px] text-slate-500 group-hover:text-slate-400">
                              {source.type || t('chat.sourceTypeNews')}
                            </span>
                            <ExternalLink className="w-3 h-3 flex-shrink-0" />
                          </a>
                        ))}
                        {message.sources.length > 5 && (
                          <div className="text-xs text-slate-500 pt-1">
                            {t('chat.moreSources').replace(
                              '{count}',
                              String(message.sources.length - 5),
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Agent Coordination Info */}
                  {message.role === 'assistant' && message.intent?.action === 'comprehensive_analyze' && (
                    <div className="mt-3 pt-3 border-t border-slate-600">
                      <div className="text-xs text-slate-400 mb-2 font-medium">🤝 {t('chat.agentsCoordinated')}:</div>
                      <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-[10px]">{t('chat.agent.marketAnalyst')}</span>
                        <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-[10px]">{t('chat.agent.newsSentiment')}</span>
                        <span className="px-2 py-1 bg-pink-500/20 text-pink-400 rounded text-[10px]">{t('chat.agent.forecaster')}</span>
                        <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-[10px]">{t('chat.agent.risk')}</span>
                        <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-[10px]">{t('chat.agent.portfolio')}</span>
                      </div>
                    </div>
                  )}
                  
                  {/* Reasoning Log Button */}
                  {message.role === 'assistant' &&
                    message.reasoning_log &&
                    Array.isArray(message.reasoning_log.steps) &&
                    message.reasoning_log.steps.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-600">
                      <button
                        type="button"
                        onClick={() => {
                          const norm = normalizeReasoningLog(message.reasoning_log)
                          if (norm) {
                            setCurrentReasoningLog(norm)
                            setShowReasoningLog(true)
                          }
                        }}
                        className="flex items-center space-x-2 text-xs text-primary-400 hover:text-primary-300 transition-colors"
                      >
                        <Brain className="w-3 h-3" />
                        <span>
                          {t('chat.reasoningChain')} (
                          {t('chat.reasoningSteps').replace(
                            '{n}',
                            String(message.reasoning_log.step_count ?? message.reasoning_log.steps?.length ?? 0),
                          )}
                          )
                        </span>
                      </button>
                    </div>
                  )}
                  
                  {/* Consensus Voting */}
                  {message.role === 'assistant' && message.coinData && message.coinData.consensus && (
                    <div className="mt-3 pt-3 border-t border-slate-600">
                      <div className="text-xs text-slate-400 mb-2 font-medium flex items-center space-x-1">
                        <Users className="w-3 h-3" />
                        <span>🗳️ {t('chat.consensusTitle')}:</span>
                      </div>
                      <div className="bg-slate-700/50 rounded-lg p-3 space-y-2">
                        {message.coinData.consensus.votes &&
                          typeof message.coinData.consensus.votes === 'object' &&
                          !Array.isArray(message.coinData.consensus.votes) &&
                          Object.entries(message.coinData.consensus.votes as Record<string, unknown>).map(([agentName, voteData]) => {
                          if (!voteData || typeof voteData !== 'object' || Array.isArray(voteData)) return null
                          const vd = voteData as Record<string, unknown>
                          const vote = String(vd.vote || 'HOLD')
                          const confN = Number(vd.confidence ?? 0)
                          const voteIcon = vote === 'BUY' ? <CheckCircle2 className="w-4 h-4 text-green-500" /> :
                                         vote === 'SELL' ? <XCircle className="w-4 h-4 text-red-500" /> :
                                         <PauseCircle className="w-4 h-4 text-yellow-500" />
                          return (
                            <div key={agentName} className="flex items-start justify-between text-xs">
                              <div className="flex items-center space-x-2 flex-1">
                                {voteIcon}
                                <span className="text-slate-300 font-medium">{agentName}:</span>
                                <span className={`font-semibold ${
                                  vote === 'BUY' ? 'text-green-400' :
                                  vote === 'SELL' ? 'text-red-400' : 'text-yellow-400'
                                }`}>
                                  {vote}
                                </span>
                              </div>
                              <span className="text-slate-400">
                                ({fmtFixed(Number.isFinite(confN) ? confN * 100 : NaN, 0, '0')}%)
                              </span>
                            </div>
                          )
                        })}
                        <div className="pt-2 mt-2 border-t border-slate-600">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-400">{t('chat.consensusLabel')}</span>
                            <span className={`text-sm font-bold ${
                              message.coinData.consensus.consensus === 'BUY' ? 'text-green-400' :
                              message.coinData.consensus.consensus === 'SELL' ? 'text-red-400' : 'text-yellow-400'
                            }`}>
                              {message.coinData.consensus.consensus || 'HOLD'}
                            </span>
                            {message.coinData.consensus.consensus_confidence != null && (
                              <span className="text-xs text-slate-400">
                                ({t('chat.confidenceLabel')}{' '}
                                {fmtFixed(
                                  Number(message.coinData.consensus.consensus_confidence) * 100,
                                  0,
                                  '0',
                                )}
                                %)
                              </span>
                            )}
                          </div>
                          {message.coinData.consensus.disagreement && (
                            <div className="mt-2 text-xs text-yellow-400 bg-yellow-500/10 rounded p-2">
                              ⚠️ {t('chat.disagreementWarning')}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Trading Recommendation */}
                  {message.role === 'assistant' && message.coinData && message.coinData.recommendation && (
                    <div className="mt-3 pt-3 border-t border-slate-600">
                      <div className="text-xs text-slate-400 mb-2 font-medium">💼 {t('chat.portfolioSuggestionTitle')}:</div>
                      <div className={`px-3 py-2 rounded-lg ${
                        message.coinData.recommendation.action === 'AL' ? 'bg-green-500/20 text-green-400' :
                        message.coinData.recommendation.action === 'SAT' ? 'bg-red-500/20 text-red-400' :
                        'bg-slate-600/20 text-slate-400'
                      }`}>
                        <div className="font-semibold text-sm mb-1">
                          {message.coinData.recommendation.action === 'AL'
                            ? `✅ ${t('chat.actionBuy')}`
                            : message.coinData.recommendation.action === 'SAT'
                              ? `❌ ${t('chat.actionSell')}`
                              : `⏸️ ${t('chat.actionNeutral')}`}
                        </div>
                        {message.coinData.recommendation.reasons && Array.isArray(message.coinData.recommendation.reasons) && message.coinData.recommendation.reasons.length > 0 && (
                          <div className="text-xs space-y-1">
                            {message.coinData.recommendation.reasons.map((reason: string, idx: number) => (
                              <div key={idx}>• {reason || t('chat.reasonUnknown')}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="space-y-3">
              <div className="flex justify-start">
                <div className="flex items-start space-x-2">
                  <div className="w-8 h-8 rounded-full bg-slate-600 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <div className="bg-slate-700 rounded-lg px-4 py-3 border-l-4 border-slate-500">
                    <div className="flex items-center gap-3 text-sm text-slate-400">
                      <span className="tabular-nums">{t('chat.typing')}</span>
                      <div className="flex gap-1.5" aria-hidden>
                        <span className="inline-block h-2 w-2 rounded-full bg-emerald-400/90 animate-bounce [animation-duration:1s]" />
                        <span
                          className="inline-block h-2 w-2 rounded-full bg-emerald-400/90 animate-bounce [animation-duration:1s]"
                          style={{ animationDelay: '0.2s' }}
                        />
                        <span
                          className="inline-block h-2 w-2 rounded-full bg-emerald-400/90 animate-bounce [animation-duration:1s]"
                          style={{ animationDelay: '0.4s' }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Agent Progress */}
              {agentProgress.length > 0 && (
                <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                  <div className="text-xs text-slate-400 mb-2 flex items-center space-x-1">
                    <Activity className="w-3 h-3" />
                    <span>{t('chat.agentsWorking')}</span>
                  </div>
                  <div className="space-y-1">
                    {agentProgress.map((progress, idx) => (
                      <div key={idx} className="flex items-center space-x-2 text-xs">
                        <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                        <span className="text-slate-300">{progress?.agent ?? 'Agent'}:</span>
                        <span className="text-slate-400">{progress?.status ?? ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {showScrollDown && (
          <button
            type="button"
            className="absolute bottom-4 right-4 z-10 flex h-11 w-11 items-center justify-center rounded-full border border-crypto-cyan/40 bg-zinc-900/95 text-crypto-cyan shadow-lg backdrop-blur-md transition hover:bg-zinc-800 hover:border-crypto-cyan/60"
            aria-label={t('chat.scrollToBottom')}
            onClick={() => {
              stickToBottomRef.current = true
              scrollChatToBottom()
              window.setTimeout(updateStickFromScroll, 50)
            }}
          >
            <ChevronDown className="h-5 w-5 shrink-0" strokeWidth={2.25} />
          </button>
        )}
        </div>
      </div>

      {/* Right: grafik / analiz — kendi içinde kayar; sol sohbeti taşımaz */}
      <div className="chat-scroll-y min-h-0 min-w-0 flex-1 overflow-x-hidden overscroll-y-contain bg-zinc-950/30 pb-36 md:min-h-0 md:pb-0">
        {selectedCoin ? (
          <div className="p-6 space-y-6">
            {/* Coin Header */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center justify-between mb-4">
                <h1 className="text-3xl font-bold text-white">{coinDetails?.symbol || selectedCoin}</h1>
                {coinDetails?.ticker && (
                  <div className={`flex items-center space-x-2 text-2xl font-bold ${
                    (coinDetails.ticker.change_24h || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {(coinDetails.ticker.change_24h || 0) >= 0 ? (
                      <TrendingUp className="w-6 h-6" />
                    ) : (
                      <TrendingDown className="w-6 h-6" />
                    )}
                    <span>${formatUsd(coinDetails.ticker.price, 2, 2)}</span>
                    <span className="text-lg">
                      (
                      {coinDetails.ticker.change_24h != null && coinDetails.ticker.change_24h !== ''
                        ? `${Number(coinDetails.ticker.change_24h) >= 0 ? '+' : ''}${fmtFixed(coinDetails.ticker.change_24h, 2)}%`
                        : 'N/A'}
                      )
                    </span>
                  </div>
                )}
              </div>
              
              {coinDetails?.ticker && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">{t('chat.high24h')}</div>
                    <div className="text-lg font-semibold text-white">
                      ${formatUsd(coinDetails.ticker.high_24h, 2, 2)}
                    </div>
                  </div>
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">{t('chat.low24h')}</div>
                    <div className="text-lg font-semibold text-white">
                      ${formatUsd(coinDetails.ticker.low_24h, 2, 2)}
                    </div>
                  </div>
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">{t('chat.vol24h')}</div>
                    <div className="text-lg font-semibold text-white">
                      ${formatUsd(coinDetails.ticker.volume_24h, 0, 0)}
                    </div>
                  </div>
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">{t('chat.exchange')}</div>
                    <div className="text-lg font-semibold text-white">
                      {typeof coinDetails.ticker.exchange === 'string'
                        ? coinDetails.ticker.exchange.toUpperCase()
                        : String(coinDetails.ticker.exchange ?? 'N/A')}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* TradingView Chart */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                <Activity className="w-5 h-5" />
                <span>{t('chat.priceChart')}</span>
              </h3>
              <div className="w-full">
                <TradingViewWidget symbol={selectedCoin} exchange="BINANCE" />
              </div>
            </div>

            {/* Technical Analysis */}
            {coinDetails?.analysis && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                  <BarChart3 className="w-5 h-5" />
                  <span>{t('chat.techAnalysisTitle')}</span>
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {coinDetails?.analysis?.rsi && (
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">RSI (14)</div>
                      <div className={`text-2xl font-bold ${
                        coinDetails.analysis.rsi > 70 ? 'text-red-500' :
                        coinDetails.analysis.rsi < 30 ? 'text-green-500' : 'text-white'
                      }`}>
                        {fmtFixed(coinDetails?.analysis?.rsi, 2, '0.00')}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        {coinDetails?.analysis?.rsi && coinDetails.analysis.rsi > 70
                          ? t('chat.rsiOverbought')
                          : coinDetails?.analysis?.rsi && coinDetails.analysis.rsi < 30
                            ? t('chat.rsiOversold')
                            : t('chat.rsiNormal')}
                      </div>
                    </div>
                  )}
                  {coinDetails?.analysis?.macd && (
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">MACD</div>
                      <div className={`text-2xl font-bold ${
                        (coinDetails?.analysis?.macd?.macd || 0) > (coinDetails?.analysis?.macd?.signal || 0) 
                          ? 'text-green-500' : 'text-red-500'
                      }`}>
                        {fmtFixed(coinDetails?.analysis?.macd?.macd, 4, 'N/A')}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        {t('chat.macdSignal')} {fmtFixed(coinDetails?.analysis?.macd?.signal, 4, 'N/A')}
                      </div>
                    </div>
                  )}
                  {coinDetails?.analysis?.bollinger_bands && (
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">Bollinger Bands</div>
                      <div className="text-xs text-slate-300 space-y-1">
                        <div>
                          {t('chat.bbUpper')}: ${fmtFixed(coinDetails?.analysis?.bollinger_bands?.upper, 2)}
                        </div>
                        <div>
                          {t('chat.bbMiddle')}: ${fmtFixed(coinDetails?.analysis?.bollinger_bands?.middle, 2)}
                        </div>
                        <div>
                          {t('page.dashboard.bbLowerShort')}: ${fmtFixed(coinDetails?.analysis?.bollinger_bands?.lower, 2)}
                        </div>
                      </div>
                    </div>
                  )}
                  {coinDetails?.analysis?.price_change_24h && (
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">{t('chat.change24h')}</div>
                      <div className={`text-2xl font-bold ${
                        (coinDetails?.analysis?.price_change_24h || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      }`}>
                        {(coinDetails?.analysis?.price_change_24h || 0) >= 0 ? '+' : ''}
                        {fmtFixed(coinDetails?.analysis?.price_change_24h ?? 0, 2, '0.00')}%
                      </div>
                    </div>
                  )}
                </div>
                
                {coinDetails?.analysis?.signals && Array.isArray(coinDetails.analysis.signals) && coinDetails.analysis.signals.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-700">
                    <div className="flex items-center space-x-2 mb-2">
                      <AlertCircle className="w-4 h-4 text-yellow-500" />
                      <span className="text-sm font-semibold text-yellow-500">{t('chat.tradingSignals')}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {coinDetails.analysis.signals.map((signal: string, index: number) => (
                        <span
                          key={index}
                          className="px-3 py-1 bg-yellow-500/20 text-yellow-500 rounded-full text-xs"
                        >
                          {signal}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Sentiment Analysis */}
            {coinDetails?.sentiment && coinDetails.sentiment.success !== false && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                  <TrendingUp className="w-5 h-5" />
                  <span>{t('chat.sentimentSectionTitle')}</span>
                </h3>
                {coinDetails?.sentiment?.overall_sentiment ? (
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm text-slate-400 mb-1">{t('chat.generalSentiment')}</div>
                        <div className={`text-2xl font-bold ${
                          (() => {
                            const s = (coinDetails?.sentiment?.overall_sentiment?.sentiment ?? '')
                              .toString()
                              .toLowerCase()
                            return s === 'positive'
                              ? 'text-green-500'
                              : s === 'negative'
                                ? 'text-red-500'
                                : 'text-slate-400'
                          })()
                        }`}>
                          {(() => {
                            const s = (coinDetails?.sentiment?.overall_sentiment?.sentiment ?? '')
                              .toString()
                              .toLowerCase()
                            if (s === 'positive') return t('chat.sentiment.positive')
                            if (s === 'negative') return t('chat.sentiment.negative')
                            if (s === 'neutral' || s === '') return t('chat.sentiment.neutral')
                            return coinDetails?.sentiment?.overall_sentiment?.sentiment != null
                              ? String(coinDetails.sentiment.overall_sentiment.sentiment)
                              : t('chat.sentiment.neutral')
                          })()}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm text-slate-400 mb-1">{t('chat.scoreLabel')}</div>
                        <div className="text-xl font-semibold text-white">
                          {fmtFixed(coinDetails?.sentiment?.overall_sentiment?.score, 4, '0.0000')}
                        </div>
                        <div className="text-xs text-slate-400 mt-1">
                          {t('chat.sentimentConfidence')}{' '}
                          {fmtFixed(
                            Number(coinDetails?.sentiment?.overall_sentiment?.confidence ?? 0) * 100,
                            1,
                            '0',
                          )}
                          %
                        </div>
                        {coinDetails?.sentiment?.overall_sentiment?.sample_size && (
                          <div className="text-xs text-slate-400 mt-1">
                            {t('chat.sampleLabel')} {coinDetails.sentiment.overall_sentiment.sample_size}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-700 rounded-lg p-4 text-center text-slate-400">
                    {t('chat.sentimentLoading')}
                  </div>
                )}
                {coinDetails?.sentiment?.sources && Array.isArray(coinDetails.sentiment.sources) && coinDetails.sentiment.sources.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-700">
                    <div className="text-sm text-slate-400 mb-2">
                      {t('chat.sourcesFound').replace('{n}', String(coinDetails.sentiment.sources.length))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Risk Assessment */}
            {coinDetails?.risk && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                  <AlertCircle className="w-5 h-5" />
                  <span>{t('chat.riskTitle')}</span>
                </h3>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <div className="text-sm text-slate-400 mb-1">{t('chat.riskScore')}</div>
                      <div className={`text-3xl font-bold ${
                        (coinDetails?.risk?.risk_score || 0) >= 70 ? 'text-red-500' :
                        (coinDetails?.risk?.risk_score || 0) >= 40 ? 'text-yellow-500' : 'text-green-500'
                      }`}>
                        {fmtFixed(coinDetails?.risk?.risk_score ?? 0, 1, '0.0')}/100
                      </div>
                    </div>
                  </div>
                  {coinDetails?.risk?.warnings && Array.isArray(coinDetails.risk.warnings) && coinDetails.risk.warnings.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-600">
                      <div className="text-sm text-slate-400 mb-2 font-medium">⚠️ {t('chat.warningsTitle')}:</div>
                      <div className="space-y-2">
                        {coinDetails.risk.warnings.map((warning: string, index: number) => (
                          <div key={index} className="text-sm text-yellow-400 flex items-start space-x-2">
                            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                            <span>{warning || t('chat.warningFallback')}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Prediction */}
            {coinDetails?.prediction && coinDetails.prediction.success !== false && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                  <Sparkles className="w-5 h-5" />
                  <span>{t('chat.forecastTitle')}</span>
                  {coinDetails?.prediction?.model && (
                    <span className="text-xs text-slate-400 ml-2">({coinDetails.prediction.model})</span>
                  )}
                </h3>
                {coinDetails?.prediction?.predicted_change ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">{t('chat.predPrice7d')}</div>
                      <div className="text-2xl font-bold text-white">
                        ${formatUsd(coinDetails?.prediction?.predicted_change?.last_period_price, 2, 2)}
                      </div>
                      {coinDetails?.prediction?.current_price != null &&
                        coinDetails.prediction.current_price !== '' && (
                        <div className="text-xs text-slate-400 mt-1">
                          {t('chat.currentPriceLabel')} ${formatUsd(coinDetails.prediction.current_price, 2, 2)}
                        </div>
                      )}
                    </div>
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">{t('chat.expectedChange')}</div>
                      <div className={`text-2xl font-bold ${
                        (coinDetails?.prediction?.predicted_change?.percentage || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                      }`}>
                        {(coinDetails?.prediction?.predicted_change?.percentage || 0) >= 0 ? '+' : ''}
                        {fmtFixed(coinDetails?.prediction?.predicted_change?.percentage ?? 0, 2, '0.00')}%
                      </div>
                      {coinDetails?.prediction?.predicted_change?.absolute && (
                        <div className="text-xs text-slate-400 mt-1">
                          ${(coinDetails.prediction.predicted_change.absolute || 0) >= 0 ? '+' : ''}
                          {fmtFixed(coinDetails.prediction.predicted_change.absolute ?? 0, 2, '0.00')}
                        </div>
                      )}
                    </div>
                    <div className="bg-slate-700 rounded-lg p-4">
                      <div className="text-sm text-slate-400 mb-1">{t('chat.modelAccuracy')}</div>
                      <div className="text-2xl font-bold text-white">
                        {fmtFixed(coinDetails?.prediction?.metrics?.directional_accuracy ?? 0, 2, '0.00')}%
                      </div>
                      {coinDetails?.prediction?.metrics?.mae && (
                        <div className="text-xs text-slate-400 mt-1">
                          MAE: {fmtFixed(coinDetails.prediction.metrics.mae, 4, 'N/A')}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-700 rounded-lg p-4 text-center text-slate-400">
                    {coinDetails.prediction.error || t('chat.predictionLoading')}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Bot className="w-16 h-16 text-slate-600 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-slate-400 mb-2">{t('chat.coinPanelTitle')}</h3>
              <p className="text-slate-500">{t('chat.coinPanelHint')}</p>
            </div>
          </div>
        )}
      </div>
      </div>

      {/* Sabit giriş: mobilde tam genişlik; masaüstünde yalnız sohbet sütunu (sağdaki grafik kaydırmasından ayrı) */}
      <div
        className="fixed bottom-0 left-0 z-40 w-full border-t border-white/[0.1] bg-zinc-950/[0.98] shadow-[0_-12px_48px_rgba(0,0,0,0.55)] backdrop-blur-xl md:right-auto md:w-[38%] lg:w-1/3"
        style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom, 0px))' }}
      >
        <div className="border-t border-white/[0.06] px-4 pt-3">
          <div className="flex gap-2">
            <VoiceAssistant
              onCommandProcessed={(response, agentData) => {
                stickToBottomRef.current = true
                const assistantMessage: Message = {
                  role: 'assistant',
                  content: response,
                  agent: coerceAgentName(agentData?.agent ?? 'ChatAgent'),
                  coinData: agentData,
                }
                setMessages((prev) => [...prev, assistantMessage])

                if (agentData?.symbol) {
                  setSelectedCoin(agentData.symbol)
                  loadCoinDetails(agentData.symbol)
                }
              }}
              disabled={isLoading}
            />
            <textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder={t('chat.placeholder')}
              className="max-h-36 min-h-[4.5rem] flex-1 resize-y rounded-xl border border-white/[0.08] bg-zinc-950/80 px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:border-crypto-cyan/35 focus:outline-none focus:ring-1 focus:ring-crypto-cyan/25"
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="btn-crypto shrink-0 self-stretch px-5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Reasoning Log Modal */}
      {showReasoningLog && currentReasoningLog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg border border-slate-700 max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-2">
                <Brain className="w-5 h-5 text-primary-500" />
                <h3 className="text-xl font-semibold text-white">{t('chat.reasoningModalTitle')}</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowReasoningLog(false)}
                className="text-slate-400 hover:text-white"
                aria-label={t('common.close')}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Summary */}
              <div className="bg-slate-700 rounded-lg p-4">
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <div className="text-slate-400 mb-1">{t('chat.totalDuration')}</div>
                    <div className="text-white font-semibold">
                      {fmtFixed(currentReasoningLog.total_duration_ms, 0, '0')}ms
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-400 mb-1">{t('chat.stepCount')}</div>
                    <div className="text-white font-semibold">{currentReasoningLog.step_count}</div>
                  </div>
                  <div>
                    <div className="text-slate-400 mb-1">{t('chat.agentCount')}</div>
                    <div className="text-white font-semibold">{currentReasoningLog.agents_involved.length}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(currentReasoningLog.agents_involved || []).map((agent, idx) => (
                    <span key={idx} className="px-2 py-1 bg-primary-500/20 text-primary-400 rounded text-xs">
                      {String(agent)}
                    </span>
                  ))}
                </div>
              </div>

              {/* Steps */}
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-slate-300">{t('chat.stepsHeading')}:</h4>
                {(currentReasoningLog.steps || []).map((step, idx) => {
                  const st = step ?? ({} as ReasoningStep)
                  const icon = {
                    data_fetch: '📥',
                    analysis: '🔍',
                    decision: '✅',
                    warning: '⚠️',
                    coordination: '🤝',
                    tool_use: '🔧'
                  }[st.type] || '•'
                  
                  const color = {
                    data_fetch: 'text-blue-400',
                    analysis: 'text-purple-400',
                    decision: 'text-green-400',
                    warning: 'text-yellow-400',
                    coordination: 'text-pink-400',
                    tool_use: 'text-orange-400'
                  }[st.type] || 'text-slate-400'
                  
                  return (
                    <div key={idx} className="bg-slate-700 rounded-lg p-3 border-l-4 border-primary-500">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span className="text-lg">{icon}</span>
                          <span className={`font-semibold ${color}`}>{st.agent ?? '—'}</span>
                          <span className="text-xs text-slate-500">({st.type})</span>
                        </div>
                        {st.duration_ms != null && Number.isFinite(Number(st.duration_ms)) && (
                          <div className="flex items-center space-x-1 text-xs text-slate-400">
                            <Clock className="w-3 h-3" />
                            <span>{fmtFixed(st.duration_ms, 0, '0')}ms</span>
                          </div>
                        )}
                      </div>
                      <div className="text-sm text-slate-300 mb-2">{String(st.description ?? '')}</div>
                      {st.data && typeof st.data === 'object' && Object.keys(st.data).length > 0 && (
                        <details className="text-xs text-slate-400">
                          <summary className="cursor-pointer hover:text-slate-300">Detaylar</summary>
                          <pre className="mt-2 p-2 bg-slate-800 rounded overflow-x-auto">
                            {(() => {
                              try {
                                return JSON.stringify(st.data, null, 2)
                              } catch {
                                return t('chat.dataUnavailable')
                              }
                            })()}
                          </pre>
                        </details>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

