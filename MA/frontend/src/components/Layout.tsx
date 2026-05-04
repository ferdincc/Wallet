import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { TrendingUp, Menu, X, Wallet } from 'lucide-react'
import { useAppPreferences } from '../contexts/AppPreferencesContext'
interface LayoutProps {
  children: React.ReactNode
  /** Chat gibi tam genişlik / dikey taşma düzeni */
  fullBleed?: boolean
}

const NAV = [{ to: '/wallet', labelKey: 'nav.wallet', icon: Wallet }] as const

export default function Layout({ children, fullBleed }: LayoutProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { t } = useAppPreferences()

  const linkClass = (active: boolean) =>
    `flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ${
      active
        ? 'bg-gradient-to-r from-crypto-cyan/20 to-crypto-violet/15 text-white shadow-glow border border-crypto-cyan/25'
        : 'text-zinc-400 hover:bg-white/[0.06] hover:text-white border border-transparent'
    }`

  return (
    <div
      className="relative flex h-full min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden font-sans"
    >
      <div className="app-shell-bg" aria-hidden />
      <div
        className="app-shell-grid"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '56px 56px',
        }}
        aria-hidden
      />
      <div
        className="app-orb h-[420px] w-[420px] -left-32 top-0 bg-crypto-cyan/30 animate-pulse-soft"
        aria-hidden
      />
      <div
        className="app-orb h-[380px] w-[380px] -right-24 top-1/4 bg-crypto-violet/35 animate-pulse-soft [animation-delay:1.5s]"
        aria-hidden
      />
      <div
        className="app-orb h-64 w-64 bottom-0 left-1/3 bg-emerald-500/20 animate-pulse-soft [animation-delay:0.8s]"
        aria-hidden
      />

      <motion.header
        initial={{ y: -12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="sticky top-0 z-50 border-b border-white/[0.06] bg-zinc-950/75 backdrop-blur-xl"
      >
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link
            to="/wallet"
            className="group flex shrink-0 items-center gap-2.5"
            onClick={() => setMobileOpen(false)}
          >
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-crypto-cyan/30 bg-gradient-to-br from-crypto-cyan/20 to-crypto-violet/20 shadow-glow">
              <TrendingUp className="h-5 w-5 text-crypto-cyan" strokeWidth={2.25} />
            </div>
            <div className="flex flex-col leading-tight">
              <span className="font-display text-lg font-bold tracking-tight text-white">OKYİSS</span>
              <span className="hidden text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-500 sm:block">
                {t('layout.tagline')}
              </span>
            </div>
          </Link>

          <nav className="hidden flex-1 flex-wrap items-center justify-end gap-1 lg:flex xl:gap-1.5">
            {NAV.map(({ to, labelKey, icon: Icon }) => {
              const active = location.pathname === to
              return (
                <Link key={to} to={to} className={linkClass(active)}>
                  <Icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={2} />
                  <span>{t(labelKey)}</span>
                </Link>
              )
            })}
          </nav>

          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-white lg:hidden"
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? t('layout.menuClose') : t('layout.menuOpen')}
            onClick={() => setMobileOpen((o) => !o)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden border-t border-white/[0.06] bg-zinc-950/95 backdrop-blur-xl lg:hidden"
            >
              <nav className="flex max-h-[min(70vh,calc(100dvh-5rem))] flex-col gap-1 overflow-y-auto p-4">
                {NAV.map(({ to, labelKey, icon: Icon }, i) => {
                  const active = location.pathname === to
                  return (
                    <motion.div
                      key={to}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                    >
                      <Link
                        to={to}
                        className={linkClass(active)}
                        onClick={() => setMobileOpen(false)}
                      >
                        <Icon className="h-4 w-4 shrink-0" strokeWidth={2} />
                        <span>{t(labelKey)}</span>
                      </Link>
                    </motion.div>
                  )
                })}
              </nav>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.header>

      <main
        className={
          fullBleed
            ? 'relative flex min-h-0 flex-1 flex-col overflow-hidden'
            : 'relative mx-auto min-h-0 w-full max-w-[1600px] flex-1 overflow-y-auto px-4 py-8 sm:px-6 lg:px-8 lg:py-10'
        }
      >
        {fullBleed ? (
          children
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.05 }}
            className="w-full"
          >
            {children}
          </motion.div>
        )}
      </main>
    </div>
  )
}
