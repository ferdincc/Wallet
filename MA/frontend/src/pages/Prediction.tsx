import { useEffect, useState } from 'react'
import { predictionApi, ablationApi } from '../services/api'
import PageHeader from '../components/PageHeader'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
import { Sparkles, TrendingUp, TrendingDown, BarChart3, AlertCircle, Info, Shield, History, GitCompare, X } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart, BarChart, Bar } from 'recharts'

interface PredictionData {
  success: boolean
  symbol: string
  model: string
  predictions: Array<{
    date: string
    price: number
    lower?: number
    upper?: number
    prophet_price?: number
    lightgbm_price?: number
  }>
  metrics: {
    mae: number
    mape: number
    directional_accuracy: number
  }
  current_price: number
  predicted_change?: {
    absolute: number
    percentage: number
    first_period_price: number
    last_period_price: number
  }
  confidence_score?: number  // 0-100
  confidence_message?: string  // "Modelimiz %65 güven oranıyla yükseliş bekliyor"
  direction?: string  // "yükseliş" or "düşüş"
  explanation?: string  // XAI explanation
  feature_importance?: { [key: string]: number }  // Feature importance for XAI
  warning?: string  // Warning message for fallback models
}

interface BacktestStats {
  total_predictions: number
  correct_predictions: number
  accuracy: number
  mae: number
  mape: number
  model_type: string
  symbol: string
  period: string
}

