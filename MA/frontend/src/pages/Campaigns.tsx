import { useCallback, useEffect, useMemo, useState } from 'react'
import { campaignsNodeApi, CampaignItemNode, CampaignTypeTagNode } from '../services/api'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { ExternalLink, Flame, Target } from 'lucide-react'

const REFRESH_MS = 30 * 60 * 1000
const NEW_MS = 2 * 60 * 60 * 1000

type SummaryFilter = 'none' | 'active' | 'today' | 'ai' | 'ending'
type SourceFilter = 'all' | 'galxe' | 'layer3' | 'nitter' | 'coinmarketcap'
type SortMode = 'score' | 'newest' | 'endingSoon'

const TYPE_TAG_STYLE: Record<CampaignTypeTagNode, string> = {
  AIRDROP: 'bg-violet-600/90 text-white border-violet-400/50',
  TESTNET: 'bg-blue-600/90 text-white border-blue-400/50',
  AI_CONTENT: 'bg-orange-600/90 text-white border-orange-400/50',
  NFT_MINT: 'bg-pink-600/90 text-white border-pink-400/50',
  REFERRAL: 'bg-emerald-600/90 text-white border-emerald-400/50',
  LAUNCH: 'bg-amber-500/90 text-slate-900 border-amber-300/50',
  OTHER: 'bg-slate-600/90 text-slate-100 border-slate-500/50',
}

function startOfTodayUtc(): Date {
  const d = new Date()
  d.setUTCHours(0, 0, 0, 0)
  return d
}

function isTodayUtc(iso?: string): boolean {
  if (!iso) return false
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return false
  const d = new Date(iso)
  const s = startOfTodayUtc()
  const e = new Date(s)
  e.setUTCDate(e.getUTCDate() + 1)
  return d >= s && d < e
}

function addedToday(c: CampaignItemNode): boolean {
  return isTodayUtc(c.publishedAt) || isTodayUtc(c.dateAdded) || isTodayUtc(c.startTime)
}

function isActiveCampaign(c: CampaignItemNode): boolean {
  if (c.source === 'nitter') return false
  if (!c.endTime) return true
  return new Date(c.endTime) > new Date()
}

function endsWithinDaysAhead(c: CampaignItemNode, days: number): boolean {
  if (!c.endTime) return false
  const end = new Date(c.endTime)
  const now = new Date()
  if (end <= now) return false
  return end.getTime() - now.getTime() <= days * 86400000
}

function primaryTimestamp(c: CampaignItemNode): number {
  const iso = c.publishedAt || c.dateAdded || c.startTime || ''
  if (!iso) return 0
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? 0 : t
}

function isNewItem(c: CampaignItemNode): boolean {
  const t = primaryTimestamp(c)
  if (!t) return false
  return Date.now() - t < NEW_MS
}

function sourceLabel(s: CampaignItemNode['source']): string {
  switch (s) {
    case 'galxe':
      return 'Galxe'
    case 'layer3':
      return 'Layer3'
    case 'nitter':
      return 'Twitter'
    case 'coinmarketcap':
      return 'CoinMarketCap'
    default:
      return s
  }
}

function endClass(iso?: string): string {
  if (!iso) return 'text-slate-400'
  const end = new Date(iso)
  const now = new Date()
  if (end <= now) return 'text-slate-500'
  const ms = end.getTime() - now.getTime()
  const days = ms / 86400000
  if (days <= 3) return 'text-red-400 font-medium'
  if (days <= 7) return 'text-amber-400 font-medium'
  return 'text-slate-300'
}

function CampaignCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="h-6 w-20 bg-slate-700 rounded" />
        <div className="h-6 w-12 bg-slate-700 rounded" />
      </div>
      <div className="h-5 bg-slate-700 rounded w-3/4 mb-3" />
      <div className="h-3 bg-slate-700 rounded w-1/2 mb-2" />
      <div className="h-3 bg-slate-700 rounded w-2/3 mb-4" />
      <div className="h-9 bg-slate-700 rounded w-full" />
    </div>
  )
}

