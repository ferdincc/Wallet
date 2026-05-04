import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

interface SentimentGaugeProps {
  score: number // 0-100
  sentiment: string
}

export default function SentimentGauge({ score, sentiment: _sentiment }: SentimentGaugeProps) {
  const { t } = useAppPreferences()
  const gaugeValue = Math.min(Math.max(score, 0), 100)

  let gaugeColor = '#f59e0b'
  let label = t('sentiment.gauge.neutral')

  if (gaugeValue < 25) {
    gaugeColor = '#dc2626'
    label = t('sentiment.gauge.extremeFear')
  } else if (gaugeValue < 45) {
    gaugeColor = '#f97316'
    label = t('sentiment.gauge.fear')
  } else if (gaugeValue < 55) {
    gaugeColor = '#f59e0b'
    label = t('sentiment.gauge.neutral')
  } else if (gaugeValue < 75) {
    gaugeColor = '#84cc16'
    label = t('sentiment.gauge.greed')
  } else {
    gaugeColor = '#22c55e'
    label = t('sentiment.gauge.extremeGreed')
  }

  const segments = [
    { start: 0, end: 25, color: '#dc2626', labelKey: 'sentiment.gauge.extremeFear' as const },
    { start: 25, end: 45, color: '#f97316', labelKey: 'sentiment.gauge.fear' as const },
    { start: 45, end: 55, color: '#f59e0b', labelKey: 'sentiment.gauge.neutral' as const },
    { start: 55, end: 75, color: '#84cc16', labelKey: 'sentiment.gauge.greed' as const },
    { start: 75, end: 100, color: '#22c55e', labelKey: 'sentiment.gauge.extremeGreed' as const },
  ]

  const simplePieData = [
    { name: 'filled', value: gaugeValue, fill: gaugeColor },
    { name: 'empty', value: 100 - gaugeValue, fill: '#1e293b' },
  ]

  return (
    <div className="flex flex-col items-center w-full">
      <div className="relative w-full max-w-md">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={simplePieData}
              cx="50%"
              cy="85%"
              startAngle={180}
              endAngle={0}
              innerRadius={70}
              outerRadius={90}
              paddingAngle={2}
              dataKey="value"
            >
              {simplePieData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>

        <div
          className="absolute top-0 left-0 right-0 bottom-0 flex flex-col items-center justify-center pointer-events-none"
          style={{ paddingTop: '20px' }}
        >
          <div className="text-5xl font-bold" style={{ color: gaugeColor }}>
            {gaugeValue}
          </div>
          <div className="text-lg font-semibold mt-2" style={{ color: gaugeColor }}>
            {label}
          </div>
          <div className="text-xs text-slate-400 mt-1">{t('sentiment.gauge.fearGreedSubtitle')}</div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-5 gap-2 text-xs w-full max-w-2xl">
        {segments.map((seg, idx) => (
          <div key={idx} className="flex items-center space-x-1">
            <div
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{ backgroundColor: seg.color }}
            />
            <span className="text-slate-400">{t(seg.labelKey)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
