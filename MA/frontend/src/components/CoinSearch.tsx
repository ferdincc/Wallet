import { useState, useEffect } from 'react'
import { Search, TrendingUp } from 'lucide-react'
import { marketsApi, Ticker } from '../services/api'
import { useAppPreferences } from '../contexts/AppPreferencesContext'

interface CoinSearchProps {
  onSelect: (symbol: string, ticker?: Ticker) => void
  selectedSymbol?: string
}

const COMMON_COINS = [
  'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 
  'ADA/USDT', 'XRP/USDT', 'DOGE/USDT', 'MATIC/USDT',
  'DOT/USDT', 'AVAX/USDT', 'LINK/USDT', 'UNI/USDT'
]

export default function CoinSearch({ onSelect, selectedSymbol }: CoinSearchProps) {
  const { t } = useAppPreferences()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<string[]>([])
  const [ticker, setTicker] = useState<Ticker | null>(null)

  const loadTicker = async (symbol: string): Promise<Ticker | null> => {
    try {
      const data = await marketsApi.getTicker(symbol)
      setTicker(data)
      return data
    } catch (error) {
      console.error('Error loading ticker:', error)
      setTicker(null)
      return null
    }
  }

  useEffect(() => {
    if (selectedSymbol) {
      loadTicker(selectedSymbol)
    }
  }, [selectedSymbol])

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    if (!query.trim()) {
      setSearchResults([])
      return
    }

    const queryUpper = query.toUpperCase()
    const filtered = COMMON_COINS.filter(
      coin => coin.includes(queryUpper) || coin.replace('/USDT', '').includes(queryUpper)
    )
    setSearchResults(filtered.slice(0, 10))
  }

  const handleSelect = async (symbol: string) => {
    setSearchQuery('')
    setSearchResults([])
    const tickerData = await loadTicker(symbol)
    onSelect(symbol, tickerData || undefined)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      // Try to format as SYMBOL/USDT if not already
      let symbol = searchQuery.trim().toUpperCase()
      if (!symbol.includes('/')) {
        symbol = `${symbol}/USDT`
      }
      handleSelect(symbol)
    }
  }

  return (
    <div className="crypto-card !p-4">
      <div className="mb-4 flex items-center gap-2">
        <Search className="h-5 w-5 text-crypto-cyan" strokeWidth={2} />
        <h3 className="font-display text-lg font-semibold text-white">{t('coin.searchTitle')}</h3>
      </div>

      {/* Search Input */}
      <div className="relative mb-4">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder={t('coin.placeholder')}
          className="w-full rounded-xl border border-white/[0.08] bg-zinc-950/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder:text-zinc-600 focus:border-crypto-cyan/40 focus:outline-none focus:ring-1 focus:ring-crypto-cyan/30"
        />
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
      </div>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="relative z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-900/95 shadow-xl backdrop-blur-md">
          {searchResults.map((symbol) => (
            <button
              key={symbol}
              type="button"
              onClick={() => handleSelect(symbol)}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-white transition-colors hover:bg-white/[0.06]"
            >
              <TrendingUp className="h-4 w-4 text-crypto-cyan" />
              <span>{symbol}</span>
            </button>
          ))}
        </div>
      )}

      {/* Selected Coin Info */}
      {selectedSymbol && ticker && (
        <div className="mt-4 border-t border-white/[0.06] pt-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm text-zinc-500">{t('coin.selected')}</span>
            <span className="text-xs uppercase tracking-wide text-zinc-600">{ticker.exchange}</span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-xl font-bold text-white">{selectedSymbol}</span>
          </div>
          <div className="mt-2 flex items-center space-x-4">
            <div>
              <div className="text-xs text-zinc-500">{t('coin.price')}</div>
              <div className="text-lg font-semibold text-white">
                ${ticker.price?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">{t('coin.change24')}</div>
              <div className={`text-lg font-semibold ${
                (ticker.change_24h || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
              }`}>
                {ticker.change_24h ? `${ticker.change_24h >= 0 ? '+' : ''}${ticker.change_24h.toFixed(2)}%` : 'N/A'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Popular Coins Quick Access */}
      <div className="mt-4 border-t border-white/[0.06] pt-4">
        <div className="mb-2 text-xs text-zinc-500">{t('coin.popular')}</div>
        <div className="flex flex-wrap gap-2">
          {COMMON_COINS.slice(0, 6).map((coin) => (
            <button
              key={coin}
              type="button"
              onClick={() => handleSelect(coin)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                selectedSymbol === coin
                  ? 'border border-crypto-cyan/40 bg-crypto-cyan/15 text-crypto-cyan'
                  : 'border border-transparent bg-white/[0.05] text-zinc-400 hover:bg-white/[0.08] hover:text-white'
              }`}
            >
              {coin.replace('/USDT', '')}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