export default function Campaigns() {
  const { t } = useAppPreferences()
  const dateLocale = 'en-US'

  const SOURCE_OPTIONS = useMemo(
    () =>
      [
        { id: 'all' as const, label: t('common.all') },
        { id: 'galxe' as const, label: 'Galxe' },
        { id: 'layer3' as const, label: 'Layer3' },
        { id: 'nitter' as const, label: 'Twitter' },
        { id: 'coinmarketcap' as const, label: 'CoinMarketCap' },
      ] satisfies { id: SourceFilter; label: string }[],
    [t],
  )

  const TYPE_OPTIONS = useMemo(
    () =>
      [
        { id: 'all' as const, label: t('common.all') },
        { id: 'AIRDROP' as const, label: t('campaigns.typeAirdrop') },
        { id: 'TESTNET' as const, label: t('campaigns.typeTestnet') },
        { id: 'AI_CONTENT' as const, label: t('campaigns.typeAiContent') },
        { id: 'NFT_MINT' as const, label: t('campaigns.typeNftMint') },
        { id: 'REFERRAL' as const, label: t('campaigns.typeReferral') },
        { id: 'LAUNCH' as const, label: t('campaigns.typeLaunch') },
      ] satisfies { id: 'all' | CampaignTypeTagNode; label: string }[],
    [t],
  )

  const TYPE_TAG_LABEL = useMemo(
    () =>
      ({
        AIRDROP: t('campaigns.badgeAIRDROP'),
        TESTNET: t('campaigns.badgeTESTNET'),
        AI_CONTENT: t('campaigns.badgeAI_CONTENT'),
        NFT_MINT: t('campaigns.badgeNFT_MINT'),
        REFERRAL: t('campaigns.badgeREFERRAL'),
        LAUNCH: t('campaigns.badgeLAUNCH'),
        OTHER: t('campaigns.badgeOTHER'),
      }) satisfies Record<CampaignTypeTagNode, string>,
    [t],
  )

  const formatDate = useCallback(
    (iso?: string) => {
      if (!iso) return '—'
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return '—'
      return d.toLocaleString(dateLocale, { dateStyle: 'short', timeStyle: 'short' })
    },
    [dateLocale],
  )

  const endDaysLeft = useCallback(
    (iso?: string) => {
      if (!iso) return null
      const end = new Date(iso)
      const now = new Date()
      if (end <= now) return t('campaigns.ended')
      const d = Math.ceil((end.getTime() - now.getTime()) / 86400000)
      if (d === 0) return t('campaigns.today')
      return t('campaigns.daysLeft').replace('{n}', String(d))
    },
    [t],
  )

  const [raw, setRaw] = useState<CampaignItemNode[]>([])
  const [loading, setLoading] = useState(true)
  const [summaryFilter, setSummaryFilter] = useState<SummaryFilter>('none')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [typeFilter, setTypeFilter] = useState<'all' | CampaignTypeTagNode>('all')
  const [sortMode, setSortMode] = useState<SortMode>('score')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await campaignsNodeApi.getAll()
      if (res.success && res.items) setRaw(res.items)
      else setRaw([])
    } catch (e) {
      console.warn('Campaigns load failed', e)
      setRaw([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const timer = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer)
  }, [load])

  const stats = useMemo(() => {
    const totalActive = raw.filter(isActiveCampaign).length
    const todayAdded = raw.filter(addedToday).length
    const aiCount = raw.filter((c) => c.typeTag === 'AI_CONTENT').length
    const ending3 = raw.filter((c) => endsWithinDaysAhead(c, 3)).length
    return { totalActive, todayAdded, aiCount, ending3 }
  }, [raw])

  const filteredBase = useMemo(() => {
    let list = [...raw]

    if (sourceFilter !== 'all') {
      list = list.filter((c) => c.source === sourceFilter)
    }
    if (typeFilter !== 'all') {
      list = list.filter((c) => c.typeTag === typeFilter)
    }

    if (summaryFilter === 'active') {
      list = list.filter(isActiveCampaign)
    } else if (summaryFilter === 'today') {
      list = list.filter(addedToday)
    } else if (summaryFilter === 'ai') {
      list = list.filter((c) => c.typeTag === 'AI_CONTENT')
    } else if (summaryFilter === 'ending') {
      list = list.filter((c) => endsWithinDaysAhead(c, 3))
    }

    return list
  }, [raw, sourceFilter, typeFilter, summaryFilter])

  const gridItems = useMemo(() => {
    const nonTwitter = filteredBase.filter((c) => c.source !== 'nitter')
    return sortList(nonTwitter, sortMode)
  }, [filteredBase, sortMode])

  const twitterItems = useMemo(() => {
    const tw = filteredBase.filter((c) => c.source === 'nitter')
    return sortList(tw, sortMode)
  }, [filteredBase, sortMode])

  function toggleSummary(key: SummaryFilter) {
    setSummaryFilter((prev) => (prev === key ? 'none' : key))
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <PageHeader
        title={t('page.campaigns.title')}
        subtitle={t('page.campaigns.subtitle')}
        icon={Target}
        badge={t('page.campaigns.badge')}
        accent="amber"
      />

      {/* Özet kartları */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <button
          type="button"
          onClick={() => toggleSummary('active')}
          className={`rounded-2xl border p-4 text-left transition-all duration-300 ${
            summaryFilter === 'active'
              ? 'border-crypto-cyan/40 bg-gradient-to-br from-crypto-cyan/15 to-crypto-violet/10 shadow-glow ring-1 ring-crypto-cyan/30'
              : 'border-white/[0.08] bg-zinc-900/50 hover:border-white/15 hover:shadow-card'
          }`}
        >
          <p className="text-sm text-zinc-500">{t('campaigns.summaryActive')}</p>
          <p className="mt-1 font-display text-2xl font-bold text-white">{stats.totalActive}</p>
          <p className="mt-2 text-xs text-zinc-600">{t('campaigns.summaryActiveHint')}</p>
        </button>
        <button
          type="button"
          onClick={() => toggleSummary('today')}
          className={`rounded-2xl border p-4 text-left transition-all duration-300 ${
            summaryFilter === 'today'
              ? 'border-crypto-cyan/40 bg-gradient-to-br from-crypto-cyan/15 to-crypto-violet/10 shadow-glow ring-1 ring-crypto-cyan/30'
              : 'border-white/[0.08] bg-zinc-900/50 hover:border-white/15 hover:shadow-card'
          }`}
        >
          <p className="text-sm text-zinc-500">{t('campaigns.summaryToday')}</p>
          <p className="mt-1 font-display text-2xl font-bold text-white">{stats.todayAdded}</p>
          <p className="mt-2 text-xs text-zinc-600">{t('campaigns.summaryTodayHint')}</p>
        </button>
        <button
          type="button"
          onClick={() => toggleSummary('ai')}
          className={`rounded-2xl border p-4 text-left transition-all duration-300 ${
            summaryFilter === 'ai'
              ? 'border-crypto-cyan/40 bg-gradient-to-br from-crypto-cyan/15 to-crypto-violet/10 shadow-glow ring-1 ring-crypto-cyan/30'
              : 'border-white/[0.08] bg-zinc-900/50 hover:border-white/15 hover:shadow-card'
          }`}
        >
          <p className="text-sm text-zinc-500">{t('campaigns.summaryAi')}</p>
          <p className="mt-1 font-display text-2xl font-bold text-white">{stats.aiCount}</p>
          <p className="mt-2 text-xs text-zinc-600">{t('campaigns.summaryAiHint')}</p>
        </button>
        <button
          type="button"
          onClick={() => toggleSummary('ending')}
          className={`rounded-2xl border p-4 text-left transition-all duration-300 ${
            summaryFilter === 'ending'
              ? 'border-crypto-cyan/40 bg-gradient-to-br from-crypto-cyan/15 to-crypto-violet/10 shadow-glow ring-1 ring-crypto-cyan/30'
              : 'border-white/[0.08] bg-zinc-900/50 hover:border-white/15 hover:shadow-card'
          }`}
        >
          <p className="text-sm text-zinc-500">{t('campaigns.summaryEnding')}</p>
          <p className="mt-1 font-display text-2xl font-bold text-white">{stats.ending3}</p>
          <p className="mt-2 text-xs text-zinc-600">{t('campaigns.summaryEndingHint')}</p>
        </button>
      </div>

      {/* Filtreler */}
      <div className="crypto-card space-y-4 !py-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-slate-400 text-sm w-full sm:w-auto">{t('campaigns.source')}</span>
          {SOURCE_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setSourceFilter(o.id)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-all ${
                sourceFilter === o.id
                  ? 'border border-crypto-cyan/35 bg-gradient-to-r from-crypto-cyan/20 to-crypto-violet/15 text-white shadow-glow'
                  : 'border border-transparent bg-white/[0.05] text-zinc-400 hover:bg-white/[0.08] hover:text-white'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-slate-400 text-sm w-full sm:w-auto">{t('campaigns.typeColon')}</span>
          {TYPE_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setTypeFilter(o.id)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-all ${
                typeFilter === o.id
                  ? 'border border-crypto-cyan/35 bg-gradient-to-r from-crypto-cyan/20 to-crypto-violet/15 text-white shadow-glow'
                  : 'border border-transparent bg-white/[0.05] text-zinc-400 hover:bg-white/[0.08] hover:text-white'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-700">
          <span className="text-slate-400 text-sm">{t('campaigns.sortBy')}:</span>
          {(
            [
              { id: 'score' as SortMode, label: t('campaigns.sortScore') },
              { id: 'newest' as SortMode, label: t('campaigns.sortNewest') },
              { id: 'endingSoon' as SortMode, label: t('campaigns.sortEnding') },
            ] as const
          ).map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setSortMode(o.id)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-all ${
                sortMode === o.id
                  ? 'border border-white/15 bg-white/10 text-white'
                  : 'border border-transparent bg-zinc-900/60 text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-300'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Kampanya grid */}
      <section>
        <h2 className="mb-4 font-display text-lg font-semibold text-white">{t('page.campaigns.campaigns')}</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <CampaignCardSkeleton key={i} />
            ))}
          </div>
        ) : gridItems.length === 0 ? (
          <p className="text-slate-500 text-center py-12 border border-dashed border-slate-700 rounded-xl">
            {t('page.campaigns.empty')}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {gridItems.map((c) => (
              <article
                key={c.id}
                className="flex flex-col rounded-2xl border border-white/[0.08] bg-zinc-900/45 p-4 shadow-card backdrop-blur-sm transition-all duration-300 hover:border-crypto-cyan/20 hover:shadow-glow"
              >
                <div className="flex justify-between items-start gap-2 mb-2">
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded border ${TYPE_TAG_STYLE[c.typeTag]}`}
                  >
                    {TYPE_TAG_LABEL[c.typeTag]}
                  </span>
                  <span className="flex items-center gap-1 text-sm font-bold text-amber-400 shrink-0">
                    {c.importanceScore >= 70 && <Flame className="w-4 h-4" />}
                    {c.importanceScore}
                  </span>
                </div>
                <div className="flex items-start gap-2 mb-2">
                  <h3 className="font-bold text-white text-sm leading-snug flex-1">{c.title}</h3>
                  {isNewItem(c) && (
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-600/90 text-white shrink-0">
                      {t('campaigns.new')}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mb-1">
                  {sourceLabel(c.source)} · {formatDate(c.publishedAt || c.dateAdded || c.startTime)}
                </p>
                {(c.rewardAmount || c.rewardType) && (
                  <p className="text-slate-300 text-sm mb-2">
                    {t('campaigns.reward')} {c.rewardAmount || c.rewardType || '—'}
                  </p>
                )}
                <p className={`text-xs mt-auto pt-2 ${endClass(c.endTime)}`}>
                  {t('campaigns.ends')}{' '}
                  {c.endTime ? `${formatDate(c.endTime)} (${endDaysLeft(c.endTime)})` : '—'}
                </p>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-crypto mt-3 w-full py-2.5 text-sm"
                >
                  {t('page.campaigns.join')}
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Twitter / Nitter */}
      <section>
        <h2 className="mb-2 flex items-center gap-2 font-display text-lg font-semibold text-white">
          <span>{t('page.campaigns.announce')}</span>
        </h2>
        <p className="mb-4 text-sm text-zinc-500">{t('page.campaigns.twitterHint')}</p>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-slate-800/80 border border-slate-700 animate-pulse" />
            ))}
          </div>
        ) : twitterItems.length === 0 ? (
          <p className="text-slate-500 text-center py-8 border border-dashed border-slate-700 rounded-xl text-sm">
            {t('campaigns.twitterEmpty')}
          </p>
        ) : (
          <div className="space-y-3">
            {twitterItems.map((c) => (
              <article
                key={c.id}
                className="rounded-2xl border border-white/[0.08] bg-zinc-900/40 p-4 backdrop-blur-sm transition-all hover:border-white/15"
              >
                <div className="flex justify-between items-start gap-2 mb-2">
                  <span className="text-primary-400 font-medium text-sm">@{c.author || 'unknown'}</span>
                  <span className="text-xs text-slate-500">{formatDate(c.publishedAt)}</span>
                </div>
                <p className="text-slate-200 text-sm whitespace-pre-wrap break-words">{c.text || c.title}</p>
                {isNewItem(c) && (
                  <span className="inline-block mt-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-600/90 text-white">
                    {t('campaigns.new')}
                  </span>
                )}
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary-400 text-sm mt-3 hover:underline"
                >
                  {t('campaigns.view')}
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function sortList<T extends CampaignItemNode>(list: T[], mode: SortMode): T[] {
  const copy = [...list]
  if (mode === 'score') {
    copy.sort((a, b) => b.importanceScore - a.importanceScore)
  } else if (mode === 'newest') {
    copy.sort((a, b) => primaryTimestamp(b) - primaryTimestamp(a))
  } else {
    copy.sort((a, b) => {
      const endA = a.endTime ? new Date(a.endTime).getTime() : 1e15
      const endB = b.endTime ? new Date(b.endTime).getTime() : 1e15
      const now = Date.now()
      const validA = a.endTime && endA > now ? endA : 1e15
      const validB = b.endTime && endB > now ? endB : 1e15
      return validA - validB
    })
  }
  return copy
}
