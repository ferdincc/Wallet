import axios from 'axios'

function resolveApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_URL
  if (raw != null && String(raw).trim() !== '') {
    return String(raw).replace(/\/$/, '')
  }
  if (import.meta.env.DEV) return '/api/v1'
  return 'http://127.0.0.1:8000/api/v1'
}

const API_BASE_URL = resolveApiBaseUrl()

const SIMULATION_HTTP_TIMEOUT_MS = 10000
const WATCH_PORTFOLIO_HTTP_TIMEOUT_MS = 130000

function nodeApiOrigin(): string {
  if (import.meta.env.VITE_BACKTEST_API_URL) {
    return import.meta.env.VITE_BACKTEST_API_URL.replace(/\/api\/backtest\/?$/, '')
  }
  if (import.meta.env.VITE_NEWS_API_URL) {
    return import.meta.env.VITE_NEWS_API_URL.replace(/\/api\/news\/?$/, '')
  }
  if (import.meta.env.DEV) return ''
  return 'http://127.0.0.1:3010'
}

const BACKTEST_API_BASE_URL = `${nodeApiOrigin()}/api/backtest`
const NEWS_NODE_API_BASE_URL = `${nodeApiOrigin()}/api/news`
const CAMPAIGNS_NODE_API_BASE_URL = `${nodeApiOrigin()}/api/campaigns`
const WALLET_NODE_API_BASE_URL = `${nodeApiOrigin()}/api/wallet`

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 90000,
})

const backtestApi = axios.create({
  baseURL: BACKTEST_API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,
})

