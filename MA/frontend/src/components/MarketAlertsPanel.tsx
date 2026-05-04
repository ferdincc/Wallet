import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, AlertTriangle, ChevronDown, ChevronUp, X } from 'lucide-react'
import type { Ticker } from '../services/api'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

const severityBadge = (severity: string) =>
  severity === 'critical'
    ? 'bg-red-600 text-white'
    : severity === 'high'
      ? 'bg-orange-600 text-white'
      : 'bg-yellow-600 text-white'

export interface MarketAlertsPanelProps {
  flashAlerts: any[]
  anomalies: any | null
  selectedSymbol: string
  selectedTicker: Ticker | null
  /** Dashboard: start collapsed so the page stays short */
  defaultCollapsed?: boolean
  showFlash?: boolean
  onDismissFlash?: () => void
  /** Haberler sayfası: başlık + biraz daha açık düzen */
  variant?: 'sidebar' | 'page'
}

export default function MarketAlertsPanel({
  flashAlerts,
  anomalies,
  selectedSymbol,
  selectedTicker,
  defaultCollapsed = true,
  showFlash = true,
  onDismissFlash,
  variant = 'sidebar',
}: MarketAlertsPanelProps) {
  const { t } = useAppPreferences()
  const timeLocale = 'en-US'
  const [expanded, setExpanded] = useState(!defaultCollapsed)

  const anomalyList = anomalies?.anomalies && Array.isArray(anomalies.anomalies) ? anomalies.anomalies : []
  const flashCount = showFlash ? flashAlerts.length : 0
  const anomalyCount = anomalyList.length
  const hasAnything = flashCount > 0 || anomalyCount > 0

  if (!hasAnything) {
    if (variant === 'page') {
      return (
        <div
          id="piyasa-uyarilari"
          className="bg-slate-800 rounded-lg p-4 border border-slate-700"
        >
          <h3 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
            <Bell className="w-5 h-5 text-slate-400" />
            {t('alerts.marketTitle')}
          </h3>
          <p className="text-sm text-slate-400">{t('alerts.emptyDetail')}</p>
        </div>
      )
    }
    return null
  }

  const maxScroll = variant === 'page' ? 'max-h-64' : 'max-h-52'

  return (
    <div
      id={variant === 'page' ? 'piyasa-uyarilari' : undefined}
      className={`rounded-lg border ${
        variant === 'page'
          ? 'bg-slate-800 border-slate-700 p-4'
          : 'bg-slate-800/90 border-slate-600 p-3'
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Bell className={`h-4 w-4 flex-shrink-0 ${flashCount > 0 ? 'text-red-400' : 'text-slate-500'}`} />
          <div className="min-w-0">
            <div className={`font-semibold ${variant === 'page' ? 'text-base text-white' : 'text-sm text-white'}`}>
              {t('alerts.marketTitle')}
            </div>
            <div className="truncate text-xs text-slate-400">
              {flashCount > 0 && <span className="text-red-300">{flashCount} flash</span>}
              {flashCount > 0 && anomalyCount > 0 && <span> · </span>}
              {anomalyCount > 0 && (
                <span className="text-yellow-400">
                  {t('alerts.anomaliesSummary')
                    .replace('{n}', String(anomalyCount))
                    .replace('{symbol}', selectedSymbol)}
                </span>
              )}
            </div>
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 flex-shrink-0 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-slate-400" />
        )}
      </button>

      {expanded && (
        <div className={`mt-3 space-y-3 overflow-y-auto ${maxScroll} pr-1`}>
          {showFlash && flashCount > 0 && (
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-red-400">Flash</span>
                {onDismissFlash && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDismissFlash()
                    }}
                    className="rounded p-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-300"
                    aria-label={t('alerts.dismissFlashAria')}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              <ul className="space-y-1.5">
                {flashAlerts.map((alert: any, idx: number) => (
                  <li
                    key={idx}
                    className="rounded border border-red-500/30 bg-red-500/10 px-2 py-1.5 text-xs text-red-100"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${severityBadge(alert.severity)}`}>
                        {String(alert.severity || '').toUpperCase()}
                      </span>
                      <span className="text-slate-500">
                        {new Date(alert.timestamp).toLocaleTimeString(timeLocale)}
                      </span>
                    </div>
                    <p className="mt-0.5 line-clamp-2">{alert.message}</p>
                    {alert.article_url && (
                      <a
                        href={alert.article_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-0.5 inline-block text-[11px] text-red-300 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {t('alerts.newsArrow')}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {anomalyCount > 0 && (
            <div>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-yellow-500">
                <AlertTriangle className="h-3.5 w-3.5" />
                {t('alerts.volumeSection')}
              </div>
              <ul className="space-y-1.5">
                {anomalyList.map((anomaly: any, idx: number) => {
                  const volumeMultiplier =
                    anomaly.volume && selectedTicker?.volume_24h
                      ? (anomaly.volume / (selectedTicker.volume_24h / 24)).toFixed(1)
                      : 'N/A'
                  return (
                    <li key={idx} className="rounded border border-yellow-500/25 bg-yellow-500/5 px-2 py-1.5 text-xs text-yellow-200">
                      <span className="font-medium text-yellow-400">#{idx + 1}</span> {t('alerts.volumeSpike')}{' '}
                      <strong>{volumeMultiplier}x</strong>
                      {anomaly.timestamp && (
                        <span className="ml-1 text-yellow-600">
                          ({new Date(anomaly.timestamp).toLocaleTimeString(timeLocale)})
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
              <p className="mt-1.5 text-[10px] text-yellow-600/90">{t('alerts.monitoringFooter')}</p>
            </div>
          )}
        </div>
      )}

      {variant === 'sidebar' && (
        <div className="mt-2 border-t border-slate-700 pt-2">
          <Link
            to="/news#piyasa-uyarilari"
            className="text-xs font-medium text-primary-400 hover:text-primary-300"
            onClick={(e) => e.stopPropagation()}
          >
            {t('alerts.openInNews')}
          </Link>
        </div>
      )}
    </div>
  )
}
