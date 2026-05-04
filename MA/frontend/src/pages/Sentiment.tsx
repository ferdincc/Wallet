import { useEffect, useState, useRef } from 'react'
import axios from 'axios'
import { newsApi, newsNodeApi, NewsItemNode } from '../services/api'
import { TrendingUp, TrendingDown, Minus, ExternalLink, Newspaper, MessageSquare, Info } from 'lucide-react'
import SentimentGauge from '../components/SentimentGauge'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

interface SentimentData {
  success: boolean
  symbol: string
  error?: string
  overall_sentiment?: {
    sentiment: string
    score: number
    gauge_score?: number  // 0-100 for gauge chart
    confidence: number
    sample_size: number
    explanation?: string  // Why this score was given
  }
  news_sentiment: Array<{
    sentiment: string
    score: number
    article?: {
      title: string
      url: string
      source: string
    }
  }>
  reddit_sentiment: Array<{
    sentiment: string
    score: number
    post?: {
      title: string
      url: string
      subreddit: string
    }
  }>
  sources: Array<{
    type: string
    title: string
    url: string
  }>
  explanation?: string  // Overall explanation
  gauge_score?: number  // Overall gauge score
}

export default function Sentiment() {
  const { t, locale } = useAppPreferences()
  const skipLocaleRefetch = useRef(true)

  const timeAgo = (iso: string): string => {
    const d = new Date(iso)
    const sec = Math.floor((Date.now() - d.getTime()) / 1000)
    const loc = 'en-US'
    if (sec < 3600)
      return t('common.timeMinutesAgo').replace('{n}', String(Math.floor(sec / 60)))
    if (sec < 86400)
      return t('common.timeHoursAgo').replace('{n}', String(Math.floor(sec / 3600)))
    return d.toLocaleDateString(loc)
  }
  const [symbol, setSymbol] = useState('BTC')
  const [sentimentData, setSentimentData] = useState<SentimentData | null>(null)
  const [relatedNews, setRelatedNews] = useState<NewsItemNode[]>([])
  const [loadingNews, setLoadingNews] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSentiment = async () => {
    if (!symbol.trim()) {
      setError(t('page.sentiment.errorSymbolRequired'))
      return
    }

    setLoading(true)
    setError(null)
    setSentimentData(null)

    try {
      console.log('Loading sentiment for:', symbol)
      const data = await newsApi.getSentiment(symbol, true, true, 24, locale)
      console.log('Sentiment data received:', data)
      if (data && data.success !== false) {
        setSentimentData(data)
        console.log('Sentiment data set successfully')
      } else {
        console.error('Invalid sentiment data:', data)
        setError(t('page.sentiment.errorDataFailed'))
      }
    } catch (error: unknown) {
      console.error('Error loading sentiment:', error)
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail
        if (detail != null) {
          setError(typeof detail === 'string' ? detail : JSON.stringify(detail))
        } else if (error.code === 'ECONNABORTED') {
          setError(t('page.sentiment.errorTimeout'))
        } else if (!error.response) {
          setError(t('page.sentiment.errorNetworkUnreachable'))
        } else {
          setError(t('page.sentiment.errorLoadFailed'))
        }
      } else {
        const err = error as { message?: string }
        setError(err.message || t('page.sentiment.errorLoadFailed'))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (symbol) loadSentiment()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (skipLocaleRefetch.current) {
      skipLocaleRefetch.current = false
      return
    }
    if (symbol.trim()) loadSentiment()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale])

  useEffect(() => {
    if (!symbol || symbol.length < 2) {
      setRelatedNews([])
      return
    }
    setLoadingNews(true)
    const coin = symbol.replace(/\/.*$/, '').toUpperCase()
    newsNodeApi.getNews({ coin }).then((res) => {
      if (res.success && res.items) setRelatedNews(res.items.slice(0, 5))
      else setRelatedNews([])
    }).catch(() => setRelatedNews([])).finally(() => setLoadingNews(false))
  }, [symbol])

  const getSentimentIcon = (sentiment: string) => {
    if (sentiment === 'positive') return <TrendingUp className="w-5 h-5 text-green-500" />
    if (sentiment === 'negative') return <TrendingDown className="w-5 h-5 text-red-500" />
    return <Minus className="w-5 h-5 text-slate-400" />
  }

  const getSentimentColor = (sentiment: string) => {
    if (sentiment === 'positive') return 'text-green-500'
    if (sentiment === 'negative') return 'text-red-500'
    return 'text-slate-400'
  }

  const inputCls =
    'rounded-xl border border-white/[0.08] bg-zinc-950/50 px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:border-crypto-cyan/40 focus:outline-none focus:ring-1 focus:ring-crypto-cyan/30'

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.sentiment.title')}
        subtitle={t('page.sentiment.subtitle')}
        icon={MessageSquare}
        badge={t('page.sentiment.badge')}
        accent="emerald"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="BTC"
              className={`${inputCls} w-28 sm:w-32`}
            />
            <button
              type="button"
              onClick={loadSentiment}
              disabled={loading || !symbol.trim()}
              className="btn-crypto disabled:opacity-50"
            >
              {loading ? t('page.sentiment.analyzing') : t('page.sentiment.analyze')}
            </button>
          </div>
        }
      />

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
          <div className="text-red-400">{error}</div>
        </div>
      )}

      {loading && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center">
          <div className="text-slate-400">{t('page.sentiment.loadingBody')}</div>
        </div>
      )}

      {!loading && !error && sentimentData && (
        <>
          {/* Overall Sentiment with Gauge Chart */}
          {sentimentData.overall_sentiment && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4">{t('page.sentiment.generalTitle')}</h3>
              
              {/* Gauge Chart */}
              {sentimentData.overall_sentiment.gauge_score !== undefined && (
                <div className="mb-6">
                  <SentimentGauge 
                    score={sentimentData.overall_sentiment.gauge_score} 
                    sentiment={sentimentData.overall_sentiment.sentiment}
                  />
                </div>
              )}
              
              {/* Sentiment Info */}
              <div className="flex items-center space-x-4 mb-4">
                {getSentimentIcon(sentimentData.overall_sentiment.sentiment)}
                <div>
                  <div className={`text-2xl font-bold ${getSentimentColor(sentimentData.overall_sentiment.sentiment)}`}>
                    {sentimentData.overall_sentiment.sentiment.toUpperCase()}
                  </div>
                  <div className="text-sm text-slate-400">
                    {t('page.sentiment.overallStats')
                      .replace('{score}', sentimentData.overall_sentiment.score.toFixed(4))
                      .replace(
                        '{confidence}',
                        `${(sentimentData.overall_sentiment.confidence * 100).toFixed(1)}%`,
                      )
                      .replace('{sample}', String(sentimentData.overall_sentiment.sample_size))}
                  </div>
                </div>
              </div>
              
              {/* Explanation - Why this score was given */}
              {(sentimentData.overall_sentiment.explanation || sentimentData.explanation) && (
                <div className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
                  <div className="flex items-start space-x-2 mb-2">
                    <Info className="w-5 h-5 text-primary-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-semibold text-primary-400 mb-1">
                        {t('page.sentiment.explanationHeading')}
                      </h4>
                      <p className="text-sm text-slate-300 leading-relaxed">
                        {sentimentData.overall_sentiment.explanation || sentimentData.explanation}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* News Sentiment */}
          {sentimentData.news_sentiment.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                <Newspaper className="w-5 h-5" />
                <span>
                  {t('page.sentiment.newsSection').replace(
                    '{count}',
                    String(sentimentData.news_sentiment.length),
                  )}
                </span>
              </h3>
              <div className="space-y-3">
                {sentimentData.news_sentiment.slice(0, 5).map((item, idx) => (
                  <div key={idx} className="bg-slate-700 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        {getSentimentIcon(item.sentiment)}
                        <span className={`font-medium ${getSentimentColor(item.sentiment)}`}>
                          {item.sentiment.toUpperCase()}
                        </span>
                        <span className="text-sm text-slate-400">({item.score.toFixed(3)})</span>
                      </div>
                      {item.article && (
                        <a
                          href={item.article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary-400 hover:text-primary-300"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                    {item.article && (
                      <div>
                        <div className="text-sm text-white font-medium">{item.article.title}</div>
                        <div className="text-xs text-slate-400 mt-1">{item.article.source}</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Reddit Sentiment */}
          {sentimentData.reddit_sentiment.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                <MessageSquare className="w-5 h-5" />
                <span>
                  {t('page.sentiment.redditSection').replace(
                    '{count}',
                    String(sentimentData.reddit_sentiment.length),
                  )}
                </span>
              </h3>
              <div className="space-y-3">
                {sentimentData.reddit_sentiment.slice(0, 5).map((item, idx) => (
                  <div key={idx} className="bg-slate-700 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        {getSentimentIcon(item.sentiment)}
                        <span className={`font-medium ${getSentimentColor(item.sentiment)}`}>
                          {item.sentiment.toUpperCase()}
                        </span>
                        <span className="text-sm text-slate-400">({item.score.toFixed(3)})</span>
                      </div>
                      {item.post && (
                        <a
                          href={item.post.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary-400 hover:text-primary-300"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                    {item.post && (
                      <div>
                        <div className="text-sm text-white font-medium">{item.post.title}</div>
                        <div className="text-xs text-slate-400 mt-1">r/{item.post.subreddit}</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sources */}
          {sentimentData.sources && sentimentData.sources.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4">
                {t('page.sentiment.allSources').replace(
                  '{count}',
                  String(sentimentData.sources.length),
                )}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {sentimentData.sources.map((source, idx) => (
                  <a
                    key={idx}
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-slate-700 rounded-lg p-3 hover:bg-slate-600 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{source.title}</div>
                        <div className="text-xs text-slate-400 mt-1">{source.type}</div>
                      </div>
                      <ExternalLink className="w-4 h-4 text-primary-400 flex-shrink-0 ml-2" />
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* İlgili Haberler (Node News API - son 5) */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
              <Newspaper className="w-5 h-5" />
              <span>
                {t('page.sentiment.relatedNews').replace('{symbol}', symbol)}
              </span>
            </h3>
            {loadingNews ? (
              <div className="text-slate-400">{t('page.sentiment.loadingNews')}</div>
            ) : relatedNews.length === 0 ? (
              <div className="text-slate-400">{t('page.sentiment.noRelatedNews')}</div>
            ) : (
              <div className="space-y-3">
                {relatedNews.map((item, idx) => (
                  <a
                    key={`${item.url}-${idx}`}
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-slate-700 rounded-lg p-3 hover:bg-slate-600 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-white line-clamp-2">{item.title}</div>
                        <div className="text-xs text-slate-400 mt-1">
                          {item.source} · {timeAgo(item.publishedAt)}
                          {item.sentiment && (
                            <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                              item.sentiment === 'POSITIVE' ? 'bg-emerald-500/20 text-emerald-400' :
                              item.sentiment === 'NEGATIVE' ? 'bg-red-500/20 text-red-400' : 'bg-slate-600 text-slate-400'
                            }`}>
                              {item.sentiment}
                            </span>
                          )}
                        </div>
                      </div>
                      <ExternalLink className="w-4 h-4 text-primary-400 flex-shrink-0 mt-0.5" />
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {!loading && !error && (!sentimentData || sentimentData.success === false) && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center">
          <div className="text-slate-400">{t('page.sentiment.emptyHint')}</div>
          {sentimentData && sentimentData.success === false && (
            <div className="text-red-400 mt-2">
              {t('page.sentiment.errorPrefix')}{' '}
              {sentimentData.error || t('page.sentiment.unknownError')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}