const newsNodeAxios = axios.create({
  baseURL: NEWS_NODE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

const campaignsNodeAxios = axios.create({
  baseURL: CAMPAIGNS_NODE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

const walletNodeAxios = axios.create({
  baseURL: WALLET_NODE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 180000,
})

export interface WalletAssetRow {
  symbol: string
  chain: string
  chainLabel: string
  amount: number
  usdValue: number
  change24hPct: number | null
  contract?: string
  logoUri?: string | null
}

export interface WalletTxRow {
  ts: number
  dateIso: string
  chain: string
  chainLabel: string
  tokenSymbol: string
  amount: number
  /** Örn. "0.5 ETH", "100 USDC" */
  amountLabel?: string
  usdValue: number
  direction: 'IN' | 'OUT'
  hash: string
  type: 'native' | 'erc20'
}

export interface ChainWalletStat {
  chain: string
  chainLabel: string
  portfolioUsd: number
  in30dUsd: number
  out30dUsd: number
  net30dUsd: number
  in90dUsd: number
  out90dUsd: number
  net90dUsd: number
  lifetimeNetUsd: number
}

export interface WalletInsight {
  totalTransfersIndexed: number
  txPerChain: Record<string, number>
  dominantChain: string
  tokenCount: number
  chainsScanned: string[]
}

export interface WalletTotalsShape {
  minUsd: number
  portfolioUsd: number
  in30dUsd: number
  out30dUsd: number
  net30dUsd: number
  in90dUsd: number
  out90dUsd: number
  net90dUsd: number
  lifetimeNetUsd: number
}

export interface WalletContextPayload {
  version: 1
  address: string
  scannedAt: string
  totals: WalletTotalsShape
  chainStats: ChainWalletStat[]
  walletInsight: WalletInsight
}

export interface WalletAnalyzeResponse {
  address: string
  totals: WalletTotalsShape
  assets: WalletAssetRow[]
  chainStats: ChainWalletStat[]
  transactions: WalletTxRow[]
  scannedChains: string[]
  warning: string | null
  scannedAt: string
  walletInsight: WalletInsight
  llmContext: string
  walletContext?: WalletContextPayload
}

export const walletNodeApi = {
  analyze: async (
    address: string,
    chain: string = 'all',
    minUsd: number = 10,
  ): Promise<WalletAnalyzeResponse> => {
    const { data } = await walletNodeAxios.post<WalletAnalyzeResponse>('/analyze', {
      address,
      chain,
      minUsd,
    })
    return data
  },
}

export interface Ticker {
  symbol: string
  price: number
  high_24h?: number
  low_24h?: number
  volume_24h?: number
  change_24h?: number
  exchange: string
  timestamp: string
}

export interface TechnicalAnalysis {
  current_price: number
  rsi?: number
  macd?: {
    macd: number
    signal: number
    histogram: number
  }
  bollinger_bands?: {
    upper: number
    middle: number
    lower: number
  }
  signals: string[]
  price_change_24h?: number
}

export const marketsApi = {
  getTicker: async (symbol: string, exchange: string = 'binance'): Promise<Ticker> => {
    const response = await api.get(`/markets/ticker/${symbol}`, {
      params: { exchange },
    })
    return response.data
  },

  getTickers: async (symbols: string[], exchange: string = 'binance'): Promise<Record<string, Ticker>> => {
    const response = await api.get('/markets/tickers', {
      params: { symbols: symbols.join(','), exchange },
    })
    return response.data.tickers
  },

  getAnalysis: async (symbol: string, exchange: string = 'binance', timeframe: string = '1h') => {
    const response = await api.get(`/markets/analysis/${symbol}`, {
      params: { exchange, timeframe },
    })
    return response.data
  },

  getOHLCV: async (symbol: string, timeframe: string = '1h', limit: number = 100, exchange: string = 'binance') => {
    const response = await api.get(`/markets/ohlcv/${symbol}`, {
      params: { timeframe, limit, exchange },
    })
    return response.data
  },

  getAnomalies: async (symbol: string, timeframe: string = '1h', exchange: string = 'binance', anomalyType: 'price' | 'volume' = 'volume') => {
    const response = await api.get(`/markets/anomalies/${symbol}`, {
      params: { timeframe, exchange, anomaly_type: anomalyType },
    })
    return response.data
  },
}

export type ChatHistoryTurn = { role: 'user' | 'assistant'; content: string }

export const chatApi = {
  sendMessage: async (opts: {
    message: string
    user_id?: number
    wallet_address?: string | null
    walletContext?: string | null
    conversationHistory?: ChatHistoryTurn[]
    lastAgentContext?: string | null
    locale?: 'en'
  }) => {
    const body: Record<string, unknown> = {
      message: opts.message,
      query: opts.message,
    }
    if (opts.user_id != null) body.user_id = opts.user_id
    if (opts.wallet_address) body.wallet_address = opts.wallet_address
    if (opts.walletContext != null && String(opts.walletContext).trim() !== '') {
      body.walletContext = String(opts.walletContext).trim()
    }
    if (opts.conversationHistory && opts.conversationHistory.length > 0) {
      body.conversationHistory = opts.conversationHistory
    }
    if (opts.lastAgentContext != null && opts.lastAgentContext.trim() !== '') {
      body.lastAgentContext = opts.lastAgentContext.trim()
    }
    // Always send locale so the backend never falls back to query-only heuristics.
    body.locale = opts.locale ?? 'en'
    const response = await api.post('/chat/message', body)
    return response.data
  },
}

export const newsApi = {
  getSentiment: async (
    symbol: string,
    include_news: boolean = true,
    include_reddit: boolean = true,
    hours: number = 24,
    locale: string = 'en',
  ) => {
    const response = await api.get('/news/sentiment', {
      params: { symbol, include_news, include_reddit, hours, locale },
    })
    return response.data
  },
}

export const predictionApi = {
  getPrediction: async (
    symbol: string,
    exchange: string = 'binance',
    timeframe: string = '1h',
    periods: number = 7,
    model: string = 'ensemble',
    lang: string = 'en',
  ) => {
    const response = await api.get('/predict', {
      params: { symbol, exchange, timeframe, periods, model, lang },
    })
    return response.data
  },
  getShortTerm: async (symbol: string, exchange: string = 'binance', lang: string = 'en') => {
    const response = await api.get('/predict/short', {
      params: { symbol, exchange, lang },
    })
    return response.data
  },
  getMediumTerm: async (symbol: string, exchange: string = 'binance', lang: string = 'en') => {
    const response = await api.get('/predict/medium', {
      params: { symbol, exchange, lang },
    })
    return response.data
  },
  
  getBacktestStats: async (symbol?: string, model_type?: string, days: number = 30) => {
    const response = await api.get('/predict/backtest/stats', {
      params: { symbol, model_type, days },
    })
    return response.data
  },
  
  getRecentPredictions: async (symbol?: string, limit: number = 10) => {
    const response = await api.get('/predict/backtest/recent', {
      params: { symbol, limit },
    })
    return response.data
  },
}

export const voiceApi = {
  processCommand: async (transcript: string, user_id?: number) => {
    const response = await api.post('/voice/command', {
      transcript,
      user_id,
    })
    return response.data
  },
  
  generateResponse: async (text: string) => {
    const response = await api.post('/voice/response', {
      text,
    })
    return response.data
  },
}

export const alertsApi = {
  checkAlerts: async (symbols: string[], exchange: string = 'binance') => {
    const response = await api.get('/alerts/check', {
      params: { symbols: symbols.join(','), exchange },
    })
    return response.data
  },
  
  getRecentAlerts: async (limit: number = 10) => {
    const response = await api.get('/alerts/recent', {
      params: { limit },
    })
    return response.data
  },
}

export const ablationApi = {
  compareModels: async (symbol: string, days: number = 30) => {
    const response = await api.get('/ablation/compare', {
      params: { symbol, days },
    })
    return response.data
  },
  
  getStudySummary: async (symbols: string[], days: number = 30) => {
    const response = await api.post('/ablation/summary', {
      symbols,
      days,
    })
    return response.data
  },
}

export interface BacktestSummary {
  model: string
  avgMAPE: number
  avgRMSE: number
  directionAccuracy: number
  totalPredictions: number
  results: Array<{
    date: string
    predicted_price: number
    actual_price: number
    mape: number
    direction_correct: boolean
  }>
  error?: string
}

export interface BacktestRunResponse {
  symbol: string
  startDate: string
  endDate: string
  models: string[]
  summaries: BacktestSummary[]
}

export interface NewsItemNode {
  title: string
  description?: string
  url: string
  source: string
  publishedAt: string
  imageUrl?: string
  score?: number
  subreddit?: string
  sentiment?: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
  sentimentScore?: number
  matchedWords?: string[]
}

export interface FearGreedNode {
  value: number
  value_classification: string
  timestamp: string
}

export type CampaignSourceNode = 'galxe' | 'layer3' | 'coinmarketcap' | 'nitter'

export type CampaignTypeTagNode =
  | 'AIRDROP'
  | 'TESTNET'
  | 'AI_CONTENT'
  | 'NFT_MINT'
  | 'REFERRAL'
  | 'LAUNCH'
  | 'OTHER'

export interface CampaignItemNode {
  id: string
  source: CampaignSourceNode
  title: string
  description?: string
  url: string
  startTime?: string
  endTime?: string
  rewardType?: string
  rewardAmount?: string
  text?: string
  author?: string
  publishedAt?: string
  dateAdded?: string
  typeTag: CampaignTypeTagNode
  importanceScore: number
}

export const campaignsNodeApi = {
  getAll: async (params?: {
    type?: string
    source?: string
  }): Promise<{ success: boolean; count: number; items: CampaignItemNode[] }> => {
    const response = await campaignsNodeAxios.get('/', { params: params || {} })
    return response.data
  },
  getTrending: async (): Promise<{ success: boolean; count: number; items: CampaignItemNode[] }> => {
    const response = await campaignsNodeAxios.get('/trending')
    return response.data
  },
}

export const newsNodeApi = {
  getLatest: async (): Promise<{ success: boolean; count: number; items: NewsItemNode[] }> => {
    const response = await newsNodeAxios.get('/latest')
    return response.data
  },
  getBySource: async (source: string): Promise<{ success: boolean; count: number; items: NewsItemNode[] }> => {
    const response = await newsNodeAxios.get('/', { params: { source } })
    return response.data
  },
  getNews: async (params: { source?: string; coin?: string }): Promise<{ success: boolean; count: number; items: NewsItemNode[] }> => {
    const q: Record<string, string> = {}
    if (params.source && params.source !== 'all') q.source = params.source
    if (params.coin && params.coin !== 'all') q.coin = params.coin
    const response = await newsNodeAxios.get('/', { params: q })
    return response.data
  },
  getFearGreed: async (): Promise<{ success: boolean; data: FearGreedNode }> => {
    const response = await newsNodeAxios.get('/fear-greed')
    return response.data
  },
}

export const backtestNodeApi = {
  run: async (payload: {
    symbol: string
    models: string[]
    startDate: string
    endDate: string
    windowDays?: number
  }): Promise<BacktestRunResponse> => {
    const response = await backtestApi.post('/run', payload)
    return response.data
  },
}

export const analyzeApi = {
  comprehensiveAnalysis: async (symbol: string, exchange: string = 'binance', include_sentiment: boolean = true, include_prediction: boolean = true, include_technical: boolean = true) => {
    const response = await api.post('/analyze', null, {
      params: { symbol, exchange, include_sentiment, include_prediction, include_technical },
    })
    return response.data
  },
  getAlerts: async (portfolio_id: number) => {
    const response = await api.get('/alerts', {
      params: { portfolio_id },
    })
    return response.data
  },
}

export const simulationApi = {
  createPortfolio: async (user_id: number, name: string = 'Default Portfolio', initial_balance: number = 10000) => {
    const response = await api.post(
      '/simulation/portfolios',
      {
        user_id,
        name,
        initial_balance,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  getPortfolios: async (user_id?: number) => {
    const params = user_id ? { user_id } : {}
    const response = await api.get('/simulation/portfolios', {
      params,
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  executeTransaction: async (
    portfolio_id: number,
    symbol: string,
    transaction_type: 'buy' | 'sell',
    quantity: number,
    exchange: string = 'binance'
  ) => {
    const response = await api.post(
      '/simulation/transactions',
      {
        portfolio_id,
        symbol,
        transaction_type,
        quantity,
        exchange,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  getPositions: async (portfolio_id: number) => {
    const response = await api.get(`/simulation/portfolios/${portfolio_id}/positions`, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getTransactions: async (portfolio_id: number) => {
    const response = await api.get(`/simulation/portfolios/${portfolio_id}/transactions`, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRiskAnalysis: async (portfolio_id: number) => {
    const response = await api.get(`/simulation/portfolios/${portfolio_id}/risk`, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  createUser: async (username: string, email?: string) => {
    const response = await api.post(
      '/simulation/users',
      {
        username,
        email,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  checkTransactionRisk: async (
    portfolio_id: number,
    symbol: string,
    transaction_type: 'buy' | 'sell' | 'limit_buy' | 'limit_sell',
    quantity: number,
    price: number,
    exchange: string = 'binance'
  ) => {
    const response = await api.post(
      '/simulation/transactions/risk-check',
      {
        portfolio_id,
        symbol,
        transaction_type,
        quantity,
        price,
        exchange,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  createLimitOrder: async (
    portfolio_id: number,
    symbol: string,
    order_type: 'limit_buy' | 'limit_sell',
    quantity: number,
    limit_price: number,
    exchange: string = 'binance'
  ) => {
    const response = await api.post(
      '/simulation/orders',
      {
        portfolio_id,
        symbol,
        order_type,
        quantity,
        limit_price,
        exchange,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  getOrders: async (portfolio_id: number) => {
    const response = await api.get(`/simulation/portfolios/${portfolio_id}/orders`, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  cancelOrder: async (order_id: number) => {
    const response = await api.post(`/simulation/orders/${order_id}/cancel`, null, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  processOrders: async (portfolio_id?: number) => {
    const params = portfolio_id ? { portfolio_id } : {}
    const response = await api.post('/simulation/orders/process', null, {
      params,
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  createExchangeCredentials: async (
    user_id: number,
    exchange: string,
    api_key: string,
    api_secret: string,
    passphrase?: string
  ) => {
    const response = await api.post(
      '/simulation/exchange-credentials',
      {
        user_id,
        exchange,
        api_key,
        api_secret,
        passphrase,
        trading_mode: 'read_only',
      },
      { timeout: 5000 }
    )
    return response.data
  },

  getExchangeCredentials: async (user_id: number) => {
    const response = await api.get('/simulation/exchange-credentials', {
      params: { user_id },
      timeout: 5000,
    })
    return response.data
  },

  deleteExchangeCredentials: async (credential_id: number, user_id: number) => {
    const response = await api.delete(`/simulation/exchange-credentials/${credential_id}`, {
      params: { user_id },
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRealExchangeBalance: async (user_id: number, exchange: string) => {
    const response = await api.get('/simulation/real-exchange/balance', {
      params: { user_id, exchange },
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRealExchangePositions: async (user_id: number, exchange: string) => {
    const response = await api.get('/simulation/real-exchange/positions', {
      params: { user_id, exchange },
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRealExchangeOrders: async (user_id: number, exchange: string, symbol?: string) => {
    const params: any = { user_id, exchange }
    if (symbol) params.symbol = symbol
    const response = await api.get('/simulation/real-exchange/orders', {
      params,
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRealExchangeWatchPortfolio: async (user_id: number, exchange: string) => {
    const response = await api.get('/simulation/real-exchange/watch-portfolio', {
      params: { user_id, exchange },
      timeout: WATCH_PORTFOLIO_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  executeRealTrade: async (
    user_id: number,
    exchange: string,
    symbol: string,
    side: 'buy' | 'sell',
    amount: number,
    order_type: 'market' | 'limit' = 'market',
    price?: number
  ) => {
    const response = await api.post(
      '/simulation/real-exchange/trade',
      {
        user_id,
        exchange,
        symbol,
        side,
        amount,
        order_type,
        price,
      },
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },

  getPortfolioRebalancing: async (portfolio_id: number) => {
    const response = await api.get(`/simulation/portfolios/${portfolio_id}/rebalancing`, {
      timeout: SIMULATION_HTTP_TIMEOUT_MS,
    })
    return response.data
  },

  getRebalancingPlan: async (portfolio_id: number, target_allocation?: { [key: string]: number }) => {
    const response = await api.post(
      `/simulation/portfolios/${portfolio_id}/rebalancing/plan`,
      target_allocation || {},
      { timeout: SIMULATION_HTTP_TIMEOUT_MS }
    )
    return response.data
  },
}

export default api

