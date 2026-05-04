import { useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { backtestNodeApi, BacktestSummary } from '../services/api'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { AlertCircle, BarChart3, Calendar, PlayCircle, RefreshCw } from 'lucide-react'

type UiSymbolOption = {
  label: string
  value: string // UI value, e.g. "BTC/USDT"
  backendSymbol: string // Node backtest sembolü, e.g. "BTCUSDT"
}

const SYMBOL_OPTIONS: UiSymbolOption[] = [
  { label: 'BTC / USDT', value: 'BTC/USDT', backendSymbol: 'BTCUSDT' },
  { label: 'ETH / USDT', value: 'ETH/USDT', backendSymbol: 'ETHUSDT' },
  { label: 'BNB / USDT', value: 'BNB/USDT', backendSymbol: 'BNBUSDT' },
  { label: 'SOL / USDT', value: 'SOL/USDT', backendSymbol: 'SOLUSDT' },
]

type ModelKey = 'prophet' | 'lgbm' | 'arima' | 'ensemble'

const MODEL_LABELS: Record<ModelKey, string> = {
  prophet: 'Prophet',
  lgbm: 'LightGBM',
  arima: 'ARIMA',
  ensemble: 'Ensemble',
}

interface ChartPoint {
  date: string
  timestamp: number
  actual?: number
  prophet?: number
  lgbm?: number
  arima?: number
  ensemble?: number
}

export default function Backtest() {
  const { t } = useAppPreferences()
  const dateLocale = 'en-US'
  const [selectedSymbol, setSelectedSymbol] = useState<UiSymbolOption>(SYMBOL_OPTIONS[0])
  const [startDate, setStartDate] = useState<string>(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 2)
    return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate] = useState<string>(() => {
    const d = new Date()
    return d.toISOString().slice(0, 10)
  })
  const [modelSelection, setModelSelection] = useState<Record<ModelKey, boolean>>({
    prophet: true,
    lgbm: true,
    arima: true,
    ensemble: true,
  })
  const [windowDays, setWindowDays] = useState<number>(30)

  const [loading, setLoading] = useState(false)
  const [progressText, setProgressText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [summaries, setSummaries] = useState<BacktestSummary[] | null>(null)

  const selectedModels = useMemo(
    () => (Object.keys(modelSelection) as ModelKey[]).filter((k) => modelSelection[k]),
    [modelSelection],
  )

  const chartData: ChartPoint[] = useMemo(() => {
    if (!summaries || summaries.length === 0) return []

    const map = new Map<string, ChartPoint>()

    const upsert = (model: string, summary: BacktestSummary) => {
      summary.results.forEach((r) => {
        const key = r.date
        const existing = map.get(key) ?? {
          date: key,
          timestamp: new Date(key).getTime(),
        }
        if (existing.actual == null && typeof r.actual_price === 'number') {
          existing.actual = r.actual_price
        }
        const m = model.toLowerCase()
        if (m === 'prophet') existing.prophet = r.predicted_price
        if (m === 'lgbm' || m === 'lightgbm') existing.lgbm = r.predicted_price
        if (m === 'arima') existing.arima = r.predicted_price
        if (m === 'ensemble') existing.ensemble = r.predicted_price
        map.set(key, existing)
      })
    }

    summaries.forEach((s) => upsert(s.model, s))

    return Array.from(map.values()).sort((a, b) => a.timestamp - b.timestamp)
  }, [summaries])

  const bestWorstByScore = useMemo(() => {
    if (!summaries || summaries.length === 0) return { bestModel: null as string | null, worstModel: null as string | null }

    const scored = summaries.map((s) => {
      const mapeScore = Number.isFinite(s.avgMAPE) ? 100 - Math.min(s.avgMAPE, 100) : 0
      const rmseScore = Number.isFinite(s.avgRMSE) && s.avgRMSE > 0 ? 100 - Math.min(s.avgRMSE / 100, 100) : 0
      const dirScore = Number.isFinite(s.directionAccuracy) ? s.directionAccuracy : 0
      const score = mapeScore * 0.4 + rmseScore * 0.2 + dirScore * 0.4
      return { model: s.model, score }
    })

    const sorted = scored.slice().sort((a, b) => b.score - a.score)
    return {
      bestModel: sorted[0]?.model ?? null,
      worstModel: sorted[sorted.length - 1]?.model ?? null,
    }
  }, [summaries])

  const handleToggleModel = (key: ModelKey) => {
    setModelSelection((prev) => ({
      ...prev,
      [key]: !prev[key],
    }))
  }

  const handleRunBacktest = async () => {
    if (!startDate || !endDate) {
      setError(t('backtest.errorDates'))
      return
    }
    if (selectedModels.length === 0) {
      setError(t('backtest.errorModel'))
      return
    }

    setLoading(true)
    setError(null)
    setSummaries(null)
    setProgressText(t('backtest.progressLoad'))

    try {
      const payload = {
        symbol: selectedSymbol.backendSymbol,
        models: selectedModels,
        startDate,
        endDate,
        windowDays,
      }

      setProgressText(t('backtest.progressBinance'))
      const data = await backtestNodeApi.run(payload)

      if (!data || !data.summaries || data.summaries.length === 0) {
        setError(t('backtest.errorNoResult'))
        return
      }

      setSummaries(data.summaries)
      setProgressText(null)
    } catch (e: any) {
      console.error('Backtest run error', e)
      const message =
        e?.response?.data?.details ||
        e?.response?.data?.error ||
        e?.message ||
        t('backtest.errorRun')
      setError(message)
      setProgressText(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.backtest.title')}
        subtitle={t('page.backtest.subtitle')}
        icon={BarChart3}
        badge={t('page.backtest.badge')}
        accent="cyan"
      />

      {/* Control Panel */}
      <div className="crypto-card">
        <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold text-white sm:text-xl">
          <BarChart3 className="h-5 w-5 text-crypto-cyan" strokeWidth={2} />
          <span>{t('page.backtest.control')}</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {/* Coin seçici */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">{t('common.coin')}</label>
            <select
              value={selectedSymbol.value}
              onChange={(e) => {
                const opt = SYMBOL_OPTIONS.find((s) => s.value === e.target.value)
                if (opt) setSelectedSymbol(opt)
              }}
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {SYMBOL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Tarih aralığı */}
          <div>
            <label className="block text-sm text-slate-400 mb-1 flex items-center space-x-1">
              <Calendar className="w-3 h-3" />
              <span>{t('backtest.labelStart')}</span>
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1 flex items-center space-x-1">
              <Calendar className="w-3 h-3" />
              <span>{t('backtest.labelEnd')}</span>
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {/* Window days */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">{t('backtest.labelWindow')}</label>
            <input
              type="number"
              min={10}
              max={120}
              value={windowDays}
              onChange={(e) => setWindowDays(parseInt(e.target.value, 10) || 30)}
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        {/* Model seçimi */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
          {(Object.keys(modelSelection) as ModelKey[]).map((key) => (
            <label
              key={key}
              className={`flex items-center space-x-2 px-3 py-2 rounded-lg border cursor-pointer ${
                modelSelection[key]
                  ? 'bg-primary-600/20 border-primary-500 text-white'
                  : 'bg-slate-800 border-slate-600 text-slate-300'
              }`}
            >
              <input
                type="checkbox"
                checked={modelSelection[key]}
                onChange={() => handleToggleModel(key)}
                className="form-checkbox h-4 w-4 text-primary-500 rounded border-slate-500 bg-slate-900"
              />
              <span className="text-sm">{MODEL_LABELS[key]}</span>
            </label>
          ))}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-slate-400">
            💡 {t('backtest.hintWalkForward')}
          </div>
          <div className="flex items-center space-x-3">
            {summaries && (
              <button
                type="button"
                onClick={() => setSummaries(null)}
                className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600"
              >
                <RefreshCw className="w-4 h-4" />
                <span>{t('backtest.clearResults')}</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleRunBacktest}
              disabled={loading}
              className="flex items-center space-x-2 px-5 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
            >
              <PlayCircle className="w-4 h-4" />
              <span>{loading ? t('backtest.running') : t('backtest.run')}</span>
            </button>
          </div>
        </div>

        {/* Loading / Progress */}
        {loading && (
          <div className="mt-4 bg-slate-900/60 border border-slate-700 rounded-lg p-3 flex items-center space-x-3">
            <div className="flex items-center justify-center">
              <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="flex-1">
              <div className="text-sm text-slate-200">{t('backtest.runningHint')}</div>
              {progressText && <div className="text-xs text-slate-400 mt-1">{progressText}</div>}
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4 flex space-x-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-semibold text-red-400 mb-1">{t('backtest.errorTitle')}</div>
            <div className="text-sm text-red-200">{error}</div>
          </div>
        </div>
      )}

      {/* Chart */}
      {summaries && summaries.length > 0 && chartData.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h3 className="text-xl font-semibold text-white mb-4">{t('backtest.chartTitle')}</h3>
          <ResponsiveContainer width="100%" height={420}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                stroke="#9ca3af"
                tickFormatter={(value) =>
                  new Date(value).toLocaleDateString(dateLocale, { month: 'short', day: 'numeric' })
                }
              />
              <YAxis stroke="#9ca3af" />
              <Tooltip
                contentStyle={{ backgroundColor: '#020617', border: '1px solid #4b5563' }}
                labelFormatter={(value) => new Date(value).toLocaleString(dateLocale)}
                formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name]}
              />
              <Legend />
              {/* Actual */}
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#ffffff"
                strokeWidth={2}
                dot={false}
                name={t('backtest.actualPrice')}
              />
              {/* Prophet */}
              <Line
                type="monotone"
                dataKey="prophet"
                stroke="#3b82f6"
                strokeWidth={1.8}
                dot={false}
                name="Prophet"
              />
              {/* LightGBM */}
              <Line
                type="monotone"
                dataKey="lgbm"
                stroke="#22c55e"
                strokeWidth={1.8}
                dot={false}
                name="LightGBM"
              />
              {/* ARIMA */}
              <Line
                type="monotone"
                dataKey="arima"
                stroke="#fb923c"
                strokeWidth={1.8}
                dot={false}
                name="ARIMA"
              />
              {/* Ensemble */}
              <Line
                type="monotone"
                dataKey="ensemble"
                stroke="#a855f7"
                strokeWidth={2}
                dot={false}
                name="Ensemble"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Comparison Table */}
      {summaries && summaries.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h3 className="text-xl font-semibold text-white mb-4">{t('backtest.tableTitle')}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-3 px-4 text-slate-400">{t('backtest.colModel')}</th>
                  <th className="text-right py-3 px-4 text-slate-400">{t('backtest.colAvgMape')}</th>
                  <th className="text-right py-3 px-4 text-slate-400">{t('backtest.colRmse')}</th>
                  <th className="text-right py-3 px-4 text-slate-400">{t('backtest.colDirAcc')}</th>
                  <th className="text-left py-3 px-4 text-slate-400">{t('backtest.colEval')}</th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((s) => {
                  const isBest = bestWorstByScore.bestModel === s.model
                  const isWorst = bestWorstByScore.worstModel === s.model
                  const rowClass = isBest
                    ? 'bg-emerald-900/40 border-emerald-500/40'
                    : isWorst
                    ? 'bg-red-900/40 border-red-500/40'
                    : 'bg-slate-900/40 border-slate-700/60'

                  let evaluation = t('backtest.evalMid')
                  if (isBest) evaluation = t('backtest.evalBest')
                  if (isWorst) evaluation = t('backtest.evalWorst')

                  return (
                    <tr key={s.model} className={`${rowClass} border-b`}>
                      <td className="py-3 px-4 text-white font-medium">
                        {MODEL_LABELS[s.model as ModelKey] || s.model}
                      </td>
                      <td className="py-3 px-4 text-right text-white">
                        {Number.isFinite(s.avgMAPE) ? s.avgMAPE.toFixed(2) : '-'}
                      </td>
                      <td className="py-3 px-4 text-right text-white">
                        {Number.isFinite(s.avgRMSE) ? s.avgRMSE.toFixed(2) : '-'}
                      </td>
                      <td className="py-3 px-4 text-right text-white">
                        {Number.isFinite(s.directionAccuracy) ? s.directionAccuracy.toFixed(1) : '-'}
                      </td>
                      <td className="py-3 px-4 text-sm">
                        <span
                          className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${
                            isBest
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/60'
                              : isWorst
                              ? 'bg-red-500/20 text-red-300 border border-red-500/60'
                              : 'bg-slate-700/60 text-slate-200 border border-slate-600/80'
                          }`}
                        >
                          {evaluation}
                        </span>
                        {s.error && (
                          <div className="mt-1 text-xs text-red-300">
                            {t('backtest.rowError')}{' '}
                            <span className="italic">{s.error}</span>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !summaries && !error && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center text-slate-400 text-sm">
          {t('backtest.emptyHint')}
        </div>
      )}
    </div>
  )
}

