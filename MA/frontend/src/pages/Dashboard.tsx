import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { marketsApi, alertsApi, newsNodeApi, Ticker, TechnicalAnalysis, NewsItemNode } from '../services/api'
import MarketCard from '../components/MarketCard'
import MarketAlertsPanel from '../components/MarketAlertsPanel'
import PageHeader from '../components/PageHeader'
import CoinSearch from '../components/CoinSearch'
import TradingViewWidget from '../components/TradingViewWidget'
import { TrendingUp, Activity, AlertCircle, Newspaper, ExternalLink, RefreshCw } from 'lucide-react'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

const POPULAR_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT', 'XRP/USDT']

const NEWS_REFRESH_MS = 5 * 60 * 1000 // 5 dakika
const DASHBOARD_NEWS_LIMIT = 10

export default function Dashboard() {
  const { t } = useAppPreferences()

  const timeAgoShort = (iso: string) => {
    const d = new Date(iso)
    const sec = Math.floor((Date.now() - d.getTime()) / 1000)
    if (sec < 60) return t('common.timeJustNow')
    if (sec < 3600) return t('common.timeMinutesAgoLong').replace('{n}', String(Math.floor(sec / 60)))
    if (sec < 86400) return t('common.timeHoursAgoLong').replace('{n}', String(Math.floor(sec / 3600)))
    return t('common.timeDaysAgoLong').replace('{n}', String(Math.floor(sec / 86400)))
  }
  const [tickers, setTickers] = useState<Record<string, Ticker>>({})
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC/USDT')
  const [selectedTicker, setSelectedTicker] = useState<Ticker | null>(null)
  const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null)
  const [anomalies, setAnomalies] = useState<any>(null)
  const [flashAlerts, setFlashAlerts] = useState<any[]>([])
  const [showAlerts, setShowAlerts] = useState(true)
  const [latestNews, setLatestNews] = useState<NewsItemNode[]>([])
  const [newsLoading, setNewsLoading] = useState(false)

  const loadLatestNews = async () => {
    setNewsLoading(true)
    try {
      const res = await newsNodeApi.getLatest()
      if (res.success && res.items) setLatestNews(res.items.slice(0, DASHBOARD_NEWS_LIMIT))
      else setLatestNews([])
    } catch {
      setLatestNews([])
    } finally {
      setNewsLoading(false)
    }
  }

  useEffect(() => {
    loadTickers()
    loadFlashAlerts()
    const interval = setInterval(loadTickers, 10000) // Update every 10 seconds
    const alertInterval = setInterval(loadFlashAlerts, 60000) // Check alerts every minute
    return () => {
      clearInterval(interval)
      clearInterval(alertInterval)
    }
  }, [])

  const loadFlashAlerts = async () => {
    try {
      const data = await alertsApi.checkAlerts(POPULAR_SYMBOLS, 'binance')
      if (data.alerts && data.alerts.length > 0) {
        setFlashAlerts(data.alerts)
        // Show browser notification if supported
        if ('Notification' in window && Notification.permission === 'granted') {
          data.alerts.slice(0, 3).forEach((alert: any) => {
            new Notification(t('dashboard.notifyTitle'), {
              body: alert.message,
              icon: '/favicon.ico',
              tag: alert.timestamp
            })
          })
        }
      } else {
        setFlashAlerts([])
      }
    } catch (error) {
      console.error('Error loading flash alerts:', error)
    }
  }

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  useEffect(() => {
    loadLatestNews()
    const t = setInterval(loadLatestNews, NEWS_REFRESH_MS)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (selectedSymbol) {
      loadAnalysis()
      loadTicker()
      loadAnomalies()
    }
  }, [selectedSymbol])
  
  useEffect(() => {
    // Check for anomalies periodically
    const interval = setInterval(() => {
      if (selectedSymbol) {
        loadAnomalies()
      }
    }, 60000) // Every minute
    return () => clearInterval(interval)
  }, [selectedSymbol])

  const loadTicker = async () => {
    try {
      const data = await marketsApi.getTicker(selectedSymbol)
      setSelectedTicker(data)
    } catch (error) {
      console.error('Error loading ticker:', error)
    }
  }

  const loadTickers = async () => {
    try {
      const data = await marketsApi.getTickers(POPULAR_SYMBOLS)
      setTickers(data)
    } catch (error) {
      console.error('Error loading tickers:', error)
    }
  }

  const loadAnalysis = async () => {
    try {
      const data = await marketsApi.getAnalysis(selectedSymbol)
      setAnalysis(data.analysis)
    } catch (error) {
      console.error('Error loading analysis:', error)
    }
  }

  const loadAnomalies = async () => {
    try {
      // Check volume anomalies (most important for alerts)
      const volumeAnomalies = await marketsApi.getAnomalies(selectedSymbol, '1h', 'binance', 'volume')
      setAnomalies(volumeAnomalies)
    } catch (error) {
      // Anomaly service might not be available, that's OK
      console.warn('Anomaly detection not available:', error)
      setAnomalies(null)
    }
  }

  const handleSymbolSelect = (symbol: string, ticker?: Ticker) => {
    setSelectedSymbol(symbol)
    if (ticker) {
      setSelectedTicker(ticker)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.dashboard.title')}
        subtitle={t('page.dashboard.subtitle')}
        icon={TrendingUp}
        badge={t('page.dashboard.badge')}
        accent="cyan"
      />

      {/* Market Cards Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {POPULAR_SYMBOLS.map((symbol) => {
          const ticker = tickers[symbol]
          if (!ticker) return null
          return (
            <MarketCard
              key={symbol}
              ticker={ticker}
              onClick={() => setSelectedSymbol(symbol)}
            />
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 lg:items-stretch">
        {/* Left Sidebar - Coin Search */}
        <div className="lg:col-span-1 space-y-6">
          <CoinSearch 
            onSelect={handleSymbolSelect} 
            selectedSymbol={selectedSymbol}
          />
        </div>

        {/* Chart and Analysis */}
        <div className="lg:col-span-2 space-y-6">
          {/* TradingView Chart */}
          <div className="crypto-card">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-white sm:text-xl">
                <TrendingUp className="h-5 w-5 text-crypto-cyan" strokeWidth={2} />
                <span>
                  {selectedSymbol} {t('page.dashboard.chart')}
                </span>
              </h3>
              {selectedTicker && (
                <div className="flex items-center space-x-4 text-sm">
                  <div>
                    <span className="text-slate-400">{t('page.dashboard.priceColon')} </span>
                    <span className="text-white font-bold">
                      ${selectedTicker.price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className={`${
                    (selectedTicker.change_24h || 0) >= 0 ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {selectedTicker.change_24h ? `${selectedTicker.change_24h >= 0 ? '+' : ''}${selectedTicker.change_24h.toFixed(2)}%` : 'N/A'}
                  </div>
                </div>
              )}
            </div>
            <div className="w-full">
              <TradingViewWidget symbol={selectedSymbol} exchange="BINANCE" />
            </div>
          </div>

          {/* Technical Analysis */}
          {analysis && (
            <div className="crypto-card">
              <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold text-white sm:text-xl">
                <Activity className="h-5 w-5 text-crypto-violet" strokeWidth={2} />
                <span>{t('page.dashboard.tech')}</span>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {analysis.rsi && (
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">RSI</div>
                    <div className={`text-2xl font-bold ${
                      analysis.rsi > 70 ? 'text-red-500' :
                      analysis.rsi < 30 ? 'text-green-500' : 'text-white'
                    }`}>
                      {analysis.rsi.toFixed(2)}
                    </div>
                  </div>
                )}
                {analysis.macd && (
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">MACD</div>
                    <div className={`text-2xl font-bold ${
                      (analysis.macd.macd || 0) > (analysis.macd.signal || 0) ? 'text-green-500' : 'text-red-500'
                    }`}>
                      {analysis.macd.macd?.toFixed(4) || 'N/A'}
                    </div>
                  </div>
                )}
                {analysis.bollinger_bands && (
                  <div className="bg-slate-700 rounded-lg p-4">
                    <div className="text-sm text-slate-400 mb-1">Bollinger Bands</div>
                    <div className="text-xs text-slate-300 space-y-1">
                      <div>
                        {t('page.dashboard.bbUpperShort')} ${analysis.bollinger_bands.upper?.toFixed(2)}
                      </div>
                      <div>
                        {t('page.dashboard.bbLowerShort')} ${analysis.bollinger_bands.lower?.toFixed(2)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              {analysis.signals && analysis.signals.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-700">
                  <div className="flex items-center space-x-2 mb-2">
                    <AlertCircle className="w-4 h-4 text-yellow-500" />
                    <span className="text-sm font-semibold text-yellow-500">{t('page.dashboard.signals')}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {analysis.signals.map((signal, index) => (
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
        </div>

        {/* Right column: uyarılar + Son Haberler (tam yükseklik) */}
        <div className="lg:col-span-1 flex flex-col gap-6 min-h-0 lg:h-full">
          <MarketAlertsPanel
            flashAlerts={flashAlerts}
            anomalies={anomalies}
            selectedSymbol={selectedSymbol}
            selectedTicker={selectedTicker}
            defaultCollapsed
            showFlash={showAlerts}
            onDismissFlash={() => setShowAlerts(false)}
            variant="sidebar"
          />
          <div className="crypto-card flex flex-col flex-1 min-h-[26rem] sm:min-h-[30rem] lg:min-h-[calc(100vh-11rem)] p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3 mb-4 shrink-0">
              <h3 className="text-xl font-semibold text-white flex items-center gap-2.5">
                <Newspaper className="w-6 h-6 text-primary-500 shrink-0" />
                <span>{t('page.dashboard.latestNews')}</span>
              </h3>
              <button
                type="button"
                onClick={() => loadLatestNews()}
                disabled={newsLoading}
                title={t('common.refresh')}
                className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 disabled:opacity-50"
                aria-label={t('page.dashboard.newsRefreshAria')}
              >
                <RefreshCw className={`w-5 h-5 ${newsLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
            {latestNews.length === 0 && !newsLoading ? (
              <div className="text-base text-slate-400">{t('page.dashboard.newsEmpty')}</div>
            ) : latestNews.length === 0 && newsLoading ? (
              <div className="text-base text-slate-400">{t('common.loading')}</div>
            ) : (
              <ul className="space-y-4 flex-1 overflow-y-auto min-h-0 pr-1 -mr-1 [scrollbar-gutter:stable]">
                {latestNews.map((item, idx) => {
                  const s = item.sentiment || 'NEUTRAL'
                  const badgeClass =
                    s === 'POSITIVE'
                      ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                      : s === 'NEGATIVE'
                        ? 'bg-red-500/20 text-red-400 border-red-500/40'
                        : 'bg-slate-600/50 text-slate-400 border-slate-500/50'
                  return (
                    <li key={`${item.url}-${idx}`}>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block group rounded-xl border border-slate-700/80 bg-slate-800/40 p-4 hover:bg-slate-700/50 hover:border-slate-600 transition-colors"
                      >
                        <div className="flex items-start gap-3">
                          <ExternalLink className="w-4 h-4 text-slate-500 group-hover:text-primary-400 shrink-0 mt-0.5" />
                          <span className="text-base text-slate-100 font-semibold leading-snug line-clamp-2 flex-1 min-w-0">
                            {item.title}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 mt-3 ml-7">
                          <span className="text-sm text-slate-500">{item.source}</span>
                          <span className="text-sm text-slate-600">·</span>
                          <span className="text-sm text-slate-500">{timeAgoShort(item.publishedAt)}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-md border font-medium ${badgeClass}`}>
                            {s}
                          </span>
                        </div>
                      </a>
                    </li>
                  )
                })}
              </ul>
            )}
            <div className="mt-5 pt-4 border-t border-slate-700 shrink-0">
              <Link
                to="/news"
                className="text-base text-primary-400 hover:text-primary-300 font-medium"
              >
                {t('page.dashboard.allNews')}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

