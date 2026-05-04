import { useEffect, useState } from 'react'
import { simulationApi } from '../services/api'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { readStoredLocale, translate } from '../i18n/messages'
import {
  Plus,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  ArrowUp,
  ArrowDown,
  X,
  Settings,
  Eye,
  Zap,
  Target,
  PlayCircle,
  Trash2,
} from 'lucide-react'

/** Sabit kullanıcı; üretimde oturumdan gelmeli. API anahtarı silme bu kullanıcıya bağlıdır. */
const SIMULATION_USER_ID = 1

interface Portfolio {
  id: number
  name: string
  initial_balance: number
  current_balance: number
}

interface Position {
  symbol: string
  quantity: number
  avg_buy_price: number
  current_price: number
  position_value: number
  unrealized_pnl: number
  unrealized_pnl_percent: number
}

type TradingMode = 'paper_trading' | 'read_only'

interface WatchHolding {
  asset: string
  symbol_pair: string
  quantity: number
  buy_price: number | null
  buy_time_iso: string | null
  current_price: number | null
  total_value_usd: number | null
  pnl_usd: number | null
  pnl_percent: number | null
  note: string | null
}

interface WatchSummary {
  total_portfolio_usd: number
  total_coins_value_usd: number
  usdt_free: number
  total_pnl_usd: number
  total_pnl_percent: number | null
  cost_basis_usd: number | null
}

/** FastAPI detail: string | {msg}[] | object */
function formatApiDetail(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((x: { msg?: string; loc?: unknown }) => x?.msg || JSON.stringify(x))
      .join('; ')
  }
  if (d != null && typeof d === 'object') return JSON.stringify(d)
  return e?.message || translate(readStoredLocale(), 'sim.errorRequest')
}

