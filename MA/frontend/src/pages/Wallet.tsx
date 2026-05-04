import { useCallback, useMemo, useState } from 'react'
import axios from 'axios'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { useWalletAnalysis } from '../contexts/WalletAnalysisContext'
import { walletNodeApi, type WalletAnalyzeResponse, type WalletTxRow } from '../services/api'
import {
  Search,
  Loader2,
  Wallet,
  ExternalLink,
  RefreshCw,
  ChevronDown,
} from 'lucide-react'

const CHAIN_PILLS: { key: string; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'ethereum', label: 'Ethereum' },
  { key: 'base', label: 'Base' },
  { key: 'arbitrum', label: 'Arbitrum' },
  { key: 'polygon', label: 'Polygon' },
]

/** Tablo / rozet — Alchemy tarama ile aynı dört ağ */
const CHAIN_VISUAL: Record<string, { abbr: string; ring: string }> = {
  ethereum: { abbr: 'ETH', ring: 'ring-blue-400/40 bg-blue-500/15' },
  base: { abbr: 'BASE', ring: 'ring-sky-400/40 bg-sky-500/15' },
  arbitrum: { abbr: 'ARB', ring: 'ring-indigo-400/40 bg-indigo-500/15' },
  polygon: { abbr: 'POL', ring: 'ring-violet-400/40 bg-violet-500/15' },
}

function fmtUsd(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(n)
}

function shortAddr(a: string): string {
  if (!a || a.length < 12) return a
  return `${a.slice(0, 6)}…${a.slice(-4)}`
}

function explorerUrl(chain: string, hash: string): string {
  const map: Record<string, string> = {
    ethereum: 'https://etherscan.io/tx/',
    polygon: 'https://polygonscan.com/tx/',
    arbitrum: 'https://arbiscan.io/tx/',
    base: 'https://basescan.org/tx/',
  }
  const base = map[chain] || map.ethereum
  return `${base}${hash}`
}

type Period = 'today' | '7d' | '30d' | '90d' | 'custom'

/** input type="date" (YYYY-MM-DD) → yerel gün başı (gg.aa.yyyy ile uyumlu) */
function localDayStartSec(yyyyMmDd: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(yyyyMmDd)) return null
  const [y, m, d] = yyyyMmDd.split('-').map(Number)
  return Math.floor(new Date(y, m - 1, d, 0, 0, 0, 0).getTime() / 1000)
}

function localDayEndSec(yyyyMmDd: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(yyyyMmDd)) return null
  const [y, m, d] = yyyyMmDd.split('-').map(Number)
  return Math.floor(new Date(y, m - 1, d, 23, 59, 59, 999).getTime() / 1000)
}

function periodBounds(period: Period, customFrom: string, customTo: string): { min: number; max: number } {
  const now = Math.floor(Date.now() / 1000)
  const max = now
  const tenYears = 10 * 365 * 86400
  let min = now - tenYears
  if (period === 'today') {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    min = Math.max(Math.floor(d.getTime() / 1000), now - tenYears)
  } else if (period === '7d') min = now - 7 * 86400
  else if (period === '30d') min = now - 30 * 86400
  else if (period === '90d') min = now - 90 * 86400
  else if (period === 'custom' && customFrom && customTo) {
    const s1 = localDayStartSec(customFrom)
    const e1 = localDayEndSec(customFrom)
    const s2 = localDayStartSec(customTo)
    const e2 = localDayEndSec(customTo)
    if (s1 !== null && e1 !== null && s2 !== null && e2 !== null) {
      const lo = Math.min(s1, s2)
      const hi = Math.max(e1, e2)
      return { min: Math.max(lo, now - tenYears), max: Math.min(hi, now) }
    }
  }
  return { min, max }
}