export default function Prediction() {
  const { t, locale } = useAppPreferences()
  const dateLocale = 'en-US'
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [model, setModel] = useState('ensemble')
  const [periods, setPeriods] = useState(7)
  const [predictionData, setPredictionData] = useState<PredictionData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [backtestStats, setBacktestStats] = useState<BacktestStats | null>(null)
  const [, setLoadingBacktest] = useState(false)
  const [ablationStudy, setAblationStudy] = useState<any>(null)
  const [showAblation, setShowAblation] = useState(false)

  const loadPrediction = async () => {
    if (!symbol.trim()) {
      setError(t('prediction.errorSymbol'))
      return
    }
    
    setLoading(true)
    setError(null)
    setPredictionData(null)
    
    try {
      const data = await predictionApi.getPrediction(symbol, 'binance', '1h', periods, model, locale)
      if (data && data.success !== false) {
        setPredictionData(data)
        // Reload backtest stats after new prediction
        loadBacktestStats()
      } else {
        setError(t('prediction.errorFetch'))
      }
    } catch (error: any) {
      console.error('Error loading prediction:', error)
      setError(error.response?.data?.detail || t('prediction.errorLoad'))
    } finally {
      setLoading(false)
    }
  }

  const loadBacktestStats = async () => {
    setLoadingBacktest(true)
    try {
      const stats = await predictionApi.getBacktestStats(symbol, model, 30)
      setBacktestStats(stats)
    } catch (error) {
      console.error('Error loading backtest stats:', error)
    } finally {
      setLoadingBacktest(false)
    }
  }

  useEffect(() => {
    // Auto-load on mount and when UI language changes (forecast text is server-rendered)
    if (symbol) {
      loadPrediction()
      loadBacktestStats()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale])

  useEffect(() => {
    // Reload backtest stats when symbol or model changes
    if (symbol) {
      loadBacktestStats()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, model])

  const field =
    'rounded-xl border border-white/[0.08] bg-zinc-950/50 px-3 py-2 text-sm text-white focus:border-crypto-cyan/40 focus:outline-none focus:ring-1 focus:ring-crypto-cyan/30'

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('page.prediction.title')}
        subtitle={t('page.prediction.subtitle')}
        icon={Sparkles}
        badge={t('page.prediction.badge')}
        accent="violet"
      />

      <div className="crypto-card flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <label className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t('page.prediction.symbol')}</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="BTC/USDT"
            className={field}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t('page.prediction.model')}</label>
          <select value={model} onChange={(e) => setModel(e.target.value)} className={field}>
            <option value="ensemble">Ensemble</option>
            <option value="prophet">Prophet</option>
            <option value="lightgbm">LightGBM</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t('page.prediction.period')}</label>
          <input
            type="number"
            value={periods}
            onChange={(e) => setPeriods(parseInt(e.target.value, 10) || 7)}
            min={1}
            max={30}
            className={`${field} w-full sm:w-24`}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadPrediction}
            disabled={loading || !symbol.trim()}
            className="btn-crypto disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {loading ? t('page.prediction.predicting') : t('page.prediction.predict')}
          </button>
          <button
            type="button"
            onClick={async () => {
              try {
                const study = await ablationApi.compareModels(symbol, 30)
                setAblationStudy(study)
                setShowAblation(true)
              } catch (error) {
                console.error('Error loading ablation study:', error)
              }
            }}
            disabled={loading || !symbol.trim()}
            className="btn-crypto-ghost border-crypto-violet/30 text-crypto-violet disabled:opacity-50"
            title={t('prediction.compareTitle')}
          >
            <GitCompare className="h-4 w-4" />
            {t('page.prediction.ablation')}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
          <div className="flex items-start space-x-2">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-red-400 font-semibold mb-1">{t('prediction.errorHeading')}</div>
              <div className="text-red-300 text-sm">{error}</div>
              <div className="text-red-400/70 text-xs mt-2">{t('prediction.errorTransparency')}</div>
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center">
          <div className="text-slate-400">{t('prediction.loading')}</div>
        </div>
      )}

      {!loading && !error && predictionData && predictionData.success && (
        <>
          {/* Current Price and Prediction Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="text-sm text-slate-400 mb-2">{t('prediction.currentPriceLabel')}</div>
              <div className="text-3xl font-bold text-white">
                ${predictionData.current_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
            
            {predictionData.predicted_change && (
              <>
                <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                  <div className="text-sm text-slate-400 mb-2">
                    {t('prediction.priceInDays').replace('{n}', String(periods))}
                  </div>
                  <div className="text-3xl font-bold text-white">
                    ${predictionData.predicted_change.last_period_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
                
                <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                  <div className="text-sm text-slate-400 mb-2">{t('prediction.expectedChange')}</div>
                  <div className={`text-3xl font-bold flex items-center space-x-2 ${
                    predictionData.predicted_change.percentage >= 0 ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {predictionData.predicted_change.percentage >= 0 ? (
                      <TrendingUp className="w-6 h-6" />
                    ) : (
                      <TrendingDown className="w-6 h-6" />
                    )}
                    <span>
                      {predictionData.predicted_change.percentage >= 0 ? '+' : ''}
                      {predictionData.predicted_change.percentage.toFixed(2)}%
                    </span>
                  </div>
                  <div className="text-sm text-slate-400 mt-2">
                    ${predictionData.predicted_change.absolute.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Warning if using fallback model */}
          {predictionData.model === 'fallback' && (
            <div className="bg-yellow-500/10 border border-yellow-500 rounded-lg p-4">
              <div className="flex items-start space-x-2">
                <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-yellow-400 font-semibold mb-1">{t('prediction.warnSimpleModel')}</div>
                  <div className="text-yellow-300 text-sm">
                    {t('prediction.fallbackDetail')}{' '}
                    <code className="bg-slate-800 px-2 py-1 rounded">pip install prophet lightgbm</code>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Backtest Statistics */}
          {backtestStats && backtestStats.total_predictions > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                <History className="w-5 h-5" />
                <span>{t('prediction.performance30d')}</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('prediction.totalPredictions')}</div>
                  <div className="text-2xl font-bold text-white">{backtestStats.total_predictions}</div>
                </div>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('prediction.successLabel')}</div>
                  <div className="text-2xl font-bold text-green-500">{backtestStats.correct_predictions}</div>
                </div>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('prediction.successRate')}</div>
                  <div className="text-2xl font-bold text-white">
                    {(backtestStats.accuracy * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-slate-700 rounded-lg p-4">
                  <div className="text-sm text-slate-400 mb-1">{t('prediction.avgMape')}</div>
                  <div className="text-2xl font-bold text-white">
                    {backtestStats.mape.toFixed(2)}%
                  </div>
                </div>
              </div>
              <div className="mt-4 text-sm text-slate-400">
                💡{' '}
                {t('prediction.hintBacktest')
                  .replace('{total}', String(backtestStats.total_predictions))
                  .replace('{correct}', String(backtestStats.correct_predictions))}{' '}
                {t('prediction.hintBacktestFooter')}
              </div>
            </div>
          )}

          {/* Confidence Score and XAI Explanation */}
          {(predictionData.confidence_score !== undefined || predictionData.explanation || predictionData.feature_importance) && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
                <Shield className="w-5 h-5" />
                <span>{t('prediction.xaiTitle')}</span>
              </h3>
              
              {predictionData.confidence_score !== undefined && (
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-slate-400">{t('prediction.confidenceScore')}</span>
                    <span className={`text-lg font-bold ${
                      predictionData.confidence_score >= 70 ? 'text-green-500' :
                      predictionData.confidence_score >= 50 ? 'text-yellow-500' : 'text-red-500'
                    }`}>
                      %{predictionData.confidence_score.toFixed(0)}
                    </span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-3 mb-2">
                    <div
                      className={`h-3 rounded-full transition-all ${
                        predictionData.confidence_score >= 70 ? 'bg-green-500' :
                        predictionData.confidence_score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${predictionData.confidence_score}%` }}
                    ></div>
                  </div>
                  {predictionData.confidence_message && (
                    <div className="text-sm font-semibold text-white">
                      {predictionData.confidence_message}
                    </div>
                  )}
                </div>
              )}
              
              {predictionData.explanation && (
                <div className="bg-slate-700/50 rounded-lg p-4 border border-slate-600 mb-4">
                  <div className="flex items-start space-x-2">
                    <Info className="w-5 h-5 text-primary-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-semibold text-primary-400 mb-1">
                        {t('prediction.explanationTitle')}
                      </h4>
                      <p className="text-sm text-slate-300 leading-relaxed">
                        {predictionData.explanation}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Feature Importance Visualization */}
              {predictionData.feature_importance && Object.keys(predictionData.feature_importance).length > 0 && (
                <div className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
                  <h4 className="text-sm font-semibold text-primary-400 mb-3 flex items-center space-x-2">
                    <BarChart3 className="w-4 h-4" />
                    <span>{t('prediction.featureTitle')}</span>
                  </h4>
                  <p className="text-xs text-slate-400 mb-3">{t('prediction.featureIntro')}</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart 
                      data={Object.entries(predictionData.feature_importance)
                        .map(([name, value]) => ({ name, value: parseFloat(value.toFixed(1)) }))
                        .sort((a, b) => b.value - a.value)}
                      layout="vertical"
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis type="number" stroke="#9ca3af" domain={[0, 100]} />
                      <YAxis 
                        type="category" 
                        dataKey="name" 
                        stroke="#9ca3af"
                        width={120}
                      />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                        formatter={(value: number) => `${value.toFixed(1)}%`}
                      />
                      <Bar 
                        dataKey="value" 
                        fill="#3b82f6"
                        radius={[0, 4, 4, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="mt-3 text-xs text-slate-400">
                    {t('prediction.featureHint')}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Model Metrics */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4 flex items-center space-x-2">
              <BarChart3 className="w-5 h-5" />
              <span>{t('prediction.modelMetricsTitle').replace('{model}', predictionData.model)}</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-700 rounded-lg p-4">
                <div className="text-sm text-slate-400 mb-1">MAE</div>
                <div className="text-2xl font-bold text-white">
                  {predictionData.metrics.mae.toFixed(4)}
                </div>
              </div>
              <div className="bg-slate-700 rounded-lg p-4">
                <div className="text-sm text-slate-400 mb-1">MAPE</div>
                <div className="text-2xl font-bold text-white">
                  {predictionData.metrics.mape.toFixed(2)}%
                </div>
              </div>
              <div className="bg-slate-700 rounded-lg p-4">
                <div className="text-sm text-slate-400 mb-1">{t('prediction.dirAccuracy')}</div>
                <div className="text-2xl font-bold text-white">
                  {predictionData.metrics.directional_accuracy.toFixed(2)}%
                </div>
              </div>
            </div>
          </div>

          {/* Prediction Chart with Confidence Interval */}
          {predictionData.predictions.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h3 className="text-xl font-semibold text-white mb-4">{t('prediction.chartTitle')}</h3>
              <ResponsiveContainer width="100%" height={400}>
                {predictionData.predictions[0]?.lower !== undefined ? (
                  // Area chart with confidence interval
                  <AreaChart data={predictionData.predictions}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="date" 
                      stroke="#9ca3af"
                      tickFormatter={(value) => new Date(value).toLocaleDateString(dateLocale, { month: 'short', day: 'numeric' })}
                    />
                    <YAxis stroke="#9ca3af" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                      labelFormatter={(value) => new Date(value).toLocaleString(dateLocale)}
                      formatter={(value: number) => `$${value.toFixed(2)}`}
                    />
                    <Legend />
                    <Area 
                      type="monotone" 
                      dataKey="upper" 
                      stroke="#22c55e" 
                      fill="#22c55e" 
                      fillOpacity={0.1}
                      name={t('prediction.upperBand')}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="lower" 
                      stroke="#ef4444" 
                      fill="#ef4444" 
                      fillOpacity={0.1}
                      name={t('prediction.lowerBand')}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="price" 
                      stroke="#3b82f6" 
                      strokeWidth={2}
                      dot={{ fill: '#3b82f6', r: 4 }}
                      name={t('prediction.predictedLine')}
                    />
                  </AreaChart>
                ) : (
                  // Simple line chart without confidence interval
                  <LineChart data={predictionData.predictions}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="date" 
                      stroke="#9ca3af"
                      tickFormatter={(value) => new Date(value).toLocaleDateString(dateLocale, { month: 'short', day: 'numeric' })}
                    />
                    <YAxis stroke="#9ca3af" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                      labelFormatter={(value) => new Date(value).toLocaleString(dateLocale)}
                      formatter={(value: number) => `$${value.toFixed(2)}`}
                    />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="price" 
                      stroke="#3b82f6" 
                      strokeWidth={2}
                      dot={{ fill: '#3b82f6', r: 4 }}
                      name={t('prediction.predictedLine')}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          )}

          {/* Predictions Table */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-xl font-semibold text-white mb-4">{t('prediction.dailyTitle')}</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400">{t('prediction.tableDate')}</th>
                    <th className="text-right py-3 px-4 text-slate-400">{t('prediction.tablePredictedPrice')}</th>
                    {predictionData.model === 'ensemble' && (
                      <>
                        <th className="text-right py-3 px-4 text-slate-400">Prophet</th>
                        <th className="text-right py-3 px-4 text-slate-400">LightGBM</th>
                      </>
                    )}
                    {predictionData.predictions[0]?.lower && (
                      <>
                        <th className="text-right py-3 px-4 text-slate-400">{t('prediction.lower')}</th>
                        <th className="text-right py-3 px-4 text-slate-400">{t('prediction.upper')}</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {predictionData.predictions.map((pred, idx) => (
                    <tr key={idx} className="border-b border-slate-700">
                      <td className="py-3 px-4 text-white">
                        {new Date(pred.date).toLocaleDateString(dateLocale)}
                      </td>
                      <td className="py-3 px-4 text-right text-white font-medium">
                        ${pred.price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </td>
                      {predictionData.model === 'ensemble' && (
                        <>
                          <td className="py-3 px-4 text-right text-slate-400">
                            {pred.prophet_price ? `$${pred.prophet_price.toFixed(2)}` : '-'}
                          </td>
                          <td className="py-3 px-4 text-right text-slate-400">
                            {pred.lightgbm_price ? `$${pred.lightgbm_price.toFixed(2)}` : '-'}
                          </td>
                        </>
                      )}
                      {pred.lower && pred.upper && (
                        <>
                          <td className="py-3 px-4 text-right text-red-400">
                            ${pred.lower.toFixed(2)}
                          </td>
                          <td className="py-3 px-4 text-right text-green-400">
                            ${pred.upper.toFixed(2)}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!loading && !error && !predictionData && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center">
          <div className="text-slate-400">{t('prediction.emptyHint')}</div>
        </div>
      )}

      {/* Ablation Study Modal */}
      {showAblation && ablationStudy && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white flex items-center space-x-2">
                <GitCompare className="w-5 h-5" />
                <span>{t('prediction.ablationModalTitle')}</span>
              </h3>
              <button
                onClick={() => setShowAblation(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              <div className="bg-slate-700 rounded-lg p-4">
                <div className="text-sm text-slate-400 mb-2">{t('prediction.ablationSymbol')}</div>
                <div className="text-lg font-bold text-white">{ablationStudy.symbol}</div>
                <div className="text-xs text-slate-400 mt-1">
                  {t('prediction.lastDays').replace('{n}', String(ablationStudy.period_days))}
                </div>
              </div>

              {/* Comparison Table */}
              <div className="bg-slate-700 rounded-lg p-4">
                <h4 className="text-lg font-semibold text-white mb-3">{t('prediction.modelCompareTitle')}</h4>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-600">
                        <th className="text-left py-3 px-4 text-slate-400">{t('prediction.approach')}</th>
                        <th className="text-right py-3 px-4 text-slate-400">{t('prediction.predCount')}</th>
                        <th className="text-right py-3 px-4 text-slate-400">{t('prediction.successRate')}</th>
                        <th className="text-right py-3 px-4 text-slate-400">MAE</th>
                        <th className="text-right py-3 px-4 text-slate-400">MAPE</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-slate-600">
                        <td className="py-3 px-4 text-white">
                          <div className="font-medium">{t('prediction.ablationTechnical')}</div>
                          <div className="text-xs text-slate-400">{ablationStudy.technical_only.description}</div>
                        </td>
                        <td className="py-3 px-4 text-right text-white">{ablationStudy.technical_only.count}</td>
                        <td className="py-3 px-4 text-right text-white">
                          {(ablationStudy.technical_only.accuracy * 100).toFixed(1)}%
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.technical_only.mae.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.technical_only.mape.toFixed(2)}%
                        </td>
                      </tr>
                      <tr className="border-b border-slate-600">
                        <td className="py-3 px-4 text-white">
                          <div className="font-medium">{t('prediction.ablationTechSent')}</div>
                          <div className="text-xs text-slate-400">{ablationStudy.technical_sentiment.description}</div>
                        </td>
                        <td className="py-3 px-4 text-right text-white">{ablationStudy.technical_sentiment.count}</td>
                        <td className="py-3 px-4 text-right text-green-400">
                          {(ablationStudy.technical_sentiment.accuracy * 100).toFixed(1)}%
                          {ablationStudy.comparison.improvement_technical_to_sentiment > 0 && (
                            <span className="text-xs ml-1">
                              (+{ablationStudy.comparison.improvement_technical_to_sentiment.toFixed(1)}%)
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.technical_sentiment.mae.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.technical_sentiment.mape.toFixed(2)}%
                        </td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 text-white">
                          <div className="font-medium">{t('prediction.ablationMulti')}</div>
                          <div className="text-xs text-slate-400">{ablationStudy.multi_agent.description}</div>
                        </td>
                        <td className="py-3 px-4 text-right text-white">{ablationStudy.multi_agent.count}</td>
                        <td className="py-3 px-4 text-right text-green-400">
                          {(ablationStudy.multi_agent.accuracy * 100).toFixed(1)}%
                          {ablationStudy.comparison.improvement_sentiment_to_multi > 0 && (
                            <span className="text-xs ml-1">
                              (+{ablationStudy.comparison.improvement_sentiment_to_multi.toFixed(1)}%)
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.multi_agent.mae.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {ablationStudy.multi_agent.mape.toFixed(2)}%
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Conclusion */}
              <div className="bg-blue-500/10 border border-blue-500 rounded-lg p-4">
                <h4 className="text-lg font-semibold text-blue-400 mb-2">{t('prediction.conclusionTitle')}</h4>
                <p className="text-sm text-slate-300 leading-relaxed">
                  {ablationStudy.conclusion}
                </p>
                <div className="mt-3 text-xs text-slate-400">
                  💡 {t('prediction.ablationHint')}
                </div>
              </div>

              <button
                onClick={() => setShowAblation(false)}
                className="w-full bg-slate-700 text-white px-4 py-2 rounded-lg hover:bg-slate-600"
              >
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}




