import { useEffect, useState, useCallback, useMemo } from 'react'
import { newsNodeApi, marketsApi, NewsItemNode, FearGreedNode, Ticker } from '../services/api'
import SentimentGauge from '../components/SentimentGauge'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { ExternalLink, RefreshCw, ArrowUpCircle, TrendingUp, TrendingDown, Newspaper } from 'lucide-react'

const INITIAL_PAGE_SIZE = 15
const REFRESH_INTERVAL_MS = 5 * 60 * 1000 // 5 min

function formatScore(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export default function News() {
  const { t } = useAppPreferences()

  const SOURCE_FILTERS = useMemo(
    () => [
      { id: 'all', label: t('news.sourceAll') },
      { id: 'CoinDesk', label: 'CoinDesk' },
      { id: 'CryptoNews', label: 'CryptoNews' },
      { id: 'Reddit', label: 'Reddit' },
      { id: 'Cointelegraph', label: 'Cointelegraph' },
    ],
    [t],
  )

  const COIN_FILTERS = useMemo(
    () => [
      { id: 'all', label: t('news.sourceAll') },
      { id: 'BTC', label: 'BTC' },
      { id: 'ETH', label: 'ETH' },
      { id: 'SOL', label: 'SOL' },
      { id: 'ADA', label: 'ADA' },
      { id: 'XRP', label: 'XRP' },
    ],
    [t],
  )

  const timeAgo = useCallback(
    (isoDate: string) => {
      const d = new Date(isoDate)
      const now = new Date()
      const sec = Math.floor((now.getTime() - d.getTime()) / 1000)
      if (sec < 60) return t('common.timeJustNow')
      if (sec < 3600) return t('common.timeMinutesAgoLong').replace('{n}', String(Math.floor(sec / 60)))
      if (sec < 86400) return t('common.timeHoursAgoLong').replace('{n}', String(Math.floor(sec / 3600)))
      if (sec < 604800) return t('common.timeDaysAgoLong').replace('{n}', String(Math.floor(sec / 86400)))
      return d.toLocaleDateString('en-US')
    },
    [t],
  )
  const [fearGreed, setFearGreed] = useState<FearGreedNode | null>(null)
  const [items, setItems] = useState<NewsItemNode[]>([])
  const [sourceFilter, setSourceFilter] = useState<string>('all')
  const [coinFilter, setCoinFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [loadingFg, setLoadingFg] = useState(true)
  const [showCount, setShowCount] = useState(INITIAL_PAGE_SIZE)
  const [coinTicker, setCoinTicker] = useState<Ticker | null>(null)

  const loadFearGreed = useCallback(async () => {
    setLoadingFg(true)
    try {
      const res = await newsNodeApi.getFearGreed()
      if (res.success && res.data) setFearGreed(res.data)
    } catch (e) {
      console.warn('Fear & Greed load failed', e)
    } finally {
      setLoadingFg(false)
    }
  }, [])

  const loadNews = useCallback(async () => {
    setLoading(true)
    try {
      const res = await newsNodeApi.getNews({
        source: sourceFilter === 'all' ? undefined : sourceFilter,
        coin: coinFilter === 'all' ? undefined : coinFilter,
      })
      if (res.success && res.items) setItems(res.items)
      else setItems([])
    } catch (e) {
      console.warn('News load failed', e)
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [sourceFilter, coinFilter])

  useEffect(() => {
    loadFearGreed()
  }, [loadFearGreed])

  useEffect(() => {
    loadNews()
  }, [loadNews])

  useEffect(() => {
    if (coinFilter === 'all') {
      setCoinTicker(null)
      return
    }
    let cancelled = false
    marketsApi.getTicker(`${coinFilter}/USDT`).then((t) => {
      if (!cancelled) setCoinTicker(t)
    }).catch(() => {
      if (!cancelled) setCoinTicker(null)
    })
    return () => { cancelled = true }
  }, [coinFilter])

  useEffect(() => {
    const t = setInterval(() => {
      loadNews()
      loadFearGreed()
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(t)
  }, [loadNews, loadFearGreed])

  const visibleItems = items.slice(0, showCount)
  const hasMore = showCount < items.length

  const sentimentStats = items.length > 0
    ? {
        pos: items.filter((i) => i.sentiment === 'POSITIVE').length,
        neg: items.filter((i) => i.sentiment === 'NEGATIVE').length,
        neu: items.filter((i) => i.sentiment === 'NEUTRAL' || !i.sentiment).length,
      }
    : null

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.news.title')}
        subtitle={t('page.news.subtitle')}
        icon={Newspaper}
        badge={t('page.news.badge')}
        accent="violet"
        actions={
          <button
            type="button"
            onClick={() => {
              loadNews()
              loadFearGreed()
            }}
            disabled={loading || loadingFg}
            className="btn-crypto-ghost disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading || loadingFg ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </button>
        }
      />

      {/* Fear & Greed */}
      <div className="crypto-card">
        <h3 className="mb-4 font-display text-lg font-semibold text-white sm:text-xl">{t('page.news.fearGreed')}</h3>
        {loadingFg ? (
          <div className="h-[220px] flex items-center justify-center">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-crypto-cyan border-t-transparent" />
          </div>
        ) : fearGreed ? (
          <SentimentGauge score={fearGreed.value} sentiment={fearGreed.value_classification} />
        ) : (
          <div className="text-slate-400 py-8 text-center">{t('page.news.loadFailed')}</div>
        )}
      </div>

      {/* Source filter bar */}
      <div className="flex flex-wrap gap-2">
        {SOURCE_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => {
              setSourceFilter(f.id)
              setShowCount(INITIAL_PAGE_SIZE)
            }}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition-all ${
              sourceFilter === f.id
                ? 'border border-crypto-cyan/35 bg-gradient-to-r from-crypto-cyan/20 to-crypto-violet/15 text-white shadow-glow'
                : 'border border-transparent bg-white/[0.04] text-zinc-400 hover:bg-white/[0.07] hover:text-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Coin filter bar — Dashboard popüler coin stili */}
      <div className="flex flex-wrap gap-2">
        {COIN_FILTERS.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => {
              setCoinFilter(c.id)
              setShowCount(INITIAL_PAGE_SIZE)
            }}
            className={`rounded-xl border px-4 py-2 text-sm font-medium transition-all ${
              coinFilter === c.id
                ? 'border-crypto-cyan/40 bg-gradient-to-r from-crypto-cyan/20 to-crypto-violet/15 text-white shadow-glow'
                : 'border-white/[0.08] bg-zinc-900/40 text-zinc-400 hover:border-white/15 hover:text-white'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Coin özet kutusu (seçili coin için) */}
      {coinFilter !== 'all' && (
        <div className="crypto-card !p-5">
          <h3 className="text-lg font-semibold text-white mb-3">
            {coinFilter} {t('page.news.coinSummary')}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('page.news.price')}</div>
              {coinTicker ? (
                <div className="flex items-center gap-2">
                  <span className="text-xl font-bold text-white">
                    ${coinTicker.price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '—'}
                  </span>
                  {(coinTicker.change_24h ?? 0) !== 0 && (
                    <span className={`flex items-center text-sm ${(coinTicker.change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {(coinTicker.change_24h ?? 0) >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                      {(coinTicker.change_24h ?? 0) >= 0 ? '+' : ''}{(coinTicker.change_24h ?? 0).toFixed(2)}%
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-slate-400">{t('common.loadingEllipsis')}</span>
              )}
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('page.news.count')}</div>
              <span className="text-xl font-bold text-white">{items.length}</span>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('page.news.sentimentLabel')}</div>
              {sentimentStats && items.length > 0 ? (
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="text-emerald-400">
                    {t('news.positivePct').replace(
                      '{n}',
                      String(((sentimentStats.pos / items.length) * 100).toFixed(0)),
                    )}
                  </span>
                  <span className="text-slate-400">
                    {t('common.neutralPct').replace(
                      '{n}',
                      ((sentimentStats.neu / items.length) * 100).toFixed(0),
                    )}
                  </span>
                  <span className="text-red-400">
                    {t('news.negativePct').replace(
                      '{n}',
                      String(((sentimentStats.neg / items.length) * 100).toFixed(0)),
                    )}
                  </span>
                </div>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* News list */}
      <div className="space-y-4">
        {loading ? (
          <>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="bg-slate-800 rounded-lg p-4 border border-slate-700 animate-pulse">
                <div className="h-5 bg-slate-700 rounded w-3/4 mb-3" />
                <div className="h-4 bg-slate-700 rounded w-1/3 mb-2" />
                <div className="h-4 bg-slate-700 rounded w-1/4" />
              </div>
            ))}
          </>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              {visibleItems.map((item, idx) => (
                <NewsCard key={`${item.url}-${idx}`} item={item} timeAgo={timeAgo} />
              ))}
            </div>
            {hasMore && (
              <div className="flex justify-center pt-4">
                <button
                  type="button"
                  onClick={() => setShowCount((c) => c + INITIAL_PAGE_SIZE)}
                  className="btn-crypto-ghost px-6 py-2.5"
                >
                  {t('page.news.more')}
                </button>
              </div>
            )}
            {!loading && visibleItems.length === 0 && (
              <div className="text-center text-slate-400 py-12">{t('page.news.empty')}</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function NewsCard({ item, timeAgo }: { item: NewsItemNode; timeAgo: (iso: string) => string }) {
  const isReddit = item.source === 'Reddit'
  const sentiment = item.sentiment || 'NEUTRAL'
  const sentimentClass =
    sentiment === 'POSITIVE'
      ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50'
      : sentiment === 'NEGATIVE'
        ? 'bg-red-500/20 text-red-400 border-red-500/50'
        : 'bg-slate-600/50 text-slate-400 border-slate-500/50'

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-2xl border border-white/[0.08] bg-zinc-900/40 shadow-card backdrop-blur-sm transition-all duration-300 hover:border-crypto-cyan/25 hover:shadow-glow"
    >
      <div className="flex">
        {item.imageUrl && (
          <div className="w-28 h-28 flex-shrink-0 bg-slate-700">
            <img
              src={item.imageUrl}
              alt=""
              className="w-full h-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        )}
        <div className="flex-1 p-4 min-w-0">
          <h4 className="font-bold text-white line-clamp-2 mb-2">{item.title}</h4>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400 mb-2">
            <span>{item.source}</span>
            <span>·</span>
            <span>{timeAgo(item.publishedAt)}</span>
            {isReddit && item.subreddit && (
              <>
                <span>·</span>
                <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300">r/{item.subreddit}</span>
              </>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-1 rounded text-xs font-medium border ${sentimentClass}`}>
              {sentiment}
            </span>
            {isReddit && item.score != null && (
              <span className="flex items-center gap-1 text-slate-400 text-xs">
                <ArrowUpCircle className="w-3.5 h-3.5" />
                {formatScore(item.score)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center pr-2 text-slate-500">
          <ExternalLink className="w-4 h-4" />
        </div>
      </div>
    </a>
  )
}