export default function WalletPage() {
  const { t } = useAppPreferences()
  const { setWalletAnalysis, clearWalletAnalysis, walletAddress: sessionAddr } = useWalletAnalysis()
  const [input, setInput] = useState('')
  const [data, setData] = useState<WalletAnalyzeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chainFilter, setChainFilter] = useState<string>('all')
  const [period, setPeriod] = useState<Period>('30d')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [txDir, setTxDir] = useState<'all' | 'in' | 'out'>('all')
  /** Backend ile aynı: listelenen işlemler ve özet kartları (varsayılan 10$) */
  const [minTrxUsd, setMinTrxUsd] = useState('10')
  const [txVisible, setTxVisible] = useState(60)

  const analyze = useCallback(async () => {
    const addr = input.trim()
    if (!/^0x[a-fA-F0-9]{40}$/.test(addr)) {
      setError(t('wallet.invalidAddress'))
      return
    }
    setError(null)
    setLoading(true)
    setData(null)
    setTxVisible(60)
    try {
      const minVal = parseFloat(minTrxUsd.replace(',', '.'))
      const res = await walletNodeApi.analyze(addr, 'all', Number.isFinite(minVal) ? minVal : 10)
      setData(res)
      const chatCtx = [res.llmContext || '', res.walletContext ? JSON.stringify(res.walletContext, null, 2) : '']
        .filter(Boolean)
        .join('\n\n--- walletContext (JSON) ---\n')
      setWalletAnalysis({
        address: res.address,
        llmContext: chatCtx,
        raw: res,
      })
    } catch (e: unknown) {
      if (axios.isAxiosError(e)) {
        const errBody = e.response?.data as { error?: string } | undefined
        const serverMsg = errBody?.error && String(errBody.error).trim()
        setError(serverMsg || t('wallet.errorData'))
      } else {
        const msg = e && typeof e === 'object' && 'message' in e ? String((e as Error).message) : String(e)
        setError(msg || t('wallet.errorGeneric'))
      }
    } finally {
      setLoading(false)
    }
  }, [input, minTrxUsd, setWalletAnalysis, t])

  const filteredTotals = useMemo(() => {
    if (!data) return null
    if (chainFilter === 'all') return data.totals
    const row = data.chainStats?.find((c) => c.chain === chainFilter)
    if (row) {
      return {
        minUsd: data.totals.minUsd,
        portfolioUsd: row.portfolioUsd,
        in30dUsd: row.in30dUsd,
        out30dUsd: row.out30dUsd,
        net30dUsd: row.net30dUsd,
        in90dUsd: row.in90dUsd,
        out90dUsd: row.out90dUsd,
        net90dUsd: row.net90dUsd,
        lifetimeNetUsd: row.lifetimeNetUsd,
      }
    }
    return data.totals
  }, [data, chainFilter])

  const filteredTxs = useMemo(() => {
    if (!data?.transactions) return []
    const { min, max } = periodBounds(period, customFrom, customTo)
    let rows = data.transactions.filter((x) => x.ts >= min && x.ts <= max)
    if (chainFilter !== 'all') rows = rows.filter((x) => x.chain === chainFilter)
    if (txDir === 'in') rows = rows.filter((x) => x.direction === 'IN')
    if (txDir === 'out') rows = rows.filter((x) => x.direction === 'OUT')
    rows.sort((a, b) => b.ts - a.ts)
    return rows
  }, [data, period, customFrom, customTo, chainFilter, txDir])

  const txSlice = useMemo(() => filteredTxs.slice(0, txVisible), [filteredTxs, txVisible])

  const aggBar = useMemo(() => {
    let inU = 0
    let outU = 0
    for (const x of filteredTxs) {
      if (x.direction === 'IN') inU += x.usdValue
      else outU += x.usdValue
    }
    return { inU, outU, net: inU - outU, n: filteredTxs.length }
  }, [filteredTxs])

  const pillLabel = (key: string) => {
    const row = CHAIN_PILLS.find((p) => p.key === key)
    if (!row) return key
    return row.label
  }

  return (
    <div className="space-y-8 text-[1.08rem] leading-relaxed sm:text-[1.12rem]">
      <PageHeader title={t('wallet.title')} subtitle={t('wallet.subtitle')} icon={Wallet} accent="violet" />

      <div className="rounded-2xl border border-white/[0.08] bg-zinc-950/50 p-4 shadow-glow sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t('wallet.placeholder')}
              className="w-full rounded-xl border border-white/[0.08] bg-zinc-950/80 py-3 pl-10 pr-3 font-mono text-base text-white placeholder:text-zinc-600 focus:border-crypto-violet/40 focus:outline-none focus:ring-1 focus:ring-crypto-violet/30"
              spellCheck={false}
              autoComplete="off"
            />
          </div>
          <button
            type="button"
            onClick={() => void analyze()}
            disabled={loading}
            className="btn-crypto inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-base font-semibold disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {t('wallet.analyze')}
          </button>
        </div>
        {sessionAddr && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-zinc-400">
            <span>
              {t('wallet.active')}:{' '}
              <span className="font-mono text-zinc-200">{shortAddr(sessionAddr)}</span>
            </span>
            <button
              type="button"
              onClick={() => {
                clearWalletAnalysis()
                setInput('')
                setData(null)
              }}
              className="rounded-lg border border-white/10 px-2 py-1 text-zinc-300 hover:bg-white/[0.06]"
            >
              {t('wallet.clear')}
            </button>
          </div>
        )}
        {error && (
          <p className="mt-3 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </div>

      <div>
        <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-zinc-400">{t('wallet.chainFilter')}</p>
        <div className="flex flex-wrap gap-2">
          {CHAIN_PILLS.map((p) => {
            const active = chainFilter === p.key
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => setChainFilter(p.key)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                  active
                    ? 'bg-gradient-to-r from-crypto-violet/40 to-crypto-cyan/25 text-white shadow-glow border border-crypto-cyan/30'
                    : 'border border-white/10 bg-zinc-900/80 text-zinc-400 hover:border-white/20 hover:text-white'
                }`}
              >
                {pillLabel(p.key)}
              </button>
            )
          })}
        </div>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-crypto-cyan/25 bg-zinc-950/40 py-16">
          <Loader2 className="h-10 w-10 animate-spin text-crypto-cyan" />
          <p className="text-base text-zinc-400">{t('wallet.scanning')}</p>
        </div>
      )}

      {data && !loading && (
        <>
          {data.warning && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              {data.warning}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { k: 'total', v: filteredTotals?.portfolioUsd ?? 0 },
              { k: 'in30', v: filteredTotals?.in30dUsd ?? 0 },
              { k: 'out30', v: filteredTotals?.out30dUsd ?? 0 },
              { k: 'pnl', v: filteredTotals?.net30dUsd ?? 0 },
            ].map((card) => (
              <div
                key={card.k}
                className="rounded-2xl border border-white/[0.07] bg-zinc-900/60 p-5 backdrop-blur-sm"
              >
                <div className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
                  {t(`wallet.card.${card.k}`)}
                </div>
                <div
                  className={`mt-3 font-display text-3xl font-extrabold tabular-nums tracking-tight sm:text-[2rem] ${
                    card.k === 'pnl' && card.v < 0
                      ? 'text-rose-400'
                      : card.k === 'pnl' && card.v > 0
                        ? 'text-emerald-400'
                        : 'text-white'
                  }`}
                >
                  {fmtUsd(card.v)}
                </div>
              </div>
            ))}
          </div>

          {data.walletInsight && (
            <p className="text-sm text-zinc-500">
              {t('wallet.insight')
                .replace('{tx}', String(data.walletInsight.totalTransfersIndexed))
                .replace('{dominant}', data.walletInsight.dominantChain)
                .replace('{tokens}', String(data.walletInsight.tokenCount))}
            </p>
          )}

          {filteredTotals && (
            <p className="text-sm text-zinc-400">
              {t('wallet.ninetySummary')
                .replace('{in30}', fmtUsd(filteredTotals.in30dUsd))
                .replace('{out30}', fmtUsd(filteredTotals.out30dUsd))
                .replace('{in90}', fmtUsd(filteredTotals.in90dUsd))
                .replace('{out90}', fmtUsd(filteredTotals.out90dUsd))
                .replace('{min}', fmtUsd(filteredTotals.minUsd))}
            </p>
          )}

          <section className="space-y-4">
            <div>
              <h3 className="text-xl font-bold text-white sm:text-2xl">{t('wallet.txTitle')}</h3>
              <p className="mt-1 text-sm text-zinc-500">{t('wallet.usdApprox')}</p>
            </div>
            <div className="flex flex-col gap-3 rounded-xl border-2 border-crypto-violet/35 bg-zinc-900/70 p-4 shadow-[0_0_24px_-8px_rgba(139,92,246,0.25)] ring-1 ring-white/5 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex flex-col gap-2 text-base text-zinc-200">
                <span className="text-base font-bold text-zinc-100">{t('wallet.minTrxUsd')}</span>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={minTrxUsd}
                    onChange={(e) => setMinTrxUsd(e.target.value)}
                    className="w-32 rounded-lg border-2 border-crypto-violet/40 bg-zinc-950 px-3 py-2 text-lg font-semibold text-white focus:border-crypto-cyan/50 focus:outline-none focus:ring-2 focus:ring-crypto-cyan/20"
                  />
                  {([1, 5, 10, 25, 100] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setMinTrxUsd(String(v))}
                      className="rounded-md border border-white/15 bg-zinc-900/80 px-2.5 py-1.5 text-sm font-medium text-zinc-300 hover:border-crypto-cyan/50 hover:text-white"
                    >
                      ${v}
                    </button>
                  ))}
                </div>
              </label>
              <p className="max-w-md text-sm leading-snug text-zinc-400">{t('wallet.minTrxHint')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(['today', '7d', '30d', '90d', 'custom'] as Period[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                    period === p
                      ? 'bg-crypto-violet/30 text-white border border-crypto-violet/40'
                      : 'border border-white/10 text-zinc-400 hover:text-white'
                  }`}
                >
                  {t(`wallet.period.${p}`)}
                </button>
              ))}
            </div>
            {period === 'custom' && (
              <div className="flex flex-wrap gap-2">
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className="rounded-lg border border-white/10 bg-zinc-950 px-2 py-1.5 text-base text-white"
                />
                <span className="self-center text-zinc-500">—</span>
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className="rounded-lg border border-white/10 bg-zinc-950 px-2 py-1.5 text-base text-white"
                />
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              {(['all', 'in', 'out'] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setTxDir(d)}
                  className={`rounded-lg px-3 py-1.5 text-sm ${
                    txDir === d ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'border border-white/10 text-zinc-400'
                  }`}
                >
                  {t(`wallet.dir.${d}`)}
                </button>
              ))}
            </div>
            <div className="rounded-lg border border-white/[0.06] bg-zinc-900/40 px-4 py-2.5 text-sm text-zinc-300">
              {t('wallet.txBar')
                .replace('{in}', fmtUsd(aggBar.inU))
                .replace('{out}', fmtUsd(aggBar.outU))
                .replace('{net}', fmtUsd(aggBar.net))
                .replace('{n}', String(aggBar.n))}
            </div>
            <div className="max-h-[560px] overflow-x-auto overflow-y-auto rounded-xl border border-white/[0.06]">
              <table className="w-full min-w-[720px] text-left text-base">
                <thead className="sticky top-0 z-[1] border-b border-white/[0.06] bg-zinc-900/95 text-sm font-bold uppercase tracking-wide text-zinc-300 backdrop-blur-sm">
                  <tr>
                    <th className="px-3 py-2">{t('wallet.col.date')}</th>
                    <th className="px-3 py-2">{t('wallet.col.chain')}</th>
                    <th className="px-3 py-2">{t('wallet.col.amount')}</th>
                    <th className="px-3 py-2">{t('wallet.col.usd')}</th>
                    <th className="px-3 py-2">{t('wallet.col.type')}</th>
                    <th className="px-3 py-2">{t('wallet.col.hash')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {txSlice.map((tx: WalletTxRow) => {
                    const amtLine =
                      tx.amountLabel && tx.amountLabel.trim() !== ''
                        ? tx.amountLabel
                        : `${tx.amount} ${tx.tokenSymbol}`
                    return (
                      <tr key={`${tx.hash}-${tx.ts}-${tx.tokenSymbol}`} className="hover:bg-white/[0.02]">
                        <td className="whitespace-nowrap px-3 py-2.5 text-zinc-300">
                          {new Date(tx.ts * 1000).toLocaleString('en-US')}
                        </td>
                        <td className="px-3 py-2 text-zinc-300">
                          <div className="flex items-center gap-2">
                            {CHAIN_VISUAL[tx.chain] ? (
                              <span
                                title={tx.chainLabel}
                                className={`inline-flex h-7 min-w-[2.25rem] shrink-0 items-center justify-center rounded-md ring-1 px-1.5 font-mono text-[10px] font-semibold uppercase text-zinc-200 ${CHAIN_VISUAL[tx.chain].ring}`}
                              >
                                {CHAIN_VISUAL[tx.chain].abbr}
                              </span>
                            ) : null}
                            <span className="text-zinc-300">{tx.chainLabel}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-base font-medium text-zinc-100">{amtLine}</td>
                        <td className="px-3 py-2.5 tabular-nums text-base font-semibold text-zinc-100">{fmtUsd(tx.usdValue)}</td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`text-base font-semibold ${tx.direction === 'IN' ? 'text-emerald-400' : 'text-rose-400'}`}
                          >
                            {tx.direction}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <a
                            href={explorerUrl(tx.chain, tx.hash)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-crypto-cyan hover:underline"
                          >
                            {shortAddr(tx.hash)}
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {filteredTxs.length > txVisible && (
              <button
                type="button"
                onClick={() => setTxVisible((v) => v + 80)}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 py-3 text-base text-zinc-300 hover:bg-white/[0.04]"
              >
                <ChevronDown className="h-4 w-4" />
                {t('wallet.loadMore')}
              </button>
            )}
          </section>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void analyze()}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-base text-zinc-300 hover:bg-white/[0.06]"
            >
              <RefreshCw className="h-4 w-4" />
              {t('common.refresh')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
