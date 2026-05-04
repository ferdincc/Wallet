import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { Ticker } from '../services/api'

interface MarketCardProps {
  ticker: Ticker
  onClick?: () => void
}

export default function MarketCard({ ticker, onClick }: MarketCardProps) {
  const isPositive = (ticker.change_24h || 0) >= 0

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={onClick ? { y: -4, transition: { duration: 0.2 } } : undefined}
      whileTap={onClick ? { scale: 0.99 } : undefined}
      onClick={onClick}
      className={`crypto-card-hover ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-white">{ticker.symbol}</h3>
        <span className="text-xs uppercase tracking-wide text-zinc-500">{ticker.exchange}</span>
      </div>
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-2xl font-bold tracking-tight text-white">
          ${ticker.price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <div className={`flex items-center gap-1 ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
          {isPositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          <span className="text-sm font-semibold">
            {ticker.change_24h ? `${ticker.change_24h >= 0 ? '+' : ''}${ticker.change_24h.toFixed(2)}%` : 'N/A'}
          </span>
        </div>
      </div>
      <div className="text-xs text-zinc-500">
        24h vol: ${ticker.volume_24h?.toLocaleString('en-US', { maximumFractionDigits: 0 }) || 'N/A'}
      </div>
    </motion.div>
  )
}
