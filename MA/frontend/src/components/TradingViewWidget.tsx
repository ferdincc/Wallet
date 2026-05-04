import { useEffect, useRef } from 'react'

interface TradingViewWidgetProps {
  symbol: string
  exchange?: string
}

export default function TradingViewWidget({ symbol, exchange = 'BINANCE' }: TradingViewWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tvLocale = 'en'

  useEffect(() => {
    if (!containerRef.current) return

    // Clean up previous widget
    const container = containerRef.current
    container.innerHTML = ''

    // TradingView widget script
    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true

    // Format symbol for TradingView (remove /USDT, add exchange prefix if needed)
    const tvSymbol = symbol.replace('/USDT', '').replace('/', '')
    
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `${exchange}:${tvSymbol}USDT`,
      interval: '15',
      timezone: 'Europe/Istanbul',
      theme: 'dark',
      style: '1',
      locale: tvLocale,
      backgroundColor: 'rgba(15, 23, 42, 1)',
      gridColor: 'rgba(51, 65, 85, 0.3)',
      hide_side_toolbar: false,
      allow_symbol_change: false,
      calendar: false,
      support_host: 'https://www.tradingview.com',
      height: 600,
      width: '100%',
    })

    container.appendChild(script)

    // Cleanup function
    return () => {
      if (container && container.contains(script)) {
        container.removeChild(script)
      }
    }
  }, [symbol, exchange, tvLocale])

  return (
    <div className="tradingview-widget-container" ref={containerRef} style={{ height: '600px' }}>
      <div className="tradingview-widget-container__widget"></div>
    </div>
  )
}