export default function Simulation() {
  const { t } = useAppPreferences()
  const dateLocale = 'en-US'
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [selectedPortfolio, setSelectedPortfolio] = useState<Portfolio | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [transactions, setTransactions] = useState<any[]>([])
  const [riskAnalysis, setRiskAnalysis] = useState<any>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newPortfolioName, setNewPortfolioName] = useState('')
  const [newPortfolioBalance, setNewPortfolioBalance] = useState(10000)
  const [showTradeModal, setShowTradeModal] = useState(false)
  const [tradeSymbol, setTradeSymbol] = useState('BTC/USDT')
  const [tradeType, setTradeType] = useState<'buy' | 'sell' | 'limit_buy' | 'limit_sell'>('buy')
  const [tradeQuantity, setTradeQuantity] = useState('')
  const [tradeLimitPrice, setTradeLimitPrice] = useState('')
  const [tradeLoading, setTradeLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showRiskWarning, setShowRiskWarning] = useState(false)
  const [riskWarningData, setRiskWarningData] = useState<any>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [rebalancingAnalysis] = useState<any>(null)
  const [showRebalancing, setShowRebalancing] = useState(false)
  
  // Real Exchange Integration
  const [tradingMode, setTradingMode] = useState<TradingMode>('paper_trading')
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [apiKeyExchange, setApiKeyExchange] = useState('binance')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [apiPassphrase, setApiPassphrase] = useState('')
  const [apiKeyModalError, setApiKeyModalError] = useState<string | null>(null)
  const [apiKeySaving, setApiKeySaving] = useState(false)
  const [flashSuccess, setFlashSuccess] = useState<string | null>(null)
  const [exchangeCredentials, setExchangeCredentials] = useState<any[]>([])
  const [watchPortfolio, setWatchPortfolio] = useState<{
    holdings: WatchHolding[]
    summary: WatchSummary
  } | null>(null)
  const [watchLoading, setWatchLoading] = useState(false)
  const [realOrders, setRealOrders] = useState<any[]>([])
  const [selectedExchange, setSelectedExchange] = useState<string | null>(null)
  const [credentialRemovingId, setCredentialRemovingId] = useState<number | null>(null)

  useEffect(() => {
    loadPortfolios()
    loadExchangeCredentials()
    try {
      const ok = sessionStorage.getItem('okyiss_flash_api_key_ok')
      if (ok) {
        sessionStorage.removeItem('okyiss_flash_api_key_ok')
        setFlashSuccess(ok)
      }
    } catch {
      /* ignore */
    }
  }, [])

  /**
   * Gerçek borsa (Binance) verisi: sayfa açılışında çağrılmaz.
   * Sadece kullanıcı "İzleme Modu"na geçtiğinde ve borsa seçiliyken yüklenir.
   */
  useEffect(() => {
    if (tradingMode === 'read_only' && selectedExchange) {
      loadRealExchangeData()
      const interval = setInterval(() => {
        loadRealExchangeData()
      }, 30000)
      return () => clearInterval(interval)
    }
  }, [tradingMode, selectedExchange])

  useEffect(() => {
    if (selectedPortfolio) {
      loadPortfolioData()
      // Process pending orders periodically
      const interval = setInterval(async () => {
        try {
          await simulationApi.processOrders(selectedPortfolio.id)
          loadPortfolioData()
        } catch (error) {
          console.error('Error processing orders:', error)
        }
      }, 30000) // Every 30 seconds
      
      return () => clearInterval(interval)
    }
  }, [selectedPortfolio])

  useEffect(() => {
    if (showTradeModal && tradeSymbol) {
      loadCurrentPrice(tradeSymbol)
    }
  }, [showTradeModal, tradeSymbol])

  const loadPortfolios = async () => {
    try {
      const data = await simulationApi.getPortfolios()
      setPortfolios(data.portfolios || [])
    } catch (error) {
      console.error('Error loading portfolios:', error)
    }
  }

  const loadPortfolioData = async () => {
    if (!selectedPortfolio) return

    try {
      const [positionsData, transactionsData, riskData, ordersData] = await Promise.all([
        simulationApi.getPositions(selectedPortfolio.id),
        simulationApi.getTransactions(selectedPortfolio.id),
        simulationApi.getRiskAnalysis(selectedPortfolio.id),
        simulationApi.getOrders(selectedPortfolio.id),
      ])

      setPositions(positionsData.positions || [])
      setTransactions(transactionsData.transactions || [])
      setRiskAnalysis(riskData)
      setOrders(ordersData.orders || [])
    } catch (error) {
      console.error('Error loading portfolio data:', error)
    }
  }

  const loadCurrentPrice = async (symbol: string) => {
    try {
      const { marketsApi } = await import('../services/api')
      const ticker = await marketsApi.getTicker(symbol, 'binance')
      setCurrentPrice(ticker.price)
      return ticker.price
    } catch (error) {
      console.error('Error loading current price:', error)
      return null
    }
  }

  const loadExchangeCredentials = async (): Promise<
    Array<{ id: number; exchange: string; trading_mode?: string; is_active?: boolean; created_at?: string }>
  > => {
    try {
      const data = await simulationApi.getExchangeCredentials(SIMULATION_USER_ID)
      const creds = data.credentials || []
      setExchangeCredentials(creds)
      return creds
    } catch (error) {
      console.error('Error loading exchange credentials:', error)
      return []
    }
  }

  const loadRealExchangeData = async () => {
    if (!selectedExchange || selectedExchange !== 'binance') return

    setWatchLoading(true)
    try {
      const [portfolioData, ordersData] = await Promise.all([
        simulationApi.getRealExchangeWatchPortfolio(SIMULATION_USER_ID, selectedExchange),
        simulationApi.getRealExchangeOrders(SIMULATION_USER_ID, selectedExchange),
      ])

      setWatchPortfolio(portfolioData)
      setRealOrders(ordersData.orders || [])
      setError(null)
    } catch (error: unknown) {
      console.error('Error loading watch portfolio — tam detay:', error)
      setWatchPortfolio(null)
      setRealOrders([])
      setError(formatApiDetail(error) || t('sim.errorWatchLoad'))
    } finally {
      setWatchLoading(false)
    }
  }

  const openApiKeyModal = () => {
    setApiKeyModalError(null)
    setShowApiKeyModal(true)
  }

  const handleSaveApiKey = async () => {
    setApiKeyModalError(null)
    if (!apiKey.trim() || !apiSecret.trim()) {
      const msg = t('sim.apiKeyRequired')
      setApiKeyModalError(msg)
      setError(msg)
      return
    }

    setApiKeySaving(true)
    try {
      await simulationApi.createExchangeCredentials(
        SIMULATION_USER_ID,
        apiKeyExchange,
        apiKey,
        apiSecret,
        apiPassphrase || undefined
      )

      setShowApiKeyModal(false)
      setApiKey('')
      setApiSecret('')
      setApiPassphrase('')
      setError(null)

      try {
        localStorage.setItem('okyiss_simulation_exchange', apiKeyExchange)
        sessionStorage.setItem('okyiss_flash_api_key_ok', t('sim.flashApiOk'))
      } catch {
        /* ignore */
      }

      window.location.reload()
    } catch (error: unknown) {
      const ax = error as {
        response?: { status?: number; data?: unknown }
        message?: string
        code?: string
      }
      console.error('[Simulation] API key kayıt hatası — tam detay:', {
        status: ax.response?.status,
        data: ax.response?.data,
        message: ax.message,
        code: ax.code,
        corsOrNetwork:
          ax.message === 'Network Error'
            ? 'Olası: backend kapalı, yanlış URL veya CORS (DEV’de /api/v1 proxy kullanın).'
            : undefined,
      })
      const detail = formatApiDetail(error) || t('sim.apiKeySaveFailed')
      setApiKeyModalError(detail)
      setError(detail)
    } finally {
      setApiKeySaving(false)
    }
  }

  const handleRemoveCredential = async (credentialId: number, exchangeName: string) => {
    if (!window.confirm(t('sim.removeKeyConfirm'))) return
    setCredentialRemovingId(credentialId)
    setApiKeyModalError(null)
    try {
      await simulationApi.deleteExchangeCredentials(credentialId, SIMULATION_USER_ID)
      const creds = await loadExchangeCredentials()
      setFlashSuccess(t('sim.keyRemoved'))
      setError(null)
      const ex = exchangeName.toLowerCase()
      if (tradingMode === 'read_only' && selectedExchange === ex) {
        const still = creds.some((c) => c.exchange?.toLowerCase() === ex)
        if (!still) {
          setTradingMode('paper_trading')
          setSelectedExchange(null)
          setWatchPortfolio(null)
          setRealOrders([])
          try {
            localStorage.removeItem('okyiss_simulation_exchange')
          } catch {
            /* ignore */
          }
        }
      }
    } catch (error: unknown) {
      setApiKeyModalError(formatApiDetail(error) || t('sim.removeKeyFailed'))
    } finally {
      setCredentialRemovingId(null)
    }
  }

  const handleCreatePortfolio = async () => {
    try {
      await simulationApi.createPortfolio(SIMULATION_USER_ID, newPortfolioName, newPortfolioBalance)
      setShowCreateModal(false)
      setNewPortfolioName('')
      setNewPortfolioBalance(10000)
      loadPortfolios()
    } catch (error: any) {
      console.error('Error creating portfolio:', error)
      setError(error.response?.data?.detail || t('sim.errorPortfolioCreate'))
    }
  }

  const handleCheckRisk = async () => {
    if (!selectedPortfolio || !tradeSymbol.trim() || !tradeQuantity.trim()) {
      setError(t('sim.errorFillAll'))
      return
    }

    const quantity = parseFloat(tradeQuantity)
    if (isNaN(quantity) || quantity <= 0) {
      setError(t('sim.errorValidQty'))
      return
    }

    // Get current price
    const price = currentPrice || await loadCurrentPrice(tradeSymbol)
    if (!price) {
      setError(t('sim.errorNoPrice'))
      return
    }

    // Check risk
    try {
      const riskCheck = await simulationApi.checkTransactionRisk(
        selectedPortfolio.id,
        tradeSymbol,
        tradeType,
        quantity,
        price,
        'binance'
      )

      if (riskCheck.is_risky && riskCheck.warning_count > 0) {
        setRiskWarningData(riskCheck)
        setShowRiskWarning(true)
      } else {
        // No risk, proceed with trade
        await handleExecuteTradeConfirmed()
      }
    } catch (error: any) {
      console.error('Error checking risk:', error)
      // If risk check fails, proceed anyway
      await handleExecuteTradeConfirmed()
    }
  }

  const handleExecuteTradeConfirmed = async () => {
    if (!selectedPortfolio || !tradeSymbol.trim() || !tradeQuantity.trim()) {
      return
    }

    const quantity = parseFloat(tradeQuantity)
    if (isNaN(quantity) || quantity <= 0) {
      return
    }

    setTradeLoading(true)
    setError(null)

    try {
      // Check if it's a limit order
      if (tradeType === 'limit_buy' || tradeType === 'limit_sell') {
        const limitPrice = parseFloat(tradeLimitPrice)
        if (isNaN(limitPrice) || limitPrice <= 0) {
          setError(t('sim.errorLimitPrice'))
          return
        }

        await simulationApi.createLimitOrder(
          selectedPortfolio.id,
          tradeSymbol,
          tradeType,
          quantity,
          limitPrice,
          'binance'
        )
      } else {
        await simulationApi.executeTransaction(
          selectedPortfolio.id,
          tradeSymbol,
          tradeType,
          quantity,
          'binance'
        )
      }

      setShowTradeModal(false)
      setShowRiskWarning(false)
      setTradeSymbol('BTC/USDT')
      setTradeQuantity('')
      setTradeLimitPrice('')
      setRiskWarningData(null)
      loadPortfolioData()
    } catch (error: any) {
      console.error('Error executing trade:', error)
      setError(error.response?.data?.detail || t('sim.errorTrade'))
    } finally {
      setTradeLoading(false)
    }
  }

  const handleExecuteTrade = async () => {
    // First check risk
    await handleCheckRisk()
  }

  const portfolioChange = ((selectedPortfolio?.current_balance || 0) - (selectedPortfolio?.initial_balance || 0))
  const portfolioChangePercent = selectedPortfolio
    ? ((portfolioChange / selectedPortfolio.initial_balance) * 100)
    : 0

  const formatWatchDate = (iso: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleDateString(dateLocale, { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  const sortedWatchHoldings = watchPortfolio?.holdings
    ? [...watchPortfolio.holdings].sort((a, b) => {
        const va = a.total_value_usd ?? 0
        const vb = b.total_value_usd ?? 0
        return vb - va
      })
    : []

  const hasBinanceCredential = exchangeCredentials.some(
    (c: { exchange?: string }) => c.exchange?.toLowerCase() === 'binance',
  )
  const selectedExchangeCredentialIds = exchangeCredentials
    .filter((c: { exchange?: string }) => c.exchange?.toLowerCase() === (selectedExchange || '').toLowerCase())
    .map((c: { id: number }) => c.id)

  useEffect(() => {
    if (tradingMode === 'read_only' && !hasBinanceCredential) {
      setTradingMode('paper_trading')
      setSelectedExchange(null)
      setWatchPortfolio(null)
      setRealOrders([])
      try {
        localStorage.removeItem('okyiss_simulation_exchange')
      } catch {
        /* ignore */
      }
    }
  }, [tradingMode, hasBinanceCredential])

  const handleRemoveSelectedExchangeCredentials = async () => {
    if (!selectedExchange) return
    if (!window.confirm(t('sim.removeWatchAccessConfirm'))) return
    if (selectedExchangeCredentialIds.length === 0) {
      setApiKeyModalError(t('sim.noActiveConnection'))
      return
    }
    setApiKeyModalError(null)
    setCredentialRemovingId(selectedExchangeCredentialIds[0])
    try {
      await Promise.all(
        selectedExchangeCredentialIds.map((id) =>
          simulationApi.deleteExchangeCredentials(id, SIMULATION_USER_ID),
        ),
      )
      await loadExchangeCredentials()
      setFlashSuccess(t('sim.watchAccessRemoved'))
      setTradingMode('paper_trading')
      setSelectedExchange(null)
      setWatchPortfolio(null)
      setRealOrders([])
      try {
        localStorage.removeItem('okyiss_simulation_exchange')
      } catch {
        /* ignore */
      }
    } catch (err) {
      setApiKeyModalError(formatApiDetail(err) || t('sim.removeKeyFailed'))
    } finally {
      setCredentialRemovingId(null)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.simulation.title')}
        subtitle={t('page.simulation.subtitle')}
        icon={PlayCircle}
        badge={t('page.simulation.badge')}
        accent="emerald"
        actions={
          <div className="flex max-w-xl flex-col gap-2 sm:max-w-none sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            <div className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-zinc-900/60 p-1">
              <button
                type="button"
                onClick={() => setTradingMode('paper_trading')}
                className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  tradingMode === 'paper_trading'
                    ? 'bg-gradient-to-r from-crypto-cyan/25 to-crypto-violet/20 text-white shadow-glow'
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                <Zap className="h-4 w-4" />
                {t('page.simulation.paper')}
              </button>
              <button
                type="button"
                onClick={() => {
                  const hasBinance = exchangeCredentials.some(
                    (c: { exchange: string }) => c.exchange === 'binance'
                  )
                  if (hasBinance) {
                    setTradingMode('read_only')
                    setSelectedExchange('binance')
                  } else {
                    setApiKeyExchange('binance')
                    openApiKeyModal()
                  }
                }}
                className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  tradingMode === 'read_only'
                    ? 'bg-gradient-to-r from-crypto-cyan/25 to-crypto-violet/20 text-white shadow-glow'
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                <Eye className="h-4 w-4" />
                {t('page.simulation.watch')}
              </button>
            </div>
            <button type="button" onClick={openApiKeyModal} className="btn-crypto-ghost py-2 text-sm">
              <Settings className="h-4 w-4" />
              {t('page.simulation.apiKey')}
            </button>
            {selectedPortfolio && (
              <button
                type="button"
                onClick={() => setShowTradeModal(true)}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-emerald-900/30 transition hover:bg-emerald-500"
              >
                <ArrowUp className="h-4 w-4" />
                {t('page.simulation.trade')}
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="btn-crypto py-2 text-sm"
            >
              <Plus className="h-4 w-4" />
              {t('page.simulation.portfolio')}
            </button>
          </div>
        }
      />

      {flashSuccess && (
        <div className="bg-emerald-500/10 border border-emerald-500 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="text-emerald-300">{flashSuccess}</div>
            <button
              type="button"
              onClick={() => setFlashSuccess(null)}
              className="text-emerald-400 hover:text-emerald-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="text-red-400">{error}</div>
            <button type="button" onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Portfolio Selector */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex space-x-4 overflow-x-auto">
          {portfolios.map((portfolio) => (
            <button
              key={portfolio.id}
              onClick={() => setSelectedPortfolio(portfolio)}
              className={`px-4 py-2 rounded-lg whitespace-nowrap ${
                selectedPortfolio?.id === portfolio.id
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {portfolio.name}
            </button>
          ))}
        </div>
      </div>

      {/* Trading Mode Content */}
      {tradingMode === 'read_only' && selectedExchange ? (
        <>
          <div className="bg-yellow-500/10 border border-yellow-500 rounded-lg p-4 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center space-x-2">
                <Eye className="w-5 h-5 text-yellow-500" />
                <span className="text-yellow-300 font-semibold">{t('sim.watchMode')}</span>
                <span className="text-slate-400">{t('sim.binanceSpotReadonly')}</span>
              </div>
              <select
                value={selectedExchange}
                onChange={(e) => setSelectedExchange(e.target.value)}
                className="bg-slate-700 text-white rounded px-3 py-1"
              >
                {exchangeCredentials
                  .filter((cred: { exchange: string }) => cred.exchange === 'binance')
                  .map((cred: { id: number; exchange: string }) => (
                    <option key={cred.id} value={cred.exchange}>
                      {cred.exchange.toUpperCase()}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                onClick={() => void handleRemoveSelectedExchangeCredentials()}
                disabled={credentialRemovingId !== null}
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50 disabled:pointer-events-none"
              >
                <Trash2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
                {t('sim.removeWatchAccess')}
              </button>
            </div>
            <p className="text-sm text-yellow-200 mt-2">{t('sim.watchExplain')}</p>
          </div>

          {watchLoading && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-slate-300 text-center">
              {t('sim.portfolioComputing')}
            </div>
          )}

          {watchPortfolio?.summary && !watchLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="text-sm text-slate-400 mb-2">{t('sim.totalPortfolioValue')}</div>
                <div className="text-3xl font-bold text-white">
                  $
                  {watchPortfolio.summary.total_portfolio_usd.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>
                {watchPortfolio.summary.usdt_free > 0 && (
                  <div className="text-xs text-slate-500 mt-2">
                    {t('sim.usdtFreeNote').replace(
                      '{amount}',
                      watchPortfolio.summary.usdt_free.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      }),
                    )}
                  </div>
                )}
              </div>
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="text-sm text-slate-400 mb-2">{t('sim.totalPnl')}</div>
                <div
                  className={`text-3xl font-bold flex flex-wrap items-center gap-2 ${
                    watchPortfolio.summary.total_pnl_usd >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {watchPortfolio.summary.total_pnl_usd >= 0 ? (
                    <TrendingUp className="w-8 h-8 shrink-0" />
                  ) : (
                    <TrendingDown className="w-8 h-8 shrink-0" />
                  )}
                  <span>
                    {watchPortfolio.summary.total_pnl_usd >= 0 ? '+' : ''}$
                    {watchPortfolio.summary.total_pnl_usd.toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                    {watchPortfolio.summary.total_pnl_percent != null && (
                      <span className="text-xl ml-2">
                        ({watchPortfolio.summary.total_pnl_percent >= 0 ? '+' : ''}
                        {watchPortfolio.summary.total_pnl_percent.toFixed(2)}%)
                      </span>
                    )}
                  </span>
                </div>
                {watchPortfolio.summary.total_pnl_percent == null && (
                  <div className="text-xs text-slate-500 mt-2">{t('sim.pnlPercentHint')}</div>
                )}
              </div>
            </div>
          )}

          {!watchLoading && watchPortfolio && (
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white mb-3">{t('sim.assets')}</h3>
              {sortedWatchHoldings.length === 0 ? (
                <div className="text-slate-400 text-center py-8 bg-slate-800 rounded-lg border border-slate-700">
                  {t('sim.noSpotHoldings')}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {sortedWatchHoldings.map((h) => {
                    const pnl = h.pnl_usd
                    const pnlPct = h.pnl_percent
                    const pnlKnown = pnl != null && pnlPct != null
                    return (
                      <div
                        key={h.asset}
                        className="bg-slate-800 rounded-lg p-5 border border-slate-700 shadow-sm"
                      >
                        <div className="text-xl font-bold text-white tracking-wide mb-3">{h.asset}</div>
                        <dl className="space-y-2 text-sm">
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.quantity')}</dt>
                            <dd className="text-white font-mono text-right">
                              {h.quantity.toLocaleString(dateLocale, { maximumFractionDigits: 8 })}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.buyPrice')}</dt>
                            <dd className="text-white text-right">
                              {h.buy_price != null ? `$${h.buy_price.toFixed(2)}` : '—'}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.spotPrice')}</dt>
                            <dd className="text-white text-right">
                              {h.current_price != null ? `$${h.current_price.toFixed(2)}` : '—'}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.totalValue')}</dt>
                            <dd className="text-white text-right">
                              {h.total_value_usd != null
                                ? `$${h.total_value_usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                                : '—'}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.pnlShort')}</dt>
                            <dd
                              className={`text-right font-medium ${
                                !pnlKnown
                                  ? 'text-slate-400'
                                  : pnl >= 0
                                    ? 'text-emerald-400'
                                    : 'text-red-400'
                              }`}
                            >
                              {!pnlKnown
                                ? '—'
                                : `${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)`}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt className="text-slate-400">{t('sim.colDate')}</dt>
                            <dd className="text-white text-right">{formatWatchDate(h.buy_time_iso)}</dd>
                          </div>
                        </dl>
                        {h.note && (
                          <p className="text-xs text-amber-400/90 mt-3 border-t border-slate-600 pt-2">
                            {h.note}
                          </p>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {realOrders.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4">{t('sim.openOrders')}</h3>
              <div className="space-y-2">
                {realOrders.map((order: any, index: number) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-slate-700 rounded-lg"
                  >
                    <div className="flex items-center space-x-4">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${
                          order.side === 'buy'
                            ? 'bg-green-500/20 text-green-500'
                            : 'bg-red-500/20 text-red-500'
                        }`}
                      >
                        {order.side.toUpperCase()}
                      </span>
                      <span className="text-white font-medium">{order.symbol}</span>
                      <span className="text-slate-400">
                        {order.amount.toFixed(4)} @ ${order.price?.toFixed(2) || t('sim.marketWord')}
                      </span>
                    </div>
                    <span className="text-slate-400 text-sm">{order.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : selectedPortfolio && tradingMode === 'paper_trading' ? (
        <>
          {/* Portfolio Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="text-sm text-slate-400 mb-2">{t('sim.totalValue')}</div>
              <div className="text-3xl font-bold text-white">
                ${selectedPortfolio.current_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="text-sm text-slate-400 mb-2">{t('sim.startBalance')}</div>
              <div className="text-3xl font-bold text-white">
                ${selectedPortfolio.initial_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="text-sm text-slate-400 mb-2">{t('sim.totalPnl')}</div>
              <div className={`text-3xl font-bold flex items-center space-x-2 ${
                portfolioChange >= 0 ? 'text-green-500' : 'text-red-500'
              }`}>
                {portfolioChange >= 0 ? (
                  <TrendingUp className="w-6 h-6" />
                ) : (
                  <TrendingDown className="w-6 h-6" />
                )}
                <span>
                  ${portfolioChange.toLocaleString('en-US', { minimumFractionDigits: 2 })} (
                  {portfolioChangePercent >= 0 ? '+' : ''}
                  {portfolioChangePercent.toFixed(2)}%)
                </span>
              </div>
            </div>
          </div>

          {/* Portfolio Rebalancing Recommendations */}
          {rebalancingAnalysis && rebalancingAnalysis.recommendations && rebalancingAnalysis.recommendations.length > 0 && (
            <div className="bg-blue-500/10 border border-blue-500 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <Target className="w-5 h-5 text-blue-500" />
                  <h3 className="font-semibold text-blue-500">{t('sim.rebalanceTitle')}</h3>
                </div>
                <div className="text-sm text-blue-400">
                  {t('sim.riskScore')} {rebalancingAnalysis.risk_score.toFixed(0)}/100 |{' '}
                  {t('sim.diversification')}: {rebalancingAnalysis.diversification_score.toFixed(0)}/100
                </div>
              </div>
              <div className="space-y-2">
                {rebalancingAnalysis.recommendations.slice(0, 3).map((rec: any, index: number) => (
                  <div key={index} className="bg-blue-500/20 rounded-lg p-3 border border-blue-500/50">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2 mb-1">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            rec.severity === 'critical' ? 'bg-red-600 text-white' :
                            rec.severity === 'high' ? 'bg-orange-600 text-white' :
                            'bg-yellow-600 text-white'
                          }`}>
                            {rec.severity.toUpperCase()}
                          </span>
                          {rec.symbol && (
                            <span className="text-xs text-blue-300 font-medium">{rec.symbol}</span>
                          )}
                        </div>
                        <div className="text-sm text-blue-200">{rec.message}</div>
                        {rec.action === 'sell' && rec.amount_usdt && (
                          <div className="text-xs text-blue-400 mt-1">
                            {t('sim.recommendSell').replace('{n}', rec.amount_usdt.toFixed(2))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Risk Warnings */}
          {riskAnalysis && riskAnalysis.warnings && riskAnalysis.warnings.length > 0 && (
            <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-2">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                <h3 className="font-semibold text-red-500">
                  {t('sim.riskWarnings').replace('{n}', String(riskAnalysis.warning_count))}
                </h3>
              </div>
              <div className="space-y-2">
                {riskAnalysis.warnings.map((warning: any, index: number) => (
                  <div key={index} className="text-sm text-red-300">
                    • {warning.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Positions */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4">{t('sim.positions')}</h3>
            {positions.length === 0 ? (
              <div className="text-slate-400 text-center py-8">{t('sim.noPositions')}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left py-3 px-4 text-slate-400">{t('sim.symbol')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.quantity')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.avgBuy')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.currentPrice')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.value')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.kz')}</th>
                      <th className="text-right py-3 px-4 text-slate-400">{t('sim.kzPct')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((position, index) => (
                      <tr key={index} className="border-b border-slate-700">
                        <td className="py-3 px-4 text-white font-medium">{position.symbol}</td>
                        <td className="py-3 px-4 text-right text-white">{position.quantity.toFixed(4)}</td>
                        <td className="py-3 px-4 text-right text-white">
                          ${position.avg_buy_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          ${position.current_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          ${position.position_value.toFixed(2)}
                        </td>
                        <td className={`py-3 px-4 text-right ${
                          position.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'
                        }`}>
                          ${position.unrealized_pnl.toFixed(2)}
                        </td>
                        <td className={`py-3 px-4 text-right ${
                          position.unrealized_pnl_percent >= 0 ? 'text-green-500' : 'text-red-500'
                        }`}>
                          {position.unrealized_pnl_percent >= 0 ? '+' : ''}
                          {position.unrealized_pnl_percent.toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Pending Orders */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4">{t('sim.pendingOrdersTitle')}</h3>
            {orders.filter((o: any) => o.status === 'pending').length === 0 ? (
              <div className="text-slate-400 text-center py-8">{t('sim.noPendingOrders')}</div>
            ) : (
              <div className="space-y-2">
                {orders.filter((o: any) => o.status === 'pending').map((order: any, index: number) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-slate-700 rounded-lg"
                  >
                    <div className="flex items-center space-x-4">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${
                          order.order_type === 'limit_buy'
                            ? 'bg-green-500/20 text-green-500'
                            : 'bg-red-500/20 text-red-500'
                        }`}
                      >
                        {order.order_type === 'limit_buy'
                          ? t('sim.orderLimitBuyBadge')
                          : t('sim.orderLimitSellBadge')}
                      </span>
                      <span className="text-white font-medium">{order.symbol}</span>
                      <span className="text-slate-400">
                        {order.quantity.toFixed(4)} @ ${order.limit_price.toFixed(2)}
                      </span>
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await simulationApi.cancelOrder(order.id)
                          loadPortfolioData()
                        } catch (error) {
                          console.error('Error cancelling order:', error)
                        }
                      }}
                      className="text-red-400 hover:text-red-300 text-sm"
                    >
                      {t('sim.cancel')}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Transactions */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4">{t('sim.recentTx')}</h3>
            {transactions.length === 0 ? (
              <div className="text-slate-400 text-center py-8">{t('sim.noTx')}</div>
            ) : (
              <div className="space-y-2">
                {transactions.slice(0, 10).map((transaction, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-slate-700 rounded-lg"
                  >
                    <div className="flex items-center space-x-4">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${
                          transaction.transaction_type === 'buy'
                            ? 'bg-green-500/20 text-green-500'
                            : 'bg-red-500/20 text-red-500'
                        }`}
                      >
                        {transaction.transaction_type === 'buy' ? t('sim.buy').toUpperCase() : t('sim.sell').toUpperCase()}
                      </span>
                      <span className="text-white font-medium">{transaction.symbol}</span>
                      <span className="text-slate-400">
                        {transaction.quantity.toFixed(4)} @ ${transaction.price.toFixed(2)}
                      </span>
                    </div>
                    <div className="text-white">
                      ${transaction.total.toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}

      {/* Trade Modal */}
      {showTradeModal && selectedPortfolio && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white">{t('sim.tradeTitle')}</h3>
              <button
                onClick={() => {
                  setShowTradeModal(false)
                  setError(null)
                }}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.tradeType')}</label>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <button
                    onClick={() => setTradeType('buy')}
                    className={`px-4 py-2 rounded-lg font-medium ${
                      tradeType === 'buy'
                        ? 'bg-green-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    <ArrowUp className="w-4 h-4 inline mr-2" />
                    {t('sim.marketBuy')}
                  </button>
                  <button
                    onClick={() => setTradeType('sell')}
                    className={`px-4 py-2 rounded-lg font-medium ${
                      tradeType === 'sell'
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    <ArrowDown className="w-4 h-4 inline mr-2" />
                    {t('sim.marketSell')}
                  </button>
                  <button
                    onClick={() => setTradeType('limit_buy')}
                    className={`px-4 py-2 rounded-lg font-medium ${
                      tradeType === 'limit_buy'
                        ? 'bg-green-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {t('sim.limitBuy')}
                  </button>
                  <button
                    onClick={() => setTradeType('limit_sell')}
                    className={`px-4 py-2 rounded-lg font-medium ${
                      tradeType === 'limit_sell'
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {t('sim.limitSell')}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.coinSymbol')}</label>
                <input
                  type="text"
                  value={tradeSymbol}
                  onChange={(e) => setTradeSymbol(e.target.value.toUpperCase())}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="BTC/USDT"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.quantity')}</label>
                <input
                  type="number"
                  value={tradeQuantity}
                  onChange={(e) => setTradeQuantity(e.target.value)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="0.001"
                  min="0"
                  step="0.0001"
                />
              </div>
              {(tradeType === 'limit_buy' || tradeType === 'limit_sell') && (
                <div>
                  <label className="block text-sm text-slate-400 mb-2">{t('sim.limitPrice')}</label>
                  <input
                    type="number"
                    value={tradeLimitPrice}
                    onChange={(e) => setTradeLimitPrice(e.target.value)}
                    className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="50000"
                    min="0"
                    step="0.01"
                  />
                  {currentPrice && (
                    <div className="text-xs text-slate-400 mt-1">
                      {t('sim.currentPrice')}: ${currentPrice.toFixed(2)}
                    </div>
                  )}
                </div>
              )}
              <div className="bg-slate-700 rounded-lg p-3">
                <div className="text-xs text-slate-400 mb-1">{t('sim.currentBalance')}</div>
                <div className="text-lg font-semibold text-white">
                  ${selectedPortfolio.current_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="flex space-x-3">
                <button
                  onClick={() => {
                    setShowTradeModal(false)
                    setError(null)
                  }}
                  className="flex-1 bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600"
                  disabled={tradeLoading}
                >
                  {t('sim.cancel')}
                </button>
                <button
                  onClick={handleExecuteTrade}
                  disabled={tradeLoading || !tradeSymbol.trim() || !tradeQuantity.trim() || ((tradeType === 'limit_buy' || tradeType === 'limit_sell') && !tradeLimitPrice.trim())}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium ${
                    tradeType === 'buy' || tradeType === 'limit_buy'
                      ? 'bg-green-600 hover:bg-green-700'
                      : 'bg-red-600 hover:bg-red-700'
                  } text-white disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {tradeLoading
                    ? t('sim.processingShort')
                    : tradeType === 'limit_buy' || tradeType === 'limit_sell'
                      ? t('sim.submitLimitOrder')
                      : tradeType === 'buy'
                        ? t('sim.submitMarketBuy')
                        : t('sim.submitMarketSell')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Risk Warning Modal */}
      {showRiskWarning && riskWarningData && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 border border-red-500 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-6 h-6 text-red-500" />
                <h3 className="text-xl font-semibold text-red-500">{t('sim.riskTitle')}</h3>
              </div>
              <button
                onClick={() => {
                  setShowRiskWarning(false)
                  setRiskWarningData(null)
                }}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
                <p className="text-red-300 font-semibold mb-2">{t('sim.riskAgentWarn')}</p>
                <div className="space-y-2">
                  {riskWarningData.warnings.map((warning: any, index: number) => (
                    <div key={index} className="text-sm text-red-200">
                      • {warning.message}
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="bg-slate-700 rounded-lg p-3">
                <div className="text-xs text-slate-400 mb-1">{t('sim.tradeValue')}</div>
                <div className="text-lg font-semibold text-white">
                  ${riskWarningData.transaction_value.toFixed(2)}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {t('sim.currentBalance')}: ${riskWarningData.portfolio_balance.toFixed(2)}
                </div>
              </div>
              
              <div className="bg-yellow-500/10 border border-yellow-500 rounded-lg p-3">
                <p className="text-yellow-300 text-sm">
                  <strong>{t('sim.recommendation')}</strong> {riskWarningData.recommendation}
                </p>
              </div>
              
              <div className="flex space-x-3">
                <button
                  onClick={() => {
                    setShowRiskWarning(false)
                    setRiskWarningData(null)
                    setShowTradeModal(false)
                  }}
                  className="flex-1 bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600"
                >
                  {t('sim.cancelAction')}
                </button>
                <button
                  onClick={async () => {
                    setShowRiskWarning(false)
                    await handleExecuteTradeConfirmed()
                  }}
                  className="flex-1 bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700"
                >
                  {t('sim.continueAnyway')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Create Portfolio Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white">{t('sim.newPortfolio')}</h3>
              <button
                onClick={() => {
                  setShowCreateModal(false)
                  setError(null)
                }}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.portfolioName')}</label>
                <input
                  type="text"
                  value={newPortfolioName}
                  onChange={(e) => setNewPortfolioName(e.target.value)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder={t('sim.portfolioNamePh')}
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.startBalanceLabel')}</label>
                <input
                  type="number"
                  value={newPortfolioBalance}
                  onChange={(e) => setNewPortfolioBalance(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  min="0"
                  step="100"
                />
              </div>
              <div className="flex space-x-3">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600"
                >
                  {t('sim.cancel')}
                </button>
                <button
                  onClick={handleCreatePortfolio}
                  className="flex-1 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
                >
                  {t('sim.create')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* API Key Modal — z-[100]: diğer z-50 modalların üstünde kalsın */}
      {showApiKeyModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 max-w-md w-full shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white">{t('sim.exchangeApiTitle')}</h3>
              <button
                type="button"
                onClick={() => {
                  setShowApiKeyModal(false)
                  setApiKeyModalError(null)
                  setError(null)
                  setApiKey('')
                  setApiSecret('')
                  setApiPassphrase('')
                }}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              {apiKeyModalError && (
                <div className="bg-red-500/15 border border-red-500/80 rounded-lg p-3 text-red-300 text-sm">
                  {apiKeyModalError}
                </div>
              )}

              {exchangeCredentials.length > 0 && (
                <div className="rounded-lg border border-slate-600 bg-slate-900/50 p-3 space-y-2">
                  <p className="text-sm font-medium text-slate-300">{t('sim.savedConnections')}</p>
                  <p className="text-xs text-slate-500 leading-relaxed">{t('sim.keysNeverExposed')}</p>
                  <ul className="space-y-2 pt-1">
                    {exchangeCredentials.map((cred: { id: number; exchange: string }) => (
                      <li
                        key={cred.id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-800/80 px-3 py-2"
                      >
                        <span className="text-white text-sm font-medium uppercase">{cred.exchange}</span>
                        <button
                          type="button"
                          disabled={credentialRemovingId === cred.id || apiKeySaving}
                          onClick={() => void handleRemoveCredential(cred.id, cred.exchange)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50 disabled:pointer-events-none"
                        >
                          <Trash2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
                          {t('sim.removeKey')}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="bg-yellow-500/10 border border-yellow-500 rounded-lg p-3 mb-4">
                <p className="text-yellow-300 text-sm">{t('sim.securityBlurb')}</p>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.exchangeLabel')}</label>
                <select
                  value={apiKeyExchange}
                  onChange={(e) => setApiKeyExchange(e.target.value)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="binance">{t('sim.binanceWatch')}</option>
                  <option value="coinbasepro">Coinbase Pro</option>
                  <option value="kraken">Kraken</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.apiKeyLabel')}</label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Binance API Key"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-2">{t('sim.apiSecretLabel')}</label>
                <input
                  type="password"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Binance API Secret"
                />
              </div>

              {(apiKeyExchange === 'coinbasepro') && (
                <div>
                  <label className="block text-sm text-slate-400 mb-2">{t('sim.passphraseCb')}</label>
                  <input
                    type="password"
                    value={apiPassphrase}
                    onChange={(e) => setApiPassphrase(e.target.value)}
                    className="w-full bg-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="Coinbase Pro Passphrase"
                  />
                </div>
              )}

              <div className="bg-slate-700 rounded-lg p-3">
                <p className="text-xs text-slate-400">
                  <strong>{t('sim.notePrefix')}</strong> {t('sim.binanceKeyNote')}
                </p>
              </div>

              <div className="flex space-x-3">
                <button
                  type="button"
                  disabled={apiKeySaving}
                  onClick={() => {
                    setShowApiKeyModal(false)
                    setApiKeyModalError(null)
                    setError(null)
                    setApiKey('')
                    setApiSecret('')
                    setApiPassphrase('')
                  }}
                  className="flex-1 bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600 disabled:opacity-50"
                >
                  {t('sim.cancel')}
                </button>
                <button
                  type="button"
                  disabled={apiKeySaving}
                  onClick={() => void handleSaveApiKey()}
                  className="flex-1 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  {apiKeySaving ? t('sim.saving') : t('sim.save')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Portfolio Rebalancing Modal */}
      {showRebalancing && selectedPortfolio && rebalancingAnalysis && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white flex items-center space-x-2">
                <Target className="w-5 h-5" />
                <span>{t('sim.smartRebalanceBtn')}</span>
              </h3>
              <button
                onClick={() => setShowRebalancing(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              {/* Portfolio Stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('sim.totalValue')}</div>
                  <div className="text-xl font-bold text-white">
                    ${rebalancingAnalysis.total_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('sim.riskScoreLabel')}</div>
                  <div className={`text-xl font-bold ${
                    rebalancingAnalysis.risk_score > 50 ? 'text-red-500' :
                    rebalancingAnalysis.risk_score > 30 ? 'text-yellow-500' : 'text-green-500'
                  }`}>
                    {rebalancingAnalysis.risk_score.toFixed(0)}/100
                  </div>
                </div>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('sim.diversification')}</div>
                  <div className={`text-xl font-bold ${
                    rebalancingAnalysis.diversification_score > 70 ? 'text-green-500' :
                    rebalancingAnalysis.diversification_score > 50 ? 'text-yellow-500' : 'text-red-500'
                  }`}>
                    {rebalancingAnalysis.diversification_score.toFixed(0)}/100
                  </div>
                </div>
              </div>

              {/* Current Positions */}
              <div className="bg-slate-700 rounded-lg p-4">
                <h4 className="text-lg font-semibold text-white mb-3">{t('sim.currentPositions')}</h4>
                <div className="space-y-2">
                  {rebalancingAnalysis.positions.map((pos: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between bg-slate-600 rounded p-2">
                      <div>
                        <span className="text-white font-medium">{pos.symbol}</span>
                        <span className="text-slate-400 text-sm ml-2">
                          {pos.quantity.toFixed(4)}
                        </span>
                      </div>
                      <div className="text-right">
                        <div className="text-white font-semibold">
                          ${pos.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </div>
                        <div className="text-slate-400 text-xs">
                          %{pos.percentage.toFixed(1)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recommendations */}
              {rebalancingAnalysis.recommendations.length > 0 && (
                <div className="bg-blue-500/10 border border-blue-500 rounded-lg p-4">
                  <h4 className="text-lg font-semibold text-blue-400 mb-3">
                    {t('sim.recommendationsTitle').replace(
                      '{n}',
                      String(rebalancingAnalysis.recommendation_count),
                    )}
                  </h4>
                  <div className="space-y-3">
                    {rebalancingAnalysis.recommendations.map((rec: any, idx: number) => (
                      <div key={idx} className="bg-slate-700 rounded-lg p-3">
                        <div className="flex items-start justify-between mb-2">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${
                            rec.severity === 'critical' ? 'bg-red-600 text-white' :
                            rec.severity === 'high' ? 'bg-orange-600 text-white' :
                            'bg-yellow-600 text-white'
                          }`}>
                            {rec.severity.toUpperCase()}
                          </span>
                          {rec.symbol && (
                            <span className="text-sm text-blue-300 font-medium">{rec.symbol}</span>
                          )}
                        </div>
                        <p className="text-sm text-slate-300 mb-2">{rec.message}</p>
                        {rec.action === 'sell' && rec.amount_usdt && (
                          <div className="text-xs text-blue-400">
                            💡 {t('sim.recommendSell').replace('{n}', rec.amount_usdt.toFixed(2))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex space-x-3">
                <button
                  onClick={() => setShowRebalancing(false)}
                  className="flex-1 bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600"
                >
                  {t('sim.close')}
                </button>
                <button
                  onClick={async () => {
                    try {
                      const plan = await simulationApi.getRebalancingPlan(selectedPortfolio.id)
                      alert(t('sim.rebalanceReady').replace('{n}', String(plan.action_count)))
                    } catch (error) {
                      console.error('Error getting rebalancing plan:', error)
                    }
                  }}
                  className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
                >
                  {t('sim.createRebalancePlan')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

